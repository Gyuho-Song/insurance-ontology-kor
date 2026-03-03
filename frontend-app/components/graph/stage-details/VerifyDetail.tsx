'use client';

import { cn } from '@/lib/utils';
import type { StageEvent } from '@/lib/types';

interface VerifyDetailProps {
  stage: StageEvent;
}

export function VerifyDetail({ stage }: VerifyDetailProps) {
  const { topo_faithfulness: rawFaithfulness, validation_status, confidence_label } =
    stage.data as {
      topo_faithfulness: number | null;
      validation_status: string;
      confidence_label: string;
    };

  const topo_faithfulness = rawFaithfulness ?? 0;
  const pct = Math.round(topo_faithfulness * 100);

  const labelColor =
    confidence_label === 'high'
      ? 'bg-emerald-100 text-emerald-700'
      : confidence_label === 'medium'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-red-100 text-red-700';

  const barColor =
    confidence_label === 'high'
      ? 'bg-emerald-500'
      : confidence_label === 'medium'
        ? 'bg-amber-500'
        : 'bg-red-500';

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">🔬 Verification</h3>
        <span
          className={cn(
            'text-xs font-medium px-2 py-0.5 rounded-full uppercase',
            labelColor,
          )}
        >
          {confidence_label}
        </span>
      </div>

      {/* Topo Faithfulness */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Topological Faithfulness</span>
          <span className="font-mono font-medium">{topo_faithfulness.toFixed(2)}</span>
        </div>
        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={cn('h-full rounded-full transition-all', barColor)}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Validation status */}
      <div className="rounded-md border p-3 space-y-1.5">
        <div className="text-xs font-medium text-muted-foreground">Validation Checks</div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-emerald-600">✅</span>
          <span>Template Source Match — {validation_status}</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-emerald-600">✅</span>
          <span>Graph Topology Faithfulness — {pct}%</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className={topo_faithfulness >= 0.5 ? 'text-emerald-600' : 'text-red-600'}>
            {topo_faithfulness >= 0.5 ? '✅' : '❌'}
          </span>
          <span>Confidence Threshold — {confidence_label.toUpperCase()}</span>
        </div>
      </div>

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">{stage.ms}ms</div>
      )}
    </div>
  );
}
