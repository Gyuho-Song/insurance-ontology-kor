'use client';

import { useState, useCallback } from 'react';
import type { ExtendedMessage } from '@/lib/types';
import { MessageTrace } from './MessageTrace';
import { ComparisonCard } from './ComparisonCard';
import { MarkdownContent } from './MarkdownContent';
import { cn } from '@/lib/utils';

interface ChatMessageProps {
  message: ExtendedMessage;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const hasSources = message.sources && message.sources.length > 0;
  const isComparison = message.comparisonMode && message.naiveRag;

  const [highlightedArticle, setHighlightedArticle] = useState<string | null>(null);

  const handleCitationClick = useCallback((articleRef: string) => {
    setHighlightedArticle(articleRef);
  }, []);

  const handleHighlightClear = useCallback(() => {
    setHighlightedArticle(null);
  }, []);

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'rounded-lg px-4 py-3',
          isUser
            ? 'max-w-[85%] bg-primary text-primary-foreground'
            : isComparison
              ? 'max-w-[95%] bg-muted text-foreground'
              : 'max-w-[85%] bg-muted text-foreground'
        )}
      >
        {isComparison ? (
          <ComparisonCard
            graphRagAnswer={message.content}
            graphRagSources={message.sources ?? []}
            graphRagFaithfulness={message.topoFaithfulness}
            graphRagTimeMs={message.graphRagResponseTimeMs}
            naiveRag={message.naiveRag!}
          />
        ) : (
          <>
            {isUser ? (
              <p className="whitespace-pre-wrap">{message.content}</p>
            ) : (
              <MarkdownContent
                content={message.content}
                onCitationClick={handleCitationClick}
                className="chat-markdown"
              />
            )}

            {!isUser && hasSources && (
              <MessageTrace
                sources={message.sources!}
                topoFaithfulness={message.topoFaithfulness}
                highlightedArticle={highlightedArticle}
                onHighlightClear={handleHighlightClear}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
