"""Historical ingestion preserves temporal uncertainty, identity and privacy."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import preparar_alertas_historicas as ingest


def test_dates_accept_explicit_formats_and_do_not_repair_typo_or_multiple_years():
    assert ingest.date_span("17.01.2024")["fecha"] == "2024-01-17"
    assert ingest.date_span("26-09-2024")["fecha"] == "2024-09-26"
    assert ingest.date_span("18 de diciembre de 2024")["fecha"] == "2024-12-18"
    for value in ("03/01/224", "31/02/2024", "2024-02-31", "99 de enero de 2024", "01/01/2021\n01/01/2022", "2030-01-01"):
        with pytest.raises(ingest.UncertainDate):
            ingest.date_span(value, "1.enero-febrero", 2024)
    assert "PRIVATE" not in json.dumps(ingest.date_span("PRIVATE NAME 17/01/2024"))


def test_report_month_and_explicit_range_retain_bounds_and_date_basis():
    month = ingest.date_span(None, "3.abril", 2024)
    assert (month["fecha"], month["fecha_hasta"]) == ("2024-04-01", "2024-04-30")
    assert (month["fecha_precision"], month["fecha_tipo"]) == ("mes_reporte", "reporte")
    span = ingest.date_span("15/07/2024\n 16/07/2024")
    assert (span["fecha"], span["fecha_hasta"], span["fecha_precision"]) == (
        "2024-07-15", "2024-07-16", "intervalo")
    with pytest.raises(ingest.UncertainDate):
        ingest.date_span(None, "1.enero-febrero", 2024)


def row(number, **changes):
    value = {"No.": number, "ZONA": "Zona 5", "DISTRITO": "Balao", "PROVINCIA": "Guayas", "CANTÓN": "Balao",
        "FECHA DEL SUCESO": "17.01.2024", "mes REPORTE": "1.enero-febrero", "SERVICIO": "Emergencia",
        "ALERTA DETECTADA (Resumen)": "PRIVATE NARRATIVE", "DETALLES": "PRIVATE DETAILS",
        "Nro. APROXIMADO DE PERSONAS AFECTADAS": "15 familias (70 personas)",
        "SE AFECTA LA PRESTACIÓN DE SERVICIOS MIES": "SI", "SOLVENTADO (SI/NO /EN PROCESO)": "En proceso",
        "ACCIONES REALIZADAS (Enumere)": "PRIVATE FOLLOWUP", "ACCIONES PENDIENTES (Enumere)": "PRIVATE TASK",
        "FUNCIONARIO A CARGO DEL LEVANTAMIENTO": "PRIVATE NAME", "TELÉFONO DE CONTACTO": "PRIVATE PHONE"}
    value.update(changes)
    return value


def write_matrix(path, rows):
    pd.DataFrame(rows).to_excel(path, sheet_name="Hoja1", startrow=3, index=False)


def test_followups_collapse_once_with_stable_id_and_no_personal_fields(tmp_path):
    path = tmp_path / "alertas2024.xlsx"
    first = row(1)
    second = row(2, **{"ACCIONES REALIZADAS (Enumere)": "PRIVATE UPDATE", "SOLVENTADO (SI/NO /EN PROCESO)": "Solventado"})
    write_matrix(path, [second, first])
    rows, metadata = ingest.matrix_2024(path)
    assert len(rows) == 1
    assert (rows[0]["codigo"], rows[0]["estado"]) == ("MAT-2024-0001", "Resuelto")
    assert rows[0]["afectados_fuente"] is None  # families never silently become people
    assert metadata["seguimientos_repetidos"] == [{"codigo": "MAT-2024-0002", "conservado": "MAT-2024-0001"}]
    assert "PRIVATE" not in json.dumps({"rows": rows, "metadata": metadata})
    assert set(rows[0]) <= ingest.FIELDS
    write_matrix(path, [first, second])
    assert ingest.matrix_2024(path)[0] == rows


def test_different_cases_in_same_place_and_day_remain_separate(tmp_path):
    path = tmp_path / "alertas2024.xlsx"
    write_matrix(path, [row(1), row(2, **{"DETALLES": "DIFFERENT CASE"})])
    records, metadata = ingest.matrix_2024(path)
    assert len(records) == 2 and metadata["seguimientos_repetidos"] == []


def test_2023_planned_dates_never_become_event_dates(tmp_path):
    path = tmp_path / "planes2023.xlsx"
    pd.DataFrame([{"Nro.": 1, "SERVICIO": "DISCAPACIDADES", "CUMPLIMIENTO\nSI/NO": "SI",
                   "FECHA POSIBLE DE EJECUCIÓN": pd.Timestamp("2023-12-01"),
                   "NOMBRE DEL RESPONSABLE": "PRIVATE NAME", "NUDO CRÍTICO O PROBLEMA": "PRIVATE NARRATIVE"}]).to_excel(
        path, sheet_name="Hoja1", startrow=2, index=False)
    aggregate, metadata = ingest.antecedent_2023(path)
    assert aggregate["registros"] == 1 and metadata["alertas_fechadas"] == 0
    assert "2023-12-01" not in json.dumps(aggregate) and "PRIVATE" not in json.dumps(aggregate)


def test_shipped_archive_source_reconciliation_and_date_quality():
    data = json.loads(ingest.OUTPUT.read_text(encoding="utf-8"))
    records = data["alertas"]
    assert len(records) == len({r["codigo"] for r in records}) == 1773
    source = next(s for s in data["fuentes"] if s["anio"] == 2024)
    assert source["registros_fuente"] == 232
    assert len(source["seguimientos_repetidos"]) == 6
    assert len(source["excluidos_fecha"]) == 3
    assert source["precision_fecha"] == {"dia": 207, "intervalo": 1, "mes_reporte": 15}
    assert data["antecedentes"][0]["registros"] == 572
    assert data["control"]["ya_presentes_en_operativo"] == 1550
    assert data["control"]["nuevas_alertas"] == 223
    assert all(set(r) <= ingest.FIELDS for r in records)
    assert not any(r["fecha"].startswith("2023") for r in records)
    assert all(r["fecha"] <= r["fecha_hasta"] <= data["corte"] for r in records)
