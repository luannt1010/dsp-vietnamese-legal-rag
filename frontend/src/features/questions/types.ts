import type { ApiError } from '../../api/client';
import type { QuestionResponse } from '../../api/types';

interface BaseEntry {
  id: string;
  query: string;
  createdAt: number;
}

export type QuestionEntry = BaseEntry &
  (
    | { state: 'pending' }
    | { state: 'answered'; response: QuestionResponse }
    | { state: 'error'; error: ApiError }
  );
