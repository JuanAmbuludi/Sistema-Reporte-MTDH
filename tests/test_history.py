"""Guardrails for history, monetary grains, partial sources and public outputs."""
from decimal import Decimal
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.historicos import upsert_partitions, national_coverage, coverage_tables, incentives, source_rank
from src.sgde_scraper import contracts
from src.gestion_laboral import _source_date, load_labour, summary
from scripts.update_history import update, expected_periods

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT/"data/series"


def test_replace_month_is_idempotent_and_retains_other_months():
    before = pd.DataFrame({"periodo": ["2026-01", "2026-02", "2026-02"], "grupo": ["A","A","B"], "valor": [10,20,30]})
    incoming = pd.DataFrame({"periodo": ["2026-02", "2027-01"], "grupo": ["A","A"], "valor": [25,50]})
    options = dict(keys=["periodo","grupo"], partitions=["periodo"])
    once = upsert_partitions(before, incoming, **options)
    twice = upsert_partitions(once, incoming, **options)
    pd.testing.assert_frame_equal(once, twice)
    assert once.valor.tolist() == [10,25,50]  # Corrected February removes its obsolete group B.
    with pytest.raises(ValueError, match="Claves"):
        upsert_partitions(before, pd.concat([incoming,incoming]), **options)
    cleared = upsert_partitions(once, incoming.iloc[:0], replace_partitions=[("2026-02",)], **options)
    assert cleared.periodo.tolist() == ["2026-01", "2027-01"]


def test_period_year_month_conflict_is_rejected(tmp_path):
    file = tmp_path/"bad.parquet"
    pd.DataFrame([dict(periodo="2026-01", anio=2026, mes=2, bono="BDH", beneficiarios_unicos=5, registros=5)]).to_parquet(file)
    with pytest.raises(ValueError, match="no concilian"):
        national_coverage(file,"VIE")


def test_gap_inventory_accepts_future_years_without_fixed_cut():
    inventory = [{"base": "cobertura_vis.parquet", "periodos": ["2026-12", "2027-02"]},
                 {"base": "bonos_vie.parquet", "periodos": ["2027-03"]}]
    expected = expected_periods(inventory)
    assert len(expected) == 15 and expected[0] == "2026-01" and expected[-1] == "2027-03"


def test_parquet_execution_preserves_amount_and_province_code(tmp_path):
    from datetime import date
    from src.etl import join_execution
    path = tmp_path/"ejecucion.parquet"
    pd.DataFrame([dict(periodo="2026-09", programa_id="BDH", provincia_codigo="01",
                       presupuesto_ejecutado=Decimal("1234.56"))]).to_parquet(path)
    rows = [dict(programa_id="BDH", provincia_codigo="01")]
    join_execution(rows, path, date(2026, 9, 1))
    assert rows[0]["presupuesto_ejecutado"] == Decimal("1234.56")


def test_repeated_bank_file_is_not_a_second_payment_and_rejection_is_excluded(tmp_path):
    common = dict(cedula="synthetic-person", valor="400.00", fecha_acreditacion="01/07/2026 20:00:00",
                  numero_referencia="synthetic-reference", observacion="PAGO1", grupo_carga="1 JOVENES EN ACCION",
                  nombre_archivo="JOVENES_EN_ACCION_3ETAPA__MIT.csv", codigo_rechazo="1")
    rows = [common, {**common,"nombre_archivo":"JOVENES_EN_ACCION_3ETAPA__MINEDEC.csv"},
            {**common,"cedula":"synthetic-rejected", "codigo_rechazo":"16"}]
    path = tmp_path/"bank.parquet"
    pd.DataFrame(rows).to_parquet(path)
    result, audit = incentives(path)
    assert len(result)==1 and result.iloc[0].beneficiarios==1
    assert result.iloc[0].monto_acreditado==Decimal("400")
    assert audit["repeticiones_transaccion_eliminadas"]==1
    assert audit["respuestas_no_acreditadas"]==1


def test_failed_batch_does_not_modify_delivered_data(tmp_path):
    data, inputs = tmp_path/"data", tmp_path/"inputs"
    data.mkdir(); inputs.mkdir()
    (data/"sentinel.parquet").write_bytes(b"unchanged")
    pd.DataFrame([dict(periodo="2026-01", anio=2026, mes=9, bono="BDH", beneficiarios_unicos=1, registros=1)]).to_parquet(inputs/"VIE_beneficiarios_bonos_2026.parquet")
    with pytest.raises(ValueError):
        update(data, inputs)
    assert list(data.iterdir())==[data/"sentinel.parquet"]
    assert (data/"sentinel.parquet").read_bytes()==b"unchanged"


def test_approved_budget_shared_allocation_and_monthly_sums():
    monthly = pd.read_parquet(SERIES/"presupuesto_social_mensual.parquet")
    annual = pd.read_parquet(SERIES/"presupuesto_social_asignado.parquet")
    audit = json.loads((SERIES/"actualizacion.json").read_text())["controles"]["presupuesto_aprobado"]
    cut = audit["periodo_corte"]
    assignments = annual.loc[annual.periodo.eq(cut)]
    assert assignments.grupo_presupuestario.tolist().count("BDH_BDHV")==1
    assert assignments.presupuesto_aprobado.sum()==Decimal(audit["presupuesto_aprobado"])
    current = monthly.loc[monthly.anio.eq(int(cut[:4])) & monthly.periodo.le(cut)]
    assert current.devengado_mes.sum()==Decimal(audit["devengado_acumulado"])
    assert not current.duplicated(["periodo", "programa_id"]).any()
    expected = current.sort_values("periodo").groupby("programa_id").devengado_mes.sum()
    observed = current.loc[current.periodo.eq(cut)].set_index("programa_id").devengado_acumulado
    assert expected.sort_index().equals(observed.sort_index().rename("devengado_mes"))


