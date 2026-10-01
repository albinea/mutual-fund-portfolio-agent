import unittest

from fundlens_rag.ingestion.chunker import chunk_markdown


class MarkdownChunkerTests(unittest.TestCase):
    def test_keeps_an_oversized_table_in_one_chunk(self):
        table = "\n".join(
            ["| Period | Market value |", "|---|---|"]
            + [f"| {year} year SIP | {year}.23 |" for year in range(1, 30)]
        )
        markdown = f"## HDFC Example Fund\n\n{table}"

        chunks = chunk_markdown(
            markdown=markdown,
            document="example.pdf",
            page=87,
            chunk_size=100,
        )

        table_chunks = [chunk for chunk in chunks if "| Period |" in chunk.text]
        self.assertEqual(len(table_chunks), 1)
        self.assertIn("| 29 year SIP | 29.23 |", table_chunks[0].text)
        self.assertEqual(table_chunks[0].page, 87)


if __name__ == "__main__":
    unittest.main()
