"""Reusable, UI-independent RAG answer service for FundLens."""

from __future__ import annotations

import logging
from typing import Any

from fundlens_rag.app.llm import generate_response, get_llm
from fundlens_rag.app.prompts import build_prompt
from fundlens_rag.app.schemas import LLMResponse
from fundlens_rag.app.usage import UsageTracker
from fundlens_rag.app.vision_fallback import (
    extract_visual_evidence,
    should_use_visual_fallback,
)
from fundlens_rag.ingestion.fund_metadata import (
    list_known_funds,
    resolve_fund_name,
)
from fundlens_rag.ingestion.table_aware import answer_table_question
from fundlens_rag.rag.citations import (
    build_citations,
    format_context_with_citations,
)
from fundlens_rag.paths import CHUNKS_DIRECTORY, MARKDOWN_DIRECTORY
from fundlens_rag.rag.grounding import GroundingError, ground_answer
from fundlens_rag.rag.retriever import retrieve_documents


NO_EVIDENCE_ANSWER = (
    "I could not find sufficient evidence in the retrieved documents to answer "
    "this question."
)
logger = logging.getLogger("fundlens")


def answer_fundlens_question(
    question: str,
    fund_scope: str | None = None,
    *,
    prompt_version: str = "v1",
    top_k: int = 5,
    usage_tracker: UsageTracker | None = None,
) -> dict[str, Any]:
    """Return a grounded FundLens answer and its evidence as plain data.

    This function has no Streamlit or Django dependency, so it can serve the
    standalone UI and the main application's API. It only searches the
    prepared Qdrant index; ingestion runs through a separate management task.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    tracker = usage_tracker or UsageTracker()
    indexed_documents: list[str] = []
    known_funds = list_known_funds(MARKDOWN_DIRECTORY, CHUNKS_DIRECTORY)
    selected_fund = resolve_fund_name(fund_scope or question, known_funds)
    if selected_fund is None:
        return _base_result(tracker, indexed_documents) | {
            "success": False,
            "error_code": "fund_not_resolved",
            "answer": "Please select a fund or include its full name in the question.",
        }

    retrieved_chunks = retrieve_documents(
        query=question,
        top_k=top_k,
        fund_name=selected_fund,
        document_type="factsheet",
    )
    result = _base_result(tracker, indexed_documents)
    result.update(
        {
            "fund_name": selected_fund,
            "retrieved_chunks": retrieved_chunks,
        }
    )

    if not retrieved_chunks:
        result.update(
            {
                "success": False,
                "error_code": "no_retrieved_chunks",
                "answer": NO_EVIDENCE_ANSWER,
            }
        )
        return result

    table_answer = answer_table_question(question, retrieved_chunks)
    llm = None
    if table_answer:
        response = LLMResponse(answer=table_answer, confidence=0.85)
    else:
        prompt = build_prompt(
            question=question,
            context=format_context_with_citations(retrieved_chunks),
            version=prompt_version,
        )
        llm = get_llm()
        response = generate_response(
            prompt=prompt,
            llm=llm,
            usage_tracker=tracker,
        )

    grounding_error: GroundingError | None = None
    try:
        response.answer, verified_chunks = ground_answer(
            answer=response.answer,
            retrieved_chunks=retrieved_chunks,
            question=question,
        )
    except GroundingError as exc:
        grounding_error = exc
        verified_chunks = []

    visual_fallback_triggered = should_use_visual_fallback(
        answer=response.answer,
        confidence=response.confidence,
        grounding_error=grounding_error,
    )
    visual_fallback_used = False
    if visual_fallback_triggered:
        visual_chunks = extract_visual_evidence(
            question=question,
            retrieved_chunks=retrieved_chunks,
            usage_tracker=tracker,
        )
        if visual_chunks:
            visual_prompt = build_prompt(
                question=question,
                context=format_context_with_citations(visual_chunks),
                version=prompt_version,
            )
            try:
                if llm is None:
                    llm = get_llm()
                visual_response = generate_response(
                    prompt=visual_prompt,
                    llm=llm,
                    usage_tracker=tracker,
                )
                visual_response.answer, visual_verified_chunks = ground_answer(
                    answer=visual_response.answer,
                    retrieved_chunks=visual_chunks,
                    question=question,
                )
                if not should_use_visual_fallback(
                    answer=visual_response.answer,
                    confidence=visual_response.confidence,
                ):
                    response = visual_response
                    verified_chunks = visual_verified_chunks
                    response.confidence = min(response.confidence, 0.65)
                    grounding_error = None
                    visual_fallback_used = True
            except Exception as exc:
                # Keep the original grounded/withheld RAG outcome if the
                # optional visual fallback is unavailable or cannot ground.
                logger.warning(
                    "Ollama visual fallback did not produce a grounded answer: %s",
                    exc,
                )

    draft_answer = None
    if grounding_error is not None:
        draft_answer = response.answer
        response.answer = NO_EVIDENCE_ANSWER
        response.confidence = 0.0
        verified_chunks = []

    response.confidence = min(response.confidence, 0.85)
    citations = build_citations([chunk for _, chunk in verified_chunks])
    source_labels = _source_labels_for_citations(verified_chunks)
    vision_requests = sum(
        record["requests"]
        for record in tracker.snapshot()
        if record["role"] == "vision"
    )

    if visual_fallback_used:
        answer_method = "rag_plus_vlm"
    elif vision_requests:
        answer_method = "rag_vlm_unaccepted"
    elif visual_fallback_triggered:
        answer_method = "rag_vlm_unavailable"
    elif table_answer:
        answer_method = "rag_table"
    else:
        answer_method = "rag_only"

    result.update(
        {
            "success": True,
            "error_code": None,
            "answer": response.answer,
            "draft_answer": draft_answer,
            "confidence": response.confidence,
            "answer_method": answer_method,
            "visual_fallback_triggered": visual_fallback_triggered,
            "visual_fallback_used": visual_fallback_used,
            "table_answer_used": bool(table_answer),
            "grounding_error": str(grounding_error) if grounding_error else None,
            "sources": [
                {
                    **source.model_dump(),
                    "labels": source_labels.get(
                        (source.document, source.page, source.source_url), []
                    ),
                }
                for source in citations
            ],
        }
    )
    # Capture calls made by both the answer and optional vision models.
    result["usage"] = tracker.snapshot()
    return result


def _base_result(
    tracker: UsageTracker,
    indexed_documents: list[str],
) -> dict[str, Any]:
    return {
        "success": False,
        "error_code": None,
        "answer": NO_EVIDENCE_ANSWER,
        "draft_answer": None,
        "confidence": 0.0,
        "fund_name": None,
        "answer_method": "rag_only",
        "visual_fallback_triggered": False,
        "visual_fallback_used": False,
        "table_answer_used": False,
        "grounding_error": None,
        "sources": [],
        "retrieved_chunks": [],
        "usage": tracker.snapshot(),
        "indexed_documents": indexed_documents,
    }


def _source_labels_for_citations(
    verified_chunks: list[tuple[int, dict[str, Any]]],
) -> dict[tuple[str, int, str], list[str]]:
    labels: dict[tuple[str, int, str], list[str]] = {}
    for index, chunk in verified_chunks:
        document = chunk.get("document")
        page = chunk.get("page")
        source_url = chunk.get("source_url")
        if document and page is not None and source_url:
            key = (str(document), int(page), str(source_url))
            labels.setdefault(key, []).append(f"SOURCE {index}")
    return labels
