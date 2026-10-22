"""Institutional PDF bulletin rendered with ReportLab (no external renderer).

Same report context, palette, fonts (Montserrat and Public Sans, embedded) and
maps as the Excel workbook: a purple cover plate with the map of Ecuador, KPI
tiles, one chapter per programme family and an optional territorial page.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle, BaseDocTemplate, Frame)

from src import theme
from .charts import bar_chart, map_png
from .context import money, number

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
C = colors.HexColor
PURPLE, NIGHT, GOLD, FUCSIA = C(theme.MORADO), C(theme.MORADO_900), C(theme.ORO), C(theme.FUCSIA)
INK, MUTED, PALE, LAVENDER, LINE = C(theme.TINTA), C("#6E6880"), C(theme.NIEBLA), C(theme.LAVANDA), C("#E7E2EF")
W, H = letter
M = 42
COVER_BAND = 250

_FONTS = {
    "Display": "Montserrat-ExtraBold.ttf", "Display-Bold": "Montserrat-Bold.ttf", "Display-Semi": "Montserrat-SemiBold.ttf",
    "Text": "PublicSans-Regular.ttf", "Text-Medium": "PublicSans-Medium.ttf", "Text-Semi": "PublicSans-SemiBold.ttf", "Text-Bold": "PublicSans-Bold.ttf",
}
for _name, _file in _FONTS.items():
    if _name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(_name, str(FONTS / _file)))


def _styles():
    return {
        "h1": ParagraphStyle("H1", fontName="Display", fontSize=22, leading=26, textColor=NIGHT, spaceAfter=4),
        "h2": ParagraphStyle("H2", fontName="Display-Bold", fontSize=13, leading=17, textColor=NIGHT, spaceBefore=14, spaceAfter=7),
        "lead": ParagraphStyle("Lead", fontName="Text-Semi", fontSize=11.5, leading=15, textColor=PURPLE, spaceAfter=10),
        "body": ParagraphStyle("Body", fontName="Text", fontSize=10, leading=14.5, textColor=INK, spaceAfter=7),
        "bullet": ParagraphStyle("Bullet", fontName="Text", fontSize=10, leading=14.5, textColor=INK, leftIndent=14, bulletIndent=0,
                                 spaceAfter=5, bulletFontName="Text-Bold", bulletColor=GOLD),
        "small": ParagraphStyle("Small", fontName="Text", fontSize=8.2, leading=11.5, textColor=MUTED, spaceAfter=5),
        "cell": ParagraphStyle("Cell", fontName="Text", fontSize=8.6, leading=11, textColor=INK),
        "cell_b": ParagraphStyle("CellB", fontName="Text-Semi", fontSize=8.6, leading=11, textColor=NIGHT),
        "num": ParagraphStyle("Num", fontName="Text", fontSize=8.6, leading=11, textColor=INK, alignment=TA_RIGHT),
        "num_b": ParagraphStyle("NumB", fontName="Text-Bold", fontSize=8.6, leading=11, textColor=NIGHT, alignment=TA_RIGHT),
        "head": ParagraphStyle("Head", fontName="Display-Bold", fontSize=7.8, leading=10, textColor=colors.white),
        "head_r": ParagraphStyle("HeadR", fontName="Display-Bold", fontSize=7.8, leading=10, textColor=colors.white, alignment=TA_RIGHT),
        "kpi_label": ParagraphStyle("KL", fontName="Text-Semi", fontSize=8.6, leading=11, textColor=C(theme.PIZARRA)),
        "kpi_value": ParagraphStyle("KV", fontName="Display", fontSize=21, leading=25, textColor=NIGHT),
        "kpi_note": ParagraphStyle("KN", fontName="Text", fontSize=7.8, leading=10, textColor=MUTED),
        "note": ParagraphStyle("Note", fontName="Text", fontSize=8.8, leading=12.5, textColor=C(theme.MORADO_800)),
    }


def _p(text, style):
    return Paragraph(escape(str(text)), style)


def _logo(canvas, x, y, height):
    if LOGO.exists():
        image = ImageReader(str(LOGO))
        iw, ih = image.getSize()
        # The PNG carries transparent margins: 18 % above and below the artwork.
        canvas.drawImage(image, x, y, width=height * iw / ih, height=height, mask="auto")


def _cover_page(canvas, doc, context, cover_map):
    canvas.saveState()
    band = COVER_BAND
    canvas.setFillColor(NIGHT)
    canvas.rect(0, H - band, W, band, fill=1, stroke=0)
    canvas.setFillColor(PURPLE)
    canvas.rect(W - 262, H - band, 262, band, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, H - band - 5, W, 5, fill=1, stroke=0)
    _logo(canvas, M - 10, H - 88, 70)
    if cover_map:
        reader = ImageReader(BytesIO(cover_map))
        iw, ih = reader.getSize()
        mw = 246
        canvas.drawImage(reader, W - mw - 10, H - band + 10, width=mw, height=mw * ih / iw, mask="auto")
    canvas.setFillColor(C("#D9CCF0"))
    canvas.setFont("Text-Semi", 9.5)
    canvas.drawString(M, H - 106, "Boletín estadístico institucional")
    _footer(canvas, doc, context)
    canvas.restoreState()


def _inner_page(canvas, doc, context):
    canvas.saveState()
    canvas.setFillColor(PURPLE)
    canvas.rect(0, H - 54, W, 54, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, H - 57, W, 3, fill=1, stroke=0)
    _logo(canvas, M - 6, H - 50, 46)
    canvas.setFillColor(colors.white)
    canvas.setFont("Display-Bold", 9)
    canvas.drawRightString(W - M, H - 26, "InfoReportes")
    canvas.setFont("Text", 8.5)
    canvas.setFillColor(C("#E4DBF3"))
    canvas.drawRightString(W - M, H - 39, context["period_label"])
    _footer(canvas, doc, context)
    canvas.restoreState()


def _footer(canvas, doc, context):
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(.6)
    canvas.line(M, 36, W - M, 36)
    canvas.setFont("Text", 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(M, 24, "Ministerio de Trabajo y Desarrollo Humano · InfoReportes")
    canvas.drawCentredString(W / 2, 24, f"Selección {context.get('selection_hash', '')}")
    canvas.drawRightString(W - M, 24, f"Página {doc.page}")


def _kpi_tiles(context, s):
    tiles = []
    for section in context["sections"]:
        tone = FUCSIA if section["id"] == "proteccion_integral" else PURPLE
        noun = "servicios" if section["id"] == "proteccion_integral" else "programas"
        tiles.append((section["people_label"], number(section["people"]), f"{len(section['rows'])} {noun} en la selección", tone))
    if context["units_total"] is not None:
        tiles.append(("Unidades de atención", number(context["units_total"]), "Servicios de protección integral", C(theme.VIOLETA_500)))
    tiles.append((f"Monto fiscal {context['year']}", f"USD {money(context['fiscal_total'], True)} M",
                  f"Acumulado de gobierno: USD {money(context['government_total'], True)} M", GOLD))
    if len(tiles) % 2:
        executed = context["executed_total"]
        tiles.append(("Presupuesto ejecutado", "No disponible" if executed is None else f"USD {money(executed, True)} M",
                      "La fuente no certifica la fase de ejecución" if executed is None else "Ejecución verificada", C(theme.LILA_300)))
    cells = [[_p(label, s["kpi_label"]), Spacer(1, 6), _p(value, s["kpi_value"]), Spacer(1, 4), _p(note, s["kpi_note"])]
             for label, value, note, _tone in tiles]
    rows = [cells[i:i + 2] for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[(W - 2 * M - 12) / 2] * 2, hAlign="LEFT")
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (-1, -1), PALE),
             ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
             ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
             ("LINEBELOW", (0, 0), (-1, -1), 6, colors.white), ("LINEAFTER", (0, 0), (0, -1), 6, colors.white)]
    for index, (_l, _v, _n, tone) in enumerate(tiles):
        r, c = divmod(index, 2)
        style.append(("LINEABOVE", (c, r), (c, r), 3, tone))
    table.setStyle(TableStyle(style))
    return table


def _table(headers, rows, widths, s, total=None, align=None):
    align = align or ["left"] + ["right"] * (len(headers) - 1)
    data = [[_p(h, s["head_r"] if align[i] == "right" else s["head"]) for i, h in enumerate(headers)]]
    for row in rows:
        data.append([_p(c, s["cell_b"] if i == 0 else (s["num"] if align[i] == "right" else s["cell"])) for i, c in enumerate(row)])
    if total:
        data.append([_p(c, s["cell_b"] if i == 0 else (s["num_b"] if align[i] == "right" else s["cell"])) for i, c in enumerate(total)])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, 1), (-1, -1), .35, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    if total:
        style += [("BACKGROUND", (0, -1), (-1, -1), LAVENDER), ("LINEABOVE", (0, -1), (-1, -1), 1.2, PURPLE)]
    table.setStyle(TableStyle(style))
    return table


def _note_box(text, s):
    box = Table([[_p(text, s["note"])]], colWidths=[W - 2 * M], hAlign="LEFT")
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.LILA_50)), ("LINEBEFORE", (0, 0), (0, -1), 3, PURPLE),
                             ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                             ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    return box


def generate_pdf(context: dict) -> bytes:
    """Cover with KPIs, one chapter per programme family and a territorial page."""
    if not context.get("sections"):
        raise ValueError("El reporte no contiene secciones.")
    s = _styles()
    out = BytesIO()
    territory = context.get("territory", [])
    values = {t["code"]: t["people"] for t in territory}
    few = {t["code"] for t in territory if t["code"] != "90"}
    cover_map = map_png(values, mode="night", selected=few if len(few) <= 3 else set(), annotate=0, legend=False,
                        scale="quantile", width=5.4, height=4.6) if territory else None
    doc = BaseDocTemplate(out, pagesize=letter, leftMargin=M, rightMargin=M, topMargin=78, bottomMargin=52,
                          title=context["title"], author=context["author"],
                          subject=f"Estadísticas agregadas de protección social · {context['period_label']}")
    cover_frame = Frame(M, 52, W - 2 * M, H - 52 - COVER_BAND - 14, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    inner_frame = Frame(M, 52, W - 2 * M, H - 52 - 78, id="inner", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=lambda c, d: _cover_page(c, d, context, cover_map)),
        PageTemplate(id="inner", frames=[inner_frame], onPage=lambda c, d: _inner_page(c, d, context)),
    ])
    title_style = ParagraphStyle("CoverTitle", fontName="Display", fontSize=23, leading=27, textColor=colors.white)
    period_style = ParagraphStyle("CoverPeriod", fontName="Display-Bold", fontSize=13, leading=17, textColor=GOLD)
    scope_style = ParagraphStyle("CoverScope", fontName="Text", fontSize=9.5, leading=13, textColor=C("#E9E2F6"))
    heading = Table([[_p(context["title"], title_style)], [_p(context["period_label"], period_style)],
                     [_p("Alcance: " + context["scope_label"], scope_style)]], colWidths=[W - 262 - M - 18], hAlign="LEFT")
    heading.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story = [NextPageTemplate("inner")]
    # The cover heading is drawn inside the purple band through an absolute flowable.
    story.insert(0, _Absolute(heading, M, H - 116))
    story += [_p("Indicadores principales", s["h2"]), _kpi_tiles(context, s), _p("Lectura del corte", s["h2"])]
    for section in context["sections"]:
        for text in section["insights"][1:3]:
            story.append(Paragraph(escape(text), s["bullet"], bulletText="●"))
    executed = context["executed_total"]
    story += [Spacer(1, 6), _note_box(
        "Presupuesto ejecutado: no disponible. El Excel de origen presenta montos presupuestarios acumulados, pero no acredita por sí "
        "solo su fase de ejecución; el indicador se habilita con una fuente adicional validada." if executed is None else
        f"Presupuesto ejecutado verificado para toda la selección: USD {money(executed)}.", s),
        _p("Criterios de lectura", s["h2"]), _p(context["notes"][0], s["small"]),
        _p(context["notes"][1] + f" Fuente: {context['source_label']}; corte {context['period_label'].lower()}.", s["small"])]
    for index, section in enumerate(context["sections"], 1):
        service = section["id"] == "proteccion_integral"
        tone = theme.FUCSIA if service else theme.SERIE_BONOS
        story += [PageBreak(), _p(section["title"], s["h1"]),
                  _p(f"{number(section['people'])} {section['people_label'].lower()}" +
                     (f" · {number(section['units'])} unidades de atención" if section["units"] is not None else ""), s["lead"]),
                  _p(section["insights"][1], s["body"])]
        headers = ["Servicio" if service else "Programa", "Usuarios" if service else "Beneficiarios"]
        if service:
            headers.append("Unidades")
        headers += [f"Fiscal {context['year']} (USD M)", "Gobierno (USD M)"]
        widths = [196, 76, 62, 96, 98] if service else [232, 92, 102, 102]
        rows = []
        for row in section["rows"]:
            values_row = [row["label"], number(row["people"])] + ([number(row["units"])] if service else [])
            rows.append(values_row + [money(row["fiscal"], True), money(row["government"], True)])
        total = ["Total de la selección", number(section["people"])] + ([number(section["units"])] if service else [])
        total += [money(section["fiscal"], True), money(section["government"], True)]
        story += [_table(headers, rows, widths, s, total), Spacer(1, 5),
                  _p("Montos acumulados en millones de USD; el acumulado de gobierno ya incluye el monto fiscal y no se suman entre sí.", s["small"])]
        if len(section["rows"]) > 1:
            tall = 2.25 if len(section["rows"]) > 5 else 1.7
            chart = bar_chart(section["rows"], label=section["people_label"], limit=8, width=8.0, height=tall, color=tone)
            story.append(KeepTogether([_p("Cobertura por " + ("servicio" if service else "programa"), s["h2"]),
                                       Image(BytesIO(chart), width=W - 2 * M, height=(W - 2 * M) * tall / 8.0)]))
        if context.get("include_territory", True) and len(section.get("territories", [])) > 1:
            top = section["territories"][:6]
            chart = bar_chart(top, label=section["people_label"], limit=6, width=8.0, height=1.85, color=tone)
            story.append(KeepTogether([_p("Provincias con mayor cobertura", s["h2"]),
                                       Image(BytesIO(chart), width=W - 2 * M, height=(W - 2 * M) * 1.85 / 8.0),
                                       _p(section["insights"][2] if len(section["insights"]) > 2 else "", s["small"])]))
        story.append(_p("Cobertura agregada; no equivale a personas únicas verificadas. Presupuesto ejecutado: " +
                        ("N/D." if section["executed"] is None else "USD " + money(section["executed"]) + "."), s["small"]))
    if context.get("include_territory", True) and territory:
        image = map_png(values, label="Cobertura reportada", annotate=6, width=6.6, height=5.6)
        top = [t for t in territory if t["code"] != "90"][:8]
        total_people = sum(t["people"] or 0 for t in territory)
        ranking = [[t["label"], number(t["people"]), f"{number((t['people'] or 0) / total_people * 100 if total_people else 0, 1)} %", t.get("region", "")]
                   for t in top]
        map_width = 380
        story += [PageBreak(), _p("Cobertura en el territorio", s["h1"]),
                  _p("Beneficiarios y usuarios reportados por provincia en la selección", s["lead"]),
                  Image(BytesIO(image), width=map_width, height=map_width * 5.6 / 6.6),
                  _p("Provincias con mayor cobertura", s["h2"]),
                  _table(["Provincia", "Cobertura reportada", "Participación", "Región natural"], ranking, [220, 110, 100, 98], s,
                         align=["left", "right", "right", "left"]),
                  Spacer(1, 6), _p("Galápagos se muestra en un recuadro fuera de su posición real. La zona en estudio se incluye en los totales sin "
                                   "polígono en el mapa. La cobertura suma registros de distintos programas.", s["small"])]
    doc.build(story)
    return out.getvalue()


class _Absolute(Spacer):
    """Draw a flowable at a fixed page position without taking space in the frame."""

    def __init__(self, flowable, x, y):
        super().__init__(0, 0)
        self.flowable, self.x, self.y = flowable, x, y

    def draw(self):
        canvas = self.canv
        width, height = self.flowable.wrap(W, H)
        canvas.saveState()
        # Translate from the frame origin to the absolute page coordinates.
        origin_x, origin_y = canvas.absolutePosition(0, 0)
        self.flowable.drawOn(canvas, self.x - origin_x, self.y - height - origin_y)
        canvas.restoreState()
