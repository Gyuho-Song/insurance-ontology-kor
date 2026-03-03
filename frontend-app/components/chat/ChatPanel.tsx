'use client';

import { useEffect, useMemo, useCallback, useRef } from 'react';
import { useChat } from '@ai-sdk/react';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { useAppContext } from '@/lib/context';
import type { ExtendedMessage, MessageAnnotation, StageEvent } from '@/lib/types';
import { getScenarioById } from '@/lib/scenarios';

interface ChatPanelProps {
  scenarioId: string | undefined;
  onScenarioConsumed: () => void;
}

export function ChatPanel({
  scenarioId,
  onScenarioConsumed,
}: ChatPanelProps) {
  const { setActiveSubgraph, setActiveTraversalEvents, setPipelineStages, setRightPanelTab, mydataConsent, ragMode, selectedCustomer } = useAppContext();

  const chatBody = useMemo(
    () => ({
      persona: 'presenter',
      ragMode,
      ...(mydataConsent ? { mydataConsent: { customer_id: mydataConsent.customer_id, consented: mydataConsent.consented } } : {}),
    }),
    [ragMode, mydataConsent]
  );

  const { messages, append, setMessages, isLoading, error, data } = useChat({
    api: '/api/chat',
    body: chatBody,
    onError: (err) => {
      console.error('[useChat] onError:', err);
    },
  });

  // Process data stream events into pipeline stages
  useEffect(() => {
    if (!data || data.length === 0) return;
    const stages: StageEvent[] = [];
    for (const item of data) {
      if (item && typeof item === 'object' && 'stage' in item) {
        stages.push(item as unknown as StageEvent);
      }
    }
    if (stages.length > 0) {
      setPipelineStages(stages);
    }
  }, [data, setPipelineStages]);

  // Auto-switch to pipeline tab when loading starts
  const prevLoadingRef = useRef(false);
  useEffect(() => {
    if (isLoading && !prevLoadingRef.current) {
      setPipelineStages([]);
      setRightPanelTab('pipeline');
    }
    prevLoadingRef.current = isLoading;
  }, [isLoading, setPipelineStages, setRightPanelTab]);

  // Reset chat when customer changes
  const prevCustomerRef = useRef(selectedCustomer?.id);
  useEffect(() => {
    if (prevCustomerRef.current !== selectedCustomer?.id) {
      prevCustomerRef.current = selectedCustomer?.id;
      setMessages([]);
      setActiveSubgraph(undefined);
      setActiveTraversalEvents(undefined);
    }
  }, [selectedCustomer?.id, setMessages, setActiveSubgraph, setActiveTraversalEvents]);

  const appendRef = useRef(append);
  appendRef.current = append;

  useEffect(() => {
    if (!scenarioId) return;

    const scenario = getScenarioById(scenarioId);
    if (scenario) {
      appendRef.current(
        { role: 'user', content: scenario.query },
        { body: { scenarioId } }
      ).catch(
        (err: unknown) => console.error('[ChatPanel] append failed:', err)
      );
      onScenarioConsumed();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, onScenarioConsumed]);

  const extendedMessages: ExtendedMessage[] = useMemo(() => messages.map((msg) => {
    const extended: ExtendedMessage = {
      id: msg.id,
      role: msg.role as 'user' | 'assistant',
      content: msg.content,
    };

    const annotations = (msg as unknown as { annotations?: unknown[] }).annotations;
    if (annotations && annotations.length > 0) {
      const annotation = annotations[0] as MessageAnnotation;
      if (annotation) {
        extended.sources = annotation.sources;
        extended.traversalEvents = annotation.traversalEvents;
        extended.subgraph = annotation.subgraph;
        extended.topoFaithfulness = annotation.topoFaithfulness;
        extended.templatesUsed = annotation.templatesUsed;
        extended.isMockResponse = annotation.isMockResponse;
        extended.naiveRag = annotation.naiveRag;
        extended.comparisonMode = annotation.comparisonMode;
        extended.graphRagResponseTimeMs = annotation.graphRagResponseTimeMs;
      }
    }

    return extended;
  }), [messages]);

  useEffect(() => {
    const lastAssistant = extendedMessages.filter((m) => m.role === 'assistant').pop();
    if (lastAssistant?.subgraph) {
      setActiveSubgraph(lastAssistant.subgraph);
      setActiveTraversalEvents(lastAssistant.traversalEvents);
    }
  }, [extendedMessages, setActiveSubgraph, setActiveTraversalEvents]);

  const handleSend = useCallback((content: string) => {
    appendRef.current({ role: 'user', content }).catch(
      (err: unknown) => console.error('[ChatPanel] send failed:', err)
    );
  }, []);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [extendedMessages, isLoading]);

  return (
    <div className="flex h-full flex-col">
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3"
      >
        {extendedMessages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg px-4 py-3 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <span className="animate-pulse">●</span>
                <span className="animate-pulse" style={{ animationDelay: '0.2s' }}>●</span>
                <span className="animate-pulse" style={{ animationDelay: '0.4s' }}>●</span>
                <span className="ml-2">응답 생성 중...</span>
              </span>
            </div>
          </div>
        )}
        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            <strong>오류:</strong> {error.message}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t p-4">
        <ChatInput onSend={handleSend} isLoading={isLoading} />
      </div>
    </div>
  );
}
