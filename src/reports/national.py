"""Report snapshots of the national areas: the institutional budget and labour management.

Like the territorial snapshot, each one is built from the rows on screen and holds everything the one-page summary,
the slides and the data workbook draw: key figures, ranked rows, map values and findings for an authority.
"""
from __future__ import annotations

import pandas as pd

from src import institutional
from src.indicators import AREAS, BUDGET_DEFINITIONS, LABOUR_DEFINITIONS
from .context import INSTITUTION, millions, number, stamp


def _pct(value) -> str:
    return "—" if value is None or pd.isna(value) else f"{number(value, 1)} %"


def _rows(frame: pd.DataFrame, label: str = "nombre", short: str | None = None) -> list[dict]:
    out = []
    for row in frame.itertuples():
        record = row._asdict()
        out.append({"name": str(record[label]), "short": str(record[short]) if short else str(record[label]),
                    "coded": float(record["presupuesto_codificado"] or 0), "accrued": float(record["presupuesto_ejecutado"] or 0),
                    "certified": None if pd.isna(record["presupuesto_certificado"]) else float(record["presupuesto_certificado"]),
                    "execution": None if pd.isna(record["porcentaje_ejecucion"]) else float(record["porcentaje_ejecucion"]),
                    "balance": float(record["saldo"] or 0), "share": float(record["participacion"] or 0),
                    "zone_code": record.get("zona_codigo") if isinstance(record.get("zona_codigo"), str) else None})
    return out


def budget_context(filtered: pd.DataFrame, *, national: pd.DataFrame, scope: pd.DataFrame, title: str, period: dict,
                   territory_label: str, programs_label: str, selected_zones=()) -> dict:
    """Snapshot of the institutional budget on screen (zones and programs chosen)."""
    if filtered.empty:
        raise ValueError("No hay presupuesto en la selección. Ajuste los filtros antes de generar el documento.")
    stats = institutional.summarize(filtered)
    reference = institutional.summarize(scope)
    active = len(filtered) != len(scope)
    programs = _rows(institutional.by(filtered, "programa"), "nombre", "programa_corto")
    zones = _rows(institutional.by(national, "zona"))
    zone_names = {z: n for z, n in zip(scope.zona_orden, scope.zona_nombre)}
    chosen = {zone_names[z] for z in selected_zones if z in zone_names}
    for row in zones:
        row["selected"] = row["name"] in chosen
    units = _rows(institutional.by(filtered, "unidad"))
    unit_zone = filtered.drop_duplicates("unidad_nombre").set_index("unidad_nombre").zona_nombre.to_dict()
    for row in units:
        row["zone"] = unit_zone.get(row["name"], "")
    groups = _rows(institutional.by(filtered, "grupo"))
    kinds = _rows(institutional.by(filtered, "tipo"))
    sources = _rows(institutional.by(filtered, "fuente"))
    keys = ["zona_orden", "zona_nombre", "unidad_nombre", "programa_nombre", "grupo_nombre", "fuente_nombre", "tipo_nombre"]
    detail_frame = filtered.groupby(keys, as_index=False, dropna=False)[institutional.MONEY].sum(min_count=1)
    detail_frame = detail_frame.sort_values(["zona_orden", "unidad_nombre", "programa_nombre", "grupo_nombre"])
    detail = [{"zone": r.zona_nombre, "unit": r.unidad_nombre, "program": r.programa_nombre, "group": r.grupo_nombre,
               "source": r.fuente_nombre, "kind": r.tipo_nombre, "coded": float(r.presupuesto_codificado or 0),
               "accrued": float(r.presupuesto_ejecutado or 0),
               "certified": None if pd.isna(r.presupuesto_certificado) else float(r.presupuesto_certificado),
               "execution": float(r.presupuesto_ejecutado) / float(r.presupuesto_codificado) * 100 if r.presupuesto_codificado else None,
               "balance": float((r.presupuesto_codificado or 0) - (r.presupuesto_ejecutado or 0))}
              for r in detail_frame.itertuples()]

    def share(key):
        return stats[key] / reference[key] * 100 if active and reference.get(key) else None

    kpis = [
        {"key": "coded", "label": "Presupuesto codificado", "value": stats["codificado"], "kind": "money", "icon": "wallet",
         "share": share("codificado")},
        {"key": "accrued", "label": "Presupuesto devengado", "value": stats["devengado"], "kind": "money", "icon": "banknote",
         "share": share("devengado")},
        {"key": "execution", "label": "Ejecución presupuestaria", "value": stats["ejecucion"], "kind": "rate", "icon": "target",
         "share": None, "note": "Devengado sobre codificado"},
        {"key": "balance", "label": "Saldo por devengar", "value": stats["saldo"], "kind": "money", "icon": "hourglass",
         "share": None, "note": f"{_pct(100 - stats['ejecucion'] if stats['ejecucion'] is not None else None)} del codificado"},
    ]
    insights = [{"icon": "target", "text": f"La ejecución presupuestaria alcanza el {_pct(stats['ejecucion'])}: USD "
                                           f"{millions(stats['devengado'])} millones devengados de USD {millions(stats['codificado'])} "
                                           f"millones codificados."}]
    if programs:
        leader = programs[0]
        insights.append({"icon": "award", "text": f"El programa {leader['short']} concentra el {_pct(leader['share'])} del presupuesto "
                                                  f"codificado y ejecuta el {_pct(leader['execution'])}."})
        relevant = [p for p in programs if p["share"] >= 2 and p["execution"] is not None]
        if len(relevant) > 1:
            low = min(relevant, key=lambda p: p["execution"])
            if low is not leader:
                insights.append({"icon": "trending-up", "text": f"El programa {low['short']} registra la menor ejecución entre los de "
                                                                f"mayor peso: {_pct(low['execution'])} de USD {millions(low['coded'])} millones."})
    current = next((k for k in kinds if k["name"] == "Gasto corriente"), None)
    investment = next((k for k in kinds if k["name"] == "Gasto de inversión"), None)
    if current and investment and investment["coded"]:
        insights.append({"icon": "layers", "text": f"El gasto de inversión ejecuta el {_pct(investment['execution'])} de USD "
                                                   f"{millions(investment['coded'])} millones, frente al {_pct(current['execution'])} "
                                                   f"del gasto corriente."})
    territorial = [z for z in zones if z["zone_code"] and z["execution"] is not None and z["coded"]]
    if len(territorial) > 1:
        high, low = max(territorial, key=lambda z: z["execution"]), min(territorial, key=lambda z: z["execution"])
        insights.append({"icon": "map", "text": f"Entre las coordinaciones zonales, la {high['name']} alcanza la mayor ejecución "
                                                f"({_pct(high['execution'])}) y la {low['name']} la menor ({_pct(low['execution'])})."})
    generated_at, generated_label = stamp()
    zone_values = {z["zone_code"]: z["execution"] for z in zones if z["zone_code"] and z["execution"] is not None}
    return {
        "kind": "presupuesto", "module_id": "presupuesto", "module_label": AREAS["presupuesto"]["label"],
        "title": str(title or AREAS["presupuesto"]["label"])[:100],
        "period_id": period["id"], "period_label": period["label"], "year": period["year"],
        "territory_label": territory_label, "programs_label": programs_label,
        "stats": stats, "kpis": kpis, "programs": programs, "zones": zones, "units": units, "groups": groups,
        "kinds": kinds, "sources": sources, "detail": detail, "insights": insights,
        "map_values": zone_values, "selected_zones": sorted(z for z in selected_zones if z != "Z0"),
        "definitions": BUDGET_DEFINITIONS, "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}",
        "generated_at": generated_at, "generated_label": generated_label,
    }


