import json
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import chunk_text


def extract_page_texts(
    document: DoclingDocument,
) -> list[tuple[int, str]]:
    """
    Extract text page-by-page from a Docling document.

    Returns:
        List of (page_number, page_text)
    """

    pages = []

    # Docling exposes page information through document provenance.
    for item in document.texts:

        text = item.text.strip()

        if not text:
            continue

        page_numbers = set()

        for provenance in getattr(
            item,
            "prov",
            [],
        ):
            page_no = getattr(
                provenance,
                "page_no",
                None,
            )

            if page_no is not None:
                page_numbers.add(page_no)

        if not page_numbers:
            # If no page provenance is available,
            # skip rather than inventing a page number.
            continue

        for page_no in sorted(page_numbers):
            pages.append(
                (page_no, text)
            )

    return pages


def ingest_pdf(
    pdf_path: str | Path,
    output_path: str | Path,
    source_url: str = "",
    document_type: str = "factsheet",
    published_date: str = "",
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
):
    """
    Parse a PDF, extract page-aware text,
    create chunks, and save them as JSON.
    """

    pdf_path = Path(pdf_path)
    output_path = Path(output_path)

    print(f"Processing: {pdf_path}")

    document = parse_pdf(pdf_path)

    page_texts = extract_page_texts(document)

    print(
        f"Extracted content from {len(page_texts)} page sections."
    )

    all_chunks = []

    for page_number, page_text in page_texts:

        chunks = chunk_text(
            text=page_text,
            document=pdf_path.name,
            page=page_number,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            source_url=source_url,
            document_type=document_type,
            published_date=published_date,
        )

        all_chunks.extend(chunks)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = []

    for index, chunk in enumerate(all_chunks):

        output.append(
            {
                "id": index,
                "text": chunk.text,
                "document": chunk.document,
                "page": chunk.page,
                "source_url": chunk.source_url,
                "document_type": chunk.document_type,
                "published_date": chunk.published_date,
            }
        )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Created {len(output)} chunks."
    )

    print(
        f"Saved chunks to: {output_path}"
    )

    return output


if __name__ == "__main__":

    ingest_pdf(
        pdf_path="data/documents/factsheets/example.pdf",
        output_path="data/chunks/example.json",
    )