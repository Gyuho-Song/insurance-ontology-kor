'use client';

import { cn } from '@/lib/utils';
import type { RagMode } from '@/lib/types';

interface RagModeToggleProps {
  ragMode: RagMode;
  onRagModeChange: (mode: RagMode) => void;
}

const OPTIONS: { value: RagMode; label: string }[] = [
  { value: 'graphrag', label: 'GraphRAG' },
  { value: 'comparison', label: '비교' },
  { value: 'naive', label: 'Naive' },
];

export function RagModeToggle({ ragMode, onRagModeChange }: RagModeToggleProps) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">RAG</span>
      <div className="inline-flex rounded-md border bg-muted p-0.5">
        {OPTIONS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => onRagModeChange(value)}
            className={cn(
              'rounded-sm px-2 py-0.5 text-xs font-medium transition-colors',
              ragMode === value
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
