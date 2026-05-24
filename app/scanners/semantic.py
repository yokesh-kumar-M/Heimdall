from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.scanners.base import OwaspCategory, ScanResult, Violation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Llama Guard 3 taxonomy
#
# Llama Guard 3 emits a verdict in the form:
#     safe
#     unsafe\nS1,S5
#
# Where the codes map to Meta's safety taxonomy (S1-S14 in Llama Guard 3-8B).
# Source: https://huggingface.co/meta-llama/Llama-Guard-3-8B
# We map each S-code to the closest OWASP LLM Top 10 category for telemetry.
# ---------------------------------------------------------------------------
LLAMA_GUARD_TAXONOMY: dict[str, tuple[str, OwaspCategory]] = {
    "S1":  ("Violent Crimes",         OwaspCategory.LLM01_PROMPT_INJECTION),
    "S2":  ("Non-Violent Crimes",     OwaspCategory.LLM01_PROMPT_INJECTION),
    "S3":  ("Sex-Related Crimes",     OwaspCategory.LLM01_PROMPT_INJECTION),
    "S4":  ("Child Sexual Exploitation", OwaspCategory.LLM01_PROMPT_INJECTION),
    "S5":  ("Defamation",             OwaspCategory.LLM09_MISINFORMATION),
    "S6":  ("Specialized Advice",     OwaspCategory.LLM09_MISINFORMATION),
    "S7":  ("Privacy",                OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE),
    "S8":  ("Intellectual Property",  OwaspCategory.LLM02_SENSITIVE_INFO_DISCLOSURE),
    "S9":  ("Indiscriminate Weapons", OwaspCategory.LLM01_PROMPT_INJECTION),
    "S10": ("Hate",                   OwaspCategory.LLM01_PROMPT_INJECTION),
    "S11": ("Suicide & Self-Harm",    OwaspCategory.LLM01_PROMPT_INJECTION),
    "S12": ("Sexual Content",         OwaspCategory.LLM01_PROMPT_INJECTION),
    "S13": ("Elections",              OwaspCategory.LLM09_MISINFORMATION),
    "S14": ("Code Interpreter Abuse", OwaspCategory.LLM06_EXCESSIVE_AGENCY),
}


_VERDICT_RE = re.compile(r"^\s*(safe|unsafe)\b", re.IGNORECASE)
_CODES_RE = re.compile(r"\bS\d{1,2}\b")


def parse_llama_guard_output(raw: str) -> tuple[bool, list[str]]:
    """Parse a Llama Guard 3 response.

    Returns (safe, codes) where:
      * safe = True  → model said 'safe' (or response was unparseable -- we
                       fail-OPEN by default; see `Semantic*Scanner.fail_closed`).
      * safe = False → model said 'unsafe'. `codes` contains the matched
                       taxonomy codes (e.g. ['S1', 'S10']).
    """
    if not raw:
        return True, []
    verdict_match = _VERDICT_RE.search(raw)
    if not verdict_match:
        return True, []
    verdict = verdict_match.group(1).lower()
    if verdict == "safe":
        return True, []
    codes = _CODES_RE.findall(raw)
    return False, list(dict.fromkeys(codes))  # dedupe, preserve order


class SemanticScanner:
    """Phase 3 — semantic safety classifier via Meta's Llama Guard 3.

    Designed to be backend-agnostic. Works with any OpenAI-compatible endpoint:
      * Ollama:     base_url=http://localhost:11434/v1   model=llama-guard3
      * OpenRouter: base_url=https://openrouter.ai/api/v1
                    model=meta-llama/llama-guard-3-8b
      * vLLM/TGI hosted yourself with Llama Guard 3 weights.

    When `enabled=False` or no base_url is configured, `scan()` returns a
    pass-through safe result so the rest of the pipeline keeps working.
    """

    layer = "semantic"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        api_key: str = "",
        enabled: bool = True,
        fail_closed: bool = False,
        timeout: float = 15.0,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._enabled = enabled and bool(base_url) and bool(model)
        self._fail_closed = fail_closed
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def scan(self, user_text: str) -> ScanResult:
        if not self._enabled:
            return ScanResult(
                layer=self.layer, safe=True, sanitized_text=user_text,
                raw={"enabled": False},
            )

        body = self._build_request_body(user_text)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Llama Guard call failed (%s); fail_closed=%s", exc, self._fail_closed)
            if self._fail_closed:
                return ScanResult(
                    layer=self.layer,
                    safe=False,
                    sanitized_text=user_text,
                    violations=[
                        Violation(
                            rule="semantic::scanner_unavailable",
                            category=OwaspCategory.LLM01_PROMPT_INJECTION,
                            detail="Semantic scanner unreachable and fail_closed=True.",
                        )
                    ],
                    raw={"error": str(exc)},
                )
            return ScanResult(
                layer=self.layer, safe=True, sanitized_text=user_text,
                raw={"degraded": True, "error": str(exc)},
            )

        raw_text = _extract_content(data)
        safe, codes = parse_llama_guard_output(raw_text)

        if safe:
            return ScanResult(
                layer=self.layer, safe=True, sanitized_text=user_text,
                raw={"verdict": "safe", "model_output": raw_text},
            )

        violations: list[Violation] = []
        if not codes:
            violations.append(
                Violation(
                    rule="semantic::unsafe_unspecified",
                    category=OwaspCategory.LLM01_PROMPT_INJECTION,
                    detail="Llama Guard returned 'unsafe' without a taxonomy code.",
                    snippet=raw_text[:160],
                )
            )
        else:
            for code in codes:
                label, category = LLAMA_GUARD_TAXONOMY.get(
                    code,
                    (f"Unknown taxonomy {code}", OwaspCategory.LLM01_PROMPT_INJECTION),
                )
                violations.append(
                    Violation(
                        rule=f"semantic::{code}",
                        category=category,
                        detail=f"Llama Guard flagged {code} — {label}.",
                    )
                )

        return ScanResult(
            layer=self.layer,
            safe=False,
            sanitized_text=user_text,
            violations=violations,
            raw={"verdict": "unsafe", "codes": codes, "model_output": raw_text},
        )

    # -- internals ---------------------------------------------------------

    def _build_request_body(self, user_text: str) -> dict[str, Any]:
        # Llama Guard 3 was trained on a chat-style input where the [INST]
        # wraps a single user turn. The OpenAI-compatible "chat/completions"
        # interface on Ollama/OpenRouter applies the model's chat template
        # automatically, so we only need to send the user message.
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": user_text}],
            "temperature": 0,
            "max_tokens": 64,
            "stream": False,
        }


def _extract_content(data: Any) -> str:
    """Pull the assistant text out of an OpenAI-compatible response."""
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""
