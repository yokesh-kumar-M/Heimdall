"""Phase 3 — Policy Manager.

Lets operators tune scanner behaviour without redeploying. Two motivations:

  1. **Manual override** — flip an over-eager rule off (or back on) from the
     dashboard. The `rule_policies` row is the source of truth; the in-memory
     cache is refreshed atomically when a policy changes.

  2. **Feedback-driven auto-suppress** — when analysts flag the same rule as
     a false positive N times, the manager auto-disables it and records a
     `note` so the next person to look knows why.

Policy is applied as a *post-scan filter*: scanners still run unmodified and
their raw output is preserved on the audit trail (with a `shadowed` marker).
Only the request-time block decision is affected. That preserves forensic
fidelity — a policy mistake doesn't lose data, it just doesn't gate traffic.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from app.scanners.base import ScanResult, Violation

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_policies (
    rule                  TEXT PRIMARY KEY,
    enabled               INTEGER NOT NULL DEFAULT 1,
    suppress_after_n_fp   INTEGER,
    note                  TEXT,
    auto_suppressed       INTEGER NOT NULL DEFAULT 0,
    updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policies_enabled ON rule_policies(enabled);
"""

# Default auto-suppress threshold applied to *any* rule with no explicit policy
# row. Set to 0 / None to disable auto-suppression globally.
DEFAULT_FP_THRESHOLD = 5


@dataclass(frozen=True)
class RulePolicy:
    rule: str
    enabled: bool
    suppress_after_n_fp: int | None
    note: str | None
    auto_suppressed: bool
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "enabled": self.enabled,
            "suppress_after_n_fp": self.suppress_after_n_fp,
            "note": self.note,
            "auto_suppressed": self.auto_suppressed,
            "updated_at": self.updated_at,
        }


