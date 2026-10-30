"""Geometry of every map in the interface and the reports: parishes, cantons, provinces and zones."""
import random

import pytest

from src import geo, territory
from src.data import load_data, load_territory
from src.reports.charts import map_png


@pytest.fixture(scope="module")
def parishes():
    return load_territory()


def test_every_province_and_zone_has_a_shape_with_its_official_name():
    provinces = geo.features("provincia")
    assert set(provinces) == {f"{i:02d}" for i in range(1, 25)} | {geo.NO_POLYGON}
    assert set(load_data().provincia_codigo) <= set(provinces)
    assert provinces["23"]["name"] == "Santo Domingo de los Tsáchilas" and provinces["20"]["name"] == "Galápagos"
    assert set(geo.features("zona")) == {f"Z{i}" for i in range(1, 10)}
    assert len(geo.features("parroquia")) == 1040 and len(geo.features("canton")) == 224


def test_layers_follow_the_current_division_of_the_data():
    cantons = geo.features("canton")
    # La Concordia belongs to Santo Domingo de los Tsáchilas, as in the data (the 2015 cartography had it in Esmeraldas).
    assert cantons["2302"]["province"] == "23" and cantons["2302"]["zone"] == "Z4"
    assert cantons["0901"]["zone"] == "Z8" and cantons["1701"]["zone"] == "Z9" and cantons["1702"]["zone"] == "Z2"
    assert geo.features("parroquia")["080850"]["province"] == "23"


def test_every_parish_of_the_data_finds_its_polygon(parishes):
    index = territory.polygon_index(parishes)
    codes = set(parishes.parroquia_codigo)
    assert codes - set(index) == {"900551", "900651", "900751", "900851"}, "Solo las zonas en estudio quedan fuera del mapa"
    assert index["010101"] == "010150", "Las parroquias urbanas se dibujan en su cabecera cantonal"
    assert index["230250"] == "080850" and index["141350"] == "140157" and index["070256"] == "070250"
    values, members = territory.polygon_values(parishes, "usuarios")
    mapped = parishes.loc[parishes.parroquia_codigo.isin(index), "usuarios"].sum()
    assert sum(values.values()) == mapped
    assert len(members["090150"]) > 1


def test_dissolving_any_group_of_parishes_closes_its_rings():
    refs = geo._refs("parroquia")
    codes = sorted(refs)
    for seed in range(25):
        rnd = random.Random(seed)
        group = rnd.sample(codes, rnd.randint(2, 400))
        rings = geo.dissolve([refs[c] for c in group])
        assert rings and all(len(r) >= 1 for r in rings)


def test_galapagos_inset_moves_only_the_islands():
    real = geo.bounds("provincia", {geo.GALAPAGOS}, inset=False)
    inset = geo.bounds("provincia", {geo.GALAPAGOS}, inset=True)
    assert round(inset[0] - real[0], 3) == geo.GALAPAGOS_SHIFT
    assert geo.bounds("provincia", {"09"}, inset=True) == geo.bounds("provincia", {"09"}, inset=False)


def test_simplification_levels_keep_more_detail_when_zooming():
    coarse = sum(len(r) for r in geo.rings("provincia", "17", level=3))
    fine = sum(len(r) for r in geo.rings("provincia", "17", level=1))
    assert fine > coarse > 20


def test_svg_maps_render_on_one_line():
    provinces = geo.svg_map({"09": "#512F8D"}, selected={"17"})
    assert provinces.startswith("<svg") and provinces.count('<path class="ec-unit') == 25 and "\n" not in provinces
    assert 'class="ec-unit is-selected" data-code="17"' in provinces
    fills = {code: "#8F75CF" if i % 2 else "#D7CEF5" for i, code in enumerate(geo.features("parroquia"))}
    mosaic = geo.svg_map(fills, layer="parroquia", regions={"09": "Guayas\n312.265 beneficiarios"})
    assert mosaic.count('<path class="ec-region') == 25 and "<title>Guayas\n312.265 beneficiarios</title>" in mosaic
    assert len(mosaic) < 180_000, "El mapa nacional parroquial se mantiene liviano"
    zoom = geo.svg_map(fills, layer="parroquia", focus={"09"}, titles={"090150": "Guayaquil"})
    assert "clipPath" in zoom and "ec-locator" in zoom and "<title>Guayaquil</title>" in zoom
    assert zoom.count('<path class="ec-unit') == sum(1 for p in geo.features("parroquia").values() if p["province"] == "09")
    zones = geo.svg_map({"Z1": "#512F8D"}, layer="zona", selected={"Z8"})
    assert zones.count('<path class="ec-unit') == 9 and 'data-code="Z8"' in zones


def test_report_maps_render_for_every_layer():
    assert map_png({"09": 10.0, "17": 5.0}).startswith(b"\x89PNG")
    assert map_png({"090150": 10.0}, layer="parroquia", focus={"09"}, mode="night", legend=False).startswith(b"\x89PNG")
    assert map_png({"Z1": 40.0, "Z5": 38.0}, layer="zona", rate=True).startswith(b"\x89PNG")
