"""Report scope and semantic checks, including the no-deduplication boundary."""
from io import BytesIO
from pathlib import Path
import zipfile

import pandas as pd
import pytest
from lxml import etree

from src.data import load_data, load_manifest, filter_data
from src.reports import build_report_context, generate_pdf, generate_docx, generate_pptx


def test_reports_use_exact_filtered_dashboard_selection():
    frame = load_data()
    chosen = filter_data(frame, provincias=["Guayas"], programas=["BDH"])
    assert len(chosen) > 0
    context = build_report_context(chosen, load_manifest())
    assert context["provinces"] == ["Guayas"]
    assert len(context["sections"]) == 1
    section = context["sections"][0]
    assert section["id"] == "bonos_pensiones"
    assert len(section["rows"]) == 1
    assert section["people"] == chosen.usuarios.sum()
    assert section["fiscal"] == pytest.approx(chosen.monto_fiscal.sum())
    assert section["government"] == pytest.approx(chosen.monto_gobierno.sum())
    assert section["units"] is None
    assert context["executed_total"] is None
    assert "únicas" in " ".join(context["notes"])


def test_report_preserves_prior_only_pension_balances():
    context = build_report_context(load_data(), load_manifest())
    bonuses = next(s for s in context["sections"] if s["id"] == "bonos_pensiones")
    assert len(bonuses["rows"]) == 8
    prior = [r for r in bonuses["rows"] if r["id"] in {"PAM", "PCD"}]
    assert len(prior) == 2
    assert all(r["people"] == 0 and r["fiscal"] == 0 and r["government"] > 0 for r in prior)
    assert context["fiscal_total"] == pytest.approx(1_180_002_196.4343)
    assert context["government_total"] == pytest.approx(4_512_402_557.1319)


def test_empty_and_multi_period_reports_are_rejected():
    frame = load_data()
    with pytest.raises(ValueError, match="No hay datos"):
        build_report_context(frame.iloc[:0])
    mixed = frame.iloc[:2].copy()
    mixed.loc[mixed.index[1], "periodo"] = pd.Timestamp("2026-08-01")
    with pytest.raises(ValueError, match="único corte"):
        build_report_context(mixed)


def test_partial_execution_is_not_presented_as_complete():
    frame = load_data().iloc[:2].copy()
    frame["presupuesto_ejecutado"] = [1234.0, None]
    context = build_report_context(frame)
    assert context["executed_total"] is None
    frame["presupuesto_ejecutado"] = [1234.0, 100.0]
    assert build_report_context(frame)["executed_total"] == 1334


def test_exported_office_files_are_complete_and_scoped():
    frame = filter_data(load_data(), provincias=["Guayas"], programas=["BDH"])
    context = build_report_context(frame, load_manifest(), {"include_territory": False})
    docx = generate_docx(context)
    with zipfile.ZipFile(BytesIO(docx)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        text = " ".join(root.itertext())
        assert "Guayas" in text
        assert "Bono de Desarrollo Humano" in text
        assert "Pensión Mis Mejores Años" not in text
        assert "N/D" in text
    pptx = generate_pptx(context)
    with zipfile.ZipFile(BytesIO(pptx)) as archive:
        slides = [p for p in archive.namelist() if p.startswith("ppt/slides/slide") and p.endswith(".xml")]
        assert len(slides) >= 3
        text = " ".join(archive.read(p).decode() for p in slides)
        assert "Guayas" in text
        assert "Pensión Mis Mejores Años" not in text
        assert "{{" not in text
        assert "N/D" in text


def test_pdf_is_real_pdf_and_does_not_require_external_renderer():
    frame = filter_data(load_data(), provincias=["Guayas"], programas=["DII"])
    context = build_report_context(frame, load_manifest())
    content = generate_pdf(context)
    assert content.startswith(b"%PDF-")
    assert len(content) > 30_000
