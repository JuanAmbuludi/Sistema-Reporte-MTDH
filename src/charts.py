"""Plotly figures with the institutional style and formal, Spanish-formatted labels.

Every chart takes an ``Indicator`` (see ``src/indicators.py``) instead of a fixed column, so the same figures
serve transfers, services and any family of indicators added later.  One colour per chart, magnitudes on a
single purple ramp, selected provinces in the gold of the national coat of arms.  Axes are fixed so a swipe
over a chart scrolls the page on phones.
"""
from __future__ import annotations

from textwrap import wrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src import geo, theme
from src.indicators import Indicator
from src.ui import number, pct

BAR = theme.SERIE_BONOS
PREVIOUS = theme.ACUMULADO_PREVIO
GRID = "#EEEAF4"
AXIS_TEXT = "#6E6880"


def fmt_value(value, indicator: Indicator) -> str:
    """Exact figure for hovers: 400.208 beneficiarios · USD 55,87 millones · USD 83.681 · 71,0 %."""
    if value is None or pd.isna(value):
        return "—"
    if indicator.is_money:
        return f"USD {number(float(value) / 1e6, 2)} millones" if abs(float(value)) >= 1e6 else f"USD {number(value)}"
    if indicator.is_rate:
        return pct(value)
    return f"{number(value)} {indicator.unit}".strip()


def short_value(value, indicator: Indicator) -> str:
    """Bar labels with their unit: 400.208 · USD 55,9 M · USD 83.681 · 71,0 %."""
    if value is None or pd.isna(value):
        return "—"
    if indicator.is_rate:
        return pct(value)
    if indicator.is_money:
        return f"USD {number(float(value) / 1e6, 1)} M" if abs(float(value)) >= 1e6 else f"USD {number(value)}"
    return number(value)


def money_text(value, decimals: int = 1) -> str:
    """USD 1.011,2 M."""
    if value is None or pd.isna(value):
        return "—"
    return f"USD {number(float(value) / 1e6, decimals)} M"


def base(fig: go.Figure, height: int = 390, margin: dict | None = None) -> go.Figure:
    fig.update_layout(
        template="none", height=height, autosize=True,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=theme.WEB_FONT_STACK, size=12, color=theme.TINTA),
        margin=margin or dict(l=8, r=24, t=12, b=30),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=theme.LILA_200, align="left",
                        font=dict(family=theme.WEB_FONT_STACK, color=theme.TINTA, size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12, color=theme.PIZARRA),
                    itemclick=False, itemdoubleclick=False),
        separators=",.", dragmode=False, hovermode="closest",
        transition=dict(duration=450, easing="cubic-in-out"),
        modebar=dict(bgcolor="rgba(0,0,0,0)", color="#9A90AC", activecolor=theme.MORADO),
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False, ticks="", showline=False,
                     fixedrange=True, tickfont=dict(size=11, color=AXIS_TEXT), title_font=dict(size=11, color=AXIS_TEXT))
    fig.update_yaxes(showgrid=False, zeroline=False, ticks="", showline=False, automargin=True, ticklabelstandoff=6,
                     fixedrange=True, tickfont=dict(size=12, color=theme.TINTA))
    return fig


def _bar_height(count: int, per: int = 40, minimum: int = 260) -> int:
    return max(minimum, count * per + 60)


def _by_category(data: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return data.groupby(["programa_id", "programa"], as_index=False, observed=True)[keys].sum(min_count=1)


def category_bars(data: pd.DataFrame, indicator: Indicator, names: dict[str, str] | None = None) -> go.Figure:
    """One indicator per program or service, largest on top, in a single colour."""
    names = names or {}
    group = _by_category(data, [indicator.key])
    # Programs without any value (pensions that only keep a previous accumulation) would read as empty bars.
    group = group.loc[pd.to_numeric(group[indicator.key], errors="coerce").fillna(0).gt(0)] if group[indicator.key].fillna(0).gt(0).any() else group
    group = group.sort_values(indicator.key, ascending=True, na_position="first")
    total = group[indicator.key].sum()
    labels = [names.get(p, p) for p in group.programa]
    values = group[indicator.key] / (1e6 if indicator.is_money else 1)
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=BAR, cornerradius=5, line=dict(width=0)),
        text=[short_value(v, indicator) for v in group[indicator.key]], textposition="outside", cliponaxis=False,
        textfont=dict(size=12, color=theme.TINTA),
        customdata=np.stack([group.programa.to_numpy(), [fmt_value(v, indicator) for v in group[indicator.key]],
                             [pct(v / total * 100 if total else 0) for v in group[indicator.key].fillna(0)]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} del total<extra></extra>",
    ))
    base(fig, _bar_height(len(group)), dict(l=8, r=70, t=8, b=16))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(categoryorder="array", categoryarray=labels)
    fig.update_layout(bargap=0.36, showlegend=False)
    return fig


