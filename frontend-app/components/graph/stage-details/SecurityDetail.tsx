'use client';

import { cn } from '@/lib/utils';
import type { StageEvent } from '@/lib/types';

interface SecurityDetailProps {
  stage: StageEvent;
}

export function SecurityDetail({ stage }: SecurityDetailProps) {
  const isBlocked = stage.status === 'blocked';
  const blockedReason = stage.data.blocked_reason as string | undefined;

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          🛡️ Security Check
        </h3>
        <span
          className={cn(
            'text-xs font-medium px-2 py-0.5 rounded-full',
            isBlocked
              ? 'bg-red-100 text-red-700'
              : 'bg-emerald-100 text-emerald-700',
          )}
        >
          {isBlocked ? '⛔ BLOCKED' : '✅ PASS'}
        </span>
      </div>

      {isBlocked ? (
        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          <div className="font-medium">입력이 차단되었습니다</div>
          <div className="text-xs mt-1">
            탐지된 패턴: {blockedReason === 'gremlin_injection' ? 'Gremlin Injection' : 'Prompt Injection'}
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-emerald-600">✅</span>
            <span>Gremlin Injection — 패턴 미탐지</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-emerald-600">✅</span>
            <span>Prompt Injection — 패턴 미탐지</span>
          </div>
        </div>
      )}

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">{stage.ms}ms</div>
      )}
    </div>
  );
}
