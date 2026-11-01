"""Unit tests for metadata extractor and legal document parser."""

import unittest

from core.schemas.document import LegalDocument, LegalMetadata
from src.data_pipeline.parsers.legal_parser import LegalDocumentParser
from src.data_pipeline.parsers.metadata_extractor import LegalMetadataExtractor, normalize_id


class TestParsers(unittest.TestCase):
    def setUp(self) -> None:
        self.metadata_extractor = LegalMetadataExtractor()
        self.parser = LegalDocumentParser(self.metadata_extractor)

        self.sample_law_text = """
QUỐC HỘI
Số: 45/2019/QH14
Hà Nội, ngày 20 tháng 11 năm 2019

BỘ LUẬT LAO ĐỘNG

Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;
Quốc hội ban hành Bộ luật Lao động.

Chương I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
Bộ luật Lao động quy định tiêu chuẩn lao động; quyền, nghĩa vụ, trách nhiệm của người lao động.

Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động
1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước:
a) Ít nhất 45 ngày nếu làm việc theo hợp đồng không xác định thời hạn;
b) Ít nhất 30 ngày nếu làm việc theo hợp đồng xác định thời hạn từ 12 đến 36 tháng.
2. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước trong các trường hợp sau đây:
a) Không được bố trí theo đúng công việc;
b) Không được trả đủ lương.

Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.
"""

    def test_normalize_id(self) -> None:
        self.assertEqual(normalize_id("45/2019/QH14"), "45_2019_QH14")
        self.assertEqual(normalize_id("145/2020/NĐ-CP"), "145_2020_ND_CP")

    def test_metadata_extractor(self) -> None:
        metadata = self.metadata_extractor.extract(self.sample_law_text)

        self.assertIsInstance(metadata, LegalMetadata)
        self.assertEqual(metadata.document_number, "45/2019/QH14")
        self.assertEqual(metadata.document_id, "45_2019_QH14")
        self.assertIn("Bộ Luật", metadata.document_type)
        self.assertIn("Quốc Hội", metadata.issuing_authority or "")
        self.assertEqual(metadata.issued_date, "2019-11-20")
        self.assertEqual(metadata.effective_date, "2021-01-01")
        self.assertEqual(metadata.status, "unknown")

    def test_legal_parser_full_document(self) -> None:
        doc = self.parser.parse(self.sample_law_text)

        self.assertIsInstance(doc, LegalDocument)
        self.assertEqual(doc.document_id, "45_2019_QH14")
        self.assertEqual(doc.document_id, doc.metadata.document_id)
        self.assertIn("Điều 35", doc.content)

    def test_legal_parser_structure(self) -> None:
        structure = self.parser.parse_to_structure(self.sample_law_text)

        # Check Chapters
        self.assertGreaterEqual(len(structure.chapters), 1)
        self.assertIn("Chương I", structure.chapters[0])

        # Check Articles
        self.assertEqual(len(structure.articles), 2)

        art1 = structure.articles[0]
        self.assertEqual(art1.number, "1")
        self.assertEqual(art1.article_id, "45_2019_QH14_DIEU_1")
        self.assertIn("Phạm vi điều chỉnh", art1.title)

        art35 = structure.articles[1]
        self.assertEqual(art35.number, "35")
        self.assertEqual(art35.article_id, "45_2019_QH14_DIEU_35")
        self.assertIn("Quyền đơn phương chấm dứt", art35.title)

        # Check Clauses of Dieu 35
        self.assertEqual(len(art35.clauses), 2)
        clause1 = art35.clauses[0]
        self.assertEqual(clause1.number, "1")
        self.assertEqual(clause1.clause_id, "45_2019_QH14_DIEU_35_KHOAN_1")

        # Check Points of Clause 1
        self.assertEqual(len(clause1.points), 2)
        self.assertEqual(clause1.points[0].letter, "a")
        self.assertEqual(clause1.points[1].letter, "b")


if __name__ == "__main__":
    unittest.main()