def resources_stack(data: pd.DataFrame, money: dict[str, Indicator], names: dict[str, str] | None = None) -> go.Figure:
    """Previous accumulation plus the period's budget; the bar end is the government accumulation."""
    names = names or {}
    keys = [money["previous"].key, money["fiscal"].key, money["government"].key]
    group = _by_category(data, keys).sort_values(money["government"].key, ascending=True)
    labels = [names.get(p, p) for p in group.programa]
    fig = go.Figure()
    for role, color in [("previous", PREVIOUS), ("fiscal", BAR)]:
        indicator = money[role]
        fig.add_trace(go.Bar(
            x=group[indicator.key] / 1e6, y=labels, name=indicator.label, orientation="h",
            marker=dict(color=color, cornerradius=4, line=dict(color="#FFFFFF", width=1.5)),
            customdata=np.stack([group.programa.to_numpy(), [fmt_value(v, indicator) for v in group[indicator.key]],
                                 [fmt_value(v, money["government"]) for v in group[money["government"].key]]], axis=1),
            hovertemplate=("<b>%{customdata[0]}</b><br>" + indicator.label + ": %{customdata[1]}<br>"
                           + money["government"].label + ": %{customdata[2]}<extra></extra>"),
        ))
    totals = group[money["government"].key] / 1e6
    fig.add_trace(go.Scatter(x=totals, y=labels, mode="text", text=[f"USD {number(v, 1)} M" for v in totals], textposition="middle right",
                             textfont=dict(size=12, color=theme.TINTA), hoverinfo="skip", showlegend=False, cliponaxis=False))
    base(fig, _bar_height(len(group)), dict(l=8, r=96, t=34, b=36))
    fig.update_layout(barmode="stack", bargap=0.36, legend=dict(traceorder="normal"))
    fig.update_xaxes(title="Millones de USD", tickformat=",.0f", rangemode="tozero")
    fig.update_yaxes(categoryorder="array", categoryarray=labels)
    return fig


def province_values(data: pd.DataFrame, key: str) -> pd.DataFrame:
    group = data.groupby(["provincia_codigo", "provincia"], as_index=False, observed=True)[key].sum(min_count=1)
    total = group[key].sum()
    group["share"] = group[key] / total * 100 if total else 0
    return group


def province_ranking(data: pd.DataFrame, indicator: Indicator, highlight: set[str] | None = None,
                     share_label: str = "del total nacional", height: int | None = None) -> go.Figure:
    """Provinces ranked by an indicator.

    Without ``highlight`` the three leaders carry the series colour; with it, the chosen provinces turn gold
    (as on the map) and keep their national place, written next to the value.
    """
    key = indicator.key
    ranked = province_values(data, key).sort_values(key, ascending=False).reset_index(drop=True)
    # Positions count provinces only; the zone in study keeps its bar but takes no place.
    real = ranked.provincia_codigo.ne(geo.NO_POLYGON)
    ranked["position"] = np.where(real, real.cumsum(), 0)
    provinces_ranked = int(real.sum())
    group = ranked.iloc[::-1]
    values = group[key] / (1e6 if indicator.is_money else 1)
    text = [short_value(v, indicator) for v in group[key]]
    if highlight:
        chosen = group.provincia_codigo.isin(highlight).to_numpy()
        colors = [theme.ORO if c else theme.LILA_200 for c in chosen]
        labels = [f"<b>{name}</b>" if c else name for name, c in zip(group.provincia, chosen)]
        text = [f"<b>{t} · {p}.º</b>" if c and p else (f"<b>{t}</b>" if c else t) for t, p, c in zip(text, group.position, chosen)]
    else:
        leaders = set(ranked.head(3).provincia)
        colors = [BAR if name in leaders else theme.LILA_300 for name in group.provincia]
        labels = list(group.provincia)
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=colors, cornerradius=4),
        text=text, textposition="outside", cliponaxis=False, textfont=dict(size=11, color=theme.TINTA),
        customdata=np.stack([list(group.provincia), [fmt_value(v, indicator) for v in group[key]], [pct(s) for s in group.share],
                             [f"{p}.º de {provinces_ranked} provincias" if p else "Sin posición provincial" for p in group.position]], axis=1),
        hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} " + share_label
                       + "<br>Posición: %{customdata[3]}<extra></extra>"),
    ))
    base(fig, height or max(300, len(group) * 25 + 46), dict(l=8, r=92 if highlight else 64, t=40 if not height else 30, b=10))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(tickfont=dict(size=11.5), categoryorder="array", categoryarray=labels)
    fig.update_layout(bargap=0.28, showlegend=False)
    return fig


