import json
from pathlib import Path

from ingestion.pdf_parser import convert_pdf_to_markdown
from ingestion.chunker import chunk_markdown


def ingest_pdf(
    pdf_path: str | Path,
    output_path: str | Path,
    markdown_path: str | Path | None = None,
    source_url: str = "",
    document_type: str = "factsheet",
    published_date: str = "",
    chunk_size: int = 5000,
    chunk_overlap: int = 250,
):
    """
    Parse a PDF, extract page-aware text,
    create chunks, and save them as JSON.
    """

    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    markdown_path = (
        Path(markdown_path)
        if markdown_path is not None
        else output_path.with_suffix(".md")
    )

    print(f"Processing: {pdf_path}")

    page_texts = convert_pdf_to_markdown(pdf_path, markdown_path)

    print(
        f"Extracted content from {len(page_texts)} page sections."
    )

    all_chunks = []

    for page_number, page_text in page_texts:

        chunks = chunk_markdown(
            markdown=page_text,
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
        markdown_path="data/markdown/example.md",
    )
