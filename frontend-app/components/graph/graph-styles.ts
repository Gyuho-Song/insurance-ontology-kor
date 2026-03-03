import { getNodeStyle, getEdgeStyle } from '@/lib/graph-utils';

export interface CytoscapeStyleEntry {
  selector: string;
  style: Record<string, unknown>;
}

const NODE_TYPES = ['Policy', 'Coverage', 'Exclusion', 'Exception', 'Dividend_Method', 'Regulation', 'Premium_Discount', 'Surrender_Value', 'Eligibility', 'Rider', 'Product_Category', 'Calculation', 'Customer'] as const;
const EDGE_STYLES = ['red_blocked', 'green_opened', 'orange_warning', 'blue_exception', 'purple_formula'] as const;

export function buildCytoscapeStylesheet(): CytoscapeStyleEntry[] {
  const styles: CytoscapeStyleEntry[] = [];

  // Base node style
  styles.push({
    selector: 'node',
    style: {
      'label': 'data(label)',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-size': 11,
      'color': '#1e293b',
      'text-wrap': 'ellipsis',
      'text-max-width': '80px',
      'background-color': '#94A3B8',
      'shape': 'ellipse',
      'width': 40,
      'height': 40,
      'border-width': 2,
      'border-color': '#e2e8f0',
    },
  });

  // Per-type node styles
  for (const type of NODE_TYPES) {
    const ns = getNodeStyle(type);
    styles.push({
      selector: `node[type="${type}"]`,
      style: {
        'background-color': ns.color,
        'shape': ns.shape,
        'width': ns.size,
        'height': ns.size,
        'color': '#ffffff',
        'border-color': ns.color,
      },
    });
  }

  // Base edge style
  styles.push({
    selector: 'edge',
    style: {
      'width': 1,
      'line-color': '#94A3B8',
      'target-arrow-color': '#94A3B8',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'arrow-scale': 1.2,
      'label': 'data(type)',
      'font-size': 9,
      'color': '#64748b',
      'text-rotation': 'autorotate',
      'text-margin-y': -8,
    },
  });

  // Edge style classes for traversal events
  for (const edgeStyleName of EDGE_STYLES) {
    const es = getEdgeStyle(edgeStyleName);
    styles.push({
      selector: `edge.${edgeStyleName}`,
      style: {
        'line-color': es.color,
        'target-arrow-color': es.color,
        'width': es.width,
        'line-style': es.lineStyle,
      },
    });
  }

  // Animation class: node glow (activated)
  styles.push({
    selector: 'node.glow',
    style: {
      'border-width': 4,
      'border-color': '#facc15',
      'background-opacity': 1,
      'overlay-color': '#facc15',
      'overlay-padding': 6,
      'overlay-opacity': 0.2,
    },
  });

  // Animation class: node shake (blocked)
  styles.push({
    selector: 'node.shake',
    style: {
      'border-width': 4,
      'border-color': '#EF4444',
      'overlay-color': '#EF4444',
      'overlay-padding': 8,
      'overlay-opacity': 0.3,
    },
  });

  // Animation class: edge highlight (traversed)
  styles.push({
    selector: 'edge.highlight',
    style: {
      'width': 3,
      'line-color': '#facc15',
      'target-arrow-color': '#facc15',
      'overlay-color': '#facc15',
      'overlay-padding': 3,
      'overlay-opacity': 0.15,
    },
  });

  // Animation class: merge-fade (MyData node injected)
  styles.push({
    selector: 'node.merge-fade',
    style: {
      'border-width': 3,
      'border-color': '#10b981',
      'overlay-color': '#10b981',
      'overlay-padding': 6,
      'overlay-opacity': 0.15,
    },
  });

  return styles;
}
