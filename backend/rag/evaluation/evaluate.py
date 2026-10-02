"""Evaluate fund-scoped retrieval against real, page-cited factsheet chunks.

By default this is an offline retrieval evaluation: it builds a temporary
in-memory Qdrant collection and does not make model/API calls. Use
``--with-answers`` to exercise the answer service as well; that option calls
the configured Ollama model and may incur provider costs. The optional mode
disables the VLM fallback so the 20 questions have predictable text-model
usage.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# This runner is intentionally self-contained and uses the cached embedding
# artifact; it must not attempt to fetch model files from the network.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import yaml
from qdrant_client import QdrantClient


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fundlens_rag.ingestion.fund_metadata import attach_fund_names_to_chunks
from fundlens_rag.paths import CHUNKS_DIRECTORY
from fundlens_rag.rag.retriever import Retriever
from fundlens_rag.rag.vector_store import VectorStore


EVALUATION_DIRECTORY = Path(__file__).resolve().parent
DATASET_PATH = EVALUATION_DIRECTORY / "dataset.yaml"
DEFAULT_RESULTS_PATH = EVALUATION_DIRECTORY / "results.json"
COLLECTION_NAME = "fundlens_eval_temporary"


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _page_number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_dataset() -> dict[str, Any]:
    with DATASET_PATH.open(encoding="utf-8") as stream:
        dataset = yaml.safe_load(stream)
    if not isinstance(dataset, dict) or not isinstance(dataset.get("questions"), list):
        raise ValueError(f"Evaluation dataset is malformed: {DATASET_PATH}")
    if len(dataset["questions"]) != 20:
        raise ValueError(f"Expected 20 evaluation questions, found {len(dataset['questions'])}.")
    return dataset


def _load_eval_chunks(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    selected_chunks: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    for entry in dataset.get("corpus", {}).get("documents", []):
        document = str(entry["document"])
        chunk_path = CHUNKS_DIRECTORY / f"{Path(document).stem}.json"
        if not chunk_path.exists():
            raise FileNotFoundError(f"Cached chunks not found for {document}: {chunk_path}")
        with chunk_path.open(encoding="utf-8") as stream:
            chunks = json.load(stream)
        if not isinstance(chunks, list):
            raise ValueError(f"Chunk file must contain a JSON list: {chunk_path}")

        pages = {int(page) for page in entry.get("pages", [])}
        enriched = attach_fund_names_to_chunks(chunks)
        selected_chunks.extend(
            chunk for chunk in enriched
            if str(chunk.get("document") or "") == document
            and _page_number(chunk.get("page")) in pages
        )
        seen_documents.add(document)

    if not selected_chunks:
        raise ValueError("The evaluation corpus contains no chunks for the configured pages.")

    available_pages = {
        (str(chunk.get("document") or ""), _page_number(chunk.get("page")))
        for chunk in selected_chunks
    }
    for case in dataset["questions"]:
        expected_page = (str(case["expected_document"]), int(case["expected_page"]))
        if expected_page not in available_pages:
            raise ValueError(f"{case['id']} expects a page missing from the evaluation corpus: {expected_page}")
        if not case.get("expected_evidence_terms"):
            raise ValueError(f"{case['id']} needs at least one expected_evidence_terms entry.")

    return selected_chunks


def _percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percent * len(ordered)) - 1))
    return round(ordered[index], 2)


def _retrieval_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    if not total:
        return {}
    return {
        "expected_page_recall_at_5": round(sum(item["expected_page_rank"] is not None for item in results) / total, 4),
        "expected_page_mean_reciprocal_rank_at_5": round(sum(item["expected_page_reciprocal_rank"] for item in results) / total, 4),
        "expected_evidence_term_recall_at_5": round(sum(item["expected_evidence_term_recall"] for item in results) / total, 4),
        "fund_scope_purity_at_5": round(sum(item["fund_scope_purity"] for item in results) / total, 4),
        "citation_metadata_coverage_at_5": round(sum(item["citation_metadata_coverage"] for item in results) / total, 4),
        "retrieval_latency_ms_p50": _percentile([item["retrieval_latency_ms"] for item in results], 0.50),
        "retrieval_latency_ms_p95": _percentile([item["retrieval_latency_ms"] for item in results], 0.95),
    }


def _answer_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    answered = [item for item in results if item.get("answer") is not None]
    if (
        not answered
        or len(answered) != len(results)
        or any(item.get("execution_error") for item in results)
    ):
        return {
            "answer_fact_accuracy": None,
            "citation_page_accuracy": None,
            "citation_completeness": None,
            "grounding_pass_rate": None,
            "answer_grounded_accuracy": None,
            "confidence_brier_score": None,
            "high_confidence_error_rate_at_80": None,
            "mean_confidence_on_incorrect_answers": None,
            "overconfident_answer_count_at_80": 0,
            "average_confidence": None,
            "answered_questions": len(answered),
        }
    count = len(answered)
    correct = [
        bool(
            item.get("answer_facts_match")
            and item.get("citation_page_match")
            and item.get("citation_present")
            and item.get("grounding_pass")
        )
        for item in answered
    ]
    confidence = [float(item.get("confidence") or 0.0) for item in answered]
    incorrect_confidence = [score for score, is_correct in zip(confidence, correct) if not is_correct]
    high_confidence = [
        is_correct
        for score, is_correct in zip(confidence, correct)
        if score >= 0.80
    ]
    return {
        "answer_fact_accuracy": round(sum(bool(item["answer_facts_match"]) for item in answered) / count, 4),
        "citation_page_accuracy": round(sum(bool(item["citation_page_match"]) for item in answered) / count, 4),
        "citation_completeness": round(sum(bool(item["citation_present"]) for item in answered) / count, 4),
        "grounding_pass_rate": round(sum(bool(item["grounding_pass"]) for item in answered) / count, 4),
        # A response only counts as correct if both its expected facts and its
        # citation page are right and runtime grounding accepted the answer.
        "answer_grounded_accuracy": round(sum(correct) / count, 4),
        # Brier score measures whether reported confidence tracks this
        # binary, evaluation-set correctness label (lower is better).
        "confidence_brier_score": round(
            statistics.mean((score - float(is_correct)) ** 2 for score, is_correct in zip(confidence, correct)),
            4,
        ),
        "high_confidence_error_rate_at_80": (
            round(sum(not is_correct for is_correct in high_confidence) / len(high_confidence), 4)
            if high_confidence else None
        ),
        "mean_confidence_on_incorrect_answers": (
            round(statistics.mean(incorrect_confidence), 4) if incorrect_confidence else None
        ),
        "overconfident_answer_count_at_80": sum(
            score >= 0.80 and not is_correct
            for score, is_correct in zip(confidence, correct)
        ),
        "average_confidence": round(statistics.mean(confidence), 4),
        "answered_questions": count,
    }


def _answer_one(
    case: dict[str, Any],
    answer_service: Any,
    retriever: Retriever,
    usage_tracker: Any,
) -> dict[str, Any]:
    answer_service.retrieve_documents = retriever.retrieve
    # Evaluate the normal grounded text/table path separately from the
    # optional, more expensive vision fallback.
    answer_service.should_use_visual_fallback = lambda *_args, **_kwargs: False
    result = answer_service.answer_fundlens_question(
        case["question"],
        fund_scope=case["fund_scope"],
        top_k=5,
        usage_tracker=usage_tracker,
    )
    return result


def _model_usage(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        for usage in result.get("model_usage", []):
            key = (str(usage.get("role", "unknown")), str(usage.get("model", "unknown")))
            record = totals.setdefault(key, {
                "role": key[0], "model": key[1], "requests": 0,
                "input_tokens": 0, "output_tokens": 0,
                "input_reports": 0, "output_reports": 0,
                "estimated_cost_values": [],
            })
            for field in ("requests", "input_tokens", "output_tokens", "input_reports", "output_reports"):
                record[field] += int(usage.get(field) or 0)
            cost = str(usage.get("estimated_cost") or "")
            if cost.startswith("$"):
                try:
                    record["estimated_cost_values"].append(float(cost[1:]))
                except ValueError:
                    pass
    output = []
    for record in totals.values():
        costs = record.pop("estimated_cost_values")
        record["estimated_cost_usd"] = round(sum(costs), 8) if costs else None
        output.append(record)
    return output


def run_evaluation(*, top_k: int = 5, with_answers: bool = False, output_path: Path = DEFAULT_RESULTS_PATH) -> dict[str, Any]:
    dataset = _load_dataset()
    cases = dataset["questions"]
    chunks = _load_eval_chunks(dataset)

    client = QdrantClient(":memory:")
    try:
        store = VectorStore(client=client, collection_name=COLLECTION_NAME)
        store.add_documents(chunks)
        retriever = Retriever(client=client, collection_name=COLLECTION_NAME)
        # Exclude one-time model warm-up from per-question retrieval timings.
        retriever.embedding_model.embed_query("FundLens evaluation warm-up")

        answer_service = None
        model_name = None
        if with_answers:
            from dotenv import load_dotenv
            from fundlens_rag.app.usage import UsageTracker

            load_dotenv(BACKEND_ROOT / ".env")
            if not os.getenv("OLLAMA_API_KEY") or not os.getenv("OLLAMA_MODEL"):
                raise RuntimeError("--with-answers requires OLLAMA_API_KEY and OLLAMA_MODEL in backend/.env.")
            from fundlens_rag import service as answer_service

            model_name = os.getenv("OLLAMA_MODEL")

        report: dict[str, Any] = {
            "version": dataset.get("version", "unknown"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "evaluation_mode": "in_memory_retrieval_and_answer" if with_answers else "in_memory_retrieval_only",
            "model": model_name,
            "embedding_model": "intfloat/multilingual-e5-base",
            "vector_store": "temporary in-memory Qdrant",
            "corpus_chunks": len(chunks),
            "corpus_pages": dataset.get("corpus", {}).get("documents", []),
            "total_questions": len(cases),
            "evaluated_questions": 0,
            "answer_questions_answered": 0,
            "answer_question_errors": 0,
            "answer_evaluation_complete": None if not with_answers else False,
            "model_calls_made": 0,
            "metrics": {},
            "questions": [],
            "notes": [
                "The temporary collection is populated from the checked-in page-aware chunk JSON; the application Qdrant service and data are not modified.",
                "Page 64 from HDFC ELSS - Tax Saver Fund is deliberately included as a wrong-fund citation distractor.",
            ],
        }
        if not with_answers:
            report["notes"].append("Answer generation, confidence, citation correctness, and model cost were not evaluated; no model/API requests were made. Pass --with-answers for that pass.")

        for index, case in enumerate(cases, start=1):
            started = time.perf_counter()
            retrieved = retriever.retrieve(
                query=case["question"],
                top_k=top_k,
                fund_name=case["fund_scope"],
                document_type="factsheet",
            )
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            expected_document = str(case["expected_document"])
            expected_page = int(case["expected_page"])
            expected_rank = next((rank for rank, chunk in enumerate(retrieved, start=1)
                                  if chunk.get("document") == expected_document
                                  and _page_number(chunk.get("page")) == expected_page), None)
            expected_page_chunks = [chunk for chunk in retrieved
                                    if chunk.get("document") == expected_document
                                    and _page_number(chunk.get("page")) == expected_page]
            evidence_text = _normalize(" ".join(str(chunk.get("text", "")) for chunk in expected_page_chunks))
            expected_terms = case["expected_evidence_terms"]
            found_terms = [term for term in expected_terms if _normalize(term) in evidence_text]
            returned_fund_names = [chunk.get("fund_name") for chunk in retrieved]
            complete_metadata = bool(retrieved) and all(
                chunk.get("document") and _page_number(chunk.get("page")) is not None
                for chunk in retrieved
            )

            row: dict[str, Any] = {
                "id": case["id"],
                "question": case["question"],
                "fund_scope": case["fund_scope"],
                "expected_document": expected_document,
                "expected_page": expected_page,
                "expected_page_rank": expected_rank,
                "expected_page_reciprocal_rank": round(1 / expected_rank, 4) if expected_rank else 0.0,
                "expected_evidence_terms": expected_terms,
                "found_evidence_terms": found_terms,
                "expected_evidence_term_recall": round(len(found_terms) / len(expected_terms), 4),
                "fund_scope_purity": round(sum(name == case["fund_scope"] for name in returned_fund_names) / len(retrieved), 4) if retrieved else 0.0,
                "citation_metadata_coverage": 1.0 if complete_metadata else 0.0,
                "retrieval_latency_ms": duration_ms,
                "retrieved_chunks": [
                    {
                        "document": chunk.get("document"),
                        "page": _page_number(chunk.get("page")),
                        "fund_name": chunk.get("fund_name"),
                        "score": round(float(chunk["score"]), 4) if chunk.get("score") is not None else None,
                        "text_preview": str(chunk.get("text", ""))[:360],
                    }
                    for chunk in retrieved
                ],
                "answer": None,
                "answer_facts_match": None,
                "citation_page_match": None,
                "citation_present": None,
                "grounding_pass": None,
                "confidence": None,
                "model_usage": [],
                "error": None,
                "execution_error": None,
            }

            if with_answers and answer_service is not None:
                usage_tracker = UsageTracker()
                try:
                    generated = _answer_one(
                        case,
                        answer_service,
                        retriever,
                        usage_tracker,
                    )
                    answer_text = str(generated.get("answer") or "")
                    normalized_answer = _normalize(answer_text)
                    required_answer_terms = case.get("expected_answer_terms", [])
                    required_answer_patterns = case.get("expected_answer_patterns", [])
                    found_answer_terms = [term for term in required_answer_terms if _normalize(term) in normalized_answer]
                    matched_answer_patterns = [pattern for pattern in required_answer_patterns if re.search(pattern, answer_text)]
                    row.update({
                        "answer": answer_text,
                        "answer_facts_found": found_answer_terms,
                        "answer_patterns_matched": matched_answer_patterns,
                        "answer_facts_match": bool(required_answer_terms or required_answer_patterns)
                        and len(found_answer_terms) == len(required_answer_terms)
                        and len(matched_answer_patterns) == len(required_answer_patterns),
                        "citation_present": bool(generated.get("sources")),
                        "citation_page_match": any(
                            source.get("document") == expected_document
                            and _page_number(source.get("page")) == expected_page
                            for source in generated.get("sources", [])
                        ),
                        "grounding_pass": bool(generated.get("success"))
                        and generated.get("grounding_error") is None
                        and generated.get("draft_answer") is None,
                        "confidence": float(generated.get("confidence") or 0.0),
                        "answer_method": generated.get("answer_method"),
                        "model_usage": generated.get("usage", []),
                        "error": generated.get("error_code"),
                    })
                    row["answer_grounded_correct"] = bool(
                        row["answer_facts_match"]
                        and row["citation_page_match"]
                        and row["citation_present"]
                        and row["grounding_pass"]
                    )
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    row["execution_error"] = row["error"]
                    # Preserve failed provider attempts (without prompts or
                    # answers) so a 404/timeout cannot look like zero usage.
                    row["model_usage"] = usage_tracker.snapshot()

            report["questions"].append(row)
            report["evaluated_questions"] += 1
            if with_answers:
                report["answer_questions_answered"] = sum(
                    item.get("answer") is not None for item in report["questions"]
                )
                report["answer_question_errors"] = sum(
                    bool(item.get("execution_error")) for item in report["questions"]
                )
                report["answer_evaluation_complete"] = (
                    report["evaluated_questions"] == report["total_questions"]
                    and report["answer_questions_answered"] == report["total_questions"]
                    and report["answer_question_errors"] == 0
                )
            report["model_calls_made"] += sum(int(item.get("requests") or 0) for item in row["model_usage"])
            report["metrics"] = _retrieval_metrics(report["questions"])
            report["metrics"].update(_answer_metrics(report["questions"]))
            report["model_usage"] = _model_usage(report["questions"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            status = f"page rank {expected_rank}" if expected_rank else "expected page NOT in top results"
            print(f"[{index:02d}/{len(cases):02d}] {case['id']}: {status}; evidence {len(found_terms)}/{len(expected_terms)}; {duration_ms:.1f} ms")

        return report
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve per question (default: 5).")
    parser.add_argument("--with-answers", action="store_true", help="Also call the configured Ollama answer model; provider charges may apply. VLM fallback stays off.")
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_PATH, help="JSON report destination (default: evaluation/results.json).")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    report = run_evaluation(top_k=args.top_k, with_answers=args.with_answers, output_path=args.output)
    print("\nEvaluation summary")
    for key, value in report["metrics"].items():
        print(f"  {key}: {value}")
    print(f"  evaluated_questions: {report['evaluated_questions']}/{report['total_questions']}")
    if args.with_answers:
        print(
            "  answer_evaluation: "
            f"{report['answer_questions_answered']}/{report['total_questions']} answered; "
            f"{report['answer_question_errors']} execution errors; "
            f"complete={report['answer_evaluation_complete']}"
        )
    print(f"  model_calls_made: {report['model_calls_made']}")
    print(f"  report: {report['output_path'] if 'output_path' in report else args.output}")
    if args.with_answers and not report["answer_evaluation_complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
