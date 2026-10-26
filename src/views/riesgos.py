"""Riesgos: unidades de atención (UA) expuestas a amenazas naturales, por amenaza, servicio y provincia.

Every figure counts unique units of attention (one per cut and code), except multihazard, which reproduces the records
of the source matrix exposed to floods or mass movements, as the source reports them.  A unit is exposed when one of
the chosen threats reaches one of the chosen categories (media, alta, muy alta).  Exposure is a territorial
susceptibility, never a confirmed damage, and a unit without a reported category is not a unit without risk.  The
units of different threats are never added: a unit exposed to two threats is one unit.
"""
from __future__ import annotations

import json
from datetime import datetime
from textwrap import wrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import charts, enos, geo, names, riesgos, theme, ui
from src.views import respuesta
from src.views.common import compact, download_table, fingerprint, show_chart


@st.cache_data(show_spinner=False)
def _read(version: int) -> pd.DataFrame:
    return pd.read_parquet(riesgos.DATA_PATH)


@st.cache_data(show_spinner=False)
def _read_details(version: int) -> pd.DataFrame:
    return pd.read_parquet(riesgos.DETAIL_PATH)


@st.cache_data(show_spinner=False)
def _read_matrix(version: int) -> pd.DataFrame:
    return pd.read_parquet(riesgos.MATRIX_PATH)


METHODOLOGY = (
    "La clasificación de las Unidades de Atención (UA) se realizó mediante el análisis espacial de sus coordenadas "
    "geográficas validadas respecto a las capas de susceptibilidad consideradas. Se clasifican como expuestas aquellas "
    "UA ubicadas en zonas de susceptibilidad media, alta o muy alta, y como no expuestas aquellas que se encuentran "
    "fuera de estas categorías. Esta clasificación no implica una afectación efectiva ni descarta la existencia de "
    "amenazas o riesgos fuera de las zonas identificadas. Los posibles impactos dependen de las condiciones "
    "territoriales, la intensidad de los eventos y la vulnerabilidad de los elementos expuestos."
)
DEFINITIONS = [
    ("UA expuesta", "Unidad de atención con susceptibilidad media, alta o muy alta en al menos una de las amenazas elegidas. "
                    "Cada código de unidad se cuenta una sola vez."),
    ("Multiamenaza", "Registros de la matriz fuente con susceptibilidad media, alta o muy alta a inundaciones o a movimientos en "
                     "masa. Conserva los códigos repetidos de la fuente; los demás indicadores cuentan unidades únicas."),
    ("Amenazas simultáneas", "Cuántas de las cuatro amenazas alcanzan las categorías elegidas en una misma unidad."),
    ("Sin categoría reportada", "Vacíos y guiones de la fuente. No acreditan ausencia de riesgo."),
]
SOURCES = ("Fuente: SIIMTDH · DGID / SGDE / MTDH. Capas: inundaciones y sequía, MAGAP 2015; movimientos en masa, SNGR 2011; "
           "incendios forestales, SNGR 2015.")
LEVEL_COLORS = {"Media": theme.LILA_300, "Alta": theme.MORADO, "Muy alta": theme.FUCSIA_700}
LEVEL_INK = {"Media": theme.MORADO_900, "Alta": "#FFFFFF", "Muy alta": "#FFFFFF"}
CONCURRENCY_COLORS = [theme.LILA_300, theme.VIOLETA_500, theme.MORADO, theme.MORADO_900]
MAP_INDICATORS = {"expuestas": "UA expuestas", "porcentaje": "% expuesto", "muy_alta": "Muy alta", "multiamenaza": "Multiamenaza",
                  "alertas": "Alertas", "kits": "Kits"}
MAP_LABELS = {"expuestas": "UA expuestas por provincia", "porcentaje": "Porcentaje de las UA de cada provincia que está expuesto",
              "muy_alta": "UA con susceptibilidad muy alta por provincia", "multiamenaza": "Registros de multiamenaza por provincia",
              "alertas": "Alertas con afectación a servicios MTDH por provincia", "kits": "Kits entregados por provincia"}
SUSCEPTIBILITY_CELLS = {"Media": ("#F3EFFC", "#5B46A0"), "Alta": ("#E2D9F6", "#3D216D"), "Muy alta": ("#F9DDEB", "#A32C74"),
                        "Sin categoría reportada": ("#FFFFFF", "#A59CB6"), "Sin categoría": ("#FFFFFF", "#A59CB6")}
RESPONSE_SCOPES = [("Alertas", enos.ALERT_NOTE), ("Kits", enos.KIT_NOTE), ("Bono de contingencia", enos.BONO_NOTE),
                   ("Filtros", respuesta.FILTERS_NOTE)]
RANK_METRICS = {"expuestas": "UA expuestas", "porcentaje": "% del inventario", "muy_alta": "Muy alta"}


def _units(value) -> str:
    return f"{ui.number(value)} UA"


def _label(text: str, width: int = 18) -> str:
    return "<br>".join(wrap(str(text), width, break_long_words=False)) or str(text)


def half_count(values) -> int:
    """How many of the largest values gather half of their total (0 when there is nothing)."""
    ordered = sorted((float(v) for v in values if v and v > 0), reverse=True)
    total, running = sum(ordered), 0.0
    for index, value in enumerate(ordered, start=1):
        running += value
        if running >= total / 2:
            return index
    return 0


# ------------------------------------------------------------------------------------------------- charts
def threat_bars(rows: pd.DataFrame, levels) -> go.Figure:
    """Each threat as one bar split by category; at its end, the exposed units and their share of the inventory."""
    rows = rows.iloc[::-1]
    labels = list(rows.amenaza)
    fig = go.Figure()
    for level in riesgos.LEVELS:
        if level not in levels or not rows[level].any():
            continue
        values = rows[level].astype(float)
        fig.add_trace(go.Bar(
            x=values, y=labels, name=level, orientation="h",
            marker=dict(color=LEVEL_COLORS[level], line=dict(color="#FFFFFF", width=2)),
            text=[ui.number(v) if v else "" for v in values], textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11.5, color=LEVEL_INK[level]),
            customdata=np.stack([labels, [_units(v) for v in values]], axis=1),
            hovertemplate=f"<b>%{{customdata[0]}}</b><br>Susceptibilidad {level.lower()}: %{{customdata[1]}}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=rows.expuestas, y=labels, mode="text", cliponaxis=False, hoverinfo="skip", showlegend=False,
        text=[f"  <b>{_units(v)}</b> · {ui.pct(p)}" for v, p in zip(rows.expuestas, rows.porcentaje)],
        textposition="middle right", textfont=dict(size=12, color=theme.TINTA)))
    charts.base(fig, max(250, len(rows) * 62 + 70), dict(l=8, r=150, t=40, b=8))
    fig.update_layout(barmode="stack", bargap=0.36, uniformtext=dict(minsize=10, mode="hide"),
                      legend=dict(traceorder="normal", y=1.08))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(categoryorder="array", categoryarray=labels, tickfont=dict(size=12))
    return fig


