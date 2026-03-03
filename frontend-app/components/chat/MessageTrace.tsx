'use client';

import { useState, useEffect, useRef } from 'react';
import type { SourceReference } from '@/lib/types';
import { cn } from '@/lib/utils';

interface MessageTraceProps {
  sources: SourceReference[];
  topoFaithfulness?: number;
  highlightedArticle?: string | null;
  onHighlightClear?: () => void;
}

export function MessageTrace({
  sources,
  topoFaithfulness,
  highlightedArticle,
  onHighlightClear,
}: MessageTraceProps) {
  const [expanded, setExpanded] = useState(false);
  const highlightRef = useRef<HTMLDivElement>(null);

  // Auto-expand when a citation is clicked
  useEffect(() => {
    if (highlightedArticle) {
      const hasMatch = sources.some(
        (s) => s.source_article === highlightedArticle,
      );
      if (hasMatch) {
        setExpanded(true);
      }
    }
  }, [highlightedArticle, sources]);

  // Scroll highlighted source into view
  useEffect(() => {
    if (highlightedArticle && expanded && highlightRef.current) {
      highlightRef.current.scrollIntoView?.({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [highlightedArticle, expanded]);

  // Auto-clear highlight after 3 seconds
  useEffect(() => {
    if (highlightedArticle) {
      const timer = setTimeout(() => {
        onHighlightClear?.();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [highlightedArticle, onHighlightClear]);

  return (
    <div className="mt-2 border rounded-md text-sm">
      <button
        className="flex w-full items-center justify-between px-3 py-2 hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="font-medium">
          {expanded ? '▼' : '▶'} 근거 보기 ({sources.length})
        </span>
        {topoFaithfulness !== undefined && (
          <span className="text-xs text-muted-foreground">
            충실도: {topoFaithfulness}
          </span>
        )}
      </button>

      {expanded && (
        <div className="border-t px-3 py-2 space-y-2">
          {topoFaithfulness !== undefined && (
            <div className="text-xs text-muted-foreground">
              Topo Faithfulness: <span>{topoFaithfulness}</span>
            </div>
          )}
          {sources.map((source) => {
            const isHighlighted =
              highlightedArticle === source.source_article;
            return (
              <div
                key={source.node_id}
                ref={isHighlighted ? highlightRef : undefined}
                className={cn(
                  'rounded bg-muted/30 p-2 transition-all duration-300',
                  isHighlighted && 'ring-2 ring-primary bg-primary/5',
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      'inline-block rounded px-1.5 py-0.5 text-xs font-medium',
                      'bg-primary/10 text-primary',
                    )}
                  >
                    {source.source_article}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {source.node_type}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {source.source_text}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
