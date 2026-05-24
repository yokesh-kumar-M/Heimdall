"""initial schema — multi-tenant Heimdall

Revision ID: 0001
Revises:
Create Date: 2026-05-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JsonCol = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    # --- tenants ---
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- api_keys ---
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_tenant", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # --- alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_id", sa.String(32), nullable=True),
        sa.Column("masked_ip", sa.String(64), nullable=False),
        sa.Column("country_code", sa.String(8), nullable=True),
        sa.Column("triggered_layer", sa.String(32), nullable=False),
        sa.Column("owasp_category", sa.String(80), nullable=False),
        sa.Column("rule", sa.String(120), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("snippet", sa.Text, nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("model_params", JsonCol, nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("blocked_prompt", sa.Text, nullable=False),
        sa.Column("original_prompt", sa.Text, nullable=True),
        sa.Column("sanitized_prompt", sa.Text, nullable=True),
        sa.Column("extra", JsonCol, nullable=True),
        sa.Column("triage_summary", sa.Text, nullable=True),
        sa.Column("triage_severity", sa.String(16), nullable=True),
        sa.Column("triage_cluster", sa.String(64), nullable=True),
        sa.Column("triage_generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_index("ix_alerts_timestamp", "alerts", ["timestamp"])
    op.create_index("ix_alerts_incident_id", "alerts", ["incident_id"])
    op.create_index("ix_alerts_triggered_layer", "alerts", ["triggered_layer"])
    op.create_index("ix_alerts_owasp_category", "alerts", ["owasp_category"])
    op.create_index("ix_alerts_rule", "alerts", ["rule"])
    op.create_index("ix_alerts_triage_cluster", "alerts", ["triage_cluster"])

    # --- alert_feedback ---
    op.create_table(
        "alert_feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("alert_id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), nullable=False),
        sa.Column("incident_id", sa.String(32), nullable=True),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_feedback_tenant_id", "alert_feedback", ["tenant_id"])
    op.create_index("ix_alert_feedback_alert_id", "alert_feedback", ["alert_id"])

    # --- rule_policies ---
    op.create_table(
        "rule_policies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("rule", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("suppress_after_n_fp", sa.Integer, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("auto_suppressed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "rule", name="uq_rule_policies_tenant_rule"),
    )
    op.create_index("ix_rule_policies_tenant_id", "rule_policies", ["tenant_id"])

    # --- usage_records ---
    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("api_key_id", sa.Integer, sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_slug", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("blocked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status_code", sa.Integer, nullable=False, server_default="200"),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index("ix_usage_records_timestamp", "usage_records", ["timestamp"])
    op.create_index("ix_usage_tenant_ts", "usage_records", ["tenant_id", "timestamp"])

    # --- budgets ---
    op.create_table(
        "budgets",
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("monthly_limit_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("warn_at_pct", sa.Integer, nullable=False, server_default="80"),
        sa.Column("hard_cap_usd", sa.Float, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- providers ---
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key_encrypted", sa.Text, nullable=True),
        sa.Column("secret_ref", sa.String(120), nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("routing_strategy", sa.String(32), nullable=False, server_default="primary_failover"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_providers_tenant_slug"),
    )
    op.create_index("ix_providers_tenant_id", "providers", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("providers")
    op.drop_table("budgets")
    op.drop_table("usage_records")
    op.drop_table("rule_policies")
    op.drop_table("alert_feedback")
    op.drop_table("alerts")
    op.drop_table("api_keys")
    op.drop_table("tenants")
