import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fundlens_rag.ingestion.fund_metadata import (
    assign_fund_names_to_pages,
    attach_fund_names_to_chunks,
    extract_fund_names,
    list_known_funds,
    resolve_fund_name,
)
from fundlens_rag.rag.factsheets import ensure_factsheets_indexed


class FundMetadataTests(unittest.TestCase):
    def test_extracts_scheme_headings_but_ignores_generic_headings(self):
        markdown = """
## Fund Manager
## HDFC Medium to Long Term Fund
## HDFC Large &amp; Mid Cap Fund
## HDFC NIFTY 50 ETF
## HDFC Developed World Overseas Equity Passive FOF
## Performance details of Schemes managed by respective Fund Managers
"""

        self.assertEqual(
            extract_fund_names(markdown),
            [
                "HDFC Medium to Long Term Fund",
                "HDFC Large & Mid Cap Fund",
                "HDFC NIFTY 50 ETF",
                "HDFC Developed World Overseas Equity Passive FOF",
            ],
        )

    def test_resolves_canonical_name_case_insensitively_and_without_amc_prefix(self):
        known = ["HDFC Medium to Long Term Fund", "HDFC Medium Term Fund"]

        self.assertEqual(
            resolve_fund_name(
                "What was the value for HDFC MEDIUM TO LONG TERM FUND?",
                known,
            ),
            "HDFC Medium to Long Term Fund",
        )
        self.assertEqual(
            resolve_fund_name("Market value for Medium to Long Term Fund", known),
            "HDFC Medium to Long Term Fund",
        )

        self.assertEqual(
            resolve_fund_name(
                "What is the objective of HDFC Developed World Overseas Equity Passive FOF?",
                ["HDFC Developed World Overseas Equity Passive FOF"],
            ),
            "HDFC Developed World Overseas Equity Passive FOF",
        )

    def test_does_not_guess_when_fund_name_is_missing_or_ambiguous(self):
        known = ["HDFC Medium to Long Term Fund", "HDFC Medium Term Fund"]

        self.assertIsNone(resolve_fund_name("What was the since inception value?", known))
        self.assertIsNone(
            resolve_fund_name("What happened to the HDFC Medium Fund?", known)
        )
        self.assertIsNone(
            resolve_fund_name(
                "Compare HDFC Medium Term Fund and HDFC Medium to Long Term Fund",
                known,
            )
        )

    def test_longer_scheme_name_wins_over_its_embedded_shorter_name(self):
        known = ["HDFC Gold ETF", "HDFC Gold ETF Fund of Fund"]

        self.assertEqual(
            resolve_fund_name(
                "What was the return of HDFC Gold ETF Fund of Fund?",
                known,
            ),
            "HDFC Gold ETF Fund of Fund",
        )
        self.assertIsNone(
            resolve_fund_name(
                "Compare HDFC Gold ETF and HDFC Gold ETF Fund of Fund",
                known,
            )
        )

    def test_carries_one_fund_heading_across_continuation_pages(self):
        pages = [
            (87, "| Since Inception | ₹60,481 |"),
            (86, "## HDFC Medium to Long Term Fund\n\nPortfolio details"),
            (88, "## HDFC Long Term Fund\n\nPerformance details"),
        ]

        assigned = assign_fund_names_to_pages(pages)

        self.assertEqual(
            assigned,
            [
                (86, "## HDFC Medium to Long Term Fund\n\nPortfolio details", "HDFC Medium to Long Term Fund"),
                (87, "| Since Inception | ₹60,481 |", "HDFC Medium to Long Term Fund"),
                (88, "## HDFC Long Term Fund\n\nPerformance details", "HDFC Long Term Fund"),
            ],
        )

    def test_shared_pages_are_not_assigned_to_one_fund_by_guess(self):
        pages = [
            (
                1,
                "## HDFC Medium to Long Term Fund\n"
                "## HDFC Long Term Fund\nShared performance details",
            )
        ]

        self.assertEqual(assign_fund_names_to_pages(pages)[0][2], None)

    def test_attaches_same_page_fund_to_heading_and_table_chunks(self):
        chunks = [
            {
                "id": 10,
                "document": "factsheet.pdf",
                "page": 87,
                "text": "## HDFC Medium to Long Term Fund",
            },
            {
                "id": 11,
                "document": "factsheet.pdf",
                "page": 87,
                "text": "Since Inception; Scheme value = 60,481",
            },
        ]

        enriched = attach_fund_names_to_chunks(chunks)

        self.assertEqual(
            [chunk["fund_name"] for chunk in enriched],
            ["HDFC Medium to Long Term Fund", "HDFC Medium to Long Term Fund"],
        )
        self.assertNotIn("fund_name", chunks[0])

    def test_fund_catalog_reads_markdown_and_chunk_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            markdown_directory = Path(directory) / "markdown"
            chunks_directory = Path(directory) / "chunks"
            markdown_directory.mkdir()
            chunks_directory.mkdir()
            (markdown_directory / "one.md").write_text(
                "## HDFC Medium to Long Term Fund\n", encoding="utf-8"
            )
            (chunks_directory / "two.json").write_text(
                json.dumps(
                    [
                        {
                            "text": "## HDFC Large &amp; Mid Cap Fund",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                list_known_funds(markdown_directory, chunks_directory),
                [
                    "HDFC Large & Mid Cap Fund",
                    "HDFC Medium to Long Term Fund",
                ],
            )


class LegacyChunkIndexMigrationTests(unittest.TestCase):
    def test_enriches_existing_chunk_json_in_memory_without_rewriting_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chunk_directory = root / "chunks"
            chunk_directory.mkdir()
            chunk_path = chunk_directory / "factsheet.json"
            original_chunks = [
                {
                    "id": 10,
                    "text": "## HDFC Medium to Long Term Fund",
                    "document": "factsheet.pdf",
                    "page": 87,
                    "source_url": "file:///factsheet.pdf",
                    "document_type": "factsheet",
                    "published_date": "",
                },
                {
                    "id": 11,
                    "text": "Since Inception; Scheme value = 60,481",
                    "document": "factsheet.pdf",
                    "page": 87,
                    "source_url": "file:///factsheet.pdf",
                    "document_type": "factsheet",
                    "published_date": "",
                },
            ]
            original_contents = json.dumps(original_chunks)
            chunk_path.write_text(original_contents, encoding="utf-8")
            store = MagicMock()
            store.indexed_documents.return_value = set()

            with (
                patch("fundlens_rag.rag.factsheets.find_factsheets", return_value=[root / "factsheet.pdf"]),
                patch("fundlens_rag.rag.factsheets.CHUNKS_DIRECTORY", chunk_directory),
                patch("fundlens_rag.rag.factsheets.MARKDOWN_DIRECTORY", root / "markdown"),
                patch("fundlens_rag.rag.factsheets.VectorStore", return_value=store),
            ):
                ensure_factsheets_indexed()

            indexed_chunks = store.add_documents.call_args.args[0]
            self.assertEqual(
                [chunk["fund_name"] for chunk in indexed_chunks],
                ["HDFC Medium to Long Term Fund"] * 2,
            )
            self.assertEqual(chunk_path.read_text(encoding="utf-8"), original_contents)
            store.client.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
