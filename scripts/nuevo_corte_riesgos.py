"""Abre la publicación de un nuevo día de Riesgos y cierra la anterior.

Uso:  python scripts/nuevo_corte_riesgos.py AAAA-MM-DD

Copia la última publicación de cada fuente (``seguimiento_enos_*.json`` y ``continuidad_servicios_*.json``) a los archivos
del nuevo día y registra en ``data/processed/cortes_riesgos.json`` la huella SHA-256 de los archivos del día que se cierra.
Los datos nuevos (alertas, kits, bono, continuidad y sus notas en ``notas``) se cargan después en los archivos del nuevo
día; el día cerrado no vuelve a editarse, de modo que su reporte se reproduce en el dashboard y en los exportables con un
periodo que termine ese día.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import enos  # noqa: E402

SOURCES = [(enos.SNAPSHOT, "seguimiento_enos"), (enos.CONTINUITY, "continuidad_servicios")]
DESCRIPTION = ("Días de Riesgos ya cerrados: cada archivo publicado con la huella SHA-256 que tenía al abrirse el día siguiente. "
               "Un día cerrado no se edita; los datos nuevos se publican en un día nuevo (scripts/nuevo_corte_riesgos.py).")


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def open_day(day: str) -> dict[str, Path]:
    """The files of the new day, copied from the latest publication of each source, after closing that publication."""
    datetime.strptime(day, "%Y-%m-%d")
    ledger = enos.ledger()
    closed = ledger.setdefault("cerrados", {})
    created = {}
    for pattern, prefix in SOURCES:
        found = enos.publications(pattern)
        if not found:
            raise SystemExit(f"No hay publicaciones de {prefix} para copiar.")
        last_day, last_path = found[-1]
        if day <= f"{last_day:%Y-%m-%d}":
            raise SystemExit(f"El {day} debe ser posterior a la última publicación de {prefix} ({last_day:%d/%m/%Y}).")
        data = json.loads(last_path.read_text(encoding="utf-8"))
        if prefix == "seguimiento_enos":
            # The report of the new day ends on that day; each source keeps its own cut until its data are updated.
            data["corte"] = day
            data["generado_utc"] = datetime.now(timezone.utc).isoformat()
            # An approved PDF belongs to the issued day; it cannot represent a new publication.
            data.pop("pdf_publicado", None)
        closed.setdefault(f"{last_day:%Y-%m-%d}", {})[last_path.name] = enos.fingerprint(last_path)
        target = enos.FOLDER / f"{prefix}_{day}.json"
        _write(target, data)
        created[prefix] = target
    _write(enos.LEDGER, {"descripcion": DESCRIPTION, "cerrados": dict(sorted(closed.items()))})
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dia", help="Día del nuevo reporte, AAAA-MM-DD")
    created = open_day(parser.parse_args().dia)
    for path in created.values():
        print(f"Creado: {path.relative_to(ROOT)}")
    print("Cargue los datos nuevos en esos archivos (alertas, kits, bono, continuidad y notas). Si el bono cambia, actualice "
          "también bonos_periodos_confirmados. El día anterior quedó cerrado en data/processed/cortes_riesgos.json.")


if __name__ == "__main__":
    main()
