import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowUp, LoaderCircle, CornerDownLeft } from 'lucide-react';
import { QUERY_MAX_LENGTH } from '../../../api/contracts';
import { queryLength, validateQuery } from '../validation';

interface QuestionComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  isSending: boolean;
  onSubmit: (query: string) => void;
  focusToken: number;
}

export function QuestionComposer({
  draft,
  onDraftChange,
  isSending,
  onSubmit,
  focusToken,
}: QuestionComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [error, setError] = useState<string>();
  const length = queryLength(draft);
  useEffect(() => {
    const textarea = ref.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
    }
  }, [draft]);
  useEffect(() => {
    if (focusToken > 0) ref.current?.focus();
  }, [focusToken]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const validation = validateQuery(draft);
    setError(validation);
    if (!validation && !isSending) onSubmit(draft);
  }

  return (
    <div className="composer-area">
      <form
        className={`composer ${error ? 'composer-invalid' : ''}`}
        onSubmit={submit}
        aria-label="Gửi câu hỏi pháp luật"
      >
        <label className="sr-only" htmlFor="question">
          Câu hỏi pháp luật
        </label>
        <textarea
          id="question"
          ref={ref}
          value={draft}
          rows={1}
          placeholder="Bạn muốn tìm hiểu quy định pháp luật nào?"
          disabled={isSending}
          aria-describedby="composer-note composer-error"
          aria-invalid={!!error}
          onChange={(event) => {
            const value = event.target.value;
            onDraftChange(value);
            setError(queryLength(value) > QUERY_MAX_LENGTH ? validateQuery(value) : undefined);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-bottom">
          <span className="composer-hint">
            <CornerDownLeft size={13} />
            Enter để gửi <span>· Shift + Enter xuống dòng</span>
          </span>
          <div>
            <span className={`character-count ${length > QUERY_MAX_LENGTH ? 'over-limit' : ''}`}>
              {length.toLocaleString('vi-VN')} / {QUERY_MAX_LENGTH.toLocaleString('vi-VN')}
            </span>
            <button
              className="send-button"
              type="submit"
              aria-label="Gửi câu hỏi"
              disabled={isSending || !draft.trim() || length > QUERY_MAX_LENGTH}
            >
              {isSending ? <LoaderCircle size={20} className="spin" /> : <ArrowUp size={21} />}
            </button>
          </div>
        </div>
      </form>
      <p className="composer-error" id="composer-error" role={error ? 'alert' : undefined}>
        {error}
      </p>
      <p className="composer-note" id="composer-note">
        Mỗi câu hỏi được xử lý độc lập. Hãy đối chiếu văn bản gốc trước khi áp dụng.
      </p>
    </div>
  );
}
