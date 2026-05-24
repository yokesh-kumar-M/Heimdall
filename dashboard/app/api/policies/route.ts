import { NextResponse } from "next/server";

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";
const TOKEN = process.env.HEIMDALL_API_TOKEN ?? "";

function authHeaders(): HeadersInit {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
}

export const dynamic = "force-dynamic";

export async function GET() {
  const r = await fetch(`${BASE}/api/policies`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}
