import { BookOpen, ExternalLink, FileText, Quote, X } from 'lucide-react';
import type { QuestionResponse } from '../../../api/types';
import { safeExternalUrl } from '../../../lib/format';
import {
  citationLocation,
  legalLocation,
  metadataText,
  sourcesForCitation,
  sourceTitle,
  sourceUrl,
} from '../utils';

interface SourcePanelProps {
  response: QuestionResponse;
  selectedIndex: number | null;
  onSelect: (index: number | null) => void;
  onClose: () => void;
}

export function SourcePanel({ response, selectedIndex, onSelect, onClose }: SourcePanelProps) {
  const citations = response.answer.citations || [];
  const sources = response.sources || [];
  const citation = selectedIndex === null ? undefined : citations[selectedIndex];
  const matching = citation ? sourcesForCitation(citation, sources) : [];
  const url = safeExternalUrl(citation?.source_url);

  return (
    <section className="source-panel" aria-label="Căn cứ và nguồn tham chiếu">
      <div className="source-panel-heading">
        <div>
          <BookOpen size={17} />
          <h2>Căn cứ & nguồn</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Đóng nguồn tham chiếu">
          <X size={18} />
        </button>
      </div>
      <div className="source-tabs" role="group" aria-label="Chọn loại nguồn">
        <button
          className={selectedIndex !== null ? 'active' : ''}
          onClick={() => onSelect(citations.length ? 0 : null)}
          disabled={!citations.length}
        >
          Trích dẫn <span>{citations.length}</span>
        </button>
        <button className={selectedIndex === null ? 'active' : ''} onClick={() => onSelect(null)}>
          Nguồn context <span>{sources.length}</span>
        </button>
      </div>
      <div className="source-panel-body">
        {citation ? (
          <>
            <div className="citation-picker">
              {citations.map((item, index) => (
                <button
                  key={`${item.document_id}-${index}`}
                  onClick={() => onSelect(index)}
                  className={selectedIndex === index ? 'selected' : ''}
                  aria-label={`Xem trích dẫn ${index + 1}`}
                  aria-pressed={selectedIndex === index}
                >
                  {index + 1}
                </button>
              ))}
            </div>
            <p className="eyebrow">TRÍCH DẪN {selectedIndex! + 1}</p>
            <h3 className="source-title">Văn bản {citation.document_number}</h3>
            {citationLocation(citation) && (
              <p className="source-location">{citationLocation(citation)}</p>
            )}
            <blockquote className="source-quote">
              <Quote size={19} />
              <p>{citation.quoted_text}</p>
            </blockquote>
            {url && (
              <a className="external-link" href={url} target="_blank" rel="noopener noreferrer">
                Mở liên kết nguồn <ExternalLink size={14} />
              </a>
            )}
            <div className="source-divider" />
            <p className="eyebrow">ĐOẠN NGUỒN ĐỐI CHIẾU</p>
            {matching.length ? (
              matching.map((source) => (
                <div className="matched-source" key={source.chunk_id}>
                  <p className="source-chunk-label">
                    <FileText size={14} />
                    {sourceTitle(source)}
                  </p>
                  <p className="source-content">{source.content}</p>
                </div>
              ))
            ) : (
              <p className="muted small">
                Không xác định được đoạn context khớp trực tiếp. Bạn vẫn có thể đọc trích dẫn và xem
                các nguồn context API trả về.
              </p>
            )}
          </>
        ) : (
          <>
            <p className="source-help">
              Các đoạn được đưa vào context trả lời. Không phải mọi đoạn đều được trích dẫn.
            </p>
            {!sources.length && <p className="muted">Kết quả này không có đoạn nguồn đi kèm.</p>}
            {sources.map((source, index) => {
              const cited = citations.some((item) => sourcesForCitation(item, [source]).length > 0);
              const link = sourceUrl(source);
              return (
                <details className="context-source" key={source.chunk_id}>
                  <summary>
                    <span className="source-number">{index + 1}</span>
                    <span>
                      {sourceTitle(source)}
                      <small>{cited ? 'Có trích dẫn đối chiếu' : 'Context bổ sung'}</small>
                    </span>
                  </summary>
                  <div className="context-source-content">
                    {metadataText(source, 'article') && (
                      <p className="source-location">
                        {legalLocation('Điều', metadataText(source, 'article'))}
                      </p>
                    )}
                    <p className="source-content">{source.content}</p>
                    {link && (
                      <a
                        className="external-link"
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Mở liên kết nguồn <ExternalLink size={13} />
                      </a>
                    )}
                  </div>
                </details>
              );
            })}
          </>
        )}
        <div className="source-footnote">
          <BookOpen size={15} />
          <span>Nội dung hiển thị từ dữ liệu API, có thể chỉ là một đoạn của văn bản.</span>
        </div>
      </div>
    </section>
  );
}
