"""Budget + usage repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget, UsageRecord


def _month_start_utc(now: datetime | None = None) -> datetime:
    n = now or datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class BudgetRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: str) -> dict[str, Any] | None:
        row = (
            await self._session.execute(
                select(Budget).where(Budget.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "tenant_id": row.tenant_id,
            "monthly_limit_usd": row.monthly_limit_usd,
            "warn_at_pct": row.warn_at_pct,
            "hard_cap_usd": row.hard_cap_usd,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def upsert(
        self,
        *,
        tenant_id: str,
        monthly_limit_usd: float | None = None,
        warn_at_pct: int | None = None,
        hard_cap_usd: float | None = None,
    ) -> dict[str, Any]:
        row = (
            await self._session.execute(
                select(Budget).where(Budget.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if row is None:
            row = Budget(
                tenant_id=tenant_id,
                monthly_limit_usd=monthly_limit_usd or 0.0,
                warn_at_pct=warn_at_pct or 80,
                hard_cap_usd=hard_cap_usd,
                updated_at=datetime.now(timezone.utc),
            )
            self._session.add(row)
        else:
            if monthly_limit_usd is not None:
                row.monthly_limit_usd = monthly_limit_usd
            if warn_at_pct is not None:
                row.warn_at_pct = warn_at_pct
            if hard_cap_usd is not None:
                row.hard_cap_usd = hard_cap_usd
            row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return await self.get(tenant_id=tenant_id) or {}

    async def month_to_date_usd(self, *, tenant_id: str) -> float:
        start = _month_start_utc()
        total = (
            await self._session.execute(
                select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0))
                .where(
                    UsageRecord.tenant_id == tenant_id,
                    UsageRecord.timestamp >= start,
                )
            )
        ).scalar_one()
        return float(total or 0.0)


class UsageRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        tenant_id: str,
        api_key_id: int | None,
        provider_slug: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        blocked: bool,
        latency_ms: int,
        status_code: int,
    ) -> None:
        row = UsageRecord(
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            timestamp=datetime.now(timezone.utc),
            provider_slug=provider_slug,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
            blocked=blocked,
            latency_ms=latency_ms,
            status_code=status_code,
        )
        self._session.add(row)
        await self._session.flush()

    async def daily_series(
        self, *, tenant_id: str, days: int = 30
    ) -> list[dict[str, Any]]:
        # Truncated to date: works on both Postgres (date_trunc) and SQLite (strftime).
        # We use strftime via SQLAlchemy func; it works on Postgres too via to_char,
        # but date_trunc is more idiomatic. Simpler: bucket in Python after select.
        rows = (
            await self._session.execute(
                select(
                    UsageRecord.timestamp,
                    UsageRecord.cost_usd,
                    UsageRecord.total_tokens,
                )
                .where(UsageRecord.tenant_id == tenant_id)
                .order_by(UsageRecord.timestamp.desc())
                .limit(days * 1000)
            )
        ).all()

        buckets: dict[str, dict[str, float]] = {}
        for r in rows:
            day = r.timestamp.date().isoformat()
            b = buckets.setdefault(day, {"cost_usd": 0.0, "tokens": 0.0, "requests": 0.0})
            b["cost_usd"] += float(r.cost_usd or 0)
            b["tokens"] += float(r.total_tokens or 0)
            b["requests"] += 1

        out = [
            {"day": day, **{k: round(v, 6) for k, v in buckets[day].items()}}
            for day in sorted(buckets.keys())[-days:]
        ]
        return out

    async def top_models(
        self, *, tenant_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(
                    UsageRecord.model,
                    func.sum(UsageRecord.cost_usd).label("cost"),
                    func.sum(UsageRecord.total_tokens).label("tokens"),
                    func.count(UsageRecord.id).label("requests"),
                )
                .where(UsageRecord.tenant_id == tenant_id)
                .group_by(UsageRecord.model)
                .order_by(func.sum(UsageRecord.cost_usd).desc())
                .limit(limit)
            )
        ).all()
        return [
            {
                "model": r.model,
                "cost_usd": float(r.cost or 0),
                "tokens": int(r.tokens or 0),
                "requests": int(r.requests or 0),
            }
            for r in rows
        ]
