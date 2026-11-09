import { lazy, Suspense, useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  Clock3,
  Copy,
  LoaderCircle,
  PencilLine,
  Scale,
} from 'lucide-react';
import { formatDuration } from '../../../lib/format';
import { citationLocation } from '../../sources/utils';
import type { QuestionEntry } from '../types';

const Markdown = lazy(() =>
  import('../../../components/ui/Markdown').then((module) => ({ default: module.Markdown })),
);

interface QuestionResultProps {
  entry: QuestionEntry;
  onNewQuestion: () => void;
  onEdit: (query: string) => void;
  onCitation: (index: number) => void;
  onSources: () => void;
}

const outcomeLabels = {
  completed: 'Đã kiểm chứng trích dẫn',
  insufficient_evidence: 'Chưa đủ căn cứ',
  failed: 'Chưa thể hoàn tất',
  timed_out: 'Hết thời gian xử lý',
} as const;

function PendingAnswer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(Date.now() - startedAt);
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return (
    <div className="pending-answer" role="status">
      <div className="pending-orbit">
        <Scale size={24} />
        <LoaderCircle size={48} className="spin" />
      </div>
      <h2>Đang tìm căn cứ cho câu hỏi của bạn</h2>
      <p>Kết quả sẽ xuất hiện sau khi hệ thống hoàn tất kiểm chứng trích dẫn.</p>
      <span className="pending-time">
        <Clock3 size={14} />
        Đã chờ {formatDuration(elapsed)}
      </span>
      {elapsed >= 30000 && (
        <p className="pending-detail">
          Quá trình có thể mất vài phút tùy câu hỏi và cấu hình máy chủ. Bạn có thể xem lại các câu
          hỏi khác trong lúc chờ.
        </p>
      )}
    </div>
  );
}

