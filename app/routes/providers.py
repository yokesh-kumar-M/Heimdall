"""Provider management endpoints (dashboard-only)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_dashboard_ctx
from app.db import get_session
from app.repositories.providers import ProviderRepo

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderPayload(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=120)
    base_url: str = Field(..., min_length=8, max_length=500)
    secret_ref: str | None = Field(None, max_length=120,
        description="Environment variable name holding the upstream API key.")
    priority: int = Field(100, ge=1, le=10_000)
    enabled: bool = True
    routing_strategy: Literal["primary_failover", "cheapest", "fastest"] = "primary_failover"


@router.get("", summary="List the current tenant's configured providers.")
async def list_providers(
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = ProviderRepo(session)
    rows = await repo.list(tenant_id=ctx.tenant_id)
    return {"count": len(rows), "providers": rows}


@router.put("", summary="Create or update a provider by slug (idempotent).")
async def upsert_provider(
    payload: ProviderPayload,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = ProviderRepo(session)
    return await repo.upsert(
        tenant_id=ctx.tenant_id,
        slug=payload.slug,
        display_name=payload.display_name,
        base_url=payload.base_url,
        secret_ref=payload.secret_ref,
        priority=payload.priority,
        enabled=payload.enabled,
        routing_strategy=payload.routing_strategy,
    )


@router.delete("/{provider_id}", summary="Delete a provider.")
async def delete_provider(
    provider_id: int,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = ProviderRepo(session)
    ok = await repo.delete(tenant_id=ctx.tenant_id, provider_id=provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "deleted", "id": provider_id}
