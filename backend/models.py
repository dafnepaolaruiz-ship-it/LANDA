"""Modelos de datos. Fechas en UTC naive (timestamp sin zona); se convierten al mostrar/exportar."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

STATUSES = ("pending", "confirmed", "cancelled")
ROLES = ("admin", "viewer")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    folio: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(254))
    attendees: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_window: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # Evidencia de consentimiento (solo lo necesario: versión y fecha; no se guarda IP ni user-agent)
    privacy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    privacy_accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing_consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    marketing_text_version: Mapped[Optional[str]] = mapped_column(String(40))
    marketing_revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    campaign_source: Mapped[Optional[str]] = mapped_column(String(180))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    anonymized_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("attendees >= 1", name="ck_registrations_attendees_positive"),
        CheckConstraint("status in ('pending','confirmed','cancelled')", name="ck_registrations_status"),
        Index("ix_registrations_created_at", "created_at"),
        Index("ix_registrations_status", "status"),
    )

    @property
    def marketing_allowed(self) -> bool:
        return bool(self.marketing_opt_in and not self.marketing_revoked_at and not self.anonymized_at)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (CheckConstraint("role in ('admin','viewer')", name="ck_admin_users_role"),)


class AdminSession(Base):
    """Sesión del lado del servidor. Solo se guarda el hash SHA-256 del token."""

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped[AdminUser] = relationship()


class AuditLog(Base):
    """Bitácora de acciones administrativas. No guarda datos personales de asistentes (solo el folio)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target_folio: Mapped[Optional[str]] = mapped_column(String(20))
    detail: Mapped[Optional[str]] = mapped_column(String(200))
