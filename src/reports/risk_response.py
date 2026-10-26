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
    response["continuity"] = r.continuity_summary()
    response["continuity"]["caption"] = r.suspension_caption()
    response["continuity"]["groups"] = r.suspended_groups()
    response["continuity"]["detail"] = r.continuity_detail.to_dict("records")
    response["kits_provinces"] = r.kits_summary()
    response["families_total"] = int(r.kits.familias.sum())
    response["kits_cut_full"] = "26/10/2026 · 22:26:42"
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
               source="Fuente: MTDH · Subsecretaría Territorial · Kobo de kits y bono de contingencia",
               sources="Subsecretaría Territorial (análisis de alertas); corte Kobo de kits; ayuda memoria del bono de contingencia; base territorial de afectaciones por lluvias.",
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


def _alert_cells(rows, *, markup=True):
    if not markup:
        return [{**a, "identity": f"{a['code']}\n{a['date']}",
                 "unit_full": f"{a['unit']}\nUA {a['ua'] or 'sin código en la fuente'} · {a['service']}",
                 "place_full": f"{a['province']}\n{a['canton']}"} for a in rows]
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


def _pdf_evolution(c, rows, top, width):
    """Compact categorical columns for dates with records; all omitted days are explicitly zero."""
    from .pdf import M, C, _heading
    _heading(c, "Evolución de las alertas", M, top, width, "Registradas por fecha · acumulado al pie")
    active = [row for row in rows if row["daily"] > 0]
    c.setFont("Text", 7.5)
    c.setFillColor(C(theme.PIZARRA))
    if not active:
        c.drawString(M, top - 26, "Sin alertas con código UA en el periodo de la consulta.")
        return top - 42
    # Equal categorical spacing avoids an empty month occupying most of the chart.
    # Daily counts keep a shared zero baseline and the same scale within the selection.
    peak = max(row["daily"] for row in active)
    columns = min(6, len(active))
    slot = width / columns
    last_bottom = top
    for start in range(0, len(active), columns):
        group = active[start:start + columns]
        base = top - 46 - (start // columns) * 70
        for index, row in enumerate(group):
            center = M + slot * (index + .5)
            bar_w = min(44, slot * .32)
            bar_h = 24 * row["daily"] / peak
            c.setStrokeColor(C(theme.LILA_200)); c.setLineWidth(.7)
            c.line(M + slot * index + 12, base, M + slot * (index + 1) - 12, base)
            c.setFillColor(C(theme.ORO)); c.roundRect(center - bar_w / 2, base, bar_w, bar_h, 2, stroke=0, fill=1)
            c.setFillColor(C(theme.MORADO_900)); c.setFont("Text-Bold", 10)
            c.drawCentredString(center, base + bar_h + 5, number(row["daily"]))
            day = pd.to_datetime(row["date"], dayfirst=True)
            label = f"{day.day} {ui._MONTHS_SHORT[day.month - 1]}"
            c.setFont("Text-Semi", 8); c.drawCentredString(center, base - 11, label)
            c.setFillColor(C(theme.MORADO)); c.setFont("Text", 7.7)
            c.drawCentredString(center, base - 22, f"Acumulado: {number(row['total'])}")
        last_bottom = base - 22
    c.setFillColor(C(theme.PIZARRA)); c.setFont("Text", 7.2)
    c.drawString(M, last_bottom - 15,
                 f"Solo fechas con registros. Los demás días del {rows[0]['date']} al {rows[-1]['date']}: 0 alertas con código UA.")
    return last_bottom - 25


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
    selected = set(ctx["selected_codes"])
    top = _band(c, {**ctx, "programs_label": "Respuesta del Ministerio"}, H, emblem_png(selected))
    cards = [dict(k) for k in ctx["kpis"]]
    for card, caption in zip(cards, [f"Desde el {r['since']}", f"{r['kit_provinces']} provincias priorizadas", "Por inundaciones",
                                     f"Corte al {r['bonus_cut']}"]):
        card["note"] = caption
    top = _kpis(c, {**ctx, "kpis": cards, "share_word": ""}, top - 16) - 8
    c.setFillColor(C(theme.LILA_50)); c.roundRect(M, top - 34, full, 34, 6, fill=1, stroke=0)
    c.setFillColor(C(theme.MORADO_900)); c.setFont("Display", 21)
    c.drawString(M + 12, top - 24, number(r["continuity"]["closed"]))
    c.setFont("Text-Bold", 9); c.drawString(M + 60, top - 13, "Unidades cerradas / suspendidas")
    c.setFont("Text", 7.5); c.drawString(M + 60, top - 25, r["continuity"]["caption"] + " · incluye suspensión presencial · 26/10/2026, 16:00")
    top -= 55
    for i, (key, title) in enumerate([("by_province", "UA suspendidas por provincia"), ("by_service", "UA suspendidas por servicio")]):
        x = M + i * (half + 22)
        rows = r["continuity"][key]; peak = max([a["value"] for a in rows] or [1])
        _heading(c, title, x, top, half)
        _bars(c, [{"name": a["name"], "text": number(a["value"]), "fraction": a["value"] / peak} for a in rows], x, top - 24, half, 25)
    top -= 24 + max(len(r["continuity"]["by_province"]), len(r["continuity"]["by_service"])) * 25 + 13
    _heading(c, "Detalle de las unidades suspendidas", M, top, full, "Suspensión total o presencial")
    groups = r["continuity"]["groups"]
    rows = [[Markup(f"<b>{escape(a['province'])}</b><br/>{escape(a['canton'])}"), a["service"], number(a["units"]), a["names"]] for a in groups]
    rows.append(["Total", "CDI / CNH", number(r["continuity"]["closed"]), "Código UA: no consta en la base territorial."])
    top = _pdf_table(c, top - 20, ["Provincia / cantón", "Servicio", "UA", "Unidades identificadas"], rows,
                     [114, 43, 34, full - 191], size=8, padding=4, align=["L", "L", "R", "L"], total=True) - 17
    top = _paragraph(c, r["continuity"]["note"], M, top, full, size=7.7) - 18
    check(top)
    _next_page(c, ctx, 1, 3)

    # Page 2: every record, with wrapped names and impacts rather than abbreviated or clipped fields.
    top = _slim_band(c, ctx, "Alertas con código UA", f"Registro completo · {r['alert_count']} alertas · {ctx['territory_label']}") - 16
    c.setFillColor(C(theme.ORO_100)); c.roundRect(M, top - 36, full, 36, 6, fill=1, stroke=0)
    c.setFillColor(C(theme.ORO)); c.roundRect(M, top - 36, 3, 36, 1.5, fill=1, stroke=0)
    _paragraph(c, r["count_note"], M + 12, top - 10, full - 24, size=8.4)
    top -= 50
    rows = _alert_cells(r["alerts"])
    top = _pdf_table(c, top, ["Alerta / registro", "Unidad de atención y servicio", "Territorio", "Afectación al servicio", "Estado"],
                     [[a["identity"], a["unit_full"], a["place_full"], a["impact"], a["state"]] for a in rows],
                     [86, 150, 66, full - 380, 78], size=7.5, padding=2.5) - 12
    top = note("Criterio de inclusión y lectura", r["notes"]["alerts"], M, top, full, size=8)
    top = note("Verificación de la afectación", r["notes"]["quality"], M, top, full, size=8)
    for i, (key, title) in enumerate([("by_province", "Alertas por provincia"), ("by_service", "Alertas por servicio")]):
        x = M + i * (half + 22); rows = r[key]; peak = max([a["value"] for a in rows] or [1])
        _heading(c, title, x, top, half)
        _bars(c, [{"name": a["name"], "text": str(a["value"]), "fraction": a["value"] / peak} for a in rows], x, top - 20, half, 18)
    top -= 24 + max(len(r["by_province"]), len(r["by_service"])) * 18
    top = _pdf_evolution(c, r["daily"], top, full)
    check(top)
    _next_page(c, ctx, 2, 3)

    # Page 3: every provincial total; delivery-level rows remain in the data export.
    top = _slim_band(c, ctx, "Acciones del Ministerio", "Kits: Kobo al 26/10/2026, 22:26 · bono: corte 23/10/2026") - 20
    _heading(c, "Respuesta por provincia", M, top, full,
             f"{r['deliveries']} registros · {number(r['kits_total'])} kits")
    families = {a["provincia"]: a["familias"] for a in r["kits_provinces"]}
    actions = _money_rows(r["actions"])
    rows = [[a["name"], number(a["kits"]), number(families.get(a["name"], 0)), _dash(number(a["managed"])),
             _dash(a["managed_text"]), _dash(number(a["articulation"])), _dash(a["articulation_text"])] for a in actions]
    totals = _money_rows([_action_totals(r["actions"])])[0]
    rows.append(["Total", number(r["kits_total"]), number(r["families_total"]), number(totals["managed"]), totals["managed_text"],
                 number(totals["articulation"]), totals["articulation_text"]])
    top = _pdf_table(c, top - 18, ["Provincia", "Kits", "Familias*", "Bono: núcleos", "Monto USD", "Articulación: personas", "Monto USD"],
                     rows, [full - 366, 43, 49, 55, 75, 69, 75], size=7.2, padding=2.7,
                     align=["L", "R", "R", "R", "R", "R", "R"], total=True) - 17
    kitrows = [{"name": a["provincia"], "value": a["kits"]} for a in r["kits_provinces"][:4]]
    rest = sum(a["kits"] for a in r["kits_provinces"][4:])
    if rest: kitrows.append({"name": "Otras provincias", "value": rest})
    peak = max([a["value"] for a in kitrows] or [1])
    _heading(c, "Kits en provincias priorizadas", M, top, half)
    _bars(c, [{"name": a["name"], "text": number(a["value"]), "fraction": a["value"] / peak} for a in kitrows], M, top - 20, half, 18)
    x = M + half + 22
    _heading(c, "Planificación del bono", x, top, half, "Nacional · 2026–2027")
    plan = r["plan"]
    text = f"{number(plan['personas'])} personas potenciales · {number(plan['nucleos'])} núcleos familiares potenciales. " \
           f"Inversión estimada: USD {number(plan['monto'], 2)}. Planificación, no ejecución."
    _paragraph(c, text, x, top - 23, half, size=9)
    top -= max(110, 20 + len(kitrows) * 18)
    _paragraph(c, f"* {number(r['families_total'])} familias reportadas por entrega; no son familias únicas. "
                  "Detalle de fechas y cantones en el dashboard y en Excel (Kits y bono).", M, top, full, size=7.2)
    top -= 30
    left = note("Kits · alcance del corte", r["notes"]["kits"], M, top, half, size=7.4)
    left = note("Filtros", r["notes"]["filters"], M, left, half, size=7.4)
    right = note("Bono de contingencia", r["notes"]["bonus"], x, top, half, size=7.4)
    right = note("Fuentes y geoportal", ctx["sources"] + " " + ctx["geoportal"], x, right, half, size=7.1)
    c.linkURL(ctx["geoportal"], (x, right, M + full, right + 20), relative=0)
    check(min(left, right))
    assert pages == 3


def render_pptx(prs, ctx):
    from .charts import emblem_png, map_png
    from .pptx import _cover, _header, _footer, _text, _bar_chart, _line_chart, _picture
    from .pptx_areas import _table, _title
    r = ctx["response"]
    chunks = [r["alerts"][i:i + 5] for i in range(0, len(r["alerts"]), 5)] or [[]]
    total = 8 + len(chunks)
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
    active = [d for d in r["daily"] if d["daily"]]
    if active:
        _bar_chart(s, [d["short"] for d in active], [d["daily"] for d in active], "Alertas por fecha", x=.55, y=1.45, w=6, h=2.1)
    _text(s, 7, 1.65, 5.5, .6, f"{r['continuity']['closed']} Unidades cerradas / suspendidas", size=22, bold=True, color=theme.MORADO)
    _text(s, 7, 2.35, 5.5, .55, "Atención suspendida · corte 26/10/2026, 16:00", size=12)
    for i, (key, title) in enumerate([("by_province", "UA suspendidas por provincia"), ("by_service", "UA suspendidas por servicio")]):
        rows = r["continuity"][key]
        _title(s, title, .55 + i * 6.25, 3.6, 5.8)
        if rows:
            _bar_chart(s, [a["name"] for a in rows], [a["value"] for a in rows], "Unidades", x=.55 + i * 6.25, y=4, w=5.8, h=2.1)
    _text(s, .55, 6.25, 12.2, .65, r["continuity"]["note"], size=9)
    s = slide("Detalle de las unidades suspendidas")
    _table(s, .55, 1.5, 12.2, [("Provincia", "province", 1.5, "text"), ("Cantón", "canton", 1.8, "text"),
           ("Servicio", "service", .8, "text"), ("UA", "units", .55, "int"), ("Unidades identificadas", "names", None, "text")],
           r["continuity"]["groups"], row_h=.61, header_h=.5, size=9)
    _text(s, .55, 6.5, 12.2, .35, "Código UA: no consta en la base. Los 63 CNH de El Oro no tienen nombre ni cantón registrados.", size=11)
    for i, chunk in enumerate(chunks, 1):
        s = slide(f"Alertas con código UA · {i}/{len(chunks)}")
        _table(s, .55, 1.5, 12.2, [("Alerta / registro", "identity", 1.4, "text"), ("Unidad y servicio", "unit_full", 3, "text"),
               ("Territorio", "place_full", 1.35, "text"), ("Afectación", "impact", None, "text"), ("Estado", "status", 1.2, "text"),
               ("Prioridad", "priority", .8, "text")], _alert_cells(chunk, markup=False), row_h=.87, header_h=.5, size=9)
        _text(s, .55, 6.43, 12.2, .4, r["notes"]["quality"], size=9)
    s = slide("Acciones del Ministerio en cada provincia")
    actions = _money_rows(r["actions"])
    for i in range(0, len(actions), 11):
        part = actions[i:i + 11]
        _table(s, .55 + (i // 11) * 6.25, 1.5, 5.9,
               [("Provincia", "name", None, "text"), ("Kits", "kits", .6, "int"), ("Bono núcleos", "managed", .65, "int"),
                ("USD gestionado", "managed_text", 1.05, "text"), ("Artic. personas", "articulation", .7, "int"),
                ("USD articulación", "articulation_text", 1.05, "text")], part, row_h=.36, header_h=.65, size=8)
    _text(s, .55, 6.25, 12.2, .5, r["notes"]["bonus"], size=9)
    s = slide("Kits y planificación del bono")
    _title(s, "Kits en provincias priorizadas", .55, 1.4, 7)
    for i in range(0, len(r["kits_provinces"]), 10):
        _table(s, .55 + (i // 10) * 3.65, 1.95, 3.5,
               [("Provincia", "provincia", None, "text"), ("Kits", "kits", .65, "int"), ("Familias*", "familias", .7, "int")],
               r["kits_provinces"][i:i + 10], row_h=.34, header_h=.5, size=8)
    _text(s, .55, 6.05, 7.1, .65, f"{number(r['kits_total'])} kits · {number(r['families_total'])} familias reportadas* · {r['deliveries']} registros. "
          "*No son familias únicas. Corte Kobo: 26/10/2026, 22:26.", size=11)
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
    row = book.kpi_row(ws, row, [("Unidades cerradas / suspendidas", r["continuity"]["closed"], "#,##0", "Atención suspendida · corte 26/10/2026, 16:00", theme.MORADO)])
    for key, title in [("by_province", "UA suspendidas por provincia"), ("by_service", "UA suspendidas por servicio")]:
        rows = r["continuity"][key]
        first, end, row = _block(book, ws, row + 1, title, [("Categoría", "name", "text"), ("Unidades", "value", "int")], rows, last=12)
        if rows:
            ws.insert_chart(row, 1, book.bar_chart(ws.name, first, end, 1, 2, title, [theme.MORADO], width=720, height=230)); row += 14
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
    ws, row = _sheet(book, "Kits y bono", theme.VIOLETA_500, "Kits y planificación del bono", [2.4, 24, 35, 35, 20, 22, 24, 2.4])
    _, _, row = _block(book, ws, row, "Kits entregados en provincias priorizadas", [("Período", "date", "text"), ("Provincia", "province", "text"),
           ("Cantón", "canton", "text"), ("Kits", "kits", "int"), ("Familias reportadas", "families", "int"), ("ID Kobo", "id", "text")], r["kits"], note=r["notes"]["kits"], last=6, total={"date": "Total", "kits": r["kits_total"], "families": r["families_total"]})
    _block(book, ws, row + 2, "Planificación El Niño 2026–2027", [("Personas potenciales", "personas", "int"),
           ("Núcleos familiares potenciales", "nucleos", "int"), ("Inversión estimada (USD)", "monto", "usd")], [r["plan"]],
           note="Proyección nacional; planificación, no ejecución", last=4)
    ws, row = _sheet(book, "Unidades suspendidas", theme.MORADO, "Detalle territorial de unidades", [2.4, 24, 30, 20, 52, 25, 42, 16, 2.4])
    _block(book, ws, row, "99 suspendidas · base 26/10/2026, 16:00 + confirmación operativa de Guayas",
           [("Provincia", "provincia", "text"), ("Cantón", "canton", "text"), ("Servicio", "servicio", "text"),
            ("Unidad", "unidad", "text"), ("Código UA", "codigo_ua", "text"), ("Estado de atención", "estado", "text"),
            ("Unidades", "unidades", "int")], r["continuity"]["detail"], note=r["continuity"]["note"], last=7, autofilter=True)
    ws, row = _sheet(book, "Ficha técnica", theme.PIZARRA, "Nota metodológica y fuentes", [2.4, 34, 112, 2.4], landscape=False)
    for label, text in ctx["scope"] + [("Fuentes", ctx["sources"]), ("Conteo", r["count_note"]), ("Geoportal", ctx["geoportal"]), ("Continuidad de atención", r["continuity"]["note"])] + _notes(ctx):
        ws.set_row(row, max(32, math.ceil(len(text) / 95) * 15 + 12))
        ws.write(row, 1, label, book.f(bold=True, font_color=theme.MORADO, text_wrap=True, valign="top", bg_color=theme.LILA_50))
        ws.write(row, 2, text, book.f(text_wrap=True, valign="top", font_size=10))
        row += 1
    ws.print_area(0, 0, row, 3)
