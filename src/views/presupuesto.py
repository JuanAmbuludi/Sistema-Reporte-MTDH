"""Institutional budget: coded, accrued and execution by program, zone, executing unit and spending group."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, geo, institutional, theme, ui
from src.indicators import AREAS
from src.views.common import compact, download_table, fingerprint, show_chart

MEASURES = {"porcentaje_ejecucion": ("Ejecución", "Ejecución presupuestaria"),
            "presupuesto_ejecutado": ("Devengado", "Presupuesto devengado"),
            "presupuesto_codificado": ("Codificado", "Presupuesto codificado")}


@st.cache_data(show_spinner=False, max_entries=24)
def _zone_svg(values: dict, titles: dict, selected: tuple, night: bool = True, width: int = 640) -> str:
    if night:
        return geo.svg_map(ui.map_fills(values), layer="zona", titles=titles, selected=set(selected), stroke=theme.MORADO_900,
                           width=width)
    return geo.svg_map(ui.map_fills(values, theme.SEQUENTIAL[2:]), layer="zona", titles=titles, selected=set(selected),
                       width=width, pad=6, stroke="#FFFFFF", selected_fill=theme.ORO, equator=None, empty_fill="#F1EEF6",
                       border_color="rgba(81,47,141,.45)", frame_color="rgba(81,47,141,.35)", label_color="rgba(81,47,141,.6)",
                       css_class="ec-map mini")


def _fold(rows: pd.DataFrame, other: str, minimum: float = 1.0) -> pd.DataFrame:
    """Rows below ``minimum`` % of the coded budget are added up as one, so the chart keeps the relevant categories."""
    small = rows.participacion < minimum
    if small.sum() < 2:
        return rows
    rest = rows.loc[small, institutional.MONEY].sum()
    folded = pd.DataFrame([{**rest.to_dict(), "nombre": other}])
    folded["porcentaje_ejecucion"] = folded.presupuesto_ejecutado / folded.presupuesto_codificado.where(folded.presupuesto_codificado > 0) * 100
    return pd.concat([rows.loc[~small], folded], ignore_index=True)


class BudgetView:
    kind = "presupuesto"
    id = "presupuesto"

    def __init__(self, frame: pd.DataFrame, manifest: dict | None):
        self.frame, self.manifest = frame, manifest
        self.label = AREAS["presupuesto"]["label"]
        self._catalog = institutional.catalog(frame)

    def catalog(self) -> list[dict]:
        return self._catalog

    def controls(self, period: dict) -> None:
        self.period = period
        self.scoped = self.frame.loc[self.frame.periodo_id.eq(period["id"])]
        zones = self.scoped.drop_duplicates("zona_orden").sort_values("zona_orden")
        self.zone_names = dict(zip(zones.zona_orden, zones.zona_nombre))
        programs = self.scoped.groupby(["programa_codigo"]).presupuesto_codificado.sum().sort_values(ascending=False)
        self.program_names = self.scoped.drop_duplicates("programa_codigo").set_index("programa_codigo").programa_corto.to_dict()
        self.program_full = self.scoped.drop_duplicates("programa_codigo").set_index("programa_codigo").programa_nombre.to_dict()
        for key, available in [("budget_zones", list(self.zone_names)), ("budget_programs", list(programs.index))]:
            if key in st.session_state:
                st.session_state[key] = [v for v in st.session_state[key] if v in available]
        col_zone, col_program = st.columns(2, gap="small")
        with col_zone:
            self.zones = st.multiselect("Zona", list(self.zone_names), format_func=self.zone_names.get,
                                        placeholder="Todas las zonas", key="budget_zones")
        with col_program:
            self.programs = st.multiselect("Programa presupuestario", list(programs.index), format_func=self.program_names.get,
                                           placeholder="Todos los programas", key="budget_programs")
        if self.zones or self.programs:
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary",
                      key="reset_budget_filters")

    @staticmethod
    def _clear() -> None:
        st.session_state["budget_zones"] = []
        st.session_state["budget_programs"] = []

    empty_message = "La combinación elegida no registra presupuesto. Ajuste la zona o los programas."

    def prepare(self) -> bool:
        scoped = self.scoped
        by_program = scoped.loc[scoped.programa_codigo.isin(self.programs)] if self.programs else scoped
        self.national = by_program
        self.filtered = by_program.loc[by_program.zona_orden.isin(self.zones)] if self.zones else by_program
        if self.filtered.empty or not self.filtered.presupuesto_codificado.sum():
            return False
        self.stats = institutional.summarize(self.filtered)
        self.national_stats = institutional.summarize(self.national)
        self.scope_stats = institutional.summarize(scoped)
        if len(self.zones) == 1:
            name = self.zone_names[self.zones[0]]
            self.territory_label = name
            self.where = "la planta central" if name == "Planta central" else f"la {name}"
        elif self.zones:
            self.territory_label = self.where = f"{len(self.zones)} zonas"
        else:
            self.territory_label, self.where = "Total institucional", ""
        self.programs_label = (self.program_names[self.programs[0]] if len(self.programs) == 1 else
                               f"{len(self.programs)} programas" if self.programs else "Todos los programas")
        self.context_label = f"{self.period['label']} · {self.territory_label}"
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        headline = f"{self.label} en {self.where}" if self.zones else self.label
        return f"Corte {self.period['label'].lower()}", headline, AREAS["presupuesto"]["description"]

    def hero_visual(self) -> None:
        if st.session_state.get("budget_measure") not in MEASURES:
            st.session_state["budget_measure"] = "porcentaje_ejecucion"
        measure = st.segmented_control("Indicador territorial", list(MEASURES), format_func=lambda k: MEASURES[k][0],
                                       key="budget_measure", required=True, width="stretch")
        self.measure = measure
        svg, label = self.map_svg(night=True)
        ui.hero_map(svg, label, selected="Zona seleccionada" if len(self.zones) == 1 else ("Zonas seleccionadas" if self.zones else ""))

    def map_svg(self, night: bool = True, width: int = 640, measure: str | None = None) -> tuple[str, str]:
        measure = measure or self.measure
        values = institutional.zone_values(self.national, measure)
        zones = institutional.by(self.national.loc[self.national.zona_codigo.notna()], "zona")
        titles = {}
        for row in zones.itertuples():
            titles[row.zona_codigo] = (f"{row.nombre}\nEjecución: {ui.pct(row.porcentaje_ejecucion)}\n"
                                       f"Devengado: {charts.money_text(row.presupuesto_ejecutado)} de {charts.money_text(row.presupuesto_codificado)}")
        # Zones are keyed by their map code; the central office ("Z0") has no polygon.
        selected = tuple(sorted(z for z in self.zones if z != "Z0"))
        return _zone_svg(values, titles, selected, night, width), f"{MEASURES[measure][1]} por zona"

    def kpi_cards(self) -> list[dict]:
        stats, reference = self.stats, self.scope_stats
        active = bool(self.zones or self.programs)
        share_label = "del total institucional"

        def share(key):
            return stats[key] / reference[key] * 100 if active and reference.get(key) else None

        return [
            {"label": "Presupuesto codificado", "value": stats["codificado"] / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones",
             "icon": "wallet", "tone": "morado", "share": share("codificado"), "share_label": share_label},
            {"label": "Presupuesto devengado", "value": stats["devengado"] / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones",
             "icon": "banknote", "tone": "oro", "share": share("devengado"), "share_label": share_label},
            {"label": "Ejecución presupuestaria", "value": stats["ejecucion"], "decimals": 1, "suffix": "%", "icon": "target",
             "tone": "lila", "bar": stats["ejecucion"], "bar_label": "Devengado sobre codificado"},
            {"label": "Saldo por devengar", "value": stats["saldo"] / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones",
             "icon": "hourglass", "tone": "fucsia", "note": f"{ui.pct(100 - stats['ejecucion'] if stats['ejecucion'] is not None else None)} del presupuesto codificado"},
        ]

    def dashboard(self) -> None:
        total = self.stats["ejecucion"]
        programs = institutional.by(self.filtered, "programa")
        zones = institutional.by(self.national, "zona")
        highlight = {self.zone_names[z] for z in self.zones}
        groups = _fold(institutional.by(self.filtered, "grupo"), "Otros grupos de gasto")
        kinds = institutional.by(self.filtered, "tipo")
        sources = _fold(institutional.by(self.filtered, "fuente"), "Otras fuentes")
        ui.section_heading("Ejecución presupuestaria", self.context_label, "target")
        subtitle = "Devengado sobre codificado · la línea dorada marca el total de la selección"
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_budget_programs"):
            ui.chart_title("Por programa presupuestario", subtitle)
            show_chart(charts.execution_bullets(programs, "programa_corto", hover_label="programa_nombre", reference=total,
                                                wrap_at=30 if compact() else 0), "budget_programs_chart")
        with right, st.container(border=True, key="card_budget_zones"):
            ui.chart_title("Por zona", "Planta central y coordinaciones zonales · selección en dorado" if highlight else
                           "Planta central y coordinaciones zonales")
            show_chart(charts.execution_bullets(zones, "nombre", highlight=highlight, reference=self.national_stats["ejecucion"],
                                                reference_label="Total"), "budget_zones_chart")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_budget_groups"):
            ui.chart_title("Por grupo de gasto", subtitle)
            show_chart(charts.execution_bullets(groups, "nombre", reference=total, wrap_at=0 if not compact() else 26), "budget_groups")
        with right, st.container(border=True, key="card_budget_sources"):
            ui.chart_title("Por tipo de gasto", "Gasto corriente y de inversión")
            show_chart(charts.execution_bullets(kinds, "nombre", reference=total), "budget_kinds")
            ui.chart_title("Por fuente de financiamiento", "Origen de los recursos")
            show_chart(charts.execution_bullets(sources, "nombre", reference=total), "budget_sources")
        self._table_section()

    LEVELS = {"Por programa": "programa", "Por zona": "zona", "Por unidad ejecutora": "unidad", "Por grupo de gasto": "grupo",
              "Por fuente": "fuente"}

    def detail(self, dimension: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        label = institutional.DIMENSIONS[dimension][0]
        frame = institutional.by(self.filtered, dimension)
        if dimension == "unidad":
            zones = self.filtered.drop_duplicates("unidad_nombre").set_index("unidad_nombre").zona_nombre
            frame["zona"] = frame.nombre.map(zones)
        columns = {"nombre": (label, "text", 330)}
        layout = [(label, "nombre", "text", 48.0)]
        if dimension == "unidad":
            columns["zona"] = ("Zona", "text", 120)
            layout.append(("Zona", "zona", "text", 16.0))
        columns.update({
            "presupuesto_codificado": ("Codificado (USD)", "money", None, None, "Codificado"),
            "presupuesto_ejecutado": ("Devengado (USD)", "money", None, None, "Devengado"),
            "porcentaje_ejecucion": ("Ejecución", "pct"),
            "saldo": ("Saldo por devengar (USD)", "money", None, None, "Saldo"),
            "presupuesto_certificado": ("Certificado (USD)", "money", None, None, "Certificado"),
            "participacion": ("Participación", "pct", None, None, "Peso"),
        })
        layout += [("Codificado (USD)", "presupuesto_codificado", "usd", 19.0), ("Devengado (USD)", "presupuesto_ejecutado", "usd", 19.0),
                   ("Ejecución", "porcentaje_ejecucion", "pct", 12.0), ("Saldo por devengar (USD)", "saldo", "usd", 19.0),
                   ("Certificado (USD)", "presupuesto_certificado", "usd", 17.0), ("Participación en el codificado", "participacion", "pct", 14.0)]
        return frame, columns, layout

    def _table_section(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        if st.session_state.get("budget_level") not in self.LEVELS:
            st.session_state["budget_level"] = next(iter(self.LEVELS))
        name = st.segmented_control("Nivel de detalle", list(self.LEVELS), key="budget_level", required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(self.LEVELS[name])
        with st.container(border=True, key="card_budget_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="budget_table", bar="participacion")
            download_table(frame, layout, title="Presupuesto institucional", subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_presupuesto_{self.period['id']}.xlsx",
                           key="budget_xlsx", share_fields=("participacion", "porcentaje_ejecucion"))

    # --------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.label), ("Zona", self.territory_label),
                ("Programas", self.programs_label)]

    def products_notes(self) -> dict[str, str]:
        return {
            "resumen": "Una página en PDF con las cifras clave, el mapa por zona, la ejecución por programa y los aspectos destacados.",
            "presentacion": "Tres diapositivas editables en PowerPoint: cifras clave, ejecución por zona y por programa.",
            "datos": "Libro de Excel con resumen, programas, zonas y unidades, grupos de gasto, detalle con filtros y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        return ["Resumen", "Programas", "Zonas", "Grupos de gasto", "Detalle", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        if kind == "datos":
            return [("grid", "Resumen", "Cifras clave, mapa y aspectos destacados"),
                    ("chart", "Programas", "Codificado, devengado y ejecución por programa presupuestario"),
                    ("map", "Zonas", "Ejecución por zona y por unidad ejecutora"),
                    ("layers", "Grupos de gasto", "Ejecución por grupo, tipo de gasto y fuente de financiamiento"),
                    ("table", "Detalle", "Cada unidad, programa y grupo de gasto, con filtros y totales"),
                    ("shield", "Ficha técnica", "Periodo, alcance y definiciones")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores principales"),
                    ("map", "Ejecución por zona", "Mapa y zonas con su ejecución"),
                    ("chart", "Ejecución por programa", "Gráfico editable y aspectos destacados")]
        return [("grid", "Cifras clave", "Codificado, devengado, ejecución y saldo"),
                ("map", "Zonas", "Mapa y ejecución por zona"),
                ("chart", "Programas", "Ejecución por programa presupuestario"),
                ("award", "Aspectos destacados", "Conclusiones para la toma de decisiones")]

    def slide_titles(self) -> tuple[str, str]:
        return "Ejecución por zona", "Ejecución por programa"

    def preview_visual(self) -> str:
        svg, _label = self.map_svg(night=False, width=300, measure="porcentaje_ejecucion")
        return svg

    def digest(self) -> str:
        return fingerprint(self.filtered)

    def report_context(self, title: str) -> dict:
        from src.reports.national import budget_context
        return budget_context(self.filtered, national=self.national, scope=self.scoped, title=title, period=self.period,
                              territory_label=self.territory_label, programs_label=self.programs_label,
                              selected_zones=[z for z in self.zones])
