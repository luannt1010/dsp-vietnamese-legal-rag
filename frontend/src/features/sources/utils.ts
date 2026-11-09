import type { LegalCitation, RetrievedChunk } from '../../api/types';
import { safeExternalUrl } from '../../lib/format';

export function metadataText(source: RetrievedChunk, key: string): string | undefined {
  const value = source.metadata?.[key];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export function citationLocation(citation: LegalCitation) {
  return [
    legalLocation('Điều', citation.article),
    legalLocation('Khoản', citation.clause),
    legalLocation('Điểm', citation.point),
  ]
    .filter(Boolean)
    .join(' · ');
}

export function legalLocation(label: string, value?: string | null) {
  if (!value) return undefined;
  return value.toLocaleLowerCase('vi').startsWith(`${label.toLocaleLowerCase('vi')} `)
    ? value
    : `${label} ${value}`;
}

// This only locates a retained chunk for display. Verification stays in the backend.
// Match its public citation fields and exact quotation; document/location alone
// cannot identify which retained chunk was cited.
export function sourcesForCitation(citation: LegalCitation, sources: RetrievedChunk[]) {
  return sources.filter(
    (source) =>
      source.document_id === citation.document_id &&
      source.metadata?.document_number === citation.document_number &&
      source.content.includes(citation.quoted_text) &&
      (['article', 'clause', 'point', 'source_url'] as const).every(
        (field) => citation[field] == null || source.metadata?.[field] === citation[field],
      ),
  );
}

export function sourceTitle(source: RetrievedChunk) {
  return (
    metadataText(source, 'document_name') ||
    metadataText(source, 'title') ||
    metadataText(source, 'document_number') ||
    source.document_id
  );
}

export function sourceUrl(source: RetrievedChunk) {
  return safeExternalUrl(metadataText(source, 'source_url'));
}
