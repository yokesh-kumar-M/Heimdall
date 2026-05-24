import { NextResponse } from "next/server";

import { backendForward } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

async function proxy(
  method: "PUT" | "DELETE",
  ctx: { params: Promise<{ rule: string }> },
  body?: string,
): Promise<NextResponse> {
  const { rule } = await ctx.params;
  const r = await backendForward(`/api/policies/${encodeURIComponent(rule)}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body,
  });
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function PUT(req: Request, ctx: { params: Promise<{ rule: string }> }) {
  return proxy("PUT", ctx, await req.text());
}

export async function DELETE(_req: Request, ctx: { params: Promise<{ rule: string }> }) {
  return proxy("DELETE", ctx);
}
