"""Lógica de negocio de registros: creación idempotente, búsqueda, estadísticas, anonimización."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import MARKETING_TEXT_VERSION, PRIVACY_NOTICE_VERSION, get_settings
from models import AuditLog, Registration, utcnow
from schemas import FiltersIn, RegistrationIn, clean_campaign_part

log = logging.getLogger("landa.registrations")

settings = get_settings()
MX_TZ = ZoneInfo("America/Mexico_City")
FOLIO_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # sin 0/O/1/I/L para evitar confusiones


def new_folio() -> str:
    raw = "".join(secrets.choice(FOLIO_ALPHABET) for _ in range(8))
    return "LANDA-%s-%s" % (raw[:4], raw[4:])


def audit(db: Session, actor: str, action: str, folio: Optional[str] = None, detail: Optional[str] = None) -> None:
    """Escribe en la bitácora. NO incluir datos personales ni secretos en 'detail'."""
    db.add(AuditLog(actor=actor[:60], action=action, target_folio=folio, detail=(detail or None) and detail[:200]))


def campaign_string(data: RegistrationIn) -> Optional[str]:
    parts = [clean_campaign_part(data.utm_source), clean_campaign_part(data.utm_medium), clean_campaign_part(data.utm_campaign)]
    if not any(parts):
        return None
    return "/".join(p or "-" for p in parts)[:180]


def create_registration(db: Session, data: RegistrationIn) -> Tuple[Registration, bool]:
    """Devuelve (registro, duplicado). Reintentos con la misma idempotency_key devuelven el mismo folio."""
    existing = db.execute(select(Registration).where(Registration.idempotency_key == data.idempotency_key)).scalar_one_or_none()
    if existing:
        return existing, True

    now = utcnow()
    window = now - timedelta(seconds=settings.duplicate_window_seconds)
    # Doble envío accidental: mismos datos en pocos minutos. No bloquea a quien comparte teléfono/correo
    # con otro nombre o cantidad distinta, ni registros posteriores a la ventana.
    dup = db.execute(
        select(Registration).where(
            and_(
                Registration.phone == data.phone,
                Registration.email == data.email,
                func.lower(Registration.full_name) == data.full_name.lower(),
                Registration.attendees == data.attendees,
                Registration.created_at >= window,
            )
        )
    ).scalars().first()
    if dup:
        return dup, True

    marketing = data.marketing_opt_in
    for _ in range(6):
        reg = Registration(
            folio=new_folio(),
            full_name=data.full_name,
            phone=data.phone,
            email=data.email,
            attendees=data.attendees,
            arrival_window=data.arrival_window,
            status="pending",
            created_at=now,
            updated_at=now,
            privacy_version=data.privacy_version,
            privacy_accepted_at=now,
            marketing_opt_in=marketing,
            marketing_consent_at=now if marketing else None,
            marketing_text_version=MARKETING_TEXT_VERSION if marketing else None,
            campaign_source=campaign_string(data),
            idempotency_key=data.idempotency_key,
        )
        db.add(reg)
        try:
            db.commit()
            try:
                from services.sharepoint_sync import notify_sharepoint_webhook, sync_to_sharepoint_files
                sync_to_sharepoint_files(db)
                notify_sharepoint_webhook(reg)
            except Exception as _sync_err:
                log.warning("No se pudo sincronizar a SharePoint en tiempo real: %s", _sync_err)
            return reg, False
        except IntegrityError:
            db.rollback()
            existing = db.execute(
                select(Registration).where(Registration.idempotency_key == data.idempotency_key)
            ).scalar_one_or_none()
            if existing:  # carrera: dos envíos simultáneos con la misma llave
                return existing, True
    raise RuntimeError("No fue posible generar un folio único")


# ------------------------------------------------------------------ búsqueda
def _local_start(d) -> datetime:
    return datetime.combine(d, time.min, tzinfo=MX_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_filters(stmt, f: FiltersIn):
    conds = []
    if f.q:
        q = f.q.strip().lower()
        digits = "".join(ch for ch in q if ch.isdigit())
        like = "%" + _esc(q) + "%"
        parts = [
            func.lower(Registration.full_name).like(like, escape="\\"),
            func.lower(Registration.email).like(like, escape="\\"),
            func.lower(Registration.folio).like(like, escape="\\"),
        ]
        if len(digits) >= 3:
            parts.append(Registration.phone.like("%" + digits + "%"))
        conds.append(or_(*parts))
    if f.status:
        conds.append(Registration.status == f.status)
    if f.date_from:
        conds.append(Registration.created_at >= _local_start(f.date_from))
    if f.date_to:
        conds.append(Registration.created_at < _local_start(f.date_to) + timedelta(days=1))
    if f.min_attendees:
        conds.append(Registration.attendees >= f.min_attendees)
    if f.max_attendees:
        conds.append(Registration.attendees <= f.max_attendees)
    if f.marketing == "allowed":
        conds.append(
            and_(Registration.marketing_opt_in.is_(True), Registration.marketing_revoked_at.is_(None), Registration.anonymized_at.is_(None))
        )
    elif f.marketing == "not_allowed":
        conds.append(
            or_(
                Registration.marketing_opt_in.is_(False),
                Registration.marketing_revoked_at.is_not(None),
                Registration.anonymized_at.is_not(None),
            )
        )
    if conds:
        stmt = stmt.where(and_(*conds))
    return stmt


def stats(db: Session) -> dict:
    rows = db.execute(
        select(Registration.status, func.count(Registration.id), func.coalesce(func.sum(Registration.attendees), 0)).group_by(
            Registration.status
        )
    ).all()
    by = {s: {"registrations": 0, "attendees": 0} for s in ("pending", "confirmed", "cancelled")}
    for status, n, a in rows:
        by[status] = {"registrations": int(n), "attendees": int(a)}
    total_regs = sum(v["registrations"] for v in by.values())
    active_attendees = by["pending"]["attendees"] + by["confirmed"]["attendees"]
    return {
        "total_registrations": total_regs,
        "total_attendees": active_attendees,
        "by_status": by,
        "attendees_criterion": "Total de asistentes = suma de la cantidad indicada en registros pendientes y confirmados. "
        "Se excluyen los registros cancelados. Es una estimación declarada por cada persona, no un control de aforo.",
    }


# ------------------------------------------------------------------ anonimización / baja
def anonymize(reg: Registration) -> None:
    """Elimina los datos personales directos y conserva solo lo estadístico (cantidad, fechas, estado)."""
    now = utcnow()
    if reg.marketing_opt_in and not reg.marketing_revoked_at:
        reg.marketing_revoked_at = now
    reg.full_name = None
    reg.phone = None
    reg.email = None
    reg.idempotency_key = None
    reg.marketing_opt_in = False
    reg.anonymized_at = now


def revoke_marketing(reg: Registration) -> bool:
    if reg.marketing_opt_in and not reg.marketing_revoked_at:
        reg.marketing_revoked_at = utcnow()
        return True
    return False
