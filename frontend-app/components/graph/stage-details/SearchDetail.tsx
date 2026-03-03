'use client';

import { cn } from '@/lib/utils';
import type { StageEvent } from '@/lib/types';

const BRANCHES = [
  { id: 'A', label: 'Branch A', desc: '상품필터 k-NN', detail: '상품명 엔티티로 필터링 후 k-NN 검색' },
  { id: 'B', label: 'Branch B', desc: 'BM25+k-NN', detail: '키워드(BM25)와 벡터(k-NN)를 RRF로 결합' },
  { id: 'C', label: 'Branch C', desc: '순수 k-NN', detail: '의미 벡터만으로 유사 노드 검색' },
];

interface SearchDetailProps {
  stage: StageEvent;
}

export function SearchDetail({ stage }: SearchDetailProps) {
  const { branch, branch_reason, result_count, top_results, policy_resolved } =
    stage.data as {
      branch: string;
      branch_reason: string;
      result_count: number;
      top_results: { label: string; type: string; score: number }[];
      policy_resolved?: string[];
    };

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">🔍 Hybrid Vector Search</h3>

      {/* Branch selection */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">검색 전략 선택</div>
        <div className="flex gap-2">
          {BRANCHES.map((b) => (
            <div
              key={b.id}
              className={cn(
                'rounded-md border px-2 py-1.5 text-xs flex-1',
                branch === b.id
                  ? 'border-emerald-500 bg-emerald-50 text-emerald-700 font-medium'
                  : 'border-muted bg-muted/30 text-muted-foreground opacity-50',
              )}
            >
              <div className="text-center">{b.label}{branch === b.id ? ' ✅' : ''}</div>
              <div className="text-[10px] text-center mt-0.5">{b.desc}</div>
            </div>
          ))}
        </div>
        {branch_reason && (
          <div className="text-xs text-muted-foreground">
            선택 이유: {branch_reason}
          </div>
        )}
        {/* Show selected branch detail */}
        {BRANCHES.find(b => b.id === branch) && (
          <div className="text-[10px] text-muted-foreground bg-muted/30 rounded px-2 py-1">
            {BRANCHES.find(b => b.id === branch)!.detail}
          </div>
        )}
      </div>

      {/* Policy resolved */}
      {policy_resolved && policy_resolved.length > 0 && (
        <div className="rounded-md border border-violet-200 bg-violet-50/50 p-3 space-y-1">
          <div className="text-xs font-medium text-violet-700">상품 매칭</div>
          <div className="space-y-1">
            {policy_resolved.map((p) => (
              <div key={p} className="text-xs font-mono text-violet-600">{p}</div>
            ))}
          </div>
          <div className="text-[10px] text-violet-500">
            추출된 상품명으로 Policy 노드를 찾아 해당 상품 내에서만 벡터 검색을 수행합니다
          </div>
        </div>
      )}

      {/* Results */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">
          검색 결과 ({result_count}건)
        </div>
        <div className="space-y-1.5">
          {top_results?.map((r, i) => (
            <div
              key={i}
              className={cn(
                'rounded-md border p-2',
                i === 0
                  ? 'border-emerald-300 bg-emerald-50/50'
                  : 'border-muted',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    {i === 0 && (
                      <span className="shrink-0 rounded bg-emerald-600 text-white px-1 py-px text-[9px] font-medium">
                        Entry Node
                      </span>
                    )}
                    <span className="text-xs font-medium truncate">{r.label}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {r.type}
                    </span>
                    {i === 0 && (
                      <span className="text-[10px] text-emerald-600">
                        그래프 탐색 시작점
                      </span>
                    )}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-mono text-xs font-medium">{(r.score ?? 0).toFixed(3)}</div>
                  <div className="text-[9px] text-muted-foreground">score</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">{stage.ms}ms</div>
      )}
    </div>
  );
}
