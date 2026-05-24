"""OpenAI-compatible chat completions proxy — tenant-aware.

Flow per request:

  1. Auth         → resolve TenantContext (API key, Clerk JWT, or default).
  2. Budget       → if the tenant has a hard cap and is over it, 402.
  3. L1 scan      → deterministic; respect tenant policy (shadowing).
  4. L2 scan      → semantic; respect tenant policy.
  5. Provider     → pick from tenant's `providers` table with failover.
  6. Forward      → stream or buffered.
  7. Record usage → parse `usage`, price it, write a UsageRecord row.

Blocked requests still get a UsageRecord with cost=0 and blocked=True so the
analytics charts show ALL traffic, not just successful proxies.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_ctx
from app.cost import BudgetCheck, estimate_cost_usd, evaluate_budget, extract_usage
from app.db import get_session
from app.policy import PolicyManager
from app.proxy.forwarder import forward_chat_completion
from app.proxy.router import select_provider
from app.repositories.budget import BudgetRepo, UsageRepo
from app.repositories.providers import ProviderRepo
from app.repositories.telemetry import TelemetryRepo
from app.scanners.base import ScanResult, Violation
from app.scanners.deterministic import deterministic_scanner
from app.scanners.semantic import SemanticScanner
from app.schemas.openai import ChatCompletionRequest
from app.telemetry.bus import AlertBus
from app.telemetry.geoip import lookup_country

_MODEL_PARAM_KEYS = {
    "model", "temperature", "top_p", "max_tokens", "max_completion_tokens",
    "n", "stream", "response_format", "tool_choice",
}

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _mask_for_event(ip: str | None) -> str:
    if not ip:
        return "unknown"
    if ":" in ip:
        return ip.rsplit(":", 4)[0] + "::*"
    parts = ip.split(".")
    return ".".join(parts[:3]) + ".*" if len(parts) == 4 else ip


def _extract_user_text(payload: dict[str, Any]) -> tuple[str, list[int]]:
    parts: list[str] = []
    indices: list[int] = []
    for i, msg in enumerate(payload.get("messages", []) or []):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
            indices.append(i)
        elif isinstance(content, list):
            text_segments = [
                seg.get("text", "")
                for seg in content
                if isinstance(seg, dict) and seg.get("type") == "text"
            ]
            if text_segments:
                parts.append("\n".join(text_segments))
                indices.append(i)
    return "\n\n".join(parts), indices


def _apply_sanitized(payload: dict[str, Any], sanitized: str, indices: list[int]) -> None:
    if not indices:
        return
    last_idx = indices[-1]
    msg = payload["messages"][last_idx]
    if isinstance(msg.get("content"), str):
        msg["content"] = sanitized
    elif isinstance(msg.get("content"), list):
        for seg in msg["content"]:
            if isinstance(seg, dict) and seg.get("type") == "text":
                seg["text"] = sanitized
                break


def _security_response(scan: ScanResult, incident_id: str | None = None) -> JSONResponse:
    payload = {
        "error": {
            "type": "security_violation",
            "message": "Request blocked by Heimdall security gateway.",
            "layer": scan.layer,
            "violations": [
                {
                    "rule": v.rule,
                    "category": v.category.value,
                    "detail": v.detail,
                    "snippet": v.snippet,
                }
                for v in scan.violations
            ],
        }
    }
    if incident_id:
        payload["error"]["incident_id"] = incident_id
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=payload)


def _budget_response(check: BudgetCheck) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        headers=check.to_headers(),
        content={
            "error": {
                "type": "budget_exceeded",
                "message": check.reason or "Monthly budget exceeded.",
                "spent_usd": round(check.spent_usd, 4),
                "limit_usd": check.monthly_limit_usd,
                "hard_cap_usd": check.hard_cap_usd,
            }
        },
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post(
    "/v1/chat/completions",
    summary="OpenAI-compatible chat completions proxy (Heimdall-protected)",
    responses={
        200: {"description": "Forwarded upstream response."},
        400: {"description": "Malformed request payload."},
        401: {"description": "Missing/invalid auth (multi-tenant mode)."},
        402: {"description": "Tenant budget exceeded."},
        403: {"description": "Blocked by Heimdall security layers."},
        502: {"description": "Upstream provider unreachable or returned an error."},
        504: {"description": "Upstream provider timed out."},
    },
)
async def chat_completions(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_ctx),
    session: AsyncSession = Depends(get_session),
) -> Any:
    started = time.perf_counter()

    # Parse + validate
    try:
        raw_body = await request.json()
        parsed = ChatCompletionRequest.model_validate(raw_body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={"error": {"type": "invalid_request", "message": f"{exc}"}},
        )

    payload: dict[str, Any] = parsed.model_dump(exclude_none=True)
    user_text, user_msg_indices = _extract_user_text(payload)
    original_user_text = user_text

    settings = request.app.state.settings
    semantic: SemanticScanner = request.app.state.semantic
    bus: AlertBus = request.app.state.bus
    policy: PolicyManager = request.app.state.policy
    telemetry = TelemetryRepo(session)
    budget_repo = BudgetRepo(session)
    usage_repo = UsageRepo(session)
    provider_repo = ProviderRepo(session)

    client_ip = _client_ip(request)
    model = payload.get("model")
    user_agent = request.headers.get("user-agent")
    country_code = lookup_country(client_ip)
    model_params = {k: v for k, v in payload.items() if k in _MODEL_PARAM_KEYS}
    masked_ip = _mask_for_event(client_ip)

    # -- BUDGET pre-check --------------------------------------------------
    budget = await budget_repo.get(tenant_id=ctx.tenant_id)
    mtd = await budget_repo.month_to_date_usd(tenant_id=ctx.tenant_id)
    budget_check = evaluate_budget(budget=budget, month_to_date_usd=mtd)
    if not budget_check.allowed:
        return _budget_response(budget_check)

    # -- L1 scan -----------------------------------------------------------
    det_raw = (
        deterministic_scanner.scan(user_text)
        if user_text
        else ScanResult(layer=deterministic_scanner.layer, safe=True, sanitized_text="")
    )
    det_result, det_shadowed = await policy.apply(ctx.tenant_id, det_raw)

    if det_shadowed:
        await telemetry.log_incident(
            tenant_id=ctx.tenant_id,
            scan=_reconstruct_shadow(det_raw, det_result),
            client_ip=client_ip,
            model=model,
            blocked_prompt=user_text,
            original_prompt=original_user_text,
            sanitized_prompt=det_raw.sanitized_text,
            user_agent=user_agent,
            country_code=country_code,
            model_params=model_params,
            extra={"shadowed_by_policy": True},
        )

    if det_result.blocked:
        incident_id = await telemetry.log_incident(
            tenant_id=ctx.tenant_id,
            scan=det_result,
            client_ip=client_ip,
            model=model,
            blocked_prompt=user_text,
            original_prompt=original_user_text,
            sanitized_prompt=det_result.sanitized_text,
            user_agent=user_agent,
            country_code=country_code,
            model_params=model_params,
        )
        bus.publish(_block_event(ctx.tenant_id, det_result, model, masked_ip, country_code))
        await usage_repo.record(
            tenant_id=ctx.tenant_id, api_key_id=ctx.api_key_id,
            provider_slug="(blocked-l1)", model=model or "(none)",
            prompt_tokens=0, completion_tokens=0, cost_usd=0.0,
            blocked=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status_code=403,
        )
        return _security_response(det_result, incident_id=incident_id)

    if user_text and det_result.sanitized_text != user_text:
        _apply_sanitized(payload, det_result.sanitized_text, user_msg_indices)
        user_text = det_result.sanitized_text

    # -- L2 scan -----------------------------------------------------------
    if semantic.enabled and user_text:
        sem_raw = await semantic.scan(user_text)
        sem_result, sem_shadowed = await policy.apply(ctx.tenant_id, sem_raw)
        if sem_shadowed:
            await telemetry.log_incident(
                tenant_id=ctx.tenant_id,
                scan=_reconstruct_shadow(sem_raw, sem_result),
                client_ip=client_ip,
                model=model,
                blocked_prompt=user_text,
                original_prompt=original_user_text,
                sanitized_prompt=user_text,
                user_agent=user_agent,
                country_code=country_code,
                model_params=model_params,
                extra={"shadowed_by_policy": True},
            )
        if sem_result.blocked:
            incident_id = await telemetry.log_incident(
                tenant_id=ctx.tenant_id,
                scan=sem_result,
                client_ip=client_ip,
                model=model,
                blocked_prompt=user_text,
                original_prompt=original_user_text,
                sanitized_prompt=user_text,
                user_agent=user_agent,
                country_code=country_code,
                model_params=model_params,
                extra=sem_result.raw,
            )
            bus.publish(_block_event(ctx.tenant_id, sem_result, model, masked_ip, country_code))
            await usage_repo.record(
                tenant_id=ctx.tenant_id, api_key_id=ctx.api_key_id,
                provider_slug="(blocked-l2)", model=model or "(none)",
                prompt_tokens=0, completion_tokens=0, cost_usd=0.0,
                blocked=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status_code=403,
            )
            return _security_response(sem_result, incident_id=incident_id)

    # -- Provider selection + failover --------------------------------------
    providers = await provider_repo.list(tenant_id=ctx.tenant_id)
    strategy = providers[0]["routing_strategy"] if providers else "primary_failover"
    failed_ids: set[int] = set()
    last_error: Exception | None = None

    bus.publish(_pass_event(ctx.tenant_id, model, masked_ip, country_code, user_text))

    for attempt in range(max(1, len(providers))):
        chosen = select_provider(
            providers=providers,
            strategy=strategy,
            requested_model=model,
            failed_ids=failed_ids,
            settings=settings,
        )
        if chosen is None:
            return JSONResponse(
                status_code=503,
                content={"error": {"type": "no_provider", "message": "No upstream providers configured."}},
            )
        try:
            response = await forward_chat_completion(
                client=request.app.state.http_client,
                request=request,
                payload=payload,
                provider=chosen,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if chosen.id is not None:
                failed_ids.add(chosen.id)
                await provider_repo.record_health(
                    provider_id=chosen.id, status="degraded",
                    consecutive_failures=999,
                )
            logger.warning("provider %s failed: %s — failing over", chosen.slug, exc)
            continue

        # Mark healthy
        if chosen.id is not None:
            await provider_repo.record_health(
                provider_id=chosen.id, status="up", consecutive_failures=0
            )

        # Record usage + cost
        prompt_tokens, completion_tokens = _maybe_extract_usage(response)
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
        await usage_repo.record(
            tenant_id=ctx.tenant_id,
            api_key_id=ctx.api_key_id,
            provider_slug=chosen.slug,
            model=model or "(none)",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            blocked=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status_code=getattr(response, "status_code", 200),
        )

        # Surface budget info on every response
        for k, v in budget_check.to_headers().items():
            response.headers[k] = v
        response.headers["X-Heimdall-Provider"] = chosen.slug
        return response

    return JSONResponse(
        status_code=502,
        content={"error": {"type": "all_providers_failed",
                           "message": f"All providers failed: {last_error}"}},
    )


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _reconstruct_shadow(raw: ScanResult, effective: ScanResult) -> ScanResult:
    """Build a scan that contains ONLY the policy-shadowed violations so we
    can persist them with a shadow marker without re-blocking the request.
    """
    active_rules = {v.rule for v in effective.violations}
    shadowed: list[Violation] = [v for v in raw.violations if v.rule not in active_rules]
    return ScanResult(
        layer=raw.layer,
        safe=False,
        sanitized_text=raw.sanitized_text,
        violations=shadowed,
        raw={**raw.raw, "shadowed_by_policy": True},
    )


def _block_event(tenant_id, result, model, masked_ip, country):
    return {
        "tenant_id": tenant_id,
        "type": "block",
        "status": 403,
        "layer": result.layer,
        "model": model,
        "masked_ip": masked_ip,
        "country_code": country,
        "rules": [v.rule for v in result.violations],
        "primary_category": result.primary_category().value if result.primary_category() else None,
    }


def _pass_event(tenant_id, model, masked_ip, country, user_text):
    return {
        "tenant_id": tenant_id,
        "type": "pass",
        "status": 200,
        "layer": None,
        "model": model,
        "masked_ip": masked_ip,
        "country_code": country,
        "char_count": len(user_text or ""),
    }


def _maybe_extract_usage(response: Any) -> tuple[int, int]:
    """Pull usage from a JSONResponse body. Skip streaming responses (we can't
    cheaply parse them mid-flight; cost accounting for streams happens via the
    Anthropic/OpenAI usage block when the client opts in to it; otherwise we
    record 0 — explicit zero in the dashboard rather than a guess)."""
    if isinstance(response, StreamingResponse):
        return 0, 0
    try:
        body = getattr(response, "body", None)
        if body:
            import json
            return extract_usage(json.loads(body))
    except Exception:  # noqa: BLE001
        pass
    return 0, 0
