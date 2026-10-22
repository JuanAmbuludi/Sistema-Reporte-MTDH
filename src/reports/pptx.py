"""Three-slide institutional presentation built with python-pptx.

1. Cover and key figures: the night map on the institutional plate and four figures with icons.
2. Results by province: map with the selection in gold, leading provinces and a territorial finding.
3. Results by program: a native, editable bar chart and the findings with icons.

Every shape is native PowerPoint (text, shapes, an editable chart), so the presenter can retitle or restyle
anything.  Fonts are Century Gothic and Calibri, installed with Microsoft Office.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from src import theme
from .charts import map_png
from .context import millions, number

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
ICONS = ROOT / "assets" / "icons" / "png"
DISPLAY, TEXT = theme.OFFICE_DISPLAY, theme.OFFICE_TEXT
TONES = [theme.MORADO, theme.VIOLETA_500, theme.ORO, theme.FUCSIA]
SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#").upper())


def _box(slide, x, y, w, h, color, shape=MSO_SHAPE.RECTANGLE, line: str | None = None, radius: float | None = None):
    item = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    item.fill.solid()
    item.fill.fore_color.rgb = _rgb(color)
    if line:
        item.line.color.rgb = _rgb(line)
        item.line.width = Pt(1)
    else:
        item.line.fill.background()
    item.shadow.inherit = False
    style = item._element.find(qn("p:style"))
    if style is not None:  # no theme effects: every viewer draws the same flat shape
        item._element.remove(style)
    if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        item.adjustments[0] = radius
    return item


def _text(slide, x, y, w, h, text, *, size=14, color=theme.TINTA, font=TEXT, bold=False, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.TOP, spacing: float | None = None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    lines = text if isinstance(text, list) else [text]
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        if spacing:
            paragraph.line_spacing = spacing
        run = paragraph.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = font
        run.font.color.rgb = _rgb(color)
    return box


def _picture(slide, source, x, y, w=None, h=None):
    stream = BytesIO(source) if isinstance(source, bytes) else str(source)
    return slide.shapes.add_picture(stream, Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)


def _badge(slide, icon: str, cx: float, cy: float, r: float, fill=theme.MORADO, variant="blanco"):
    circle = _box(slide, cx - r, cy - r, 2 * r, 2 * r, fill, shape=MSO_SHAPE.OVAL)
    path = ICONS / f"{icon}-{variant}.png"
    if path.exists():
        size = r * 1.1
        _picture(slide, path, cx - size / 2, cy - size / 2, size, size)
    return circle


def _gradient(shape, stops: list[tuple[float, str]], angle: float = 0):
    shape.fill.gradient()
    shape.fill.gradient_angle = angle
    gradient = shape.fill.gradient_stops
    for stop, (position, color) in zip(gradient, [stops[0], stops[-1]]):
        stop.position = position
        stop.color.rgb = _rgb(color)


def _value(kpi: dict) -> str:
    if kpi["value"] is None:
        return "—"
    return f"USD {millions(kpi['value'])} M" if kpi["kind"] == "money" else number(kpi["value"])


def _header(slide, title: str, subtitle: str):
    band = _box(slide, 0, 0, 13.333, 1.12, theme.MORADO)
    _gradient(band, [(0, theme.MORADO_900), (1, theme.MORADO)], 0)
    _box(slide, 0, 1.12, 13.333, 0.06, theme.ORO)
    _text(slide, 0.55, 0.2, 9.4, 0.55, title, size=26, color="#FFFFFF", font=DISPLAY, bold=True)
    _text(slide, 0.55, 0.7, 9.4, 0.32, subtitle, size=12.5, color="#E4DBF3")
    if LOGO.exists():
        _picture(slide, LOGO, 10.25, 0.28, h=0.62)


def _footer(slide, ctx: dict, page: int, left: float = 0.55):
    color = "#7A748B"
    _text(slide, left, 7.08, 11.2 - left, 0.25, f"{ctx['source']} · {ctx['generated_label'].capitalize()}", size=9.5, color=color)
    _text(slide, 11.8, 7.08, 1.0, 0.25, f"{page} / 3", size=9.5, color=color, align=PP_ALIGN.RIGHT)


def _cover(prs, ctx: dict):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    panel = _box(slide, 0, 0, 5.35, 7.5, theme.MORADO_900)
    _gradient(panel, [(0, "#1E0F3B"), (1, theme.MORADO)], 300)
    night = map_png(ctx["map_values"], mode="night", selected=set(ctx["selected_codes"]), annotate=0, legend=False,
                    width=4.2, height=3.7, dpi=220, scale="quantile")
    _picture(slide, night, 0.75, 3.85, w=4.15)
    if LOGO.exists():
        _picture(slide, LOGO, 0.48, 0.42, h=0.66)
    _text(slide, 0.6, 1.5, 4.4, 0.35, ctx["period_label"], size=13, color=theme.ORO, bold=True)
    title = ctx["title"]
    _text(slide, 0.6, 1.88, 4.45, 1.55, title, size=32 if len(title) > 24 else 36, color="#FFFFFF", font=DISPLAY, bold=True,
          spacing=0.95)
    _box(slide, 0.6, 3.48, 0.9, 0.07, theme.ORO)
    _text(slide, 0.6, 3.62, 4.4, 0.32, f"{ctx['territory_label']} · {ctx['programs_label']}", size=13, color="#E4DBF3")

    _text(slide, 5.85, 0.62, 6.9, 0.5, "Cifras clave", size=24, color=theme.MORADO_900, font=DISPLAY, bold=True)
    _text(slide, 5.85, 1.12, 6.9, 0.35, f"{ctx['module_label']} · {ctx['period_label']} · {ctx['territory_label']}",
          size=13, color=theme.PIZARRA)
    width, height, gap = 3.38, 2.42, 0.28
    for index, kpi in enumerate(ctx["kpis"][:4]):
        x = 5.85 + (index % 2) * (width + gap)
        y = 1.78 + (index // 2) * (height + gap)
        _box(slide, x, y, width, height, "#FFFFFF", shape=MSO_SHAPE.ROUNDED_RECTANGLE, line="#E4DEEE", radius=0.08)
        _box(slide, x, y + 0.3, 0.07, height - 0.6, TONES[index])
        _badge(slide, kpi["icon"], x + 0.66, y + 0.66, 0.34)
        _text(slide, x + 1.15, y + 0.4, width - 1.35, 0.6, kpi["label"], size=13, color=theme.PIZARRA, spacing=0.95)
        value = _value(kpi)
        _text(slide, x + 0.36, y + 1.18, width - 0.5, 0.6, value, size=28 if len(value) < 12 else 24, color=theme.MORADO_900,
              font=DISPLAY, bold=True)
        note = (f"{number(kpi['share'], 1)} % del total nacional" if kpi.get("share") is not None else kpi.get("note", ""))
        if note:
            _text(slide, x + 0.36, y + 1.85, width - 0.5, 0.3, note, size=12, color=theme.MORADO, bold=True)
    _footer(slide, ctx, 1, left=5.85)
    slide.notes_slide.notes_text_frame.text = " ".join(
        f"{k['label']}: {_value(k)}." for k in ctx["kpis"]) + " " + ctx["insights"][0]["text"]


def _territory(prs, ctx: dict):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    people = ctx["labels"]["people"]
    _header(slide, "Resultados por provincia", f"{people} · {ctx['period_label']} · {ctx['territory_label']}")
    picture = map_png(ctx["map_values"], mode="light", selected=set(ctx["selected_codes"]), label=people, annotate=0,
                      width=6.0, height=5.4, dpi=220, legend=True)
    _picture(slide, picture, 0.45, 1.42, h=5.55)
    _text(slide, 7.05, 1.45, 5.7, 0.4, "Principales provincias", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    ranked = [p for p in ctx["provinces"] if p["position"]]
    rows = ranked[:7]
    chosen = [p for p in ranked if p["selected"] and p not in rows]
    if chosen:
        rows = rows[:max(1, 7 - len(chosen))] + chosen[:6]
    peak = max((p["people"] or 0) for p in rows) or 1
    y = 2.0
    for row in rows:
        selected = row["selected"]
        _text(slide, 7.05, y, 4.3, 0.3, f"{row['position']}. {row['name']}", size=13.5, color=theme.MORADO_900 if selected else theme.TINTA,
              bold=selected)
        _text(slide, 10.75, y, 2.0, 0.3, number(row["people"]), size=13.5, color=theme.TINTA, bold=True, align=PP_ALIGN.RIGHT)
        _box(slide, 7.05, y + 0.33, 5.7, 0.09, "#EFECF5", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        share = max(0.02, (row["people"] or 0) / peak)
        _box(slide, 7.05, y + 0.33, 5.7 * share, 0.09, theme.ORO if selected else theme.SERIE_BONOS,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        y += 0.52
    finding = ctx["insights"][1]
    _box(slide, 7.05, 5.82, 5.7, 1.02, theme.LILA_50, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    _badge(slide, finding["icon"], 7.55, 6.33, 0.3)
    _text(slide, 8.0, 5.95, 4.55, 0.8, finding["text"], size=12.5, color=theme.TINTA, anchor=MSO_ANCHOR.MIDDLE)
    _footer(slide, ctx, 2)
    slide.notes_slide.notes_text_frame.text = finding["text"]


def _programs(prs, ctx: dict):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    labels = ctx["labels"]
    item = labels["item"]
    _header(slide, f"Resultados por {item}", f"{labels['people']} · {ctx['period_label']} · {ctx['territory_label']}")
    rows = list(reversed(ctx["programs"]))  # bar charts draw the first category at the bottom
    data = CategoryChartData(number_format="#,##0")
    data.categories = [r["short"] for r in rows]
    data.add_series(labels["people"], [r["people"] or 0 for r in rows])
    frame = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.45), Inches(1.45), Inches(6.95), Inches(5.45), data)
    chart = frame.chart
    chart.has_legend = False
    chart.has_title = False
    chart.font.name = TEXT
    chart.font.size = Pt(12)
    chart.font.color.rgb = _rgb(theme.TINTA)
    plot = chart.plots[0]
    plot.gap_width = 55
    plot.has_data_labels = True
    plot.data_labels.number_format = "#,##0"
    plot.data_labels.number_format_is_linked = False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    plot.data_labels.font.size = Pt(12)
    plot.data_labels.font.bold = True
    plot.data_labels.font.color.rgb = _rgb(theme.TINTA)
    series = plot.series[0]
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = _rgb(theme.SERIE_BONOS)
    value_axis = chart.value_axis
    value_axis.visible = False
    value_axis.has_major_gridlines = False
    value_axis.minimum_scale = 0
    category_axis = chart.category_axis
    category_axis.format.line.fill.background()
    category_axis.tick_labels.font.size = Pt(12)
    category_axis.has_major_gridlines = False

    _text(slide, 7.75, 1.45, 5.0, 0.4, "Aspectos destacados", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    findings = [ctx["insights"][0], *ctx["insights"][2:]][:3]
    y = 2.02
    for finding in findings:
        _box(slide, 7.75, y, 5.05, 1.42, theme.LILA_50, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        _badge(slide, finding["icon"], 8.27, y + 0.71, 0.32)
        _text(slide, 8.78, y + 0.14, 3.85, 1.14, finding["text"], size=12.5, color=theme.TINTA, anchor=MSO_ANCHOR.MIDDLE)
        y += 1.6
    _footer(slide, ctx, 3)
    slide.notes_slide.notes_text_frame.text = " ".join(f["text"] for f in findings)


def generate_pptx(context: dict) -> bytes:
    """Cover with key figures, results by province and results by program."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    props = prs.core_properties
    props.title = f"{context['title']} · {context['period_label']}"
    props.author = context["institution"]
    props.subject = f"{context['module_label']} · {context['territory_label']}"
    props.keywords = "MTDH, InfoReportes, indicadores"
    _cover(prs, context)
    _territory(prs, context)
    _programs(prs, context)
    out = BytesIO()
    prs.save(out)
    return out.getvalue()
