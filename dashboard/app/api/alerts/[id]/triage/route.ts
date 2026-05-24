import { NextResponse } from "next/server";

import { backendForward } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const r = await backendForward(`/api/alerts/${id}/triage`, {
    method: "POST",
  });
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}
