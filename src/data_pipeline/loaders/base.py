"""Base document loader contract."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseDocumentLoader(ABC):
    """Abstract base class for document loaders."""

    @abstractmethod
    def load(self, file_path: str | Path) -> str:
        """Load text content from a given file path.

        Args:
            file_path: Path to the target document.

        Returns:
            Extracted text content as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
            DataPipelineError: If file parsing/reading fails.
        """
        raise NotImplementedError
