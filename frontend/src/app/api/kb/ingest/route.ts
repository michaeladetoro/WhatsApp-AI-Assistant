import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:4777';
  const secret = process.env.KB_API_SECRET || '';

  try {
    const formData = await req.formData();
    const res = await fetch(`${backendUrl}/kb/ingest`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${secret}`,
      },
      body: formData,
    });

    if (!res.ok) {
      const errorText = await res.text();
      return NextResponse.json({ error: errorText }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: 'Failed to upload document' }, { status: 500 });
  }
}
