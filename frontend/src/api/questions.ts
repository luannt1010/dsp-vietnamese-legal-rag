import { request } from './client';
import { isQuestionResponse } from './contracts';
import type { QuestionRequest } from './types';

export function askQuestion(query: string) {
  const body: QuestionRequest = { query };
  // 502/504 contain the pipeline's public fallback, rather than ErrorResponse.
  return request('/api/v1/questions', isQuestionResponse, {
    method: 'POST',
    body,
    acceptedStatuses: [200, 502, 504],
  });
}
