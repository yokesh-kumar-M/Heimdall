"""Heimdall FastAPI app factory.

Everything wires up here:
  * Settings + structured logging
  * DB engine + session factory
  * httpx client, alert bus, semantic scanner, policy manager, triager
  * Middleware: CORS, request_id, rate limit
  * Exception handlers
  * Routers: /v1/chat/completions, /api/*
  * Sentry (optional)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RateLimitMiddleware, RequestIdMiddleware
from app.db import dispose_engine, init_engine, session_factory
from app.policy import PolicyManager
from app.proxy.forwarder import build_http_client
from app.routes.alerts import router as alerts_router
from app.routes.auth_keys import router as keys_router
from app.routes.budget import router as budget_router
from app.routes.chat import router as chat_router
from app.routes.policies import router as policies_router
from app.routes.providers import router as providers_router
from app.routes.sandbox import router as sandbox_router
from app.routes.triage import router as triage_router
from app.scanners.semantic import SemanticScanner
from app.telemetry.bus import AlertBus
from app.triage import Triager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    # Sentry — optional. Only initialise if DSN configured so dev is silent.
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.sentry_environment,
                traces_sample_rate=settings.sentry_traces_sample_rate,
                integrations=[FastApiIntegration()],
                release=__version__,
            )
            logger.info("Sentry initialised")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sentry init failed: %s", exc)

    logger.info(
        "Heimdall starting v=%s tenancy=%s db=%s",
        __version__,
        "multi" if settings.multi_tenant_mode else "single",
        settings.database_url.split("@")[-1],  # don't log creds
    )

    # DB
    init_engine(settings)

    # Shared deps
    http_client = build_http_client(settings)
    bus = AlertBus()
    semantic = SemanticScanner(
        client=http_client,
        base_url=settings.semantic_base_url,
        model=settings.semantic_model,
        api_key=settings.semantic_api_key,
        enabled=settings.semantic_enabled,
        fail_closed=settings.semantic_fail_closed,
        timeout=settings.semantic_timeout,
    )
    policy = PolicyManager(
        session_factory(),
        default_fp_threshold=settings.policy_default_fp_threshold,
    )
    triager = Triager(settings)

    app.state.settings = settings
    app.state.http_client = http_client
    app.state.bus = bus
    app.state.semantic = semantic
    app.state.policy = policy
    app.state.triager = triager

    logger.info(
        "Layers: L1=on L2=%s triage=%s providers=%s",
        "on" if semantic.enabled else "off",
        "anthropic" if triager.configured else "heuristic",
        "tenant-config" if settings.multi_tenant_mode else "global-fallback",
    )

    try:
        yield
    finally:
        await http_client.aclose()
        await dispose_engine()
        logger.info("Heimdall shutdown complete.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Heimdall",
        version=__version__,
        description=(
            "Security reverse proxy for OpenAI-compatible LLM APIs. "
            "Layered defense (L1 deterministic → L2 semantic) plus per-tenant "
            "budgets, multi-provider routing, AI-powered triage, and a full "
            "audit trail mapped to the OWASP LLM Top 10."
        ),
        lifespan=lifespan,
    )

    # ----- middleware (order matters: outermost first) -----
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Heimdall-Provider",
            "X-Heimdall-Budget-Spent-Usd",
            "X-Heimdall-Budget-Limit-Usd",
            "X-Heimdall-Budget-Pct",
            "X-Heimdall-Budget-Warning",
            "X-Request-ID",
        ],
    )

    register_exception_handlers(app)

    # ----- routers -----
    app.include_router(chat_router)             # /v1/chat/completions
    app.include_router(alerts_router)           # /api/alerts/*
    app.include_router(sandbox_router)          # /api/sandbox/evaluate
    app.include_router(policies_router)         # /api/policies/*
    app.include_router(keys_router)             # /api/keys/*
    app.include_router(budget_router)           # /api/billing/*
    app.include_router(providers_router)        # /api/providers/*
    app.include_router(triage_router)           # /api/alerts/{id}/triage etc.

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "service": "heimdall",
            "version": __version__,
            "dashboard": "Open the Next.js dashboard for the UI.",
            "openapi": "/docs",
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )
