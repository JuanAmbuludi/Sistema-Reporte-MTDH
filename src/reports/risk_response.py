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
               pdf_pages=3, selected_codes=list(view.provinces),
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


class Markup(str):
    """A cell already written in the markup of ReportLab paragraphs (it is not escaped)."""


STATUS_INK = {"Pendiente": "#8A5D00", "En seguimiento": theme.MORADO_600, "Resuelto": "#1E5E3B", "Por confirmar": "#6E6880"}


def _dash(value: str) -> str:
    return "—" if value in ("0", "0,00") else value


def _alert_cells(rows):
    muted = "#6E6880"
    out = []
    for a in rows:
        ink = STATUS_INK.get(a["status"], theme.MORADO_900)
        out.append({**a,
                    "identity": Markup(f"<b>{escape(a['code'])}</b><br/><font color='{muted}'>{escape(a['date'])}</font>"),
                    "unit_full": Markup(f"<b>{escape(a['unit'])}</b><br/><font color='{muted}'>UA {escape(a['ua'] or 'sin código en la fuente')}"
                                        f" · {escape(a['service'])}</font>"),
                    "place_full": Markup(f"{escape(a['province'])}<br/><font color='{muted}'>{escape(a['canton'])}</font>"),
                    "state": Markup(f"<font color='{ink}'><b>{escape(a['status'])}</b></font><br/>"
                                    f"<font color='{muted}'>Prioridad {escape(str(a['priority']).lower())}</font>")})
    return out


def _pdf_table(c, top, headers, rows, widths, size=8, *, x=None, padding=5, align=None, total=False):
    """A designed table: purple header, zebra rows, figures to the right and, with ``total``, a closing row."""
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib import colors
    from .pdf import M, BOTTOM
    x = M if x is None else x
    align = align or ["L"] * len(headers)
    normal = ParagraphStyle("cell", fontName="Text", fontSize=size, leading=size * 1.32, textColor=colors.HexColor(theme.TINTA))
    right = ParagraphStyle("cellr", parent=normal, alignment=TA_RIGHT)
    header = ParagraphStyle("head", parent=normal, fontName="Text-Bold", fontSize=size - 0.3, textColor=colors.white)
    header_r = ParagraphStyle("headr", parent=header, alignment=TA_RIGHT)

    def cell(value, style):
        text = str(value) if isinstance(value, Markup) else escape(str(value)).replace("\n", "<br/>")
        return Paragraph(text, style)

    data = [[cell(h, header_r if a == "R" else header) for h, a in zip(headers, align)]]
    for index, row in enumerate(rows):
        closing = total and index == len(rows) - 1
        data.append([cell(Markup(f"<b>{escape(str(v))}</b>") if closing and not isinstance(v, Markup) else v,
                          right if a == "R" else normal) for v, a in zip(row, align)])
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.MORADO)),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F5FA")]),
             ("VALIGN", (0, 0), (-1, 0), "MIDDLE"), ("VALIGN", (0, 1), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
             ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#ECE9F0"))]
    if total:
        style += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor(theme.LAVANDA)),
                  ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor(theme.MORADO))]
    table.setStyle(TableStyle(style))
    _, height = table.wrap(sum(widths), 2000)
    if top - height < BOTTOM:
        raise ValueError("La tabla del boletín excede el área imprimible.")
    table.drawOn(c, x, top - height)
    return top - height


def _evolution_png(rows, width, height) -> bytes:
    """Alerts registered each day (gold columns) and their running total (purple area), from the first day of the follow-up."""
    from .charts import _LOCK, MUTED, FigureCanvasAgg, Figure, _png, font
    totals, daily = [r["total"] for r in rows], [r["daily"] for r in rows]
    peak = max(totals + [1])
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=220, facecolor="#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0.045, 0.17, 0.94, 0.78])
        xs = list(range(len(rows)))
        ax.fill_between(xs, totals, step="post", color=theme.LILA_100, alpha=0.55, lw=0, zorder=1)
        ax.step(xs, totals, where="post", color=theme.MORADO, lw=1.8, zorder=2)
        ax.bar(xs, daily, width=0.62, color=theme.ORO, zorder=3)
        for i, value in enumerate(daily):
            if value:
                ax.text(i - 0.45, value + peak * 0.04, f"+{value}", ha="right", va="bottom", color=theme.ORO_700,
                        fontproperties=font("Bold", size=7.4), zorder=4)
        ax.text(len(xs) - 1, totals[-1] + peak * 0.06, f"{totals[-1]} alertas", ha="right", va="bottom", color=theme.MORADO_900,
                fontproperties=font("Bold", size=8), zorder=4)
        ticks = [i for i in xs if i % 7 == 0]
        if xs and xs[-1] not in ticks and xs[-1] - ticks[-1] > 2:
            ticks.append(xs[-1])
        ax.set_xticks(ticks)
        ax.set_xticklabels([rows[i]["short"] for i in ticks], fontproperties=font("SemiBold", size=6.8), color=MUTED)
        step = max(1, math.ceil(peak / 4))
        ax.set_yticks(list(range(0, int(peak * 1.3) + 1, step)))
        ax.set_yticklabels([str(t) for t in range(0, int(peak * 1.3) + 1, step)], fontproperties=font(size=6.6), color=MUTED)
        ax.set_ylim(0, peak * 1.32)
        ax.set_xlim(-0.8, len(xs) - 0.2)
        ax.grid(axis="y", color="#EEEAF4", lw=0.6, zorder=0)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0, pad=3)
        return _png(fig, dpi=220)


