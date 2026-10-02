"""Fund-scoped, retrieval-only interface for agent and API consumers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fundlens_rag.ingestion.fund_metadata import (
    list_known_funds,
    resolve_fund_name,
)
from fundlens_rag.paths import CHUNKS_DIRECTORY, MARKDOWN_DIRECTORY
from fundlens_rag.rag.retriever import retrieve_documents


def _public_source_url(value: Any) -> str | None:
    """Do not expose an ingestion host's local filesystem path to the client/model."""
    if not value:
        return None
    url = str(value)
    if urlsplit(url).scheme.casefold() == "file":
        return None
    return url


def retrieve_fund_documents(
    query: str,
    fund_scope: str | None = None,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """Return page-addressable chunks for exactly one indexed fund.

    This deliberately stops before answer generation: the calling agent may
    combine these chunks with portfolio calculations in its existing turn.
    If a single known fund cannot be resolved, Qdrant is not queried at all.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k must be between 1 and 10.")

    known_funds = list_known_funds(MARKDOWN_DIRECTORY, CHUNKS_DIRECTORY)
    query_fund = resolve_fund_name(query, known_funds)
    scoped_fund = resolve_fund_name(fund_scope, known_funds) if fund_scope else None
    if query_fund and scoped_fund and query_fund.casefold() != scoped_fund.casefold():
        return {
            "success": False,
            "error_code": "FUND_SCOPE_MISMATCH",
            "message": "The requested fund and supplied fund scope do not match; no search was run.",
            "fund_name": None,
            "results": [],
            "sources": [],
            "source": None,
        }
    selected_fund = scoped_fund or query_fund
    if selected_fund is None:
        return {
            "success": False,
            "error_code": "FUND_NOT_RESOLVED",
            "message": (
                "No single indexed fund could be identified. Specify one fund; "
                "the search was not run across the full document collection."
            ),
            "fund_name": None,
            "results": [],
            "sources": [],
            "source": None,
        }

    chunks = retrieve_documents(
        query=query.strip(),
        top_k=top_k,
        fund_name=selected_fund,
        document_type="factsheet",
    )
    results = [
        {
            "text": str(chunk.get("text") or ""),
            "document": chunk.get("document"),
            "page": chunk.get("page"),
            "source_url": _public_source_url(chunk.get("source_url")),
            "fund_name": chunk.get("fund_name") or selected_fund,
            "published_date": chunk.get("published_date"),
            "document_type": chunk.get("document_type"),
            "score": chunk.get("score"),
        }
        for chunk in chunks
        if isinstance(chunk, dict) and str(chunk.get("text") or "").strip()
    ]

    sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, int | None, str | None]] = set()
    for chunk in results:
        document = chunk.get("document")
        page = chunk.get("page")
        source_url = chunk.get("source_url")
        if not document:
            continue
        try:
            page_number = int(page) if page is not None else None
        except (TypeError, ValueError):
            page_number = None
        key = (str(document), page_number, str(source_url) if source_url else None)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        sources.append(
            {
                "name": str(document),
                "document": str(document),
                "page": page_number,
                "url": str(source_url) if source_url else None,
                "data_as_of": chunk.get("published_date"),
            }
        )

    return {
        "success": True,
        "fund_name": selected_fund,
        "results": results,
        "sources": sources,
        "source": sources[0] if sources else None,
        "message": None if results else "No indexed chunks matched this fund and question.",
    }
