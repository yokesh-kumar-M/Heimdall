"""Cost & budget — pricing table + per-request cost calc + monthly enforcement.

Pricing is **USD per 1M tokens** and reflects public 2025-2026 rates for the
commonly-proxied models. When a model is unknown we still record the request
but with cost=0 — better to undercount than to refuse traffic. The dashboard
shows the missing-price hint so users can extend the table.

To add a model, append to `MODEL_PRICES` below. Wildcards aren't supported
on purpose — explicit beats clever for billing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1M tokens (input/output)."""
    prompt: float
    completion: float


# Conservative, public list-prices as of mid-2026. Update freely.
MODEL_PRICES: dict[str, ModelPrice] = {
    # --- OpenAI ---
    "gpt-4o":              ModelPrice(prompt=2.50,  completion=10.00),
    "gpt-4o-mini":         ModelPrice(prompt=0.15,  completion=0.60),
    "gpt-4.1":             ModelPrice(prompt=2.00,  completion=8.00),
    "gpt-4.1-mini":        ModelPrice(prompt=0.40,  completion=1.60),
    "gpt-4.1-nano":        ModelPrice(prompt=0.10,  completion=0.40),
    "o1":                  ModelPrice(prompt=15.00, completion=60.00),
    "o1-mini":             ModelPrice(prompt=3.00,  completion=12.00),
    "o3-mini":             ModelPrice(prompt=1.10,  completion=4.40),
    # --- Anthropic ---
    "claude-opus-4-7":              ModelPrice(prompt=15.00, completion=75.00),
    "claude-sonnet-4-6":            ModelPrice(prompt=3.00,  completion=15.00),
    "claude-haiku-4-5-20251001":    ModelPrice(prompt=1.00,  completion=5.00),
    "claude-haiku-4-5":             ModelPrice(prompt=1.00,  completion=5.00),
    "claude-3-5-sonnet-20241022":   ModelPrice(prompt=3.00,  completion=15.00),
    # --- Google ---
    "gemini-2.0-flash":     ModelPrice(prompt=0.10, completion=0.40),
    "gemini-2.5-pro":       ModelPrice(prompt=1.25, completion=10.00),
    # --- Open / hosted ---
    "meta-llama/llama-3.3-70b-instruct": ModelPrice(prompt=0.20, completion=0.20),
    "llama-guard3":                       ModelPrice(prompt=0.00, completion=0.00),
}


def estimate_cost_usd(model: str | None, prompt_tokens: int, completion_tokens: int) -> float:
    """Return the USD cost for a single completion. Unknown models → 0."""
    if not model:
        return 0.0
    price = MODEL_PRICES.get(model) or MODEL_PRICES.get(model.lower())
    if price is None:
        # Try to strip a provider prefix like 'openai/gpt-4o-mini'.
        if "/" in model:
            price = MODEL_PRICES.get(model.split("/", 1)[1])
    if price is None:
        return 0.0
    return (prompt_tokens / 1_000_000) * price.prompt + (
        completion_tokens / 1_000_000
    ) * price.completion


def extract_usage(upstream_body: Any) -> tuple[int, int]:
    """Best-effort extraction of OpenAI-style `usage` field from the response.

    OpenAI:   {"usage": {"prompt_tokens": …, "completion_tokens": …}}
    Anthropic OpenAI-compat:  same shape (Anthropic SDK can emit `input_tokens`/`output_tokens`)
    """
    if not isinstance(upstream_body, dict):
        return 0, 0
    usage = upstream_body.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0
    p = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    c = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    try:
        return int(p), int(c)
    except (TypeError, ValueError):
        return 0, 0


# ---------------------------------------------------------------------------
# Budget check result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BudgetCheck:
    allowed: bool
    spent_usd: float
    monthly_limit_usd: float
    hard_cap_usd: float | None
    warn_at_pct: int
    warn: bool
    reason: str | None = None

    def to_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.monthly_limit_usd > 0:
            pct = (self.spent_usd / self.monthly_limit_usd) * 100
            headers["X-Heimdall-Budget-Spent-Usd"] = f"{self.spent_usd:.4f}"
            headers["X-Heimdall-Budget-Limit-Usd"] = f"{self.monthly_limit_usd:.2f}"
            headers["X-Heimdall-Budget-Pct"] = f"{pct:.1f}"
        if self.warn:
            headers["X-Heimdall-Budget-Warning"] = "soft threshold crossed"
        return headers


def evaluate_budget(
    *, budget: dict[str, Any] | None, month_to_date_usd: float
) -> BudgetCheck:
    if budget is None or budget.get("monthly_limit_usd", 0) <= 0:
        return BudgetCheck(
            allowed=True,
            spent_usd=month_to_date_usd,
            monthly_limit_usd=0.0,
            hard_cap_usd=budget.get("hard_cap_usd") if budget else None,
            warn_at_pct=80,
            warn=False,
        )
    limit = float(budget["monthly_limit_usd"])
    hard_cap = budget.get("hard_cap_usd")
    warn_at_pct = int(budget.get("warn_at_pct", 80))
    pct = (month_to_date_usd / limit) * 100 if limit > 0 else 0
    warn = pct >= warn_at_pct

    if hard_cap is not None and month_to_date_usd >= hard_cap:
        return BudgetCheck(
            allowed=False,
            spent_usd=month_to_date_usd,
            monthly_limit_usd=limit,
            hard_cap_usd=hard_cap,
            warn_at_pct=warn_at_pct,
            warn=True,
            reason=f"Hard budget cap ${hard_cap:.2f} reached.",
        )
    return BudgetCheck(
        allowed=True,
        spent_usd=month_to_date_usd,
        monthly_limit_usd=limit,
        hard_cap_usd=hard_cap,
        warn_at_pct=warn_at_pct,
        warn=warn,
    )
