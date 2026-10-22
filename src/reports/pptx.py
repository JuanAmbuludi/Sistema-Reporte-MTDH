"""Editable PowerPoint export from the institution's reusable PPTX template.

The template is authored once with native PowerPoint objects.  At runtime this
module fills OOXML text, tables, chart caches and their embedded workbooks.
No Node service, office application, internet access or proprietary SDK is
required to download a presentation from Streamlit.
"""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from math import ceil, isfinite
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree as ET

from .charts import map_png
from .context import money, number

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "presentation.pptx"
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}
REL = NS["r"] + "/"
EMU = 9525
SHORT = {
    "BDH": "BDH", "BDHV": "BDH variable", "BMD": "Bono 1.000 Días",
    "BJGL": "Bono J. Gallegos Lara", "MMA": "Mis Mejores Años",
    "PTV": "Toda Una Vida", "PAM": "Pensión adultos mayores",
    "PCD": "Pensión discapacidad", "DII": "Desarrollo infantil",
    "DIS": "Discapacidades", "PCD_SERV": "Discapacidades", "PE": "Protección especial",
}


def _xml(content):
    return ET.fromstring(content)


def _bytes(root):
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def _q(prefix, local):
    return f"{{{NS[prefix]}}}{local}"


def _fill(root, values):
    for t in root.findall(".//a:t", NS):
        raw = t.text or ""
        for key, value in values.items():
            raw = raw.replace("{{" + key + "}}", str(value))
        t.text = raw


def _font_for_shape(root, name, pixels):
    for s in root.findall(".//p:sp", NS):
        props = s.find("p:nvSpPr/p:cNvPr", NS)
        if props is not None and props.get("name") == name:
            for style in s.findall(".//a:rPr", NS) + s.findall(".//a:defRPr", NS):
                style.set("sz", str(round(pixels * 75)))


def _body_text(body, text):
    """Replace text while keeping cell typography and paragraph settings."""
    old = body.findall("a:p", NS)
    base = deepcopy(old[0])
    run = base.find("a:r", NS)
    run_base = deepcopy(run) if run is not None else ET.Element(_q("a", "r"))
    for p in old:
        body.remove(p)
    for line in str(text).split("\n"):
        p = deepcopy(base)
        for child in list(p):
            if child.tag != _q("a", "pPr"):
                p.remove(child)
        r = deepcopy(run_base)
        for child in list(r):
            if child.tag != _q("a", "rPr"):
                r.remove(child)
        ET.SubElement(r, _q("a", "t")).text = line
        p.append(r)
        body.append(p)


def _row_values(row, values):
    for cell, value in zip(row.findall("a:tc", NS), values):
        _body_text(cell.find("a:txBody", NS), value)


def _populate_table(slide, rows, section, context, last_page):
    tbl = slide.find(".//a:tbl", NS)
    original = tbl.findall("a:tr", NS)
    header, body, total = [deepcopy(x) for x in original]
    for row in original:
        tbl.remove(row)
    _row_values(header, ["Programa o servicio",
                        "Beneficiarios" if section["id"] == "bonos_pensiones" else "Usuarios",
                        "Unidades", f"Fiscal {context.get('year', '')}\nUSD millones", "Gobierno\nUSD millones"])
    header.set("h", str(58 * EMU))
    tbl.append(header)
    body_height = 55 if len(rows) >= 5 else 63
    for idx, item in enumerate(rows):
        row = deepcopy(body)
        row.set("h", str(body_height * EMU))
        _row_values(row, [item["label"], number(item.get("people")), number(item.get("units")),
                          money(item.get("fiscal"), millions=True), money(item.get("government"), millions=True)])
        for cell in row.findall("a:tc", NS):
            fill = cell.find("a:tcPr/a:solidFill/a:srgbClr", NS)
            if fill is not None:
                fill.set("val", "F7F5FA" if idx % 2 == 0 else "FFFFFF")
        tbl.append(row)
    if last_page:
        total.set("h", str(53 * EMU))
        _row_values(total, ["Total de la selección", number(section.get("people")), number(section.get("units")),
                           money(section.get("fiscal"), millions=True), money(section.get("government"), millions=True)])
        tbl.append(total)
    frame = tbl.getparent().getparent().getparent()
    ext = frame.find("p:xfrm/a:ext", NS)
    if ext is not None:
        ext.set("cy", str(sum(int(row.get("h")) for row in tbl.findall("a:tr", NS))))


