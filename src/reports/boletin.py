"""The period bulletin («Informe de gestión»): what the Ministry delivered from January to the latest month, or in the
government period, told with figures that read at a glance.

Each page tells one story with its own forms — a ring for who receives each bonus, a mosaic for where the accrued
budget went, an area for the months, dark panels with the key figures of El Niño, maps, lollipops, a waffle, gauges for
the budget and a time line for the coverage of each base — instead of a wall of bars and tables.
"""
from __future__ import annotations

import math
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as pdf_canvas

from src import theme
from src.data import MONTHS
from .context import PRODUCT, millions, number

C = colors.HexColor
W, H = A4
M = 34
PALETTE = [theme.SERIE_BONOS, theme.VIOLETA_500, theme.LILA_300, theme.ORO, theme.FUCSIA, theme.LILA_200, theme.MORADO_900,
           theme.VIOLETA_400, theme.ORO_700, theme.LILA_100]


def _fmt(value, kind: str = "count") -> str:
    if value is None:
        return "—"
    if kind == "money":
        return f"USD {millions(value, 1)} M"
    if kind == "rate":
        return f"{number(value, 1)} %"
    return number(value)


def _compact(value: float) -> str:
    if value >= 1e6:
        return f"{number(value / 1e6, 2)} M"
    if value >= 1e4:
        return f"{number(value / 1e3, 0)} mil"
    return number(value)


# ------------------------------------------------------------------------------------------------ primitives
def title(c, text: str, x: float, y: float, width: float, note: str = "") -> None:
    """A chart title in the display face with its note under it (never cut: the note shrinks to fit)."""
    c.setFillColor(C(theme.MORADO_900))
    c.setFont("Display-Bold", 10.5)
    c.drawString(x, y, text)
    if note:
        size = 7.2
        while size > 5.8 and c.stringWidth(note, "Text", size) > width:
            size -= 0.2
        c.setFillColor(C("#6E6880"))
        c.setFont("Text", size)
        c.drawString(x, y - 11, note)


def area(c, x: float, y: float, w: float, h: float, labels: list[str], values: list[float], *, color=theme.SERIE_BONOS,
         fill=theme.LILA_100, fmt=_compact) -> None:
    """A month series as a filled area with its points; the first, the highest and the last figure are written."""
    if not values:
        return
    low = min(values)
    high = max(values)
    floor = max(0.0, low - (high - low) * 1.4) if high > 0 else 0
    span = (high - floor) or 1
    step = w / max(1, len(values) - 1)
    points = [(x + i * step, y + 14 + (v - floor) / span * (h - 34)) for i, v in enumerate(values)]
    path = c.beginPath()
    path.moveTo(points[0][0], y + 14)
    for px, py in points:
        path.lineTo(px, py)
    path.lineTo(points[-1][0], y + 14)
    path.close()
    c.setFillColor(C(fill))
    c.drawPath(path, stroke=0, fill=1)
    c.setStrokeColor(C(color))
    c.setLineWidth(1.8)
    line = c.beginPath()
    line.moveTo(*points[0])
    for px, py in points[1:]:
        line.lineTo(px, py)
    c.drawPath(line, stroke=1, fill=0)
    peak = values.index(high)
    for i, ((px, py), v) in enumerate(zip(points, values)):
        last = i == len(values) - 1
        c.setFillColor(C(theme.ORO if last else color))
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.2)
        c.circle(px, py, 3.4 if last else 2.3, stroke=1, fill=1)
        if i in (0, peak) or last:
            c.setFillColor(C(theme.MORADO_900))
            c.setFont("Text-Semi", 7.2)
            c.drawCentredString(min(max(px, x + 14), x + w - 14), py + 6, fmt(v))
        c.setFillColor(C("#6E6880"))
        c.setFont("Text", 6.4)
        c.drawCentredString(px, y + 3, labels[i])


def donut(c, cx: float, cy: float, radius: float, parts: list[tuple[str, float]], center: str, sub: str) -> None:
    """Who receives what: a ring with each part in its colour and the whole in the middle."""
    total = sum(v for _l, v in parts) or 1
    start = 90.0
    for index, (_label, value) in enumerate(parts):
        extent = -360.0 * value / total
        c.setFillColor(C(PALETTE[index % len(PALETTE)]))
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.4)
        c.wedge(cx - radius, cy - radius, cx + radius, cy + radius, start, extent, stroke=1, fill=1)
        start += extent
    c.setFillColor(colors.white)
    c.circle(cx, cy, radius * 0.62, stroke=0, fill=1)
    c.setFillColor(C(theme.MORADO_900))
    c.setFont("Display-Bold", 13 if len(center) < 10 else 11)
    c.drawCentredString(cx, cy + 1, center)
    c.setFillColor(C("#6E6880"))
    c.setFont("Text", 6.6)
    c.drawCentredString(cx, cy - 10, sub)