def concurrency_columns(rows: pd.DataFrame) -> go.Figure:
    """Exposed units by how many threats they face at once: one column per count, darker with more threats."""
    labels = [f"{n} amenaza" if n == 1 else f"{n} amenazas" for n in rows.amenazas]
    peak = float(rows.unidades.max() or 1)
    fig = go.Figure(go.Bar(
        x=labels, y=rows.unidades, marker=dict(color=CONCURRENCY_COLORS[:len(rows)], cornerradius=6),
        text=[f"<b>{_units(u)}</b><br>{ui.pct(p)}" for u, p in zip(rows.unidades, rows.porcentaje)], textposition="outside",
        cliponaxis=False, textfont=dict(size=12, color=theme.TINTA),
        customdata=np.stack([[f"{n} amenaza a la vez" if n == 1 else f"{n} amenazas a la vez" for n in rows.amenazas],
                             [_units(u) for u in rows.unidades], [ui.pct(p) for p in rows.porcentaje]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]} de las UA expuestas<extra></extra>"))
    charts.base(fig, 300, dict(l=8, r=8, t=14, b=30))
    fig.update_layout(bargap=0.34, showlegend=False)
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12, color=theme.TINTA))
    fig.update_yaxes(showticklabels=False, showgrid=False, range=[0, peak * 1.3])
    return fig


def share_bars(labels: list[str], values: list[float], shares: list[float], *, hover: list[str] | None = None,
               color: str = charts.BAR, per: int = 32, share_word: str = "de las UA expuestas") -> go.Figure:
    """Ranked bars (largest on top) with the units and their share written at the end."""
    labels, values, shares = labels[::-1], values[::-1], shares[::-1]
    hover = (hover or labels)[::-1] if hover else labels
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=color, cornerradius=4),
        text=[f"{_units(v)} · {ui.pct(s)}" for v, s in zip(values, shares)], textposition="outside", cliponaxis=False,
        textfont=dict(size=11.5, color=theme.TINTA),
        customdata=np.stack([hover, [_units(v) for v in values], [f"{ui.pct(s)} {share_word}" for s in shares]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>"))
    charts.base(fig, max(220, len(labels) * per + 30), dict(l=8, r=128, t=8, b=8))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(categoryorder="array", categoryarray=labels, tickfont=dict(size=11.5))
    fig.update_layout(bargap=0.34, showlegend=False)
    return fig


def service_bars(rows: pd.DataFrame, levels) -> go.Figure:
    """Exposed units of each service by their highest category; at the end, the units and the share of the service."""
    rows = rows.loc[rows.inventario.gt(0)].iloc[::-1]
    labels = [_label(s) for s in rows.servicio]
    fig = go.Figure()
    for level in riesgos.LEVELS:
        if level not in levels or not rows[level].any():
            continue
        values = rows[level].astype(float)
        fig.add_trace(go.Bar(
            x=values, y=labels, name=f"Más alta: {level.lower()}", orientation="h",
            marker=dict(color=LEVEL_COLORS[level], line=dict(color="#FFFFFF", width=2)),
            text=[ui.number(v) if v else "" for v in values], textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11, color=LEVEL_INK[level]),
            customdata=np.stack([list(rows.servicio), [_units(v) for v in values]], axis=1),
            hovertemplate=f"<b>%{{customdata[0]}}</b><br>Susceptibilidad más alta {level.lower()}: %{{customdata[1]}}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=rows.expuestas, y=labels, mode="text", cliponaxis=False, hoverinfo="skip", showlegend=False,
        text=[f"  <b>{_units(v)}</b> · {ui.pct(p)}" for v, p in zip(rows.expuestas, rows.porcentaje)],
        textposition="middle right", textfont=dict(size=12, color=theme.TINTA)))
    charts.base(fig, max(260, len(rows) * 60 + 70), dict(l=8, r=150, t=40, b=8))
    fig.update_layout(barmode="stack", bargap=0.34, uniformtext=dict(minsize=10, mode="hide"),
                      legend=dict(traceorder="normal", y=1.08))
    fig.update_xaxes(showticklabels=False, showgrid=False, rangemode="tozero")
    fig.update_yaxes(categoryorder="array", categoryarray=labels, tickfont=dict(size=11.5))
    return fig


def threat_matrix(frame: pd.DataFrame, label_col: str, *, highlight: set[str] | None = None, code_col: str | None = None,
                  row_word: str = "la provincia") -> go.Figure:
    """Share of the units of each row exposed to each threat in the chosen categories; units in the hover."""
    frame = frame.loc[frame.inventario.gt(0)]
    threats = list(riesgos.THREATS.values())
    shares = frame[threats].div(frame.inventario, axis=0).to_numpy(dtype=float) * 100
    highlight = highlight or set()
    codes = list(frame[code_col]) if code_col else [None] * len(frame)
    labels = [f"<b>{n}</b>" if c in highlight else n for n, c in zip(frame[label_col], codes)]
    custom = np.dstack([np.array([[t] * len(frame) for t in threats], dtype=object).T,
                        np.array([[ui.number(v) for v in frame[t]] for t in threats], dtype=object).T,
                        np.array([[ui.number(v)] * len(threats) for v in frame.inventario], dtype=object)])
    few = len(frame) <= 6
    fig = go.Figure(go.Heatmap(
        z=shares, x=[_label(t, 12) for t in threats], y=labels, zmin=0, zmax=100, xgap=3, ygap=3 if few else 2,
        colorscale=[[0, "#FBFAFE"], [0.12, theme.SEQUENTIAL[2]], [0.35, theme.SEQUENTIAL[4]], [0.65, theme.SEQUENTIAL[6]],
                    [1, theme.SEQUENTIAL[9]]],
        customdata=custom, texttemplate="%{z:.1f} %", textfont=dict(size=12 if few else 11, family=theme.WEB_FONT_STACK),
        hovertemplate=(f"<b>%{{y}}</b><br>%{{customdata[0]}}<br>%{{customdata[1]}} de %{{customdata[2]}} UA"
                       f"<br>%{{z:.1f}} % de las UA de {row_word}<extra></extra>"),
        showscale=False))
    head = 46
    charts.base(fig, len(frame) * (56 if few else 26) + head + 16, dict(l=8, r=8, t=head, b=6))
    fig.update_xaxes(side="top", showgrid=False, tickangle=0, tickfont=dict(size=11, color=theme.TINTA))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=11.5))
    return fig


