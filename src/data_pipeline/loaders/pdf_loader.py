from pathlib import Path
try:
    import pymupdf as fitz
except ImportError:
    import fitz  # type: ignore

from src.data_pipeline import DataPipelineError
from src.data_pipeline.loaders.base import BaseDocumentLoader


class PDFLoader(BaseDocumentLoader):
    """Loads and extracts structured text from PDF legal documents."""

    def __init__(self, preserve_layout: bool = True) -> None:
        self.preserve_layout = preserve_layout

    def load(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        try:
            doc = fitz.open(str(path))
            pages_text: list[str] = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                # "text" mode preserves natural text flow and line breaks
                text = page.get_text("text")
                if text:
                    # Clean up excessive blank lines while preserving structural breaks
                    cleaned_lines = [line.strip() for line in text.splitlines()]
                    page_content = "\n".join(line for line in cleaned_lines if line)
                    if page_content:
                        pages_text.append(page_content)

            doc.close()
            full_text = "\n\n".join(pages_text).strip()

            if not full_text:
                raise DataPipelineError(f"PDF document is empty or scanned image without OCR: {path}")

            return full_text

        except FileNotFoundError:
            raise
        except DataPipelineError:
            raise
        except Exception as e:
            raise DataPipelineError(f"Failed to read PDF document {path}: {e}") from e
