from pathlib import Path
import sys

import streamlit as st
from dotenv import load_dotenv

# Streamlit executes this file as a script.  Ensure the project root is on
# ``sys.path`` so package imports work even when launched from ``app/``.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.fallback import LLMFallback
from app.llm import generate_response, get_llm
from app.logging_config import logger
from app.prompts import build_prompt
from app.schemas import LLMResponse
from rag.citations import build_citations, format_context_with_citations
from rag.factsheets import ensure_factsheets_indexed, find_factsheets
from rag.grounding import GroundingError, ground_answer
from rag.retriever import retrieve_documents
from ingestion.pdf_parser import get_docling_device_label
from ingestion.table_aware import answer_table_question


load_dotenv()


st.set_page_config(
    page_title="FundLens RAG",
    page_icon="📊",
    layout="wide",
)


st.title("📊 FundLens RAG")
st.caption(
    "Mutual-fund document research with evidence-backed answers."
)


def generate_answer(
    question: str,
    context: str,
):
    """
    Generate an answer from retrieved RAG context.
    """

    prompt = build_prompt(
        question=question,
        context=context,
        version="v1",
    )

    primary_llm = get_llm()

    fallback = LLMFallback(
        primary=lambda p: generate_response(
            p,
            llm=primary_llm,
        )
    )

    return fallback.invoke(prompt)


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

with st.sidebar:
    st.header("RAG Settings")

    prompt_version = st.selectbox(
        "Prompt version",
        ["v1"],
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


# ---------------------------------------------------------
# Generate
# ---------------------------------------------------------

if st.button("Ask FundLens", type="primary"):

    if not question.strip():
        st.warning("Please enter a question.")
        st.stop()

    try:
        with st.spinner("Analyzing documents..."):
            indexed_documents = ensure_factsheets_indexed()

            retrieved_chunks = retrieve_documents(
                query=question,
                top_k=5,
                document_type="factsheet",
            )

            if not retrieved_chunks:
                st.warning(
                    "I could not find relevant content in the indexed factsheets."
                )
                st.stop()

            table_answer = answer_table_question(question, retrieved_chunks)
            if table_answer:
                response = LLMResponse(answer=table_answer, confidence=0.85)
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
                )

            try:
                response.answer, verified_chunks = ground_answer(
                    answer=response.answer,
                    retrieved_chunks=retrieved_chunks,
                    question=question,
                )
            except GroundingError as exc:
                logger.warning("Withholding ungrounded RAG answer: %s", exc)
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

        st.write(response.answer)

        st.subheader("Confidence")

        st.progress(response.confidence)

        st.write(
            f"{response.confidence:.0%}"
        )

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
