"""Unit tests for PhapDienLoader."""

import unittest

from core.schemas.document import LegalChunk, LegalDocument, LegalMetadata
from src.data_pipeline.loaders.phapdien_loader import PhapDienLoader


class TestPhapDienLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.loader = PhapDienLoader()
        self.sample_row = {
            "record_id": "rec_001",
            "subject_title_vi": "An ninh quốc gia",
            "topic_title_vi": "Bảo vệ bí mật nhà nước",
            "chapter_title": "Chương II: Hoạt động bảo vệ",
            "article_id": "Điều 1.1.LQ.1",
            "article_title": "Điều 1.1.LQ.1. Phạm vi điều chỉnh",
            "source_note_text": "(Điều 1 Luật số 32/2004/QH11 An ninh Quốc gia ngày 03/12/2004 của Quốc hội, có hiệu lực thi hành kể từ ngày 01/07/2005 )",
            "related_note_text": "(Điều này có nội dung liên quan đến Điều 1.12.LQ.11. Biện pháp cảnh vệ ; Điều 1.11.LQ.1. Phạm vi áp dụng)",
            "content_text": "Luật này quy định về chính sách an ninh quốc gia, nguyên tắc và biện pháp bảo vệ.",
            "source_links": [
                {
                    "text": "Link nguồn",
                    "href": "http://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=18562#Chuong_I_Dieu_1",
                }
            ],
        }

    def test_extract_metadata(self) -> None:
        metadata = self.loader.extract_metadata_from_row(self.sample_row)

        self.assertIsInstance(metadata, LegalMetadata)
        self.assertEqual(metadata.document_number, "32/2004/QH11")
        self.assertEqual(metadata.document_id, "32_2004_QH11")
        self.assertEqual(metadata.document_type, "Luật")
        self.assertEqual(metadata.issued_date, "2004-12-03")
        self.assertEqual(metadata.effective_date, "2005-07-01")
        self.assertIn("Quốc Hội", metadata.issuing_authority or "")
        self.assertEqual(metadata.status, "active")

    def test_extract_relations(self) -> None:
        relations = self.loader.extract_relations_from_row(self.sample_row)

        self.assertIsInstance(relations, list)
        self.assertEqual(len(relations), 2)
        self.assertEqual(relations[0]["source"], "Điều 1.1.LQ.1")
        self.assertEqual(relations[0]["target"], "Điều 1.12.LQ.11")
        self.assertEqual(relations[0]["type"], "RELATED_TO")
        self.assertEqual(relations[1]["target"], "Điều 1.11.LQ.1")

    def test_transform_row(self) -> None:
        doc, chunk, relations = self.loader.transform_row(self.sample_row)

        # Validate Document
        self.assertIsInstance(doc, LegalDocument)
        self.assertEqual(doc.document_id, "32_2004_QH11")
        self.assertEqual(doc.document_id, doc.metadata.document_id)

        # Validate Chunk
        self.assertIsInstance(chunk, LegalChunk)
        self.assertEqual(chunk.document_id, "32_2004_QH11")
        self.assertEqual(chunk.document_id, chunk.metadata.document_id)
        self.assertIn("An ninh quốc gia", chunk.content)
        self.assertIn("Bảo vệ bí mật nhà nước", chunk.content)
        self.assertEqual(chunk.chapter, "Chương II: Hoạt động bảo vệ")
        self.assertEqual(chunk.article, "Điều 1.1.LQ.1. Phạm vi điều chỉnh")

        # Validate Relations count
        self.assertEqual(len(relations), 2)


if __name__ == "__main__":
    unittest.main()
