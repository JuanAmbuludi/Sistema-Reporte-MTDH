"""Charts of the Riesgos documents, in the visual language of the dashboard.

Each question keeps one kind of chart in the dashboard, the summary and the slides: where services were suspended (a
treemap of provinces and cantons coloured by service, and a donut by service), when alerts were registered (daily
columns over the running total), where kits arrived (a lollipop of each province beside every delivery in time) and the
stages of the contingency bonus (100 % strips by province, drawn natively by each document).  Services keep one colour
everywhere: Desarrollo Infantil (CDI) purple and Creciendo con Nuestros Hijos (CNH) lilac.
"""
from __future__ import annotations

from datetime import datetime

from matplotlib import patheffects
from matplotlib.patches import FancyBboxPatch
from matplotlib.textpath import TextToPath

from src import theme, ui
from .charts import _LOCK, INK, MUTED, Figure, FigureCanvasAgg, _png, font
from .context import number

SERVICE_TONES = {"Desarrollo Infantil": theme.MORADO, "CDI": theme.MORADO, "Creciendo con Nuestros Hijos (CNH)": theme.LILA_300,
                 "CNH": theme.LILA_300}
PROVINCE_TONES = {"Guayas": theme.MORADO, "Esmeraldas": theme.VIOLETA_500, "El Oro": theme.LILA_300, "Los Ríos": theme.FUCSIA_700,
                  "Imbabura": theme.FUCSIA_300, "Manabí": theme.ORO, "Azuay": theme.MORADO_900}
LIGHT = {theme.LILA_300, theme.LILA_200, theme.LILA_100, theme.ORO, theme.FUCSIA_300, theme.LILA_50}


_MEASURE = TextToPath()


def _width(text: str, weight: str, size: float) -> float:
    """Width in inches of ``text`` set in the institutional face of the charts."""
    return _MEASURE.get_text_width_height_descent(text, font(weight, size=size), ismath=False)[0] / 72


def _fits(text: str, size: float, width: float, weight: str = "Bold") -> bool:
    """Whether ``text`` at ``size`` points fits ``width`` inches."""
    return _width(text, weight, size) <= width


def tone(service: str) -> str:
    return SERVICE_TONES.get(service, theme.VIOLETA_500)


def ink(color: str) -> str:
    return theme.MORADO_900 if color in LIGHT else "#FFFFFF"


def short_service(name: str) -> str:
    return {"Creciendo con Nuestros Hijos (CNH)": "CNH", "Desarrollo Infantil": "Desarrollo Infantil"}.get(name, name)


def pct(value: float, total: float) -> str:
    return f"{number(value / total * 100 if total else 0, 1)} %"


# ------------------------------------------------------------------------------------------------ treemap
def _layout(sizes, x, y, dx, dy):
    covered = sum(sizes)
    rects = []
    if dx >= dy:
        width = covered / dy
        for size in sizes:
            rects.append((x, y, width, size / width))
            y += size / width
    else:
        height = covered / dx
        for size in sizes:
            rects.append((x, y, size / height, height))
            x += size / height
    return rects


def _leftover(sizes, x, y, dx, dy):
    covered = sum(sizes)
    if dx >= dy:
        width = covered / dy
        return x + width, y, dx - width, dy
    height = covered / dx
    return x, y + height, dx, dy - height


def _worst(sizes, x, y, dx, dy):
    return max(max(w / h, h / w) for _x, _y, w, h in _layout(sizes, x, y, dx, dy))


def squarify(values: list[float], x: float, y: float, dx: float, dy: float) -> list[tuple]:
    """Squarified treemap (Bruls, Huizing and van Wijk): rectangles for ``values`` (sorted from the largest) in the box."""
    total = sum(values)
    if not values or total <= 0 or dx <= 0 or dy <= 0:
        return []
    sizes = [v * dx * dy / total for v in values]

    def place(sizes, x, y, dx, dy):
        if not sizes:
            return []
        if len(sizes) == 1:
            return _layout(sizes, x, y, dx, dy)
        i = 1
        while i < len(sizes) and _worst(sizes[:i], x, y, dx, dy) >= _worst(sizes[:i + 1], x, y, dx, dy):
            i += 1
        current = sizes[:i]
        return _layout(current, x, y, dx, dy) + place(sizes[i:], *_leftover(current, x, y, dx, dy))
    return place(sizes, x, y, dx, dy)