def test_national_coverage_is_not_summed_into_territorial_data():
    vis = pd.read_parquet(SERIES/"cobertura_vis.parquet")
    vie = pd.read_parquet(SERIES/"bonos_vie.parquet")
    assert set(f"2026-{m:02d}" for m in range(1,10)) <= set(vis.periodo)
    assert set(f"2026-{m:02d}" for m in range(1,10)) <= set(vie.periodo)
    assert not vis.duplicated(["periodo","servicio","modalidad"]).any()
    assert "provincia" not in vis and "provincia" not in vie
    assert (vie.beneficiarios_unicos <= vie.registros).all()
    orphans = pd.read_parquet(SERIES/"beneficiarios_orfandad.parquet")
    assert (orphans.beneficiarios <= orphans.registros).all()


def test_orphan_source_missing_month_is_not_filled_with_zero(tmp_path):
    from src.historicos import orphan_beneficiaries
    path = tmp_path/"beneficiarios.csv"
    path.write_text("AÑO,MES,TOTAL_REGISTROS,BENEFICIARIOS_DISTINTOS\n2026,5,3,2\n2026,7,6,3\n")
    result = orphan_beneficiaries(path)
    assert result.periodo.tolist() == ["2026-05", "2026-07"]


def test_laboral_decoded_tables_reconcile_and_do_not_invent_parishes():
    base = pd.read_parquet(SERIES/"laboral/contratos_base.parquet")
    for date, current in base.groupby("fecha_corte"):
        control = current.groupby(["estado","provincia"]).contratos.sum().sort_index()
        for dim in ["canton","rama","tipo","etnia","act"]:
            table = pd.read_parquet(SERIES/f"laboral/contratos_{dim}.parquet")
            observed = table.loc[table.fecha_corte.eq(date)].groupby(["estado","provincia"]).contratos.sum().sort_index()
            assert observed.equals(control)
            assert "parroquia" not in table
    # Independent observation dates stay independent in the UI and reports.
    info = summary(load_labour())
    assert info["months"] and info["stock"]
    if not info["same_cut"]:
        assert info["cohorts_share"] is None
    assert _source_date("2026-09-18").isoformat()=="2026-09-18"


def test_output_is_aggregate_parquet_with_small_files():
    prohibited = {"cedula","nombres_beneficiario","nombre","telefono","cuenta_beneficiario","numero_referencia"}
    for path in SERIES.rglob("*.parquet"):
        file = pq.ParquetFile(path)
        assert not (set(file.schema_arrow.names) & prohibited), path
        assert file.schema_arrow.metadata[b"mtdh.grain"]
        assert {"periodo","anio","mes","mes_nombre"} <= set(file.schema_arrow.names), path


def test_version_selection_prefers_complete_september_over_august():
    assert source_rank("Base_Antr_picos_2026__9._Septiembre.csv")[:2]==("GENERAL",2026)
    assert source_rank("Base_Antr_picos_2026__9._Septiembre.csv")[2:] > source_rank("Base_Antr_picos_2026_corte_a_31_Agosto_2026.csv")[2:]


def test_territorial_levels_reconcile_to_national_without_multiplying_totals():
    for name, dims in [("cobertura_vis", ["servicio", "modalidad"]), ("bonos_vie", ["bono"])]:
        national = pd.read_parquet(SERIES/f"{name}.parquet")
        territorial = pd.read_parquet(SERIES/f"{name}_territorial.parquet")
        keys = ["periodo", *dims]
        expected = national.set_index(keys).registros.sort_index()
        assert set(territorial.nivel_territorial) == {"Provincia", "Cantón", "Parroquia"}
        for level, block in territorial.groupby("nivel_territorial"):
            assert block.groupby(keys).registros.sum().sort_index().equals(expected), level
        assert not territorial.duplicated(["periodo", "nivel_territorial", "codigo_territorio", "provincia", "canton", "parroquia", *dims]).any()


def test_detailed_cdi_and_conflicting_territorial_labels_are_preserved():
    vis = pd.read_parquet(SERIES/"cobertura_vis.parquet")
    assert {"CDI DIRECTOS", "CDI CONVENIOS", "EMBLEMATICO"} <= set(vis.modalidad)
    vie = pd.read_parquet(SERIES/"bonos_vie_territorial.parquet")
    conflict = vie.loc[vie.periodo.eq("2026-01") & vie.nivel_territorial.eq("Provincia") & vie.codigo_territorio.eq("14")]
    assert {"MORONA SANTIAGO", "CHIMBORAZO"} <= set(conflict.provincia)
    assert conflict.codigo_ambiguo.all()


def test_territorial_mismatch_is_rejected(tmp_path):
    rows=[]
    for level, width in [("Nacional",0),("Provincia",2),("Cantón",4),("Parroquia",6)]:
        rows.append(dict(periodo="2026-09", anio=2026, mes=9, nivel_territorial=level,
            codigo_provincia="01" if width>=2 else None, provincia="AZUAY" if width>=2 else None,
            codigo_canton="0101" if width>=4 else None, canton="CUENCA" if width>=4 else None,
            codigo_parroquia="010101" if width>=6 else None, parroquia="BELLAVISTA" if width>=6 else None,
            bono="BDH", beneficiarios_unicos=3, registros=4 if level=="Cantón" else 3))
    path=tmp_path/"mismatch.parquet"
    pd.DataFrame(rows).to_parquet(path)
    with pytest.raises(ValueError, match="no concilian"):
        coverage_tables(path,"VIE")
