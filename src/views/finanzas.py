"""Budget views with one explicit source and reporting scope per selection.

*Fiscal* reads the SGDE publication: coded, certified, committed, accrued and available budget by program, kind of
spending, spending group and funding source.  *Gobierno* reads the government accumulation: the budget accumulated from
2023 to the previous year plus the year's accrued budget, by program, province and scope.  Both speak the language of
the rest of the dashboard: execution bars on a 0–100 % track with the total as a dotted gold line, stacked bars with
their figure at the end, the figure that deserves its own reading in a gold tile and the results table in a card.
"""
from __future__ import annotations

from datetime import date
from textwrap import wrap

import pandas as pd
import streamlit as st

from src import charts, corte, finanzas, theme, ui
from src.data import MONTHS
from src.indicators import Indicator
from src.views.common import compact, download_table, fingerprint, show_chart

FIRST_YEAR = 2023
CODED = Indicator("codificado", "Presupuesto codificado", "money", "wallet")
ACCUMULATED = Indicator("acumulado", "Acumulado de gobierno", "money", "landmark")
# How the dashboard writes some SGDE names; the official name stays in the hover and in every document.
SHORT_NAMES = {
    # The two longest programs, by a short form.
    "Promoción de empleo, verificación y control de derechos y obligaciones laborales": "Promoción de empleo y control laboral",
    "Coordinación en la formulación, ejecución, seguimiento y evaluación de las políticas públicas": "Coordinación de políticas públicas",
    # Names the publication writes in title case, in sentence case as everywhere else in the dashboard.
    "Protección Social": "Protección social", "Desarrollo Infantil": "Desarrollo infantil",
    "Administración Central": "Administración central", "Recursos Fiscales": "Recursos fiscales",
    "Préstamos Externos": "Préstamos externos", "Colocaciones Internas": "Colocaciones internas",
    "Recursos Fiscales generados por las Instituciones": "Recursos fiscales generados por las instituciones",
    "Asistencia Técnica y Donaciones": "Asistencia técnica y donaciones",
}
FISCAL_LEVELS = {"Por programa": "programa", "Por tipo de gasto": "tipo_gasto", "Por grupo de gasto": "grupo_gasto",
                 "Por fuente de financiamiento": "fuente"}
GOVERNMENT_LEVELS = {"Por programa": "programa", "Por provincia": "provincia", "Por ámbito": "ambito"}
TABLE_LABELS = {"programa": "Programa presupuestario", "tipo_gasto": "Tipo de gasto", "grupo_gasto": "Grupo de gasto",
                "fuente": "Fuente de financiamiento", "provincia": "Provincia", "ambito": "Ámbito"}
PLACEHOLDERS = {"programa": "Todos los programas", "tipo_gasto": "Todos los tipos", "fuente": "Todas las fuentes",
                "provincia": "Todas las provincias", "ambito": "Todos los ámbitos"}


def short(name: object) -> str:
    return SHORT_NAMES.get(str(name), str(name))


def _long_date(text: str) -> str:
    """«30 de septiembre de 2026» from an ISO date."""
    day = date.fromisoformat(str(text)[:10])
    return f"{day.day} de {MONTHS[day.month - 1]} de {day.year}"


def _share(part: float | None, whole: float | None) -> float | None:
    return part / whole * 100 if part is not None and whole else None


def _fold(rows: pd.DataFrame, other: str, minimum: float = 1.0) -> pd.DataFrame:
    """Rows below ``minimum`` % of the coded budget are added up as one, so a chart keeps the categories that weigh."""
    small = rows.participacion < minimum
    if small.sum() < 2:
        return rows
    rest = rows.loc[small, ["presupuesto_codificado", "presupuesto_ejecutado"]].sum()
    folded = {"nombre": other, "nombre_oficial": other + "<br>" + "<br>".join(rows.loc[small, "nombre_oficial"]), **rest.to_dict(),
              "porcentaje_ejecucion": _share(rest.presupuesto_ejecutado, rest.presupuesto_codificado)}
    return pd.concat([rows.loc[~small], pd.DataFrame([folded])], ignore_index=True)


