'use client';

import type { StageEvent, PipelineStageId } from '@/lib/types';
import { DefaultOverview } from './DefaultOverview';
import { SecurityDetail } from './stage-details/SecurityDetail';
import { UnderstandDetail } from './stage-details/UnderstandDetail';
import { ClassifyDetail } from './stage-details/ClassifyDetail';
import { SearchDetail } from './stage-details/SearchDetail';
import { TraverseDetail } from './stage-details/TraverseDetail';
import { GenerateDetail } from './stage-details/GenerateDetail';
import { VerifyDetail } from './stage-details/VerifyDetail';

interface DetailPanelProps {
  stages: StageEvent[];
  selectedStage: PipelineStageId | null;
}

export function DetailPanel({ stages, selectedStage }: DetailPanelProps) {
  if (!selectedStage) {
    return <DefaultOverview />;
  }

  // Find the latest event for the selected stage
  const stageEvent = [...stages].reverse().find((s) => s.stage === selectedStage);

  if (!stageEvent) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground p-4">
        이 단계는 아직 실행되지 않았습니다.
      </div>
    );
  }

  switch (selectedStage) {
    case 'security':
      return <SecurityDetail stage={stageEvent} />;
    case 'understand':
      return <UnderstandDetail stage={stageEvent} />;
    case 'classify':
      return <ClassifyDetail stage={stageEvent} />;
    case 'search':
      return <SearchDetail stage={stageEvent} />;
    case 'traverse':
      return <TraverseDetail stage={stageEvent} />;
    case 'generate':
      return <GenerateDetail stage={stageEvent} />;
    case 'verify':
      return <VerifyDetail stage={stageEvent} />;
    default:
      return <DefaultOverview />;
  }
}
