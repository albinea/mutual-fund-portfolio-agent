"""Discover and index local mutual-fund factsheets for the chat application."""

from __future__ import annotations

from pathlib import Path

from ingestion.ingest import ingest_pdf
from rag.vector_store import VectorStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FACTSHEET_DIRECTORIES = (
    PROJECT_ROOT / "data" / "documents" / "factsheets",
    PROJECT_ROOT / "evaluation" / "documents" / "factsheets",
)
CHUNKS_DIRECTORY = PROJECT_ROOT / "data" / "chunks"
MARKDOWN_DIRECTORY = PROJECT_ROOT / "data" / "markdown"


def find_factsheets() -> list[Path]:
    """Return every PDF factsheet bundled with the project."""
    factsheets: dict[str, Path] = {}

    for directory in FACTSHEET_DIRECTORIES:
        if directory.exists():
            for pdf_path in directory.glob("*.pdf"):
                factsheets.setdefault(pdf_path.name, pdf_path)

    return sorted(factsheets.values(), key=lambda path: path.name.lower())


def ensure_factsheets_indexed() -> list[str]:
    """Index factsheets that are not yet in the local Qdrant collection.

    Chunk metadata retains the original document name and PDF page number, so
    retrieval results can always be shown with a verifiable citation.
    """
    factsheets = find_factsheets()
    if not factsheets:
        searched = ", ".join(str(path) for path in FACTSHEET_DIRECTORIES)
        raise FileNotFoundError(f"No factsheet PDFs found in: {searched}")

    store = VectorStore(path=str(PROJECT_ROOT / "qdrant_data"))
    newly_indexed: list[str] = []

    try:
        indexed = store.indexed_documents()

        for pdf_path in factsheets:
            if pdf_path.name in indexed:
                continue

            chunks = ingest_pdf(
                pdf_path=pdf_path,
                output_path=CHUNKS_DIRECTORY / f"{pdf_path.stem}.json",
                markdown_path=MARKDOWN_DIRECTORY / f"{pdf_path.stem}.md",
                source_url=pdf_path.resolve().as_uri(),
                document_type="factsheet",
            )
            store.add_documents(chunks)
            newly_indexed.append(pdf_path.name)
    finally:
        # Local Qdrant uses a file lock; release it before retrieval opens its
        # own client against the same on-disk collection.
        store.client.close()

    return newly_indexed
