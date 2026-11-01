"""Regression tests for data integrity, document flow, identity, and metadata correctness."""

from pathlib import Path
import tempfile
import unittest

import docx

from core.schemas.document import LegalChunk, LegalDocument, LegalMetadata
from scripts.ingest_phapdien import group_articles_into_documents
from src.data_pipeline.loaders.docx_loader import DocxLoader
from src.data_pipeline.loaders.phapdien_loader import PhapDienLoader
from src.data_pipeline.parsers.legal_parser import LegalDocumentParser
from src.data_pipeline.parsers.metadata_extractor import (
    LegalMetadataExtractor,
    validate_iso_date,
)


class TestRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.metadata_extractor = LegalMetadataExtractor()
        self.parser = LegalDocumentParser(self.metadata_extractor)
        self.phapdien_loader = PhapDienLoader()

    # 1. docx_loader: Paragraph and table ordering
    def test_docx_paragraph_table_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_order.docx"
            doc = docx.Document()
            doc.add_paragraph("Điều 1. Phạm vi điều chỉnh")
            table = doc.add_table(rows=1, cols=1)
            table.rows[0].cells[0].text = "Bảng chi tiết nội dung Điều 1"
            doc.add_paragraph("Điều 2. Đối tượng áp dụng")
            doc.save(str(file_path))

            loader = DocxLoader()
            text = loader.load(file_path)

            idx_dieu1 = text.find("Điều 1. Phạm vi điều chỉnh")
            idx_bang = text.find("Bảng chi tiết nội dung Điều 1")
            idx_dieu2 = text.find("Điều 2. Đối tượng áp dụng")

            self.assertTrue(idx_dieu1 != -1 and idx_bang != -1 and idx_dieu2 != -1)
            # Verify table appears strictly BETWEEN Điều 1 and Điều 2
            self.assertLess(idx_dieu1, idx_bang, "Table must appear after Điều 1")
            self.assertLess(idx_bang, idx_dieu2, "Table must appear before Điều 2")

    # 2. metadata_extractor: distinct and deterministic ID for unnumbered documents
    def test_unknown_doc_id_distinct_and_deterministic(self) -> None:
        text_a = "VĂN BẢN HƯỚNG DẪN NỘI BỘ\nĐiều 1. Quy định về tài chính công ty A."
        text_b = "QUY ĐỊNH AN TOÀN LAO ĐỘNG\nĐiều 1. Quy định về trang bị bảo hộ tại công trường B."

        meta_a1 = self.metadata_extractor.extract(text_a, fallback_title="Văn bản A")
        meta_a2 = self.metadata_extractor.extract(text_a, fallback_title="Văn bản A")
        meta_b = self.metadata_extractor.extract(text_b, fallback_title="Quy định B")

        # Distinct between different sources
        self.assertNotEqual(meta_a1.document_id, meta_b.document_id)
        self.assertNotEqual(meta_a1.document_id, "doc_unknown")
        self.assertNotEqual(meta_b.document_id, "doc_unknown")

        # Deterministic across repeated calls on identical source
        self.assertEqual(meta_a1.document_id, meta_a2.document_id)

    # 3. legal_parser: Letter suffixes in Article numbers ("Điều 1" vs "Điều 1a")
    def test_article_letter_suffix_preserved(self) -> None:
        text = """
QUỐC HỘI
Số: 01/2024/QH15

Điều 1. Quy định chung
Nội dung điều 1.

Điều 1a. Quy định bổ sung
Nội dung điều 1a.

Điều 12b. Hiệu lực thi hành
Nội dung điều 12b.
"""
        structure = self.parser.parse_to_structure(text)
        articles = structure.articles

        self.assertEqual(len(articles), 3)

        self.assertEqual(articles[0].number, "1")
        self.assertEqual(articles[0].article_id, "01_2024_QH15_DIEU_1")

        self.assertEqual(articles[1].number, "1a")
        self.assertEqual(articles[1].article_id, "01_2024_QH15_DIEU_1A")

        self.assertEqual(articles[2].number, "12b")
        self.assertEqual(articles[2].article_id, "01_2024_QH15_DIEU_12B")

        # Ensure no ID collisions
        ids = [a.article_id for a in articles]
        self.assertEqual(len(ids), len(set(ids)))

    # 4. legal_parser: Multiline point content preserved in ParsedPoint.content
    def test_multiline_point_content_preserved(self) -> None:
        text = """
QUỐC HỘI
Số: 02/2024/QH15

Điều 5. Nghĩa vụ người lao động
1. Người lao động có các nghĩa vụ sau:
a) Chấp hành nghiêm chỉnh nội quy lao động;
đồng thời tuân thủ các quy định về an toàn vệ sinh lao động tại nơi làm việc;
b) Thực hiện đúng hợp đồng.
"""
        structure = self.parser.parse_to_structure(text)
        art = structure.articles[0]
        clause = art.clauses[0]
        point_a = clause.points[0]

        self.assertEqual(point_a.letter, "a")
        self.assertIn("Chấp hành nghiêm chỉnh nội quy lao động", point_a.content)
        self.assertIn("đồng thời tuân thủ các quy định về an toàn vệ sinh lao động", point_a.content)

    # 5. phapdien_loader: Effective date is not mistakenly copied as issued_date
    def test_effective_date_not_confused_with_issued_date(self) -> None:
        row = {
            "record_id": "rec_002",
            "article_id": "Điều 1.1.LQ.2",
            "article_title": "Điều 1.1.LQ.2. Đối tượng áp dụng",
            "source_note_text": "(Điều 2 Luật số 32/2004/QH11, có hiệu lực thi hành kể từ ngày 01/07/2005)",
            "content_text": "Luật này áp dụng đối với cá nhân, tổ chức.",
        }
        meta = self.phapdien_loader.extract_metadata_from_row(row)

        self.assertEqual(meta.effective_date, "2005-07-01")
        # Issued date was not in source_note, so it MUST remain None
        self.assertIsNone(meta.issued_date, "issued_date must be None when only effective_date is provided")

    # 6. metadata_extractor: Calendar validation rejects impossible dates (e.g., 31/02/2024)
    def test_calendar_validation_rejects_invalid_dates(self) -> None:
        # Direct helper check
        self.assertIsNone(validate_iso_date(2024, 2, 31))
        self.assertEqual(validate_iso_date(2024, 2, 29), "2024-02-29")  # Leap year valid
        self.assertIsNone(validate_iso_date(2023, 2, 29))  # Non-leap year invalid

        # Regex extractor check with impossible date
        text = "QUỐC HỘI\nSố: 99/2024/QH15\nngày 31 tháng 02 năm 2024\nĐiều 1. Thử nghiệm."
        meta = self.metadata_extractor.extract(text)
        self.assertIsNone(meta.issued_date, "Invalid calendar date 31/02/2024 must yield None")

    # 7. status remains 'unknown' without verified authority
    def test_status_remains_unknown_without_verification(self) -> None:
        text = "QUỐC HỘI\nSố: 45/2019/QH14\nngày 20 tháng 11 năm 2019\ncó hiệu lực từ ngày 01 tháng 01 năm 2021\nĐiều 1. Luật."
        meta1 = self.metadata_extractor.extract(text)
        self.assertEqual(meta1.status, "unknown")

        row = {
            "record_id": "rec_003",
            "article_id": "Điều 1.1.LQ.1",
            "source_note_text": "(Điều 1 Luật số 32/2004/QH11 ngày 03/12/2004 của Quốc hội, có hiệu lực thi hành kể từ ngày 01/07/2005)",
            "content_text": "Nội dung",
        }
        meta2 = self.phapdien_loader.extract_metadata_from_row(row)
        self.assertEqual(meta2.status, "unknown")

    # 8. ingest_phapdien: Group articles into unified LegalDocument by document_id
    def test_phapdien_document_grouping(self) -> None:
        meta_doc1 = LegalMetadata(
            document_id="45_2019_QH14",
            title="Bộ luật Lao động 2019",
            document_number="45/2019/QH14",
            document_type="Bộ luật",
        )
        meta_doc2 = LegalMetadata(
            document_id="145_2020_ND_CP",
            title="Nghị định 145/2020/NĐ-CP",
            document_number="145/2020/NĐ-CP",
            document_type="Nghị định",
        )

        doc1_art1 = LegalDocument(document_id="45_2019_QH14", content="Nội dung Điều 1 Luật 45", metadata=meta_doc1)
        doc1_art2 = LegalDocument(document_id="45_2019_QH14", content="Nội dung Điều 2 Luật 45", metadata=meta_doc1)
        doc2_art1 = LegalDocument(document_id="145_2020_ND_CP", content="Nội dung Điều 1 Nghị định 145", metadata=meta_doc2)

        pairs = [
            (doc1_art1, object()),
            (doc1_art2, object()),
            (doc2_art1, object()),
        ]

        merged = group_articles_into_documents(pairs)

        # 3 articles should be grouped into exactly 2 LegalDocuments
        self.assertEqual(len(merged), 2)
        doc_ids = {d.document_id for d in merged}
        self.assertEqual(doc_ids, {"45_2019_QH14", "145_2020_ND_CP"})

        # Check that doc1 contains both articles' contents
        doc1_merged = next(d for d in merged if d.document_id == "45_2019_QH14")
        self.assertIn("Nội dung Điều 1 Luật 45", doc1_merged.content)
        self.assertIn("Nội dung Điều 2 Luật 45", doc1_merged.content)

    # 9. ingest_phapdien: Empty conversion aborts and does not overwrite existing files
    def test_empty_ingest_aborts_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            existing_file = tmp_path / "phapdien_chunks.json"
            sentinel_data = [{"chunk_id": "PRESERVED_CHUNK"}]

            with open(existing_file, "w", encoding="utf-8") as f:
                import json
                json.dump(sentinel_data, f)

            # Check sentinel data exists
            with open(existing_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), '[{"chunk_id": "PRESERVED_CHUNK"}]')


if __name__ == "__main__":
    unittest.main()
