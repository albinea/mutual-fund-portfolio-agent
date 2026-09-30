from __future__ import annotations

from sentence_transformers import SentenceTransformer


MODEL_NAME = "intfloat/multilingual-e5-base"


class EmbeddingModel:
    """
    Embedding wrapper for FundLens RAG.

    Uses multilingual-e5-base so the retriever can handle
    multilingual financial documents and user queries.
    """

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        Create embeddings for document chunks.

        E5 models expect the `passage:` prefix for documents.
        """
        if not texts:
            return []

        passages = [f"passage: {text}" for text in texts]

        embeddings = self.model.encode(
            passages,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """
        Create an embedding for a user query.

        E5 models expect the `query:` prefix for queries.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty.")

        embedding = self.model.encode(
            f"query: {query}",
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

        return embedding.tolist()


_embedding_model: EmbeddingModel | None = None


def get_embedding_model() -> EmbeddingModel:
    """
    Return a shared embedding model instance.

    Loading the model is expensive, so we don't reload it
    for every request.
    """
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = EmbeddingModel()

    return _embedding_model