def _update_cache(cache, values, numeric=False):
    for node in list(cache):
        if node.tag != _q("c", "formatCode"):
            cache.remove(node)
    ET.SubElement(cache, _q("c", "ptCount"), val=str(len(values)))
    for i, value in enumerate(values):
        pt = ET.SubElement(cache, _q("c", "pt"), idx=str(i))
        ET.SubElement(pt, _q("c", "v")).text = str(float(value)) if numeric else str(value)


def _chart_and_workbook(chart_bytes, workbook_bytes, rows, label, color="512F8D"):
    # Native bar axes render in reverse category order; ascending input places
    # the largest reported count at the top without changing its value.
    values = sorted(rows, key=lambda x: x.get("people") or 0)
    categories = [x.get("chart_label") or SHORT.get(x.get("id"), x["label"]) for x in values]
    numbers = [float(x.get("people") or 0) for x in values]
    if not all(isfinite(x) and x >= 0 for x in numbers):
        raise ValueError("El gráfico contiene un conteo inválido.")
    chart = _xml(chart_bytes)
    chart.find("c:lang", NS).set("val", "es-EC")
    # Series colour follows the programme family (bonos: purple, services: fuchsia).
    for fill in chart.findall(".//c:ser/c:spPr/a:solidFill/a:srgbClr", NS):
        fill.set("val", color)
    chart.find(".//c:ser/c:tx/c:v", NS).text = label
    _update_cache(chart.find(".//c:cat/c:strRef/c:strCache", NS), categories)
    _update_cache(chart.find(".//c:val/c:numRef/c:numCache", NS), numbers, True)
    chart.find(".//c:cat/c:strRef/c:f", NS).text = f"'Chart Data'!$A$2:$A${len(values)+1}"
    chart.find(".//c:val/c:numRef/c:f", NS).text = f"'Chart Data'!$B$2:$B${len(values)+1}"
    # Localized labels are native chart text. Their numeric values remain in
    # both the chart cache and embedded workbook; each export refreshes both.
    labels = chart.find(".//c:ser/c:dLbls", NS)
    if labels is not None:
        prototype = deepcopy(labels.find("c:dLbl", NS))
        for item in list(labels):
            if item.tag == _q("c", "dLbl"):
                labels.remove(item)
        for index, value in enumerate(numbers):
            item = deepcopy(prototype)
            item.find("c:idx", NS).set("val", str(index))
            item.find("c:tx/c:rich/a:p/a:r/a:t", NS).text = number(value)
            labels.insert(index, item)
    if not any(numbers):
        scaling = chart.find(".//c:valAx/c:scaling", NS)
        ET.SubElement(scaling, _q("c", "max"), val="1")
    # Keep an embedded, editable workbook synchronized with every cache value.
    old_wb = ZipFile(BytesIO(workbook_bytes))
    sheet = _xml(old_wb.read("xl/worksheets/sheet1.xml"))
    sheet.find("s:dimension", NS).set("ref", f"A1:B{len(values)+1}")
    data = sheet.find("s:sheetData", NS)
    for row in list(data):
        data.remove(row)
    for i, pair in enumerate([("Categoría", label), *zip(categories, numbers)], 1):
        row = ET.SubElement(data, _q("s", "row"), r=str(i))
        for col, value in zip("AB", pair):
            cell = ET.SubElement(row, _q("s", "c"), r=f"{col}{i}")
            if isinstance(value, str):
                cell.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(cell, _q("s", "is")), _q("s", "t")).text = value
            else:
                ET.SubElement(cell, _q("s", "v")).text = str(value)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as wb:
        for name in old_wb.namelist():
            wb.writestr(name, _bytes(sheet) if name == "xl/worksheets/sheet1.xml" else old_wb.read(name))
    return _bytes(chart), output.getvalue()