class FinanceView:
    kind = "presupuesto"
    id = "presupuesto"
    empty_message = "La selección no registra presupuesto. Ajuste los filtros."

    def __init__(self, frame: pd.DataFrame, *, government: bool = False, metadata: dict | None = None):
        self.frame, self.government, self.metadata = frame, government, metadata or {}
        self.file_id = "presupuesto_gobierno" if government else "presupuesto_fiscal"
        self.label = "Presupuesto acumulado de gobierno" if government else "Presupuesto fiscal"
        self.dimensions = ({"programa": "Programa", "provincia": "Provincia", "ambito": "Ámbito"} if government else
                           {"programa": "Programa", "tipo_gasto": "Tipo de gasto", "grupo_gasto": "Grupo de gasto",
                            "fuente": "Fuente de financiamiento"})
        self.filter_dimensions = ["programa", "provincia", "ambito"] if government else ["programa", "tipo_gasto", "fuente"]
        self.measure = "acumulado" if government else "codificado"

    # ---------------------------------------------------------------------------------------------- selection
    def catalog(self):
        return [{"id": p, "year": int(p[:4]), "month": int(p[5:]),
                 "label": f"{MONTHS[int(p[5:]) - 1].capitalize()} {p[:4]}"}
                for p in sorted(self.frame.periodo_id.unique(), reverse=True)]

    def select(self, period: dict, **filters):
        self.period = period
        self.filters = {d: list(filters.get(d, ())) for d in self.dimensions}

    def controls(self, period):
        self.select(period)
        scoped = self.frame.loc[self.frame.periodo_id.eq(period["id"])]
        columns = st.columns(len(self.filter_dimensions), gap="small")
        for column, dimension in zip(columns, self.filter_dimensions):
            # Programs read from the largest budget down, as in the charts; the other lists in alphabetical order.
            weights = scoped.groupby(dimension)[self.measure].sum()
            options = (list(weights.sort_values(ascending=False).index) if dimension == "programa" else sorted(weights.index))
            key = self.file_id + "_" + dimension
            if key in st.session_state:
                st.session_state[key] = [v for v in st.session_state[key] if v in options]
            with column:
                self.filters[dimension] = st.multiselect(self.dimensions[dimension], options, key=key, format_func=short,
                                                         placeholder=PLACEHOLDERS[dimension])
        if any(self.filters.values()):
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary",
                      key=self.file_id + "_reset")

    def _clear(self) -> None:
        for dimension in self.filter_dimensions:
            st.session_state[self.file_id + "_" + dimension] = []

    def _stats(self, frame: pd.DataFrame) -> dict:
        measures = finanzas.GOVERNMENT_MEASURES if self.government else finanzas.FISCAL_MEASURES
        stats = {m: float(frame[m].sum()) for m in measures}
        if not self.government:
            coded = stats["codificado"]
            stats["ejecucion"] = stats["devengado"] / coded * 100 if coded else None
            stats["saldo_por_devengar"] = coded - stats["devengado"]
        return stats

    def prepare(self):
        scoped = self.frame.loc[self.frame.periodo_id.eq(self.period["id"])]
        frame = scoped
        for dimension, selected in self.filters.items():
            if selected:
                frame = frame.loc[frame[dimension].isin(selected)]
        if frame.empty:
            return False
        self.filtered = frame.copy()
        self.stats = self._stats(frame)
        self.whole = self._stats(scoped)
        self.active = any(self.filters.values())
        programs = self.filters.get("programa") or []
        self.programs_label = (short(programs[0]) if len(programs) == 1 else f"{len(programs)} programas" if programs
                               else "Todos los programas")
        provinces = self.filters.get("provincia") or []
        self.territory_label = (", ".join(provinces) or "Total nacional") if self.government else "Total institucional"
        others = [", ".join(map(short, values)) for dimension, values in self.filters.items() if values and dimension != "programa"]
        self.context_label = " · ".join([self.period["label"], self.programs_label, *others])
        return True

    # ------------------------------------------------------------------------------------------------- words
    @property
    def cut_text(self) -> str:
        """«30 de septiembre de 2026» for the SGDE cut; «septiembre de 2026» for the government accumulation."""
        if not self.government and self.metadata.get("fecha_corte"):
            return _long_date(self.metadata["fecha_corte"])
        return f"{MONTHS[self.period['month'] - 1]} de {self.period['year']}"

    @property
    def span(self) -> str:
        return f"{FIRST_YEAR}–{self.period['year'] - 1}"

    @property
    def scope_note(self):
        year = self.period["year"]
        if self.government:
            return (f"Presupuesto de transferencias y servicios en la gestión de gobierno: el acumulado de {FIRST_YEAR} a {year - 1} "
                    f"más el presupuesto ejecutado en {year} al corte, que ya forma parte del acumulado. Incluye programas "
                    "históricos sin cobertura actual.")
        return (f"Presupuesto fiscal institucional publicado por SGDE, con corte al {self.cut_text}. El presupuesto de programas y servicios "
                "MDH–MTDH se presenta en Programas y servicios: son universos distintos y no se suman.")

    def hero_copy(self):
        year = self.period["year"]
        if self.government:
            lead = (f"Presupuesto de transferencias y servicios en la gestión de gobierno: el acumulado de {FIRST_YEAR} a {year - 1} "
                    f"más el ejecutado en {year} al corte de {self.cut_text}. Incluye programas históricos sin cobertura actual.")
        else:
            lead = f"Presupuesto codificado, comprometido y devengado del Ministerio, publicado por SGDE con corte al {self.cut_text}."
        return f"Año fiscal {year} · corte {self.period['label'].lower()}", self.label, lead

    def update_stamp(self):
        stamp = corte.stamp(self.id, self.period)
        consulted = (self.metadata.get("procedencia") or {}).get("consulta")
        if self.government or not consulted:
            return stamp
        day = date.fromisoformat(consulted)
        cut_day = date.fromisoformat(self.metadata["fecha_corte"][:10])
        frequency = stamp["frequency"]
        return {**stamp, "cut": self.cut_text, "updated": _long_date(consulted), "updated_label": "Consultado en SGDE el",
                "updated_short": f"{day:%d/%m/%Y}",
                "line": f"Corte de la información: {self.cut_text} · consultada en SGDE el {_long_date(consulted)} · {frequency.lower()}",
                "short": f"Corte: {cut_day:%d/%m/%Y} · Consulta SGDE: {day:%d/%m/%Y} · {frequency}"}

    # -------------------------------------------------------------------------------------------------- band
    def hero_visual(self):
        word = "Composición del acumulado" if self.government else "Codificado, comprometido y devengado"
        ui.hero_series(self.preview_visual(night=True, width=640, height=330), f"{word} · millones de USD · {self.programs_label}")

    def preview_visual(self, night=False, width=300, height=170):
        stats, year = self.stats, self.period["year"]
        if self.government:
            keys, labels, highlight, word = ["anterior", "fiscal", "acumulado"], [self.span, str(year), "Acumulado"], 1, "del acumulado"
        else:
            keys, labels, highlight, word = ["codificado", "comprometido", "devengado"], ["Codificado", "Comprometido", "Devengado"], 2, \
                "del codificado"
        whole = stats[keys[-1] if self.government else keys[0]]
        values = [stats[k] / 1e6 for k in keys]
        shares = [_share(stats[k], whole) for k in keys]
        notes = ["100 %" if s is not None and round(s, 1) == 100 else ui.pct(s) for s in shares]
        titles = [f"{label}: USD {ui.number(v, 1)} millones · {note} {word}" for label, v, note in zip(labels, values, notes)]
        return ui.svg_columns(values, labels, titles=titles, sublabels=notes if night else None, width=width, height=height,
                              night=night, highlight=highlight, value_text=lambda v: ui.number(v, 1),
                              css_class="ec-columns" if night else "ec-columns mini")

    def kpi_cards(self):
        stats, whole, year = self.stats, self.whole, self.period["year"]

        def card(label, value, icon, tone, note="", share_key=None, share_label=""):
            item = {"label": label, "value": value / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones", "icon": icon, "tone": tone}
            # With filters the card tells the selection's weight; without them, its note.
            if self.active and share_key:
                item.update(share=_share(stats[share_key], whole[share_key]), share_label=share_label)
            elif note:
                item["note"] = note
            return item

        if self.government:
            total = stats["acumulado"]
            return [
                card(f"Presupuesto acumulado {self.span}", stats["anterior"], "history", "morado",
                     f"{ui.pct(_share(stats['anterior'], total))} del acumulado de gobierno", "anterior", "del total nacional"),
                card(f"Presupuesto ejecutado {year}", stats["fiscal"], "banknote", "oro",
                     f"{ui.pct(_share(stats['fiscal'], total))} del acumulado de gobierno", "fiscal", "del total nacional"),
                card(f"Presupuesto acumulado {FIRST_YEAR}–{year}", total, "landmark", "lila",
                     "Acumulado de gobierno de transferencias y servicios", "acumulado", "del total nacional"),
            ]
        pace = self.period["month"] / 12 * 100
        return [
            card(f"Presupuesto codificado {year}", stats["codificado"], "wallet", "morado",
                 f"Comprometido: USD {ui.millions(stats['comprometido'])} M", "codificado", "del total institucional"),
            card("Presupuesto devengado", stats["devengado"], "banknote", "oro", f"Al {self.cut_text}", "devengado",
                 "del total institucional"),
            {"label": "Ejecución presupuestaria", "value": stats["ejecucion"], "decimals": 1, "suffix": "%", "icon": "target", "tone": "lila",
             "bar": stats["ejecucion"], "bar_label": f"Ritmo uniforme del año: {ui.pct(pace)}"},
            {**card("Saldo disponible", stats["saldo_disponible"], "hourglass", "fucsia"),
             "note": f"Saldo por devengar: USD {ui.millions(stats['saldo_por_devengar'])} M"},
        ]

    # --------------------------------------------------------------------------------------------- dashboard
    def rows(self, dimension: str) -> pd.DataFrame:
        """Amounts of the selection by one dimension, largest first, with each row's share of the whole."""
        rows = finanzas.by(self.filtered, dimension, self.government)
        total = rows[self.measure].sum()
        rows["participacion"] = rows[self.measure] / total * 100 if total else 0.0
        rows["nombre_oficial"] = rows[dimension].astype(str)
        rows["nombre"] = rows.nombre_oficial.map(short)
        return rows

    def _bullets(self, dimension: str, *, fold: str | None = None, wrap: int = 0, per: int = 36):
        rows = self.rows(dimension).rename(columns={"codificado": "presupuesto_codificado", "devengado": "presupuesto_ejecutado",
                                                    "ejecucion": "porcentaje_ejecucion"})
        if fold:
            rows = _fold(rows, fold)
        return charts.execution_bullets(rows, "nombre", hover_label="nombre_oficial", reference=self.stats["ejecucion"],
                                        wrap_at=wrap, per=per)

    def _stack(self, dimension: str, *, per: int = 34, wrap: int = 0):
        rows = self.rows(dimension)
        rows = rows.loc[rows.acumulado.fillna(0) > 0]
        year = self.period["year"]
        return charts.accumulation_bars(list(rows.nombre), list(rows.anterior), list(rows.fiscal), list(rows.acumulado),
                                        names=(f"Acumulado {self.span}", f"Ejecutado {year}"), hover=list(rows.nombre_oficial),
                                        total_label=f"Acumulado {FIRST_YEAR}–{year}", per=per, wrap_at=wrap)

    def dashboard(self):
        (self._government_dashboard if self.government else self._fiscal_dashboard)()
        self._table()

    def _fiscal_dashboard(self):
        stats, phone = self.stats, compact()
        ui.section_heading("Ejecución presupuestaria", f"{self.context_label} · devengado sobre presupuesto codificado", "target")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_fiscal_programs"):
            ui.chart_title("Por programa presupuestario", f"Devengado al {self.cut_text} sobre codificado · la línea dorada marca el total")
            show_chart(self._bullets("programa", wrap=26 if phone else 40, per=50 if phone else 40), "fiscal_programs")
        with right:
            coded = stats["codificado"]
            with st.container(border=True, key="card_fiscal_stages"):
                ui.chart_title("Etapas de la ejecución", "Comprometido y devengado frente al presupuesto codificado")
                word = "" if phone else " del codificado"
                steps = [("Codificado", coded, "Presupuesto vigente al corte"),
                         ("Comprometido", stats["comprometido"], f"{ui.pct(_share(stats['comprometido'], coded))}{word}"),
                         ("Devengado", stats["devengado"], f"{ui.pct(stats['ejecucion'])}{word}")]
                show_chart(charts.funnel_bars(steps, money=True, height=230, right=150 if phone else 230), "fiscal_stages")
            remaining = 12 - self.period["month"]
            if remaining > 0 and stats["saldo_por_devengar"] > 0:
                # The pace the rest of the fiscal year needs to accrue the whole coded budget.
                months = f"{MONTHS[self.period['month']]} a diciembre" if remaining > 1 else "diciembre"
                ui.focus_tile("hourglass", f"Ritmo necesario de {months}",
                              f"USD {ui.millions(stats['saldo_por_devengar'] / remaining)} millones por mes",
                              "Para devengar el 100 % del presupuesto codificado hasta el cierre del año fiscal. Saldo por devengar al "
                              f"{self.cut_text}: USD {ui.millions(stats['saldo_por_devengar'])} millones.")
        ui.section_heading("Composición del gasto", f"{self.context_label} · presupuesto codificado por grupo, tipo y fuente", "layers")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_fiscal_groups"):
            groups = self.rows("grupo_gasto")
            ui.chart_title("Por grupo de gasto", "Presupuesto codificado · millones de USD")
            names = ["<br>".join(wrap(n, 22, break_long_words=False)) for n in groups.nombre] if phone else list(groups.nombre)
            show_chart(charts.ranked_bars(names, list(groups.codificado), CODED, hover=list(groups.nombre_oficial),
                                          share_total=float(groups.codificado.sum()), share_label="del codificado",
                                          height=max(260, len(groups) * (42 if phone else 34) + 50)), "fiscal_groups")
        with right:
            with st.container(border=True, key="card_fiscal_kinds"):
                kinds = self.rows("tipo_gasto")
                ui.chart_title("Por tipo de gasto", "Codificado y devengado · millones de USD")
                show_chart(charts.grouped_bars(list(kinds.nombre), [("Codificado", list(kinds.codificado), theme.LILA_200),
                                                                    ("Devengado", list(kinds.devengado), theme.ORO)],
                                               height=max(170, len(kinds) * 80 + 60)), "fiscal_kinds")
            with st.container(border=True, key="card_fiscal_sources"):
                sources = self.rows("fuente")
                main = sources.loc[sources.participacion >= 1]
                parts = [(name, value) for name, value in zip(main.nombre, main.codificado)]
                if len(main) < len(sources):
                    parts.append(("Otras fuentes", float(sources.loc[sources.participacion < 1, "codificado"].sum())))
                ui.chart_title("Por fuente de financiamiento", "Participación en el presupuesto codificado")
                show_chart(charts.part_of_whole(parts, money=True), "fiscal_sources")

    def _government_dashboard(self):
        year = self.period["year"]
        ui.section_heading("Composición del acumulado", f"{self.context_label} · acumulado {self.span} más el ejecutado en {year}",
                           "landmark")
        left, right = st.columns(2, gap="medium")
        with left:
            with st.container(border=True, key="card_government_programs"):
                ui.chart_title("Por programa", "Millones de USD · al final de cada barra, su acumulado de gobierno")
                show_chart(self._stack("programa", wrap=24 if compact() else 0, per=42 if compact() else 34), "government_programs")
            with st.container(border=True, key="card_government_scope"):
                scopes = self.rows("ambito")
                ui.chart_title("Por ámbito", "Participación en el acumulado de gobierno")
                show_chart(charts.part_of_whole(list(zip(scopes.nombre, scopes.acumulado)), money=True), "government_scope")
        with right, st.container(border=True, key="card_government_provinces"):
            provinces = self.rows("provincia")
            provinces = provinces.loc[provinces.acumulado.fillna(0) > 0]
            ui.chart_title("Por provincia", "Acumulado de gobierno · millones de USD")
            show_chart(charts.ranked_bars(list(provinces.nombre), list(provinces.acumulado), ACCUMULATED,
                                          share_total=float(provinces.acumulado.sum()),
                                          share_label="del total nacional" if not self.filters.get("provincia") else "de la selección"),
                       "government_provinces")

    def detail(self, dimension: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        """The results table of a level: rows, on-screen columns and the Excel layout (official names, every measure)."""
        rows, label = self.rows(dimension), TABLE_LABELS[dimension]
        if self.government:
            year = self.period["year"]
            columns = {"nombre": (label, "text", 340),
                       "anterior": (f"Acumulado {self.span} (USD)", "money", None, None, self.span),
                       "fiscal": (f"Ejecutado {year} (USD)", "money", None, None, str(year)),
                       "acumulado": (f"Acumulado {FIRST_YEAR}–{year} (USD)", "money", None, None, "Acumulado"),
                       "participacion": ("Participación en el acumulado", "pct", None, None, "Peso")}
            layout = [(label, "nombre_oficial", "text", 46.0), (f"Acumulado {self.span} (USD)", "anterior", "usd", 22.0),
                      (f"Ejecutado {year} (USD)", "fiscal", "usd", 20.0), (f"Acumulado {FIRST_YEAR}–{year} (USD)", "acumulado", "usd", 22.0),
                      ("Participación en el acumulado", "participacion", "pct", 16.0)]
            return rows, columns, layout
        columns = {"nombre": (label, "text", 370),
                   "codificado": ("Codificado (USD)", "money", None, None, "Codificado"),
                   "comprometido": ("Comprometido (USD)", "money", None, None, "Comprometido"),
                   "devengado": ("Devengado (USD)", "money", None, None, "Devengado"),
                   "ejecucion": ("Ejecución", "pct"),
                   "saldo_disponible": ("Saldo disponible (USD)", "money", None, None, "Disponible"),
                   "participacion": ("Participación", "pct", None, None, "Peso")}
        layout = [(label, "nombre_oficial", "text", 52.0), ("Codificado (USD)", "codificado", "usd", 19.0),
                  ("Certificado (USD)", "certificado", "usd", 18.0), ("Comprometido (USD)", "comprometido", "usd", 19.0),
                  ("Devengado (USD)", "devengado", "usd", 19.0), ("Ejecución", "ejecucion", "pct", 12.0),
                  ("Saldo disponible (USD)", "saldo_disponible", "usd", 19.0),
                  ("Saldo por devengar (USD)", "saldo_por_devengar", "usd", 19.0),
                  ("Participación en el codificado", "participacion", "pct", 15.0)]
        return rows, columns, layout

    def _table(self):
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        levels = GOVERNMENT_LEVELS if self.government else FISCAL_LEVELS
        key = self.file_id + "_level"
        if st.session_state.get(key) not in levels:
            st.session_state[key] = next(iter(levels))
        name = st.segmented_control("Nivel de detalle", list(levels), key=key, required=True, width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(levels[name])
        with st.container(border=True, key=f"card_{self.file_id}_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key=self.file_id + "_table", bar="participacion")
            download_table(frame, layout, title=self.label, subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_{self.file_id}_{self.period['id']}.xlsx",
                           key=self.file_id + "_xlsx", share_fields=("participacion", "ejecucion"))

    # ----------------------------------------------------------------------------------------------- reports
    def columns(self):
        year = self.period["year"]
        if self.government:
            return [(f"Acumulado {self.span}", "anterior", "money"), (f"Ejecutado {year}", "fiscal", "money"),
                    (f"Acumulado {FIRST_YEAR}–{year}", "acumulado", "money")]
        return [("Codificado", "codificado", "money"), ("Certificado", "certificado", "money"),
                ("Comprometido", "comprometido", "money"), ("Devengado", "devengado", "money"),
                ("Saldo disponible", "saldo_disponible", "money"), ("Ejecución", "ejecucion", "pct")]

    def scope_items(self):
        return [("Año fiscal", str(self.period["year"])), ("Corte", self.cut_text), ("Ámbito", self.label),
                *[(self.dimensions[k], ", ".join(v)) for k, v in self.filters.items() if v]]

    def products_notes(self):
        return {"resumen": "Dos páginas en PDF: cifras clave, presupuesto por programa, alcance y detalle con el corte de la fuente.",
                "presentacion": "Tres diapositivas editables en PowerPoint: cifras clave, presupuesto por programa y desagregación.",
                "datos": "Libro de Excel con resumen, montos exactos por cada desagregación, registros de la fuente y ficha técnica."}

    def sheets(self):
        return ["Resumen", *self.dimensions.values(), "Detalle", "Ficha técnica"]

    def report_contents(self, kind):
        return [("wallet", "Cifras clave", "Año fiscal, presupuesto y acumulados"),
                ("chart", "Desagregación", "Resultados por programa y ámbito de la fuente"),
                ("table", "Detalle", "Montos en USD y fuente")]

    def slide_titles(self):
        return "Presupuesto por programa", "Detalle presupuestario"

    def digest(self):
        return fingerprint(self.filtered, self.file_id, "finanzas-v2")

    def report_context(self, title):
        from src.reports.finanzas import context
        return context(self, title)
