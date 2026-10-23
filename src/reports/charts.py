"""Publication maps and charts rendered with matplotlib for every report format.

Maps use the same geometry as the interface (parishes, provinces or zones; the whole country or a zoom into the
selected provinces), the institutional palette and the bundled Montserrat / Public Sans fonts, so the one-page
summary, the slides and the data workbook show identical figures without depending on installed fonts.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import RLock

import matplotlib
matplotlib.use("Agg")
from matplotlib import patheffects
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PathCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.path import Path as MPath

from src import geo, theme
from .context import number

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
INK = theme.TINTA
MUTED = "#6E6880"
_LOCK = RLock()


def font(weight: str = "Regular", display: bool = False, size: float = 9) -> FontProperties:
    family = "Montserrat" if display else "PublicSans"
    path = FONTS / f"{family}-{weight}.ttf"
    if not path.exists():
        path = FONTS / ("DejaVuSans-Bold.ttf" if weight in ("Bold", "SemiBold", "ExtraBold") else "DejaVuSans.ttf")
    return FontProperties(fname=str(path), size=size)


def _png(fig: Figure, transparent: bool = False, dpi: int = 200) -> bytes:
    out = BytesIO()
    fig.savefig(out, format="png", dpi=dpi, transparent=transparent, facecolor="none" if transparent else fig.get_facecolor())
    return out.getvalue()


def _compact(value: float, money: bool = False, rate: bool = False) -> str:
    if rate:
        return f"{number(value, 1)} %"
    if money:
        return f"{number(value / 1_000_000, 1)} M"
    if value >= 10_000:
        return f"{number(value / 1000, 0)} mil"
    return number(value)


def _shape(ring_list) -> MPath | None:
    vertices, codes = [], []
    for ring in ring_list:
        if len(ring) < 3:
            continue
        vertices += [tuple(p) for p in ring] + [tuple(ring[0])]
        codes += [MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 1) + [MPath.CLOSEPOLY]
    return MPath(vertices, codes) if vertices else None


def _classes(values: dict[str, float], stops: list[str]) -> dict[str, str]:
    """Ordered classes of the ramp, as on the interface map; zero or empty values stay neutral."""
    present = {c: v for c, v in values.items() if v is not None and v == v and v > 0}
    colors = theme.ramp(list(present.values()), stops)
    return {c: col for c, col in zip(present, colors) if col}


def map_png(values: dict[str, float | None], *, layer: str = "provincia", focus=None, selected=None, mode: str = "light",
            label: str = "", money: bool = False, rate: bool = False, annotate: int = 0, width: float = 6.6,
            height: float = 5.6, dpi: int = 220, legend: bool = True, names: dict[str, str] | None = None) -> bytes:
    """Choropleth of Ecuador: provinces, cantons, parishes or zones; the whole country (with the Galápagos inset and
    the equator) or a zoom into ``focus`` provinces with the rest of the country as context.

    ``light`` is for white pages and carries a key (``label``) from lower to higher; ``night`` returns a transparent
    image for purple plates.  ``selected`` provinces (or zones) take the gold accent; ``annotate`` labels the leading
    units with their figure.
    """
    selected = set(selected or ())
    provinces = geo.features("provincia")
    focus = {c for c in (focus or ()) if c in provinces} if layer in ("parroquia", "canton") else set()
    night = mode == "night"
    stops = theme.NIGHT_SEQUENTIAL if night else theme.SEQUENTIAL[1:]
    fills = _classes(values, stops)
    inset = not focus or (geo.GALAPAGOS in focus and len(focus) > 1)
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="none" if night else "#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        if focus:
            x0, y0, x1, y1 = geo.bounds("provincia", focus, inset=inset)
            span = max(x1 - x0, y1 - y0)
            margin = span * 0.06
            bottom_room = span * 0.16 if legend and not night else 0
            x0, y0, x1, y1 = x0 - margin, y0 - margin - bottom_room, x1 + margin, y1 + margin
        else:
            x0, y0, x1, y1 = geo.bounds("provincia", inset=True)
            gx0, gy0, gx1, gy1 = geo.galapagos_frame()
            x0, y1 = min(x0, gx0) - 0.2, max(y1, gy1) + 0.45
            x1, y0 = x1 + 0.25, y0 - (1.25 if legend and not night else 0.25)
        # Fit the box to the figure's aspect so the map is never stretched.
        aspect = width / height
        if (x1 - x0) / (y1 - y0) < aspect:
            extra = ((y1 - y0) * aspect - (x1 - x0)) / 2
            x0, x1 = x0 - extra, x1 + extra
        else:
            extra = ((x1 - x0) / aspect - (y1 - y0)) / 2
            y0, y1 = y0 - extra, y1 + extra
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        pixels_per_degree = width * dpi / (x1 - x0)
        level = geo.level_for(pixels_per_degree / 2)
        empty = "#3A2563" if night else "#DAD7E0"
        stroke = theme.MORADO_900 if night else "#FFFFFF"
        gold = theme.ORO
        if not focus or (y0 < 0 < y1):
            ax.plot([x0 + 0.05 * (x1 - x0), x1 - 0.02 * (x1 - x0)], [0, 0], color=gold, lw=1.0, ls=(0, (1.2, 3.2)),
                    zorder=1, solid_capstyle="round")
            ax.text(x1 - 0.02 * (x1 - x0), 0.008 * (y1 - y0), "Latitud 0°", ha="right", va="bottom",
                    color=(gold if night else theme.ORO_700), fontproperties=font("SemiBold", size=6.8), zorder=6,
                    path_effects=[patheffects.withStroke(linewidth=2.4, foreground=(theme.MORADO_900 if night else "#FFFFFF"))])
        if focus:
            context = [_shape(geo.rings("provincia", c, level=3, inset=inset)) for c in provinces if c not in focus]
            context = [p for p in context if p is not None]
            ax.add_collection(PathCollection(context, facecolors=("#2E1A55" if night else "#F4F2F8"),
                                             edgecolors=("#4A3478" if night else "#DCD5E8"), linewidths=0.5, zorder=1))
        units = geo.features(layer)
        paths, colors = [], []
        for code in units:
            owner = code if layer == "zona" else geo.province_of(layer, code)
            if focus and owner not in focus:
                continue
            path = _shape(geo.rings(layer, code, level=level, inset=inset))
            if path is None:
                continue
            paths.append(path)
            chosen = code in selected and layer in ("provincia", "zona")
            colors.append(gold if chosen else fills.get(code, empty))
        if layer == "parroquia":
            edges, width_units = (stroke, 0.35) if focus else (colors, 0.15)
        elif layer == "canton":
            edges, width_units = stroke, (0.7 if focus else 0.3)
        else:
            edges, width_units = stroke, 0.7
        ax.add_collection(PathCollection(paths, facecolors=colors, edgecolors=edges, linewidths=width_units, zorder=2))
        if layer in ("parroquia", "canton", "zona") and not focus:
            borders = [_shape(geo.rings("provincia", c, level=level, inset=True)) for c in provinces]
            ax.add_collection(PathCollection([b for b in borders if b is not None], facecolors="none",
                                             edgecolors=("#FFFFFF" if not night else (1, 1, 1, .55)),
                                             linewidths=0.4 if layer == "zona" else (0.75 if layer == "canton" else 0.55), zorder=3))
        if focus and layer == "parroquia":
            cantons = [_shape(geo.rings("canton", c, level=level, inset=inset)) for c, meta in geo.features("canton").items()
                       if meta.get("province") in focus]
            ax.add_collection(PathCollection([c for c in cantons if c is not None], facecolors="none",
                                             edgecolors=((1, 1, 1, .6) if night else "#FFFFFF"), linewidths=0.6, zorder=3))
        outline = focus or (selected if layer in ("parroquia", "canton") else set())
        if outline:
            edges = [_shape(geo.rings("provincia", c, level=level, inset=inset)) for c in outline]
            ax.add_collection(PathCollection([e for e in edges if e is not None], facecolors="none", edgecolors=gold,
                                             linewidths=1.4, zorder=4))
        if inset:
            gx0, gy0, gx1, gy1 = geo.galapagos_frame()
            frame_color = (1, 1, 1, .5) if night else theme.LILA_300
            ax.add_patch(Rectangle((gx0, gy0), gx1 - gx0, gy1 - gy0, fill=False, ec=frame_color, lw=0.8, ls=(0, (2, 2.5)), zorder=1))
            ax.text(gx0 + 0.05, gy1 + 0.12, "Galápagos (recuadro)", color=("#E6DDF5" if night else MUTED),
                    fontproperties=font("Medium", size=7.5))
        if annotate and values:
            names = names or geo.names(layer)
            points = geo.label_points(layer, inset)
            present = {c: v for c, v in values.items() if v is not None and v == v and c in points
                       and (not focus or geo.province_of(layer, c) in focus)}
            halo = [patheffects.withStroke(linewidth=2.6, foreground=(theme.MORADO_900 if night else "#FFFFFF"))]
            for code, value in sorted(present.items(), key=lambda kv: -kv[1])[:annotate]:
                px, py = points[code]
                ax.text(px, py + 0.012 * (y1 - y0), names.get(code, code), ha="center", va="bottom",
                        color=("#FFFFFF" if night else theme.MORADO_900), fontproperties=font("Bold", display=True, size=7.2),
                        path_effects=halo, zorder=7)
                ax.text(px, py - 0.008 * (y1 - y0), _compact(value, money, rate), ha="center", va="top",
                        color=("#F8E3A6" if night else theme.TINTA), fontproperties=font("SemiBold", size=6.8),
                        path_effects=halo, zorder=7)
        if legend and not night:
            cmap = LinearSegmentedColormap.from_list("mtdh", stops)
            lw, lh = (x1 - x0) * 0.42, (y1 - y0) * 0.022
            lx0, ly0 = x0 + (x1 - x0) * 0.04, y0 + (y1 - y0) * 0.06
            for i in range(60):
                ax.add_patch(Rectangle((lx0 + lw * i / 60, ly0), lw / 60 + lw * 0.002, lh, color=cmap(i / 59), lw=0, zorder=5))
            ax.add_patch(FancyBboxPatch((lx0, ly0), lw, lh, boxstyle="round,pad=0,rounding_size=0.01", fill=False, ec="#E4DEEE",
                                        lw=0.5, zorder=6))
            ax.text(lx0, ly0 - lh * 0.6, "Menor", ha="left", va="top", color=MUTED, fontproperties=font(size=7))
            ax.text(lx0 + lw, ly0 - lh * 0.6, "Mayor", ha="right", va="top", color=MUTED, fontproperties=font(size=7))
            ax.text(lx0, ly0 + lh * 1.6, label, ha="left", va="bottom", color=INK, fontproperties=font("SemiBold", size=7.6))
        return _png(fig, transparent=night, dpi=dpi)


def emblem_png(selected=(), *, layer: str = "provincia", width: float = 3.4, height: float = 3.0, dpi: int = 200) -> bytes:
    """A quiet silhouette of Ecuador for the cover plates, on a faint graticule.

    It carries no figures: the maps with data live in the body of each product, so a cover never repeats them.
    ``selected`` provinces (or zones, with ``layer="zona"``) glow in gold and locate the territory of the report.
    """
    selected = set(selected or ())
    provinces = geo.features("provincia")
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="none")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        x0, y0, x1, y1 = geo.bounds("provincia", inset=True)
        gx0, gy0, gx1, gy1 = geo.galapagos_frame()
        x0, y0, x1, y1 = min(x0, gx0) - 0.25, min(y0, gy0) - 0.25, x1 + 0.25, max(y1, gy1) + 0.25
        aspect = width / height
        if (x1 - x0) / (y1 - y0) < aspect:
            extra = ((y1 - y0) * aspect - (x1 - x0)) / 2
            x0, x1 = x0 - extra, x1 + extra
        else:
            extra = ((x1 - x0) / aspect - (y1 - y0)) / 2
            y0, y1 = y0 - extra, y1 + extra
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        # Meridians and parallels every degree: the language of maps, as on the band of the interface.
        for lon in range(int(x0) - 1, int(x1) + 2):
            ax.plot([lon, lon], [y0, y1], color=(1, 1, 1, .07), lw=0.5, zorder=0)
        for lat in range(int(y0) - 1, int(y1) + 2):
            ax.plot([x0, x1], [lat, lat], color=(1, 1, 1, .07), lw=0.5, zorder=0)
        ax.plot([x0 + 0.04 * (x1 - x0), x1 - 0.02 * (x1 - x0)], [0, 0], color=theme.ORO, lw=0.9, ls=(0, (1.2, 3.2)),
                zorder=1, solid_capstyle="round", alpha=.85)
        shapes = [_shape(geo.rings("provincia", c, level=3, inset=True)) for c in provinces]
        ax.add_collection(PathCollection([s for s in shapes if s is not None], facecolors=(1, 1, 1, .09),
                                         edgecolors=(1, 1, 1, .34), linewidths=0.5, zorder=2))
        chosen = [_shape(geo.rings(layer, c, level=3, inset=True)) for c in selected if c in geo.features(layer)]
        chosen = [s for s in chosen if s is not None]
        if chosen:
            ax.add_collection(PathCollection(chosen, facecolors="none", edgecolors=(248 / 255, 192 / 255, 24 / 255, .35),
                                             linewidths=4.0, zorder=3))
            ax.add_collection(PathCollection(chosen, facecolors=theme.ORO, edgecolors="#FFF3C4", linewidths=0.6, zorder=4))
        ax.add_patch(Rectangle((gx0, gy0), gx1 - gx0, gy1 - gy0, fill=False, ec=(1, 1, 1, .3), lw=0.7, ls=(0, (2, 2.5)), zorder=1))
        return _png(fig, transparent=True, dpi=dpi)


def columns_png(labels: list[str], values: list[float], *, mode: str = "light", width: float = 7.2, height: float = 3.0,
                dpi: int = 220, average: float | None = None, value_text=None, average_text: str = "") -> bytes:
    """Monthly columns with their figures; the mean as a dotted gold line."""
    value_text = value_text or (lambda v: number(v))
    night = mode == "night"
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="none" if night else "#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0.02, 0.13, 0.96, 0.8])
        ax.set_axis_off()
        peak = max(values or [1]) or 1
        color = theme.NIGHT_SEQUENTIAL[-2] if night else theme.SERIE_BONOS
        track = (1, 1, 1, .06) if night else "#F1EEF6"
        ink = "#EFE8FA" if night else theme.TINTA
        muted = "#CDBFE6" if night else MUTED
        positions = list(range(len(values)))
        ax.bar(positions, [peak * 1.12] * len(values), width=0.62, color=track, zorder=1)
        ax.bar(positions, values, width=0.62, color=color, zorder=2)
        for index, (label, value) in enumerate(zip(labels, values)):
            ax.text(index, value + peak * 0.03, value_text(value), ha="center", va="bottom", color=ink,
                    fontproperties=font("Bold", size=8.2), zorder=4)
            ax.text(index, -peak * 0.05, label, ha="center", va="top", color=muted, fontproperties=font("SemiBold", size=8))
        if average:
            ax.plot([-0.5, len(values) - 0.5], [average, average], color=theme.ORO, lw=1.2, ls=(0, (1.2, 3)), zorder=3,
                    solid_capstyle="round")
            if average_text:
                ax.text(len(values) - 0.5, average + peak * 0.02, average_text, ha="right", va="bottom",
                        color=(theme.ORO if night else theme.ORO_700), fontproperties=font("SemiBold", size=7.4), zorder=4)
        ax.set_xlim(-0.6, len(values) - 0.4)
        ax.set_ylim(-peak * 0.02, peak * 1.2)
        return _png(fig, transparent=night, dpi=dpi)
