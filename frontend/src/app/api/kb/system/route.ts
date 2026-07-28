import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:4777';
  const secret = process.env.KB_API_SECRET || '';
  
  const { action } = await req.json();

  try {
    let endpoint = '';
    let method = 'POST';
    
    if (action === 'rebuild') {
      endpoint = '/kb/rebuild';
    } else if (action === 'wipe_memory') {
      endpoint = '/kb/messages';
      method = 'DELETE';
    } else if (action === 'wipe_knowledge') {
      endpoint = '/kb/all';
      method = 'DELETE';
    } else {
      return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
    }

    const res = await fetch(`${backendUrl}${endpoint}`, {
      method,
      headers: {
        'Authorization': `Bearer ${secret}`,
      },
    });

    if (!res.ok) {
      return NextResponse.json({ error: 'Action failed' }, { status: res.status });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to connect to backend' }, { status: 500 });
  }
}