def labour_context(info: dict, *, title: str, period: dict) -> dict:
    """Snapshot of the labour figures of the latest consultation."""
    if not info:
        raise ValueError("La información laboral no está disponible.")
    from src.gestion_laboral import month_span
    span = month_span(info)
    year = info["year"]
    kpis = [
        {"key": "stock", "label": "Contratos vigentes", "value": info["stock"], "kind": "count", "icon": "briefcase", "share": None,
         "note": f"Al {info['stock_label']}"},
        {"key": "cohorts", "label": f"Contratos registrados en {year}", "value": info["cohorts"], "kind": "count", "icon": "file-check",
         "share": None, "note": f"{_pct(info['cohorts_share'])} de los vigentes"},
        {"key": "retirees", "label": "Personas jubiladas compensadas", "value": info["retirees"], "kind": "count", "icon": "user-check",
         "share": None, "note": "Exservidores y extrabajadores"},
        {"key": "compensation", "label": "Compensaciones jubilares", "value": info["compensation"], "kind": "money", "icon": "coins",
         "share": None, "lower_bound": info["compensation_lower_bound"], "decimals": 0, "note": f"Pagadas en {info['retirees_year']}"},
    ]
    months = [{"label": m["label"], "short": m["short"], "value": m["value"],
               "share": m["value"] / info["cohorts"] * 100 if info["cohorts"] else None} for m in info["months"]]
    running = 0.0
    for row in months:
        running += row["value"]
        row["cumulative"] = running
    amount = f"{'más de ' if info['compensation_lower_bound'] else ''}USD {millions(info['compensation'], 0)} millones"
    insights = [
        {"icon": "briefcase", "text": f"El país registra {number(info['stock'])} contratos de trabajo vigentes al {info['stock_label']}."},
        {"icon": "file-check", "text": f"De {span} de {year} se registraron {number(info['cohorts'])} contratos que siguen vigentes: el "
                                       f"{_pct(info['cohorts_share'])} de los contratos vigentes del país."},
        {"icon": "user-check", "text": f"En {info['retirees_year']} se compensó a {number(info['retirees'])} exservidores y extrabajadores "
                                       f"públicos jubilados, con {amount}."},
        {"icon": "trending-up", "text": f"En promedio se registraron {number(info['average'])} contratos por mes que siguen vigentes."},
    ]
    sources = [
        ("Contratos vigentes y registrados por mes", "Sistema Único de Trabajo (SUT), Ministerio del Trabajo",
         next((u for i, u in info["sources"] if i == "sut_contratos"), "")),
        ("Personas jubiladas y compensaciones jubilares", "Balance oficial publicado por el Ministerio del Trabajo"
         + (f" el {info['published_label']}" if info.get("published_label") else ""),
         next((u for i, u in info["sources"] if i == "mdt_noticia_jubilados"), "")),
    ]
    generated_at, generated_label = stamp()
    return {
        "kind": "laboral", "module_id": "laboral", "module_label": AREAS["laboral"]["label"],
        "title": str(title or AREAS["laboral"]["label"])[:100],
        "period_id": period["id"], "period_label": period["label"], "year": year, "span": span,
        "territory_label": "Nacional", "programs_label": f"Consulta del {info['consulted_label']}",
        "info": {k: v for k, v in info.items() if k not in ("sources",)}, "kpis": kpis, "months": months,
        "insights": insights, "sources": sources, "definitions": LABOUR_DEFINITIONS,
        "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}",
        "generated_at": generated_at, "generated_label": generated_label,
    }
