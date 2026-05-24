import { NextResponse } from "next/server";

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  try {
    const r = await fetch(`${BASE}/health`, { cache: "no-store" });
    if (!r.ok) {
      return NextResponse.json({ status: "down", upstream_status: r.status }, { status: 502 });
    }
    return NextResponse.json(await r.json());
  } catch (e) {
    return NextResponse.json(
      { status: "down", error: (e as Error).message },
      { status: 502 }
    );
  }
}
