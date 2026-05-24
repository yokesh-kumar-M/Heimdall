"""Phase 3 — Policy Manager REST endpoints.

Lets operators inspect and tune per-rule policy:
  * GET    /api/policies          — every policy + observed rules.
  * GET    /api/policies/{rule}   — one policy.
  * PUT    /api/policies/{rule}   — upsert (enable/disable, threshold, note).
  * DELETE /api/policies/{rule}   — clear back to default (enabled, default
                                    auto-suppress threshold).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.policy import PolicyManager

router = APIRouter(prefix="/api/policies", tags=["policy"])


class PolicyUpdate(BaseModel):
    enabled: bool | None = None
    suppress_after_n_fp: int | None = Field(None, ge=0, le=10_000)
    note: str | None = Field(None, max_length=500)


@router.get("", summary="List all rule policies (stored + observed-but-unset).")
async def list_policies(request: Request) -> dict[str, Any]:
    policy: PolicyManager = request.app.state.policy
    rules = await request.app.state.telemetry.distinct_rules()
    observed_names = [r["rule"] for r in rules]
    policies = await policy.list_policies(include_unseen_rule_names=observed_names)
    rule_meta = {r["rule"]: r for r in rules}
    return {
        "count": len(policies),
        "default_fp_threshold": policy._default_threshold,  # noqa: SLF001 (intentional read)
        "policies": [
            {**p.to_dict(), **rule_meta.get(p.rule, {"hits": 0, "fp_count": 0})}
            for p in policies
        ],
    }


@router.get("/{rule}", summary="Fetch one rule policy.")
async def get_policy(request: Request, rule: str) -> dict[str, Any]:
    policy: PolicyManager = request.app.state.policy
    p = await policy.get(rule)
    if p is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return p.to_dict()


@router.put("/{rule}", summary="Upsert a rule policy (partial fields ok).")
async def upsert_policy(
    request: Request, rule: str, payload: PolicyUpdate
) -> dict[str, Any]:
    policy: PolicyManager = request.app.state.policy
    # Manual edits clear the auto-suppress marker — analyst has decided.
    updated = await policy.upsert(
        rule=rule,
        enabled=payload.enabled,
        suppress_after_n_fp=payload.suppress_after_n_fp,
        note=payload.note,
        auto_suppressed=False,
    )
    return updated.to_dict()


@router.delete("/{rule}", summary="Remove rule policy override (revert to default).")
async def delete_policy(request: Request, rule: str) -> dict[str, str]:
    policy: PolicyManager = request.app.state.policy
    await policy.reset(rule)
    return {"status": "ok", "rule": rule}
