import { Scale } from 'lucide-react';

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Scale size={24} strokeWidth={1.5} />
      </span>
      {!compact && (
        <div>
          <strong>
            pháp điển<span className="brand-dot">.</span>
          </strong>
          <span className="brand-caption">VIETNAMESE LEGAL RAG</span>
        </div>
      )}
    </div>
  );
}
