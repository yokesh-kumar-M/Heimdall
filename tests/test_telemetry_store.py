"""TelemetryRepo tests — SQLAlchemy-backed, tenant-scoped."""

from __future__ import annotations

import pytest

from app.db import session_factory
from app.repositories.telemetry import TelemetryRepo, mask_ip
from app.scanners.base import OwaspCategory, ScanResult, Violation

TENANT = "default"


def test_mask_ipv4() -> None:
    assert mask_ip("10.20.30.40") == "10.20.30.*"


def test_mask_ipv6_collapses_low_bits() -> None:
    masked = mask_ip("2001:db8:85a3::8a2e:370:7334")
    assert masked.endswith("::*")


def test_mask_unknown() -> None:
    assert mask_ip(None) == "unknown"
    assert mask_ip("not-an-ip") == "unknown"


async def _with_repo(fn):
    async with session_factory()() as session:
        repo = TelemetryRepo(session)
        result = await fn(repo)
        await session.commit()
        return result


@pytest.mark.asyncio
async def test_log_incident_writes_all_violations(_db_ready) -> None:
    scan = ScanResult(
        layer="deterministic",
        safe=False,
        sanitized_text="cleaned",
        violations=[
            Violation(rule="jailbreak::ignore_previous",
                      category=OwaspCategory.LLM01_PROMPT_INJECTION, detail="…"),
            Violation(rule="secret::aws_access_key_id",
                      category=OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
                      detail="…", snippet="AKIA…XXXX"),
        ],
    )

    async def _do(repo: TelemetryRepo):
        return await repo.log_incident(
            tenant_id=TENANT, scan=scan, client_ip="203.0.113.7",
            model="gpt-4o-mini", blocked_prompt="ignore previous instructions",
            sanitized_prompt="cleaned",
        )

    incident_id = await _with_repo(_do)
    assert incident_id

    async with session_factory()() as session:
        repo = TelemetryRepo(session)
        rows = await repo.list_alerts(tenant_id=TENANT, limit=10)
    assert len(rows) == 2
    assert {r["rule"] for r in rows} == {
        "jailbreak::ignore_previous", "secret::aws_access_key_id"
    }
    assert rows[0]["masked_ip"] == "203.0.113.*"


@pytest.mark.asyncio
async def test_get_incident_groups_siblings(_db_ready) -> None:
    scan = ScanResult(
        layer="deterministic", safe=False, sanitized_text="x",
        violations=[
            Violation(rule="r1", category=OwaspCategory.LLM01_PROMPT_INJECTION, detail=""),
            Violation(rule="r2", category=OwaspCategory.LLM01_PROMPT_INJECTION, detail=""),
        ],
    )
    async def _do(repo):
        await repo.log_incident(tenant_id=TENANT, scan=scan, client_ip="1.2.3.4",
                                model=None, blocked_prompt="x")
        rows = await repo.list_alerts(tenant_id=TENANT, limit=10)
        return rows[0]["id"], rows[0]["incident_id"]
    pid, incid = await _with_repo(_do)

    async with session_factory()() as session:
        repo = TelemetryRepo(session)
        incident = await repo.get_incident(tenant_id=TENANT, alert_id=pid)
    assert incident
    assert len(incident["violations"]) == 2
    assert incident["incident_id"] == incid


@pytest.mark.asyncio
async def test_stats_count_by_layer_and_category(_db_ready) -> None:
    async def _do(repo):
        for layer, rule in [("deterministic", "r1"), ("semantic", "semantic::S1")]:
            scan = ScanResult(
                layer=layer, safe=False, sanitized_text="",
                violations=[Violation(rule=rule,
                                      category=OwaspCategory.LLM01_PROMPT_INJECTION,
                                      detail="")],
            )
            await repo.log_incident(tenant_id=TENANT, scan=scan,
                                    client_ip="1.1.1.1", model=None, blocked_prompt="x")
    await _with_repo(_do)

    async with session_factory()() as session:
        stats = await TelemetryRepo(session).stats(tenant_id=TENANT)
    assert stats["total"] == 2
    assert stats["by_layer"] == {"deterministic": 1, "semantic": 1}
    assert stats["by_category"]["LLM01: Prompt Injection"] == 2


@pytest.mark.asyncio
async def test_record_feedback_returns_rule_and_fp_count(_db_ready) -> None:
    async def _seed(repo):
        scan = ScanResult(
            layer="deterministic", safe=False, sanitized_text="",
            violations=[Violation(rule="jailbreak::ignore_previous",
                                  category=OwaspCategory.LLM01_PROMPT_INJECTION,
                                  detail="")],
        )
        await repo.log_incident(tenant_id=TENANT, scan=scan, client_ip="1.2.3.4",
                                model="x", blocked_prompt="x")
        rows = await repo.list_alerts(tenant_id=TENANT, limit=1)
        return rows[0]["id"]

    alert_id = await _with_repo(_seed)

    async def _fb(repo):
        return await repo.record_feedback(
            tenant_id=TENANT, alert_id=alert_id,
            feedback_type="false_positive", note="cherrypicked",
        )

    fid, rule, fp = await _with_repo(_fb)
    assert fid > 0
    assert rule == "jailbreak::ignore_previous"
    assert fp == 1


@pytest.mark.asyncio
async def test_distinct_rules_aggregates_hits(_db_ready) -> None:
    async def _do(repo):
        scan = ScanResult(
            layer="deterministic", safe=False, sanitized_text="",
            violations=[
                Violation(rule="r-alpha",
                          category=OwaspCategory.LLM01_PROMPT_INJECTION, detail=""),
                Violation(rule="r-alpha",
                          category=OwaspCategory.LLM01_PROMPT_INJECTION, detail=""),
            ],
        )
        await repo.log_incident(tenant_id=TENANT, scan=scan,
                                client_ip="1.1.1.1", model=None, blocked_prompt="x")
    await _with_repo(_do)
    async with session_factory()() as session:
        rules = await TelemetryRepo(session).distinct_rules(tenant_id=TENANT)
    assert any(r["rule"] == "r-alpha" and r["hits"] == 2 for r in rules)
