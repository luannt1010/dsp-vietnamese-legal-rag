import {
  ArrowUpRight,
  BookOpen,
  GraduationCap,
  Route,
  Sparkles,
  Quote,
  ShieldCheck,
  Search,
} from 'lucide-react';
import type { CorpusResponse } from '../../../api/types';

const suggestions = [
  {
    icon: GraduationCap,
    label: 'Giáo dục',
    question: 'Người học có những quyền gì theo Luật Giáo dục?',
  },
  {
    icon: Route,
    label: 'Giao thông',
    question: 'Phương tiện thủy nội địa phải đáp ứng những điều kiện gì để được hoạt động?',
  },
  {
    icon: Search,
    label: 'Tra cứu văn bản',
    question: 'Luật Giao thông đường thủy nội địa số 23/2004/QH11 điều chỉnh những hoạt động nào?',
  },
];

export function Welcome({
  onSuggestion,
  corpus,
}: {
  onSuggestion: (query: string) => void;
  corpus?: CorpusResponse;
}) {
  return (
    <section className="welcome" aria-labelledby="welcome-heading">
      <div className="welcome-emblem">
        <BookOpen size={30} strokeWidth={1.35} />
        <span>
          <Sparkles size={12} />
        </span>
      </div>
      <div className="welcome-eyebrow">
        <span />
        TRỢ LÝ TRA CỨU PHÁP LUẬT TIẾNG VIỆT
      </div>
      <h1 id="welcome-heading">
        Hiểu đúng luật.
        <br />
        <em>Bắt đầu từ một câu hỏi.</em>
      </h1>
      <p className="welcome-description">
        Tìm câu trả lời từ dữ liệu pháp luật, kèm trích dẫn
        <br className="desktop-break" /> để bạn đọc hiểu và đối chiếu căn cứ.
      </p>
      <div className="welcome-benefits">
        <span>
          <Quote size={14} />
          Trích dẫn rõ ràng
        </span>
        <i />
        <span>
          <ShieldCheck size={14} />
          Đối chiếu nguồn
        </span>
      </div>
      <div className="suggestions-heading">
        <span>BẠN CÓ THỂ BẮT ĐẦU VỚI</span>
        <span className="suggestion-line" />
      </div>
      <div className="suggestion-grid">
        {suggestions.map(({ icon: Icon, label, question }) => (
          <button key={label} className="suggestion-card" onClick={() => onSuggestion(question)}>
            <span className="suggestion-card-top">
              <Icon size={18} strokeWidth={1.6} />
              <ArrowUpRight size={16} />
            </span>
            <span className="suggestion-label">{label}</span>
            <span className="suggestion-query">{question}</span>
          </button>
        ))}
      </div>
      <p className="welcome-scope">
        {corpus
          ? `Phạm vi hiện tại: ${[...corpus.topics, ...corpus.subjects].slice(0, 4).join(' · ') || 'theo snapshot đang phục vụ'}.`
          : 'Câu hỏi gợi ý chỉ mang tính tham khảo; khả năng trả lời phụ thuộc dữ liệu đang phục vụ.'}
      </p>
    </section>
  );
}