def _column_label(name: str, width: int = 11) -> str:
    return "<br>".join(wrap(name, width, break_long_words=False)) or name


def composition_matrix(data: pd.DataFrame, indicator: Indicator, names: dict[str, str] | None = None,
                       highlight: set[str] | None = None, *, rows: tuple[str, str] = ("provincia_codigo", "provincia"),
                       row_word: str = "la provincia", show_values: bool = False) -> go.Figure:
    """Share of each program or service within every territory, territories in descending order.

    ``rows`` names the code and label columns of the territories (provinces by default; cantons or parishes with
    their own columns) and ``row_word`` how a hover refers to one of them.  ``show_values`` writes every share in
    its cell (wide cards).
    """
    names, highlight, key = names or {}, highlight or set(), indicator.key
    code_col, name_col = rows
    grouped = data.groupby([code_col, name_col, "programa_id", "programa"], observed=True)[key].sum(min_count=1).reset_index()
    pivot = grouped.pivot_table(index=name_col, columns="programa", values=key, aggfunc="sum").astype(float)
    order = pivot.sum(axis=1).sort_values(ascending=False).index
    pivot = pivot.reindex(order)
    # Programs without any value for this indicator would only add empty columns.
    columns = [c for c in sorted(pivot.columns, key=lambda c: -np.nansum(pivot[c].to_numpy())) if np.nansum(pivot[c].to_numpy()) > 0]
    pivot = pivot[columns]
    totals = pivot.sum(axis=1).replace(0, np.nan)
    # A program without people in a territory reads 0 % there (not a gap in the matrix).
    shares = pivot.fillna(0).div(totals, axis=0) * 100
    text = [[fmt_value(v, indicator) for v in row] for row in pivot.to_numpy()]
    full = [list(columns) for _ in range(len(pivot))]
    custom = np.dstack([np.array(text, dtype=object), np.array(full, dtype=object)])
    finite = shares.to_numpy()[np.isfinite(shares.to_numpy())]
    zmax = min(100.0, max(10.0, np.ceil((finite.max() if finite.size else 100) / 10) * 10))
    codes = grouped.drop_duplicates(name_col).set_index(name_col)[code_col]
    labels = [f"<b>{p}</b>" if codes.get(p) in highlight else p for p in pivot.index]
    few = len(pivot) <= 4
    written = few or show_values
    fig = go.Figure(go.Heatmap(
        z=shares.to_numpy(), x=[_column_label(names.get(c, c)) for c in columns], y=labels,
        colorscale=[[0, "#FBFAFE"], [0.12, theme.SEQUENTIAL[2]], [0.35, theme.SEQUENTIAL[4]], [0.65, theme.SEQUENTIAL[6]], [1, theme.SEQUENTIAL[9]]],
        zmin=0, zmax=zmax, xgap=3 if few else 2, ygap=3 if few else 2, customdata=custom,
        hovertemplate=f"<b>%{{y}}</b><br>%{{customdata[1]}}<br>%{{customdata[0]}}<br>%{{z:.1f}} % de {row_word}<extra></extra>",
        texttemplate="%{z:.1f} %" if written else None, textfont=dict(size=12 if few else 11, family=theme.WEB_FONT_STACK),
        showscale=not few,
        colorbar=dict(title=dict(text=f"% de {row_word}", side="top", font=dict(size=11, color=AXIS_TEXT)), thickness=10, len=0.5,
                      ticksuffix=" %", outlinewidth=0, tickfont=dict(size=10, color=AXIS_TEXT)),
    ))
    head = 14 * max(len(_column_label(names.get(c, c)).split("<br>")) for c in columns) + 16 if columns else 40
    per_row = 27 if show_values and not few else 25
    base(fig, len(pivot) * 58 + head + 20 if few else max(320, len(pivot) * per_row + head + 12), dict(l=8, r=8, t=head, b=6))
    fig.update_xaxes(side="top", showgrid=False, tickangle=0, tickfont=dict(size=10.5, color=theme.TINTA))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11.5))
    return fig


