"""One-page executive summary in PDF, drawn with ReportLab (no external renderer).

A4 portrait: an institutional plate with the night map (or the monthly series), four key figures with icons, the
territory or the main breakdown, results by program and the findings.  Same context, palette and fonts (Montserrat
and Public Sans, embedded) as the slides and the data workbook.  Transfers and services, labour management and the
institutional budget share the same composition.
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
from .charts import columns_png, map_png
from .context import PRODUCT, millions, number

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


def _heading(c, text: str, x: float, y: float, width: float) -> None:
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 11)
    c.drawString(x, y, _clip(text, "Display-Bold", 11, width))
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


def _band(c, ctx: dict, top: float, picture: bytes | None, ratio: float = 3.0 / 3.4, kind_label: str = "Resumen ejecutivo") -> float:
    height = 132
    bottom = top - height
    c.saveState()
    path = c.beginPath()
    path.rect(0, bottom, W, height)
    c.clipPath(path, stroke=0, fill=0)
    c.linearGradient(0, bottom, W, top, (C("#1E0F3B"), NIGHT, C("#41246F"), PURPLE), positions=(0, 0.35, 0.7, 1), extend=False)
    c.restoreState()
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
    c.setFillColor(GOLD)
    c.rect(0, bottom - 4, W, 4, stroke=0, fill=1)
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
        c.drawString(x, y, _clip(prefix + row["name"], "Text-Medium", 8.4, width - 76))
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


def _findings(c, items: list[dict], x: float, top: float, width: float, limit: int = 3, bottom: float = 52) -> None:
    style = ParagraphStyle("ins", fontName="Text", fontSize=8.7, leading=12.2, textColor=INK)
    y = top
    for item in items[:limit]:
        para = Paragraph(escape(item["text"]), style)
        _w, h = para.wrap(width - 50, 80)
        box = max(54, h + 22)
        if y - box < bottom:
            break
        c.setFillColor(C(theme.LILA_50))
        c.roundRect(x, y - box, width, box, 8, stroke=0, fill=1)
        _badge(c, item["icon"], x + 21, y - box / 2, 12.5)
        para.drawOn(c, x + 42, y - box / 2 - h / 2 + 1)
        y -= box + 9


def _picture(c, data: bytes, x: float, top: float, width: float, ratio: float) -> float:
    height = width * ratio
    c.drawImage(ImageReader(BytesIO(data)), x, top - height, width=width, height=height, mask="auto")
    return top - height


def _footer(c, ctx: dict) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, 42, W - M, 42)
    c.setFillColor(MUTED)
    c.setFont("Text", 7.6)
    c.drawString(M, 30, f"{ctx['institution']} · {PRODUCT}")
    c.drawRightString(W - M, 30, f"{ctx['source']} · {ctx['generated_label'].capitalize()}")


# ------------------------------------------------------------------------------------------- compositions
def _territorial(c, ctx: dict) -> None:
    layer, focus = ctx.get("map_layer", "provincia"), ctx.get("map_focus", [])
    night = map_png(ctx["map_values"], layer=layer, focus=focus, selected=set(ctx["selected_codes"]), mode="night",
                    legend=False, width=3.4, height=3.0, dpi=200)
    y = _band(c, ctx, H, night)
    y = _kpis(c, ctx, y - 18)
    top = y - 20
    column = (W - 2 * M - 22) / 2
    labels = ctx["labels"]
    people = labels["people"]
    scope = "parroquia" if layer == "parroquia" else "provincia"
    _heading(c, f"{people} por {scope}", M, top - 12, column)
    picture = map_png(ctx["map_values"], layer=layer, focus=focus, selected=set(ctx["selected_codes"]), mode="light",
                      label=f"{people} por {scope}", width=5.0, height=4.6, dpi=220)
    _picture(c, picture, M - 6, top - 22, column + 12, 4.6 / 5.0)
    x = M + column + 22
    parish = ctx.get("parish")
    if parish and len(focus) == 1:
        _heading(c, "Principales parroquias", x, top - 12, column)
        rows = _count_rows(parish["top"][:8], "people", "label")
    else:
        _heading(c, "Principales provincias", x, top - 12, column)
        ranked = [p for p in ctx["provinces"] if p["position"]]
        rows = ranked[:8]
        chosen = [p for p in ranked if p["selected"] and p not in rows]
        if chosen:
            rows = rows[:max(1, 8 - len(chosen))] + chosen[:7]
        rows = _count_rows(rows, "people", "name")
    _bars(c, rows, x, top - 36, column, 29.5)
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
    _findings(c, ctx["insights"], x, top - 26, column, limit=4)


def _budget(c, ctx: dict) -> None:
    selected = set(ctx["selected_zones"])
    night = map_png(ctx["map_values"], layer="zona", selected=selected, mode="night", legend=False, width=3.4, height=3.0, dpi=200)
    y = _band(c, ctx, H, night)
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


def _labour(c, ctx: dict) -> None:
    months = ctx["months"]
    labels, values = [m["short"] for m in months], [m["value"] for m in months]
    average = ctx["info"]["average"]
    night = columns_png(labels, values, mode="night", width=3.8, height=2.4, dpi=200, average=average,
                        value_text=lambda v: f"{number(v / 1000, 1)} mil")
    y = _band(c, ctx, H, night, ratio=2.4 / 3.8)
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


def generate_pdf(context: dict) -> bytes:
    """Render the one-page executive summary of any area."""
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle(f"{context['title']} · Resumen ejecutivo")
    c.setAuthor(context["institution"])
    c.setSubject(f"{context['module_label']} · {context['period_label']} · {context['territory_label']}")
    c.setCreator(PRODUCT)
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    {"presupuesto": _budget, "laboral": _labour}.get(context.get("kind"), _territorial)(c, context)
    _footer(c, context)
    c.showPage()
    c.save()
    return out.getvalue()
