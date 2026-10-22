"""Plotly figures with consistent institutional styling and exact hover values."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.ui import FUCHSIA, NAVY, PURPLE, number, pretty_label

PALETTE = [PURPLE, FUCHSIA, "#345E92", "#8A73BA", "#D393B5", "#7587B3", "#AF77B3", "#6B4F95", "#B8C4DD"]
SECTION_COLORS = {"bonos_pensiones": PURPLE, "proteccion_integral": FUCHSIA}


def short_name(name: str) -> str:
    replacements = {
        "Bono de Desarrollo Humano Variable": "BDH · componente variable",
        "Bono de Desarrollo Humano con componente variable": "BDH · componente variable",
        "Bono de Desarrollo Humano": "Bono de Desarrollo Humano",
        "Desarrollo Infantil Integral": "Desarrollo infantil integral",
        "Personas adultas mayores": "Personas adultas mayores",
        "Personas con discapacidad": "Personas con discapacidad",
    }
    label = replacements.get(name, name)
    # The data table always keeps the full official program name.
    if len(label) > 43:
        words = label.split()
        pivot = max(1, len(words) // 2)
        return " ".join(words[:pivot]) + "<br>" + " ".join(words[pivot:])
    return label


def base(fig: go.Figure, height: int = 390, margin: dict | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Aptos, Arial, sans-serif", size=12, color=NAVY),
        margin=margin or dict(l=5, r=25, t=15, b=30),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E5DDEC", font=dict(color=NAVY, size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=11)),
        separators=",.",
        modebar=dict(bgcolor="rgba(0,0,0,0)", color="#8A7B9B", activecolor=PURPLE),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#ECE8F2", zeroline=False, ticks="", showline=False, fixedrange=False)
    fig.update_yaxes(showgrid=False, zeroline=False, ticks="", showline=False, automargin=True)
    return fig


def program_bars(data: pd.DataFrame, metric: str = "usuarios", currency: bool = False) -> go.Figure:
    group = data.groupby(["programa", "seccion"], as_index=False, observed=True)[metric].sum(min_count=1)
    group = group.sort_values(metric, ascending=True)
    values = group[metric] / 1e6 if currency else group[metric]
    text = [number(v, 2) + " M" if currency else number(v) for v in values]
    hover = [f"USD {number(v, 2)}" if currency else number(v) for v in group[metric]]
    fig = go.Figure(go.Bar(
        x=values, y=[short_name(p) for p in group.programa], orientation="h",
        marker=dict(color=[SECTION_COLORS.get(s, PURPLE) for s in group.seccion], cornerradius=4),
        text=text, textposition="outside", cliponaxis=False,
        customdata=np.array([group.programa.tolist(), hover]).T,
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    ))
    base(fig, max(345, len(group) * 41 + 55), dict(l=5, r=85, t=12, b=25))
    fig.update_xaxes(title="Millones de USD" if currency else "", tickformat=",.0f", rangemode="tozero")
    fig.update_yaxes(tickfont=dict(size=11))
    fig.update_layout(bargap=0.38, showlegend=False)
    return fig


def budget_stack(data: pd.DataFrame) -> go.Figure:
    group = data.groupby("programa", as_index=False, observed=True)[["monto_anterior", "monto_fiscal", "monto_gobierno"]].sum(min_count=1)
    group = group.sort_values("monto_gobierno", ascending=True)
    fig = go.Figure()
    year = int(data.anio.iloc[0])
    for field, name, color in [("monto_anterior", f"Acumulado previo 2023–{year - 1}", "#DCD2EA"), ("monto_fiscal", f"Fiscal {year}", PURPLE)]:
        fig.add_trace(go.Bar(
            x=group[field] / 1e6, y=[short_name(p) for p in group.programa], name=name, orientation="h",
            marker=dict(color=color, cornerradius=3),
            customdata=np.array([group.programa.tolist(), [number(v, 2) for v in group[field]]]).T,
            hovertemplate="<b>%{customdata[0]}</b><br>" + name + ": USD %{customdata[1]}<extra></extra>",
        ))
    base(fig, max(345, len(group) * 41 + 55), dict(l=5, r=20, t=30, b=25))
    fig.update_layout(barmode="stack", bargap=0.38)
    fig.update_xaxes(title="Millones de USD", tickformat=",.0f", rangemode="tozero")
    fig.update_yaxes(tickfont=dict(size=11))
    return fig


def province_bars(data: pd.DataFrame, metric: str = "usuarios", top_n: int = 24) -> go.Figure:
    group = data.groupby("provincia", as_index=False, observed=True)[metric].sum(min_count=1)
    group = group.sort_values(metric, ascending=False).head(top_n).iloc[::-1]
    is_money = metric.startswith("monto") or metric.startswith("presupuesto")
    values = group[metric] / 1e6 if is_money else group[metric]
    labels = [pretty_label(p) for p in group.provincia]
    custom = np.array([labels, ["USD " + number(v, 2) if is_money else number(v) for v in group[metric]]]).T
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=PURPLE, cornerradius=4),
        text=[number(v, 2) + " M" if is_money else number(v) for v in values], textposition="outside", cliponaxis=False,
        customdata=custom, hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
    ))
    base(fig, max(340, len(group) * 26 + 50), dict(l=5, r=80, t=5, b=30))
    fig.update_xaxes(title="Millones de USD" if is_money else "", tickformat=",.0f", rangemode="tozero")
    fig.update_layout(bargap=0.3)
    return fig


def territorial_matrix(data: pd.DataFrame, metric: str = "usuarios", top_n: int = 24) -> go.Figure:
    grouped = data.groupby(["provincia", "programa"], observed=True)[metric].sum(min_count=1).unstack()
    order = grouped.sum(axis=1).sort_values(ascending=False).head(top_n).index
    grouped = grouped.reindex(order)
    # Shares use reported observations within each province, not distinct people.
    totals = grouped.sum(axis=1).replace(0, np.nan)
    shares = grouped.div(totals, axis=0) * 100
    grouped = grouped.fillna(0)
    is_money = metric.startswith("monto") or metric.startswith("presupuesto")
    text = [[("USD " + number(v, 2)) if is_money else number(v) for v in row] for row in grouped.to_numpy()]
    measure_label = "" if is_money else (" unidades de atención" if metric == "unidades" else " conteos reportados")
    fig = go.Figure(go.Heatmap(
        z=shares.to_numpy(), x=[short_name(p) for p in grouped.columns], y=[pretty_label(p) for p in grouped.index],
        colorscale=[[0, "#F6F2FA"], [0.3, "#D5C3E8"], [0.65, "#9272B9"], [1, PURPLE]],
        zmin=0, zmax=100, xgap=3, ygap=3,
        customdata=text,
        hovertemplate="<b>%{y}</b><br>%{x}<br>%{customdata}" + measure_label + "<br>%{z:.1f}% del total provincial seleccionado<extra></extra>",
        colorbar=dict(title="%", thickness=8, len=0.7, tickvals=[0,25,50,75,100], outlinewidth=0),
    ))
    base(fig, max(340, len(grouped) * 26 + 105), dict(l=5, r=15, t=5, b=80))
    fig.update_xaxes(tickangle=-38, showgrid=False, tickfont=dict(size=10))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11))
    return fig


def fiscal_allocation(data: pd.DataFrame) -> go.Figure:
    group = data.groupby(["programa", "seccion"], as_index=False, observed=True).agg(monto_fiscal=("monto_fiscal", "sum"), usuarios=("usuarios", "sum"))
    group = group[group.monto_fiscal > 0].sort_values("monto_fiscal", ascending=False)
    total = group.monto_fiscal.sum()
    fig = go.Figure(go.Pie(
        labels=group.programa, values=group.monto_fiscal, hole=0.74,
        marker=dict(colors=PALETTE, line=dict(color="#FFFFFF", width=3)),
        textinfo="none", sort=False,
        customdata=[number(v, 2) for v in group.monto_fiscal],
        hovertemplate="<b>%{label}</b><br>USD %{customdata}<br>%{percent:.1%} del monto fiscal<extra></extra>",
    ))
    base(fig, 335, dict(l=5, r=5, t=15, b=15))
    fig.update_layout(showlegend=False, annotations=[dict(text=f"<b>{number(total/1e6, 2)}</b><br><span style='font-size:11px'>millones USD</span>", x=0.5, y=0.5, showarrow=False, font=dict(size=27, color=PURPLE))])
    return fig
