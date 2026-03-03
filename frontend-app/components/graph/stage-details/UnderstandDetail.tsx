'use client';

import type { StageEvent } from '@/lib/types';

interface UnderstandDetailProps {
  stage: StageEvent;
}

export function UnderstandDetail({ stage }: UnderstandDetailProps) {
  const { original_query, expanded_query, added_synonyms, embedding_model, embedding_dims } =
    stage.data as {
      original_query: string;
      expanded_query: string;
      added_synonyms: { original: string; expanded: string }[];
      embedding_model: string;
      embedding_dims: number;
    };

  return (
    <div className="space-y-3 p-4">
      <h3 className="text-sm font-semibold flex items-center gap-2">📖 Query Understanding</h3>

      <div className="rounded-md border p-3 space-y-2 text-xs">
        <div className="font-medium text-muted-foreground">용어 확장</div>
        <div>
          <span className="text-muted-foreground">원본: </span>
          <span>{original_query}</span>
        </div>
        <div>
          <span className="text-muted-foreground">확장: </span>
          <span>{expanded_query}</span>
        </div>
        {added_synonyms && added_synonyms.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {added_synonyms.map((s, i) => (
              <span key={i} className="rounded bg-blue-100 text-blue-700 px-1.5 py-0.5 text-[10px]">
                {s.original} → {s.expanded}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-md border p-3 text-xs space-y-1">
        <div className="font-medium text-muted-foreground">임베딩</div>
        <div>{embedding_model} → {embedding_dims}차원 벡터 생성</div>
        <div className="text-muted-foreground">이 벡터는 의도 분류와 벡터 검색에서 재사용됩니다</div>
      </div>

      {stage.ms !== undefined && (
        <div className="text-right text-xs text-muted-foreground">{stage.ms}ms</div>
      )}
    </div>
  );
}