def execution_bullets(rows: pd.DataFrame, label: str, *, highlight=None, reference: float | None = None,
                      reference_label: str = "Total", hover_label: str | None = None, wrap_at: int = 0,
                      per: int = 36, height: int | None = None) -> go.Figure:
    """Budget execution of each row as a bar on a 0–100 % track, largest coded budget on top.

    ``rows`` carries ``presupuesto_codificado``, ``presupuesto_ejecutado`` and ``porcentaje_ejecucion``; ``label``
    names the column shown on the axis and ``hover_label`` an optional longer name for the hover.  ``reference`` draws
    the execution of the whole selection, so every row reads above or below it.  ``highlight`` holds labels drawn in
    gold (the territory chosen on the map).
    """
    highlight = set(highlight or ())
    group = rows.loc[rows.presupuesto_codificado.fillna(0) > 0].iloc[::-1]
    labels = ["<br>".join(wrap(str(t), wrap_at, break_long_words=False)) if wrap_at else str(t) for t in group[label]]
    rates = group.porcentaje_ejecucion.fillna(0).clip(lower=0)
    chosen = group[label].isin(highlight).to_numpy()
    colors = [theme.ORO if c else BAR for c in chosen]
    full = group[hover_label] if hover_label else group[label]
    custom = np.stack([full.astype(str).to_numpy(), [pct(v) for v in group.porcentaje_ejecucion],
                       [fmt_money(v) for v in group.presupuesto_ejecutado], [fmt_money(v) for v in group.presupuesto_codificado]], axis=1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[100] * len(group), y=labels, orientation="h", marker=dict(color="#EEEAF6", cornerradius=5),
                         hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Bar(x=rates.clip(upper=100), y=labels, orientation="h", marker=dict(color=colors, cornerradius=5),
                         customdata=custom, showlegend=False,
                         hovertemplate="<b>%{customdata[0]}</b><br>Ejecución: %{customdata[1]}<br>Devengado: %{customdata[2]}"
                                       "<br>Codificado: %{customdata[3]}<extra></extra>"))
    # The figures sit in a fixed right margin, so they never clip however narrow the plot becomes on a phone.
    fig.add_trace(go.Scatter(x=[101] * len(group), y=labels, mode="text", text=[f" <b>{pct(v)}</b>" if c else f" {pct(v)}"
                                                                               for v, c in zip(group.porcentaje_ejecucion, chosen)],
                             textposition="middle right", textfont=dict(size=12, color=theme.TINTA), hoverinfo="skip",
                             showlegend=False, cliponaxis=False))
    base(fig, height or execution_height(len(group), per), dict(l=8, r=62, t=30 if reference is not None else 8, b=8))
    fig.update_layout(barmode="overlay", bargap=0.42, showlegend=False)
    fig.update_xaxes(range=[0, 101], showticklabels=False, showgrid=False)
    fig.update_yaxes(categoryorder="array", categoryarray=labels, tickfont=dict(size=11.5))
    if reference is not None and pd.notna(reference):
        fig.add_shape(type="line", x0=reference, x1=reference, y0=-0.6, y1=len(group) - 0.4, line=dict(color=theme.ORO_700, width=1.4, dash="dot"))
        fig.add_annotation(x=reference, y=len(group) - 0.4, yshift=4, text=f"{reference_label}: {pct(reference)}", showarrow=False,
                           yanchor="bottom", font=dict(size=11, color=theme.ORO_700))
    return fig


def execution_height(rows: int, per: int = 36) -> int:
    return max(150, rows * per + 66)


