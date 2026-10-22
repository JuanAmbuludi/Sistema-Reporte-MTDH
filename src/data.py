"""Shared, side-effect-free data access and aggregation for dashboard and exports.

Never add snapshots across years. A current row is a reported program/province
aggregate; the source does not identify distinct people or physical units.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
SECTIONS = {
    "bonos_pensiones": "Bonos y pensiones",
    "proteccion_integral": "Servicios de protección integral",
}
MONEY_COLUMNS = ["monto_fiscal", "monto_gobierno", "monto_anterior", "presupuesto_ejecutado"]
METRIC_COLUMNS = ["usuarios", "unidades", *MONEY_COLUMNS]


def load_data(data_dir: str | Path | None = None) -> pd.DataFrame:
    """Load the current snapshot. ``data_dir`` may also be a parquet filename."""
    path = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    if path.suffix.lower() != ".parquet":
        path = path / "indicadores.parquet"
    frame = pd.read_parquet(path)
    for col in MONEY_COLUMNS:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="raise").astype(float)
    for col in ["usuarios", "unidades", "unidades_origen"]:
        if col in frame:
            frame[col] = frame[col].astype("Int64")
    frame["periodo"] = pd.to_datetime(frame["periodo"])
    return frame


def load_manifest(data_dir: str | Path | None = None) -> dict:
    return json.loads((Path(data_dir or DEFAULT_DATA_DIR) / "manifest.json").read_text(encoding="utf-8"))


def load_history(data_dir: str | Path | None = None) -> pd.DataFrame:
    """Reference snapshots only: their cutoff months are not documented."""
    path = Path(data_dir or DEFAULT_DATA_DIR) / "historico_referencia.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    for col in MONEY_COLUMNS:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="raise").astype(float)
    return frame


MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")
PERIOD_COLUMNS = ["periodo", "anio", "seccion", "programa_id", "programa", "provincia_codigo", "provincia", *METRIC_COLUMNS]


def load_periods(data_dir: str | Path | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Every period the base can show: monthly cuts and annual reference years.

    Rows keep their own ``periodo_id``; filter to one period before adding anything.  The catalog lists the
    periods newest first, each with ``id``, ``year``, ``month`` (None for a year without a monthly cut) and
    ``label`` ("Septiembre 2026", "Año 2025").
    """
    current = load_data(data_dir)
    current = current.assign(periodo_id=current["periodo"].dt.strftime("%Y-%m"),
                             periodo_anio=current["periodo"].dt.year.astype(int),
                             periodo_mes=current["periodo"].dt.month.astype(int))
    frames = [current[PERIOD_COLUMNS + ["periodo_id", "periodo_anio", "periodo_mes"]]]
    history = load_history(data_dir)
    if not history.empty:
        years = history["anio_referencia"].astype(int)
        annual = history.assign(anio=years, periodo=pd.NaT, periodo_id=years.astype(str), periodo_anio=years, periodo_mes=0)
        frames.append(annual[PERIOD_COLUMNS + ["periodo_id", "periodo_anio", "periodo_mes"]])
    combined = pd.concat(frames, ignore_index=True)
    for col in ["usuarios", "unidades"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce").astype("Int64")
    for col in MONEY_COLUMNS:
        combined[col] = pd.to_numeric(combined[col], errors="coerce").astype(float)
    catalog = []
    for (period_id, year, month), _rows in combined.groupby(["periodo_id", "periodo_anio", "periodo_mes"], sort=False):
        month = int(month) or None
        label = f"{MONTHS[month - 1].capitalize()} {year}" if month else f"Año {year}"
        catalog.append({"id": period_id, "year": int(year), "month": month, "label": label})
    catalog.sort(key=lambda p: (p["year"], p["month"] or 13), reverse=True)
    return combined, catalog


def filter_data(
    df: pd.DataFrame,
    provincias: Iterable[str] | None = None,
    programas: Iterable[str] | None = None,
    secciones: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Filter by province codes/names, program IDs and section IDs.

    ``None`` keeps every value; an explicitly empty list returns no rows.
    """
    mask = pd.Series(True, index=df.index)
    if provincias is not None:
        selected = list(provincias)
        mask &= df["provincia_codigo"].isin(selected) | df["provincia"].isin(selected)
    if programas is not None:
        mask &= df["programa_id"].isin(list(programas))
    if secciones is not None:
        mask &= df["seccion"].isin(list(secciones))
    return df.loc[mask].copy()


def _sum(series: pd.Series, *, integer: bool = False):
    value = series.sum(min_count=1)
    if pd.isna(value):
        return None
    return int(value) if integer else float(value)


def _assert_single_period(df: pd.DataFrame) -> None:
    if "periodo_id" in df and df["periodo_id"].nunique() > 1:
        raise ValueError("Seleccione un solo corte: los usuarios y unidades no se suman entre períodos.")
    if "periodo" in df and df["periodo"].dropna().nunique() > 1:
        raise ValueError("Seleccione un solo corte: los usuarios y unidades no se suman entre períodos.")
    if "anio_referencia" in df and df["anio_referencia"].nunique() > 1:
        raise ValueError("Las referencias históricas tienen cortes distintos; no se pueden sumar.")


def summarize(df: pd.DataFrame) -> dict:
    """One consistent snapshot consumed by the UI and every report format.

    Execution totals are withheld when any selected row lacks certified data.
    Partial sums remain explicit and must not be called the total execution.
    """
    _assert_single_period(df)
    bonos = df.loc[df["seccion"].eq("bonos_pensiones")]
    servicios = df.loc[df["seccion"].eq("proteccion_integral")]
    complete = len(df) > 0 and df["presupuesto_ejecutado"].notna().all()
    partial = _sum(df["presupuesto_ejecutado"])
    dates = df["periodo"].dropna() if "periodo" in df else pd.Series(dtype="datetime64[ns]")
    return {
        "usuarios": _sum(df["usuarios"], integer=True) or 0,
        "beneficiarios": _sum(bonos["usuarios"], integer=True) or 0,
        "usuarios_servicios": _sum(servicios["usuarios"], integer=True) or 0,
        "unidades": _sum(servicios["unidades"], integer=True),
        "monto_fiscal": _sum(df["monto_fiscal"]),
        "monto_gobierno": _sum(df["monto_gobierno"]),
        "monto_anterior": _sum(df["monto_anterior"]),
        "presupuesto_ejecutado": partial if complete else None,
        "presupuesto_ejecutado_parcial": partial,
        "ejecucion_cobertura_pct": float(df["presupuesto_ejecutado"].notna().mean() * 100) if len(df) else 0.0,
        "registros": len(df),
        "provincias": int(df.loc[df["provincia_codigo"].ne("90"), "provincia_codigo"].nunique()),
        "programas": int(df["programa_id"].nunique()),
        "periodo": pd.Timestamp(dates.iloc[0]).date().isoformat() if len(dates) else None,
        "anio": int(df["anio"].iloc[0]) if len(df) and "anio" in df else None,
    }


def aggregate(df: pd.DataFrame, by: str | list[str] = "programa") -> pd.DataFrame:
    """Sum non-overlapping current rows; all-null metrics remain null."""
    _assert_single_period(df)
    groups = [by] if isinstance(by, str) else list(by)
    if not groups:
        raise ValueError("Indique al menos una dimensión para agrupar.")
    if df.empty:
        return pd.DataFrame(columns=groups + METRIC_COLUMNS + ["registros", "ejecucion_cobertura_pct"])
    grouped = df.groupby(groups, dropna=False, observed=True)
    out = grouped[METRIC_COLUMNS].sum(min_count=1)
    out["registros"] = grouped.size()
    supplied = grouped["presupuesto_ejecutado"].count()
    out["ejecucion_cobertura_pct"] = 100 * supplied / out["registros"]
    out.loc[supplied.ne(out["registros"]), "presupuesto_ejecutado"] = float("nan")
    return out.reset_index()
