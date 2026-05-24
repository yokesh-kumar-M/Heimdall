"""Shared fixtures for the Heimdall test suite.

Everything here is network-free: stub semantic scanner, in-memory SQLite via
SQLAlchemy, and an httpx transport that refuses real upstream calls.
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
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import init_engine, dispose_engine, session_factory as get_session_factory
from app.models import Base
from app.policy import PolicyManager
from app.repositories.auth import TenantRepo
from app.scanners.base import OwaspCategory, ScanResult, Violation
from app.scanners.semantic import SemanticScanner
from app.telemetry.bus import AlertBus
from app.triage import Triager


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
            return ScanResult(
                layer="semantic",
                safe=False,
                sanitized_text=text,
                violations=[
                    Violation(
                        rule=f"semantic::{code}",
                        category=OwaspCategory.LLM01_PROMPT_INJECTION,
                        detail=f"Stubbed unsafe ({code}).",
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
                layer=self.layer, safe=True, sanitized_text=user_text, raw={"enabled": False},
            )
        return self._verdict(user_text)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    """Run every test against a fresh SQLite file + single-user mode."""
    db_file = tmp_path / "heimdall_test.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("MULTI_TENANT_MODE", "false")
    monkeypatch.setenv("SEMANTIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # heuristic triage
    monkeypatch.setenv("LOG_FORMAT", "text")
    # Reset the LRU-cached settings between tests
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def _db_ready():
    """Init engine + create schema."""
    settings = get_settings()
    engine = init_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed the default tenant.
    sf = get_session_factory()
    async with sf() as session:
        await TenantRepo(session).ensure("default", "Default")
        await session.commit()
    yield
    await dispose_engine()


@pytest.fixture
def stub_semantic() -> StubSemanticScanner:
    return StubSemanticScanner()


@pytest.fixture
def app_factory(_db_ready, stub_semantic):
    """Build a FastAPI app pre-wired with stub state for route-level tests."""
    from fastapi import FastAPI

    from app.core.exceptions import register_exception_handlers
    from app.routes.alerts import router as alerts_router
    from app.routes.auth_keys import router as keys_router
    from app.routes.budget import router as budget_router
    from app.routes.chat import router as chat_router
    from app.routes.policies import router as policies_router
    from app.routes.providers import router as providers_router
    from app.routes.sandbox import router as sandbox_router
    from app.routes.triage import router as triage_router

    def _factory() -> FastAPI:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(chat_router)
        app.include_router(alerts_router)
        app.include_router(sandbox_router)
        app.include_router(policies_router)
        app.include_router(keys_router)
        app.include_router(budget_router)
        app.include_router(providers_router)
        app.include_router(triage_router)

        async def _refuse(_request: httpx.Request) -> httpx.Response:
            raise AssertionError(
                "Test attempted to hit real upstream — scanners should "
                "short-circuit before this point."
            )

        settings = get_settings()
        app.state.settings = settings
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refuse))
        app.state.bus = AlertBus()
        app.state.semantic = stub_semantic
        app.state.policy = PolicyManager(get_session_factory(), default_fp_threshold=3)
        app.state.triager = Triager(settings)
        return app

    return _factory


@pytest.fixture
def client(app_factory):
    app = app_factory()
    with TestClient(app) as c:
        yield c
    asyncio.run(app.state.http_client.aclose())
