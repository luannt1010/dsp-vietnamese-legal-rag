import { QUERY_MAX_LENGTH } from '../../api/contracts';

// Python len() counts Unicode code points, unlike JavaScript's UTF-16 length.
export const queryLength = (query: string) => Array.from(query.trim()).length;

export function validateQuery(query: string): string | undefined {
  const length = queryLength(query);
  if (!length) return 'Bạn hãy nhập câu hỏi trước khi gửi.';
  if (length > QUERY_MAX_LENGTH)
    return `Câu hỏi tối đa ${QUERY_MAX_LENGTH.toLocaleString('vi-VN')} ký tự.`;
  return undefined;
}
