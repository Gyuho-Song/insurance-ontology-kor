'use client';

import { cn } from '@/lib/utils';

const NODE_TYPES = [
  { type: 'Policy', count: 30, icon: '📋', desc: '보험상품 — 온톨로지의 중심. 모든 관계의 시작점', primary: true },
  { type: 'Coverage', count: 433, icon: '🛡️', desc: '보장항목 — 사망보험금, 입원급여금 등 지급 사유와 금액' },
  { type: 'Exclusion', count: 224, icon: '🚫', desc: '면책사유 — 보험금을 지급하지 않는 사유' },
  { type: 'Exception', count: 178, icon: '✅', desc: '예외조항 — 면책이지만 보장되는 특수 케이스' },
  { type: 'Calculation', count: 280, icon: '🧮', desc: '계산규칙 — 보험료, 환급금, 이율 산출 방식' },
  { type: 'Rider', count: 222, icon: '📎', desc: '특약 — 주계약에 추가하는 선택 보장' },
  { type: 'Surrender_Value', count: 147, icon: '💰', desc: '해약환급금 — 해지 시 돌려받는 금액 테이블' },
  { type: 'Dividend_Method', count: 82, icon: '📊', desc: '배당방식 — 배당 가능 여부 및 배당금 산출 방식' },
  { type: 'Eligibility', count: 60, icon: '🎫', desc: '가입조건 — 나이, 건강상태 등 가입 자격 요건' },
  { type: 'Regulation', count: 219, icon: '⚖️', desc: '규제/법률 — 보험업법, 감독규정, 금지행위' },
  { type: 'Customer', count: 10, icon: '👤', desc: '고객 — 마이데이터 연동 고객 (보유 계약 연결)' },
];

const EDGE_TYPES = [
  { type: 'HAS_COVERAGE', count: 424, desc: '보장항목 보유' },
  { type: 'CALCULATED_BY', count: 246, desc: '계산규칙 적용' },
  { type: 'EXCLUDED_IF', count: 227, desc: '면책 조건' },
  { type: 'GOVERNED_BY', count: 219, desc: '규제 적용' },
  { type: 'HAS_RIDER', count: 194, desc: '특약 보유' },
  { type: 'EXCEPTION_ALLOWED', count: 152, desc: '예외 인정' },
  { type: 'SURRENDER_PAYS', count: 117, desc: '환급금 지급' },
  { type: 'STRICTLY_PROHIBITED', count: 73, desc: '금지행위' },
  { type: 'EXCEPTIONALLY_ALLOWED', count: 55, desc: '예외 허용' },
  { type: 'OWNS', count: 30, desc: '계약 보유' },
];

const TOTAL_NODES = 1885;
const TOTAL_EDGES = 1771;
const MAX_COUNT = Math.max(...NODE_TYPES.map((n) => n.count));

export function DefaultOverview() {
  return (
    <div className="flex h-full flex-col overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="text-center space-y-1">
        <div className="text-sm font-semibold">보험 온톨로지 지식 그래프</div>
        <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <span><span className="font-medium text-foreground">{TOTAL_NODES.toLocaleString()}</span> 노드</span>
          <span className="text-border">|</span>
          <span><span className="font-medium text-foreground">{TOTAL_EDGES.toLocaleString()}</span> 관계</span>
          <span className="text-border">|</span>
          <span><span className="font-medium text-foreground">30</span> 상품</span>
        </div>
      </div>

      {/* Ontology relationship diagram */}
      <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
        <div className="text-[10px] font-medium text-muted-foreground text-center">핵심 관계 구조</div>
        <div className="flex items-center justify-center gap-1 text-[10px] flex-wrap">
          <span className="rounded bg-blue-100 border border-blue-300 px-1.5 py-0.5 font-medium text-blue-700">👤 Customer</span>
          <span className="text-muted-foreground">—OWNS→</span>
          <span className="rounded bg-amber-100 border border-amber-300 px-1.5 py-0.5 font-bold text-amber-800">📋 Policy</span>
          <span className="text-muted-foreground">—HAS→</span>
          <span className="rounded bg-emerald-100 border border-emerald-300 px-1.5 py-0.5 font-medium text-emerald-700">🛡️ Coverage</span>
        </div>
        <div className="flex items-center justify-center gap-1 text-[10px] flex-wrap">
          <span className="w-[100px]" />
          <span className="rounded bg-emerald-100 border border-emerald-300 px-1.5 py-0.5 font-medium text-emerald-700">🛡️ Coverage</span>
          <span className="text-muted-foreground">—EXCLUDED_IF→</span>
          <span className="rounded bg-red-100 border border-red-300 px-1.5 py-0.5 font-medium text-red-700">🚫 Exclusion</span>
          <span className="text-muted-foreground">—EXCEPTION→</span>
          <span className="rounded bg-green-100 border border-green-300 px-1.5 py-0.5 font-medium text-green-700">✅ Exception</span>
        </div>
        <div className="flex items-center justify-center gap-1 text-[10px] flex-wrap">
          <span className="w-[100px]" />
          <span className="rounded bg-amber-100 border border-amber-300 px-1.5 py-0.5 font-bold text-amber-800">📋 Policy</span>
          <span className="text-muted-foreground">—GOVERNED_BY→</span>
          <span className="rounded bg-violet-100 border border-violet-300 px-1.5 py-0.5 font-medium text-violet-700">⚖️ Regulation</span>
        </div>
      </div>

      {/* Node types - ordered by importance */}
      <div className="rounded-lg border p-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">노드 타입 (11종)</div>
        <div className="space-y-1">
          {NODE_TYPES.map((n) => (
            <div
              key={n.type}
              className={cn(
                'flex items-center gap-2 text-xs rounded-md px-1.5 py-1',
                n.primary && 'bg-amber-50 border border-amber-200',
              )}
            >
              <span className="w-4 text-center shrink-0">{n.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className={cn('font-medium', n.primary && 'text-amber-800')}>
                    {n.type}
                  </span>
                  {n.primary && (
                    <span className="rounded bg-amber-200 text-amber-800 px-1 text-[9px] font-medium">중심</span>
                  )}
                  <span className="text-muted-foreground ml-auto shrink-0">{n.count}</span>
                </div>
                <div className="text-[10px] text-muted-foreground truncate">{n.desc.split(' — ')[1]}</div>
              </div>
              <div className="w-12 shrink-0">
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full',
                      n.primary ? 'bg-amber-400' : 'bg-emerald-500/60',
                    )}
                    style={{ width: `${(n.count / MAX_COUNT) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Edge types */}
      <div className="rounded-lg border p-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">관계 타입 (10종)</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1">
          {EDGE_TYPES.map((e) => (
            <div key={e.type} className="flex items-center gap-1.5 text-[10px]">
              <span className="text-muted-foreground font-mono truncate flex-1">{e.type}</span>
              <span className="text-muted-foreground shrink-0">{e.desc}</span>
              <span className="text-muted-foreground/60 shrink-0 w-6 text-right">{e.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Dual storage summary */}
      <div className="rounded-lg bg-muted/30 border p-3 space-y-1 text-center">
        <div className="text-[10px] text-muted-foreground">
          <span className="font-medium text-foreground">Neptune</span>(구조적 관계)과{' '}
          <span className="font-medium text-foreground">OpenSearch</span>(1,024차원 의미 벡터)에 이중 저장 · Amazon Titan V2 임베딩
        </div>
        <div className="text-xs text-muted-foreground">
          채팅에서 질문하면 파이프라인이 단계별로 실행됩니다
        </div>
      </div>
    </div>
  );
}
