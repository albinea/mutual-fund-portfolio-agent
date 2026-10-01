"""Table-aware PDF-to-Markdown conversion using Docling."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import torch
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption

from fundlens_rag.ingestion.table_aware import make_tables_retrievable
from fundlens_rag.paths import RAG_PROJECT_ROOT


DEFAULT_ARTIFACTS_PATH = RAG_PROJECT_ROOT / "docling_models"
logger = logging.getLogger("fundlens")


def convert_pdf_to_markdown(
    pdf_path: str | Path,
    markdown_path: str | Path,
) -> list[tuple[int, str]]:
    """Convert a text-based PDF into page-aware, table-aware Markdown.

    The complete Markdown file is retained for inspection and reuse. The
    returned page fragments keep source-page metadata for RAG citations.
    """
    pdf_path = Path(pdf_path)
    markdown_path = Path(markdown_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.suffix}")

    document = _get_converter().convert(str(pdf_path)).document
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    full_markdown = make_tables_retrievable(
        document.export_to_markdown(
            page_break_placeholder="\n\n<!-- page break -->\n\n",
        )
    )
    markdown_path.write_text(full_markdown, encoding="utf-8")

    pages = [
        (
            page_number,
            make_tables_retrievable(
                document.export_to_markdown(page_no=page_number)
            ).strip(),
        )
        for page_number in sorted(document.pages)
    ]
    pages = [(page, text) for page, text in pages if text]

    if not pages:
        raise ValueError(f"No usable content was found in PDF: {pdf_path}")

    return pages


@lru_cache(maxsize=1)
def _get_converter() -> DocumentConverter:
    """Build one local Docling converter for the ingestion process."""
    artifacts_path = Path(
        os.getenv("DOCLING_ARTIFACTS_PATH", str(DEFAULT_ARTIFACTS_PATH))
    )
    if not artifacts_path.is_dir():
        raise RuntimeError(
            "Docling model artifacts are missing. Download the layout and "
            "tableformer models into "
            f"{artifacts_path} before starting FundLens."
        )

    accelerator, accelerator_name = _select_accelerator()
    logger.info("Docling PDF processing device: %s", accelerator_name)

    options = PdfPipelineOptions(
        artifacts_path=artifacts_path,
        accelerator_options=AcceleratorOptions(
            device=accelerator,
            num_threads=4,
        ),
    )
    options.do_ocr = False
    options.do_table_structure = True
    options.table_structure_options.mode = (
        TableFormerMode.ACCURATE
        if accelerator == AcceleratorDevice.CUDA
        else TableFormerMode.FAST
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        }
    )


def get_docling_device_label() -> str:
    """Return the device Docling will use, suitable for the app sidebar."""
    accelerator, name = _select_accelerator()
    if accelerator == AcceleratorDevice.CUDA:
        return f"CUDA GPU · {name}"
    if os.getenv("DOCLING_DEVICE", "cuda").strip().lower() == "cpu":
        return "CPU · selected by DOCLING_DEVICE"
    return "CPU · CUDA unavailable to this app process"


def _select_accelerator() -> tuple[AcceleratorDevice, str]:
    """Prefer CUDA by default, with an explicit CPU fallback when unavailable."""
    requested = os.getenv("DOCLING_DEVICE", "cuda").strip().lower()
    if requested not in {"cuda", "cpu", "auto"}:
        raise ValueError("DOCLING_DEVICE must be one of: cuda, cpu, auto")

    if requested != "cpu" and torch.cuda.is_available():
        return AcceleratorDevice.CUDA, torch.cuda.get_device_name(0)

    if requested == "cuda":
        logger.warning(
            "CUDA was requested for Docling, but this process cannot access "
            "an NVIDIA GPU; using CPU. Check the NVIDIA driver and CUDA "
            "device visibility from the same environment that runs Streamlit."
        )
    return AcceleratorDevice.CPU, "CPU"
