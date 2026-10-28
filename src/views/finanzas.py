"""Budget views with one explicit source and reporting scope per selection."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from textwrap import wrap

from src import finanzas, theme, ui
from src.data import MONTHS
from src.views.common import download_table, fingerprint, show_chart


class FinanceView:
    kind = "presupuesto"
    id = "presupuesto"
    empty_message = "La selección no registra presupuesto. Ajuste los filtros."

    def __init__(self, frame: pd.DataFrame, *, government: bool = False, metadata: dict | None = None):
        self.frame, self.government, self.metadata = frame, government, metadata or {}
        self.file_id = "presupuesto_gobierno" if government else "presupuesto_fiscal"
        self.label = "Presupuesto acumulado de gobierno" if government else "Presupuesto fiscal"
        self.dimensions = ({"programa": "Programa", "provincia": "Provincia", "ambito": "Ámbito"} if government else
                           {"programa": "Programa", "tipo_gasto": "Tipo de gasto", "grupo_gasto": "Grupo de gasto", "fuente": "Fuente de financiamiento"})

    def catalog(self):
        return [{"id": p, "year": int(p[:4]), "month": int(p[5:]),
                 "label": f"{MONTHS[int(p[5:]) - 1].capitalize()} {p[:4]}"}
                for p in sorted(self.frame.periodo_id.unique(), reverse=True)]

    def select(self, period: dict, **filters):
        self.period = period
        self.filters = {d: list(filters.get(d, ())) for d in self.dimensions}

    def controls(self, period):
        self.select(period)
        dimensions = ["programa", "provincia", "ambito"] if self.government else ["programa", "tipo_gasto", "fuente"]
        columns = st.columns(len(dimensions), gap="small")
        for column, dimension in zip(columns, dimensions):
            options = sorted(self.frame.loc[self.frame.periodo_id.eq(period["id"]), dimension].unique())
            key = self.file_id + "_" + dimension
            if key in st.session_state:
                st.session_state[key] = [v for v in st.session_state[key] if v in options]
            with column:
                self.filters[dimension] = st.multiselect(self.dimensions[dimension], options, key=key, placeholder="Todos")

    def prepare(self):
        frame = self.frame.loc[self.frame.periodo_id.eq(self.period["id"])].copy()
        for dimension, selected in self.filters.items():
            if selected:
                frame = frame.loc[frame[dimension].isin(selected)]
        if frame.empty:
            return False
        self.filtered = frame
        measures = finanzas.GOVERNMENT_MEASURES if self.government else finanzas.FISCAL_MEASURES
        self.stats = {m: float(frame[m].sum()) for m in measures}
        if not self.government:
            coded = self.stats["codificado"]
            self.stats["ejecucion"] = self.stats["devengado"] / coded * 100 if coded else None
            self.stats["saldo_por_devengar"] = coded - self.stats["devengado"]
        self.territory_label = ", ".join(self.filters.get("provincia", [])) or "Total nacional"
        self.programs_label = ", ".join(self.filters.get("programa", [])) or "Todos los programas"
        self.context_label = f"Año fiscal {self.period['year']} · corte {self.period['label'].lower()}"
        return True

    @property
    def scope_note(self):
        if self.government:
            return ("Acumulado de gobierno reportado en VIS–VIE: 2023–2025 más el presupuesto 2026 registrado al corte. "
                    "El componente 2026 forma parte del acumulado. Incluye programas históricos sin cobertura actual.")
        return ("Ejecución fiscal institucional publicada por SGDE, con corte al 30 de septiembre de 2026. "
                "La ejecución social de enero a septiembre (MDH–MTDH) se presenta en Social; son universos distintos y no se suman.")

    def hero_copy(self):
        return f"Año fiscal {self.period['year']}", self.label, self.scope_note

    def update_stamp(self):
        return {"line": f"Corte {self.period['label'].lower()} · conciliado el 27/10/2026", "short": f"Corte {self.period['label'].lower()}"}

    def hero_visual(self):
        ui.hero_series(self.preview_visual(night=True, width=640, height=330),
                       "Composición del acumulado · millones de USD" if self.government else "Presupuesto fiscal · millones de USD")

    def preview_visual(self, night=False, width=300, height=170):
        keys = ["anterior", "fiscal", "acumulado"] if self.government else ["codificado", "comprometido", "devengado"]
        labels = ["2023–2025", str(self.period["year"]), "Gobierno"] if self.government else ["Codificado", "Comprometido", "Devengado"]
        return ui.svg_columns([self.stats[k]/1e6 for k in keys], labels, width=width, height=height, night=night,
                              value_text=lambda v: ui.number(v, 1), css_class="ec-columns" if night else "ec-columns mini")

    def kpi_cards(self):
        year = self.period["year"]
        pairs = ([("anterior", "Acumulado 2023–2025"), ("fiscal", f"Componente fiscal {year}"),
                  ("acumulado", f"Acumulado de gobierno 2023–{year}")] if self.government else
                 [("codificado", f"Codificado fiscal {year}"), ("devengado", "Ejecutado (devengado)"),
                  ("ejecucion", "Ejecución fiscal"), ("saldo_disponible", "Saldo disponible")])
        cards = []
        for i, (key, label) in enumerate(pairs):
            rate = key == "ejecucion"
            cards.append({"label": label, "value": self.stats[key] if rate else self.stats[key]/1e6,
                          "decimals": 2 if rate else 1, "prefix": "" if rate else "USD", "suffix": "%" if rate else "millones",
                          "tone": ["morado", "oro", "lila", "fucsia"][i], "icon": "target" if rate else "wallet",
                          "note": "Devengado / codificado" if rate else
                                  "Saldo informado por SGDE" if key == "saldo_disponible" else ""})
        return cards

    def chart(self, dimension):
        rows = finanzas.by(self.filtered, dimension, self.government)
        labels = ["<br>".join(wrap(str(value), 34, break_long_words=False)) for value in rows[dimension]]
        fig = go.Figure()
        fields = [("anterior", "2023–2025", theme.MORADO), ("fiscal", str(self.period["year"]), theme.ORO)] if self.government else [
            ("codificado", "Codificado", theme.LILA_300), ("devengado", "Devengado", theme.MORADO)]
        for field, label, color in fields:
            fig.add_bar(y=labels, x=rows[field]/1e6, name=label, orientation="h", marker=dict(color=color, cornerradius=4),
                        customdata=list(zip(rows[dimension], rows[field])),
                        hovertemplate="%{customdata[0]}<br>"+label+": USD %{customdata[1]:,.2f}<extra></extra>")
        fig.update_layout(template="plotly_white", barmode="stack" if self.government else "group",
                          height=max(300, 48*len(rows)+80), margin=dict(l=10,r=20,t=20,b=55),
                          font=dict(family="Public Sans", color=theme.TINTA),
                          xaxis=dict(title="Millones de USD", rangemode="tozero"),
                          yaxis=dict(autorange="reversed", automargin=True), legend=dict(orientation="h", y=-0.13),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        return fig

    def columns(self):
        if self.government:
            return [("Acumulado 2023–2025", "anterior", "money"), (f"Componente {self.period['year']}", "fiscal", "money"),
                    ("Acumulado de gobierno", "acumulado", "money")]
        return [("Codificado", "codificado", "money"), ("Certificado", "certificado", "money"),
                ("Comprometido", "comprometido", "money"), ("Devengado", "devengado", "money"),
                ("Saldo disponible", "saldo_disponible", "money"), ("Ejecución fiscal", "ejecucion", "pct")]

    def dashboard(self):
        ui.section_heading("Presupuesto por programa", self.context_label, "wallet")
        dims = ["programa", "provincia"] if self.government else ["programa", "tipo_gasto"]
        for column, dimension in zip(st.columns(2, gap="medium"), dims):
            with column, st.container(border=True):
                ui.chart_title("Por " + self.dimensions[dimension].lower(), "Millones de USD")
                show_chart(self.chart(dimension), self.file_id + "_chart_" + dimension)
        ui.section_heading("Detalle presupuestario", self.context_label, "table")
        dimension = st.segmented_control("Agrupar por", list(self.dimensions), format_func=self.dimensions.get,
                                          default="programa", key=self.file_id+"_detail", required=True)
        rows = finanzas.by(self.filtered, dimension, self.government)
        columns = {dimension: (self.dimensions[dimension], "text", 330)}
        columns.update({k: (label + (" (USD)" if kind == "money" else ""), kind) for label,k,kind in self.columns()})
        ui.data_table(rows, columns, height=min(800, 35*(len(rows)+1)+3), key=self.file_id+"_table")
        layout = [(self.dimensions[dimension], dimension, "text", 48)] + [
            (label+" (USD)" if kind=="money" else label, key, "usd" if kind=="money" else kind, 22) for label,key,kind in self.columns()]
        download_table(rows, layout, title=self.label, subtitle=self.context_label, period_label=self.period["label"],
                       file_name=f"MTDH_{self.file_id}_{self.period['id']}.xlsx", key=self.file_id+"_download", share_fields=("ejecucion",))
        if not self.government:
            st.caption(f"Saldo por devengar (codificado menos devengado): USD {ui.number(self.stats['saldo_por_devengar'], 2)}. "
                       "El saldo disponible es el valor publicado por SGDE y tiene una definición distinta.")
            st.link_button("Consultar fuente fiscal SGDE", self.metadata["procedencia"]["url"])

    def scope_items(self):
        return [("Año fiscal", str(self.period["year"])), ("Corte", self.period["label"]), ("Ámbito", self.label),
                *[(self.dimensions[k], ", ".join(v)) for k,v in self.filters.items() if v]]

    def products_notes(self):
        return {"resumen": "Cifras clave, gráficos y detalle presupuestario con el corte y alcance de la fuente.",
                "presentacion": "Cifras clave y gráficos de presupuesto con formato institucional.",
                "datos": "Montos exactos, desagregaciones y fuentes del presupuesto seleccionado."}

    def sheets(self):
        return ["Resumen", *self.dimensions.values(), "Detalle", "Ficha técnica"]

    def report_contents(self, kind):
        return [("wallet", "Cifras clave", "Año fiscal, presupuesto y acumulados"),
                ("chart", "Desagregación", "Resultados por programa y ámbito de la fuente"),
                ("table", "Detalle", "Montos en USD y fuente")]

    def slide_titles(self):
        return "Presupuesto por programa", "Detalle presupuestario"

    def digest(self):
        return fingerprint(self.filtered, self.file_id, "finanzas-v1")

    def report_context(self, title):
        from src.reports.finanzas import context
        return context(self, title)
