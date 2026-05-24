"""AI-powered alert triage endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_dashboard_ctx
from app.db import get_session
from app.repositories.telemetry import TelemetryRepo
from app.triage import Triager

router = APIRouter(prefix="/api/alerts", tags=["telemetry"])


@router.post(
    "/{alert_id}/triage",
    summary="Generate (or fetch cached) AI explanation for an alert.",
)
async def triage_alert(
    request: Request,
    alert_id: int,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = TelemetryRepo(session)
    incident = await repo.get_incident(tenant_id=ctx.tenant_id, alert_id=alert_id)
    if not incident or not incident.get("violations"):
        raise HTTPException(status_code=404, detail="Alert not found")
    primary = incident["violations"][0]

    # If we've already triaged this alert, return cached.
    cached = primary.get("triage")
    if cached and cached.get("summary"):
        return {"cached": True, **cached}

    triager: Triager = request.app.state.triager
    result = await triager.triage(primary)
    await repo.cache_triage(
        tenant_id=ctx.tenant_id,
        alert_id=alert_id,
        summary=result.summary,
        severity=result.severity,
        cluster=result.cluster,
    )
    return {
        "cached": False,
        "summary": result.summary,
        "severity": result.severity,
        "suggested_action": result.suggested_action,
        "cluster": result.cluster,
        "model_used": result.model_used,
    }


@router.get(
    "/clusters",
    summary="Group recent triaged alerts by cluster signature.",
)
async def list_clusters(
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
    hours: int = 24,
) -> dict[str, Any]:
    repo = TelemetryRepo(session)
    rows = await repo.cluster_counts(tenant_id=ctx.tenant_id, hours=hours)
    return {"count": len(rows), "clusters": rows}
