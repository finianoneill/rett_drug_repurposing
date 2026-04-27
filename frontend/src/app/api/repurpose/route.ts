// Proxies POST /api/repurpose → ${BACKEND_URL}/repurpose, re-streaming the
// SSE body to the browser. Inside Docker Compose, BACKEND_URL is
// http://backend:8000; the browser only ever talks to the frontend container.

import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/repurpose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: request.signal,
    });
  } catch (err) {
    return NextResponse.json(
      { error: `Cannot reach backend at ${backendUrl}: ${(err as Error).message}` },
      { status: 502 },
    );
  }

  if (!upstream.ok && !upstream.body) {
    return NextResponse.json(
      { error: `Backend returned ${upstream.status}` },
      { status: upstream.status },
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
