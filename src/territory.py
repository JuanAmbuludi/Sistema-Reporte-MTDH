"""Territorial detail (province, canton and parish) for maps, rankings and tables, shared by the dashboard and
every export.

Rows come from :func:`src.data.load_territory` (one per program and parish).  The 2015 cartography draws the urban
parishes of a city as its cantonal seat, so a map polygon may gather several parishes of the data; rankings and
tables keep each parish of the data with its own name.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src import geo, names

LEVELS = ("provincia", "canton", "parroquia")
LEVEL_LABELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}
LEVEL_PLURALS = {"provincia": "Provincias", "canton": "Cantones", "parroquia": "Parroquias"}
# Agreement of Spanish words with each level: "Las 25 primeras parroquias", "Los 25 primeros cantones".
LEVEL_GENDER = {"provincia": "f", "canton": "m", "parroquia": "f"}


@lru_cache(maxsize=8)
def _match(records: tuple[tuple[str, str, str, str], ...]) -> dict[str, str]:
    return geo.match_parishes({"code": c, "name": n, "canton": k, "province": p} for c, n, k, p in records)


def polygon_index(frame: pd.DataFrame) -> dict[str, str]:
    """Map polygon of every parish code in the rows (codes without a polygon are left out)."""
    unique = frame.drop_duplicates("parroquia_codigo")
    records = tuple(sorted(zip(unique.parroquia_codigo.astype(str), unique.parroquia.astype(str),
                               unique.canton.astype(str), unique.provincia_codigo.astype(str))))
    return _match(records)


def polygon_values(frame: pd.DataFrame, key: str) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Indicator per map polygon and the parish codes each polygon gathers."""
    if frame.empty:
        return {}, {}
    index = polygon_index(frame)
    by_parish = frame.groupby("parroquia_codigo", observed=True)[key].sum(min_count=1)
    values, members = {}, {}
    for code, value in by_parish.items():
        polygon = index.get(str(code))
        if polygon is None:
            continue
        members.setdefault(polygon, []).append(str(code))
        if pd.notna(value):
            values[polygon] = values.get(polygon, 0.0) + float(value)
    return values, members


