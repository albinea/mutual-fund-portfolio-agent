from dataclasses import dataclass
import re


@dataclass
class DocumentChunk:
    """
    A page-aware chunk of a document.
    """

    text: str
    document: str
    page: int
    source_url: str = ""
    document_type: str = ""
    published_date: str = ""
    fund_name: str | None = None


def chunk_text(
    text: str,
    document: str,
    page: int,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    source_url: str = "",
    document_type: str = "",
    published_date: str = "",
    fund_name: str | None = None,
) -> list[DocumentChunk]:
    """
    Split page text into overlapping chunks.

    Page number is preserved for every chunk.
    """

    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be greater than 0"
        )

    if chunk_overlap < 0:
        raise ValueError(
            "chunk_overlap cannot be negative"
        )

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be smaller than chunk_size"
        )

    text = text.strip()

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(
                DocumentChunk(
                    text=chunk,
                    document=document,
                    page=page,
                    source_url=source_url,
                    document_type=document_type,
                    published_date=published_date,
                    fund_name=fund_name,
                )
            )

        if end >= len(text):
            break

        start = end - chunk_overlap

    return chunks


def chunk_markdown(
    markdown: str,
    document: str,
    page: int,
    chunk_size: int = 5000,
    chunk_overlap: int = 250,
    source_url: str = "",
    document_type: str = "",
    published_date: str = "",
    fund_name: str | None = None,
) -> list[DocumentChunk]:
    """Chunk Markdown without splitting recognised tables.

    Docling emits tables as contiguous Markdown blocks. A table is therefore
    kept intact even when it exceeds the preferred chunk size; preserving its
    headers and rows matters more than the size limit for RAG evidence.
    """
    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n", markdown.strip())
        if block.strip()
    ]
    if not blocks:
        return []

    chunks: list[DocumentChunk] = []
    current: list[str] = []
    current_length = 0

    def save_current() -> None:
        nonlocal current, current_length
        if current:
            chunks.append(
                DocumentChunk(
                    text="\n\n".join(current),
                    document=document,
                    page=page,
                    source_url=source_url,
                    document_type=document_type,
                    published_date=published_date,
                    fund_name=fund_name,
                )
            )
        current = []
        current_length = 0

    for block in blocks:
        block_length = len(block)
        if current and current_length + 2 + block_length > chunk_size:
            save_current()

        # Do not split a structural Markdown block. In particular, splitting
        # table rows from their headers breaks table-aware retrieval.
        current.append(block)
        current_length += block_length if current_length == 0 else block_length + 2

    save_current()
    return chunks
