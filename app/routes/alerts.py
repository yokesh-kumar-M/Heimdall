"""Alerts read API + SSE live feed — tenant-scoped."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_dashboard_ctx
from app.db import get_session
from app.repositories.telemetry import TelemetryRepo
from app.telemetry.bus import AlertBus

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get("/alerts", summary="List recent blocked-request incidents.")
async def list_alerts(
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    layer: str | None = Query(None),
    category: str | None = Query(None),
) -> dict[str, Any]:
    repo = TelemetryRepo(session)
    rows = await repo.list_alerts(
        tenant_id=ctx.tenant_id, limit=limit, offset=offset, layer=layer, category=category
    )
    return {"count": len(rows), "limit": limit, "offset": offset, "alerts": rows}


@router.get("/alerts/stats", summary="Aggregate counts.")
async def alerts_stats(
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = TelemetryRepo(session)
    return await repo.stats(tenant_id=ctx.tenant_id)


@router.get(
    "/alerts/stream",
    summary="SSE feed of live block/pass events for the current tenant.",
)
async def stream_alerts(
    request: Request,
    ctx: TenantContext = Depends(get_dashboard_ctx),
) -> StreamingResponse:
    bus: AlertBus = request.app.state.bus

    async def gen():
        queue = await bus.subscribe()
        try:
            yield (f"event: hello\ndata: {json.dumps({'subscribers': bus.subscriber_count})}\n\n").encode()
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                # Filter: only emit events for THIS tenant. Cross-tenant traffic
                # is in the same process but never visible to the wrong viewer.
                if event.get("tenant_id") and event["tenant_id"] != ctx.tenant_id:
                    continue
                yield (f"event: alert\ndata: {json.dumps(event)}\n\n").encode()
        finally:
            await bus.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/alerts/{alert_id}",
    summary="Fetch one alert with sibling violations from the same incident.",
)
async def get_alert(
    alert_id: int,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = TelemetryRepo(session)
    incident = await repo.get_incident(tenant_id=ctx.tenant_id, alert_id=alert_id)
    if not incident or not incident.get("violations"):
        raise HTTPException(status_code=404, detail="Alert not found")
    return incident


class FeedbackPayload(BaseModel):
    feedback_type: Literal["false_positive", "confirmed", "note"]
    note: str | None = Field(None, max_length=2000)


@router.post(
    "/alerts/{alert_id}/feedback",
    summary="Record analyst feedback (may auto-suppress a noisy rule).",
)
async def post_feedback(
    request: Request,
    alert_id: int,
    payload: FeedbackPayload,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = TelemetryRepo(session)
    incident = await repo.get_incident(tenant_id=ctx.tenant_id, alert_id=alert_id)
    if not incident or not incident.get("violations"):
        raise HTTPException(status_code=404, detail="Alert not found")

    feedback_id, rule, fp_count = await repo.record_feedback(
        tenant_id=ctx.tenant_id,
        alert_id=alert_id,
        feedback_type=payload.feedback_type,
        note=payload.note,
    )

    auto_suppressed = None
    if rule:
        policy = request.app.state.policy
        updated = await policy.on_feedback(
            tenant_id=ctx.tenant_id,
            rule=rule,
            feedback_type=payload.feedback_type,
            fp_count=fp_count,
            session=session,
        )
        if updated and updated.get("auto_suppressed"):
            auto_suppressed = updated

    return {
        "feedback_id": feedback_id,
        "alert_id": alert_id,
        "rule": rule,
        "fp_count": fp_count,
        "auto_suppressed": auto_suppressed,
    }
