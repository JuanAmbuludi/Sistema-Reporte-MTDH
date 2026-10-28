"""Period bulletins: January to the latest month of the year, and the government period (from November 2023).

Both follow the executive summaries: a band with the period, two rows of key figures, the coverage of the information of
each section (from when to when it exists) and then, section by section, monthly or yearly charts with their tables.
Every figure is read from the bases of the dashboard; a section without data for part of the period says so instead of
filling it.
"""
from __future__ import annotations

import logging
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdf_canvas

from src import theme
from src.data import MONTHS
from .context import INSTITUTION, PRODUCT, millions, number, stamp

LOG = logging.getLogger(__name__)
GOVERNMENT_START = "2023-11"
MODES = {"anual": "Informe de gestión del año", "gobierno": "Informe de gestión del periodo de gobierno"}


def _month(period_id: str) -> str:
    return f"{MONTHS[int(period_id[5:7]) - 1]} de {period_id[:4]}"


def _short(period_id: str, year: bool = False) -> str:
    text = MONTHS[int(period_id[5:7]) - 1][:3].capitalize()
    return f"{text} {period_id[2:4]}" if year else text


def _within(frame: pd.DataFrame, start: str, end: str, field: str = "periodo_id") -> pd.DataFrame:
    ids = frame[field].astype(str)
    return frame.loc[ids.str.len().eq(7) & ids.ge(start) & ids.le(end)]


