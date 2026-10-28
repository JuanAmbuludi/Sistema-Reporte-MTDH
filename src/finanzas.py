"""Reconciled budget sources. Fiscal, social and government are separate universes."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FISCAL_MEASURES = ["codificado", "certificado", "comprometido", "devengado", "saldo_disponible"]
GOVERNMENT_MEASURES = ["anterior", "fiscal", "acumulado"]


def load_fiscal(path: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Read the captured SGDE publication without fabricating territorial detail."""
    path = path or ROOT / "data/processed/presupuesto_fiscal_2026-09.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    dimensions = data["dimensiones"]
    if data["medidas"] != FISCAL_MEASURES:
        raise ValueError("Medidas fiscales no reconocidas.")
    rows = []
    catalogs = {key: {item["id"]: item for item in items} for key, items in data["catalogos"].items()}
    for record in data["registros"]:
        if len(record) != len(dimensions) + len(FISCAL_MEASURES):
            raise ValueError("Registro fiscal incompleto.")
        row = {}
        for index, dimension in enumerate(dimensions):
            item = catalogs[dimension][record[index]]
            row[dimension] = item["nombre"]
            row[dimension + "_codigo"] = str(item.get("codigo", item["id"]))
        for key, value in zip(FISCAL_MEASURES, record[len(dimensions):]):
            amount = Decimal(str(value))
            if not amount.is_finite() or amount < 0:
                raise ValueError(f"Monto fiscal inválido: {key}.")
            row[key] = float(amount)
        row["periodo_id"] = data["fecha_corte"][:7]
        rows.append(row)
    frame = pd.DataFrame(rows)
    keys = [d + "_codigo" for d in dimensions]
    if frame.duplicated(keys).any():
        raise ValueError("Claves fiscales duplicadas.")
    return frame, {k: v for k, v in data.items() if k != "registros"}


def load_government() -> pd.DataFrame:
    """296 provincial source rows, including the historical pensions with no current users."""
    from src.etl import _read_snapshot, parse_period
    from src.table_source import load_workbook

    source = ROOT / "data/source/Acumulado_VIS_VIE"
    manifest = json.loads((ROOT / "data/processed/manifest.json").read_text(encoding="utf-8"))
    period = manifest["periodo"][:7]
    year = int(period[:4])
    workbook = load_workbook(source, data_only=True, read_only=True)
    try:
        records = _read_snapshot(workbook["provincial"], year, parse_period(period), "current")
    finally:
        workbook.close()
    frame = pd.DataFrame(records).rename(columns={"monto_anterior": "anterior", "monto_fiscal": "fiscal",
                                                  "monto_gobierno": "acumulado"})
    for column in GOVERNMENT_MEASURES:
        frame[column] = frame[column].astype(float)
    frame["periodo_id"] = period
    frame["ambito"] = frame.seccion.map({"bonos_pensiones": "Transferencias monetarias no contributivas",
                                        "proteccion_integral": "Servicios de protección social"})
    # This financial view never substitutes the workbook's older coverage for the validated monthly series.
    return frame.drop(columns=["usuarios", "unidades", "unidades_origen", "presupuesto_ejecutado"])


def by(frame: pd.DataFrame, dimension: str, government: bool = False) -> pd.DataFrame:
    measures = GOVERNMENT_MEASURES if government else FISCAL_MEASURES
    rows = frame.groupby(dimension, as_index=False, dropna=False)[measures].sum(min_count=1)
    if not government:
        rows["ejecucion"] = rows.devengado / rows.codificado.where(rows.codificado.gt(0)) * 100
        rows["saldo_por_devengar"] = rows.codificado - rows.devengado
    return rows.sort_values("acumulado" if government else "codificado", ascending=False).reset_index(drop=True)
