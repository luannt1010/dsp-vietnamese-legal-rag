// Optional browser QA service, never enabled by the application or used as fallback.
// Shares the unit-test fixtures. Node >=22.18 supports erasing their TS annotations.
import { createServer } from 'node:http';
import { answer, corpus, fallback } from '../src/test/fixtures.ts';

const port = 8010;
const server = createServer(async (request, response) => {
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.setHeader('Cache-Control', 'no-store');
  response.setHeader('X-Request-ID', 'browser-fixture');

  if (request.method === 'GET' && request.url === '/health/ready') {
    response.end(JSON.stringify({ status: 'ready' }));
    return;
  }
  if (request.method === 'GET' && request.url === '/api/v1/corpus') {
    response.end(JSON.stringify(corpus));
    return;
  }
  if (request.method === 'POST' && request.url === '/api/v1/questions') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    let body;
    try {
      body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } catch {
      response.writeHead(400);
      response.end('{}');
      return;
    }
    const query = String(body.query || '').toLocaleLowerCase('vi');
    if (query.includes('busy')) {
      response.writeHead(503, { 'Retry-After': '1' });
      response.end(
        JSON.stringify({
          request_id: 'browser-fixture',
          error: {
            code: 'service_busy',
            message: 'Thông báo bận từ fixture kiểm thử.',
            issues: [],
          },
        }),
      );
      return;
    }
    const outcome = query.includes('timeout')
      ? 'timed_out'
      : query.includes('failed')
        ? 'failed'
        : query.includes('thiếu căn cứ')
          ? 'insufficient_evidence'
          : undefined;
    response.statusCode = outcome === 'timed_out' ? 504 : outcome === 'failed' ? 502 : 200;
    const result = outcome ? fallback(outcome) : answer;
    response.end(
      JSON.stringify({
        ...result,
        answer: {
          ...result.answer,
          answer: `**Dữ liệu kiểm thử giao diện.**\n\n${result.answer.answer}\n\nNội dung này chỉ dùng để kiểm tra kết nối HTTP và cách hiển thị trích dẫn.`,
        },
      }),
    );
    return;
  }
  response.statusCode = 404;
  response.end('{}');
});

server.listen(port, '127.0.0.1', () =>
  console.log(`Fixture API (synthetic data only): http://127.0.0.1:${port}`),
);
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => server.close(() => process.exit(0)));
