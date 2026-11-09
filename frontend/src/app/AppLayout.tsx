import type { ReactNode } from 'react';
import {
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  Database,
  Info,
  Menu,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { Brand } from '../components/ui/Brand';
import type { useServiceInfo } from '../features/corpus/hooks/useServiceInfo';
import { formatNumber } from '../lib/format';

interface AppLayoutProps {
  service: ReturnType<typeof useServiceInfo>;
  history: ReactNode;
  children: ReactNode;
  onNewQuestion: () => void;
  onOpenCorpus: () => void;
  onOpenHelp: () => void;
  onOpenNavigation: () => void;
}

export function AppLayout({
  service,
  history,
  children,
  onNewQuestion,
  onOpenCorpus,
  onOpenHelp,
  onOpenNavigation,
}: AppLayoutProps) {
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Đến nội dung chính
      </a>
      <aside className="sidebar" aria-label="Điều hướng chính">
        <Brand />
        <button className="new-question-button" onClick={onNewQuestion}>
          <Plus size={18} />
          Câu hỏi mới<span>↗</span>
        </button>
        <div className="sidebar-nav">
          <span>
            <BookOpen size={17} />
            Hỏi đáp pháp luật
          </span>
          <span className="nav-active-dot" />
        </div>
        {history}
        <div className="sidebar-bottom">
          <button className="corpus-sidebar-card" onClick={onOpenCorpus}>
            <span className="corpus-sidebar-icon">
              <Database size={17} />
            </span>
            <span>
              <strong>Kho dữ liệu pháp luật</strong>
              <small>
                {service.corpus
                  ? `${formatNumber(service.corpus.document_count)} văn bản trong snapshot`
                  : 'Xem phạm vi dữ liệu'}
              </small>
            </span>
            <ArrowUpRight size={15} />
          </button>
          <button className="sidebar-help" onClick={onOpenHelp}>
            <Info size={16} />
            Về công cụ này
            <ChevronRight size={14} />
          </button>
          <div className="sidebar-footer">
            <span className="mini-logo">PĐ</span>
            <span>
              Vietnamese Legal RAG<small>Tra cứu có căn cứ.</small>
            </span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              onClick={onOpenNavigation}
              aria-label="Mở menu và lịch sử"
            >
              <Menu size={21} />
            </button>
            <span className="topbar-breadcrumb">Không gian tra cứu</span>
            <ChevronRight size={13} />
            <span className="topbar-current">Hỏi đáp pháp luật</span>
          </div>
          <div className="topbar-right">
            <button
              className="service-status"
              onClick={() => void service.refresh()}
              disabled={service.state === 'checking'}
              title="Kiểm tra runtime tại thời điểm bấm; không kiểm tra liên tục mọi kết nối dữ liệu."
            >
              <span className={`status-dot ${service.state}`} />
              <span>
                {service.state === 'checking'
                  ? 'Đang kết nối'
                  : service.state === 'ready'
                    ? 'Runtime sẵn sàng'
                    : 'Chưa kết nối API'}
              </span>
              <RefreshCw size={12} className={service.state === 'checking' ? 'spin' : ''} />
            </button>
            <span className="topbar-divider" />
            <button className="icon-button" onClick={onOpenCorpus} aria-label="Thông tin dữ liệu">
              <Database size={18} />
            </button>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