def gather(bases: dict, mode: str) -> dict:
    """Figures, series, tables and coverage of every section for the period of the bulletin."""
    data = bases["data"]
    monthly_ids = sorted(p for p in data.periodo_id.astype(str).unique() if len(p) == 7)
    end = monthly_ids[-1]
    start = f"{end[:4]}-01" if mode == "anual" else GOVERNMENT_START
    yearly = mode == "gobierno"
    out = {"mode": mode, "start": start, "end": end, "kpis": [], "coverage": [], "sections": [], "insights": []}
    span = f"enero a {MONTHS[int(end[5:]) - 1]} de {end[:4]}" if mode == "anual" else f"noviembre de 2023 a {_month(end)}"
    out["span"] = span

    # -------------------------------------------------------------- transfers and services
    last = data.loc[data.periodo_id.eq(end)]
    people = last.groupby("seccion").usuarios.sum()
    accrued = last.groupby("seccion").presupuesto_ejecutado.sum()
    government = last.groupby("seccion").monto_gobierno.sum()
    series = {}
    for section in ("bonos_pensiones", "proteccion_integral"):
        rows = data.loc[data.seccion.eq(section)]
        points = rows.groupby("periodo_id").usuarios.sum()
        keep = [p for p in points.index if (len(p) == 7 and start <= p <= end) or (yearly and len(p) == 4 and p >= start[:4])]
        series[section] = [(p if len(p) == 4 else (_short(p, yearly)), float(points[p])) for p in sorted(keep)]
    program_rows = (last.groupby(["seccion", "programa"], as_index=False)[["usuarios", "presupuesto_ejecutado", "monto_gobierno"]].sum()
                    .sort_values(["seccion", "usuarios"], ascending=[True, False]))
    budget = bases.get("program_budget")
    accrued_months = []
    if budget is not None and not budget.empty:
        months = _within(budget, start, end).groupby("periodo_id").devengado_mes.sum()
        accrued_months = [(_short(p, yearly), float(v)) for p, v in months.items()]
    total_people = float(people.sum())
    out["kpis"] += [
        {"label": "Beneficiarios de bonos y pensiones", "value": float(people.get("bonos_pensiones", 0)), "kind": "count",
         "icon": "hand-coins", "note": _month(end).capitalize()},
        {"label": "Usuarios de servicios sociales", "value": float(people.get("proteccion_integral", 0)), "kind": "count",
         "icon": "users", "note": _month(end).capitalize()},
        ({"label": f"Presupuesto devengado {end[:4]}", "value": float(accrued.sum()), "kind": "money", "icon": "banknote",
          "note": "Transferencias y servicios"} if mode == "anual" else
         {"label": f"Presupuesto acumulado 2023–{end[:4]}", "value": float(government.sum()), "kind": "money", "icon": "landmark",
          "note": "Transferencias y servicios"}),
    ]
    first_month = monthly_ids[0]
    out["coverage"].append(("Transferencias y servicios sociales", _month(start) if mode == "anual" else "2024 (referencia anual)", _month(end),
                            "Personas del mes y presupuesto" if mode == "anual" else "Mensual desde " + _month(first_month)))
    out["sections"].append({
        "title": "Transferencias monetarias y servicios sociales", "icon": "hand-coins", "stack": True,
        "subtitle": f"Cobertura de cada mes y presupuesto de {span}",
        "charts": [{"title": "Beneficiarios de bonos y pensiones", "note": "Personas · 2024 y 2025 en referencia anual" if yearly else "Personas por mes",
                    "labels": [l for l, _v in series["bonos_pensiones"]], "values": [v for _l, v in series["bonos_pensiones"]]},
                   {"title": "Usuarios de servicios sociales", "note": "Personas · 2024 y 2025 en referencia anual" if yearly else "Personas por mes",
                    "labels": [l for l, _v in series["proteccion_integral"]], "values": [v for _l, v in series["proteccion_integral"]]}],
        "table": {"title": "Cobertura y presupuesto por bono, pensión y servicio",
                  "note": f"Personas de {_month(end)} · devengado de {end[:4]} en millones de USD",
                  "columns": [("Programa o servicio", "programa", None, "text"), ("Personas", "usuarios", 78, "int"),
                              (f"Devengado {end[:4]}", "presupuesto_ejecutado", 82, "mill"),
                              *([("Acumulado 2023–2026", "monto_gobierno", 92, "mill")] if yearly else [])],
                  "rows": program_rows.loc[program_rows.usuarios.gt(0) | (yearly & program_rows.monto_gobierno.fillna(0).gt(0))]
                  .to_dict("records")},
        "extra": {"title": f"Presupuesto devengado por mes, {end[:4]}", "note": "Millones de USD · transferencias y servicios",
                  "labels": [l for l, _v in accrued_months], "values": [v for _l, v in accrued_months], "money": True} if accrued_months else None,
    })
    out["insights"].append({"icon": "users", "text": f"En {_month(end)}, {number(people.get('bonos_pensiones', 0))} personas reciben bonos "
                                                     f"y pensiones y {number(people.get('proteccion_integral', 0))} son atendidas en servicios sociales."})

    # -------------------------------------------------------------------- credit and brigades
    from src.views.area import PROCESSED
    cdh_path, brigades_path = PROCESSED / "cdh_territorio.parquet", PROCESSED / "brigadas.parquet"
    section = {"title": "Crédito de Desarrollo Humano y Brigadas sociales", "icon": "coins", "subtitle": f"De {span}", "charts": []}
    if cdh_path.exists():
        cdh = pd.read_parquet(cdh_path)
        disbursed = _within(cdh.loc[cdh.fuente.eq("desembolso")], start, end, "periodo")
        by_month = disbursed.groupby("periodo")[["creditos", "monto"]].sum()
        credits, amount = int(by_month.creditos.sum()), float(by_month.monto.sum())
        out["kpis"].append({"label": "Créditos de Desarrollo Humano", "value": credits, "kind": "count", "icon": "coins",
                            "note": f"USD {millions(amount, 1)} M"})
        section["charts"].append({"title": "Créditos de Desarrollo Humano por mes", "note": "Créditos desembolsados",
                                  "labels": [_short(p, yearly) for p in by_month.index], "values": list(by_month.creditos)})
        months = list(by_month.index)
        out["coverage"].append(("Crédito de Desarrollo Humano", _month(months[0]) if months else "—", _month(months[-1]) if months else "—",
                                "Desembolsos y cartera vigente"))
        out["insights"].append({"icon": "coins", "text": f"Se desembolsaron {number(credits)} Créditos de Desarrollo Humano por USD "
                                                         f"{millions(amount, 1)} millones ({_month(months[0])} a {_month(months[-1])})."})
    if brigades_path.exists():
        brig = _within(pd.read_parquet(brigades_path), start, end, "periodo")
        key = brig.periodo.str[:4] if yearly else brig.periodo
        grouped = brig.groupby(key).agg(brigadas=("periodo", "size"), atendida=("atendida", "sum"))
        out["kpis"].append({"label": "Brigadas sociales", "value": int(len(brig)), "kind": "count", "icon": "users",
                            "note": f"{number(brig.atendida.sum())} personas atendidas"})
        section["charts"].append({"title": "Brigadas sociales por " + ("año" if yearly else "mes"), "note": "Brigadas realizadas",
                                  "labels": [p if yearly else _short(p) for p in grouped.index], "values": list(grouped.brigadas)})
        provinces = (brig.groupby("provincia", as_index=False).agg(brigadas=("periodo", "size"), atendida=("atendida", "sum"))
                     .sort_values("atendida", ascending=False).head(10))
        section["table"] = {"title": "Brigadas sociales por provincia", "note": "Diez provincias con más personas atendidas",
                            "columns": [("Provincia", "provincia", None, "text"), ("Brigadas", "brigadas", 70, "int"),
                                        ("Personas atendidas", "atendida", 96, "int")], "rows": provinces.to_dict("records")}
        out["coverage"].append(("Brigadas sociales", _month(brig.periodo.min()) if not brig.empty else "—",
                                _month(brig.periodo.max()) if not brig.empty else "—", "Brigadas realizadas"))
        out["insights"].append({"icon": "users", "text": f"Se realizaron {number(len(brig))} brigadas sociales que atendieron a "
                                                         f"{number(brig.atendida.sum())} personas."})
    out["sections"].append(section)

    # ------------------------------------------------------ contingencies, youth and employment
    section = {"title": "Contingencias, Jóvenes en Acción y Empleo", "icon": "shield", "subtitle": f"De {span}", "charts": []}
    contingencies = bases.get("contingencies")
    if contingencies is not None and not contingencies.empty:
        rows = _within(contingencies, start, end)
        key = rows.periodo_id.str[:4] if yearly else rows.periodo_id
        amounts = rows.groupby(key).monto.sum()
        out["kpis"].append({"label": "Monto en contingencias y compensaciones", "value": float(rows.monto.sum()), "kind": "money",
                            "icon": "shield", "note": "Bonos y compensaciones"})
        section["charts"].append({"title": "Contingencias y compensaciones por " + ("año" if yearly else "mes"), "note": "Millones de USD",
                                  "labels": [p if yearly else _short(p) for p in amounts.index], "values": list(amounts), "money": True})
        programs = (rows.groupby("programa", as_index=False).agg(personas=("personas", "sum"), monto=("monto", "sum"))
                    .sort_values("monto", ascending=False))
        section["table"] = {"title": "Contingencias y compensaciones por programa", "note": "Personas-mes con bono y monto (USD M)",
                            "columns": [("Programa", "programa", None, "text"), ("Personas-mes", "personas", 84, "int"),
                                        ("Monto (USD M)", "monto", 84, "mill")], "rows": programs.to_dict("records")}
        out["coverage"].append(("Contingencias y compensaciones", _month(rows.periodo_id.min()), _month(rows.periodo_id.max()),
                                "Habilitados o acreditados"))
    try:
        from src import jovenes
        payments = _within(jovenes.payments(), start, end)
        if not payments.empty:
            key = payments.periodo_id.str[:4] if yearly else payments.periodo_id
            transfers = payments.groupby(key).transferencias.sum()
            out["kpis"].append({"label": "Transferencias de Jóvenes en Acción", "value": float(payments.transferencias.sum()), "kind": "count",
                                "icon": "graduation", "note": f"USD {millions(payments.monto.sum(), 1)} M"})
            section["charts"].append({"title": "Jóvenes en Acción: transferencias por " + ("año" if yearly else "mes"), "note": "Transferencias acreditadas",
                                      "labels": [p if yearly else _short(p) for p in transfers.index], "values": list(transfers)})
            out["coverage"].append(("Jóvenes en Acción", _month(payments.periodo_id.min()), _month(payments.periodo_id.max()),
                                    "Pagos acreditados por fase"))
    except Exception:  # noqa: BLE001 - a section without its base never stops the bulletin
        LOG.exception("Jóvenes en Acción sin datos para el boletín")
    try:
        from src.views.laboral import LabourView
        labour = LabourView(bases["labour"])
        labour.select(labour.catalog()[0])
        if labour.prepare():
            cards = labour.kpi_cards()
            section["note"] = (f"Empleo al corte {labour.cut['contracts_label']}: {number(cards[0]['value'])} contratos vigentes en "
                               f"{number(cards[1]['value'])} empresas. El registro de contratos es un saldo al día de la consulta.")
            out["coverage"].append(("Empleo", "Saldo al corte", labour.cut["contracts_label"].split(",")[0], "Contratos vigentes al corte"))
    except Exception:  # noqa: BLE001
        LOG.exception("Empleo sin datos para el boletín")
    out["sections"].append(section)

    # --------------------------------------------------------------------------------- budget
    section = {"title": "Presupuesto", "icon": "landmark", "subtitle": "Social y fiscal del año; acumulado de gobierno", "charts": []}
    groups = bases.get("social_groups")
    if groups is not None and not groups.empty:
        year_rows = _within(groups, f"{end[:4]}-01", end)
        months = year_rows.groupby("periodo_id")[["devengado_mes", "devengado_acumulado"]].sum()
        approved = float(groups.loc[groups.periodo_id.eq(end), "presupuesto_aprobado"].sum())
        executed = float(months.devengado_acumulado.iloc[-1]) if not months.empty else 0.0
        section["charts"].append({"title": f"Presupuesto social devengado por mes, {end[:4]}", "note": "Millones de USD",
                                  "labels": [_short(p) for p in months.index], "values": list(months.devengado_mes), "money": True})
        out["kpis"].append({"label": f"Ejecución del presupuesto social {end[:4]}", "value": executed / approved * 100 if approved else None,
                            "kind": "rate", "decimals": 1, "icon": "target", "note": f"USD {millions(executed, 1)} M devengados"})
        section["note_budget"] = (f"Presupuesto social {end[:4]}: USD {millions(executed, 1)} millones devengados de USD "
                                  f"{millions(approved, 1)} millones aprobados ({number(executed / approved * 100 if approved else 0, 1)} %).")
        out["coverage"].append(("Presupuesto social", _month(months.index.min()) if not months.empty else "—", _month(end),
                                "Grupos 58, 57 y 78"))
    gov = bases.get("government_budget")
    if gov is not None and not gov.empty:
        scope = gov.groupby("ambito", as_index=False)[["anterior", "fiscal", "acumulado"]].sum().sort_values("acumulado", ascending=False)
        section["table"] = {"title": "Presupuesto acumulado de gobierno", "note": "Millones de USD",
                            "columns": [("Ámbito", "ambito", None, "text"), ("2023–2025", "anterior", 80, "mill"),
                                        (end[:4], "fiscal", 70, "mill"), ("Acumulado", "acumulado", 80, "mill")],
                            "rows": scope.to_dict("records")}
        out["coverage"].append(("Presupuesto acumulado de gobierno", "2023", _month(end), "2023–2025 más el año"))
    out["sections"].append(section)
    out["coverage"].append(("Plan ENOS", "28 de septiembre de 2026", "Último reporte", "En su propio informe"))
    return out


