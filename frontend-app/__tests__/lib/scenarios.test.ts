import { scenarios, getScenariosByCategory, getScenarioById, CATEGORY_LABELS, CATEGORY_ORDER } from '@/lib/scenarios';
import type { Scenario } from '@/lib/types';

describe('scenarios', () => {
  it('should have 31 curated scenarios', () => {
    expect(scenarios).toHaveLength(31);
  });

  it('each scenario should have required fields', () => {
    scenarios.forEach((scenario: Scenario) => {
      expect(scenario.id).toBeTruthy();
      expect(scenario.title).toBeTruthy();
      expect(scenario.query).toBeTruthy();
      expect(CATEGORY_ORDER).toContain(scenario.category);
    });
  });

  it('should have unique IDs', () => {
    const ids = scenarios.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('all categories should have labels', () => {
    CATEGORY_ORDER.forEach((cat) => {
      expect(CATEGORY_LABELS[cat]).toBeTruthy();
    });
  });

  describe('getScenariosByCategory', () => {
    it('should group scenarios by category', () => {
      const map = getScenariosByCategory();
      let total = 0;
      map.forEach((items) => {
        total += items.length;
        items.forEach((s) => expect(CATEGORY_ORDER).toContain(s.category));
      });
      expect(total).toBe(31);
    });

    it('should cover 15 categories', () => {
      const map = getScenariosByCategory();
      expect(map.size).toBe(15);
    });
  });

  describe('getScenarioById', () => {
    it('should find scenario by ID', () => {
      expect(getScenarioById('A01')?.title).toBe('시그니처H암보험 보장항목');
    });

    it('should return undefined for unknown ID', () => {
      expect(getScenarioById('Z99')).toBeUndefined();
    });
  });
});
