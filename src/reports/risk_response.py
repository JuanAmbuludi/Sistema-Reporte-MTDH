"""Complete bulletin of the visible response dashboard; exposure stays internal."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

import pandas as pd

from src import enos, theme, ui
from .areas import _base, kpis_from_cards
from .context import number


def build_context(view, *, title: str) -> dict:
    from .risks import _response
    if not view.response:
        raise ValueError("No hay un corte de respuesta disponible.")
    r = view.response
    ctx = _base(view, "riesgos", title)
    response = _response(r)
    response["by_province"] = enos.summary(r.alerts, "provincia")
    response["by_service"] = enos.summary(r.alerts, "servicio")
    days = pd.date_range(r.since, r.cut, freq="D")
    daily = pd.to_datetime(r.alerts.fecha).value_counts().reindex(days, fill_value=0)
    response["daily"] = [{"date": d.strftime("%d/%m/%Y"), "short": d.strftime("%d/%m"), "daily": int(n), "total": int(c)}
                         for (d, n), c in zip(daily.items(), daily.cumsum())]
    response["count_note"] = r.count_note()
    response["actions"] = [{"name": row["nombre"], "cantons": row["provincia_sub"].removeprefix("Cantones: "),
                            "kits": int(row["kits"]), "managed": int(row["gestionados"]),
                            "managed_amount": float(row["monto_gestionado"]), "articulation": int(row["articulacion"]),
                            "articulation_amount": float(row["monto_articulacion"])}
                           for row in view.action_rows().sort_values("nombre").to_dict("records")]
    kpis = kpis_from_cards(view.kpi_cards())
    for k in kpis:
        if k["kind"] == "money":
            k["display_value"] = f"USD {number(k['value'], 2)}"
            k["exact_money"] = True
    ctx.update(response=response, kpis=kpis, period_label=r.scope_text(), response_only=True,
               pdf_pages=3 + max(1, math.ceil(len(r.alerts) / 7)), selected_codes=list(view.provinces),
               map_values=view.map_values("alertas")[0], kits_map_values=view.map_values("kits")[0],
               scope=view.scope_items(), selection=view.programs_label, geoportal=ui.GEOPORTAL_URL,
               source="Fuente: MTDH · Subsecretaría Territorial · reportes de kits y bono de contingencia",
               sources="Subsecretaría Territorial (análisis de alertas); reporte ministerial de kits; ayuda memoria del bono de contingencia.",
               insights=[{"icon": "shield", "text": r.count_note()},
                         {"icon": "life-buoy", "text": f"{r.kits_total} kits en {response['kit_provinces']} provincias priorizadas; corte {response['kits_cut']}."},
                         {"icon": "hand-coins", "text": f"{response['managed_people']} núcleos con bono gestionado: USD {number(response['managed_amount'], 2)}."}])
    return ctx


def _notes(ctx):
    r = ctx["response"]
    return [("Alertas", r["notes"]["alerts"]), ("Revisión de alertas", r["notes"]["quality"]),
            ("Kits", r["notes"]["kits"]), ("Bono de contingencia", r["notes"]["bonus"]),
            ("Filtros", r["notes"]["filters"])]


def _money_rows(rows):
    return [{**r, "managed_text": number(r["managed_amount"], 2), "articulation_text": number(r["articulation_amount"], 2)} for r in rows]


def _action_totals(rows):
    return {"name": "Total", "cantons": "", **{k: sum(a[k] for a in rows) for k in
            ("kits", "managed", "managed_amount", "articulation", "articulation_amount")}}


def _alert_cells(rows):
    return [{**a, "identity": f"{a['code']}\n{a['date']}",
             "unit_full": f"{a['unit']}\nUA: {a['ua'] or 'Sin código en la fuente'}\n{a['service']}",
             "place_full": f"{a['province']}\n{a['canton']}"} for a in rows]


def _pdf_table(c, top, headers, rows, widths, size=8):
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from .pdf import M, BOTTOM
    normal = ParagraphStyle("cell", fontName="Text", fontSize=size, leading=size * 1.3, textColor=colors.HexColor(theme.TINTA))
    header = ParagraphStyle("head", parent=normal, fontName="Text-Bold", textColor=colors.white)
    def cell(value, style):
        return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)
    data = [[cell(h, header) for h in headers]] + [[cell(v, normal) for v in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.MORADO)),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(theme.LILA_50)]),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    _, height = table.wrap(sum(widths), 2000)
    if top - height < BOTTOM:
        raise ValueError("La tabla del boletín excede el área imprimible.")
    table.drawOn(c, M, top - height)
    return top - height


def _pdf_evolution(c, rows, top, width):
    from .pdf import M, C, _heading
    _heading(c, "Evolución de las alertas", M, top, width, "Registradas en el día (dorado) y acumuladas (morado)")
    left, bottom, height = M + 20, top - 174, 125
    step = (width - 40) / max(1, len(rows) - 1)
    peak = max([r["total"] for r in rows] or [1]) or 1
    c.setFont("Text", 7)
    for value in range(0, peak + 1, max(1, math.ceil(peak / 4))):
        y = bottom + value / peak * height
        c.setStrokeColor(C(theme.LILA_200)); c.setLineWidth(.4); c.line(left, y, left + width - 40, y)
        c.setFillColor(C(theme.PIZARRA)); c.drawRightString(left - 5, y - 2, str(value))
    c.setStrokeColor(C(theme.MORADO)); c.setLineWidth(2)
    for i, row in enumerate(rows):
        x = left + i * step
        if i:
            previous = bottom + rows[i - 1]["total"] / peak * height
            y = bottom + row["total"] / peak * height
            c.line(x - step, previous, x, previous); c.line(x, previous, x, y)
        if row["daily"]:
            c.setFillColor(C(theme.ORO)); c.rect(x - 2.5, bottom, 5, row["daily"] / peak * height, fill=1, stroke=0)
            c.setFillColor(C(theme.MORADO_900)); c.drawCentredString(x, bottom + row["daily"] / peak * height + 5, str(row["daily"]))
        if i % 7 == 0 or i == len(rows) - 1:
            c.setFillColor(C(theme.PIZARRA)); c.drawCentredString(x, bottom - 14, row["short"])
    return bottom - 25


def render_pdf(c, ctx, pages):
    from .charts import emblem_png, map_png
    from .pdf import H, M, W, BOTTOM, _band, _kpis, _heading, _bars, _next_page, _slim_band, _picture
    from .risks import _paragraph
    full = W - 2 * M; half = (full - 20) / 2
    r = ctx["response"]; page = 1
    top = _kpis(c, ctx, _band(c, ctx, H, emblem_png(set(ctx["selected_codes"])), kind_label="Boletín de respuesta") - 14) - 28
    for i, (key, title) in enumerate([("by_province", "Alertas por provincia"), ("by_service", "Alertas por servicio")]):
        x = M + i * (half + 20)
        _heading(c, title, x, top, half)
        rows = r[key]; peak = max([v["value"] for v in rows] or [1]) or 1
        # Labels split before drawing to keep the CNH service name complete.
        for j, row in enumerate(rows):
            y = top - 30 - j * 46
            label = row["name"]
            _paragraph(c, label, x, y + 4, half - 25, size=8.3)
            _bars(c, [{"name": "", "text": str(row["value"]), "fraction": row["value"] / peak}], x, y - 17, half, 30)
    top -= 190
    top = _pdf_evolution(c, r["daily"], top, full)
    _heading(c, "Cómo se cuenta", M, top - 14, full)
    _paragraph(c, r["count_note"], M, top - 32, full, size=9)
    chunks = [r["alerts"][i:i + 7] for i in range(0, len(r["alerts"]), 7)] or [[]]
    for index, chunk in enumerate(chunks, 1):
        _next_page(c, ctx, page, pages); page += 1
        top = _slim_band(c, ctx, "Alertas con código UA", f"Detalle completo · parte {index} de {len(chunks)} · {r['scope']}") - 20
        rows = _alert_cells(chunk)
        top = _pdf_table(c, top, ["Alerta / registro", "Unidad y servicio", "Territorio", "Afectación al servicio", "Estado / prioridad"],
                         [[a["identity"], a["unit_full"], a["place_full"], a["impact"], a["status"] + "\n" + a["priority"]] for a in rows],
                         [88, 140, 65, full - 363, 70], size=8)
        _paragraph(c, r["notes"]["quality"], M, top - 16, full, size=8.2)
    _next_page(c, ctx, page, pages); page += 1
    top = _slim_band(c, ctx, "Acciones del Ministerio", "Kits en provincias priorizadas y bono de contingencia") - 20
    _heading(c, "Acciones del Ministerio en cada provincia", M, top, full)
    actions = _money_rows(r["actions"] + [_action_totals(r["actions"])])
    top = _pdf_table(c, top - 16, ["Provincia / cantones", "Kits", "Bono gestionado (núcleos)", "Monto (USD)", "En articulación (personas)", "Monto (USD)"],
                     [[a["name"] + ("\n" + a["cantons"] if a["cantons"] else ""), number(a["kits"]), number(a["managed"]), a["managed_text"],
                       number(a["articulation"]), a["articulation_text"]] for a in actions], [full - 353, 38, 75, 80, 80, 80], size=7.4)
    _heading(c, "Kits entregados en provincias priorizadas", M, top - 24, full, r["notes"]["kits"])
    top = _pdf_table(c, top - 44, ["Fecha", "Provincia", "Cantón", "Kits"],
                     [[a["date"], a["province"], a["canton"], number(a["kits"])] for a in r["kits"]] + [["Total", "", "", number(r["kits_total"])]],
                     [80, 145, full - 275, 50], size=8)
    _heading(c, "Planificación El Niño 2026–2027", M, top - 24, full, "Proyección nacional del bono · planificación, no ejecución")
    plan = r["plan"]
    _pdf_table(c, top - 44, ["Personas potenciales", "Núcleos familiares potenciales", "Inversión estimada (USD)"],
               [[number(plan["personas"]), number(plan["nucleos"]), number(plan["monto"], 2)]], [full / 3] * 3)
    _next_page(c, ctx, page, pages); page += 1
    top = _slim_band(c, ctx, "Territorio y nota metodológica", r["scope"] + " · " + ctx["territory_label"]) - 18
    for i, (key, title) in enumerate([("map_values", "Alertas con código UA"), ("kits_map_values", "Kits en provincias priorizadas")]):
        x = M + i * (half + 20)
        _heading(c, title, x, top, half)
        pic = map_png(ctx[key], layer="provincia", selected=set(ctx["selected_codes"]), mode="light", label=title, width=4, height=2.8, dpi=180)
        _picture(c, pic, x, top - 18, half, .7)
    top -= half * .7 + 44
    for title, text in _notes(ctx):
        _heading(c, title, M, top, full)
        top = _paragraph(c, text, M, top - 16, full, size=8.1) - 18
    top = _paragraph(c, "Fuentes: " + ctx["sources"], M, top, full, size=7.5) - 12
    _paragraph(c, "Geoportal: " + ctx["geoportal"], M, top, full, size=8)
    c.linkURL(ctx["geoportal"], (M, top - 12, M + full, top), relative=0)
    if top - 15 < BOTTOM:
        raise ValueError("Las notas del boletín exceden el área imprimible.")
    assert page == pages


def render_pptx(prs, ctx):
    from .charts import emblem_png, map_png
    from .pptx import _cover, _header, _footer, _text, _bar_chart, _line_chart, _picture
    from .pptx_areas import _table, _title
    r = ctx["response"]
    chunks = [r["alerts"][i:i + 5] for i in range(0, len(r["alerts"]), 5)] or [[]]
    total = 7 + len(chunks)
    _cover(prs, ctx, emblem_png(set(ctx["selected_codes"])), total, share_word="")
    def slide(title):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        _header(s, title, f"{r['scope']} · {ctx['territory_label']} · {ctx['programs_label']}")
        _footer(s, ctx, len(prs.slides), total)
        s.notes_slide.notes_text_frame.text = ctx["sources"]
        return s
    s = slide("Alertas por provincia y servicio")
    for i, (key, title) in enumerate([("by_province", "Alertas por provincia"), ("by_service", "Alertas por servicio")]):
        x = .55 + i * 6.25; rows = r[key]
        _title(s, title, x, 1.45, 5.8)
        if rows:
            _bar_chart(s, [a["name"] for a in rows], [a["value"] for a in rows], "Alertas", x=x, y=2, w=5.8, h=3.8)
    _text(s, .55, 6.05, 12.2, .65, r["count_note"], size=11)
    s = slide("Evolución de las alertas")
    _line_chart(s, [d["short"] for d in r["daily"]], [("Acumuladas", [d["total"] for d in r["daily"]], theme.MORADO),
                 ("Registradas en el día", [d["daily"] for d in r["daily"]], theme.ORO)], x=.55, y=1.5, w=12.2, h=4.9, legend=True, minimum=0)
    _text(s, .55, 6.45, 12.2, .3, "Fecha de registro de la alerta; seguimiento desde " + r["since"], size=11)
    for i, chunk in enumerate(chunks, 1):
        s = slide(f"Alertas con código UA · {i}/{len(chunks)}")
        _table(s, .55, 1.5, 12.2, [("Alerta / registro", "identity", 1.4, "text"), ("Unidad y servicio", "unit_full", 3, "text"),
               ("Territorio", "place_full", 1.35, "text"), ("Afectación", "impact", None, "text"), ("Estado", "status", 1.2, "text"),
               ("Prioridad", "priority", .8, "text")], _alert_cells(chunk), row_h=.87, header_h=.5, size=9)
        _text(s, .55, 6.43, 12.2, .4, r["notes"]["quality"], size=9)
    s = slide("Acciones del Ministerio en cada provincia")
    _table(s, .55, 1.5, 12.2, [("Provincia / cantones", "place", None, "text"), ("Kits", "kits", .75, "int"),
           ("Bono gestionado (núcleos)", "managed", 1.5, "int"), ("Monto (USD)", "managed_text", 1.6, "text"),
           ("En articulación (personas)", "articulation", 1.7, "int"), ("Monto (USD)", "articulation_text", 1.7, "text")],
           [{**a, "place": a["name"] + "\n" + a["cantons"]} for a in _money_rows(r["actions"] + [_action_totals(r["actions"])])], row_h=.5, size=10)
    _text(s, .55, 6.15, 12.2, .65, r["notes"]["bonus"], size=10)
    s = slide("Kits y planificación del bono")
    _title(s, "Kits en provincias priorizadas", .55, 1.4, 7)
    _table(s, .55, 1.95, 7, [("Fecha", "date", 1.15, "text"), ("Provincia", "province", 2, "text"),
           ("Cantón", "canton", None, "text"), ("Kits", "kits", .8, "int")], r["kits"] + [{"date": "Total", "province": "", "canton": "", "kits": r["kits_total"]}], row_h=.43, size=10)
    _text(s, .55, 6.15, 7, .5, r["notes"]["kits"], size=10)
    plan = r["plan"]
    _title(s, "Planificación El Niño 2026–2027", 8, 1.4, 4.8)
    _text(s, 8, 2.1, 4.8, 3.8, [f"{number(plan['personas'])} personas potenciales", f"{number(plan['nucleos'])} núcleos familiares potenciales",
          f"USD {number(plan['monto'], 2)} de inversión estimada", "Proyección nacional; planificación, no ejecución."], size=18)
    s = slide("Respuesta en el territorio")
    for i, (key, title) in enumerate([("map_values", "Alertas con código UA"), ("kits_map_values", "Kits en provincias priorizadas")]):
        x = .55 + i * 6.3
        _title(s, title, x, 1.4, 5.9)
        pic = map_png(ctx[key], layer="provincia", selected=set(ctx["selected_codes"]), mode="light", label=title, width=5.8, height=4.8, dpi=180)
        _picture(s, pic, x, 2, w=5.8)
    s = slide("Nota metodológica y fuentes")
    y = 1.45
    for title, text in _notes(ctx):
        height = .42 + len(text) / 150 * .2
        _text(s, .55, y, 2, height, title, size=12, bold=True, color=theme.MORADO)
        _text(s, 2.7, y, 10, height, text, size=11)
        y += height + .12
    _text(s, .55, y, 12.2, .65, "Fuentes: " + ctx["sources"] + "\nGeoportal: " + ctx["geoportal"], size=10)
    assert len(prs.slides) == total


def render_workbook(book):
    from .excel_areas import _summary, _finish_summary, _sheet, _block
    from .charts import map_png
    ctx = book.ctx; r = ctx["response"]
    ws, row = _summary(book, "")
    for key, title in [("by_province", "Alertas por provincia"), ("by_service", "Alertas por servicio")]:
        first, end, row = _block(book, ws, row + 1, title, [("Categoría", "name", "text"), ("Alertas", "value", "int")], r[key], last=12)
        if r[key]:
            chart = book.bar_chart(ws.name, first, end, 1, 2, title, [theme.MORADO], width=720, height=230)
            ws.insert_chart(row, 1, chart); row += 14
    for key, title in [("map_values", "Alertas por provincia"), ("kits_map_values", "Kits en provincias priorizadas")]:
        pic = map_png(ctx[key], layer="provincia", selected=set(ctx["selected_codes"]), mode="light", label=title, width=4.8, height=3.3, dpi=150)
        row = book.heading(ws, row, title)
        book.image(ws, row, 1, pic, 420, key + ".png", description=title); row += 18
    _finish_summary(book, ws, row, ctx["insights"])
    ws, row = _sheet(book, "Evolución", theme.ORO, "Evolución de las alertas", [2.4, 22, 25, 25, 2.4])
    first, end, row = _block(book, ws, row, "Desde " + r["since"], [("Fecha", "date", "text"), ("Registradas en el día", "daily", "int"),
                           ("Acumuladas", "total", "int")], r["daily"], last=3, autofilter=True)
    chart = book.wb.add_chart({"type": "line"})
    for col, title, color in [(2, "Registradas en el día", theme.ORO), (3, "Acumuladas", theme.MORADO)]:
        chart.add_series({"name": title, "categories": [ws.name, first, 1, end, 1], "values": [ws.name, first, col, end, col], "line": {"color": color}})
    chart.set_title({"name": "Evolución de las alertas"}); chart.set_size({"width": 800, "height": 300}); ws.insert_chart(row, 1, chart)
    ws, row = _sheet(book, "Alertas", theme.ORO, "Alertas con código UA", [2.4, 24, 16, 22, 22, 18, 60, 38, 80, 24, 16, 2.4])
    _block(book, ws, row, "Detalle completo", [("Alerta", "code", "text"), ("Fecha de registro", "date", "text"),
           ("Provincia", "province", "text"), ("Cantón", "canton", "text"), ("Código UA", "ua", "text"), ("Unidad", "unit", "text"),
           ("Servicio", "service", "text"), ("Afectación", "impact", "text"), ("Estado", "status", "text"), ("Prioridad", "priority", "text")],
           r["alerts"], note=r["count_note"], height=48, last=10, autofilter=True)
    ws, row = _sheet(book, "Provincias", theme.MORADO, "Acciones del Ministerio en cada provincia", [2.4, 24, 55, 16, 25, 24, 27, 25, 2.4])
    _block(book, ws, row, "Kits y bono de contingencia", [("Provincia", "name", "text"), ("Cantones", "cantons", "text"),
           ("Kits", "kits", "int"), ("Bono gestionado (núcleos)", "managed", "int"), ("Monto gestionado (USD)", "managed_amount", "usd"),
           ("En articulación (personas)", "articulation", "int"), ("Monto en articulación (USD)", "articulation_amount", "usd")], r["actions"], last=7,
           total={"name": "Total", **{k: sum(a[k] for a in r["actions"]) for k in ("kits", "managed", "managed_amount", "articulation", "articulation_amount")}})
    ws, row = _sheet(book, "Kits y bono", theme.VIOLETA_500, "Kits y planificación del bono", [2.4, 24, 35, 35, 28, 2.4])
    _, _, row = _block(book, ws, row, "Kits entregados en provincias priorizadas", [("Fecha", "date", "text"), ("Provincia", "province", "text"),
           ("Cantón", "canton", "text"), ("Kits", "kits", "int")], r["kits"], note=r["notes"]["kits"], last=4, total={"date": "Total", "kits": r["kits_total"]})
    _block(book, ws, row + 2, "Planificación El Niño 2026–2027", [("Personas potenciales", "personas", "int"),
           ("Núcleos familiares potenciales", "nucleos", "int"), ("Inversión estimada (USD)", "monto", "usd")], [r["plan"]],
           note="Proyección nacional; planificación, no ejecución", last=4)
    ws, row = _sheet(book, "Ficha técnica", theme.PIZARRA, "Nota metodológica y fuentes", [2.4, 34, 112, 2.4], landscape=False)
    for label, text in ctx["scope"] + [("Fuentes", ctx["sources"]), ("Conteo", r["count_note"]), ("Geoportal", ctx["geoportal"])] + _notes(ctx):
        ws.set_row(row, max(32, math.ceil(len(text) / 95) * 15 + 12))
        ws.write(row, 1, label, book.f(bold=True, font_color=theme.MORADO, text_wrap=True, valign="top", bg_color=theme.LILA_50))
        ws.write(row, 2, text, book.f(text_wrap=True, valign="top", font_size=10))
        row += 1
    ws.print_area(0, 0, row, 3)
