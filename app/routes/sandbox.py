"""Phase 1b — Interactive security sandbox.

Runs the same L1 and L2 scanners as the live `/v1/chat/completions` route,
but emits *positional* match data (start/end offsets into the original text)
so the dashboard can highlight inline. It also captures per-phase wall-clock
timing and intentionally bypasses telemetry — sandbox traffic is not an
incident.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.scanners.base import OwaspCategory
from app.scanners.deterministic import (
    _CC_RE,
    _INVISIBLE_RE,
    _JAILBREAK_PATTERNS,
    _PII_PATTERNS,
    _luhn_ok,
)
from app.scanners.semantic import (
    LLAMA_GUARD_TAXONOMY,
    SemanticScanner,
    parse_llama_guard_output,
)

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


class SandboxRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20000)
    run_semantic: bool = True


@router.post(
    "/evaluate",
    summary=(
        "Run the L1 + L2 scanners on a prompt without writing telemetry. "
        "Returns positional match data and per-phase timings for the "
        "interactive sandbox."
    ),
)
async def evaluate(req: SandboxRequest, request: Request) -> dict[str, Any]:
    raw = req.prompt
    semantic: SemanticScanner = request.app.state.semantic

    # ---------- Phase 1: Unicode normalization ----------
    t0 = time.perf_counter()
    invisible_hits = []
    for m in _INVISIBLE_RE.finditer(raw):
        ch = m.group(0)
        invisible_hits.append(
            {
                "start": m.start(),
                "end": m.end(),
                "codepoint": f"U+{ord(ch):04X}",
                "name": _safe_unicode_name(ch),
            }
        )
    stripped = _INVISIBLE_RE.sub("", raw)
    sanitized = unicodedata.normalize("NFKC", stripped)
    unicode_ms = (time.perf_counter() - t0) * 1000

    # ---------- Phase 2: Deterministic regex ----------
    t1 = time.perf_counter()
    det_matches: list[dict[str, Any]] = []

    for rule_name, pattern in _JAILBREAK_PATTERNS:
        for m in pattern.finditer(sanitized):
            det_matches.append(
                _match_dict(
                    rule=f"jailbreak::{rule_name}",
                    category=OwaspCategory.LLM01_PROMPT_INJECTION,
                    detail=f"Jailbreak trigger phrase matched ({rule_name}).",
                    match=m,
                    kind="jailbreak",
                )
            )

    for rule_name, category, pattern, detail in _PII_PATTERNS:
        for m in pattern.finditer(sanitized):
            det_matches.append(
                _match_dict(
                    rule=f"secret::{rule_name}",
                    category=category,
                    detail=detail,
                    match=m,
                    kind="secret",
                )
            )

    for m in _CC_RE.finditer(sanitized):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            det_matches.append(
                _match_dict(
                    rule="secret::credit_card",
                    category=OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
                    detail="Credit card number (Luhn-valid) detected.",
                    match=m,
                    kind="pii",
                    snippet_override=f"{digits[:4]}****{digits[-4:]}",
                )
            )

    det_ms = (time.perf_counter() - t1) * 1000

    # ---------- Phase 3: Semantic (Llama Guard 3) ----------
    sem_payload: dict[str, Any] = {
        "enabled": bool(semantic.enabled),
        "ran": False,
        "ms": 0.0,
        "verdict": None,
        "codes": [],
        "taxonomy": [],
        "raw_output": None,
        "error": None,
    }

    # Only run semantic if requested AND deterministic didn't already block.
    # That mirrors the live route's short-circuit behaviour.
    if (
        req.run_semantic
        and semantic.enabled
        and not det_matches
        and not invisible_hits
    ):
        t2 = time.perf_counter()
        result = await semantic.scan(sanitized)
        sem_payload["ms"] = (time.perf_counter() - t2) * 1000
        sem_payload["ran"] = True

        if "error" in result.raw:
            sem_payload["error"] = result.raw.get("error")
            sem_payload["verdict"] = "degraded"
        else:
            sem_payload["raw_output"] = result.raw.get("model_output")
            if result.safe:
                sem_payload["verdict"] = "safe"
            else:
                codes = result.raw.get("codes") or []
                sem_payload["verdict"] = "unsafe"
                sem_payload["codes"] = codes
                sem_payload["taxonomy"] = [
                    {
                        "code": c,
                        "label": LLAMA_GUARD_TAXONOMY.get(c, ("Unknown", None))[0],
                    }
                    for c in codes
                ]
    elif not req.run_semantic:
        sem_payload["verdict"] = "skipped"

    blocked_by_l1 = bool(det_matches or invisible_hits)
    blocked_by_l2 = sem_payload["verdict"] == "unsafe"
    would_block = blocked_by_l1 or blocked_by_l2

    total_ms = unicode_ms + det_ms + (sem_payload["ms"] or 0.0)

    return {
        "input": raw,
        "sanitized": sanitized,
        "would_block": would_block,
        "blocked_by": (
            "deterministic" if blocked_by_l1 else "semantic" if blocked_by_l2 else None
        ),
        "phases": {
            "unicode": {
                "ms": round(unicode_ms, 3),
                "invisible_chars": invisible_hits,
                "char_count_in": len(raw),
                "char_count_out": len(sanitized),
            },
            "deterministic": {
                "ms": round(det_ms, 3),
                "matches": det_matches,
                "verdict": "blocked" if det_matches else "safe",
            },
            "semantic": sem_payload,
        },
        "totals": {
            "ms": round(total_ms, 3),
            "l1_ms": round(unicode_ms + det_ms, 3),
            "l2_ms": round(sem_payload["ms"] or 0.0, 3),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_unicode_name(ch: str) -> str:
    try:
        return unicodedata.name(ch)
    except ValueError:
        return f"UNNAMED-{ord(ch):04X}"


def _match_dict(
    *,
    rule: str,
    category: OwaspCategory,
    detail: str,
    match: re.Match[str],
    kind: str,
    snippet_override: str | None = None,
) -> dict[str, Any]:
    snippet = snippet_override if snippet_override is not None else match.group(0)
    if len(snippet) > 64:
        snippet = snippet[:30] + "…" + snippet[-30:]
    return {
        "rule": rule,
        "category": category.value,
        "detail": detail,
        "kind": kind,  # 'jailbreak' | 'secret' | 'pii'
        "start": match.start(),
        "end": match.end(),
        "snippet": snippet,
    }
