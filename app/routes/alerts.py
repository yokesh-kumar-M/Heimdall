from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.telemetry.bus import AlertBus

router = APIRouter(prefix="/api", tags=["telemetry"])


@router.get(
    "/alerts",
    summary="List blocked-request incidents (Phase 4 telemetry).",
)
async def list_alerts(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    layer: str | None = Query(None, description="Filter: deterministic | semantic"),
    category: str | None = Query(
        None, description="OWASP category, e.g. 'LLM01: Prompt Injection'"
    ),
) -> dict[str, Any]:
    store = request.app.state.telemetry
    rows = await store.list_alerts(
        limit=limit, offset=offset, layer=layer, category=category
    )
    return {"count": len(rows), "limit": limit, "offset": offset, "alerts": rows}


@router.get(
    "/alerts/stats",
    summary="Aggregate counts: total blocks, by layer, by OWASP category.",
)
async def alerts_stats(request: Request) -> dict[str, Any]:
    store = request.app.state.telemetry
    return await store.stats()


@router.get(
    "/alerts/stream",
    summary=(
        "Server-Sent Events feed of live proxy activity (block + pass). "
        "Used by the dashboard live tail; not durable — clients resubscribe."
    ),
)
async def stream_alerts(request: Request) -> StreamingResponse:
    bus: AlertBus = request.app.state.bus

    async def gen():
        queue = await bus.subscribe()
        try:
            # Initial 'hello' frame so the client knows the stream is alive
            # before the first event arrives.
            yield (
                f"event: hello\ndata: {json.dumps({'subscribers': bus.subscriber_count})}\n\n"
            ).encode()

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # SSE keepalive — comment frames don't fire client events.
                    yield b": keepalive\n\n"
                    continue
                yield (f"event: alert\ndata: {json.dumps(event)}\n\n").encode()
        finally:
            await bus.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx buffering if present
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/alerts/{alert_id}",
    summary="Fetch one alert with all sibling violations from the same incident.",
)
async def get_alert(request: Request, alert_id: int) -> dict[str, Any]:
    store = request.app.state.telemetry
    incident = await store.get_incident(alert_id)
    if not incident or not incident.get("violations"):
        raise HTTPException(status_code=404, detail="Alert not found")
    return incident


class FeedbackPayload(BaseModel):
    feedback_type: Literal["false_positive", "confirmed", "note"]
    note: str | None = Field(None, max_length=2000)


@router.post(
    "/alerts/{alert_id}/feedback",
    summary=(
        "Record analyst feedback on an alert. False-positive feedback is "
        "forwarded to the Policy Manager, which may auto-suppress a rule "
        "once it crosses its configured threshold."
    ),
)
async def post_feedback(
    request: Request, alert_id: int, payload: FeedbackPayload
) -> dict[str, Any]:
    store = request.app.state.telemetry
    policy = request.app.state.policy
    incident = await store.get_incident(alert_id)
    if not incident or not incident.get("violations"):
        raise HTTPException(status_code=404, detail="Alert not found")
    feedback_id, rule, fp_count = await store.record_feedback(
        alert_id=alert_id,
        feedback_type=payload.feedback_type,
        note=payload.note,
    )
    auto_suppressed = None
    if rule:
        updated = await policy.on_feedback(
            rule=rule, feedback_type=payload.feedback_type, fp_count=fp_count
        )
        if updated and updated.auto_suppressed:
            auto_suppressed = updated.to_dict()
    return {
        "feedback_id": feedback_id,
        "alert_id": alert_id,
        "rule": rule,
        "fp_count": fp_count,
        "auto_suppressed": auto_suppressed,
    }
