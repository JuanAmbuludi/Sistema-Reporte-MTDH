#!/usr/bin/env python3
"""Convert the official aggregated workbook to validated Parquet files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.etl import build_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", type=Path, help="Excel fuente, por ejemplo 'Acumulado VIS-VIE.xlsx'.")
    parser.add_argument("--period", "--periodo", required=True, help="Corte AAAA-MM; el Excel no documenta el mes.")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "processed")
    parser.add_argument("--period-source", default="Corte indicado por el operador; no consta en el Excel.", help="Documento o evidencia que respalda el mes del corte.")
    parser.add_argument("--sheet", default="provincial", help="Nombre de la hoja vigente.")
    parser.add_argument("--ejecucion", type=Path, help="CSV complementario de presupuesto ejecutado verificado.")
    args = parser.parse_args()
    try:
        result = build_dataset(args.excel, args.output, args.period, period_source=args.period_source,
                               execution_csv=args.ejecucion, current_sheet=args.sheet)
    except (ValueError, FileNotFoundError, PermissionError) as error:
        print(f"No se importó la base: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"resultado": "Importación completa", "corte": result["periodo_label"],
                      "filas": result["filas"], "salida": str(args.output.resolve()),
                      "beneficiarios_reportados": result["totales"]["beneficiarios"],
                      "usuarios_servicios": result["totales"]["usuarios_servicios"],
                      "unidades": result["totales"]["unidades"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
