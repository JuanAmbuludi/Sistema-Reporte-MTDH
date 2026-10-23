#!/usr/bin/env python3
"""Genera ``assets/geo/ecuador_dpa.json``: parroquias, cantones, provincias y zonas de planificación del Ecuador.

Fuente: el atlas topológico del paquete npm ``ec-atlas`` 0.0.7 (licencia MIT, Carlos León, 2023), elaborado con
los límites cartográficos del INEC 2015.  El script:

1. decodifica los arcos compartidos del TopoJSON (los vecinos conservan exactamente el mismo borde);
2. asigna a cada vértice un nivel de simplificación por área efectiva (Visvalingam), sin mover los extremos de
   los arcos, de modo que la topología se mantiene en cualquier escala;
3. relaciona los códigos parroquiales de las bases con los polígonos (``src.geo.match_parishes``) y adopta la
   división político-administrativa vigente de los datos (por ejemplo, La Concordia en Santo Domingo de los
   Tsáchilas y Sevilla Don Bosco como cantón);
4. disuelve las parroquias en cantones, provincias, zonas de planificación y el contorno del país.

Uso (Node.js solo para descargar el paquete)::

    npm pack ec-atlas@0.0.7 && tar -xzf ec-atlas-0.0.7.tgz
    python scripts/build_geo.py package/ecuador-transverse_mercator-50k.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import names  # noqa: E402
from src.geo import ZONE_NAMES, dissolve, match_parishes, zone_of  # noqa: E402

DATA = ROOT / "data" / "processed"
OUTPUT = ROOT / "assets" / "geo" / "ecuador_dpa.json"
# Effective-area thresholds in square degrees: a vertex is kept at a level when its triangle is at least this big.
THRESHOLDS = {3: 5.0e-4, 2: 4.0e-5, 1: 0.0}


def decode(topology: dict) -> list[list[tuple[int, int]]]:
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            points.append((x, y))
        arcs.append(points)
    return arcs


def effective_areas(points: list[tuple[int, int]], sx: float, sy: float) -> list[float]:
    """Visvalingam–Whyatt areas (monotone); both ends of an arc are kept at every level."""
    n = len(points)
    areas = [math.inf] * n
    if n <= 2:
        return areas
    xs = [p[0] * sx for p in points]
    ys = [p[1] * sy for p in points]
    prev, nxt = list(range(-1, n - 1)), list(range(1, n + 1))

    def triangle(i: int) -> float:
        a, c = prev[i], nxt[i]
        return abs((xs[a] - xs[c]) * (ys[i] - ys[a]) - (xs[a] - xs[i]) * (ys[c] - ys[a])) / 2

    current = {i: triangle(i) for i in range(1, n - 1)}
    heap = [(area, i) for i, area in current.items()]
    heapq.heapify(heap)
    removed, floor = [False] * n, 0.0
    while heap:
        area, i = heapq.heappop(heap)
        if removed[i] or current.get(i) != area:
            continue
        floor = max(floor, area)
        areas[i], removed[i] = floor, True
        p, q = prev[i], nxt[i]
        nxt[p], prev[q] = q, p
        for j in (p, q):
            if 0 < j < n - 1 and not removed[j]:
                current[j] = triangle(j)
                heapq.heappush(heap, (current[j], j))
    if points[0] == points[-1] and n > 4:
        # A closed arc (an island) keeps its two largest vertices so it never collapses to a line.
        for i in sorted(range(1, n - 1), key=lambda k: -areas[k])[:2]:
            areas[i] = math.inf
    return areas


def level(area: float) -> int:
    for lvl in (3, 2, 1):
        if area >= THRESHOLDS[lvl]:
            return lvl
    return 0


def encode(points: list[tuple[int, int]], areas: list[float]) -> list[int]:
    flat, last = [], None
    for (x, y), area in zip(points, areas):
        lvl = level(area)
        if lvl == 0:
            continue
        if last is None:
            flat += [x, y, lvl]
        else:
            flat += [x - last[0], y - last[1], lvl]
        last = (x, y)
    return flat


def ring_refs(geometry: dict) -> list[list[int]]:
    if geometry["type"] == "Polygon":
        return [list(ring) for ring in geometry["arcs"]]
    return [list(ring) for polygon in geometry["arcs"] for ring in polygon]


def data_parishes() -> pd.DataFrame:
    coverage = pd.read_parquet(DATA / "cobertura_territorial.parquet")
    frame = coverage.drop_duplicates("parroquia_codigo")[["parroquia_codigo", "parroquia", "canton_codigo", "canton",
                                                          "provincia_codigo"]]
    return frame.astype(str).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("topojson", type=Path, help="ecuador-transverse_mercator-50k.json del paquete ec-atlas 0.0.7")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    raw = args.topojson.read_bytes()
    topology = json.loads(raw)
    (sx, sy) = topology["transform"]["scale"]
    arcs = decode(topology)
    objects = topology["objects"]

    def ends(ref: int):
        arc = arcs[ref] if ref >= 0 else arcs[~ref][::-1]
        return arc[0], arc[-1]

    def merge(groups):
        return dissolve(groups, ends)
    atlas_cantons = {g["id"]: g["properties"]["name"] for g in objects["level3"]["geometries"]}
    atlas = {g["id"]: g for g in objects["level4"]["geometries"]}

    # 1. Codes of the data -> polygons, with the atlas attributes of 2015.
    polygons = {code: {"name": g["properties"]["name"], "province": code[:2],
                       "canton_name": atlas_cantons.get(code[:4], "")} for code, g in atlas.items()}
    parishes = data_parishes()
    records = [{"code": r.parroquia_codigo, "name": r.parroquia, "canton": r.canton, "province": r.provincia_codigo}
               for r in parishes.itertuples()]
    mapping = match_parishes(records, polygons)
    unmatched = sorted(set(parishes.parroquia_codigo) - set(mapping))
    moved = {code: target for code, target in mapping.items() if code != target and int(code[4:]) >= 50}
    print(f"Parroquias de los datos: {len(parishes)}; con polígono: {len(mapping)}; sin polígono: {unmatched}")
    for code, target in sorted(moved.items()):
        print(f"  {code} → {target} ({atlas[target]['properties']['name']})")

    # 2. Current division of each polygon: the canton and province the data assign to the parishes it draws.
    owner = {}
    by_code = parishes.set_index("parroquia_codigo")
    for code, target in mapping.items():
        row = by_code.loc[code]
        exact = code == target
        if exact or target not in owner:
            owner[target] = (row.canton_codigo, row.provincia_codigo, exact)
        elif not owner[target][2] and row.canton_codigo != owner[target][0]:
            raise ValueError(f"El polígono {target} recibe parroquias de cantones distintos.")
    canton_names = {r.canton_codigo: names.place(r.canton) for r in parishes.drop_duplicates("canton_codigo").itertuples()}
    indicators = pd.read_parquet(DATA / "indicadores.parquet")
    province_names = (indicators.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.astype(str).to_dict())
    province_names["90"] = "Zona no delimitada"
    display = {r.parroquia_codigo: names.place(r.parroquia) for r in parishes.itertuples()}

    parish_items, canton_rings, canton_province = [], defaultdict(list), {}
    for code, geometry in sorted(atlas.items()):
        canton, province, _ = owner.get(code, (code[:4], code[:2], True))
        canton_province[canton] = province
        rings = ring_refs(geometry)
        canton_rings[canton].append(rings)
        name = display.get(code) or names.place(geometry["properties"]["name"])
        parish_items.append({"c": code, "n": name, "k": canton, "p": province, "r": rings})
    canton_items, province_groups, zone_groups = [], defaultdict(list), defaultdict(list)
    for canton, groups in sorted(canton_rings.items()):
        rings = merge(groups)
        province = canton_province[canton]
        zone = zone_of(province, canton)
        name = canton_names.get(canton) or names.place(atlas_cantons.get(canton, canton))
        item = {"c": canton, "n": name, "p": province, "r": rings}
        if zone:
            item["z"] = zone
            zone_groups[zone].append(rings)
        canton_items.append(item)
        province_groups[province].append(rings)
    province_items = [{"c": code, "n": province_names.get(code, code), "r": merge(groups)}
                      for code, groups in sorted(province_groups.items())]
    zone_items = [{"c": code, "n": ZONE_NAMES[code], "r": merge(groups)} for code, groups in sorted(zone_groups.items())]
    country = merge([p["r"] for p in province_items])

    encoded = [encode(points, effective_areas(points, sx, sy)) for points in arcs]
    asset = {
        "version": 1,
        "fuente": {"paquete": "ec-atlas@0.0.7", "archivo": args.topojson.name, "licencia": "MIT (Carlos León, 2023)",
                   "datos": "Límites cartográficos INEC 2015", "sha256": hashlib.sha256(raw).hexdigest()},
        "transform": topology["transform"],
        "niveles": {str(k): v for k, v in THRESHOLDS.items()},
        "arcs": encoded,
        "parroquias": parish_items, "cantones": canton_items, "provincias": province_items, "zonas": zone_items,
        "pais": [{"c": "EC", "n": "Ecuador", "r": country}],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asset, ensure_ascii=False, separators=(",", ":"))
    args.output.write_text(text, encoding="utf-8")
    kept = Counter(flat[i] for flat in encoded for i in range(2, len(flat), 3))
    print(f"{args.output.relative_to(ROOT)}: {len(text) / 1024:.0f} KB; parroquias {len(parish_items)}, cantones "
          f"{len(canton_items)}, provincias {len(province_items)}, zonas {len(zone_items)}; vértices por nivel {dict(sorted(kept.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
