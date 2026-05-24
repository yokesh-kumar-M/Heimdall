from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from app.scanners.base import OwaspCategory, ScanResult, Violation


# ---------------------------------------------------------------------------
# Invisible / steganographic Unicode characters commonly used to smuggle
# malicious instructions past human reviewers. Sources: Unicode TR36,
# documented "ASCII smuggling" attacks against LLMs (Joseph Thacker, 2024).
# ---------------------------------------------------------------------------
_INVISIBLE_CHARS = {
    # Zero-width characters
    "​",  # ZERO WIDTH SPACE
    "‌",  # ZERO WIDTH NON-JOINER
    "‍",  # ZERO WIDTH JOINER
    "⁠",  # WORD JOINER
    "﻿",  # ZERO WIDTH NO-BREAK SPACE / BOM
    # Bidirectional control overrides (Trojan Source class of attacks)
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
    # Variation selectors used in "ASCII smuggling" via tag chars
    *(chr(c) for c in range(0xE0020, 0xE0080)),  # Tags block
    "᠎",  # MONGOLIAN VOWEL SEPARATOR
}

_INVISIBLE_RE = re.compile("|".join(re.escape(ch) for ch in _INVISIBLE_CHARS))


# ---------------------------------------------------------------------------
# Jailbreak / prompt-injection trigger phrases. Curated from public corpora:
# DAN family, "ignore previous instructions", developer-mode, role-confusion.
# Patterns are intentionally fuzzy to survive trivial obfuscation.
# ---------------------------------------------------------------------------
_JAILBREAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_previous", re.compile(
        r"ignore\s+(?:all\s+|the\s+|your\s+|any\s+)?(?:previous|prior|earlier|above)\s+(?:instructions?|prompts?|rules?|directives?)",
        re.IGNORECASE,
    )),
    ("disregard_previous", re.compile(
        r"disregard\s+(?:all\s+|the\s+|your\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?)",
        re.IGNORECASE,
    )),
    ("forget_everything", re.compile(
        r"forget\s+(?:everything|all|what)\s+(?:you|i)\s+(?:were\s+told|said|know)",
        re.IGNORECASE,
    )),
    ("system_override", re.compile(
        r"\b(?:system\s+override|override\s+the\s+system|root\s+access\s+granted|sudo\s+mode)\b",
        re.IGNORECASE,
    )),
    ("dan_persona", re.compile(
        r"\b(?:do\s+anything\s+now|you\s+are\s+DAN|act\s+as\s+DAN|enter\s+DAN\s+mode)\b",
        re.IGNORECASE,
    )),
    ("developer_mode", re.compile(
        r"\b(?:developer\s+mode\s+(?:enabled|on|activated)|enable\s+developer\s+mode|dev[\s-]?mode\s+on)\b",
        re.IGNORECASE,
    )),
    ("jailbreak_keyword", re.compile(
        r"\b(?:jailbreak|jailbroken|unfiltered\s+mode|no\s+restrictions?)\b",
        re.IGNORECASE,
    )),
    ("role_reveal", re.compile(
        r"\b(?:reveal|print|show|repeat|output)\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt|hidden\s+instructions?)\b",
        re.IGNORECASE,
    )),
    ("pretend_no_rules", re.compile(
        r"\bpretend\s+(?:you\s+have\s+)?no\s+(?:rules|restrictions|limitations|filters)\b",
        re.IGNORECASE,
    )),
)


# ---------------------------------------------------------------------------
# PII / secret patterns. Designed for high precision (avoid false positives
# on natural text) rather than maximum recall.
# ---------------------------------------------------------------------------
def _luhn_ok(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_PII_PATTERNS: tuple[tuple[str, OwaspCategory, re.Pattern[str], str], ...] = (
    (
        "aws_access_key_id",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\b(?:AKIA|ASIA|AIDA|AGPA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}\b"),
        "AWS access key identifier detected.",
    ),
    (
        "aws_secret_access_key",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(
            r"(?i)aws_secret_access_key\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{40})[\"']?"
        ),
        "AWS secret access key detected.",
    ),
    (
        "github_token",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
        "GitHub personal/OAuth token detected.",
    ),
    (
        "openai_api_key",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
        "OpenAI-style API key detected.",
    ),
    (
        "anthropic_api_key",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
        "Anthropic API key detected.",
    ),
    (
        "google_api_key",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        "Google API key detected.",
    ),
    (
        "slack_token",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\bxox[abpr]-[0-9A-Za-z-]{10,}\b"),
        "Slack token detected.",
    ),
    (
        "private_key_block",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(
            r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED) PRIVATE KEY-----"
        ),
        "Private key material detected.",
    ),
    (
        "us_ssn",
        OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
        re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
        "US Social Security Number detected.",
    ),
)

# Credit cards need a Luhn check after regex match to avoid FP on long numbers.
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _scan_credit_cards(text: str) -> Iterable[Violation]:
    for match in _CC_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 13 or len(digits) > 19:
            continue
        if not _luhn_ok(digits):
            continue
        yield Violation(
            rule="credit_card",
            category=OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE,
            detail="Credit card number (Luhn-valid) detected.",
            snippet=f"{digits[:4]}****{digits[-4:]}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
class DeterministicScanner:
    """Fast, sub-millisecond Layer-1 scanner.

    The contract:
      * `scan(text)` is pure and synchronous — safe to call on every request.
      * Always returns a `ScanResult` with the sanitized text (invisible
        characters stripped + NFC-normalized) so downstream layers and the
        upstream LLM see the same string the security gate evaluated.
      * Verdict is `safe=False` if ANY rule fires.
    """

    layer = "deterministic"

    def scan(self, text: str) -> ScanResult:
        violations: list[Violation] = []

        # 1. Invisible-character detection (Trojan Source / ASCII smuggling)
        hidden = _INVISIBLE_RE.findall(text)
        if hidden:
            violations.append(
                Violation(
                    rule="invisible_unicode",
                    category=OwaspCategory.LLM01_PROMPT_INJECTION,
                    detail=(
                        f"{len(hidden)} invisible/control character(s) found "
                        "and stripped (codepoints: "
                        + ", ".join(sorted({f"U+{ord(c):04X}" for c in hidden}))
                        + ")."
                    ),
                )
            )

        # Strip hidden chars and normalize before further matching so that
        # adversaries cannot bypass downstream patterns with zero-width gaps.
        cleaned = _INVISIBLE_RE.sub("", text)
        cleaned = unicodedata.normalize("NFKC", cleaned)

        # 2. Jailbreak phrase matching (on cleaned text)
        for rule_name, pattern in _JAILBREAK_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                violations.append(
                    Violation(
                        rule=f"jailbreak::{rule_name}",
                        category=OwaspCategory.LLM01_PROMPT_INJECTION,
                        detail=f"Jailbreak trigger phrase matched ({rule_name}).",
                        snippet=match.group(0)[:120],
                    )
                )

        # 3. PII / secret detection
        for rule_name, category, pattern, detail in _PII_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                snippet = match.group(0)
                # Mask all but first/last 4 chars for any long token
                if len(snippet) > 12:
                    snippet = f"{snippet[:4]}…{snippet[-4:]}"
                violations.append(
                    Violation(
                        rule=f"secret::{rule_name}",
                        category=category,
                        detail=detail,
                        snippet=snippet,
                    )
                )

        for violation in _scan_credit_cards(cleaned):
            violations.append(violation)

        return ScanResult(
            layer=self.layer,
            safe=not violations,
            sanitized_text=cleaned,
            violations=violations,
        )


# Singleton — the scanner has no per-request state.
deterministic_scanner = DeterministicScanner()
