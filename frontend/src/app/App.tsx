import { useEffect, useState } from 'react';
import { Database, Plus, ShieldCheck } from 'lucide-react';
import { AppLayout } from './AppLayout';
import { Dialog } from '../components/ui/Dialog';
import { CorpusDialog } from '../features/corpus/components/CorpusDialog';
import { useServiceInfo } from '../features/corpus/hooks/useServiceInfo';
import { HistoryList } from '../features/history/components/HistoryList';
import { QuestionComposer } from '../features/questions/components/QuestionComposer';
import { QuestionResult } from '../features/questions/components/QuestionResult';
import { Welcome } from '../features/questions/components/Welcome';
import { useQuestionSession } from '../features/questions/hooks/useQuestionSession';
import { SourcePanel } from '../features/sources/components/SourcePanel';

function useCompactSources() {
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 1199px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1199px)');
    const update = () => setCompact(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return compact;
}

export default function App() {
  const session = useQuestionSession();
  const service = useServiceInfo();
  const [draft, setDraft] = useState('');
  const [focusToken, setFocusToken] = useState(0);
  const [corpusOpen, setCorpusOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [desktopSourcesOpen, setDesktopSourcesOpen] = useState(true);
  const [mobileSourcesOpen, setMobileSourcesOpen] = useState(false);
  const [citationIndex, setCitationIndex] = useState<number | null>(0);
  const compactSources = useCompactSources();
  const response =
    session.activeEntry?.state === 'answered' ? session.activeEntry.response : undefined;
  const selectedIndex =
    citationIndex !== null && response?.answer.citations?.[citationIndex] ? citationIndex : null;
  const showSourcePane = !!response && desktopSourcesOpen && !compactSources;

  function resetSourceView() {
    setCitationIndex(0);
    setMobileSourcesOpen(false);
    setDesktopSourcesOpen(true);
  }

  function newQuestion() {
    session.newQuestion();
    setDraft('');
    setFocusToken((value) => value + 1);
    setNavigationOpen(false);
    resetSourceView();
  }

  function selectHistory(id: string) {
    session.select(id);
    setNavigationOpen(false);
    resetSourceView();
  }

  function useQuestion(query: string) {
    setDraft(query);
    setFocusToken((value) => value + 1);
  }

  async function submit(query: string) {
    resetSourceView();
    const success = await session.submit(query);
    if (success) setDraft((current) => (current === query ? '' : current));
  }

  function openSources(index: number | null) {
    setCitationIndex(index);
    setDesktopSourcesOpen(true);
    if (compactSources) setMobileSourcesOpen(true);
  }

  const history = (
    <HistoryList entries={session.entries} activeId={session.activeId} onSelect={selectHistory} />
  );
  const sources = response && (
    <SourcePanel
      response={response}
      selectedIndex={selectedIndex}
      onSelect={setCitationIndex}
      onClose={() => {
        setDesktopSourcesOpen(false);
        setMobileSourcesOpen(false);
      }}
    />
  );

  return (
    <>
      <AppLayout
        service={service}
        history={history}
        onNewQuestion={newQuestion}
        onOpenCorpus={() => setCorpusOpen(true)}
        onOpenHelp={() => setHelpOpen(true)}
        onOpenNavigation={() => setNavigationOpen(true)}
      >
        <div className={`workspace ${showSourcePane ? 'with-sources' : ''}`}>
          <main
            id="main-content"
            className={`main-content ${session.activeEntry ? 'has-result' : ''}`}
          >
            <div className="content-scroll" key={session.activeId || 'welcome'}>
              {session.activeEntry ? (
                <QuestionResult
                  key={session.activeEntry.id}
                  entry={session.activeEntry}
                  onNewQuestion={newQuestion}
                  onEdit={useQuestion}
                  onCitation={(index) => openSources(index)}
                  onSources={() => openSources(null)}
                />
              ) : (
                <Welcome onSuggestion={useQuestion} corpus={service.corpus} />
              )}
            </div>
            <QuestionComposer
              draft={draft}
              onDraftChange={setDraft}
              isSending={session.isSending}
              onSubmit={(query) => void submit(query)}
              focusToken={focusToken}
            />
            <footer className="main-footer">
              <span>
                <ShieldCheck size={12} />
                Tra cứu theo dữ liệu · Đối chiếu căn cứ
              </span>
              <span>PHÁP ĐIỂN / LEGAL RAG</span>
            </footer>
          </main>
          {showSourcePane && <aside className="desktop-sources">{sources}</aside>}
        </div>
      </AppLayout>
      {corpusOpen && <CorpusDialog service={service} onClose={() => setCorpusOpen(false)} />}
      {navigationOpen && (
        <Dialog
          title="Không gian tra cứu"
          className="navigation-dialog"
          onClose={() => setNavigationOpen(false)}
        >
          <button className="new-question-button" onClick={newQuestion}>
            <Plus size={18} />
            Câu hỏi mới
          </button>
          {history}
          <button
            className="text-button"
            onClick={() => {
              setNavigationOpen(false);
              setCorpusOpen(true);
            }}
          >
            <Database size={16} />
            Thông tin dữ liệu
          </button>
        </Dialog>
      )}
      {compactSources && mobileSourcesOpen && response && (
        <Dialog
          title="Nguồn tham chiếu"
          className="source-dialog"
          onClose={() => setMobileSourcesOpen(false)}
        >
          {sources}
        </Dialog>
      )}
      {helpOpen && (
        <Dialog title="Về Pháp điển" onClose={() => setHelpOpen(false)}>
          <p className="dialog-intro">
            Công cụ hỏi đáp pháp luật tiếng Việt sử dụng dữ liệu truy xuất để tạo câu trả lời kèm
            căn cứ.
          </p>
          <ol className="help-steps">
            <li>
              <strong>Hỏi đầy đủ bối cảnh.</strong> Mỗi câu hỏi được xử lý độc lập; hệ thống không
              sử dụng nội dung câu hỏi trước.
            </li>
            <li>
              <strong>Đọc và đối chiếu.</strong> Chọn một trích dẫn để xem đoạn được dẫn và nguồn
              context tương ứng khi xác định được.
            </li>
            <li>
              <strong>Kiểm tra phạm vi dữ liệu.</strong> Câu trả lời dựa trên snapshot đang phục vụ;
              hãy kiểm tra văn bản gốc và hiệu lực trước khi áp dụng.
            </li>
          </ol>
          <p className="callout">
            Lịch sử chỉ nằm trong bộ nhớ của trang và mất khi tải lại hoặc đóng trang. Công cụ không
            lưu tài khoản hay lịch sử lâu dài trên frontend.
          </p>
          <p className="muted small">
            Thông báo “đã kiểm chứng trích dẫn” phản ánh bước kiểm chứng của pipeline, không xác
            nhận toàn bộ kết luận pháp lý.
          </p>
        </Dialog>
      )}
    </>
  );
}
