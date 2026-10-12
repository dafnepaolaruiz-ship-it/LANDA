"""Esquemas de entrada/salida con validación estricta en el servidor."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import List, Literal, Optional

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from config import MARKETING_TEXT_VERSION, PRIVACY_NOTICE_VERSION, get_settings

settings = get_settings()

ArrivalWindow = Literal["10-12", "12-15", "15-17", "17-19", "unknown"]
Status = Literal["pending", "confirmed", "cancelled"]

FOLIO_RE = re.compile(r"^LANDA-[A-Z0-9]{4}-[A-Z0-9]{4}$")


# ------------------------------------------------------------------ helpers
def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = "".join(ch for ch in value if ch in " " or not unicodedata.category(ch).startswith("C"))
    return re.sub(r"\s+", " ", value).strip()


def normalize_mx_phone(raw: str) -> Optional[str]:
    """Devuelve 10 dígitos nacionales o None. Acepta espacios, guiones, paréntesis, +52, 52, 044/045."""
    s = raw.strip()
    if not s or not re.fullmatch(r"[\d\s\-\.\(\)\+]+", s):
        return None
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        if not digits.startswith("52"):
            return None
        digits = digits[2:]
        if len(digits) == 11 and digits.startswith("1"):  # formato antiguo +52 1
            digits = digits[1:]
    elif digits.startswith(("044", "045")) and len(digits) == 13:
        digits = digits[3:]
    elif digits.startswith("52") and len(digits) in (12, 13):
        digits = digits[2:]
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return None
    return digits


def clean_campaign_part(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    v = v.strip()[:60]
    return v if re.fullmatch(r"[A-Za-z0-9_\-\.\+ ]+", v) else None


# ------------------------------------------------------------------ público
class RegistrationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=200)
    phone: str = Field(max_length=40)
    email: str = Field(max_length=320)
    attendees: StrictInt
    arrival_window: Optional[ArrivalWindow] = None
    privacy_accepted: StrictBool
    privacy_version: str = Field(max_length=40)
    marketing_opt_in: StrictBool = False
    marketing_text_version: Optional[str] = Field(default=None, max_length=40)
    form_token: str = Field(max_length=200)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9\-]{16,64}$")
    website: Optional[str] = Field(default="", max_length=200)  # honeypot: debe venir vacío
    captcha_token: Optional[str] = Field(default=None, max_length=2048)
    utm_source: Optional[str] = Field(default=None, max_length=100)
    utm_medium: Optional[str] = Field(default=None, max_length=100)
    utm_campaign: Optional[str] = Field(default=None, max_length=100)

    @field_validator("full_name")
    @classmethod
    def v_name(cls, v: str) -> str:
        v = clean_text(v)
        if len(v) < 3:
            raise ValueError("Escribe tu nombre completo.")
        if len(v) > 120:
            raise ValueError("El nombre es demasiado largo (máximo 120 caracteres).")
        if not any(ch.isalpha() for ch in v):
            raise ValueError("El nombre debe contener letras.")
        return v

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: str) -> str:
        n = normalize_mx_phone(v)
        if not n:
            raise ValueError("Escribe un celular mexicano de 10 dígitos, por ejemplo 449 123 4567.")
        return n

    @field_validator("email")
    @classmethod
    def v_email(cls, v: str) -> str:
        try:
            info = validate_email(v.strip(), check_deliverability=False)
        except EmailNotValidError:
            raise ValueError("Escribe un correo electrónico válido, por ejemplo nombre@correo.com.")
        email = info.normalized
        if len(email) > 254:
            raise ValueError("El correo electrónico es demasiado largo.")
        return email

    @field_validator("attendees")
    @classmethod
    def v_attendees(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Indica al menos 1 asistente (tú).")
        if v > settings.max_attendees:
            raise ValueError("Para grupos de más de %d personas, contáctanos directamente." % settings.max_attendees)
        return v

    @field_validator("privacy_accepted")
    @classmethod
    def v_privacy(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Debes aceptar el Aviso de Privacidad para registrar tu asistencia.")
        return v


class RegistrationOut(BaseModel):
    folio: str
    attendees: int
    created_at: str
    duplicate: bool = False


class RevocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folio: str = Field(max_length=30)
    email: str = Field(max_length=320)


# ------------------------------------------------------------------ admin
class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class FiltersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: Optional[str] = Field(default=None, max_length=100)
    status: Optional[Status] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_attendees: Optional[int] = Field(default=None, ge=1, le=1000)
    max_attendees: Optional[int] = Field(default=None, ge=1, le=1000)
    marketing: Optional[Literal["allowed", "not_allowed"]] = None


class SearchIn(FiltersIn):
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=25, ge=1, le=100)


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status


class ConfirmActionIn(BaseModel):
    """Para acciones destructivas: exige confirmar el folio escrito."""
    model_config = ConfigDict(extra="forbid")
    confirm_folio: str = Field(max_length=30)
    reason: Optional[str] = Field(default=None, max_length=150)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def registration_summary(r) -> dict:
    return {
        "folio": r.folio,
        "created_at": iso(r.created_at),
        "full_name": r.full_name,
        "phone": r.phone,
        "email": r.email,
        "attendees": r.attendees,
        "arrival_window": r.arrival_window,
        "status": r.status,
        "marketing_allowed": r.marketing_allowed,
        "anonymized": bool(r.anonymized_at),
    }


def registration_detail(r) -> dict:
    d = registration_summary(r)
    d.update(
        {
            "updated_at": iso(r.updated_at),
            "privacy_version": r.privacy_version,
            "privacy_accepted_at": iso(r.privacy_accepted_at),
            "marketing_opt_in": r.marketing_opt_in,
            "marketing_consent_at": iso(r.marketing_consent_at),
            "marketing_text_version": r.marketing_text_version,
            "marketing_revoked_at": iso(r.marketing_revoked_at),
            "campaign_source": r.campaign_source,
            "anonymized_at": iso(r.anonymized_at),
        }
    )
    return d
