"""Hierarchical Legal Document Parser for Vietnamese legal documents."""

import re
from dataclasses import dataclass, field
from core.schemas.document import LegalDocument, LegalMetadata
from src.data_pipeline.parsers.metadata_extractor import LegalMetadataExtractor


@dataclass
class ParsedPoint:
    point_id: str
    letter: str  # a, b, c, đ...
    content: str


@dataclass
class ParsedClause:
    clause_id: str
    number: str  # 1, 2, 3...
    content: str
    points: list[ParsedPoint] = field(default_factory=list)


@dataclass
class ParsedArticle:
    article_id: str
    number: str
    title: str
    content: str
    chapter: str | None = None
    section: str | None = None
    clauses: list[ParsedClause] = field(default_factory=list)


@dataclass
class ParsedLegalStructure:
    metadata: LegalMetadata
    chapters: list[str] = field(default_factory=list)
    articles: list[ParsedArticle] = field(default_factory=list)


class LegalDocumentParser:
    """Parses Vietnamese legal documents into structured hierarchical components."""

    # Regex patterns for structural levels
    CHAPTER_PATTERN = re.compile(
        r"^(Chương\s+[IVXLCDM\d]+)[\.:\s\-—]*(.*)$", re.IGNORECASE
    )
    SECTION_PATTERN = re.compile(
        r"^(Mục\s+\d+)[\.:\s\-—]*(.*)$", re.IGNORECASE
    )
    ARTICLE_PATTERN = re.compile(
        r"^(Điều\s+\d+)[\.:\s\-—]*(.*)$", re.IGNORECASE
    )
    CLAUSE_PATTERN = re.compile(
        r"^(\d+)[\.\)]\s+(.*)$"
    )
    POINT_PATTERN = re.compile(
        r"^([a-zđ])\)\s+(.*)$", re.IGNORECASE
    )

    def __init__(self, metadata_extractor: LegalMetadataExtractor | None = None) -> None:
        self.metadata_extractor = metadata_extractor or LegalMetadataExtractor()

    def parse_to_structure(self, text: str, metadata: LegalMetadata | None = None) -> ParsedLegalStructure:
        """Parse raw text into hierarchical structure of Chapters, Sections, Articles, Clauses and Points."""
        if metadata is None:
            metadata = self.metadata_extractor.extract(text)

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        current_chapter: str | None = None
        current_section: str | None = None
        current_article: ParsedArticle | None = None
        current_clause: ParsedClause | None = None

        articles: list[ParsedArticle] = []
        chapters: list[str] = []

        for line in lines:
            # Check Chapter
            chap_match = self.CHAPTER_PATTERN.match(line)
            if chap_match:
                chap_num = chap_match.group(1).strip()
                chap_title = chap_match.group(2).strip()
                current_chapter = f"{chap_num}: {chap_title}" if chap_title else chap_num
                chapters.append(current_chapter)
                continue

            # Check Section
            sec_match = self.SECTION_PATTERN.match(line)
            if sec_match:
                sec_num = sec_match.group(1).strip()
                sec_title = sec_match.group(2).strip()
                current_section = f"{sec_num}: {sec_title}" if sec_title else sec_num
                continue

            # Check Article
            art_match = self.ARTICLE_PATTERN.match(line)
            if art_match:
                art_num_str = art_match.group(1).strip()
                art_title = art_match.group(2).strip()
                num_only = re.search(r"\d+", art_num_str).group(0)

                art_id = f"{metadata.document_id}_DIEU_{num_only}"
                current_article = ParsedArticle(
                    article_id=art_id,
                    number=num_only,
                    title=f"{art_num_str}: {art_title}" if art_title else art_num_str,
                    content="",
                    chapter=current_chapter,
                    section=current_section,
                    clauses=[],
                )
                articles.append(current_article)
                current_clause = None
                continue

            # If we are inside an Article, check Clauses and Points
            if current_article:
                clause_match = self.CLAUSE_PATTERN.match(line)
                point_match = self.POINT_PATTERN.match(line)

                if clause_match:
                    cl_num = clause_match.group(1).strip()
                    cl_text = clause_match.group(2).strip()
                    cl_id = f"{current_article.article_id}_KHOAN_{cl_num}"

                    current_clause = ParsedClause(
                        clause_id=cl_id,
                        number=cl_num,
                        content=line,
                        points=[],
                    )
                    current_article.clauses.append(current_clause)
                    # Append to article overall content
                    current_article.content = (current_article.content + "\n" + line).strip()
                    continue

                elif point_match and current_clause:
                    pt_letter = point_match.group(1).lower().strip()
                    pt_id = f"{current_clause.clause_id}_DIEM_{pt_letter}"

                    current_point = ParsedPoint(
                        point_id=pt_id,
                        letter=pt_letter,
                        content=line,
                    )
                    current_clause.points.append(current_point)
                    # Also append to clause and article content
                    current_clause.content = (current_clause.content + "\n" + line).strip()
                    current_article.content = (current_article.content + "\n" + line).strip()
                    continue

                else:
                    # Additional continuation text for current clause or article
                    if current_clause:
                        current_clause.content = (current_clause.content + " " + line).strip()
                    current_article.content = (current_article.content + "\n" + line).strip()

        return ParsedLegalStructure(
            metadata=metadata,
            chapters=chapters,
            articles=articles,
        )

    def parse(self, text: str, metadata: LegalMetadata | None = None) -> LegalDocument:
        """Parse raw text into a LegalDocument conforming to core.schemas.document.LegalDocument."""
        if metadata is None:
            metadata = self.metadata_extractor.extract(text)

        cleaned_content = text.strip()
        return LegalDocument(
            document_id=metadata.document_id,
            content=cleaned_content,
            metadata=metadata,
        )
