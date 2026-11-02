
from core.schemas.answer import LegalAnswer, LegalCitation


class AnswerFormatter:
    """Formats a LegalAnswer into a human-readable string."""

    def format(self, answer: LegalAnswer) -> str:
        lines = []
        lines.append(answer.answer)
        lines.append("")

        if answer.citations:
            lines.append("Citations:")

            for i, cit in enumerate(answer.citations, start=1):
                base = f"[{i}] {cit.document_id} - {cit.document_number}"

                parts = []

                if cit.article:
                    parts.append(f"Điều {cit.article}")

                if cit.clause:
                    parts.append(f"khoản {cit.clause}")

                if cit.point:
                    parts.append(f"điểm {cit.point}")

                extra = ", ".join(parts)

                citation_str = (
                    f"{base}{(' ' + extra) if extra else ''}: {cit.quoted_text}"
                )

                if cit.source_url:
                    citation_str += f" (Source: {cit.source_url})"

                lines.append(citation_str)

            lines.append("")

        lines.append(f"Confidence: {answer.confidence:.2f}")

        if answer.disclaimer:
            lines.append("")
            lines.append(f"Disclaimer: {answer.disclaimer}")

        return "\n".join(lines)
