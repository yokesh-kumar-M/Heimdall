import { NextResponse } from "next/server";

import { backendForward } from "@/lib/heimdall";

export async function POST(req: Request) {
  const body = await req.text();
  try {
    const r = await backendForward("/api/sandbox/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const text = await r.text();
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: { type: "upstream_unreachable", message: (e as Error).message } },
      { status: 502 },
    );
  }
}
