"""Esquema inicial: registros, usuarios admin, sesiones y bitácora.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("folio", sa.String(20), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120)),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(254)),
        sa.Column("attendees", sa.Integer, nullable=False),
        sa.Column("arrival_window", sa.String(10)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("privacy_version", sa.String(40), nullable=False),
        sa.Column("privacy_accepted_at", sa.DateTime, nullable=False),
        sa.Column("marketing_opt_in", sa.Boolean, nullable=False),
        sa.Column("marketing_consent_at", sa.DateTime),
        sa.Column("marketing_text_version", sa.String(40)),
        sa.Column("marketing_revoked_at", sa.DateTime),
        sa.Column("campaign_source", sa.String(180)),
        sa.Column("idempotency_key", sa.String(64), unique=True),
        sa.Column("anonymized_at", sa.DateTime),
        sa.CheckConstraint("attendees >= 1", name="ck_registrations_attendees_positive"),
        sa.CheckConstraint("status in ('pending','confirmed','cancelled')", name="ck_registrations_status"),
    )
    op.create_index("ix_registrations_created_at", "registrations", ["created_at"])
    op.create_index("ix_registrations_status", "registrations", ["status"])

    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(60), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("failed_attempts", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_login_at", sa.DateTime),
        sa.Column("password_changed_at", sa.DateTime),
        sa.CheckConstraint("role in ('admin','viewer')", name="ck_admin_users_role"),
    )

    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("actor", sa.String(60), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target_folio", sa.String(20)),
        sa.Column("detail", sa.String(200)),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")
    op.drop_table("registrations")