def legend(c, x: float, top: float, width: float, rows: list[tuple[str, str, str]], step: float = 21) -> float:
    """Colour and name of each part on one line, its figure and share under it: nothing overlaps, nothing is cut."""
    y = top
    for index, (label, figure, share) in enumerate(rows):
        c.setFillColor(C(PALETTE[index % len(PALETTE)]))
        c.roundRect(x, y - 7, 7, 7, 1.6, stroke=0, fill=1)
        c.setFillColor(C(theme.TINTA))
        size = 7.4
        while size > 5.8 and c.stringWidth(label, "Text-Semi", size) > width - 12:
            size -= 0.2
        c.setFont("Text-Semi", size)
        c.drawString(x + 12, y - 6.5, label)
        c.setFillColor(C(theme.MORADO_900))
        c.setFont("Text", 7)
        c.drawString(x + 12, y - 15.5, f"{figure} · {share}")
        y -= step
    return y


def mosaic(c, x: float, y: float, w: float, h: float, items: list[tuple[str, float]], fmt=lambda v: _fmt(v, "money")) -> None:
    """Where the money went: each item a tile with an area proportional to its amount (largest first)."""
    items = [(l, v) for l, v in sorted(items, key=lambda t: -t[1]) if v and v > 0]
    total = sum(v for _l, v in items) or 1

    def place(rows, x0, y0, w0, h0, vertical, colour_from):
        if not rows:
            return
        if len(rows) == 1:
            tile(rows[0], x0, y0, w0, h0, colour_from)
            return
        whole = sum(v for _l, v in rows)
        first = rows[0][1] / whole
        if vertical:
            cut = w0 * first
            tile(rows[0], x0, y0, cut, h0, colour_from)
            place(rows[1:], x0 + cut, y0, w0 - cut, h0, not vertical, colour_from + 1)
        else:
            cut = h0 * first
            tile(rows[0], x0, y0 + h0 - cut, w0, cut, colour_from)
            place(rows[1:], x0, y0, w0, h0 - cut, not vertical, colour_from + 1)

    def tile(item, x0, y0, w0, h0, colour):
        label, value = item
        fill = PALETTE[colour % len(PALETTE)]
        c.setFillColor(C(fill))
        c.setStrokeColor(colors.white)
        c.setLineWidth(2)
        c.rect(x0, y0, w0, h0, stroke=1, fill=1)
        dark = fill in (theme.LILA_300, theme.LILA_200, theme.LILA_100, theme.ORO)
        c.setFillColor(C(theme.MORADO_900) if dark else colors.white)
        if w0 > 54 and h0 > 26:
            size = 7.6
            while size > 5.6 and c.stringWidth(label, "Text-Semi", size) > w0 - 10:
                size -= 0.2
            c.setFont("Text-Semi", size)
            lines = [label]
            if c.stringWidth(label, "Text-Semi", size) > w0 - 10:
                words, lines = label.split(" "), [""]
                for word in words:
                    trial = (lines[-1] + " " + word).strip()
                    if c.stringWidth(trial, "Text-Semi", size) <= w0 - 10 or not lines[-1]:
                        lines[-1] = trial
                    else:
                        lines.append(word)
                lines = lines[:2] if h0 > 40 else lines[:1]
            for k, line in enumerate(lines):
                c.drawString(x0 + 5, y0 + h0 - 11 - k * 9, line)
            shift = 9 * (len(lines) - 1)
            c.setFont("Display-Bold", 9.5 if h0 > 34 else 8)
            c.drawString(x0 + 5, y0 + h0 - 23 - shift, fmt(value))
            if h0 > 46 + shift:
                c.setFont("Text", 6.6)
                c.drawString(x0 + 5, y0 + h0 - 33 - shift, f"{number(value / total * 100, 1)} %")

    place(items, x, y, w, h, True, 0)


