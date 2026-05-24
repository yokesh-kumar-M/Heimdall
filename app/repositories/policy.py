"""Policy repository — per-tenant rule overrides."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RulePolicy


class PolicyRepo:
    def __init__(self, session: AsyncSession, default_fp_threshold: int | None = 5) -> None:
        self._session = session
        self._default_threshold = default_fp_threshold

    async def list_policies(
        self, *, tenant_id: str, include_unseen_rule_names: Iterable[str] | None = None
    ) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(RulePolicy).where(RulePolicy.tenant_id == tenant_id)
            )
        ).scalars().all()
        out = [_to_dict(r) for r in rows]
        seen = {r["rule"] for r in out}
        if include_unseen_rule_names:
            now = datetime.now(timezone.utc).isoformat()
            for name in include_unseen_rule_names:
                if name in seen:
                    continue
                out.append({
                    "rule": name,
                    "enabled": True,
                    "suppress_after_n_fp": self._default_threshold,
                    "note": None,
                    "auto_suppressed": False,
                    "updated_at": now,
                })
        return sorted(out, key=lambda r: (r["enabled"], r["rule"]))

    async def get(self, *, tenant_id: str, rule: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                select(RulePolicy).where(
                    RulePolicy.tenant_id == tenant_id, RulePolicy.rule == rule
                )
            )
        ).scalar_one_or_none()
        return _to_dict(row) if row else None

    async def upsert(
        self,
        *,
        tenant_id: str,
        rule: str,
        enabled: bool | None = None,
        suppress_after_n_fp: int | None = None,
        note: str | None = None,
        auto_suppressed: bool | None = None,
    ) -> dict[str, Any]:
        existing = (
            await self._session.execute(
                select(RulePolicy).where(
                    RulePolicy.tenant_id == tenant_id, RulePolicy.rule == rule
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = RulePolicy(
                tenant_id=tenant_id,
                rule=rule,
                enabled=True if enabled is None else enabled,
                suppress_after_n_fp=(
                    suppress_after_n_fp
                    if suppress_after_n_fp is not None
                    else self._default_threshold
                ),
                note=note,
                auto_suppressed=False if auto_suppressed is None else auto_suppressed,
                updated_at=datetime.now(timezone.utc),
            )
            self._session.add(existing)
        else:
            if enabled is not None:
                existing.enabled = enabled
            if suppress_after_n_fp is not None:
                existing.suppress_after_n_fp = suppress_after_n_fp
            if note is not None:
                existing.note = note
            if auto_suppressed is not None:
                existing.auto_suppressed = auto_suppressed
            existing.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return _to_dict(existing)

    async def reset(self, *, tenant_id: str, rule: str) -> None:
        row = (
            await self._session.execute(
                select(RulePolicy).where(
                    RulePolicy.tenant_id == tenant_id, RulePolicy.rule == rule
                )
            )
        ).scalar_one_or_none()
        if row:
            await self._session.delete(row)


def _to_dict(row: RulePolicy | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "rule": row.rule,
        "enabled": row.enabled,
        "suppress_after_n_fp": row.suppress_after_n_fp,
        "note": row.note,
        "auto_suppressed": row.auto_suppressed,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