def fmt_money(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"USD {number(float(value) / 1e6, 2)} millones"


def ranked_bars(labels: list[str], values: list[float], indicator: Indicator, *, hover: list[str] | None = None,
                share_total: float | None = None, share_label: str = "del total", height: int | None = None) -> go.Figure:
    """Leading places (parishes, units) as horizontal bars, largest on top, in the series colour."""
    labels, values = list(labels)[::-1], list(values)[::-1]
    hover = list(hover)[::-1] if hover else labels
    scaled = [(v or 0) / (1e6 if indicator.is_money else 1) for v in values]
    shares = [pct((v or 0) / share_total * 100) + " " + share_label if share_total else "" for v in values]
    fig = go.Figure(go.Bar(
        x=scaled, y=labels, orientation="h", marker=dict(color=BAR, cornerradius=4),
        text=[short_value(v, indicator) for v in values], textposition="outside", cliponaxis=False,
        textfont=dict(size=11, color=theme.TINTA),
        customdata=np.stack([hover, [fmt_value(v, indicator) for v in values], shares], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>",
    ))
    base(fig, height or max(300, len(labels) * 25 + 46), dict(l=8, r=96 if indicator.is_money else 64, t=30 if height else 10, b=10))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(tickfont=dict(size=11.5), categoryorder="array", categoryarray=labels)
    fig.update_layout(bargap=0.28 if not height else 0.4, showlegend=False)
    return fig


def monthly_columns(months: list[str], values: list[float], *, unit: str = "contratos", average: float | None = None,
                    full_names: list[str] | None = None) -> go.Figure:
    """A monthly series as columns with their figures; ``average`` draws the monthly mean as a reference."""
    full_names = full_names or months
    fig = go.Figure(go.Bar(
        x=months, y=values, marker=dict(color=BAR, cornerradius=5), text=[number(v) for v in values], textposition="outside",
        cliponaxis=False, textfont=dict(size=12, color=theme.TINTA),
        customdata=np.stack([full_names, [f"{number(v)} {unit}" for v in values]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    ))
    base(fig, 380, dict(l=8, r=8, t=34, b=30))
    fig.update_layout(bargap=0.32, showlegend=False)
    fig.update_yaxes(showticklabels=False, showgrid=False, rangemode="tozero", range=[0, max(values or [1]) * 1.18])
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12, color=theme.TINTA))
    if average:
        fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=average, y1=average, line=dict(color=theme.ORO_700, width=1.4, dash="dot"))
        fig.add_annotation(xref="paper", x=1, y=average, yshift=4, text=f"Promedio mensual: {number(average)}", showarrow=False,
                           xanchor="right", yanchor="bottom", font=dict(size=11, color=theme.ORO_700))
    return fig


def compact_number(value) -> str:
    """Axis and label figures: 1,58 M · 453,9 mil · 9.512."""
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    if abs(value) >= 1e6:
        return f"{number(value / 1e6, 2)} M"
    if abs(value) >= 1e4:
        return f"{number(value / 1e3, 1)} mil"
    return number(value)


def month_trend(labels: list[str], values: list[float], *, selected: int | None = None, unit: str = "", full: list[str] | None = None,
                notes: list[str] | None = None, height: int = 330) -> go.Figure:
    """A monthly series as a line with its points; the month of the consultation in gold and labelled.

    The axis starts near the lowest month (not at zero), so month-to-month changes read; every figure stays in the hover.
    """
    full = full or labels
    notes = notes or [""] * len(values)
    present = [v for v in values if v is not None and not pd.isna(v)]
    low, high = (min(present), max(present)) if present else (0, 1)
    pad = max((high - low) * 0.35, high * 0.01, 1)
    colors = [theme.ORO if i == selected else BAR for i in range(len(values))]
    sizes = [13 if i == selected else 8 for i in range(len(values))]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=values, mode="lines+markers", line=dict(color=BAR, width=2.4, shape="linear"),
        marker=dict(color=colors, size=sizes, line=dict(color="#FFFFFF", width=2)),
        customdata=np.stack([full, [f"{number(v)} {unit}".strip() for v in values], notes], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>", showlegend=False,
    ))
    if selected is not None and 0 <= selected < len(values) and values[selected] is not None:
        fig.add_annotation(x=labels[selected], y=values[selected], text=f"<b>{number(values[selected])}</b>", showarrow=False,
                           yshift=18, font=dict(size=12.5, color=theme.MORADO_900), bgcolor="rgba(255,255,255,.85)")
    base(fig, height, dict(l=8, r=14, t=24, b=30))
    ticks = np.linspace(low - pad * 0.6, high + pad * 0.6, 4)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, range=[low - pad, high + pad], tickvals=ticks,
                     ticktext=[compact_number(t) for t in ticks], tickfont=dict(size=11, color=AXIS_TEXT))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=11.5, color=theme.TINTA))
    return fig


