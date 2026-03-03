import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.GRAPHRAG_BACKEND_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const customerId = request.nextUrl.searchParams.get('customer_id') || '';
    const res = await fetch(
      `${BACKEND_URL}/v1/mydata/contracts?customer_id=${encodeURIComponent(customerId)}`
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: '백엔드 서비스에 연결할 수 없습니다.' },
      { status: 503 }
    );
  }
}
