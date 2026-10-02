import unittest

from fundlens_rag.rag.grounding import GroundingError, cited_chunks, ground_answer


class CitationGroundingTests(unittest.TestCase):
    def test_rejects_a_citation_for_a_different_fund(self):
        chunks = [
            {
                "text": "HDFC ELSS - Tax Saver Fund is an equity linked savings scheme.",
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 64,
                "source_url": "file:///factsheet.pdf",
            }
        ]

        with self.assertRaisesRegex(GroundingError, "does not match"):
            cited_chunks(
                answer="It tracks the MSCI World Index. [SOURCE 1]",
                retrieved_chunks=chunks,
                question=(
                    "What is the investment objective of HDFC Developed World "
                    "Overseas Equity Passive FOF?"
                ),
            )

    def test_accepts_a_citation_for_the_requested_fund(self):
        chunks = [
            {
                "text": (
                    "HDFC Developed World Overseas Equity Passive FOF invests in "
                    "overseas index funds and ETFs that closely correspond to the "
                    "MSCI World Index, subject to tracking errors."
                ),
                "document": "HDFC MF Index Solutions Factsheet - July 2026.pdf",
                "page": 64,
                "source_url": "file:///factsheet.pdf",
            }
        ]

        self.assertEqual(
            cited_chunks(
                answer=(
                    "It seeks returns corresponding to the MSCI World Index. "
                    "[SOURCE 1]"
                ),
                retrieved_chunks=chunks,
                question=(
                    "What is the investment objective of HDFC Developed World "
                    "Overseas Equity Passive FOF?"
                ),
            ),
            [(1, chunks[0])],
        )

    def test_adds_a_verified_citation_when_the_model_omits_one(self):
        chunks = [
            {
                "text": (
                    "HDFC Medium to Long Term Fund. SIP Performance: 1 year SIP. "
                    "Market Value as on August 31, 2026 (Rs. in Lacs): 1.23."
                ),
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 87,
                "source_url": "file:///factsheet.pdf",
            },
            {
                "text": "HDFC ELSS Tax Saver Fund. SIP Performance: 1 year SIP: 1.20.",
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 64,
                "source_url": "file:///factsheet.pdf",
            },
        ]

        answer, citations = ground_answer(
            answer="The 1-year SIP market value was Rs. 1.23 lakh.",
            retrieved_chunks=chunks,
            question=(
                "What was the market value as on August 31, 2026 for the "
                "1-year SIP of HDFC Medium to Long Term Fund?"
            ),
        )

        self.assertTrue(answer.endswith("[SOURCE 1]"))
        self.assertEqual(citations, [(1, chunks[0])])

    def test_combines_adjacent_chunks_from_the_same_page(self):
        chunks = [
            {
                "text": "HDFC Medium to Long Term Fund. SIP Performance.",
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 87,
                "source_url": "file:///factsheet.pdf",
            },
            {
                "text": "1 year SIP. Market Value as on August 31, 2026: 1.23.",
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 87,
                "source_url": "file:///factsheet.pdf",
            },
        ]

        answer, citations = ground_answer(
            answer="The 1-year SIP market value was Rs. 1.23 lakh.",
            retrieved_chunks=chunks,
            question=(
                "What was the market value as on August 31, 2026 for the "
                "1-year SIP of HDFC Medium to Long Term Fund?"
            ),
        )

        self.assertTrue(answer.endswith("[SOURCE 1] [SOURCE 2]"))
        self.assertEqual(citations, [(1, chunks[0]), (2, chunks[1])])

    def test_uses_indexed_fund_metadata_when_a_table_chunk_omits_its_heading(self):
        chunks = [
            {
                "text": (
                    "| Period | Value of ₹ 10,000 invested - Scheme |\n"
                    "| Since Inception | 60,481 |"
                ),
                "fund_name": "HDFC Medium to Long Term Fund",
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 87,
                "source_url": "file:///factsheet.pdf",
            }
        ]

        answer, citations = ground_answer(
            answer="The scheme value was ₹60,481. [SOURCE 1]",
            retrieved_chunks=chunks,
            question=(
                "For HDFC Medium to Long Term Fund, what was the value of "
                "₹10,000 invested since inception?"
            ),
        )

        self.assertEqual(answer, "The scheme value was ₹60,481. [SOURCE 1]")
        self.assertEqual(citations, [(1, chunks[0])])

    def test_does_not_require_question_dates_to_be_repeated_in_source_text(self):
        chunks = [
            {
                "text": "HDFC Medium to Long Term Fund. 1 year SIP market value: 1.23.",
                "document": "HDFC MF Factsheet - August 2026.pdf",
                "page": 87,
                "source_url": "file:///factsheet.pdf",
            }
        ]

        answer, _ = ground_answer(
            answer="As of August 31, 2026, the value was Rs. 1.23 lakh.",
            retrieved_chunks=chunks,
            question=(
                "What was the market value as on August 31, 2026 for the "
                "1-year SIP of HDFC Medium to Long Term Fund?"
            ),
        )

        self.assertTrue(answer.endswith("[SOURCE 1]"))


if __name__ == "__main__":
    unittest.main()
