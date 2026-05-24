"""Tests for the /api/alerts endpoints (list, stats, get-one, feedback)."""

from __future__ import annotations

import asyncio

from app.scanners.base import OwaspCategory, ScanResult, Violation


def _seed(telemetry, *, layer="deterministic", rule="r1") -> int:
    scan = ScanResult(
        layer=layer,
        safe=False,
        sanitized_text="",
        violations=[
            Violation(rule=rule, category=OwaspCategory.LLM01_PROMPT_INJECTION, detail="")
        ],
    )
    asyncio.run(
        telemetry.log_incident(
            scan=scan,
            client_ip="203.0.113.1",
            model="gpt-4o-mini",
            blocked_prompt="bad stuff",
        )
    )
    rows = asyncio.run(telemetry.list_alerts(limit=1))
    return rows[0]["id"]


def test_alerts_list_empty(client) -> None:
    r = client.get("/api/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["alerts"] == []


def test_alerts_list_after_block(client, telemetry) -> None:
    _seed(telemetry)
    r = client.get("/api/alerts")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["alerts"][0]["rule"] == "r1"


def test_alerts_filter_by_layer(client, telemetry) -> None:
    _seed(telemetry, layer="deterministic", rule="det-rule")
    _seed(telemetry, layer="semantic", rule="semantic::S1")
    r = client.get("/api/alerts?layer=semantic")
    body = r.json()
    assert body["count"] == 1
    assert body["alerts"][0]["triggered_layer"] == "semantic"


def test_alerts_stats(client, telemetry) -> None:
    _seed(telemetry)
    r = client.get("/api/alerts/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["by_layer"] == {"deterministic": 1}
    assert "LLM01: Prompt Injection" in body["by_category"]


def test_get_alert_404(client) -> None:
    r = client.get("/api/alerts/999")
    assert r.status_code == 404


def test_get_alert_groups_incident(client, telemetry) -> None:
    alert_id = _seed(telemetry)
    r = client.get(f"/api/alerts/{alert_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["primary_id"] == alert_id
    assert len(body["violations"]) == 1


def test_feedback_records_and_returns_rule(client, telemetry) -> None:
    alert_id = _seed(telemetry, rule="jailbreak::ignore_previous")
    r = client.post(
        f"/api/alerts/{alert_id}/feedback",
        json={"feedback_type": "false_positive", "note": "internal scrubber"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rule"] == "jailbreak::ignore_previous"
    assert body["fp_count"] == 1
    assert body["auto_suppressed"] is None


def test_feedback_threshold_triggers_auto_suppress(client, telemetry) -> None:
    # policy fixture is configured with threshold = 3
    for _ in range(3):
        alert_id = _seed(telemetry, rule="jailbreak::ignore_previous")
        r = client.post(
            f"/api/alerts/{alert_id}/feedback",
            json={"feedback_type": "false_positive"},
        )
        body = r.json()
    assert body["fp_count"] == 3
    assert body["auto_suppressed"] is not None
    assert body["auto_suppressed"]["enabled"] is False
    assert body["auto_suppressed"]["auto_suppressed"] is True
