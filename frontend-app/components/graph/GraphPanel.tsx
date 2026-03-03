'use client';

import { useMemo } from 'react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';
import { GraphPlaceholder } from './GraphPlaceholder';
import { AnimationController } from './AnimationController';
import { PipelineExplorer } from './PipelineExplorer';
import { useGraphAnimation } from '@/lib/useGraphAnimation';
import { subgraphToCytoscapeElements } from '@/lib/graph-utils';
import { useAppContext } from '@/lib/context';
import type { SubgraphNode, SubgraphEdge, TraversalEvent } from '@/lib/types';

// Dynamic import with SSR disabled — react-cytoscapejs depends on window object
const GraphVisualizer = dynamic(
  () => import('./GraphVisualizer').then((mod) => ({ default: mod.GraphVisualizer })),
  { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-muted-foreground">Loading graph...</div> }
);

const EMPTY_TRAVERSAL_EVENTS: TraversalEvent[] = [];

interface GraphPanelProps {
  subgraph?: { nodes: SubgraphNode[]; edges: SubgraphEdge[] };
  traversalEvents?: TraversalEvent[];
}

export function GraphPanel({ subgraph, traversalEvents }: GraphPanelProps) {
  const { pipelineStages, rightPanelTab, setRightPanelTab } = useAppContext();
  const events = traversalEvents ?? EMPTY_TRAVERSAL_EVENTS;

  const {
    status,
    currentHop,
    totalHops,
    speed,
    appliedEvents,
    play,
    pause,
    nextStep,
    reset,
    setSpeed,
  } = useGraphAnimation(events);

  const elements = useMemo(() => {
    if (!subgraph) return [];
    return subgraphToCytoscapeElements(subgraph.nodes, subgraph.edges);
  }, [subgraph]);

  const graphKey = useMemo(() => {
    if (!subgraph || subgraph.nodes.length === 0) return 'empty';
    return subgraph.nodes.map((n) => n.id).sort().join('|');
  }, [subgraph]);

  const hasGraph = subgraph && subgraph.nodes.length > 0;

  return (
    <div className="flex h-full flex-col">
      {/* Tab bar */}
      <div className="flex border-b shrink-0">
        <button
          onClick={() => setRightPanelTab('graph')}
          className={cn(
            'flex-1 px-3 py-2 text-xs font-medium transition-colors',
            rightPanelTab === 'graph'
              ? 'border-b-2 border-foreground text-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Knowledge Graph
        </button>
        <button
          onClick={() => setRightPanelTab('pipeline')}
          className={cn(
            'flex-1 px-3 py-2 text-xs font-medium transition-colors',
            rightPanelTab === 'pipeline'
              ? 'border-b-2 border-foreground text-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Pipeline Explorer
        </button>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {rightPanelTab === 'graph' ? (
          !hasGraph ? (
            <GraphPlaceholder />
          ) : (
            <div className="flex h-full flex-col">
              <div className="flex-1 min-h-0">
                <GraphVisualizer
                  key={graphKey}
                  elements={elements}
                  appliedEvents={appliedEvents}
                />
              </div>
              <div className="border-t p-2">
                <AnimationController
                  status={status}
                  currentHop={currentHop}
                  totalHops={totalHops}
                  speed={speed}
                  onPlay={play}
                  onPause={pause}
                  onNextStep={nextStep}
                  onReset={reset}
                  onSpeedChange={setSpeed}
                />
              </div>
            </div>
          )
        ) : (
          <PipelineExplorer stages={pipelineStages} />
        )}
      </div>
    </div>
  );
}
