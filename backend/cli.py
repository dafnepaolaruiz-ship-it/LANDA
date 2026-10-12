"""CLI administrativa. Uso:  python cli.py <comando>

  create-admin USERNAME [--role admin|viewer]   Crea una cuenta (pide la contraseña por teclado, sin eco)
  reset-password USERNAME                       Restablece la contraseña y cierra todas sus sesiones
  deactivate USERNAME                           Desactiva la cuenta y cierra sus sesiones
  list-admins                                   Lista cuentas (sin hashes)
  anonymize-expired --months N [--dry-run]      Anonimiza registros más antiguos que N meses
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import timedelta

from sqlalchemy import delete, select

import auth
from database import SessionLocal
from models import AdminSession, AdminUser, Registration, utcnow
from services import registrations as svc


def _ask_password() -> str:
    while True:
        p1 = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
        problem = auth.password_problem(p1)
        if problem:
            print(problem)
            continue
        if p1 != getpass.getpass("Repite la contraseña: "):
            print("No coinciden.")
            continue
        return p1


def cmd_create(a) -> int:
    username = a.username.strip().lower()
    with SessionLocal() as db:
        if db.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none():
            print("Ya existe ese usuario.")
            return 1
        db.add(AdminUser(username=username, password_hash=auth.hash_password(_ask_password()), role=a.role, password_changed_at=utcnow()))
        svc.audit(db, "cli", "admin_created", None, "usuario=%s rol=%s" % (username, a.role))
        db.commit()
    print("Cuenta creada: %s (%s)" % (username, a.role))
    return 0


def cmd_reset(a) -> int:
    with SessionLocal() as db:
        u = db.execute(select(AdminUser).where(AdminUser.username == a.username.strip().lower())).scalar_one_or_none()
        if not u:
            print("No existe ese usuario.")
            return 1
        u.password_hash = auth.hash_password(_ask_password())
        u.failed_attempts, u.locked_until, u.password_changed_at = 0, None, utcnow()
        db.execute(delete(AdminSession).where(AdminSession.user_id == u.id))
        svc.audit(db, "cli", "password_reset", None, "usuario=%s" % u.username)
        db.commit()
    print("Contraseña restablecida y sesiones cerradas.")
    return 0


def cmd_deactivate(a) -> int:
    with SessionLocal() as db:
        u = db.execute(select(AdminUser).where(AdminUser.username == a.username.strip().lower())).scalar_one_or_none()
        if not u:
            print("No existe ese usuario.")
            return 1
        u.is_active = False
        db.execute(delete(AdminSession).where(AdminSession.user_id == u.id))
        svc.audit(db, "cli", "admin_deactivated", None, "usuario=%s" % u.username)
        db.commit()
    print("Cuenta desactivada.")
    return 0


def cmd_list(a) -> int:
    with SessionLocal() as db:
        for u in db.execute(select(AdminUser).order_by(AdminUser.id)).scalars():
            print("%-20s %-7s activo=%s último acceso=%s" % (u.username, u.role, u.is_active, u.last_login_at))
    return 0


def cmd_anonymize(a) -> int:
    if a.months < 1:
        print("Indica --months con el periodo de conservación definido por la organización (≥ 1).")
        return 1
    cutoff = utcnow() - timedelta(days=int(a.months * 30.4375))
    with SessionLocal() as db:
        rows = db.execute(select(Registration).where(Registration.created_at < cutoff, Registration.anonymized_at.is_(None))).scalars().all()
        print("Registros que se anonimizarían: %d (anteriores a %s UTC)" % (len(rows), cutoff.date()))
        if a.dry_run:
            print("Simulación: no se modificó nada.")
            return 0
        for r in rows:
            svc.anonymize(r)
            svc.audit(db, "cli", "anonymized", r.folio, "Política de conservación: %s meses" % a.months)
        db.commit()
    print("Listo.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Administración de EXPO LANDA")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin")
    c.add_argument("username")
    c.add_argument("--role", choices=["admin", "viewer"], default="admin")
    c.set_defaults(fn=cmd_create)
    for name, fn in (("reset-password", cmd_reset), ("deactivate", cmd_deactivate)):
        s = sub.add_parser(name)
        s.add_argument("username")
        s.set_defaults(fn=fn)
    sub.add_parser("list-admins").set_defaults(fn=cmd_list)
    an = sub.add_parser("anonymize-expired")
    an.add_argument("--months", type=int, required=True)
    an.add_argument("--dry-run", action="store_true")
    an.set_defaults(fn=cmd_anonymize)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