def treemap_png(groups: list[dict], width: float, height: float, *, dpi: int = 220, scale: float = 1.0) -> bytes:
    """Suspended units: provinces (with their total) holding their cantons, each tile in the colour of its service.

    ``groups`` items carry ``province``, ``canton``, ``service`` and ``units``."""
    provinces: dict[str, list[dict]] = {}
    for g in groups:
        provinces.setdefault(g["province"], []).append(g)
    order = sorted(provinces, key=lambda p: -sum(g["units"] for g in provinces[p]))
    total = sum(g["units"] for g in groups) or 1
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, width)
        ax.set_ylim(0, height)
        ax.set_axis_off()
        gap = 0.035
        head = 0.2 * scale
        for province, (x, y, w, h) in zip(order, squarify([sum(g["units"] for g in provinces[p]) for p in order], 0, 0, width, height)):
            top = height - y
            units = sum(g["units"] for g in provinces[province])
            ax.add_patch(FancyBboxPatch((x + gap, top - h + gap), w - 2 * gap, h - 2 * gap, boxstyle="round,pad=0,rounding_size=0.05",
                                        fc=theme.LILA_50, ec="none"))
            label = f"{province} · {units} UA · {pct(units, total)}"
            size = 7.6 * scale
            while size > 5.2 * scale and not _fits(label, size, w - 0.16):
                size -= 0.2 * scale
            ax.text(x + 0.08, top - 0.06 - head / 2, label if _fits(label, size, w - 0.16) else province, ha="left", va="center",
                    color=theme.MORADO_900, fontproperties=font("Bold", size=size))
            inner = (x + 0.06, y + head + 0.02, w - 0.12, h - head - 0.08)
            leaves = sorted(provinces[province], key=lambda g: -g["units"])
            for leaf, (lx, ly, lw, lh) in zip(leaves, squarify([g["units"] for g in leaves], *inner)):
                color = tone(leaf["service"])
                ltop = height - ly
                ax.add_patch(FancyBboxPatch((lx + gap, ltop - lh + gap), lw - 2 * gap, lh - 2 * gap,
                                            boxstyle="round,pad=0,rounding_size=0.04", fc=color, ec="none"))
                _leaf_label(ax, leaf, lx, ltop, lw, lh, color, scale)
        return _png(fig, dpi=dpi)


def _leaf_label(ax, leaf: dict, lx: float, ltop: float, lw: float, lh: float, color: str, scale: float) -> None:
    """The name of a tile (its canton, or its service when the source gives no canton) with its service and units, in
    two lines or, in a narrow tile, three; the font steps down before the words give way to the units alone."""
    service, units = short_service(leaf["service"]), f"{leaf['units']} UA"
    layouts = [[leaf["canton"], f"{service} · {units}"], [leaf["canton"], service, units]] if leaf["canton"] else [[service, units]]
    room = lw - 0.14
    for size in (6.8 * scale, 6.4 * scale, 6.0 * scale, 5.6 * scale):
        step = size * 1.42 / 72
        for lines in layouts:
            sizes = [size] + [size * 0.93] * (len(lines) - 1)
            weights = ["Bold"] + ["Medium"] * (len(lines) - 1)
            if len(lines) * step + 0.1 <= lh and all(_fits(t, z, room, w) for t, z, w in zip(lines, sizes, weights)):
                y = ltop - 0.08
                for text, z, w in zip(lines, sizes, weights):
                    ax.text(lx + 0.07, y, text, ha="left", va="top", color=ink(color), fontproperties=font(w, size=z))
                    y -= step
                return
    if lw > 0.16 and lh > 0.14:
        ax.text(lx + lw / 2, ltop - lh / 2, str(leaf["units"]), ha="center", va="center", color=ink(color),
                fontproperties=font("Bold", size=6.2 * scale))


