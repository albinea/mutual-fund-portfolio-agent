from pathlib import Path

from docling.document_converter import DocumentConverter


def parse_pdf(pdf_path: str | Path):
    """
    Parse a PDF using Docling.

    Returns:
        DoclingDocument
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path}"
        )

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"Expected a PDF file, got: {pdf_path.suffix}"
        )

    converter = DocumentConverter()

    result = converter.convert(str(pdf_path))

    return result.document