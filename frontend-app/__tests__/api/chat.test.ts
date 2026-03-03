/**
 * @jest-environment node
 */
import { POST } from '@/app/api/chat/route';
import { NextRequest } from 'next/server';

// Mock global fetch for backend calls
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe('POST /api/chat', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  it('should forward messages to the backend', async () => {
    const mockBody = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('0:"Hello"\n'));
        controller.close();
      },
    });
    mockFetch.mockResolvedValue({
      ok: true,
      body: mockBody,
    });

    const request = new NextRequest('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: '테스트 질문' }],
        persona: 'presenter',
        ragMode: 'graphrag',
      }),
    });

    const response = await POST(request);
    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toContain('text/plain');

    // Verify backend was called with correct payload
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/v1/chat');
    const body = JSON.parse(options.body);
    expect(body.persona).toBe('presenter');
    expect(body.messages).toEqual([{ role: 'user', content: '테스트 질문' }]);
  });

  it('should include mydata_consent when provided', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      body: new ReadableStream({ start(c) { c.close(); } }),
    });

    const request = new NextRequest('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: '내 보험 조회' }],
        persona: 'presenter',
        mydataConsent: { customer_id: 'CUSTOMER_PARK', consented: true },
        ragMode: 'graphrag',
      }),
    });

    await POST(request);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.mydata_consent).toEqual({ customer_id: 'CUSTOMER_PARK', consented: true });
  });

  it('should return error when backend is unreachable', async () => {
    mockFetch.mockRejectedValue(new Error('Connection refused'));

    const request = new NextRequest('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: 'test' }],
        persona: 'presenter',
      }),
    });

    const response = await POST(request);
    expect(response.status).toBe(503);
  });

  it('should return backend error status when backend returns error', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error'),
    });

    const request = new NextRequest('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: [{ role: 'user', content: 'test' }],
        persona: 'presenter',
      }),
    });

    const response = await POST(request);
    expect(response.status).toBe(500);
  });
});
