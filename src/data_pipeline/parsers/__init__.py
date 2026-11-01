"""Legal document parsers module."""

from src.data_pipeline.parsers.legal_parser import (
    LegalDocumentParser,
    ParsedArticle,
    ParsedClause,
    ParsedLegalStructure,
    ParsedPoint,
)
from src.data_pipeline.parsers.metadata_extractor import LegalMetadataExtractor, normalize_id

__all__ = [
    "LegalMetadataExtractor",
    "LegalDocumentParser",
    "ParsedLegalStructure",
    "ParsedArticle",
    "ParsedClause",
    "ParsedPoint",
    "normalize_id",
]