class PolicyManager:
    """Async-safe, in-memory cache of per-rule policy backed by SQLite."""

    def __init__(
        self,
        db_path: str,
        *,
        default_fp_threshold: int | None = DEFAULT_FP_THRESHOLD,
    ) -> None:
        self.db_path = db_path
        self._default_threshold = default_fp_threshold
        self._lock = asyncio.Lock()
        self._cache: dict[str, RulePolicy] = {}
        self._init_schema()
        self._reload_sync()

    # -- schema / connection -------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            yield conn
        finally:
            conn.close()

    # -- reads ---------------------------------------------------------------

    def is_enabled(self, rule: str) -> bool:
        p = self._cache.get(rule)
        return p.enabled if p else True

    def filter_violations(
        self, violations: Iterable[Violation]
    ) -> tuple[list[Violation], list[Violation]]:
        """Split violations into (active, shadowed).

        * active   — still cause a block.
        * shadowed — silenced by policy; written to telemetry with the marker
                     so the audit trail records them but the request is not
                     blocked on their account.
        """
        active: list[Violation] = []
        shadowed: list[Violation] = []
        for v in violations:
            if self.is_enabled(v.rule):
                active.append(v)
            else:
                shadowed.append(v)
        return active, shadowed

    def apply(self, scan: ScanResult) -> tuple[ScanResult, list[Violation]]:
        """Return a scan-result with shadowed violations removed.

        The original scan object is left intact — callers needing the raw
        verdict (telemetry, sandbox) still see it. The returned tuple is
        `(effective_scan, shadowed_violations)`.
        """
        active, shadowed = self.filter_violations(scan.violations)
        if not shadowed:
            return scan, []

        # Construct a new ScanResult so we don't mutate the original. If every
        # violation got shadowed, the effective verdict flips to safe.
        effective = ScanResult(
            layer=scan.layer,
            safe=not active,
            sanitized_text=scan.sanitized_text,
            violations=active,
            raw={**scan.raw, "shadowed_rules": [v.rule for v in shadowed]},
        )
        return effective, shadowed

    async def list_policies(
        self, *, include_unseen_rule_names: Iterable[str] | None = None
    ) -> list[RulePolicy]:
        """Return all stored policies plus optional placeholders for rules
        that have no row yet (e.g. rules observed in alerts but never tuned).
        """
        async with self._lock:
            policies = list(self._cache.values())
        seen = {p.rule for p in policies}
        if include_unseen_rule_names:
            now = datetime.now(timezone.utc).isoformat()
            for name in include_unseen_rule_names:
                if name in seen:
                    continue
                policies.append(
                    RulePolicy(
                        rule=name,
                        enabled=True,
                        suppress_after_n_fp=self._default_threshold,
                        note=None,
                        auto_suppressed=False,
                        updated_at=now,
                    )
                )
        return sorted(policies, key=lambda p: (p.enabled, p.rule))

    async def get(self, rule: str) -> RulePolicy | None:
        async with self._lock:
            return self._cache.get(rule)

    # -- writes --------------------------------------------------------------

    async def upsert(
        self,
        *,
        rule: str,
        enabled: bool | None = None,
        suppress_after_n_fp: int | None = None,
        note: str | None = None,
        auto_suppressed: bool | None = None,
    ) -> RulePolicy:
        """Insert or update a policy. Only provided fields are touched."""
        async with self._lock:
            existing = self._cache.get(rule)
            merged = RulePolicy(
                rule=rule,
                enabled=enabled if enabled is not None else (existing.enabled if existing else True),
                suppress_after_n_fp=(
                    suppress_after_n_fp
                    if suppress_after_n_fp is not None
                    else (existing.suppress_after_n_fp if existing else self._default_threshold)
                ),
                note=note if note is not None else (existing.note if existing else None),
                auto_suppressed=(
                    auto_suppressed
                    if auto_suppressed is not None
                    else (existing.auto_suppressed if existing else False)
                ),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            await asyncio.to_thread(self._write_sync, merged)
            self._cache[rule] = merged
        return merged

    async def reset(self, rule: str) -> None:
        async with self._lock:
            await asyncio.to_thread(self._delete_sync, rule)
            self._cache.pop(rule, None)

    def _write_sync(self, p: RulePolicy) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rule_policies (
                    rule, enabled, suppress_after_n_fp, note, auto_suppressed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule) DO UPDATE SET
                    enabled             = excluded.enabled,
                    suppress_after_n_fp = excluded.suppress_after_n_fp,
                    note                = excluded.note,
                    auto_suppressed     = excluded.auto_suppressed,
                    updated_at          = excluded.updated_at
                """,
                (
                    p.rule,
                    int(p.enabled),
                    p.suppress_after_n_fp,
                    p.note,
                    int(p.auto_suppressed),
                    p.updated_at,
                ),
            )

    def _delete_sync(self, rule: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM rule_policies WHERE rule = ?", (rule,))

    # -- cache load ----------------------------------------------------------

    def _reload_sync(self) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM rule_policies").fetchall()
        self._cache = {
            row["rule"]: RulePolicy(
                rule=row["rule"],
                enabled=bool(row["enabled"]),
                suppress_after_n_fp=row["suppress_after_n_fp"],
                note=row["note"],
                auto_suppressed=bool(row["auto_suppressed"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        }

    # -- feedback hook -------------------------------------------------------

    async def on_feedback(
        self,
        *,
        rule: str,
        feedback_type: str,
        fp_count: int,
    ) -> RulePolicy | None:
        """Called by TelemetryStore after a feedback row is written.

        If the rule has crossed its FP threshold, auto-disable it and stamp
        a note. Returns the new policy if it changed, else None.
        """
        if feedback_type != "false_positive":
            return None

        existing = self._cache.get(rule)
        threshold = (
            existing.suppress_after_n_fp
            if existing and existing.suppress_after_n_fp is not None
            else self._default_threshold
        )
        if threshold is None or threshold <= 0:
            return None
        if fp_count < threshold:
            return None
        if existing and not existing.enabled:
            return None  # already off

        note = (
            f"Auto-suppressed after {fp_count} false-positive reports "
            f"(threshold {threshold})."
        )
        logger.warning(
            "policy auto-suppress rule=%s fp_count=%d threshold=%d",
            rule,
            fp_count,
            threshold,
        )
        return await self.upsert(
            rule=rule,
            enabled=False,
            note=note,
            auto_suppressed=True,
        )
