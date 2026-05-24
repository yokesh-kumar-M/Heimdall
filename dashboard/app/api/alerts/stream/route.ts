import type { NextRequest } from "next/server";

import { backendForward } from "@/lib/heimdall";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const revalidate = 0;

export async function GET(req: NextRequest) {
  const upstream = await backendForward("/api/alerts/stream", {
    headers: { Accept: "text/event-stream" },
    signal: req.signal,
  }).catch(
    (e) =>
      new Response(
        `event: error\ndata: ${JSON.stringify({ message: (e as Error).message })}\n\n`,
        { status: 502, headers: { "Content-Type": "text/event-stream" } },
      ),
  );

  if (!upstream.ok || !upstream.body) {
    return new Response(
      `event: error\ndata: ${JSON.stringify({ status: upstream.status })}\n\n`,
      {
        status: upstream.status || 502,
        headers: { "Content-Type": "text/event-stream" },
      },
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
