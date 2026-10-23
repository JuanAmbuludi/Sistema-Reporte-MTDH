"""Ecuador geometry shared by the interface maps and the report maps: parishes, cantons, provinces and zones.

Boundaries come from the INEC 2015 cartography published as a topological atlas (``assets/geo/PROCEDENCIA.md``).
Cantons, provinces and the nine planning zones are dissolved from the parishes with the current political and
administrative division (DPA) of the data, so every layer shares exactly the same borders.  Each vertex keeps a
simplification level: national views draw the coarse outline and a zoom into a province draws the full detail.

The Galápagos islands are drawn in an inset moved 7.5° east so the mainland keeps a legible size; every national
map labels that inset.  Code ``90`` (zones not delimited) has no reported data and is drawn as neutral territory.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import html
import json
from pathlib import Path

import numpy as np

from src import names as toponyms

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "geo" / "ecuador_dpa.json"
GALAPAGOS = "20"
NO_POLYGON = "90"
GALAPAGOS_SHIFT = 7.5  # degrees of longitude, inset only
GALAPAGOS_WEST = -85.0  # every vertex of the islands lies west of this meridian; the mainland lies east of it
LAYERS = ("parroquia", "canton", "provincia", "zona")
_ASSET_KEYS = {"parroquia": "parroquias", "canton": "cantones", "provincia": "provincias", "zona": "zonas", "pais": "pais"}

# Planning zones: provinces, with the cantons of Guayaquil, Durán, Samborondón (zone 8) and Quito (zone 9).
ZONE_CANTONS = {"0901": "Z8", "0907": "Z8", "0916": "Z8", "1701": "Z9"}
ZONE_PROVINCES = {
    "04": "Z1", "08": "Z1", "10": "Z1", "21": "Z1", "15": "Z2", "17": "Z2", "22": "Z2",
    "05": "Z3", "06": "Z3", "16": "Z3", "18": "Z3", "13": "Z4", "23": "Z4",
    "02": "Z5", "09": "Z5", "12": "Z5", "20": "Z5", "24": "Z5", "01": "Z6", "03": "Z6", "14": "Z6",
    "07": "Z7", "11": "Z7", "19": "Z7",
}
ZONE_NAMES = {f"Z{i}": f"Zona {i}" for i in range(1, 10)}


def zone_of(province: str, canton: str | None = None) -> str | None:
    """Planning zone of a canton (or of a province when the canton is unknown)."""
    if canton and canton in ZONE_CANTONS:
        return ZONE_CANTONS[canton]
    return ZONE_PROVINCES.get(str(province))


# ----------------------------------------------------------------------------------------------- asset access
@lru_cache(maxsize=1)
def _asset() -> dict:
    return json.loads(ASSET.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _decoded() -> tuple[np.ndarray, ...]:
    """Every arc as rows of integer x, y and simplification level."""
    out = []
    for flat in _asset()["arcs"]:
        values = np.asarray(flat, dtype=np.int64).reshape(-1, 3)
        values[:, :2] = np.cumsum(values[:, :2], axis=0)
        out.append(values)
    return tuple(out)


@lru_cache(maxsize=4)
def _arcs(level: int) -> tuple[np.ndarray, ...]:
    """Arcs in degrees, keeping the vertices whose simplification level is at least ``level`` (1 fine, 3 coarse)."""
    (sx, sy), (tx, ty) = _asset()["transform"]["scale"], _asset()["transform"]["translate"]
    out = []
    for values in _decoded():
        keep = values[:, 2] >= level
        keep[0] = keep[-1] = True
        points = values[keep, :2].astype(float)
        points[:, 0] = points[:, 0] * sx + tx
        points[:, 1] = points[:, 1] * sy + ty
        out.append(points)
    return tuple(out)


@lru_cache(maxsize=1)
def _ends() -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    return tuple(((int(v[0, 0]), int(v[0, 1])), (int(v[-1, 0]), int(v[-1, 1]))) for v in _decoded())


def _ring(refs, arcs: tuple[np.ndarray, ...]) -> np.ndarray:
    parts = []
    for index, ref in enumerate(refs):
        arc = arcs[ref] if ref >= 0 else arcs[~ref][::-1]
        parts.append(arc if index == 0 else arc[1:])
    return np.concatenate(parts) if parts else np.zeros((0, 2))


def dissolve(groups, ends=None) -> list[list[int]]:
    """Merge features (each a list of rings of arc references) into one shape and return its rings.

    An arc walked in both directions separates two merged features and disappears; the arcs left keep their net
    direction and are stitched into closed rings.  ``ends`` gives the first and last vertex of an arc reference; by
    default the arcs of the bundled atlas.
    """
    if ends is None:
        table = _ends()

        def ends(ref: int):
            first, last = table[ref if ref >= 0 else ~ref]
            return (first, last) if ref >= 0 else (last, first)
    net, order = Counter(), []
    for group in groups:
        for ring in group:
            for ref in ring:
                arc = ref if ref >= 0 else ~ref
                if arc not in net:
                    order.append(arc)
                net[arc] += 1 if ref >= 0 else -1
    # The atlas has a few borders traced twice in the same direction; the sign keeps one copy of them.
    boundary = [arc if net[arc] > 0 else ~arc for arc in order if net[arc]]
    starts = defaultdict(list)
    for ref in boundary:
        starts[ends(ref)[0]].append(ref)
    used, out = set(), []
    for ref in boundary:
        if ref in used:
            continue
        ring, (origin, end) = [ref], ends(ref)
        used.add(ref)
        while end != origin:
            options = [r for r in starts.get(end, []) if r not in used]
            if not options:
                raise ValueError("No se pudo cerrar un anillo al disolver la geometría.")
            ring.append(options[0])
            used.add(options[0])
            end = ends(options[0])[1]
        out.append(ring)
    return out


@lru_cache(maxsize=8)
def _refs(layer: str) -> dict[str, tuple[tuple[int, ...], ...]]:
    return {item["c"]: tuple(tuple(r) for r in item["r"]) for item in _asset()[_ASSET_KEYS[layer]]}


@lru_cache(maxsize=16)
def _layer(layer: str, level: int) -> dict[str, tuple[np.ndarray, ...]]:
    arcs = _arcs(level)
    return {code: tuple(_ring(r, arcs) for r in rings_) for code, rings_ in _refs(layer).items()}


@lru_cache(maxsize=96)
def _merged(layer: str, codes: tuple[str, ...]) -> tuple[tuple[int, ...], ...]:
    refs = _refs(layer)
    groups = [refs[c] for c in codes if c in refs]
    try:
        return tuple(tuple(r) for r in dissolve(groups))
    except ValueError:
        # Never lose the drawing over a defect of the cartography: keep the features as they are.
        return tuple(tuple(r) for group in groups for r in group)


@lru_cache(maxsize=4)
def features(layer: str = "provincia") -> dict[str, dict]:
    """Metadata of every feature of a layer: name and, below provinces, the canton and province it belongs to."""
    out = {}
    for item in _asset()[_ASSET_KEYS[layer]]:
        meta = {"code": item["c"], "name": item.get("n", item["c"])}
        for short, full in (("k", "canton"), ("p", "province"), ("z", "zone")):
            if short in item:
                meta[full] = item[short]
        out[item["c"]] = meta
    return out


def names(layer: str = "provincia") -> dict[str, str]:
    return {code: meta["name"] for code, meta in features(layer).items()}


def province_of(layer: str, code: str) -> str | None:
    if layer == "provincia":
        return code
    if layer == "zona":
        return None
    return features(layer).get(code, {}).get("province")


def _inset(ring: np.ndarray) -> np.ndarray:
    if len(ring) and ring[:, 0].max() < GALAPAGOS_WEST:
        ring = ring.copy()
        ring[:, 0] += GALAPAGOS_SHIFT
    return ring


def rings(layer: str, code: str, *, level: int = 3, inset: bool = True) -> list[np.ndarray]:
    """Rings (outer boundaries and holes) of one feature, in degrees; Galápagos moves into its inset."""
    found = _layer(layer, level).get(code, ())
    return [_inset(r) if inset else r for r in found]


def merged_rings(layer: str, codes, *, level: int = 3, inset: bool = True) -> list[np.ndarray]:
    """One shape for several features of a layer (shared borders removed)."""
    arcs = _arcs(level)
    out = [_ring(r, arcs) for r in _merged(layer, tuple(sorted(codes)))]
    return [_inset(r) if inset else r for r in out]


def bounds(layer: str = "provincia", codes=None, *, inset: bool = True) -> tuple[float, float, float, float]:
    xs, ys = [], []
    wanted = set(codes) if codes else None
    for code, found in _layer(layer, 3).items():
        if wanted is not None and code not in wanted:
            continue
        for ring in found:
            ring = _inset(ring) if inset else ring
            if len(ring):
                xs += [ring[:, 0].min(), ring[:, 0].max()]
                ys += [ring[:, 1].min(), ring[:, 1].max()]
    if not xs:
        raise ValueError("No hay geometría para los territorios indicados.")
    return min(xs), min(ys), max(xs), max(ys)


def _area_centroid(ring: np.ndarray) -> tuple[float, float, float]:
    x, y = ring[:, 0], ring[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    area = cross.sum() / 2
    if abs(area) < 1e-12:
        return 0.0, float(x.mean()), float(y.mean())
    cx = ((x + np.roll(x, -1)) * cross).sum() / (6 * area)
    cy = ((y + np.roll(y, -1)) * cross).sum() / (6 * area)
    return abs(float(area)), float(cx), float(cy)


@lru_cache(maxsize=8)
def label_points(layer: str = "provincia", inset: bool = True) -> dict[str, tuple[float, float]]:
    """Centroid of the largest ring of each feature, for map labels."""
    out = {}
    for code in _layer(layer, 3):
        candidates = [_area_centroid(r) for r in rings(layer, code, level=3, inset=inset) if len(r) > 2]
        if candidates:
            best = max(candidates, key=lambda t: t[0])
            out[code] = (best[1], best[2])
    return out


def galapagos_frame(pad: float = 0.22) -> tuple[float, float, float, float]:
    """Bounding box of the relocated Galápagos inset, with padding."""
    x0, y0, x1, y1 = bounds("provincia", {GALAPAGOS}, inset=True)
    return x0 - pad, y0 - pad, x1 + pad, y1 + pad


def level_for(pixels_per_degree: float) -> int:
    """Simplification level that keeps vertices about a pixel apart at a given scale."""
    if pixels_per_degree < 150:
        return 3
    if pixels_per_degree < 420:
        return 2
    return 1


# --------------------------------------------------------------------------------- parish codes of the data
def match_parishes(records, polygons: dict[str, dict] | None = None) -> dict[str, str]:
    """Polygon of every parish code of the data.

    ``records`` holds dicts with ``code``, ``name``, ``canton`` (name) and ``province`` (code).  The 2015 cartography
    draws the urban parishes of a city as its cantonal seat (``canton + 50``) and predates some parishes; the rules,
    in order: the same code; an urban parish goes to its seat; the same name in the same province and canton; the
    same name in the province; the same name and canton elsewhere (a canton that changed province); the cantonal
    seat.  Codes without any match (zones in study) stay off the map and keep their place in every total.
    """
    explicit = polygons is not None
    polygons = polygons if explicit else features("parroquia")
    # The build passes the atlas with canton names; the application reads them from the canton layer.
    canton_names = {} if explicit else {code: toponyms.key(meta.get("name")) for code, meta in features("canton").items()}
    by_province, by_name = defaultdict(list), defaultdict(list)
    for code, meta in polygons.items():
        name = toponyms.key(meta.get("name"))
        by_province[(meta.get("province"), name)].append(code)
        by_name[name].append(code)

    def canton_of(candidate: str) -> str:
        meta = polygons[candidate]
        return toponyms.key(meta.get("canton_name") or canton_names.get(meta.get("canton"), ""))

    out = {}
    for record in records:
        code = str(record["code"])
        if code in polygons:
            out[code] = code
            continue
        seat = code[:4] + "50"
        if code[4:].isdigit() and int(code[4:]) < 50 and seat in polygons:
            out[code] = seat
            continue
        name, canton = toponyms.key(record.get("name")), toponyms.key(record.get("canton"))
        same = by_province.get((str(record.get("province")), name), [])
        strict = [c for c in same if canton_of(c) == canton]
        elsewhere = [c for c in by_name.get(name, []) if canton_of(c) == canton]
        for options in (strict, same, elsewhere):
            if len(options) == 1:
                out[code] = options[0]
                break
        else:
            if seat in polygons:
                out[code] = seat
    return out


# ------------------------------------------------------------------------------------------------ SVG maps
def _num(value: float) -> str:
    text = f"{value:.1f}"
    text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _path(ring_list, project) -> str:
    out = []
    for ring in ring_list:
        if len(ring) < 3:
            continue
        points = np.round(project(ring), 1)
        steps = np.diff(points, axis=0)
        steps = steps[np.any(steps != 0, axis=1)]
        if len(steps) < 2:
            continue
        out.append("M" + _num(points[0, 0]) + " " + _num(points[0, 1]) + "l"
                   + " ".join(_num(a) + " " + _num(b) for a, b in steps) + "z")
    return "".join(out)


def svg_map(fills: dict[str, str], *, layer: str = "provincia", titles: dict[str, str] | None = None,
            regions: dict[str, str] | None = None, selected: set[str] | None = None, focus: set[str] | None = None,
            width: int = 640, pad: int = 18, stroke: str = "#2B164F", selected_fill: str = "#F8C018",
            equator: str | None = "#F8C018", frame_color: str = "rgba(255,255,255,.45)",
            label_color: str = "rgba(255,255,255,.72)", empty_fill: str = "rgba(255,255,255,.08)",
            context_fill: str = "rgba(255,255,255,.07)", border_color: str = "rgba(255,255,255,.55)",
            locator: bool = True, css_class: str = "ec-map", label: str = "Mapa del Ecuador") -> str:
    """Inline SVG map of Ecuador on a single line (safe for Markdown rendering).

    ``fills`` maps feature codes of ``layer`` to colours and ``titles`` gives their native tooltips.

    * Provinces or zones: one shape per unit; ``selected`` units take the gold accent.
    * Parishes, whole country: the colours form a mosaic (parishes of one colour are drawn as one shape) under the
      province borders, which carry the tooltips in ``regions``; ``selected`` provinces are outlined in gold.
    * Parishes with ``focus`` (province codes): the map zooms into those provinces, every parish keeps its own
      tooltip, cantons are outlined, the rest of the country stays as context and a locator shows the place.

    Units are grouped by province and revealed west to east by CSS through the ``--d`` custom property.
    """
    selected, titles, regions = set(selected or ()), titles or {}, regions or {}
    provinces = features("provincia")
    focus = {c for c in (focus or ()) if c in provinces} if layer == "parroquia" else set()
    inset = not focus or (GALAPAGOS in focus and len(focus) > 1)
    if focus:
        x0, y0, x1, y1 = bounds("provincia", focus, inset=inset)
        margin = max(x1 - x0, y1 - y0) * 0.05
        x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
    else:
        x0, y0, x1, y1 = bounds("provincia", inset=True)
        gx0, gy0, gx1, gy1 = galapagos_frame()
        x0, y0, x1, y1 = min(x0, gx0), min(y0, gy0), max(x1, gx1), max(y1, gy1)
    usable = width - 2 * pad
    scale = min(usable / (x1 - x0), usable * 1.05 / (y1 - y0))
    height = round((y1 - y0) * scale + 2 * pad)
    shift_x = pad + (usable - (x1 - x0) * scale) / 2
    level = level_for(scale)

    def project(ring: np.ndarray) -> np.ndarray:
        return np.column_stack([(ring[:, 0] - x0) * scale + shift_x, (y1 - ring[:, 1]) * scale + pad])

    def shape(lay: str, code: str, lvl: int = level) -> str:
        return _path(rings(lay, code, level=lvl, inset=inset), project)

    west = label_points("provincia", True)
    order = sorted(provinces, key=lambda c: west.get(c, (0, 0))[0])
    layers = []
    if layer == "parroquia" and not focus:
        # National mosaic: one shape per colour, a hairline of the same colour hides seams between shapes.
        classes = defaultdict(list)
        for code in features("parroquia"):
            classes[fills.get(code, empty_fill)].append(code)
        mosaic = "".join(f'<path d="{_path(merged_rings("parroquia", codes, level=level, inset=True), project)}" fill="{color}" '
                         f'stroke="{color}"/>' for color, codes in sorted(classes.items(), key=lambda kv: -len(kv[1])))
        layers.append(f'<g class="ec-mosaic">{mosaic}</g>')
        hits = []
        for index, code in enumerate(order):
            chosen = " is-selected" if code in selected else ""
            title = regions.get(code, provinces[code]["name"])
            hits.append(f'<path class="ec-region{chosen}" data-code="{code}" d="{shape("provincia", code)}" '
                        f'style="--d:{index * 0.045:.3f}s"><title>{html.escape(title)}</title></path>')
        layers.append(f'<g class="ec-regions" stroke="{border_color}">{"".join(hits)}</g>')
    else:
        if focus:
            context = "".join(shape("provincia", c, 3) for c in provinces if c not in focus)
            layers.append(f'<path class="ec-context" d="{context}" fill="{context_fill}" stroke="{border_color}" '
                          f'stroke-opacity=".3"/>')
        units = features(layer)
        groups = defaultdict(list)
        for code in units:
            owner = code if layer == "zona" else province_of(layer, code)
            if focus and owner not in focus:
                continue
            groups[owner].append(code)
        group_order = sorted(groups) if layer == "zona" else sorted(groups, key=lambda o: order.index(o) if o in order else -1)
        painted = []
        for index, owner in enumerate(group_order):
            paths = []
            for code in groups[owner]:
                d = shape(layer, code)
                if not d:
                    continue
                chosen = code in selected and layer in ("provincia", "zona")
                fill = selected_fill if chosen else fills.get(code, empty_fill)
                state = " is-selected" if chosen else ""
                title = titles.get(code, units[code]["name"])
                paths.append(f'<path class="ec-unit{state}" data-code="{html.escape(code)}" d="{d}" fill="{fill}">'
                             f'<title>{html.escape(title)}</title></path>')
            if paths:
                painted.append(f'<g class="ec-prov" style="--d:{index * 0.045:.3f}s">{"".join(paths)}</g>')
        layers.append(f'<g class="ec-units" data-layer="{layer}" stroke="{stroke}">{"".join(painted)}</g>')
        if layer == "zona":
            outline = "".join(shape("provincia", c) for c in provinces)
            layers.append(f'<path class="ec-borders thin" d="{outline}" fill="none" stroke="{border_color}" stroke-opacity=".4"/>')
        if focus:
            cantons = "".join(shape("canton", c) for c, meta in features("canton").items() if meta.get("province") in focus)
            layers.append(f'<path class="ec-borders thin" d="{cantons}" fill="none" stroke="{border_color}" stroke-opacity=".65"/>')
            outline = "".join(shape("provincia", c) for c in focus)
            layers.append(f'<path class="ec-focus" d="{outline}" fill="none" stroke="{selected_fill}"/>')
    under, over = [], []
    if inset:
        gx0, gy0, gx1, gy1 = galapagos_frame()
        (fx0, fy0), (fx1, fy1) = project(np.array([[gx0, gy1], [gx1, gy0]]))
        under.append(f'<rect class="ec-inset" x="{fx0:.1f}" y="{fy0:.1f}" width="{fx1 - fx0:.1f}" height="{fy1 - fy0:.1f}" '
                     f'rx="10" fill="none" stroke="{frame_color}" stroke-dasharray="4 4"/>'
                     f'<text class="ec-inset-label" x="{fx0 + 4:.1f}" y="{fy1 + 16:.1f}" fill="{label_color}">Galápagos (recuadro)</text>')
    if equator and y0 < 0 < y1:
        ey = y1 * scale + pad
        over.append(f'<line class="ec-equator" x1="{pad / 2:.1f}" y1="{ey:.1f}" x2="{width - pad / 2:.1f}" y2="{ey:.1f}" '
                    f'stroke="{equator}" stroke-dasharray="2 6" stroke-linecap="round"><title>Latitud 0°: línea equinoccial</title></line>')
    if focus and locator:
        over.append(_locator(focus, width, pad, selected_fill))
    body = "".join(layers)
    if focus:
        # The context provinces extend beyond the zoom: clip them to the drawing.
        clip = f"ec-clip-{width}-{'-'.join(sorted(focus))}"
        body = (f'<defs><clipPath id="{clip}"><rect width="{width}" height="{height}" rx="18"/></clipPath></defs>'
                f'<g clip-path="url(#{clip})">{body}</g>')
    return (f'<svg class="{css_class}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(under)}{body}{"".join(over)}</svg>')


def _locator(focus: set[str], width: int, pad: int, gold: str) -> str:
    """A small mainland silhouette with the zoomed provinces in gold, in the upper right corner."""
    mainland = [c for c in features("provincia") if c != GALAPAGOS]
    x0, y0, x1, y1 = bounds("provincia", mainland, inset=False)
    box = 92
    scale = (box - 14) / max(x1 - x0, y1 - y0)
    left, top = width - pad - box, pad / 2
    offset_x = left + 7 + (box - 14 - (x1 - x0) * scale) / 2
    offset_y = top + 7 + (box - 14 - (y1 - y0) * scale) / 2

    def project(ring: np.ndarray) -> np.ndarray:
        return np.column_stack([(ring[:, 0] - x0) * scale + offset_x, (y1 - ring[:, 1]) * scale + offset_y])

    land = _path(merged_rings("provincia", mainland, level=3, inset=False), project)
    chosen = _path(merged_rings("provincia", [c for c in focus if c != GALAPAGOS], level=3, inset=False), project) \
        if any(c != GALAPAGOS for c in focus) else ""
    return (f'<g class="ec-locator" aria-hidden="true"><rect x="{left:.1f}" y="{top:.1f}" width="{box}" height="{box}" rx="14" '
            f'fill="rgba(27,13,53,.62)" stroke="rgba(255,255,255,.18)"/><path d="{land}" fill="rgba(255,255,255,.18)" '
            f'stroke="rgba(255,255,255,.35)" stroke-width=".6"/><path d="{chosen}" fill="{gold}"/></g>')
