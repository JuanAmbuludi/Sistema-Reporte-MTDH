"""Exports: one-page summary, three slides and the data workbook, all built from the on-screen selection."""
from io import BytesIO
import zipfile

import pymupdf
import pytest
from openpyxl import load_workbook
from pptx import Presentation

from src.data import filter_data, load_periods, load_territory
from src.gestion_laboral import load_labour, summary
from src.institutional import catalog as budget_catalog, load_budget
from src.reports import build_report_context, generate_pdf, generate_pptx, generate_xlsx
from src.reports.national import budget_context, labour_context

BANNED = ["N/D", "No aplica", "no disponible", "No disponible", "Excel", "fuente_", "no certifica",
          "no documentado", "registros", "Selección ", "deduplicación", "no sumar", "sin identificadores", "fase presupuestaria"]


@pytest.fixture(scope="module")
def periods():
    data, catalog = load_periods()
    return data, catalog


@pytest.fixture(scope="module")
def parishes():
    return load_territory()


@pytest.fixture(scope="module")
def budget():
    frame, _manifest = load_budget()
    period = budget_catalog(frame)[0]
    scoped = frame.loc[frame.periodo_id.eq(period["id"])]
    return budget_context(scoped, national=scoped, scope=scoped, title="Presupuesto institucional", period=period,
                          territory_label="Total institucional", programs_label="Todos los programas")


@pytest.fixture(scope="module")
def labour():
    period = {"id": "2026", "year": 2026, "month": None, "label": "Año 2026"}
    return labour_context(summary(load_labour()), title="Gestión laboral", period=period)


def _period(data, period_id):
    return data.loc[data.periodo_id.eq(period_id)]


def _context(data, parishes, section, period_id="2026-09", provinces=None):
    rows = filter_data(_period(data, period_id), secciones=[section])
    parish = parishes.loc[parishes.periodo_id.eq(period_id) & parishes.seccion.eq(section)]
    chosen = filter_data(parish, provincias=provinces) if len(parish) else parish
    return build_report_context(filter_data(rows, provincias=provinces), national=rows, selected_codes=set(provinces or []),
                                parishes=chosen, parishes_national=parish)


def _strings(context: dict) -> list[str]:
    texts = [context["title"], context["period_label"], context["territory_label"], context["programs_label"]]
    texts += [i["text"] for i in context["insights"]]
    texts += [k["label"] for k in context["kpis"]] + [str(k.get("note", "")) for k in context["kpis"]]
    texts += [v for v in context.get("labels", {}).values() if isinstance(v, str)]
    return texts


def _pdf_text(content: bytes) -> str:
    document = pymupdf.open(stream=content, filetype="pdf")
    assert document.page_count == 1
    return document[0].get_text()


def _deck_texts(content: bytes):
    deck = Presentation(BytesIO(content))
    texts = ["".join(run.text for p in shape.text_frame.paragraphs for run in p.runs)
             for slide in deck.slides for shape in slide.shapes if shape.has_text_frame]
    return deck, texts


def test_context_follows_module_and_period(periods, parishes):
    data, _ = periods
    current = _context(data, parishes, "bonos_pensiones")
    assert current["module_label"] == "Transferencias monetarias" and current["period_label"] == "Septiembre 2026"
    assert current["totals"]["people"] == 1578019
    assert [k["label"] for k in current["kpis"]] == ["Beneficiarios", "Ejecución presupuestaria", "Presupuesto ejecutado 2026",
                                                     "Presupuesto acumulado 2023–2026"]
    assert round(current["totals"]["execution"], 2) == 71.02
    assert current["map_layer"] == "parroquia" and current["parish"]["count"] > 1000
    annual = build_report_context(filter_data(_period(data, "2025"), secciones=["proteccion_integral"]))
    assert annual["period_label"] == "Año 2025" and annual["labels"]["fiscal"] == "Presupuesto 2025"
    assert annual["totals"]["people"] == 443903 and annual["totals"]["units"] == 10906
    assert annual["map_layer"] == "provincia" and annual["parish"] is None


