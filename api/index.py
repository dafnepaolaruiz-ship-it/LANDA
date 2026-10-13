"""Punto de entrada de FastAPI para Vercel Serverless Functions."""
from __future__ import annotations

import sys
from pathlib import Path

# Inyectar la carpeta backend al path de ejecución de Python
_backend = Path(__file__).resolve().parent.parent / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from main import app  # noqa: E402
