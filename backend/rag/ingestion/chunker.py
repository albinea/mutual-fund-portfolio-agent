from dataclasses import dataclass


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


def chunk_text(
    text: str,
    document: str,
    page: int,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    source_url: str = "",
    document_type: str = "",
    published_date: str = "",
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
                )
            )

        if end >= len(text):
            break

        start = end - chunk_overlap

    return chunks