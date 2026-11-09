import { request } from './client';
import { isHealthResponse } from './contracts';

export const getReadiness = () => request('/health/ready', isHealthResponse, { timeoutMs: 10000 });