def lollipop(c, x: float, top: float, w: float, rows: list[tuple[str, float]], fmt=_fmt, step: float = 15.5,
             color=theme.SERIE_BONOS) -> float:
    """A ranking as stems and dots: lighter than bars, the figure at the end."""
    peak = max([v for _l, v in rows] or [1]) or 1
    label_w = 98
    for index, (label, value) in enumerate(rows):
        yy = top - index * step - 6
        c.setFillColor(C(theme.TINTA))
        size = 7.2
        while size > 5.8 and c.stringWidth(label, "Text", size) > label_w - 6:
            size -= 0.2
        c.setFont("Text", size)
        c.drawRightString(x + label_w - 6, yy - 2.5, label)
        end = x + label_w + (w - label_w - 52) * value / peak
        c.setStrokeColor(C(theme.LILA_200))
        c.setLineWidth(1.6)
        c.line(x + label_w, yy, end, yy)
        c.setFillColor(C(theme.ORO if index == 0 else color))
        c.circle(end, yy, 3.6, stroke=0, fill=1)
        c.setFillColor(C(theme.MORADO_900))
        c.setFont("Text-Semi", 7.2)
        c.drawString(end + 7, yy - 2.5, fmt(value))
    return top - len(rows) * step


def waffle(c, x: float, top: float, share: float, cell: float = 9.2, gap: float = 2.2) -> None:
    """One hundred squares: the share in purple, the rest in lilac."""
    filled = round(share)
    for index in range(100):
        row, col = divmod(index, 10)
        c.setFillColor(C(theme.SERIE_BONOS if index < filled else theme.LILA_100))
        c.roundRect(x + col * (cell + gap), top - (row + 1) * (cell + gap), cell, cell, 1.6, stroke=0, fill=1)


def gauge(c, cx: float, cy: float, radius: float, value: float, pace: float | None, label: str, sub: str) -> None:
    """A half dial for a rate: the track, the figure reached and a gold tick at the even pace of the year."""
    c.setLineCap(1)
    c.setLineWidth(11)
    c.setStrokeColor(C(theme.LILA_100))
    c.arc(cx - radius, cy - radius, cx + radius, cy + radius, 0, 180)
    c.setStrokeColor(C(theme.SERIE_BONOS))
    reach = max(0.0, min(100.0, value or 0))
    c.arc(cx - radius, cy - radius, cx + radius, cy + radius, 180, -180 * reach / 100)
    if pace is not None:
        angle = math.radians(180 - 180 * pace / 100)
        c.setStrokeColor(C(theme.ORO_700))
        c.setLineWidth(2)
        c.line(cx + (radius - 9) * math.cos(angle), cy + (radius - 9) * math.sin(angle),
               cx + (radius + 9) * math.cos(angle), cy + (radius + 9) * math.sin(angle))
    c.setLineCap(0)
    c.setFillColor(C(theme.MORADO_900))
    c.setFont("Display-Bold", 15)
    c.drawCentredString(cx, cy + 2, _fmt(value, "rate"))
    c.setFont("Text-Semi", 7.4)
    c.drawCentredString(cx, cy - 12, label)
    c.setFillColor(C("#6E6880"))
    c.setFont("Text", 6.6)
    c.drawCentredString(cx, cy - 22, sub)


def panel(c, x: float, top: float, w: float, items: list[tuple[str, str, str]], height: float = 74) -> float:
    """The key figures of a story on a dark band: big figure, label and a short note in gold."""
    c.setFillColor(C(theme.MORADO_900))
    c.roundRect(x, top - height, w, height, 10, stroke=0, fill=1)
    slot = w / max(1, len(items))
    for index, (figure, label, note) in enumerate(items):
        sx = x + index * slot + 12
        if index:
            c.setStrokeColor(C("#4E3680"))
            c.setLineWidth(0.8)
            c.line(x + index * slot, top - 14, x + index * slot, top - height + 14)
        size = 17
        while size > 11 and c.stringWidth(figure, "Display-Bold", size) > slot - 20:
            size -= 0.5
        c.setFillColor(colors.white)
        c.setFont("Display-Bold", size)
        c.drawString(sx, top - 30, figure)
        c.setFillColor(C("#E9E2F7"))
        size = 7.4
        while size > 5.8 and c.stringWidth(label, "Text-Semi", size) > slot - 20:
            size -= 0.2
        c.setFont("Text-Semi", size)
        c.drawString(sx, top - 44, label)
        c.setFillColor(C(theme.ORO))
        size = 6.8
        while size > 5.6 and c.stringWidth(note, "Text", size) > slot - 20:
            size -= 0.2
        c.setFont("Text", size)
        c.drawString(sx, top - 56, note)
    return top - height