# -------------------------------------------------------------------------------------------------- donut
def donut_png(rows: list[dict], width: float, height: float, *, label: str = "UA suspendidas", dpi: int = 220,
              scale: float = 1.0) -> bytes:
    """Share of each service, with the total at the centre and the legend under the ring."""
    total = sum(r["value"] for r in rows) or 1
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="#FFFFFF")
        FigureCanvasAgg(fig)
        legend_h = 0.22 * scale * max(1, len(rows))
        side = min(width, height - legend_h - 0.05)
        ax = fig.add_axes([(1 - side / width) / 2, (legend_h + 0.05) / height, side / width, side / height])
        ax.pie([r["value"] for r in rows], colors=[tone(r["name"]) for r in rows], startangle=90, counterclock=False,
               wedgeprops=dict(width=0.34, edgecolor="#FFFFFF", linewidth=2.2))
        ax.set_aspect("equal")
        ax.text(0, 0.1, number(total), ha="center", va="center", color=theme.MORADO_900, fontproperties=font("Bold", size=17 * scale, display=True))
        ax.text(0, -0.2, label, ha="center", va="center", color=MUTED, fontproperties=font("Medium", size=6.6 * scale))
        for index, r in enumerate(rows):
            y = legend_h - 0.17 * scale - index * 0.22 * scale
            fig.patches.append(FancyBboxPatch((0.12 / width, y / height), 0.1 / width, 0.1 / height, boxstyle="round,pad=0,rounding_size=0.01",
                                              fc=tone(r["name"]), ec="none", transform=fig.transFigure, figure=fig))
            fig.text(0.28 / width, (y + 0.05) / height, f"{short_service(r['name'])}", ha="left", va="center", color=INK,
                     fontproperties=font("SemiBold", size=7 * scale))
            fig.text(1 - 0.08 / width, (y + 0.05) / height, f"{number(r['value'])} UA · {pct(r['value'], total)}", ha="right", va="center",
                     color=INK, fontproperties=font("Bold", size=7 * scale))
        return _png(fig, dpi=dpi)


# ------------------------------------------------------------------------------------------------ evolution
def evolution_png(rows: list[dict], width: float, height: float, *, dpi: int = 220, scale: float = 1.0) -> bytes:
    """Alerts registered each day (gold columns) over their running total (purple area), from the first day of the follow-up."""
    totals, daily = [r["total"] for r in rows], [r["daily"] for r in rows]
    peak = max(totals + [1])
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0.055, 0.15, 0.93, 0.8])
        xs = list(range(len(rows)))
        ax.fill_between(xs, totals, step="post", color=theme.LILA_100, alpha=0.6, lw=0, zorder=1)
        ax.step(xs, totals, where="post", color=theme.MORADO, lw=1.7, zorder=2)
        ax.bar(xs, daily, width=0.66, color=theme.ORO, zorder=3)
        halo = [patheffects.withStroke(linewidth=2.6, foreground="#FFFFFF")]
        for i, value in enumerate(daily):
            if value:
                ax.text(i, value + peak * 0.05, f"+{value}", ha="center", va="bottom", color=theme.ORO_700,
                        fontproperties=font("Bold", size=7.2 * scale), zorder=5, path_effects=halo)
        if xs:
            ax.text(xs[-1], totals[-1] + peak * 0.07, f"{totals[-1]} alertas", ha="right", va="bottom", color=theme.MORADO_900,
                    fontproperties=font("Bold", size=7.8 * scale), zorder=5, path_effects=halo)
        ax.axvline(0, color=theme.LILA_200, lw=0.9, ls=(0, (2, 2)), zorder=0)
        ticks = [i for i in xs if i % 7 == 0]
        if xs and ticks and xs[-1] - ticks[-1] > 2:
            ticks.append(xs[-1])
        labels = []
        for i in ticks:
            day = datetime.strptime(rows[i]["date"], "%d/%m/%Y")
            labels.append(f"{day.day} {ui._MONTHS_SHORT[day.month - 1]}")
        ax.set_xticks(ticks)
        ax.set_xticklabels(labels, fontproperties=font("SemiBold", size=6.8 * scale), color=MUTED)
        step = max(1, round(peak / 4))
        yticks = list(range(0, int(peak * 1.3) + 1, step))
        ax.set_yticks(yticks)
        ax.set_yticklabels([str(t) for t in yticks], fontproperties=font(size=6.6 * scale), color=MUTED)
        ax.set_ylim(0, peak * 1.34)
        ax.set_xlim(-0.8, len(xs) - 0.2)
        ax.grid(axis="y", color="#EEEAF4", lw=0.6, zorder=0)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0, pad=3)
        return _png(fig, dpi=dpi)


