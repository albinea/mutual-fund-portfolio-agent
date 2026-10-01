import unittest
from unittest.mock import MagicMock, patch

from rag.retriever import retrieve_documents


class RetrieverLifecycleTests(unittest.TestCase):
    def test_closes_the_local_qdrant_client_after_a_search(self):
        client = MagicMock()
        retriever = MagicMock()
        retriever.retrieve.return_value = [{"text": "result"}]

        with patch("rag.retriever.QdrantClient", return_value=client), patch(
            "rag.retriever.Retriever", return_value=retriever
        ):
            result = retrieve_documents("test query")

        self.assertEqual(result, [{"text": "result"}])
        client.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