def build(bases: dict, mode: str, title: str = "") -> dict:
    figures = gather(bases, mode)
    generated_at, generated_label = stamp()
    label = MODES[mode]
    return {"kind": "periodo", "title": (title or label)[:100], "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}",
            "generated_at": generated_at, "generated_label": generated_label,
            "period_label": figures["span"][:1].upper() + figures["span"][1:], "territory_label": "Nacional",
            "programs_label": "Todas las secciones", "module_label": label, "update": {}, "kpis": figures["kpis"], "figures": figures,
            "share_word": ""}


# ---------------------------------------------------------------------------------------------- drawing
def generate(ctx: dict) -> bytes:
    from .pdf import BOTTOM, H, M, W, _band, _findings, _footer, _heading, _kpis, _slim_band, _table
    from .pdf_areas import _columns
    figures = ctx["figures"]
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4_SIZE, pageCompression=1)
    c.setTitle(ctx["title"])
    c.setAuthor(ctx["institution"])
    c.setSubject(ctx["period_label"])
    c.setCreator(PRODUCT)
    full = W - 2 * M
    half = (full - 22) / 2
    sections = figures["sections"]
    total = 1 + len(sections)
    page = 1

    def blank():
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)

    def columns(chart, x, top, width, height=128):
        _heading(c, chart["title"], x, top, width, chart.get("note", ""))
        values = [v or 0 for v in chart["values"]]
        if not values:
            return
        money = chart.get("money", False)
        text = ((lambda v: number(v / 1e6, 1)) if money else (lambda v: f"{number(v / 1000, 0)} mil" if v >= 10000 else number(v)))
        _columns(c, chart["labels"], values, x, top - 22, width, height, highlight=len(values) - 1,
                 label_size=6.4 if len(values) > 9 else 7.2, value_text=text)

    def table(spec, x, top, width):
        _heading(c, spec["title"], x, top, width, spec.get("note", ""))
        return _table(c, x, top - 13, width, spec["columns"], spec["rows"], row_h=13.6, header_h=18)

    # Page 1: the period, its key figures, the coverage of each section and the findings.
    blank()
    y = _band(c, ctx, H, None, kind_label=ctx["module_label"]) - 18
    y = _kpis(c, {**ctx, "kpis": figures["kpis"][:4]}, y) - 12
    y = _kpis(c, {**ctx, "kpis": figures["kpis"][4:8]}, y) - 26
    _heading(c, "Cobertura de la información por sección", M, y, full, "Desde y hasta cuándo existe información en cada base")
    rows = [{"name": s, "from": a, "to": b, "note": n} for s, a, b, n in figures["coverage"]]
    y = _table(c, M, y - 13, full, [("Sección", "name", 150, "text"), ("Desde", "from", 118, "text"), ("Hasta", "to", 96, "text"),
                                    ("Alcance", "note", None, "text")], rows, row_h=14.2, header_h=18) - 24
    if y > BOTTOM + 120:
        _heading(c, "Aspectos destacados", M, y, full)
        _findings(c, figures["insights"], M, y - 18, full, limit=4)
    # One page per group of sections: two charts side by side, a third chart or a table, and its note.
    for section in sections:
        _footer(c, ctx, page, total)
        c.showPage()
        page += 1
        blank()
        y = _slim_band(c, ctx, section["title"], section["subtitle"]) - 26
        charts = [ch for ch in section["charts"] if ch]
        if section.get("stack"):
            # Long monthly series of people read better across the page, one under the other.
            for chart in charts:
                columns(chart, M, y, full, 92)
                y -= 22 + 92 + 26
        else:
            for index in range(0, len(charts), 2):
                pair = charts[index:index + 2]
                for k, chart in enumerate(pair):
                    columns(chart, M + k * (half + 22), y, half if len(pair) == 2 else full)
                y -= 22 + 128 + 30
        if section.get("extra"):
            columns(section["extra"], M, y, full, 92)
            y -= 22 + 92 + 26
        if section.get("table"):
            y = table(section["table"], M, y, full) - 22
        for key in ("note_budget", "note"):
            if section.get(key) and y > BOTTOM + 40:
                _findings(c, [{"icon": "info", "text": section[key]}], M, y, full, limit=1)
                y -= 48
    _footer(c, ctx, page, total)
    c.showPage()
    c.save()
    return out.getvalue()


