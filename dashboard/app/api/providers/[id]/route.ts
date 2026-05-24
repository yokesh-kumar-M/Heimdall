import { NextResponse } from "next/server";

import { backendForward } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const r = await backendForward(`/api/providers/${id}`, { method: "DELETE" });
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}
