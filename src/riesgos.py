"""Susceptibilidad territorial de UA; una observación por corte y código de unidad."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "riesgos_ua.parquet"
DETAIL_PATH = DATA_PATH.with_name("riesgos_ua_detalle.parquet")
MATRIX_PATH = DATA_PATH.with_name("riesgos_ua_matriz.parquet")
MULTI_THREATS = ("susc_inundacion", "susc_movimientos_masa")
MULTI_NOTE = ("Multiamenaza reproduce los registros de la matriz fuente expuestos a inundaciones o movimientos en masa, "
              "con los filtros vigentes; puede incluir códigos UA repetidos. Los demás indicadores cuentan unidades únicas.")
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
DETAIL_FIELDS = ["periodo_id", "codigo_ua", "nombre", "provincia_codigo", "provincia", "programa_id", "servicio",
                 *THREATS, "susceptibilidad_maxima"]


def normalize(source: pd.DataFrame, period: str, *, deduplicate: bool = True) -> pd.DataFrame:
    """Keep only the UA inventory needed by the dashboard; collapse repeated codes.

    Repeated codes may have different modalities. Retain their modalities and the
    highest *reported* category per threat. With deduplicate=False, preserve source
    rows for the separate matrix counts. Never infer damage or a zero risk.
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
    if deduplicate:
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


def aggregate_matrix(data: pd.DataFrame) -> pd.DataFrame:
    """Source-row counts by category combination, without publishing unit identifiers."""
    keys = ["periodo_id", "provincia_codigo", "provincia", "programa_id", "servicio", *THREATS, "susceptibilidad_maxima"]
    return data.groupby(keys, as_index=False, observed=True).size().rename(columns={"size": "registros"})


def multihazard(data: pd.DataFrame, levels=LEVELS) -> pd.DataFrame:
    """Union of inundation OR mass movement, counting each source row only once."""
    return data.loc[data[list(MULTI_THREATS)].isin(levels).any(axis=1)].copy()


def count_records(data: pd.DataFrame) -> int:
    return int(data.registros.sum())


def threat_keys(threat=None) -> list[str]:
    """Columns of the chosen threats: one (``"susc_sequia"``), several (a list) or the four when none is chosen."""
    if not threat:
        return list(THREATS)
    chosen = [threat] if isinstance(threat, str) else list(threat)
    return [key for key in THREATS if key in chosen]


def threat_label(threat=None) -> str:
    """«Todas las amenazas», «Sequía» or «Inundaciones y sequía»."""
    keys = threat_keys(threat)
    if len(keys) == len(THREATS):
        return "Todas las amenazas"
    names = [THREATS[k] for k in keys]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " y " + names[-1].lower()


def exposed(data: pd.DataFrame, threat=None, levels=LEVELS) -> pd.DataFrame:
    """A UA is counted once if any selected threat has a selected reported level."""
    keys = threat_keys(threat)
    return data.loc[data[keys].isin(levels).any(axis=1)].copy()


def threat_counts(data: pd.DataFrame, threat=None, levels=LEVELS) -> pd.DataFrame:
    rows = []
    for key in threat_keys(threat):
        for level in LEVELS:
            if level in levels:
                rows.append({"amenaza": THREATS[key], "nivel": level,
                             "unidades": count_units(data.loc[data[key].eq(level)])})
    return pd.DataFrame(rows, columns=["amenaza", "nivel", "unidades"])


def max_level(data: pd.DataFrame, threat=None, levels=LEVELS) -> pd.Series:
    """Highest of the chosen categories among the chosen threats of each row (empty text when none applies)."""
    if data.empty:
        return pd.Series("", index=data.index, dtype=object)
    ranks = pd.concat([data[key].map(RANK).where(data[key].isin(levels), 0) for key in threat_keys(threat)], axis=1).max(axis=1)
    return ranks.astype(int).map({1: "Media", 2: "Alta", 3: "Muy alta"}).fillna("")


def threat_count(data: pd.DataFrame, levels=LEVELS) -> pd.Series:
    """How many of the four threats each row faces in the chosen categories (0 to 4)."""
    return data[list(THREATS)].isin(levels).sum(axis=1)


def by_threat(scoped: pd.DataFrame, threat=None, levels=LEVELS) -> pd.DataFrame:
    """Each chosen threat: its units by category, the exposed units and their share of the inventory of the selection."""
    inventory = count_units(scoped)
    rows = []
    for key in threat_keys(threat):
        row = {"clave": key, "amenaza": THREATS[key]}
        for level in LEVELS:
            row[level] = count_units(scoped.loc[scoped[key].eq(level)]) if level in levels else 0
        row["expuestas"] = sum(row[level] for level in LEVELS)
        row["porcentaje"] = row["expuestas"] / inventory * 100 if inventory else None
        rows.append(row)
    return pd.DataFrame(rows, columns=["clave", "amenaza", *LEVELS, "expuestas", "porcentaje"])


