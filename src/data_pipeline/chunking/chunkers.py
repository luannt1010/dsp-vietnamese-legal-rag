"""Fixed, article-aware and hierarchical chunking with the same token splitter."""

import hashlib
import re
from dataclasses import dataclass, field

from core.config.settings import ChunkingSettings
from core.schemas import LegalChunk, LegalDocument
from src.data_pipeline.parsers.legal_parser import LegalDocumentParser
from src.infrastructure.tokenization import ModelTokenizer


@dataclass
class ChunkingResult:
    chunks: list[LegalChunk] = field(default_factory=list)
    parents: list[LegalChunk] = field(default_factory=list)


class FixedTokenChunker:
    """Token-window baseline. Parent sources are stored but never embedded twice."""

    strategy = "fixed"

    def __init__(self, tokenizer: ModelTokenizer, settings: ChunkingSettings):
        self.tokenizer = tokenizer
        self.settings = settings

    def chunk(self, document: LegalDocument) -> ChunkingResult:
        source = LegalChunk(
            chunk_id=document.document_id + ":document", document_id=document.document_id,
            content=document.content, metadata=document.metadata,
        )
        return self.split_chunk(source)

    def split_chunk(self, source: LegalChunk) -> ChunkingResult:
        source = LegalChunk.model_validate(source.model_dump())
        return ChunkingResult(self._leaves(source, source.content, ""), [source])

    def _leaves(self, parent: LegalChunk, body: str, heading: str) -> list[LegalChunk]:
        prefix = heading.strip() + "\n" if heading.strip() else ""
        budget = self.settings.target_tokens - self.tokenizer.count(prefix)
        if budget <= self.settings.overlap_tokens:
            raise ValueError("legal heading leaves no room for the configured body/overlap")
        while budget > self.settings.overlap_tokens:
            pieces = self.tokenizer.windows(
                body, max_tokens=budget, overlap_tokens=self.settings.overlap_tokens,
            )
            if all(self.tokenizer.count(prefix + piece) <= self.settings.target_tokens for piece in pieces):
                break
            budget -= 1
        else:
            raise ValueError("legal chunk cannot fit the token budget")
        leaves = []
        for index, piece in enumerate(pieces):
            content = (prefix + piece).strip()
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
            leaves.append(LegalChunk.model_validate({
                **parent.model_dump(), "embedding": None,
                "chunk_id": f"{parent.chunk_id}:{self.strategy}:{index}:{digest}",
                "parent_id": parent.chunk_id, "content": content,
            }))
        return leaves


class LegalChunker(FixedTokenChunker):
    """Respect article boundaries; repeat their source heading in long windows."""

    strategy = "legal"

    def chunk(self, document: LegalDocument) -> ChunkingResult:
        structure = LegalDocumentParser().parse_to_structure(document.content, document.metadata)
        if not structure.articles:
            return super().chunk(document)
        result = ChunkingResult()
        for article in structure.articles:
            source = LegalChunk(
                chunk_id=article.article_id, document_id=document.document_id,
                content=article.title + "\n" + article.content,
                metadata=document.metadata, chapter=article.chapter, article=article.title,
            )
            split = self.split_chunk(source)
            result.chunks.extend(split.chunks)
            result.parents.extend(split.parents)
        return result

    def split_chunk(self, source: LegalChunk) -> ChunkingResult:
        source = LegalChunk.model_validate(source.model_dump())
        heading, body = _article_body(source)
        return ChunkingResult(self._leaves(source, body, heading), [source])


class HierarchicalChunker(LegalChunker):
    """Retrieve bounded leaves; retain article/clause parents for context expansion."""

    strategy = "hierarchical"

    def split_chunk(self, source: LegalChunk) -> ChunkingResult:
        source = LegalChunk.model_validate(source.model_dump())
        heading, body = _article_body(source)
        result = ChunkingResult(parents=[source])
        if self.tokenizer.count(source.content) <= self.settings.target_tokens:
            result.chunks.extend(self._leaves(source, body, heading))
            return result
        pattern = re.compile(LegalDocumentParser.CLAUSE_PATTERN.pattern, re.MULTILINE)
        matches = list(pattern.finditer(body))
        numbers = [match.group(1) for match in matches]
        if not matches or len(set(numbers)) != len(numbers):
            # Some codified articles contain several quoted/restarted lists.
            # Their repeated numbers cannot safely identify a legal clause.
            result.chunks.extend(self._leaves(source, body, heading))
            return result
        # Preserve article introductions as evidence rather than discarding text
        # before the first numbered clause.
        if body[:matches[0].start()].strip():
            result.chunks.extend(self._leaves(source, body[:matches[0].start()], heading))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            clause_body = body[match.start():end].strip()
            parent = LegalChunk.model_validate({
                **source.model_dump(), "chunk_id": source.chunk_id + ":clause:" + match.group(1),
                "parent_id": source.chunk_id, "clause": match.group(1),
                "content": (heading + "\n" + clause_body).strip(), "embedding": None,
            })
            result.parents.append(parent)
            point_pattern = re.compile(LegalDocumentParser.POINT_PATTERN.pattern, re.MULTILINE | re.IGNORECASE)
            points = list(point_pattern.finditer(clause_body))
            if len({point.group(1).casefold() for point in points}) != len(points):
                points = []  # Ambiguous nested lists stay inside the clause.
            introduction = clause_body[:points[0].start()].strip() if points else ""
            point_heading = (heading + "\n" + introduction).strip()
            if points and self.tokenizer.count(parent.content) > self.settings.target_tokens and self.tokenizer.count(point_heading) < self.settings.target_tokens - self.settings.overlap_tokens:
                for point_index, point in enumerate(points):
                    point_end = points[point_index + 1].start() if point_index + 1 < len(points) else len(clause_body)
                    location = LegalChunk.model_validate({**parent.model_dump(), "point": point.group(1).casefold()})
                    result.chunks.extend(self._leaves(location, clause_body[point.start():point_end], point_heading))
            else:
                result.chunks.extend(self._leaves(parent, clause_body, heading))
        return result


def _article_body(source: LegalChunk) -> tuple[str, str]:
    """Use the existing article label/breadcrumb verbatim when present."""
    if source.article:
        position = source.content.find(source.article)
        if position >= 0:
            end = source.content.find("\n", position)
            if end >= 0 and source.content[end + 1:].strip():
                return source.content[:end], source.content[end + 1:]
    return "", source.content
