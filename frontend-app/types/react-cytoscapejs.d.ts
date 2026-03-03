declare module 'react-cytoscapejs' {
  import type cytoscape from 'cytoscape';

  interface CytoscapeComponentProps {
    elements: Array<Record<string, unknown>>;
    stylesheet?: Array<{ selector: string; style: Record<string, unknown> }>;
    layout?: Record<string, unknown>;
    cy?: (cy: cytoscape.Core) => void;
    style?: React.CSSProperties;
    className?: string;
    userZoomingEnabled?: boolean;
    userPanningEnabled?: boolean;
    boxSelectionEnabled?: boolean;
    [key: string]: unknown;
  }

  const CytoscapeComponent: React.FC<CytoscapeComponentProps>;
  export default CytoscapeComponent;
}
