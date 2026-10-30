"""Historical alerts extend queries without overriding operational decisions."""
import gzip
import json

import pandas as pd
import pytest

from src import enos, enos_excel
from src.views.respuesta import Response, alert_date, alerts_evolution


def alert(code, when, **extra):
    return dict(codigo=code, fecha=when, provincia="Guayas", canton="Balao", estado="Pendiente",
                prioridad="Baja", codigo_ua="123", unidad="Unidad", servicio="Desarrollo Infantil",
                afectacion_servicio_confirmada=True, origen="matriz_alertas", fuente="matriz.xlsx", **extra)


@pytest.fixture
def register(tmp_path, monkeypatch):
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    monkeypatch.setattr(enos, "FOLDER", processed)
    data = {"desde": "2026-09-01", "corte": "2026-09-30", "alertas": [alert("CURRENT", "2026-09-20")],
        "kits": [{"id_kobo": "K", "fecha": "2026-09-20", "provincia": "Guayas", "canton": "Balao", "kits": 7, "familias": 7}],
        "brigadas": [], "cortes": {"alertas": "2026-09-30", "kits": "2026-09-30", "bonos": "2026-09-30"},
        "bonos": {"gestionados": [], "articulacion": [], "planificacion": {}}, "fuentes": [], "notas": {},
        "criterio_alertas": "codigo_ua_y_reportes_sectoriales", "control": {"alertas_excluidas_codigos": ["EXCLUDED"]}}
    target = processed / "seguimiento_enos_2026-09-30.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return processed, data, target


def archive(processed, records):
    path = processed / enos.HISTORICAL_ALERTS
    path.write_text(json.dumps({"alertas": records, "fuentes": [{"nombre": "matriz.xlsx", "sha256": "source"}],
                               "antecedentes": [{"anio": 2023, "registros": 572, "fecha_disponible": False}]}), encoding="utf-8")
    return path


def test_archive_extends_government_dates_without_changing_current_counts_or_publications(register):
    processed, _, target = register
    before = target.read_bytes()
    original = enos.history(live=True)
    archive(processed, [alert("OLD", "2024-02-04"), alert("CURRENT", "2025-01-01"), alert("EXCLUDED", "2024-03-01")])
    merged = enos.history(live=True)
    assert [(r["codigo"], r["fecha"]) for r in merged["alertas"]] == [("OLD", "2024-02-04"), ("CURRENT", "2026-09-20")]
    assert enos.history_window(merged) == (pd.Timestamp("2024-02-04"), pd.Timestamp("2026-09-20"))
    assert merged["ventana_operativa"] == {"desde": original["desde"], "hasta": original["corte"]}
    for name in ("kits", "brigadas", "bonos", "cortes"):
        assert merged[name] == original[name]
    assert target.read_bytes() == before
    assert len(Response(merged, since="2026-01-01", until="2026-12-31").alerts) == 1


def test_excel_exclusion_wins_even_for_id_not_in_daily_publications(register, monkeypatch):
    processed, _, _ = register
    archive(processed, [alert("OLD", "2024-02-04"), alert("NO", "2024-04-01")])
    original_read = enos_excel.read
    monkeypatch.setattr(enos_excel, "overlay", lambda data, folder: data)
    monkeypatch.setattr(enos_excel, "read", lambda folder, kind: ("2026-09-30", {}, [(2, {"codigo": "NO", "incluir": "No"})])
                        if kind == "alertas" else original_read(folder, kind))
    assert {r["codigo"] for r in enos.history(live=True)["alertas"]} == {"OLD", "CURRENT"}


def test_validated_register_merges_archive_and_preserves_validated_exclusions_on_bad_upload(register):
    processed, _, _ = register
    original = enos.history(live=True)
    folder = enos_excel.directory(processed)
    folder.mkdir()
    publication = {"formato": "ENOS_VALIDADO_1", "datos": original, "fuentes": {},
                   "identificadores": {"alertas": ["CURRENT", "NO"]}}
    (folder / enos_excel.VALIDATED).write_bytes(gzip.compress(json.dumps(publication).encode()))
    archive(processed, [alert("OLD", "2024-02-04"), alert("NO", "2024-04-01")])
    (folder / "alertas.xlsx").write_bytes(b"invalid upload")
    data = enos.history()
    assert data["carga_pendiente"]
    assert {r["codigo"] for r in data["alertas"]} == {"OLD", "CURRENT"}
    assert data["kits"] == original["kits"]
    # Repeated cache loads and a corrected archive replace their own IDs once.
    publication["datos"] = data
    (folder / enos_excel.VALIDATED).write_bytes(gzip.compress(json.dumps(publication).encode()))
    archive(processed, [alert("OLD", "2024-03-04"), alert("NO", "2024-04-01")])
    revised = enos.history()
    assert {r["codigo"]: r["fecha"] for r in revised["alertas"]} == {"OLD": "2024-03-04", "CURRENT": "2026-09-20"}
    assert revised["desde"] == "2024-03-04"


def test_month_precision_requires_entire_month_and_is_never_drawn_as_day_one(register):
    processed, _, _ = register
    monthly = alert("MONTH", "2024-04-01", fecha_hasta="2024-04-30", fecha_precision="mes_reporte")
    archive(processed, [monthly, alert("DAY", "2024-04-09")])
    data = enos.history(live=True)
    full = Response(data, since="2024-04-01", until="2024-04-30")
    assert set(full.alerts.codigo) == {"MONTH", "DAY"}
    assert set(Response(data, since="2024-04-01", until="2024-04-29").alerts.codigo) == {"DAY"}
    assert set(Response(data, since="2024-04-02", until="2024-04-30").alerts.codigo) == {"DAY"}
    figure = alerts_evolution(full)
    assert figure.data[1].name == "Registradas en el mes"
    assert list(figure.data[1].y) == [2]
    assert "mes de reporte" in alert_date(monthly) and "01/04" not in alert_date(monthly)
    assert "572 nudos críticos" in full.publication_text()
    assert "572 nudos críticos" not in Response(data, since="2026-08-28", until="2026-09-30").publication_text()


def test_reported_interval_is_counted_once_only_when_fully_contained(register):
    processed, _, _ = register
    interval = alert("RANGE", "2024-07-15", fecha_hasta="2024-07-16", fecha_precision="intervalo")
    archive(processed, [interval])
    data = enos.history(live=True)
    assert len(Response(data, since="2024-07-15", until="2024-07-16").alerts) == 1
    assert Response(data, since="2024-07-15", until="2024-07-15").alerts.empty
    assert Response(data, since="2024-07-16", until="2024-07-16").alerts.empty
    assert "intervalo reportado" in alert_date(interval)


def test_archive_fingerprint_participates_in_cache_and_validation(register):
    processed, _, _ = register
    source = archive(processed, [alert("OLD", "2024-02-04")])
    assert source in enos.history_paths()
    assert "data/processed/alertas_historicas.json" in enos_excel.source_hashes(processed)
    archive(processed, [alert("OLD", "2024-02-04"), alert("OLD", "2024-02-05")])
    with pytest.raises(ValueError, match="códigos únicos"):
        enos.history(live=True)
