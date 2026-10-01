from pathlib import Path
import re
import sys

import streamlit as st
from dotenv import load_dotenv

# Streamlit executes this file as a script.  Ensure the project root is on
# ``sys.path`` so package imports work even when launched from ``app/``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.llm import generate_response, get_llm
from app.logging_config import logger
from app.prompts import build_prompt
from app.schemas import LLMResponse
from app.usage import UsageTracker
from app.vision_fallback import (
    extract_visual_evidence,
    should_use_visual_fallback,
)
from ingestion.fund_metadata import list_known_funds, resolve_fund_name
from rag.citations import build_citations, format_context_with_citations
from rag.factsheets import (
    CHUNKS_DIRECTORY,
    MARKDOWN_DIRECTORY,
    ensure_factsheets_indexed,
    find_factsheets,
)
from rag.grounding import GroundingError, ground_answer
from rag.retriever import retrieve_documents
from ingestion.pdf_parser import get_docling_device_label
from ingestion.table_aware import answer_table_question


load_dotenv()
FUND_AUTO_OPTION = "Auto-detect from question"


st.set_page_config(
    page_title="FundLens RAG",
    page_icon="📊",
    layout="wide",
)


st.title("📊 FundLens RAG")
st.caption(
    "Mutual-fund document research with evidence-backed answers."
)


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

with st.sidebar:
    st.header("RAG Settings")

    prompt_version = st.selectbox(
        "Prompt version",
        ["v1"],
    )
    lenient_mode = st.checkbox(
        "Show unverified drafts (lenient mode)",
        value=True,
        help=(
            "When grounding fails, show the model's draft with a clear warning. "
            "Confidence remains 0% and no citation is attached. Turn this off "
            "to withhold ungrounded drafts."
        ),
    )
    known_funds = list_known_funds(MARKDOWN_DIRECTORY, CHUNKS_DIRECTORY)
    fund_options = [FUND_AUTO_OPTION, *known_funds]
    fund_scope_selection = st.selectbox(
        "Fund scope",
        fund_options,
        help=(
            "Choose a fund or let FundLens detect its name in your question. "
            "Retrieval is limited to the selected fund."
        ),
    )
    if not known_funds:
        st.caption(
            "Fund names will appear after the factsheets are indexed."
        )

    st.divider()

    factsheets = find_factsheets()
    st.caption(f"{len(factsheets)} factsheet(s) available")
    st.caption(f"PDF processing: {get_docling_device_label()}")
    for factsheet in factsheets:
        st.caption(f"• {factsheet.name}")


# ---------------------------------------------------------
# Question
# ---------------------------------------------------------

question = st.text_input(
    "Ask a question about a mutual fund document",
    placeholder="Why did the fund increase its exposure to IT?",
)


def _save_session_usage(usage_tracker: UsageTracker) -> list[dict]:
    current = usage_tracker.snapshot()
    if not current:
        return st.session_state.get("_fundlens_model_usage_totals", [])

    previous = st.session_state.get("_fundlens_model_usage_totals", [])
    totals = UsageTracker.merge_snapshots(previous, current)
    st.session_state["_fundlens_model_usage_totals"] = totals
    return totals


def _show_usage_report(
    usage_tracker: UsageTracker,
) -> None:
    turn_records = usage_tracker.snapshot()
    st.subheader("Model / API usage for this answer")
    if turn_records:
        st.table(UsageTracker.display_rows(turn_records))
        st.caption(
            "Request counts include attempted calls. Token counts are shown "
            "only when returned by Ollama; cost needs configured per-model rates."
        )
    else:
        st.caption("No model API requests were recorded for this answer.")

    session_records = st.session_state.get("_fundlens_model_usage_totals", [])
    if session_records:
        with st.expander("Browser-session totals"):
            st.table(UsageTracker.display_rows(session_records))
            st.caption(
                "Totals are kept only for this Streamlit browser session and "
                "reset when the session ends."
            )


