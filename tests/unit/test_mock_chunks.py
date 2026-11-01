"""Tests for mock chunks validation and schema compliance."""

import json
from pathlib import Path
import unittest

from core.schemas.document import LegalChunk


class TestMockChunks(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_file = Path("data/chunks/mock_chunks.json")

    def test_mock_chunks_file_exists(self) -> None:
        self.assertTrue(self.mock_file.is_file(), "mock_chunks.json does not exist")

    def test_mock_chunks_schema_compliance(self) -> None:
        with open(self.mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 5, "At least 5 mock chunks should be provided")

        validated_chunks: list[LegalChunk] = []
        for item in data:
            chunk = LegalChunk.model_validate(item)
            validated_chunks.append(chunk)

            # Assert required core attributes
            self.assertTrue(chunk.chunk_id)
            self.assertEqual(chunk.document_id, chunk.metadata.document_id)
            self.assertTrue(chunk.content)
            self.assertTrue(chunk.article)
            self.assertTrue(chunk.metadata.title)
            self.assertTrue(chunk.metadata.document_number)

        # Check that target articles (Dieu 35, 36, 137) are included
        articles_included = " ".join(c.article or "" for c in validated_chunks)
        self.assertIn("Điều 35", articles_included)
        self.assertIn("Điều 36", articles_included)
        self.assertIn("Điều 137", articles_included)


if __name__ == "__main__":
    unittest.main()
