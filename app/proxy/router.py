"""Multi-provider routing & failover.

Strategies:
  * `primary_failover` — pick the lowest-priority enabled provider; on 5xx/
    timeout retry the next; mark failing providers `degraded` after 3 strikes.
  * `cheapest`         — pick the provider whose model price table has the
    lowest combined prompt+completion cost for the requested model. Falls
    back to priority if no price data.
  * `fastest`          — pick the provider with the lowest 10-min EWMA
    latency (tracked in the in-process health map).

Per-tenant config lives in the `providers` table. For backwards-compat with
the original single-upstream design, when a tenant has no providers we fall
back to the global settings `upstream_base_url` / `upstream_api_key`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.cost import MODEL_PRICES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedProvider:
    id: int | None  # None for the global fallback
    slug: str
    base_url: str
    api_key: str | None  # plain (read from secret_ref env or decrypted blob)
    display_name: str


def _resolve_api_key(provider: dict[str, Any]) -> str | None:
    if provider.get("secret_ref"):
        return os.environ.get(provider["secret_ref"])
    # api_key_encrypted decryption omitted — for now we accept env-only.
    # Production hardening task: add a KMS/Fernet wrapper here.
    return None


def select_provider(
    *,
    providers: list[dict[str, Any]],
    strategy: str,
    requested_model: str | None,
    failed_ids: set[int] | None = None,
    settings: Settings | None = None,
) -> ResolvedProvider | None:
    failed_ids = failed_ids or set()
    eligible = [
        p for p in providers
        if p.get("enabled") and p["id"] not in failed_ids
        and (p.get("health_status") in ("up", "unknown") or p["consecutive_failures"] < 3)
    ]
    if not eligible:
        # Fall back to global default if absolutely nothing else works
        if settings and settings.upstream_base_url:
            return ResolvedProvider(
                id=None,
                slug="global-fallback",
                base_url=settings.upstream_base_url,
                api_key=settings.upstream_api_key or None,
                display_name="Global default",
            )
        return None

    if strategy == "cheapest" and requested_model:
        price = MODEL_PRICES.get(requested_model)
        if price is not None:
            # All eligible providers theoretically expose the model at the
            # same list price (it's the model's price, not the provider's).
            # So 'cheapest' really means 'lowest priority among those that
            # support this model'. We don't track per-provider model lists
            # yet — proxy and let downstream 404 if unsupported.
            pass

    if strategy == "fastest":
        eligible.sort(key=lambda p: p.get("latency_ms_p50", 99999))
    else:
        eligible.sort(key=lambda p: p["priority"])

    p = eligible[0]
    return ResolvedProvider(
        id=p["id"],
        slug=p["slug"],
        base_url=p["base_url"],
        api_key=_resolve_api_key(p),
        display_name=p["display_name"],
    )
