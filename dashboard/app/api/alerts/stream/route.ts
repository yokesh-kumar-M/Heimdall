import type { NextRequest } from "next/server";

// SSE proxy. The browser's EventSource hits this route, we open a long-lived
// fetch to the FastAPI /api/alerts/stream and pipe its bytes through. Forcing
// the route dynamic + streaming the body keeps Next from buffering.
export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const revalidate = 0;

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";
const TOKEN = process.env.HEIMDALL_API_TOKEN ?? "";

export async function GET(req: NextRequest) {
  const upstream = await fetch(`${BASE}/api/alerts/stream`, {
    headers: {
      Accept: "text/event-stream",
      ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
    },
    // Propagate browser-side cancellation to the upstream connection so the
    // FastAPI generator unsubscribes from the AlertBus promptly.
    signal: req.signal,
    cache: "no-store",
  }).catch((e) => {
    return new Response(
      `event: error\ndata: ${JSON.stringify({ message: (e as Error).message })}\n\n`,
      { status: 502, headers: { "Content-Type": "text/event-stream" } }
    );
  });

  if (!upstream.ok || !upstream.body) {
    return new Response(
      `event: error\ndata: ${JSON.stringify({ status: upstream.status })}\n\n`,
      {
        status: upstream.status || 502,
        headers: { "Content-Type": "text/event-stream" },
      }
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