def timeline(c, x: float, top: float, w: float, rows: list[tuple[str, str, str]], start: str, end: str) -> float:
    """From when to when each base has information, on one calendar."""
    def index(period: str) -> int:
        return int(period[:4]) * 12 + int(period[5:7]) - 1
    first, last = index(start), index(end)
    months = max(1, last - first + 1)
    label_w = 150
    track = w - label_w - 8
    c.setFont("Text", 6.4)
    c.setFillColor(C("#6E6880"))
    for k in range(months):
        p = first + k
        year, month = divmod(p, 12)
        if months <= 14 or month in (0, 6):
            c.drawCentredString(x + label_w + track * (k + 0.5) / months, top, MONTHS[month][:3].capitalize() + ("" if months <= 14 else f" {str(year)[2:]}"))
    y = top - 10
    for name, since, until in rows:
        c.setFillColor(C(theme.TINTA))
        c.setFont("Text", 7.2)
        c.drawRightString(x + label_w - 8, y - 7, name)
        c.setFillColor(C(theme.LILA_50))
        c.roundRect(x + label_w, y - 10, track, 8, 4, stroke=0, fill=1)
        a = max(first, index(since)) if since else first
        b = min(last, index(until)) if until else last
        if b >= a:
            c.setFillColor(C(theme.SERIE_BONOS))
            c.roundRect(x + label_w + track * (a - first) / months, y - 10, track * (b - a + 1) / months, 8, 4, stroke=0, fill=1)
        y -= 14
    return y


