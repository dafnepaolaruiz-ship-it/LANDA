"""Aplicación FastAPI de EXPO LANDA."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import get_settings
from database import Base, engine
from routes import admin, public
from security import security_headers

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("landa")

app = FastAPI(
    title="EXPO LANDA – API",
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

if settings.auto_create_tables and not settings.is_production:
    import models  # noqa: F401

    Base.metadata.create_all(engine)

if not settings.event_details_confirmed:
    log.warning("EVENT_DETAILS_CONFIRMED=false: fecha, horario y datos del evento aún NO confirmados.")
if not settings.legal_configured:
    log.warning("Datos legales del Aviso de Privacidad sin configurar (PRIVACY_*). No publicar así.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    max_age=600,
)


@app.middleware("http")
async def hardening(request: Request, call_next):
    # Límite de tamaño de solicitud
    if request.method in ("POST", "PUT", "PATCH"):
        cl = request.headers.get("content-length")
        if cl is None:
            return JSONResponse({"detail": "Falta Content-Length."}, status_code=411)
        if not cl.isdigit() or int(cl) > settings.max_body_bytes:
            return JSONResponse({"detail": "Solicitud demasiado grande."}, status_code=413)
    try:
        response = await call_next(request)
    except Exception:  # sin trazas ni datos al cliente; el log no incluye cuerpo de la solicitud
        log.exception("Error no controlado en %s %s", request.method, request.url.path)
        response = JSONResponse({"detail": "Ocurrió un error interno. Inténtalo de nuevo."}, status_code=500)
    for k, v in security_headers(request.url.path).items():
        response.headers.setdefault(k, v)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Mensajes en español por campo, SIN reenviar los valores recibidos (pueden ser datos personales)."""
    errors = {}
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", []) if p != "body"]
        field = loc[-1] if loc else "_"
        if err.get("type") == "value_error":
            msg = str(err.get("msg", "")).replace("Value error, ", "")
        elif err.get("type") == "missing":
            msg = "Este campo es obligatorio."
        elif err.get("type") in ("string_too_long", "too_long"):
            msg = "El valor es demasiado largo."
        else:
            msg = "Dato no válido."
        errors.setdefault(field, msg)
    return JSONResponse({"detail": "Revisa los datos del formulario.", "errors": errors}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


app.include_router(public.router)
app.include_router(admin.router)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if settings.serve_frontend and FRONTEND.exists():

    @app.get("/admin", include_in_schema=False)
    def admin_page():
        return RedirectResponse("/admin.html")

    @app.get("/aviso-privacidad", include_in_schema=False)
    def privacy_page():
        return RedirectResponse("/aviso-privacidad.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
