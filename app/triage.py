"""AI-powered alert triage — Claude Haiku 4.5 explains each blocked request
in plain English, suggests an action, and emits a cluster signature so the
dashboard can group similar incidents.

Why Haiku: ~3-4× cheaper than Sonnet, plenty smart enough for "summarise
this 3-line scanner verdict + this 200-token prompt" — and the dashboard
calls it interactively so latency matters.

We cache the result on the Alert row (triage_summary, _severity, _cluster).
Re-opening an explained alert is free.

Costs are budgeted with `triage_max_per_minute` to defend against a
runaway dashboard reloading.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Simple in-process rate limiter so a runaway client can't burn through tokens
# ---------------------------------------------------------------------------
class _Limiter:
    def __init__(self, per_minute: int) -> None:
        self._per_minute = per_minute
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def take(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - 60
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= self._per_minute:
                return False
            self._timestamps.append(now)
            return True


@dataclass(frozen=True)
class TriageResult:
    summary: str
    severity: str  # "low" | "medium" | "high" | "critical"
    suggested_action: str  # human-readable next step
    cluster: str  # short stable hash for grouping similar incidents
    model_used: str | None = None


SYSTEM_PROMPT = """You are Heimdall's security triage assistant. \
Given a blocked LLM request and the scanner's verdict, produce a strictly \
JSON object with these keys:

  summary           — 1-2 plain-English sentences explaining what was blocked
                      and why a security operator should care.
  severity          — one of "low", "medium", "high", "critical".
  suggested_action  — one short sentence: tune policy / investigate user /
                      acknowledge / escalate.
  cluster_signature — a short kebab-case slug that groups identical attack
                      patterns (e.g. "dan-ignore-instructions", "aws-key-leak",
                      "ssn-disclosure"). Same attack ⇒ same signature.

Output ONLY the JSON object, no markdown, no commentary. If the prompt looks \
like a false positive, set severity="low" and say so in the summary."""


def _build_user_prompt(alert: dict[str, Any]) -> str:
    return json.dumps(
        {
            "layer": alert.get("triggered_layer"),
            "rule": alert.get("rule"),
            "owasp_category": alert.get("owasp_category"),
            "detail": alert.get("detail"),
            "snippet": alert.get("snippet"),
            "blocked_prompt_excerpt": (alert.get("blocked_prompt") or "")[:1500],
        },
        ensure_ascii=False,
    )


def _fallback_cluster(alert: dict[str, Any]) -> str:
    """When the model isn't available or returns garbage."""
    seed = f"{alert.get('rule', '')}|{alert.get('owasp_category', '')}"
    return f"unclassified-{hashlib.sha1(seed.encode()).hexdigest()[:10]}"


class Triager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._limiter = _Limiter(settings.triage_max_per_minute)
        self._client: Any | None = None  # lazily constructed Anthropic client

    @property
    def configured(self) -> bool:
        return bool(self._settings.anthropic_api_key)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("anthropic package not installed") from exc
        self._client = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)
        return self._client

    async def triage(self, alert: dict[str, Any]) -> TriageResult:
        if not self.configured:
            # Heuristic fallback so the feature still works on free self-host.
            return self._heuristic(alert)

        if not await self._limiter.take():
            logger.warning("triage rate-limit hit; serving heuristic instead")
            return self._heuristic(alert)

        client = self._get_client()
        try:
            response = await client.messages.create(
                model=self._settings.triage_model,
                max_tokens=400,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_user_prompt(alert)}],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("triage call failed: %s", exc)
            return self._heuristic(alert)

        text = ""
        try:
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    text += block.text
        except Exception:  # noqa: BLE001
            text = ""

        try:
            data = json.loads(text.strip().strip("`").lstrip("json").strip())
        except (ValueError, AttributeError):
            return self._heuristic(alert)

        return TriageResult(
            summary=str(data.get("summary") or "").strip()[:600] or "(no summary)",
            severity=_clamp_severity(str(data.get("severity") or "medium")),
            suggested_action=str(data.get("suggested_action") or "").strip()[:300] or "Review and acknowledge.",
            cluster=str(data.get("cluster_signature") or _fallback_cluster(alert))[:64],
            model_used=self._settings.triage_model,
        )

    def _heuristic(self, alert: dict[str, Any]) -> TriageResult:
        layer = alert.get("triggered_layer", "?")
        rule = alert.get("rule") or "(unknown)"
        category = alert.get("owasp_category") or "(uncategorised)"
        severity = "high" if "secret" in rule or "credit_card" in rule else "medium"
        return TriageResult(
            summary=(
                f"{layer.title()} scanner blocked rule `{rule}` under {category}. "
                "Configure ANTHROPIC_API_KEY in your environment for richer triage."
            ),
            severity=severity,
            suggested_action="Review the prompt, then either acknowledge or mark as false positive.",
            cluster=_fallback_cluster(alert),
            model_used=None,
        )


def _clamp_severity(s: str) -> str:
    s = s.lower().strip()
    return s if s in {"low", "medium", "high", "critical"} else "medium"