# ----------------------------------------------------------------------------------------------------- pages
def generate(ctx: dict) -> bytes:
    from .charts import map_png
    from .pdf import _band, _findings, _footer, _kpis, _picture, _slim_band
    f = ctx["figures"]
    x_ = ctx["extras"]
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle(ctx["title"])
    c.setAuthor(ctx["institution"])
    c.setSubject(ctx["period_label"])
    c.setCreator(PRODUCT)
    full = W - 2 * M
    half = (full - 24) / 2
    pages = 5
    page = [1]

    def blank():
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)

    def turn(heading: str, subtitle: str) -> float:
        _footer(c, ctx, page[0], pages)
        c.showPage()
        page[0] += 1
        blank()
        return _slim_band(c, ctx, heading, subtitle) - 28

    # 1 · What was delivered, the time line of the information and the findings ------------------------------
    blank()
    y = _band(c, ctx, H, None, kind_label=ctx["module_label"]) - 18
    y = _kpis(c, {**ctx, "kpis": f["kpis"][:4]}, y) - 12
    y = _kpis(c, {**ctx, "kpis": f["kpis"][4:8]}, y) - 30
    title(c, "Información disponible en cada sección", M, y, full, "Meses del periodo con información en la base de cada sección")
    y = timeline(c, M, y - 26, full, x_["timeline"], f["start"], f["end"]) - 22
    title(c, "Lo más relevante del periodo", M, y, full)
    _findings(c, x_["highlights"], M, y - 16, full, limit=5)

    # 2 · Transfers and coverage ---------------------------------------------------------------------------------
    y = turn("Transferencias y cobertura", f"Bonos, pensiones y servicios sociales · {f['span']}")
    bonos = x_["bonos"]
    title(c, "Quién recibe cada bono y pensión", M, y, half, f"Beneficiarios de {x_['end_label']}")
    donut(c, M + 62, y - 92, 56, [(b["label"], b["people"]) for b in bonos], _compact(sum(b["people"] for b in bonos)), "beneficiarios")
    legend(c, M + 132, y - 34, half - 132, [(b["label"], number(b["people"]), f"{number(b['share'], 1)} %") for b in bonos])
    series = x_["series"]
    title(c, "Beneficiarios mes a mes", M + half + 24, y, half, "Bonos y pensiones · el último mes en dorado")
    area(c, M + half + 30, y - 158, half - 12, 128, series["bonos"][0], series["bonos"][1])
    y -= 186
    title(c, "A dónde fue el presupuesto devengado", M, y, full,
          f"USD {millions(x_['accrued_total'], 1)} millones devengados de enero a {x_['end_month']} en transferencias y servicios · cada área es proporcional")
    mosaic(c, M, y - 168, full, 150, x_["accrued_items"])
    y -= 196
    title(c, "Usuarios de servicios sociales mes a mes", M, y, half, "Personas atendidas · el último mes en dorado")
    area(c, M + 6, y - 150, half - 12, 120, series["servicios"][0], series["servicios"][1], color=theme.FUCSIA, fill="#F6E3EE")
    title(c, "Usuarios por servicio", M + half + 24, y, half, f"Personas atendidas en {x_['end_label']}")
    lollipop(c, M + half + 24, y - 30, half, [(s["label"], s["people"]) for s in x_["servicios"]], color=theme.FUCSIA)

    # 3 · El Niño ------------------------------------------------------------------------------------------------------
    enos = x_.get("enos")
    y = turn("Fenómeno El Niño: respuesta del Ministerio", f"Plan ENOS · seguimiento desde el 28 de septiembre de 2026 · corte {enos['cut'] if enos else ''}")
    if enos:
        y = panel(c, M, y, full, [(number(enos["units"]), "Unidades de atención con alertas", f"{number(enos['alerts'])} alertas y reportes"),
                                  (number(enos["kits"]), "Kits entregados", f"{enos['kit_provinces']} provincias priorizadas"),
                                  (number(enos["families"]), "Familias con bono de contingencia", "Habilitadas al pago"),
                                  (f"USD {number(enos['amount'], 0)}", "Monto del bono de contingencia", "En articulación"),
                                  (number(enos["closed"]), "Unidades de atención", "con atención suspendida")]) - 24
        title(c, "Kits entregados por provincia", M, y, half, "Más oscuro, más kits")
        picture = map_png(enos["kits_map"], layer="provincia", mode="light", legend=False, marks=False, width=half / 72, height=230 / 72, dpi=200)
        _picture(c, picture, M, y - 16, half, 230 / half)
        title(c, "Provincias con más kits", M + half + 24, y, half, "Kits entregados")
        bottom = lollipop(c, M + half + 24, y - 30, half, enos["kits_rank"], step=17)
        title(c, "Bono de contingencia por provincia", M + half + 24, bottom - 14, half, "Familias habilitadas al pago")
        lollipop(c, M + half + 24, bottom - 44, half, enos["bono_rank"], step=17, color=theme.VIOLETA_500)
        y -= 270
        y = _findings(c, enos["findings"], M, y, full, limit=3) - 18
        if enos.get("alerts_rank"):
            title(c, "Alertas por provincia", M, y, half, "Alertas y reportes sectoriales revisados")
            lollipop(c, M, y - 30, half, enos["alerts_rank"], step=16, color=theme.FUCSIA)
            title(c, "Atención suspendida por servicio", M + half + 24, y, half, "Unidades de atención con atención suspendida")
            lollipop(c, M + half + 24, y - 30, half, enos["closed_rank"], step=16, color=theme.ORO_700)

    # 4 · Brigades and Crédito de Desarrollo Humano -----------------------------------------------------------------
    y = turn("Brigadas sociales y Crédito de Desarrollo Humano", f"Atención en territorio y crédito para emprender · {f['span']}")
    brig = x_.get("brigadas")
    if brig:
        y = panel(c, M, y, full, [(number(brig["count"]), "Brigadas realizadas", f"{brig['provinces']} provincias"),
                                  (number(brig["attended"]), "Personas atendidas", f"{number(brig['rate'], 1)} % de las alcanzadas"),
                                  (number(brig["average"]), "Personas por brigada", "Promedio del periodo")], height=64) - 22
        title(c, "Personas atendidas mes a mes", M, y, half, "Brigadas sociales · el último mes en dorado")
        area(c, M + 6, y - 140, half - 12, 110, brig["months"][0], brig["months"][1], color=theme.VIOLETA_500)
        title(c, "Dónde se realizaron", M + half + 24, y, half, "Brigadas por provincia · más oscuro, más brigadas")
        picture = map_png(brig["map"], layer="provincia", mode="light", legend=False, marks=False, width=half / 72, height=150 / 72, dpi=200)
        _picture(c, picture, M + half + 24, y - 16, half, 150 / half)
        y -= 168
    cdh = x_.get("cdh")
    if cdh:
        y = panel(c, M, y, full, [(number(cdh["credits"]), "Créditos de Desarrollo Humano", "Desembolsados en el periodo"),
                                  (f"USD {millions(cdh['amount'], 1)} M", "Monto desembolsado", f"USD {number(cdh['average'])} por crédito"),
                                  (number(cdh["portfolio"]), "Cartera vigente", f"USD {millions(cdh['portfolio_amount'], 1)} M")], height=64) - 22
        title(c, "De cada 100 créditos", M, y, 150, f"{number(cdh['women'], 0)} son para mujeres")
        waffle(c, M + 4, y - 22, cdh["women"], cell=8.6)
        title(c, "Créditos por mes", M + 136, y, 210, "Desembolsos · el último mes en dorado")
        area(c, M + 140, y - 140, 200, 110, cdh["months"][0], cdh["months"][1])
        title(c, "Bono de origen", M + 366, y, full - 366, "Créditos del periodo")
        donut(c, M + 410, y - 70, 38, [(b, v) for b, v in cdh["bonus"]], _compact(cdh["credits"]), "créditos")
        legend(c, M + 366, y - 120, full - 366, [(b, number(v), f"{number(v / cdh['credits'] * 100, 1)} %") for b, v in cdh["bonus"]], step=12)

    # 5 · Contingencies, youth, employment and budget -----------------------------------------------------------------
    y = turn("Contingencias, Jóvenes en Acción, Empleo y Presupuesto", f"{f['span'][:1].upper()}{f['span'][1:]}")
    cont = x_.get("contingencias")
    if cont:
        title(c, "Contingencias y compensaciones", M, y, half, f"USD {millions(cont['total'], 1)} M entregados · área proporcional al monto")
        mosaic(c, M, y - 150, half, 128, cont["items"])
    youth = x_.get("jovenes")
    if youth:
        from .pdf_areas import _columns
        title(c, "Jóvenes en Acción", M + half + 24, y, half, f"{number(youth['transfers'])} transferencias · USD {millions(youth['amount'], 1)} M")
        _columns(c, youth["months"][0], youth["months"][1], M + half + 24, y - 22, half, 118, highlight=len(youth["months"][1]) - 1,
                 label_size=7, value_text=_compact)
    y -= 176
    budget = x_.get("presupuesto", {})
    title(c, "Ejecución del presupuesto", M, y, full, "La marca dorada señala el ritmo uniforme del año (una doceava parte por mes)")
    gauges = [g for g in budget.get("gauges", [])]
    slot = full / max(1, len(gauges) + 1)
    for index, g in enumerate(gauges):
        gauge(c, M + slot * (index + 0.5), y - 92, 52, g["value"], g.get("pace"), g["label"], g["sub"])
    if budget.get("government"):
        gx = M + slot * len(gauges) + 8
        gov = budget["government"]
        c.setFillColor(C(theme.MORADO_900))
        c.setFont("Display-Bold", 15)
        c.drawString(gx, y - 54, f"USD {millions(gov['total'], 1)} M")
        c.setFont("Text-Semi", 7.4)
        c.drawString(gx, y - 66, "Presupuesto acumulado 2023–" + f["end"][:4])
        bar_w = slot - 16
        share = gov["previous"] / gov["total"] if gov["total"] else 0
        c.setFillColor(C(theme.LILA_200))
        c.roundRect(gx, y - 88, bar_w, 10, 3, stroke=0, fill=1)
        c.setFillColor(C(theme.SERIE_BONOS))
        c.roundRect(gx + bar_w * share, y - 88, bar_w * (1 - share), 10, 3, stroke=0, fill=1)
        c.setFillColor(C("#6E6880"))
        c.setFont("Text", 6.6)
        c.drawString(gx, y - 98, f"2023–{int(f['end'][:4]) - 1}: USD {millions(gov['previous'], 1)} M")
        c.drawString(gx, y - 107, f"{f['end'][:4]}: USD {millions(gov['current'], 1)} M")
    y -= 140
    jobs = x_.get("empleo_cards")
    if jobs:
        title(c, "Empleo", M, y, full, x_.get("empleo_cut", ""))
        y = panel(c, M, y - 18, full, jobs, height=64) - 22
    if budget.get("note"):
        _findings(c, [{"icon": "wallet", "text": budget["note"]}], M, y, full, limit=1)
    _footer(c, ctx, page[0], pages)
    c.showPage()
    c.save()
    return out.getvalue()
