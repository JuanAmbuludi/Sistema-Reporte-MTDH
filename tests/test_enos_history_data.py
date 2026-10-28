"""Reconciliation contracts for current event history, separate from issued PDFs."""
import json

import pandas as pd
import pytest

from src import enos
from src.views import respuesta


@pytest.fixture
def register(tmp_path, monkeypatch):
    monkeypatch.setattr(enos, "FOLDER", tmp_path)
    monkeypatch.setattr(respuesta, "_code", lambda province: {"Guayas": "09", "El Oro": "07"}.get(province))

    def write(published, **changes):
        data = {
            "desde": "2026-09-01", "corte": published,
            "criterio_alertas": "afectacion_confirmada",
            "alertas": [], "kits": [], "brigadas": [],
            "bonos": {"gestionados": [], "articulacion": [], "planificacion": {}},
            "cortes": {"alertas": published, "kits": published, "bonos": published},
            "bonos_referencia_confirmada": {"articulacion": {"confirmacion": "Acumulado confirmado"}},
            "fuentes": [], "notas": {},
        }
        data.update(changes)
        (tmp_path / f"seguimiento_enos_{published}.json").write_text(json.dumps(data), encoding="utf-8")
        return data

    return write


def alert(identifier, when, *, confirmed=True, status="Pendiente"):
    return {"codigo": identifier, "fecha": when, "provincia": "Guayas", "canton": "Balao",
            "estado": status, "prioridad": "Baja", "codigo_ua": "123", "unidad": "Unidad",
            "afectacion_servicio_confirmada": confirmed, "servicio": "Desarrollo Infantil",
            "afectacion_servicio": "Acceso afectado", "origen": "aplicativo", "fuente": "fuente.xlsx"}


def kit(identifier, when, count):
    return {"id_kobo": identifier, "fecha": when, "provincia": "Guayas", "canton": "Balao",
            "kits": count, "familias": count}


def brigade(identifier, when, canton="Balao"):
    return {"id": identifier, "fecha": when, "provincia": "Guayas", "canton": canton, "tipo": "Emergencia"}


