from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import Settings
from app.core.exceptions import (
    UpstreamConnectionError,
    UpstreamProtocolError,
    UpstreamTimeoutError,
)

logger = logging.getLogger(__name__)

# Hop-by-hop and request-bound headers we must NOT forward upstream.
_BLOCKED_REQUEST_HEADERS = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "accept-encoding",
}

# Headers we strip from the upstream response before relaying to the client.
_BLOCKED_RESPONSE_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "content-encoding",
}


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        timeout=settings.http_total_timeout,
        connect=settings.http_connect_timeout,
        read=settings.http_read_timeout,
    )
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    return httpx.AsyncClient(timeout=timeout, limits=limits)


def _filter_request_headers(incoming: dict[str, str], settings: Settings) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in incoming.items():
        if key.lower() in _BLOCKED_REQUEST_HEADERS:
            continue
        out[key] = value

    # Inject server-side fallback key if client did not provide one.
    if "authorization" not in {k.lower() for k in out} and settings.upstream_api_key:
        out["Authorization"] = f"Bearer {settings.upstream_api_key}"

    return out


def _filter_response_headers(upstream: httpx.Headers) -> dict[str, str]:
    return {
        key: value
        for key, value in upstream.items()
        if key.lower() not in _BLOCKED_RESPONSE_HEADERS
    }


async def forward_chat_completion(
    *,
    client: httpx.AsyncClient,
    settings: Settings,
    request: Request,
    payload: dict[str, Any],
) -> JSONResponse | StreamingResponse:
    """Forward a (sanitized) chat completion payload to the upstream provider.

    Honors `stream=true` by relaying the upstream SSE stream chunk-by-chunk.
    All known network failure modes are mapped to Heimdall exceptions so the
    central exception handler can render consistent JSON errors.
    """

    url = f"{settings.upstream_base_url.rstrip('/')}/chat/completions"
    headers = _filter_request_headers(dict(request.headers), settings)
    is_stream = bool(payload.get("stream"))

    logger.info(
        "forwarding upstream=%s model=%s stream=%s",
        url,
        payload.get("model"),
        is_stream,
    )

    if not is_stream:
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Upstream LLM provider timed out.") from exc
        except httpx.ConnectError as exc:
            raise UpstreamConnectionError(
                "Could not reach upstream LLM provider."
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamProtocolError(f"Upstream protocol error: {exc}") from exc

        return JSONResponse(
            status_code=response.status_code,
            content=_safe_json(response),
            headers=_filter_response_headers(response.headers),
        )

    # Streaming path: open the connection, stream bytes through.
    return StreamingResponse(
        _stream_upstream(client, url, payload, headers),
        media_type="text/event-stream",
    )


def _safe_json(response: httpx.Response) -> Any:
    """Return the upstream response body decoded as JSON, falling back to a
    structured error envelope if the body is not valid JSON.
    """
    try:
        return response.json()
    except ValueError:
        return {
            "error": {
                "type": "upstream_non_json",
                "message": "Upstream returned a non-JSON body.",
                "raw": response.text[:2000],
            }
        }


async def _stream_upstream(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> AsyncIterator[bytes]:
    try:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            async for chunk in resp.aiter_raw():
                if chunk:
                    yield chunk
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError("Upstream LLM provider timed out.") from exc
    except httpx.ConnectError as exc:
        raise UpstreamConnectionError("Could not reach upstream LLM provider.") from exc
    except httpx.HTTPError as exc:
        raise UpstreamProtocolError(f"Upstream protocol error: {exc}") from exc
