"""Runtime configuration.

Pulled from environment / .env. Group conventions:
  * Upstream/proxy — defaults that get used if a tenant hasn't configured
    their own provider in the database (single-user dev mode).
  * Auth — Clerk JWKS for verifying dashboard session tokens, plus a
    server-side admin token for ops scripts.
  * Database — single DATABASE_URL drives the async engine. Defaults to a
    local SQLite file so `uvicorn app.main:app --reload` still works
    out of the box.
  * Triage / Anthropic — used by the AI alert-explanation endpoint.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Fallback upstream (used by the "default" tenant) ----
    upstream_base_url: str = Field(default="https://api.openai.com/v1")
    upstream_api_key: str = Field(default="")

    http_connect_timeout: float = 10.0
    http_read_timeout: float = 120.0
    http_total_timeout: float = 180.0

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = Field(
        default="text",
        description="`text` (dev) or `json` (production, ingested by Logtail/Axiom).",
    )

    # ---- Semantic layer (Llama Guard 3) ----
    semantic_enabled: bool = True
    semantic_base_url: str = "http://localhost:11434/v1"
    semantic_model: str = "llama-guard3"
    semantic_api_key: str = ""
    semantic_fail_closed: bool = False
    semantic_timeout: float = 15.0

    # ---- Database (single URL drives SQLAlchemy) ----
    #   dev   sqlite+aiosqlite:///telemetry/heimdall.sqlite3
    #   prod  postgresql+asyncpg://USER:PASS@HOST/DB
    database_url: str = "sqlite+aiosqlite:///telemetry/heimdall.sqlite3"

    # Legacy var kept for backward compatibility with older deployments; if
    # set and database_url is the default, we auto-derive the SQLite URL.
    telemetry_db_path: str = "telemetry/heimdall.sqlite3"

    # ---- Multi-tenancy & auth ----
    multi_tenant_mode: bool = Field(
        default=False,
        description=(
            "When false, every request is attributed to the 'default' tenant "
            "— suits single-user self-host and local dev. When true, requests "
            "MUST present either a Clerk JWT (dashboard) or a Heimdall API "
            "key (proxy) — anonymous traffic is rejected."
        ),
    )
    default_tenant_id: str = "default"

    # Clerk — see https://dashboard.clerk.com/ -> API Keys
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_secret_key: str = ""  # only used for admin-side calls (user lookups)

    # Static admin token for service-to-service calls (CI, healthchecks).
    admin_api_token: str = ""

    # ---- Policy auto-suppress ----
    policy_default_fp_threshold: int = 5

    # ---- AI Triage ----
    anthropic_api_key: str = ""
    triage_model: str = "claude-haiku-4-5-20251001"
    triage_max_per_minute: int = 30  # protect against runaway costs

    # ---- Rate limiting (per tenant, applied on /v1/* proxy routes) ----
    rate_limit_per_minute: int = 600
    rate_limit_per_day: int = 50_000

    # ---- Observability ----
    sentry_dsn: str = ""
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.05

    # ---- CORS (dashboard origin list, comma-separated) ----
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def _normalize_db_url(url: str) -> str:
    # Hosted Postgres providers (Render, Heroku, Neon) hand out `postgres://`
    # or `postgresql://`. SQLAlchemy's async engine needs the `+asyncpg` driver.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Back-compat: if DATABASE_URL wasn't overridden and the legacy
    # TELEMETRY_DB_PATH was, point SQLite at the legacy path.
    if (
        s.database_url == Settings.model_fields["database_url"].default
        and s.telemetry_db_path != Settings.model_fields["telemetry_db_path"].default
    ):
        # mutate via model_copy to keep frozen-like semantics
        s = s.model_copy(update={"database_url": f"sqlite+aiosqlite:///{s.telemetry_db_path}"})
    normalized = _normalize_db_url(s.database_url)
    if normalized != s.database_url:
        s = s.model_copy(update={"database_url": normalized})
    return s
