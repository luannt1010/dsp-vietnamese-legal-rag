import type { CorpusResponse, LegalCitation, QuestionResponse, RetrievedChunk } from '../api/types';

// Synthetic contract fixtures. These are not legal conclusions or production data.
export const citation: LegalCitation = {
  document_id: 'document-test',
  document_number: 'TEST/2026',
  article: '1',
  clause: null,
  point: null,
  quoted_text: 'Nội dung trích dẫn minh họa.',
  source_url: 'https://example.com/document',
};
export const source: RetrievedChunk = {
  chunk_id: 'chunk-1',
  document_id: citation.document_id,
  score: 0.8,
  retrieval_method: 'hybrid',
  content: 'Điều 1. Nội dung trích dẫn minh họa. Phần còn lại của đoạn nguồn.',
  metadata: {
    title: 'Văn bản kiểm thử',
    document_number: 'TEST/2026',
    article: '1',
    source_url: citation.source_url,
  },
};
export const answer: QuestionResponse = {
  request_id: 'request-test',
  status: 'completed',
  answer: {
    answer: 'Đây là **câu trả lời kiểm thử** có căn cứ.',
    citations: [citation],
    confidence: 0.8,
    disclaimer: 'Nội dung kiểm thử giao diện.',
  },
  sources: [source],
  corpus_id: 'snapshot-test',
  rounds: 1,
  duration_ms: 1234,
  failure: null,
};
export const corpus: CorpusResponse = {
  corpus_id: 'snapshot-test',
  source_type: 'json',
  dataset: null,
  revision: null,
  topics: ['Giáo dục, đào tạo'],
  subjects: [],
  document_count: 15,
  chunk_count: 100,
  parent_chunk_count: 10,
  relation_count: 4,
  unresolved_reference_count: 0,
};

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

export function fallback(
  status: 'failed' | 'timed_out' | 'insufficient_evidence',
): QuestionResponse {
  return {
    ...answer,
    status,
    answer: {
      answer: `Thông báo ${status} từ backend.`,
      citations: [],
      confidence: 0,
      disclaimer: null,
    },
    sources: [],
    failure:
      status === 'insufficient_evidence' ? null : { code: 'test_failure', stage: 'generation' },
  };
}
