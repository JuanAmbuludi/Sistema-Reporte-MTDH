"""Daily refresh: real parsers, repeat queries, failed batches and dashboard reloads."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
from threading import Thread

import pandas as pd
import pytest
import requests

from scripts.update_history import update, update_current_labour
from src import corte, gestion_laboral, sgde_scraper


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / "source"
    columns = {
        "base": ["estado", "prov", "sexo", "edad", "disc", "n"],
        "canton": ["estado", "canton", "n"],
        "rama": ["estado", "prov", "rama", "n"],
        "tipo": ["estado", "prov", "tipo", "n"],
        "etnia": ["estado", "prov", "etnia", "n"],
        "nac": ["estado", "prov", "nac", "n"],
        "act": ["estado", "prov", "act", "n"],
        "empresas": ["estado", "prov", "n"],
    }
    payload = {"version": 3, "naturaleza": "foto_diaria", "fecha_corte": "2026-10-27",
        "fecha_hora_corte": "2026-10-27T03:35", "registrados": 10, "cols": columns,
        "dic": {"estado": ["Vigente"], "prov": ["Pichincha"], "sexo": ["Mujer"],
            "edad": ["30 a 40"], "disc": ["No"], "canton": [[0, "Quito"]],
            "rama": ["Servicios"], "tipo": ["Indefinido"], "etnia": ["Mestizo"],
            "nac": ["Colombia"], "act": [[0, "Servicios"]]},
        "t": {name: [[*[0] * (len(cols) - 1), 1 if name == "empresas" else 2 if name == "nac" else 10]]
              for name, cols in columns.items()}}
    resources = {page: '../datos/kpis/contratos/dashboard_data.json ../datos/kpis/kpi_trabajo.csv'
                 for page in sgde_scraper.PAGES}
    resources.update(dict(zip(sgde_scraper.FILES, [json.dumps(payload), "indicador,valor\nprueba,1\n",
        "corte\n2026-09-18\n",
        "anio,mes_fin,parcial,dimension,categoria,codigo,expedientes,monto_usd\n2026,9,True,total,Total,,2,100.00\n",
        "orden,periodo,etiqueta,estado,inicio,fin,registrados,beneficiarios,transferencias,monto_transferencia_usd,presupuesto_usd,ejecucion_usd,corte_ejecucion,nota\n3,Fase 3,Fase 3,en_ejecucion,2026-07-01,,10,8,1,400,3200,3200,2026-09,Prueba\n"])))
    for name, value in resources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    return root


@pytest.fixture
def web_source(sources, monkeypatch):
    original = sgde_scraper.collect
    calls = []

    def collect(_local=None):
        raw, receipt = original(sources)
        receipt["consulta_utc"] = (datetime(2026, 10, 27, 12, 15, tzinfo=timezone.utc)
                                   + timedelta(days=len(calls))).isoformat()
        calls.append(receipt["consulta_utc"])
        return raw, receipt

    monkeypatch.setattr(sgde_scraper, "collect", collect)
    return sources


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_repeat_query_updates_consultation_without_redating_or_duplicating_source(web_source, tmp_path):
    data = tmp_path / "data"
    update(data, web=True)
    before = snapshot(data)
    update(data, web=True)
    after = snapshot(data)
    status = "series/laboral/ultima_consulta.json"
    assert json.loads(before.pop(status))["consulta_utc"] == "2026-10-27T12:15:00+00:00"
    last = json.loads(after.pop(status))
    assert last["consulta_utc"] == "2026-10-28T12:15:00+00:00"
    assert last["actualizado_datos_utc"] == "2026-10-27T12:15:00+00:00"
    assert all(r["actualizado_datos_utc"] == "2026-10-27T12:15:00+00:00"
               for r in last["revisiones_fuente"].values())
    assert last["fecha_corte"] == "2026-10-27"
    assert before == after


@pytest.mark.parametrize("failure", ["bad_total", "old_cut", "new_unvalidated_phase"])
def test_invalid_source_keeps_data_and_last_successful_query(web_source, tmp_path, failure):
    data = tmp_path / "data"
    update(data, web=True)
    before = snapshot(data)
    if failure == "new_unvalidated_phase":
        path = web_source / sgde_scraper.FILES[4]
        path.write_text(path.read_text().replace("\n3,Fase", "\n4,Fase"))
    else:
        path = web_source / sgde_scraper.FILES[0]
        payload = json.loads(path.read_text())
        if failure == "bad_total":
            payload["registrados"] = 11
        else:
            payload.update(fecha_corte="2026-10-26", fecha_hora_corte="2026-10-26T03:35")
        path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        update(data, web=True)
    assert snapshot(data) == before


@pytest.mark.parametrize("status,expected_calls", [(503, 2), (404, 1)])
def test_http_retries_transient_failure_but_not_missing_source(sources, monkeypatch, status, expected_calls):
    calls = []
    target = "/" + sgde_scraper.FILES[0]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == target:
                calls.append(self.path)
                if len(calls) == 1:
                    self.send_response(status)
                    self.end_headers()
                    return
            raw = (sources / self.path.lstrip("/")).read_bytes()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(sgde_scraper, "BASE", f"http://127.0.0.1:{server.server_port}/")
    try:
        if status == 404:
            with pytest.raises(requests.HTTPError):
                sgde_scraper.collect()
        else:
            raw, receipt = sgde_scraper.collect()
            assert len(receipt["recursos"]) == 7
            assert sgde_scraper.contracts(raw[sgde_scraper.FILES[0]])[1]["registrados"] == 10
        assert len(calls) == expected_calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_reloads_contracts_after_file_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(gestion_laboral, "SGDE", tmp_path)
    monkeypatch.setattr(gestion_laboral, "_TABLES", {})
    path = tmp_path / "contratos_base.parquet"
    pd.DataFrame({"fecha_corte": ["2026-10-26"], "contratos": [10]}).to_parquet(path)
    assert gestion_laboral.contracts("base").contratos.sum() == 10
    previous_time = path.stat().st_mtime_ns
    pd.DataFrame({"fecha_corte": ["2026-10-27"], "contratos": [11]}).to_parquet(path)
    os.utime(path, ns=(previous_time + 1_000_000, previous_time + 1_000_000))
    current = gestion_laboral.contracts("base")
    assert current.contratos.sum() == 11
    assert current.fecha_corte.iloc[0] == "2026-10-27"


def test_labour_stamp_uses_real_revision_and_preserves_source_cut(tmp_path, monkeypatch):
    series = tmp_path / "series"
    (series / "laboral").mkdir(parents=True)
    (series / "laboral/ultima_consulta.json").write_text(json.dumps({"consulta_utc": "2026-10-28T12:15:00+00:00",
        "actualizado_datos_utc": "2026-10-27T12:15:00+00:00"}))
    (series / "actualizacion.json").write_text(json.dumps({"controles": {
        "contratos": {"fecha_hora_corte": "2026-10-27T03:35"}}}))
    monkeypatch.setattr(corte, "SERIES", series)
    monkeypatch.setattr(corte, "PROCESSED", tmp_path / "absent")
    stamp = corte.stamp("laboral")
    assert stamp["cut"] == "27 de octubre de 2026, 03:35"
    assert stamp["updated"] == "27 de octubre de 2026, 07:15"
    assert stamp["updated_label"] == "Actualizado el"
    assert "Actualizado: 27/10/2026 07:15" in stamp["short"]
    assert corte.labour_consulted_at().day == 28


def test_transport_format_changes_do_not_redate_the_data(web_source, tmp_path):
    data = tmp_path / "data"
    update(data, web=True)
    before = {p: content for p, content in snapshot(data).items() if p.endswith(".parquet")}
    status_path = data / "series/laboral/ultima_consulta.json"
    prior = json.loads(status_path.read_text())
    page = web_source / sgde_scraper.PAGES[0]
    page.write_text(page.read_text() + "\n<!-- cosmetic site update -->")
    payload_path = web_source / sgde_scraper.FILES[0]
    payload_path.write_text(json.dumps(json.loads(payload_path.read_text()), indent=4))
    result = update(data, web=True)
    current = json.loads(status_path.read_text())
    assert current["consulta_utc"] != prior["consulta_utc"]
    assert current["revisiones_fuente"] == prior["revisiones_fuente"]
    assert current["actualizado_datos_utc"] == prior["actualizado_datos_utc"]
    assert result["bases_actualizadas"] == []
    assert before == {p: content for p, content in snapshot(data).items() if p.endswith(".parquet")}


def test_real_contract_change_does_not_redate_retirement_or_youth(web_source, tmp_path):
    data = tmp_path / "data"
    update(data, web=True)
    status_path = data / "series/laboral/ultima_consulta.json"
    before = json.loads(status_path.read_text())
    payload_path = web_source / sgde_scraper.FILES[0]
    payload = json.loads(payload_path.read_text())
    payload["registrados"] = 11
    for name in ("base", "canton", "rama", "tipo", "etnia", "act"):
        payload["t"][name][0][-1] = 11
    payload_path.write_text(json.dumps(payload))
    update(data, web=True)
    after = json.loads(status_path.read_text())
    assert after["actualizado_datos_utc"] == after["consulta_utc"] == "2026-10-28T12:15:00+00:00"
    assert after["revisiones_fuente"]["contratos"] != before["revisiones_fuente"]["contratos"]
    for source in ("jubilados", "jovenes"):
        assert after["revisiones_fuente"][source] == before["revisiones_fuente"][source]


def test_legacy_revision_is_seeded_from_saved_evidence_not_today(web_source, tmp_path):
    data = tmp_path / "data"
    update(data, web=True)
    status_path = data / "series/laboral/ultima_consulta.json"
    status = json.loads(status_path.read_text())
    for field in ("actualizado_datos_utc", "huella_datos_laborales", "revisiones_fuente"):
        status.pop(field)
    status_path.write_text(json.dumps(status))
    update(data, web=True)
    after = json.loads(status_path.read_text())
    assert after["consulta_utc"] == "2026-10-28T12:15:00+00:00"
    assert after["actualizado_datos_utc"] == "2026-10-27T12:15:00+00:00"


def test_refreshing_stock_preserves_unchanged_retirement_observation(tmp_path):
    root = Path(__file__).resolve().parents[1] / "data"
    stage = tmp_path / "data"
    (stage / "processed").mkdir(parents=True)
    for name in ("gestion_laboral.parquet", "manifest_laboral.json"):
        shutil.copyfile(root / "processed" / name, stage / "processed" / name)
    before = pd.read_parquet(stage / "processed/gestion_laboral.parquet")
    audit = json.loads((root / "series/actualizacion.json").read_text())
    checks = audit["controles"]["contratos"]
    new_day = (pd.Timestamp(checks["fecha_corte"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    checks.update(fecha_corte=new_day, fecha_hora_corte=new_day + "T03:35")
    checks["por_estado"]["Vigente"] += 1
    receipt = audit["fuentes"]["web"]
    receipt["consulta_utc"] = (datetime.fromisoformat(receipt["consulta_utc"]) + timedelta(days=1)).isoformat()
    for resource in receipt["recursos"]:
        if resource["url"].endswith("contratos/dashboard_data.json"):
            resource["sha256"] = "b" * 64
    retirees = pd.read_parquet(root / "series/laboral/jubilados.parquet")
    update_current_labour(stage, pd.DataFrame(), checks, receipt, retirees)
    after = pd.read_parquet(stage / "processed/gestion_laboral.parquet")
    unchanged = ["jubilados_compensados", "compensaciones_jubilares_usd", "contratos_del_mes_vigentes"]
    pd.testing.assert_frame_equal(before.loc[before.indicador_id.isin(unchanged)].reset_index(drop=True),
                                  after.loc[after.indicador_id.isin(unchanged)].reset_index(drop=True))
    old_stock = before.loc[before.indicador_id.eq("contratos_vigentes_total")].iloc[0]
    stock = after.loc[after.indicador_id.eq("contratos_vigentes_total")].iloc[0]
    assert stock.valor == old_stock.valor + 1
    assert stock.fecha_consulta_utc > old_stock.fecha_consulta_utc
