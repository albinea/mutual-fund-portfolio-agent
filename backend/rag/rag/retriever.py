from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient

from rag.embeddings import get_embedding_model


COLLECTION_NAME = "fundlens_documents"


class Retriever:
    """
    Retrieves relevant document chunks from Qdrant.

    The retrieved metadata is preserved so that citations.py
    can produce page-level citations.
    """

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str = COLLECTION_NAME,
    ):
        self.client = client
        self.collection_name = collection_name
        self.embedding_model = get_embedding_model()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        fund_name: str | None = None,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the most relevant chunks for a user query.
        """

        if not query or not query.strip():
            raise ValueError("Query cannot be empty.")

        query_vector = self.embedding_model.embed_query(query)

        query_filter = self._build_filter(
            fund_name=fund_name,
            document_type=document_type,
        )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        retrieved: list[dict[str, Any]] = []

        for result in results.points:
            payload = result.payload or {}

            retrieved.append(
                {
                    "score": result.score,
                    "text": payload.get("text", ""),
                    "document": payload.get("document"),
                    "page": payload.get("page"),
                    "source_url": payload.get("source_url"),
                    "document_type": payload.get("document_type"),
                    "fund_name": payload.get("fund_name"),
                    "published_date": payload.get("published_date"),
                }
            )

        return retrieved

    @staticmethod
    def _build_filter(
        fund_name: str | None = None,
        document_type: str | None = None,
    ):
        """
        Build optional Qdrant metadata filters.

        Returns None when no filtering is requested.
        """

        conditions = []

        if fund_name:
            conditions.append(
                {
                    "key": "fund_name",
                    "match": {"value": fund_name},
                }
            )

        if document_type:
            conditions.append(
                {
                    "key": "document_type",
                    "match": {"value": document_type},
                }
            )

        if not conditions:
            return None

        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qdrant_conditions = []

        if fund_name:
            qdrant_conditions.append(
                FieldCondition(
                    key="fund_name",
                    match=MatchValue(value=fund_name),
                )
            )

        if document_type:
            qdrant_conditions.append(
                FieldCondition(
                    key="document_type",
                    match=MatchValue(value=document_type),
                )
            )

        return Filter(must=qdrant_conditions)


def retrieve_documents(
    query: str,
    top_k: int = 5,
    fund_name: str | None = None,
    document_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Convenience function for the rest of the application.
    """

    client = QdrantClient(path="qdrant_data")

    retriever = Retriever(
        client=client,
        collection_name=COLLECTION_NAME,
    )

    return retriever.retrieve(
        query=query,
        top_k=top_k,
        fund_name=fund_name,
        document_type=document_type,
    )