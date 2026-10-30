"""Visible update dates belong to source revisions, never queries or deployments."""
import json
import os

from src import corte


def test_monthly_sections_have_independent_revision_clocks(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    registry = processed / "actualizacion_secciones.json"
    registry.write_text(json.dumps({"areas": {
        "transferencias": {"actualizado_utc": "2026-10-25T23:03:00+00:00"},
        "servicios": {"actualizado_utc": "2026-10-26T15:00:00+00:00"},
        "presupuesto_social": {"actualizado_utc": "2026-10-24T12:00:00+00:00"},
    }}))
    monkeypatch.setattr(corte, "PROCESSED", processed)
    period = {"year": 2026, "month": 9}
    before = corte.stamp("transferencias", period)
    assert before["updated_short"] == "25/10/2026 18:03"
    assert corte.stamp("servicios", period)["updated_short"] == "26/10/2026 10:00"
    (processed / "manifest_laboral.json").write_text(json.dumps({"fecha_consulta_utc": "2026-11-02T15:00:00+00:00"}))
    os.utime(registry, (2000000000, 2000000000))
    assert corte.stamp("transferencias", period) == before
    assert corte.stamp("presupuesto_social", period)["updated_short"] == "24/10/2026 07:00"
    assert corte.stamp("no_registrada", period)["updated"] == ""


def test_labour_query_is_distinct_from_data_revision(tmp_path, monkeypatch):
    series = tmp_path / "series"
    (series / "laboral").mkdir(parents=True)
    path = series / "laboral/ultima_consulta.json"
    data = {"consulta_utc": "2026-10-29T12:15:00+00:00", "actualizado_datos_utc": "2026-10-27T12:15:00+00:00"}
    path.write_text(json.dumps(data))
    monkeypatch.setattr(corte, "SERIES", series)
    before = corte.stamp("laboral")
    data["consulta_utc"] = "2026-10-30T12:15:00+00:00"
    path.write_text(json.dumps(data))
    assert corte.stamp("laboral") == before
    assert before["updated_short"] == "27/10/2026 07:15"
    assert before["updated_label"] == "Actualizado el"
    assert corte.labour_consulted_at().strftime("%d/%m/%Y") == "30/10/2026"


def test_undated_phase4_keeps_cut_separate_from_revision(tmp_path, monkeypatch):
    from src.views.jovenes_fase4 import PhaseFourView

    (tmp_path / "actualizacion_secciones.json").write_text(json.dumps({"areas": {
        "jovenes_fase4": {"actualizado_utc": "2026-10-30T15:30:00+00:00"}}}))
    monkeypatch.setattr(corte, "PROCESSED", tmp_path)
    view = PhaseFourView()
    view.select()
    assert view.prepare()
    update = view.update_stamp()
    assert update["cut"] == "Fuente sin fecha de corte"
    assert update["updated_short"] == "30/10/2026 10:30"
    assert view.report_context(view.label)["update"] == update


def test_monthly_budget_block_uses_latest_revision_of_all_its_sources(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from src.reports.panorama import _budget_block

    (tmp_path / "actualizacion_secciones.json").write_text(json.dumps({"areas": {
        "presupuesto_fiscal": {"actualizado_utc": "2026-10-24T12:00:00+00:00"},
        "presupuesto_social": {"actualizado_utc": "2026-10-25T12:00:00+00:00"},
        "presupuesto_gobierno": {"actualizado_utc": "2026-10-26T12:00:00+00:00"},
    }}))
    monkeypatch.setattr(corte, "PROCESSED", tmp_path)
    period = {"id": "2026-09", "year": 2026, "month": 9, "label": "Septiembre 2026"}
    common = {"catalog": lambda: [period], "select": lambda period: None, "prepare": lambda: True}
    fiscal = SimpleNamespace(**common, stats={"codificado": 100, "devengado": 60, "ejecucion": 60},
                             cut_text="30/09/2026", update_stamp=lambda: corte.stamp("presupuesto_fiscal", period, cut_text="30/09/2026"))
    government = SimpleNamespace(**common, stats={"acumulado": 1000})
    block = _budget_block({"presupuesto": fiscal, "presupuesto_gobierno": government})
    assert block["update"]["updated_short"] == "26/10/2026 07:00"
    assert block["update"]["cut"] == "30/09/2026"


def test_monthly_fair_block_keeps_its_own_revision(tmp_path, monkeypatch):
    import pandas as pd
    from src import ferias
    from src.reports.ferias import latest_block

    (tmp_path / "actualizacion_secciones.json").write_text(json.dumps({"areas": {
        "ferias": {"actualizado_utc": "2026-10-25T12:00:00+00:00"},
        "transferencias": {"actualizado_utc": "2026-10-30T12:00:00+00:00"},
    }}))
    monkeypatch.setattr(corte, "PROCESSED", tmp_path)
    monkeypatch.setattr(ferias, "load", lambda: pd.DataFrame({
        "periodo_id": ["2026-09"], "fuente": ["inclusion_economica"],
        "provincia_codigo": ["17"], "participaciones": [7],
    }))
    block = latest_block()
    assert block["update"]["label"] == "Septiembre de 2026"
    assert block["update"]["updated_short"] == "25/10/2026 07:00"
