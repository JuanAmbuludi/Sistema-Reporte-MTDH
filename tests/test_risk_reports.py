"""The public risk products contain the response only, at the dashboard's grain."""
from io import BytesIO
import openpyxl
import pymupdf
from pptx import Presentation
from src import riesgos
from src.reports import generate_pdf, generate_pptx, generate_xlsx
from src.views.riesgos import RiskView


def view(provinces=(), programs=(), threat=None, levels=riesgos.LEVELS):
    v = RiskView()
    v.select(v.catalog()[-1], provinces, programs, threat, levels)
    assert v.prepare()
    return v


def test_counts_distinguish_alerts_from_units_and_services():
    v = view(); r = v.response
    assert len(r.alerts) == r.alerts.codigo.nunique() == 10
    assert r.units == 10
    assert r.alerts.codigo_ua.eq("").sum() == 0
    assert r.alerts.groupby("servicio").size().to_dict() == {"Desarrollo Infantil": 8, "Creciendo con Nuestros Hijos (CNH)": 2}
    cards = v.kpi_cards()
    assert [c["value"] for c in cards] == [10, 802, 113, 33200.8, 19]
    assert "Núcleos" in cards[2]["label"]
    assert v.kpi_groups() == []
    # The exposure calculation is retained internally, outside the public context.
    assert riesgos.count_records(v.multihazard) == 6220
    assert not {"units", "exposed", "threats", "multihazard"}.intersection(v.report_context("Riesgos"))


def test_response_exports_are_complete_and_exclude_hidden_exposure():
    v = view(); ctx = v.report_context("Riesgos")
    pdf = pymupdf.open(stream=generate_pdf(ctx), filetype="pdf")
    assert len(pdf) == ctx["pdf_pages"] == 3
    pdf_text = " ".join(page.get_text() for page in pdf)
    slides = Presentation(BytesIO(generate_pptx(ctx))).slides
    ppt_text = " ".join(shape.text if shape.has_text_frame else " ".join(cell.text for row in shape.table.rows for cell in row.cells)
                        if shape.has_table else "" for slide in slides for shape in slide.shapes)
    wb = openpyxl.load_workbook(BytesIO(generate_xlsx(ctx)), data_only=True)
    assert wb.sheetnames == v.sheets()
    xlsx_text = " ".join(str(c.value) for sheet in wb for row in sheet for c in row if c.value is not None)
    for text in [pdf_text, ppt_text, xlsx_text]:
        for hidden in ["UA expuestas", "Multiamenaza", "Susceptibilidad muy alta", "Exposición de las unidades", "6 pendientes · 7 en seguimiento", "Gestionado no acredita cobro", "El código por sí solo no confirma una afectación"]:
            assert hidden not in text
        for a in ctx["response"]["alerts"]:
            assert a["code"] in text
            # All names and impacts survive wrapping, including the longest entries.
            compact = " ".join(text.split())
            assert " ".join(a["unit"].split()) in compact
            assert " ".join(a["impact"].split()) in compact
        assert "Núcleos" in text and "provincias priorizadas" in text
    assert "33.200,80" in pdf_text and "33.200,80" in ppt_text
    normalized_pdf = " ".join(pdf_text.split())
    for note in ctx["response"]["notes"].values():
        assert " ".join(note.split()) in normalized_pdf
    for kit in ctx["response"]["kits"]:
        assert kit["date"] in normalized_pdf and kit["province"] in normalized_pdf and kit["canton"] in normalized_pdf
    for value in ["145.523", "44.098", "13.405.351,02", "802", "113"]:
        assert value in normalized_pdf
    assert 33200.8 in [c.value for row in wb["Resumen"] for c in row]
    assert len(slides) == 9


def test_filters_apply_consistently_to_response_and_do_not_depend_on_exposure():
    ctx = view(("09",), ("DII",), "susc_inundacion", ("Alta",)).report_context("Riesgos")
    assert ctx["response"]["alert_count"] == 6
    assert ctx["response"]["kits_total"] == 400
    assert ctx["response"]["managed_people"] == 67
    assert sum(a["value"] for a in ctx["response"]["by_province"]) == 6
    assert sum(a["value"] for a in ctx["response"]["by_service"]) == 6
    empty = view((), ("PAM_SERV",), levels=()).report_context("Riesgos")
    assert empty["response"]["alert_count"] == 0 and empty["response"]["kits_total"] == 802
    assert generate_pdf(empty)


def test_timeline_preserves_the_full_reporting_window():
    r = view().report_context("Riesgos")["response"]
    assert r["daily"][0] == {"date": "14/09/2026", "short": "14/09", "daily": 0, "total": 0}
    assert sum(a["daily"] for a in r["daily"]) == r["daily"][-1]["total"] == r["alert_count"]


def test_continuity_keeps_suspension_and_virtual_attention_separate():
    r = view().response
    assert r.closed_units == 19
    assert r.continuity_summary()["by_province"] == [{"name": "El Oro", "value": 12}, {"name": "Santa Elena", "value": 7}]
    assert r.continuity.groupby("estado").unidades.sum().to_dict() == {"Suspendida": 19, "Suspendida presencial": 63, "Atención virtual": 11, "Afectada; modalidad por confirmar": 17}
    assert view(("07",)).response.closed_units == 12
    assert view(("09",)).response.closed_units == 0
    assert view(programs=("PAM_SERV",)).response.closed_units == 0
