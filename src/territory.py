"""Parish detail for maps, rankings and tables, shared by the dashboard and every export.

Rows come from :func:`src.data.load_territory` (one per program and parish).  The 2015 cartography draws the urban
parishes of a city as its cantonal seat, so a map polygon may gather several parishes of the data; rankings and
tables keep each parish of the data with its own name.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from src import geo, names


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


def parish_label(row) -> str:
    """``Eloy Alfaro · Durán``; the canton is left out when one name contains the other (``Quito``)."""
    parish, canton = row["parroquia_nombre"], row["canton_nombre"]
    a, b = names.key(parish), names.key(canton)
    return parish if (a in b or b in a) else f"{parish} · {canton}"
