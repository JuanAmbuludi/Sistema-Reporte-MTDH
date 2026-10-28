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

    def select(self, period: dict, zones=(), programs=()) -> None:
        """A cut and a selection without widgets (scripts, tests and the summary of every section)."""
        self.period = period
        self.scoped = self.frame.loc[self.frame.periodo_id.eq(period["id"])]
        zones_frame = self.scoped.drop_duplicates("zona_orden").sort_values("zona_orden")
        self.zone_names = dict(zip(zones_frame.zona_orden, zones_frame.zona_nombre))
        self.program_names = self.scoped.drop_duplicates("programa_codigo").set_index("programa_codigo").programa_corto.to_dict()
        self.program_full = self.scoped.drop_duplicates("programa_codigo").set_index("programa_codigo").programa_nombre.to_dict()
        self.zones, self.programs = list(zones), list(programs)

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
            "resumen": "Dos páginas en PDF: cifras clave, mapa por zona, ejecución por programa y aspectos destacados; composición "
                       "del gasto y unidades ejecutoras.",
            "presentacion": "Cuatro diapositivas editables en PowerPoint: cifras clave, ejecución por zona y por programa, y "
                            "composición del gasto.",
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
                    ("chart", "Ejecución por programa", "Gráfico editable y aspectos destacados"),
                    ("layers", "Composición del gasto", "Grupos de gasto, fuentes de financiamiento y tipo de gasto")]
        return [("grid", "Cifras clave", "Codificado, devengado, ejecución y saldo"),
                ("map", "Zonas y programas", "Mapa, ejecución por zona y por programa presupuestario"),
                ("award", "Aspectos destacados", "Conclusiones para la toma de decisiones"),
                ("layers", "Composición del gasto", "Grupos, fuentes, tipo de gasto y unidades ejecutoras")]

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


# ------------------------------------------------------------------------------------------------ social budget
MONTH_NAMES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
               "diciembre")


