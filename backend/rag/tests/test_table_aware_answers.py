import unittest

from fundlens_rag.ingestion.table_aware import answer_table_question


class StructuredFactAnswerTests(unittest.TestCase):
    def test_reads_a_dated_aum_fact_from_a_labelled_block(self):
        answer = answer_table_question(
            "What AUM does the factsheet report as of August 31, 2026?",
            [
                {
                    "text": (
                        "## ASSETS UNDER MANAGEMENT\n\nAs on August 31, 2026\n\n"
                        "Average for Month of August, 2026\n\n₹\n\n830.20Cr.\n\n₹\n\n834.46Cr."
                    )
                }
            ],
        )

        self.assertEqual(
            answer,
            "The factsheet reports assets under management of ₹830.20 crore "
            "as of August 31, 2026. [SOURCE 1]",
        )

    def test_distinguishes_average_aum_from_as_of_aum(self):
        answer = answer_table_question(
            "What was the scheme's average AUM for August 2026?",
            [
                {
                    "text": (
                        "## ASSETS UNDER MANAGEMENT\n\nAs on August 31, 2026\n\n"
                        "Average for Month of August, 2026\n\n₹\n\n830.20Cr.\n\n₹\n\n834.46Cr."
                    )
                }
            ],
        )

        self.assertEqual(
            answer,
            "The factsheet reports average assets under management of ₹834.46 crore "
            "for August, 2026. [SOURCE 1]",
        )

    def test_reads_scheme_value_for_since_inception_from_performance_table(self):
        answer = answer_table_question(
            "For HDFC Medium to Long Term Fund, what was the value of ₹10,000 invested since inception?",
            [
                {
                    "text": (
                        "| Date | Period | Value of ₹ 10,000 invested - Scheme ( ₹ ) | "
                        "Value of ₹ 10,000 invested - Benchmark ( ₹ )# |\n"
                        "|---|---|---|---|\n"
                        "| Sep 11, 00 | Since Inception | 60,481 | 84,528 |"
                    )
                }
            ],
        )

        self.assertEqual(
            answer,
            "The factsheet reports a scheme value of ₹60,481 for ₹10,000 "
            "invested since inception. [SOURCE 1]",
        )

    def test_does_not_guess_when_multiple_scheme_values_conflict(self):
        answer = answer_table_question(
            "What was the value of ₹10,000 invested since inception?",
            [
                {
                    "text": (
                        "| Date | Period | Value of ₹ 10,000 invested - Scheme ( ₹ ) |\n"
                        "|---|---|---|\n| Sep 11, 00 | Since Inception | 60,481 |"
                    )
                },
                {
                    "text": (
                        "| Date | Period | Value of ₹ 10,000 invested - Scheme ( ₹ ) |\n"
                        "|---|---|---|\n| Sep 11, 00 | Since Inception | 70,000 |"
                    )
                },
            ],
        )

        self.assertIsNone(answer)


if __name__ == "__main__":
    unittest.main()