def concurrency(selected: pd.DataFrame, levels=LEVELS) -> pd.DataFrame:
    """Exposed units by how many of the four threats they face at once, in the chosen categories."""
    counts = selected.assign(amenazas=threat_count(selected, levels)).groupby("amenazas").unidades.sum()
    out = pd.DataFrame({"amenazas": [1, 2, 3, 4]})
    out["unidades"] = out.amenazas.map(counts).fillna(0).astype(int)
    total = out.unidades.sum()
    out["porcentaje"] = out.unidades / total * 100 if total else 0.0
    return out


def combinations(selected: pd.DataFrame, levels=LEVELS, limit: int | None = None) -> pd.DataFrame:
    """Threats that coincide in the exposed units (each unit in exactly one combination), largest first."""
    if selected.empty:
        return pd.DataFrame(columns=["combinacion", "amenazas", "unidades", "porcentaje"])
    flags = selected[list(THREATS)].isin(levels)
    names = [" + ".join(THREATS[key] for key in THREATS if row[key]) for row in flags.to_dict("records")]
    frame = pd.DataFrame({"combinacion": names, "amenazas": flags.sum(axis=1).to_numpy(), "unidades": selected.unidades.to_numpy()})
    frame = frame.loc[frame.amenazas.gt(0)]
    out = frame.groupby(["combinacion", "amenazas"], as_index=False).unidades.sum().sort_values(
        ["unidades", "amenazas"], ascending=[False, True]).reset_index(drop=True)
    total = out.unidades.sum()
    out["porcentaje"] = out.unidades / total * 100 if total else 0.0
    return out.head(limit) if limit else out


def _place_columns(frame: pd.DataFrame, by: str) -> list[str]:
    return ["provincia_codigo", "provincia"] if by == "provincia" else ["programa_id", "servicio"]


def profile(scoped: pd.DataFrame, selected: pd.DataFrame, by: str = "provincia", threat=None, levels=LEVELS,
            multihazard_rows: pd.DataFrame | None = None) -> pd.DataFrame:
    """Provinces (``by="provincia"``) or services (``by="servicio"``) of the selection, largest exposure first.

    Columns: the inventory of units, the exposed units and their share of that inventory, the exposed units by their
    highest category among the chosen threats (Media, Alta, Muy alta), the share of all exposed units, the units of
    each threat in the chosen categories and, with ``multihazard_rows``, the multihazard records of the source matrix.
    """
    keys = _place_columns(scoped, by)
    inventory = scoped.groupby(keys, observed=True).unidades.sum().rename("inventario")
    out = inventory.to_frame()
    exposed_units = selected.groupby(keys, observed=True).unidades.sum()
    out["expuestas"] = exposed_units.reindex(out.index).fillna(0).astype(int)
    out["porcentaje"] = out.expuestas / out.inventario.where(out.inventario > 0) * 100
    top = selected.assign(nivel_maximo=max_level(selected, threat, levels))
    for level in LEVELS:
        part = top.loc[top.nivel_maximo.eq(level)].groupby(keys, observed=True).unidades.sum()
        out[level] = part.reindex(out.index).fillna(0).astype(int)
    total = out.expuestas.sum()
    out["participacion"] = out.expuestas / total * 100 if total else 0.0
    for key, name in THREATS.items():
        part = scoped.loc[scoped[key].isin(levels)].groupby(keys, observed=True).unidades.sum()
        out[name] = part.reindex(out.index).fillna(0).astype(int)
    if multihazard_rows is not None:
        part = multihazard_rows.groupby(keys, observed=True).registros.sum()
        out["multiamenaza"] = part.reindex(out.index).fillna(0).astype(int)
    out = out.reset_index().sort_values(["expuestas", "inventario"], ascending=False).reset_index(drop=True)
    return out


def detail_counts(data: pd.DataFrame, threat=None, levels=LEVELS) -> pd.DataFrame:
    keys = threat_keys(threat)
    long = data.melt(id_vars=["provincia", "servicio", "unidades"], value_vars=keys,
                     var_name="amenaza", value_name="susceptibilidad")
    long = long.loc[long.susceptibilidad.isin(levels)]
    long["amenaza"] = long.amenaza.map(THREATS)
    return long.groupby(["provincia", "servicio", "amenaza", "susceptibilidad"], as_index=False, observed=True).unidades.sum()
