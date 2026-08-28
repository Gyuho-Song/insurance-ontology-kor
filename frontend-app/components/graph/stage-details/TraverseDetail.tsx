'use client';

import type { StageEvent } from '@/lib/types';

const NODE_TYPE_LABELS: Record<string, string> = {
  Policy: '보험상품',
  Coverage: '보장항목',
  Exclusion: '면책사유',
  Exception: '예외조항',
  Calculation: '계산규칙',
  Rider: '특약',
  Surrender_Value: '해약환급금',
  Dividend_Method: '배당방식',
  Eligibility: '가입조건',
  Regulation: '규제/법률',
  Premium_Discount: '보험료 할인',
  Product_Category: '상품분류',
};

const TEMPLATE_EXPLANATIONS: Record<string, string[]> = {
  coverage_lookup: [
    'Policy 노드에서 시작',
    'HAS_COVERAGE 관계를 따라 보장항목 조회',
    '각 보장항목의 면책사유(EXCLUDED_IF) 확인',
    '면책사유의 예외조항(EXCEPTION_ALLOWED) 확인',
  ],
  dividend_eligibility_check: [
    'Policy 노드에서 시작',
    '배당 구조(NO_DIVIDEND_STRUCTURE) 확인',
    '관련 규제(GOVERNED_BY) 조회',
    '규제 예외사항(EXCEPTIONALLY_ALLOWED) 확인',
  ],
  exclusion_exception_traverse: [
    'Policy 노드에서 시작',
    '면책사유(EXCLUDED_IF) 전체 조회',
    '각 면책사유의 예외조항(EXCEPTION_ALLOWED) 확인',
    '보장항목별 면책/예외 체계 구성',
  ],
  exclusion_full_traverse: [
    'Policy 노드에서 시작',
    '보장항목(HAS_COVERAGE) 조회',
    '면책사유(EXCLUDED_IF) 전체 탐색',
    '예외조항(EXCEPTION_ALLOWED) 확인',
  ],
  surrender_value_lookup: [
    'Policy 노드에서 시작',
    '해약환급금(SURRENDER_PAYS) 노드 조회',
    'label 순으로 정렬해 경과기간별 환급금 데이터 수집',
  ],
  calculation_lookup: [
    'Policy 노드에서 시작',
    '보장/환급금/특약(HAS_COVERAGE·SURRENDER_PAYS·HAS_RIDER) 경유',
    '계산 규칙(CALCULATED_BY) 노드 조회',
  ],
  regulation_lookup: [
    'Policy 노드에서 시작',
    '규제(GOVERNED_BY) 노드 조회',
    '금지행위(STRICTLY_PROHIBITED) 확인',
    '예외적 허용(EXCEPTIONALLY_ALLOWED) 확인',
  ],
  regulation_reverse_lookup: [
    'Regulation 노드에서 시작',
    '해당 규제가 적용되는 Policy 역추적',
    '금지행위 및 예외 허용 범위 확인',
  ],
  rider_lookup: [
    'Policy 노드에서 시작',
    '특약(HAS_RIDER) 노드 조회',
    '각 특약의 보장 내용 확인',
  ],
  eligibility_lookup: [
    'Policy 노드에서 시작',
    '가입조건(REQUIRES_ELIGIBILITY) 노드 조회',
    '나이/건강 조건 등 가입 자격 데이터 수집',
  ],
  discount_eligibility: [
    'Policy 노드에서 시작',
    '할인 조건(HAS_DISCOUNT) 노드 조회',
    '할인율 및 적용 조건 확인',
  ],
  premium_waiver_lookup: [
    'Policy 노드에서 시작',
    '납입면제(WAIVES_PREMIUM) 보장 조회',
    '면책사유(EXCLUDED_IF)와 예외조항(EXCEPTION_ALLOWED) 확인',
  ],
  dividend_portfolio_check: [
    '여러 Policy 노드를 함께 조회',
    '각 상품의 배당 구조(NO_DIVIDEND_STRUCTURE) 확인',
    '포트폴리오 단위 배당 가능 여부 종합',
  ],
  comprehensive_lookup: [
    'Policy 노드에서 시작',
    '보장/면책/예외/계산/환급금 등 전체 관계 탐색',
    '복합 질문에 대한 종합 데이터 수집',
  ],
};

interface TraverseDetailProps {
  stage: StageEvent;
}

export function TraverseDetail({ stage }: TraverseDetailProps) {
  const {
    template, template_label, gremlin_query,
    node_count, edge_count, hops, constraints_found,
    node_types_used, edge_types_used, fallback_used,
  } = stage.data as {
    template: string;
    template_label: string;
    gremlin_query: string;
    node_count: number;
    edge_count: number;
    hops: number;
    constraints_found: number;
    node_types_used: string[];
    edge_types_used: string[];
    fallback_used: boolean;
  };

  const explanation = TEMPLATE_EXPLANATIONS[template];

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">🗺️ Graph Traversal</h3>

      {/* Template info */}
      <div className="rounded-md border p-3 space-y-1 text-xs">
        <div className="font-medium">{template_label}</div>
        <div className="text-muted-foreground font-mono text-[10px]">{template}</div>
      </div>

      {/* Gremlin query + explanation */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">Gremlin Query</div>
        <pre className="text-[10px] font-mono bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
          {gremlin_query}
        </pre>
        {explanation && (
          <div className="space-y-1 pt-1 border-t">
            <div className="text-[10px] font-medium text-muted-foreground">쿼리 해설</div>
            <ol className="space-y-0.5">
              {explanation.map((step, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[11px]">
                  <span className="shrink-0 w-4 h-4 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-medium flex items-center justify-center">
                    {i + 1}
                  </span>
                  <span className="text-muted-foreground">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {/* Results summary */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="grid grid-cols-4 gap-2 text-center text-xs">
          <div>
            <div className="text-lg font-semibold">{node_count}</div>
            <div className="text-muted-foreground">nodes</div>
          </div>
          <div>
            <div className="text-lg font-semibold">{edge_count}</div>
            <div className="text-muted-foreground">edges</div>
          </div>
          <div>
            <div className="text-lg font-semibold">{hops}</div>
            <div className="text-muted-foreground">hops</div>
          </div>
          <div>
            <div className="text-lg font-semibold">{constraints_found}</div>
            <div className="text-muted-foreground">constraints</div>
          </div>
        </div>

        {/* Node type chain with Korean labels */}
        {node_types_used && node_types_used.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 pt-1">
            {node_types_used.map((t, i) => (
              <span key={t} className="inline-flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground text-[10px]">→</span>}
                <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 text-[10px] font-medium">
                  {t}
                  {NODE_TYPE_LABELS[t] && (
                    <span className="text-emerald-500 ml-0.5">({NODE_TYPE_LABELS[t]})</span>
                  )}
                </span>
              </span>
            ))}
          </div>
        )}

        {fallback_used && (
          <div className="text-xs text-amber-600 flex items-center gap-1">
            ⚠️ 폴백 템플릿이 사용되었습니다
          </div>
        )}
      </div>

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">{stage.ms}ms</div>
      )}
    </div>
  );
}
