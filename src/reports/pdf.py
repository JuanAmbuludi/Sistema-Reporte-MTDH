"""One-page executive summary in PDF, drawn with ReportLab (no external renderer).

A4 portrait: an institutional plate with the night map, four key figures with icons, the territory (map and
leading provinces), results by program and three findings.  Same context, palette and fonts (Montserrat and
Public Sans, embedded) as the slides and the data workbook.
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
from .charts import map_png
from .context import millions, number

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
ICONS = ROOT / "assets" / "icons" / "png"
C = colors.HexColor
NIGHT, PURPLE, GOLD = C(theme.MORADO_900), C(theme.MORADO), C(theme.ORO)
INK, MUTED, MIST, LINE = C(theme.TINTA), C("#6E6880"), C(theme.NIEBLA), C("#E7E2EF")
TONES = [theme.MORADO, theme.VIOLETA_500, theme.ORO, theme.FUCSIA]
W, H = A4
M = 34

_FONTS = {
    "Display": "Montserrat-ExtraBold.ttf", "Display-Bold": "Montserrat-Bold.ttf", "Display-Semi": "Montserrat-SemiBold.ttf",
    "Text": "PublicSans-Regular.ttf", "Text-Medium": "PublicSans-Medium.ttf", "Text-Semi": "PublicSans-SemiBold.ttf",
    "Text-Bold": "PublicSans-Bold.ttf",
}
for _name, _file in _FONTS.items():
    if _name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_name, str(FONTS / _file)))


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


def _heading(c, text: str, x: float, y: float, width: float) -> None:
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 11)
    c.drawString(x, y, text)
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.8)
    c.line(x, y - 6, x + width, y - 6)


def _value(kpi: dict) -> str:
    if kpi["value"] is None:
        return "—"
    return f"USD {millions(kpi['value'])} M" if kpi["kind"] == "money" else number(kpi["value"])


def _band(c, ctx: dict, top: float) -> float:
    height = 132
    bottom = top - height
    c.saveState()
    path = c.beginPath()
    path.rect(0, bottom, W, height)
    c.clipPath(path, stroke=0, fill=0)
    c.linearGradient(0, bottom, W, top, (C("#1E0F3B"), NIGHT, C("#41246F"), PURPLE), positions=(0, 0.35, 0.7, 1), extend=False)
    c.restoreState()
    night = map_png(ctx["map_values"], mode="night", selected=set(ctx["selected_codes"]), annotate=0, legend=False,
                    width=3.4, height=3.0, dpi=200, scale="quantile")
    c.drawImage(ImageReader(BytesIO(night)), W - M - 150, bottom + 6, width=150, height=150 * 3.0 / 3.4, mask="auto")
    if LOGO.exists():
        logo = ImageReader(str(LOGO))
        iw, ih = logo.getSize()
        c.drawImage(logo, M - 4, top - 44, width=30 * iw / ih, height=30, mask="auto")
    c.setFillColor(C("#FFE7A3"))
    c.setFont("Text-Semi", 9)
    c.drawString(M, top - 64, f"Resumen ejecutivo · {ctx['period_label']}")
    title = ctx["title"]
    size = _fit(title, "Display", 23, W - 2 * M - 170, 14)
    c.setFillColor(colors.white)
    c.setFont("Display", size)
    c.drawString(M, top - 92, title)
    c.setFillColor(C("#E4DBF3"))
    c.setFont("Text", 9.5)
    c.drawString(M, top - 111, _clip(f"{ctx['territory_label']} · {ctx['programs_label']}", "Text", 9.5, W - 2 * M - 170))
    c.setFillColor(GOLD)
    c.rect(0, bottom - 4, W, 4, stroke=0, fill=1)
    return bottom - 4


def _kpis(c, ctx: dict, top: float) -> float:
    gap, height = 10, 74
    width = (W - 2 * M - gap * 3) / 4
    share_word = "del total nacional"
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
        value = _value(kpi)
        size = _fit(value, "Display", 16, width - 22, 10)
        c.setFillColor(NIGHT)
        c.setFont("Display", size)
        c.drawString(x + 12, y + 24, value)
        note = (f"{number(kpi['share'], 1)} % {share_word}" if kpi.get("share") is not None else kpi.get("note", ""))
        if note:
            c.setFillColor(PURPLE)
            c.setFont("Text-Semi", 7)
            c.drawString(x + 12, y + 11, _clip(note, "Text-Semi", 7, width - 20))
    return top - height


def _bars(c, rows: list[dict], x: float, top: float, width: float, row_h: float, label_key: str, money_kind=False) -> None:
    """Name over a thin bar, value at the right; chosen rows in gold."""
    peak = max([(r["value"] or 0) for r in rows] or [1]) or 1
    for i, row in enumerate(rows):
        y = top - i * row_h
        chosen = row.get("selected")
        prefix = f"{row['position']}. " if row.get("position") else ""
        c.setFillColor(NIGHT if chosen else INK)
        c.setFont("Text-Bold" if chosen else "Text-Medium", 8.4)
        value = (f"{millions(row['value'])} M" if money_kind else number(row["value"]))
        c.drawString(x, y, _clip(prefix + row[label_key], "Text-Medium", 8.4, width - 70))
        c.setFont("Text-Bold", 8.4)
        c.drawRightString(x + width, y, value)
        track_y = y - 8
        c.setFillColor(C("#EFECF5"))
        c.roundRect(x, track_y, width, 4.2, 2.1, stroke=0, fill=1)
        share = max(0.0, (row["value"] or 0) / peak)
        if share > 0:
            c.setFillColor(GOLD if chosen else C(theme.SERIE_BONOS))
            c.roundRect(x, track_y, max(4.2, width * share), 4.2, 2.1, stroke=0, fill=1)


def _territory(c, ctx: dict, top: float) -> float:
    column = (W - 2 * M - 22) / 2
    people = ctx["labels"]["people"]
    _heading(c, f"{people} por provincia", M, top - 12, column)
    picture = map_png(ctx["map_values"], mode="light", selected=set(ctx["selected_codes"]), label=people, annotate=0,
                      width=5.0, height=4.6, dpi=220, legend=True)
    c.drawImage(ImageReader(BytesIO(picture)), M - 6, top - 270, width=column + 12, height=(column + 12) * 4.6 / 5.0, mask="auto")
    x = M + column + 22
    _heading(c, "Principales provincias", x, top - 12, column)
    ranked = [p for p in ctx["provinces"] if p["position"]]
    rows = ranked[:8]
    chosen = [p for p in ranked if p["selected"] and p not in rows]
    if chosen:
        rows = rows[:max(1, 8 - len(chosen))] + chosen[:7]
    _bars(c, [{**p, "value": p["people"]} for p in rows], x, top - 36, column, 29.5, "name")
    return top - 280


def _programs_and_findings(c, ctx: dict, top: float) -> None:
    column = (W - 2 * M - 22) / 2
    labels = ctx["labels"]
    _heading(c, f"{labels['people']} por {labels['item']}", M, top - 12, column)
    rows = [{**p, "value": p["people"], "name": p["short"]} for p in ctx["programs"][:8]]
    with_units = bool(labels.get("units")) and len(rows) <= 4
    step = 24 if with_units else 27.5
    _bars(c, rows, M, top - 36, column, step, "name")
    if with_units:
        # Few services leave room for their units of attention, the other count of this module.
        below = top - 36 - len(rows) * step - 12
        _heading(c, f"{labels['units']} por {labels['item']}", M, below, column)
        units = [{**p, "value": p["units"], "name": p["short"]} for p in sorted(ctx["programs"], key=lambda r: -(r["units"] or 0))]
        _bars(c, units, M, below - 24, column, step, "name")
    x = M + column + 22
    _heading(c, "Aspectos destacados", x, top - 12, column)
    style = ParagraphStyle("ins", fontName="Text", fontSize=8.7, leading=12.2, textColor=INK)
    y = top - 26
    for item in ctx["insights"][:3]:
        para = Paragraph(escape(item["text"]), style)
        _w, h = para.wrap(column - 50, 80)
        box = max(54, h + 22)
        c.setFillColor(C(theme.LILA_50))
        c.roundRect(x, y - box, column, box, 8, stroke=0, fill=1)
        _badge(c, item["icon"], x + 21, y - box / 2, 12.5)
        para.drawOn(c, x + 42, y - box / 2 - h / 2 + 1)
        y -= box + 9


def _footer(c, ctx: dict) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, 42, W - M, 42)
    c.setFillColor(MUTED)
    c.setFont("Text", 7.6)
    c.drawString(M, 30, f"{ctx['institution']} · InfoReportes")
    c.drawRightString(W - M, 30, f"{ctx['source']} · {ctx['generated_label'].capitalize()}")


def generate_pdf(context: dict) -> bytes:
    """Render the one-page executive summary."""
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle(f"{context['title']} · Resumen ejecutivo")
    c.setAuthor(context["institution"])
    c.setSubject(f"{context['module_label']} · {context['period_label']} · {context['territory_label']}")
    c.setCreator("InfoReportes")
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    y = _band(c, context, H)
    y = _kpis(c, context, y - 18)
    y = _territory(c, context, y - 20)
    _programs_and_findings(c, context, y - 8)
    _footer(c, context)
    c.showPage()
    c.save()
    return out.getvalue()