def parish_table(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """One row per parish with readable names, largest first.

    Records of a cantonal seat and of the urban parish that shares its name (``MACHALA`` 070102 and 070150) read as
    one place, so they are added together; their codes stay listed in ``parroquia_codigo``.
    """
    view = frame.assign(parroquia_nombre=frame.parroquia.map(names.place), canton_nombre=frame.canton.map(names.place))
    columns = ["provincia_codigo", "provincia", "canton_codigo", "canton_nombre", "parroquia_nombre"]
    grouped = view.groupby(columns, as_index=False, observed=True).agg(
        **{key: (key, lambda s: s.sum(min_count=1)) for key in keys},
        parroquia_codigo=("parroquia_codigo", lambda s: ", ".join(sorted(set(map(str, s))))))
    return grouped.sort_values(keys[0], ascending=False, na_position="last").reset_index(drop=True)


def canton_table(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    columns = ["provincia_codigo", "provincia", "canton_codigo", "canton"]
    grouped = frame.groupby(columns, as_index=False, observed=True)[keys].sum(min_count=1)
    grouped["canton_nombre"] = grouped.canton.map(names.place)
    return grouped.sort_values(keys[0], ascending=False, na_position="last").reset_index(drop=True)


def parish_count(frame: pd.DataFrame, key: str = "usuarios") -> int:
    """Parishes with a positive value of the indicator (places, as in :func:`parish_table`)."""
    if frame.empty:
        return 0
    table = parish_table(frame, [key])
    return int(pd.to_numeric(table[key], errors="coerce").gt(0).sum())


def short_canton(name: str) -> str:
    """Chart name of a canton: ``Distrito Metropolitano de Quito`` reads ``Quito`` (tables keep the official name)."""
    return name.removeprefix("Distrito Metropolitano de ").strip() or name


def parish_label(row) -> str:
    """``Eloy Alfaro · Durán``; the canton is left out when one name contains the other (``Quito``)."""
    parish, canton = row["parroquia_nombre"], short_canton(row["canton_nombre"])
    a, b = names.key(parish), names.key(canton)
    return parish if (a in b or b in a) else f"{parish} · {canton}"


def canton_values(frame: pd.DataFrame, key: str) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Indicator per canton polygon and the cantons of the data each polygon gathers.

    Each parish is drawn where its polygon lies, so the value of a canton is the sum of the parishes inside its
    polygon (a parish the 2015 cartography placed in a neighbouring canton is drawn with that canton).
    """
    if frame.empty:
        return {}, {}
    index = polygon_index(frame)
    parishes = geo.features("parroquia")
    by_parish = frame.groupby(["parroquia_codigo", "canton_codigo"], observed=True)[key].sum(min_count=1)
    values, members = {}, {}
    for (code, canton), value in by_parish.items():
        target = parishes.get(index.get(str(code), ""), {}).get("canton")
        if target is None:
            continue
        members.setdefault(target, set()).add(str(canton))
        if pd.notna(value):
            values[target] = values.get(target, 0.0) + float(value)
    return values, {code: sorted(found) for code, found in members.items()}


def unique_labels(labels: list[str], qualifiers: list[str]) -> list[str]:
    """Chart labels that never repeat: a repeated name carries its province (``Bolívar · Carchi``)."""
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    out = [f"{label} · {qualifier}" if counts[label] > 1 and qualifier else label for label, qualifier in zip(labels, qualifiers)]
    seen: dict[str, int] = {}
    for index, label in enumerate(out):
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            out[index] = f"{label} ({seen[label]})"
    return out


def level_table(frame: pd.DataFrame, level: str, keys: list[str]) -> pd.DataFrame:
    """One row per province, canton or parish of the rows, largest first by ``keys[0]``.

    Columns: ``codigo``, ``nombre``, ``etiqueta`` (unique chart label), ``detalle`` (full place for hovers),
    ``provincia_codigo``, ``provincia``, ``canton_nombre`` (cantons and parishes) and the summed ``keys``; with both
    budget columns it adds ``porcentaje_ejecucion``.
    """
    if frame.empty:
        return pd.DataFrame(columns=["codigo", "nombre", "etiqueta", "detalle", "provincia_codigo", "provincia", *keys])
    if level == "parroquia":
        table = parish_table(frame, keys)
        table["codigo"], table["nombre"] = table.parroquia_codigo, table.parroquia_nombre
        labels = [parish_label(row) for _index, row in table.iterrows()]
        table["detalle"] = [f"{label}, {province}" for label, province in zip(labels, table.provincia)]
    elif level == "canton":
        table = canton_table(frame, keys)
        table["codigo"], table["nombre"] = table.canton_codigo, table.canton_nombre
        labels = [short_canton(name) for name in table.canton_nombre]
        table["detalle"] = [f"{row.canton_nombre} · {row.provincia}" for row in table.itertuples()]
    else:
        table = frame.groupby(["provincia_codigo", "provincia"], as_index=False, observed=True)[keys].sum(min_count=1)
        table = table.sort_values(keys[0], ascending=False, na_position="last").reset_index(drop=True)
        table["codigo"], table["nombre"] = table.provincia_codigo, table.provincia
        labels = list(table.provincia)
        table["detalle"] = list(table.provincia)
    table["etiqueta"] = unique_labels(labels, list(table.provincia))
    if {"presupuesto_ejecutado", "presupuesto_codificado"} <= set(table.columns):
        coded = pd.to_numeric(table.presupuesto_codificado, errors="coerce")
        table["porcentaje_ejecucion"] = pd.to_numeric(table.presupuesto_ejecutado, errors="coerce") / coded.where(coded > 0) * 100
    return table.reset_index(drop=True)


def half_count(values) -> int:
    """Fewest territories that together hold half of the total (0 without values)."""
    ordered = sorted((float(v) for v in values if v is not None and v == v and v > 0), reverse=True)
    total, running = sum(ordered), 0.0
    for count, value in enumerate(ordered, start=1):
        running += value
        if running >= total / 2:
            return count
    return 0


def reach(frame: pd.DataFrame, key: str = "usuarios", levels=LEVELS) -> dict[str, dict]:
    """Territories with coverage at each level and how many of them gather half of it."""
    out = {}
    for level in levels:
        table = level_table(frame, level, [key])
        values = pd.to_numeric(table[key], errors="coerce") if key in table else pd.Series(dtype=float)
        # The zone in study is not a delimited territory: it counts in totals, not among provinces, cantons or parishes.
        values = values[table.provincia_codigo.astype(str).ne(geo.NO_POLYGON)] if len(table) else values
        positive = values[values > 0]
        out[level] = {"count": int(len(positive)), "half": half_count(positive.tolist()), "total": float(positive.sum())}
    return out


def level_programs(frame: pd.DataFrame, level: str, key: str, territories: pd.DataFrame) -> pd.DataFrame:
    """Program rows of the ``territories`` (a slice of :func:`level_table`), labelled for the composition matrix.

    Returns ``fila_codigo``, ``fila`` (the territory's chart label), ``programa_id``, ``programa`` and ``key``.
    """
    columns = ["fila_codigo", "fila", "programa_id", "programa", key]
    if frame.empty or territories.empty:
        return pd.DataFrame(columns=columns)
    if level == "parroquia":
        view = frame.assign(parroquia_nombre=frame.parroquia.map(names.place))
        index = {(str(r.provincia_codigo), str(r.canton_codigo), r.parroquia_nombre): (str(r.codigo), r.etiqueta)
                 for r in territories.itertuples()}
        keys = zip(view.provincia_codigo.astype(str), view.canton_codigo.astype(str), view.parroquia_nombre)
    elif level == "canton":
        view = frame
        index = {(str(r.provincia_codigo), str(r.codigo)): (str(r.codigo), r.etiqueta) for r in territories.itertuples()}
        keys = zip(view.provincia_codigo.astype(str), view.canton_codigo.astype(str))
    else:
        view = frame
        index = {(str(r.codigo),): (str(r.codigo), r.etiqueta) for r in territories.itertuples()}
        keys = zip(view.provincia_codigo.astype(str))
    matched = [index.get(tuple(k)) for k in keys]
    mask = [m is not None for m in matched]
    out = view.loc[mask, ["programa_id", "programa", key]].copy()
    found = [m for m in matched if m is not None]
    out.insert(0, "fila", [m[1] for m in found])
    out.insert(0, "fila_codigo", [m[0] for m in found])
    return out.reset_index(drop=True)