def _show_retrieved_chunks(
    chunks: list[dict],
    *,
    empty_message: str = "Fund-scoped retrieval returned no chunks.",
) -> None:
    """Expose the exact retrieval payload so answers can be audited in the UI."""
    with st.expander(f"Retrieved chunks ({len(chunks)})", expanded=True):
        if not chunks:
            st.info(empty_message)
            return

        for index, chunk in enumerate(chunks, start=1):
            document = str(chunk.get("document") or "Unknown document")
            page = chunk.get("page")
            score = chunk.get("score")
            score_text = (
                f"{float(score):.4f}"
                if isinstance(score, (int, float))
                else "not provided"
            )
            st.text(
                f"[SOURCE {index}] {document} · PDF page {page or 'unknown'} "
                f"· retrieval score {score_text}"
            )
            st.text(str(chunk.get("text", "")))


def _strip_unverified_source_labels(answer: str) -> str:
    """Avoid presenting model-generated source labels as valid citations."""
    return re.sub(r"\s*\[SOURCE\s+\d+\]", "", answer, flags=re.IGNORECASE).strip()


# ---------------------------------------------------------
# Generate
# ---------------------------------------------------------

if st.button("Ask FundLens", type="primary"):

    if not question.strip():
        st.warning("Please enter a question.")
        st.stop()

    usage_tracker = UsageTracker()
    visual_fallback_triggered = False
    table_answer = None
    ungrounded_draft = None
    grounding_error = None
    retrieved_chunks: list[dict] = []
    selected_fund_name = None

    try:
        with st.spinner("Analyzing documents..."):
            current_funds = list_known_funds(MARKDOWN_DIRECTORY, CHUNKS_DIRECTORY)
            indexed_documents = []
            indexing_checked = False
            if not current_funds:
                # A clean checkout may not have generated Markdown/chunk data
                # yet. Index once to discover the scheme catalog, then still
                # require a resolved fund before any retrieval is run.
                indexed_documents = ensure_factsheets_indexed()
                indexing_checked = True
                current_funds = list_known_funds(
                    MARKDOWN_DIRECTORY,
                    CHUNKS_DIRECTORY,
                )

            if fund_scope_selection == FUND_AUTO_OPTION:
                selected_fund_name = resolve_fund_name(question, current_funds)
            else:
                selected_fund_name = resolve_fund_name(
                    fund_scope_selection,
                    current_funds,
                )

            if selected_fund_name is None:
                st.warning(
                    "I couldn't confidently identify the fund. Choose one in "
                    "the sidebar or include its name in the question."
                )
                _show_retrieved_chunks(
                    [],
                    empty_message=(
                        "No corpus search was run because a fund could not be "
                        "resolved. This avoids mixing results from different funds."
                    ),
                )
                st.stop()

            st.caption(f"Fund scope: {selected_fund_name}")

            if not indexing_checked:
                indexed_documents = ensure_factsheets_indexed()

            retrieved_chunks = retrieve_documents(
                query=question,
                top_k=5,
                fund_name=selected_fund_name,
                document_type="factsheet",
            )

            if not retrieved_chunks:
                st.warning(
                    "I could not find relevant content in the indexed factsheets."
                )
                _show_retrieved_chunks(retrieved_chunks)
                st.stop()

            table_answer = answer_table_question(question, retrieved_chunks)
            visual_fallback_used = False
            llm = None
            if table_answer:
                response = LLMResponse(answer=table_answer, confidence=0.85)
                try:
                    response.answer, verified_chunks = ground_answer(
                        answer=response.answer,
                        retrieved_chunks=retrieved_chunks,
                        question=question,
                    )
                    grounding_error = None
                except GroundingError as exc:
                    grounding_error = exc
                    verified_chunks = []
            else:
                context = format_context_with_citations(retrieved_chunks)

                prompt = build_prompt(
                    question=question,
                    context=context,
                    version=prompt_version,
                )

                llm = get_llm()

                response = generate_response(
                    prompt=prompt,
                    llm=llm,
                    usage_tracker=usage_tracker,
                )

                try:
                    response.answer, verified_chunks = ground_answer(
                        answer=response.answer,
                        retrieved_chunks=retrieved_chunks,
                        question=question,
                    )
                    grounding_error = None
                except GroundingError as exc:
                    grounding_error = exc
                    verified_chunks = []

            visual_fallback_triggered = should_use_visual_fallback(
                answer=response.answer,
                confidence=response.confidence,
                grounding_error=grounding_error,
            )
            if visual_fallback_triggered:
                visual_chunks = extract_visual_evidence(
                    question=question,
                    retrieved_chunks=retrieved_chunks,
                    usage_tracker=usage_tracker,
                )

                if visual_chunks:
                    # The fallback answer is generated from the visual
                    # transcription alone, so a misleading retrieved page
                    # cannot be cited alongside the page actually inspected.
                    visual_context = format_context_with_citations(visual_chunks)
                    visual_prompt = build_prompt(
                        question=question,
                        context=visual_context,
                        version=prompt_version,
                    )
                    try:
                        if llm is None:
                            llm = get_llm()
                        visual_response = generate_response(
                            prompt=visual_prompt,
                            llm=llm,
                            usage_tracker=usage_tracker,
                        )
                        (
                            visual_response.answer,
                            visual_verified_chunks,
                        ) = ground_answer(
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
                        logger.warning(
                            "Ollama visual evidence did not produce a grounded answer: %s",
                            exc,
                        )

            if grounding_error is not None:
                ungrounded_draft = response.answer
                logger.warning(
                    "Withholding ungrounded RAG answer: %s",
                    grounding_error,
                )
                response.answer = (
                    "I could not find sufficient evidence in the retrieved "
                    "documents to answer this question."
                )
                response.confidence = 0.0
                verified_chunks = []

            # Citations always come from verified retrieval metadata, never
            # from LLM-generated document names, pages, or URLs.
            citations = build_citations(
                [chunk for _, chunk in verified_chunks]
            )
            source_labels: dict[tuple[str, int, str], list[int]] = {}
            for index, chunk in verified_chunks:
                document = chunk.get("document")
                page = chunk.get("page")
                source_url = chunk.get("source_url")
                if document and page is not None and source_url:
                    key = (document, int(page), source_url)
                    source_labels.setdefault(key, []).append(index)

            # Model confidence is not calibrated. Keep a cited answer below
            # certainty; ungrounded answers were already reduced to zero.
            response.confidence = min(response.confidence, 0.85)

        if indexed_documents:
            st.success(
                f"Indexed {len(indexed_documents)} new factsheet(s)."
            )

        st.subheader("Answer")

        if ungrounded_draft is not None and lenient_mode:
            st.warning(
                "Unverified draft — the grounding check failed. Check the "
                "retrieved chunks below; this is not a verified answer."
            )
            st.write(_strip_unverified_source_labels(ungrounded_draft))
            if grounding_error is not None:
                st.caption(f"Grounding check: {grounding_error}")
        else:
            st.write(response.answer)

        if visual_fallback_used:
            st.caption(
                "A retrieved PDF page was checked with Ollama vision "
                "to verify the evidence."
            )

        st.subheader("Confidence")

        st.progress(response.confidence)

        st.write(
            f"{response.confidence:.0%}"
        )

        vision_calls = sum(
            record["requests"]
            for record in usage_tracker.snapshot()
            if record["role"] == "vision"
        )
        st.subheader("Answer method")
        if visual_fallback_used:
            st.info(
                "RAG + VLM fallback — a PDF page was read visually, then the "
                "answer was grounded against that page."
            )
        elif vision_calls:
            st.info(
                "RAG only — the VLM fallback was tried, but its evidence was "
                "not accepted for the final answer."
            )
        elif visual_fallback_triggered:
            st.info(
                "RAG only — the VLM fallback was triggered but did not make a "
                "model request or return usable evidence."
            )
        elif table_answer:
            st.info(
                "RAG only — answered from retrieved, table-aware document data; "
                "no VLM was needed."
            )
        else:
            st.info(
                "RAG only — answered from retrieved document text; no VLM was needed."
            )

        _save_session_usage(usage_tracker)
        _show_usage_report(usage_tracker)
        _show_retrieved_chunks(retrieved_chunks)

        if citations:

            st.subheader("Sources")

            for source in citations:
                key = (source.document, source.page, source.source_url)
                labels = ", ".join(
                    f"SOURCE {index}"
                    for index in source_labels.get(key, [])
                )

                st.markdown(
                    f"- **[{labels}] {source.document}**, page {source.page}"
                )

        else:
            st.info(
                "No retrieved source could be verified for this answer."
            )

    except Exception as exc:

        logger.exception(
            "Failed to generate RAG response"
        )

        st.error(
            f"Unable to generate response: {exc}"
        )

        _save_session_usage(usage_tracker)
        _show_usage_report(usage_tracker)
        _show_retrieved_chunks(retrieved_chunks)
