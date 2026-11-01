"""Legal Metadata Extractor using Vietnamese administrative legal regex patterns."""

import datetime
import hashlib
import re
import unicodedata
from core.schemas.document import LegalMetadata


def normalize_id(text: str) -> str:
    """Normalize document number or string to a slug-like safe ID."""
    # Decompose unicode to remove diacritics
    nfkd = unicodedata.normalize("NFKD", text)
    no_diacritics = "".join(c for c in nfkd if not unicodedata.combining(c))
    no_diacritics = no_diacritics.replace("đ", "d").replace("Đ", "D")
    # Replace non-alphanumeric with underscore
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", no_diacritics).strip("_")
    return slug


def validate_iso_date(y: int, m: int, d: int) -> str | None:
    """Validate calendar date and return ISO YYYY-MM-DD or None if invalid."""
    try:
        dt = datetime.date(y, m, d)
        if 1945 <= dt.year <= 2100:
            return dt.isoformat()
        return None
    except (ValueError, OverflowError):
        return None


class LegalMetadataExtractor:
    """Extracts administrative legal metadata from raw document header text."""

    AUTHORITY_PATTERN = re.compile(
        r"(QUỐC HỘI|ỦY BAN THƯỜNG VỤ QUỐC HỘI|CHÍNH PHỦ|THỦ TƯỚNG CHÍNH PHỦ|"
        r"BỘ\s+[A-ZÀ-Ỹ\s]+|TÒA ÁN NHÂN DÂN TỐI CAO|VIỆN KIỂM SÁT NHÂN DÂN TỐI CAO|"
        r"ỦY BAN NHÂN DÂN\s+[A-ZÀ-Ỹ\s]+)",
        re.IGNORECASE,
    )

    DOC_NUMBER_PATTERN = re.compile(
        r"(?:Số|Số:)\s*([0-9]+/[0-9]{4}/[A-ZĐ0-9\-_/]+|[0-9]+/[A-ZĐ0-9\-_/]+)",
        re.IGNORECASE,
    )

    DOC_TYPE_PATTERN = re.compile(
        r"\b(BỘ LUẬT|LUẬT|NGHỊ ĐỊNH|THÔNG TƯ LIÊN TỊCH|THÔNG TƯ|NGHỊ QUYẾT|QUYẾT ĐỊNH|PHÁP LỆNH|CHỈ THỊ)\b",
        re.IGNORECASE,
    )

    ISSUED_DATE_PATTERN = re.compile(
        r"(?:ngày|ngày:)\s*(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        re.IGNORECASE,
    )

    EFFECTIVE_DATE_PATTERN = re.compile(
        r"(?:có hiệu lực|hiệu lực thi hành|áp dụng)(?:\s+kể)?(?:\s+từ)?\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        re.IGNORECASE,
    )

    def extract(self, text: str, fallback_title: str | None = None) -> LegalMetadata:
        """Extract metadata from the text content.

        Args:
            text: Full text or header text of the document.
            fallback_title: Optional fallback title if regex matching fails.

        Returns:
            LegalMetadata object conforming to project schema.
        """
        # Read the first ~3000 characters which usually contain the official header
        header_text = text[:3000]

        # 1. Document Type
        type_match = self.DOC_TYPE_PATTERN.search(header_text)
        doc_type = type_match.group(1).title() if type_match else "Văn bản"

        # 2. Document Number
        number_match = self.DOC_NUMBER_PATTERN.search(header_text)
        if number_match:
            doc_number = number_match.group(1).strip()
            document_id = normalize_id(doc_number)
        else:
            # Fallback if "Số: ..." is not explicitly marked
            sub_match = re.search(r"\b([0-9]+/[0-9]{4}/[A-ZĐ0-9\-_]+)\b", header_text)
            if sub_match:
                doc_number = sub_match.group(1)
                document_id = normalize_id(doc_number)
            else:
                # Generate deterministic, distinct ID based on content to prevent collisions across different unnumbered docs
                content_sample = (fallback_title or "") + "\n" + text[:1000]
                digest = hashlib.sha256(content_sample.encode("utf-8")).hexdigest()[:10]
                document_id = f"doc_unknown_{digest}"
                doc_number = f"UNKNOWN_{digest}"

        # 3. Authority
        authority_match = self.AUTHORITY_PATTERN.search(header_text)
        issuing_authority = authority_match.group(1).title() if authority_match else None

        # 4. Effective Date (search full text as it often appears in closing provisions)
        effective_date = None
        eff_match = self.EFFECTIVE_DATE_PATTERN.search(text)
        eff_span_header = None
        if eff_match:
            d, m, y = eff_match.groups()
            effective_date = validate_iso_date(int(y), int(m), int(d))
            # If the effective date appeared in the header, record its span to exclude from issued date search
            eff_header_match = self.EFFECTIVE_DATE_PATTERN.search(header_text)
            if eff_header_match:
                eff_span_header = eff_header_match.span()

        # 5. Issued Date (exclude effective date span so effective date is not mistaken for issued date)
        text_for_issued = (
            (header_text[: eff_span_header[0]] + " " + header_text[eff_span_header[1] :])
            if eff_span_header
            else header_text
        )
        issued_date = None
        issued_match = self.ISSUED_DATE_PATTERN.search(text_for_issued)
        if issued_match:
            d, m, y = issued_match.groups()
            issued_date = validate_iso_date(int(y), int(m), int(d))

        # 6. Document Title
        title = fallback_title or ""
        if not title:
            # Search for title right after document type
            title_match = re.search(
                rf"{re.escape(doc_type)}[\s\n:]+([^\n]+(?:\n[^\n]+){{0,2}})",
                header_text,
                re.IGNORECASE,
            )
            if title_match:
                title = " ".join(title_match.group(1).split()).strip()
            else:
                title = f"{doc_type} {doc_number}"

        # Clean title of common uppercase boilerplate
        title = re.sub(r"^(CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM|Độc lập - Tự do - Hạnh phúc)\s*", "", title).strip()

        # 7. Status: do not guess 'active' merely because a date exists; keep 'unknown' without verified authority
        return LegalMetadata(
            document_id=document_id,
            title=title if title else f"Văn bản {doc_number}",
            document_number=doc_number,
            document_type=doc_type,
            issuing_authority=issuing_authority,
            issued_date=issued_date,
            effective_date=effective_date,
            expiry_date=None,
            status="unknown",
            legal_domain=[],
            amended_by=[],
            replaced_by=[],
            repealed_by=[],
            related_documents=[],
        )
