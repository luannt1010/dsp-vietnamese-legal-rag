import { MessageSquare, LoaderCircle, AlertCircle, ArrowUpRight } from 'lucide-react';
import type { QuestionEntry } from '../../questions/types';

interface HistoryListProps {
  entries: QuestionEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

export function HistoryList({ entries, activeId, onSelect }: HistoryListProps) {
  return (
    <div className="history-list">
      <div className="sidebar-section-label">
        TRONG PHIÊN NÀY <span>{entries.length.toString().padStart(2, '0')}</span>
      </div>
      {!entries.length && (
        <div className="history-empty">
          <MessageSquare size={19} />
          <p>
            Các câu hỏi của bạn
            <br />
            sẽ xuất hiện ở đây.
          </p>
        </div>
      )}
      {entries.map((entry) => (
        <button
          key={entry.id}
          className={`history-item ${entry.id === activeId ? 'active' : ''}`}
          onClick={() => onSelect(entry.id)}
          aria-current={entry.id === activeId ? 'page' : undefined}
        >
          {entry.state === 'pending' ? (
            <LoaderCircle size={15} className="spin" />
          ) : entry.state === 'error' ? (
            <AlertCircle size={15} />
          ) : (
            <MessageSquare size={15} />
          )}
          <span>{entry.query}</span>
          <ArrowUpRight size={13} className="history-arrow" />
        </button>
      ))}
      <p className="history-note">
        Lịch sử chỉ giữ khi trang đang mở.
        <br />
        Mỗi câu hỏi được xử lý độc lập.
      </p>
    </div>
  );
}
