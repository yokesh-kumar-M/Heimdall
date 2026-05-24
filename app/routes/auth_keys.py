"""Dashboard endpoints for managing the tenant's Heimdall API keys."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_dashboard_ctx
from app.db import get_session
from app.repositories.auth import ApiKeyRepo

router = APIRouter(prefix="/api/keys", tags=["auth"])


class CreateKey(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@router.get("", summary="List the current tenant's API keys (hashed; never plaintext).")
async def list_keys(
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = ApiKeyRepo(session)
    return {"keys": await repo.list(tenant_id=ctx.tenant_id)}


@router.post(
    "",
    summary=(
        "Mint a new API key. The plaintext key is returned ONCE — store it "
        "immediately, we don't keep a copy."
    ),
)
async def create_key(
    payload: CreateKey,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = ApiKeyRepo(session)
    plain, row = await repo.create(tenant_id=ctx.tenant_id, name=payload.name)
    return {"plain": plain, "key": row}


@router.delete("/{key_id}", summary="Revoke an API key (sets revoked_at; row stays for audit).")
async def revoke_key(
    key_id: int,
    ctx: TenantContext = Depends(get_dashboard_ctx),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = ApiKeyRepo(session)
    ok = await repo.revoke(tenant_id=ctx.tenant_id, key_id=key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "revoked", "id": key_id}
