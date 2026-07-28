import { NextRequest, NextResponse } from 'next/server';

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:4777';
  const secret = process.env.KB_API_SECRET || '';
  
  const { id } = await params;

  try {
    const res = await fetch(`${backendUrl}/kb/${id}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${secret}`,
      },
    });

    if (!res.ok) {
      return NextResponse.json({ error: 'Failed to delete document' }, { status: res.status });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:4777';
  const secret = process.env.KB_API_SECRET || '';
  const { id } = await params;
  
  try {
    const body = await req.json();
    const res = await fetch(`${backendUrl}/kb/${id}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${secret}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      return NextResponse.json({ error: 'Failed to rename document' }, { status: res.status });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
