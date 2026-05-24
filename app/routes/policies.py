"""Policy CRUD — tenant-scoped."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_dashboard_ctx
from app.db import get_session
from app.repositories.policy import PolicyRepo
from app.repositories.telemetry import TelemetryRepo

router = APIRouter(prefix="/api/policies", tags=["policy"])


class PolicyUpdate(BaseModel):
    enabled: bool | None = None
    suppress_after_n_fp: int | None = Field(None, ge=0, le=10_000)
    note: str | None = Field(None, max_length=500)


@router.get("", summary="List the tenant's policies (stored + observed-but-unset).")
async def list_policies(
    request: Request,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    telemetry = TelemetryRepo(session)
    policy_repo = PolicyRepo(
        session, request.app.state.policy.default_fp_threshold
    )
    rules = await telemetry.distinct_rules(tenant_id=ctx.tenant_id)
    observed = [r["rule"] for r in rules]
    policies = await policy_repo.list_policies(
        tenant_id=ctx.tenant_id, include_unseen_rule_names=observed
    )
    rule_meta = {r["rule"]: r for r in rules}
    return {
        "count": len(policies),
        "default_fp_threshold": request.app.state.policy.default_fp_threshold,
        "policies": [
            {**p, **rule_meta.get(p["rule"], {"hits": 0, "fp_count": 0})}
            for p in policies
        ],
    }


@router.get("/{rule}", summary="Fetch one rule policy.")
async def get_policy(
    rule: str,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = PolicyRepo(session)
    p = await repo.get(tenant_id=ctx.tenant_id, rule=rule)
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    return p


@router.put("/{rule}", summary="Upsert a rule policy.")
async def upsert_policy(
    request: Request,
    rule: str,
    payload: PolicyUpdate,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = PolicyRepo(session, request.app.state.policy.default_fp_threshold)
    out = await repo.upsert(
        tenant_id=ctx.tenant_id,
        rule=rule,
        enabled=payload.enabled,
        suppress_after_n_fp=payload.suppress_after_n_fp,
        note=payload.note,
        auto_suppressed=False,  # manual edit clears the auto flag
    )
    request.app.state.policy.invalidate(ctx.tenant_id)
    return out


@router.delete("/{rule}", summary="Remove a rule policy override (revert to default).")
async def delete_policy(
    request: Request,
    rule: str,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    repo = PolicyRepo(session)
    await repo.reset(tenant_id=ctx.tenant_id, rule=rule)
    request.app.state.policy.invalidate(ctx.tenant_id)
    return {"status": "ok", "rule": rule}
