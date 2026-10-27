"""Complete bulletin of the visible response dashboard; exposure stays internal."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

import pandas as pd

from src import enos, theme, ui
from .areas import _base, kpis_from_cards
from .context import number


def build_context(view, *, title: str) -> dict:
    from .approved_risk_pdf import alert_chunks
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
    tiles: dict[tuple, int] = {}
    for d in response["continuity"]["detail"]:
        if d["estado"] in ("Suspendida", "Suspendida presencial"):
            key = (d["provincia"], d["canton"], d["servicio"])
            tiles[key] = tiles.get(key, 0) + int(d["unidades"])
    response["continuity"]["tiles"] = [{"province": a, "canton": b, "service": c, "units": n} for (a, b, c), n in tiles.items()]
    response["kits_provinces"] = r.kits_summary()
    response["families_total"] = int(r.kits.familias.sum())
    response["kits_cut_full"] = "27/10/2026 · 13:35:45"
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
               pdf_pages=2 + len(alert_chunks(response["alerts"])), approved_risk_template=True, selected_codes=list(view.provinces),
               map_values=view.map_values("alertas")[0], kits_map_values=view.map_values("kits")[0],
               suspended_map_values=view.map_values("suspendidas")[0],
               scope=view.scope_items(), selection=view.programs_label, geoportal=ui.GEOPORTAL_URL,
               source="Fuente: MTDH · Subsecretaría Territorial · Kobo de kits y bono de contingencia",
               sources="Subsecretaría Territorial (análisis de alertas); corte Kobo de kits; ayuda memoria del bono de contingencia; base territorial de afectaciones por lluvias.",
               insights=_findings(r, response))
    return ctx


def _findings(r, response: dict) -> list[dict]:
    """The findings of the selection: only the actions it has (a zero is never a finding); the national plan of the
    bonus completes them when fewer than two remain."""
    plan = response["plan"]
    out = []
    if response["continuity"]["closed"]:
        out.append({"icon": "storm", "text": _continuity_finding(response["continuity"])})
    if len(r.alerts):
        out.append({"icon": "shield", "text": r.count_note()})
    if r.kits_total:
        out.append({"icon": "life-buoy", "text": f"{number(r.kits_total)} kits en "
                                                 f"{_count(response['kit_provinces'], 'provincia priorizada', 'provincias priorizadas')}; "
                                                 f"corte {response['kits_cut']}."})
    if response["managed_people"]:
        out.append({"icon": "hand-coins", "text": f"{number(response['managed_people'])} núcleos familiares con bono gestionado: "
                                                  f"USD {number(response['managed_amount'], 2)}."})
    if response["articulation_people"] and len(out) < 4:
        out.append({"icon": "users", "text": f"{number(response['articulation_people'])} personas en articulación del bono de contingencia: "
                                             f"USD {number(response['articulation_amount'], 2)}."})
    if len(out) < 2:
        out.append({"icon": "layers", "text": f"Planificación El Niño 2026–2027: {number(plan['personas'])} personas potenciales, "
                                              f"{number(plan['nucleos'])} núcleos familiares y USD {number(plan['monto'], 2)} "
                                              "(proyección nacional)."})
    return out[:4]


def _count(value: int, singular: str, plural: str | None = None) -> str:
    """A count with its noun in the right number: 1 provincia, 20 provincias."""
    return f"{number(value)} {singular if value == 1 else (plural or singular + 's')}"


def _continuity_finding(continuity: dict) -> str:
    closed = continuity["closed"]
    lead = continuity["by_province"][0] if continuity["by_province"] else None
    text = f"{number(closed)} unidades de atención con atención suspendida ({continuity['caption']})"
    if lead and closed:
        text += f"; {lead['name']} concentra {number(lead['value'])} ({number(lead['value'] / closed * 100, 1)} %)"
    return text + "."


def _notes(ctx):
    r = ctx["response"]
    return [("Alertas", r["notes"]["alerts"]),
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
                 "unit_full": f"{a['unit']}\n" + (f"UA {a['ua']} · " if a["ua"] else "") + a["service"],
                 "place_full": f"{a['province']}\n{a['canton']}"} for a in rows]
    muted = "#6E6880"
    out = []
    for a in rows:
        ink = STATUS_INK.get(a["status"], theme.MORADO_900)
        out.append({**a,
                    "identity": Markup(f"<b>{escape(a['code'])}</b><br/><font color='{muted}'>{escape(a['date'])}</font>"),
                    "unit_full": Markup(f"<b>{escape(a['unit'])}</b><br/><font color='{muted}'>"
                                        + (f"UA {escape(a['ua'])} · " if a["ua"] else "") + f"{escape(a['service'])}</font>"),
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
        # Paragraph wrapping can differ slightly between renderers. Recover space
        # from row padding before reducing type, keeping every row and column.
        for compact_padding, compact_leading in ((.8, 1.24), (.4, 1.16)):
            for cells in data:
                for paragraph in cells:
                    paragraph.style = paragraph.style.clone("compact")
                    paragraph.style.leading = paragraph.style.fontSize * compact_leading
            compact = Table(data, colWidths=widths, repeatRows=1)
            compact.setStyle(TableStyle(style + [
                ("TOPPADDING", (0, 0), (-1, -1), compact_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), compact_padding),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4)]))
            _, height = compact.wrap(sum(widths), 2000)
            table = compact
            if top - height >= BOTTOM:
                break
        if top - height < BOTTOM:
            raise ValueError("La tabla del boletín excede el área imprimible.")
    table.drawOn(c, x, top - height)
    return top - height


def _units_pdf(c, alerts: list[dict], x: float, top: float, width: float) -> float:
    """Each alert as one square in the row of its province, in the colour of its service (the unit chart of the dashboard)."""
    from .pdf import C, MUTED, NIGHT
    from .risk_charts import short_service, tone
    counts: dict[str, int] = {}
    for a in alerts:
        counts[a["province"]] = counts.get(a["province"], 0) + 1
    provinces = sorted(counts, key=lambda p: -counts[p])
    services = sorted({a["service"] for a in alerts}, key=lambda s: -sum(1 for a in alerts if a["service"] == s))
    rank = {s: i for i, s in enumerate(services)}
    label_w = 64
    widest = max(counts.values() or [1])
    size = max(9.0, min(15.0, (width - label_w) / max(widest, 6) - 4))
    y = top
    for province in provinces:
        c.setFillColor(NIGHT); c.setFont("Text-Bold", 8.2)
        c.drawString(x, y - size / 2 - 2.8, province)
        c.setFillColor(MUTED); c.setFont("Text-Semi", 8.2)
        c.drawRightString(x + label_w - 8, y - size / 2 - 2.8, str(counts[province]))
        part = sorted((a for a in alerts if a["province"] == province), key=lambda a: (rank[a["service"]], a["date"], a["code"]))
        for index, a in enumerate(part):
            c.setFillColor(C(tone(a["service"])))
            c.roundRect(x + label_w + index * (size + 4), y - size, size, size, 2.2, stroke=0, fill=1)
        y -= size + 9
    y -= 4
    cx = x
    for service in services:
        c.setFillColor(C(tone(service))); c.roundRect(cx, y - 7, 7, 7, 1.5, stroke=0, fill=1)
        c.setFillColor(C(theme.PIZARRA)); c.setFont("Text-Medium", 7.2)
        text = f"{short_service(service)} · {sum(1 for a in alerts if a['service'] == service)}"
        c.drawString(cx + 10, y - 6.2, text)
        cx += 10 + c.stringWidth(text, "Text-Medium", 7.2) + 14
    return y - 12


def _strips_pdf(c, bonus: list[dict], x: float, top: float, width: float) -> float:
    """Each stage of the bonus as a 100 % strip split by province (families with a managed payment; people in articulation)."""
    from reportlab.pdfbase import pdfmetrics
    from .pdf import C, NIGHT
    from .risk_charts import PROVINCE_TONES, ink
    stages = [("Pago gestionado", "managed", "managed_amount", "núcleos familiares"),
              ("En articulación", "articulation", "articulation_amount", "personas")]
    stages = [s for s in stages if sum(b[s[1]] for b in bonus)]
    weight = {b["name"]: sum(b[key] / (sum(x[key] for x in bonus) or 1) for _n, key, _a, _u in stages) for b in bonus}
    order = sorted(weight, key=lambda name: -weight[name])
    y = top
    for title, key, amount, unit in stages:
        total = sum(b[key] for b in bonus)
        money = sum(b[amount] for b in bonus)
        c.setFillColor(NIGHT); c.setFont("Text-Bold", 8.4); c.drawString(x, y, title)
        c.setFillColor(C(theme.PIZARRA)); c.setFont("Text", 7.6)
        c.drawRightString(x + width, y, f"{number(total)} {unit} · USD {number(money, 2)}")
        bar_y, bar_h = y - 21, 15
        cx = x
        for name in order:
            value = next((b[key] for b in bonus if b["name"] == name), 0)
            if not value:
                continue
            length = width * value / total
            color = PROVINCE_TONES.get(name, theme.LILA_200)
            c.setFillColor(C(color)); c.rect(cx, bar_y, max(0.8, length - 1.6), bar_h, stroke=0, fill=1)
            label = f"{name} {number(value)}"
            for text in (label, number(value)):
                if pdfmetrics.stringWidth(text, "Text-Bold", 7) + 6 <= length - 1.6:
                    c.setFillColor(C(ink(color))); c.setFont("Text-Bold", 7)
                    c.drawCentredString(cx + (length - 1.6) / 2, bar_y + 4.6, text)
                    break
            cx += length
        y = bar_y - 17
    cx = x
    for name in order:
        color = PROVINCE_TONES.get(name, theme.LILA_200)
        width_text = c.stringWidth(name, "Text-Medium", 7)
        if cx + 10 + width_text > x + width:
            cx, y = x, y - 11
        c.setFillColor(C(color)); c.roundRect(cx, y - 1, 7, 7, 1.5, stroke=0, fill=1)
        c.setFillColor(C(theme.PIZARRA)); c.setFont("Text-Medium", 7); c.drawString(cx + 10, y, name)
        cx += 10 + width_text + 12
    return y - 10


def _kits_pdf(c, provinces: list[dict], deliveries: list[dict], since: str | None, x: float, top: float, width: float,
              row: float = 13.2) -> float:
    """Kits of each province (a lollipop with its total and share) beside every delivery in time (a circle whose area
    follows its kits), drawn as vectors so the names of the provinces stay text in the bulletin."""
    from datetime import datetime, timedelta
    from .pdf import C, INK, MUTED, NIGHT
    total = sum(p["kits"] for p in provinces) or 1
    peak = max([p["kits"] for p in provinces] or [1]) or 1
    names = [p["provincia"] for p in provinces]
    label_w = min(118.0, max(c.stringWidth(n, "Text-Medium", 7) for n in names) + 10)
    left_w = (width - label_w) * 0.4
    right_x = x + label_w + left_w + 16
    right_w = x + width - right_x
    c.setFillColor(NIGHT); c.setFont("Text-Bold", 7.4)
    c.drawString(x + label_w, top - 7, "Total por provincia")
    c.drawString(right_x, top - 7, "Entregas en el tiempo · tamaño: kits")
    first = top - 16
    bottom = first - row * len(provinces)
    dated = []
    for d in deliveries:
        try:
            dated.append((datetime.strptime(d["date"], "%d/%m/%Y"), d))
        except (KeyError, ValueError):
            continue
    if dated:
        start = min(day for day, _d in dated) - timedelta(days=3)
        end = max(day for day, _d in dated) + timedelta(days=3)
        span = max(1, (end - start).days)

        def at(day):
            return right_x + right_w * (day - start).days / span
        tick = min(day for day, _d in dated)
        while tick <= end - timedelta(days=3):
            c.setStrokeColor(C("#EEEAF4")); c.setLineWidth(0.6); c.line(at(tick), bottom, at(tick), first)
            c.setFillColor(MUTED); c.setFont("Text-Semi", 6.4)
            c.drawCentredString(at(tick), bottom - 9, f"{tick.day} {ui._MONTHS_SHORT[tick.month - 1]}")
            tick += timedelta(days=14)
        if since:
            mark = datetime.strptime(since, "%d/%m/%Y")
            if start <= mark <= end:
                c.setStrokeColor(C(theme.ORO)); c.setLineWidth(0.9); c.setDash(2, 2)
                c.line(at(mark), bottom, at(mark), first)
                c.setDash()
                c.setFillColor(C(theme.ORO_700)); c.setFont("Text-Semi", 6.2)
                c.drawString(at(mark) + 3, bottom + 3, "Inicio del seguimiento de alertas")
        biggest = max(d["kits"] for _day, d in dated) or 1
        c.setFillColor(C(theme.VIOLETA_500)); c.setStrokeColor(C("#FFFFFF")); c.setLineWidth(0.5)
        c.setFillAlpha(0.72)
        for day, d in sorted(dated, key=lambda item: -item[1]["kits"]):
            if d["province"] in names:
                y = first - row * names.index(d["province"]) - row / 2
                c.circle(at(day), y, math.sqrt((8 + 230 * d["kits"] / biggest) / math.pi), stroke=1, fill=1)
        c.setFillAlpha(1)
    for index, p in enumerate(provinces):
        y = first - row * index - row / 2
        c.setFillColor(INK); c.setFont("Text-Medium", 7)
        c.drawRightString(x + label_w - 6, y - 2.4, p["provincia"])
        length = (left_w - 66) * p["kits"] / peak
        c.setStrokeColor(C(theme.LILA_200)); c.setLineWidth(1.4); c.setLineCap(1)
        c.line(x + label_w, y, x + label_w + length, y)
        c.setFillColor(C(theme.MORADO)); c.setStrokeColor(C("#FFFFFF")); c.setLineWidth(0.6)
        c.circle(x + label_w + length, y, 2.7, stroke=1, fill=1)
        c.setFillColor(INK); c.setFont("Text-Semi", 6.6)
        c.drawString(x + label_w + length + 6, y - 2.3, f"{number(p['kits'])} · {number(p['kits'] / total * 100, 1)} %")
    c.setLineCap(0)
    return bottom - 16


def _plan_pdf(c, plan: dict, x: float, top: float, width: float, height: float) -> None:
    """The national plan of the bonus: three figures in one gold panel."""
    from .pdf import C, NIGHT, _badge, _fit
    c.setFillColor(C(theme.ORO_100)); c.roundRect(x, top - height, width, height, 8, stroke=0, fill=1)
    c.setFillColor(C(theme.ORO)); c.rect(x, top - height + 10, 3, height - 20, stroke=0, fill=1)
    rows = [("users", number(plan["personas"]), "personas potenciales"), ("layers", number(plan["nucleos"]), "núcleos familiares potenciales"),
            ("banknote", f"USD {number(plan['monto'], 2)}", "inversión estimada")]
    step = (height - 24) / 3
    for index, (symbol, value, label) in enumerate(rows):
        y = top - 12 - index * step
        _badge(c, symbol, x + 22, y - step / 2 + 2, 9.5, fill=C(theme.ORO), variant="blanco")
        c.setFillColor(NIGHT); c.setFont("Display", _fit(value, "Display", 14, width - 50, 9))
        c.drawString(x + 38, y - step / 2 + 2, value)
        c.setFillColor(C(theme.PIZARRA)); c.setFont("Text", 7.2); c.drawString(x + 38, y - step / 2 - 8.5, label)
    c.setFillColor(C("#8A5D00")); c.setFont("Text-Semi", 6.8)
    c.drawString(x + 12, top - height + 7, "Proyección nacional · planificación, no ejecución")


def _risk_bars(c, rows, x, top, width, row_h=27):
    from .pdf import C, _fit
    total = sum(a["value"] for a in rows)
    for i, a in enumerate(rows):
        y = top - i * row_h
        pct = 100 * a["value"] / total if total else 0
        value = f"{number(a['value'])}  ·  {number(pct,1)} %"
        c.setFillColor(C(theme.MORADO_900)); c.setFont("Text-Semi", _fit(a["name"], "Text-Semi", 8.4, width-87, 6.7))
        c.drawString(x, y, a["name"])
        c.setFont("Text-Bold", 8.5); c.drawRightString(x + width, y, value)
        c.setFillColor(C(theme.LILA_50)); c.roundRect(x, y-12, width, 6.5, 3.25, fill=1, stroke=0)
        if pct > 0:
            c.setFillColor(C(theme.MORADO if i == 0 else theme.VIOLETA_500))
            c.roundRect(x, y-12, width * pct/100, 6.5, min(3.25, width*pct/200), fill=1, stroke=0)

def render_pdf(c, ctx, pages):
    from .approved_risk_pdf import render
    return render(c, ctx, pages)


def _register_page(c, ctx, pages, empty, check):
    """Every alert and every suspended unit of the selection."""
    from .pdf import M, W, _heading, _next_page, _slim_band
    from .risks import _paragraph
    full = W - 2 * M
    r = ctx["response"]
    continuity = r["continuity"]
    top = _slim_band(c, ctx, "Registro de alertas y unidades suspendidas", f"{r['scope']} · {ctx['territory_label']}") - 20
    if not r["alerts"]:
        _heading(c, "Alertas reportadas", M, top, full, r["scope"])
        top = empty("No hay alertas reportadas en la selección.", M, top - 16, full) - 24
    else:
        _heading(c, "Alertas reportadas", M, top, full, f"{_count(r['alert_count'], 'alerta')} · de la más reciente a la más antigua")
        rows = _alert_cells(r["alerts"])
        top = _pdf_table(c, top - 18, ["Alerta / registro", "Unidad de atención y servicio", "Territorio", "Afectación al servicio", "Estado"],
                         [[a["identity"], a["unit_full"], a["place_full"], a["impact"], a["state"]] for a in rows],
                         [84, 142, 62, full - 360, 72], size=7.4, padding=3) - 22
    if not continuity["groups"]:
        _heading(c, "Unidades suspendidas", M, top, full, "Corte territorial: 26/10/2026, 16:00")
        top = empty("El reporte territorial no registra unidades suspendidas en la selección.", M, top - 16, full) - 10
    else:
        _heading(c, "Unidades suspendidas", M, top, full, "Suspensión total o presencial · de la provincia con más unidades")
        rows = [[Markup(f"<b>{escape(a['province'])}</b>" + (f"<br/><font color='#6E6880'>{escape(a['canton'])}</font>" if a["canton"] else "")),
                 a["service"], number(a["units"]), a["names"] or "—"] for a in continuity["groups"]]
        rows.append(["Total", continuity["caption"], number(continuity["closed"]), ""])
        top = _pdf_table(c, top - 18, ["Provincia / cantón", "Servicio", "UA", "Unidades identificadas"], rows,
                         [104, 84, 30, full - 218], size=7.5, padding=3, align=["L", "L", "R", "L"], total=True) - 10
        top = _paragraph(c, continuity["note"], M, top, full, size=7.2) - 4
    check(top)
    _next_page(c, ctx, 2, pages)


def _actions_page(c, ctx, pages, empty, check):
    """Kits (each province and every delivery in time) and the contingency bonus (stages and plan), with the scopes."""
    from .pdf import M, W, _heading, _slim_band
    from .risks import _paragraph
    full = W - 2 * M
    half = (full - 22) / 2
    r = ctx["response"]
    top = _slim_band(c, ctx, "Kits y bono de contingencia", f"Kits: Kobo al 27/10/2026, 13:35 · bono: corte {r['bonus_cut']}") - 20
    if not r["kits_provinces"]:
        _heading(c, "Kits entregados en provincias priorizadas", M, top, full, f"Kobo al {r['kits_cut']}")
        top = empty("No hay entregas de kits en la selección.", M, top - 16, full) - 24
    else:
        _heading(c, "Kits entregados en provincias priorizadas", M, top, full,
                 f"{number(r['kits_total'])} kits · {_count(r['kit_provinces'], 'provincia')} · {_count(r['deliveries'], 'registro')} Kobo")
        top = _kits_pdf(c, r["kits_provinces"], r["kits"], r["since"], M, top - 14, full)
        top = _paragraph(c, f"Núcleos familiares reportados por entrega: {number(r['families_total'])}; no son núcleos familiares únicos.",
                         M, top, full, size=7) - 22
    strips_w = full * 0.6
    plan_x, plan_w = M + strips_w + 18, full - strips_w - 18
    _heading(c, "Bono de contingencia por provincia", M, top, strips_w, "Inundaciones · cada barra suma el 100 %")
    _heading(c, "Planificación El Niño 2026–2027", plan_x, top, plan_w)
    bottom = _strips_pdf(c, r["bonus"], M, top - 24, strips_w) if r["bonus"] else \
        empty("No hay registros del bono en la selección.", M, top - 16, strips_w)
    _plan_pdf(c, r["plan"], plan_x, top - 18, plan_w, 112)
    top = min(bottom, top - 18 - 112) - 18
    _heading(c, "Alcances y fuentes", M, top, full)
    # Each scope reads on its own, without subtitles; the geoportal closes the section as an anchored link.
    left = right = top - 18
    for text in (r["notes"]["alerts"], r["notes"]["kits"]):
        left = _paragraph(c, text, M, left, half, size=7.6) - 7
    for text in (r["notes"]["bonus"], r["notes"]["filters"], "Fuentes: " + ctx["sources"]):
        right = _paragraph(c, text, M + half + 22, right, half, size=7.6) - 7
    check(_geoportal_link(c, ctx["geoportal"], M, min(left, right) - 3, full))


def _geoportal_link(c, url: str, x: float, top: float, width: float) -> float:
    """«Más información en el geoportal…», with the name of the geoportal as a link (the address is not printed)."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from .pdf import INK
    text = (f'Más información en el <link href="{escape(url)}"><font color="{theme.MORADO}"><u><b>geoportal de unidades de atención '
            'y amenazas</b></u></font></link>.')
    para = Paragraph(text, ParagraphStyle("geo", fontName="Text", fontSize=7.8, leading=10.6, textColor=INK))
    _w, height = para.wrap(width, 100)
    para.drawOn(c, x, top - height)
    return top - height


