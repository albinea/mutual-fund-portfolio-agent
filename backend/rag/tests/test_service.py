import unittest
from unittest.mock import patch

from fundlens_rag.app.schemas import LLMResponse
from fundlens_rag.app.usage import UsageTracker
from fundlens_rag.service import answer_fundlens_question


class FundLensServiceTests(unittest.TestCase):
    FUND = "HDFC Medium to Long Term Fund"
    QUESTION = (
        "What was the market value as on August 31, 2026 for the 1-year SIP "
        "of HDFC Medium to Long Term Fund?"
    )
    CHUNK = {
        "text": (
            "HDFC Medium to Long Term Fund. Market value as on August 31, 2026; "
            "1 year SIP: ₹1.23 lacs."
        ),
        "document": "HDFC MF Factsheet - August 2026.pdf",
        "page": 87,
        "source_url": "file:///factsheets/HDFC-August-2026.pdf",
        "fund_name": FUND,
        "score": 0.9,
    }

    def test_returns_fund_scoped_answer_citations_evidence_and_usage(self):
        tracker = UsageTracker()

        def generate(*, prompt, llm, usage_tracker):
            usage_tracker.record_request("answer", "test-answer-model")
            usage_tracker.record_usage(
                "answer",
                "test-answer-model",
                input_tokens=100,
                output_tokens=20,
            )
            return LLMResponse(
                answer="The market value was ₹1.23 lacs. [SOURCE 1]",
                confidence=0.8,
            )

        with (
            patch(
                "fundlens_rag.service.list_known_funds",
                return_value=[self.FUND],
            ),
            patch(
                "fundlens_rag.service.resolve_fund_name",
                return_value=self.FUND,
            ),
            patch(
                "fundlens_rag.service.retrieve_documents",
                return_value=[self.CHUNK],
            ) as retrieve,
            patch("fundlens_rag.service.answer_table_question", return_value=None),
            patch("fundlens_rag.service.build_prompt", return_value="prompt"),
            patch("fundlens_rag.service.get_llm", return_value=object()),
            patch("fundlens_rag.service.generate_response", side_effect=generate),
        ):
            result = answer_fundlens_question(
                self.QUESTION,
                fund_scope=self.FUND,
                usage_tracker=tracker,
            )

        retrieve.assert_called_once_with(
            query=self.QUESTION,
            top_k=5,
            fund_name=self.FUND,
            document_type="factsheet",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["answer_method"], "rag_only")
        self.assertEqual(result["retrieved_chunks"], [self.CHUNK])
        self.assertEqual(result["sources"][0]["page"], 87)
        self.assertEqual(result["sources"][0]["labels"], ["SOURCE 1"])
        self.assertEqual(result["usage"][0]["input_tokens"], 100)

    def test_reports_empty_retrieval_as_evidence_gap(self):
        with (
            patch(
                "fundlens_rag.service.list_known_funds",
                return_value=[self.FUND],
            ),
            patch(
                "fundlens_rag.service.resolve_fund_name",
                return_value=self.FUND,
            ),
            patch("fundlens_rag.service.retrieve_documents", return_value=[]),
        ):
            result = answer_fundlens_question(self.QUESTION, self.FUND)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "no_retrieved_chunks")
        self.assertEqual(result["retrieved_chunks"], [])
        self.assertIn("sufficient evidence", result["answer"])

    def test_does_not_search_when_fund_cannot_be_resolved(self):
        with (
            patch("fundlens_rag.service.list_known_funds", return_value=[]),
            patch("fundlens_rag.service.resolve_fund_name", return_value=None),
            patch("fundlens_rag.service.retrieve_documents") as retrieve,
        ):
            result = answer_fundlens_question("Why did the fund grow?")

        self.assertEqual(result["error_code"], "fund_not_resolved")
        self.assertEqual(result["retrieved_chunks"], [])
        retrieve.assert_not_called()

    def test_question_answering_never_runs_factsheet_ingestion(self):
        with (
            patch(
                "fundlens_rag.service.list_known_funds",
                return_value=[self.FUND],
            ),
            patch(
                "fundlens_rag.service.resolve_fund_name",
                return_value=self.FUND,
            ),
            patch("fundlens_rag.service.retrieve_documents", return_value=[]),
            patch(
                "fundlens_rag.rag.factsheets.ensure_factsheets_indexed"
            ) as index_factsheets,
        ):
            answer_fundlens_question(self.QUESTION, self.FUND)

        index_factsheets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
