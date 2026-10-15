"""Utilidades de seguridad: IP del cliente, límite de solicitudes, token de formulario, antispam,
cabeceras HTTP y neutralización de fórmulas para Excel."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

import httpx
from fastapi import HTTPException, Request

from config import get_settings

settings = get_settings()


# ---------------------------------------------------------------- IP y límites
def client_ip(request: Request) -> str:
    """IP del cliente. Solo se confía en X-Forwarded-For si TRUSTED_PROXY_COUNT > 0."""
    n = settings.trusted_proxy_count
    if n > 0:
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            idx = len(parts) - n
            return parts[idx] if idx >= 0 else parts[0]
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Ventana deslizante en memoria. Con varias instancias del backend usar Redis (ver docs)."""

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int) -> bool:
        """Registra un intento. Devuelve False si se superó el límite."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 50000:  # evita crecimiento sin límite
                for k in [k for k, v in self._hits.items() if not v][:10000]:
                    self._hits.pop(k, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def enforce_rate_limit(request: Request, bucket: str, limit: int, window: int) -> None:
    if not limiter.hit("%s:%s" % (bucket, client_ip(request)), limit, window):
        raise HTTPException(
            status_code=429,
            detail="Demasiadas solicitudes. Espera unos minutos e inténtalo de nuevo.",
            headers={"Retry-After": str(window)},
        )


# ---------------------------------------------------------------- Token de formulario
def _sign(payload: str) -> str:
    return hmac.new(settings.signing_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def issue_form_token(now: Optional[float] = None) -> str:
    ts = str(int(now if now is not None else time.time()))
    nonce = secrets.token_hex(8)
    payload = "%s.%s" % (ts, nonce)
    return "%s.%s" % (payload, _sign(payload))


def check_form_token(token: str, now: Optional[float] = None) -> str:
    """Devuelve 'ok', 'invalid', 'expired' o 'too_fast'."""
    try:
        ts, nonce, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign("%s.%s" % (ts, nonce))):
            return "invalid"
        age = (now if now is not None else time.time()) - int(ts)
    except Exception:
        return "invalid"
    if age > settings.form_token_max_hours * 3600:
        return "expired"
    if age < settings.min_form_seconds:
        return "too_fast"
    return "ok"


# ---------------------------------------------------------------- CAPTCHA opcional (Turnstile)
def verify_turnstile(token: Optional[str], ip: str) -> bool:
    if not settings.turnstile_secret_key:
        return True  # desactivado
    if not token:
        return False
    try:
        r = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": settings.turnstile_secret_key, "response": token, "remoteip": ip},
            timeout=5.0,
        )
        return bool(r.json().get("success"))
    except Exception:
        return False  # si el servicio no responde, no se acepta (el usuario puede reintentar)


# ---------------------------------------------------------------- Cabeceras de seguridad
def security_headers(path: str) -> Dict[str, str]:
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com https://connect.facebook.net; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://www.facebook.com; font-src 'self'; "
        "connect-src 'self' https://connect.facebook.net https://www.facebook.com; frame-src https://challenges.cloudflare.com; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    h = {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), interest-cohort=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "X-Frame-Options": "DENY",
    }
    if settings.is_production:
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if path.startswith("/api/admin") or path.startswith("/admin"):
        h["Cache-Control"] = "no-store"
        h["X-Robots-Tag"] = "noindex, nofollow"
    elif path.startswith("/api"):
        h["Cache-Control"] = "no-store"
    return h


# ---------------------------------------------------------------- Excel
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r", "\n")


def neutralize_formula(value):
    """Prefija con apóstrofo los textos que Excel/Sheets podrían interpretar como fórmula."""
    if isinstance(value, str) and value:
        if value.startswith(_FORMULA_PREFIX) or value.lstrip().startswith(_FORMULA_PREFIX):
            return "'" + value
    return value
