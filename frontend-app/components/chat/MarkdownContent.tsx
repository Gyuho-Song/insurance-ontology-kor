'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

interface MarkdownContentProps {
  content: string;
  onCitationClick?: (articleRef: string) => void;
  className?: string;
}

/**
 * Pre-process content to convert [출처: 제X조Y항] citation tags into
 * markdown links that the custom `a` renderer will intercept.
 */
function preprocessCitations(content: string): string {
  return content.replace(
    /\[출처:\s*([^\]]+)\]/g,
    (_match, articleRef: string) => {
      const trimmed = articleRef.trim();
      return `[🔖 ${trimmed}](#cite:${encodeURIComponent(trimmed)})`;
    },
  );
}

export function MarkdownContent({
  content,
  onCitationClick,
  className,
}: MarkdownContentProps) {
  const processed = preprocessCitations(content);

  const components: Components = {
    a: ({ href, children }) => {
      if (href?.startsWith('#cite:')) {
        const articleRef = decodeURIComponent(href.slice(6));
        return (
          <button
            type="button"
            className="inline-flex items-center rounded-full bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors cursor-pointer align-baseline mx-0.5"
            onClick={(e) => {
              e.preventDefault();
              onCitationClick?.(articleRef);
            }}
            title={`출처: ${articleRef}`}
          >
            {children}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    },
    table: ({ children }) => (
      <div className="overflow-x-auto my-2">
        <table>{children}</table>
      </div>
    ),
  };

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {processed}
      </ReactMarkdown>
    </div>
  );
}