def province_bars(rows: pd.DataFrame, metric: str, highlight: set[str]) -> go.Figure:
    """Provinces ranked by exposed units, their share of the province's units or the units in «muy alta»."""
    column = {"expuestas": "expuestas", "porcentaje": "porcentaje", "muy_alta": "Muy alta"}[metric]
    rows = rows.loc[rows.inventario.gt(0)].sort_values([column, "expuestas"], ascending=False).iloc[::-1]
    labels = [names.place(p) for p in rows.provincia]
    chosen = rows.provincia_codigo.isin(highlight).to_numpy()
    leaders = set(rows.iloc[::-1].head(3).provincia_codigo)
    colors = [theme.ORO if c else (charts.BAR if code in leaders and not highlight else theme.LILA_300)
              for c, code in zip(chosen, rows.provincia_codigo)]
    total = float(rows.expuestas.sum()) or 1.0
    very_total = float(rows["Muy alta"].sum()) or 1.0
    if metric == "porcentaje":
        values = rows.porcentaje.fillna(0)
        text = [f"{ui.pct(p)} · {ui.number(e)} de {ui.number(i)}" for p, e, i in zip(rows.porcentaje, rows.expuestas, rows.inventario)]
    elif metric == "muy_alta":
        values = rows["Muy alta"]
        text = [f"{_units(v)} · {ui.pct(v / very_total * 100)}" for v in values]
    else:
        values = rows.expuestas
        text = [f"{_units(v)} · {ui.pct(v / total * 100)}" for v in values]
    text = [f"<b>{t}</b>" if c else t for t, c in zip(text, chosen)]
    fig = go.Figure()
    if metric == "porcentaje":
        fig.add_trace(go.Bar(x=[100] * len(rows), y=labels, orientation="h", marker=dict(color="#EEEAF6", cornerradius=4),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Bar(
        x=values, y=labels, orientation="h", marker=dict(color=colors, cornerradius=4), showlegend=False,
        customdata=np.stack([labels, [_units(v) for v in rows.expuestas], [ui.pct(p) for p in rows.porcentaje],
                             [_units(v) for v in rows.inventario], [_units(v) for v in rows["Muy alta"]]], axis=1),
        hovertemplate=("<b>%{customdata[0]}</b><br>UA expuestas: %{customdata[1]} de %{customdata[3]} (%{customdata[2]})"
                       "<br>Muy alta: %{customdata[4]}<extra></extra>")))
    reach = 100.0 if metric == "porcentaje" else float(values.max() or 1)
    fig.add_trace(go.Scatter(x=[reach * 1.01] * len(rows) if metric == "porcentaje" else values, y=labels, mode="text", text=text,
                             textposition="middle right", cliponaxis=False, hoverinfo="skip", showlegend=False,
                             textfont=dict(size=11, color=theme.TINTA)))
    charts.base(fig, max(300, len(rows) * 25 + 30), dict(l=8, r=150 if metric == "porcentaje" else 118, t=8, b=8))
    fig.update_layout(barmode="overlay", bargap=0.3, showlegend=False)
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[0, reach * 1.02] if metric == "porcentaje" else None,
                     rangemode="tozero")
    fig.update_yaxes(categoryorder="array", categoryarray=labels, tickfont=dict(size=11.5))
    return fig


