"""Executive summary in PDF (one or two A4 pages), drawn with ReportLab (no external renderer).

Transfers and services: page 1 holds the institutional plate, four key figures, the map and the leading territories
of the chosen level, the results by program and the findings; page 2 the territorial detail (reach by level,
ranked tables with coverage, budget and execution, and how each program weighs in the leading territories).
Institutional budget: page 1 with zones and programs, page 2 with the composition of spending and the executing
units.  Labour management fits one page.  Same context, palette and fonts (Montserrat and Public Sans, embedded)
as the slides and the data workbook.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Paragraph

from src import theme
from .charts import columns_png, emblem_png, map_png
from .context import NO_POLYGON, PRODUCT, millions, number

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
ICONS = ROOT / "assets" / "icons" / "png"
C = colors.HexColor
NIGHT, PURPLE, GOLD = C(theme.MORADO_900), C(theme.MORADO), C(theme.ORO)
INK, MUTED, MIST, LINE = C(theme.TINTA), C("#6E6880"), C(theme.NIEBLA), C("#E7E2EF")
TONES = [theme.MORADO, theme.VIOLETA_500, theme.ORO, theme.FUCSIA]
LEVEL_LABELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}
LEVEL_PLURALS = {"provincia": "Provincias", "canton": "Cantones", "parroquia": "Parroquias"}
W, H = A4
M = 34
BOTTOM = 52   # lowest drawing line: the footer rule sits below it

_FONTS = {
    "Display": "Montserrat-ExtraBold.ttf", "Display-Bold": "Montserrat-Bold.ttf", "Display-Semi": "Montserrat-SemiBold.ttf",
    "Text": "PublicSans-Regular.ttf", "Text-Medium": "PublicSans-Medium.ttf", "Text-Semi": "PublicSans-SemiBold.ttf",
    "Text-Bold": "PublicSans-Bold.ttf",
}
for _name, _file in _FONTS.items():
    if _name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_name, str(FONTS / _file)))
# Paragraph markup (<b>) needs the family to know its bold face.
pdfmetrics.registerFontFamily("Text", normal="Text", bold="Text-Bold", italic="Text", boldItalic="Text-Bold")


def _icon(c, name: str, variant: str, x: float, y: float, size: float) -> None:
    path = ICONS / f"{name}-{variant}.png"
    if path.exists():
        c.drawImage(ImageReader(str(path)), x, y, width=size, height=size, mask="auto")


def _badge(c, name: str, x: float, y: float, r: float, fill=PURPLE, variant="blanco") -> None:
    """Icon centred on a filled circle; (x, y) is the centre."""
    c.setFillColor(fill)
    c.circle(x, y, r, stroke=0, fill=1)
    size = r * 1.12
    _icon(c, name, variant, x - size / 2, y - size / 2, size)


def _fit(text: str, font: str, size: float, width: float, minimum: float = 7) -> float:
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _clip(text: str, font: str, size: float, width: float) -> str:
    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(text: str, font: str, size: float, width: float, lines: int = 3) -> list[str]:
    """Words broken into at most ``lines`` lines that fit ``width``."""
    out, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(candidate, font, size) <= width or not current:
            current = candidate
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    if len(out) > lines:
        out = out[:lines - 1] + [_clip(" ".join(out[lines - 1:]), font, size, width)]
    return out


def _heading(c, text: str, x: float, y: float, width: float, note: str = "") -> None:
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 11)
    c.drawString(x, y, _clip(text, "Display-Bold", 11, width - (pdfmetrics.stringWidth(note, "Text", 7.4) + 10 if note else 0)))
    if note:
        c.setFillColor(MUTED)
        c.setFont("Text", 7.4)
        c.drawRightString(x + width, y + 1, note)
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.8)
    c.line(x, y - 6, x + width, y - 6)


def value_text(kpi: dict) -> str:
    """Key figure as printed: 1.578.019 · USD 1.011,2 M · 71,0 % · Más de USD 229 M."""
    if kpi["value"] is None:
        return "—"
    if kpi["kind"] == "rate":
        return f"{number(kpi['value'], 1)} %"
    if kpi["kind"] == "money":
        amount = f"USD {millions(kpi['value'], kpi.get('decimals', 1))} M"
        return f"Más de {amount}" if kpi.get("lower_bound") else amount
    return number(kpi["value"])


def _plate(c, top: float, height: float) -> float:
    bottom = top - height
    c.saveState()
    path = c.beginPath()
    path.rect(0, bottom, W, height)
    c.clipPath(path, stroke=0, fill=0)
    c.linearGradient(0, bottom, W, top, (C("#1E0F3B"), NIGHT, C("#41246F"), PURPLE), positions=(0, 0.35, 0.7, 1), extend=False)
    c.restoreState()
    c.setFillColor(GOLD)
    c.rect(0, bottom - 4, W, 4, stroke=0, fill=1)
    return bottom


def _band(c, ctx: dict, top: float, picture: bytes | None, ratio: float = 3.0 / 3.4, kind_label: str = "Resumen ejecutivo") -> float:
    """Institutional plate: logo, product, title and scope; the picture at the right carries no figures."""
    bottom = _plate(c, top, 132)
    if picture:
        width = 150 if ratio > 0.6 else 190
        c.drawImage(ImageReader(BytesIO(picture)), W - M - width, bottom + 6, width=width, height=min(124, width * ratio), mask="auto")
    if LOGO.exists():
        logo = ImageReader(str(LOGO))
        iw, ih = logo.getSize()
        c.drawImage(logo, M - 4, top - 44, width=30 * iw / ih, height=30, mask="auto")
    c.setFillColor(C("#FFE7A3"))
    c.setFont("Text-Semi", 9)
    c.drawString(M, top - 64, f"{kind_label} · {ctx['period_label']}")
    title = ctx["title"]
    size = _fit(title, "Display", 23, W - 2 * M - 200, 14)
    c.setFillColor(colors.white)
    c.setFont("Display", size)
    c.drawString(M, top - 92, title)
    c.setFillColor(C("#E4DBF3"))
    c.setFont("Text", 9.5)
    c.drawString(M, top - 111, _clip(f"{ctx['territory_label']} · {ctx['programs_label']}", "Text", 9.5, W - 2 * M - 200))
    return bottom - 4


def _slim_band(c, ctx: dict, title: str, subtitle: str) -> float:
    """Plate of a second page: the section it opens and the scope, with the logo at the right."""
    top = H
    bottom = _plate(c, top, 74)
    if LOGO.exists():
        logo = ImageReader(str(LOGO))
        iw, ih = logo.getSize()
        c.drawImage(logo, W - M - 26 * iw / ih, top - 44, width=26 * iw / ih, height=26, mask="auto")
    c.setFillColor(C("#FFE7A3"))
    c.setFont("Text-Semi", 8.4)
    c.drawString(M, top - 26, f"{ctx['title']} · {ctx['period_label']}")
    c.setFillColor(colors.white)
    c.setFont("Display", 18)
    c.drawString(M, top - 48, title)
    c.setFillColor(C("#E4DBF3"))
    c.setFont("Text", 8.6)
    c.drawString(M, top - 63, _clip(subtitle, "Text", 8.6, W - 2 * M - 160))
    return bottom - 4


def _kpis(c, ctx: dict, top: float) -> float:
    gap, height = 10, 74
    width = (W - 2 * M - gap * 3) / 4
    share_word = ctx.get("share_word", "del total nacional")
    for i, kpi in enumerate(ctx["kpis"][:4]):
        x = M + i * (width + gap)
        y = top - height
        c.setFillColor(MIST)
        c.roundRect(x, y, width, height, 7, stroke=0, fill=1)
        c.setFillColor(C(TONES[i]))
        c.rect(x, y + 8, 3, height - 16, stroke=0, fill=1)
        _badge(c, kpi["icon"], x + 22, top - 20, 10.5, fill=C(theme.LILA_50), variant="morado")
        label = ParagraphStyle("kl", fontName="Text-Semi", fontSize=7.4, leading=8.8, textColor=C(theme.PIZARRA))
        para = Paragraph(escape(kpi.get("short") or kpi["label"]), label)
        _w, h = para.wrap(width - 46, 22)
        para.drawOn(c, x + 38, top - 14 - h + 4)
        value = value_text(kpi)
        size = _fit(value, "Display", 16, width - 22, 9)
        c.setFillColor(NIGHT)
        c.setFont("Display", size)
        c.drawString(x + 12, y + 24, value)
        note = (f"{number(kpi['share'], 1)} % {share_word}" if kpi.get("share") is not None else kpi.get("note", ""))
        if note:
            c.setFillColor(PURPLE)
            c.setFont("Text-Semi", 7)
            c.drawString(x + 12, y + 11, _clip(note, "Text-Semi", 7, width - 20))
    return top - height


def _bars(c, rows: list[dict], x: float, top: float, width: float, row_h: float) -> None:
    """Name over a thin bar and its figure at the right; chosen rows in gold.

    Rows carry ``name``, ``text`` and ``fraction`` (0–1 bar length), and optionally ``selected`` and ``position``.
    """
    for i, row in enumerate(rows):
        y = top - i * row_h
        chosen = row.get("selected")
        prefix = f"{row['position']}. " if row.get("position") else ""
        c.setFillColor(NIGHT if chosen else INK)
        c.setFont("Text-Bold" if chosen else "Text-Medium", 8.4)
        room = width - max(60, pdfmetrics.stringWidth(row["text"], "Text-Bold", 8.4)) - 12
        c.drawString(x, y, _clip(prefix + row["name"], "Text-Bold" if chosen else "Text-Medium", 8.4, room))
        c.setFont("Text-Bold", 8.4)
        c.drawRightString(x + width, y, row["text"])
        track_y = y - 8
        c.setFillColor(C("#EFECF5"))
        c.roundRect(x, track_y, width, 4.2, 2.1, stroke=0, fill=1)
        share = max(0.0, min(1.0, row.get("fraction") or 0))
        if share > 0:
            c.setFillColor(GOLD if chosen else C(theme.SERIE_BONOS))
            c.roundRect(x, track_y, max(4.2, width * share), 4.2, 2.1, stroke=0, fill=1)


def _count_rows(rows: list[dict], key: str, label: str, money: bool = False) -> list[dict]:
    peak = max([(r.get(key) or 0) for r in rows] or [1]) or 1
    return [{**r, "name": r[label], "fraction": (r.get(key) or 0) / peak,
             "text": f"{millions(r.get(key))} M" if money else number(r.get(key))} for r in rows]


def _rate_rows(rows: list[dict], label: str = "short") -> list[dict]:
    return [{**r, "name": r[label], "fraction": (r.get("execution") or 0) / 100,
             "text": f"{number(r.get('execution'), 1)} %" if r.get("execution") is not None else "—"} for r in rows]


def _findings(c, items: list[dict], x: float, top: float, width: float, limit: int = 3, bottom: float = BOTTOM) -> float:
    style = ParagraphStyle("ins", fontName="Text", fontSize=8.6, leading=11.8, textColor=INK)
    y = top
    for item in items[:limit]:
        para = Paragraph(escape(item["text"]), style)
        _w, h = para.wrap(width - 50, 80)
        box = max(42, h + 16)
        if y - box < bottom:
            break
        c.setFillColor(C(theme.LILA_50))
        c.roundRect(x, y - box, width, box, 8, stroke=0, fill=1)
        _badge(c, item["icon"], x + 21, y - box / 2, 12.5)
        para.drawOn(c, x + 42, y - box / 2 - h / 2 + 1)
        y -= box + 7
    return y


def _picture(c, data: bytes, x: float, top: float, width: float, ratio: float) -> float:
    height = width * ratio
    c.drawImage(ImageReader(BytesIO(data)), x, top - height, width=width, height=height, mask="auto")
    return top - height


def _footer(c, ctx: dict, page: int | None = None, pages: int | None = None) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, 42, W - M, 42)
    c.setFillColor(MUTED)
    c.setFont("Text", 7.6)
    c.drawString(M, 30, f"{ctx['institution']} · {PRODUCT}")
    right = f"{ctx['source']} · {ctx['generated_label'].capitalize()}"
    if pages and pages > 1:
        right += f" · Página {page} de {pages}"
    c.drawRightString(W - M, 30, right)


def _next_page(c, ctx: dict, page: int, pages: int) -> None:
    _footer(c, ctx, page, pages)
    c.showPage()
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)


def _reach_tiles(c, tiles: list[dict], x: float, top: float, width: float, height: float = 58) -> float:
    """Territories with coverage at each level; the gold share is how many of them gather half of it."""
    gap = 10
    w = (width - gap * (len(tiles) - 1)) / max(1, len(tiles))
    for i, tile in enumerate(tiles):
        tx = x + i * (w + gap)
        c.setFillColor(MIST)
        c.roundRect(tx, top - height, w, height, 7, stroke=0, fill=1)
        _badge(c, tile["icon"], tx + 19, top - 21, 10.5, fill=C(theme.LILA_50), variant="morado")
        c.setFillColor(C(theme.PIZARRA))
        c.setFont("Text-Semi", 7.6)
        c.drawString(tx + 36, top - 15, tile["title"])
        count = number(tile["count"])
        c.setFillColor(NIGHT)
        c.setFont("Display", 15)
        c.drawString(tx + 36, top - 32, count)
        c.setFillColor(C(theme.PIZARRA))
        c.setFont("Text", 7.4)
        c.drawString(tx + 40 + pdfmetrics.stringWidth(count, "Display", 15), top - 32, tile["with_text"])
        track = w - 24
        c.setFillColor(C("#EBE7F2"))
        c.roundRect(tx + 12, top - height + 19, track, 3.6, 1.8, stroke=0, fill=1)
        share = tile["half"] / tile["count"] if tile["count"] else 0
        c.setFillColor(GOLD)
        c.roundRect(tx + 12, top - height + 19, max(4, track * share), 3.6, 1.8, stroke=0, fill=1)
        c.setFillColor(PURPLE)
        c.setFont("Text-Bold", 7.4)
        half = number(tile["half"])
        c.drawString(tx + 12, top - height + 8, half)
        c.setFont("Text", 7.4)
        c.drawString(tx + 15 + pdfmetrics.stringWidth(half, "Text-Bold", 7.4), top - height + 8,
                     _clip(tile["half_text"], "Text", 7.4, track - 20))
    return top - height


def _cell(value, kind: str) -> str:
    if value is None or value != value:
        return "—"
    if kind == "int":
        return number(value)
    if kind in ("pct", "share"):
        return f"{number(value, 1)} %"
    if kind == "mill":
        return millions(value, 1)
    return str(value)


def _table(c, x: float, top: float, width: float, columns: list[tuple], rows: list[dict], *, row_h: float = 14.2,
           header_h: float = 22) -> float:
    """Ranked table: ``columns`` are (header, key, width, kind) with one ``None`` width that takes the rest.

    Kinds: ``text``, ``center``, ``int``, ``pct``, ``mill`` and ``share`` (a percentage over a thin bar).
    ``selected`` rows read in gold.
    """
    fixed = sum(w for _h, _k, w, _kind in columns if w)
    widths = [w if w else width - fixed for _h, _k, w, _kind in columns]
    c.setFillColor(PURPLE)
    c.roundRect(x, top - header_h, width, header_h, 3.5, stroke=0, fill=1)
    cx = x
    for (header, _key, _w, kind), w in zip(columns, widths):
        lines = header.split("\n")
        c.setFillColor(colors.white)
        c.setFont("Text-Bold", 6.9)
        for index, line in enumerate(lines):
            y = top - header_h / 2 + (len(lines) - 1) * 3.9 - index * 7.8 - 2.4
            if kind == "text":
                c.drawString(cx + 6, y, line)
            elif kind == "center":
                c.drawCentredString(cx + w / 2, y, line)
            else:
                c.drawRightString(cx + w - 6, y, line)
        cx += w
    peaks = {key: max([(r.get(key) or 0) for r in rows] or [1]) or 1 for _h, key, _w, kind in columns if kind == "share"}
    y = top - header_h
    for i, row in enumerate(rows):
        y -= row_h
        chosen = row.get("selected")
        c.setFillColor(C(theme.ORO_100) if chosen else (MIST if i % 2 else colors.white))
        c.rect(x, y, width, row_h, stroke=0, fill=1)
        cx = x
        for (_header, key, _w, kind), w in zip(columns, widths):
            value = row.get(key)
            text = _cell(value, kind)
            base = y + row_h / 2 - 2.6
            if kind == "text":
                c.setFillColor(NIGHT if chosen else INK)
                c.setFont("Text-Bold" if chosen else "Text-Medium", 7.6)
                c.drawString(cx + 6, base, _clip(text, "Text-Medium", 7.6, w - 10))
            elif kind == "center":
                c.setFillColor(MUTED)
                c.setFont("Text-Semi", 7.4)
                c.drawCentredString(cx + w / 2, base, text)
            elif kind == "share":
                c.setFillColor(INK)
                c.setFont("Text-Semi", 7.6)
                c.drawRightString(cx + w - 6, base, text)
                track = w - 46
                c.setFillColor(C("#EBE7F2"))
                c.roundRect(cx + 6, y + row_h / 2 - 1.6, track, 3.2, 1.6, stroke=0, fill=1)
                fraction = max(0.0, min(1.0, (value or 0) / peaks[key]))
                if fraction:
                    c.setFillColor(GOLD if chosen else C(theme.LILA_300))
                    c.roundRect(cx + 6, y + row_h / 2 - 1.6, max(3.2, track * fraction), 3.2, 1.6, stroke=0, fill=1)
            else:
                c.setFillColor(INK)
                c.setFont("Text-Bold" if chosen else "Text-Medium", 7.6)
                c.drawRightString(cx + w - 6, base, text)
            cx += w
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.8)
    c.line(x, y, x + width, y)
    return y


def _heatmap(c, x: float, top: float, width: float, composition: dict, *, label_w: float = 150, row_h: float = 15.2) -> float:
    """Share of each program in the leading territories: one shaded cell per program, its figure inside."""
    programs, rows = composition["programs"], composition["rows"]
    if not programs or not rows:
        return top
    cell = (width - label_w) / len(programs)
    wrapped = [_wrap(name, "Text-Semi", 6.8, cell - 6, 3) for name in programs]
    header_h = 9 + 8 * max(len(lines) for lines in wrapped)
    for j, lines in enumerate(wrapped):
        cx = x + label_w + j * cell + cell / 2
        c.setFillColor(C(theme.PIZARRA))
        c.setFont("Text-Semi", 6.8)
        for index, line in enumerate(lines):
            c.drawCentredString(cx, top - header_h + 5 + (len(lines) - 1 - index) * 8, line)
    shares = [s for r in rows for s in r["shares"] if s is not None]
    peak = min(100.0, max(10.0, -(-max(shares or [10]) // 10) * 10))
    y = top - header_h
    for row in rows:
        y -= row_h
        c.setFillColor(INK)
        c.setFont("Text-Medium", 7.6)
        c.drawRightString(x + label_w - 8, y + row_h / 2 - 2.6, _clip(row["label"], "Text-Medium", 7.6, label_w - 12))
        for j, share in enumerate(row["shares"]):
            cx = x + label_w + j * cell
            t = (share or 0) / peak
            c.setFillColor(C(theme.ramp_at(t, theme.SEQUENTIAL[1:])) if share is not None else C("#F4F2F8"))
            c.rect(cx + 0.8, y + 0.8, cell - 1.6, row_h - 1.6, stroke=0, fill=1)
            c.setFillColor(colors.white if t > 0.5 else INK)
            c.setFont("Text-Semi", 7.2)
            c.drawCentredString(cx + cell / 2, y + row_h / 2 - 2.5, _cell(share, "pct"))
    return y


# ------------------------------------------------------------------------------------------- compositions
def _rank_rows(ctx: dict, level: str, limit: int = 8) -> list[dict]:
    """Leading territories of a level for the bars of page 1 (provinces keep their national place)."""
    if level == "provincia":
        ranked = [p for p in ctx["provinces"] if p["position"]]
        rows = ranked[:limit]
        chosen = [p for p in ranked if p["selected"] and p not in rows]
        if chosen:
            rows = rows[:max(1, limit - len(chosen))] + chosen[:limit - 1]
        return _count_rows(rows, "people", "name")
    rows = [{**r, "name": r["label"]} for r in ctx["territories"].get(level, [])[:limit]]
    return _count_rows(rows, "people", "name")


def _territorial(c, ctx: dict, pages: int) -> None:
    labels = ctx["labels"]
    people = labels["people"]
    levels = ctx.get("levels") or ["provincia"]
    main = levels[-1]
    selected = set(ctx["selected_codes"])
    chosen_map = ctx.get("maps", {}).get(main) or {"layer": ctx["map_layer"], "values": ctx["map_values"], "focus": ctx["map_focus"]}
    focus = chosen_map["focus"]
    y = _band(c, ctx, H, emblem_png(selected - {NO_POLYGON}))
    y = _kpis(c, ctx, y - 18)
    top = y - 20
    column = (W - 2 * M - 22) / 2
    word = LEVEL_LABELS[main].lower()
    _heading(c, f"{people} por {word}", M, top - 12, column)
    picture = map_png(chosen_map["values"], layer=chosen_map["layer"], focus=focus, selected=selected, mode="light",
                      label=f"{people} por {word}", width=5.0, height=4.6, dpi=220)
    _picture(c, picture, M - 6, top - 22, column + 12, 4.6 / 5.0)
    # The territories are detailed on page 2; next to the map, how each program executes (or what it receives).
    x = M + column + 22
    funded = sorted([p for p in ctx["programs"] if p.get("coded") or p.get("fiscal")],
                    key=lambda p: -(p.get("coded") or p.get("fiscal") or 0))[:8]
    if ctx.get("executed_available"):
        _heading(c, f"Ejecución presupuestaria por {labels['item']}", x, top - 12, column)
        _bars(c, _rate_rows(funded), x, top - 36, column, 29.5)
    else:
        _heading(c, f"{labels['fiscal']} por {labels['item']}", x, top - 12, column)
        _bars(c, _count_rows(funded, "fiscal", "short", money=True), x, top - 36, column, 29.5)
    top -= 288
    _heading(c, f"{people} por {labels['item']}", M, top - 12, column)
    programs = [p for p in ctx["programs"] if (p["people"] or 0) > 0][:8] or ctx["programs"][:8]
    with_units = bool(labels.get("units")) and len(programs) <= 4
    step = 24 if with_units else 27.5
    _bars(c, _count_rows(programs, "people", "short"), M, top - 36, column, step)
    if with_units:
        # Few services leave room for their units of attention, the other count of this module.
        below = top - 36 - len(programs) * step - 12
        _heading(c, f"{labels['units']} por {labels['item']}", M, below, column)
        units = sorted(ctx["programs"], key=lambda r: -(r["units"] or 0))
        _bars(c, _count_rows(units, "units", "short"), M, below - 24, column, step)
    _heading(c, "Aspectos destacados", x, top - 12, column)
    first_page = [i for i in ctx["insights"] if i["icon"] not in ("layers", "landmark")]
    _findings(c, first_page, x, top - 26, column, limit=4, bottom=46)
    _next_page(c, ctx, 1, pages)
    _territorial_detail(c, ctx)


def _territory_columns(ctx: dict, level: str) -> list[tuple]:
    labels = ctx["labels"]
    executed = ctx.get("executed_available")
    columns = [("N.º", "position", 24, "center"), (LEVEL_LABELS[level], "place", None, "text"),
               (labels["people"], "people", 62, "int"), ("Participación", "share", 86, "share")]
    if labels.get("units"):
        columns.append(("Unidades", "units", 52, "int"))
    if executed:
        columns += [("Ejecutado\n(millones de USD)", "fiscal", 72, "mill"), ("Ejecución", "execution", 52, "pct")]
    elif level == "provincia":
        columns += [(f"Presupuesto {ctx['year']}\n(millones de USD)", "fiscal", 76, "mill"),
                    ("Acumulado\n(millones de USD)", "government", 72, "mill")]
    else:
        columns.append((f"Presupuesto {ctx['year']}\n(millones de USD)", "fiscal", 76, "mill"))
    return columns


def _territory_table_rows(ctx: dict, level: str, limit: int) -> list[dict]:
    if level == "provincia":
        ranked = [p for p in ctx["provinces"] if p["position"]]
        rows = ranked[:limit]
        chosen = [p for p in ranked if p["selected"] and p not in rows]
        if chosen:
            rows = rows[:max(1, limit - len(chosen))] + chosen[:limit - 1]
        return [{**p, "place": p["name"]} for p in rows]
    return [{**r, "place": r["detail"]} for r in ctx["territories"].get(level, [])[:limit]]


def _territorial_detail(c, ctx: dict) -> None:
    labels = ctx["labels"]
    people_lower = labels["people"].lower()
    levels = ctx.get("levels") or ["provincia"]
    subtitle = f"{ctx['territory_label']} · {ctx['programs_label']}"
    y = _slim_band(c, ctx, "Detalle territorial", subtitle)
    tiles = ctx.get("reach_tiles") or []
    if tiles:
        y = _reach_tiles(c, tiles, M, y - 16, W - 2 * M)
    many = len(levels) > 1
    width = W - 2 * M
    for level in levels:
        limit = 10 if many else (24 if level == "provincia" else 20)
        rows = _territory_table_rows(ctx, level, limit)
        if not rows:
            continue
        total = len([p for p in ctx["provinces"] if p["position"]]) if level == "provincia" else len(ctx["territories"].get(level, []))
        if level == "provincia":
            title = "Posición de las provincias en el país" if ctx["selected_codes"] else f"Provincias con más {people_lower}"
        else:
            title = f"{LEVEL_PLURALS[level]} con más {people_lower}"
        note = f"{len(rows)} de {number(total)}" if total > len(rows) else ""
        _heading(c, title, M, y - 26, width, note)
        y = _table(c, M, y - 38, width, _territory_columns(ctx, level), rows)
    composition = (ctx.get("composition") or {}).get(levels[0]) if not many else None
    if composition and y - 60 - 15.2 * len(composition["rows"]) > BOTTOM:
        level = levels[0]
        article = "los" if level == "canton" else "las"
        _heading(c, f"Distribución por {labels['item']} en {article} {LEVEL_PLURALS[level].lower()} con más {people_lower}", M, y - 26,
                 width, f"Participación en cada {LEVEL_LABELS[level].lower()}")
        _heatmap(c, M, y - 40, width, composition)
    remaining = [i for i in ctx["insights"] if i["icon"] in ("layers", "landmark")]
    if many and remaining and y - 70 > BOTTOM:
        _heading(c, "Aspectos territoriales", M, y - 26, width)
        half = (width - 12) / 2
        for index, item in enumerate(remaining[:2]):
            _findings(c, [item], M + index * (half + 12), y - 40, half, limit=1)


# -------------------------------------------------------------------------------------------------- budget
def _budget(c, ctx: dict, pages: int) -> None:
    selected = set(ctx["selected_zones"])
    y = _band(c, ctx, H, emblem_png(selected, layer="zona"))
    y = _kpis(c, {**ctx, "share_word": "del total institucional"}, y - 18)
    top = y - 20
    column = (W - 2 * M - 22) / 2
    _heading(c, "Ejecución por zona", M, top - 12, column)
    picture = map_png(ctx["map_values"], layer="zona", selected=selected, mode="light", rate=True,
                      label="Ejecución presupuestaria por zona", width=5.0, height=4.6, dpi=220)
    _picture(c, picture, M - 6, top - 22, column + 12, 4.6 / 5.0)
    x = M + column + 22
    _heading(c, "Planta central y zonas", x, top - 12, column)
    _bars(c, _rate_rows(ctx["zones"], "name"), x, top - 36, column, 26)
    top -= 288
    _heading(c, "Ejecución por programa presupuestario", M, top - 12, column)
    _bars(c, _rate_rows(ctx["programs"][:8]), M, top - 36, column, 27.5)
    _heading(c, "Aspectos destacados", x, top - 12, column)
    _findings(c, ctx["insights"], x, top - 26, column, limit=3)
    _next_page(c, ctx, 1, pages)
    _budget_detail(c, ctx)


def _budget_detail(c, ctx: dict) -> None:
    y = _slim_band(c, ctx, "Composición del gasto", f"{ctx['territory_label']} · {ctx['programs_label']}")
    width = W - 2 * M
    column = (width - 22) / 2
    top = y - 26
    _heading(c, "Por grupo de gasto", M, top, column, "Ejecución · codificado")
    groups = _rate_rows(ctx["groups"][:7], "name")
    for row, source in zip(groups, ctx["groups"][:7]):
        row["text"] = f"{number(source['execution'], 1)} % · USD {millions(source['coded'])} M" if source.get("execution") is not None else "—"
    _bars(c, groups, M, top - 24, column, 26)
    x = M + column + 22
    _heading(c, "Por fuente de financiamiento", x, top, column, "Ejecución · codificado")
    sources = _rate_rows(ctx["sources"][:4], "name")
    for row, source in zip(sources, ctx["sources"][:4]):
        row["text"] = f"{number(source['execution'], 1)} % · USD {millions(source['coded'])} M" if source.get("execution") is not None else "—"
    _bars(c, sources, x, top - 24, column, 26)
    below = top - 24 - 26 * len(sources) - 8
    _heading(c, "Por tipo de gasto", x, below, column, "Ejecución · codificado")
    kinds = _rate_rows(ctx["kinds"], "name")
    for row, source in zip(kinds, ctx["kinds"]):
        row["text"] = f"{number(source['execution'], 1)} % · USD {millions(source['coded'])} M" if source.get("execution") is not None else "—"
    _bars(c, kinds, x, below - 24, column, 26)
    y = min(top - 24 - 26 * len(groups), below - 24 - 26 * len(kinds)) - 4
    units = sorted(ctx["units"], key=lambda u: -(u["coded"] or 0))[:16]
    rows = [{"position": i + 1, "place": u["name"], "zone": u.get("zone", ""), "coded": u["coded"], "accrued": u["accrued"],
             "execution": u["execution"], "share": u["share"]} for i, u in enumerate(units)]
    _heading(c, "Unidades ejecutoras con mayor presupuesto codificado", M, y - 18, width,
             f"{len(rows)} de {number(len(ctx['units']))}" if len(ctx["units"]) > len(rows) else "")
    columns = [("N.º", "position", 24, "center"), ("Unidad ejecutora", "place", None, "text"), ("Zona", "zone", 92, "text"),
               ("Codificado\n(millones de USD)", "coded", 74, "mill"), ("Devengado\n(millones de USD)", "accrued", 74, "mill"),
               ("Ejecución", "execution", 52, "pct")]
    y = _table(c, M, y - 30, width, columns, rows)
    # Findings that did not fit on the first page close the composition of spending.
    remaining = ctx["insights"][3:5]
    if remaining and y - 72 > BOTTOM:
        _heading(c, "Aspectos destacados", M, y - 24, width)
        half = (width - 12) / 2
        for index, item in enumerate(remaining):
            _findings(c, [item], M + index * (half + 12), y - 38, half, limit=1)


# -------------------------------------------------------------------------------------------------- labour
def _labour(c, ctx: dict, pages: int) -> None:
    months = ctx["months"]
    labels, values = [m["short"] for m in months], [m["value"] for m in months]
    average = ctx["info"]["average"]
    y = _band(c, ctx, H, emblem_png())
    y = _kpis(c, ctx, y - 18)
    top = y - 20
    full = W - 2 * M
    _heading(c, f"Contratos registrados por mes en {ctx['year']} que siguen vigentes", M, top - 12, full)
    legend = f"Promedio mensual: {number(average)}"
    c.setFont("Text-Semi", 7.6)
    c.setFillColor(C(theme.ORO_700))
    c.drawRightString(W - M, top - 26, legend)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    c.setDash(1.2, 2.6)
    end = W - M - pdfmetrics.stringWidth(legend, "Text-Semi", 7.6) - 6
    c.line(end - 18, top - 23.5, end, top - 23.5)
    c.setDash()
    picture = columns_png(labels, values, mode="light", width=7.6, height=2.9, dpi=220, average=average)
    bottom = _picture(c, picture, M - 4, top - 30, full + 8, 2.9 / 7.6)
    top = bottom - 14
    column = (full - 22) / 2
    info = ctx["info"]
    _heading(c, "Contratos vigentes según su registro", M, top - 12, column)
    share = (info["cohorts_share"] or 0) / 100
    bar_y = top - 58
    c.setFillColor(C(theme.LILA_200))
    c.roundRect(M, bar_y, column, 18, 4, stroke=0, fill=1)
    c.setFillColor(C(theme.SERIE_BONOS))
    c.roundRect(M, bar_y, max(8, column * share), 18, 4, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Text-Bold", 8.4)
    c.drawString(M + 6, bar_y + 6, f"{number(info['cohorts_share'], 1)} %")
    c.setFillColor(NIGHT)
    c.drawRightString(M + column - 6, bar_y + 6, f"{number(100 - (info['cohorts_share'] or 0), 1)} %")
    legend = [(C(theme.SERIE_BONOS), f"Registrados de {ctx['span']} de {ctx['year']}: {number(info['cohorts'])}"),
              (C(theme.LILA_200), f"Registrados en otros periodos: {number(info['stock'] - info['cohorts'])}")]
    for index, (color, text) in enumerate(legend):
        ly = bar_y - 22 - index * 16
        c.setFillColor(color)
        c.roundRect(M, ly, 9, 9, 2, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("Text-Medium", 8.4)
        c.drawString(M + 15, ly + 1.5, text)
    sources_y = bar_y - 80
    _heading(c, "Fuentes de información", M, sources_y, column)
    style = ParagraphStyle("src", fontName="Text", fontSize=8.2, leading=11, textColor=INK)
    y = sources_y - 22
    for label, origin, _url in ctx["sources"]:
        para = Paragraph(f"<b>{escape(label)}</b><br/>{escape(origin)}", style)
        _w, h = para.wrap(column, 60)
        para.drawOn(c, M, y - h)
        y -= h + 10
    x = M + column + 22
    _heading(c, "Aspectos destacados", x, top - 12, column)
    _findings(c, ctx["insights"], x, top - 26, column, limit=4)


def page_count(context: dict) -> int:
    """Pages of the summary: two for the territorial areas and the budget, one for labour management."""
    return 1 if context.get("kind") == "laboral" else 2


def generate_pdf(context: dict) -> bytes:
    """Render the executive summary of any area (one or two pages)."""
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle(f"{context['title']} · Resumen ejecutivo")
    c.setAuthor(context["institution"])
    c.setSubject(f"{context['module_label']} · {context['period_label']} · {context['territory_label']}")
    c.setCreator(PRODUCT)
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    pages = page_count(context)
    {"presupuesto": _budget, "laboral": _labour}.get(context.get("kind"), _territorial)(c, context, pages)
    _footer(c, context, pages, pages)
    c.showPage()
    c.save()
    return out.getvalue()
