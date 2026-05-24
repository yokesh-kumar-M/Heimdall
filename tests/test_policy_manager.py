"""Policy Manager: filter/apply, manual upsert, auto-suppress."""

from __future__ import annotations

import pytest

from app.policy import PolicyManager
from app.scanners.base import OwaspCategory, ScanResult, Violation


def _v(rule: str) -> Violation:
    return Violation(
        rule=rule, category=OwaspCategory.LLM01_PROMPT_INJECTION, detail=""
    )


def _scan(rules: list[str], layer: str = "deterministic") -> ScanResult:
    return ScanResult(
        layer=layer,
        safe=False,
        sanitized_text="",
        violations=[_v(r) for r in rules],
    )


def test_default_rule_is_enabled(policy: PolicyManager) -> None:
    assert policy.is_enabled("jailbreak::ignore_previous") is True


@pytest.mark.asyncio
async def test_suppressed_rule_blocks_no_more(policy: PolicyManager) -> None:
    await policy.upsert(rule="jailbreak::ignore_previous", enabled=False)
    scan = _scan(["jailbreak::ignore_previous"])
    effective, shadowed = policy.apply(scan)
    assert effective.safe is True
    assert len(shadowed) == 1
    assert shadowed[0].rule == "jailbreak::ignore_previous"


@pytest.mark.asyncio
async def test_partial_shadow_keeps_active_rules(policy: PolicyManager) -> None:
    await policy.upsert(rule="jailbreak::ignore_previous", enabled=False)
    scan = _scan(["jailbreak::ignore_previous", "secret::aws_access_key_id"])
    effective, shadowed = policy.apply(scan)
    assert effective.blocked
    assert {v.rule for v in effective.violations} == {"secret::aws_access_key_id"}
    assert {v.rule for v in shadowed} == {"jailbreak::ignore_previous"}


@pytest.mark.asyncio
async def test_upsert_only_touches_provided_fields(policy: PolicyManager) -> None:
    p1 = await policy.upsert(rule="r1", enabled=False, note="first")
    assert p1.note == "first"
    p2 = await policy.upsert(rule="r1", suppress_after_n_fp=20)
    assert p2.enabled is False  # preserved
    assert p2.note == "first"   # preserved
    assert p2.suppress_after_n_fp == 20


@pytest.mark.asyncio
async def test_auto_suppress_fires_at_threshold(policy: PolicyManager) -> None:
    # policy fixture configured threshold = 3
    assert await policy.on_feedback(rule="r1", feedback_type="false_positive", fp_count=2) is None
    triggered = await policy.on_feedback(rule="r1", feedback_type="false_positive", fp_count=3)
    assert triggered is not None
    assert triggered.enabled is False
    assert triggered.auto_suppressed is True
    assert "Auto-suppressed" in (triggered.note or "")
    assert policy.is_enabled("r1") is False


@pytest.mark.asyncio
async def test_auto_suppress_respects_per_rule_threshold(policy: PolicyManager) -> None:
    await policy.upsert(rule="r2", suppress_after_n_fp=10)
    # Same count that would trigger the default still doesn't trip the custom
    triggered = await policy.on_feedback(rule="r2", feedback_type="false_positive", fp_count=5)
    assert triggered is None
    triggered = await policy.on_feedback(rule="r2", feedback_type="false_positive", fp_count=10)
    assert triggered is not None
    assert triggered.enabled is False


@pytest.mark.asyncio
async def test_non_fp_feedback_is_noop(policy: PolicyManager) -> None:
    triggered = await policy.on_feedback(rule="r1", feedback_type="confirmed", fp_count=99)
    assert triggered is None


@pytest.mark.asyncio
async def test_reset_removes_override(policy: PolicyManager) -> None:
    await policy.upsert(rule="r1", enabled=False)
    assert policy.is_enabled("r1") is False
    await policy.reset("r1")
    assert policy.is_enabled("r1") is True


@pytest.mark.asyncio
async def test_persistence_across_instances(db_path: str) -> None:
    p1 = PolicyManager(db_path, default_fp_threshold=3)
    await p1.upsert(rule="r1", enabled=False, note="persist me")
    p2 = PolicyManager(db_path, default_fp_threshold=3)
    stored = await p2.get("r1")
    assert stored is not None
    assert stored.enabled is False
    assert stored.note == "persist me"


@pytest.mark.asyncio
async def test_list_policies_with_observed(policy: PolicyManager) -> None:
    await policy.upsert(rule="explicit", enabled=False)
    policies = await policy.list_policies(
        include_unseen_rule_names=["explicit", "observed_only"]
    )
    rules = {p.rule for p in policies}
    assert {"explicit", "observed_only"} <= rules
    # The observed-only entry should default to enabled=True
    observed = next(p for p in policies if p.rule == "observed_only")
    assert observed.enabled is True
