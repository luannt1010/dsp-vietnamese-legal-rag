import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { answer, corpus, fallback, jsonResponse } from '../test/fixtures';

function setup(post: () => Promise<Response> = async () => jsonResponse(answer)) {
  const fetcher = vi.fn(async (input: string, options?: RequestInit) => {
    if (options?.method === 'POST') return post();
    return jsonResponse(input.endsWith('/corpus') ? corpus : { status: 'ready' });
  });
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  return fetcher;
}

async function send(query = 'Câu hỏi kiểm thử') {
  const user = userEvent.setup();
  await user.type(screen.getByRole('textbox', { name: 'Câu hỏi pháp luật' }), query);
  await user.click(screen.getByRole('button', { name: 'Gửi câu hỏi' }));
  return user;
}

it('loads corpus and uses a suggestion as an editable draft without submitting', async () => {
  const fetcher = setup();
  await screen.findByText('Runtime sẵn sàng');
  await userEvent.click(screen.getByRole('button', { name: /Giáo dục.*Người học/ }));
  expect(screen.getByRole('textbox')).toHaveValue(
    'Người học có những quyền gì theo Luật Giáo dục?',
  );
  expect(fetcher.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0);
});

it('renders a completed answer, opens its exact citation, and copies it', async () => {
  setup();
  const user = await send();
  expect(await screen.findByText('câu trả lời kiểm thử')).toBeVisible();
  expect(screen.getByText('Đã kiểm chứng trích dẫn')).toBeVisible();
  expect(screen.getByRole('textbox')).toHaveValue('');
  await user.click(screen.getByRole('button', { name: /Trích dẫn 1:/ }));
  expect(screen.getByRole('region', { name: 'Căn cứ và nguồn tham chiếu' })).toHaveTextContent(
    'Nội dung trích dẫn minh họa.',
  );
  await user.click(screen.getByRole('button', { name: 'Sao chép' }));
  expect(await screen.findByText('Đã sao chép')).toBeVisible();
});

it.each([
  ['insufficient_evidence', 200, 'Chưa đủ căn cứ'],
  ['failed', 502, 'Chưa thể hoàn tất'],
  ['timed_out', 504, 'Hết thời gian xử lý'],
] as const)(
  'shows the %s fallback rather than treating it as a successful legal answer',
  async (status, http, label) => {
    setup(async () => jsonResponse(fallback(status), http));
    await send();
    expect(await screen.findByText(`Thông báo ${status} từ backend.`)).toBeVisible();
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.queryByText('Đã kiểm chứng trích dẫn')).not.toBeInTheDocument();
  },
);

it('keeps a failed query available, exposes request ID, and never retries busy POSTs', async () => {
  const fetcher = setup(async () =>
    jsonResponse(
      {
        request_id: 'request-busy',
        error: { code: 'service_busy', message: 'Đang bận xử lý.', issues: [] },
      },
      503,
      { 'Retry-After': '1' },
    ),
  );
  await send();
  expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang xử lý câu hỏi khác');
  expect(screen.getByRole('textbox')).toHaveValue('Câu hỏi kiểm thử');
  expect(screen.getByText(/request-busy/)).toBeVisible();
  expect(fetcher.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
});

it('keeps inference pending across navigation and blocks duplicate submissions', async () => {
  let resolve!: (value: Response) => void;
  const fetcher = setup(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const user = await send();
  expect(await screen.findByRole('status')).toHaveTextContent('Đang tìm căn cứ');
  const textarea = screen.getByRole('textbox');
  expect(textarea).toBeDisabled();
  fireEvent.keyDown(textarea, { key: 'Enter' });
  await user.click(screen.getByRole('button', { name: /Câu hỏi mới/ }));
  expect(screen.getByRole('heading', { name: /Hiểu đúng luật/ })).toBeVisible();
  await act(async () => resolve(jsonResponse(answer)));
  expect(screen.getByRole('heading', { name: /Hiểu đúng luật/ })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Câu hỏi kiểm thử' }));
  expect(await screen.findByText('câu trả lời kiểm thử')).toBeVisible();
  expect(fetcher.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
});

it('shows the actual corpus metadata and refresh control', async () => {
  setup();
  await screen.findByText('Runtime sẵn sàng');
  await userEvent.click(screen.getByRole('button', { name: 'Thông tin dữ liệu' }));
  const dialog = screen.getByRole('dialog', { name: 'Phạm vi dữ liệu' });
  expect(within(dialog).getByText('snapshot-test')).toBeVisible();
  expect(within(dialog).getByText('Giáo dục, đào tạo')).toBeVisible();
  await userEvent.click(within(dialog).getByRole('button', { name: 'Đóng' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('keeps the UI usable if the backend is offline', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
  render(<App />);
  await screen.findByText('Chưa kết nối API');
  await send();
  expect(await screen.findByRole('alert')).toHaveTextContent('Không kết nối được');
  expect(screen.getByRole('textbox')).toHaveValue('Câu hỏi kiểm thử');
});

it('uses a modal source viewer at compact breakpoints', async () => {
  vi.mocked(window.matchMedia).mockReturnValueOnce({
    matches: true,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as MediaQueryList);
  setup();
  const user = await send();
  await screen.findByText('câu trả lời kiểm thử');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Trích dẫn 1:/ }));
  expect(screen.getByRole('dialog', { name: 'Nguồn tham chiếu' })).toBeVisible();
});

it('rejects oversized drafts and supports Shift+Enter without submitting', async () => {
  const fetcher = setup();
  const textbox = screen.getByRole('textbox');
  fireEvent.change(textbox, { target: { value: 'a'.repeat(4001) } });
  expect(screen.getByRole('alert')).toHaveTextContent('4.000');
  expect(screen.getByRole('button', { name: 'Gửi câu hỏi' })).toBeDisabled();
  fireEvent.change(textbox, { target: { value: 'Câu hỏi hợp lệ' } });
  fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: true });
  expect(fetcher.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0);
  fireEvent.keyDown(textbox, { key: 'Enter' });
  await waitFor(() => expect(screen.getByText('câu trả lời kiểm thử')).toBeVisible());
});

it('does not persist questions when the page is remounted', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, options?: RequestInit) =>
      jsonResponse(
        options?.method === 'POST'
          ? answer
          : input.endsWith('/corpus')
            ? corpus
            : { status: 'ready' },
      ),
    ),
  );
  const view = render(<App />);
  await send();
  await screen.findByText('câu trả lời kiểm thử');
  view.unmount();
  render(<App />);
  expect(screen.queryByText('Câu hỏi kiểm thử')).not.toBeInTheDocument();
});
