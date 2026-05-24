"""Provider repository — per-tenant upstream LLM configuration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Provider


class ProviderRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, *, tenant_id: str) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(Provider)
                .where(Provider.tenant_id == tenant_id)
                .order_by(Provider.priority.asc(), Provider.id.asc())
            )
        ).scalars().all()
        return [_to_dict(r) for r in rows]

    async def upsert(
        self,
        *,
        tenant_id: str,
        slug: str,
        display_name: str,
        base_url: str,
        api_key_encrypted: str | None = None,
        secret_ref: str | None = None,
        priority: int = 100,
        enabled: bool = True,
        routing_strategy: str = "primary_failover",
    ) -> dict[str, Any]:
        row = (
            await self._session.execute(
                select(Provider).where(
                    Provider.tenant_id == tenant_id, Provider.slug == slug
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = Provider(
                tenant_id=tenant_id,
                slug=slug[:64],
                display_name=display_name[:120],
                base_url=base_url[:500],
                api_key_encrypted=api_key_encrypted,
                secret_ref=secret_ref,
                priority=priority,
                enabled=enabled,
                routing_strategy=routing_strategy,
                created_at=datetime.now(timezone.utc),
            )
            self._session.add(row)
        else:
            row.display_name = display_name[:120]
            row.base_url = base_url[:500]
            if api_key_encrypted is not None:
                row.api_key_encrypted = api_key_encrypted
            if secret_ref is not None:
                row.secret_ref = secret_ref
            row.priority = priority
            row.enabled = enabled
            row.routing_strategy = routing_strategy
        await self._session.flush()
        return _to_dict(row)

    async def delete(self, *, tenant_id: str, provider_id: int) -> bool:
        row = (
            await self._session.execute(
                select(Provider).where(
                    Provider.id == provider_id, Provider.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        return True

    async def record_health(
        self,
        *,
        provider_id: int,
        status: str,
        consecutive_failures: int,
    ) -> None:
        row = (
            await self._session.execute(
                select(Provider).where(Provider.id == provider_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.health_status = status
        row.consecutive_failures = consecutive_failures
        row.last_check_at = datetime.now(timezone.utc)


def _to_dict(p: Provider) -> dict[str, Any]:
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "slug": p.slug,
        "display_name": p.display_name,
        "base_url": p.base_url,
        "has_key": bool(p.api_key_encrypted or p.secret_ref),
        "secret_ref": p.secret_ref,
        "priority": p.priority,
        "enabled": p.enabled,
        "health_status": p.health_status,
        "last_check_at": p.last_check_at.isoformat() if p.last_check_at else None,
        "consecutive_failures": p.consecutive_failures,
        "routing_strategy": p.routing_strategy,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
