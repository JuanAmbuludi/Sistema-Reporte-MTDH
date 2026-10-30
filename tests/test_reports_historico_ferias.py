"""Institutional reports reconcile dated history without summing stocks or sources."""
import pandas as pd
import pytest

from src import contingencias, ferias, finanzas, mensual, presupuesto_social
from src.data import load_periods, load_territory
from src.gestion_laboral import load_labour
from src.reports import gestion, panorama
from src.reports.ferias import period_block
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
            "social_groups": groups, "social_programs": programs, "government_budget": finanzas.load_government()}


@pytest.mark.parametrize("start,yearly", [("2023-11", True), ("2026-01", False), ("2026-09", False)])
def test_each_training_source_reconciles_to_its_period(start, yearly):
    block = period_block(start, "2026-09", "Período", yearly=yearly)
    rows = ferias.load()
    expected = rows.loc[rows.periodo_id.between(start, "2026-09")].groupby("fuente").participaciones.sum().to_dict()
    assert {r["fuente"]: r["participaciones"] for r in block["source_totals"]} == expected
    for source, total in expected.items():
        assert sum(r[source] or 0 for r in block["table"]["rows"]) == total
    assert len(block["visual"]["rows"]) == 2
    assert "personas únicas" not in " ".join(k["label"] for k in block["kpis"])


def test_government_report_uses_observed_stocks_and_historic_credit(bases):
    report = gestion.build(bases, "gobierno")
    blocks = {b["key"]: b for b in report["blocks"]}
    for section, key in [("bonos_pensiones", "transferencias"), ("proteccion_integral", "servicios")]:
        data = bases["data"]
        rows = data.loc[data.seccion.eq(section) & data.periodo_id.astype(str).str.len().eq(7)
                        & data.periodo_id.between("2023-11", "2026-09")]
        monthly = rows.groupby("periodo_id").usuarios.sum()
        periods = list({p[:4]: p for p in sorted(monthly.index)}.values())
        assert blocks[key]["visual"]["values"] == [monthly[p] for p in periods]
        assert len(blocks[key]["visual"]["values"]) == 4
    credits = pd.read_parquet(PROCESSED / "cdh_territorio.parquet")
    selected = credits.loc[credits.fuente.eq("desembolso") & credits.periodo.between("2023-11", "2026-09")]
    assert blocks["cdh"]["kpis"][0]["value"] == selected.creditos.sum() == 152517
    assert sum(blocks["cdh"]["visual"]["values"]) == selected.creditos.sum()
    assert {r["fuente"]: r["participaciones"] for r in blocks["ferias"]["source_totals"]} == {
        "inclusion_economica": 176661, "empleabilidad_autoempleo": 11756}


def test_both_institutional_export_paths_include_new_section(bases):
    monthly = panorama.build_panorama(bases, "Informe")
    annual = gestion.build(bases, "anual")
    for report in [monthly, annual]:
        blocks = {b["key"]: b for b in report["blocks"]}
        assert {"transferencias", "servicios", "cdh", "ferias"} <= blocks.keys()
        assert blocks["ferias"]["label"] == "Ferias de Empleabilidad y Autoempleo"
    fair = next(b for b in monthly["blocks"] if b["key"] == "ferias")
    assert {r["fuente"]: r["participaciones"] for r in fair["source_totals"]} == {
        "inclusion_economica": 5072, "empleabilidad_autoempleo": 309}
