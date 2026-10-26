"""Executive summaries of the areas with their own structure, drawn with the components of the territorial summary.

Contingencies and compensation (two pages): key figures, the map and ranking of the bonuses enabled in the year, the
budget month by month and its execution, findings; then every program of the month, each program over the last twelve
months, the deeper territorial levels and the types of contingency.
Jóvenes en Acción (one page): the phases, from registration to payment, budget and execution by phase, the payments of
every month and the findings.
Labour management (two pages): contracts in force by territory and their profile; economic activity, the contracts
registered in the year, retirement compensation and the cantons.
Social budget (two pages): the accrued budget of every month, its execution and the pace the year needs; the detail by
program and month.

Every figure carries its unit: counts name what they count, money reads «USD 21,3 M» or in full dollars, and rates «%».
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph

from src import theme
from .charts import columns_png, emblem_png, execution_png, map_png, trend_png
from .context import millions, number
from .pdf import (BOTTOM, H, INK, M, MIST, MUTED, NIGHT, PURPLE, W, C, _badge, _band, _bars, _clip, _heading, _kpis,
                  _next_page, _picture, _slim_band, _table)

PAGES = {"contingencias": 2, "jovenes": 1, "laboral": 2, "presupuesto_social": 2}
LEVEL_LABELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}
LEVEL_PLURALS = {"provincia": "Provincias", "canton": "Cantones", "parroquia": "Parroquias"}
COLUMN = (W - 2 * M - 22) / 2
RIGHT = M + COLUMN + 22
FULL = W - 2 * M
PHASE_COLORS = {1: theme.LILA_300, 2: theme.VIOLETA_500, 3: theme.ORO}
SHORT_PROGRAMS = {"ORFANDAD_VIOLENCIA": "Orfandad", "CONTINGENCIAS": "Contingencias", "ANTROPICOS": "Eventos",
                  "COMPENSACION_GASOLINA": "Transporte", "COMPENSACION_DIESEL": "Diésel", "MIGRANTES": "Migrantes"}
SHORT_UNITS = {"beneficiarios": "Beneficiarios", "personas habilitadas": "Habilitadas", "personas con pago acreditado": "Pago acreditado"}


# ----------------------------------------------------------------------------------------------- helpers
def usd(value) -> str:
    """«USD 142,4 M» from a million up, «USD 83.681» below."""
    if value is None or value != value:
        return "—"
    if abs(value) >= 1_000_000:
        return f"USD {number(value / 1e6, 1)} M"
    return f"USD {number(value)}"


def _money_label(values: list[float], slot: float):
    """Column figures in millions of USD: «USD 21,3 M» when the column is wide enough, «21,3 M» otherwise."""
    wide = slot >= 58
    small = max([abs(v or 0) for v in values] or [0]) < 10_000_000
    def text(v):
        if v and 0 < abs(v) < 5_000:
            return "< 0,01 M"
        figure = number((v or 0) / 1e6, 2 if small or abs(v or 0) < 50_000 else 1)
        return f"USD {figure} M" if wide else f"{figure} M"
    return text


def _two_findings(c, items: list[dict], top: float, *, rows: int = 2, bottom: float = BOTTOM) -> float:
    """Findings in two columns, filled left to right; a finding left alone in its row takes the whole width."""
    half = (FULL - 12) / 2
    style = ParagraphStyle("f2", fontName="Text", fontSize=8.4, leading=11.4, textColor=INK)
    y = top
    for start in range(0, min(len(items), rows * 2), 2):
        pair = items[start:start + 2]
        width = half if len(pair) == 2 else FULL
        heights = []
        for item in pair:
            para = Paragraph(escape(item["text"]), style)
            _w, h = para.wrap(width - 50, 90)
            heights.append(h)
        box = max(40, max(heights) + 16)
        if y - box < bottom:
            break
        for index, item in enumerate(pair):
            x = M + index * (half + 12)
            c.setFillColor(C(theme.LILA_50))
            c.roundRect(x, y - box, width, box, 8, stroke=0, fill=1)
            _badge(c, item["icon"], x + 21, y - box / 2, 12.5)
            para = Paragraph(escape(item["text"]), style)
            _w, h = para.wrap(width - 50, 90)
            para.drawOn(c, x + 42, y - box / 2 - h / 2 + 1)
        y -= box + 7
    return y


def _findings_height(items: list[dict], rows: int) -> float:
    """Height the findings need in two columns (to plan a page before drawing it)."""
    half = (FULL - 12) / 2
    style = ParagraphStyle("f2", fontName="Text", fontSize=8.4, leading=11.4, textColor=INK)
    total = 0.0
    for start in range(0, min(len(items), rows * 2), 2):
        pair = items[start:start + 2]
        width = half if len(pair) == 2 else FULL
        heights = [Paragraph(escape(i["text"]), style).wrap(width - 50, 90)[1] for i in pair]
        total += max(40, max(heights) + 16) + 7
    return total


def _stacked(c, title: str, parts: list[dict], x: float, top: float, width: float, palette: list[str]) -> float:
    """One 100 % bar with its parts; names and shares under the segments wide enough, the rest in a key at the right."""
    c.setFillColor(C(theme.PIZARRA))
    c.setFont("Text-Semi", 7.8)
    c.drawString(x, top, title)
    y = top - 17
    total = sum(p["share"] or 0 for p in parts) or 100
    cx = x
    for index, part in enumerate(parts):
        length = width * (part["share"] or 0) / total
        c.setFillColor(C(palette[index % len(palette)]))
        c.rect(cx, y, max(0.0, length - (1.2 if index < len(parts) - 1 else 0)), 10, stroke=0, fill=1)
        cx += length
    cx = x
    legend = []
    for index, part in enumerate(parts):
        length = width * (part["share"] or 0) / total
        text = f"{part['name']}: {number(part['share'], 1)} %"
        if pdfmetrics.stringWidth(text, "Text-Medium", 7.4) + 6 <= length:
            c.setFillColor(INK)
            c.setFont("Text-Medium", 7.4)
            c.drawString(cx + 1, y - 10.5, text)
        else:
            legend.append((palette[index % len(palette)], text))
        cx += length
    if legend:
        lx = x + width
        for color, text in reversed(legend):
            lx -= pdfmetrics.stringWidth(text, "Text-Medium", 7.2)
            c.setFillColor(INK)
            c.setFont("Text-Medium", 7.2)
            c.drawString(lx, y - 10.5, text)
            lx -= 11
            c.setFillColor(C(color))
            c.roundRect(lx, y - 11, 7, 7, 1.5, stroke=0, fill=1)
            lx -= 10
    return y - 19


def _funnel(c, steps: list[tuple[str, float]], x: float, top: float, width: float, row_h: float = 38) -> float:
    """Registration to payment: one bar per step relative to the first, its figure and its share of the previous step."""
    first = steps[0][1] or 1
    y = top
    tones = [theme.LILA_300, theme.SERIE_BONOS, theme.ORO]
    for index, (label, value) in enumerate(steps):
        c.setFillColor(INK)
        c.setFont("Text-Semi", 8.4)
        c.drawString(x, y, label)
        c.setFont("Display", 11)
        c.setFillColor(NIGHT)
        c.drawRightString(x + width, y, f"{number(value)} jóvenes")
        track_y = y - 14
        c.setFillColor(C("#EFECF5"))
        c.roundRect(x, track_y, width, 8, 3, stroke=0, fill=1)
        c.setFillColor(C(tones[index % len(tones)]))
        c.roundRect(x, track_y, max(6, width * (value or 0) / first), 8, 3, stroke=0, fill=1)
        if index:
            previous = steps[index - 1][1]
            c.setFillColor(PURPLE)
            c.setFont("Text-Semi", 7.2)
            c.drawString(x, track_y - 10, f"{number((value or 0) / previous * 100 if previous else 0, 1)} % de los "
                                          f"{steps[index - 1][0].lower()}")
        y -= row_h
    return y


def _mini_series(c, item: dict, x: float, top: float, width: float, height: float = 70) -> float:
    """A program over twelve months: name, criterion with its latest figure, and its line."""
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 8.6)
    c.drawString(x, top, _clip(item["name"], "Display-Bold", 8.6, width - 4))
    c.setFillColor(MUTED)
    c.setFont("Text", 7)
    c.drawString(x, top - 11, _clip(f"{item['short_criterion']} · {item['latest_label']}: {number(item['latest'])}", "Text", 7, width - 4))
    inches = max(2.6, width / 72)
    picture = trend_png(item["labels"], item["values"], highlight=item.get("highlight"), width=inches, height=inches * height / width,
                        dpi=220, every=3 if width < 300 else 1, font_scale=0.9)
    return _picture(c, picture, x - 3, top - 15, width + 6, height / width)


def _rate_bars(rows: list[dict], label: str = "name") -> list[dict]:
    return [{**r, "name": r[label], "fraction": (r.get("execution") or 0) / 100,
             "text": f"{number(r['execution'], 1)} %" if r.get("execution") is not None else "—"} for r in rows]


def _count_bars(rows: list[dict], key: str, label: str = "name", unit: str = "") -> list[dict]:
    peak = max([(r.get(key) or 0) for r in rows] or [1]) or 1
    return [{**r, "name": r[label], "fraction": (r.get(key) or 0) / peak,
             "text": (f"{number(r.get(key))} {unit}".strip() if r.get(key) is not None else "—")} for r in rows]


def _share_bars(rows: list[dict], key: str, label: str = "name") -> list[dict]:
    """Bars with their count and share: «638 · 35,8 %»."""
    bars = _count_bars(rows, key, label)
    for bar, row in zip(bars, rows):
        bar["text"] = f"{number(row.get(key))} · {number(row.get('share'), 1)} %"
    return bars


def _columns(c, labels, values, x, top, width, height, *, highlight=None, money=False, colors=None, label_size=8,
             value_text=None) -> float:
    if money and value_text is None:
        slot = width / max(1, len(values))
        value_text = _money_label(values, slot)
        if slot < 58:
            label_size = min(label_size, 7.0)
    picture = columns_png(labels, values, width=width / 72, height=height / 72, highlight=highlight, value_text=value_text, colors=colors,
                          label_size=label_size)
    return _picture(c, picture, x, top, width, height / width)


def _legend(c, items: list[tuple[str, str]], x: float, y: float, *, right: bool = False) -> None:
    widths = [18 + pdfmetrics.stringWidth(text, "Text-Medium", 7.2) for _color, text in items]
    if right:
        x -= sum(widths) - 8
    for (color, text), step in zip(items, widths):
        c.setFillColor(C(color))
        c.roundRect(x, y - 1, 7, 7, 1.5, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Text-Medium", 7.2)
        c.drawString(x + 10, y, text)
        x += step


def _caption(c, text: str, x: float, y: float, width: float) -> None:
    """A unit or reading line right under a heading."""
    c.setFillColor(MUTED)
    c.setFont("Text", 7.2)
    c.drawString(x, y, _clip(text, "Text", 7.2, width))


def _matrix(c, x: float, top: float, width: float, matrix: dict, *, label_w: float = 162, row_h: float = 14.4) -> float:
    """Accrued budget of each program in each month (millions of USD), shaded by its weight in the row."""
    months, rows = matrix["months"], matrix["rows"]
    if not rows:
        return top
    total_w = 52
    cell = (width - label_w - total_w) / max(1, len(months))
    header_h = 18
    c.setFillColor(PURPLE)
    c.roundRect(x, top - header_h, width, header_h, 3.5, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Text-Bold", 6.9)
    c.drawString(x + 6, top - header_h / 2 - 2.4, "Programa (millones de USD)")
    for j, month in enumerate(months):
        c.drawCentredString(x + label_w + j * cell + cell / 2, top - header_h / 2 - 2.4, month)
    c.drawRightString(x + width - 6, top - header_h / 2 - 2.4, "Total del año")
    y = top - header_h
    for i, row in enumerate(rows):
        y -= row_h
        c.setFillColor(MIST if i % 2 else colors.white)
        c.rect(x, y, width, row_h, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Text-Medium", 7.4)
        c.drawString(x + 6, y + row_h / 2 - 2.6, _clip(row["name"], "Text-Medium", 7.4, label_w - 10))
        peak = max([v or 0 for v in row["values"]] or [1]) or 1
        for j, value in enumerate(row["values"]):
            cx = x + label_w + j * cell
            shade = 0.15 + 0.7 * (value or 0) / peak
            if value:
                c.setFillColor(C(theme.ramp_at(shade, theme.SEQUENTIAL[1:])))
                c.rect(cx + 0.8, y + 0.8, cell - 1.6, row_h - 1.6, stroke=0, fill=1)
            c.setFillColor(colors.white if value and shade > 0.55 else INK)
            c.setFont("Text-Semi", 6.6)
            text = "—" if not value else (number(value / 1e6, 1) if value >= 1e6 else number(value / 1e6, 2))
            c.drawCentredString(cx + cell / 2, y + row_h / 2 - 2.5, text)
        c.setFillColor(NIGHT)
        c.setFont("Text-Bold", 7.2)
        c.drawRightString(x + width - 6, y + row_h / 2 - 2.6, number(row["total"] / 1e6, 1 if row["total"] >= 1e6 else 2))
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.8)
    c.line(x, y, x + width, y)
    return y


def _tile(c, x: float, top: float, width: float, height: float, icon: str, title: str, value: str, caption: str) -> float:
    """A highlighted figure with its reading, in the gold tint of the institution."""
    c.setFillColor(C(theme.ORO_100))
    c.roundRect(x, top - height, width, height, 8, stroke=0, fill=1)
    c.setFillColor(C(theme.ORO))
    c.rect(x, top - height + 8, 3, height - 16, stroke=0, fill=1)
    _badge(c, icon, x + 24, top - 22, 11, fill=C(theme.ORO), variant="blanco")
    c.setFillColor(C(theme.PIZARRA))
    c.setFont("Text-Semi", 7.8)
    c.drawString(x + 42, top - 19, _clip(title, "Text-Semi", 7.8, width - 52))
    c.setFillColor(NIGHT)
    c.setFont("Display", 15)
    c.drawString(x + 42, top - 38, value)
    style = ParagraphStyle("tile", fontName="Text", fontSize=7.8, leading=10.2, textColor=INK)
    para = Paragraph(escape(caption), style)
    _w, h = para.wrap(width - 54, height - 44)
    para.drawOn(c, x + 42, top - 46 - h)
    return top - height


# ------------------------------------------------------------------------------------------ contingencies
def _program_table(c, ctx: dict, top: float) -> float:
    """Every program of the month: people by the criterion of its source, collections, amounts and budget (in USD)."""
    rows = []
    for p in ctx["programs"]:
        rows.append({"place": p["name"], "criterion": SHORT_UNITS.get(p["unit"], ""), "people": p["people"], "collected": p["collected"],
                     "amount": p["amount"], "approved": p["approved"], "accrued": p["accrued"], "execution": p["execution"]})
    columns = [("Programa", "place", None, "text"), ("Criterio", "criterion", 82, "text"), ("Personas", "people", 46, "int")]
    if any(r["collected"] for r in rows):
        columns.append(("Cobraron", "collected", 46, "int"))
    columns.append(("Monto del mes\n(USD)", "amount", 60, "int"))
    if ctx.get("budget"):
        columns += [("Aprobado 2026\n(USD)", "approved", 64, "int"), ("Devengado\nacumulado (USD)", "accrued", 66, "int"),
                    ("Ejecución", "execution", 60, "rate")]
    return _table(c, M, top, FULL, columns, rows, row_h=14.2)


def contingency(c, ctx: dict, pages: int) -> None:
    y = _band(c, ctx, H, emblem_png())
    y = _kpis(c, {**ctx, "share_word": ""}, y - 18)
    top = y - 20
    levels = ctx["levels"]
    if levels and ctx["territories"].get(levels[0]):
        level = levels[0]
        _heading(c, f"Bonos habilitados por {LEVEL_LABELS[level].lower()}", M, top - 12, COLUMN, ctx["map_program_label"])
        picture = map_png(ctx["level_maps"][level], layer=level, mode="light", label=f"Bonos habilitados de {ctx['span']}", width=4.8,
                          height=3.45, dpi=220)
        map_bottom = _picture(c, picture, M - 6, top - 22, COLUMN + 12, 3.45 / 4.8)
        rows = ctx["territories"][level][:9]
        whole = ctx["level_totals"][level]
        _heading(c, f"{LEVEL_PLURALS[level]} con más bonos", RIGHT, top - 12, COLUMN, "Bonos habilitados · participación")
        _bars(c, _share_bars(rows, "records"), RIGHT, top - 36, COLUMN, 21.5)
        bottom = top - 36 - len(rows) * 21.5
        if whole["count"] > len(rows):
            _caption(c, f"{len(rows)} de {number(whole['count'])} {LEVEL_PLURALS[level].lower()} con bonos habilitados en el año", RIGHT,
                     bottom - 2, COLUMN)
        top = min(map_bottom, bottom - 6) - 8
    else:
        _heading(c, "Resultados por programa", M, top - 12, FULL, ctx["when"].capitalize())
        top = _program_table(c, ctx, top - 24) - 18
    budget = ctx.get("budget") or {}
    months = ctx["months"]
    chart_h = 96
    ctx["types_on_first"] = False
    if budget:
        funded = sorted([p for p in ctx["programs"] if p.get("approved")], key=lambda p: -(p["approved"] or 0))
        accrued = [m for m in months if m.get("month_accrued") is not None]
        selected = next((i for i, m in enumerate(accrued) if m["selected"]), None)
        _heading(c, "Presupuesto devengado por mes", M, top - 12, COLUMN)
        _columns(c, [m["short"] for m in accrued], [m["month_accrued"] for m in accrued], M - 4, top - 22, COLUMN + 8, chart_h,
                 highlight=selected, money=True)
        if len(funded) >= 3:
            _heading(c, f"Ejecución {ctx['year']} por programa", RIGHT, top - 12, COLUMN, f"Total: {number(budget['execution'], 1)} %")
            step = 16 if len(funded) > 5 else 19
            _bars(c, _rate_bars(funded), RIGHT, top - 34, COLUMN, step)
            top = min(top - 22 - chart_h, top - 34 - len(funded) * step) - 8
        else:
            _heading(c, "Ejecución acumulada", RIGHT, top - 12, COLUMN, "Frente al ritmo uniforme del año")
            picture = execution_png([m["short"] for m in accrued], [m["execution"] for m in accrued], [m["month"] for m in accrued],
                                    highlight=selected, width=4.4, height=4.4 * chart_h / (COLUMN + 8))
            _picture(c, picture, RIGHT - 4, top - 22, COLUMN + 8, chart_h / (COLUMN + 8))
            top -= 22 + chart_h + 8
    elif ctx["types"]:
        types = ctx["types"][:5]
        amounts = [m for m in months if m.get("amount")]
        selected = next((i for i, m in enumerate(amounts) if m["selected"]), None)
        _heading(c, "Monto habilitado o acreditado por mes", M, top - 12, COLUMN)
        _columns(c, [m["short"] for m in amounts], [m["amount"] for m in amounts], M - 4, top - 22, COLUMN + 8, chart_h,
                 highlight=selected, money=True)
        _heading(c, "Bonos habilitados por tipo", RIGHT, top - 12, COLUMN, ctx["span"].capitalize())
        _bars(c, _share_bars(types, "records"), RIGHT, top - 34, COLUMN, 20)
        top = min(top - 22 - chart_h, top - 34 - len(types) * 20) - 8
        ctx["types_on_first"] = True
    _heading(c, "Aspectos destacados", M, top - 12, FULL)
    _two_findings(c, ctx["insights"], top - 24, rows=3, bottom=46)
    ctx["findings_drawn"] = _count_drawn(ctx["insights"][:6], top - 24, 46)
    _next_page(c, ctx, 1, pages)
    _contingency_detail(c, ctx)


def _count_drawn(items: list[dict], top: float, bottom: float) -> int:
    """How many findings fitted between ``top`` and ``bottom`` (two per row)."""
    count, y = 0, top
    for start in range(0, len(items), 2):
        pair = items[start:start + 2]
        height = _findings_height(pair, 1)
        if y - height < bottom - 1:
            break
        y -= height
        count += len(pair)
    return count


def _contingency_detail(c, ctx: dict) -> None:
    y = _slim_band(c, ctx, "Programas, evolución y territorio", f"{ctx['territory_label']} · {ctx['programs_label']}")
    top = y - 24
    levels = ctx["levels"]
    on_first = bool(levels and ctx["territories"].get(levels[0]))
    if on_first:
        _heading(c, "Resultados por programa", M, top, FULL, ctx["when"].capitalize())
        top = _program_table(c, ctx, top - 12) - 26
    history = ctx["history"][:6]
    if len(history) >= 3:
        _heading(c, "Evolución mensual de cada programa", M, top, FULL, "Personas de los últimos doce meses · el mes de la consulta en dorado")
        cell = (FULL - 2 * 16) / 3
        row_top = top - 22
        for index, item in enumerate(history):
            col, row = index % 3, index // 3
            _mini_series(c, item, M + col * (cell + 16), row_top - row * 100, cell, 66)
        top = row_top - ((len(history) + 2) // 3) * 100 - 4
    elif history:
        _heading(c, "Evolución mensual", M, top, FULL, "Personas de los últimos doce meses · el mes de la consulta en dorado")
        cell = (FULL - 16 * (len(history) - 1)) / len(history)
        for index, item in enumerate(history):
            _mini_series(c, item, M + index * (cell + 16), top - 22, cell, 104)
        top = top - 22 - 15 - 104 - 14
    deeper = [lvl for lvl in (levels[1:] if on_first else levels) if ctx["territories"].get(lvl)]
    types = [] if ctx.get("types_on_first") else ctx["types"]
    # Plan the rest of the page: the deeper territorial levels (one shares its row with the types), the types and the
    # year month by month; the rows left over go to the territories first, so the page ends full.
    types_beside = bool(types) and len(deeper) == 1
    types_alone = bool(types) and not types_beside
    free = top - BOTTOM - 4
    year_h = 36 + len(ctx["months"]) * 14.2 + 10
    deeper_rows = 4 if deeper else 0
    type_rows = min(3, len(types)) if types_alone else 0
    needed = (50 + deeper_rows * 21 + 8 if deeper else 0) + (36 + type_rows * 21 + 6 if type_rows else 0)
    with_year = free - needed >= year_h
    extra = int((free - needed - (year_h if with_year else 0)) // 21)
    if deeper:
        grow = max(0, min(extra, 10 - deeper_rows))
        deeper_rows += grow
        extra -= grow
    if types_alone:
        type_rows += max(0, min(extra, min(6, len(types)) - type_rows))
    if deeper:
        columns = deeper + (["tipos"] if types_beside else [])
        title = "Bonos habilitados por " + " y ".join(LEVEL_LABELS[lvl].lower() for lvl in deeper) + (" y por tipo" if types_beside else "")
        _heading(c, title, M, top - 12, FULL, f"{ctx['map_program_label']} · {ctx['span']}")
        cell = (FULL - 16 * (len(columns) - 1)) / len(columns)
        lowest = top
        for index, column in enumerate(columns):
            x = M + index * (cell + 16)
            c.setFillColor(C(theme.PIZARRA))
            c.setFont("Text-Semi", 7.8)
            if column == "tipos":
                c.drawString(x, top - 32, "Por tipo de contingencia o evento")
                rows = types[:deeper_rows]
            else:
                c.drawString(x, top - 32, f"{LEVEL_PLURALS[column]} · {number(ctx['level_totals'][column]['count'])} con bonos habilitados")
                rows = ctx["territories"][column][:deeper_rows]
            _bars(c, _share_bars(rows, "records"), x, top - 50, cell, 21)
            lowest = min(lowest, top - 50 - len(rows) * 21)
        top = lowest - 8
    if type_rows:
        shown = types[:type_rows]
        _heading(c, "Bonos habilitados por tipo de contingencia o evento", M, top - 12, FULL, ctx["span"].capitalize())
        _bars(c, _share_bars(shown, "records"), M, top - 36, FULL, 21)
        top = top - 36 - len(shown) * 21 - 6
    if with_year:
        top = _year_table(c, ctx, top)
    if on_first and not deeper and top - 90 > BOTTOM:
        top = _place_table(c, ctx, levels[0], top)
    remaining = ctx["insights"][ctx.get("findings_drawn", 4):]
    if remaining and top - 60 > BOTTOM:
        _heading(c, "Otros aspectos destacados", M, top - 12, FULL)
        _two_findings(c, remaining, top - 24, rows=2, bottom=46)


def _place_table(c, ctx: dict, level: str, top: float) -> float:
    """Detail of the level on page 1: bonuses enabled, share, people and amount of each territory, as many rows as fit."""
    rows = ctx["territories"][level]
    room = int((top - 36 - BOTTOM) // 13.6)
    if room < 3:
        return top
    shown = rows[:room]
    whole = ctx["level_totals"][level]
    table = [{"position": i + 1, "place": r["detail"], "records": r["records"], "share": r["share"], "people": r["people"],
              "amount": r["amount"]} for i, r in enumerate(shown)]
    _heading(c, f"Detalle por {LEVEL_LABELS[level].lower()}", M, top - 12, FULL,
             f"{ctx['map_program_label']} · {len(shown)} de {number(whole['count'])}" if whole["count"] > len(shown) else ctx["map_program_label"])
    columns = [("N.º", "position", 24, "center"), (LEVEL_LABELS[level], "place", None, "text"), ("Bonos\nhabilitados", "records", 64, "int"),
               ("Participación", "share", 96, "share"), ("Personas", "people", 60, "int"), ("Monto habilitado\n(USD)", "amount", 84, "int")]
    return _table(c, M, top - 24, FULL, columns, table, row_h=13.6) - 10


def _year_table(c, ctx: dict, top: float) -> float:
    """The year month by month: people of each program (up to three), amounts and budget."""
    months = ctx["months"]
    programs = [p for p in ctx["programs"] if any(m["people"].get(p["id"]) is not None for m in months)][:3]
    rows, columns = [], [("Mes", "place", None, "text")]
    for p in programs:
        columns.append((f"{SHORT_PROGRAMS.get(p['id'], p['name'])}\n({SHORT_UNITS.get(p['unit'], 'personas').lower()})", p["id"], 84, "int"))
    columns.append(("Monto habilitado o\nacreditado (USD)", "amount", 86, "int"))
    if ctx.get("budget"):
        columns += [("Devengado del\nmes (USD)", "month_accrued", 78, "int"), ("Ejecución\nacumulada", "execution", 66, "rate")]
    for m in months:
        row = {"place": m["label"], "amount": m["amount"], "month_accrued": m["month_accrued"], "execution": m["execution"],
               "selected": m["selected"]}
        for p in programs:
            row[p["id"]] = m["people"].get(p["id"])
        rows.append(row)
    room = int((top - 36 - BOTTOM) // 14.2)
    if room < 3:
        return top
    rows = rows[-room:]
    first, last = rows[0]["place"].lower(), rows[-1]["place"].lower()
    _heading(c, "El año mes a mes", M, top - 12, FULL, f"{first.capitalize()} a {last} de {ctx['year']}" if first != last else "")
    return _table(c, M, top - 24, FULL, columns, rows, row_h=14.2) - 10


# --------------------------------------------------------------------------------------- Jóvenes en Acción
def youth(c, ctx: dict, pages: int) -> None:
    info = ctx["info"]
    y = _band(c, ctx, H, emblem_png())
    y = _kpis(c, ctx, y - 18)
    top = y - 20
    phases = ctx["phases"]
    _heading(c, "Jóvenes participantes por fase", M, top - 12, COLUMN, "Fase en curso en dorado")
    labels = [f"{p['name']}" for p in phases]
    _columns(c, labels, [p["participants"] for p in phases], M - 4, top - 22, COLUMN + 8, 104, highlight=len(phases) - 1,
             value_text=lambda v: f"{number(v)} jóvenes")
    c.setFillColor(MUTED)
    c.setFont("Text", 7)
    slot = (COLUMN + 8) / max(1, len(phases))
    for index, p in enumerate(phases):
        c.drawCentredString(M - 4 + slot * (index + 0.5), top - 22 - 104 - 3, _clip(p["period_short"], "Text", 7, slot - 4))
    phase = info["phase_name"].lower()
    _heading(c, f"Del registro al pago · {phase}", RIGHT, top - 12, COLUMN)
    _funnel(c, ctx["funnel"], RIGHT, top - 36, COLUMN, row_h=37)
    top -= 22 + 104 + 18
    _heading(c, "Presupuesto, ejecución y pagos por fase", M, top - 12, FULL, "Montos en USD")
    rows = [{"place": p["name"], "period": p["period_short"].capitalize(), "participants": p["participants"], "budget": p["budget"],
             "executed": p["execution_amount"], "execution": p["execution"], "accredited": p["accredited"], "selected": p["current"]}
            for p in phases]
    columns = [("Fase", "place", 40, "text"), ("Periodo", "period", None, "text"), ("Jóvenes\nparticipantes", "participants", 62, "int"),
               ("Presupuesto\n(USD)", "budget", 68, "int"), ("Ejecutado\n(USD)", "executed", 68, "int"),
               ("Ejecución\n(% del presupuesto)", "execution", 84, "rate"), ("Pagos acreditados\n(USD)", "accredited", 78, "int")]
    top = _table(c, M, top - 24, FULL, columns, rows, row_h=15) - 18
    payments = ctx["payments"]
    if payments:
        _heading(c, "Pagos acreditados por mes", M, top - 12, FULL, "Millones de USD por mes, por fase")
        _columns(c, [p["short"] for p in payments], [p["amount"] for p in payments], M - 4, top - 22, FULL + 8, 96, money=True,
                 colors=[PHASE_COLORS.get(p["phase"], theme.SERIE_BONOS) for p in payments], label_size=7.2)
        _legend(c, [(PHASE_COLORS[f], f"Fase {f}") for f in sorted({p["phase"] for p in payments})], M, top - 22 - 96 - 8)
        top -= 22 + 96 + 16
    _heading(c, "Aspectos destacados", M, top - 12, FULL)
    _two_findings(c, ctx["insights"], top - 24, rows=3, bottom=46)


# --------------------------------------------------------------------------------------- labour management
def labour(c, ctx: dict, pages: int) -> None:
    selected = set(ctx["selected"])
    y = _band(c, ctx, H, emblem_png(selected))
    y = _kpis(c, ctx, y - 18)
    top = y - 20
    level = ctx["map_level"]
    focus = selected if level == "canton" else None
    _heading(c, f"Contratos vigentes por {LEVEL_LABELS[level].lower()}", M, top - 12, COLUMN)
    picture = map_png(ctx["map_values"], layer=level, focus=focus, selected=selected if level == "provincia" else None, mode="light",
                      label=f"Contratos vigentes por {LEVEL_LABELS[level].lower()}", width=4.8, height=3.7, dpi=220)
    map_bottom = _picture(c, picture, M - 6, top - 22, COLUMN + 12, 3.7 / 4.8)
    rank_level = "canton" if level == "canton" or len(selected) == 1 else "provincia"
    rows = ctx["territories"][rank_level][:9]
    whole = len(ctx["territories"][rank_level])
    _heading(c, f"{LEVEL_PLURALS[rank_level]} con más contratos", RIGHT, top - 12, COLUMN, "Contratos vigentes · participación")
    _bars(c, _share_bars(rows, "contracts"), RIGHT, top - 36, COLUMN, 21.5)
    bottom = top - 36 - len(rows) * 21.5
    if whole > len(rows):
        _caption(c, f"{len(rows)} de {number(whole)} {LEVEL_PLURALS[rank_level].lower()} con contratos vigentes", RIGHT, bottom - 2, COLUMN)
    top = min(map_bottom, bottom - 6) - 10
    _heading(c, "Perfil de los contratos vigentes", M, top - 12, FULL, "Participación en el total de contratos vigentes")
    palette = [theme.SERIE_BONOS, theme.LILA_300, theme.ORO, theme.FUCSIA, theme.VIOLETA_500, theme.LILA_200]
    y = top - 32
    for title, parts in ctx["profile"].items():
        y = _stacked(c, title, parts, M, y, FULL, palette) - 9
    _heading(c, "Aspectos destacados", M, y - 6, FULL)
    first = ctx["insights"][:4]
    _two_findings(c, first, y - 18, rows=2, bottom=46)
    ctx["findings_drawn"] = _count_drawn(first, y - 18, 46)
    _next_page(c, ctx, 1, pages)
    _labour_detail(c, ctx)


def _labour_detail(c, ctx: dict) -> None:
    y = _slim_band(c, ctx, "Actividad, contratación y jubilación", f"{ctx['territory_label']} · {ctx['programs_label']}")
    top = y - 24
    _heading(c, "Por rama de actividad", M, top, COLUMN, "Contratos vigentes · participación")
    branches = ctx["branches"][:8]
    _bars(c, _distribution_bars(branches), M, top - 24, COLUMN, 21)
    _heading(c, "Por tipo de contrato", RIGHT, top, COLUMN, "Contratos vigentes · participación")
    kinds = ctx["kinds"][:8]
    _bars(c, _distribution_bars(kinds), RIGHT, top - 24, COLUMN, 21)
    top -= 24 + 8 * 21 + 8
    months = ctx["months"]
    if months:
        registrations = ctx["registrations"]
        _heading(c, f"Contratos registrados por mes en {registrations['year']} que siguen vigentes", M, top - 12, FULL,
                 f"Promedio: {number(registrations['average'])} por mes")
        _columns(c, [m["short"] for m in months], [m["value"] for m in months], M - 4, top - 22, FULL + 8, 96,
                 value_text=lambda v: number(v), label_size=7.6)
        top -= 22 + 96 + 14
    retirement = ctx["retirement"]
    parts = ctx["retirement_parts"]
    if retirement:
        cut = ctx["cut"].get("retirement_label", "")
        _heading(c, "Compensación jubilar por año", M, top - 12, COLUMN, f"Corte: {cut}" if cut else "")
        rows = [{"place": r["label"], "files": r["files"], "amount": r["amount"], "average": r["average"],
                 "selected": r is retirement[-1]} for r in retirement]
        left_bottom = _table(c, M, top - 24, COLUMN, [("Año", "place", None, "text"), ("Expedientes", "files", 50, "int"),
                                                      ("Monto pagado\n(USD)", "amount", 62, "int"), ("Promedio por\nexpediente (USD)", "average", 66, "int")],
                             rows, row_h=15)
        if parts["regimes"]:
            _heading(c, f"Expedientes {ctx['retirement_year']} por régimen laboral", RIGHT, top - 12, COLUMN)
            side = parts["regimes"][:5]
            _bars(c, _share_bars(side, "files"), RIGHT, top - 36, COLUMN, 21)
            right_bottom = top - 36 - len(side) * 21
        else:
            # A territorial selection has no regime detail: the composition of its contracts by self-identification.
            _heading(c, "Por autoidentificación étnica", RIGHT, top - 12, COLUMN, "Contratos vigentes · participación")
            side = ctx["ethnicity"][:5]
            _bars(c, _distribution_bars(side), RIGHT, top - 36, COLUMN, 21)
            right_bottom = top - 36 - len(side) * 21
        top = min(left_bottom, right_bottom) - 10
    remaining = ctx["insights"][ctx.get("findings_drawn", 4):]
    if remaining and top - 70 > BOTTOM:
        _heading(c, "Otros aspectos destacados", M, top - 12, FULL)
        drawn = _count_drawn(remaining[:2], top - 24, 46)
        _two_findings(c, remaining[:2], top - 24, rows=1, bottom=46)
        top = top - 24 - _findings_height(remaining[:drawn], 1) - 6 if drawn else top
    levels = ctx["levels"]
    detail = "canton" if "canton" in levels else "provincia"
    rows = ctx["territories"][detail]
    on_first = ctx["map_level"] == detail and len(rows) <= 9
    if rows and not on_first and top - 90 > BOTTOM:
        room = int((top - 36 - BOTTOM) // 13.6)
        shown = rows[:max(3, room)]
        table = [{"position": i + 1, "place": r["detail"], "contracts": r["contracts"], "share": r["share"]} for i, r in enumerate(shown)]
        _heading(c, f"{LEVEL_PLURALS[detail]} con más contratos vigentes", M, top - 12, FULL,
                 f"{len(table)} de {number(len(rows))} {LEVEL_PLURALS[detail].lower()}" if len(rows) > len(table) else "")
        top = _table(c, M, top - 24, FULL, [("N.º", "position", 24, "center"), (LEVEL_LABELS[detail], "place", None, "text"),
                                            ("Contratos vigentes", "contracts", 90, "int"), ("Participación", "share", 110, "share")],
                     table, row_h=13.6) - 10
    foreign = ctx["foreign"][:6]
    if foreign and top - 110 > BOTTOM:
        limit = max(3, min(len(foreign), int((top - 36 - BOTTOM) // 21)))
        total = ctx.get("foreign_total")
        _heading(c, "Contratos vigentes de personas extranjeras", M, top - 12, FULL,
                 f"{number(total)} contratos en total · principales nacionalidades" if total else "")
        bars = _count_bars(foreign[:limit], "contracts")
        for bar, row in zip(bars, foreign[:limit]):
            bar["text"] = f"{number(row['contracts'])} · {number(row['contracts'] / total * 100 if total else 0, 1)} % de los extranjeros"
        _bars(c, bars, M, top - 36, FULL, 21)


def _distribution_bars(rows: list[dict]) -> list[dict]:
    """Share bars of a distribution: the bar measures the share against the largest, the text gives contracts and share."""
    peak = max([(r.get("share") or 0) for r in rows] or [1]) or 1
    return [{**r, "fraction": (r.get("share") or 0) / peak, "text": f"{number(r['contracts'])} · {number(r['share'], 1)} %"} for r in rows]


# ------------------------------------------------------------------------------------------- social budget
def social_budget(c, ctx: dict, pages: int) -> None:
    y = _band(c, ctx, H, emblem_png())
    y = _kpis(c, ctx, y - 18)
    top = y - 20
    months = ctx["months"]
    selected = next((i for i, m in enumerate(months) if m["selected"]), None)
    _heading(c, "Presupuesto devengado por mes", M, top - 12, FULL, "El mes de la consulta en dorado")
    _columns(c, [m["label"] for m in months], [m["month_accrued"] for m in months], M - 4, top - 22, FULL + 8, 140,
             highlight=selected, money=True)
    top -= 22 + 140 + 14
    _heading(c, "Ejecución acumulada", M, top - 12, COLUMN, "Frente al ritmo uniforme del año")
    picture = execution_png([m["short"] for m in months], [m["execution"] for m in months], [m["month"] for m in months],
                            highlight=selected, width=4.4, height=2.7)
    chart_bottom = _picture(c, picture, M - 4, top - 22, COLUMN + 8, 2.7 / 4.4)
    if len(ctx["groups"]) > 1:
        _heading(c, "Por grupo de gasto", RIGHT, top - 12, COLUMN, "Ejecución y presupuesto aprobado")
        rows = _rate_bars(ctx["groups"], "short")
        for bar, group in zip(rows, ctx["groups"]):
            bar["text"] = f"{number(group['execution'], 1)} % de {usd(group['approved'])}"
    else:
        _heading(c, "Ejecución por programa", RIGHT, top - 12, COLUMN, "Devengado sobre aprobado")
        rows = _rate_bars(ctx["programs"][:4])
        for bar, program in zip(rows, ctx["programs"][:4]):
            bar["text"] = f"{number(program['execution'], 1)} % de {usd(program['approved'])}"
    _bars(c, rows, RIGHT, top - 36, COLUMN, 27)
    right_bottom = top - 36 - len(rows) * 27
    closing = ctx.get("closing")
    if closing:
        room = (right_bottom - 4) - chart_bottom
        right_bottom = _tile(c, RIGHT, right_bottom - 4, COLUMN, max(78, room), "hourglass", f"Ritmo necesario de {closing['months']}",
                             f"{usd(closing['required'])} por mes",
                             f"Para devengar el 100 % del presupuesto aprobado. El promedio de enero a "
                             f"{months[-1]['label'].lower()} fue de {usd(closing['average'])} por mes.")
    top = min(chart_bottom, right_bottom) - 12
    _heading(c, "Aspectos destacados", M, top - 12, FULL)
    _two_findings(c, ctx["insights"], top - 24, rows=3, bottom=46)
    ctx["findings_drawn"] = _count_drawn(ctx["insights"][:6], top - 24, 46)
    _next_page(c, ctx, 1, pages)
    _social_detail(c, ctx)


def _social_detail(c, ctx: dict) -> None:
    y = _slim_band(c, ctx, "Ejecución por programa presupuestario", f"{ctx['territory_label']} · {ctx['programs_label']}")
    top = y - 24
    month_word = next((m["label"] for m in ctx["months"] if m["selected"]), "del mes")
    programs = ctx["programs"]
    _heading(c, "Presupuesto aprobado, devengado y ejecución", M, top, FULL, f"Montos en USD · {ctx['span']}")
    rows = [{"place": p["name"], "approved": p["approved"], "month": p["month_accrued"], "accrued": p["accrued"], "execution": p["execution"],
             "balance": p["balance"]} for p in programs]
    columns = [("Programa presupuestario", "place", None, "text"), ("Aprobado", "approved", 62, "int"),
               (f"Devengado\n{month_word.lower()}", "month", 58, "int"), ("Devengado\nacumulado", "accrued", 62, "int"),
               ("Ejecución", "execution", 74, "rate"), ("Saldo por\ndevengar", "balance", 60, "int")]
    stats = ctx["stats"]
    total = {"place": "Total de la selección", "approved": stats["approved"], "month": stats["month"], "accrued": stats["accrued"],
             "execution": stats["execution"], "balance": stats["balance"], "selected": True}
    top = _table(c, M, top - 12, FULL, columns, rows + ([total] if len(rows) > 1 else []), row_h=14.2) - 22
    matrix = ctx["matrix"]
    closing = ctx.get("closing")
    pending = sorted([p for p in programs if p.get("required") is not None and (p["balance"] or 0) > 0], key=lambda p: -(p["balance"] or 0))
    months = ctx["months"]
    remaining = ctx["insights"][ctx.get("findings_drawn", 4):]
    if len(programs) <= 4:
        # Few programs: each one month by month, as columns as tall as the rest of the page allows.
        _heading(c, "Devengado de cada programa por mes", M, top, FULL, "El mes de la consulta en dorado")
        count = len(programs)
        per_row = 2 if count > 1 else 1
        cell = (FULL - 16 * (per_row - 1)) / per_row
        rows_of_charts = (count + per_row - 1) // per_row
        others = ((12 + 22 + len(pending) * 14.2 + 22) if closing and pending else 0) + (12 + 22 + len(months) * 14.2 + 22) \
            + ((12 + _findings_height(remaining[:4], 2)) if remaining else 0)
        height = max(96, min(250, (top - BOTTOM - others - 22) / rows_of_charts - 34))
        for index, program in enumerate(programs):
            values = matrix["rows"][index]["values"] if index < len(matrix["rows"]) else []
            x = M + (index % per_row) * (cell + 16)
            row_top = top - 18 - (index // per_row) * (height + 34)
            c.setFillColor(NIGHT)
            c.setFont("Display-Bold", 8.4)
            c.drawString(x, row_top, _clip(program["name"], "Display-Bold", 8.4, cell))
            selected = next((i for i, m in enumerate(ctx["months"]) if m["selected"]), None)
            _columns(c, matrix["months"], values, x - 4, row_top - 6, cell + 8, height, highlight=selected, money=True)
        top = top - 18 - ((count + per_row - 1) // per_row) * (height + 34) - 4
    elif matrix["rows"]:
        _heading(c, "Devengado de cada programa por mes", M, top, FULL, "Millones de USD · el tono más intenso marca el mes de mayor devengado")
        top = _matrix(c, M, top - 12, FULL, matrix) - 22
    if closing and pending and top - 80 > BOTTOM:
        limit = max(2, min(len(pending), int((top - 30 - BOTTOM) // 14.2)))
        _heading(c, f"Ritmo necesario para devengar el presupuesto aprobado de {closing['months']}", M, top, FULL, "Montos en USD por mes")
        table = [{"place": p["name"], "average": p["average"], "required": p["required"],
                  "ratio": (p["required"] / p["average"] - 1) * 100 if p["average"] else None} for p in pending[:limit]]
        top = _table(c, M, top - 12, FULL, [("Programa presupuestario", "place", None, "text"),
                                            ("Promedio mensual devengado\n(enero a " + month_word.lower() + ")", "average", 124, "int"),
                                            ("Necesario por mes\nhasta diciembre", "required", 100, "int"),
                                            ("Diferencia frente\nal promedio", "ratio", 84, "spct")], table, row_h=14.2) - 22
    if top - 80 > BOTTOM and len(programs) <= 4:
        rows = [{"place": m["label"], "month": m["month_accrued"], "accrued": m["accrued"], "execution": m["execution"],
                 "pace": m["month"] / 12 * 100, "selected": m["selected"]} for m in months]
        room = int((top - 30 - BOTTOM) // 14.2)
        rows = rows[-max(3, room):]
        _heading(c, "El año mes a mes", M, top, FULL, f"Programas de la selección · {ctx['span']}")
        top = _table(c, M, top - 12, FULL, [("Mes", "place", None, "text"), ("Devengado del mes (USD)", "month", 110, "int"),
                                            ("Devengado acumulado (USD)", "accrued", 120, "int"), ("Ejecución acumulada", "execution", 90, "rate"),
                                            ("Ritmo uniforme", "pace", 70, "pct")], rows, row_h=14.2) - 22
    if remaining and top - 60 > BOTTOM:
        _heading(c, "Otros aspectos destacados", M, top, FULL)
        _two_findings(c, remaining, top - 12, rows=2, bottom=46)


from .risks import render_pdf as risk_summary

RENDERERS = {"contingencias": contingency, "jovenes": youth, "laboral": labour, "presupuesto_social": social_budget,
             "riesgos": risk_summary}
