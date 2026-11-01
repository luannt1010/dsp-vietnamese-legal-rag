"""Legal Metadata Extractor using Vietnamese administrative legal regex patterns."""

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
        # Read the first ~2500 characters which usually contain the official header
        header_text = text[:3000]

        # 1. Document Type
        type_match = self.DOC_TYPE_PATTERN.search(header_text)
        doc_type = type_match.group(1).title() if type_match else "Văn bản"

        # 2. Document Number
        number_match = self.DOC_NUMBER_PATTERN.search(header_text)
        if number_match:
            doc_number = number_match.group(1).strip()
        else:
            # Fallback if "Số: ..." is not explicitly marked
            sub_match = re.search(r"\b([0-9]+/[0-9]{4}/[A-ZĐ0-9\-_]+)\b", header_text)
            doc_number = sub_match.group(1) if sub_match else "UNKNOWN_NUMBER"

        # 3. Document ID (slugified document number or fallback)
        document_id = normalize_id(doc_number) if doc_number != "UNKNOWN_NUMBER" else "doc_unknown"

        # 4. Authority
        authority_match = self.AUTHORITY_PATTERN.search(header_text)
        issuing_authority = authority_match.group(1).title() if authority_match else None

        # 5. Issued Date
        issued_date = None
        issued_match = self.ISSUED_DATE_PATTERN.search(header_text)
        if issued_match:
            d, m, y = issued_match.groups()
            issued_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

        # 6. Effective Date (may be in header or closing provisions)
        effective_date = None
        eff_match = self.EFFECTIVE_DATE_PATTERN.search(text)
        if eff_match:
            d, m, y = eff_match.groups()
            effective_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

        # 7. Document Title
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

        return LegalMetadata(
            document_id=document_id,
            title=title if title else f"Văn bản {doc_number}",
            document_number=doc_number,
            document_type=doc_type,
            issuing_authority=issuing_authority,
            issued_date=issued_date,
            effective_date=effective_date,
            expiry_date=None,
            status="active" if (effective_date or issued_date) else "unknown",
            legal_domain=[],
            amended_by=[],
            replaced_by=[],
            repealed_by=[],
            related_documents=[],
        )
