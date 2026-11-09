import { Database, Layers, FileText, RefreshCw } from 'lucide-react';
import { Dialog } from '../../../components/ui/Dialog';
import { formatNumber } from '../../../lib/format';
import type { useServiceInfo } from '../hooks/useServiceInfo';

interface CorpusDialogProps {
  service: ReturnType<typeof useServiceInfo>;
  onClose: () => void;
}

export function CorpusDialog({ service, onClose }: CorpusDialogProps) {
  const { corpus, state, corpusError, checkedAt, refresh } = service;
  return (
    <Dialog title="Phạm vi dữ liệu" onClose={onClose}>
      <p className="dialog-intro">
        Thông tin về bộ dữ liệu hiện được backend sử dụng để trả lời câu hỏi.
      </p>
      {corpus ? (
        <>
          <div className="corpus-stats">
            <div>
              <FileText size={19} />
              <strong>{formatNumber(corpus.document_count)}</strong>
              <span>Văn bản</span>
            </div>
            <div>
              <Layers size={19} />
              <strong>{formatNumber(corpus.chunk_count)}</strong>
              <span>Đoạn dữ liệu</span>
            </div>
            <div>
              <Database size={19} />
              <strong>{formatNumber(corpus.relation_count)}</strong>
              <span>Quan hệ</span>
            </div>
          </div>
          <h3>Chủ đề trong dữ liệu</h3>
          <div className="topic-tags">
            {corpus.topics.length ? (
              corpus.topics.map((topic) => <span key={topic}>{topic}</span>)
            ) : (
              <p className="muted">Chưa có thông tin chủ đề.</p>
            )}
          </div>
          {!!corpus.subjects.length && (
            <details className="corpus-subjects">
              <summary>Đề mục ({corpus.subjects.length})</summary>
              <ul>
                {corpus.subjects.map((subject) => (
                  <li key={subject}>{subject}</li>
                ))}
              </ul>
            </details>
          )}
          <dl className="metadata-list">
            <div>
              <dt>Snapshot</dt>
              <dd>{corpus.corpus_id}</dd>
            </div>
            <div>
              <dt>Loại nguồn</dt>
              <dd>{corpus.source_type}</dd>
            </div>
            {corpus.dataset && (
              <div>
                <dt>Dataset</dt>
                <dd>{corpus.dataset}</dd>
              </div>
            )}
            {corpus.revision && (
              <div>
                <dt>Revision</dt>
                <dd>{corpus.revision}</dd>
              </div>
            )}
          </dl>
          <p className="callout">
            Dữ liệu phản ánh snapshot đang được phục vụ. Thông tin này không xác nhận hiệu lực hiện
            tại của từng văn bản.
          </p>
        </>
      ) : (
        <div className="corpus-unavailable">
          <Database size={30} />
          <p>
            {state === 'checking'
              ? 'Đang tải thông tin dữ liệu…'
              : corpusError
                ? 'Chưa tải được thông tin dữ liệu.'
                : 'Chưa có thông tin dữ liệu.'}
          </p>
          <span>Kiểm tra API đã chạy, rồi tải lại.</span>
        </div>
      )}
      <div className="dialog-footer">
        <span>
          {checkedAt
            ? `Kiểm tra lúc ${new Date(checkedAt).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`
            : 'Chưa kiểm tra'}
        </span>
        <button
          className="text-button"
          onClick={() => void refresh()}
          disabled={state === 'checking'}
        >
          <RefreshCw size={14} className={state === 'checking' ? 'spin' : ''} />
          Tải lại
        </button>
      </div>
    </Dialog>
  );
}
