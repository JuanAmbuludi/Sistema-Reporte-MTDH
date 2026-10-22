"""Ecuador province geometry shared by the interface maps and the report maps.

Boundaries: Natural Earth 1:10m Admin-1 (public domain), simplified with a
topology-preserving method.  Province codes follow the INEC two-digit codes used
by the data model.  ``Zona en estudio`` (code 90) has no polygon and is always
reported beside the map, never drawn.

The Galápagos islands are shown as an inset: their geometry is moved east so
the mainland keeps a legible size.  Every map labels that inset explicitly.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEOJSON_PATH = ROOT / "assets" / "geo" / "ecuador_provincias.geojson"
GALAPAGOS = "20"
NO_POLYGON = "90"
GALAPAGOS_SHIFT = 7.5  # degrees of longitude, inset only


@lru_cache(maxsize=1)
def _raw() -> dict:
    return json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))


def _shift(coords, dx: float):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0] + dx, 4), coords[1]]
    return [_shift(c, dx) for c in coords]


def _signed_area(ring) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])) / 2


def _rewind(polygon):
    """Spherical renderers (d3-geo, Plotly) need clockwise outer rings."""
    out = []
    for index, ring in enumerate(polygon):
        clockwise = _signed_area(ring) < 0
        wants_clockwise = index == 0
        out.append(ring if clockwise == wants_clockwise else ring[::-1])
    return out


@lru_cache(maxsize=2)
def _provinces(inset: bool) -> str:
    data = deepcopy(_raw())
    for feature in data["features"]:
        geometry = feature["geometry"]
        if inset and feature["properties"]["codigo"] == GALAPAGOS:
            geometry["coordinates"] = _shift(geometry["coordinates"], GALAPAGOS_SHIFT)
        if geometry["type"] == "Polygon":
            geometry["coordinates"] = _rewind(geometry["coordinates"])
        else:
            geometry["coordinates"] = [_rewind(p) for p in geometry["coordinates"]]
    return json.dumps(data, ensure_ascii=False)


def provinces(inset: bool = True) -> dict:
    """GeoJSON FeatureCollection keyed by ``properties.codigo`` (d3 winding)."""
    return json.loads(_provinces(inset))


def names() -> dict[str, str]:
    return {f["properties"]["codigo"]: f["properties"]["nombre"] for f in _raw()["features"]}


def polygons(feature: dict) -> list[list[list[list[float]]]]:
    geometry = feature["geometry"]
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def bounds(collection: dict, codes: set[str] | None = None) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for feature in collection["features"]:
        if codes and feature["properties"]["codigo"] not in codes:
            continue
        for polygon in polygons(feature):
            for x, y in polygon[0]:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _ring_area_centroid(ring):
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    area *= 0.5
    if abs(area) < 1e-12:
        return 0.0, ring[0][0], ring[0][1]
    return abs(area), cx / (6 * area), cy / (6 * area)


def label_points(inset: bool = True) -> dict[str, tuple[float, float]]:
    """Centroid of the largest polygon of each province, for map labels."""
    out = {}
    for feature in provinces(inset)["features"]:
        best = max((_ring_area_centroid(p[0]) for p in polygons(feature)), key=lambda t: t[0])
        out[feature["properties"]["codigo"]] = (best[1], best[2])
    return out


def galapagos_frame(pad: float = 0.22) -> tuple[float, float, float, float]:
    """Bounding box of the relocated Galápagos inset, with padding."""
    x0, y0, x1, y1 = bounds(provinces(True), {GALAPAGOS})
    return x0 - pad, y0 - pad, x1 + pad, y1 + pad


def svg_map(fills: dict[str, str], *, width: int = 640, pad: int = 18, stroke: str = "#2B164F",
            titles: dict[str, str] | None = None, selected: set[str] | None = None,
            selected_fill: str = "#F8C018", equator: str | None = "#F8C018",
            frame_color: str = "rgba(255,255,255,.45)", label_color: str = "rgba(255,255,255,.72)",
            css_class: str = "ec-map") -> str:
    """Inline SVG map of Ecuador on a single line (safe for Markdown rendering).

    ``fills`` maps province codes to colors; ``selected`` provinces receive the
    gold accent.  Titles become native tooltips.  Paths are animated by CSS with
    a west-to-east stagger through the ``--d`` custom property.
    """
    data = provinces(True)
    x0, y0, x1, y1 = bounds(data)
    gx0, gy0, gx1, gy1 = galapagos_frame()
    x0, y0, x1, y1 = min(x0, gx0), min(y0, gy0), max(x1, gx1), max(y1, gy1)
    scale = (width - 2 * pad) / (x1 - x0)
    height = round((y1 - y0) * scale + 2 * pad)

    def px(x, y):
        return (x - x0) * scale + pad, (y1 - y) * scale + pad

    selected = selected or set()
    titles = titles or {}
    paths = []
    order = sorted(data["features"], key=lambda f: bounds({"features": [f]})[0])
    for index, feature in enumerate(order):
        code = feature["properties"]["codigo"]
        segments = []
        for polygon in polygons(feature):
            for ring in polygon:
                pts = [px(x, y) for x, y in ring]
                if len(pts) < 3:
                    continue
                segments.append("M" + "L".join(f"{a:.1f} {b:.1f}" for a, b in pts) + "Z")
        fill = selected_fill if code in selected else fills.get(code, "rgba(255,255,255,.08)")
        state = " is-selected" if code in selected else ""
        title = html.escape(titles.get(code, feature["properties"]["nombre"]))
        paths.append(
            f'<path class="ec-prov{state}" data-code="{code}" d="{"".join(segments)}" fill="{fill}" '
            f'stroke="{stroke}" style="--d:{index * 0.045:.3f}s"><title>{title}</title></path>'
        )
    fx0, fy0 = px(gx0, gy1)
    fx1, fy1 = px(gx1, gy0)
    frame = (f'<rect class="ec-inset" x="{fx0:.1f}" y="{fy0:.1f}" width="{fx1 - fx0:.1f}" height="{fy1 - fy0:.1f}" '
             f'rx="10" fill="none" stroke="{frame_color}" stroke-dasharray="4 4"/>'
             f'<text class="ec-inset-label" x="{fx0 + 4:.1f}" y="{fy1 + 16:.1f}" fill="{label_color}">Galápagos (recuadro)</text>')
    line = ""
    if equator:
        _, ey = px(0, 0)
        line = (f'<line class="ec-equator" x1="{pad / 2:.1f}" y1="{ey:.1f}" x2="{width - pad / 2:.1f}" y2="{ey:.1f}" '
                f'stroke="{equator}" stroke-dasharray="2 6" stroke-linecap="round"><title>Latitud 0°: línea equinoccial</title></line>')
    return (f'<svg class="{css_class}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Mapa de las provincias del Ecuador" preserveAspectRatio="xMidYMid meet">'
            f'{line}{frame}<g class="ec-provs">{"".join(paths)}</g></svg>')
