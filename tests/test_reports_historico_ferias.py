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


@pytest.mark.parametrize("start,yearly", [("2023-12", True), ("2026-01", False), ("2026-09", False)])
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
                        & data.periodo_id.between("2023-12", "2026-09")]
        monthly = rows.groupby("periodo_id").usuarios.sum()
        periods = list({p[:4]: p for p in sorted(monthly.index)}.values())
        assert blocks[key]["visual"]["values"] == [monthly[p] for p in periods]
        assert len(blocks[key]["visual"]["values"]) == 4
    assert report["period_label"] == "Diciembre de 2023 a septiembre de 2026"
    credits = pd.read_parquet(PROCESSED / "cdh_desembolsos_fechados.parquet")
    selected = credits.loc[credits.periodo.between("2023-12", "2026-09")]
    assert blocks["cdh"]["kpis"][0]["value"] == selected.creditos.sum() == 151629
    assert blocks["cdh"]["kpis"][1]["value"] == pytest.approx(143733886.03)
    assert selected.loc[selected.fecha_precision.eq("mes_reporte"), "creditos"].sum() == 55
    assert "55 operaciones sin fecha diaria" in " ".join(f["text"] for f in blocks["cdh"]["findings"])
    assert sum(blocks["cdh"]["visual"]["values"]) == selected.creditos.sum()
    assert {r["fuente"]: r["participaciones"] for r in blocks["ferias"]["source_totals"]} == {
        "inclusion_economica": 173010, "empleabilidad_autoempleo": 10832}
    assert "Noviembre de 2023" not in " ".join(f["text"] for f in blocks["ferias"]["findings"])


def test_both_institutional_export_paths_include_new_section(bases):
    from src import enos

    monthly = panorama.build_panorama(bases, "Informe")
    annual = gestion.build(bases, "anual")
    for report in [monthly, annual]:
        blocks = {b["key"]: b for b in report["blocks"]}
        assert {"transferencias", "servicios", "cdh", "ferias"} <= blocks.keys()
        assert blocks["ferias"]["label"] == "Ferias de Inclusión Económica, Empleabilidad y Autoempleo"
    fair = next(b for b in monthly["blocks"] if b["key"] == "ferias")
    assert {r["fuente"]: r["participaciones"] for r in fair["source_totals"]} == {
        "inclusion_economica": 5072, "empleabilidad_autoempleo": 309}
    operative = enos.history()["ventana_operativa"]
    risks = next(b for b in monthly["blocks"] if b["key"] == "riesgos")
    assert risks["period"] == f"Del {enos.day(operative['desde']):%d/%m/%Y} al {enos.day(operative['hasta']):%d/%m/%Y}"


@pytest.mark.parametrize("mode,start", [("gobierno", "2023-12-01"), ("anual", "2026-01-01")])
def test_management_alerts_are_event_dated_without_later_fallback(bases, mode, start):
    from src import enos

    report = gestion.build(bases, mode)
    block = next(b for b in report["blocks"] if b["key"] == "riesgos")
    history = enos.history()
    expected = [row for row in history["alertas"] if start <= row["fecha"] <= "2026-09-30"]
    kpi = next(k for k in block["kpis"] if k["label"] == "Alertas registradas")
    assert kpi["value"] == len(expected)
    assert sum(r["alertas"] or 0 for r in block["table"]["rows"][:-1]) == len(expected)
    assert block["table"]["rows"][-1]["alertas"] == len(expected)
    delivery = next(d for d in report["deliveries"] if d["what"].startswith("Alertas de riesgos"))
    assert delivery["amount_people"] == len(expected)
    assert "fechas disponibles" in " ".join(item["text"] for item in block["findings"])
    if mode == "gobierno":
        assert "sin fechar las alertas" in " ".join(item["text"] for item in block["findings"])


def test_alert_caption_preserves_the_end_of_monthly_and_interval_records():
    rows = pd.DataFrame([{"fecha": "2024-04-01", "fecha_hasta": "2024-04-30"},
                         {"fecha": "2024-07-15", "fecha_hasta": "2024-07-16"},
                         {"fecha": "2024-07-12", "fecha_hasta": None}])
    assert gestion._alert_span(rows) == "del 01/04/2024 al 16/07/2024"


@pytest.mark.parametrize("mode,alerts", [("gobierno", 1699), ("anual", 1176)])
def test_bonus_reference_uses_its_full_cut_without_expanding_dated_actions(bases, mode, alerts):
    from src.reports.enos_scope import response_view

    report = gestion.build(bases, mode)
    cards = {d["what"]: d for d in report["deliveries"]}
    enabled = cards["Bono de contingencia · habilitados"]
    collected = cards["Bono de contingencia · cobrados"]
    assert (enabled["amount_people"], enabled["money"]) == (1720, pytest.approx(521322.45))
    assert (collected["amount_people"], collected["money"]) == (692, pytest.approx(209776.23))
    for card in [enabled, collected]:
        assert card["context"] == "Referencia al 29/10/2026 · fuera del período"
    block = next(b for b in report["blocks"] if b["key"] == "riesgos")
    rows = block["table"]["rows"]
    assert sum(r["bono_familias"] or 0 for r in rows[:-1] if pd.notna(r["bono_familias"])) == rows[-1]["bono_familias"] == 1720
    assert rows[-1]["bono_monto"] == pytest.approx(521322.45)
    assert rows[-1]["alertas"] == alerts
    assert rows[-1]["kits"] == 4938
    findings = " ".join(f["text"] for f in block["findings"])
    assert "25/09/2026 al 29/10/2026" in findings
    assert "no acredita el acumulado de toda la gestión" in findings
    # The underlying dashboard query must still honor the actual habilitation dates.
    dated = response_view("2023-12", "2026-09").response
    assert dated.articulation.personas.sum() == dated.managed.personas.sum() == 1
    assert dated.articulation.monto.sum() == pytest.approx(302.94)
