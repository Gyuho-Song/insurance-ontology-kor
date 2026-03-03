import {
  subgraphToCytoscapeElements,
  getNodeStyle,
  getEdgeStyle,
} from '@/lib/graph-utils';
import type { SubgraphNode, SubgraphEdge } from '@/lib/types';

// === Behavior 1: subgraphToCytoscapeElements ===

describe('subgraphToCytoscapeElements', () => {
  const nodes: SubgraphNode[] = [
    { id: 'Policy#p1', type: 'Policy', label: '종신보험', properties: { code: 'P001' } },
    { id: 'Coverage#c1', type: 'Coverage', label: '제5조①', properties: { article: '제5조' } },
  ];

  const edges: SubgraphEdge[] = [
    { source: 'Policy#p1', target: 'Coverage#c1', type: 'HAS_COVERAGE', properties: {} },
  ];

  it('converts SubgraphNodes to Cytoscape node elements', () => {
    const result = subgraphToCytoscapeElements(nodes, edges);
    const cyNodes = result.filter((el) => 'source' in el.data === false);
    expect(cyNodes).toHaveLength(2);
    expect(cyNodes[0].data).toEqual({
      id: 'Policy#p1',
      label: '종신보험',
      type: 'Policy',
      properties: { code: 'P001' },
    });
  });

  it('converts SubgraphEdges to Cytoscape edge elements with generated id', () => {
    const result = subgraphToCytoscapeElements(nodes, edges);
    const cyEdges = result.filter((el) => 'source' in el.data);
    expect(cyEdges).toHaveLength(1);
    expect(cyEdges[0].data).toEqual({
      id: 'Policy#p1-Coverage#c1-HAS_COVERAGE',
      source: 'Policy#p1',
      target: 'Coverage#c1',
      type: 'HAS_COVERAGE',
      properties: {},
    });
  });

  it('handles empty arrays', () => {
    const result = subgraphToCytoscapeElements([], []);
    expect(result).toEqual([]);
  });

  it('handles multiple edges between same nodes with different types', () => {
    const multiEdges: SubgraphEdge[] = [
      { source: 'A', target: 'B', type: 'REL_1', properties: {} },
      { source: 'A', target: 'B', type: 'REL_2', properties: {} },
    ];
    const result = subgraphToCytoscapeElements([], multiEdges);
    const cyEdges = result.filter((el) => 'source' in el.data);
    expect(cyEdges).toHaveLength(2);
    expect(cyEdges[0].data.id).toBe('A-B-REL_1');
    expect(cyEdges[1].data.id).toBe('A-B-REL_2');
  });
});

// === Behavior 2: getNodeStyle ===

describe('getNodeStyle', () => {
  it('returns blue ellipse 60px for Policy', () => {
    const style = getNodeStyle('Policy');
    expect(style).toEqual({ color: '#3B82F6', shape: 'ellipse', size: 60 });
  });

  it('returns green ellipse 50px for Coverage', () => {
    const style = getNodeStyle('Coverage');
    expect(style).toEqual({ color: '#22C55E', shape: 'ellipse', size: 50 });
  });

  it('returns blue diamond 45px for Exception', () => {
    const style = getNodeStyle('Exception');
    expect(style).toEqual({ color: '#3B82F6', shape: 'diamond', size: 45 });
  });

  it('returns purple star 50px for Calculation', () => {
    const style = getNodeStyle('Calculation');
    expect(style).toEqual({ color: '#A855F7', shape: 'star', size: 50 });
  });

  it('returns orange triangle 50px for Exclusion', () => {
    const style = getNodeStyle('Exclusion');
    expect(style).toEqual({ color: '#F97316', shape: 'triangle', size: 50 });
  });

  it('returns red octagon 50px for Regulation', () => {
    const style = getNodeStyle('Regulation');
    expect(style).toEqual({ color: '#EF4444', shape: 'octagon', size: 50 });
  });

  it('returns slate ellipse 40px for unknown types', () => {
    const style = getNodeStyle('SomeOtherType');
    expect(style).toEqual({ color: '#94A3B8', shape: 'ellipse', size: 40 });
  });
});

// === Behavior 3: getEdgeStyle ===

describe('getEdgeStyle', () => {
  it('returns red solid 3px for red_blocked', () => {
    const style = getEdgeStyle('red_blocked');
    expect(style).toEqual({
      color: '#EF4444',
      lineStyle: 'solid',
      width: 3,
      arrowShape: 'triangle',
    });
  });

  it('returns green dashed 2px for green_opened', () => {
    const style = getEdgeStyle('green_opened');
    expect(style).toEqual({
      color: '#22C55E',
      lineStyle: 'dashed',
      width: 2,
      arrowShape: 'triangle',
    });
  });

  it('returns orange dashed 2px for orange_warning', () => {
    const style = getEdgeStyle('orange_warning');
    expect(style).toEqual({
      color: '#F97316',
      lineStyle: 'dashed',
      width: 2,
      arrowShape: 'triangle',
    });
  });

  it('returns blue solid 2px for blue_exception', () => {
    const style = getEdgeStyle('blue_exception');
    expect(style).toEqual({
      color: '#3B82F6',
      lineStyle: 'solid',
      width: 2,
      arrowShape: 'triangle',
    });
  });

  it('returns purple solid 2px for purple_formula', () => {
    const style = getEdgeStyle('purple_formula');
    expect(style).toEqual({
      color: '#A855F7',
      lineStyle: 'solid',
      width: 2,
      arrowShape: 'triangle',
    });
  });

  it('returns slate solid 1px for default/undefined', () => {
    const style = getEdgeStyle('default');
    expect(style).toEqual({
      color: '#94A3B8',
      lineStyle: 'solid',
      width: 1,
      arrowShape: 'triangle',
    });
    expect(getEdgeStyle(undefined)).toEqual(style);
  });
});
