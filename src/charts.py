"""Plotly figures with the institutional style and exact, Spanish-formatted hovers.

Colour does one job per chart: the two programme families (bonos y pensiones,
protección integral) are the only categorical pair; magnitude uses one purple
ramp.  Axes are fixed so a swipe over a chart scrolls the page on phones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src import geo, theme
from src.ui import number, pct

PALETTE = [theme.SERIE_BONOS, theme.SERIE_SERVICIOS, theme.VIOLETA_500, theme.FUCSIA_300,
           theme.MORADO_800, theme.FUCSIA_700, theme.LILA_300, theme.ORO_700]
SECTION_COLORS = theme.SECTION_COLORS
METRIC_LABELS = {
    "usuarios": "Cobertura reportada",
    "monto_fiscal": "Monto fiscal",
    "unidades": "Unidades de atención",
    "monto_gobierno": "Acumulado de gobierno",
}
GRID = "#EEEAF4"
AXIS_TEXT = "#6E6880"


def is_money(metric: str) -> bool:
    return metric.startswith("monto") or metric.startswith("presupuesto")


def fmt_value(value, metric: str) -> str:
    if value is None or pd.isna(value):
        return "No disponible"
    if is_money(metric):
        return f"USD {number(float(value) / 1e6, 2)} millones"
    return number(value)


def short_name(name: str, program_id: str | None = None) -> str:
    return theme.program_label(program_id, name)


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
    fig.update_yaxes(showgrid=False, zeroline=False, ticks="", showline=False, automargin=True,
                     fixedrange=True, tickfont=dict(size=12, color=theme.TINTA))
    return fig


def _bar_height(count: int, per: int = 40, minimum: int = 300) -> int:
    return max(minimum, count * per + 70)


def program_bars(data: pd.DataFrame, metric: str = "usuarios") -> go.Figure:
    group = data.groupby(["programa_id", "programa", "seccion"], as_index=False, observed=True)[metric].sum(min_count=1)
    group = group.sort_values(metric, ascending=True, na_position="first")
    total = group[metric].sum()
    labels = [short_name(p, i) for p, i in zip(group.programa, group.programa_id)]
    values = group[metric] / 1e6 if is_money(metric) else group[metric]
    text = [(number(v, 1) + " M") if is_money(metric) else number(v) for v in values]
    share = [pct(v / total * 100 if total else 0) for v in group[metric]]
    fig = go.Figure()
    for section in ["bonos_pensiones", "proteccion_integral"]:
        mask = group.seccion.eq(section).to_numpy()
        if not mask.any():
            continue
        fig.add_trace(go.Bar(
            x=values[mask], y=np.array(labels)[mask], orientation="h", name=theme.SECTIONS[section],
            marker=dict(color=SECTION_COLORS[section], cornerradius=5, line=dict(width=0)),
            text=np.array(text)[mask], textposition="outside", cliponaxis=False,
            textfont=dict(size=12, color=theme.TINTA),
            customdata=np.stack([group.programa.to_numpy()[mask], [fmt_value(v, metric) for v in group[metric].to_numpy()[mask]], np.array(share)[mask]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} de la selección<extra></extra>",
        ))
    base(fig, _bar_height(len(group)), dict(l=8, r=70, t=34, b=24))
    fig.update_xaxes(title=None, tickformat=",.0f", rangemode="tozero", showticklabels=False, showgrid=False)
    fig.update_yaxes(categoryorder="array", categoryarray=labels)
    fig.update_layout(bargap=0.36, barmode="overlay", showlegend=group.seccion.nunique() > 1)
    return fig


def budget_stack(data: pd.DataFrame) -> go.Figure:
    group = data.groupby(["programa_id", "programa"], as_index=False, observed=True)[["monto_anterior", "monto_fiscal", "monto_gobierno"]].sum(min_count=1)
    group = group.sort_values("monto_gobierno", ascending=True)
    labels = [short_name(p, i) for p, i in zip(group.programa, group.programa_id)]
    year = int(data.anio.iloc[0])
    fig = go.Figure()
    for field, name, color in [("monto_anterior", f"Acumulado 2023–{year - 1}", theme.ACUMULADO_PREVIO),
                               ("monto_fiscal", f"Monto fiscal {year}", theme.SERIE_BONOS)]:
        fig.add_trace(go.Bar(
            x=group[field] / 1e6, y=labels, name=name, orientation="h",
            marker=dict(color=color, cornerradius=4, line=dict(color="#FFFFFF", width=1.5)),
            customdata=np.stack([group.programa.to_numpy(), [fmt_value(v, field) for v in group[field]],
                                 [fmt_value(v, "monto_gobierno") for v in group.monto_gobierno]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>" + name + ": %{customdata[1]}<br>Acumulado de gobierno: %{customdata[2]}<extra></extra>",
        ))
    totals = group.monto_gobierno / 1e6
    fig.add_trace(go.Scatter(x=totals, y=labels, mode="text", text=[number(v, 0) for v in totals], textposition="middle right",
                             textfont=dict(size=12, color=theme.TINTA), hoverinfo="skip", showlegend=False, cliponaxis=False))
    base(fig, _bar_height(len(group)), dict(l=8, r=56, t=34, b=36))
    fig.update_layout(barmode="stack", bargap=0.36, legend=dict(traceorder="normal"))
    fig.update_xaxes(title="Millones de USD", tickformat=",.0f", rangemode="tozero")
    return fig


def fiscal_treemap(data: pd.DataFrame) -> go.Figure:
    group = data.groupby(["seccion", "programa_id", "programa"], as_index=False, observed=True)["monto_fiscal"].sum(min_count=1)
    group = group[group.monto_fiscal.fillna(0) > 0]
    total = group.monto_fiscal.sum()
    ids, parents, labels, values, colors, custom = [], [], [], [], [], []
    for section, part in group.groupby("seccion", sort=False):
        ids.append(section)
        parents.append("")
        labels.append(theme.SECTIONS[section])
        values.append(part.monto_fiscal.sum())
        colors.append(SECTION_COLORS[section])
        custom.append([theme.SECTIONS[section], fmt_value(part.monto_fiscal.sum(), "monto_fiscal"), pct(part.monto_fiscal.sum() / total * 100)])
        tones = [theme.mix(SECTION_COLORS[section], "#FFFFFF", t) for t in (0.0, 0.14, 0.26, 0.36, 0.46, 0.54, 0.6, 0.66)]
        for i, row in enumerate(part.sort_values("monto_fiscal", ascending=False).itertuples()):
            ids.append(f"{section}/{row.programa_id}")
            parents.append(section)
            labels.append(short_name(row.programa, row.programa_id))
            values.append(row.monto_fiscal)
            colors.append(tones[min(i, len(tones) - 1)])
            custom.append([row.programa, fmt_value(row.monto_fiscal, "monto_fiscal"), pct(row.monto_fiscal / total * 100)])
    fig = go.Figure(go.Treemap(
        ids=ids, parents=parents, labels=labels, values=values, branchvalues="total", sort=True,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=3), pad=dict(t=26, l=4, r=4, b=4), cornerradius=8),
        customdata=custom, texttemplate="<b>%{label}</b><br>%{customdata[2]}",
        textfont=dict(family=theme.WEB_FONT_STACK, color="#FFFFFF", size=13),
        insidetextfont=dict(color="#FFFFFF"), pathbar=dict(visible=False),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} del monto fiscal<extra></extra>",
        tiling=dict(packing="squarify", pad=3),
    ))
    base(fig, 380, dict(l=0, r=0, t=0, b=0))
    fig.update_layout(uniformtext=dict(minsize=10, mode="hide"))
    return fig


def province_values(data: pd.DataFrame, metric: str) -> pd.DataFrame:
    group = data.groupby(["provincia_codigo", "provincia"], as_index=False, observed=True)[metric].sum(min_count=1)
    total = group[metric].sum()
    group["share"] = group[metric] / total * 100 if total else 0
    return group


def province_map(data: pd.DataFrame, metric: str = "usuarios", height: int = 540, compact: bool = False,
                 highlight: set[str] | None = None, share_label: str = "de la selección") -> go.Figure:
    """Choropleth drawn as filled shapes on fixed axes.

    It needs no map tiles or remote topojson, so it renders offline and on
    restricted networks; colour is linear in the value (an honest magnitude).
    ``highlight`` outlines the chosen provinces in gold over the national context.
    """
    highlight = highlight or set()
    group = province_values(data, metric)
    values = dict(zip(group.provincia_codigo, group[metric]))
    shares = dict(zip(group.provincia_codigo, group.share))
    mapped = [v for c, v in values.items() if c != geo.NO_POLYGON and v is not None and v == v]
    vmax = max(mapped) if mapped and max(mapped) > 0 else 1.0
    collection = geo.provinces(inset=True)
    fig = go.Figure()
    outlines = []
    for feature in collection["features"]:
        code, name = feature["properties"]["codigo"], feature["properties"]["nombre"]
        xs, ys = [], []
        for polygon in geo.polygons(feature):
            for ring in polygon:
                xs += [p[0] for p in ring] + [None]
                ys += [p[1] for p in ring] + [None]
        value = values.get(code)
        inside = value is not None and value == value
        color = theme.ramp_at(value / vmax) if inside else "#F1EEF6"
        hover = (f"<b>{name}</b><br>{fmt_value(value, metric)}<br>{pct(shares.get(code))} {share_label}" if inside
                 else f"<b>{name}</b><br>Fuera de la selección")
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", fill="toself", fillcolor=color, name=name,
                                 line=dict(color="#FFFFFF", width=1.1), hoveron="fills", hoverinfo="text", text=hover,
                                 showlegend=False))
        if code in highlight:
            outlines.append((xs, ys))
    for xs, ys in outlines:
        # A white halo under the gold line keeps the outline visible on light and dark fills.
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#FFFFFF", width=4.2), hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=theme.ORO, width=2.4), hoverinfo="skip", showlegend=False))
    label = METRIC_LABELS.get(metric, metric)
    scale = 1e6 if is_money(metric) else 1
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", hoverinfo="skip", showlegend=False, marker=dict(
        colorscale=[[i / 8, c] for i, c in enumerate(theme.SEQUENTIAL[1:])], cmin=0, cmax=vmax / scale, color=[0], showscale=True,
        colorbar=dict(title=dict(text="Millones de USD" if is_money(metric) else label, side="top", font=dict(size=11, color=AXIS_TEXT)),
                      orientation="h", thickness=10, len=0.62 if compact else 0.5, x=0.0, xanchor="left", y=0.0, yanchor="bottom",
                      outlinewidth=0, nticks=4 if compact else 6, tickangle=0,
                      tickfont=dict(size=10, color=AXIS_TEXT), tickformat=",.0f"))))
    gx0, gy0, gx1, gy1 = geo.galapagos_frame()
    fig.add_shape(type="rect", x0=gx0, y0=gy0, x1=gx1, y1=gy1, line=dict(color=theme.LILA_300, width=1, dash="dot"),
                  fillcolor="rgba(0,0,0,0)", layer="below")
    fig.add_annotation(x=gx0, y=gy1, text="Galápagos (recuadro)", showarrow=False, xanchor="left", yanchor="bottom",
                       font=dict(size=11, color=theme.PIZARRA), yshift=4)
    x0, y0, x1, y1 = geo.bounds(collection)
    fig.add_shape(type="line", x0=gx0 - 0.2, x1=x1 + 0.2, y0=0, y1=0, line=dict(color=theme.ORO, width=1.3, dash="dot"), layer="below")
    fig.add_annotation(x=x1 + 0.2, y=0, text="Latitud 0°", showarrow=False, xanchor="right", yanchor="bottom",
                       font=dict(size=10.5, color=theme.ORO_700), yshift=3)
    base(fig, 390 if compact else height, dict(l=0, r=0, t=6, b=0))
    fig.update_xaxes(visible=False, range=[min(x0, gx0) - 0.25, x1 + 0.3])
    fig.update_yaxes(visible=False, range=[y0 - 1.15, y1 + 0.45], scaleanchor="x", scaleratio=1)
    fig.update_layout(hoverdistance=-1)
    return fig


def province_bars(data: pd.DataFrame, metric: str = "usuarios", top_n: int = 25, highlight: set[str] | None = None,
                  share_label: str = "de la selección") -> go.Figure:
    """Provinces ranked by value.

    Without ``highlight`` the three leaders carry the series colour; with it, the
    chosen provinces turn gold (as on the hero map) and keep their place in the
    national order, with their position written next to the value.
    """
    ranked = province_values(data, metric).sort_values(metric, ascending=False).reset_index(drop=True)
    # Positions count provinces only; the zone in study keeps its bar but takes no place.
    real = ranked.provincia_codigo.ne(geo.NO_POLYGON)
    ranked["position"] = np.where(real, real.cumsum(), 0)
    provinces_ranked = int(real.sum())
    group = ranked.head(top_n).iloc[::-1]
    values = group[metric] / 1e6 if is_money(metric) else group[metric]
    text = [(number(v, 1) + " M") if is_money(metric) else number(v) for v in values]
    if highlight:
        chosen = group.provincia_codigo.isin(highlight).to_numpy()
        colors = [theme.ORO if c else theme.LILA_200 for c in chosen]
        labels = [f"<b>{name}</b>" if c else name for name, c in zip(group.provincia, chosen)]
        text = [f"<b>{t} · {p}.º</b>" if c and p else (f"<b>{t}</b>" if c else t) for t, p, c in zip(text, group.position, chosen)]
    else:
        leaders = set(ranked.head(3).provincia)
        colors = [theme.SERIE_BONOS if name in leaders else theme.LILA_300 for name in group.provincia]
        labels = list(group.provincia)
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=colors, cornerradius=4),
        text=text, textposition="outside", cliponaxis=False, textfont=dict(size=11, color=theme.TINTA),
        customdata=np.stack([list(group.provincia), [fmt_value(v, metric) for v in group[metric]], [pct(s) for s in group.share],
                             [f"{p}.º de {provinces_ranked} provincias" if p else "fuera del orden provincial" for p in group.position]], axis=1),
        hovertemplate=("<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} " + share_label
                       + "<br>Posición: %{customdata[3]}<extra></extra>"),
    ))
    base(fig, max(300, len(group) * 25 + 40), dict(l=8, r=92 if highlight else 64, t=6, b=10))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(tickfont=dict(size=11.5), categoryorder="array", categoryarray=labels)
    fig.update_layout(bargap=0.28, showlegend=False)
    return fig


def territorial_matrix(data: pd.DataFrame, metric: str = "usuarios", top_n: int = 25) -> go.Figure:
    grouped = data.groupby(["provincia", "programa_id", "programa"], observed=True)[metric].sum(min_count=1).reset_index()
    pivot = grouped.pivot_table(index="provincia", columns="programa_id", values=metric, aggfunc="sum").astype(float)
    order = pivot.sum(axis=1).sort_values(ascending=False).head(top_n).index
    pivot = pivot.reindex(order)
    programs = grouped.drop_duplicates("programa_id").set_index("programa_id").programa
    columns = sorted(pivot.columns, key=lambda c: -pivot[c].sum())
    pivot = pivot[columns]
    totals = pivot.sum(axis=1).replace(0, np.nan)
    shares = pivot.div(totals, axis=0) * 100
    text = [[fmt_value(v, metric) for v in row] for row in pivot.to_numpy()]
    full = [[programs[c] for c in columns] for _ in range(len(pivot))]
    custom = np.dstack([np.array(text, dtype=object), np.array(full, dtype=object)])
    top = float(np.nanmax(shares.to_numpy())) if shares.size and np.isfinite(shares.to_numpy()).any() else 100.0
    zmax = min(100.0, max(10.0, np.ceil(top / 10) * 10))
    few = len(pivot) <= 4
    fig = go.Figure(go.Heatmap(
        z=shares.to_numpy(), x=[theme.PROGRAM_ABBR.get(c, c) for c in columns], y=list(pivot.index),
        colorscale=[[0, "#FBFAFE"], [0.12, theme.SEQUENTIAL[2]], [0.35, theme.SEQUENTIAL[4]], [0.65, theme.SEQUENTIAL[6]], [1, theme.SEQUENTIAL[9]]],
        zmin=0, zmax=zmax, xgap=3 if few else 2, ygap=3 if few else 2, customdata=custom,
        hovertemplate="<b>%{y}</b><br>%{customdata[1]}<br>%{customdata[0]}<br>%{z:.1f} % del territorio<extra></extra>",
        # A handful of territories reads better with the share written in each cell than with a colour scale.
        texttemplate="%{z:.1f} %" if few else None, textfont=dict(size=12, family=theme.WEB_FONT_STACK),
        showscale=not few,
        colorbar=dict(title=dict(text="% del territorio", side="top", font=dict(size=11, color=AXIS_TEXT)), thickness=10, len=0.6,
                      ticksuffix=" %", outlinewidth=0, tickfont=dict(size=10, color=AXIS_TEXT)),
    ))
    base(fig, len(pivot) * 58 + 64 if few else max(340, len(pivot) * 25 + 90), dict(l=8, r=8, t=36, b=10))
    fig.update_xaxes(side="top", showgrid=False, tickfont=dict(size=11, color=theme.TINTA))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11.5))
    return fig


def reference_bars(totals: pd.DataFrame) -> go.Figure:
    frame = totals.sort_values("usuarios")
    labels = [short_name(p, i) for p, i in zip(frame.programa, frame.programa_id)] if "programa_id" in frame else list(frame.programa)
    fig = go.Figure(go.Bar(
        x=frame.usuarios, y=labels, orientation="h", marker=dict(color=theme.VIOLETA_500, cornerradius=4),
        text=[number(v) for v in frame.usuarios], textposition="outside", cliponaxis=False, textfont=dict(size=11),
        customdata=np.stack([frame.programa.to_numpy(), [number(v) for v in frame.usuarios]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} registros de referencia<extra></extra>",
    ))
    base(fig, _bar_height(len(frame), 34), dict(l=8, r=70, t=8, b=10))
    fig.update_xaxes(showticklabels=False, showgrid=False)
    return fig