def test_transfers_and_services_are_never_mixed(periods):
    data, _ = periods
    with pytest.raises(ValueError, match="ámbitos distintos"):
        build_report_context(_period(data, "2026-09"))


def test_selected_province_keeps_its_national_place_and_its_parishes(periods, parishes):
    data, _ = periods
    context = _context(data, parishes, "proteccion_integral", provinces=["09"])
    assert context["territory_label"] == "Guayas"
    assert context["totals"]["people"] == 88004
    assert all(k["share"] is not None for k in context["kpis"])
    assert "primer lugar" in context["insights"][1]["text"]
    guayas = next(p for p in context["provinces"] if p["code"] == "09")
    assert guayas["selected"] and guayas["position"] == 1
    assert context["map_focus"] == ["09"]
    assert {r["province_code"] for r in context["parish"]["rows"]} == {"09"}
    assert sum(r["people"] or 0 for r in context["parish"]["rows"]) == 88004
    assert context["parish"]["top"][0]["parish"] == "Tarqui"


def test_documents_use_formal_wording_without_technical_notes(periods, parishes, budget, labour):
    data, catalog = periods
    contexts = [budget, labour]
    for period in catalog:
        for section in ["bonos_pensiones", "proteccion_integral"]:
            contexts.append(_context(data, parishes, section, period["id"]))
    for context in contexts:
        for text in _strings(context):
            for banned in BANNED:
                assert banned not in text, f"{banned!r} en {text!r}"


def test_empty_and_multi_period_selections_are_rejected(periods):
    data, _ = periods
    with pytest.raises(ValueError, match="No hay información"):
        build_report_context(data.iloc[0:0])
    both = filter_data(data.loc[data.periodo_id.isin(["2026-09", "2025"])], secciones=["bonos_pensiones"])
    with pytest.raises(ValueError, match="único periodo"):
        build_report_context(both)


def test_executive_summary_is_one_page(periods, parishes):
    data, _ = periods
    text = _pdf_text(generate_pdf(_context(data, parishes, "bonos_pensiones")))
    for expected in ["Transferencias monetarias", "Beneficiarios por programa", "Principales provincias", "Aspectos destacados",
                     "1.578.019", "71,0 %", "Beneficiarios por parroquia"]:
        assert expected in text
    for banned in BANNED:
        assert banned not in text
    zoom = _pdf_text(generate_pdf(_context(data, parishes, "proteccion_integral", provinces=["09"])))
    assert "Principales parroquias" in zoom and "Tarqui" in zoom


def test_presentation_has_three_slides_with_icons_and_a_native_chart(periods, parishes):
    data, _ = periods
    deck, texts = _deck_texts(generate_pptx(_context(data, parishes, "proteccion_integral", provinces=["17"])))
    assert len(deck.slides) == 3
    assert "Cifras clave" in texts and "Resultados por territorio" in texts and "Resultados por servicio" in texts
    pictures = [shape for slide in deck.slides for shape in slide.shapes if shape.shape_type == 13]
    assert len(pictures) >= 10, "Iconos, logo y mapas"
    charts = [shape for shape in deck.slides[2].shapes if shape.has_chart]
    assert len(charts) == 1 and len(charts[0].chart.plots[0].categories) == 4
    for text in texts:
        for banned in BANNED:
            assert banned not in text


def test_data_workbook_is_institutional_numeric_and_formula_driven(periods, parishes):
    data, _ = periods
    content = generate_xlsx(_context(data, parishes, "bonos_pensiones", provinces=["09"]))
    book = load_workbook(BytesIO(content))
    assert book.sheetnames == ["Resumen", "Programas", "Provincias", "Parroquias", "Detalle", "Ficha técnica"]
    values = [cell.value for sheet in book.worksheets for row in sheet.iter_rows() for cell in row if cell.value is not None]
    strings = [v for v in values if isinstance(v, str)]
    assert any(v.startswith("=SUBTOTAL(109,") for v in strings)
    assert 312265 in values
    for banned in BANNED:
        assert not any(banned in v for v in strings if not v.startswith("=")), banned
    detail = book["Detalle"]
    assert detail.auto_filter.ref and detail.freeze_panes
    provinces = book["Provincias"]
    guayas = [row for row in provinces.iter_rows(values_only=True) if "Guayas" in row]
    assert guayas and 1 in guayas[0]
    parish_rows = [row for row in book["Parroquias"].iter_rows(values_only=True) if row[1] == "Guayas"]
    assert len(parish_rows) > 40 and book["Parroquias"].auto_filter.ref
    with zipfile.ZipFile(BytesIO(content)) as archive:
        assert 'name="MTDH Institucional"' in archive.read("xl/theme/theme1.xml").decode()


