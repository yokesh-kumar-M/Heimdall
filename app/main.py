from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.policy import PolicyManager
from app.proxy.forwarder import build_http_client
from app.routes.alerts import router as alerts_router
from app.routes.chat import router as chat_router
from app.routes.policies import router as policies_router
from app.routes.sandbox import router as sandbox_router
from app.scanners.semantic import SemanticScanner
from app.telemetry.bus import AlertBus
from app.telemetry.store import TelemetryStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    configure_logging(settings.log_level)

    logger.info("Heimdall starting (v%s) upstream=%s", __version__, settings.upstream_base_url)

    http_client = build_http_client(settings)
    telemetry = TelemetryStore(settings.telemetry_db_path)
    bus = AlertBus()
    policy = PolicyManager(
        settings.telemetry_db_path,
        default_fp_threshold=settings.policy_default_fp_threshold,
    )
    semantic = SemanticScanner(
        client=http_client,
        base_url=settings.semantic_base_url,
        model=settings.semantic_model,
        api_key=settings.semantic_api_key,
        enabled=settings.semantic_enabled,
        fail_closed=settings.semantic_fail_closed,
        timeout=settings.semantic_timeout,
    )

    app.state.settings = settings
    app.state.http_client = http_client
    app.state.telemetry = telemetry
    app.state.bus = bus
    app.state.policy = policy
    app.state.semantic = semantic

    logger.info(
        "Layers active: deterministic=on semantic=%s telemetry=%s",
        "on" if semantic.enabled else "off",
        settings.telemetry_db_path,
    )

    try:
        yield
    finally:
        await http_client.aclose()
        logger.info("Heimdall shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Heimdall",
        version=__version__,
        description=(
            "Security reverse proxy for OpenAI-compatible LLM APIs. "
            "Layered defense: deterministic scanners (L1) → Llama Guard 3 (L2) "
            "→ upstream provider. Blocked requests are audited to SQLite and "
            "mapped to the OWASP LLM Top 10."
        ),
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.include_router(chat_router)
    app.include_router(alerts_router)
    app.include_router(sandbox_router)
    app.include_router(policies_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

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