def observation(folder, published, cut, units):
    data = {"corte": cut, "registros": [
        {"provincia": "Guayas", "canton": "Balao", "servicio": "CDI", "unidades": units,
         "estado": "Suspendida", "programa_id": "DII", "corte_fuente": cut}
    ], "detalle": []}
    (folder / f"continuidad_servicios_{published}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def response(data, since, until, continuity=None):
    return respuesta.Response(data, since=since, until=until,
                              continuity=continuity if continuity is not None else enos.continuity_at(until))


def test_latest_id_wins_once_and_reconciliation_does_not_rewrite_publications(register):
    register("2026-10-20", alertas=[alert("A", "2026-09-10")], kits=[kit("K", "2026-09-10", 5)])
    register("2026-10-21", alertas=[alert("A", "2026-09-10", status="Resuelto"), alert("B", "2026-09-12")],
             kits=[kit("K", "2026-09-10", 8)])
    before = {p.name: p.read_bytes() for p in enos.snapshots()}
    data = enos.history()
    assert {row["codigo"]: row["estado"] for row in data["alertas"]} == {"A": "Resuelto", "B": "Pendiente"}
    assert len(data["kits"]) == 1 and data["kits"][0]["kits"] == 8
    assert enos.history_window(data) == (pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-12"))
    assert {p.name: p.read_bytes() for p in enos.snapshots()} == before


def test_date_correction_outside_selected_period_does_not_revive_old_version(register):
    register("2026-10-20", alertas=[alert("A", "2026-09-10"), alert("ANCHOR", "2026-09-01")],
             kits=[kit("K", "2026-09-10", 5)])
    register("2026-10-21", alertas=[alert("A", "2026-10-12")], kits=[kit("K", "2026-10-12", 8)])
    selected = response(enos.history(), "2026-09-01", "2026-09-30")
    assert selected.alerts.codigo.tolist() == ["ANCHOR"]
    assert selected.kits.empty and selected.kits_total == 0


def test_latest_explicit_exclusion_removes_old_included_alert(register):
    register("2026-10-20", alertas=[alert("A", "2026-09-10"), alert("B", "2026-09-12")])
    register("2026-10-21", alertas=[alert("A", "2026-09-10", confirmed=False)])
    data = enos.history()
    assert [row["codigo"] for row in data["alertas"]] == ["B"]
    assert response(data, "2026-09-01", "2026-09-30").alerts.codigo.tolist() == ["B"]


def test_reconciled_alert_retains_its_source_inclusion_criterion(register):
    sectorial = dict(alert("SECTORIAL", "2026-09-10"), codigo_ua="", origen="reporte_sectorial")
    register("2026-10-20", criterio_alertas="codigo_ua_y_reportes_sectoriales", alertas=[sectorial])
    # A later source with another inclusion rule does not retract that record.
    register("2026-10-21", criterio_alertas="codigo_ua", alertas=[])
    data = enos.history()
    assert [row["codigo"] for row in data["alertas"]] == ["SECTORIAL"]
    assert response(data, "2026-09-01", "2026-09-30").alerts.codigo.tolist() == ["SECTORIAL"]


def test_complete_kit_replacement_discards_omitted_ids_then_partial_updates_merge(register):
    register("2026-10-20", kits=[kit("OLD", "2026-09-01", 90), kit("KEEP", "2026-09-02", 2)])
    register("2026-10-21", kits=[kit("KEEP", "2026-09-02", 3)],
             kits_metadatos={"reemplaza_corte_anterior": True})
    register("2026-10-22", kits=[kit("NEW", "2026-09-03", 4)])
    selected = response(enos.history(), "2026-09-01", "2026-09-30")
    assert set(selected.kits.id_kobo) == {"KEEP", "NEW"}
    assert selected.kits_total == 7


def test_final_day_includes_late_timestamps_and_preserves_local_source_day(register):
    stamp = "2026-09-30T23:59:59-05:00"
    data = register("2026-09-30", alertas=[alert("A", stamp)], kits=[kit("K", stamp, 5)],
                    brigadas=[brigade("B", stamp)])
    # Check the direct publication path as well as normalized merged history.
    direct = response(data, "2026-09-30", "2026-09-30")
    merged = response(enos.history(), "2026-09-30", "2026-09-30")
    for selected in (direct, merged):
        assert selected.alerts.codigo.tolist() == ["A"]
        assert selected.kits_total == 5
        assert [row["id"] for row in selected.brigadas] == ["B"]
    indexed = enos.dates(pd.Series([stamp], index=[42]))
    assert indexed.index.tolist() == [42] and indexed.loc[42] == pd.Timestamp("2026-09-30")


def test_canonical_brigades_win_at_same_cut_and_later_partial_keeps_other_ids(register):
    register("2026-10-20", brigadas=[brigade("OBSOLETE", "2026-03-01")])
    register("2026-10-22", brigadas=[brigade("B1", "2026-09-24", "Dato anterior"),
                                    brigade("B2", "2026-09-25", "Dato anterior")])
    canonical = {"corte": "2026-10-22", "brigadas": [brigade("B1", "2026-09-24", "Salitre"),
                                                      brigade("B2", "2026-09-25", "Salitre")], "fuentes": []}
    (enos.FOLDER / "brigadas_emergencia.json").write_text(json.dumps(canonical), encoding="utf-8")
    register("2026-10-23", brigadas=[brigade("B1", "2026-09-24", "Balao"), brigade("B3", "2026-10-23")])
    data = enos.history()
    assert {row["id"]: row["canton"] for row in data["brigadas"]} == {"B1": "Balao", "B2": "Salitre", "B3": "Balao"}
    assert data["cortes"]["brigadas"] == "2026-10-23"


def test_continuity_uses_one_latest_observation_even_if_before_period_start(register):
    register("2026-10-20", alertas=[alert("A", "2026-09-01")])
    observation(enos.FOLDER, "2026-09-02", "2026-09-02T19:00:00", 10)
    observation(enos.FOLDER, "2026-09-15", "2026-09-15T19:00:00", 8)
    # A correction of the same observation supersedes its earlier publication.
    observation(enos.FOLDER, "2026-09-16", "2026-09-15T19:00:00", 7)
    selected_cut = enos.continuity_at("2026-09-20")
    assert selected_cut["registros"][0]["unidades"] == 7
    selected = response(enos.history(), "2026-09-19", "2026-09-20", selected_cut)
    assert selected.closed_units == 7 and selected.available["continuidad"] is True
    assert selected.continuity_cut == pd.Timestamp("2026-09-15T19:00:00")


def test_continuity_before_first_observation_is_unavailable_not_an_observed_zero(register):
    register("2026-10-20", alertas=[alert("A", "2026-09-01")])
    observation(enos.FOLDER, "2026-09-15", "2026-09-15T19:00:00", 8)
    unavailable = enos.continuity_at("2026-09-14")
    assert unavailable["disponible"] is False and unavailable["registros"] == []
    selected = response(enos.history(), "2026-09-01", "2026-09-14", unavailable)
    assert selected.available["continuidad"] is False
    assert "no hay un corte territorial disponible" in selected.missing_text()


def test_response_without_explicit_continuity_resolves_the_selected_end_date(register):
    register("2026-10-20", alertas=[alert("A", "2026-09-01")])
    observation(enos.FOLDER, "2026-09-15", "2026-09-15T19:00:00", 8)
    observation(enos.FOLDER, "2026-09-25", "2026-09-25T19:00:00", 3)
    selected = respuesta.Response(enos.history(), since="2026-09-16", until="2026-09-20")
    assert selected.closed_units == 8
    assert selected.continuity_cut == pd.Timestamp("2026-09-15T19:00:00")
    assert selected.available["continuidad"] is True
