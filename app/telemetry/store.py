from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.scanners.base import ScanResult

logger = logging.getLogger(__name__)


# Base tables — must run BEFORE any migration. Columns added in Phase 2 are
# declared inline so a fresh DB has the full schema, but indexes that touch
# Phase-2 columns are created in a second pass (post-migration) so they
# work against pre-Phase-2 databases too.
_SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    incident_id     TEXT,
    masked_ip       TEXT    NOT NULL,
    country_code    TEXT,
    triggered_layer TEXT    NOT NULL,
    owasp_category  TEXT    NOT NULL,
    rule            TEXT    NOT NULL,
    detail          TEXT,
    snippet         TEXT,
    model           TEXT,
    model_params    TEXT,
    user_agent      TEXT,
    blocked_prompt  TEXT    NOT NULL,
    original_prompt TEXT,
    sanitized_prompt TEXT,
    extra           TEXT
);

CREATE TABLE IF NOT EXISTS alert_feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id        INTEGER NOT NULL,
    incident_id     TEXT,
    feedback_type   TEXT NOT NULL,
    note            TEXT,
    created_at      TEXT NOT NULL
);
"""

_SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp  ON alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_layer      ON alerts(triggered_layer);
CREATE INDEX IF NOT EXISTS idx_alerts_category   ON alerts(owasp_category);
CREATE INDEX IF NOT EXISTS idx_alerts_incident   ON alerts(incident_id);

CREATE INDEX IF NOT EXISTS idx_feedback_alert    ON alert_feedback(alert_id);
CREATE INDEX IF NOT EXISTS idx_feedback_incident ON alert_feedback(incident_id);
"""

# Columns we may need to ADD to a pre-Phase-2 alerts table.
_NEW_COLUMNS: list[tuple[str, str]] = [
    ("incident_id", "TEXT"),
    ("country_code", "TEXT"),
    ("model_params", "TEXT"),
    ("user_agent", "TEXT"),
    ("original_prompt", "TEXT"),
    ("sanitized_prompt", "TEXT"),
]


def mask_ip(addr: str | None) -> str:
    """Mask an IPv4/IPv6 address to comply with privacy requirements."""
    if not addr:
        return "unknown"
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return "unknown"
    if isinstance(ip, ipaddress.IPv4Address):
        parts = str(ip).split(".")
        return ".".join(parts[:3]) + ".*"
    return ip.exploded.rsplit(":", 4)[0] + "::*"


class TelemetryStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # -- lifecycle ---------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_TABLES)
            self._migrate_legacy_columns(conn)
            conn.executescript(_SCHEMA_INDEXES)

    def _migrate_legacy_columns(self, conn: sqlite3.Connection) -> None:
        """Add Phase-2 columns to a pre-existing alerts table from Phase 1.

        SQLite's ALTER TABLE ADD COLUMN is the only safe option; we discover
        which columns already exist via PRAGMA table_info.
        """
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(alerts)")
        }
        for name, decl in _NEW_COLUMNS:
            if name not in existing:
                logger.info("Migrating: ADD COLUMN alerts.%s %s", name, decl)
                conn.execute(f"ALTER TABLE alerts ADD COLUMN {name} {decl}")

        # Backfill incident_id for legacy rows so they group sanely in the
        # drawer. One incident per (timestamp, masked_ip, blocked_prompt).
        if existing and "incident_id" in {n for n, _ in _NEW_COLUMNS}:
            null_count = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE incident_id IS NULL"
            ).fetchone()[0]
            if null_count:
                logger.info("Backfilling incident_id for %s legacy rows", null_count)
                groups = conn.execute(
                    "SELECT DISTINCT timestamp, masked_ip, blocked_prompt "
                    "FROM alerts WHERE incident_id IS NULL"
                ).fetchall()
                for row in groups:
                    incident = uuid.uuid4().hex
                    conn.execute(
                        "UPDATE alerts SET incident_id = ? "
                        "WHERE timestamp = ? AND masked_ip = ? "
                        "AND blocked_prompt = ? AND incident_id IS NULL",
                        (incident, row["timestamp"], row["masked_ip"], row["blocked_prompt"]),
                    )

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

    # -- writes ------------------------------------------------------------

    async def log_incident(
        self,
        *,
        scan: ScanResult,
        client_ip: str | None,
        model: str | None,
        blocked_prompt: str,
        original_prompt: str | None = None,
        sanitized_prompt: str | None = None,
        user_agent: str | None = None,
        country_code: str | None = None,
        model_params: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str | None:
        """Persist every violation in a ScanResult, all sharing one incident_id.

        Returns the incident_id string (so callers can correlate or surface in
        the response).
        """
        if scan.safe or not scan.violations:
            return None

        incident_id = uuid.uuid4().hex
        ts = datetime.now(timezone.utc).isoformat()
        masked = mask_ip(client_ip)
        extra_json = json.dumps(extra or {}, default=str)
        params_json = json.dumps(model_params or {}, default=str)

        rows = [
            (
                ts,
                incident_id,
                masked,
                country_code,
                scan.layer,
                v.category.value,
                v.rule,
                v.detail,
                v.snippet,
                model,
                params_json,
                user_agent,
                blocked_prompt,
                original_prompt if original_prompt is not None else blocked_prompt,
                sanitized_prompt,
                extra_json,
            )
            for v in scan.violations
        ]

        async with self._lock:
            await asyncio.to_thread(self._insert_many, rows)
        return incident_id

    def _insert_many(self, rows: list[tuple]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO alerts (
                    timestamp, incident_id, masked_ip, country_code,
                    triggered_layer, owasp_category, rule, detail, snippet,
                    model, model_params, user_agent, blocked_prompt,
                    original_prompt, sanitized_prompt, extra
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    async def record_feedback(
        self,
        *,
        alert_id: int,
        feedback_type: str,
        note: str | None = None,
    ) -> tuple[int, str | None, int]:
        """Persist analyst feedback and return (feedback_id, rule, fp_count).

        The `rule` and `fp_count` are returned so callers (the route layer)
        can hand them to the PolicyManager for auto-suppression evaluation —
        the store deliberately does not know about policy.
        """
        return await asyncio.to_thread(
            self._record_feedback_sync, alert_id, feedback_type, note
        )

    def _record_feedback_sync(
        self, alert_id: int, feedback_type: str, note: str | None
    ) -> tuple[int, str | None, int]:
        ts = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT incident_id, rule FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            incident_id = row["incident_id"] if row else None
            rule = row["rule"] if row else None
            cursor = conn.execute(
                "INSERT INTO alert_feedback "
                "(alert_id, incident_id, feedback_type, note, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (alert_id, incident_id, feedback_type, note, ts),
            )
            feedback_id = int(cursor.lastrowid)
            fp_count = 0
            if rule and feedback_type == "false_positive":
                fp_count = conn.execute(
                    """
                    SELECT COUNT(*) FROM alert_feedback f
                    JOIN alerts a ON a.id = f.alert_id
                    WHERE a.rule = ? AND f.feedback_type = 'false_positive'
                    """,
                    (rule,),
                ).fetchone()[0]
            return feedback_id, rule, int(fp_count)

    # -- reads -------------------------------------------------------------

    async def list_alerts(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        layer: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._list_alerts_sync, limit, offset, layer, category
        )

    def _list_alerts_sync(
        self,
        limit: int,
        offset: int,
        layer: str | None,
        category: str | None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM alerts"
        clauses: list[str] = []
        params: list[Any] = []
        if layer:
            clauses.append("triggered_layer = ?")
            params.append(layer)
        if category:
            clauses.append("owasp_category = ?")
            params.append(category)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [_row_to_dict(row) for row in cursor.fetchall()]

    async def get_incident(self, alert_id: int) -> dict[str, Any] | None:
        """Fetch one alert and all sibling violations from the same incident."""
        return await asyncio.to_thread(self._get_incident_sync, alert_id)

    def _get_incident_sync(self, alert_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            primary = conn.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if not primary:
                return None
            primary_dict = _row_to_dict(primary)

            incident_id = primary_dict.get("incident_id")
            if incident_id:
                siblings = [
                    _row_to_dict(r)
                    for r in conn.execute(
                        "SELECT * FROM alerts WHERE incident_id = ? ORDER BY id",
                        (incident_id,),
                    )
                ]
            else:
                siblings = [primary_dict]

            feedback = [
                _row_to_dict(r)
                for r in conn.execute(
                    "SELECT * FROM alert_feedback WHERE alert_id IN ("
                    + ",".join("?" for _ in siblings) + ") ORDER BY id DESC",
                    tuple(s["id"] for s in siblings),
                )
            ] if siblings else []

            return {
                "incident_id": incident_id,
                "violations": siblings,
                "feedback": feedback,
                "primary_id": alert_id,
            }

    async def stats(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._stats_sync)

    async def distinct_rules(self) -> list[dict[str, Any]]:
        """Return every rule that has ever fired, with the hit count and
        false-positive feedback count. Used by the policies endpoint so the
        UI can show rules that have no explicit policy row yet.
        """
        return await asyncio.to_thread(self._distinct_rules_sync)

    def _distinct_rules_sync(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.rule                                    AS rule,
                       COUNT(a.id)                               AS hits,
                       SUM(CASE WHEN f.feedback_type = 'false_positive'
                                THEN 1 ELSE 0 END)               AS fp_count
                FROM alerts a
                LEFT JOIN alert_feedback f ON f.alert_id = a.id
                GROUP BY a.rule
                ORDER BY hits DESC
                """
            ).fetchall()
        return [
            {
                "rule": r["rule"],
                "hits": int(r["hits"]),
                "fp_count": int(r["fp_count"] or 0),
            }
            for r in rows
        ]

    def _stats_sync(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            by_layer = {
                row["triggered_layer"]: row["n"]
                for row in conn.execute(
                    "SELECT triggered_layer, COUNT(*) n FROM alerts GROUP BY triggered_layer"
                )
            }
            by_category = {
                row["owasp_category"]: row["n"]
                for row in conn.execute(
                    "SELECT owasp_category, COUNT(*) n FROM alerts GROUP BY owasp_category"
                )
            }
        return {"total": total, "by_layer": by_layer, "by_category": by_category}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = {k: row[k] for k in row.keys()}
    for json_field in ("extra", "model_params"):
        val = out.get(json_field)
        if val:
            try:
                out[json_field] = json.loads(val)
            except (TypeError, ValueError):
                pass
    return out
