"""Institutional budget of the Ministry: its own universe, never added to the VIS/VIE coverage or budgets.

The base lists the budget by executing unit, program, project, activity, spending group and funding source.  Every
view adds rows first and divides afterwards: execution is accrued over coded budget of the sum, never an average of
row percentages.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import names
from src.data import DEFAULT_DATA_DIR, MONTHS

MONEY = ["presupuesto_codificado", "presupuesto_certificado", "presupuesto_ejecutado"]
# Dimension -> (label, plural label, display column, code column used to order and filter)
DIMENSIONS = {
    "programa": ("Programa presupuestario", "Programas presupuestarios", "programa_nombre", "programa_codigo"),
    "zona": ("Zona", "Zonas", "zona_nombre", "zona_orden"),
    "unidad": ("Unidad ejecutora", "Unidades ejecutoras", "unidad_nombre", "eod_codigo"),
    "grupo": ("Grupo de gasto", "Grupos de gasto", "grupo_nombre", "grupo_gasto_codigo"),
    "fuente": ("Fuente de financiamiento", "Fuentes de financiamiento", "fuente_nombre", "fuente_financiamiento_codigo"),
    "tipo": ("Tipo de gasto", "Tipos de gasto", "tipo_nombre", "tipo_nombre"),
}


def load_budget(data_dir: str | Path | None = None) -> tuple[pd.DataFrame, dict | None]:
    """Rows of the institutional base with readable names, and its manifest; empty when the base is absent."""
    base = Path(data_dir or DEFAULT_DATA_DIR)
    path, manifest_path = base / "presupuesto_institucional.parquet", base / "manifest_financiero.json"
    if not path.exists() or not manifest_path.exists():
        return pd.DataFrame(), None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame = pd.read_parquet(path)
    for column in MONEY:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    frame["periodo_id"] = pd.to_datetime(frame["periodo"]).dt.strftime("%Y-%m")
    for column in ["programa_codigo", "grupo_gasto_codigo", "fuente_financiamiento_codigo", "eod_codigo"]:
        frame[column] = frame[column].astype(str).str.strip()
    frame["programa_nombre"] = [names.budget_program(c, p) for c, p in zip(frame.programa_codigo, frame.programa)]
    frame["programa_corto"] = [names.budget_program(c, p, short=True) for c, p in zip(frame.programa_codigo, frame.programa)]
    frame["zona_nombre"] = frame.zona.map(names.zone)
    frame["zona_codigo"] = frame.zona.map(names.zone_code)
    # Central office first, then the zones in their order.
    frame["zona_orden"] = frame.zona_codigo.fillna("Z0")
    frame["unidad_nombre"] = frame.unidad_ejecutora.map(names.executing_unit)
    frame["grupo_nombre"] = [names.spending_group(c, g) for c, g in zip(frame.grupo_gasto_codigo, frame.grupo_gasto)]
    frame["fuente_nombre"] = [names.funding_source(c, s) for c, s in zip(frame.fuente_financiamiento_codigo, frame.fuente_financiamiento)]
    frame["tipo_nombre"] = frame.tipo_gasto.map(names.spending_type)
    return frame, manifest


def catalog(frame: pd.DataFrame) -> list[dict]:
    """Cuts of the base, newest first, in the shape of :func:`src.data.load_periods`."""
    out = []
    for period_id in sorted(frame.periodo_id.unique(), reverse=True) if not frame.empty else []:
        year, month = map(int, period_id.split("-"))
        out.append({"id": period_id, "year": year, "month": month, "label": f"{MONTHS[month - 1].capitalize()} {year}"})
    return out


def _measures(codified: float, accrued: float, certified: float | None) -> dict:
    return {"codificado": codified, "devengado": accrued, "certificado": certified,
            "ejecucion": accrued / codified * 100 if codified else None, "saldo": codified - accrued}


def summarize(frame: pd.DataFrame) -> dict:
    codified = float(frame.presupuesto_codificado.sum()) if len(frame) else 0.0
    accrued = float(frame.presupuesto_ejecutado.sum()) if len(frame) else 0.0
    certified = float(frame.presupuesto_certificado.sum()) if len(frame) else None
    return {**_measures(codified, accrued, certified), "filas": len(frame),
            "unidades": int(frame.unidad_nombre.nunique()) if len(frame) else 0,
            "programas": int(frame.programa_codigo.nunique()) if len(frame) else 0}


def by(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Budget by one dimension: coded, accrued, certified, execution, balance and share of the coded budget."""
    _label, _plural, name, order = DIMENSIONS[dimension]
    keys = [order, name] if order != name else [name]
    if dimension == "programa":
        keys.append("programa_corto")
    if dimension == "zona":
        keys.append("zona_codigo")
    grouped = frame.groupby(keys, as_index=False, dropna=False)[MONEY].sum(min_count=1)
    grouped["porcentaje_ejecucion"] = grouped.presupuesto_ejecutado / grouped.presupuesto_codificado.where(grouped.presupuesto_codificado > 0) * 100
    grouped["saldo"] = grouped.presupuesto_codificado - grouped.presupuesto_ejecutado
    total = grouped.presupuesto_codificado.sum()
    grouped["participacion"] = grouped.presupuesto_codificado / total * 100 if total else 0.0
    grouped["nombre"] = grouped[name]
    if dimension == "zona":
        return grouped.sort_values(order).reset_index(drop=True)
    return grouped.sort_values("presupuesto_codificado", ascending=False).reset_index(drop=True)


def zone_values(frame: pd.DataFrame, measure: str) -> dict[str, float]:
    """Measure of every planning zone (``Z1`` … ``Z9``) for the map; the central office has no polygon."""
    zones = by(frame.loc[frame.zona_codigo.notna()], "zona")
    if measure == "porcentaje_ejecucion":
        return {row.zona_codigo: float(row.porcentaje_ejecucion) for row in zones.itertuples() if pd.notna(row.porcentaje_ejecucion)}
    return {row.zona_codigo: float(getattr(row, measure)) for row in zones.itertuples() if pd.notna(getattr(row, measure))}


def financial_programs(frame: pd.DataFrame) -> pd.DataFrame:
    """Budget by program from raw rows of the base (kept for the data update checks)."""
    grouped = frame.groupby(["programa_codigo", "programa"], as_index=False)[MONEY].sum(min_count=1)
    grouped["porcentaje_ejecucion"] = 100 * grouped.presupuesto_ejecutado / grouped.presupuesto_codificado.replace(0, float("nan"))
    return grouped.sort_values("presupuesto_ejecutado", ascending=False)
