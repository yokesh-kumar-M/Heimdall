import { NextResponse } from "next/server";

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";
const TOKEN = process.env.HEIMDALL_API_TOKEN ?? "";

export async function POST(req: Request) {
  const body = await req.text();
  try {
    const r = await fetch(`${BASE}/api/sandbox/evaluate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
      },
      body,
      cache: "no-store",
    });
    const text = await r.text();
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    return NextResponse.json(
      { error: { type: "upstream_unreachable", message: (e as Error).message } },
      { status: 502 }
    );
  }
}
