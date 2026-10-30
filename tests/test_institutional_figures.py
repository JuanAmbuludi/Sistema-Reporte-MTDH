"""Institutional reports keep each figure's dates, unit and territorial measure."""
import json

import pandas as pd
import pytest

from src import contingencias, finanzas, mensual, presupuesto_social
from src.data import load_periods, load_territory
from src.gestion_laboral import load_labour
from src.reports import gestion
from src.views.area import PROCESSED


@pytest.fixture(scope="module")
def bases():
    data, catalog = load_periods()
    budget, manifest = finanzas.load_fiscal()
    groups, programs = presupuesto_social.load_social_budget()
    return {"data": data, "catalog": catalog, "territory": load_territory(),
            "budget": budget, "budget_manifest": manifest, "labour": load_labour(),
            "program_budget": mensual.program_budget(), "contingencies": contingencias.monthly(),
            "contingency_places": contingencias.territorial(), "contingency_catalog": contingencias.catalog(),
            "social_groups": groups, "social_programs": programs,
            "government_budget": finanzas.load_government()}


@pytest.fixture(scope="module", params=["anual", "gobierno"])
def report(request, bases):
    return gestion.build(bases, request.param)


def block(report, key):
    return next(item for item in report["blocks"] if item["key"] == key)


def delivery(report, prefix):
    return next(item for item in report["deliveries"] if item["what"].startswith(prefix))


def text(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def test_enos_uses_event_dates_through_september_in_both_management_reports(report):
    enos = block(report, "riesgos")
    kits = delivery(report, "Kits humanitarios")
    assert "septiembre de 2026" in report["period_label"]
    # The 27 October source contains 14,581 kits, but only 4,291 were delivered
    # through September. Neither the whole source nor its published 28/09 start
    # defines the annual/government report's date selection.
    assert kits["amount_people"] == 4291
    assert "11 provincias" in kits["context"]
    assert next(k for k in enos["kpis"] if k["label"] == "Kits entregados")["value"] == 4291
    assert sum(enos["visual"]["map"].values()) == 4291
    assert len(enos["visual"]["map"]) == 11
    provincial = enos["table"]["rows"][:-1]
    total = enos["table"]["rows"][-1]
    assert total["provincia"] == "Total nacional"
    assert sum(row["kits"] for row in provincial) == total["kits"] == 4291
    assert len([row for row in provincial if row["kits"] > 0]) == 11
    assert total["bono_familias"] == 1171 and total["bono_monto"] == pytest.approx(354987.39)
    assert "La base de alertas inicia el 05/10/2026" in text(enos)
    assert "11.207" not in text(enos) and "14.581" not in text(enos)


def test_enos_bonus_remains_confirmed_reference_with_its_own_cut(report):
    bonus = delivery(report, "Bono de contingencia")
    assert bonus["amount_people"] == 1171
    assert bonus["money"] == pytest.approx(354987.39, abs=0.001)
    assert "familias" in bonus["detail"].lower()
    # Keeping the confirmed amount does not turn an October balance into a
    # September disbursement: its reference date must remain visible.
    assert "27/10/2026" in text(bonus)
    assert "pagados" not in bonus.get("money_word", "").lower()


def test_managed_contingency_payments_are_not_claimed_as_paid_people(report):
    assert not any(d["what"] == "Bonos de contingencia pagados" for d in report["deliveries"])
    for item in report["deliveries"]:
        if item.get("amount_people") == 113 and "contingencia" in item["what"].lower():
            wording = text(item).lower()
            assert "núcleos familiares" in wording
            assert "personas" not in wording and "pagad" not in wording
    assert "ya fueron entregados" not in text(block(report, "riesgos"))


def test_brigade_map_uses_attended_population_not_number_of_brigades(report):
    raw = pd.read_parquet(PROCESSED / "brigadas.parquet")
    first = "2026-01" if report["mode"] == "anual" else "2023-12"
    selected = raw.loc[raw.periodo.between(first, "2026-09")]
    expected = selected.groupby("provincia_codigo").atendida.sum().to_dict()
    actual = block(report, "brigadas")["visual"]["map"]
    assert actual == expected
    if report["mode"] == "anual":
        assert sum(actual.values()) == 331445
        assert actual["09"] == 102114
        assert len(selected) == 901


def test_youth_accreditations_keep_source_total_without_universal_400_claim(report):
    youth = delivery(report, "Jóvenes en Acción")
    wording = text([youth, block(report, "jovenes")])
    assert "USD 400 por joven habilitado" not in wording
    if report["mode"] == "anual":
        assert youth["amount_people"] == 126855
        assert youth["money"] == pytest.approx(50754800, abs=0.001)
    # The annual total includes January/February phase 2 settlements and July
    # phase 3 payments. Its reported transaction count is not unique people.
    assert "transferencias acreditadas" in youth["detail"].lower()


def test_other_verified_cover_figures_are_preserved(bases):
    report = gestion.build(bases, "anual")
    transfers = delivery(report, "Transferencias monetarias")
    services = delivery(report, "Servicios de protección social")
    brigades = delivery(report, "Brigadas sociales")
    credit = delivery(report, "Crédito de Desarrollo Humano")
    assert transfers["amount_people"] == 1578019
    assert transfers["money"] == pytest.approx(1011249393.8388579, abs=0.01)
    assert services["amount_people"] == 453994
    assert services["money"] == pytest.approx(168752803.413388, abs=0.01)
    assert "11.215 unidades de atención" in services["context"]
    assert brigades["amount_people"] == 331445
    assert "901 brigadas" in brigades["detail"] and "24 provincias" in brigades["context"]
    assert credit["amount_people"] == 44834
    assert credit["money"] == pytest.approx(48036993.87, abs=0.01)
    women = next(k for k in block(report, "cdh")["kpis"] if k["label"] == "Créditos para mujeres")
    assert women["value"] == pytest.approx(94.52647544274436)


def test_latest_section_overview_uses_full_enos_history_and_filtered_bonus():
    from src.reports.panorama import _block
    from src.views.riesgos import RiskView

    result = _block("riesgos", "Plan ENOS: respuesta del Ministerio", "storm", RiskView())
    assert result["period"] == "Del 27/02/2026 al 27/10/2026"
    assert result["update"]["label"] == result["period"]
    assert next(k for k in result["kpis"] if k["label"].startswith("Kits"))["value"] == 14581
    assert not any(k["value"] == 113 for k in result["kpis"])
    assert "354.987,39" in text(result)


def test_management_pdf_keeps_bonus_cents_and_source_scope(bases):
    import pymupdf

    content = gestion.generate(gestion.build(bases, "anual"))
    with pymupdf.open(stream=content, filetype="pdf") as document:
        output = "\n".join(page.get_text() for page in document)
        assert "4.291" in output and "11.207" not in output
        assert "354.987,39" in output and "33.641,04" in output
        assert "referencia fuera del período" in output
        assert "Bonos de contingencia pagados" not in output
        assert "USD 400 por joven habilitado" not in output
        for page in document:
            for block_ in page.get_text("dict")["blocks"]:
                for line in block_.get("lines", []):
                    for span in line["spans"]:
                        x0, y0, x1, y1 = span["bbox"]
                        assert 0 <= x0 <= x1 <= page.rect.width + 1
                        assert 0 <= y0 <= y1 <= page.rect.height + 1
