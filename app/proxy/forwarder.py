"""Outbound HTTP client for upstream LLM providers.

`forward_chat_completion(client, request, payload, provider)` takes a
ResolvedProvider (slug + base_url + api_key) so the chat route can fail over
between providers without rebuilding URLs.

For multi-tenant mode the API key comes from the provider config (env var
referenced by `secret_ref`). For single-user mode it's the global settings
fallback — both paths end up here.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.exceptions import (
    UpstreamConnectionError,
    UpstreamProtocolError,
    UpstreamTimeoutError,
)
from app.proxy.router import ResolvedProvider

logger = logging.getLogger(__name__)

_BLOCKED_REQUEST_HEADERS = {
    "host", "content-length", "connection", "keep-alive",
    "proxy-authenticate", "proxy-authorization", "te",
    "trailer", "transfer-encoding", "upgrade", "accept-encoding",
    "authorization",  # we set this from the provider key, never forward client's
}

_BLOCKED_RESPONSE_HEADERS = {
    "content-length", "transfer-encoding", "connection", "content-encoding",
}


def build_http_client(settings: Any) -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        timeout=settings.http_total_timeout,
        connect=settings.http_connect_timeout,
        read=settings.http_read_timeout,
    )
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    return httpx.AsyncClient(timeout=timeout, limits=limits)


def _filter_request_headers(incoming: dict[str, str], provider: ResolvedProvider) -> dict[str, str]:
    out: dict[str, str] = {
        k: v for k, v in incoming.items() if k.lower() not in _BLOCKED_REQUEST_HEADERS
    }
    if provider.api_key:
        out["Authorization"] = f"Bearer {provider.api_key}"
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
    request: Request,
    payload: dict[str, Any],
    provider: ResolvedProvider,
) -> JSONResponse | StreamingResponse:
    url = f"{provider.base_url.rstrip('/')}/chat/completions"
    headers = _filter_request_headers(dict(request.headers), provider)
    is_stream = bool(payload.get("stream"))

    logger.info(
        "forwarding provider=%s url=%s model=%s stream=%s",
        provider.slug, url, payload.get("model"), is_stream,
    )

    if not is_stream:
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("Upstream LLM provider timed out.") from exc
        except httpx.ConnectError as exc:
            raise UpstreamConnectionError("Could not reach upstream LLM provider.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamProtocolError(f"Upstream protocol error: {exc}") from exc

        return JSONResponse(
            status_code=response.status_code,
            content=_safe_json(response),
            headers=_filter_response_headers(response.headers),
        )

    return StreamingResponse(
        _stream_upstream(client, url, payload, headers),
        media_type="text/event-stream",
    )


def _safe_json(response: httpx.Response) -> Any:
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
