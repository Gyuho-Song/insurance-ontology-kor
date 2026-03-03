import { render, screen } from '@testing-library/react';
import { AppProvider } from '@/lib/context';
import type { SubgraphNode, SubgraphEdge, TraversalEvent } from '@/lib/types';

// Mock next/dynamic to render the component directly
jest.mock('next/dynamic', () => {
  return function mockDynamic(importFn: () => Promise<{ default: React.ComponentType }>) {
    // Execute import synchronously for test
    let Component: React.ComponentType | null = null;
    importFn().then((mod) => {
      Component = mod.default;
    });
    // Return a wrapper that renders the component or loading state
    const DynamicComponent = (props: Record<string, unknown>) => {
      if (Component) {
        return <Component {...props} />;
      }
      return <div>Loading graph...</div>;
    };
    DynamicComponent.displayName = 'DynamicComponent';
    return DynamicComponent;
  };
});

// Mock GraphVisualizer (avoid Canvas/WebGL)
jest.mock('@/components/graph/GraphVisualizer', () => ({
  GraphVisualizer: (props: Record<string, unknown>) => (
    <div data-testid="graph-visualizer-mock">
      <span data-testid="elements-count">{(props.elements as unknown[])?.length}</span>
    </div>
  ),
}));

// Mock useGraphAnimation
const mockPlay = jest.fn();
const mockPause = jest.fn();
const mockNextStep = jest.fn();
const mockReset = jest.fn();
const mockSetSpeed = jest.fn();

jest.mock('@/lib/useGraphAnimation', () => ({
  useGraphAnimation: () => ({
    status: 'idle' as const,
    currentHop: 0,
    totalHops: 0,
    speed: 1,
    currentEvent: null,
    appliedEvents: [],
    play: mockPlay,
    pause: mockPause,
    nextStep: mockNextStep,
    reset: mockReset,
    setSpeed: mockSetSpeed,
  }),
}));

// Import AFTER mocks
import { GraphPanel } from '@/components/graph/GraphPanel';

const mockNodes: SubgraphNode[] = [
  { id: 'P1', type: 'Policy', label: 'Policy 1', properties: {} },
  { id: 'C1', type: 'Coverage', label: 'Coverage 1', properties: {} },
];

const mockEdges: SubgraphEdge[] = [
  { source: 'P1', target: 'C1', type: 'HAS_COVERAGE', properties: {} },
];

const mockTraversalEvents: TraversalEvent[] = [
  {
    type: 'node_activated',
    hop: 0,
    delay_ms: 0,
    data: { node_id: 'P1', node_type: 'Policy', node_label: 'Policy 1' },
  },
];

describe('GraphPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders GraphPlaceholder when no subgraph provided', () => {
    render(<AppProvider><GraphPanel /></AppProvider>);
    // GraphPlaceholder should be rendered
    expect(screen.getByText('그래프 시각화')).toBeInTheDocument();
    expect(screen.queryByTestId('graph-visualizer-mock')).not.toBeInTheDocument();
  });

  it('renders GraphVisualizer when subgraph provided', () => {
    render(
      <AppProvider>
        <GraphPanel
          subgraph={{ nodes: mockNodes, edges: mockEdges }}
          traversalEvents={mockTraversalEvents}
        />
      </AppProvider>
    );
    expect(screen.getByTestId('graph-visualizer-mock')).toBeInTheDocument();
  });

  it('converts subgraph to Cytoscape elements', () => {
    render(
      <AppProvider>
        <GraphPanel
          subgraph={{ nodes: mockNodes, edges: mockEdges }}
          traversalEvents={mockTraversalEvents}
        />
      </AppProvider>
    );
    // 2 nodes + 1 edge = 3 elements
    expect(screen.getByTestId('elements-count')).toHaveTextContent('3');
  });

  it('renders AnimationController when subgraph provided', () => {
    render(
      <AppProvider>
        <GraphPanel
          subgraph={{ nodes: mockNodes, edges: mockEdges }}
          traversalEvents={mockTraversalEvents}
        />
      </AppProvider>
    );
    // AnimationController should have play/next buttons
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
  });
});