# ----------------------------------------------------------------------------------------------------- kits
def kits_png(provinces: list[dict], deliveries: list[dict], since: str | None, width: float, height: float, *, dpi: int = 220,
             scale: float = 1.0) -> bytes:
    """Kits of each province (a lollipop with its total and share) beside every delivery in time (a circle sized by its kits).

    ``provinces`` items carry ``provincia`` and ``kits`` (sorted from the largest); ``deliveries`` carry ``date``
    (dd/mm/aaaa), ``province`` and ``kits``."""
    names = [p["provincia"] for p in provinces]
    total = sum(p["kits"] for p in provinces) or 1
    peak = max([p["kits"] for p in provinces] or [1])
    rows = {name: len(names) - 1 - i for i, name in enumerate(names)}
    dated = [(datetime.strptime(d["date"], "%d/%m/%Y"), d) for d in deliveries if d.get("date", "").count("/") == 2]
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=dpi, facecolor="#FFFFFF")
        FigureCanvasAgg(fig)
        label_w = 1.62 * scale / width
        left_w = 0.36 if dated else 0.98 - label_w
        # Margins in inches keep room for the titles above and the dates below whatever the height of the figure.
        bottom = 0.3 * scale / height
        span = 1 - bottom - 0.26 * scale / height
        ax = fig.add_axes([label_w, bottom, left_w, span])
        for name in names:
            y = rows[name]
            value = next(p["kits"] for p in provinces if p["provincia"] == name)
            ax.plot([0, value], [y, y], color=theme.LILA_200, lw=1.6, solid_capstyle="round", zorder=1)
            ax.scatter([value], [y], s=34 * scale, color=theme.MORADO, edgecolors="#FFFFFF", linewidths=1, zorder=2)
            ax.text(value + peak * 0.04, y, f"{number(value)} · {pct(value, total)}", ha="left", va="center", color=INK,
                    fontproperties=font("SemiBold", size=6.5 * scale))
        ax.set_yticks(list(rows.values()))
        ax.set_yticklabels(list(rows.keys()), fontproperties=font("Medium", size=6.7 * scale), color=INK)
        ax.set_xlim(0, peak * 1.62)
        ax.set_ylim(-0.7, len(names) - 0.3)
        ax.set_xticks([])
        ax.set_title("Total por provincia", loc="left", fontproperties=font("Bold", size=7.4 * scale), color=theme.MORADO_900, pad=4)
        for side in ("top", "right", "left", "bottom"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=0, pad=4)
        if dated:
            bx = fig.add_axes([label_w + left_w + 0.02, bottom, 0.98 - label_w - left_w - 0.02, span], sharey=ax)
            biggest = max(d["kits"] for _day, d in dated) or 1
            bx.scatter([day for day, _d in dated], [rows.get(d["province"], -5) for _day, d in dated],
                       s=[8 + 260 * scale * (d["kits"] / biggest) for _day, d in dated], color=theme.VIOLETA_500, alpha=0.7,
                       edgecolors="#FFFFFF", linewidths=0.6, zorder=2)
            start = min(day for day, _d in dated)
            end = max(day for day, _d in dated)
            if since:
                mark = datetime.strptime(since, "%d/%m/%Y")
                if start <= mark <= end:
                    bx.axvline(mark, color=theme.ORO, lw=1, ls=(0, (2, 2)), zorder=1)
                    bx.text(mark, -0.62, " Inicio del seguimiento de alertas", ha="left", va="bottom", color=theme.ORO_700,
                            fontproperties=font("SemiBold", size=6.2 * scale))
            from datetime import timedelta
            ticks, tick = [], start
            while tick <= end:
                ticks.append(tick)
                tick += timedelta(days=14)
            bx.set_xticks(ticks)
            bx.set_xticklabels([f"{t.day} {ui._MONTHS_SHORT[t.month - 1]}" for t in ticks], fontproperties=font("SemiBold", size=6.4 * scale),
                               color=MUTED)
            bx.set_xlim(start - timedelta(days=3), end + timedelta(days=3))
            bx.grid(axis="x", color="#EEEAF4", lw=0.6, zorder=0)
            bx.tick_params(axis="y", left=False, labelleft=False)
            bx.tick_params(length=0, pad=3)
            bx.set_title("Entregas en el tiempo · tamaño: kits", loc="left", fontproperties=font("Bold", size=7.4 * scale),
                         color=theme.MORADO_900, pad=4)
            for side in ("top", "right", "left", "bottom"):
                bx.spines[side].set_visible(False)
        return _png(fig, dpi=dpi)
