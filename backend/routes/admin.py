"""Rutas administrativas. TODAS dependen de una función de autenticación del servidor."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import auth
from auth import AuthContext, auth_admin, auth_read, auth_write
from config import get_settings
from database import get_db
from models import AdminUser, AuditLog, Registration, utcnow
from schemas import (
    ChangePasswordIn,
    ConfirmActionIn,
    FiltersIn,
    LoginIn,
    SearchIn,
    StatusIn,
    FOLIO_RE,
    iso,
    registration_detail,
    registration_summary,
)
from security import client_ip, enforce_rate_limit
from services import registrations as svc
from services.export import build_workbook

router = APIRouter(prefix="/api/admin")
settings = get_settings()


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )


def _session_info(ctx: AuthContext) -> dict:
    return {
        "username": ctx.user.username,
        "role": ctx.user.role,
        "csrf_token": ctx.session.csrf_token,
        "idle_minutes": settings.session_idle_minutes,
        "event_details_confirmed": settings.event_details_confirmed,
        "legal_configured": settings.legal_configured,
    }


# ------------------------------------------------------------------ sesión
@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_origin(request)
    enforce_rate_limit(request, "login", 10, 900)
    username = payload.username.strip().lower()
    user = db.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none()
    now = utcnow()
    generic = HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    if user is None:
        auth.burn_time()
        svc.audit(db, "desconocido", "login_failed", None, "usuario inexistente")
        db.commit()
        raise generic
    if user.locked_until and user.locked_until > now:
        auth.burn_time()
        raise HTTPException(status_code=429, detail="Cuenta bloqueada temporalmente por intentos fallidos. Inténtalo más tarde.")
    if not user.is_active or not auth.verify_password(user.password_hash, payload.password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_attempts = 0
            svc.audit(db, user.username, "account_locked", None, "bloqueo por intentos fallidos")
        svc.audit(db, user.username, "login_failed")
        db.commit()
        raise generic

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    svc.audit(db, user.username, "login")
    db.commit()
    token, sess = auth.create_session(db, user)
    _set_cookie(response, token)
    return _session_info(AuthContext(user, sess))


@router.get("/me")
def me(ctx: AuthContext = Depends(auth_read)):
    return _session_info(ctx)


@router.post("/logout")
def logout(request: Request, response: Response, ctx: AuthContext = Depends(auth_write), db: Session = Depends(get_db)):
    auth.destroy_session(db, request.cookies.get(settings.session_cookie_name))
    svc.audit(db, ctx.user.username, "logout")
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.post("/change-password")
def change_password(payload: ChangePasswordIn, request: Request, response: Response, ctx: AuthContext = Depends(auth_write), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "chpass", 10, 900)
    if not auth.verify_password(ctx.user.password_hash, payload.current_password):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
    problem = auth.password_problem(payload.new_password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    ctx.user.password_hash = auth.hash_password(payload.new_password)
    ctx.user.password_changed_at = utcnow()
    # Cierra TODAS las demás sesiones del usuario y emite una nueva
    from models import AdminSession
    from sqlalchemy import delete
    db.execute(delete(AdminSession).where(AdminSession.user_id == ctx.user.id))
    svc.audit(db, ctx.user.username, "password_changed")
    db.commit()
    token, sess = auth.create_session(db, ctx.user)
    _set_cookie(response, token)
    return _session_info(AuthContext(ctx.user, sess))


# ------------------------------------------------------------------ datos
@router.get("/stats")
def get_stats(ctx: AuthContext = Depends(auth_read), db: Session = Depends(get_db)):
    return svc.stats(db)


@router.post("/registrations/search")
def search(payload: SearchIn, ctx: AuthContext = Depends(auth_write), db: Session = Depends(get_db)):
    """POST (y no GET) para que nombres, teléfonos o correos buscados no queden en URLs ni logs de acceso."""
    base = svc.apply_filters(select(Registration), payload)
    total = db.execute(svc.apply_filters(select(func.count(Registration.id)), payload)).scalar_one()
    att = db.execute(
        svc.apply_filters(select(func.coalesce(func.sum(Registration.attendees), 0)).where(Registration.status != "cancelled"), payload)
    ).scalar_one()
    rows = db.execute(
        base.order_by(Registration.created_at.desc(), Registration.id.desc()).offset((payload.page - 1) * payload.page_size).limit(payload.page_size)
    ).scalars().all()
    pages = max(1, -(-total // payload.page_size))
    return {
        "items": [registration_summary(r) for r in rows],
        "page": payload.page,
        "page_size": payload.page_size,
        "total": total,
        "pages": pages,
        "filtered_attendees": int(att),
    }


def _get_reg(db: Session, folio: str) -> Registration:
    folio = folio.strip().upper()
    reg = db.execute(select(Registration).where(Registration.folio == folio)).scalar_one_or_none() if FOLIO_RE.match(folio) else None
    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    return reg


@router.get("/registrations/{folio}")
def detail(folio: str, ctx: AuthContext = Depends(auth_read), db: Session = Depends(get_db)):
    return registration_detail(_get_reg(db, folio))


@router.patch("/registrations/{folio}/status")
def change_status(folio: str, payload: StatusIn, ctx: AuthContext = Depends(auth_admin), db: Session = Depends(get_db)):
    reg = _get_reg(db, folio)
    old = reg.status
    reg.status = payload.status
    svc.audit(db, ctx.user.username, "status_changed", reg.folio, "%s -> %s" % (old, payload.status))
    db.commit()
    return registration_detail(reg)


@router.post("/registrations/{folio}/revoke-marketing")
def revoke_marketing(folio: str, ctx: AuthContext = Depends(auth_admin), db: Session = Depends(get_db)):
    reg = _get_reg(db, folio)
    changed = svc.revoke_marketing(reg)
    svc.audit(db, ctx.user.username, "marketing_revoked", reg.folio, "Registrado por la organización" if changed else "Sin cambios")
    db.commit()
    return registration_detail(reg)


@router.post("/registrations/{folio}/anonymize")
def anonymize(folio: str, payload: ConfirmActionIn, ctx: AuthContext = Depends(auth_admin), db: Session = Depends(get_db)):
    reg = _get_reg(db, folio)
    if payload.confirm_folio.strip().upper() != reg.folio:
        raise HTTPException(status_code=400, detail="Escribe el folio exacto para confirmar.")
    svc.anonymize(reg)
    svc.audit(db, ctx.user.username, "anonymized", reg.folio, payload.reason)
    db.commit()
    return registration_detail(reg)


@router.post("/registrations/{folio}/delete")
def delete_registration(folio: str, payload: ConfirmActionIn, ctx: AuthContext = Depends(auth_admin), db: Session = Depends(get_db)):
    """Eliminación definitiva (p. ej. cancelación ARCO). POST con confirmación del folio."""
    reg = _get_reg(db, folio)
    if payload.confirm_folio.strip().upper() != reg.folio:
        raise HTTPException(status_code=400, detail="Escribe el folio exacto para confirmar.")
    svc.audit(db, ctx.user.username, "deleted", reg.folio, payload.reason)
    db.delete(reg)
    db.commit()
    return {"ok": True}


@router.post("/export")
def export(filters: FiltersIn, ctx: AuthContext = Depends(auth_admin), db: Session = Depends(get_db)):
    """Exporta TODOS los registros que cumplen los filtros (no solo la página visible)."""
    stmt = svc.apply_filters(select(Registration), filters).order_by(Registration.created_at.asc(), Registration.id.asc())
    rows = db.execute(stmt).scalars().all()
    data = build_workbook(rows, filters, ctx.user.username)
    svc.audit(db, ctx.user.username, "export_xlsx", None, "%d registros" % len(rows))
    db.commit()
    stamp = utcnow().strftime("%Y%m%d-%H%M")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="expo-landa-registros-%s.xlsx"' % stamp,
            "Cache-Control": "no-store",
        },
    )


@router.get("/audit")
def audit_list(page: int = 1, ctx: AuthContext = Depends(auth_read), db: Session = Depends(get_db)):
    page = max(1, min(page, 10000))
    size = 25
    total = db.execute(select(func.count(AuditLog.id))).scalar_one()
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)).scalars().all()
    return {
        "items": [
            {"created_at": iso(a.created_at), "actor": a.actor, "action": a.action, "folio": a.target_folio, "detail": a.detail}
            for a in rows
        ],
        "page": page,
        "pages": max(1, -(-total // size)),
        "total": total,
    }
