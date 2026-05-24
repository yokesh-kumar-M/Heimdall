"""Tests for /api/alerts endpoints (list, stats, get-one, feedback)."""

from __future__ import annotations

import asyncio

from app.db import session_factory
from app.repositories.telemetry import TelemetryRepo
from app.scanners.base import OwaspCategory, ScanResult, Violation


def _seed(*, layer="deterministic", rule="r1") -> int:
    async def _do():
        scan = ScanResult(
            layer=layer, safe=False, sanitized_text="",
            violations=[Violation(rule=rule,
                                  category=OwaspCategory.LLM01_PROMPT_INJECTION,
                                  detail="")],
        )
        async with session_factory()() as session:
            repo = TelemetryRepo(session)
            await repo.log_incident(
                tenant_id="default", scan=scan, client_ip="203.0.113.1",
                model="gpt-4o-mini", blocked_prompt="bad stuff",
            )
            rows = await repo.list_alerts(tenant_id="default", limit=1)
            await session.commit()
            return rows[0]["id"]
    return asyncio.run(_do())


def test_alerts_list_empty(client) -> None:
    r = client.get("/api/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["alerts"] == []


def test_alerts_list_after_block(client) -> None:
    _seed()
    r = client.get("/api/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["alerts"][0]["rule"] == "r1"


def test_alerts_filter_by_layer(client) -> None:
    _seed(layer="deterministic", rule="det-rule")
    _seed(layer="semantic", rule="semantic::S1")
    r = client.get("/api/alerts?layer=semantic")
    body = r.json()
    assert body["count"] == 1
    assert body["alerts"][0]["triggered_layer"] == "semantic"


def test_alerts_stats(client) -> None:
    _seed()
    r = client.get("/api/alerts/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["by_layer"] == {"deterministic": 1}
    assert "LLM01: Prompt Injection" in body["by_category"]


def test_get_alert_404(client) -> None:
    r = client.get("/api/alerts/999")
    assert r.status_code == 404


def test_get_alert_groups_incident(client) -> None:
    alert_id = _seed()
    r = client.get(f"/api/alerts/{alert_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["primary_id"] == alert_id
    assert len(body["violations"]) == 1


def test_feedback_records_and_returns_rule(client) -> None:
    alert_id = _seed(rule="jailbreak::ignore_previous")
    r = client.post(
        f"/api/alerts/{alert_id}/feedback",
        json={"feedback_type": "false_positive", "note": "internal scrubber"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rule"] == "jailbreak::ignore_previous"
    assert body["fp_count"] == 1
    assert body["auto_suppressed"] is None


def test_feedback_threshold_triggers_auto_suppress(client) -> None:
    # policy fixture configured with threshold = 3
    body = {}
    for _ in range(3):
        alert_id = _seed(rule="jailbreak::ignore_previous")
        r = client.post(
            f"/api/alerts/{alert_id}/feedback",
            json={"feedback_type": "false_positive"},
        )
        body = r.json()
    assert body["fp_count"] == 3
    assert body["auto_suppressed"] is not None
    assert body["auto_suppressed"]["enabled"] is False
    assert body["auto_suppressed"]["auto_suppressed"] is True
