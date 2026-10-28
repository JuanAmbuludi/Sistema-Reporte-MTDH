"""Import the full emergency-brigade workbook without rewriting daily reports.

Usage: python scripts/update_brigadas.py source.xlsx --corte AAAA-MM-DD
"""
from pathlib import Path
from datetime import date
import argparse
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import brigadas


def update(source, corte, output=brigadas.CANONICAL, *, sheet=None):
    output = Path(output)
    if output.name.startswith(("seguimiento_enos_", "continuidad_servicios_")):
        raise ValueError("La ingesta de brigadas no puede reemplazar publicaciones históricas.")
    data = brigadas.read_workbook(source, corte, sheet=sheet)
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        if previous.get("corte") and date.fromisoformat(data["corte"]) < date.fromisoformat(previous["corte"]):
            raise ValueError("El corte de brigadas es anterior al de la base existente; no se reemplazará el historial.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--corte", required=True, help="Fecha de corte declarada por la fuente (AAAA-MM-DD).")
    parser.add_argument("--output", type=Path, default=brigadas.CANONICAL)
    parser.add_argument("--sheet", help="Hoja que contiene la matriz, si hay varias candidatas.")
    args = parser.parse_args()
    result = update(args.source, args.corte, args.output, sheet=args.sheet)
    print(json.dumps({"output": str(args.output), "corte": result["corte"],
                      "desde": result["desde"], "hasta": result["hasta"],
                      **result["control"]}, ensure_ascii=False, indent=2))
