"""Publication charts using the exact same report context as the tables."""
from __future__ import annotations

from io import BytesIO
from threading import RLock
from textwrap import fill

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.ticker import FuncFormatter

from .context import number

PURPLE = "#512F8D"
NAVY = "#172849"
LAVENDER = "#AB97D2"
BLUE = "#4877B4"
INK = "#20202B"
_LOCK = RLock()


def bar_chart(rows, field="people", label="Registros reportados", limit=8, width=8.0, height=3.1, color=PURPLE):
    """Return a self-contained PNG; zero is shown, missing is omitted and noted."""
    chosen = [r for r in rows if r.get(field) is not None][:limit]
    with _LOCK:
        fig = Figure(figsize=(width, height), dpi=180, facecolor="#FFFFFF")
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        if not chosen:
            ax.text(.5, .5, "Información no disponible", ha="center", va="center", transform=ax.transAxes, color=INK, fontsize=12)
            ax.set_axis_off()
        else:
            labels = [fill(r["label"], 31 if width > 6 else 20) for r in chosen][::-1]
            values = [r[field] for r in chosen][::-1]
            colors = [LAVENDER] * len(chosen)
            colors[-1] = color
            ax.barh(labels, values, color=colors, height=.55, zorder=3)
            vmax = max(values) or 1
            ax.set_xlim(0, vmax * 1.27)
            for index, value in enumerate(values):
                ax.text(value + vmax * .018, index, number(value), va="center", ha="left", fontsize=8.4, color=INK)
            ax.tick_params(axis="y", labelsize=8.6, length=0, pad=9, labelcolor=INK)
            ax.tick_params(axis="x", labelsize=7.8, length=0, pad=7, labelcolor="#777382")
            ax.xaxis.set_major_formatter(FuncFormatter(lambda n, pos: f"{number(n / 1000, 0)} mil" if vmax >= 10000 else number(n)))
            ax.xaxis.grid(True, color="#EEEAF4", zorder=0, linewidth=.6)
            ax.set_xlabel(label, fontsize=8.2, color="#6C6879", labelpad=9)
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.set_axisbelow(True)
        fig.tight_layout(pad=1.4)
        out = BytesIO()
        fig.savefig(out, format="png", dpi=180, facecolor=fig.get_facecolor())
        return out.getvalue()
