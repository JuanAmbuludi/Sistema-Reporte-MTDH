"""Province geometry used by every map in the interface and the reports."""
from src import geo
from src.data import load_data
from src.reports.charts import map_png


def test_all_reported_provinces_have_a_polygon():
    collection = geo.provinces(inset=False)
    codes = {f["properties"]["codigo"] for f in collection["features"]}
    assert codes == {f"{i:02d}" for i in range(1, 25)}
    data_codes = set(load_data().provincia_codigo) - {geo.NO_POLYGON}
    assert data_codes <= codes
    names = geo.names()
    assert names["23"] == "Santo Domingo de los Tsáchilas" and names["20"] == "Galápagos"


def test_galapagos_inset_moves_only_the_islands():
    real = geo.bounds(geo.provinces(inset=False), {geo.GALAPAGOS})
    inset = geo.bounds(geo.provinces(inset=True), {geo.GALAPAGOS})
    assert round(inset[0] - real[0], 3) == geo.GALAPAGOS_SHIFT
    assert geo.bounds(geo.provinces(inset=True), {"09"}) == geo.bounds(geo.provinces(inset=False), {"09"})


def test_outer_rings_are_clockwise_for_spherical_renderers():
    for feature in geo.provinces(inset=True)["features"]:
        for polygon in geo.polygons(feature):
            assert geo._signed_area(polygon[0]) < 0


def test_svg_and_png_maps_render():
    svg = geo.svg_map({"09": "#512F8D"}, selected={"17"})
    assert svg.startswith("<svg") and svg.count("<path") == 24 and "\n" not in svg
    png = map_png({"09": 10.0, "17": 5.0})
    assert png.startswith(b"\x89PNG")