def test_services_workbook_names_its_sheet_after_services(periods):
    data, _ = periods
    context = build_report_context(filter_data(_period(data, "2024"), secciones=["proteccion_integral"]))
    book = load_workbook(BytesIO(generate_xlsx(context)))
    assert book.sheetnames[1] == "Servicios" and "Parroquias" not in book.sheetnames
    headers = [cell.value for row in book["Servicios"].iter_rows(max_row=12) for cell in row if isinstance(cell.value, str)]
    assert "Presupuesto 2024" in headers and "Unidades de atención" in headers


def test_reports_accept_rows_loaded_without_period_catalog():
    from src.data import load_data
    frame = filter_data(load_data(), secciones=["bonos_pensiones"], programas=["BDH"])
    context = build_report_context(frame)
    assert context["period_label"] == "Septiembre 2026"
    assert context["insights"][0]["text"].startswith("Bono de Desarrollo Humano registra")
    assert sum(context["map_values"].values()) == 619073


def test_budget_exports_read_execution_by_program_and_zone(budget):
    assert [k["label"] for k in budget["kpis"]] == ["Presupuesto codificado", "Presupuesto devengado", "Ejecución presupuestaria",
                                                    "Saldo por devengar"]
    assert round(budget["stats"]["ejecucion"], 2) == 45.77 and round(budget["stats"]["devengado"], 2) == 978122861.16
    assert budget["zones"][0]["name"] == "Planta central" and set(budget["map_values"]) <= {f"Z{i}" for i in range(1, 10)}
    text = _pdf_text(generate_pdf(budget))
    for expected in ["Presupuesto institucional", "45,8 %", "Ejecución por zona", "Ejecución por programa presupuestario"]:
        assert expected in text
    deck, texts = _deck_texts(generate_pptx(budget))
    assert len(deck.slides) == 3 and "Ejecución por zona" in texts and "Ejecución por programa" in texts
    book = load_workbook(BytesIO(generate_xlsx(budget)))
    assert book.sheetnames == ["Resumen", "Programas", "Zonas", "Grupos de gasto", "Detalle", "Ficha técnica"]
    names = [c.value for c in book["Programas"]["C"] if isinstance(c.value, str)]
    assert "Servicios de atención gerontológica" in names
    assert not any("PROTECCION" in (c.value or "") for row in book["Detalle"].iter_rows() for c in row if isinstance(c.value, str))


def test_labour_exports_keep_each_figure_with_its_reference(labour):
    assert labour["info"]["stock"] == 2789419 and labour["info"]["cohorts"] == 507451
    assert labour["kpis"][3]["lower_bound"]
    text = _pdf_text(generate_pdf(labour))
    for expected in ["Gestión laboral", "2.789.419", "507.451", "Más de USD 229 M", "Fuentes de información"]:
        assert expected in text
    deck, texts = _deck_texts(generate_pptx(labour))
    assert len(deck.slides) == 3 and "Contratación laboral" in texts and "Compensaciones jubilares" in texts
    charts = [shape for shape in deck.slides[1].shapes if shape.has_chart]
    assert len(charts) == 1 and len(charts[0].chart.plots[0].categories) == 9
    book = load_workbook(BytesIO(generate_xlsx(labour)))
    assert book.sheetnames == ["Resumen", "Contratos por mes", "Ficha técnica"]
    links = [c.hyperlink.target for row in book["Ficha técnica"].iter_rows() for c in row if c.hyperlink]
    assert any("trabajo.gob.ec" in (link or "") for link in links)
