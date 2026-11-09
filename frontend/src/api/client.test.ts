import { askQuestion } from './questions';
import { getCorpus } from './corpus';
import { ApiError, parseRetryAfter, request } from './client';
import { isCorpusResponse } from './contracts';
import { answer, corpus, fallback, jsonResponse } from '../test/fixtures';

describe('API transport and backend contracts', () => {
  it('sends only the independent query and validates the completed response', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(answer));
    vi.stubGlobal('fetch', fetcher);
    expect(await askQuestion('Câu hỏi')).toEqual(answer);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(
      '/api/v1/questions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ query: 'Câu hỏi' }),
        cache: 'no-store',
        credentials: 'omit',
      }),
    );
  });

  it.each([
    ['failed', 502],
    ['timed_out', 504],
    ['insufficient_evidence', 200],
  ] as const)('preserves the %s pipeline response at HTTP %i', async (status, http) => {
    const response = fallback(status);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(response, http)));
    expect(await askQuestion('Câu hỏi')).toEqual(response);
  });

  it('reads busy errors and Retry-After without automatically retrying', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          request_id: 'busy-request',
          error: { code: 'service_busy', message: 'Hệ thống bận.', issues: [] },
        },
        503,
        { 'Retry-After': '1' },
      ),
    );
    vi.stubGlobal('fetch', fetcher);
    await expect(askQuestion('Câu hỏi')).rejects.toMatchObject({
      kind: 'http',
      status: 503,
      code: 'service_busy',
      requestId: 'busy-request',
      retryAfter: 1,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('preserves validation issues', async () => {
    const issues = [{ location: ['body', 'query'], code: 'missing', message: 'Field required' }];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            request_id: 'invalid',
            error: { code: 'invalid_request', message: 'Không hợp lệ', issues },
          },
          422,
        ),
      ),
    );
    await expect(askQuestion('')).rejects.toMatchObject({ status: 422, issues });
  });

  it.each([
    { ...answer, status: 'invented' },
    { ...answer, answer: { answer: 'Missing confidence' } },
    { ...answer, duration_ms: -1 },
  ])('rejects malformed success instead of rendering it as an answer', async (payload) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(payload, 200, { 'X-Request-ID': 'invalid-response' })),
    );
    await expect(askQuestion('Câu hỏi')).rejects.toMatchObject({
      kind: 'contract',
      requestId: 'invalid-response',
    });
  });

  it('handles non-JSON proxy errors without displaying HTML', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(new Response('<html>private proxy details</html>', { status: 502 })),
    );
    await expect(askQuestion('Câu hỏi')).rejects.toMatchObject({ kind: 'http', status: 502 });
  });

  it('normalizes connection failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(askQuestion('Câu hỏi')).rejects.toBeInstanceOf(ApiError);
    await expect(askQuestion('Câu hỏi')).rejects.toMatchObject({ kind: 'network' });
  });

  it('aborts a request at the client deadline', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_path, options: RequestInit) =>
          new Promise((_resolve, reject) => {
            options.signal?.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            );
          }),
      ),
    );
    await expect(
      request('/api/v1/corpus', isCorpusResponse, { timeoutMs: 5 }),
    ).rejects.toMatchObject({ kind: 'timeout' });
  });

  it('keeps a timeout during body reading distinct from a contract failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_path, options: RequestInit) =>
        Promise.resolve({
          headers: new Headers(),
          status: 200,
          ok: true,
          json: () =>
            new Promise((_resolve, reject) =>
              options.signal?.addEventListener('abort', () =>
                reject(new DOMException('Aborted', 'AbortError')),
              ),
            ),
        }),
      ),
    );
    await expect(
      request('/api/v1/corpus', isCorpusResponse, { timeoutMs: 5 }),
    ).rejects.toMatchObject({ kind: 'timeout' });
  });

  it('loads corpus through the same transport', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(corpus)));
    expect(await getCorpus()).toEqual(corpus);
  });

  it('understands both forms of Retry-After', () => {
    expect(parseRetryAfter('3')).toBe(3);
    expect(parseRetryAfter(new Date(Date.now() + 5000).toUTCString())).toBeGreaterThanOrEqual(4);
    expect(parseRetryAfter('invalid')).toBeUndefined();
    expect(parseRetryAfter(null)).toBeUndefined();
  });
});
