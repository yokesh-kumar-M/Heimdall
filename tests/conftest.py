"""Shared fixtures for the Heimdall test suite.

Everything here is network-free: we never call a real LLM or open a real
upstream connection. The semantic scanner is patched to a deterministic
callable, and the app instance uses an in-memory SQLite DB.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable regardless of where pytest is invoked from.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
from typing import Any, Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app.policy import PolicyManager
from app.scanners.base import OwaspCategory, ScanResult, Violation
from app.scanners.semantic import SemanticScanner
from app.telemetry.bus import AlertBus
from app.telemetry.store import TelemetryStore


class StubSemanticScanner(SemanticScanner):
    """A SemanticScanner whose verdict can be set per-test."""

    def __init__(self) -> None:
        self.layer = "semantic"
        self._enabled = True
        self._verdict: Callable[[str], ScanResult] = lambda text: ScanResult(
            layer="semantic", safe=True, sanitized_text=text, raw={"stub": True}
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_verdict(self, fn: Callable[[str], ScanResult]) -> None:
        self._verdict = fn

    def set_unsafe(self, code: str = "S1") -> None:
        def _verdict(text: str) -> ScanResult:
            label, category = (
                "Violent Crimes",
                OwaspCategory.LLM01_PROMPT_INJECTION,
            )
            return ScanResult(
                layer="semantic",
                safe=False,
                sanitized_text=text,
                violations=[
                    Violation(
                        rule=f"semantic::{code}",
                        category=category,
                        detail=f"Stubbed unsafe ({code} — {label}).",
                    )
                ],
                raw={"verdict": "unsafe", "codes": [code], "model_output": "unsafe\n" + code},
            )

        self._verdict = _verdict

    def set_safe(self) -> None:
        self._verdict = lambda text: ScanResult(
            layer="semantic", safe=True, sanitized_text=text, raw={"verdict": "safe"}
        )

    def disable(self) -> None:
        self._enabled = False

    async def scan(self, user_text: str) -> ScanResult:  # type: ignore[override]
        if not self._enabled:
            return ScanResult(
                layer=self.layer, safe=True, sanitized_text=user_text,
                raw={"enabled": False},
            )
        return self._verdict(user_text)


@pytest.fixture
def db_path(tmp_path: Any) -> str:
    return str(tmp_path / "heimdall_test.sqlite3")


@pytest.fixture
def telemetry(db_path: str) -> TelemetryStore:
    return TelemetryStore(db_path)


@pytest.fixture
def policy(db_path: str) -> PolicyManager:
    return PolicyManager(db_path, default_fp_threshold=3)


@pytest.fixture
def stub_semantic() -> StubSemanticScanner:
    return StubSemanticScanner()


@pytest.fixture
def app_factory(
    db_path: str, telemetry: TelemetryStore, policy: PolicyManager, stub_semantic: StubSemanticScanner
):
    """Build a FastAPI app pre-wired with stub state for route-level tests.

    We bypass `create_app`'s lifespan so the test client doesn't need a real
    HTTP client. Each route reads `request.app.state`, which we populate
    directly.
    """
    from fastapi import FastAPI

    from app.core.exceptions import register_exception_handlers
    from app.config import get_settings
    from app.routes.alerts import router as alerts_router
    from app.routes.chat import router as chat_router
    from app.routes.policies import router as policies_router
    from app.routes.sandbox import router as sandbox_router

    def _factory() -> FastAPI:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(chat_router)
        app.include_router(alerts_router)
        app.include_router(sandbox_router)
        app.include_router(policies_router)

        # Use a transport that always raises so any accidental upstream call
        # surfaces loudly as a test bug.
        async def _refuse(_request: httpx.Request) -> httpx.Response:
            raise AssertionError(
                "Test attempted to hit real upstream — scanners should "
                "short-circuit before this point."
            )

        app.state.settings = get_settings()
        app.state.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(_refuse)
        )
        app.state.telemetry = telemetry
        app.state.bus = AlertBus()
        app.state.policy = policy
        app.state.semantic = stub_semantic
        return app

    return _factory


@pytest.fixture
def client(app_factory):
    app = app_factory()
    with TestClient(app) as c:
        yield c
    # Close stubbed http client to silence ResourceWarning.
    asyncio.run(app.state.http_client.aclose())
