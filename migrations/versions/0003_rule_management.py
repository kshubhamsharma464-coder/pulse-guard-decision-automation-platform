"""dynamic Rule Management platform: incidents table, audit_log.reason,
rule_sets.activated_at type fix (Phase 2.5)

The rule_sets.activated_at column was originally declared as a bare
Optional[str] in models.py (an oversight -- same class of bug as the
Phase-1 "timestamps as strings" issue documented in docs/persistence.md,
just missed on this particular column at the time). It has never held
real data in any live deployment (no live Postgres has been available to
run migrations against in this project so far), so this is a plain type
correction, not a data migration.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Fix rule_sets.activated_at's type --------------------------------
    op.alter_column(
        "rule_sets", "activated_at",
        existing_type=sa.String(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="activated_at::timestamptz",
        existing_nullable=True,
    )

    # -- audit_log.reason ---------------------------------------------------
    op.add_column("audit_log", sa.Column("reason", sa.Text, nullable=True))

    # -- incidents ------------------------------------------------------
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(50), primary_key=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("enriched_context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("degraded_context", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("context_sources_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("context_sources_degraded", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("region", sa.String(50), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_incidents_status_created", "incidents", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("incidents")
    op.drop_column("audit_log", "reason")
    op.alter_column(
        "rule_sets", "activated_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(),
        existing_nullable=True,
    )
