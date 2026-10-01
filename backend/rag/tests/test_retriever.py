import unittest
from unittest.mock import MagicMock, patch

from rag.retriever import Retriever, retrieve_documents


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

    def test_passes_fund_scope_to_the_retriever(self):
        client = MagicMock()
        retriever = MagicMock()
        retriever.retrieve.return_value = []
        fund_name = "HDFC Medium to Long Term Fund"

        with patch("rag.retriever.QdrantClient", return_value=client), patch(
            "rag.retriever.Retriever", return_value=retriever
        ):
            retrieve_documents(
                "since inception value",
                fund_name=fund_name,
                document_type="factsheet",
            )

        retriever.retrieve.assert_called_once_with(
            query="since inception value",
            top_k=5,
            fund_name=fund_name,
            document_type="factsheet",
        )

    def test_builds_qdrant_fund_filter(self):
        query_filter = Retriever._build_filter(
            fund_name="HDFC Medium to Long Term Fund",
            document_type="factsheet",
        )

        conditions = {condition.key: condition.match.value for condition in query_filter.must}
        self.assertEqual(conditions["fund_name"], "HDFC Medium to Long Term Fund")
        self.assertEqual(conditions["document_type"], "factsheet")


if __name__ == "__main__":
    unittest.main()
