/**
 * @jest-environment node
 */
import { GET } from '@/app/api/scenarios/route';

describe('GET /api/scenarios', () => {
  it('should return all 31 curated scenarios', async () => {
    const response = await GET();
    const data = await response.json();
    expect(response.status).toBe(200);
    expect(data.scenarios).toHaveLength(31);
  });

  it('each scenario should have id, title, query, category', async () => {
    const response = await GET();
    const data = await response.json();
    data.scenarios.forEach((s: Record<string, unknown>) => {
      expect(s.id).toBeTruthy();
      expect(s.title).toBeTruthy();
      expect(s.query).toBeTruthy();
      expect(s.category).toBeTruthy();
    });
  });
});
