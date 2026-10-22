"""A paginated executive bulletin with portable ReportLab rendering."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

from .charts import bar_chart
from .context import number, money

ROOT = Path(__file__).resolve().parents[2]
PURPLE = colors.HexColor("#512F8D")
NAVY = colors.HexColor("#172849")
INK = colors.HexColor("#20202B")
MUTED = colors.HexColor("#666178")
PALE = colors.HexColor("#F7F5FA")
LAVENDER = colors.HexColor("#EBE5F3")

pdfmetrics.registerFont(TTFont("MTDH", str(ROOT / "assets" / "fonts" / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("MTDH-Bold", str(ROOT / "assets" / "fonts" / "DejaVuSans-Bold.ttf")))


def _styles():
    return {
        "title": ParagraphStyle("ReportTitle", fontName="MTDH-Bold", fontSize=25, leading=29, textColor=INK, spaceAfter=10),
        "section": ParagraphStyle("Section", fontName="MTDH-Bold", fontSize=21, leading=25, textColor=PURPLE, spaceAfter=10),
        "sub": ParagraphStyle("Sub", fontName="MTDH-Bold", fontSize=12.5, leading=16, textColor=INK, spaceBefore=12, spaceAfter=8),
        "body": ParagraphStyle("Body", fontName="MTDH", fontSize=10.1, leading=14.2, textColor=INK, spaceAfter=9),
        "meta": ParagraphStyle("Meta", fontName="MTDH", fontSize=9.1, leading=12.5, textColor=MUTED, spaceAfter=8),
        "small": ParagraphStyle("Small", fontName="MTDH", fontSize=8, leading=11, textColor=MUTED, spaceAfter=6),
        "cell": ParagraphStyle("Cell", fontName="MTDH", fontSize=8.3, leading=11.2, textColor=INK),
        "num": ParagraphStyle("Num", fontName="MTDH", fontSize=8.3, leading=11.2, textColor=INK, alignment=TA_RIGHT),
        "head": ParagraphStyle("Head", fontName="MTDH-Bold", fontSize=8, leading=10.5, textColor=colors.white),
        "head_num": ParagraphStyle("HeadNum", fontName="MTDH-Bold", fontSize=8, leading=10.5, textColor=colors.white, alignment=TA_RIGHT),
        "big": ParagraphStyle("Big", fontName="MTDH-Bold", fontSize=25, leading=30, textColor=PURPLE),
        "metric": ParagraphStyle("Metric", fontName="MTDH", fontSize=9.2, leading=12, textColor=MUTED),
    }


def _p(text, style):
    return Paragraph(escape(str(text)), style)


def _table(headers, rows, widths, s):
    data = [[_p(h, s["head"] if i == 0 else s["head_num"]) for i, h in enumerate(headers)]]
    data += [[_p(c, s["cell"] if i == 0 else s["num"]) for i, c in enumerate(row)] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LINEBELOW", (0, 0), (-1, 0), .6, PURPLE),
        ("LINEBELOW", (0, 1), (-1, -1), .35, LAVENDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _header(canvas, doc, context, page_count):
    canvas.saveState()
    w, h = letter
    canvas.setFillColor(PURPLE)
    canvas.rect(40, h-91, w-80, 58, fill=1, stroke=0)
    logo = ROOT / "assets" / "brand" / "mtdh_logo.png"
    if logo.exists():
        canvas.drawImage(str(logo), 50, h-87, width=212, height=50.5, mask="auto", preserveAspectRatio=True)
    canvas.setFillColor(colors.white)
    canvas.setFont("MTDH-Bold", 9)
    canvas.drawRightString(w-54, h-55, "INFORMACIÓN ESTADÍSTICA")
    canvas.setFont("MTDH", 9)
    canvas.drawRightString(w-54, h-72, context["period_label"])
    canvas.setStrokeColor(LAVENDER)
    canvas.setLineWidth(.6)
    canvas.line(40, 39, w-40, 39)
    canvas.setFont("MTDH", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(40, 25, "Ministerio de Trabajo y Desarrollo Humano")
    canvas.drawRightString(w-40, 25, f"Página {doc.page}")
    canvas.restoreState()


def _metrics(context, s):
    metrics = []
    for section in context["sections"]:
        metrics.append((number(section["people"]), section["people_label"]))
    if context["units_total"] is not None:
        metrics.append((number(context["units_total"]), "Unidades reportadas de protección integral"))
    metrics.append((f"USD {money(context['fiscal_total'], True)} MM", f"Acumulado fiscal {context['year']}"))
    if len(metrics) % 2:
        metrics.append(("N/D" if context["executed_total"] is None else f"USD {money(context['executed_total'], True)} MM", "Presupuesto ejecutado validado"))
    grid = []
    for i in range(0, len(metrics), 2):
        grid.append([[ _p(value, s["big"]), Spacer(1, 4), _p(label, s["metric"]) ] for value, label in metrics[i:i+2]])
    t = Table(grid, colWidths=[266, 266], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 17),
        ("LINEBELOW", (0, 0), (-1, -1), .6, LAVENDER),
    ]))
    return t


def generate_pdf(context: dict) -> bytes:
    """Generate executive overview + one chapter page per selected section."""
    if not context.get("sections"):
        raise ValueError("El reporte no contiene secciones.")
    s = _styles()
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=letter, rightMargin=40, leftMargin=40,
                            topMargin=111, bottomMargin=55,
                            title=context["title"], author=context["author"],
                            subject=f"Estadísticas agregadas de protección social - {context['period_label']}")
    story = [_p(context["title"], s["title"]), _p(context["period_label"], s["sub"]),
             _p("Ámbito: " + context["scope_label"], s["meta"]),
             _p("Este boletín reúne la cobertura reportada y los montos acumulados de los programas seleccionados. Las cifras corresponden al ámbito territorial indicado y permiten revisar conjuntamente los recursos y la atención registrada.", s["body"]),
             _metrics(context, s), Spacer(1, 10), _p("Lectura del corte", s["sub"])]
    for section in context["sections"]:
        story.append(_p(section["insights"][1], s["body"]))
    story += [_p("Presupuesto ejecutado", s["sub"]),
              _p("N/D. El Excel de origen presenta montos presupuestarios acumulados, pero no acredita por sí solo su condición de ejecución. Este indicador se habilita cuando existe una fuente adicional validada." if context["executed_total"] is None else f"USD {money(context['executed_total'])}. El valor corresponde a registros con validación adicional de ejecución en toda la selección.", s["body"]),
              _p("Criterios de lectura", s["sub"]), _p(context["notes"][0], s["small"]),
              _p(context["notes"][1], s["small"]),
              _p("Fuente: " + context["source_label"] + ". Corte informado: " + context["period_label"] + ".", s["small"])]
    for index, section in enumerate(context["sections"], 1):
        story.append(PageBreak())
        story += [_p(f"{index:02d}  {section['title']}", s["section"]),
                  _p(f"{number(section['people'])} {section['people_label'].lower()}" + (f"   /   {number(section['units'])} unidades reportadas" if section["units"] is not None else ""), s["sub"]),
                  _p(section["insights"][1], s["body"])]
        is_service = section["id"] == "proteccion_integral"
        headers = ["Servicio" if is_service else "Programa", "Usuarios" if is_service else "Beneficiarios"]
        if is_service:
            headers += ["Unidades"]
        headers += [f"Fiscal {context['year']} USD MM", "Gobierno USD MM"]
        widths = [183, 77, 66, 101, 105] if is_service else [211, 101, 110, 110]
        rows = []
        for row in section["rows"]:
            values = [row["label"], number(row["people"])]
            if is_service:
                values += [number(row["units"])]
            values += [money(row["fiscal"], True), money(row["government"], True)]
            rows.append(values)
        total = ["Total seleccionado", number(section["people"])]
        if is_service:
            total += [number(section["units"])]
        total += [money(section["fiscal"], True), money(section["government"], True)]
        rows.append(total)
        table = _table(headers, rows, widths, s)
        table.setStyle(TableStyle([("BACKGROUND", (0, -1), (-1, -1), LAVENDER), ("LINEABOVE", (0, -1), (-1, -1), .7, PURPLE)]))
        story += [table, Spacer(1, 7), _p("Montos acumulados, expresados en millones de USD. Las diferencias de centésimas pueden obedecer al redondeo de cada fila.", s["small"])]
        if context.get("include_territory", True):
            story.append(_p("Distribución territorial", s["sub"]))
            chart = bar_chart(section["territories"], label=section["people_label"], limit=6, width=8.0, height=2.3 if len(section["rows"]) > 6 else 2.65,
                              color="#512F8D" if not is_service else "#4877B4")
            image = Image(BytesIO(chart), width=532, height=145 if len(section["rows"]) > 6 else 176)
            story += [image, _p(f"Se muestran hasta seis ámbitos con mayor cobertura entre {len(section['territories'])} seleccionados. " + (section["insights"][2] if len(section["insights"]) > 2 else ""), s["small"])]
        else:
            chart = bar_chart(section["rows"], label=section["people_label"], limit=8, width=8, height=2.4)
            story += [_p("Cobertura por programa", s["sub"]), Image(BytesIO(chart), width=532, height=160)]
        story.append(_p("Cobertura agregada; no equivale a personas únicas verificadas. Presupuesto ejecutado: " + ("N/D." if section["executed"] is None else "USD " + money(section["executed"]) + "."), s["small"]))
    page_count = 1 + len(context["sections"])
    doc.build(story, onFirstPage=lambda c, d: _header(c, d, context, page_count),
              onLaterPages=lambda c, d: _header(c, d, context, page_count))
    return out.getvalue()
