"""Publication maps rendered with matplotlib for every report format.

Maps use the institutional palette and the bundled Montserrat / Public Sans
fonts, so the one-page summary, the slides and the data workbook show identical
figures without depending on installed fonts.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import RLock

import matplotlib
matplotlib.use("Agg")
from matplotlib import patheffects
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch, PathPatch, Rectangle
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


def _compact(value: float) -> str:
    if value >= 1_000_000:
        return f"{number(value / 1_000_000, 1)} M"
    if value >= 10_000:
        return f"{number(value / 1000, 0)} mil"
    return number(value)


def _path_for(feature) -> MPath:
    vertices, codes = [], []
    for polygon in geo.polygons(feature):
        for ring in polygon:
            if len(ring) < 3:
                continue
            vertices += [tuple(p) for p in ring] + [tuple(ring[0])]
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 1) + [MPath.CLOSEPOLY]
    return MPath(vertices, codes)


def map_png(values: dict[str, float | None], *, mode: str = "light", selected: set[str] | None = None,
            label: str = "Cobertura reportada", money: bool = False, annotate: int = 5,
            width: float = 6.6, height: float = 5.6, dpi: int = 220, legend: bool = True, scale: str = "linear") -> bytes:
    """Choropleth of Ecuador with the Galápagos inset and the equator.

    ``light`` is for white pages (linear purple ramp, labelled leaders);
    ``night`` returns a transparent image for purple covers.  ``quantile``
    orders provinces instead of measuring them and is only used without a
    numeric legend.
    """
    selected = selected or set()
    collection = geo.provinces(inset=True)
    present = {c: v for c, v in values.items() if v is not None and v == v and c != geo.NO_POLYGON}
    vmax = max(present.values()) if present and max(present.values()) > 0 else 1.0
    night = mode == "night"
    stops = theme.NIGHT_SEQUENTIAL if night else theme.SEQUENTIAL[1:]
    if scale == "quantile" and present:
        ranked = sorted(set(present.values()))
        steps = max(1, len(ranked) - 1)
        present_t = {c: ranked.index(v) / steps for c, v in present.items()}
    else:
        present_t = {c: v / vmax for c, v in present.items()}
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="none" if night else "#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        x0, y0, x1, y1 = geo.bounds(collection)
        gx0, gy0, gx1, gy1 = geo.galapagos_frame()
        ax.set_xlim(min(x0, gx0) - 0.2, x1 + 0.25)
        ax.set_ylim(y0 - (1.25 if legend and not night else 0.25), max(y1, gy1) + 0.45)
        ax.set_aspect("equal")
        stroke = theme.MORADO_900 if night else "#FFFFFF"
        ax.plot([gx0 - 0.15, x1 + 0.2], [0, 0], color=theme.ORO, lw=1.1, ls=(0, (1.2, 3.2)), zorder=1, solid_capstyle="round")
        for feature in collection["features"]:
            code = feature["properties"]["codigo"]
            value = present.get(code)
            if code in selected:
                color = theme.ORO
            elif value is None:
                color = "#3A2563" if night else "#F1EEF6"
            else:
                color = theme.ramp_at(present_t[code], stops)
            ax.add_patch(PathPatch(_path_for(feature), facecolor=color, edgecolor=stroke, lw=0.7, zorder=2, joinstyle="round"))
        frame_color = (1, 1, 1, .5) if night else theme.LILA_300
        ax.add_patch(Rectangle((gx0, gy0), gx1 - gx0, gy1 - gy0, fill=False, ec=frame_color, lw=0.8, ls=(0, (2, 2.5)), zorder=1))
        ax.text(gx0 + 0.05, gy1 + 0.12, "Galápagos (recuadro)", color=("#E6DDF5" if night else MUTED), fontproperties=font("Medium", size=7.5))
        ax.text(x1 + 0.2, 0.1, "Latitud 0°", ha="right", va="bottom", color=(theme.ORO if night else theme.ORO_700), fontproperties=font("SemiBold", size=7))
        if annotate and present:
            points = geo.label_points(inset=True)
            leaders = sorted(present.items(), key=lambda kv: -kv[1])[:annotate]
            names = geo.names()
            halo = [patheffects.withStroke(linewidth=2.6, foreground=(theme.MORADO_900 if night else "#FFFFFF"))]
            for code, value in leaders:
                if code not in points:
                    continue
                px, py = points[code]
                text_value = (number(value / 1e6, 1) + " M") if money else _compact(value)
                ax.text(px, py + 0.06, names.get(code, code), ha="center", va="bottom", color=("#FFFFFF" if night else theme.MORADO_900),
                        fontproperties=font("Bold", display=True, size=7.2), path_effects=halo, zorder=5)
                ax.text(px, py - 0.04, text_value, ha="center", va="top", color=("#F8E3A6" if night else theme.TINTA),
                        fontproperties=font("SemiBold", size=6.8), path_effects=halo, zorder=5)
        if legend and not night:
            cmap = LinearSegmentedColormap.from_list("mtdh", stops)
            lx0, ly0, lw, lh = min(x0, gx0) + 0.05, y0 - 0.85, 3.4, 0.16
            for i in range(60):
                ax.add_patch(Rectangle((lx0 + lw * i / 60, ly0), lw / 60 + 0.01, lh, color=cmap(i / 59), lw=0, zorder=3))
            ax.add_patch(FancyBboxPatch((lx0, ly0), lw, lh, boxstyle="round,pad=0,rounding_size=0.05", fill=False, ec="#E4DEEE", lw=0.5, zorder=4))
            top = (number(vmax / 1e6, 1) + " M") if money else _compact(vmax)
            ax.text(lx0, ly0 - 0.1, "0", ha="left", va="top", color=MUTED, fontproperties=font(size=7))
            ax.text(lx0 + lw, ly0 - 0.1, top, ha="right", va="top", color=MUTED, fontproperties=font(size=7))
            ax.text(lx0, ly0 + lh + 0.08, label + (" (millones de USD)" if money else ""), ha="left", va="bottom", color=INK,
                    fontproperties=font("SemiBold", size=7.6))
        return _png(fig, transparent=night, dpi=dpi)
