import { NextResponse } from "next/server";

import { backendForward } from "@/lib/heimdall";

export const dynamic = "force-dynamic";

export async function PUT(req: Request) {
  const body = await req.text();
  const r = await backendForward("/api/billing/budget", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "Content-Type": "application/json" },
  });
}