def _chunks_balanced(rows, maximum=6):
    if not rows:
        return [[]]
    count = ceil(len(rows) / maximum)
    size = ceil(len(rows) / count)
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _short_chart_rows(rows, territory=False):
    result = []
    for item in rows:
        row = dict(item)
        if territory:
            row["chart_label"] = item["label"]
        elif item.get("id") == "PAM_SERV":
            row["chart_label"] = "Personas adultas mayores"
        elif len(item["label"]) > 34 and item.get("id") not in SHORT:
            row["chart_label"] = item["label"].replace("Personas con", "").replace("personas con", "").strip()
        result.append(row)
    return result


def _shape(slide, name):
    for shape in slide.findall(".//p:sp", NS):
        props = shape.find("p:nvSpPr/p:cNvPr", NS)
        if props is not None and props.get("name") == name:
            return shape
    return None


def _place(shape, x=None, y=None, cx=None, cy=None):
    xfrm = shape.find("p:spPr/a:xfrm", NS)
    off, ext = xfrm.find("a:off", NS), xfrm.find("a:ext", NS)
    for node, key, value in [(off, "x", x), (off, "y", y), (ext, "cx", cx), (ext, "cy", cy)]:
        if value is not None:
            node.set(key, str(int(value)))


def _set_text(slide, name, text):
    shape = _shape(slide, name)
    if shape is not None:
        _body_text(shape.find("p:txBody", NS), text)
    return shape


def _picture(slide, rid, x, y, cx, cy, shape_id, name, description):
    """Append a native picture shape that references an image relationship."""
    tree = slide.find(".//p:cSld/p:spTree", NS)
    pic = ET.SubElement(tree, _q("p", "pic"))
    nv = ET.SubElement(pic, _q("p", "nvPicPr"))
    ET.SubElement(nv, _q("p", "cNvPr"), id=str(shape_id), name=name, descr=description)
    locks = ET.SubElement(ET.SubElement(nv, _q("p", "cNvPicPr")), _q("a", "picLocks"))
    locks.set("noChangeAspect", "1")
    ET.SubElement(nv, _q("p", "nvPr"))
    fill = ET.SubElement(pic, _q("p", "blipFill"))
    blip = ET.SubElement(fill, _q("a", "blip"))
    blip.set(_q("r", "embed"), rid)
    ET.SubElement(ET.SubElement(fill, _q("a", "stretch")), _q("a", "fillRect"))
    sppr = ET.SubElement(pic, _q("p", "spPr"))
    xfrm = ET.SubElement(sppr, _q("a", "xfrm"))
    ET.SubElement(xfrm, _q("a", "off"), x=str(int(x)), y=str(int(y)))
    ET.SubElement(xfrm, _q("a", "ext"), cx=str(int(cx)), cy=str(int(cy)))
    ET.SubElement(ET.SubElement(sppr, _q("a", "prstGeom"), prst="rect"), _q("a", "avLst"))
    return pic


def _image_rel(rels, rid, target):
    ET.SubElement(rels, _q("rel", "Relationship"), Id=rid, Type=REL + "image", Target=target)


