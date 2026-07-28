import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:4777';
  const secret = process.env.KB_API_SECRET || '';

  try {
    const res = await fetch(`${backendUrl}/kb/analytics`, {
      headers: {
        'Authorization': `Bearer ${secret}`,
      },
      // Ensure fresh data
      cache: 'no-store',
    });

    if (!res.ok) {
      return NextResponse.json({ error: 'Failed to fetch analytics' }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