def month_columns(labels: list[str], values: list[float], *, selected: int | None = None, money: bool = False, unit: str = "",
                  full: list[str] | None = None, height: int = 330) -> go.Figure:
    """Monthly amounts as columns from zero (money in millions of USD); the month of the consultation in gold."""
    full = full or labels
    scaled = [(v or 0) / (1e6 if money else 1) for v in values]
    # Money columns read in millions with their unit; a small month keeps two decimals instead of «0,0».
    text = [(f"{number(v, 2 if 0 < abs(v) < 0.05 else 1)} M" if money else compact_number(v)) if v else "" for v in scaled]
    hover = [f"USD {number((v or 0) / 1e6, 2)} millones" if money else f"{number(v)} {unit}".strip() for v in values]
    colors = [theme.ORO if i == selected else BAR for i in range(len(values))]
    fig = go.Figure(go.Bar(
        x=labels, y=scaled, marker=dict(color=colors, cornerradius=4), text=text, textposition="outside", cliponaxis=False,
        textfont=dict(size=11, color=theme.TINTA), customdata=np.stack([full, hover], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    ))
    base(fig, height, dict(l=8, r=8, t=24, b=30))
    fig.update_layout(bargap=0.34, showlegend=False)
    fig.update_yaxes(showticklabels=False, showgrid=False, rangemode="tozero", range=[0, max(scaled or [1]) * 1.18 or 1])
    fig.update_xaxes(showgrid=False, tickfont=dict(size=11.5, color=theme.TINTA))
    return fig


def cumulative_execution(labels: list[str], rates: list[float], *, selected: int | None = None, months: list[int] | None = None,
                         full: list[str] | None = None, height: int = 330) -> go.Figure:
    """Accumulated execution of the year month by month, against an even pace (one twelfth of the budget per month)."""
    full = full or labels
    months = months or list(range(1, len(labels) + 1))
    pace = [m / 12 * 100 for m in months]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=pace, mode="lines", name="Ritmo uniforme del año", line=dict(color=theme.LILA_300, width=1.6, dash="dot"),
                             hovertemplate="<b>%{x}</b><br>Ritmo uniforme: %{y:.1f} %<extra></extra>"))
    colors = [theme.ORO if i == selected else BAR for i in range(len(rates))]
    fig.add_trace(go.Scatter(
        x=labels, y=rates, mode="lines+markers", name="Ejecución acumulada", line=dict(color=BAR, width=2.6),
        marker=dict(color=colors, size=[13 if i == selected else 8 for i in range(len(rates))], line=dict(color="#FFFFFF", width=2)),
        customdata=np.stack([full, [pct(r) for r in rates], [pct(p) for p in pace]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>Ejecución acumulada: %{customdata[1]}<br>Ritmo uniforme: %{customdata[2]}<extra></extra>",
    ))
    if selected is not None and 0 <= selected < len(rates) and rates[selected] is not None:
        fig.add_annotation(x=labels[selected], y=rates[selected], text=f"<b>{pct(rates[selected])}</b>", showarrow=False, yshift=18,
                           font=dict(size=12.5, color=theme.MORADO_900), bgcolor="rgba(255,255,255,.85)")
    base(fig, height, dict(l=8, r=14, t=40, b=30))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, range=[0, 105], tickvals=[0, 25, 50, 75, 100], ticksuffix=" %",
                     tickfont=dict(size=11, color=AXIS_TEXT))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=11.5, color=theme.TINTA))
    fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
    return fig


