#!/usr/bin/env python3
"""Configura automáticamente la cuenta admin de InfoReportes MTDH."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.security import hash_password

USERNAME = "admin"
PASSWORD = "admin12345678"
NAME = "Administrador"


def main():
    parser = argparse.ArgumentParser(description="Configura la cuenta admin.")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / ".streamlit" / "secrets.toml"
    )
    args = parser.parse_args()

    existing = (
        args.output.read_text(encoding="utf-8")
        if args.output.exists() else ""
    )
    config = tomllib.loads(existing)
    encoded = hash_password(PASSWORD)

    if "auth" not in config:
        existing = existing.rstrip() + (
            "\n\n[auth]\nidle_minutes = 30\nmax_hours = 8\n"
        )

    block = (
        f'[auth.users."{USERNAME}"]\n'
        f'name = {json.dumps(NAME)}\n'
        f'password_hash = {json.dumps(encoded)}\n'
        'role = "admin"\n'
        'enabled = true\n'
    )

    # Actualiza solo admin y conserva las demás cuentas y configuraciones.
    if USERNAME in config.get("auth", {}).get("users", {}):
        pattern = (
            r"""(?ms)^[ \t]*\[auth\.users\.(?:"admin"|'admin'|admin)\]"""
            r"[^\S\n]*(?:#[^\n]*)?\r?\n.*?(?=^[ \t]*\[|\Z)"
        )
        result, replacements = re.subn(
            pattern, lambda _: block + "\n", existing, count=1
        )
        if replacements != 1:
            raise SystemExit(
                "La cuenta admin usa una estructura TOML diferente. "
                "Genera un archivo nuevo con --output secrets_admin.toml "
                "y copia su bloque admin en tu configuración."
            )
    else:
        result = existing.rstrip() + "\n\n" + block

    # Comprueba el archivo completo antes de reemplazarlo.
    tomllib.loads(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            dir=args.output.parent, delete=False
        ) as target:
            temporary = Path(target.name)
            target.write(result)
        os.replace(temporary, args.output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    print("Cuenta configurada correctamente.")
    print(f"Usuario: {USERNAME}")
    print(f"Contraseña: {PASSWORD}")
    print(f"Archivo generado: {args.output.resolve()}")
    print(
        "Streamlit Cloud: copia el contenido del archivo generado "
        "en Settings → Secrets."
    )


if __name__ == "__main__":
    main()

