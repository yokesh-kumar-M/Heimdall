import { NextResponse } from "next/server";

const BASE = process.env.HEIMDALL_API_URL ?? "http://127.0.0.1:8000";
const TOKEN = process.env.HEIMDALL_API_TOKEN ?? "";

function authHeaders(): HeadersInit {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
}

export const dynamic = "force-dynamic";

async function proxy(
  method: "PUT" | "DELETE",
  ctx: { params: Promise<{ rule: string }> },
  body?: string
): Promise<NextResponse> {
  const { rule } = await ctx.params;
  const r = await fetch(`${BASE}/api/policies/${encodeURIComponent(rule)}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body,
    cache: "no-store",
  });
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function PUT(
  req: Request,
  ctx: { params: Promise<{ rule: string }> }
) {
  return proxy("PUT", ctx, await req.text());
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ rule: string }> }
) {
  return proxy("DELETE", ctx);
}
