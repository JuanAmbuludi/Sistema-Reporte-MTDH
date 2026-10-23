"""One immutable report snapshot shared by the one-page summary, the slides and the data workbook.

All values come from the rows already filtered on screen: one period and one thematic module.  No exporter
reopens the source or changes the scope behind the reader's selection, and transfers are never mixed with
services.  The parish detail, when the cut has it, travels with the snapshot for the maps and the parish sheet.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src import theme
from src.indicators import module_for_sections

REGIONS = theme.REGIONS
NO_POLYGON = "90"
MONTHS = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")
INSTITUTION = "Ministerio de Trabajo y Desarrollo Humano"
PRODUCT = "InfoReport"


def number(value, decimals=0):
    """Ecuadorian figures: 1.578.019 · 55.867.299,38.  A missing value reads as a dash."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", "~").replace(".", ",").replace("~", ".")


def millions(value, decimals=1):
    return "—" if value is None or pd.isna(value) else number(float(value) / 1_000_000, decimals)


def _sum(df, name, integer=False):
    if name not in df or df.empty:
        return None
    values = pd.to_numeric(df[name], errors="coerce")
    if values.notna().sum() == 0:
        return None
    total = float(values.sum(min_count=1))
    return int(round(total)) if integer else total


def _period(frame: pd.DataFrame) -> tuple[str, str, int]:
    """Period id, label and year of the rows; more than one period is rejected."""
    if "periodo_id" in frame:
        if frame["periodo_id"].nunique() != 1:
            raise ValueError("El reporte requiere un único periodo. Las cifras no se suman entre periodos.")
        period_id = str(frame["periodo_id"].iloc[0])
        year, month = int(frame["periodo_anio"].iloc[0]), int(frame["periodo_mes"].iloc[0]) or None
    else:
        periods = pd.to_datetime(frame["periodo"]).dt.to_period("M").unique()
        if len(periods) != 1:
            raise ValueError("El reporte requiere un único periodo. Las cifras no se suman entre periodos.")
        moment = periods[0].to_timestamp()
        period_id, year, month = moment.strftime("%Y-%m"), moment.year, moment.month
    label = f"{MONTHS[month].capitalize()} {year}" if month else f"Año {year}"
    return period_id, label, year


def _figures(df: pd.DataFrame) -> dict:
    executed = _sum(df, "presupuesto_ejecutado") if df["presupuesto_ejecutado"].notna().all() else None
    coded = _sum(df, "presupuesto_codificado") if "presupuesto_codificado" in df and df["presupuesto_codificado"].notna().all() else None
    return {
        "people": _sum(df, "usuarios", integer=True),
        "units": _sum(df, "unidades", integer=True),
        "fiscal": _sum(df, "monto_fiscal"),
        "previous": _sum(df, "monto_anterior"),
        "government": _sum(df, "monto_gobierno"),
        "executed": executed,
        "coded": coded,
        "execution": executed / coded * 100 if executed is not None and coded else None,
    }


def _share(part, whole):
    return part / whole * 100 if part is not None and whole else None


ORDINALS = ("primer", "segundo", "tercer", "cuarto", "quinto", "sexto", "séptimo", "octavo", "noveno", "décimo")


def _place(position: int) -> str:
    return f"{ORDINALS[position - 1]} lugar" if 1 <= position <= len(ORDINALS) else f"puesto {position}"


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def stamp() -> tuple[str, str]:
    moment = datetime.now(ZoneInfo("America/Guayaquil"))
    return moment.isoformat(timespec="seconds"), f"{moment.day} de {MONTHS[moment.month]} de {moment.year}"


def _parish_block(parishes: pd.DataFrame | None, national: pd.DataFrame | None, selected: set[str], has_units: bool) -> dict | None:
    """Parish detail of the selection: map values, leading parishes and every parish for the workbook."""
    if parishes is None or parishes.empty:
        return None
    from src import territory
    keys = ["usuarios", "presupuesto_ejecutado"] + (["unidades"] if has_units else [])
    focus = {c for c in selected if c != NO_POLYGON}
    source = parishes if focus else (national if national is not None and not national.empty else parishes)
    values, _members = territory.polygon_values(source, "usuarios")
    table = territory.parish_table(parishes, keys)
    total = pd.to_numeric(table.usuarios, errors="coerce").sum()
    rows = []
    for row in table.itertuples():
        people = None if pd.isna(row.usuarios) else int(row.usuarios)
        rows.append({"province": str(row.provincia), "province_code": str(row.provincia_codigo), "canton": row.canton_nombre,
                     "parish": row.parroquia_nombre, "code": row.parroquia_codigo,
                     "label": territory.parish_label({"parroquia_nombre": row.parroquia_nombre, "canton_nombre": row.canton_nombre}),
                     "people": people, "share": _share(people, total),
                     "units": (None if pd.isna(row.unidades) else int(row.unidades)) if has_units else None,
                     "fiscal": None if pd.isna(row.presupuesto_ejecutado) else float(row.presupuesto_ejecutado)})
    return {"values": values, "focus": sorted(focus), "rows": rows, "top": rows[:10],
            "count": sum(1 for r in rows if (r["people"] or 0) > 0), "total": total}


