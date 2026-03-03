'use client';

import { cn } from '@/lib/utils';
import type { StageEvent } from '@/lib/types';

interface GenerateDetailProps {
  stage: StageEvent;
}

export function GenerateDetail({ stage }: GenerateDetailProps) {
  const { model, complexity, context_nodes, context_edges, prompt_rules } =
    stage.data as {
      model: string;
      complexity: string;
      context_nodes: number;
      context_edges: number;
      prompt_rules: number;
    };

  const isStreaming = stage.status === 'streaming';

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">✍️ Answer Generation</h3>
        {isStreaming && (
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 animate-pulse">
            Streaming...
          </span>
        )}
      </div>

      {/* Model info */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Model</span>
          <span className="font-medium">{model}</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Complexity</span>
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10px] font-medium',
              complexity === 'complex'
                ? 'bg-amber-50 border border-amber-200 text-amber-700'
                : 'bg-emerald-50 border border-emerald-200 text-emerald-700',
            )}
          >
            {complexity}
          </span>
        </div>
      </div>

      {/* Context stats */}
      <div className="rounded-md border p-3">
        <div className="text-xs font-medium text-muted-foreground mb-2">Context Window</div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div>
            <div className="text-lg font-semibold">{context_nodes}</div>
            <div className="text-muted-foreground">nodes</div>
          </div>
          <div>
            <div className="text-lg font-semibold">{context_edges}</div>
            <div className="text-muted-foreground">edges</div>
          </div>
          <div>
            <div className="text-lg font-semibold">{prompt_rules}</div>
            <div className="text-muted-foreground">rules</div>
          </div>
        </div>
      </div>

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">
          {stage.ms >= 1000 ? `${(stage.ms / 1000).toFixed(1)}s` : `${stage.ms}ms`}
        </div>
      )}
    </div>
  );
}
