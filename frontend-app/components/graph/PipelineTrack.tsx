'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { StageEvent, PipelineStageId } from '@/lib/types';

const STAGE_DEFS: { id: PipelineStageId; icon: string; label: string }[] = [
  { id: 'security', icon: '🛡️', label: '보안' },
  { id: 'understand', icon: '📖', label: '이해' },
  { id: 'classify', icon: '🎯', label: '의도' },
  { id: 'search', icon: '🔍', label: '검색' },
  { id: 'traverse', icon: '🗺️', label: '탐색' },
  { id: 'generate', icon: '🤖', label: '생성' },
  { id: 'verify', icon: '✅', label: '검증' },
];

type StageStatus = 'pending' | 'done' | 'active' | 'blocked';

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function deriveStageStatuses(stages: StageEvent[]): Record<PipelineStageId, { status: StageStatus; ms?: number }> {
  const result: Record<string, { status: StageStatus; ms?: number }> = {};
  for (const def of STAGE_DEFS) {
    result[def.id] = { status: 'pending' };
  }

  for (const event of stages) {
    const id = event.stage;
    if (event.status === 'blocked') {
      result[id] = { status: 'blocked', ms: event.ms };
    } else if (event.status === 'streaming') {
      result[id] = { status: 'active', ms: event.ms };
    } else if (event.status === 'done' || event.status === 'pass') {
      result[id] = { status: 'done', ms: event.ms };
    }
  }

  return result as Record<PipelineStageId, { status: StageStatus; ms?: number }>;
}

interface PipelineTrackProps {
  stages: StageEvent[];
  onStageSelect: (stage: PipelineStageId) => void;
  selectedStage: PipelineStageId | null;
}

export function PipelineTrack({ stages, onStageSelect, selectedStage }: PipelineTrackProps) {
  const statuses = useMemo(() => deriveStageStatuses(stages), [stages]);

  return (
    <div className="flex items-center justify-between px-3 py-2 gap-1">
      {STAGE_DEFS.map((def, idx) => {
        const { status, ms } = statuses[def.id];
        const isSelected = selectedStage === def.id;
        const isClickable = status === 'done' || status === 'blocked';

        return (
          <div key={def.id} className="flex items-center gap-1">
            {idx > 0 && (
              <div
                className={cn(
                  'h-px w-3 flex-shrink-0',
                  status !== 'pending' ? 'bg-emerald-500' : 'bg-border',
                )}
              />
            )}
            <button
              data-testid={`stage-node-${def.id}`}
              data-status={status}
              onClick={() => isClickable && onStageSelect(def.id)}
              className={cn(
                'flex flex-col items-center gap-0.5 rounded-md px-1.5 py-1 text-xs transition-all min-w-[48px]',
                status === 'pending' && 'text-muted-foreground opacity-40',
                status === 'done' && 'text-emerald-600',
                status === 'active' && 'text-blue-600 animate-pulse',
                status === 'blocked' && 'text-red-600',
                isSelected && 'bg-accent ring-1 ring-accent-foreground/20',
                isClickable && 'cursor-pointer hover:bg-accent/50',
                !isClickable && 'cursor-default',
              )}
            >
              <span className="text-base leading-none">{def.icon}</span>
              <span className="font-medium leading-none">{def.label}</span>
              {(status === 'done' || status === 'blocked') && ms !== undefined && (
                <span className="text-[10px] leading-none text-muted-foreground">
                  {formatDuration(ms)}
                </span>
              )}
            </button>
          </div>
        );
      })}
    </div>
  );
}
