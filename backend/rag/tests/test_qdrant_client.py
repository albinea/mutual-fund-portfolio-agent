import os
import unittest
from unittest.mock import patch

from fundlens_rag.rag.qdrant import DEFAULT_QDRANT_URL, create_qdrant_client


class QdrantClientConfigurationTests(unittest.TestCase):
    def test_uses_configured_persistent_server_url_and_api_key(self):
        with patch.dict(
            os.environ,
            {
                "QDRANT_URL": "https://qdrant.example:6333",
                "QDRANT_API_KEY": "test-key",
            },
        ), patch("fundlens_rag.rag.qdrant.QdrantClient") as client_type:
            client = create_qdrant_client()

        self.assertIs(client, client_type.return_value)
        client_type.assert_called_once_with(
            url="https://qdrant.example:6333",
            api_key="test-key",
        )

    def test_defaults_to_localhost_server_not_embedded_storage(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "fundlens_rag.rag.qdrant.QdrantClient"
        ) as client_type:
            create_qdrant_client()

        client_type.assert_called_once_with(url=DEFAULT_QDRANT_URL, api_key=None)

    def test_accepts_an_explicit_server_url(self):
        with patch.dict(
            os.environ, {"QDRANT_URL": "http://ignored:6333"}, clear=True
        ), patch("fundlens_rag.rag.qdrant.QdrantClient") as client_type:
            create_qdrant_client("http://explicit:6333")

        client_type.assert_called_once_with(url="http://explicit:6333", api_key=None)


if __name__ == "__main__":
    unittest.main()
