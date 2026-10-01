from __future__ import annotations

from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from rag.embeddings import get_embedding_model


# Page-sized chunks preserve tables whose headers, labels, and values would
# otherwise be split apart. A new collection name triggers a safe automatic
# rebuild without deleting the earlier index.
COLLECTION_NAME = "fundlens_documents_v5"
VECTOR_SIZE = 768


class VectorStore:
    """
    Qdrant vector store for FundLens documents.

    Stores:
        - embedding vector
        - document text
        - document name
        - page number
        - source URL
        - fund name
        - document type
        - publication date
    """

    def __init__(
        self,
        path: str = "qdrant_data",
        collection_name: str = COLLECTION_NAME,
    ):
        self.client = QdrantClient(path=path)
        self.collection_name = collection_name
        self.embedding_model = get_embedding_model()

    def create_collection(self) -> None:
        """
        Create the Qdrant collection if it doesn't already exist.
        """

        existing_collections = self.client.get_collections().collections

        if any(
            collection.name == self.collection_name
            for collection in existing_collections
        ):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )

    def add_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> None:
        """
        Embed and store document chunks.

        Each document should contain at least:

            text
            document
            page
            source_url

        Optional:

            fund_name
            document_type
            published_date
        """

        if not documents:
            return

        self.create_collection()

        texts = [
            document["text"]
            for document in documents
            if document.get("text")
        ]

        if not texts:
            return

        embeddings = self.embedding_model.embed_documents(texts)

        points: list[PointStruct] = []

        embedding_index = 0

        for document in documents:
            text = document.get("text")

            if not text:
                continue

            payload = {
                "text": text,
                "document": document.get("document"),
                "page": document.get("page"),
                "source_url": document.get("source_url"),
                "fund_name": document.get("fund_name"),
                "document_type": document.get("document_type"),
                "published_date": document.get("published_date"),
            }

            points.append(
                PointStruct(
                    id=str(uuid4()),
                    vector=embeddings[embedding_index],
                    payload=payload,
                )
            )

            embedding_index += 1

        if points:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

    def count(self) -> int:
        """
        Return the number of vectors currently stored.
        """

        result = self.client.count(
            collection_name=self.collection_name,
            exact=True,
        )

        return result.count

    def indexed_documents(self) -> set[str]:
        """Return the source document names already present in the index."""
        if not any(
            collection.name == self.collection_name
            for collection in self.client.get_collections().collections
        ):
            return set()

        documents: set[str] = set()
        offset = None

        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=None,
                limit=250,
                with_payload=["document"],
                with_vectors=False,
                offset=offset,
            )

            documents.update(
                point.payload["document"]
                for point in points
                if point.payload and point.payload.get("document")
            )

            if offset is None:
                break

        return documents

    def delete_collection(self) -> None:
        """
        Delete the entire collection.

        Useful during development when rebuilding the index.
        """

        self.client.delete_collection(
            collection_name=self.collection_name
        )