def render_pdf(c, ctx, pages):
    """Three-page bulletin: overview; complete alert register; actions, kits and methodological scope."""
    from .charts import map_png
    from .pdf import M, W, BOTTOM, C, _kpis, _heading, _bars, _next_page, _slim_band, _picture, _fit
    from .risks import _paragraph
    full = W - 2 * M
    half = (full - 22) / 2
    r = ctx["response"]

    def note(title, text, x, top, width, size=8):
        c.setFillColor(C(theme.MORADO)); c.setFont("Text-Bold", 8.8)
        c.drawString(x, top, title)
        return _paragraph(c, text, x, top - 12, width, size=size) - 13

    def check(top):
        if top < BOTTOM:
            raise ValueError("El contenido del resumen excede las tres páginas; revisar la composición del nuevo corte.")

    # Page 1: the institutional band, four figures, alerts by province and service, their evolution and two maps.
    from .charts import emblem_png
    from .pdf import H, _band
    from .pdf_areas import _legend
    selected = set(ctx["selected_codes"])
    top = _band(c, {**ctx, "programs_label": "Respuesta del Ministerio"}, H, emblem_png(selected))
    cards = [dict(k) for k in ctx["kpis"]]
    for card, caption in zip(cards, [f"Desde el {r['since']}", f"{r['kit_provinces']} provincias priorizadas", "Por inundaciones",
                                     f"Corte al {r['bonus_cut']}"]):
        card["note"] = caption
    top = _kpis(c, {**ctx, "kpis": cards, "share_word": ""}, top - 16) - 24
    rows_h = 0
    for i, (key, title) in enumerate([("by_province", "Alertas por provincia"), ("by_service", "Alertas por servicio")]):
        x = M + i * (half + 22)
        rows = r[key]
        peak = max([v["value"] for v in rows] or [1]) or 1
        _heading(c, title, x, top, half, f"{r['alert_count']} alertas")
        _bars(c, [{"name": v["name"], "text": f"{v['value']} alerta" + ("" if v["value"] == 1 else "s"), "fraction": v["value"] / peak}
                  for v in rows], x, top - 24, half, 22)
        rows_h = max(rows_h, len(rows))
    top -= 24 + rows_h * 22 + 10
    _heading(c, "Evolución de las alertas", M, top, full, f"Desde el {r['since']} · registradas en el día y acumuladas")
    _legend(c, [(theme.ORO, "Registradas en el día"), (theme.MORADO, "Acumuladas")], M + full, top - 15, right=True)
    chart_h = 104
    _picture(c, _evolution_png(r["daily"], full / 72, chart_h / 72), M, top - 22, full, chart_h / full)
    top -= 22 + chart_h + 26
    map_h = half * 0.66
    for i, (key, title, label) in enumerate([("map_values", "Alertas con código UA", "Alertas"),
                                              ("kits_map_values", "Kits en provincias priorizadas", "Kits")]):
        x = M + i * (half + 22)
        _heading(c, title, x, top, half, "Por provincia" + (" · en dorado, la selección" if selected else ""))
        pic = map_png(ctx[key], layer="provincia", selected=selected, mode="light", label=label, marks=False,
                      width=half / 72, height=map_h / 72, dpi=200)
        _picture(c, pic, x, top - 20, half, map_h / half)
    top -= 20 + map_h + 12
    c.setFillColor(C(theme.LILA_50)); c.roundRect(M, top - 34, full, 34, 6, fill=1, stroke=0)
    c.setFillColor(C(theme.MORADO)); c.roundRect(M, top - 34, 3, 34, 1.5, fill=1, stroke=0)
    _paragraph(c, "Cada alerta se cuenta una vez por su código. Los mapas muestran todo el país y destacan el territorio "
                  "seleccionado. " + ctx["update"]["line"] + ".", M + 12, top - 8, full - 24, size=7.6)
    check(top - 34)
    _next_page(c, ctx, 1, 3)

    # Page 2: every record, with wrapped names and impacts rather than abbreviated or clipped fields.
    top = _slim_band(c, ctx, "Alertas con código UA", f"Registro completo · {r['alert_count']} alertas · {ctx['territory_label']}") - 16
    c.setFillColor(C(theme.ORO_100)); c.roundRect(M, top - 52, full, 52, 6, fill=1, stroke=0)
    c.setFillColor(C(theme.ORO)); c.roundRect(M, top - 52, 3, 52, 1.5, fill=1, stroke=0)
    _paragraph(c, r["count_note"], M + 12, top - 10, full - 24, size=8.4)
    top -= 66
    rows = _alert_cells(r["alerts"])
    top = _pdf_table(c, top, ["Alerta / registro", "Unidad de atención y servicio", "Territorio", "Afectación al servicio", "Estado"],
                     [[a["identity"], a["unit_full"], a["place_full"], a["impact"], a["state"]] for a in rows],
                     [86, 150, 66, full - 380, 78], size=7.6, padding=5) - 20
    top = note("Criterio de inclusión y lectura", r["notes"]["alerts"], M, top, full, size=8)
    top = note("Verificación de la afectación", r["notes"]["quality"], M, top, full, size=8)
    check(top)
    _next_page(c, ctx, 2, 3)

    # Page 3: provincial response, deliveries and national planning share the available width.
    top = _slim_band(c, ctx, "Acciones del Ministerio", "Kits en provincias priorizadas y bono de contingencia") - 22
    _heading(c, "Acciones del Ministerio en cada provincia", M, top, full)
    actions = _money_rows(r["actions"] + [_action_totals(r["actions"])])
    top = _pdf_table(c, top - 16, ["Provincia / cantones", "Kits", "Bono gestionado (núcleos)", "Monto (USD)", "En articulación (personas)", "Monto (USD)"],
                     [[Markup(f"<b>{escape(a['name'])}</b>" + (f"<br/><font color='#6E6880'>{escape(a['cantons'])}</font>" if a["cantons"] else "")),
                       _dash(number(a["kits"])), _dash(number(a["managed"])), _dash(a["managed_text"]), _dash(number(a["articulation"])),
                       _dash(a["articulation_text"])] for a in actions[:-1]]
                     + [["Total", number(actions[-1]["kits"]), number(actions[-1]["managed"]), actions[-1]["managed_text"],
                         number(actions[-1]["articulation"]), actions[-1]["articulation_text"]]],
                     [full - 353, 38, 75, 80, 80, 80], size=7.5, align=["L", "R", "R", "R", "R", "R"], total=True) - 26
    kit_w = full * .63
    plan_x = M + kit_w + 18
    plan_w = full - kit_w - 18
    _heading(c, "Kits en provincias priorizadas", M, top, kit_w)
    _heading(c, "Planificación del bono", plan_x, top, plan_w)
    c.setFillColor(C(theme.PIZARRA)); c.setFont("Text", 7.5)
    c.drawString(plan_x, top - 18, "El Niño 2026–2027 · nacional")
    bottom = _pdf_table(c, top - 16, ["Fecha", "Provincia", "Cantón", "Kits"],
                     [[a["date"], a["province"], a["canton"], number(a["kits"])] for a in r["kits"]]
                     + [["Total", f"{len(r['kits'])} entregas", "", number(r["kits_total"])]], [65, 85, kit_w - 184, 34], size=7.7,
                     padding=5, align=["L", "L", "L", "R"], total=True)
    plan = r["plan"]
    y = top - 29
    tiles = [("Personas potenciales", number(plan["personas"])),
             ("Núcleos familiares potenciales", number(plan["nucleos"])),
             ("Inversión estimada", "USD " + number(plan["monto"], 2))]
    for label, value in tiles:
        c.setFillColor(C(theme.ORO_100)); c.roundRect(plan_x, y - 48, plan_w, 48, 5, fill=1, stroke=0)
        c.setFillColor(C(theme.MORADO_900)); c.setFont("Text-Semi", 7.5); c.drawString(plan_x + 10, y - 13, label)
        c.setFont("Display", _fit(value, "Display", 16, plan_w - 20, 10)); c.drawString(plan_x + 10, y - 35, value)
        y -= 54
    y = _paragraph(c, "Planificación, no ejecución.", plan_x, y - 1, plan_w, size=7.5)
    top = min(bottom, y) - 24
    _heading(c, "Alcances y fuentes", M, top, full)
    top -= 22
    left_bottom = note("Entregas de kits", r["notes"]["kits"], M, top, half, size=7.8)
    left_bottom = note("Filtros de la consulta", r["notes"]["filters"], M, left_bottom, half, size=7.8)
    left_bottom = note("Fuentes", ctx["sources"], M, left_bottom, half, size=7.6)
    right_bottom = note("Bono de contingencia", r["notes"]["bonus"], M + half + 22, top, half, size=7.8)
    right_bottom = note("Geoportal institucional", ctx["geoportal"], M + half + 22, right_bottom, half, size=7.8)
    c.linkURL(ctx["geoportal"], (M + half + 22, right_bottom, M + full, right_bottom + 28), relative=0)
    check(min(left_bottom, right_bottom))
    assert pages == 3


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
