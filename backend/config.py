"""Configuración de la aplicación. Todo valor sensible viene de variables de entorno."""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Versiones de los textos legales mostrados. Cambiarlas cada vez que se edite el texto.
PRIVACY_NOTICE_VERSION = "2026-10-borrador-1"
MARKETING_TEXT_VERSION = "2026-10-publicidad-1"
PRIVACY_PLACEHOLDER = "[POR CONFIGURAR ANTES DE PUBLICAR]"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True)

    # --- Entorno ---
    environment: str = "development"  # development | production
    database_url: str = "sqlite:///./landa_dev.db"
    auto_create_tables: bool = False  # solo para desarrollo local; en producción usar migraciones
    serve_frontend: bool = True  # sirve ../frontend desde FastAPI (útil en local o despliegue único)

    # --- Seguridad web ---
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    cookie_secure: Optional[bool] = None  # None => True en producción, False en desarrollo
    form_signing_secret: str = ""
    trusted_proxy_count: int = 0  # nº de proxies de confianza delante de la app (X-Forwarded-For)
    max_body_bytes: int = 16384

    # --- Sesiones y login administrativo ---
    admin_initial_username: str = ""
    admin_initial_password: str = ""
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    # --- Registro público ---
    max_attendees: int = 10  # límite configurable; NO es el aforo oficial
    min_form_seconds: float = 2.0
    form_token_max_hours: int = 6
    register_rate_limit: int = 20  # solicitudes por ventana y por IP (redes móviles comparten IP)
    register_rate_window_seconds: int = 600
    duplicate_window_seconds: int = 180

    # --- Antispam opcional (Cloudflare Turnstile). Vacío = desactivado ---
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    # --- Evento ---
    event_details_confirmed: bool = True  # Confirmado con fecha, horario y ubicación definitiva de Landa

    # --- Datos legales oficiales de Landa Entorno Residencial ---
    privacy_controller_name: str = "Landa Entorno Residencial / Grupo Soldi"
    privacy_controller_address: str = "Blvd. El Chichimeco s/n, Circuito Golondrinas, a un minuto del Parque Industrial Chichimeco, C.P. 20916, Jesús María, Aguascalientes"
    privacy_contact_email: str = "contacto@gruposoldi.com.mx"
    privacy_contact_phone: str = "449 348 1867"
    privacy_retention_text: str = "Tus datos se conservarán durante 12 meses para fines de seguimiento del evento, asesoría de vivienda y crédito, al término de los cuales se anonimizarán o cancelarán de forma segura."
    privacy_providers_text: str = "Servicios de infraestructura de cómputo en la nube con cifrado y almacenamiento protegido para la custodia de los registros."
    privacy_transfers_text: str = "No se realizan transferencias comerciales de datos personales a terceros ajenos a la organización sin tu consentimiento expreso."
    retention_months: int = 12

    # --- Integración y Sincronización SharePoint / OneDrive ---
    sharepoint_folder_url: str = "https://eduuaa-my.sharepoint.com/:f:/g/personal/al280268_edu_uaa_mx/IgABkutONQVvSZDJs2Uon_mAAZxqhwvRrnXXFKtXIDnhoCo?e=p6qRYl"
    sharepoint_sync_dir: str = "./sharepoint_sync"
    sharepoint_webhook_url: str = ""

    @property
    def origins(self) -> List[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def session_cookie_name(self) -> str:
        return "__Host-landa_session" if self.secure_cookies else "landa_session"

    @property
    def signing_secret(self) -> str:
        return self.form_signing_secret

    @property
    def legal_configured(self) -> bool:
        return all(
            [
                self.privacy_controller_name,
                self.privacy_controller_address,
                self.privacy_contact_email,
                self.privacy_retention_text,
            ]
        )


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    if not s.form_signing_secret:
        if s.is_production:
            raise RuntimeError("FORM_SIGNING_SECRET es obligatorio en producción (mínimo 32 caracteres).")
        s.form_signing_secret = secrets.token_urlsafe(32)  # solo desarrollo; cambia en cada arranque
    if s.is_production:
        if len(s.form_signing_secret) < 32:
            raise RuntimeError("FORM_SIGNING_SECRET debe tener al menos 32 caracteres.")
        if not s.secure_cookies:
            raise RuntimeError("COOKIE_SECURE no puede ser false en producción.")
    return s