def render_pptx(prs, ctx):
    """Up to ten slides in the language of the dashboard: cover; continuity (treemap and doughnut) and its units; alerts
    (evolution and unit chart) and their register; kits (each province beside every delivery); the bonus (native 100 %
    strips and the plan); the summary by province; three maps; scopes and sources.  A section without records in the
    selection has no slide (the bonus keeps its slide for the national plan)."""
    from lxml import etree
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Inches, Pt
    from .charts import emblem_png, map_png
    from .pptx import DISPLAY, TEXT, _box, _cover, _footer, _header, _picture, _rgb, _text
    from .pptx_areas import _table, _title
    from .risk_charts import PROVINCE_TONES, evolution_png, ink, kits_png, short_service, tone, treemap_png
    r = ctx["response"]
    continuity = r["continuity"]
    alerts = r["alerts"]
    # Only the slides the selection has content for: the bonus (its national plan), the maps and the scopes always stay.
    total = (1 + 2 * bool(continuity["closed"] and continuity["groups"]) + 2 * bool(alerts) + bool(r["kits_provinces"]) + 1
             + bool(r["actions"]) + 2 + max(0, math.ceil(len(alerts) / 7) - 1) + max(0, math.ceil(len(continuity["detail"]) / 18) - 1))
    _cover(prs, ctx, emblem_png(set(ctx["selected_codes"])), total, share_word="")

    def slide(title):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        _header(s, title, f"{r['scope']} · {ctx['territory_label']} · {ctx['programs_label']}")
        _footer(s, ctx, len(prs.slides), total)
        s.notes_slide.notes_text_frame.text = ctx["sources"]
        return s

    def empty(s, text, x=0.55, y=1.6, w=12.2):
        _text(s, x, y, w, 0.5, text, size=14, color=theme.PIZARRA)

    # 2. Where services were suspended: a treemap of provinces and cantons, and a doughnut by service.
    if continuity["closed"] and continuity["groups"]:
        s = slide("Continuidad de los servicios")
        _title(s, "Dónde se suspendió la atención", 0.55, 1.36, 7.6, "Provincia y cantón · el color indica el servicio")
        _picture(s, treemap_png(continuity["tiles"], 7.7, 4.5, dpi=200, scale=1.4), 0.5, 2.15, w=7.7)
        _title(s, "Por servicio", 8.65, 1.36, 4.2, "Participación en las unidades suspendidas")
        rows = continuity["by_service"]
        data = CategoryChartData(number_format="#,##0")
        closed = continuity["closed"] or 1
        data.categories = [f"{short_service(row['name'])} · {number(row['value'])} UA ({number(row['value'] / closed * 100, 1)} %)" for row in rows]
        data.add_series("UA suspendidas", [row["value"] for row in rows])
        chart = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(8.55), Inches(2.1), Inches(4.3), Inches(4.55), data).chart
        chart.font.name = TEXT
        chart.has_title = False
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(13)
        plot = chart.plots[0]
        for point, row in zip(plot.series[0].points, rows):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = _rgb(tone(row["name"]))
            point.format.line.color.rgb = _rgb("#FFFFFF")
            point.format.line.width = Pt(3)
        doughnut = chart._chartSpace.xpath(".//c:doughnutChart")[0]
        hole = doughnut.find(qn("c:holeSize"))
        if hole is None:
            hole = etree.SubElement(doughnut, qn("c:holeSize"))
        hole.set("val", "58")
        _text(s, 8.55, 3.55, 4.3, 0.6, number(continuity["closed"]), size=32, color=theme.MORADO_900, font=DISPLAY, bold=True,
              align=PP_ALIGN.CENTER)
        _text(s, 8.55, 4.15, 4.3, 0.35, "UA suspendidas", size=12, color=theme.PIZARRA, align=PP_ALIGN.CENTER)
        _text(s, 0.55, 6.72, 12.2, 0.3, continuity["note"], size=9.5, color=theme.PIZARRA)

        # 3. Full nominal directory, paginated as the territorial source grows.
        for start in range(0, len(continuity["detail"]), 18):
            s = slide(f"Unidades suspendidas · {start // 18 + 1}")
            part = continuity["detail"][start:start+18]
            _table(s, .55, 1.45, 12.25, [("Provincia", "provincia", 1.5, "text"), ("Cantón", "canton", 1.6, "text"),
                   ("Servicio", "servicio", 2.1, "text"), ("Unidad de atención", "unidad", None, "text")],
                   part, row_h=.26, header_h=.4, size=9)

    # 4. When and where alerts were registered: evolution and unit chart.
    if alerts:
        s = slide("Alertas en servicios MTDH")
        _title(s, "Evolución de las alertas", 0.55, 1.36, 7.4, f"Registradas cada día y acumuladas desde el {r['since']}")
        _picture(s, evolution_png(r["daily"], 7.6, 4.3, dpi=200, scale=1.45), 0.45, 2.15, w=7.6)
        _title(s, "Cada alerta, una unidad", 8.45, 1.36, 4.4, "Por provincia · el color indica el servicio")
        counts: dict[str, int] = {}
        for a in alerts:
            counts[a["province"]] = counts.get(a["province"], 0) + 1
        provinces = sorted(counts, key=lambda p: -counts[p])
        services = sorted({a["service"] for a in alerts}, key=lambda name: -sum(1 for a in alerts if a["service"] == name))
        rank = {name: i for i, name in enumerate(services)}
        size, gap = 0.33, 0.07
        for i, province in enumerate(provinces[:6]):
            y = 2.35 + i * 0.55
            _text(s, 8.45, y + 0.02, 1.2, 0.4, province, size=13, color=theme.MORADO_900, bold=True)
            _text(s, 9.6, y + 0.02, 0.35, 0.4, str(counts[province]), size=13, color=theme.PIZARRA)
            part = sorted((a for a in alerts if a["province"] == province), key=lambda a: (rank[a["service"]], a["date"], a["code"]))
            for j, a in enumerate(part[:7]):
                _box(s, 10.0 + j * (size + gap), y, size, size, tone(a["service"]), shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
        y = 2.35 + min(len(provinces), 6) * 0.55 + 0.1
        x = 8.45
        for service_index, name in enumerate(services):
            x = 8.45 + (service_index % 2) * 2.3
            legend_y = y + (service_index // 2) * 0.35
            _box(s, x, legend_y + 0.06, 0.2, 0.2, tone(name), shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
            label = f"{short_service(name)} · {sum(1 for a in alerts if a['service'] == name)}"
            _text(s, x + 0.27, legend_y, 2.1, 0.35, label, size=11, color=theme.PIZARRA)
            x += 0.27 + 0.105 * len(label) + 0.3
        _text(s, 0.55, 6.62, 12.2, 0.4, r["count_note"], size=11, color=theme.PIZARRA)

        # 5. The register of alerts.
        for start in range(0, len(alerts), 7):
            part = alerts[start:start + 7]
            s = slide(f"Registro de alertas · {start // 7 + 1}")
            _table(s, 0.5, 1.4, 12.33, [("Alerta / fecha", "identity", 1.55, "text"), ("Unidad y servicio", "unit_full", 3.15, "text"),
                   ("Territorio", "place_full", 1.45, "text"), ("Situación reportada", "impact", None, "text"), ("Estado", "status", 1.3, "text")],
                   _alert_cells(part, markup=False), row_h=0.65, header_h=0.42, size=9)

    # 6. Kits: each province beside every delivery in time.
    if r["kits_provinces"]:
        s = slide("Kits entregados en provincias priorizadas")
        _title(s, f"{number(r['kits_total'])} kits en {_count(r['kit_provinces'], 'provincia')}", 0.55, 1.36, 12.2,
               f"{_count(r['deliveries'], 'registro')} Kobo · corte 27/10/2026, 13:35 · cada círculo es una entrega y su tamaño indica los kits")
        # As tall as its provinces need (a few provinces do not stretch over the whole slide).
        height = min(4.55, max(1.7, 0.21 * len(r["kits_provinces"]) + 1.0))
        _picture(s, kits_png(r["kits_provinces"], r["kits"], r["since"], 12.2, height, dpi=200, scale=1.3), 0.55, 2.1, w=12.2)
        _text(s, 0.55, min(6.68, 2.1 + height + 0.2), 12.2, 0.3,
              f"Núcleos familiares reportados por entrega: {number(r['families_total'])}; no son núcleos familiares únicos.",
              size=10, color=theme.PIZARRA)

    # 7. The contingency bonus: native 100 % strips by province and the national plan.
    s = slide("Bono de contingencia")
    bonus = r["bonus"]
    stages = [("Pago gestionado", "managed", "managed_amount", "núcleos familiares"),
              ("En articulación", "articulation", "articulation_amount", "personas")]
    stages = [st_ for st_ in stages if sum(b[st_[1]] for b in bonus)]
    if stages:
        _title(s, "Cada etapa, por provincia", 0.55, 1.36, 7.7, "Inundaciones · cada barra suma el 100 % de su etapa; las etapas no se suman")
        weight = {b["name"]: sum(b[key] / (sum(x[key] for x in bonus) or 1) for _n, key, _a, _u in stages) for b in bonus}
        order = sorted(weight, key=lambda name: -weight[name])
        data = CategoryChartData(number_format="#,##0")
        data.categories = [f"{title}\n{number(sum(b[key] for b in bonus))} {unit} · USD {number(sum(b[amount] for b in bonus), 2)}"
                           for title, key, amount, unit in stages]
        for name in order:
            data.add_series(name, [next((b[key] for b in bonus if b["name"] == name), 0) or None for _t, key, _a, _u in stages])
        chart = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED_100, Inches(0.45), Inches(2.05), Inches(7.9), Inches(3.9), data).chart
        chart.font.name = TEXT
        chart.font.size = Pt(12)
        chart.has_title = False  # a single province would otherwise title the chart with its name
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.value_axis.visible = False
        chart.value_axis.has_major_gridlines = False
        chart.category_axis.reverse_order = True
        chart.category_axis.format.line.fill.background()
        chart.plots[0].gap_width = 70
        chart.plots[0].overlap = 100
        for series, name in zip(chart.series, order):
            color = PROVINCE_TONES.get(name, theme.LILA_200)
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = _rgb(color)
            series.format.line.color.rgb = _rgb("#FFFFFF")
            series.format.line.width = Pt(2)
            series.data_labels.show_value = True
            series.data_labels.number_format = '#,##0;-#,##0;""'
            series.data_labels.number_format_is_linked = False
            series.data_labels.position = XL_LABEL_POSITION.CENTER
            series.data_labels.font.size = Pt(12)
            series.data_labels.font.bold = True
            series.data_labels.font.color.rgb = _rgb(ink(color))
            # A segment under 5 % of its stage keeps its colour but not its figure, which would spill out of the bar.
            for index, (_t, key, _a, _u) in enumerate(stages):
                value = next((b[key] for b in bonus if b["name"] == name), 0)
                if value and value / (sum(b[key] for b in bonus) or 1) < 0.05:
                    label = series._element.get_or_add_dLbls().get_or_add_dLbl_for_point(index)
                    for child in list(label):
                        if child.tag != qn("c:idx"):
                            label.remove(child)
                    etree.SubElement(label, qn("c:delete")).set("val", "1")
    else:
        empty(s, "Sin registros del bono en la selección.", w=7.7)
    plan = r["plan"]
    _title(s, "Planificación El Niño 2026–2027", 8.75, 1.36, 4.1, "Proyección nacional · planificación, no ejecución")
    tiles = [("Personas potenciales", number(plan["personas"])), ("Núcleos familiares potenciales", number(plan["nucleos"])),
             ("Inversión estimada", f"USD {number(plan['monto'], 2)}")]
    for index, (label, value) in enumerate(tiles):
        y = 2.15 + index * 1.25
        _box(s, 8.75, y, 4.1, 1.08, theme.ORO_100, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        _box(s, 8.75, y + 0.16, 0.07, 0.76, theme.ORO)
        _text(s, 9.05, y + 0.1, 3.7, 0.3, label, size=11.5, color=theme.PIZARRA, bold=True)
        _text(s, 9.05, y + 0.4, 3.7, 0.5, value, size=22, color=theme.MORADO_900, font=DISPLAY, bold=True)
    _text(s, 0.55, 6.25, 12.2, 0.7, r["notes"]["bonus"], size=9.5, color=theme.PIZARRA)

    # 8. The summary by province.
    actions = [{**a, "kits_t": _dash(number(a["kits"])), "managed_t": _dash(number(a["managed"])), "managed_usd": _dash(number(a["managed_amount"], 2)),
                "articulation_t": _dash(number(a["articulation"])), "articulation_usd": _dash(number(a["articulation_amount"], 2))}
               for a in r["actions"]]
    if actions:
        s = slide("Resumen por provincia")
        _title(s, "Acciones del Ministerio en cada provincia", 0.55, 1.36, 12.2,
               f"{_count(len(actions), 'provincia')} · kits, bono gestionado (núcleos familiares) y casos en articulación (personas)")
        per = (len(actions) + 1) // 2 if len(actions) > 10 else len(actions)
        columns = [("Provincia", "name", None, "text"), ("Kits", "kits_t", 0.75, "num"), ("Bono", "managed_t", 0.65, "num"),
                   ("USD gestionado", "managed_usd", 1.15, "num"), ("Artic.", "articulation_t", 0.65, "num"),
                   ("USD articulación", "articulation_usd", 1.2, "num")]
        for i in range(0, len(actions), per):
            _table(s, 0.55 + (i // per) * 6.2, 2.05, 6.0, columns, actions[i:i + per], row_h=min(0.4, 4.45 / per), header_h=0.45, size=9.5)

    # 9. Three maps: alerts, suspended units and kits.
    s = slide("Respuesta en el territorio")
    for i, (key, title) in enumerate([("map_values", "Alertas reportadas"), ("suspended_map_values", "UA suspendidas"),
                                      ("kits_map_values", "Kits entregados")]):
        x = 0.5 + i * 4.15
        _title(s, title, x, 1.36, 4.0)
        pic = map_png(ctx[key], layer="provincia", selected=set(ctx["selected_codes"]), mode="light", label=title, marks=False,
                      width=4.0, height=4.6, dpi=180)
        _picture(s, pic, x, 1.95, w=4.0)

    # 10. Scopes and sources: each scope reads on its own, without subtitles, in two columns that flow by themselves; the
    # geoportal closes the left column as a link.
    s = slide("Nota metodológica y fuentes")
    columns = [([r["notes"]["alerts"], r["notes"]["kits"]] + ([continuity["note"]] if continuity["closed"] else []), ctx["geoportal"]),
               ([r["notes"]["bonus"], r["notes"]["filters"], "Fuentes: " + ctx["sources"]], None)]
    for index, (texts, link) in enumerate(columns):
        frame = s.shapes.add_textbox(Inches(0.55 + index * 6.25), Inches(1.45), Inches(5.95), Inches(5.0)).text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        for number_, text in enumerate(texts):
            paragraph = frame.paragraphs[0] if number_ == 0 else frame.add_paragraph()
            paragraph.space_after = Pt(10)
            run = paragraph.add_run()
            run.text = text
            run.font.size = Pt(12.5)
            run.font.name = TEXT
            run.font.color.rgb = _rgb(theme.TINTA)
        if link:
            paragraph = frame.add_paragraph()
            paragraph.space_before = Pt(6)
            for text, url in [("Más información en el ", None), ("geoportal de unidades de atención y amenazas", link), (".", None)]:
                run = paragraph.add_run()
                run.text = text
                run.font.size = Pt(13.5)
                run.font.name = TEXT
                run.font.color.rgb = _rgb(theme.MORADO if url else theme.PIZARRA)
                if url:
                    run.font.bold = True
                    run.font.underline = True
                    run.hyperlink.address = url
    assert len(prs.slides) == total


def render_workbook(book):
    """Workbook in the language of the dashboard.  Resumen: the five key figures in one row, the continuity of the services
    (a doughnut by service beside the tables by service and province), the evolution of the alerts, three maps and the
    findings.  Then every suspended unit, every alert (real dates, to sort and filter), the daily evolution (columns over
    the running total on a date axis), kits by province beside the running total of the deliveries, every Kobo delivery,
    the bonus (a 100 % bar per stage drawn from its own table) with the national plan, the actions in each province and
    the technical sheet.  Every chart is native and editable, and each kind of chart is used once."""
    from datetime import datetime
    from .charts import map_png
    from .excel import DISPLAY, INT, MUTED, SOFT_LINE, TEXT, WHITE
    from .excel_areas import _block, _layout, _sheet
    from .risk_charts import PROVINCE_TONES, short_service, tone
    ctx = book.ctx
    r = ctx["response"]
    continuity = r["continuity"]
    closed = continuity["closed"]
    accents = {"oro": theme.ORO, "violeta": theme.VIOLETA_500, "lila": theme.LILA_300, "morado": theme.MORADO, "fucsia": theme.FUCSIA}

    def day(text):
        try:
            return datetime.strptime(text, "%d/%m/%Y")
        except (TypeError, ValueError):
            return None

    def framed(chart, title, width, height, legend=None):
        chart.set_title({"name": title, "overlay": False, "name_font": {"name": DISPLAY, "size": 11, "bold": True, "color": theme.MORADO_900}})
        chart.set_chartarea({"border": {"color": SOFT_LINE}, "fill": {"color": WHITE}})
        chart.set_plotarea({"border": {"none": True}, "fill": {"none": True}})
        chart.set_legend({"position": legend, "font": {"name": TEXT, "size": 9, "color": theme.TINTA}} if legend else {"none": True})
        chart.set_size({"width": width, "height": height})
        return chart

    def axis_font(size=8.5, color=MUTED):
        return {"name": TEXT, "size": size, "color": color}

    def grid():
        return {"visible": True, "line": {"color": "#EEEAF4", "width": 0.75}}

    def label(ws, row, col, text, last=None):
        fmt = book.f(font_name=DISPLAY, font_size=10.5, bold=True, font_color=theme.MORADO_900)
        if last and last > col:
            ws.merge_range(row, col, row, last, text, fmt)
        else:
            ws.write(row, col, text, fmt)
        ws.set_row(row, 22)
        return row + 1

    def evolution_chart(first, end, width, height):
        """Alerts registered each day (gold columns) over their running total (purple line), on a date axis."""
        columns = book.wb.add_chart({"type": "column"})
        columns.add_series({"name": "Registradas en el día", "categories": ["Evolución", first, 1, end, 1],
                            "values": ["Evolución", first, 2, end, 2], "fill": {"color": theme.ORO}, "border": {"none": True}, "gap": 40,
                            "data_labels": {"value": True, "num_format": '#,##0;-#,##0;""', "position": "outside_end",
                                            "font": {"name": TEXT, "size": 8.5, "bold": True, "color": theme.ORO_700}}})
        line = book.wb.add_chart({"type": "line"})
        line.add_series({"name": "Acumuladas", "categories": ["Evolución", first, 1, end, 1], "values": ["Evolución", first, 3, end, 3],
                         "line": {"color": theme.MORADO, "width": 2.25}, "marker": {"type": "none"}})
        columns.combine(line)
        start, stop = day(r["daily"][0]["date"]), day(r["daily"][-1]["date"])
        columns.set_x_axis({"date_axis": True, "min": start, "max": stop, "major_unit": 7, "major_unit_type": "days", "num_format": "dd/mm",
                            "num_font": {**axis_font(), "rotation": 0}, "line": {"color": theme.LILA_100}, "major_tick_mark": "none"})
        columns.set_y_axis({"num_format": INT, "num_font": axis_font(), "min": 0, "line": {"none": True}, "major_gridlines": grid(),
                            "major_tick_mark": "none"})
        return framed(columns, "Alertas registradas cada día y acumuladas", width, height, "top")

    def empty(ws, row, text, last):
        return book.note(ws, row, text, first=1, last=last, height=30)

    # ------------------------------------------------------------------ Resumen
    summary = book.wb.add_worksheet("Resumen")
    book.widths(summary, [2.4] + [10.2] * 15 + [2.4])
    book.page(summary, tall=1)
    summary.set_tab_color(theme.MORADO)
    row = book.band(summary, ctx["title"], book.subtitle(), last=16)
    row = book.heading(summary, row + 1, "Cifras clave", ctx["period_label"], last=15)
    cards = [(k["label"], k["value"], book.kpi_format(k), k.get("note", ""), accents.get(k.get("tone"), theme.MORADO)) for k in ctx["kpis"]]
    row = book.kpi_row(summary, row + 1, cards, first=1, last=15) + 1
    row = book.heading(summary, row, "Continuidad de los servicios",
                       f"{number(closed)} UA suspendidas · corte territorial: 26/10/2026, 16:00" if closed else "Corte territorial: 26/10/2026, 16:00",
                       last=15)
    if closed:
        top = row + 1
        services = [{"name": short_service(x["name"]), "value": x["value"], "share": x["value"] / closed} for x in continuity["by_service"]]
        provinces = [{"name": x["name"], "value": x["value"], "share": x["value"] / closed} for x in continuity["by_province"]]
        left = label(summary, top, 1, "Por servicio", last=7)
        layout = [("Servicio", "name", "text", 1, 3), ("UA suspendidas", "value", "int", 4, 2), ("Participación", "share", "pct", 6, 2)]
        s_first, s_end, left = book.table(summary, left, layout, services, total={"value": closed, "share": 1.0}, header_height=30, height=21)
        left = label(summary, left + 1, 1, "Por provincia", last=7)
        p_first, p_end, left = book.table(summary, left, [("Provincia", "name", "text", 1, 3), *layout[1:]], provinces,
                                          total={"value": closed, "share": 1.0}, header_height=30, height=21)
        book.data_bar(summary, p_first, p_end, 6, theme.LILA_300, maximum=1)
        doughnut = book.wb.add_chart({"type": "doughnut"})
        doughnut.add_series({"name": "UA suspendidas", "categories": ["Resumen", s_first, 1, s_end, 1], "values": ["Resumen", s_first, 4, s_end, 4],
                             "points": [{"fill": {"color": tone(x["name"])}, "border": {"color": WHITE, "width": 2.5}} for x in services],
                             "data_labels": {"value": True, "percentage": True, "separator": "\n",
                                             "font": {"name": TEXT, "size": 10, "bold": True, "color": WHITE},
                                             "custom": [{"font": {"name": TEXT, "size": 10, "bold": True,
                                                                  "color": theme.MORADO_900 if tone(x["name"]) == theme.LILA_300 else WHITE}}
                                                        for x in services]}})
        doughnut.set_hole_size(55)
        # Row heights are points: the doughnut spans the two tables at its left (labels, headers, rows, totals and the gap).
        block = 2 * (22 + 30 + 22) + 15 + 21 * (len(services) + len(provinces))
        summary.insert_chart(top, 9, framed(doughnut, "UA suspendidas por servicio", 532, round(block * 4 / 3) - 4, "right"),
                             {"x_offset": 4, "y_offset": 2})
        row = max(left, top + 13) + 1
    else:
        row = empty(summary, row + 1, "El reporte territorial no registra unidades suspendidas en la selección.", 15) + 1
    evolution_row = book.heading(summary, row, "Evolución de las alertas",
                                 f"{_count(r['alert_count'], 'alerta')} reportada · desde el {r['since']}", last=15)
    if r["alerts"]:
        row = evolution_row + 16
    else:
        row = empty(summary, evolution_row + 1, "No hay alertas reportadas en la selección.", 15) + 1
    for index, (key, title) in enumerate([("map_values", "Alertas reportadas"), ("suspended_map_values", "UA suspendidas"),
                                          ("kits_map_values", "Kits entregados")]):
        picture = map_png(ctx[key], layer="provincia", selected=set(ctx["selected_codes"]), mode="light", label=title, marks=False,
                          width=3.4, height=3.4, dpi=150)
        book.heading(summary, row, title, first=1 + index * 5, last=4 + index * 5)
        book.image(summary, row + 1, 1 + index * 5, picture, 318, f"{key}.png", description=f"Mapa del Ecuador: {title.lower()}")
    row = book.findings(summary, row + 18, ctx["insights"], last=15)
    summary.print_area(0, 0, row, 16)
    summary.activate()
    summary.set_first_sheet()
    summary.set_zoom(90)

    # ------------------------------------------------------- every suspended unit
    ws, row = _sheet(book, "Unidades suspendidas", theme.FUCSIA, "Unidades de atención suspendidas", [2.4, 24, 22, 12, 46, 24, 13, 2.4])
    weight: dict[str, int] = {}
    for d in continuity["detail"]:
        weight[d["provincia"]] = weight.get(d["provincia"], 0) + int(d["unidades"])
    detail = sorted(continuity["detail"], key=lambda d: (-weight[d["provincia"]], d["provincia"], not d["canton"], d["canton"], d["servicio"], d["unidad"]))
    if detail:
        _block(book, ws, row + 1, _count(closed, 'unidad suspendida', 'unidades suspendidas'),
               [("Provincia", "provincia", "text"), ("Cantón", "canton", "text"), ("Servicio", "servicio", "text"),
                ("Unidad de atención", "unidad", "text"), ("Estado de atención", "estado", "text"), ("Unidades", "unidades", "int")],
               [{**d, "canton": d["canton"] or "—", "unidad": d["unidad"] or "—"} for d in detail], note=continuity["note"], last=6,
               autofilter=True, total={"unidades": sum(int(d["unidades"]) for d in detail)})
    else:
        empty(ws, row + 1, "El reporte territorial no registra unidades suspendidas en la selección.", 6)

    # ------------------------------------------------------------- every alert
    ws, row = _sheet(book, "Alertas", theme.ORO, "Alertas reportadas", [2.4, 19, 13, 13, 16, 11, 40, 30, 58, 16, 11, 2.4])
    if r["alerts"]:
        alerts = [{**a, "day": day(a["date"]) or a["date"]} for a in r["alerts"]]
        first, _end, _next = _block(book, ws, row + 1, f"{_count(r['alert_count'], 'alerta')} · de la más reciente a la más antigua",
                                    [("Alerta", "code", "text"), ("Fecha de registro", "day", "date"), ("Provincia", "province", "text"),
                                     ("Cantón", "canton", "text"), ("Código UA", "ua", "center"), ("Unidad de atención", "unit", "text"),
                                     ("Servicio", "service", "text"), ("Afectación al servicio", "impact", "text"), ("Estado", "status", "text"),
                                     ("Prioridad", "priority", "text")], alerts, note=r["count_note"], last=10, autofilter=True)
        for index, a in enumerate(alerts):
            lines = max(1, math.ceil(len(a["impact"]) / 56), math.ceil(len(a["unit"]) / 38), math.ceil(len(a["service"]) / 28),
                        math.ceil(len(a["province"]) / 12), math.ceil(len(a["canton"]) / 12))
            ws.set_row(first + index, max(21, 14 * lines + 7))
    else:
        empty(ws, row + 1, "No hay alertas reportadas en la selección.", 10)

    # ---------------------------------------------------------- the evolution
    ws, row = _sheet(book, "Evolución", theme.ORO, "Evolución de las alertas", [2.4, 14, 20, 15, 3] + [11.0] * 9 + [2.4])
    if r["alerts"]:
        daily = [{**d, "day": day(d["date"]) or d["date"]} for d in r["daily"]]
        first, end, _next = _block(book, ws, row + 1, f"Desde el {r['since']}", [("Fecha", "day", "date"),
                                   ("Registradas en el día", "daily", "int"), ("Acumuladas", "total", "int")], daily, last=3, autofilter=True,
                                   total={"daily": sum(d["daily"] for d in r["daily"])})
        ws.insert_chart(row + 1, 5, evolution_chart(first, end, 736, 360), {"x_offset": 6, "y_offset": 6})
        summary.insert_chart(evolution_row, 1, evolution_chart(first, end, 1140, 290), {"y_offset": 6})
    else:
        empty(ws, row + 1, "No hay alertas reportadas en la selección.", 13)

    # ------------------------------------------------- kits: provinces and time
    ws, row = _sheet(book, "Kits", theme.VIOLETA_500, "Kits entregados en provincias priorizadas", [2.4, 28, 11, 14, 18, 12, 3] + [11.0] * 7 + [2.4])
    kits_sheet = ws
    total_kits = r["kits_total"] or 1
    provinces = [{"name": p["provincia"], "kits": p["kits"], "share": p["kits"] / total_kits, "families": p["familias"],
                  "records": p["registros"]} for p in r["kits_provinces"]]
    kits_top = row + 1
    if provinces:
        _first, _end, row = _block(book, ws, kits_top, "Por provincia", [("Provincia", "name", "text"), ("Kits", "kits", "int"),
                                   ("Participación", "share", "pct"), ("Núcleos familiares reportados*", "families", "int"),
                                   ("Registros Kobo", "records", "int")], provinces, last=5, bar="share",
                                   note=f"Kobo · corte {r['kits_cut_full']}", total={"kits": r["kits_total"], "share": 1.0, "families": r["families_total"], "records": r["deliveries"]})
        ws.merge_range(row + 1, 1, row + 1, 5, "* Núcleos familiares reportados por entrega; no son núcleos familiares únicos. "
                       "Cada entrega, en la hoja Entregas Kobo.", book.f(font_size=9.5, font_color=theme.PIZARRA, text_wrap=True, valign="top"))
        ws.set_row(row + 1, 30)
    else:
        empty(ws, kits_top, "No hay entregas de kits en la selección.", 13)

    ws, row = _sheet(book, "Entregas Kobo", theme.VIOLETA_500, "Cada entrega de kits", [2.4, 13, 29, 30, 10, 15, 22, 15, 2.4])
    if r["kits"]:
        row = book.heading(ws, row + 1, f"{_count(r['deliveries'], 'entrega registrada', 'entregas registradas')} en Kobo", f"Kobo · corte {r['kits_cut_full']}", last=7)
        row = book.note(ws, row, r["notes"]["kits"], first=1, last=7, height=46)
        ws.set_row(row, 8)
        running, deliveries = 0, []
        for k in r["kits"]:
            running += k["kits"]
            deliveries.append({**k, "day": day(k["date"]) or k["date"], "running": running})
        layout = _layout([("Fecha", "day", "date"), ("Provincia", "province", "text"), ("Cantón", "canton", "text"), ("Kits", "kits", "int"),
                          ("Kits acumulados", "running", "int"), ("Núcleos familiares reportados*", "families", "int"), ("ID Kobo", "id", "center")])
        first, end, _next = book.table(ws, row + 1, layout, deliveries, total={"kits": r["kits_total"], "families": r["families_total"]},
                                       header_height=36, height=19)
        ws.autofilter(row + 1, 1, end, 7)
        dated = [d["day"] for d in deliveries if isinstance(d["day"], datetime)]
        if provinces and len(dated) == len(deliveries):
            # The running total of the kits, one point per delivery (a vertical rise when several share a day).
            chart = book.wb.add_chart({"type": "scatter", "subtype": "straight_with_markers"})
            chart.add_series({"name": "Kits acumulados", "categories": ["Entregas Kobo", first, 1, end, 1],
                              "values": ["Entregas Kobo", first, 5, end, 5], "line": {"color": theme.MORADO, "width": 2.25},
                              "marker": {"type": "circle", "size": 5, "fill": {"color": theme.VIOLETA_500}, "border": {"color": WHITE}},
                              "data_labels": {"value": True, "num_format": INT, "position": "above",
                                              "font": {"name": TEXT, "size": 9, "bold": True, "color": theme.MORADO_900},
                                              "custom": [{"delete": True}] * (len(deliveries) - 1) + [None]}})
            serial = lambda d: (d - datetime(1899, 12, 30)).days
            start, stop = min(dated), max(dated)
            chart.set_x_axis({"min": serial(start) - 2, "max": serial(stop) + 2, "major_unit": 7, "num_format": "dd/mm",
                              "num_font": {**axis_font(), "rotation": 0}, "line": {"color": theme.LILA_100}, "major_tick_mark": "none",
                              "major_gridlines": {"visible": False}})
            chart.set_y_axis({"num_format": INT, "num_font": axis_font(), "min": 0, "line": {"none": True}, "major_gridlines": grid(),
                              "major_tick_mark": "none"})
            # As tall as the table beside it (heading, header, rows and total; row heights are points).
            height = round((27 + 36 + 19 * len(provinces) + 22) * 4 / 3)
            kits_sheet.insert_chart(kits_top, 7, framed(chart, "Kits acumulados por fecha de entrega", 574, height), {"x_offset": 6})
    else:
        empty(ws, row + 1, "No hay entregas de kits en la selección.", 7)

    # ---------------------------------------------------------------- the bonus
    ws, row = _sheet(book, "Bono", theme.ORO, "Bono de contingencia", [2.4, 24, 22, 22, 22, 24, 2.4], landscape=False)
    ws.fit_to_pages(1, 1)
    bonus = r["bonus"]
    if bonus:
        first, end, row = _block(book, ws, row + 1, "Por provincia", [("Provincia", "name", "text"),
                                 ("Pago gestionado (núcleos familiares)", "managed", "int_dash"), ("En articulación (personas)", "articulation", "int_dash"),
                                 ("Monto gestionado (USD)", "managed_amount", "usd_dash"), ("Monto en articulación (USD)", "articulation_amount", "usd_dash")],
                                 bonus, last=5, note=f"Pagos gestionados desde el {r['bonus_since']} · articulación al {r['bonus_cut']}",
                                 total={"managed": r["managed_people"], "articulation": r["articulation_people"], "managed_amount": r["managed_amount"],
                                        "articulation_amount": r["articulation_amount"]})
        header = first - 1
        stages = [r["managed_people"], r["articulation_people"]]
        chart = book.wb.add_chart({"type": "bar", "subtype": "percent_stacked"})
        for index, b in enumerate(bonus):
            color = PROVINCE_TONES.get(b["name"], theme.LILA_200)
            shares = [value / whole if whole else 0 for value, whole in zip((b["managed"], b["articulation"]), stages)]
            chart.add_series({"name": ["Bono", first + index, 1], "categories": ["Bono", header, 2, header, 3],
                              "values": ["Bono", first + index, 2, first + index, 3], "fill": {"color": color},
                              "border": {"color": WHITE, "width": 1.5}, "gap": 60,
                              "data_labels": {"value": True, "num_format": '#,##0;-#,##0;""',
                                              "custom": [None if share >= 0.05 else {"delete": True} for share in shares],
                                              "font": {"name": TEXT, "size": 10, "bold": True,
                                                       "color": theme.MORADO_900 if color in (theme.LILA_300, theme.ORO, theme.FUCSIA_300) else WHITE}}})
        chart.set_y_axis({"reverse": True, "num_font": axis_font(10, theme.TINTA), "line": {"none": True}, "major_tick_mark": "none"})
        chart.set_x_axis({"visible": False, "major_gridlines": {"visible": False}})
        ws.insert_chart(row + 1, 1, framed(chart, "Cada etapa, por provincia (cada barra suma el 100 %)", 823, 250, "bottom"), {"y_offset": 4})
        row += 15
    else:
        row = empty(ws, row + 1, "No hay registros del bono de contingencia en la selección.", 5) + 1
    plan = r["plan"]
    row = book.heading(ws, row + 1, "Planificación El Niño 2026–2027", "Proyección nacional · planificación, no ejecución", last=5)
    edge = dict(left=5, left_color=theme.ORO)
    for label_text, value, fmt in [("Personas potenciales", plan["personas"], INT), ("Núcleos familiares potenciales", plan["nucleos"], INT),
                                   ("Inversión estimada", plan["monto"], '"USD "#,##0.00')]:
        ws.set_row(row, 30)
        ws.merge_range(row, 1, row, 2, label_text, book.f(bg_color=theme.ORO_100, bold=True, font_color=theme.PIZARRA, indent=1, **edge))
        ws.merge_range(row, 3, row, 5, None, book.f(bg_color=theme.ORO_100))
        ws.write_number(row, 3, value, book.f(bg_color=theme.ORO_100, font_name=DISPLAY, font_size=15, bold=True, font_color=theme.MORADO_900,
                                              num_format=fmt, align="right", indent=1))
        row += 1

    # ------------------------------------------------------ actions by province
    ws, row = _sheet(book, "Provincias", theme.MORADO, "Acciones del Ministerio en cada provincia", [2.4, 26, 50, 11, 20, 20, 20, 22, 2.4])
    actions = r["actions"]
    if actions:
        first, _end, _next = _block(book, ws, row + 1, f"{_count(len(actions), 'provincia')} con acciones · kits y bono de contingencia",
                                    [("Provincia", "name", "text"), ("Cantones", "cantons", "text"), ("Kits", "kits", "int_dash"),
                                     ("Bono gestionado (núcleos familiares)", "managed", "int_dash"), ("Monto gestionado (USD)", "managed_amount", "usd_dash"),
                                     ("En articulación (personas)", "articulation", "int_dash"),
                                     ("Monto en articulación (USD)", "articulation_amount", "usd_dash")],
                                    actions, last=7, autofilter=True, note="Cada acción conserva su unidad; no se suman entre sí",
                                    total={k: sum(a[k] for a in actions) for k in ("kits", "managed", "managed_amount", "articulation", "articulation_amount")})
        for index, a in enumerate(actions):
            ws.set_row(first + index, max(21, 14 * max(1, math.ceil(len(a["cantons"]) / 50)) + 7))
    else:
        empty(ws, row + 1, "Las provincias de la consulta no registran acciones del Ministerio en este seguimiento.", 7)

    # --------------------------------------------------------- technical sheet
    ws, row = _sheet(book, "Ficha técnica", theme.PIZARRA, "Nota metodológica y fuentes", [2.4, 34, 112, 2.4], landscape=False)
    for label_text, text in ctx["scope"] + [("Fuentes", ctx["sources"]), ("Conteo", r["count_note"]), ("Geoportal", ctx["geoportal"]),
                                            ("Continuidad de atención", continuity["note"])] + _notes(ctx):
        ws.set_row(row, max(32, math.ceil(len(text) / 95) * 15 + 12))
        ws.write(row, 1, label_text, book.f(bold=True, font_color=theme.MORADO, text_wrap=True, valign="top", bg_color=theme.LILA_50))
        if label_text == "Geoportal":
            # The name of the geoportal is the link; the address travels in the tip of the cell.
            ws.write_url(row, 2, text, book.f(valign="top", font_size=10, bold=True, underline=1, font_color=theme.MORADO),
                         string="Más información en el geoportal de unidades de atención y amenazas", tip=text)
        else:
            ws.write(row, 2, text, book.f(text_wrap=True, valign="top", font_size=10))
        row += 1
    ws.print_area(0, 0, row, 3)
