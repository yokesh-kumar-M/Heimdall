"""Budget + usage analytics endpoints (dashboard-only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_dashboard_ctx
from app.db import get_session
from app.repositories.budget import BudgetRepo, UsageRepo

router = APIRouter(prefix="/api/billing", tags=["billing"])


class BudgetUpsert(BaseModel):
    monthly_limit_usd: float | None = Field(None, ge=0)
    warn_at_pct: int | None = Field(None, ge=1, le=100)
    hard_cap_usd: float | None = Field(None, ge=0)


@router.get("/summary", summary="Month-to-date spend + budget for the current tenant.")
async def summary(
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    bud = BudgetRepo(session)
    usg = UsageRepo(session)
    budget = await bud.get(tenant_id=ctx.tenant_id)
    mtd = await bud.month_to_date_usd(tenant_id=ctx.tenant_id)
    top_models = await usg.top_models(tenant_id=ctx.tenant_id)
    series = await usg.daily_series(tenant_id=ctx.tenant_id, days=30)

    pct = None
    projected_month_end = None
    if budget and budget["monthly_limit_usd"]:
        pct = round((mtd / budget["monthly_limit_usd"]) * 100, 2)
    if series:
        # Simple linear projection: avg of last 7 days × remaining days
        from datetime import datetime, timezone
        days_in_month = 30  # close enough for a projection
        recent = series[-7:]
        if recent:
            avg = sum(d["cost_usd"] for d in recent) / len(recent)
            now = datetime.now(timezone.utc)
            day_of_month = now.day
            remaining = max(0, days_in_month - day_of_month)
            projected_month_end = round(mtd + avg * remaining, 2)

    return {
        "tenant_id": ctx.tenant_id,
        "budget": budget,
        "month_to_date_usd": round(mtd, 6),
        "month_to_date_pct": pct,
        "projected_month_end_usd": projected_month_end,
        "top_models": top_models,
        "daily_series": series,
    }


@router.put("/budget", summary="Set or update the tenant's monthly budget.")
async def put_budget(
    payload: BudgetUpsert,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = BudgetRepo(session)
    return await repo.upsert(
        tenant_id=ctx.tenant_id,
        monthly_limit_usd=payload.monthly_limit_usd,
        warn_at_pct=payload.warn_at_pct,
        hard_cap_usd=payload.hard_cap_usd,
    )
