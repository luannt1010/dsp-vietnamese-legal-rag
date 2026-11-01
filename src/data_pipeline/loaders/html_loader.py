"""HTML Document Loader using BeautifulSoup4."""

from pathlib import Path
from bs4 import BeautifulSoup

from src.data_pipeline import DataPipelineError
from src.data_pipeline.loaders.base import BaseDocumentLoader


class HTMLLoader(BaseDocumentLoader):
    """Loads and cleans HTML legal documents crawled from legal portals."""

    # Unwanted HTML tags to strip
    STRIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "iframe", "noscript", "svg"}

    # Common class names and IDs associated with navigation, sidebars and ads in Vietnamese legal sites
    UNWANTED_SELECTORS = [
        ".nav", ".navbar", ".menu", ".sidebar", ".ads", ".advertisement",
        ".header", ".footer", ".breadcrumb", ".social-share", ".comment-section",
        "#header", "#footer", "#sidebar", "#menu", "#nav"
    ]

    def load(self, file_path: str | Path) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"HTML file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            soup = BeautifulSoup(content, "html.parser")

            # Remove unwanted tags
            for tag in soup.find_all(self.STRIP_TAGS):
                tag.decompose()

            # Remove elements matching unwanted selectors
            for selector in self.UNWANTED_SELECTORS:
                for el in soup.select(selector):
                    el.decompose()

            # Prefer legal content container if present (common across thuvienphapluat, vbpl, vanban.chinhphu)
            main_container = (
                soup.find("div", class_="content1")
                or soup.find("div", id="content")
                or soup.find("div", class_="content")
                or soup.find("article")
                or soup.body
                or soup
            )

            # Extract text with newline preservation
            text = main_container.get_text(separator="\n")
            lines = [line.strip() for line in text.splitlines()]
            cleaned_text = "\n".join(line for line in lines if line)

            if not cleaned_text:
                raise DataPipelineError(f"HTML document contains no extractable text: {path}")

            return cleaned_text

        except FileNotFoundError:
            raise
        except DataPipelineError:
            raise
        except Exception as e:
            raise DataPipelineError(f"Failed to read HTML document {path}: {e}") from e
