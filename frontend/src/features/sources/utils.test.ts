import { citationLocation, sourcesForCitation, sourceUrl } from './utils';
import { safeExternalUrl } from '../../lib/format';
import { citation, source } from '../../test/fixtures';

describe('citation/source association', () => {
  it('finds the exact quotation and metadata returned by the backend', () => {
    expect(sourcesForCitation(citation, [source])).toEqual([source]);
  });
  it('does not match a quotation from a different document', () => {
    expect(sourcesForCitation(citation, [{ ...source, document_id: 'other-document' }])).toEqual(
      [],
    );
  });
  it('does not guess source matches when the quotation differs', () => {
    expect(
      sourcesForCitation({ ...citation, quoted_text: 'Another quotation' }, [
        { ...source, metadata: { article: 'Điều 1' } },
      ]),
    ).toEqual([]);
  });
  it('does not associate unrelated chunks merely because document IDs match', () => {
    expect(
      sourcesForCitation(citation, [
        { ...source, content: 'Nội dung khác', metadata: { article: '2' } },
      ]),
    ).toEqual([]);
  });
  it('requires all specified citation fields to match the same source', () => {
    expect(
      sourcesForCitation({ ...citation, clause: '2', quoted_text: 'Another quotation' }, [source]),
    ).toEqual([]);
  });
  it('formats legal locations without inventing missing fields', () => {
    expect(citationLocation({ ...citation, clause: '2', point: 'a' })).toBe(
      'Điều 1 · Khoản 2 · Điểm a',
    );
  });
  it('does not duplicate legal location labels supplied by the API', () => {
    expect(citationLocation({ ...citation, article: 'Điều 1', clause: 'khoản 2' })).toBe(
      'Điều 1 · khoản 2',
    );
  });
  it('rejects conflicting document numbers even if the quote matches', () => {
    expect(
      sourcesForCitation(citation, [
        { ...source, metadata: { ...source.metadata, document_number: 'OTHER' } },
      ]),
    ).toEqual([]);
  });
  it.each([
    'javascript:alert(1)',
    'data:text/html,unsafe',
    '/local/path',
    'https://user:secret@example.com',
  ])('blocks unsafe source URL %s', (url) => {
    expect(safeExternalUrl(url)).toBeUndefined();
    expect(sourceUrl({ ...source, metadata: { source_url: url } })).toBeUndefined();
  });
});
