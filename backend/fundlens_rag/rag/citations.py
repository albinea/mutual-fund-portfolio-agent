# rag/citations.py

from __future__ import annotations

from typing import Any

from fundlens_rag.app.schemas import Citation


def build_citations(
    retrieved_chunks: list[dict[str, Any]],
) -> list[Citation]:
    """
    Convert retrieved RAG chunks into validated, deduplicated citations.

    Expected metadata in each retrieved chunk:
        document
        page
        source_url

    Optional:
        published_date
        document_type
        fund_name
    """

    citations: list[Citation] = []
    seen: set[tuple[str, int, str]] = set()

    for chunk in retrieved_chunks:
        document = chunk.get("document")
        page = chunk.get("page")
        source_url = chunk.get("source_url")

        # Never invent citation information.
        if not document or page is None or not source_url:
            continue

        try:
            page = int(page)
        except (TypeError, ValueError):
            continue

        if page < 1:
            continue

        key = (document, page, source_url)

        if key in seen:
            continue

        seen.add(key)

        citations.append(
            Citation(
                document=document,
                page=page,
                source_url=source_url,
            )
        )

    return citations


def format_citations(
    citations: list[Citation],
) -> str:
    """
    Format citations for displaying below an answer.
    """

    if not citations:
        return "No document citations available."

    lines = ["Sources:"]

    for citation in citations:
        lines.append(
            f"- {citation.document}, page {citation.page} "
            f"({citation.source_url})"
        )

    return "\n".join(lines)


def format_context_with_citations(
    retrieved_chunks: list[dict[str, Any]],
) -> str:
    """
    Format retrieved chunks so the LLM can see the exact
    document and page associated with each piece of context.
    """

    if not retrieved_chunks:
        return "No relevant documents were retrieved."

    sections: list[str] = []

    for index, chunk in enumerate(retrieved_chunks, start=1):
        text = chunk.get("text", "").strip()

        if not text:
            continue

        document = chunk.get("document", "Unknown document")
        page = chunk.get("page")

        if page is not None:
            citation_label = f"{document}, page {page}"
        else:
            citation_label = document

        sections.append(
            f"[SOURCE {index}]\n"
            f"Document: {citation_label}\n"
            f"Content:\n{text}"
        )

    if not sections:
        return "No usable document content was retrieved."

    return "\n\n".join(sections)
