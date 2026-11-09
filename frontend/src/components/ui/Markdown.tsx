import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { safeExternalUrl } from '../../lib/format';

// Raw HTML and embedded images are intentionally not rendered from model output.
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={(url) => safeExternalUrl(url) || ''}
        components={{
          a: ({ href, children: label }) =>
            href ? (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {label}
              </a>
            ) : (
              <span>{label}</span>
            ),
          img: () => null,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
