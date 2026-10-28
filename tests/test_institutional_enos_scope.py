"""Institutional ENOS reports respect their cover period and label accumulated balances."""
from types import SimpleNamespace

import pandas as pd
import pymupdf
import pytest

from src.reports.enos_scope import bonus_scope, response_view


@pytest.fixture(scope="module")
def bases():
    from src import contingencias, finanzas, mensual, presupuesto_social
    from src.data import load_periods, load_territory
    from src.gestion_laboral import load_labour

    data, catalog = load_periods()
    budget, manifest = finanzas.load_fiscal()
    groups, programs = presupuesto_social.load_social_budget()
    return {"data": data, "catalog": catalog, "territory": load_territory(),
            "budget": budget, "budget_manifest": manifest, "labour": load_labour(),
            "program_budget": mensual.program_budget(), "contingencies": contingencias.monthly(),
            "contingency_places": contingencias.territorial(), "contingency_catalog": contingencias.catalog(),
            "social_groups": groups, "social_programs": programs, "government_budget": finanzas.load_government()}


@pytest.mark.parametrize("start,end,kits,brigades", [
    ("2026-01", "2026-09", 4291, 70),
    ("2023-11", "2026-09", 4291, 70),
    ("2026-08", "2026-08", 403, 0),
    ("2026-09", "2026-09", 3888, 2),
])
def test_month_scopes_use_reconciled_history_and_inclusive_calendar_bounds(start, end, kits, brigades):
    view = response_view(start, end)
    assert view is not None and view.query_mode == "periodo"
    response = view.response
    assert response.start == pd.Period(start, freq="M").start_time.normalize()
    assert response.end == pd.Period(end, freq="M").end_time.normalize()
    assert response.kits_total == kits
    assert len(response.brigadas) == brigades
    assert response.kits.id_kobo.nunique() == len(response.kits)
    assert pd.to_datetime(response.kits.fecha).between(response.start, response.end).all()
    assert response.alerts.empty
    assert not response.available["continuidad"]
    assert [card["value"] for card in view.kpi_cards()][2:5] == [1171, 354987.39, None]
    assert bonus_scope(response) == "Acumulado confirmado al 27/10/2026 · referencia fuera del período"


def test_latest_section_overview_uses_full_history_instead_of_publication_window():
    view = response_view()
    assert view is not None
    assert (view.since, view.until) == (pd.Timestamp("2026-02-27"), pd.Timestamp("2026-10-27"))
    assert [card["value"] for card in view.kpi_cards()] == [44, 14581, 1171, 354987.39, 124, 71]
    assert view.response.kits.id_kobo.nunique() == len(view.response.kits) == 117
    assert bonus_scope(view.response) == "Acumulado confirmado al 27/10/2026"


@pytest.mark.parametrize("start,end", [("2026-09", None), (None, "2026-09"), ("2026-10", "2026-09")])
def test_incomplete_or_reversed_month_scopes_do_not_silently_change_the_report(start, end):
    with pytest.raises(ValueError):
        response_view(start, end)


@pytest.mark.parametrize("cut,outside", [("2026-09-01T00:00:00-05:00", False),
                                        ("2026-09-30T19:00:00-05:00", False),
                                        ("2026-08-31", True), ("2026-10-01", True)])
def test_bonus_scope_compares_inclusive_calendar_days(cut, outside):
    response = SimpleNamespace(cuts={"bonos": cut}, start=pd.Timestamp("2026-09-01"), end=pd.Timestamp("2026-09-30"))
    assert ("referencia fuera del período" in bonus_scope(response)) is outside


@pytest.mark.parametrize("mode,start", [("anual", "2026-01"), ("gobierno", "2023-11")])
def test_legacy_period_data_uses_cover_dates_and_preserves_missing_continuity(bases, mode, start):
    from src.reports import periodo

    figures = periodo.gather(bases, mode)
    extra = periodo.extras(bases, figures)
    response = extra["enos"]
    assert figures["start"] == start and figures["end"] == "2026-09"
    assert response["kits"] == 4291 and response["alerts"] == 0
    assert response["closed"] is None and response["closed_rank"] == []
    assert response["closed_note"] == "Sin observación disponible hasta el 30/09/2026"
    assert response["families"] == 1171 and response["amount"] == 354987.39
    assert response["period"] == f"Del 01/{start[5:]}/{start[:4]} al 30/09/2026"
    assert response["bonus_scope"] == "Acumulado confirmado al 27/10/2026 · referencia fuera del período"
    assert sum(response["kits_map"].values()) == 4291
    assert next(row for row in figures["coverage"] if row[0] == "Plan ENOS")[1:3] == ("27/02/2026", "30/09/2026")
    assert ("Plan ENOS (registros disponibles)", "2026-02", "2026-09") in extra["timeline"]
    assert "0 unidades de atención con atención suspendida" not in str(response["findings"])


def test_legacy_pdf_labels_bonus_reference_and_does_not_publish_future_flows(bases):
    from src.reports import boletin, periodo

    context = periodo._build_plain(bases, "anual")
    context["extras"] = periodo.extras(bases, context["figures"])
    with pymupdf.open(stream=boletin.generate(context), filetype="pdf") as document:
        assert len(document) == 5
        enos_page = document[2]
        text = enos_page.get_text()
        for expected in ("Del 01/01/2026 al 30/09/2026", "4.291", "1.171", "354.987,39",
                         "Acumulado confirmado al 27/10/2026", "referencia fuera del período",
                         "Sin observación disponible"):
            assert expected in text
        for invalid in ("11.207", "14.581", "seguimiento desde el 28 de septiembre", "bono pagado"):
            assert invalid not in text
        for block in enos_page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    assert 0 <= x0 <= x1 <= enos_page.rect.width + 1
                    assert 0 <= y0 <= y1 <= enos_page.rect.height + 1
