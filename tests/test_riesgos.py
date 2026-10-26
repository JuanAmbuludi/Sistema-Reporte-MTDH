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
