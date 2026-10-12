"""Exportación a XLSX con neutralización de fórmulas."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from schemas import FiltersIn
from security import neutralize_formula
from services.registrations import MX_TZ

STATUS_ES = {"pending": "Pendiente", "confirmed": "Confirmado", "cancelled": "Cancelado"}
WINDOW_ES = {
    "10-12": "10:00 a. m. – 12:00 p. m.",
    "12-15": "12:00 p. m. – 3:00 p. m.",
    "15-17": "3:00 p. m. – 5:00 p. m.",
    "17-19": "5:00 p. m. – 7:00 p. m.",
    "unknown": "Aún no lo sé",
}
HEADERS = [
    "Folio",
    "Fecha de registro",
    "Nombre completo",
    "Teléfono",
    "Correo electrónico",
    "Total de asistentes",
    "Horario aproximado",
    "Estado del registro",
    "Consentimiento finalidades primarias",
    "Versión del aviso de privacidad",
    "Preferencia de publicidad",
    "Fecha del consentimiento publicitario",
    "Revocación de publicidad",
    "Fuente de campaña",
]


def _local(dt) -> str:
    if not dt:
        return ""
    return dt.replace(tzinfo=timezone.utc).astimezone(MX_TZ).strftime("%Y-%m-%d %H:%M")


def _text(ws, row: int, col: int, value) -> None:
    """Escribe SIEMPRE como texto (nunca fórmula)."""
    cell = ws.cell(row=row, column=col)
    cell.value = neutralize_formula("" if value is None else str(value))
    cell.data_type = "s"


def build_workbook(rows: Iterable, filters: FiltersIn, exporter: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Registros"
    ws.append([])  # reservar fila 1 para encabezados (se escriben con _text)
    for c, h in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=c)
        cell.value = h
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="3B3028")
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    total_regs = total_att = 0
    r = 2
    for reg in rows:
        total_regs += 1
        if reg.status != "cancelled":
            total_att += reg.attendees
        values = [
            reg.folio,
            _local(reg.created_at),
            reg.full_name or "(anonimizado)",
            reg.phone or "",
            reg.email or "",
            None,  # numérico
            WINDOW_ES.get(reg.arrival_window or "", ""),
            STATUS_ES.get(reg.status, reg.status),
            ("Sí – " + _local(reg.privacy_accepted_at)) if reg.privacy_accepted_at else "",
            reg.privacy_version,
            "Sí" if reg.marketing_allowed else "No",
            _local(reg.marketing_consent_at),
            _local(reg.marketing_revoked_at),
            reg.campaign_source or "",
        ]
        for c, v in enumerate(values, start=1):
            if c == 6:
                ws.cell(row=r, column=c).value = int(reg.attendees)
            else:
                _text(ws, r, c, v)
        r += 1

    widths = [18, 18, 30, 15, 32, 12, 26, 14, 30, 22, 14, 22, 20, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(HEADERS)), max(r - 1, 1))

    s = wb.create_sheet("Resumen")
    info = [
        ("Exportado (hora de México)", datetime.now(timezone.utc).astimezone(MX_TZ).strftime("%Y-%m-%d %H:%M")),
        ("Exportado por", exporter),
        ("Registros incluidos", total_regs),
        ("Asistentes (pendientes + confirmados; excluye cancelados)", total_att),
        ("Filtro de estado", STATUS_ES.get(filters.status or "", "Todos")),
        ("Filtro de búsqueda de texto", "Aplicado" if filters.q else "Ninguno"),
        ("Fecha desde", str(filters.date_from or "")),
        ("Fecha hasta", str(filters.date_to or "")),
        ("Aviso", "Contiene datos personales. Manéjalo según el procedimiento de seguridad y elimínalo cuando ya no sea necesario."),
    ]
    for i, (k, v) in enumerate(info, start=1):
        _text(s, i, 1, k)
        s.cell(row=i, column=1).font = Font(bold=True)
        if isinstance(v, int):
            s.cell(row=i, column=2).value = v
        else:
            _text(s, i, 2, v)
    s.column_dimensions["A"].width = 55
    s.column_dimensions["B"].width = 60

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
