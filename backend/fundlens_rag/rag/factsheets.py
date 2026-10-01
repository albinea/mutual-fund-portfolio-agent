"""Discover and index local mutual-fund factsheets for the chat application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fundlens_rag.ingestion.fund_metadata import attach_fund_names_to_chunks
from fundlens_rag.paths import (
    CHUNKS_DIRECTORY,
    FACTSHEET_DIRECTORIES,
    MARKDOWN_DIRECTORY,
)
from fundlens_rag.rag.vector_store import VectorStore


def find_factsheets() -> list[Path]:
    """Return every PDF factsheet bundled with the project."""
    factsheets: dict[str, Path] = {}

    for directory in FACTSHEET_DIRECTORIES:
        if directory.exists():
            for pdf_path in directory.glob("*.pdf"):
                factsheets.setdefault(pdf_path.name, pdf_path)

    return sorted(factsheets.values(), key=lambda path: path.name.lower())


def ensure_factsheets_indexed() -> list[str]:
    """Index factsheets that are not yet in the persistent Qdrant collection.

    Chunk metadata retains the original document name and PDF page number, so
    retrieval results can always be shown with a verifiable citation.
    """
    factsheets = find_factsheets()
    if not factsheets:
        searched = ", ".join(str(path) for path in FACTSHEET_DIRECTORIES)
        raise FileNotFoundError(f"No factsheet PDFs found in: {searched}")

    store = VectorStore()
    newly_indexed: list[str] = []

    try:
        indexed = store.indexed_documents()

        for pdf_path in factsheets:
            if pdf_path.name in indexed:
                continue

            chunks_path = CHUNKS_DIRECTORY / f"{pdf_path.stem}.json"
            if chunks_path.exists():
                # Migrate existing chunk data in memory. This avoids
                # reprocessing PDFs or overwriting a user's Markdown/chunk
                # files just to add fund metadata to the new collection.
                chunks = _load_existing_chunks(chunks_path, pdf_path.name)
                chunks = attach_fund_names_to_chunks(chunks)
            else:
                # Docling is imported only for an actual PDF ingestion task,
                # never for an ordinary retrieval request.
                from fundlens_rag.ingestion.ingest import ingest_pdf

                chunks = ingest_pdf(
                    pdf_path=pdf_path,
                    output_path=chunks_path,
                    markdown_path=MARKDOWN_DIRECTORY / f"{pdf_path.stem}.md",
                    source_url=pdf_path.resolve().as_uri(),
                    document_type="factsheet",
                )

            store.add_documents(chunks)
            newly_indexed.append(pdf_path.name)
    finally:
        # Release HTTP/gRPC client resources after the one-shot indexing job.
        store.client.close()

    return newly_indexed


def _load_existing_chunks(path: Path, expected_document: str) -> list[dict[str, Any]]:
    """Load a chunk JSON file for indexing without rewriting its source data."""
    try:
        chunks = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid chunk JSON file: {path}") from exc

    if not isinstance(chunks, list) or not chunks:
        raise ValueError(f"Chunk JSON must contain a non-empty list: {path}")

    normalized: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict) or not str(chunk.get("text", "")).strip():
            raise ValueError(f"Invalid chunk at index {index} in {path}")
        document = chunk.get("document")
        if document and document != expected_document:
            raise ValueError(
                f"Chunk {index} in {path} belongs to {document}, "
                f"not {expected_document}"
            )
        normalized.append({**chunk, "document": expected_document})

    return normalized
