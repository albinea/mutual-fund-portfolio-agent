from pathlib import Path
import re
import sys

import streamlit as st
from dotenv import load_dotenv

# Streamlit executes this file as a script. Add ``backend`` to the path so
# both the standalone UI and Django import one collision-free package.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fundlens_rag.app.logging_config import logger
from fundlens_rag.app.usage import UsageTracker
from fundlens_rag.ingestion.fund_metadata import list_known_funds
from fundlens_rag.paths import CHUNKS_DIRECTORY, MARKDOWN_DIRECTORY
from fundlens_rag.rag.factsheets import find_factsheets
from fundlens_rag.service import answer_fundlens_question


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
    for factsheet in factsheets:
        st.caption(f"• {factsheet.name}")
    st.caption(
        "Index new PDFs separately with `python manage.py index_factsheets` "
        "from the backend directory."
    )


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
    retrieved_chunks: list[dict] = []

    try:
        with st.spinner("Analyzing documents..."):
            result = answer_fundlens_question(
                question=question,
                fund_scope=(
                    None
                    if fund_scope_selection == FUND_AUTO_OPTION
                    else fund_scope_selection
                ),
                prompt_version=prompt_version,
                top_k=5,
                usage_tracker=usage_tracker,
            )

        retrieved_chunks = result["retrieved_chunks"]
        if result["error_code"] == "fund_not_resolved":
            st.warning(
                "I couldn't confidently identify the fund. Choose one in the "
                "sidebar or include its name in the question."
            )
            _show_retrieved_chunks(
                retrieved_chunks,
                empty_message=(
                    "No corpus search was run because a fund could not be "
                    "resolved. This avoids mixing results from different funds."
                ),
            )
            st.stop()

        if result["error_code"] == "no_retrieved_chunks":
            st.warning(
                "I could not find relevant content in the indexed factsheets."
            )

        if result.get("fund_name"):
            st.caption(f"Fund scope: {result['fund_name']}")

        st.subheader("Answer")
        if result["draft_answer"] is not None and lenient_mode:
            st.warning(
                "Unverified draft — the grounding check failed. Check the "
                "retrieved chunks below; this is not a verified answer."
            )
            st.write(_strip_unverified_source_labels(result["draft_answer"]))
            if result["grounding_error"]:
                st.caption(f"Grounding check: {result['grounding_error']}")
        else:
            st.write(result["answer"])

        if result["visual_fallback_used"]:
            st.caption(
                "A retrieved PDF page was checked with Ollama vision "
                "to verify the evidence."
            )

        st.subheader("Confidence")
        st.progress(result["confidence"])
        st.write(f"{result['confidence']:.0%}")

        st.subheader("Answer method")
        method_messages = {
            "rag_plus_vlm": (
                "RAG + VLM fallback — a retrieved PDF page was read visually, "
                "then the answer was grounded against that page."
            ),
            "rag_vlm_unaccepted": (
                "RAG only — the VLM fallback was tried, but its evidence was "
                "not accepted for the final answer."
            ),
            "rag_vlm_unavailable": (
                "RAG only — the VLM fallback was triggered but did not make a "
                "model request or return usable evidence."
            ),
            "rag_table": (
                "RAG only — answered from retrieved, table-aware document data; "
                "no VLM was needed."
            ),
            "rag_only": (
                "RAG only — answered from retrieved document text; no VLM was needed."
            ),
        }
        st.info(method_messages[result["answer_method"]])

        _save_session_usage(usage_tracker)
        _show_usage_report(usage_tracker)
        _show_retrieved_chunks(retrieved_chunks)

        if result["sources"]:
            st.subheader("Sources")
            for source in result["sources"]:
                labels = ", ".join(f"[{label}]" for label in source["labels"])
                st.markdown(
                    f"- **{labels} {source['document']}**, page {source['page']}"
                )
        else:
            st.info("No retrieved source could be verified for this answer.")

    except Exception as exc:
        logger.exception("Failed to generate RAG response")
        st.error(f"Unable to generate response: {exc}")
        _save_session_usage(usage_tracker)
        _show_usage_report(usage_tracker)
        _show_retrieved_chunks(retrieved_chunks)
