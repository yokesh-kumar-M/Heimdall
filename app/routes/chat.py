from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.config import Settings
from app.policy import PolicyManager
from app.proxy.forwarder import forward_chat_completion
from app.scanners.base import ScanResult, Violation
from app.scanners.deterministic import deterministic_scanner
from app.scanners.semantic import SemanticScanner
from app.schemas.openai import ChatCompletionRequest
from app.telemetry.bus import AlertBus
from app.telemetry.geoip import lookup_country
from app.telemetry.store import TelemetryStore


# Model/sampling params we keep on the alert for forensics. Anything outside
# this allowlist is dropped — payload-replay must not leak proprietary fields.
_MODEL_PARAM_KEYS = {
    "model",
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "n",
    "stream",
    "response_format",
    "tool_choice",
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
    """Cheap masking just for live-feed events (telemetry already masks)."""
    if not ip:
        return "unknown"
    if ":" in ip:  # IPv6
        return ip.rsplit(":", 4)[0] + "::*"
    parts = ip.split(".")
    return ".".join(parts[:3]) + ".*" if len(parts) == 4 else ip


def _extract_user_text(payload: dict[str, Any]) -> tuple[str, list[int]]:
    """Concatenate the user-supplied content from the messages array.

    Returns the joined text and the indices of the user messages that
    contributed to it (so we can rewrite them post-sanitization).
    """
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
            # Multimodal content — concatenate any text segments.
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
    """Replace the last user message's text content with the sanitized text.

    For Phase 1+2 we only need to ensure invisible characters are stripped
    from what we forward — most chat flows put the latest user turn at the
    end, so we patch that one and leave earlier messages intact.
    """
    if not indices:
        return
    last_idx = indices[-1]
    messages = payload["messages"]
    msg = messages[last_idx]
    if isinstance(msg.get("content"), str):
        msg["content"] = sanitized
    elif isinstance(msg.get("content"), list):
        # Replace the first text segment with the sanitized text.
        for seg in msg["content"]:
            if isinstance(seg, dict) and seg.get("type") == "text":
                seg["text"] = sanitized
                break


def _security_response(scan: ScanResult, request_id: str | None = None) -> JSONResponse:
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
    if request_id:
        payload["error"]["request_id"] = request_id
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=payload)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post(
    "/v1/chat/completions",
    summary="OpenAI-compatible chat completions proxy (Heimdall-protected)",
    responses={
        200: {"description": "Forwarded upstream response."},
        400: {"description": "Malformed request payload."},
        403: {"description": "Blocked by Heimdall security layers."},
        502: {"description": "Upstream provider unreachable or returned an error."},
        504: {"description": "Upstream provider timed out."},
    },
)
async def chat_completions(request: Request) -> Any:
    # Parse + validate envelope (Pydantic). extra='allow' preserves all
    # OpenAI fields and any provider-specific extensions transparently.
    try:
        raw_body = await request.json()
        parsed = ChatCompletionRequest.model_validate(raw_body)
    except Exception as exc:  # noqa: BLE001 — we want broad validation catch
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "type": "invalid_request",
                    "message": f"Invalid chat completion payload: {exc}",
                }
            },
        )

    payload: dict[str, Any] = parsed.model_dump(exclude_none=True)
    user_text, user_msg_indices = _extract_user_text(payload)
    original_user_text = user_text

    settings: Settings = request.app.state.settings
    telemetry: TelemetryStore = request.app.state.telemetry
    semantic: SemanticScanner = request.app.state.semantic
    bus: AlertBus = request.app.state.bus
    policy: PolicyManager = request.app.state.policy
    client_ip = _client_ip(request)
    model = payload.get("model")
    user_agent = request.headers.get("user-agent")
    country_code = lookup_country(client_ip)
    model_params = {k: v for k, v in payload.items() if k in _MODEL_PARAM_KEYS}
    masked_ip = _mask_for_event(client_ip)

    # -----------------------------------------------------------------
    # LAYER 1 — Deterministic scanners (sub-millisecond)
    # -----------------------------------------------------------------
    det_raw = deterministic_scanner.scan(user_text) if user_text else ScanResult(
        layer=deterministic_scanner.layer, safe=True, sanitized_text=""
    )
    det_result, det_shadowed = policy.apply(det_raw)

    if det_shadowed:
        # Shadowed violations are still telemetered so the audit trail is
        # complete, but they do not gate the request.
        await _log_shadowed(
            telemetry=telemetry,
            scan=det_raw,
            active_rules={v.rule for v in det_result.violations},
            client_ip=client_ip,
            model=model,
            user_text=user_text,
            original_user_text=original_user_text,
            user_agent=user_agent,
            country_code=country_code,
            model_params=model_params,
        )

    if det_result.blocked:
        logger.warning(
            "BLOCK layer=deterministic ip=%s rules=%s",
            client_ip,
            [v.rule for v in det_result.violations],
        )
        await telemetry.log_incident(
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
        bus.publish(
            {
                "type": "block",
                "status": 403,
                "layer": det_result.layer,
                "model": model,
                "masked_ip": masked_ip,
                "country_code": country_code,
                "rules": [v.rule for v in det_result.violations],
                "primary_category": det_result.primary_category().value
                if det_result.primary_category()
                else None,
            }
        )
        return _security_response(det_result)

    # Push sanitized text back into the payload so the upstream LLM never
    # sees the original invisible-char-laden string. Even on a SAFE verdict
    # we forward the NFKC-normalized version.
    if user_text and det_result.sanitized_text != user_text:
        _apply_sanitized(payload, det_result.sanitized_text, user_msg_indices)
        user_text = det_result.sanitized_text

    # -----------------------------------------------------------------
    # LAYER 2 — Semantic classifier (Llama Guard 3)
    # -----------------------------------------------------------------
    if semantic.enabled and user_text:
        sem_raw = await semantic.scan(user_text)
        sem_result, sem_shadowed = policy.apply(sem_raw)
        if sem_shadowed:
            await _log_shadowed(
                telemetry=telemetry,
                scan=sem_raw,
                active_rules={v.rule for v in sem_result.violations},
                client_ip=client_ip,
                model=model,
                user_text=user_text,
                original_user_text=original_user_text,
                user_agent=user_agent,
                country_code=country_code,
                model_params=model_params,
            )
        if sem_result.blocked:
            logger.warning(
                "BLOCK layer=semantic ip=%s codes=%s",
                client_ip,
                [v.rule for v in sem_result.violations],
            )
            await telemetry.log_incident(
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
            bus.publish(
                {
                    "type": "block",
                    "status": 403,
                    "layer": sem_result.layer,
                    "model": model,
                    "masked_ip": masked_ip,
                    "country_code": country_code,
                    "rules": [v.rule for v in sem_result.violations],
                    "primary_category": sem_result.primary_category().value
                    if sem_result.primary_category()
                    else None,
                }
            )
            return _security_response(sem_result)

    # -----------------------------------------------------------------
    # Forward to upstream
    # -----------------------------------------------------------------
    bus.publish(
        {
            "type": "pass",
            "status": 200,
            "layer": None,
            "model": model,
            "masked_ip": masked_ip,
            "country_code": country_code,
            "char_count": len(user_text or ""),
        }
    )
    return await forward_chat_completion(
        client=request.app.state.http_client,
        settings=settings,
        request=request,
        payload=payload,
    )


async def _log_shadowed(
    *,
    telemetry: TelemetryStore,
    scan: ScanResult,
    active_rules: set[str],
    client_ip: str | None,
    model: str | None,
    user_text: str,
    original_user_text: str,
    user_agent: str | None,
    country_code: str | None,
    model_params: dict[str, Any],
) -> None:
    """Persist policy-shadowed violations so the audit trail isn't lost.

    A shadowed scan is reconstructed with ONLY the suppressed violations and
    flagged in `extra` so analysts can spot them. We mark `safe=False` so the
    store's existing block-logging path takes it.
    """
    shadowed: list[Violation] = [v for v in scan.violations if v.rule not in active_rules]
    if not shadowed:
        return
    shadow_scan = ScanResult(
        layer=scan.layer,
        safe=False,
        sanitized_text=scan.sanitized_text,
        violations=shadowed,
        raw={**scan.raw, "shadowed_by_policy": True},
    )
    await telemetry.log_incident(
        scan=shadow_scan,
        client_ip=client_ip,
        model=model,
        blocked_prompt=user_text,
        original_prompt=original_user_text,
        sanitized_prompt=scan.sanitized_text,
        user_agent=user_agent,
        country_code=country_code,
        model_params=model_params,
        extra={"shadowed_by_policy": True},
    )