# --------------------------------------------------------------------------------------------------- view
class RiskView:
    id = "riesgos"
    label = "Riesgos"
    kind = "riesgos"
    empty_message = "La matriz de riesgos no registra unidades de atención para esta combinación de territorio y servicio."
    summary_pages = 2

    def __init__(self):
        self.data = _read(riesgos.DATA_PATH.stat().st_mtime_ns) if riesgos.DATA_PATH.exists() else pd.DataFrame()
        self.inventory = (_read_details(riesgos.DETAIL_PATH.stat().st_mtime_ns) if riesgos.DETAIL_PATH.exists()
                          else pd.DataFrame(columns=riesgos.DETAIL_FIELDS))
        self.matrix = (_read_matrix(riesgos.MATRIX_PATH.stat().st_mtime_ns) if riesgos.MATRIX_PATH.exists()
                       else self.data.iloc[:0].rename(columns={"unidades": "registros"}))
        self.provinces, self.programs, self.threat, self.levels = [], [], None, riesgos.LEVELS
        self.map_indicator = "expuestas"
        # The response of the Ministry: one snapshot per cut of the follow-up (alerts, kits and contingency bonus).
        self.snapshots = enos.snapshots()
        self.response_path = self.snapshots[-1] if self.snapshots else None
        self.response = None

    def catalog(self) -> list[dict]:
        from src.corte import MONTHS
        if self.data.empty:
            return []
        return [{"id": p, "year": int(p[:4]), "month": int(p[5:]),
                 "label": f"{MONTHS[int(p[5:]) - 1].capitalize()} {p[:4]}"}
                for p in sorted(self.data.periodo_id.unique())]

    # ----------------------------------------------------------------------------------------- consultation
    def select(self, period: dict, provinces=(), programs=(), threat=None, levels=riesgos.LEVELS) -> None:
        """A cut and a selection without widgets (scripts, tests and the summary of every section)."""
        self.period, self.provinces, self.programs = period, list(provinces), list(programs)
        self.threat, self.levels = threat, tuple(levels)
        self.response_path = self.snapshots[-1] if self.snapshots else None

    def _names(self, period_id: str) -> tuple[dict, dict]:
        scoped = self.data.loc[self.data.periodo_id.eq(period_id)]
        provinces = scoped.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.map(names.place).to_dict()
        services = (scoped.groupby(["programa_id", "servicio"]).unidades.sum().sort_values(ascending=False)
                    .reset_index().set_index("programa_id").servicio.to_dict())
        return provinces, services

    def controls(self, period: dict) -> None:
        self.period = period
        province_names, service_names = self._names(period["id"])
        for key, options in [("risk_provinces", province_names), ("risk_programs", service_names),
                             ("risk_threats", riesgos.THREATS)]:
            if key in st.session_state:
                st.session_state[key] = [value for value in st.session_state[key] if value in options]
        if "risk_levels" not in st.session_state:
            st.session_state["risk_levels"] = list(riesgos.LEVELS)
        left, right = st.columns(2, gap="small")
        with left:
            self.provinces = st.multiselect("Territorio", sorted(province_names, key=province_names.get),
                                            format_func=province_names.get, placeholder="Todo el país", key="risk_provinces")
        with right:
            self.programs = st.multiselect("Servicio", list(service_names), format_func=service_names.get,
                                           placeholder="Todos los servicios", key="risk_programs")
        left, right = st.columns([1.15, 1], gap="small")
        with left:
            threats = st.multiselect("Amenaza", list(riesgos.THREATS), format_func=riesgos.THREATS.get,
                                     placeholder="Todas las amenazas", key="risk_threats")
        with right:
            levels = st.segmented_control("Susceptibilidad", list(riesgos.LEVELS), selection_mode="multi", key="risk_levels",
                                          width="stretch")
        self.threat = threats or None
        self.levels = tuple(level for level in riesgos.LEVELS if level in (levels or []))
        if len(self.snapshots) > 1:
            cuts = {path.stem[-10:]: path for path in self.snapshots}
            if st.session_state.get("risk_response_cut") not in cuts:
                st.session_state["risk_response_cut"] = list(cuts)[-1]
            cut = st.selectbox("Corte del seguimiento de la respuesta", list(cuts), key="risk_response_cut",
                               format_func=lambda x: pd.Timestamp(x).strftime("%d/%m/%Y"))
            self.response_path = cuts[cut]
        elif self.snapshots:
            self.response_path = self.snapshots[-1]
        if self.provinces or self.programs or threats or len(self.levels) != len(riesgos.LEVELS):
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary",
                      key="risk_reset_filters")

    @staticmethod
    def _clear() -> None:
        st.session_state["risk_provinces"] = []
        st.session_state["risk_programs"] = []
        st.session_state["risk_threats"] = []
        st.session_state["risk_levels"] = list(riesgos.LEVELS)

    def prepare(self) -> bool:
        pid = self.period["id"]
        levels = self.levels
        self.scoped = riesgos.select(self.data, pid, self.provinces, self.programs)
        if self.scoped.empty:
            return False
        self.inventory_units = riesgos.count_units(self.scoped)
        self.selected = riesgos.exposed(self.scoped, self.threat, levels)
        self.national = riesgos.select(self.data, pid, (), self.programs)
        self.national_selected = riesgos.exposed(self.national, self.threat, levels)
        self.detail_selected = riesgos.exposed(riesgos.select(self.inventory, pid, self.provinces, self.programs), self.threat, levels)
        self.matrix_available = bool(self.matrix.periodo_id.eq(pid).any())
        matrix_selected = riesgos.exposed(riesgos.select(self.matrix, pid, self.provinces, self.programs), self.threat, levels)
        self.multihazard = riesgos.multihazard(matrix_selected, levels)
        national_matrix = riesgos.exposed(riesgos.select(self.matrix, pid, (), self.programs), self.threat, levels)
        self.national_multihazard = riesgos.multihazard(national_matrix, levels)
        self.threats = riesgos.by_threat(self.scoped, self.threat, levels)
        self.concurrent = riesgos.concurrency(self.selected, levels)
        self.combos = riesgos.combinations(self.selected, levels)
        self.province_rows = riesgos.profile(self.scoped, self.selected, "provincia", self.threat, levels, self.multihazard)
        self.national_rows = riesgos.profile(self.national, self.national_selected, "provincia", self.threat, levels,
                                             self.national_multihazard)
        self.service_rows = riesgos.profile(self.scoped, self.selected, "servicio", self.threat, levels, self.multihazard)
        top = riesgos.max_level(self.selected, self.threat, levels)
        self.very_high = riesgos.count_units(self.selected.loc[top.eq("Muy alta")]) if "Muy alta" in levels else None
        self.several = riesgos.count_units(self.selected.loc[riesgos.threat_count(self.selected, levels).ge(2)])
        place_names = self.scoped.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.map(names.place)
        if len(self.provinces) == 1:
            self.territory_label = place_names.get(self.provinces[0], "Nacional")
        elif self.provinces:
            self.territory_label = f"{len(self.provinces)} provincias"
        else:
            self.territory_label = "Nacional"
        services = sorted(self.scoped.servicio.unique())
        self.programs_label = (services[0] if len(self.programs) == 1 and services else
                               f"{len(self.programs)} servicios" if self.programs else "Todos los servicios")
        self.threat_label = riesgos.threat_label(self.threat)
        self.levels_label = ("Media, alta y muy alta" if len(levels) == len(riesgos.LEVELS) else
                             " y ".join(level.lower() for level in levels).capitalize() if levels else "Ninguna categoría")
        self.selection_label = f"{self.threat_label} · susceptibilidad {self.levels_label.lower()}"
        self.context_label = f"{self.period['label']} · {self.territory_label} · {self.programs_label}"
        self.response = None
        if self.response_path:
            unit_programs = {}
            if self.programs:
                units = riesgos.select(self.inventory, pid, (), ())
                unit_programs = dict(zip(units.codigo_ua.astype(str), units.programa_id))
            self.response = respuesta.Response(enos.load(self.response_path), self.provinces, self.programs, unit_programs)
        return True

    # ----------------------------------------------------------------------------------------------- band
    def hero_copy(self) -> tuple[str, str, str]:
        follow = f" · respuesta al {self.response.cut:%d/%m/%Y}" if self.response else ""
        return (f"Exposición: {self.period['label'].lower()}{follow}", "Riesgos",
                "Unidades de atención expuestas a amenazas de El Niño y respuesta del Ministerio.")

    def update_stamp(self) -> dict:
        from src.corte import ECUADOR, long_date
        path = riesgos.DATA_PATH.with_name(f"riesgos_ua_{self.period['id']}.json")
        metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        value = metadata.get("generado_utc")
        updated = long_date(datetime.fromisoformat(value).astimezone(ECUADOR)) if value else ""
        moments = [datetime.fromisoformat(value).astimezone(ECUADOR)] if value else []
        response = ""
        if self.response:
            moments.append(datetime.fromisoformat(self.response.data["generado_utc"]).astimezone(ECUADOR))
            response = f" · respuesta al {self.response.cut:%d/%m/%Y}"
        updated = long_date(max(moments)) if moments else ""
        cut = f"Exposición: {self.period['label']}{response}"
        line = cut + (f" · Actualizado el {updated}" if updated else "")
        short = f"Exposición {self.period['label'].lower()}" + (f" · respuesta al {self.response.cut:%d/%m/%Y}" if self.response else "")
        return {"cut": cut, "updated": updated, "short": short, "line": line,
                "frequency": "Exposición según matriz; respuesta según cortes recibidos", "frequency_short": "según cortes recibidos"}

    def national_table(self) -> pd.DataFrame:
        """Exposure of every province (service and threat filters) with the actions of the Ministry in it."""
        rows = self.national_rows.copy()
        if self.response:
            rows = rows.merge(self.response.by_province(national=True), on="provincia_codigo", how="left")
        for column in ["alertas", "kits", "gestionados", "monto_gestionado", "articulacion", "monto_articulacion"]:
            rows[column] = rows[column].fillna(0) if column in rows else 0
        return rows

    def map_values(self, indicator: str) -> tuple[dict, dict]:
        """Values and native tooltips of the province map (the whole country, with the service and threat filters)."""
        rows = self.national_table()
        column = {"expuestas": "expuestas", "porcentaje": "porcentaje", "muy_alta": "Muy alta", "multiamenaza": "multiamenaza",
                  "alertas": "alertas", "kits": "kits"}[indicator]
        values, titles = {}, {}
        for row in rows.to_dict("records"):
            code = str(row["provincia_codigo"])
            if code == geo.NO_POLYGON or column not in row:
                continue
            value = row[column]
            values[code] = float(value) if value == value else None
            extra = f"\nMultiamenaza: {ui.number(row['multiamenaza'])} registros" if "multiamenaza" in row else ""
            actions = [f"{ui.number(row['alertas'])} alertas" if row["alertas"] else "", f"{ui.number(row['kits'])} kits" if row["kits"] else "",
                       f"{ui.number(row['gestionados'])} personas con bono gestionado" if row["gestionados"] else ""]
            actions = [a for a in actions if a]
            titles[code] = (f"{names.place(row['provincia'])}\n{_units(row['expuestas'])} expuestas de {_units(row['inventario'])} "
                            f"({ui.pct(row['porcentaje'])})\nMuy alta: {_units(row['Muy alta'])}{extra}"
                            + (f"\nRespuesta: {', '.join(actions)}" if actions else ""))
        return values, titles

    def map_svg(self, indicator: str | None = None, night: bool = True, width: int = 640) -> tuple[str, str]:
        indicator = indicator or self.map_indicator
        values, titles = self.map_values(indicator)
        selected = set(self.provinces)
        if night:
            svg = geo.svg_map(ui.map_fills(values), layer="provincia", titles=titles, selected=selected, stroke=theme.MORADO_900,
                              width=width)
        else:
            svg = geo.svg_map(ui.map_fills(values, theme.SEQUENTIAL[2:]), layer="provincia", titles=titles, selected=selected,
                              width=width, pad=6, stroke="#FFFFFF", equator=None, locator=False, empty_fill="#F1EEF6",
                              context_fill="#F1EEF6", border_color="rgba(81,47,141,.45)", frame_color="rgba(81,47,141,.35)",
                              label_color="rgba(81,47,141,.6)", css_class="ec-map mini")
        return svg, MAP_LABELS[indicator]

    def hero_visual(self) -> None:
        options = [key for key in MAP_INDICATORS if key != "multiamenaza" or self.matrix_available]
        if not self.response:
            options = [key for key in options if key not in ("alertas", "kits")]
        if "Muy alta" not in self.levels:
            options = [key for key in options if key != "muy_alta"]
        if st.session_state.get("risk_map_indicator") not in options:
            st.session_state["risk_map_indicator"] = options[0]
        self.map_indicator = st.segmented_control("Indicador territorial", options, format_func=MAP_INDICATORS.get,
                                                  key="risk_map_indicator", required=True, width="stretch")
        svg, label = self.map_svg()
        selected = ("Provincia seleccionada" if len(self.provinces) == 1 else "Provincias seleccionadas") if self.provinces else ""
        ui.hero_map(svg, label, selected=selected)

    # ----------------------------------------------------------------------------------------------- KPIs
    def _exposure_kpis(self) -> list[dict]:
        exposed = riesgos.count_units(self.selected)
        share = exposed / self.inventory_units * 100 if self.inventory_units else None
        return [
            {"label": "Unidades expuestas", "value": exposed, "icon": "building", "bar": share,
             "bar_label": f"{ui.pct(share)} de las {ui.number(self.inventory_units)} UA del inventario"},
            {"label": "Multiamenaza", "value": riesgos.count_records(self.multihazard) if self.matrix_available else None,
             "icon": "storm", "tone": "fucsia", "note": "Registros con inundaciones o movimientos en masa"},
            {"label": "Susceptibilidad muy alta", "value": self.very_high, "icon": "flame", "tone": "oro",
             "note": "UA con al menos una amenaza en muy alta" if self.very_high is not None else "Categoría no elegida"},
        ]

    def _response_kpis(self) -> list[dict]:
        r = self.response
        states = [(r.pending, respuesta._n(r.pending, "pendiente")), (r.following, f"{r.following} en seguimiento"),
                  (r.resolved, respuesta._n(r.resolved, "resuelta"))]
        kit_provinces, _cantons = r.places(r.kits)
        managed, articulation = int(r.managed.personas.sum()), int(r.articulation.personas.sum())
        bonus = [f"USD {ui.number(r.managed.monto.sum(), 2)}" if managed else "",
                 f"{ui.number(articulation)} en articulación" if articulation else ""]
        return [
            {"label": "Alertas en servicios MTDH", "value": len(r.alerts), "icon": "shield", "tone": "oro",
             "note": " · ".join(text for count, text in states if count) or "Sin alertas en la consulta"},
            {"label": "Kits entregados", "value": r.kits_total, "icon": "life-buoy", "tone": "violeta",
             "note": (f"{respuesta._n(len(r.kits), 'entrega')} · {respuesta._n(kit_provinces, 'provincia')} · 24 y 25/10" if len(r.kits)
                      else "Sin entregas en la consulta")},
            {"label": "Personas con bono gestionado", "value": managed, "icon": "hand-coins", "tone": "lila",
             "note": " · ".join(t for t in bonus if t) or "Sin registros en la consulta"},
        ]

    def kpi_cards(self) -> list[dict]:
        """With the response, UA expuestas, multiamenaza, alertas and kits lead (the documents show those four)."""
        if self.response:
            exposure, response = self._exposure_kpis(), self._response_kpis()
            return [exposure[0], exposure[1], response[0], response[1], response[2], exposure[2]]
        exposed = riesgos.count_units(self.selected)
        provinces_with = int(self.province_rows.expuestas.gt(0).sum())
        provinces_all = int(self.province_rows.inventario.gt(0).sum())
        return self._exposure_kpis() + [
            {"label": "Dos o más amenazas", "value": self.several, "icon": "layers", "tone": "violeta",
             "note": f"{ui.pct(self.several / exposed * 100 if exposed else 0)} de las UA expuestas"},
            {"label": "Provincias con UA expuestas", "value": provinces_with, "icon": "map", "tone": "lila",
             "note": f"De {provinces_all} provincia{'s' if provinces_all != 1 else ''} con UA en la selección"},
        ]

    def kpi_groups(self) -> list[dict]:
        """The exposure and the response side by side, three figures each; without the follow-up, the cards alone."""
        if not self.response:
            return []
        return [{"title": "Exposición de las unidades de atención", "icon": "storm", "tone": "morado",
                 "subtitle": f"Susceptibilidad territorial · matriz de {self.period['label'].lower()}", "cards": self._exposure_kpis()},
                {"title": "Respuesta del Ministerio", "icon": "life-buoy", "tone": "oro",
                 "subtitle": f"Seguimiento {self.response.scope_text().lower()}", "cards": self._response_kpis()}]

    # ------------------------------------------------------------------------------------------ dashboard
    def dashboard(self) -> None:
        r = self.response
        where = self.territory_label if self.provinces else "todo el país"
        if r:
            ui.chapter("Exposición de las unidades de atención",
                       f"Susceptibilidad territorial de las UA ante amenazas naturales · {self.period['label']} · {where}", "storm",
                       anchor="exposicion")
        if not self.levels:
            ui.info_note("Elija al menos una categoría de susceptibilidad: media, alta o muy alta.", "Sin categorías elegidas",
                         tone="warn")
        elif self.selected.empty:
            ui.info_note("No hay unidades expuestas con las amenazas y categorías elegidas en este territorio y servicio.",
                         "Sin unidades expuestas", tone="warn")
        else:
            self._threats()
            self._services()
            self._territory()
            self.table()
        if r:
            ui.chapter("Respuesta del Ministerio", f"Alertas en los servicios, kits entregados y bono de contingencia · "
                                                   f"seguimiento {r.scope_text().lower()} · {where}", "life-buoy", tone="oro",
                       anchor="respuesta")
            self._response()
        self.methodology()

    def _pair(self, ratio=(1, 1)):
        return [st.container(), st.container()] if compact() else st.columns(list(ratio), gap="medium")

    # -------------------------------------------------------------------------------- response of the Ministry
    def _response(self) -> None:
        r = self.response
        acting = self.action_rows()
        if self.programs:
            ui.info_note(f"Las alertas corresponden a las UA de {self.programs_label.lower() if len(self.programs) > 1 else self.programs_label}; "
                         "los kits y el bono de contingencia no se asocian a un servicio y se muestran por territorio.",
                         "Alcance del filtro de servicio")
        if r.alerts.empty and r.kits.empty and acting.empty:
            ui.info_note("No hay alertas, entregas de kits ni registros del bono de contingencia en el territorio de la consulta.",
                         "Sin acciones registradas")
        else:
            ui.section_heading("Acciones en el territorio", f"{respuesta._n(len(acting), 'provincia')} con acciones registradas · "
                                                            "cronología y provincias", "map")
            with st.container(border=True, key="card_response_evolution"):
                ui.chart_title(f"Evolución de las alertas desde el {r.since:%d/%m/%Y}",
                               f"Alertas con afectación documentada registradas cada día y su acumulado al {r.cut:%d/%m/%Y}")
                show_chart(respuesta.alerts_evolution(r), "response_evolution")
            with st.container(border=True, key="card_response_provinces"):
                ui.chart_title("Acciones del Ministerio en cada provincia",
                               "Con la exposición de sus UA según los filtros de servicio, amenaza y susceptibilidad")
                self._actions_table(acting)
        if not r.alerts.empty:
            ui.section_heading("Alertas en servicios MTDH", f"{respuesta._n(len(r.alerts), 'alerta')} con afectación documentada · "
                                                            f"{respuesta._n(r.units, 'UA', 'UA')} · {r.scope_text().lower()}", "shield")
            with st.container(border=True, key="card_response_alert_table"):
                ui.chart_title("Cada alerta con su unidad, territorio, afectación y estado",
                               "Código y nombre de la UA cuando constan en la fuente · de la más reciente a la más antigua")
                respuesta.alerts_table(r)
        ui.section_heading("Kits y bono de contingencia", "Entregas del fin de semana y planificación nacional del bono", "hand-coins")
        left, right = self._pair((1.2, 1))
        if not r.kits.empty:
            with left, st.container(border=True, key="card_response_kit_table"):
                ui.chart_title("Entregas de kits", f"Fecha, provincia, cantón y kits de cada entrega · corte {r.cut_text('kits')}")
                respuesta.kits_table(r)
        with right if not r.kits.empty else left, st.container(border=True, key="card_response_plan"):
            ui.chart_title("Planificación El Niño 2026–2027", "Bono de contingencia · proyección nacional")
            respuesta.plan_tiles(r)

    def action_rows(self) -> pd.DataFrame:
        """Provinces of the consultation with an action of the Ministry, with their exposure and the detail of each action."""
        rows = self.integrated_rows()
        rows = rows.loc[rows.acciones].reset_index(drop=True)
        details = self.response.details_by_province(national=True) if self.response else {}
        rows["provincia_sub"] = [("Cantones: " + details.get(code, {}).get("cantons", "")) if details.get(code, {}).get("cantons") else ""
                                 for code in rows.provincia_codigo]
        rows["expuestas_sub"] = [f"{ui.pct(p)} de sus {ui.number(i)} UA" for p, i in zip(rows.porcentaje, rows.inventario)]
        rows["alertas_sub"] = [details.get(code, {}).get("alert_states", "") for code in rows.provincia_codigo]
        rows["kits_sub"] = [details.get(code, {}).get("deliveries", "") for code in rows.provincia_codigo]
        rows["gestionados_sub"] = [f"USD {ui.number(v, 2)}" if v else "" for v in rows.monto_gestionado]
        rows["articulacion_sub"] = [f"USD {ui.number(v, 2)}" if v else "" for v in rows.monto_articulacion]
        return rows

    def _actions_table(self, rows: pd.DataFrame) -> None:
        if rows.empty:
            ui.info_note("Las provincias de la consulta no registran acciones del Ministerio en este seguimiento.", "Sin acciones registradas")
        else:
            columns = [{"key": "nombre", "label": "Provincia", "kind": "strong", "sub": "provincia_sub"},
                       {"key": "expuestas", "label": "UA expuestas", "kind": "num", "sub": "expuestas_sub"},
                       {"key": "Muy alta", "label": "Muy alta", "kind": "num", "zero": "dash"},
                       {"key": "alertas", "label": "Alertas", "kind": "num", "zero": "dash", "sub": "alertas_sub"},
                       {"key": "kits", "label": "Kits", "kind": "num", "zero": "dash", "sub": "kits_sub"},
                       {"key": "gestionados", "label": "Bono gestionado", "kind": "num", "zero": "dash", "sub": "gestionados_sub"},
                       {"key": "articulacion", "label": "En articulación", "kind": "num", "zero": "dash", "sub": "articulacion_sub"}]
            total = {"nombre": f"Total de {respuesta._n(len(rows), 'provincia')}", **{c["key"]: rows[c["key"]].sum() for c in columns[1:]}}
            ui.rich_table(columns, rows.to_dict("records"), total=total)
            st.caption("Bono gestionado y en articulación: personas por inundaciones (pagos gestionados desde el "
                       f"{pd.Timestamp(self.response.cuts['bonos_desde']):%d/%m/%Y} y casos en articulación al "
                       f"{pd.Timestamp(self.response.cuts['bonos']):%d/%m/%Y}). Las acciones no se suman entre sí.")
        rows = self.integrated_rows()
        layout = [("Provincia", "nombre", "text", 26.0), ("UA", "inventario", "int", 10.0), ("UA expuestas", "expuestas", "int", 13.0),
                  ("% expuesto", "porcentaje", "pct", 12.0), ("Muy alta", "Muy alta", "int", 10.0),
                  ("Multiamenaza", "multiamenaza", "int", 13.0), ("Alertas", "alertas", "int", 10.0), ("Kits", "kits", "int", 10.0),
                  ("Bono gestionado (personas)", "gestionados", "int", 16.0), ("Monto gestionado (USD)", "monto_gestionado", "usd", 18.0),
                  ("En articulación (personas)", "articulacion", "int", 16.0), ("Monto en articulación (USD)", "monto_articulacion", "usd", 18.0)]
        download_table(rows, layout, title="Exposición y respuesta por provincia", subtitle=f"{self.context_label} · {self.selection_label}",
                       period_label=self.period["label"], file_name=f"MTDH_riesgos_provincias_{self.period['id']}.xlsx",
                       key="risk_integrated_xlsx", share_fields=("porcentaje",),
                       label=f"Descargar exposición y respuesta de {respuesta._n(len(rows), 'provincia')} (Excel)")

    def integrated_rows(self) -> pd.DataFrame:
        """Provinces of the consultation: exposure (service and threat filters) and the actions of the Ministry."""
        rows = self.national_table()
        if self.provinces:
            rows = rows.loc[rows.provincia_codigo.isin(self.provinces)]
        rows = rows.loc[rows.inventario.gt(0)].copy()
        rows["nombre"] = rows.provincia.map(names.place)
        rows["acciones"] = rows[["alertas", "kits", "gestionados", "articulacion"]].sum(axis=1).gt(0)
        return rows.sort_values(["expuestas", "inventario"], ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------------------------------- exposure
    def _threats(self) -> None:
        ui.section_heading("Exposición por amenaza", f"{self.context_label} · {self.selection_label}", "storm")
        left, right = self._pair()
        with left, st.container(border=True, key="card_risk_threats"):
            ui.chart_title("Unidades expuestas por amenaza y susceptibilidad",
                           "UA por categoría · al final, UA expuestas y porcentaje de las UA de la selección")
            show_chart(threat_bars(self.threats, self.levels), "risk_threats_chart")
        with right, st.container(border=True, key="card_risk_concurrency"):
            ui.chart_title("Amenazas simultáneas", "UA expuestas según cuántas de las cuatro amenazas enfrentan a la vez")
            show_chart(concurrency_columns(self.concurrent), "risk_concurrency_chart")
        combos = self.combos.head(8)
        with st.container(border=True, key="card_risk_combos"):
            ui.chart_title("Combinaciones de amenazas más frecuentes",
                           f"Cada UA expuesta pertenece a una sola combinación · {len(combos)} de {len(self.combos)} combinaciones")
            # On phones the long combinations wrap so their names stay inside the card.
            full = list(combos.combinacion)
            labels = [_label(name, 22) for name in full] if compact() else full
            show_chart(share_bars(labels, list(combos.unidades), list(combos.porcentaje), hover=full, per=46 if compact() else 34,
                                  color=theme.VIOLETA_500), "risk_combos_chart")

    def _services(self) -> None:
        ui.section_heading("Exposición por servicio", self.context_label, "building")
        left, right = self._pair()
        with left, st.container(border=True, key="card_risk_services"):
            ui.chart_title("Unidades expuestas por servicio",
                           "Según la susceptibilidad más alta de cada UA · al final, UA expuestas y porcentaje del servicio")
            show_chart(service_bars(self.service_rows, self.levels), "risk_services_chart")
        with right, st.container(border=True, key="card_risk_service_matrix"):
            ui.chart_title("Servicio y amenaza", "Porcentaje de las UA de cada servicio expuesto a cada amenaza")
            show_chart(threat_matrix(self.service_rows, "servicio", row_word="el servicio"), "risk_service_matrix")

    def reach_tiles(self) -> list[dict]:
        rows = self.province_rows
        services = self.service_rows

        def half_text(count: int, what: str) -> str:
            return f"{'reúne' if count == 1 else 'reúnen'} la mitad de {what}"
        tiles = [{"icon": "map", "title": "Provincias", "count": int(rows.expuestas.gt(0).sum()), "with_text": "con UA expuestas",
                  "half": half_count(rows.expuestas), "half_text": half_text(half_count(rows.expuestas), "las UA expuestas")},
                 {"icon": "building", "title": "Servicios", "count": int(services.expuestas.gt(0).sum()), "with_text": "con UA expuestas",
                  "half": half_count(services.expuestas), "half_text": half_text(half_count(services.expuestas), "las UA expuestas")}]
        if "Muy alta" in self.levels and rows["Muy alta"].gt(0).any():
            half = half_count(rows["Muy alta"])
            tiles.append({"icon": "flame", "title": "Provincias en muy alta", "count": int(rows["Muy alta"].gt(0).sum()),
                          "with_text": "con UA en muy alta", "half": half, "half_text": half_text(half, "las UA en muy alta")})
        return tiles

    def _territory(self) -> None:
        ui.section_heading("Exposición por territorio", f"{self.period['label']} · {self.programs_label} · {self.selection_label}", "map")
        ui.reach_strip(self.reach_tiles())
        left, right = self._pair()
        highlight = set(self.provinces)
        with left, st.container(border=True, key="card_risk_provinces"):
            head, toggle = st.columns([1.2, 1], gap="small", vertical_alignment="center")
            options = [k for k in RANK_METRICS if k != "muy_alta" or "Muy alta" in self.levels]
            if st.session_state.get("lvl_risk_rank") not in options:
                st.session_state["lvl_risk_rank"] = options[0]
            with toggle:
                metric = st.segmented_control("Medida", options, format_func=RANK_METRICS.get, key="lvl_risk_rank", required=True,
                                              label_visibility="collapsed", width="stretch" if compact() else "content")
            with head:
                subtitle = {"expuestas": "UA expuestas y su participación en el total nacional",
                            "porcentaje": "Porcentaje de las UA de cada provincia que está expuesto",
                            "muy_alta": "UA con al menos una amenaza en muy alta"}[metric]
                ui.chart_title("Unidades expuestas por provincia", subtitle + (" · en dorado, la selección" if highlight else ""))
            show_chart(province_bars(self.national_rows, metric, highlight), "risk_provinces_chart")
        with right, st.container(border=True, key="card_risk_province_matrix"):
            rows = self.national_rows.assign(provincia=self.national_rows.provincia.map(names.place))
            ui.chart_title("Provincia y amenaza", "Porcentaje de las UA de cada provincia expuesto a cada amenaza"
                           + (" · en negrita, la selección" if highlight else ""))
            show_chart(threat_matrix(rows, "provincia", highlight=highlight, code_col="provincia_codigo"), "risk_province_matrix")

    def unit_rows(self) -> pd.DataFrame:
        """Exposed units of the selection: code, name, service, province, the four threats and how many apply."""
        detail = self.detail_selected.copy()
        detail["provincia"] = detail.provincia.map(names.place)
        detail["amenazas"] = riesgos.threat_count(detail, self.levels)
        detail["nivel_maximo"] = riesgos.max_level(detail, self.threat, self.levels)
        detail["_rank"] = detail.nivel_maximo.map(riesgos.RANK).fillna(0)
        return detail.sort_values(["_rank", "amenazas", "servicio", "provincia", "nombre"],
                                  ascending=[False, False, True, True, True]).drop(columns="_rank").reset_index(drop=True)

    def table(self) -> None:
        ui.section_heading("Unidades de atención expuestas", f"{self.context_label} · {self.selection_label}", "building")
        with st.container(border=True, key="card_risk_table"):
            ui.chart_title("Cada unidad con su susceptibilidad a las cuatro amenazas",
                           "Ordenadas de la susceptibilidad más alta a la más baja · el color indica la categoría")
            query = st.text_input("Buscar código, unidad, provincia o servicio", key="risk_search",
                                  placeholder="Código o nombre de la unidad, provincia o servicio")
            detail = self.unit_rows()
            if query.strip():
                mask = detail[["codigo_ua", "nombre", "provincia", "servicio"]].apply(
                    lambda column: column.str.contains(query.strip(), case=False, regex=False, na=False)).any(axis=1)
                detail = detail.loc[mask]
            labels = {"codigo_ua": "Código UA", "nombre": "Unidad de atención", "servicio": "Servicio", "provincia": "Provincia",
                      "nivel_maximo": "Más alta", **riesgos.THREATS, "amenazas": "Amenazas"}
            # Widths that fit the card at desktop width; the threats read «Sin categoría» here (the downloads keep the
            # wording of the source).
            widths = {"codigo_ua": 78, "nombre": 248, "servicio": 176, "provincia": 106, "nivel_maximo": 84, "susc_inundacion": 104,
                      "susc_movimientos_masa": 150, "susc_sequia": 84, "susc_inc_forestales": 134, "amenazas": 88}
            columns = {key: (label, "int" if key == "amenazas" else "text", widths.get(key, 120),
                             "Amenazas en las categorías elegidas" if key == "amenazas" else None)
                       for key, label in labels.items()}
            tones = {key: SUSCEPTIBILITY_CELLS for key in [*riesgos.THREATS, "nivel_maximo"]}
            shown = detail.copy()
            for key in [*riesgos.THREATS, "nivel_maximo"]:
                shown[key] = shown[key].replace({"Sin categoría reportada": "Sin categoría"})
            ui.data_table(shown, columns, height=440, key="risk_table", tones=tones)
            st.caption(f"{ui.number(len(detail))} unidades únicas en la tabla. La búsqueda solo filtra esta tabla; "
                       "«Sin categoría» (sin categoría reportada en la fuente) no acredita ausencia de riesgo.")
            with st.container(horizontal=True, gap="small", key="risk_downloads"):
                exported = [k for k in labels if k != "nivel_maximo"]
                st.download_button("Descargar unidades (CSV)",
                                   detail[exported].rename(columns=labels).assign(Corte=self.period["label"])
                                   .to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"MTDH_riesgos_UA_{self.period['id']}.csv", mime="text/csv",
                                   icon=":material/download:", key="risk_download")
                layout = [("Código UA", "codigo_ua", "text", 12.0), ("Unidad de atención", "nombre", "text", 46.0),
                          ("Servicio", "servicio", "text", 28.0), ("Provincia", "provincia", "text", 20.0)]
                layout += [(label, key, "text", 22.0) for key, label in riesgos.THREATS.items()]
                layout.append(("Amenazas", "amenazas", "int", 12.0))
                download_table(detail, layout, title="Unidades de atención expuestas", subtitle=f"{self.context_label} · {self.selection_label}",
                               period_label=self.period["label"], file_name=f"MTDH_riesgos_UA_{self.period['id']}.xlsx",
                               key="risk_xlsx", share_fields=())

    def methodology(self) -> None:
        items = "".join(f'<div><dt>{ui._esc(term)}</dt><dd>{ui._esc(text)}</dd></div>' for term, text in DEFINITIONS)
        scopes = ""
        if self.response:
            scopes = ('<h4>Alcance de la respuesta</h4><dl class="method-defs">'
                      + "".join(f'<div><dt>{ui._esc(term)}</dt><dd>{ui._esc(text)}</dd></div>' for term, text in RESPONSE_SCOPES)
                      + f'<div><dt>Revisión de alertas</dt><dd>{ui._esc(enos.QUALITY_NOTE)}</dd></div></dl>')
        st.markdown(
            f'<section class="method-card"><header><span class="method-icon">{ui.icon("info", 20)}</span><h3>Nota metodológica</h3></header>'
            f'<p>{ui._esc(METHODOLOGY)}</p><dl class="method-defs">{items}</dl>{scopes}<p class="method-source">{ui._esc(SOURCES)} '
            'Respuesta: Subsecretaría Territorial (análisis de alertas), reporte ministerial de kits y ayuda memoria del bono de '
            'contingencia. Hay unidades sin coordenadas en la fuente.</p></section>', unsafe_allow_html=True)

    @staticmethod
    def geoportal() -> None:
        ui.geoportal_card("riesgos", "Consulte la ubicación de las unidades de atención y las zonas de amenaza natural "
                                    "y riesgo antrópico en el visor geográfico del Ministerio.")

    # ---------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        items = [("Exposición", self.period["label"]), ("Territorio", self.territory_label), ("Servicios", self.programs_label),
                 ("Amenaza", self.threat_label), ("Susceptibilidad", self.levels_label)]
        if self.response:
            items.insert(1, ("Respuesta", self.response.scope_text()))
        return items

    def products_notes(self) -> dict[str, str]:
        if not self.response:
            return {"resumen": "Dos páginas en PDF: cifras clave, mapa, amenazas, servicios, provincias y nota metodológica.",
                    "presentacion": "Seis diapositivas editables: cifras clave, amenazas, combinaciones y servicios, mapa, provincias "
                                    "y metodología.",
                    "datos": "Excel con resumen, amenazas, servicios, provincias, unidades y ficha técnica."}
        return {"resumen": "Dos páginas en PDF: la exposición de las unidades de atención (mapa, amenazas y combinaciones) y la "
                           "respuesta del Ministerio (alertas, provincias con acciones, kits y bono), con sus alcances.",
                "presentacion": "Siete diapositivas editables: cifras clave, amenazas, combinaciones y servicios, alertas, kits y "
                                "bono, exposición y respuesta por provincia, y metodología.",
                "datos": "Excel con resumen, amenazas, servicios, provincias (exposición y acciones), respuesta, unidades y ficha técnica."}

    def sheets(self) -> list[str]:
        middle = ["Respuesta"] if self.response else []
        return ["Resumen", "Amenazas", "Servicios", "Provincias", *middle, "Unidades", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        items = [("grid", "Cifras clave", "Exposición de las UA y respuesta del Ministerio, con el mismo peso" if self.response
                  else "UA expuestas, multiamenaza, muy alta y amenazas simultáneas"),
                 ("storm", "Exposición", "Amenazas, categorías, amenazas simultáneas, combinaciones y servicios")]
        if self.response:
            items.append(("life-buoy", "Respuesta del Ministerio", "Alertas en servicios, kits entregados y bono de contingencia"))
        items.append(("map", "Provincias", "Exposición y acciones de cada provincia, con su mapa" if self.response
                      else "Exposición de cada provincia, con su mapa"))
        if kind == "datos":
            items.append(("table", "Unidades de atención", "Código, nombre, servicio, provincia y amenazas"))
        return items + [("document", "Nota metodológica", "Alcances, definiciones, fuentes y acceso al geoportal")]

    def slide_titles(self) -> tuple[str, str]:
        return ("Exposición por amenaza", "Alertas con afectación a servicios MTDH") if self.response else \
            ("Exposición por amenaza", "Unidades expuestas por provincia")

    def preview_visual(self) -> str:
        svg, _label = self.map_svg("expuestas", night=False, width=300)
        return svg

    def digest(self) -> str:
        response = self.response.data.get("generado_utc") if self.response else ""
        return fingerprint(self.selected, self.detail_selected, self.multihazard, self.period, self.provinces, self.programs,
                           self.threat, self.levels, METHODOLOGY, self.update_stamp(), str(self.response_path), response)

    def report_context(self, title: str) -> dict:
        from src.reports.risks import build_context
        return build_context(self, title=title)
