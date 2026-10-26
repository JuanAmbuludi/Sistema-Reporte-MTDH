"""Units, threat categories and filter consistency for the risks inventory."""
import pandas as pd
import pytest

from src import riesgos


def test_inventory_is_unique_and_reconciles_to_source():
    data = pd.read_parquet(riesgos.DATA_PATH)
    cut = riesgos.select(data, "2026-09")
    assert riesgos.count_units(cut) == 9860
    assert not {"codigo_ua", "nombre", "modalidad", "canton", "parroquia"} & set(data.columns)
    assert not data.drop(columns="unidades").duplicated().any()
    assert riesgos.count_units(riesgos.exposed(cut)) == 9460
    assert riesgos.count_units(riesgos.exposed(cut, levels=("Alta", "Muy alta"))) == 6788
    assert riesgos.count_units(riesgos.exposed(cut, "susc_inundacion")) == 2216
    # The workbook summary reports 6,220 rows; nine repeated UA codes must not inflate the inventory.
    assert riesgos.count_units(cut.loc[cut[["susc_inundacion", "susc_movimientos_masa"]].isin(riesgos.LEVELS).any(axis=1)]) == 6211


def test_filters_preserve_period_province_service_and_threat():
    data = pd.read_parquet(riesgos.DATA_PATH)
    scoped = riesgos.select(data, "2026-09", ["09"], ["DII"])
    assert set(scoped.provincia_codigo) == {"09"}
    assert set(scoped.programa_id) == {"DII"}
    selected = riesgos.exposed(scoped, "susc_inundacion", ("Alta",))
    assert not selected.empty
    assert selected.susc_inundacion.eq("Alta").all()
    counts = riesgos.threat_counts(selected, "susc_inundacion", ("Alta",))
    assert counts.unidades.sum() == riesgos.count_units(selected)
    assert riesgos.detail_counts(selected, "susc_inundacion", ("Alta",)).unidades.sum() == riesgos.count_units(selected)
    assert riesgos.select(data, "2026-08").empty
    assert riesgos.select(data, "2026-09", ["99"]).empty


def test_categories_are_not_damage_and_missing_is_not_zero_risk():
    data = pd.read_parquet(riesgos.DATA_PATH)
    cut = riesgos.select(data, "2026-09")
    unclassified = cut.loc[cut.susceptibilidad_maxima.eq("Sin categoría reportada")]
    assert riesgos.count_units(unclassified) == 400
    assert riesgos.exposed(unclassified).empty
    assert riesgos.exposed(cut, levels=()).empty
    for key in riesgos.THREATS:
        assert set(cut[key]) <= set(riesgos.RANK)
        counts = riesgos.threat_counts(cut, key)
        assert counts.unidades.sum() == riesgos.count_units(riesgos.exposed(cut, key))


def test_repeated_codes_keep_modalities_and_highest_reported_category():
    row = {"co_siimdh": "123", "nombre": "Unidad", "servicio": "DESARROLLO INFANTIL INTEGRAL",
           "mod": "Modalidad A", "dpa_prov": "01", "dpa_despro": "AZUAY", "dpa_can": "0101",
           "dpa_descan": "CUENCA", "dpa_par": "010101", "dpa_despar": "BELLAVISTA",
           **{key: "-" for key in riesgos.THREATS}}
    source = pd.DataFrame([row, {**row, "mod": "Modalidad B", "susc_inundacion": "Alta"}])
    clean = riesgos.normalize(source, "2026-09")
    assert len(clean) == 1
    assert clean.iloc[0].modalidad == "Modalidad A / Modalidad B"
    assert clean.iloc[0].susc_inundacion == "Alta"
    source.loc[1, "dpa_prov"] = "02"
    with pytest.raises(ValueError, match="valores distintos"):
        riesgos.normalize(source, "2026-09")


def test_unit_detail_reconciles_with_aggregates_and_filters():
    detail = pd.read_parquet(riesgos.DETAIL_PATH)
    totals = pd.read_parquet(riesgos.DATA_PATH)
    assert list(detail.columns) == riesgos.DETAIL_FIELDS
    assert not detail.duplicated(["periodo_id", "codigo_ua"]).any()
    assert detail.codigo_ua.ne("").all() and detail.nombre.ne("").all()
    pd.testing.assert_frame_equal(riesgos.aggregate_inventory(detail), totals)
    for threat in (None, *riesgos.THREATS):
        for levels in (riesgos.LEVELS, ("Alta",), ("Muy alta",)):
            units = riesgos.exposed(riesgos.select(detail, "2026-09", ["09"], ["DII"]), threat, levels)
            aggregate = riesgos.exposed(riesgos.select(totals, "2026-09", ["09"], ["DII"]), threat, levels)
            assert len(units) == riesgos.count_units(aggregate)


def test_multihazard_matches_source_matrix_and_every_province_in_supplied_table():
    matrix = riesgos.select(pd.read_parquet(riesgos.MATRIX_PATH), "2026-09")
    assert riesgos.count_records(matrix) == 9869
    assert not {"codigo_ua", "nombre", "modalidad", "canton", "parroquia"} & set(matrix)
    multi = riesgos.multihazard(matrix)
    assert riesgos.count_records(multi) == 6220
    expected = dict(zip([f"{i:02}" for i in range(1, 25)],
                        [355, 124, 244, 97, 185, 285, 205, 338, 950, 199, 439, 340,
                         854, 249, 160, 97, 372, 182, 48, 0, 82, 91, 152, 172]))
    actual = multi.groupby("provincia_codigo").registros.sum().reindex(expected, fill_value=0).to_dict()
    assert actual == expected
    filtered = riesgos.exposed(riesgos.select(matrix, "2026-09", ["09"], ["DII"]), "susc_inundacion", ("Alta",))
    assert riesgos.count_records(riesgos.multihazard(filtered, ("Alta",))) == 287
    assert riesgos.multihazard(matrix, ()).empty


def test_matrix_preserves_source_rows_and_counts_union_once():
    row = {"co_siimdh": "123", "nombre": "Unidad", "servicio": "DESARROLLO INFANTIL INTEGRAL",
           "mod": "Modalidad A", "dpa_prov": "01", "dpa_despro": "AZUAY", "dpa_can": "0101",
           "dpa_descan": "CUENCA", "dpa_par": "010101", "dpa_despar": "BELLAVISTA",
           **{key: "-" for key in riesgos.THREATS}}
    source = pd.DataFrame([{**row, "susc_inundacion": "Alta", "susc_movimientos_masa": "Media"}, row])
    matrix = riesgos.aggregate_matrix(riesgos.normalize(source, "2026-09", deduplicate=False))
    assert riesgos.count_records(matrix) == 2
    assert riesgos.count_records(riesgos.multihazard(matrix)) == 1
    assert riesgos.multihazard(matrix, ("Muy alta",)).empty
