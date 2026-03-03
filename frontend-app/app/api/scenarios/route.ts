import { NextResponse } from 'next/server';
import { scenarios } from '@/lib/scenarios';

export async function GET() {
  return NextResponse.json({ scenarios });
}
