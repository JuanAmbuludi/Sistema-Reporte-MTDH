"""Regression gates for different source grains, repeated budgets and provenance."""
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src import etl_actualizacion as update
from src.data import aggregate, load_data, summarize
from src.etl import build_dataset
from src.institutional import financial_programs

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/source"
DATA = ROOT / "data/processed"


@pytest.fixture(scope="module")
def legacy(tmp_path_factory):
    target = tmp_path_factory.mktemp("legacy")
    build_dataset(SOURCE / "Acumulado_VIS_VIE", target, "2026-09", period_source="Prueba de conciliación")
    return target


def test_compatible_names_and_prior_accumulation_are_preserved(legacy):
    old = pq.read_table(legacy / "indicadores.parquet")
    new = pq.read_table(DATA / "indicadores.parquet")
    assert set(old.column_names) <= set(new.column_names)
    before, after = old.to_pandas(), new.to_pandas()
    keys = ["periodo", "programa_id", "provincia_codigo"]
    merged = before.merge(after, on=keys, validate="one_to_one", suffixes=("_old", "_new"))
    assert len(merged) == 296
    assert merged.monto_anterior_old.equals(merged.monto_anterior_new)
    assert all(after.monto_gobierno == after.monto_anterior + after.presupuesto_ejecutado)
    assert new.schema.field("presupuesto_codificado").type.scale == 6
    assert new.schema.metadata[b"mtdh.schema_version"] == b"1.1.0"
    assert (legacy / "historico_referencia.parquet").read_bytes() == (DATA / "historico_referencia.parquet").read_bytes()


def test_parish_users_reconcile_without_multiplying_budget_by_modalities():
    people = pd.read_parquet(DATA / "cobertura_territorial.parquet")
    budget = pd.read_parquet(DATA / "presupuesto_territorial.parquet")
    keys = ["programa_id", "parroquia_codigo"]
    users = people.groupby(keys).usuarios.sum().sort_index()
    controls = budget.set_index(keys).usuarios_control.sort_index()
    assert len(people) == 10849 and len(budget) == 9299
    assert users.equals(controls.rename("usuarios"))
    assert not budget.duplicated(keys).any()
    assert people.parroquia_codigo.str.len().eq(6).all()
    assert sum(people.unidades.dropna()) == 11215
    assert sum(budget.presupuesto_ejecutado) == sum(pq.read_table(DATA / "indicadores.parquet").column("presupuesto_ejecutado").to_pylist())


def test_distributed_codified_and_weighted_percentage():
    frame = load_data()
    stats = summarize(frame)
    assert stats["presupuesto_codificado"] == pytest.approx(1781225672.52, abs=0.01)
    assert stats["porcentaje_ejecucion"] == pytest.approx(66.2466421553)
    manifest = json.loads((DATA / "manifest.json").read_text())
    assert manifest["control_calidad"]["codificado_suma_columna_original_no_utilizable"] > 10e9
    assert manifest["control_calidad"]["grupos_distribucion_validados"] == 160
    by_section = aggregate(frame, "seccion")
    assert by_section.presupuesto_codificado.sum() == pytest.approx(stats["presupuesto_codificado"])
    for row in by_section.itertuples():
        assert row.porcentaje_ejecucion == pytest.approx(row.presupuesto_ejecutado / row.presupuesto_codificado * 100)


def test_missing_codified_is_not_a_partial_total():
    frame = load_data().iloc[:2].copy()
    frame.iloc[0, frame.columns.get_loc("presupuesto_codificado")] = float("nan")
    assert summarize(frame)["presupuesto_codificado"] is None
    assert summarize(frame)["porcentaje_ejecucion"] is None
    assert aggregate(frame, "seccion").porcentaje_ejecucion.isna().all()


def test_financial_universe_duplicate_flags_and_explicit_cut():
    frame = pd.read_parquet(DATA / "presupuesto_institucional.parquet")
    manifest = json.loads((DATA / "manifest_financiero.json").read_text())
    assert len(frame) == 5206 and frame.fila_identica_previa.sum() == 11
    assert sum(frame.presupuesto_codificado) == Decimal("2137233099.360000")
    assert sum(frame.presupuesto_ejecutado) == Decimal("978122861.160000")
    assert sum(frame.loc[frame.fila_identica_previa, "presupuesto_codificado"]) == Decimal("45570")
    assert manifest["periodo"] == "2026-09-01" and "confirmado" in manifest["periodo_origen"]
    assert manifest["totales"]["porcentaje_ejecucion"] == pytest.approx(45.7658484446)
    grouped = financial_programs(frame.assign(**{k: frame[k].astype(float) for k in
                                 ["presupuesto_codificado", "presupuesto_ejecutado", "presupuesto_certificado"]}))
    assert grouped.presupuesto_ejecutado.sum() == pytest.approx(978122861.16)


@pytest.mark.parametrize("failure", ["missing_budget_parish", "repeated_coverage", "wrong_cut", "invalid_distribution"])
def test_inconsistent_sources_fail_instead_of_being_filled_with_zeros(legacy, tmp_path, monkeypatch, failure):
    target = tmp_path / "stage"
    shutil.copytree(legacy, target)
    original = update.read_rows

    def corrupt(path, *args, **kwargs):
        rows = original(path, *args, **kwargs)
        if path.name.startswith("Presupuesto"):
            if failure == "missing_budget_parish":
                rows.pop()
            if failure == "invalid_distribution":
                next(r for r in rows if r["vice"] == "VIS")["distribucion"] = 0.99
        else:
            if failure == "repeated_coverage":
                rows.append(dict(rows[0]))
            if failure == "wrong_cut":
                next(r for r in rows if r["fecha"])["fecha"] = "2026-08-31"
        return rows

    monkeypatch.setattr(update, "read_rows", corrupt)
    original_bytes = (target / "indicadores.parquet").read_bytes()
    with pytest.raises(ValueError):
        update.refresh_vis_vie(target, SOURCE / "Usuarios_vis_vie.parquet", SOURCE / "Presupuesto_vis_vie.parquet",
                               "2026-09", period_source="Prueba")
    assert (target / "indicadores.parquet").read_bytes() == original_bytes


def test_all_sources_rebuild_together_and_validation_failure_preserves_delivered_files(tmp_path):
    manifest = json.loads((DATA / "manifest_laboral.json").read_text())
    command = [sys.executable, str(ROOT / "scripts/build_data.py"), "--config", str(ROOT / "config/actualizacion_datos.json"),
               "--output", str(tmp_path), "--incluir-laboral", "--laboral-evidencia", str(DATA / manifest["evidencia"])]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for name in ["indicadores.parquet", "historico_referencia.parquet",
                 "cobertura_territorial.parquet", "presupuesto_territorial.parquet", "presupuesto_institucional.parquet"]:
        assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes(), name
    # Replay the dated original SUT extraction, not the subsequently updated SGDE stock.
    assert (tmp_path / "gestion_laboral.parquet").read_bytes() == (DATA / manifest["copia_del_corte"]).read_bytes()
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.*")}
    failed = subprocess.run(command + ["--financiero", str(tmp_path / "missing.xlsx")], capture_output=True, text=True)
    assert failed.returncode == 1 and "Actualización no completada" in failed.stderr
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.*")}


def test_financial_cut_requires_provenance(tmp_path):
    with pytest.raises(ValueError, match="origen del corte"):
        update.build_financial(SOURCE / "Base_de_datos_fin.parquet", tmp_path, "2026-09", "")
