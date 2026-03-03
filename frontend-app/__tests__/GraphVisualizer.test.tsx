import { render, screen } from '@testing-library/react';
import { GraphVisualizer } from '@/components/graph/GraphVisualizer';
import type { TraversalEvent } from '@/lib/types';
import type { CytoscapeElement } from '@/lib/graph-utils';

// Mock react-cytoscapejs — jsdom cannot render Canvas/WebGL
// Verify props (elements, stylesheet, layout) and animation classes
let lastCyProps: Record<string, unknown> | null = null;

jest.mock('react-cytoscapejs', () => {
  const MockCytoscape = (props: Record<string, unknown>) => {
    lastCyProps = props;
    // Simulate cy ref callback
    if (typeof props.cy === 'function') {
      const mockCy = {
        nodes: jest.fn(() => ({ lock: jest.fn() })),
        on: jest.fn(),
        off: jest.fn(),
        getElementById: jest.fn(() => ({
          addClass: jest.fn(),
          removeClass: jest.fn(),
        })),
      };
      (props.cy as (cy: unknown) => void)(mockCy);
    }
    return <div data-testid="cytoscape-mock">Cytoscape Mock</div>;
  };
  MockCytoscape.displayName = 'CytoscapeComponent';
  return MockCytoscape;
});

jest.mock('cytoscape-fcose', () => {
  return jest.fn();
});

beforeEach(() => {
  lastCyProps = null;
});

const mockElements: CytoscapeElement[] = [
  { data: { id: 'P1', label: 'Policy 1', type: 'Policy', properties: {} } },
  { data: { id: 'C1', label: 'Coverage 1', type: 'Coverage', properties: {} } },
  { data: { id: 'P1-C1-HAS_COVERAGE', source: 'P1', target: 'C1', type: 'HAS_COVERAGE', properties: {} } },
];

const mockAppliedEvents: TraversalEvent[] = [
  {
    type: 'node_activated',
    hop: 0,
    delay_ms: 0,
    data: { node_id: 'P1', node_type: 'Policy', node_label: 'Policy 1' },
  },
  {
    type: 'edge_traversed',
    hop: 1,
    delay_ms: 300,
    data: { node_id: 'C1', node_type: 'Coverage', edge_type: 'HAS_COVERAGE', edge_style: 'default' },
  },
];

describe('GraphVisualizer', () => {
  it('renders Cytoscape component with elements', () => {
    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={[]}
      />
    );
    expect(screen.getByTestId('cytoscape-mock')).toBeInTheDocument();
    expect(lastCyProps).not.toBeNull();
    expect(lastCyProps!.elements).toEqual(mockElements);
  });

  it('passes fcose layout configuration', () => {
    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={[]}
      />
    );
    const layout = lastCyProps!.layout as Record<string, unknown>;
    expect(layout.name).toBe('fcose');
    expect(layout.animate).toBe(false);
  });

  it('passes stylesheet array', () => {
    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={[]}
      />
    );
    expect(Array.isArray(lastCyProps!.stylesheet)).toBe(true);
    expect((lastCyProps!.stylesheet as unknown[]).length).toBeGreaterThan(0);
  });

  it('calls cy ref callback for node locking', () => {
    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={[]}
      />
    );
    expect(lastCyProps!.cy).toBeDefined();
    expect(typeof lastCyProps!.cy).toBe('function');
  });

  it('computes animated elements with glow class for node_activated events', () => {
    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={[mockAppliedEvents[0]]}
      />
    );

    // The elements passed to Cytoscape should have a 'classes' field on the activated node
    const passedElements = lastCyProps!.elements as Array<{ data: { id: string }; classes?: string }>;
    const p1Node = passedElements.find((el) => el.data.id === 'P1');
    expect(p1Node?.classes).toContain('glow');
  });

  it('computes animated elements with highlight class for edge_traversed events', () => {
    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={mockAppliedEvents}
      />
    );

    const passedElements = lastCyProps!.elements as Array<{ data: { id: string }; classes?: string }>;
    // Edge between P1 and C1 should have highlight class
    const edge = passedElements.find((el) => el.data.id === 'P1-C1-HAS_COVERAGE');
    expect(edge?.classes).toContain('highlight');
  });

  it('adds shake class for constraint_blocked events', () => {
    const blockedEvent: TraversalEvent = {
      type: 'constraint_blocked',
      hop: 2,
      delay_ms: 600,
      data: { node_id: 'X1', node_type: 'Exception', edge_style: 'red_blocked', blocked_reason: 'Blocked' },
    };

    const elementsWithBlockedNode: CytoscapeElement[] = [
      ...mockElements,
      { data: { id: 'X1', label: 'Exception X', type: 'Exception', properties: {} } },
    ];

    render(
      <GraphVisualizer
        elements={elementsWithBlockedNode}
        appliedEvents={[...mockAppliedEvents, blockedEvent]}
      />
    );

    const passedElements = lastCyProps!.elements as Array<{ data: { id: string }; classes?: string }>;
    const blockedNode = passedElements.find((el) => el.data.id === 'X1');
    expect(blockedNode?.classes).toContain('shake');
  });

  it('adds edge style class for styled edge_traversed events', () => {
    const styledEdgeEvent: TraversalEvent = {
      type: 'edge_traversed',
      hop: 1,
      delay_ms: 300,
      data: { node_id: 'C1', node_type: 'Coverage', edge_type: 'HAS_COVERAGE', edge_style: 'red_blocked' },
    };

    render(
      <GraphVisualizer
        elements={mockElements}
        appliedEvents={[mockAppliedEvents[0], styledEdgeEvent]}
      />
    );

    const passedElements = lastCyProps!.elements as Array<{ data: { id: string }; classes?: string }>;
    const edge = passedElements.find((el) => el.data.id === 'P1-C1-HAS_COVERAGE');
    expect(edge?.classes).toContain('red_blocked');
  });
});
