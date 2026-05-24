"""Tests for the L2 Llama Guard 3 scanner and its parser."""

from __future__ import annotations

import httpx
import pytest

from app.scanners.semantic import (
    LLAMA_GUARD_TAXONOMY,
    SemanticScanner,
    parse_llama_guard_output,
)


def test_parse_safe_verdict() -> None:
    assert parse_llama_guard_output("safe") == (True, [])
    assert parse_llama_guard_output("  safe\n") == (True, [])


def test_parse_unsafe_codes() -> None:
    safe, codes = parse_llama_guard_output("unsafe\nS1,S5")
    assert safe is False
    assert codes == ["S1", "S5"]


def test_parse_unsafe_dedupes_codes() -> None:
    safe, codes = parse_llama_guard_output("unsafe\nS1 S1 S2")
    assert safe is False
    assert codes == ["S1", "S2"]


def test_parse_unparseable_fails_open() -> None:
    safe, codes = parse_llama_guard_output("¯\\_(ツ)_/¯")
    assert safe is True
    assert codes == []


def test_taxonomy_complete() -> None:
    # Llama Guard 3-8B has S1..S14
    for n in range(1, 15):
        assert f"S{n}" in LLAMA_GUARD_TAXONOMY


@pytest.mark.asyncio
async def test_scanner_disabled_passes_through() -> None:
    async with httpx.AsyncClient() as client:
        scanner = SemanticScanner(
            client=client,
            base_url="http://invalid",
            model="x",
            enabled=False,
        )
        result = await scanner.scan("anything")
    assert result.safe
    assert result.raw == {"enabled": False}


@pytest.mark.asyncio
async def test_scanner_unreachable_fail_open() -> None:
    async def _boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    transport = httpx.MockTransport(_boom)
    async with httpx.AsyncClient(transport=transport) as client:
        scanner = SemanticScanner(
            client=client,
            base_url="http://stub/v1",
            model="llama-guard3",
            fail_closed=False,
        )
        result = await scanner.scan("hello")
    assert result.safe
    assert result.raw.get("degraded") is True


@pytest.mark.asyncio
async def test_scanner_unreachable_fail_closed() -> None:
    async def _boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    transport = httpx.MockTransport(_boom)
    async with httpx.AsyncClient(transport=transport) as client:
        scanner = SemanticScanner(
            client=client,
            base_url="http://stub/v1",
            model="llama-guard3",
            fail_closed=True,
        )
        result = await scanner.scan("hello")
    assert result.blocked
    assert result.violations[0].rule == "semantic::scanner_unavailable"


@pytest.mark.asyncio
async def test_scanner_unsafe_response() -> None:
    def _ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "unsafe\nS1,S10"}}
                ]
            },
        )

    transport = httpx.MockTransport(_ok)
    async with httpx.AsyncClient(transport=transport) as client:
        scanner = SemanticScanner(
            client=client,
            base_url="http://stub/v1",
            model="llama-guard3",
        )
        result = await scanner.scan("plot something terrible")
    assert result.blocked
    rules = [v.rule for v in result.violations]
    assert rules == ["semantic::S1", "semantic::S10"]
    assert result.raw["codes"] == ["S1", "S10"]
