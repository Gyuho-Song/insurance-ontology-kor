'use client';

import type { StageEvent } from '@/lib/types';

const INTENT_INFO: Record<string, { desc: string; template: string; targets: string[] }> = {
  coverage_inquiry: {
    desc: '보장항목, 지급사유, 보장금액 관련 질문',
    template: 'coverage_lookup',
    targets: ['Coverage', 'Exclusion', 'Exception'],
  },
  dividend_check: {
    desc: '배당 가능 여부 및 배당 방식 확인',
    template: 'dividend_eligibility_check',
    targets: ['Dividend_Method', 'Regulation'],
  },
  exclusion_exception: {
    desc: '면책사유와 예외 인정 조건 확인',
    template: 'exclusion_exception_traverse',
    targets: ['Exclusion', 'Exception'],
  },
  surrender_value: {
    desc: '해지 시 환급금 계산 방식 및 금액 조회',
    template: 'surrender_value_traverse',
    targets: ['Surrender_Value', 'Calculation'],
  },
  discount_eligibility: {
    desc: '할인/우대 조건 및 적용 가능 여부 확인',
    template: 'discount_eligibility_traverse',
    targets: ['Eligibility'],
  },
  regulation_inquiry: {
    desc: '보험업법, 감독규정 등 규제 관련 질문',
    template: 'regulation_lookup',
    targets: ['Regulation'],
  },
  loan_inquiry: {
    desc: '보험계약 대출 조건 및 이율 확인',
    template: 'loan_traverse',
    targets: ['Calculation'],
  },
  premium_waiver: {
    desc: '보험료 납입면제 사유 및 조건 조회',
    template: 'premium_waiver_traverse',
    targets: ['Coverage', 'Exclusion'],
  },
  policy_comparison: {
    desc: '복수 상품 간 보장항목/조건 비교',
    template: 'comparison_traverse',
    targets: ['Policy', 'Coverage'],
  },
  calculation_inquiry: {
    desc: '보험료, 환급금, 보험가격지수 등 계산 방식 확인',
    template: 'calculation_traverse',
    targets: ['Calculation'],
  },
  eligibility_inquiry: {
    desc: '가입 나이, 건강 조건 등 가입 자격 확인',
    template: 'eligibility_traverse',
    targets: ['Eligibility'],
  },
  rider_inquiry: {
    desc: '특약 종류, 보장 내용 및 가입 조건 조회',
    template: 'rider_traverse',
    targets: ['Rider', 'Coverage'],
  },
  general_inquiry: {
    desc: '일반적인 보험 관련 질문',
    template: 'comprehensive_lookup',
    targets: ['Policy'],
  },
};

const ENTITY_ROLE: Record<string, string> = {
  product_name: '벡터 검색 필터링에 사용',
  coverage_type: '보장 유형 매칭에 사용',
  regulation_name: '규제 노드 직접 조회에 사용',
};

interface ClassifyDetailProps {
  stage: StageEvent;
}

export function ClassifyDetail({ stage }: ClassifyDetailProps) {
  const { intent, intent_label, confidence, entities } = stage.data as {
    intent: string;
    intent_label: string;
    confidence: number;
    entities: { value: string; type: string }[];
  };

  const pct = Math.round((confidence ?? 0) * 100);
  const info = INTENT_INFO[intent];

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">🎯 Intent Classification</h3>

      {/* Intent + confidence */}
      <div className="rounded-md border p-3 space-y-2">
        <div className="text-sm font-medium">{intent_label}</div>
        {info && (
          <div className="text-xs text-muted-foreground">{info.desc}</div>
        )}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs font-medium w-10 text-right">{pct}%</span>
        </div>
      </div>

      {/* Data flow: intent → template → target nodes */}
      {info && (
        <div className="rounded-md border p-3 space-y-2">
          <div className="text-xs font-medium text-muted-foreground">다음 단계 연결</div>
          <div className="flex items-center gap-1.5 flex-wrap text-xs">
            <span className="rounded bg-blue-50 border border-blue-200 px-1.5 py-0.5 font-medium text-blue-700">
              {intent_label}
            </span>
            <span className="text-muted-foreground">→</span>
            <span className="rounded bg-violet-50 border border-violet-200 px-1.5 py-0.5 font-medium text-violet-700">
              {info.template}
            </span>
            <span className="text-muted-foreground">→</span>
            {info.targets.map((t, i) => (
              <span key={t} className="inline-flex items-center gap-1">
                {i > 0 && <span className="text-muted-foreground">,</span>}
                <span className="rounded bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 font-medium text-emerald-700">
                  {t}
                </span>
              </span>
            ))}
          </div>
          <div className="text-[10px] text-muted-foreground">
            의도 분류 결과가 그래프 탐색 템플릿과 조회 대상 노드를 결정합니다
          </div>
        </div>
      )}

      {/* Entities with role descriptions */}
      {entities && entities.length > 0 && (
        <div className="rounded-md border p-3 space-y-2">
          <div className="text-xs font-medium text-muted-foreground">추출된 엔티티</div>
          <div className="space-y-1.5">
            {entities.map((e, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs shrink-0">
                  <span className="font-medium">{e.value}</span>
                  <span className="text-blue-400">|</span>
                  <span className="text-muted-foreground">{e.type}</span>
                </span>
                {ENTITY_ROLE[e.type] && (
                  <span className="text-[10px] text-muted-foreground pt-0.5">
                    → {ENTITY_ROLE[e.type]}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">{stage.ms}ms</div>
      )}
    </div>
  );
}