def _thin_ticks(labels: list[str], every: int) -> tuple[list[str], list[str]]:
    """Category ticks every ``every`` labels (the last one always shown)."""
    keep = [i for i in range(len(labels)) if i % every == 0 or i == len(labels) - 1]
    if len(keep) > 1 and keep[-1] - keep[-2] < max(2, every // 2):
        keep.pop(-2)
    return [labels[i] for i in keep], [labels[i] for i in keep]


def history_line(labels: list[str], series: list[tuple[str, list, str]], *, selected: int | None = None, unit: str = "",
                 full: list[str] | None = None, height: int = 330, from_zero: bool = True) -> go.Figure:
    """Several years month by month: one or two lines (the first one carries the month of the consultation in gold).

    ``series`` items are (name, values, colour); labels thin out so a long history stays legible on a phone.
    """
    full = full or labels
    fig = go.Figure()
    for index, (name, values, color) in enumerate(series):
        marker_colors = [theme.ORO if index == 0 and i == selected else color for i in range(len(values))]
        sizes = [12 if index == 0 and i == selected else 5 for i in range(len(values))]
        fig.add_trace(go.Scatter(
            x=labels, y=values, mode="lines+markers", name=name, connectgaps=False,
            line=dict(color=color, width=2.4 if index == 0 else 1.8, dash="solid" if index == 0 else "dot"),
            marker=dict(color=marker_colors, size=sizes, line=dict(color="#FFFFFF", width=1.5)),
            customdata=np.stack([full, [f"{number(v)} {unit}".strip() if v is not None and not pd.isna(v) else "Sin registro" for v in values]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>" + name + ": %{customdata[1]}<extra></extra>",
        ))
    first = series[0][1] if series else []
    if selected is not None and 0 <= selected < len(first) and first[selected] is not None and not pd.isna(first[selected]):
        fig.add_annotation(x=labels[selected], y=first[selected], text=f"<b>{number(first[selected])}</b>", showarrow=False, yshift=16,
                           font=dict(size=12.5, color=theme.MORADO_900), bgcolor="rgba(255,255,255,.85)")
    base(fig, height, dict(l=8, r=14, t=40 if len(series) > 1 else 24, b=30))
    ticks, text = _thin_ticks(labels, 6 if len(labels) > 18 else (3 if len(labels) > 9 else 1))
    fig.update_xaxes(showgrid=False, tickvals=ticks, ticktext=text, tickfont=dict(size=11, color=theme.TINTA))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, rangemode="tozero" if from_zero else "normal", tickformat=",.0f",
                     tickfont=dict(size=11, color=AXIS_TEXT))
    fig.update_layout(showlegend=len(series) > 1, legend=dict(orientation="h", y=1.1, x=0))
    return fig


def history_columns(labels: list[str], values: list[float], *, selected: int | None = None, partial: int | None = None,
                    unit: str = "", money: bool = False, full: list[str] | None = None, height: int = 330) -> go.Figure:
    """Months as columns from zero; the month of the consultation in gold and a partial month in a lighter tone."""
    full = full or labels
    scaled = [(v or 0) / (1e6 if money else 1) for v in values]
    colors = [theme.ORO if i == selected else (theme.LILA_200 if i == partial else BAR) for i in range(len(values))]
    hover = [(f"USD {number((v or 0) / 1e6, 2)} millones" if money else f"{number(v)} {unit}".strip()) + (" · mes en curso" if i == partial else "")
             for i, v in enumerate(values)]
    fig = go.Figure(go.Bar(x=labels, y=scaled, marker=dict(color=colors, cornerradius=3), customdata=np.stack([full, hover], axis=1),
                           hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>"))
    if selected is not None and 0 <= selected < len(values):
        fig.add_annotation(x=labels[selected], y=scaled[selected], text=f"<b>{number(scaled[selected], 1) if money else number(values[selected])}</b>",
                           showarrow=False, yshift=12, font=dict(size=12, color=theme.MORADO_900))
    base(fig, height, dict(l=8, r=8, t=24, b=30))
    ticks, text = _thin_ticks(labels, 6 if len(labels) > 18 else (3 if len(labels) > 9 else 1))
    fig.update_xaxes(showgrid=False, tickvals=ticks, ticktext=text, tickfont=dict(size=11, color=theme.TINTA))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, rangemode="tozero", tickformat=",.1f" if money else ",.0f",
                     tickfont=dict(size=11, color=AXIS_TEXT))
    fig.update_layout(bargap=0.25, showlegend=False)
    return fig


PHASE_COLORS = [theme.LILA_300, theme.VIOLETA_500, theme.SERIE_BONOS]


def grouped_bars(categories: list[str], series: list[tuple[str, list, str]], *, money: bool = True, height: int | None = None) -> go.Figure:
    """Horizontal bars grouped by category (one colour per measure, a legend on top), figures at the bar ends."""
    fig = go.Figure()
    for name, values, color in series:
        scaled = [None if v is None or pd.isna(v) else v / (1e6 if money else 1) for v in values]
        text = ["" if v is None else (f"{number(v, 1)} M" if money else number(v)) for v in scaled]
        fig.add_trace(go.Bar(
            y=categories, x=scaled, name=name, orientation="h", marker=dict(color=color, cornerradius=3), text=text,
            textposition="outside", cliponaxis=False, textfont=dict(size=11, color=theme.TINTA),
            customdata=[[name, f"USD {number((v or 0) / 1e6, 2)} millones" if money else number(v)] for v in values],
            hovertemplate="<b>%{y}</b><br>%{customdata[0]}: %{customdata[1]}<extra></extra>",
        ))
    base(fig, height or max(300, len(categories) * 92 + 70), dict(l=8, r=72, t=40, b=10))
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.08, legend=dict(orientation="h", y=1.1, x=0, traceorder="normal"))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=12))
    return fig


def funnel_bars(steps: list[tuple[str, float, str]], *, height: int | None = None) -> go.Figure:
    """Successive stages of a process (registered, enabled, paid) as bars sharing the first stage as reference."""
    labels = [label for label, _v, _n in steps]
    values = [v for _l, v, _n in steps]
    # Each stage reads against the previous one, with words: «150.000 · 23,5 % de los registrados».
    text = [f"<b>{number(v)}</b>" + (f" · {note}" if i else "") for i, (_l, v, note) in enumerate(steps)]
    colors = [theme.LILA_200, theme.SERIE_BONOS, theme.ORO][:len(steps)]
    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h", marker=dict(color=colors, cornerradius=5), text=text, textposition="outside",
        cliponaxis=False, textfont=dict(size=12, color=theme.TINTA),
        customdata=[[note] for _l, _v, note in steps], hovertemplate="<b>%{y}</b><br>%{customdata[0]}<extra></extra>",
    ))
    base(fig, height or max(240, len(steps) * 74 + 40), dict(l=8, r=230, t=10, b=10))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=12.5))
    fig.update_layout(bargap=0.38, showlegend=False)
    return fig


