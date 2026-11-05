"""Explicit legal document references; never infer scope from an LLM rewrite."""

import re
import unicodedata
from collections.abc import Iterable

from src.data_pipeline.parsers.metadata_extractor import normalize_id


_DOCUMENT_NUMBER = re.compile(
    r"(?<![\w/])[0-9]+\s*/\s*(?:[0-9]{4}\s*/\s*)?"
    r"[A-ZĐ][A-ZĐ0-9]*(?:[-/][A-ZĐ0-9]+)*(?![\w/])",
    re.IGNORECASE,
)
_PROVISION_REFERENCE = re.compile(r'(?:điều(?:\s+khoản)?|khoản|mục)\s+[“"\']([^”"\']+)[”"\']', re.IGNORECASE)


def provision_title(article: str) -> str:
    """Remove a displayed article identifier, preserving its actual title."""
    return re.sub(r"^Điều\s+\d+[A-Za-zĐđ]?(?:\.[A-Za-zĐđ0-9]+)*\.?\s*", "", article, flags=re.IGNORECASE).strip()


def extract_provision_titles(query: str) -> list[str]:
    return list(dict.fromkeys(match[1].strip() for match in _PROVISION_REFERENCE.finditer(unicodedata.normalize("NFC", query))))


def names_provision(query: str, article: str, *, allow_question_particles: bool = False) -> bool:
    """Exact title references for filters; question-particle variants for ranking.

    Soft matching only changes context priority, never the hard article filter.
    It handles e.g. "hoạt động gì để bảo đảm ..." vs "Hoạt động bảo đảm ...".
    """
    key = normalize_id(provision_title(article)).casefold()
    query_key = normalize_id(query).casefold()
    if allow_question_particles:
        particles = {"gi", "nao", "nhung", "cac", "de"}
        key = "_".join(word for word in key.split("_") if word not in particles)
        query_key = "_".join(word for word in query_key.split("_") if word not in particles)
    return bool(key and "_" in key and "_" + key + "_" in "_" + query_key + "_")


def document_number_key(number: str) -> str:
    """Compare case/diacritic variants; return original corpus labels in filters."""
    return normalize_id(number).casefold()


def extract_document_numbers(query: str) -> list[str]:
    """Find whole numbers such as 23/2004/QH11, 76/2018/NĐ-CP or 33/CP.

    Requiring a letter in the final component excludes dates and fractions.
    Keep unknown references: silently dropping one could answer from the wrong law.
    """
    result, seen = [], set()
    for match in _DOCUMENT_NUMBER.finditer(unicodedata.normalize("NFC", query)):
        number = re.sub(r"\s+", "", match.group())
        key = document_number_key(number)
        if key not in seen:
            seen.add(key)
            result.append(number)
    return result


def resolve_document_numbers(query: str, vocabulary: Iterable[str] = ()) -> list[str]:
    """Resolve explicit spelling variants to exact indexed labels, without guessing."""
    indexed: dict[str, list[str]] = {}
    for label in vocabulary:
        indexed.setdefault(document_number_key(label), []).append(label)
    return list(dict.fromkeys(
        label
        for number in extract_document_numbers(query)
        for label in indexed.get(document_number_key(number), [number])
    ))
