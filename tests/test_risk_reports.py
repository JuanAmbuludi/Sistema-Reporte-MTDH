"""The three risk products use the same filtered snapshot and preserve unit identities."""
from io import BytesIO
from zipfile import ZipFile

import openpyxl
import pytest
import pymupdf
from pptx import Presentation

from src import riesgos
from src.reports import generate_pdf, generate_pptx, generate_xlsx
from src.views.riesgos import METHODOLOGY, RiskView


def view(provinces=(), programs=(), threat=None, levels=riesgos.LEVELS):
    v = RiskView()
    v.period = next(p for p in v.catalog() if p["id"] == "2026-09")
    v.provinces, v.programs, v.threat, v.levels = provinces, programs, threat, levels
    v.prepare()
    return v


def test_filtered_risk_exports_preserve_counts_scope_methodology_and_codes():
    v = view(("09",), ("DII",), "susc_inundacion", ("Alta",))
    ctx = v.report_context("Riesgos")
    assert len(ctx["units"]) == 287 == ctx["kpis"][0]["value"]
    assert ctx["threats"] == [{"name": "Inundaciones", "media": 0, "alta": 287, "muy_alta": 0, "units": 287}]
    assert ctx["territory_label"] == "Guayas"
    pdf = pymupdf.open(stream=generate_pdf(ctx), filetype="pdf")
    assert len(pdf) == 2
    text = " ".join(" ".join(p.get_text().split()) for p in pdf)
    assert METHODOLOGY in text and "Inundaciones" in text and "287" in text
    pptx = generate_pptx(ctx)
    slides = Presentation(BytesIO(pptx)).slides
    assert len(slides) == 4
    assert METHODOLOGY in " ".join(s.text for s in slides[3].shapes if s.has_text_frame)
    assert len([n for n in ZipFile(BytesIO(pptx)).namelist() if n.startswith("ppt/charts/chart") and n.endswith(".xml")]) == 2
    xlsx = generate_xlsx(ctx)
    wb = openpyxl.load_workbook(BytesIO(xlsx), data_only=True)
    assert wb.sheetnames == v.sheets()
    sheet = wb["Unidades"]
    header = next(r for r in sheet if r[1].value == "Código UA")
    rows = list(sheet.iter_rows(min_row=header[0].row + 1, max_col=9))
    assert len(rows) == 287
    assert {r[1].value for r in rows} == {u["codigo_ua"] for u in ctx["units"]}
    assert all(r[1].data_type == "s" and r[2].value and r[4].value == "Guayas" and r[5].value == "Alta" for r in rows)
    assert sheet.auto_filter.ref and sheet.freeze_panes
    assert METHODOLOGY in [c.value for row in wb["Ficha técnica"] for c in row]


def test_risk_report_scope_invalidates_download_and_rejects_empty_or_incomplete_detail():
    v = view()
    original = v.digest()
    assert len(v.report_context("Riesgos")["units"]) == 9460
    v.levels = ("Alta",)
    v.prepare()
    assert v.digest() != original
    v.detail_selected = v.detail_selected.iloc[1:]
    with pytest.raises(ValueError, match="no coincide"):
        v.report_context("Riesgos")
    with pytest.raises(ValueError, match="No hay unidades"):
        view(("99",)).report_context("Riesgos")
