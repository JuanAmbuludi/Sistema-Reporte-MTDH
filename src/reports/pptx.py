"""Three-slide institutional presentation built with python-pptx.

Transfers and services: 1. cover and key figures (night map); 2. results by territory (map, leading provinces or
parishes and a finding); 3. results by program (native chart and findings).
Institutional budget: 1. cover; 2. execution by zone; 3. execution by program.
Labour management: 1. cover (monthly series); 2. contracts registered by month; 3. retirement compensation.

Every shape is native PowerPoint (text, shapes, editable charts), so the presenter can retitle or restyle anything.
Fonts are Century Gothic and Calibri, installed with Microsoft Office.
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
from .charts import columns_png, map_png
from .context import PRODUCT, millions, number
from .pdf import value_text

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


def _cover(prs, ctx: dict, picture: bytes, picture_width: float = 4.15, share_word: str = "del total nacional"):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    panel = _box(slide, 0, 0, 5.35, 7.5, theme.MORADO_900)
    _gradient(panel, [(0, "#1E0F3B"), (1, theme.MORADO)], 300)
    _picture(slide, picture, 0.75 + (4.15 - picture_width) / 2, 3.95, w=picture_width)
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
        value = value_text(kpi)
        _text(slide, x + 0.36, y + 1.18, width - 0.5, 0.6, value, size=28 if len(value) < 12 else (24 if len(value) < 16 else 20),
              color=theme.MORADO_900, font=DISPLAY, bold=True)
        note = (f"{number(kpi['share'], 1)} % {share_word}" if kpi.get("share") is not None else kpi.get("note", ""))
        if note:
            _text(slide, x + 0.36, y + 1.85, width - 0.5, 0.3, note, size=12, color=theme.MORADO, bold=True)
    _footer(slide, ctx, 1, left=5.85)
    slide.notes_slide.notes_text_frame.text = " ".join(f"{k['label']}: {value_text(k)}." for k in ctx["kpis"]) + " " + ctx["insights"][0]["text"]


def _ranked(slide, rows: list[dict], x: float, y: float, width: float, step: float = 0.52):
    """Rows with ``name``, ``text``, ``fraction`` and optionally ``selected``: name, figure and a thin bar."""
    for row in rows:
        selected = row.get("selected")
        _text(slide, x, y, width - 1.6, 0.3, row["name"], size=13.5, color=theme.MORADO_900 if selected else theme.TINTA, bold=bool(selected))
        _text(slide, x + width - 2.0, y, 2.0, 0.3, row["text"], size=13.5, color=theme.TINTA, bold=True, align=PP_ALIGN.RIGHT)
        _box(slide, x, y + 0.33, width, 0.09, "#EFECF5", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        _box(slide, x, y + 0.33, max(0.02, width * max(0.0, min(1.0, row.get("fraction") or 0))), 0.09,
             theme.ORO if selected else theme.SERIE_BONOS, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        y += step
    return y


def _finding(slide, finding: dict, x: float, y: float, w: float, h: float):
    _box(slide, x, y, w, h, theme.LILA_50, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    _badge(slide, finding["icon"], x + 0.5, y + h / 2, 0.3)
    _text(slide, x + 0.95, y + 0.12, w - 1.15, h - 0.24, finding["text"], size=12.5, color=theme.TINTA, anchor=MSO_ANCHOR.MIDDLE)


def _findings_column(slide, findings: list[dict], x: float = 7.75, y: float = 2.02, w: float = 5.05, h: float = 1.42, step: float = 1.6):
    for finding in findings:
        _box(slide, x, y, w, h, theme.LILA_50, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        _badge(slide, finding["icon"], x + 0.52, y + h / 2, 0.32)
        _text(slide, x + 1.03, y + 0.14, w - 1.2, h - 0.28, finding["text"], size=12.5, color=theme.TINTA, anchor=MSO_ANCHOR.MIDDLE)
        y += step


def _bar_chart(slide, categories: list[str], values: list[float], name: str, *, x=0.45, y=1.45, w=6.95, h=5.45,
               number_format="#,##0", chart_type=XL_CHART_TYPE.BAR_CLUSTERED, maximum: float | None = None):
    data = CategoryChartData(number_format=number_format)
    data.categories = categories
    data.add_series(name, values)
    frame = slide.shapes.add_chart(chart_type, Inches(x), Inches(y), Inches(w), Inches(h), data)
    chart = frame.chart
    chart.has_legend = False
    chart.has_title = False
    chart.font.name = TEXT
    chart.font.size = Pt(12)
    chart.font.color.rgb = _rgb(theme.TINTA)
    plot = chart.plots[0]
    plot.gap_width = 55
    plot.has_data_labels = True
    plot.data_labels.number_format = number_format
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
    if maximum is not None:
        value_axis.maximum_scale = maximum
    category_axis = chart.category_axis
    category_axis.format.line.fill.background()
    category_axis.tick_labels.font.size = Pt(12)
    category_axis.has_major_gridlines = False
    return chart


# ------------------------------------------------------------------------------------- transfers and services
def _territorial(prs, ctx: dict):
    layer, focus = ctx.get("map_layer", "provincia"), ctx.get("map_focus", [])
    selected = set(ctx["selected_codes"])
    night = map_png(ctx["map_values"], layer=layer, focus=focus, selected=selected, mode="night", legend=False,
                    width=4.2, height=3.7, dpi=220)
    _cover(prs, ctx, night)

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    people = ctx["labels"]["people"]
    _header(slide, "Resultados por territorio", f"{people} · {ctx['period_label']} · {ctx['territory_label']}")
    scope = "parroquia" if layer == "parroquia" else "provincia"
    picture = map_png(ctx["map_values"], layer=layer, focus=focus, selected=selected, mode="light", label=f"{people} por {scope}",
                      width=6.0, height=5.4, dpi=220)
    _picture(slide, picture, 0.45, 1.42, h=5.55)
    parish = ctx.get("parish")
    if parish and len(focus) == 1:
        title = "Principales parroquias"
        top = parish["top"][:7]
        peak = max((r["people"] or 0) for r in top) or 1
        rows = [{"name": r["label"], "text": number(r["people"]), "fraction": (r["people"] or 0) / peak} for r in top]
    else:
        title = "Principales provincias"
        ranked = [p for p in ctx["provinces"] if p["position"]]
        chosen_rows = ranked[:7]
        chosen = [p for p in ranked if p["selected"] and p not in chosen_rows]
        if chosen:
            chosen_rows = chosen_rows[:max(1, 7 - len(chosen))] + chosen[:6]
        peak = max((p["people"] or 0) for p in chosen_rows) or 1
        rows = [{"name": f"{p['position']}. {p['name']}", "text": number(p["people"]), "fraction": (p["people"] or 0) / peak,
                 "selected": p["selected"]} for p in chosen_rows]
    _text(slide, 7.05, 1.45, 5.7, 0.4, title, size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    _ranked(slide, rows, 7.05, 2.0, 5.7)
    finding = next((i for i in ctx["insights"] if i["icon"] == "map"), ctx["insights"][1]) if parish and len(focus) == 1 else ctx["insights"][1]
    _finding(slide, finding, 7.05, 5.82, 5.7, 1.02)
    _footer(slide, ctx, 2)
    slide.notes_slide.notes_text_frame.text = finding["text"]

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    labels = ctx["labels"]
    _header(slide, f"Resultados por {labels['item']}", f"{labels['people']} · {ctx['period_label']} · {ctx['territory_label']}")
    programs = [p for p in ctx["programs"] if (p["people"] or 0) > 0] or ctx["programs"]
    rows = list(reversed(programs))  # bar charts draw the first category at the bottom
    _bar_chart(slide, [r["short"] for r in rows], [r["people"] or 0 for r in rows], labels["people"])
    _text(slide, 7.75, 1.45, 5.0, 0.4, "Aspectos destacados", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    findings = [i for i in ctx["insights"] if i["icon"] in ("award", "trending-up", "banknote")][:3]
    _findings_column(slide, findings)
    _footer(slide, ctx, 3)
    slide.notes_slide.notes_text_frame.text = " ".join(f["text"] for f in findings)


# -------------------------------------------------------------------------------------- institutional budget
def _budget(prs, ctx: dict):
    selected = set(ctx["selected_zones"])
    night = map_png(ctx["map_values"], layer="zona", selected=selected, mode="night", legend=False, width=4.2, height=3.7, dpi=220)
    _cover(prs, ctx, night, share_word="del total institucional")

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, "Ejecución por zona", f"Devengado sobre codificado · {ctx['period_label']} · {ctx['territory_label']}")
    picture = map_png(ctx["map_values"], layer="zona", selected=selected, mode="light", rate=True,
                      label="Ejecución presupuestaria por zona", width=6.0, height=5.4, dpi=220)
    _picture(slide, picture, 0.45, 1.42, h=5.55)
    _text(slide, 7.05, 1.45, 5.7, 0.4, "Planta central y zonas", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    rows = [{"name": z["name"], "text": f"{number(z['execution'], 1)} %" if z["execution"] is not None else "—",
             "fraction": (z["execution"] or 0) / 100, "selected": z.get("selected")} for z in ctx["zones"]]
    _ranked(slide, rows, 7.05, 1.98, 5.7, step=0.42)
    finding = next((i for i in ctx["insights"] if i["icon"] == "map"), ctx["insights"][0])
    _finding(slide, finding, 7.05, 5.95, 5.7, 0.95)
    _footer(slide, ctx, 2)
    slide.notes_slide.notes_text_frame.text = finding["text"]

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, "Ejecución por programa", f"Devengado sobre codificado · {ctx['period_label']} · {ctx['territory_label']}")
    rows = list(reversed(ctx["programs"]))
    chart = _bar_chart(slide, [r["short"] for r in rows], [(r["execution"] or 0) / 100 for r in rows], "Ejecución presupuestaria",
                       number_format="0.0%", maximum=1.0)
    chart.plots[0].gap_width = 70
    _text(slide, 7.75, 1.45, 5.0, 0.4, "Aspectos destacados", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    findings = [i for i in ctx["insights"] if i["icon"] != "map"][:3]
    _findings_column(slide, findings)
    _footer(slide, ctx, 3)
    slide.notes_slide.notes_text_frame.text = " ".join(f["text"] for f in findings)


# ---------------------------------------------------------------------------------------- labour management
def _labour(prs, ctx: dict):
    months, info = ctx["months"], ctx["info"]
    labels, values = [m["short"] for m in months], [m["value"] for m in months]
    night = columns_png(labels, values, mode="night", width=4.4, height=2.9, dpi=220, average=info["average"],
                        value_text=lambda v: f"{number(v / 1000, 1)} mil")
    _cover(prs, ctx, night, picture_width=4.3)

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, "Contratación laboral", f"Contratos registrados de {ctx['span']} de {ctx['year']} que siguen vigentes · Total nacional")
    _bar_chart(slide, [m["label"] for m in months], values, "Contratos registrados", x=0.45, y=1.45, w=8.1, h=5.45,
               chart_type=XL_CHART_TYPE.COLUMN_CLUSTERED)
    _text(slide, 8.95, 1.45, 3.9, 0.4, "Contratos vigentes", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    _text(slide, 8.95, 1.95, 3.9, 0.6, number(info["stock"]), size=34, color=theme.MORADO_900, font=DISPLAY, bold=True)
    _text(slide, 8.95, 2.62, 3.9, 0.3, f"Al {info['stock_label']}", size=12, color=theme.PIZARRA)
    share = (info["cohorts_share"] or 0) / 100
    _box(slide, 8.95, 3.2, 3.85, 0.34, theme.LILA_200, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
    _box(slide, 8.95, 3.2, max(0.2, 3.85 * share), 0.34, theme.SERIE_BONOS, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
    _text(slide, 8.95, 3.62, 3.9, 0.6, f"{number(info['cohorts_share'], 1)} % se registró de {ctx['span']} de {ctx['year']}",
          size=12.5, color=theme.MORADO, bold=True)
    finding = ctx["insights"][1]
    _finding(slide, finding, 8.95, 4.55, 3.9, 2.25)
    _footer(slide, ctx, 2)
    slide.notes_slide.notes_text_frame.text = finding["text"]

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, "Compensaciones jubilares", f"Exservidores y extrabajadores públicos · Año {info['retirees_year']}")
    amount = f"{'Más de ' if info['compensation_lower_bound'] else ''}USD {millions(info['compensation'], 0)} M"
    average = info["compensation"] / info["retirees"] if info.get("compensation") and info.get("retirees") else None
    tiles = [("user-check", "Personas compensadas", number(info["retirees"])), ("coins", "Recursos destinados", amount)]
    if average:
        tiles.append(("banknote", "Promedio por persona", f"{'Más de ' if info['compensation_lower_bound'] else ''}USD {number(average)}"))
    for index, (icon, label, value) in enumerate(tiles):
        y = 1.62 + index * 1.72
        _box(slide, 0.55, y, 6.2, 1.5, "#FFFFFF", shape=MSO_SHAPE.ROUNDED_RECTANGLE, line="#E4DEEE", radius=0.08)
        _box(slide, 0.55, y + 0.25, 0.07, 1.0, TONES[(index + 2) % 4])
        _badge(slide, icon, 1.3, y + 0.75, 0.38)
        _text(slide, 2.0, y + 0.28, 4.5, 0.35, label, size=14, color=theme.PIZARRA)
        _text(slide, 2.0, y + 0.66, 4.6, 0.6, value, size=28, color=theme.MORADO_900, font=DISPLAY, bold=True)
    _text(slide, 7.75, 1.45, 5.0, 0.4, "Aspectos destacados", size=18, color=theme.MORADO_900, font=DISPLAY, bold=True)
    findings = [ctx["insights"][2], ctx["insights"][0], ctx["insights"][3]]
    _findings_column(slide, findings)
    _footer(slide, ctx, 3)
    slide.notes_slide.notes_text_frame.text = " ".join(f["text"] for f in findings)


def generate_pptx(context: dict) -> bytes:
    """Three slides for the area of the selection."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    props = prs.core_properties
    props.title = f"{context['title']} · {context['period_label']}"
    props.author = context["institution"]
    props.subject = f"{context['module_label']} · {context['territory_label']}"
    props.keywords = f"MTDH, {PRODUCT}, indicadores"
    {"presupuesto": _budget, "laboral": _labour}.get(context.get("kind"), _territorial)(prs, context)
    out = BytesIO()
    prs.save(out)
    return out.getvalue()
