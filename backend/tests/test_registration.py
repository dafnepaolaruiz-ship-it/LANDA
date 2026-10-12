"""Pruebas del formulario público y la persistencia (puntos 1-14 de la lista de verificación)."""
import io
import uuid

import pytest
from sqlalchemy import select

import models
from config import MARKETING_TEXT_VERSION, PRIVACY_NOTICE_VERSION
from database import SessionLocal, make_engine
from schemas import normalize_mx_phone
from security import issue_form_token
from tests.conftest import make_payload, register


# ---- 1, 10: registro válido con folio
def test_valid_registration_returns_folio(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["folio"].startswith("LANDA-") and len(body["folio"]) == 15
    assert body["attendees"] == 3 and body["duplicate"] is False
    # La respuesta no devuelve datos personales
    assert "maria" not in r.text.lower() and "449" not in r.text


def test_folio_is_random_not_sequential(client):
    folios = {register(client, full_name="Persona %d Prueba" % i, phone="449 000 %04d" % (1000 + i)).json()["folio"] for i in range(5)}
    assert len(folios) == 5


# ---- 2-6
@pytest.mark.parametrize(
    "field,value,key",
    [
        ("full_name", "", "full_name"),
        ("full_name", "   ", "full_name"),
        ("full_name", "1234", "full_name"),
        ("phone", "98765", "phone"),
        ("phone", "abcdefghij", "phone"),
        ("phone", "0123456789", "phone"),
        ("email", "no-es-correo", "email"),
        ("email", "a@", "email"),
        ("attendees", 0, "attendees"),
        ("attendees", -2, "attendees"),
        ("attendees", 999, "attendees"),
        ("attendees", 2.5, "attendees"),
        ("attendees", "3", "attendees"),
        ("privacy_accepted", False, "privacy_accepted"),
    ],
)
def test_invalid_fields_rejected_by_backend(client, field, value, key):
    r = register(client, **{field: value})
    assert r.status_code == 422
    assert key in r.json()["errors"]
    # los mensajes de error no reenvían el valor recibido
    assert str(value) not in r.text or str(value) in ("", "0", "-2", "3", "False")


def test_missing_consent_field_rejected(client):
    p = make_payload()
    del p["privacy_accepted"]
    r = client.post("/api/registrations", json=p)
    assert r.status_code == 422


def test_unknown_fields_rejected(client):
    r = register(client, status="confirmed")
    assert r.status_code == 422


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("449 123 4567", "4491234567"),
        ("(449) 123-4567", "4491234567"),
        ("+52 449 123 4567", "4491234567"),
        ("+52 1 449 123 4567", "4491234567"),
        ("52 449 123 4567", "4491234567"),
        ("044 449 123 4567", "4491234567"),
        ("449.123.4567", "4491234567"),
        ("+1 449 123 4567", None),
        ("12345", None),
    ],
)
def test_phone_formats(raw, expected):
    assert normalize_mx_phone(raw) == expected


def test_valid_unusual_emails_accepted(client):
    for i, e in enumerate(["nombre+expo@sub.dominio.com.mx", "a.b-c_d@correo.mx", "ÑANDÚ@ejemplo.com"]):
        r = register(client, email=e, full_name="Persona %d Prueba" % i, phone="449 111 %04d" % (2000 + i))
        assert r.status_code == 201, (e, r.text)


# ---- 7: consentimiento publicitario opcional e independiente
def test_marketing_optional_and_recorded(client):
    r = register(client)  # sin publicidad
    with SessionLocal() as db:
        reg = db.execute(select(models.Registration)).scalar_one()
        assert reg.marketing_opt_in is False and reg.marketing_consent_at is None and reg.marketing_allowed is False
        assert reg.privacy_accepted_at is not None and reg.privacy_version == PRIVACY_NOTICE_VERSION
    r2 = register(client, marketing_opt_in=True, marketing_text_version=MARKETING_TEXT_VERSION, full_name="Otra Persona Prueba", phone="449 222 3344")
    assert r2.status_code == 201
    with SessionLocal() as db:
        reg = db.execute(select(models.Registration).where(models.Registration.folio == r2.json()["folio"])).scalar_one()
        assert reg.marketing_opt_in and reg.marketing_consent_at and reg.marketing_text_version == MARKETING_TEXT_VERSION


def test_marketing_with_wrong_text_version_rejected(client):
    r = register(client, marketing_opt_in=True, marketing_text_version="otra")
    assert r.status_code == 409


