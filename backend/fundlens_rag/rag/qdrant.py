"""Shared configuration for the persistent Qdrant service."""

from __future__ import annotations

import os

from qdrant_client import QdrantClient


DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"


def create_qdrant_client(url: str | None = None) -> QdrantClient:
    """Create an HTTP client for the configured Qdrant server.

    Qdrant's local embedded ``path=`` mode is deliberately not used: separate
    Django workers must be able to access the same persistent server safely.
    """
    endpoint = (url or os.getenv("QDRANT_URL") or DEFAULT_QDRANT_URL).strip()
    if not endpoint:
        raise ValueError("QDRANT_URL cannot be blank.")

    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    return QdrantClient(url=endpoint, api_key=api_key)