def generate_pptx(context: dict) -> bytes:
    """Return a polished editable deck for the exact dashboard selection.

    Tables paginate rather than shrink to unreadable text.  Territorial slides
    show the top eight territories when requested, explicitly labeled.  All
    amounts retain their fiscal/government bases and missing execution remains
    unavailable, never zero.
    """
    if not context.get("sections"):
        raise ValueError("La selección no contiene apartados para presentar.")
    if not TEMPLATE.is_file():
        raise FileNotFoundError("Falta templates/presentation.pptx en el paquete de la aplicación.")
    template = ZipFile(TEMPLATE)
    old = {name: template.read(name) for name in template.namelist()}
    exclude = re.compile(r"^(?:ppt/slides/(?:slide\d+\.xml|_rels/slide\d+\.xml\.rels|charts/)|ppt/notesSlides/|ppt/embeddings/)")
    output = {k: v for k, v in old.items() if not exclude.match(k)}
    output["ppt/media/shield-check.png"] = (ROOT / "assets/icons/shield-check.png").read_bytes()
    content_types = _xml(old["[Content_Types].xml"])
    for entry in list(content_types):
        if exclude.match(entry.get("PartName", "").lstrip("/")):
            content_types.remove(entry)
    rels = _xml(old["ppt/_rels/presentation.xml.rels"])
    for rel in list(rels):
        if rel.get("Type") == REL + "slide":
            rels.remove(rel)
    pres = _xml(old["ppt/presentation.xml"])
    slide_ids = pres.find("p:sldIdLst", NS)
    for entry in list(slide_ids):
        slide_ids.remove(entry)
    chart_count = 0
    pages = []
    common = {
        "TITLE": context["title"], "PERIOD": context["period_label"],
        "SCOPE": context["scope_label"], "SOURCE": "Fuente: " + context["source_label"],
        "FOOTER": "MTDH   " + context["period_label"] + "   " + context["scope_label"],
        "SPEAKER_NOTES": "Fuente: " + context["source_label"] + "\n" + "\n".join(context.get("notes", []))
                         + "\nÍconos Lucide, licencia ISC: https://lucide.dev/license\nSelección: " + context.get("selection_hash", ""),
    }
    pages.append((1, common, None, None, False))
    territory = context.get("territory", [])
    map_values = {t["code"]: t["people"] for t in territory}
    few = {t["code"] for t in territory if t["code"] != "90"}
    cover_map = map_png(map_values, mode="night", selected=few if len(few) <= 3 else set(), annotate=0, legend=False,
                        scale="quantile", width=5.6, height=4.8) if territory else None
    if cover_map:
        output["ppt/media/cover_map.png"] = cover_map
    if context.get("include_territory", True) and territory:
        output["ppt/media/territory_map.png"] = map_png(map_values, label="Cobertura reportada", annotate=6, width=6.6, height=5.6)
        places = [t for t in territory if t["code"] != "90"]
        total_people = sum(t["people"] or 0 for t in territory) or 1
        ranking = "\n".join(f"{i + 1}.  {t['label']}: {number(t['people'])} ({number((t['people'] or 0) / total_people * 100, 1)} %)"
                            for i, t in enumerate(places[:8]))
        top3 = places[:3]
        share3 = sum(t["people"] or 0 for t in top3) / total_people * 100
        names = ", ".join(t["label"] for t in top3[:-1]) + (" y " + top3[-1]["label"] if len(top3) > 1 else top3[0]["label"] if top3 else "")
        reading = (f"{names} concentran el {number(share3, 1)} % de la cobertura reportada de la selección." if len(top3) > 1
                   else f"La selección corresponde a {names}." if top3 else "")
        pages.append((4, {**common, "_MAP": True, "NOTE_TITLE_1": "Provincias con mayor cobertura", "NOTE_BODY_1": ranking,
                          "NOTE_TITLE_2": "Lectura territorial", "NOTE_BODY_2": reading,
                          "NOTE_TITLE_3": "", "NOTE_BODY_3": ""}, None, None, False))
    for section in context["sections"]:
        values = {
            **common, "SECTION_TITLE": section["title"], "PEOPLE": number(section.get("people")),
            "PEOPLE_LABEL": section["people_label"], "FISCAL": "USD " + money(section.get("fiscal"), millions=True),
            "FISCAL_LABEL": f"millones en el acumulado fiscal {context.get('year', '')}",
            "COUNT_NOTE": "Conteos reportados. No equivalen a personas únicas verificadas.",
            "CHART_SUBTITLE": "Distribución por programa" if section["id"] == "bonos_pensiones" else "Distribución por servicio",
        }
        if section.get("units") is None:
            values.update(EXTRA_VALUE="USD " + money(section.get("government"), millions=True),
                          EXTRA_LABEL="millones en el acumulado de gobierno")
        else:
            values.update(EXTRA_VALUE=number(section["units"]), EXTRA_LABEL="unidades reportadas")
        rows = section["rows"]
        positives = [r for r in rows if r.get("people")]
        pages.append((2, values, section, _short_chart_rows(positives or rows), False))
        chunks = _chunks_balanced(rows)
        for chunk_index, chunk in enumerate(chunks):
            title = "Detalle de bonos y pensiones" if section["id"] == "bonos_pensiones" else "Detalle de protección integral"
            if len(chunks) > 1:
                title += f"   {chunk_index+1} de {len(chunks)}"
            details = {**common, "DETAIL_TITLE": title,
                       "DETAIL_SUBTITLE": "Presupuesto ejecutado: " + ("N/D" if section.get("executed") is None else "USD " + money(section["executed"], millions=True) + " millones"),
                       "DETAIL_NOTE": "Fiscal y gobierno son acumulados superpuestos. No se suman entre sí. N/D: no disponible o no aplica."}
            pages.append((3, details, section, chunk, chunk_index == len(chunks)-1))
        if context.get("include_territory", True) and section.get("territories"):
            top = section["territories"][:8]
            territorial = {**values, "CHART_SUBTITLE": f"Las {len(top)} provincias con mayor cobertura",
                           "COUNT_NOTE": "El gráfico muestra las provincias seleccionadas con mayor conteo reportado."}
            pages.append((2, territorial, section, _short_chart_rows(top, territory=True), False))
    executed = context.get("executed_total")
    methods = {
        **common, "NOTE_TITLE_1": "Cobertura reportada",
        "NOTE_BODY_1": "Conteos agregados de beneficiarios y usuarios. La fuente no permite comprobar personas únicas ni eliminar coincidencias entre programas.",
        "NOTE_TITLE_2": "Montos acumulados",
        "NOTE_BODY_2": f"El fiscal {context.get('year', '')} corresponde al presupuesto del año en la fuente. El acumulado de gobierno lo incluye y añade períodos anteriores. No se suman entre sí.",
        "NOTE_TITLE_3": "Presupuesto ejecutado y unidades",
        "NOTE_BODY_3": ("Ejecución presupuestaria: N/D. La fuente no certifica el gasto ejecutado. " if executed is None else "Ejecución certificada de la selección: USD " + money(executed, millions=True) + " millones. ")
                       + "Las unidades corresponden a protección integral. N/D distingue un dato ausente de un cero reportado.",
    }
    pages.append((4, methods, None, None, False))
    for index, (template_index, values, section, rows, last) in enumerate(pages, 1):
        slide = _xml(old[f"ppt/slides/slide{template_index}.xml"])
        _fill(slide, {**values, "PAGE": f"{index:02d}"})
        if template_index == 1 and len(context["title"]) > 48:
            _font_for_shape(slide, "cover-title", 48 if len(context["title"]) < 80 else 42)
        extra_rels = []
        if template_index == 1 and cover_map:
            for name in ("cover-title", "cover-period", "cover-scope", "cover-source"):
                shape = _shape(slide, name)
                if shape is not None:
                    _place(shape, cx=6_150_000)
            _picture(slide, "rIdCoverMap", 6_980_000, 1_380_000, 4_620_000, 3_960_000, 900, "Mapa del Ecuador",
                     "Mapa del Ecuador con la cobertura reportada por provincia")
            extra_rels.append(("rIdCoverMap", "/ppt/media/cover_map.png"))
        if template_index == 4 and values.get("_MAP"):
            _set_text(slide, "title", "Cobertura en el territorio")
            for name, y, cy in [("method-head-1", 1_640_000, 380_000), ("method-body-1", 2_040_000, 2_700_000),
                                ("method-head-2", 4_880_000, 380_000), ("method-body-2", 5_260_000, 900_000),
                                ("method-head-3", 6_200_000, 10_000), ("method-body-3", 6_210_000, 10_000)]:
                shape = _shape(slide, name)
                if shape is not None:
                    _place(shape, x=6_560_000, y=y, cx=4_950_000, cy=cy)
            _font_for_shape(slide, "method-body-1", 20)
            _font_for_shape(slide, "method-body-2", 20)
            _picture(slide, "rIdTerritoryMap", 560_000, 1_560_000, 5_620_000, 4_770_000, 901, "Mapa territorial",
                     "Mapa coroplético de la cobertura reportada por provincia")
            extra_rels.append(("rIdTerritoryMap", "/ppt/media/territory_map.png"))
        if template_index == 3:
            _populate_table(slide, rows, section, context, last)
        slide_rels = _xml(old[f"ppt/slides/_rels/slide{template_index}.xml.rels"])
        for rid, target in extra_rels:
            _image_rel(slide_rels, rid, target)
        for rel in slide_rels:
            kind = rel.get("Type", "")
            if kind == REL + "notesSlide":
                rel.set("Target", f"/ppt/notesSlides/notesSlide{index}.xml")
            elif kind == REL + "image" and template_index == 2 and section["id"] == "proteccion_integral":
                rel.set("Target", "/ppt/media/shield-check.png")
            elif kind == REL + "chart":
                chart_count += 1
                tone = "C33F8D" if section["id"] == "proteccion_integral" else "512F8D"
                chart, wb = _chart_and_workbook(old["ppt/slides/charts/chart1.xml"], old["ppt/embeddings/chart-data-snapshot-001.xlsx"],
                                                rows, section["people_label"], tone)
                chart_path = f"ppt/slides/charts/chart{chart_count}.xml"
                workbook_path = f"ppt/embeddings/chart-data-{chart_count:03d}.xlsx"
                output[chart_path] = chart
                output[workbook_path] = wb
                chart_rels = _xml(old["ppt/slides/charts/_rels/chart1.xml.rels"])
                chart_rels[0].set("Target", "../../embeddings/" + Path(workbook_path).name)
                output[f"ppt/slides/charts/_rels/chart{chart_count}.xml.rels"] = _bytes(chart_rels)
                rel.set("Target", "/" + chart_path)
                ET.SubElement(content_types, _q("ct", "Override"), PartName="/"+chart_path,
                              ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml")
        output[f"ppt/slides/slide{index}.xml"] = _bytes(slide)
        output[f"ppt/slides/_rels/slide{index}.xml.rels"] = _bytes(slide_rels)
        notes = _xml(old[f"ppt/notesSlides/notesSlide{template_index}.xml"])
        _fill(notes, values)
        output[f"ppt/notesSlides/notesSlide{index}.xml"] = _bytes(notes)
        notes_rels = _xml(old[f"ppt/notesSlides/_rels/notesSlide{template_index}.xml.rels"])
        for rel in notes_rels:
            if rel.get("Type") == REL + "slide":
                rel.set("Target", f"/ppt/slides/slide{index}.xml")
        output[f"ppt/notesSlides/_rels/notesSlide{index}.xml.rels"] = _bytes(notes_rels)
        for part, type_ in [(f"ppt/slides/slide{index}.xml", "slide"), (f"ppt/notesSlides/notesSlide{index}.xml", "notesSlide")]:
            ET.SubElement(content_types, _q("ct", "Override"), PartName="/"+part,
                          ContentType=f"application/vnd.openxmlformats-officedocument.presentationml.{type_}+xml")
        rid = f"rIdReport{index}"
        ET.SubElement(rels, _q("rel", "Relationship"), Id=rid, Type=REL+"slide", Target=f"/ppt/slides/slide{index}.xml")
        ET.SubElement(slide_ids, _q("p", "sldId"), id=str(255+index), attrib={_q("r", "id"):rid})
    output["ppt/presentation.xml"] = _bytes(pres)
    output["ppt/_rels/presentation.xml.rels"] = _bytes(rels)
    output["[Content_Types].xml"] = _bytes(content_types)
    # The template's metadata must not retain a stale page count or author.
    app = _xml(output["docProps/app.xml"])
    for el in app.iter():
        if ET.QName(el).localname == "Slides":
            el.text = str(len(pages))
    output["docProps/app.xml"] = _bytes(app)
    core = _xml(output["docProps/core.xml"])
    for el in core.iter():
        name = ET.QName(el).localname
        if name == "title":
            el.text = context["title"]
        elif name in ("creator", "lastModifiedBy"):
            el.text = "Ministerio de Trabajo y Desarrollo Humano"
    output["docProps/core.xml"] = _bytes(core)
    unresolved = [name for name, value in output.items() if name.endswith(".xml") and b"{{" in value]
    if unresolved:
        raise ValueError("La plantilla contiene campos sin resolver: " + ", ".join(unresolved))
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zipped:
        for name, value in output.items():
            zipped.writestr(name, value)
    return buf.getvalue()
