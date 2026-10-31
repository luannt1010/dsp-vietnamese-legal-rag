import json
from core.schemas.answer import LegalAnswer, LegalCitation

class AnswerFormatter:
    """Formats a :class:`LegalAnswer` into a human‑readable string.

    The formatter concatenates the answer text, renders each citation as a numbered
    footnote, includes the confidence score and optional disclaimer.
    """

    def format(self, answer: LegalAnswer) -> str:
        lines = []
        lines.append(answer.answer)
        lines.append("")
        if answer.citations:
            lines.append("Citations:")
            for i, cit in enumerate(answer.citations, start=1):
                # Include document_number and optional article/clause/point
                base = f"[{i}] {cit.document_id} - {cit.document_number}"
                extra = f"{cit.article or ''}{cit.clause or ''}{cit.point or ''}"
                citation_str = f"{base}{(' ' + extra) if extra else ''}: {cit.quoted_text}"
                if cit.source_url:
                    citation_str += f" (Source: {cit.source_url})"
                lines.append(citation_str)
            lines.append("")
        lines.append(f"Confidence: {answer.confidence:.2f}")
        if answer.disclaimer:
            lines.append("")
            lines.append(f"Disclaimer: {answer.disclaimer}")
        return "\n".join(lines)
