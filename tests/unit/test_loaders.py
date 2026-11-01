"""Unit tests for document loaders (PDFLoader, DocxLoader, HTMLLoader)."""

from pathlib import Path
import tempfile
import unittest

import docx
import fitz

from src.data_pipeline.loaders.docx_loader import DocxLoader
from src.data_pipeline.loaders.html_loader import HTMLLoader
from src.data_pipeline.loaders.pdf_loader import PDFLoader


class TestLoaders(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_pdf_loader_success(self) -> None:
        pdf_path = self.temp_path / "sample.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "QUOC HOI\nSo: 45/2019/QH14\nDieu 1. Pham vi dieu chinh\nNoi dung dieu luat.")
        doc.save(str(pdf_path))
        doc.close()

        loader = PDFLoader()
        text = loader.load(pdf_path)

        self.assertIn("QUOC HOI", text)
        self.assertIn("Dieu 1. Pham vi dieu chinh", text)

    def test_pdf_loader_missing_file(self) -> None:
        loader = PDFLoader()
        with self.assertRaises(FileNotFoundError):
            loader.load(self.temp_path / "non_existent.pdf")

    def test_docx_loader_success(self) -> None:
        docx_path = self.temp_path / "sample.docx"
        doc = docx.Document()
        doc.add_paragraph("BỘ LUẬT LAO ĐỘNG")
        doc.add_paragraph("Điều 1. Phạm vi áp dụng")
        table = doc.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Cột 1"
        table.rows[0].cells[1].text = "Cột 2"
        doc.save(str(docx_path))

        loader = DocxLoader()
        text = loader.load(docx_path)

        self.assertIn("BỘ LUẬT LAO ĐỘNG", text)
        self.assertIn("Điều 1. Phạm vi áp dụng", text)
        self.assertIn("Cột 1 | Cột 2", text)

    def test_docx_loader_missing_file(self) -> None:
        loader = DocxLoader()
        with self.assertRaises(FileNotFoundError):
            loader.load(self.temp_path / "non_existent.docx")

    def test_html_loader_success(self) -> None:
        html_path = self.temp_path / "sample.html"
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Test</title></head>
        <body>
            <nav><a href="#">Trang chủ</a></nav>
            <div class="sidebar"><p>Quảng cáo</p></div>
            <div id="content">
                <h1>NGHỊ ĐỊNH Số: 145/2020/NĐ-CP</h1>
                <p>Điều 1. Hướng dẫn thi hành một số điều của Bộ luật Lao động.</p>
            </div>
            <footer>Bản quyền 2024</footer>
        </body>
        </html>
        """
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        loader = HTMLLoader()
        text = loader.load(html_path)

        self.assertIn("145/2020/NĐ-CP", text)
        self.assertIn("Điều 1. Hướng dẫn thi hành", text)
        self.assertNotIn("Quảng cáo", text)
        self.assertNotIn("Bản quyền 2024", text)

    def test_html_loader_missing_file(self) -> None:
        loader = HTMLLoader()
        with self.assertRaises(FileNotFoundError):
            loader.load(self.temp_path / "non_existent.html")


if __name__ == "__main__":
    unittest.main()
