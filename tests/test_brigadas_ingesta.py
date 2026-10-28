from datetime import datetime
import hashlib
import json

import openpyxl
import pytest

from scripts.update_brigadas import update
from src import brigadas


def workbook(tmp_path, rows):
    path = tmp_path / "brigadas.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "PLANIFICACIÓN"
    # Deliberately reordered columns plus private source-only fields.
    sheet.append(["PROVINCIA", "TIPO DE BRIGADA", "#", "FECHA", "CANTÓN", "DOMICILIO", "CONTACTO"])
    for row in rows:
        sheet.append(row)
    book.save(path)
    return path


def event(identifier, when, kind="EMERGENCIA", canton="PASAJE"):
    return ["EL ORO", kind, identifier, when, canton, "Domicilio reservado", "Contacto reservado"]


def test_full_history_and_explicit_cut_are_independent_of_report_window(tmp_path):
    source = workbook(tmp_path, [event(1, datetime(2024, 2, 6)),
                                event(2, "28/08/2026", " emergencia "),
                                event(3, "2026-09-24"),
                                event(4, "2026-10-13"),
                                event(5, "2026-10-22", "REGULAR MTDH")])
    data = brigadas.read_workbook(source, "2026-10-22")
    assert [r["id"] for r in data["brigadas"]] == ["BRI-1", "BRI-2", "BRI-3", "BRI-4"]
    assert (data["desde"], data["hasta"], data["corte"]) == ("2024-02-06", "2026-10-13", "2026-10-22")
    assert all(set(row) == {"id", "fecha", "provincia", "canton", "tipo"} for row in data["brigadas"])
    assert "reservado" not in json.dumps(data)
    assert data["fuentes"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_identical_ids_count_once_but_conflicts_fail(tmp_path):
    source = workbook(tmp_path, [event(29, "2026-09-24"), event("29.0", "2026-09-24")])
    data = brigadas.read_workbook(source, "2026-10-22")
    assert len(data["brigadas"]) == 1
    assert data["control"]["duplicados_identicos"] == 1
    source = workbook(tmp_path, [event(29, "2026-09-24"), event(29, "2026-09-25")])
    with pytest.raises(ValueError, match="contradictorios"):
        brigadas.read_workbook(source, "2026-10-22")


@pytest.mark.parametrize("row, message", [
    (event(None, "2026-09-24"), "identificador"),
    (event(1.5, "2026-09-24"), "identificador"),
    (event(1, None), "fecha"),
    (event(1, "2026-10-23"), "posterior al corte"),
    (event(1, "2026-09-24", canton=None), "cantón"),
])
def test_invalid_emergency_rows_cannot_silently_disappear(tmp_path, row, message):
    source = workbook(tmp_path, [row])
    with pytest.raises(ValueError, match=message):
        brigadas.read_workbook(source, "2026-10-22")


def test_failed_ingestion_preserves_canonical_file_and_historical_files(tmp_path):
    output = tmp_path / "brigadas_emergencia.json"
    output.write_text('{"brigadas": []}\n')
    source = workbook(tmp_path, [event(1, "2026-10-23")])
    with pytest.raises(ValueError):
        update(source, "2026-10-22", output)
    assert json.loads(output.read_text()) == {"brigadas": []}
    with pytest.raises(ValueError, match="históricas"):
        update(source, "2026-10-22", tmp_path / "seguimiento_enos_2026-10-27.json")


def test_older_source_cut_cannot_replace_complete_canonical_history(tmp_path):
    output = tmp_path / "brigadas_emergencia.json"
    recent = workbook(tmp_path, [event(1, "2026-09-24"), event(2, "2026-10-13")])
    update(recent, "2026-10-22", output)
    before = output.read_bytes()
    older = workbook(tmp_path, [event(1, "2026-09-24")])
    with pytest.raises(ValueError, match="anterior al de la base existente"):
        update(older, "2026-10-01", output)
    assert output.read_bytes() == before
    assert len(brigadas.load(output)["brigadas"]) == 2


def test_bundled_full_register_contains_previously_filtered_brigades():
    data = brigadas.load()
    assert len(data["brigadas"]) == 71
    assert (data["desde"], data["hasta"], data["corte"]) == ("2026-02-27", "2026-10-13", "2026-10-22")
    selected = [r for r in data["brigadas"] if "2026-08-28" <= r["fecha"] <= "2026-10-27"]
    assert {(r["id"], r["provincia"], r["canton"]) for r in selected} == {
        ("BRI-2929", "El Oro", "Pasaje"), ("BRI-2935", "Guayas", "Salitre"),
        ("BRI-2995", "Guayas", "Balao"),
    }
    assert data["control"]["duplicados_identicos"] == 0
