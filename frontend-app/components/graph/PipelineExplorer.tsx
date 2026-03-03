'use client';

import { useState } from 'react';
import type { StageEvent, PipelineStageId } from '@/lib/types';
import { PipelineTrack } from './PipelineTrack';
import { DetailPanel } from './DetailPanel';

interface PipelineExplorerProps {
  stages: StageEvent[];
}

export function PipelineExplorer({ stages }: PipelineExplorerProps) {
  const [selectedStage, setSelectedStage] = useState<PipelineStageId | null>(null);

  return (
    <div className="flex h-full flex-col">
      {/* Fixed top track */}
      <div className="shrink-0 border-b">
        <PipelineTrack
          stages={stages}
          onStageSelect={setSelectedStage}
          selectedStage={selectedStage}
        />
      </div>

      {/* Scrollable detail panel */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <DetailPanel stages={stages} selectedStage={selectedStage} />
      </div>
    </div>
  );
}