class SocialBudgetView:
    """The approved social budget (spending groups 58, 57 and 78): allocations, accrued budget of each month and execution."""

    kind = "presupuesto"
    id = "presupuesto"
    file_id = "presupuesto_social"
    universe = "social"

    def __init__(self, groups: pd.DataFrame, programs: pd.DataFrame):
        self.groups, self.programs_rows = groups, programs
        self.label = "Presupuesto social"
        self._catalog = []
        for period_id in sorted(groups.periodo_id.unique(), reverse=True) if not groups.empty else []:
            year, month = map(int, period_id.split("-"))
            self._catalog.append({"id": period_id, "year": year, "month": month, "label": f"{MONTH_NAMES[month - 1].capitalize()} {year}"})

    def catalog(self) -> list[dict]:
        return self._catalog

    def select(self, period: dict, groups=()) -> None:
        self.period, self.chosen = period, list(groups)

    def controls(self, period: dict) -> None:
        self.period = period
        latest = self.groups.loc[self.groups.periodo_id.eq(period["id"])].sort_values("presupuesto_aprobado", ascending=False)
        names = dict(zip(latest.grupo_presupuestario, latest.nombre))
        if "social_groups" in st.session_state:
            st.session_state["social_groups"] = [g for g in st.session_state["social_groups"] if g in names]
        self.chosen = st.multiselect("Programa presupuestario", list(names), format_func=names.get, placeholder="Todos los programas",
                                     key="social_groups")
        if self.chosen:
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary", key="reset_social")

    @staticmethod
    def _clear() -> None:
        st.session_state["social_groups"] = []

    empty_message = "La combinación elegida no registra presupuesto. Ajuste los programas."

    def prepare(self) -> bool:
        period = self.period
        rows = self.groups.loc[self.groups.grupo_presupuestario.isin(self.chosen)] if self.chosen else self.groups
        self.month = rows.loc[rows.periodo_id.eq(period["id"])].copy()
        if self.month.empty:
            return False
        self.year_rows = rows.loc[rows.periodo_id.str[:4].eq(str(period["year"])) & rows.periodo_id.le(period["id"])]
        self.series = self.year_rows.groupby("periodo_id", as_index=False)[["devengado_mes", "devengado_acumulado"]].sum()
        approved = float(self.month.presupuesto_aprobado.sum())
        self.series["presupuesto_aprobado"] = approved
        self.series["porcentaje_ejecucion"] = self.series.devengado_acumulado / approved * 100 if approved else None
        self.series["mes"] = [MONTH_NAMES[int(p[5:]) - 1].capitalize() for p in self.series.periodo_id]
        accrued = float(self.month.devengado_acumulado.sum())
        self.stats = {"approved": approved, "accrued": accrued, "month": float(self.month.devengado_mes.sum()),
                      "planned": float(self.month.planificado_anual.sum()), "execution": accrued / approved * 100 if approved else None,
                      "balance": approved - accrued, "pace": period["month"] / 12 * 100}
        self.programs_label = (self.month.nombre.iloc[0] if len(self.chosen) == 1 else f"{len(self.chosen)} programas" if self.chosen
                               else "Todos los programas")
        self.territory_label = "Total nacional"
        self.context_label = f"{period['label']} · {self.programs_label}"
        self.span = f"enero a {MONTH_NAMES[period['month'] - 1]} de {period['year']}" if period["month"] > 1 else f"enero de {period['year']}"
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return (f"Año fiscal {self.period['year']} · corte {self.period['label'].lower()}", self.label,
                f"Presupuesto aprobado y devengado acumulado de {self.span}, grupos 58, 57 y 78.")

    def update_stamp(self) -> dict:
        from src import corte
        return corte.stamp(self.id, self.period)

    def series_svg(self, night: bool = True, width: int = 640, height: int = 360) -> str:
        series = self.series
        selected = list(series.periodo_id).index(self.period["id"]) if self.period["id"] in set(series.periodo_id) else None
        return ui.svg_columns([float(v) / 1e6 for v in series.devengado_mes], [m[:3] for m in series.mes],
                              titles=[f"{m} {self.period['year']}: USD {ui.number(v / 1e6, 1)} millones" for m, v in zip(series.mes, series.devengado_mes)],
                              width=width, height=height, night=night, highlight=selected, value_text=lambda v: ui.number(v, 1),
                              css_class="ec-columns" if night else "ec-columns mini")

    def hero_visual(self) -> None:
        ui.hero_series(self.series_svg(), f"Presupuesto devengado por mes · millones de USD · {self.programs_label}")

    def kpi_cards(self) -> list[dict]:
        stats = self.stats
        return [
            {"label": f"Presupuesto aprobado {self.period['year']}", "value": stats["approved"] / 1e6, "decimals": 1, "prefix": "USD",
             "suffix": "millones", "icon": "wallet", "tone": "morado", "note": f"Planificado anual: USD {ui.millions(stats['planned'])} M"},
            {"label": "Presupuesto devengado", "value": stats["accrued"] / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones",
             "icon": "banknote", "tone": "oro", "note": f"De {self.span}"},
            {"label": "Ejecución presupuestaria", "value": stats["execution"], "decimals": 1, "suffix": "%", "icon": "target", "tone": "lila",
             "bar": stats["execution"], "bar_label": f"Ritmo uniforme del año: {ui.pct(stats['pace'])}"},
            {"label": f"Devengado de {MONTH_NAMES[self.period['month'] - 1]}", "value": stats["month"] / 1e6, "decimals": 1, "prefix": "USD",
             "suffix": "millones", "icon": "calendar", "tone": "fucsia", "note": f"Saldo por devengar: USD {ui.millions(stats['balance'])} M"},
        ]

    def dashboard(self) -> None:
        stats, period, series = self.stats, self.period, self.series
        ui.section_heading("Ejecución presupuestaria", f"{self.context_label} · devengado acumulado sobre presupuesto aprobado", "target")
        rows = self.month.rename(columns={"devengado_acumulado": "presupuesto_ejecutado", "presupuesto_aprobado": "presupuesto_codificado"})
        rows = rows.sort_values("presupuesto_codificado", ascending=False)
        labels = [m[:3] for m in series.mes]
        selected = list(series.periodo_id).index(period["id"]) if period["id"] in set(series.periodo_id) else None
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_social_programs"):
            ui.chart_title("Por programa presupuestario", f"Devengado de {self.span} sobre aprobado · la línea dorada marca el total")
            show_chart(charts.execution_bullets(rows, "nombre", reference=stats["execution"], wrap_at=30 if compact() else 0,
                                                denominator_label="Aprobado"), "social_programs")
        with right, st.container(border=True, key="card_social_pace"):
            ui.chart_title("Ejecución acumulada por mes", "Frente a un ritmo uniforme de una doceava parte del presupuesto por mes")
            show_chart(charts.cumulative_execution(labels, list(series.porcentaje_ejecucion), selected=selected,
                                                   months=[int(p[5:]) for p in series.periodo_id],
                                                   full=[f"{m} {period['year']}" for m in series.mes]), "social_pace")
        ui.section_heading("Devengado mensual", f"Millones de USD · {self.programs_label}", "banknote")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_social_months"):
            ui.chart_title("Presupuesto devengado por mes", "El mes de la consulta en dorado")
            show_chart(charts.month_columns(labels, list(series.devengado_mes), selected=selected, money=True,
                                            full=[f"{m} {period['year']}" for m in series.mes]), "social_months")
        with right:
            spending = self.month.groupby("grupo_gasto_nombre", as_index=False)[["devengado_acumulado", "presupuesto_aprobado"]].sum()
            if len(spending) > 1:
                with st.container(border=True, key="card_social_spending"):
                    spending = spending.rename(columns={"devengado_acumulado": "presupuesto_ejecutado", "presupuesto_aprobado": "presupuesto_codificado"})
                    spending["porcentaje_ejecucion"] = spending.presupuesto_ejecutado / spending.presupuesto_codificado * 100
                    ui.chart_title("Por grupo de gasto", "Devengado acumulado sobre aprobado")
                    show_chart(charts.execution_bullets(spending.sort_values("presupuesto_codificado", ascending=False), "grupo_gasto_nombre",
                                                        reference=stats["execution"], wrap_at=26 if compact() else 0), "social_spending")
            remaining = 12 - period["month"]
            if remaining > 0 and stats["approved"]:
                # The pace the rest of the year needs to accrue the whole approved budget.
                average = stats["accrued"] / period["month"]
                required = max(0.0, stats["balance"]) / remaining
                months = f"{MONTH_NAMES[period['month']]} a diciembre" if remaining > 1 else "diciembre"
                ui.focus_tile("hourglass", f"Ritmo necesario de {months}", f"USD {ui.millions(required)} millones por mes",
                              f"Para devengar el 100 % del presupuesto aprobado. El promedio de {self.span} fue de USD "
                              f"{ui.millions(average)} millones por mes.")
        self._table()

    LEVELS = {"Por programa": "programa", "Por mes": "mes", "Programa y mes": "matriz"}

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        if level == "mes":
            frame = self.series.assign(mes_nombre=[f"{m} {self.period['year']}" for m in self.series.mes])
            columns = {"mes_nombre": ("Mes", "text", 160), "devengado_mes": ("Devengado del mes (USD)", "money", None, None, "Devengado"),
                       "devengado_acumulado": ("Devengado acumulado (USD)", "money", None, None, "Acumulado"),
                       "porcentaje_ejecucion": ("Ejecución acumulada", "pct")}
            layout = [("Mes", "mes_nombre", "text", 18.0), ("Devengado del mes (USD)", "devengado_mes", "usd", 20.0),
                      ("Devengado acumulado (USD)", "devengado_acumulado", "usd", 20.0), ("Ejecución acumulada", "porcentaje_ejecucion", "pct", 14.0)]
            return frame, columns, layout
        if level == "matriz":
            frame = self.year_rows.pivot_table(index="nombre", columns="periodo_id", values="devengado_mes", aggfunc="sum")
            ids = list(frame.columns)
            frame.columns = [MONTH_NAMES[int(p[5:]) - 1][:3].capitalize() for p in ids]
            frame["Total"] = frame.sum(axis=1)
            frame = frame.reset_index().sort_values("Total", ascending=False)
            columns = {"nombre": ("Programa presupuestario", "text", 280)}
            layout = [("Programa presupuestario", "nombre", "text", 40.0)]
            for name in [c for c in frame.columns if c != "nombre"]:
                columns[name] = (name, "money")
                layout.append((name, name, "usd", 15.0))
            return frame, columns, layout
        frame = self.month.copy()
        total = frame.presupuesto_aprobado.sum()
        frame["participacion"] = frame.presupuesto_aprobado / total * 100 if total else 0.0
        columns = {"nombre": ("Programa presupuestario", "text", 300), "presupuesto_aprobado": ("Aprobado (USD)", "money", None, None, "Aprobado"),
                   "devengado_mes": ("Devengado del mes (USD)", "money", None, None, "Mes"),
                   "devengado_acumulado": ("Devengado acumulado (USD)", "money", None, None, "Acumulado"),
                   "porcentaje_ejecucion": ("Ejecución", "pct"), "saldo": ("Saldo por devengar (USD)", "money", None, None, "Saldo"),
                   "participacion": ("Participación en el aprobado", "pct", None, None, "Peso")}
        layout = [("Programa presupuestario", "nombre", "text", 40.0), ("Aprobado (USD)", "presupuesto_aprobado", "usd", 19.0),
                  ("Devengado del mes (USD)", "devengado_mes", "usd", 19.0), ("Devengado acumulado (USD)", "devengado_acumulado", "usd", 19.0),
                  ("Ejecución", "porcentaje_ejecucion", "pct", 12.0), ("Saldo por devengar (USD)", "saldo", "usd", 19.0),
                  ("Participación en el aprobado", "participacion", "pct", 14.0)]
        return frame.sort_values("presupuesto_aprobado", ascending=False), columns, layout

    def _table(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        if st.session_state.get("social_level") not in self.LEVELS:
            st.session_state["social_level"] = next(iter(self.LEVELS))
        name = st.segmented_control("Nivel de detalle", list(self.LEVELS), key="social_level", required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(self.LEVELS[name])
        with st.container(border=True, key="card_social_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="social_table",
                          bar="participacion" if "participacion" in columns else None)
            download_table(frame, layout, title="Presupuesto social", subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_presupuesto_social_{self.period['id']}.xlsx",
                           key="social_xlsx", share_fields=("participacion", "porcentaje_ejecucion"))

    # --------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        return [("Año fiscal", str(self.period["year"])), ("Periodo", self.period["label"]), ("Ámbito", self.label),
                ("Programas", self.programs_label), ("Universo", "MDH–MTDH · grupos 58, 57 y 78")]

    def products_notes(self) -> dict[str, str]:
        return {
            "resumen": "Dos páginas en PDF: cifras clave, devengado mensual, ejecución por programa y acumulada, grupos de gasto y "
                       "aspectos destacados.",
            "presentacion": "Cuatro diapositivas editables en PowerPoint: cifras clave, ejecución por programa, evolución mensual y "
                            "detalle del devengado.",
            "datos": "Libro de Excel con resumen, programas, serie mensual, devengado por programa y mes, y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        return ["Resumen", "Programas", "Serie mensual", "Programa y mes", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        if kind == "datos":
            return [("grid", "Resumen", "Cifras clave y aspectos destacados"), ("chart", "Programas", "Aprobado, devengado y ejecución"),
                    ("trending-up", "Serie mensual", "Devengado del mes, acumulado y ejecución"),
                    ("table", "Programa y mes", "Devengado de cada programa en cada mes"), ("shield", "Ficha técnica", "Universo y definiciones")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores principales"), ("target", "Ejecución por programa", "Devengado sobre aprobado"),
                    ("trending-up", "Evolución mensual", "Devengado del mes y ejecución acumulada"),
                    ("layers", "Grupos de gasto", "Composición del devengado")]
        return [("grid", "Cifras clave", "Aprobado, devengado y ejecución"), ("trending-up", "Evolución mensual", "Devengado de cada mes"),
                ("target", "Ejecución por programa", "Cada programa frente a su aprobado"), ("award", "Aspectos destacados", "Conclusiones")]

    def slide_titles(self) -> tuple[str, str]:
        return "Ejecución por programa", "Evolución mensual"

    def preview_visual(self) -> str:
        return self.series_svg(night=False, width=300, height=170)

    def digest(self) -> str:
        return fingerprint(self.month, self.series, tuple(self.chosen))

    def report_context(self, title: str) -> dict:
        from src.reports.areas import social_budget_context
        return social_budget_context(self, title=title)


UNIVERSES = {"institucional": "Fiscal", "social": "Social", "gobierno": "Gobierno"}


class BudgetArea:
    """The budget area: the institutional budget or the approved social budget, chosen before the period."""

    kind = "presupuesto"
    id = "presupuesto"

    def __init__(self, institutional, social, government=None):
        self.views = {k: v for k, v in (("institucional", institutional), ("social", social), ("gobierno", government))
                      if v is not None and v.catalog()}

    @property
    def active(self):
        chosen = st.session_state.get("budget_universe")
        return self.views.get(chosen) or next(iter(self.views.values()))

    def pre_controls(self) -> None:
        if len(self.views) < 2:
            return
        if st.session_state.get("budget_universe") not in self.views:
            st.session_state["budget_universe"] = next(iter(self.views))
        st.segmented_control("Presupuesto", list(self.views), format_func=UNIVERSES.get, key="budget_universe", required=True,
                             width="stretch")

    def __getattr__(self, name):
        if name.startswith("__") or name == "views":
            raise AttributeError(name)
        return getattr(self.active, name)
