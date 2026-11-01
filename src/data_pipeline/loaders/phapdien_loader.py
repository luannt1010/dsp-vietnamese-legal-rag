"""Phap Dien (MOJ) Dataset Loader and Transformer.

Extracts codified articles from the Ministry of Justice Electronic Legal Codification
(Bộ Pháp Điển - phapdien.moj.gov.vn / Hugging Face dataset tmquan/phapdien-moj-gov-vn)
and transforms them into project-standard LegalDocument, LegalChunk, and Knowledge Graph relations.
"""

import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from core.schemas.document import LegalChunk, LegalDocument, LegalMetadata
from src.data_pipeline import DataPipelineError
from src.data_pipeline.parsers.metadata_extractor import normalize_id, validate_iso_date


class PhapDienLoader:
    """Loads and transforms data from Hugging Face dataset tmquan/phapdien-moj-gov-vn."""

    HF_API_URL = "https://datasets-server.huggingface.co/rows"
    DATASET_NAME = "tmquan/phapdien-moj-gov-vn"

    DOC_NUM_PATTERN = re.compile(
        r"(?:số|Số)\s*([0-9]+/[0-9]{4}/[A-ZĐ0-9\-_/]+|[0-9]+/[A-ZĐ0-9\-_/]+)",
        re.IGNORECASE,
    )
    DOC_TYPE_PATTERN = re.compile(
        r"\b(Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết|Quyết định|Pháp lệnh)\b",
        re.IGNORECASE,
    )
    ISSUED_DATE_PATTERN = re.compile(
        r"(?:ban hành\s+)?ngày\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE
    )
    EFF_DATE_PATTERN = re.compile(
        r"có hiệu lực(?:\s+thi hành)?(?:\s+kể)?(?:\s+từ)?\s+ngày\s+(\d{1,2})/(\d{1,2})/(\d{4})",
        re.IGNORECASE,
    )
    AUTHORITY_PATTERN = re.compile(
        r"của\s+([A-ZÀ-Ỹ\s]+?)(?:,|$|\))", re.IGNORECASE
    )
    RELATED_ART_PATTERN = re.compile(
        r"Điều\s+(\d+(?:\.\d+)*(?:\.[A-ZĐa-z]+(?:\.\d+)*)*)", re.IGNORECASE
    )

    def __init__(self, user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)") -> None:
        self.user_agent = user_agent

    def fetch_rows_via_api(
        self,
        limit: int = 50,
        offset: int = 0,
        config: str = "documents",
        split: str = "train",
    ) -> list[dict]:
        """Fetch raw rows from Hugging Face dataset server REST API."""
        params = {
            "dataset": self.DATASET_NAME,
            "config": config,
            "split": split,
            "offset": str(offset),
            "limit": str(limit),
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{self.HF_API_URL}?{query_string}"

        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = [item["row"] for item in data.get("rows", [])]
                return rows
        except Exception as e:
            raise DataPipelineError(f"Failed to fetch data from Hugging Face API: {e}") from e

    def extract_metadata_from_row(self, row: dict) -> LegalMetadata:
        """Extract structured LegalMetadata from a Phap Dien document row."""
        source_note = row.get("source_note_text", "") or ""
        article_title = row.get("article_title", "") or ""
        subject = row.get("subject_title_vi", "") or ""

        # 1. Document Number
        num_match = self.DOC_NUM_PATTERN.search(source_note)
        if num_match:
            doc_number = num_match.group(1).strip()
        else:
            # Fallback based on subject or row id
            doc_number = f"PD/{row.get('article_id', 'UNKNOWN')}"

        document_id = normalize_id(doc_number)

        # 2. Document Type
        type_match = self.DOC_TYPE_PATTERN.search(source_note)
        doc_type = type_match.group(1).title() if type_match else "Pháp điển"

        # 3. Effective Date (extract first to isolate from issued date)
        effective_date = None
        eff_match = self.EFF_DATE_PATTERN.search(source_note)
        eff_span = None
        if eff_match:
            d, m, y = eff_match.groups()
            effective_date = validate_iso_date(int(y), int(m), int(d))
            eff_span = eff_match.span()

        # 4. Issued Date (exclude effective date span so effective date is not mistaken for issued date)
        text_for_issued = (
            (source_note[: eff_span[0]] + " " + source_note[eff_span[1] :])
            if eff_span
            else source_note
        )
        issued_date = None
        issued_match = self.ISSUED_DATE_PATTERN.search(text_for_issued)
        if issued_match:
            d, m, y = issued_match.groups()
            issued_date = validate_iso_date(int(y), int(m), int(d))

        # 5. Authority
        auth_match = self.AUTHORITY_PATTERN.search(source_note)
        authority = auth_match.group(1).strip().title() if auth_match else "Nhà nước Việt Nam"

        # 6. Title
        title = f"{doc_type} số {doc_number}"
        if subject:
            title += f" về {subject}"

        # 7. Status: do not speculate 'active' simply because dates exist; keep 'unknown'
        return LegalMetadata(
            document_id=document_id,
            title=title,
            document_number=doc_number,
            document_type=doc_type,
            issuing_authority=authority,
            issued_date=issued_date,
            effective_date=effective_date,
            expiry_date=None,
            status="unknown",
            legal_domain=[normalize_id(subject)] if subject else [],
            amended_by=[],
            replaced_by=[],
            repealed_by=[],
            related_documents=[],
        )

    def extract_relations_from_row(self, row: dict) -> list[dict]:
        """Extract relationships from related_note_text and source notes for the Knowledge Graph."""
        relations: list[dict] = []
        source_art_id = row.get("article_id")
        if not source_art_id:
            return relations

        related_note = row.get("related_note_text", "") or ""
        matched_articles = self.RELATED_ART_PATTERN.findall(related_note)
        for target_num in matched_articles:
            target_id = f"Điều {target_num}"
            relations.append({
                "source": source_art_id,
                "target": target_id,
                "type": "RELATED_TO",
                "evidence": related_note[:250],
            })

        return relations

    def transform_row(self, row: dict) -> tuple[LegalDocument, LegalChunk, list[dict]]:
        """Transform a raw Phap Dien row into LegalDocument, LegalChunk, and relation dicts."""
        metadata = self.extract_metadata_from_row(row)
        content_text = row.get("content_text", "") or ""
        article_title = row.get("article_title", "") or ""
        chapter_title = row.get("chapter_title", "") or None
        subject_title = row.get("subject_title_vi", "") or ""
        topic_title = row.get("topic_title_vi", "") or ""
        article_id_raw = row.get("article_id", "art")

        chunk_slug = normalize_id(f"{article_id_raw}")
        chunk_id = f"{metadata.document_id}_{chunk_slug}"

        # Context-enriched content: Prepend hierarchy breadcrumbs so chunk has full standalone semantic context
        breadcrumb_parts = [p for p in [subject_title, topic_title, chapter_title] if p]
        breadcrumb = " > ".join(breadcrumb_parts)
        enriched_content = f"[{breadcrumb}]\n{article_title}\n{content_text}".strip()

        legal_doc = LegalDocument(
            document_id=metadata.document_id,
            content=enriched_content,
            metadata=metadata,
        )

        legal_chunk = LegalChunk(
            chunk_id=chunk_id,
            document_id=metadata.document_id,
            content=enriched_content,
            metadata=metadata,
            chapter=chapter_title,
            article=article_title,
            clause=None,
            point=None,
            parent_id=None,
            embedding=None,
        )

        relations = self.extract_relations_from_row(row)

        return legal_doc, legal_chunk, relations
