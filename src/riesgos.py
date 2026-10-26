"""Susceptibilidad territorial de UA; una observación por corte y código de unidad."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "riesgos_ua.parquet"
THREATS = {
    "susc_inundacion": "Inundaciones",
    "susc_movimientos_masa": "Movimientos en masa",
    "susc_sequia": "Sequía",
    "susc_inc_forestales": "Incendios forestales",
}
LEVELS = ("Media", "Alta", "Muy alta")
RANK = {"Sin categoría reportada": 0, "Media": 1, "Alta": 2, "Muy alta": 3}
SERVICES = {
    "DESARROLLO INFANTIL INTEGRAL": ("DII", "Desarrollo Infantil Integral"),
    "PERSONAS ADULTOS MAYORES - PEJ": ("PAM_SERV", "Personas adultas mayores"),
    "PERSONAS CON DISCAPACIDAD": ("PCD_SERV", "Personas con discapacidad"),
    "PROTECCION ESPECIAL": ("PE", "Protección Especial"),
    "ACOMPAÑAMIENTO FAMILIAR": ("AF", "Acompañamiento familiar"),
}


def normalize(source: pd.DataFrame, period: str) -> pd.DataFrame:
    """Keep only the UA inventory needed by the dashboard; collapse repeated codes.

    Repeated codes may have different modalities. Retain their modalities and the
    highest *reported* category per threat. Never infer damage or a zero risk.
    """
    fields = {"co_siimdh": "codigo_ua", "nombre": "nombre", "servicio": "servicio",
              "mod": "modalidad", "dpa_prov": "provincia_codigo", "dpa_despro": "provincia",
              "dpa_can": "canton_codigo", "dpa_descan": "canton", "dpa_par": "parroquia_codigo",
              "dpa_despar": "parroquia", **{key: key for key in THREATS}}
    missing = set(fields) - set(source.columns)
    if missing:
        raise ValueError(f"Faltan columnas de riesgos: {sorted(missing)}")
    data = source[list(fields)].rename(columns=fields).copy()
    for key in data:
        data[key] = data[key].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    data.codigo_ua = data.codigo_ua.str.replace(r"\.0$", "", regex=True)
    if data.codigo_ua.eq("").any():
        raise ValueError("Hay unidades sin código; no se pueden contar como unidades únicas.")
    for key, width in [("provincia_codigo", 2), ("canton_codigo", 4), ("parroquia_codigo", 6)]:
        data[key] = data[key].str.replace(r"\.0$", "", regex=True).str.zfill(width)
    if not set(data.servicio) <= set(SERVICES):
        raise ValueError(f"Servicios no reconocidos: {sorted(set(data.servicio) - set(SERVICES))}")
    for key in THREATS:
        data[key] = data[key].str.casefold().map({"media": "Media", "alta": "Alta", "muy alta": "Muy alta",
                                                "-": "Sin categoría reportada", "": "Sin categoría reportada"})
        if data[key].isna().any():
            raise ValueError(f"Categorías no reconocidas en {key}")
    grouped = data.groupby("codigo_ua", sort=False)
    for key in ["servicio", "provincia_codigo", "canton_codigo", "parroquia_codigo"]:
        if grouped[key].nunique().gt(1).any():
            raise ValueError(f"Un mismo código UA tiene valores distintos de {key}; revisar la fuente.")
    aggregations = {key: "first" for key in data if key != "codigo_ua"}
    aggregations["modalidad"] = lambda values: " / ".join(dict.fromkeys(v for v in values if v))
    for key in THREATS:
        aggregations[key] = lambda values: max(values, key=RANK.get)
    data = grouped.agg(aggregations).reset_index()
    data["programa_id"] = data.servicio.map(lambda value: SERVICES[value][0])
    data["servicio"] = data.servicio.map(lambda value: SERVICES[value][1])
    data["periodo_id"] = period
    data["susceptibilidad_maxima"] = data[list(THREATS)].apply(lambda row: max(row, key=RANK.get), axis=1)
    return data.sort_values("codigo_ua").reset_index(drop=True)


def select(data: pd.DataFrame, period: str, provinces=(), programs=()) -> pd.DataFrame:
    selected = data.loc[data.periodo_id.eq(period)]
    if provinces:
        selected = selected.loc[selected.provincia_codigo.isin(provinces)]
    if programs:
        selected = selected.loc[selected.programa_id.isin(programs)]
    return selected.copy()


def aggregate_inventory(data: pd.DataFrame) -> pd.DataFrame:
    """Publish counts only; retain category combinations so unions remain exact.

    No unit code, name, address, coordinates or canton/parish is published.
    Input is the already deduplicated local inventory from normalize().
    """
    keys = ["periodo_id", "provincia_codigo", "provincia", "programa_id", "servicio",
            *THREATS, "susceptibilidad_maxima"]
    return data.groupby(keys, as_index=False, observed=True).codigo_ua.nunique().rename(columns={"codigo_ua": "unidades"})


def count_units(data: pd.DataFrame) -> int:
    return int(data.unidades.sum())


def exposed(data: pd.DataFrame, threat: str | None = None, levels=LEVELS) -> pd.DataFrame:
    """A UA is counted once if any selected threat has a selected reported level."""
    keys = [threat] if threat else list(THREATS)
    return data.loc[data[keys].isin(levels).any(axis=1)].copy()


def threat_counts(data: pd.DataFrame, threat: str | None = None, levels=LEVELS) -> pd.DataFrame:
    rows = []
    for key in ([threat] if threat else THREATS):
        for level in LEVELS:
            if level in levels:
                rows.append({"amenaza": THREATS[key], "nivel": level,
                             "unidades": count_units(data.loc[data[key].eq(level)])})
    return pd.DataFrame(rows, columns=["amenaza", "nivel", "unidades"])


def detail_counts(data: pd.DataFrame, threat: str | None = None, levels=LEVELS) -> pd.DataFrame:
    keys = [threat] if threat else list(THREATS)
    long = data.melt(id_vars=["provincia", "servicio", "unidades"], value_vars=keys,
                     var_name="amenaza", value_name="susceptibilidad")
    long = long.loc[long.susceptibilidad.isin(levels)]
    long["amenaza"] = long.amenaza.map(THREATS)
    return long.groupby(["provincia", "servicio", "amenaza", "susceptibilidad"], as_index=False, observed=True).unidades.sum()
