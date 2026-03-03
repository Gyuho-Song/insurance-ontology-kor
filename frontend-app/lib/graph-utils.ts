import type { SubgraphNode, SubgraphEdge } from './types';

// === Cytoscape Element Types ===

export interface CytoscapeNodeData {
  id: string;
  label: string;
  type: string;
  properties: Record<string, unknown>;
}

export interface CytoscapeEdgeData {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
}

export type CytoscapeElement =
  | { data: CytoscapeNodeData }
  | { data: CytoscapeEdgeData };

// === Node Style Types ===

export interface NodeStyle {
  color: string;
  shape: string;
  size: number;
}

export interface EdgeStyle {
  color: string;
  lineStyle: string;
  width: number;
  arrowShape: string;
}

// === Behavior 1: SubgraphNode/Edge → Cytoscape Elements ===

export function subgraphToCytoscapeElements(
  nodes: SubgraphNode[],
  edges: SubgraphEdge[]
): CytoscapeElement[] {
  const cyNodes: CytoscapeElement[] = nodes.map((node) => ({
    data: {
      id: node.id,
      label: node.label,
      type: node.type,
      properties: node.properties,
    },
  }));

  const cyEdges: CytoscapeElement[] = edges.map((edge) => ({
    data: {
      id: `${edge.source}-${edge.target}-${edge.type}`,
      source: edge.source,
      target: edge.target,
      type: edge.type,
      properties: edge.properties,
    },
  }));

  return [...cyNodes, ...cyEdges];
}

// === Behavior 2: Node Type → Style Mapping ===

const NODE_STYLE_MAP: Record<string, NodeStyle> = {
  Policy: { color: '#3B82F6', shape: 'ellipse', size: 60 },
  Coverage: { color: '#22C55E', shape: 'ellipse', size: 50 },
  Exclusion: { color: '#F97316', shape: 'triangle', size: 50 },
  Exception: { color: '#3B82F6', shape: 'diamond', size: 45 },
  Dividend_Method: { color: '#8B5CF6', shape: 'roundrectangle', size: 45 },
  Regulation: { color: '#EF4444', shape: 'octagon', size: 50 },
  Premium_Discount: { color: '#14B8A6', shape: 'hexagon', size: 45 },
  Surrender_Value: { color: '#F59E0B', shape: 'roundrectangle', size: 45 },
  Eligibility: { color: '#EAB308', shape: 'diamond', size: 45 },
  Rider: { color: '#6366F1', shape: 'roundrectangle', size: 45 },
  Product_Category: { color: '#94A3B8', shape: 'ellipse', size: 45 },
  Calculation: { color: '#A855F7', shape: 'star', size: 50 },
  Customer: { color: '#10B981', shape: 'star', size: 55 },
};

const DEFAULT_NODE_STYLE: NodeStyle = { color: '#94A3B8', shape: 'ellipse', size: 40 };

export function getNodeStyle(type: string): NodeStyle {
  return NODE_STYLE_MAP[type] ?? DEFAULT_NODE_STYLE;
}

// === Behavior 3: Edge Style → Style Mapping ===

const EDGE_STYLE_MAP: Record<string, EdgeStyle> = {
  red_blocked: { color: '#EF4444', lineStyle: 'solid', width: 3, arrowShape: 'triangle' },
  green_opened: { color: '#22C55E', lineStyle: 'dashed', width: 2, arrowShape: 'triangle' },
  orange_warning: { color: '#F97316', lineStyle: 'dashed', width: 2, arrowShape: 'triangle' },
  blue_exception: { color: '#3B82F6', lineStyle: 'solid', width: 2, arrowShape: 'triangle' },
  purple_formula: { color: '#A855F7', lineStyle: 'solid', width: 2, arrowShape: 'triangle' },
  default: { color: '#94A3B8', lineStyle: 'solid', width: 1, arrowShape: 'triangle' },
};

export function getEdgeStyle(edgeStyle: string | undefined): EdgeStyle {
  return EDGE_STYLE_MAP[edgeStyle ?? 'default'] ?? EDGE_STYLE_MAP['default'];
}
