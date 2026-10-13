"""Servicio de sincronización continua con la carpeta de SharePoint / OneDrive (REGISTRO LANDA).

Mantiene un archivo Excel (.xlsx) y CSV actualizado al instante con cada nuevo registro
para que se sincronice automáticamente con Microsoft SharePoint / OneDrive.
Opcionalmente envía un webhook (Power Automate / Zapier) si se configura.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from models import Registration
from schemas import FiltersIn
from services.export import build_workbook

log = logging.getLogger("landa.sharepoint")


def sync_to_sharepoint_files(db: Session) -> Optional[Path]:
    """Genera y actualiza los archivos Excel y CSV en la carpeta configurada de SharePoint/OneDrive."""
    settings = get_settings()
    sync_dir = Path(settings.sharepoint_sync_dir).resolve()
    sync_dir.mkdir(parents=True, exist_ok=True)

    # 1. Obtener registros ordenados
    stmt = select(Registration).order_by(Registration.created_at.desc())
    registrations = list(db.scalars(stmt))

    # 2. Generar Excel seguro con fórmula-injection protection y estilo corporativo
    xlsx_bytes = build_workbook(registrations, FiltersIn(), "sincronizacion-sharepoint")
    excel_path = sync_dir / "REGISTRO_LANDA.xlsx"
    with open(excel_path, "wb") as f:
        f.write(xlsx_bytes)

    # 3. Generar también CSV para compatibilidad universal
    csv_path = sync_dir / "REGISTRO_LANDA.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Folio",
            "Nombre completo",
            "Teléfono",
            "Correo",
            "Asistentes",
            "Horario aproximado",
            "Estado",
            "Publicidad autorizada",
            "Fecha y hora de registro",
            "Origen (UTM)",
        ])
        for r in registrations:
            # Sanitización de fórmulas en CSV
            def sanitize(val):
                s = str(val or "")
                if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
                    return "'" + s
                return s

            writer.writerow([
                r.folio,
                sanitize(r.full_name),
                sanitize(r.phone),
                sanitize(r.email),
                r.attendees,
                r.arrival_window or "No especificado",
                r.status,
                "Sí" if r.marketing_opt_in else "No",
                r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
                r.campaign_source or "",
            ])

    log.info("Sincronización a SharePoint completada: %d registros en %s", len(registrations), excel_path)
    return excel_path


def notify_sharepoint_webhook(registration: Registration) -> None:
    """Envía el nuevo registro por Webhook a Power Automate / Zapier si está configurado."""
    settings = get_settings()
    if not settings.sharepoint_webhook_url:
        return

    import urllib.request
    import json

    payload = {
        "folio": registration.folio,
        "full_name": registration.full_name,
        "phone": registration.phone,
        "email": registration.email,
        "attendees": registration.attendees,
        "arrival_window": registration.arrival_window,
        "status": registration.status,
        "marketing_opt_in": registration.marketing_opt_in,
        "created_at": registration.created_at.isoformat() if registration.created_at else "",
        "campaign_source": registration.campaign_source or "",
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            settings.sharepoint_webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            log.info("Webhook SharePoint enviado: status %d", res.status)
    except Exception as exc:
        log.warning("No se pudo enviar el webhook de SharePoint: %s", exc)
