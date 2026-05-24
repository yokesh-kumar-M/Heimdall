"""Telemetry repository — alerts + feedback writes/reads, tenant-scoped.

Public API mirrors the old hand-rolled `TelemetryStore` so call sites in the
route layer change minimally — they just pass `tenant_id` now.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertFeedback
from app.scanners.base import ScanResult

logger = logging.getLogger(__name__)


def mask_ip(addr: str | None) -> str:
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


class TelemetryRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----- writes -----------------------------------------------------------
    async def log_incident(
        self,
        *,
        tenant_id: str,
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
        if scan.safe or not scan.violations:
            return None

        incident_id = uuid.uuid4().hex
        ts = datetime.now(timezone.utc)
        masked = mask_ip(client_ip)

        rows = [
            Alert(
                tenant_id=tenant_id,
                timestamp=ts,
                incident_id=incident_id,
                masked_ip=masked,
                country_code=country_code,
                triggered_layer=scan.layer,
                owasp_category=v.category.value,
                rule=v.rule,
                detail=v.detail,
                snippet=v.snippet,
                model=model,
                model_params=model_params or {},
                user_agent=(user_agent or "")[:500] or None,
                blocked_prompt=blocked_prompt,
                original_prompt=original_prompt if original_prompt is not None else blocked_prompt,
                sanitized_prompt=sanitized_prompt,
                extra=extra or {},
            )
            for v in scan.violations
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return incident_id

    async def record_feedback(
        self,
        *,
        tenant_id: str,
        alert_id: int,
        feedback_type: str,
        note: str | None = None,
    ) -> tuple[int, str | None, int]:
        """Insert feedback. Returns (feedback_id, rule, fp_count_for_rule)."""
        alert = (
            await self._session.execute(
                select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()

        if alert is None:
            return 0, None, 0

        fb = AlertFeedback(
            tenant_id=tenant_id,
            alert_id=alert_id,
            incident_id=alert.incident_id,
            feedback_type=feedback_type,
            note=note,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(fb)
        await self._session.flush()

        fp_count = 0
        if feedback_type == "false_positive":
            fp_count = int(
                (
                    await self._session.execute(
                        select(func.count(AlertFeedback.id))
                        .join(Alert, Alert.id == AlertFeedback.alert_id)
                        .where(
                            Alert.tenant_id == tenant_id,
                            Alert.rule == alert.rule,
                            AlertFeedback.feedback_type == "false_positive",
                        )
                    )
                ).scalar_one()
            )
        return fb.id, alert.rule, fp_count

    async def cache_triage(
        self,
        *,
        tenant_id: str,
        alert_id: int,
        summary: str,
        severity: str,
        cluster: str,
    ) -> None:
        alert = (
            await self._session.execute(
                select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not alert:
            return
        alert.triage_summary = summary
        alert.triage_severity = severity
        alert.triage_cluster = cluster
        alert.triage_generated_at = datetime.now(timezone.utc)

    # ----- reads ------------------------------------------------------------
    async def list_alerts(
        self,
        *,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
        layer: str | None = None,
        category: str | None = None,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(Alert).where(Alert.tenant_id == tenant_id)
        if layer:
            stmt = stmt.where(Alert.triggered_layer == layer)
        if category:
            stmt = stmt.where(Alert.owasp_category == category)
        if since:
            stmt = stmt.where(Alert.timestamp >= since)
        stmt = stmt.order_by(Alert.id.desc()).limit(limit).offset(offset)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_alert_to_dict(r) for r in rows]

    async def get_incident(
        self, *, tenant_id: str, alert_id: int
    ) -> dict[str, Any] | None:
        primary = (
            await self._session.execute(
                select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if primary is None:
            return None

        if primary.incident_id:
            siblings = (
                await self._session.execute(
                    select(Alert)
                    .where(
                        Alert.tenant_id == tenant_id,
                        Alert.incident_id == primary.incident_id,
                    )
                    .order_by(Alert.id)
                )
            ).scalars().all()
        else:
            siblings = [primary]

        sibling_ids = [s.id for s in siblings]
        feedback_rows = (
            await self._session.execute(
                select(AlertFeedback)
                .where(
                    AlertFeedback.tenant_id == tenant_id,
                    AlertFeedback.alert_id.in_(sibling_ids),
                )
                .order_by(AlertFeedback.id.desc())
            )
        ).scalars().all()

        return {
            "incident_id": primary.incident_id,
            "primary_id": alert_id,
            "violations": [_alert_to_dict(s) for s in siblings],
            "feedback": [_feedback_to_dict(f) for f in feedback_rows],
        }

    async def stats(self, *, tenant_id: str) -> dict[str, Any]:
        total = int(
            (
                await self._session.execute(
                    select(func.count(Alert.id)).where(Alert.tenant_id == tenant_id)
                )
            ).scalar_one()
        )
        by_layer = {
            row.triggered_layer: int(row.n)
            for row in (
                await self._session.execute(
                    select(Alert.triggered_layer, func.count().label("n"))
                    .where(Alert.tenant_id == tenant_id)
                    .group_by(Alert.triggered_layer)
                )
            ).all()
        }
        by_category = {
            row.owasp_category: int(row.n)
            for row in (
                await self._session.execute(
                    select(Alert.owasp_category, func.count().label("n"))
                    .where(Alert.tenant_id == tenant_id)
                    .group_by(Alert.owasp_category)
                )
            ).all()
        }
        return {"total": total, "by_layer": by_layer, "by_category": by_category}

    async def distinct_rules(self, *, tenant_id: str) -> list[dict[str, Any]]:
        rows = (
            await self._session.execute(
                select(
                    Alert.rule,
                    func.count(Alert.id).label("hits"),
                    func.sum(
                        case((AlertFeedback.feedback_type == "false_positive", 1), else_=0)
                    ).label("fp_count"),
                )
                .outerjoin(AlertFeedback, AlertFeedback.alert_id == Alert.id)
                .where(Alert.tenant_id == tenant_id)
                .group_by(Alert.rule)
                .order_by(func.count(Alert.id).desc())
            )
        ).all()
        return [
            {"rule": r.rule, "hits": int(r.hits), "fp_count": int(r.fp_count or 0)}
            for r in rows
        ]

    async def cluster_counts(
        self, *, tenant_id: str, hours: int = 24
    ) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = (
            await self._session.execute(
                select(
                    Alert.triage_cluster,
                    func.count(Alert.id).label("n"),
                    func.max(Alert.timestamp).label("last_seen"),
                )
                .where(
                    Alert.tenant_id == tenant_id,
                    Alert.triage_cluster.is_not(None),
                    Alert.timestamp >= since,
                )
                .group_by(Alert.triage_cluster)
                .order_by(func.count(Alert.id).desc())
            )
        ).all()
        return [
            {
                "cluster": r.triage_cluster,
                "count": int(r.n),
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            }
            for r in rows
        ]


def _alert_to_dict(a: Alert) -> dict[str, Any]:
    return {
        "id": a.id,
        "tenant_id": a.tenant_id,
        "timestamp": a.timestamp.isoformat() if a.timestamp else None,
        "incident_id": a.incident_id,
        "masked_ip": a.masked_ip,
        "country_code": a.country_code,
        "triggered_layer": a.triggered_layer,
        "owasp_category": a.owasp_category,
        "rule": a.rule,
        "detail": a.detail,
        "snippet": a.snippet,
        "model": a.model,
        "model_params": a.model_params,
        "user_agent": a.user_agent,
        "blocked_prompt": a.blocked_prompt,
        "original_prompt": a.original_prompt,
        "sanitized_prompt": a.sanitized_prompt,
        "extra": a.extra,
        "triage": {
            "summary": a.triage_summary,
            "severity": a.triage_severity,
            "cluster": a.triage_cluster,
            "generated_at": a.triage_generated_at.isoformat() if a.triage_generated_at else None,
        } if a.triage_summary else None,
    }


def _feedback_to_dict(f: AlertFeedback) -> dict[str, Any]:
    return {
        "id": f.id,
        "tenant_id": f.tenant_id,
        "alert_id": f.alert_id,
        "incident_id": f.incident_id,
        "feedback_type": f.feedback_type,
        "note": f.note,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
