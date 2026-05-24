"""PolicyManager + PolicyRepo: filter/apply, manual upsert, auto-suppress."""

from __future__ import annotations

import pytest

from app.db import session_factory
from app.policy import PolicyManager
from app.repositories.policy import PolicyRepo
from app.scanners.base import OwaspCategory, ScanResult, Violation

TENANT = "default"


def _v(rule: str) -> Violation:
    return Violation(rule=rule, category=OwaspCategory.LLM01_PROMPT_INJECTION, detail="")


def _scan(rules: list[str], layer: str = "deterministic") -> ScanResult:
    return ScanResult(
        layer=layer, safe=False, sanitized_text="",
        violations=[_v(r) for r in rules],
    )


@pytest.fixture
def policy(_db_ready) -> PolicyManager:
    return PolicyManager(session_factory(), default_fp_threshold=3)


@pytest.mark.asyncio
async def test_default_rule_is_enabled(policy: PolicyManager) -> None:
    assert await policy.is_enabled(TENANT, "jailbreak::ignore_previous") is True


@pytest.mark.asyncio
async def test_suppressed_rule_blocks_no_more(policy: PolicyManager) -> None:
    async with session_factory()() as session:
        await PolicyRepo(session, 3).upsert(tenant_id=TENANT,
                                            rule="jailbreak::ignore_previous",
                                            enabled=False)
        await session.commit()
    policy.invalidate(TENANT)
    effective, shadowed = await policy.apply(TENANT, _scan(["jailbreak::ignore_previous"]))
    assert effective.safe is True
    assert len(shadowed) == 1


@pytest.mark.asyncio
async def test_partial_shadow_keeps_active_rules(policy: PolicyManager) -> None:
    async with session_factory()() as session:
        await PolicyRepo(session, 3).upsert(tenant_id=TENANT,
                                            rule="jailbreak::ignore_previous",
                                            enabled=False)
        await session.commit()
    policy.invalidate(TENANT)
    effective, shadowed = await policy.apply(
        TENANT, _scan(["jailbreak::ignore_previous", "secret::aws_access_key_id"])
    )
    assert effective.blocked
    assert {v.rule for v in effective.violations} == {"secret::aws_access_key_id"}
    assert {v.rule for v in shadowed} == {"jailbreak::ignore_previous"}


@pytest.mark.asyncio
async def test_upsert_only_touches_provided_fields(_db_ready) -> None:
    async with session_factory()() as session:
        repo = PolicyRepo(session, 3)
        p1 = await repo.upsert(tenant_id=TENANT, rule="r1", enabled=False, note="first")
        assert p1["note"] == "first"
        p2 = await repo.upsert(tenant_id=TENANT, rule="r1", suppress_after_n_fp=20)
        await session.commit()
    assert p2["enabled"] is False
    assert p2["note"] == "first"
    assert p2["suppress_after_n_fp"] == 20


@pytest.mark.asyncio
async def test_auto_suppress_fires_at_threshold(policy: PolicyManager) -> None:
    assert await policy.on_feedback(tenant_id=TENANT, rule="r1",
                                    feedback_type="false_positive", fp_count=2) is None
    triggered = await policy.on_feedback(tenant_id=TENANT, rule="r1",
                                         feedback_type="false_positive", fp_count=3)
    assert triggered is not None
    assert triggered["enabled"] is False
    assert triggered["auto_suppressed"] is True
    assert "Auto-suppressed" in (triggered["note"] or "")
    assert await policy.is_enabled(TENANT, "r1") is False


@pytest.mark.asyncio
async def test_auto_suppress_respects_per_rule_threshold(policy: PolicyManager) -> None:
    async with session_factory()() as session:
        await PolicyRepo(session, 3).upsert(tenant_id=TENANT, rule="r2",
                                            suppress_after_n_fp=10)
        await session.commit()
    policy.invalidate(TENANT)
    triggered = await policy.on_feedback(tenant_id=TENANT, rule="r2",
                                         feedback_type="false_positive", fp_count=5)
    assert triggered is None
    triggered = await policy.on_feedback(tenant_id=TENANT, rule="r2",
                                         feedback_type="false_positive", fp_count=10)
    assert triggered is not None and triggered["enabled"] is False


@pytest.mark.asyncio
async def test_non_fp_feedback_is_noop(policy: PolicyManager) -> None:
    triggered = await policy.on_feedback(tenant_id=TENANT, rule="r1",
                                         feedback_type="confirmed", fp_count=99)
    assert triggered is None


@pytest.mark.asyncio
async def test_reset_removes_override(_db_ready) -> None:
    async with session_factory()() as session:
        repo = PolicyRepo(session, 3)
        await repo.upsert(tenant_id=TENANT, rule="r1", enabled=False)
        await session.commit()
    async with session_factory()() as session:
        await PolicyRepo(session, 3).reset(tenant_id=TENANT, rule="r1")
        await session.commit()
    async with session_factory()() as session:
        gone = await PolicyRepo(session, 3).get(tenant_id=TENANT, rule="r1")
    assert gone is None


@pytest.mark.asyncio
async def test_list_policies_with_observed(_db_ready) -> None:
    async with session_factory()() as session:
        repo = PolicyRepo(session, 3)
        await repo.upsert(tenant_id=TENANT, rule="explicit", enabled=False)
        await session.commit()
    async with session_factory()() as session:
        out = await PolicyRepo(session, 3).list_policies(
            tenant_id=TENANT, include_unseen_rule_names=["explicit", "observed_only"]
        )
    rules = {p["rule"] for p in out}
    assert {"explicit", "observed_only"} <= rules
    observed = next(p for p in out if p["rule"] == "observed_only")
    assert observed["enabled"] is True
