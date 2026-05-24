"""Per-tenant Policy Manager — stateless, talks to the DB on each call.

The original Phase-3 design held an in-memory cache of policies. That worked
because the process was single-tenant. With multi-tenancy we'd need either
per-tenant caches (memory bloat with many tenants) or a session-aware lookup
(simpler, and the policy hot-path is a per-request DB query that's a single
indexed key lookup — cheap on Postgres).

We keep a lightweight per-tenant in-process cache anyway (5s TTL) because
chat traffic is bursty and 99% of the time the policy hasn't changed in 5s.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import RulePolicy
from app.scanners.base import ScanResult, Violation

logger = logging.getLogger(__name__)


@dataclass
class _TenantCache:
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    fetched_at: float = 0.0


CACHE_TTL_SECONDS = 5.0


class PolicyManager:
    """Stateless across tenants — gets a session factory at init time."""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        *,
        default_fp_threshold: int | None = 5,
    ) -> None:
        self._session_factory = session_factory
        self._default_threshold = default_fp_threshold
        self._cache: dict[str, _TenantCache] = {}
        self._lock = asyncio.Lock()

    # ----- core ------------------------------------------------------------
    async def _load(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        async with self._lock:
            cache = self._cache.get(tenant_id)
            if cache and time.monotonic() - cache.fetched_at < CACHE_TTL_SECONDS:
                return cache.rules
        # Acquire outside the lock so a slow DB call doesn't block other tenants.
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(RulePolicy).where(RulePolicy.tenant_id == tenant_id)
                )
            ).scalars().all()
        rules = {
            r.rule: {
                "enabled": r.enabled,
                "suppress_after_n_fp": r.suppress_after_n_fp,
                "note": r.note,
                "auto_suppressed": r.auto_suppressed,
            }
            for r in rows
        }
        async with self._lock:
            self._cache[tenant_id] = _TenantCache(rules=rules, fetched_at=time.monotonic())
        return rules

    def invalidate(self, tenant_id: str) -> None:
        self._cache.pop(tenant_id, None)

    async def is_enabled(self, tenant_id: str, rule: str) -> bool:
        rules = await self._load(tenant_id)
        p = rules.get(rule)
        return p["enabled"] if p else True

    async def apply(self, tenant_id: str, scan: ScanResult) -> tuple[ScanResult, list[Violation]]:
        """Filter a scan's violations according to this tenant's policies.

        Returns (effective_scan, shadowed_violations). Shadowed violations
        are the ones the policy silenced; the caller logs them with a marker
        so the audit trail is intact.
        """
        rules = await self._load(tenant_id)
        active: list[Violation] = []
        shadowed: list[Violation] = []
        for v in scan.violations:
            p = rules.get(v.rule)
            if not p or p["enabled"]:
                active.append(v)
            else:
                shadowed.append(v)
        if not shadowed:
            return scan, []
        effective = ScanResult(
            layer=scan.layer,
            safe=not active,
            sanitized_text=scan.sanitized_text,
            violations=active,
            raw={**scan.raw, "shadowed_rules": [v.rule for v in shadowed]},
        )
        return effective, shadowed

    # ----- feedback-driven auto-suppress -----------------------------------
    async def on_feedback(
        self,
        *,
        tenant_id: str,
        rule: str,
        feedback_type: str,
        fp_count: int,
        session: Any = None,
    ) -> dict[str, Any] | None:
        """Evaluate feedback and (optionally) auto-suppress the rule.

        If `session` is provided, the upsert runs in that session — required
        on SQLite to avoid write-lock deadlocks when called from inside an
        already-open route session.
        """
        if feedback_type != "false_positive":
            return None
        rules = await self._load(tenant_id)
        existing = rules.get(rule)
        threshold = (
            existing["suppress_after_n_fp"]
            if existing and existing["suppress_after_n_fp"] is not None
            else self._default_threshold
        )
        if not threshold or threshold <= 0:
            return None
        if fp_count < threshold:
            return None
        if existing and not existing["enabled"]:
            return None  # already off

        note = (
            f"Auto-suppressed after {fp_count} false-positive reports "
            f"(threshold {threshold})."
        )
        logger.warning(
            "policy auto-suppress tenant=%s rule=%s fp_count=%d",
            tenant_id, rule, fp_count,
        )
        from app.repositories.policy import PolicyRepo

        if session is not None:
            updated = await PolicyRepo(session, self._default_threshold).upsert(
                tenant_id=tenant_id,
                rule=rule,
                enabled=False,
                note=note,
                auto_suppressed=True,
            )
        else:
            async with self._session_factory() as own_session:
                updated = await PolicyRepo(own_session, self._default_threshold).upsert(
                    tenant_id=tenant_id,
                    rule=rule,
                    enabled=False,
                    note=note,
                    auto_suppressed=True,
                )
                await own_session.commit()
        self.invalidate(tenant_id)
        return updated

    @property
    def default_fp_threshold(self) -> int | None:
        return self._default_threshold
