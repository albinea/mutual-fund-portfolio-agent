"""Shared filesystem locations for the FundLens RAG package."""

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
RAG_PROJECT_ROOT = BACKEND_ROOT / "rag"
FACTSHEET_DIRECTORIES = (
    RAG_PROJECT_ROOT / "data" / "documents" / "factsheets",
    RAG_PROJECT_ROOT / "evaluation" / "documents" / "factsheets",
)
CHUNKS_DIRECTORY = RAG_PROJECT_ROOT / "data" / "chunks"
MARKDOWN_DIRECTORY = RAG_PROJECT_ROOT / "data" / "markdown"
