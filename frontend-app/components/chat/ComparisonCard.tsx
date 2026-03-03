'use client';

import { useState, useCallback } from 'react';
import { MessageTrace } from './MessageTrace';
import { MarkdownContent } from './MarkdownContent';
import { Badge } from '@/components/ui/badge';
import type { SourceReference, NaiveRagResult } from '@/lib/types';

interface ComparisonCardProps {
  graphRagAnswer: string;
  graphRagSources: SourceReference[];
  graphRagFaithfulness?: number;
  graphRagTimeMs?: number;
  naiveRag: NaiveRagResult;
}

export function ComparisonCard({
  graphRagAnswer,
  graphRagSources,
  graphRagFaithfulness,
  graphRagTimeMs,
  naiveRag,
}: ComparisonCardProps) {
  const [graphHighlight, setGraphHighlight] = useState<string | null>(null);
  const [naiveHighlight, setNaiveHighlight] = useState<string | null>(null);

  const handleGraphCitation = useCallback((ref: string) => setGraphHighlight(ref), []);
  const handleGraphClear = useCallback(() => setGraphHighlight(null), []);
  const handleNaiveCitation = useCallback((ref: string) => setNaiveHighlight(ref), []);
  const handleNaiveClear = useCallback(() => setNaiveHighlight(null), []);

  return (
    <div className="space-y-3">
      {/* Metrics bar */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary" className="bg-blue-100 text-blue-800">비교 모드</Badge>
        {graphRagTimeMs != null && <span>GraphRAG: {graphRagTimeMs}ms</span>}
        <span>Naive RAG: {naiveRag.responseTimeMs}ms</span>
      </div>

      {/* Side-by-side cards */}
      <div className="grid grid-cols-2 gap-3">
        {/* GraphRAG Card */}
        <div className="rounded-lg border-2 border-blue-200 bg-blue-50/50 p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Badge className="bg-blue-600 text-white">GraphRAG</Badge>
            {graphRagFaithfulness != null && (
              <span className="text-xs text-muted-foreground">
                충실도: {graphRagFaithfulness}
              </span>
            )}
          </div>
          <MarkdownContent
            content={graphRagAnswer}
            onCitationClick={handleGraphCitation}
            className="chat-markdown text-sm"
          />
          {graphRagSources.length > 0 && (
            <MessageTrace
              sources={graphRagSources}
              topoFaithfulness={graphRagFaithfulness}
              highlightedArticle={graphHighlight}
              onHighlightClear={handleGraphClear}
            />
          )}
        </div>

        {/* Naive RAG Card */}
        <div className="rounded-lg border-2 border-gray-200 bg-gray-50/50 p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">Naive RAG</Badge>
            <span className="text-xs text-muted-foreground">충실도: N/A</span>
          </div>
          <MarkdownContent
            content={naiveRag.answer}
            onCitationClick={handleNaiveCitation}
            className="chat-markdown text-sm"
          />
          {naiveRag.sources.length > 0 && (
            <MessageTrace
              sources={naiveRag.sources}
              highlightedArticle={naiveHighlight}
              onHighlightClear={handleNaiveClear}
            />
          )}
        </div>
      </div>
    </div>
  );
}