export function QuestionResult({
  entry,
  onNewQuestion,
  onEdit,
  onCitation,
  onSources,
}: QuestionResultProps) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');
  useEffect(() => {
    if (copyState === 'idle') return;
    const timer = window.setTimeout(() => setCopyState('idle'), 3000);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  async function copyAnswer() {
    if (entry.state !== 'answered') return;
    const { answer } = entry.response;
    const citations = (answer.citations || []).map(
      (citation, index) =>
        `[${index + 1}] ${citation.document_number} · ${citationLocation(citation)}\n${citation.quoted_text}`,
    );
    try {
      await navigator.clipboard.writeText(
        [answer.answer, ...citations, answer.disclaimer].filter(Boolean).join('\n\n'),
      );
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
  }

  return (
    <article className="question-result">
      <button className="back-button" onClick={onNewQuestion}>
        <ArrowLeft size={15} />
        Không gian tra cứu
      </button>
      <p className="eyebrow question-eyebrow">CÂU HỎI CỦA BẠN</p>
      <h1 className="question-title">{entry.query}</h1>
      <div className="question-rule" />
      {entry.state === 'pending' && <PendingAnswer startedAt={entry.createdAt} />}
      {entry.state === 'error' && (
        <div className="error-card" role="alert">
          <AlertCircle size={24} />
          <div>
            <h2>
              {entry.error.code === 'service_busy'
                ? 'Hệ thống đang xử lý câu hỏi khác'
                : entry.error.code === 'service_not_ready'
                  ? 'Dịch vụ chưa sẵn sàng'
                  : 'Chưa nhận được câu trả lời'}
            </h2>
            <p>{entry.error.message}</p>
            {entry.error.retryAfter !== undefined && (
              <p className="small">
                Máy chủ đề nghị chờ ít nhất {entry.error.retryAfter} giây trước khi thử lại.
              </p>
            )}
            {!!entry.error.issues?.length && (
              <ul className="validation-issues">
                {entry.error.issues.map((issue, index) => (
                  <li key={index}>
                    {issue.location.join('.')} — {issue.message}
                  </li>
                ))}
              </ul>
            )}
            <button className="text-button" onClick={() => onEdit(entry.query)}>
              <PencilLine size={14} />
              Xem lại câu hỏi
            </button>
            {entry.error.requestId && (
              <p className="request-id">Mã yêu cầu: {entry.error.requestId}</p>
            )}
          </div>
        </div>
      )}
      {entry.state === 'answered' && (
        <>
          <div className="answer-heading">
            <div className="answer-author">
              <span>
                <Scale size={18} />
              </span>
              <strong>Pháp điển</strong>
              <span className="answer-author-label">TRỢ LÝ PHÁP LUẬT</span>
            </div>
            <span
              className={`outcome-badge ${entry.response.status === 'completed' ? 'verified' : 'fallback'}`}
            >
              {entry.response.status === 'completed' ? (
                <CheckCheck size={13} />
              ) : (
                <AlertCircle size={13} />
              )}
              {outcomeLabels[entry.response.status]}
            </span>
          </div>
          <Suspense fallback={<p className="plain-answer">{entry.response.answer.answer}</p>}>
            <Markdown>{entry.response.answer.answer}</Markdown>
          </Suspense>
          {!!entry.response.answer.citations?.length && (
            <section className="answer-citations" aria-label="Trích dẫn pháp luật">
              <div className="citations-label">
                <BookOpen size={15} />
                <span>CĂN CỨ PHÁP LUẬT</span>
                <i>{entry.response.answer.citations.length}</i>
              </div>
              <div className="citation-cards">
                {entry.response.answer.citations.map((citation, index) => (
                  <button
                    className="citation-card"
                    key={`${citation.document_id}-${index}`}
                    onClick={() => onCitation(index)}
                    aria-label={`Trích dẫn ${index + 1}: Văn bản ${citation.document_number}, ${citationLocation(citation) || 'xem đoạn trích'}`}
                  >
                    <span className="citation-index">{index + 1}</span>
                    <span>
                      <strong>{citation.document_number}</strong>
                      <small>{citationLocation(citation) || 'Xem đoạn trích dẫn'}</small>
                    </span>
                    <ArrowUpRight size={16} />
                  </button>
                ))}
              </div>
            </section>
          )}
          {entry.response.answer.disclaimer && (
            <p className="answer-disclaimer">
              <AlertCircle size={15} />
              <span>{entry.response.answer.disclaimer}</span>
            </p>
          )}
          <div className="answer-actions">
            <div>
              <button className="text-button" onClick={() => void copyAnswer()}>
                {copyState === 'copied' ? <Check size={15} /> : <Copy size={15} />}
                {copyState === 'copied' ? 'Đã sao chép' : 'Sao chép'}
              </button>
              <button className="text-button" onClick={onSources}>
                <BookOpen size={15} />
                Xem nguồn ({entry.response.sources?.length || 0})
              </button>
            </div>
            <span>
              {formatDuration(entry.response.duration_ms)} · {entry.response.rounds} vòng xử lý
            </span>
          </div>
          <p className="copy-feedback" role="status">
            {copyState === 'failed'
              ? 'Trình duyệt chưa cho phép sao chép. Bạn có thể chọn và sao chép nội dung trực tiếp.'
              : ''}
          </p>
          {['failed', 'timed_out'].includes(entry.response.status) && (
            <button className="text-button" onClick={() => onEdit(entry.query)}>
              <PencilLine size={15} />
              Xem lại câu hỏi để gửi lại
            </button>
          )}
          <details className="result-details">
            <summary>Thông tin yêu cầu</summary>
            <dl className="metadata-list">
              <div>
                <dt>Mã yêu cầu</dt>
                <dd>{entry.response.request_id}</dd>
              </div>
              <div>
                <dt>Snapshot</dt>
                <dd>{entry.response.corpus_id}</dd>
              </div>
              {entry.response.failure && (
                <div>
                  <dt>Mã xử lý</dt>
                  <dd>{entry.response.failure.code}</dd>
                </div>
              )}
            </dl>
          </details>
        </>
      )}
    </article>
  );
}
