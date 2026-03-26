/**
 * SSE 전용 프록시 — Next.js rewrite 프록시의 SSE 버퍼링 문제 우회
 *
 * POST /api/sse/mission → 백엔드 POST /mission (SSE 응답)
 * GET  /api/sse/mission/{id}/events → 백엔드 GET /mission/{id}/events
 * POST /api/sse/chat → 백엔드 POST /chat
 * POST /api/sse/chat/smart → 백엔드 POST /chat/smart
 * POST /api/sse/chat/agent/{name} → 백엔드 POST /chat/agent/{name}
 */

const BACKEND = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:19000';

async function proxySSE(req: Request, path: string): Promise<Response> {
  const url = `${BACKEND}/${path}`;

  const fetchOpts: RequestInit = {
    method: req.method,
    headers: { 'Content-Type': 'application/json' },
  };

  if (req.method === 'POST') {
    fetchOpts.body = await req.text();
  }

  const upstream = await fetch(url, fetchOpts);

  if (!upstream.ok || !upstream.body) {
    return new Response(upstream.body, { status: upstream.status });
  }

  // SSE 응답을 버퍼링 없이 스트리밍
  return new Response(upstream.body as ReadableStream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

export async function GET(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxySSE(req, path.join('/'));
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  return proxySSE(req, path.join('/'));
}

// Edge runtime: 버퍼링 없는 스트리밍 보장
export const runtime = 'edge';
