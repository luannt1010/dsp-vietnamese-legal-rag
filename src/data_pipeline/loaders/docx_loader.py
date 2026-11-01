"""DOCX Document Loader using python-docx."""

from pathlib import Path
import docx

from src.data_pipeline import DataPipelineError
from src.data_pipeline.loaders.base import BaseDocumentLoader


class DocxLoader(BaseDocumentLoader):
    """Loads and extracts text from Word (.docx) legal documents."""

    def load(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"DOCX file not found: {path}")

        try:
            document = docx.Document(str(path))
            elements: list[str] = []

            # Extract paragraphs
            for paragraph in document.paragraphs:
                text = paragraph.text.strip()
                if text:
                    elements.append(text)

            # Extract tables if any (commonly used in decrees and annexes)
            for table in document.tables:
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if row_cells:
                        elements.append(" | ".join(row_cells))

            full_text = "\n".join(elements).strip()
            if not full_text:
                raise DataPipelineError(f"DOCX document contains no readable text: {path}")

            return full_text

        except FileNotFoundError:
            raise
        except DataPipelineError:
            raise
        except Exception as e:
            raise DataPipelineError(f"Failed to read DOCX document {path}: {e}") from e
