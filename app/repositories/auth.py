"""Auth repository — tenants, API keys (sk_hd_*)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiKey, Tenant


KEY_PREFIX = "sk_hd_"


def generate_api_key() -> tuple[str, str, str]:
    """Return (plain_key, prefix_display, sha256_hash).

    The plain_key is shown to the user once; only the hash is stored.
    """
    rand = secrets.token_urlsafe(32).replace("-", "").replace("_", "")[:40]
    plain = f"{KEY_PREFIX}{rand}"
    prefix = plain[:12]  # sk_hd_ + 6 chars
    digest = hashlib.sha256(plain.encode("utf-8")).hexdigest()
    return plain, prefix, digest


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


class TenantRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure(self, tenant_id: str, display_name: str | None = None) -> Tenant:
        """Idempotently create the tenant row (e.g. on first sign-in)."""
        existing = (
            await self._session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if existing is not None:
            if display_name and not existing.display_name:
                existing.display_name = display_name
            return existing
        tenant = Tenant(
            id=tenant_id,
            display_name=display_name,
            plan="free",
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(tenant)
        await self._session.flush()
        return tenant


class ApiKeyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: str, name: str) -> tuple[str, dict[str, Any]]:
        plain, prefix, digest = generate_api_key()
        row = ApiKey(
            tenant_id=tenant_id,
            name=name[:120],
            prefix=prefix,
            key_hash=digest,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        return plain, _to_dict(row)

    async def list(self, *, tenant_id: str) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(ApiKey)
                .where(ApiKey.tenant_id == tenant_id)
                .order_by(ApiKey.created_at.desc())
            )
        ).scalars().all()
        return [_to_dict(r) for r in rows]

    async def revoke(self, *, tenant_id: str, key_id: int) -> bool:
        row = (
            await self._session.execute(
                select(ApiKey).where(
                    ApiKey.id == key_id, ApiKey.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(timezone.utc)
        return True

    async def lookup_by_plain(self, plain: str) -> ApiKey | None:
        """Constant-ish-time lookup: hash then index lookup."""
        if not plain.startswith(KEY_PREFIX):
            return None
        digest = hash_key(plain)
        row = (
            await self._session.execute(
                select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.revoked_at.is_(None))
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        # Best-effort last_used update (don't fail the request if it errors).
        await self._session.execute(
            update(ApiKey)
            .where(ApiKey.id == row.id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        return row


def _to_dict(k: ApiKey) -> dict[str, Any]:
    return {
        "id": k.id,
        "tenant_id": k.tenant_id,
        "name": k.name,
        "prefix": k.prefix,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
    }
