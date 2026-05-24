"""SQLAlchemy ORM models for Heimdall.

Naming conventions:
  * `tenant_id` is a string (Clerk user/org IDs are stringly typed, so we keep
    everything string-keyed for symmetry with API keys' "default" tenant).
  * All timestamp columns are timezone-aware UTC.
  * All ID-bearing models have an auto-increment `id` for stable URLs.

A NOTE on multi-tenancy isolation: every query hits these tables MUST filter
by tenant_id. We don't enforce row-level security at the DB layer (works on
Postgres, not SQLite) — enforcement lives in `app/repositories/*` which never
expose a raw `Session` to route code.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Single declarative base — keeps Alembic autogenerate happy."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# JSON column that uses JSONB on Postgres, regular JSON elsewhere. Tighter
# typing in Postgres; SQLite gets the portable JSON1 path.
JsonCol = JSON().with_variant(JSONB(), "postgresql")


# ---------------------------------------------------------------------------
# Auth — tenants + API keys
# ---------------------------------------------------------------------------
class Tenant(Base):
    """One row per Clerk user OR Clerk organization OR the magic 'default'.

    Clerk user IDs look like `user_2NN...`; org IDs like `org_2NN...`. We
    accept both — the dashboard decides which to use based on whether the
    user has an active org context.
    """

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    budget: Mapped["Budget | None"] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )
    providers: Mapped[list["Provider"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class ApiKey(Base):
    """User-facing Heimdall API keys (sk_hd_...).

    We store ONLY the SHA-256 hash. Plain key is shown once on creation and
    cannot be retrieved. `prefix` is the first 12 chars (e.g. sk_hd_abc12) so
    the dashboard can identify keys without a lookup.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_tenant", "tenant_id"),
        Index("ix_api_keys_key_hash", "key_hash"),
    )


# ---------------------------------------------------------------------------
# Telemetry — alerts + feedback (replaces the old hand-rolled SQLite tables)
# ---------------------------------------------------------------------------
class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    incident_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    masked_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    triggered_layer: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owasp_category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rule: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_params: Mapped[dict | None] = mapped_column(JsonCol, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    blocked_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    original_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JsonCol, nullable=True)

    # Triage cache: when the user clicks "Explain this alert", we persist the
    # AI answer so opening the drawer is instant and we don't re-bill.
    triage_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    triage_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    triage_cluster: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    triage_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertFeedback(Base):
    __tablename__ = "alert_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    alert_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), nullable=False, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Policy — per-tenant rule overrides
# ---------------------------------------------------------------------------
class RulePolicy(Base):
    __tablename__ = "rule_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    suppress_after_n_fp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "rule", name="uq_rule_policies_tenant_rule"),
    )


# ---------------------------------------------------------------------------
# Cost & budget
# ---------------------------------------------------------------------------
class UsageRecord(Base):
    """One row per successfully proxied (or blocked-pre-flight-priced) request.

    We persist enough to rebuild a per-tenant invoice without hitting the
    upstream provider's billing API.
    """

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    api_key_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    provider_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    __table_args__ = (
        Index("ix_usage_tenant_ts", "tenant_id", "timestamp"),
    )


class Budget(Base):
    """Per-tenant monthly budget (USD). One row per tenant.

    `warn_at_pct` is a soft threshold — when crossed, responses get a
    `X-Heimdall-Budget-Warning` header. `hard_cap_usd` is enforced before
    the request leaves Heimdall — once exceeded the request is 402'd.
    """

    __tablename__ = "budgets"

    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    monthly_limit_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    warn_at_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    hard_cap_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="budget")


# ---------------------------------------------------------------------------
# Multi-provider routing
# ---------------------------------------------------------------------------
class Provider(Base):
    """A configured upstream LLM provider for a tenant.

    The routing layer picks one per request based on `priority` (lower wins),
    `enabled`, current health, and the routing strategy ("cheapest", "fastest",
    "primary_failover"). Keys are stored encrypted at rest only when the user
    provides them — for self-host they typically live in env vars and the
    `secret_ref` points to those vars.
    """

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)  # openai | anthropic | openrouter | custom-...
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    routing_strategy: Mapped[str] = mapped_column(String(32), default="primary_failover", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="providers")

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_providers_tenant_slug"),
    )