from reportlab.lib.pagesizes import A4 as A4_SIZE  # noqa: E402


# ------------------------------------------------------------------------------------------- bulletin figures
def extras(bases: dict, figures: dict) -> dict:
    """What the bulletin draws beyond the key figures: rings, mosaics, months, El Niño, brigades, credit and budget."""
    from src.views.area import PROCESSED
    start, end, mode = figures["start"], figures["end"], figures["mode"]
    yearly = mode == "gobierno"
    data = bases["data"]
    last = data.loc[data.periodo_id.eq(end)]
    out = {"end_label": _month(end), "end_month": MONTHS[int(end[5:]) - 1], "highlights": list(figures["insights"]), "timeline": []}
    programs = last.groupby(["seccion", "programa"], as_index=False)[["usuarios", "presupuesto_ejecutado"]].sum()
    bonos = programs.loc[programs.seccion.eq("bonos_pensiones") & programs.usuarios.gt(0)].sort_values("usuarios", ascending=False)
    total = bonos.usuarios.sum()
    out["bonos"] = [{"label": r.programa, "people": float(r.usuarios), "share": r.usuarios / total * 100 if total else 0} for r in bonos.itertuples()]
    services = programs.loc[programs.seccion.eq("proteccion_integral") & programs.usuarios.gt(0)].sort_values("usuarios", ascending=False)
    out["servicios"] = [{"label": r.programa, "people": float(r.usuarios)} for r in services.itertuples()]
    out["accrued_items"] = [(r.programa, float(r.presupuesto_ejecutado or 0)) for r in programs.itertuples() if (r.presupuesto_ejecutado or 0) > 0]
    out["accrued_total"] = sum(v for _l, v in out["accrued_items"])
    out["series"] = {}
    for key, section in (("bonos", "bonos_pensiones"), ("servicios", "proteccion_integral")):
        points = data.loc[data.seccion.eq(section)].groupby("periodo_id").usuarios.sum()
        keep = [p for p in sorted(points.index) if (len(p) == 7 and start <= p <= end) or (yearly and len(p) == 4)]
        out["series"][key] = ([p if len(p) == 4 else _short(p, yearly) for p in keep], [float(points[p]) for p in keep])
    monthly_ids = sorted(p for p in data.periodo_id.astype(str).unique() if len(p) == 7)
    out["timeline"].append(("Transferencias y servicios", "2024-01" if yearly else monthly_ids[0], end))
    # El Niño (Plan ENOS): the latest report of the response.
    try:
        from src.views.riesgos import RiskView
        risk = RiskView()
        risk.select(risk.catalog()[0])
        if risk.prepare():
            r = risk.response
            kits = r.kits.groupby(["provincia_codigo", "provincia"]).kits.sum().sort_values(ascending=False)
            bono = r.articulation.groupby("provincia").personas.sum().sort_values(ascending=False)
            units = int(r.alerts.codigo_ua.dropna().astype(str).str.strip().replace("", None).dropna().nunique())
            out["enos"] = {"units": units, "alerts": int(len(r.alerts)), "kits": int(r.kits_total),
                           "kit_provinces": int(kits.index.get_level_values(0).nunique()), "families": int(r.articulation.personas.sum()),
                           "amount": float(r.articulation.monto.sum()), "closed": int(r.closed_units or 0), "closed_note": r.suspension_short(),
                           "kits_map": {code: float(v) for (code, _n), v in kits.items()},
                           "alerts_rank": [(n, float(v)) for n, v in r.alerts.groupby("provincia").size().sort_values(ascending=False).head(6).items()],
                           "closed_rank": [(part.split(" ", 1)[1].replace("en otros servicios", "Otros servicios"), float(part.split(" ", 1)[0]))
                                           for part in r.suspension_short().split(" · ") if part.split(" ", 1)[0].isdigit()],
                           "kits_rank": [(n, float(v)) for (_c, n), v in kits.head(6).items()],
                           "bono_rank": [(n, float(v)) for n, v in bono.head(5).items()],
                           "cut": r.cut_text("alertas"),
                           "findings": [{"icon": "life-buoy", "text": f"{number(r.kits_total)} kits llegaron a {kits.index.get_level_values(0).nunique()} "
                                                                      f"provincias; Guayas y Esmeraldas reciben la mayor parte."},
                                        {"icon": "shield", "text": f"{number(r.closed_units or 0)} unidades de atención con atención suspendida "
                                                                   f"({r.suspension_short()})."},
                                        {"icon": "hand-coins", "text": f"{number(r.articulation.personas.sum())} familias habilitadas al pago del "
                                                                       f"bono de contingencia, por USD {number(r.articulation.monto.sum(), 2)}."}]}
            out["timeline"].append(("Plan ENOS (El Niño)", "2026-09", end))
            out["highlights"].insert(1, {"icon": "life-buoy", "text": f"Fenómeno El Niño: {number(r.kits_total)} kits entregados, "
                                                                      f"{number(r.articulation.personas.sum())} familias con bono de contingencia "
                                                                      f"y {units} unidades de atención con alertas."})
    except Exception:  # noqa: BLE001 - the bulletin keeps the other stories
        LOG.exception("ENOS sin datos para el boletín")
    brigades_path = PROCESSED / "brigadas.parquet"
    if brigades_path.exists():
        brig = _within(pd.read_parquet(brigades_path), start, end, "periodo")
        if not brig.empty:
            key = brig.periodo.str[:4] if yearly else brig.periodo
            months = brig.groupby(key).atendida.sum()
            out["brigadas"] = {"count": int(len(brig)), "attended": int(brig.atendida.sum()), "reached": int(brig.alcanzada.sum()),
                               "rate": brig.atendida.sum() / brig.alcanzada.sum() * 100 if brig.alcanzada.sum() else 0,
                               "average": brig.atendida.sum() / len(brig), "provinces": int(brig.provincia.nunique()),
                               "months": ([p if yearly else _short(p) for p in months.index], [float(v) for v in months]),
                               "map": brig.groupby("provincia_codigo").size().astype(float).to_dict()}
            out["timeline"].append(("Brigadas sociales", brig.periodo.min(), brig.periodo.max()))
    cdh_path = PROCESSED / "cdh_territorio.parquet"
    if cdh_path.exists():
        cdh = pd.read_parquet(cdh_path)
        disbursed = _within(cdh.loc[cdh.fuente.eq("desembolso")], start, end, "periodo")
        profile_path = PROCESSED / "cdh_perfil.parquet"
        profile = pd.read_parquet(profile_path) if profile_path.exists() else pd.DataFrame()
        if not disbursed.empty:
            months = disbursed.groupby("periodo").creditos.sum()
            prof = _within(profile.loc[profile.fuente.eq("desembolso")], start, end, "periodo") if not profile.empty else profile
            women = prof.loc[prof.sexo.eq("Mujeres"), "creditos"].sum() / prof.creditos.sum() * 100 if not prof.empty else 0
            portfolio = cdh.loc[cdh.fuente.eq("vigente")]
            bonus = disbursed.groupby("bono").creditos.sum().sort_values(ascending=False)
            out["cdh"] = {"credits": int(disbursed.creditos.sum()), "amount": float(disbursed.monto.sum()),
                          "average": disbursed.monto.sum() / disbursed.creditos.sum(), "portfolio": int(portfolio.creditos.sum()),
                          "portfolio_amount": float(portfolio.monto.sum()), "women": float(women),
                          "months": ([_short(p, yearly) for p in months.index], [float(v) for v in months]),
                          "bonus": [(b, float(v)) for b, v in bonus.items()]}
            out["timeline"].append(("Crédito de Desarrollo Humano", months.index.min(), months.index.max()))
    contingencies = bases.get("contingencies")
    if contingencies is not None and not contingencies.empty:
        rows = _within(contingencies, start, end)
        items = rows.groupby("programa").monto.sum().sort_values(ascending=False)
        out["contingencias"] = {"total": float(rows.monto.sum()), "items": [(p, float(v)) for p, v in items.items() if v > 0]}
        out["timeline"].append(("Contingencias y compensaciones", rows.periodo_id.min(), rows.periodo_id.max()))
    try:
        from src import jovenes
        payments = _within(jovenes.payments(), start, end)
        if not payments.empty:
            key = payments.periodo_id.str[:4] if yearly else payments.periodo_id
            months = payments.groupby(key).transferencias.sum()
            out["jovenes"] = {"transfers": float(payments.transferencias.sum()), "amount": float(payments.monto.sum()),
                              "months": ([p if yearly else _short(p) for p in months.index], [float(v) for v in months])}
            out["timeline"].append(("Jóvenes en Acción", payments.periodo_id.min(), payments.periodo_id.max()))
    except Exception:  # noqa: BLE001
        LOG.exception("Jóvenes en Acción sin datos para el boletín")
    budget = {"gauges": []}
    pace = int(end[5:]) / 12 * 100
    groups = bases.get("social_groups")
    if groups is not None and not groups.empty:
        year_rows = _within(groups, f"{end[:4]}-01", end)
        approved = float(groups.loc[groups.periodo_id.eq(end), "presupuesto_aprobado"].sum())
        accrued = float(year_rows.groupby("periodo_id").devengado_acumulado.sum().iloc[-1]) if not year_rows.empty else 0.0
        budget["gauges"].append({"value": accrued / approved * 100 if approved else 0, "pace": pace, "label": "Presupuesto social",
                                 "sub": f"USD {millions(accrued, 1)} M de USD {millions(approved, 1)} M"})
        out["timeline"].append(("Presupuesto social", f"{end[:4]}-01", end))
    fiscal = bases.get("budget")
    if fiscal is not None and not fiscal.empty:
        coded, accrued = float(fiscal.codificado.sum()), float(fiscal.devengado.sum())
        budget["gauges"].append({"value": accrued / coded * 100 if coded else 0, "pace": pace, "label": "Presupuesto fiscal (SGDE)",
                                 "sub": f"USD {millions(accrued, 1)} M de USD {millions(coded, 1)} M"})
        budget["note"] = (f"Presupuesto fiscal SGDE al 30 de septiembre: USD {millions(accrued, 1)} millones devengados de USD "
                          f"{millions(coded, 1)} millones codificados.")
    gov = bases.get("government_budget")
    if gov is not None and not gov.empty:
        budget["government"] = {"total": float(gov.acumulado.sum()), "previous": float(gov.anterior.sum()), "current": float(gov.fiscal.sum())}
    out["presupuesto"] = budget
    try:
        from src.views.laboral import LabourView
        labour = LabourView(bases["labour"])
        labour.select(labour.catalog()[0])
        if labour.prepare():
            cards = labour.kpi_cards()[:4]
            out["empleo_cut"] = f"Contratos vigentes al {labour.cut['contracts_label'].split(',')[0]}; jubilación del año"
            out["empleo_cards"] = [(f"USD {millions(k['value'] * 1e6, 1)} M" if k.get("prefix") == "USD" else number(k["value"]), k["label"],
                                    k.get("note") or "") for k in cards]
    except Exception:  # noqa: BLE001
        LOG.exception("Empleo sin datos para el boletín")
    out["highlights"] = out["highlights"][:5]
    return out


def _bulletin(ctx: dict) -> bytes:
    from .boletin import generate as draw
    return draw(ctx)


_build_plain = build


def build(bases: dict, mode: str, title: str = "") -> dict:  # noqa: F811 - the bulletin adds its drawings to the figures
    ctx = _build_plain(bases, mode, title)
    ctx["extras"] = extras(bases, ctx["figures"])
    return ctx


generate = _bulletin  # noqa: F811


# The period reports follow the structure of the monthly executive report (src/reports/gestion.py).
from . import gestion as _gestion  # noqa: E402

MODES = {"anual": _gestion.TITLES["anual"], "gobierno": _gestion.TITLES["gobierno"]}  # noqa: F811
build = _gestion.build  # noqa: F811
generate = _gestion.generate  # noqa: F811
