"""Importa una matriz de amenazas sin reemplazar otros cortes del inventario.

python scripts/build_risks.py --input UA_SEP26_AMENAZAS.xlsx --period 2026-09
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.riesgos import DATA_PATH, DETAIL_FIELDS, THREATS, aggregate_inventory, exposed, normalize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--period", required=True, help="AAAA-MM")
    parser.add_argument("--sheet", help="Hoja de unidades; se detecta si se omite")
    parser.add_argument("--output", type=Path, default=DATA_PATH)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.period):
        parser.error("--period debe tener formato AAAA-MM")
    workbook = pd.ExcelFile(args.input)
    source = None
    for sheet in ([args.sheet] if args.sheet else workbook.sheet_names):
        top = pd.read_excel(workbook, sheet, header=None, nrows=40)
        headers = [i for i, row in top.iterrows() if "co_siimdh" in row.astype(str).str.strip().tolist()]
        if headers:
            source = pd.read_excel(workbook, sheet, header=headers[0], dtype=str).dropna(how="all")
            break
    if source is None:
        raise ValueError("No se encontró una hoja con el campo co_siimdh")
    month_names = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    expected = f"{month_names[int(args.period[5:]) - 1]} {args.period[:4]}"
    if "corte" not in source or set(source.corte.str.strip().str.casefold().dropna()) != {expected}:
        raise ValueError("El corte de la matriz no coincide con --period")
    clean = normalize(source, args.period)
    public = aggregate_inventory(clean)
    combined = public
    if args.output.exists():
        old = pd.read_parquet(args.output)
        if "codigo_ua" in old.columns:
            old = aggregate_inventory(old)
        combined = pd.concat([old.loc[old.periodo_id.ne(args.period)], public], ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(args.output, index=False, compression="zstd")
    # The requested unit detail contains codes/names and province-level geography only.
    detail_path = args.output.with_name(f"{args.output.stem}_detalle.parquet")
    detail = clean[DETAIL_FIELDS].copy()
    if detail_path.exists():
        previous = pd.read_parquet(detail_path)
        detail = pd.concat([previous.loc[previous.periodo_id.ne(args.period), DETAIL_FIELDS], detail], ignore_index=True)
    detail.to_parquet(detail_path, index=False, compression="zstd")
    metadata = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "periodo_id": args.period, "archivo_fuente": args.input.name, "hoja": sheet,
        "sha256_fuente": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "registros_fuente": len(source), "unidades_unicas": len(clean),
        "repeticiones_consolidadas": len(source) - len(clean),
        "unidades_expuestas_alguna_amenaza": len(exposed(clean)),
        "inundaciones_o_movimientos_masa": int(clean[list(THREATS)[:2]].isin(["Media", "Alta", "Muy alta"]).any(axis=1).sum()),
        "fuente": "SIIMTDH; elaboración DGID / SGDE / MTDH",
        "capas": {"inundaciones": "MAGAP 2015", "movimientos_masa": "SNGR 2011", "sequia": "MAGAP 2015", "incendios_forestales": "SNGR 2015"},
        "criterio": "Una UA por corte y código. Media, alta o muy alta en al menos una amenaza. No representa afectación confirmada. Guiones y vacíos no acreditan ausencia de riesgo.",
    }
    audit = args.output.with_name(f"riesgos_ua_{args.period}.json")
    audit.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
