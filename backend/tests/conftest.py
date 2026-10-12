import os
import tempfile
import uuid

_TMP = tempfile.mkdtemp(prefix="landa_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db").replace("\\", "/")
os.environ["ENVIRONMENT"] = "development"
os.environ["FORM_SIGNING_SECRET"] = "x" * 48
os.environ["SERVE_FRONTEND"] = "false"
os.environ["MIN_FORM_SECONDS"] = "0"
os.environ["COOKIE_SECURE"] = "false"
os.environ["REGISTER_RATE_LIMIT"] = "1000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import models  # noqa: E402
from config import MARKETING_TEXT_VERSION, PRIVACY_NOTICE_VERSION, get_settings  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from security import issue_form_token, limiter  # noqa: E402

settings = get_settings()
PASSWORD = "Contraseña-Segura-123"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    yield


@pytest.fixture()
def client():
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def make_payload(**over):
    p = {
        "full_name": "María Fernanda López",
        "phone": "449 123 4567",
        "email": "maria@example.com",
        "attendees": 3,
        "arrival_window": "12-15",
        "privacy_accepted": True,
        "privacy_version": PRIVACY_NOTICE_VERSION,
        "marketing_opt_in": False,
        "form_token": issue_form_token(),
        "idempotency_key": str(uuid.uuid4()),
        "website": "",
    }
    p.update(over)
    return p


def create_user(username="organizadora", role="admin", password=PASSWORD):
    with SessionLocal() as db:
        db.add(models.AdminUser(username=username, password_hash=auth.hash_password(password), role=role))
        db.commit()


def login(client, username="organizadora", password=PASSWORD):
    r = client.post("/api/admin/login", json={"username": username, "password": password})
    return r


def admin_client(client, role="admin", username="organizadora"):
    create_user(username, role)
    r = login(client, username)
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return client


def register(client, **over):
    return client.post("/api/registrations", json=make_payload(**over))
