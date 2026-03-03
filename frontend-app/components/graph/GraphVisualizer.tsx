'use client';

import { useRef, useMemo, useCallback } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { buildCytoscapeStylesheet } from './graph-styles';
import type { CytoscapeElement, CytoscapeEdgeData } from '@/lib/graph-utils';
import type { TraversalEvent } from '@/lib/types';

function isEdgeData(data: unknown): data is CytoscapeEdgeData {
  return typeof data === 'object' && data !== null && 'source' in data;
}

// Register fcose layout
try {
  cytoscape.use(fcose);
} catch {
  // Already registered
}

interface GraphVisualizerProps {
  elements: CytoscapeElement[];
  appliedEvents: TraversalEvent[];
}

const LAYOUT_CONFIG = {
  name: 'fcose',
  animate: false,
  quality: 'default',
  randomize: true,
  padding: 30,
  nodeDimensionsIncludeLabels: true,
};

/**
 * Compute animation classes for elements based on applied traversal events.
 *
 * - node_activated → 'glow' on node
 * - edge_traversed → 'highlight' on traversed edge + 'glow' on target node + edge_style class
 * - constraint_blocked → 'shake' on node + 'red_blocked' on edge
 * - constraint_opened → 'glow' on node + edge_style class on edge
 */
function computeAnimatedElements(
  elements: CytoscapeElement[],
  appliedEvents: TraversalEvent[]
): Array<CytoscapeElement & { classes?: string }> {
  // Collect classes per element id
  const classMap = new Map<string, Set<string>>();

  const addClass = (id: string, cls: string) => {
    if (!classMap.has(id)) classMap.set(id, new Set());
    classMap.get(id)!.add(cls);
  };

  for (const event of appliedEvents) {
    const nodeId = event.data.node_id;

    switch (event.type) {
      case 'node_activated':
        if (nodeId) addClass(nodeId, 'glow');
        break;

      case 'edge_traversed':
        if (nodeId) addClass(nodeId, 'glow');
        // Find matching edge and add highlight + style class
        if (nodeId && event.data.edge_type) {
          for (const el of elements) {
            if (isEdgeData(el.data) && el.data.target === nodeId && el.data.type === event.data.edge_type) {
              addClass(el.data.id, 'highlight');
              if (event.data.edge_style && event.data.edge_style !== 'default') {
                addClass(el.data.id, event.data.edge_style);
              }
            }
          }
        }
        break;

      case 'constraint_blocked':
        if (nodeId) addClass(nodeId, 'shake');
        if (nodeId && event.data.edge_style) {
          for (const el of elements) {
            if (isEdgeData(el.data) && el.data.target === nodeId) {
              addClass(el.data.id, event.data.edge_style);
            }
          }
        }
        break;

      case 'constraint_opened':
        if (nodeId) addClass(nodeId, 'glow');
        if (nodeId && event.data.edge_style) {
          for (const el of elements) {
            if (isEdgeData(el.data) && el.data.target === nodeId) {
              addClass(el.data.id, event.data.edge_style);
            }
          }
        }
        break;

      case 'merge_node_added':
        if (nodeId) addClass(nodeId, 'merge-fade');
        // Highlight OWNS edges connected to this node
        if (nodeId) {
          for (const el of elements) {
            if (isEdgeData(el.data) && (el.data.source === nodeId || el.data.target === nodeId) && el.data.type === 'OWNS') {
              addClass(el.data.id, 'highlight');
            }
          }
        }
        break;
    }
  }

  // Merge classes into elements
  return elements.map((el) => {
    const id = el.data.id;
    const classes = classMap.get(id);
    if (classes && classes.size > 0) {
      return { ...el, classes: Array.from(classes).join(' ') };
    }
    return el;
  });
}

export function GraphVisualizer({ elements, appliedEvents }: GraphVisualizerProps) {
  const cyRef = useRef<cytoscape.Core | null>(null);

  const stylesheet = useMemo(() => buildCytoscapeStylesheet(), []);

  const animatedElements = useMemo(
    () => computeAnimatedElements(elements, appliedEvents),
    [elements, appliedEvents]
  );

  const handleCyRef = useCallback((cy: cytoscape.Core) => {
    cyRef.current = cy;

    // Lock all nodes after layout completes to prevent jitter during animation
    cy.on('layoutstop', () => {
      cy.nodes().lock();
    });
  }, []);

  return (
    <div className="h-full w-full" data-testid="graph-visualizer">
      <CytoscapeComponent
        elements={animatedElements}
        stylesheet={stylesheet}
        layout={LAYOUT_CONFIG}
        cy={handleCyRef}
        style={{ width: '100%', height: '100%' }}
        userZoomingEnabled={true}
        userPanningEnabled={true}
        boxSelectionEnabled={false}
      />
    </div>
  );
}
