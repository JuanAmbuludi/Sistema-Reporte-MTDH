"""Editable executive Word bulletin with native tables and real chart assets."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from .charts import bar_chart
from .context import number, money

ROOT = Path(__file__).resolve().parents[2]
PURPLE = "512F8D"
INK = "20202B"
MUTED = "666178"
PALE = "F7F5FA"
LAVENDER = "EBE5F3"


def _shade(cell, fill):
    props = cell._tc.get_or_add_tcPr()
    element = props.find(qn("w:shd"))
    if element is None:
        element = OxmlElement("w:shd")
        props.append(element)
    element.set(qn("w:fill"), fill)


def _cell_border(cell, color="D9D9D9"):
    props = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for name in ["top", "left", "bottom", "right"]:
        edge = OxmlElement("w:" + name)
        for key, value in {"val": "single", "sz": "4", "color": color}.items():
            edge.set(qn("w:" + key), value)
        borders.append(edge)
    props.append(borders)


def _cell_padding(cell, top=90, bottom=90, left=100, right=100):
    props = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for side, value in {"top": top, "bottom": bottom, "left": left, "right": right}.items():
        item = OxmlElement("w:" + side)
        item.set(qn("w:w"), str(value))
        item.set(qn("w:type"), "dxa")
        margins.append(item)
    props.append(margins)


def _font(run, size=11, bold=False, color=INK):
    run.font.name = "Times New Roman"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _para(doc, text, style=None, size=11, color=INK, bold=False, after=6):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.08
    _font(p.add_run(str(text)), size=size, bold=bold, color=color)
    return p


def _table(doc, headers, rows, widths):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for column, width in zip(t.columns, widths):
        column.width = Inches(width)
    for i, value in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.width = Inches(widths[i])
        cell.text = ""
        _shade(cell, PURPLE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(0)
        _font(p.add_run(str(value)), size=9.5, bold=True, color="FFFFFF")
    repeat = OxmlElement("w:tblHeader")
    t.rows[0]._tr.get_or_add_trPr().append(repeat)
    for index, values in enumerate(rows):
        cells = t.add_row().cells
        for i, value in enumerate(values):
            cells[i].width = Inches(widths[i])
            cells[i].text = ""
            _shade(cells[i], LAVENDER if index == len(rows)-1 else ("FFFFFF" if index % 2 == 0 else PALE))
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.RIGHT
            _font(p.add_run(str(value)), size=9.5, bold=index == len(rows)-1)
    for row in t.rows:
        dontsplit = OxmlElement("w:cantSplit")
        row._tr.get_or_add_trPr().append(dontsplit)
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _cell_border(cell)
            _cell_padding(cell)
    return t


def _configure(doc, context):
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.top_margin, sec.bottom_margin = Inches(1.43), Inches(.6)
    sec.left_margin, sec.right_margin = Inches(.7), Inches(.7)
    sec.header_distance, sec.footer_distance = Inches(.4), Inches(.3)
    for name in ["Normal", "Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"]:
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(11)
        style.font.color.rgb = RGBColor.from_string("000000")
        # Some Word templates ship a blue bottom border in Title. Remove it
        # explicitly so the document remains clean across Word/LibreOffice.
        props = style.element.find(qn("w:pPr"))
        if props is not None:
            for border in list(props.findall(qn("w:pBdr"))):
                props.remove(border)
    doc.styles["Title"].font.size = Pt(26)
    doc.styles["Title"].font.bold = True
    doc.styles["Heading 1"].font.size = Pt(19)
    doc.styles["Heading 1"].font.bold = True
    doc.styles["Heading 2"].font.size = Pt(12)
    doc.styles["Heading 2"].font.bold = True
    for name in ["Title", "Heading 1", "Heading 2"]:
        doc.styles[name].paragraph_format.keep_with_next = True
        doc.styles[name].paragraph_format.space_before = Pt(9)
        doc.styles[name].paragraph_format.space_after = Pt(7)
    h = sec.header
    h.paragraphs[0].paragraph_format.space_after = Pt(0)
    h.paragraphs[0].paragraph_format.space_before = Pt(0)
    h.paragraphs[0].paragraph_format.line_spacing = Pt(1)
    table = h.add_table(rows=1, cols=2, width=Inches(7.1))
    table.autofit = False
    table.columns[0].width, table.columns[1].width = Inches(4.1), Inches(3)
    for cell in table.rows[0].cells:
        _shade(cell, PURPLE)
        _cell_padding(cell, 25, 25, 100, 100)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    logo = ROOT / "assets" / "brand" / "mtdh_logo.png"
    p = table.cell(0, 0).paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    if logo.exists():
        p.add_run().add_picture(str(logo), width=Inches(3.6))
    p = table.cell(0, 1).paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(0)
    _font(p.add_run("INFORMACIÓN ESTADÍSTICA\n" + context["period_label"]), size=10, color="FFFFFF")
    footer = sec.footer.paragraphs[0]
    footer.paragraph_format.space_after = Pt(0)
    _font(footer.add_run("Ministerio de Trabajo y Desarrollo Humano"), size=8, color=MUTED)
    footer.add_run("\t")
    footer.paragraph_format.tab_stops.clear_all()
    footer.paragraph_format.tab_stops.add_tab_stop(Inches(6.75), WD_TAB_ALIGNMENT.RIGHT)
    run = footer.add_run()
    _font(run, size=8, color=MUTED)
    begin, instr, end = OxmlElement("w:fldChar"), OxmlElement("w:instrText"), OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end.set(qn("w:fldCharType"), "end")
    for item in [begin, instr, end]:
        run._r.append(item)
    doc.core_properties.title = context["title"]
    doc.core_properties.author = context["author"]
    doc.core_properties.subject = context["period_label"] + ". Estadísticas agregadas de protección social."
    doc.core_properties.comments = "Selección de datos: " + context["selection_hash"]


def generate_docx(context: dict) -> bytes:
    if not context.get("sections"):
        raise ValueError("El reporte no contiene secciones.")
    doc = Document()
    _configure(doc, context)
    _para(doc, context["title"], "Title", size=26, color="000000", bold=True, after=7)
    _para(doc, context["period_label"], size=12, bold=True, after=5)
    _para(doc, "Ámbito: " + context["scope_label"], size=10, color=MUTED, after=12)
    _para(doc, "Este boletín reúne la cobertura reportada y los montos acumulados de los programas seleccionados. Las cifras corresponden al ámbito territorial indicado y permiten revisar conjuntamente los recursos y la atención registrada.")
    metrics = [[section["people_label"], number(section["people"])] for section in context["sections"]]
    if context["units_total"] is not None:
        metrics.append(["Unidades reportadas de protección integral", number(context["units_total"])])
    metrics += [[f"Acumulado fiscal {context['year']} (USD MM)", money(context["fiscal_total"], True)],
                ["Acumulado de gobierno (USD MM)", money(context["government_total"], True)],
                ["Presupuesto ejecutado validado (USD MM)", money(context["executed_total"], True)]]
    _table(doc, ["Indicador", "Resultado de la selección"], metrics, [4.8, 2.3])
    _para(doc, "Lectura del corte", "Heading 2", size=12, color="000000", bold=True)
    for section in context["sections"]:
        _para(doc, section["insights"][1])
    _para(doc, "Criterios de lectura", "Heading 2", size=12, color="000000", bold=True)
    for note in context["notes"][:3]:
        _para(doc, note, size=9.5, color=MUTED, after=6)
    _para(doc, "Fuente: " + context["source_label"] + ". Corte informado: " + context["period_label"] + ".", size=9, color=MUTED)
    for index, section in enumerate(context["sections"], 1):
        doc.add_page_break()
        _para(doc, f"{index:02d} {section['title']}", "Heading 1", size=19, color="000000", bold=True, after=8)
        _para(doc, f"{number(section['people'])} {section['people_label'].lower()}" + (f" y {number(section['units'])} unidades reportadas" if section["units"] is not None else ""), size=12, bold=True)
        _para(doc, section["insights"][1])
        service = section["id"] == "proteccion_integral"
        headers = ["Servicio" if service else "Programa", "Usuarios" if service else "Beneficiarios"]
        if service:
            headers.append("Unidades")
        headers += [f"Fiscal {context['year']}\nUSD MM", "Gobierno\nUSD MM"]
        widths = [2.35, 1.05, .8, 1.45, 1.45] if service else [3.0, 1.2, 1.45, 1.45]
        rows = []
        for row in section["rows"]:
            vals = [row["label"], number(row["people"])]
            if service:
                vals += [number(row["units"])]
            rows.append(vals + [money(row["fiscal"], True), money(row["government"], True)])
        total = ["Total seleccionado", number(section["people"])]
        if service:
            total += [number(section["units"])]
        rows.append(total + [money(section["fiscal"], True), money(section["government"], True)])
        _table(doc, headers, rows, widths)
        _para(doc, "Montos acumulados en millones de USD. Los subtotales visibles pueden diferir por redondeo.", size=9, color=MUTED, after=5)
        if context.get("include_territory", True):
            _para(doc, "Distribución territorial", "Heading 2", size=12, color="000000", bold=True)
            picture = bar_chart(section["territories"], label=section["people_label"], limit=6,
                                height=2.3 if len(section["rows"]) > 6 else 2.65,
                                color="#4877B4" if service else "#512F8D")
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            p.add_run().add_picture(BytesIO(picture), width=Inches(7.0))
            _para(doc, f"Se muestran hasta seis ámbitos con mayor cobertura entre {len(section['territories'])} seleccionados. " + (section["insights"][2] if len(section["insights"]) > 2 else ""), size=9, color=MUTED)
        else:
            _para(doc, "Cobertura por programa", "Heading 2", size=12, color="000000", bold=True)
            picture = bar_chart(section["rows"], label=section["people_label"], limit=8, height=2.4)
            doc.add_paragraph().add_run().add_picture(BytesIO(picture), width=Inches(7.0))
        _para(doc, "Los conteos agregados no permiten verificar personas únicas. Presupuesto ejecutado: " + ("N/D." if section["executed"] is None else "USD " + money(section["executed"]) + "."), size=9, color=MUTED)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()
