"""Rutas públicas: configuración, token de formulario, registro y baja de publicidad."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import MARKETING_TEXT_VERSION, PRIVACY_NOTICE_VERSION, PRIVACY_PLACEHOLDER, get_settings
from database import get_db
from models import Registration
from schemas import FOLIO_RE, RegistrationIn, RegistrationOut, RevocationIn, iso
from security import check_form_token, client_ip, enforce_rate_limit, issue_form_token, verify_turnstile
from services import registrations as svc

router = APIRouter(prefix="/api")
settings = get_settings()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/config")
def public_config():
    """Configuración pública. No contiene secretos."""
    ph = PRIVACY_PLACEHOLDER
    return {
        "max_attendees": settings.max_attendees,
        "privacy_version": PRIVACY_NOTICE_VERSION,
        "marketing_text_version": MARKETING_TEXT_VERSION,
        "event_details_confirmed": settings.event_details_confirmed,
        "turnstile_site_key": settings.turnstile_site_key or None,
        "privacy": {
            "controller_name": settings.privacy_controller_name or ph,
            "controller_address": settings.privacy_controller_address or ph,
            "contact_email": settings.privacy_contact_email or ph,
            "contact_phone": settings.privacy_contact_phone or ph,
            "retention_text": settings.privacy_retention_text or ph,
            "providers_text": settings.privacy_providers_text or ph,
            "transfers_text": settings.privacy_transfers_text or "",
            "legal_configured": settings.legal_configured,
        },
    }


@router.get("/form-token")
def form_token(request: Request):
    enforce_rate_limit(request, "token", 60, 600)
    return {"token": issue_form_token()}


@router.post("/registrations", response_model=RegistrationOut, status_code=201)
def register(payload: RegistrationIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    enforce_rate_limit(request, "register", settings.register_rate_limit, settings.register_rate_window_seconds)

    # Honeypot: los humanos no ven este campo. Se responde "como si" hubiera funcionado, sin guardar nada.
    if payload.website:
        return RegistrationOut(folio="LANDA-0000-0000", attendees=payload.attendees, created_at=iso(svc.utcnow()), duplicate=False)

    tk = check_form_token(payload.form_token)
    if tk == "too_fast":
        raise HTTPException(status_code=429, detail="Revisa tus datos un momento y vuelve a enviar el formulario.")
    if tk != "ok":
        raise HTTPException(status_code=400, detail="La sesión del formulario expiró. Recarga la página e inténtalo de nuevo.")
    if not verify_turnstile(payload.captcha_token, ip):
        raise HTTPException(status_code=400, detail="No pudimos verificar que eres una persona. Inténtalo de nuevo.")

    if payload.privacy_version != PRIVACY_NOTICE_VERSION or (
        payload.marketing_opt_in and payload.marketing_text_version != MARKETING_TEXT_VERSION
    ):
        raise HTTPException(status_code=409, detail="El aviso de privacidad se actualizó. Recarga la página para leerlo y continuar.")

    try:
        reg, duplicate = svc.create_registration(db, payload)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="No pudimos guardar tu registro todavía. Inténtalo de nuevo en un momento.")
    return RegistrationOut(folio=reg.folio, attendees=reg.attendees, created_at=iso(reg.created_at), duplicate=duplicate)


@router.post("/marketing-revocation")
def public_marketing_revocation(payload: RevocationIn, request: Request, db: Session = Depends(get_db)):
    """Baja de publicidad con folio + correo. Respuesta siempre igual para no revelar si existe un registro."""
    enforce_rate_limit(request, "revoke", 10, 3600)
    folio = payload.folio.strip().upper()
    email = payload.email.strip().lower()
    if FOLIO_RE.match(folio):
        reg = db.execute(select(Registration).where(Registration.folio == folio)).scalar_one_or_none()
        if reg and reg.email and secrets.compare_digest(reg.email.lower(), email):
            if svc.revoke_marketing(reg):
                svc.audit(db, "titular (público)", "marketing_revoked", reg.folio, "Revocación solicitada por el titular")
            db.commit()
    return {"message": "Si los datos coinciden con un registro, tu preferencia de publicidad quedó actualizada: no recibirás comunicaciones comerciales."}