def phase_columns(labels: list[str], values: list[float], phases: list[int], *, money: bool = False, unit: str = "",
                  full: list[str] | None = None, height: int = 330) -> go.Figure:
    """Months as columns coloured by the phase they belong to (a legend names each phase)."""
    full = full or labels
    fig = go.Figure()
    for phase in sorted(set(phases)):
        index = [i for i, p in enumerate(phases) if p == phase]
        scaled = [(values[i] or 0) / (1e6 if money else 1) for i in index]
        fig.add_trace(go.Bar(
            x=[labels[i] for i in index], y=scaled, name=f"Fase {phase}", marker=dict(color=PHASE_COLORS[(phase - 1) % 3], cornerradius=3),
            text=[(f"{number(v, 2 if 0 < abs(v) < 0.05 else 1)} M" if money else compact_number(v)) if v else "" for v in scaled],
            textposition="outside", cliponaxis=False,
            textfont=dict(size=10.5, color=theme.TINTA),
            customdata=[[full[i], f"USD {number((values[i] or 0) / 1e6, 2)} millones" if money else f"{number(values[i])} {unit}".strip()] for i in index],
            hovertemplate="<b>%{customdata[0]}</b><br>Fase " + str(phase) + ": %{customdata[1]}<extra></extra>",
        ))
    base(fig, height, dict(l=8, r=8, t=40, b=30))
    fig.update_layout(barmode="overlay", bargap=0.3, legend=dict(orientation="h", y=1.1, x=0, traceorder="normal"))
    fig.update_xaxes(showgrid=False, categoryorder="array", categoryarray=labels, tickfont=dict(size=10.5, color=theme.TINTA))
    fig.update_yaxes(showticklabels=False, showgrid=False, rangemode="tozero",
                     range=[0, max([(v or 0) / (1e6 if money else 1) for v in values] or [1]) * 1.2])
    return fig


def change_bars(labels: list[str], changes: list[float], *, unit: str = "", full: list[str] | None = None,
                since: str = "", height: int | None = None) -> go.Figure:
    """Change of each program between two months: increases to the right in purple, decreases to the left in fuchsia."""
    full = full or labels
    order = sorted(range(len(changes)), key=lambda i: changes[i])
    labels = [labels[i] for i in order]
    full = [full[i] for i in order]
    changes = [changes[i] for i in order]
    colors = [BAR if c >= 0 else theme.FUCSIA for c in changes]
    text = [("+" if c > 0 else ("−" if c < 0 else "")) + number(abs(c)) for c in changes]
    reach = max([abs(c) for c in changes] or [1]) or 1
    fig = go.Figure(go.Bar(
        x=changes, y=labels, orientation="h", marker=dict(color=colors, cornerradius=4), text=text, textposition="outside",
        cliponaxis=False, textfont=dict(size=11.5, color=theme.TINTA),
        customdata=np.stack([full, [f"{t} {unit}".strip() for t in text]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}" + (f" desde {since}" if since else "") + "<extra></extra>",
    ))
    base(fig, height or _bar_height(len(labels), 42), dict(l=8, r=72, t=8, b=10))
    fig.add_vline(x=0, line=dict(color=theme.PIZARRA, width=1))
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[-reach * 1.35, reach * 1.35])
    fig.update_yaxes(categoryorder="array", categoryarray=labels, tickfont=dict(size=11.5))
    fig.update_layout(bargap=0.4, showlegend=False)
    return fig


def part_of_whole(parts: list[tuple[str, float]], *, unit: str = "contratos") -> go.Figure:
    """One 100 % bar split in its parts, each with its share written inside."""
    total = sum(v for _l, v in parts) or 1
    colors = [BAR, theme.LILA_200, theme.LILA_100]
    fig = go.Figure()
    for index, (label, value) in enumerate(parts):
        share = value / total * 100
        fig.add_trace(go.Bar(
            x=[share], y=[""], orientation="h", name=label, marker=dict(color=colors[index % len(colors)], line=dict(color="#FFFFFF", width=2)),
            text=[f"<b>{pct(share)}</b>"], textposition="inside", insidetextanchor="middle",
            textfont=dict(size=13, color="#FFFFFF" if index == 0 else theme.MORADO_900),
            customdata=[[label, f"{number(value)} {unit}", pct(share)]],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} del total<extra></extra>",
        ))
    base(fig, 150, dict(l=8, r=8, t=36, b=8))
    fig.update_layout(barmode="stack", bargap=0.1, legend=dict(orientation="h", y=1.25, x=0, traceorder="normal"))
    fig.update_xaxes(range=[0, 100], showticklabels=False, showgrid=False)
    fig.update_yaxes(showticklabels=False)
    return fig
