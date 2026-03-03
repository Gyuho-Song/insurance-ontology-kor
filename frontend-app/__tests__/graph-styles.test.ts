import { buildCytoscapeStylesheet } from '@/components/graph/graph-styles';

describe('buildCytoscapeStylesheet', () => {
  const stylesheet = buildCytoscapeStylesheet();

  it('returns an array of style objects', () => {
    expect(Array.isArray(stylesheet)).toBe(true);
    expect(stylesheet.length).toBeGreaterThan(0);
  });

  it('includes a base node style with label', () => {
    const nodeStyle = stylesheet.find((s) => s.selector === 'node');
    expect(nodeStyle).toBeDefined();
    expect(nodeStyle!.style['label']).toBe('data(label)');
    expect(nodeStyle!.style['text-valign']).toBe('center');
  });

  it('includes styles for each node type (Policy, Coverage, Exclusion, Exception, Dividend_Method, Regulation, Premium_Discount, Surrender_Value, Eligibility, Rider, Product_Category, Calculation, Customer)', () => {
    const types = ['Policy', 'Coverage', 'Exclusion', 'Exception', 'Dividend_Method', 'Regulation', 'Premium_Discount', 'Surrender_Value', 'Eligibility', 'Rider', 'Product_Category', 'Calculation', 'Customer'];
    for (const type of types) {
      const typeStyle = stylesheet.find((s) => s.selector === `node[type="${type}"]`);
      expect(typeStyle).toBeDefined();
      expect(typeStyle!.style['background-color']).toBeDefined();
      expect(typeStyle!.style['shape']).toBeDefined();
      expect(typeStyle!.style['width']).toBeDefined();
      expect(typeStyle!.style['height']).toBeDefined();
    }
  });

  it('includes Policy node with blue color and ellipse shape', () => {
    const policyStyle = stylesheet.find((s) => s.selector === 'node[type="Policy"]');
    expect(policyStyle!.style['background-color']).toBe('#3B82F6');
    expect(policyStyle!.style['shape']).toBe('ellipse');
    expect(policyStyle!.style['width']).toBe(60);
  });

  it('includes base edge style with arrow', () => {
    const edgeStyle = stylesheet.find((s) => s.selector === 'edge');
    expect(edgeStyle).toBeDefined();
    expect(edgeStyle!.style['target-arrow-shape']).toBe('triangle');
    expect(edgeStyle!.style['curve-style']).toBe('bezier');
  });

  it('includes animation class styles (glow, highlight, shake)', () => {
    const glowStyle = stylesheet.find((s) => s.selector === 'node.glow');
    expect(glowStyle).toBeDefined();

    const highlightStyle = stylesheet.find((s) => s.selector === 'edge.highlight');
    expect(highlightStyle).toBeDefined();

    const shakeStyle = stylesheet.find((s) => s.selector === 'node.shake');
    expect(shakeStyle).toBeDefined();
  });

  it('includes edge style classes for traversal events', () => {
    const blockedStyle = stylesheet.find((s) => s.selector === 'edge.red_blocked');
    expect(blockedStyle).toBeDefined();
    expect(blockedStyle!.style['line-color']).toBe('#EF4444');

    const openedStyle = stylesheet.find((s) => s.selector === 'edge.green_opened');
    expect(openedStyle).toBeDefined();
    expect(openedStyle!.style['line-color']).toBe('#22C55E');

    const formulaStyle = stylesheet.find((s) => s.selector === 'edge.purple_formula');
    expect(formulaStyle).toBeDefined();
    expect(formulaStyle!.style['line-color']).toBe('#A855F7');
  });
});
