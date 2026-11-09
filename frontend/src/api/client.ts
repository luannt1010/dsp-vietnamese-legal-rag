import type { ValidateFunction } from 'ajv';
import type { paths } from './generated/schema';
import type { ErrorResponse } from './types';
import { isErrorResponse } from './contracts';

type ErrorKind = 'network' | 'timeout' | 'http' | 'contract';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: ErrorKind,
    public readonly status?: number,
    public readonly requestId?: string,
    public readonly code?: string,
    public readonly retryAfter?: number,
    public readonly issues?: ErrorResponse['error']['issues'],
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const configuredTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS || 300000);
const apiTimeout =
  Number.isFinite(configuredTimeout) && configuredTimeout > 0 ? configuredTimeout : 300000;
const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds);
  const date = Date.parse(value);
  return Number.isFinite(date) ? Math.max(0, Math.ceil((date - Date.now()) / 1000)) : undefined;
}

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  timeoutMs?: number;
  acceptedStatuses?: number[];
}

// One transport owns deadlines, error envelopes, contract checks, and request IDs.
// POST is deliberately never retried: the backend has no idempotency cache.
export async function request<T>(
  path: keyof paths,
  validate: ValidateFunction<T>,
  { method = 'GET', body, timeoutMs = apiTimeout, acceptedStatuses = [200] }: RequestOptions = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: 'no-store',
      credentials: 'omit',
    });
    const requestId = response.headers.get('X-Request-ID') || undefined;
    const retryAfter = parseRetryAfter(response.headers.get('Retry-After'));
    const payload: unknown = await response.json().catch((error: unknown) => {
      if (controller.signal.aborted) throw error;
      return null;
    });

    if (acceptedStatuses.includes(response.status) && validate(payload)) return payload;

    if (isErrorResponse(payload)) {
      throw new ApiError(
        payload.error.message,
        'http',
        response.status,
        payload.request_id,
        payload.error.code,
        retryAfter,
        payload.error.issues,
      );
    }
    if (!response.ok) {
      throw new ApiError(
        'Dịch vụ chưa trả được kết quả. Bạn có thể thử lại sau.',
        'http',
        response.status,
        requestId,
        undefined,
        retryAfter,
      );
    }
    throw new ApiError(
      'Dữ liệu phản hồi chưa đúng định dạng API. Vui lòng kiểm tra phiên bản dịch vụ.',
      'contract',
      response.status,
      requestId,
    );
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      throw new ApiError(
        'Đã hết thời gian chờ trên trình duyệt. Câu hỏi có thể vẫn đang được xử lý ở máy chủ.',
        'timeout',
      );
    }
    throw new ApiError(
      'Không kết nối được với dịch vụ. Câu hỏi của bạn vẫn được giữ lại để gửi lại.',
      'network',
    );
  } finally {
    window.clearTimeout(timeout);
  }
}