def test_old_privacy_version_rejected(client):
    assert register(client, privacy_version="vieja").status_code == 409


# ---- 8, 14: doble envío / reintento
def test_retry_same_idempotency_key_returns_same_folio(client):
    p = make_payload()
    r1 = client.post("/api/registrations", json=p)
    r2 = client.post("/api/registrations", json=dict(p, form_token=issue_form_token()))
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["folio"] == r2.json()["folio"] and r2.json()["duplicate"] is True
    with SessionLocal() as db:
        assert len(db.execute(select(models.Registration)).scalars().all()) == 1


def test_accidental_double_submit_with_new_key_is_merged(client):
    r1 = register(client)
    r2 = register(client)  # misma persona, otra llave, segundos después
    assert r1.json()["folio"] == r2.json()["folio"]


def test_shared_phone_or_email_not_blocked(client):
    r1 = register(client)
    r2 = register(client, full_name="Roberto Gómez Díaz")  # mismo teléfono y correo, otra persona
    r3 = register(client, attendees=5)  # misma persona, otra cantidad
    assert len({r1.json()["folio"], r2.json()["folio"], r3.json()["folio"]}) == 3


# ---- Antispam
def test_honeypot_does_not_store(client):
    r = register(client, website="http://spam.example")
    assert r.status_code == 201
    with SessionLocal() as db:
        assert db.execute(select(models.Registration)).first() is None


def test_bad_form_token_rejected(client):
    assert register(client, form_token="falso.token.firma").status_code == 400


def test_too_fast_submission_rejected(client, monkeypatch):
    import security

    monkeypatch.setattr(security.settings, "min_form_seconds", 60)
    assert register(client).status_code == 429


def test_registration_rate_limit(client, monkeypatch):
    import routes.public as pub

    monkeypatch.setattr(pub.settings, "register_rate_limit", 3)
    codes = [register(client, full_name="Persona %d Prueba" % i, phone="449 333 %04d" % (3000 + i)).status_code for i in range(5)]
    assert codes[:3] == [201, 201, 201] and 429 in codes[3:]


# ---- 9: error temporal del servidor → mensaje claro, sin confirmar
def test_server_error_during_save_is_not_confirmed(client, monkeypatch):
    import routes.public as pub

    def boom(*a, **k):
        raise RuntimeError("db caída: datos privados maria@example.com")

    monkeypatch.setattr(pub.svc, "create_registration", boom)
    r = register(client)
    assert r.status_code == 503
    assert "maria" not in r.text and "RuntimeError" not in r.text and "Traceback" not in r.text
    assert "folio" not in r.json()


# ---- 11, 12, 13: persistencia
def test_registration_survives_backend_restart(client):
    r = register(client, attendees=7)
    folio = r.json()["folio"]
    from config import get_settings

    # "Reinicio": nuevo motor y nueva sesión contra el mismo archivo de base de datos
    new_engine = make_engine(get_settings().database_url)
    from sqlalchemy.orm import Session

    with Session(new_engine) as db:
        reg = db.execute(select(models.Registration).where(models.Registration.folio == folio)).scalar_one()
        assert reg.attendees == 7 and reg.email == "maria@example.com"
    new_engine.dispose()


def test_attendee_total_is_server_side_and_device_independent(client):
    from tests.conftest import admin_client

    register(client, attendees=3)
    register(client, attendees=2, full_name="Segundo Registro Prueba", phone="449 555 0000")
    ac = admin_client(client)
    s = ac.get("/api/admin/stats").json()
    assert s["total_registrations"] == 2 and s["total_attendees"] == 5


# ---- Evidencia mínima: no se guardan IP ni user-agent
def test_no_ip_or_user_agent_columns():
    cols = {c.name for c in models.Registration.__table__.columns}
    assert not ({"ip", "ip_address", "user_agent"} & cols)


# ---- Público: baja de publicidad
def test_public_marketing_revocation(client):
    r = register(client, marketing_opt_in=True, marketing_text_version=MARKETING_TEXT_VERSION)
    folio = r.json()["folio"]
    bad = client.post("/api/marketing-revocation", json={"folio": folio, "email": "otro@example.com"})
    good = client.post("/api/marketing-revocation", json={"folio": folio, "email": "MARIA@example.com"})
    assert bad.json() == good.json()  # no revela si hubo coincidencia
    with SessionLocal() as db:
        reg = db.execute(select(models.Registration)).scalar_one()
        assert reg.marketing_revoked_at is not None and reg.marketing_allowed is False
