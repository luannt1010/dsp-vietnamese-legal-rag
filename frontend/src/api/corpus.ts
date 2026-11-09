import { request } from './client';
import { isCorpusResponse } from './contracts';

export const getCorpus = () => request('/api/v1/corpus', isCorpusResponse, { timeoutMs: 10000 });
