import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.GRAPHRAG_BACKEND_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { messages, persona, mydataConsent, ragMode } = body;

  return handleLiveMode(messages, persona, mydataConsent, ragMode);
}

async function handleLiveMode(
  messages: Array<{ role: string; content: string }>,
  persona: string,
  mydataConsent?: { customer_id: string; consented: boolean } | null,
  ragMode?: string,
): Promise<Response> {
  try {
    // Strip annotations/parts from messages — backend only needs role + content
    const cleanMessages = messages.map((msg: Record<string, unknown>) => ({
      role: msg.role,
      content: msg.content,
    }));
    const requestBody: Record<string, unknown> = { messages: cleanMessages, persona };
    if (mydataConsent) {
      requestBody.mydata_consent = mydataConsent;
    }
    if (ragMode) {
      requestBody.rag_mode = ragMode;
    }
    const backendResponse = await fetch(`${BACKEND_URL}/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      return NextResponse.json(
        { error: `백엔드 오류: ${backendResponse.status} - ${errorText}` },
        { status: backendResponse.status }
      );
    }

    // Pass through the Data Stream Protocol response from FastAPI
    return new Response(backendResponse.body, {
      headers: {
        'Content-Type': 'text/plain; charset=utf-8',
        'Transfer-Encoding': 'chunked',
        'x-vercel-ai-data-stream': 'v1',
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: '백엔드 서비스에 연결할 수 없습니다.' },
      { status: 503 }
    );
  }
}
