"""Autenticación administrativa: hashing Argon2id, sesiones en servidor, CSRF y roles."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta
from typing import Optional
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models import AdminSession, AdminUser, utcnow

settings = get_settings()
_hasher = PasswordHasher()  # Argon2id con parámetros por defecto recomendados
_DUMMY_HASH = _hasher.hash("contraseña-ficticia-para-igualar-tiempos")

COMMON_PASSWORDS = {"password1234", "contraseña123", "123456789012", "qwertyuiop12", "administrador1"}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_time() -> None:
    """Verifica contra un hash ficticio para que usuarios inexistentes tarden lo mismo."""
    verify_password(_DUMMY_HASH, "x")


def password_problem(password: str) -> Optional[str]:
    if len(password) < 12:
        return "La contraseña debe tener al menos 12 caracteres."
    if len(password) > 256:
        return "La contraseña es demasiado larga."
    if not (re.search(r"[A-Za-z]", password) and re.search(r"[\d\W_]", password)):
        return "Usa letras y al menos un número o símbolo."
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 5:
        return "Esa contraseña es demasiado común."
    return None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------ sesiones
def create_session(db: Session, user: AdminUser):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    sess = AdminSession(
        token_hash=hash_token(token),
        csrf_token=secrets.token_urlsafe(24),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_hours),
    )
    db.add(sess)
    db.execute(delete(AdminSession).where(AdminSession.expires_at < now))  # limpieza oportunista
    db.commit()
    return token, sess


def destroy_session(db: Session, token: Optional[str]) -> None:
    if token:
        db.execute(delete(AdminSession).where(AdminSession.token_hash == hash_token(token)))
        db.commit()


class AuthContext:
    def __init__(self, user: AdminUser, session: AdminSession):
        self.user = user
        self.session = session


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Sesión no válida o expirada.")


def current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _unauthorized()
    sess = db.execute(select(AdminSession).where(AdminSession.token_hash == hash_token(token))).scalar_one_or_none()
    now = utcnow()
    if not sess:
        raise _unauthorized()
    idle_limit = sess.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if sess.expires_at <= now or idle_limit <= now:
        db.delete(sess)
        db.commit()
        raise _unauthorized()
    user = sess.user
    if not user or not user.is_active:
        raise _unauthorized()
    if (now - sess.last_seen_at).total_seconds() > 30:
        sess.last_seen_at = now
        db.commit()
    return AuthContext(user, sess)


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    origin = origin.rstrip("/")
    host = request.headers.get("host", "")
    if origin in settings.origins or urlparse(origin).netloc == host:
        return
    raise HTTPException(status_code=403, detail="Origen no permitido.")


def auth_read(ctx: AuthContext = Depends(current_auth)) -> AuthContext:
    """Cualquier usuario autenticado (admin o lector) para operaciones de solo lectura."""
    return ctx


def auth_write(request: Request, ctx: AuthContext = Depends(current_auth)) -> AuthContext:
    """Operaciones POST/PATCH/DELETE: exige sesión + token CSRF + origen válido."""
    check_origin(request)
    sent = request.headers.get("x-csrf-token", "")
    if not sent or not secrets.compare_digest(sent, ctx.session.csrf_token):
        raise HTTPException(status_code=403, detail="Token CSRF no válido.")
    return ctx


def auth_admin(ctx: AuthContext = Depends(auth_write)) -> AuthContext:
    """Operaciones que modifican o exportan datos: solo rol 'admin'."""
    if ctx.user.role != "admin":
        raise HTTPException(status_code=403, detail="Tu cuenta no tiene permiso para esta acción.")
    return ctx