def build_report_context(frame: pd.DataFrame, *, national: pd.DataFrame | None = None, title: str | None = None,
                         period_label: str | None = None, territory_label: str | None = None,
                         programs_label: str | None = None, selected_codes=None, parishes: pd.DataFrame | None = None,
                         parishes_national: pd.DataFrame | None = None) -> dict:
    """Serializable snapshot of the selection.

    ``national`` is the same period, module and programs for every province; it gives the selection its place
    in the country.  ``parishes`` (and ``parishes_national``) carry the parish detail of the same rows when the cut
    has it.  Labels arrive from the interface so documents name things exactly as the screen does.
    """
    if frame.empty:
        raise ValueError("No hay información en la selección. Ajuste los filtros antes de generar el documento.")
    for column in ["monto_anterior", "presupuesto_ejecutado", "presupuesto_codificado"]:
        if column not in frame:
            frame = frame.assign(**{column: float("nan")})
    module = module_for_sections(frame["seccion"].unique())
    national = frame if national is None else national
    for column in ["monto_anterior", "presupuesto_ejecutado", "presupuesto_codificado"]:
        if column not in national:
            national = national.assign(**{column: float("nan")})
    period_id, default_label, year = _period(frame)
    period_label = period_label or default_label
    executed = bool(frame["presupuesto_ejecutado"].notna().all() and frame["presupuesto_codificado"].notna().all())
    money = module.money(year, executed=executed)
    selected = {str(c) for c in (selected_codes or [])}
    people_label = module.people
    people_lower = people_label.lower()
    has_units = bool(module.extra)

    totals = _figures(frame)
    nation = _figures(national)
    labels = {"people": people_label, "units": module.extra[0].label if has_units else None,
              "fiscal": money["fiscal"].label, "previous": money["previous"].label, "government": money["government"].label,
              "coded": money["coded"].label, "fiscal_short": money["fiscal"].compact, "previous_short": money["previous"].compact,
              "government_short": money["government"].compact, "item": module.item, "items": module.items}

    # Programs or services of the selection, largest first.
    programs = []
    for (pid, name), group in frame.groupby(["programa_id", "programa"], sort=False):
        figures = _figures(group)
        programs.append({"id": str(pid), "label": str(name), "short": theme.program_label(pid, name), **figures,
                         "share": _share(figures["people"], totals["people"])})
    programs.sort(key=lambda r: (-(r["people"] or 0), r["label"]))
    active_programs = sum(1 for p in programs if (p["people"] or 0) > 0)

    # Every province in the national context, with its place among provinces and whether it was chosen.
    provinces = []
    for (code, name), group in national.groupby(["provincia_codigo", "provincia"], sort=False):
        figures = _figures(group)
        provinces.append({"code": str(code), "name": str(name), "region": REGIONS.get(str(code), ""), **figures,
                          "share": _share(figures["people"], nation["people"]), "selected": str(code) in selected})
    provinces.sort(key=lambda r: (-(r["people"] or 0), r["name"]))
    place = 0
    for row in provinces:
        if row["code"] != NO_POLYGON:
            place += 1
            row["position"] = place
        else:
            row["position"] = None
    province_count = place

    detail = []
    for row in frame.sort_values(["programa", "provincia"]).itertuples(index=False):
        coded = getattr(row, "presupuesto_codificado", float("nan"))
        executed_row = row.presupuesto_ejecutado
        detail.append({
            "program_id": str(row.programa_id), "program": str(row.programa), "code": str(row.provincia_codigo),
            "province": str(row.provincia), "region": REGIONS.get(str(row.provincia_codigo), ""),
            "people": None if pd.isna(row.usuarios) else int(row.usuarios),
            "units": None if pd.isna(row.unidades) else int(row.unidades),
            "fiscal": None if pd.isna(row.monto_fiscal) else float(row.monto_fiscal),
            "coded": None if pd.isna(coded) else float(coded),
            "execution": float(executed_row) / float(coded) * 100 if executed and not pd.isna(coded) and coded else None,
            "previous": None if pd.isna(row.monto_anterior) else float(row.monto_anterior),
            "government": None if pd.isna(row.monto_gobierno) else float(row.monto_gobierno),
        })

    share_national = _share(totals["people"], nation["people"]) if selected else None
    kpis = [{"key": "people", "label": people_label, "value": totals["people"], "kind": "count", "icon": module.people_icon,
             "share": share_national}]
    if has_units:
        kpis.append({"key": "units", "label": labels["units"], "value": totals["units"], "kind": "count", "icon": "building",
                     "share": _share(totals["units"], nation["units"]) if selected else None})
    elif executed:
        kpis.append({"key": "execution", "label": "Ejecución presupuestaria", "short": "Ejecución presupuestaria",
                     "value": totals["execution"], "kind": "rate", "icon": "target", "share": None,
                     "note": f"Codificado: USD {millions(totals['coded'])} M"})
    else:
        kpis.append({"key": "programs", "label": f"{module.items.capitalize()} con {people_lower}", "value": active_programs,
                     "kind": "count", "icon": "layers", "share": None, "note": f"De {len(programs)} {module.items}"})
    fiscal_note = f"Ejecución: {number(totals['execution'], 1)} % del codificado" if executed and has_units else ""
    kpis.append({"key": "fiscal", "label": labels["fiscal"], "short": labels["fiscal_short"], "value": totals["fiscal"], "kind": "money",
                 "icon": "banknote", "share": _share(totals["fiscal"], nation["fiscal"]) if selected else None, "note": fiscal_note})
    kpis.append({"key": "government", "label": labels["government"], "short": labels["government_short"], "value": totals["government"],
                 "kind": "money", "icon": "landmark", "share": _share(totals["government"], nation["government"]) if selected else None})

    parish = _parish_block(parishes, parishes_national, selected, has_units)

    # Findings written for an authority: leading program, territory, resources and parishes.
    insights = []
    leader = programs[0]
    if len(programs) > 1 and totals["people"]:
        insights.append({"icon": "award", "text": f"{leader['label']} concentra el {number(leader['share'], 1)} % de los "
                                                  f"{people_lower}, con {number(leader['people'])} personas."})
    else:
        insights.append({"icon": "award", "text": f"{leader['label']} registra {number(leader['people'])} {people_lower} en el periodo."})
    chosen = [p for p in provinces if p["selected"]]
    if len(chosen) == 1 and chosen[0]["position"]:
        row = chosen[0]
        insights.append({"icon": "pin", "text": f"{row['name']} ocupa el {_place(row['position'])} entre las {province_count} provincias "
                                                f"y reúne el {number(row['share'], 1)} % de los {people_lower} del país."})
    elif chosen:
        insights.append({"icon": "pin", "text": f"Las {len(chosen)} provincias seleccionadas reúnen el {number(share_national, 1)} % de los "
                                                f"{people_lower} del país; {chosen[0]['name']} registra el mayor número."})
    else:
        leaders = [p for p in provinces if p["position"]][:3]
        share3 = sum(p["share"] or 0 for p in leaders)
        insights.append({"icon": "pin", "text": f"{_join([p['name'] for p in leaders])} reúnen el {number(share3, 1)} % de los "
                                                f"{people_lower} del país."})
    if executed:
        unit_text = f"Los servicios operan con {number(totals['units'])} unidades de atención. " if has_units else ""
        insights.append({"icon": "trending-up", "text": f"{unit_text}El {money['fiscal'].label.lower()} asciende a USD "
                                                        f"{millions(totals['fiscal'])} millones, el {number(totals['execution'], 1)} % "
                                                        f"del presupuesto codificado."})
    elif has_units:
        insights.append({"icon": "trending-up", "text": f"Los servicios operan con {number(totals['units'])} unidades de atención y un "
                                                        f"{money['fiscal'].label.lower()} de USD {millions(totals['fiscal'])} millones."})
    else:
        insights.append({"icon": "trending-up", "text": f"El {money['fiscal'].label.lower()} asciende a USD {millions(totals['fiscal'])} millones y el "
                                                        f"presupuesto acumulado 2023–{year} alcanza USD {millions(totals['government'])} millones."})
    if parish and parish["top"]:
        first = parish["top"][0]
        where = f"{first['parish']}, en {first['canton']}," if first["parish"] != first["canton"] else f"{first['parish']}"
        insights.append({"icon": "map", "text": f"La cobertura llega a {number(parish['count'])} parroquias; {where} registra el mayor "
                                                f"número de {people_lower} ({number(first['people'])})."})
    budget_leader = max(programs, key=lambda r: r["fiscal"] or 0)
    if len(programs) > 1 and totals["fiscal"]:
        insights.append({"icon": "banknote", "text": f"{budget_leader['label']} registra el "
                                                     f"{number(budget_leader['fiscal'] / totals['fiscal'] * 100, 1)} % del {money['fiscal'].label.lower()}, "
                                                     f"con USD {millions(budget_leader['fiscal'])} millones."})

    if territory_label is None:
        names = [p["name"] for p in provinces if p["selected"]]
        territory_label = names[0] if len(names) == 1 else (f"{len(names)} provincias" if names else "Nacional")
    generated_at, generated_label = stamp()
    map_values = parish["values"] if parish else {p["code"]: p["people"] for p in provinces}
    return {
        "kind": "territorial",
        "title": str(title or module.label)[:100],
        "module_id": module.id, "module_label": module.label, "module_description": module.description,
        "period_id": period_id, "period_label": period_label, "year": year,
        "territory_label": territory_label, "programs_label": programs_label or f"Todos los {module.items}",
        "labels": labels, "kpis": kpis, "totals": totals, "national": nation,
        "executed_available": executed,
        "programs": programs, "provinces": provinces, "province_count": province_count, "detail": detail,
        "selected_codes": sorted(selected), "map_values": map_values,
        "map_layer": "parroquia" if parish else "provincia", "map_focus": parish["focus"] if parish else [],
        "parish": parish,
        "insights": insights, "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}",
        "generated_at": generated_at, "generated_label": generated_label,
    }
