"""Jóvenes en Acción: the three phases of the program, the registration and enabling of the current phase, the
accredited payments month by month and the budget of 2026.

The information of the program comes from the phases published by SGDE, the accredited transfers and the approved
social budget; it reaches the third phase (the latest with documented execution).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, jovenes as source, theme, ui
from src.indicators import AREAS
from src.views.common import compact, download_table, fingerprint, show_chart

MONTHS = source.MONTHS


class YouthView:
    kind = "jovenes"
    id = "jovenes"
    summary_pages = 1

    def __init__(self):
        self.label = AREAS["jovenes"]["label"]
        self.table = source.phases()
        self.paid = source.payments()
        self.money = source.budget()
        self.info = source.summary()
        self._catalog = source.catalog()
        self.report_level = "provincia"

    def catalog(self) -> list[dict]:
        return self._catalog

    def select(self, period: dict) -> None:
        self.period = period

    def controls(self, period: dict) -> None:
        self.period = period

    empty_message = "La información de Jóvenes en Acción no está disponible en este momento."

    def prepare(self) -> bool:
        if self.table.empty or not self.info:
            return False
        info = self.info
        self.territory_label, self.programs_label = "Nacional", f"Fases 1 a {info['phase']}"
        self.context_label = f"{self.period['label']} · {self.programs_label}"
        return True

    # ------------------------------------------------------------------------------------------------ band
    def hero_copy(self) -> tuple[str, str, str]:
        return f"Corte {self.period['label'].lower()}", self.label, AREAS["jovenes"]["description"]

    def update_stamp(self) -> dict:
        from src import corte
        return corte.stamp(self.id, self.period)

    def phases_svg(self, night: bool = True, width: int = 640, height: int = 360) -> str:
        table = self.table
        values = [float(v) for v in table.participantes]
        labels = list(table.nombre)
        sub = [t.replace(" de ", " ").replace("diciembre", "dic").replace("agosto", "ago").replace("octubre", "oct")
               .replace("junio", "jun").replace("desde", "desde") for t in table.periodo_texto]
        return ui.svg_columns(values, labels, titles=[f"{n} ({t}): {ui.number(v)} jóvenes" for n, t, v in zip(labels, table.periodo_texto, values)],
                              width=width, height=height, night=night, highlight=len(values) - 1, sublabels=sub if night else None,
                              css_class="ec-columns" if night else "ec-columns mini", value_text=lambda v: ui.number(v))

    def hero_visual(self) -> None:
        ui.hero_series(self.phases_svg(), "Jóvenes participantes de cada fase · la fase en curso en dorado")

    def kpi_cards(self) -> list[dict]:
        info = self.info
        paid_month = info.get("paid_month")
        cards = [
            {"label": f"Jóvenes habilitados · {info['phase_name'].lower()}", "value": info["enabled"], "icon": "graduation", "tone": "morado",
             "bar": info["enabled_share"], "bar_label": f"{ui.pct(info['enabled_share'])} de {ui.number(info['registered'])} registrados"},
            {"label": f"Presupuesto de la {info['phase_name'].lower()}", "value": (info["budget"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
             "suffix": "millones", "icon": "wallet", "tone": "violeta",
             "note": f"{ui.number(info['transfers'])} transferencias de USD {ui.number(info['transfer_amount'])} por joven"},
            {"label": "Presupuesto devengado", "value": (info["accrued"] or 0) / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones",
             "icon": "banknote", "tone": "oro", "bar": info["execution"], "bar_label": f"{ui.pct(info['execution'])} del presupuesto de la fase"},
        ]
        if paid_month:
            cards.append({"label": f"Jóvenes con pago acreditado · {source.month_label(paid_month)}", "value": info["paid_people"],
                          "icon": "send", "tone": "fucsia", "note": f"USD {ui.millions(info['paid_amount'])} millones acreditados"})
        return cards

    # ------------------------------------------------------------------------------------------- dashboard
    def dashboard(self) -> None:
        info, table = self.info, self.table
        ui.section_heading("Fases del programa", f"{self.context_label} · participantes, presupuesto y ejecución de cada fase", "graduation")
        accredited = self.paid.groupby("fase").monto.sum() if not self.paid.empty else pd.Series(dtype=float)
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_youth_phases"):
            ui.chart_title("Jóvenes participantes por fase", "Habilitados o atendidos en cada fase · la fase en curso en dorado")
            rows = table.assign(etiqueta=[f"{n} · {t}" for n, t in zip(table.nombre, table.etiqueta)])
            figure = charts.ranked_bars(list(rows.etiqueta)[::-1], list(rows.participantes)[::-1], _count(),
                                        hover=[f"{n} ({t})" for n, t in zip(rows.nombre, rows.periodo_texto)][::-1],
                                        height=charts.execution_height(len(rows), 64))
            # The bars are drawn from the bottom: the current phase (listed first) is the last one drawn.
            figure.update_traces(marker_color=[theme.ORO if i == len(rows) - 1 else charts.BAR for i in range(len(rows))])
            show_chart(figure, "youth_phases")
        with right, st.container(border=True, key="card_youth_money"):
            ui.chart_title("Presupuesto, ejecución y pagos acreditados", "Millones de USD por fase")
            series = [("Presupuesto", list(table.presupuesto_usd), theme.LILA_300),
                      ("Ejecución", list(table.ejecucion), theme.SERIE_BONOS),
                      ("Pagos acreditados", [accredited.get(f) for f in table.fase], theme.ORO)]
            show_chart(charts.grouped_bars(list(table.nombre), series, money=True), "youth_money")
        ui.section_heading(f"Registro y pagos de la {info['phase_name'].lower()}",
                           f"Desde {source.month_label(info['start'])} · corte {self.period['label'].lower()}", "user-plus")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_youth_funnel"):
            ui.chart_title("Del registro al pago", "Jóvenes registrados, habilitados y con pago acreditado")
            steps = [("Registrados", info["registered"], "Jóvenes que se registraron en la fase"),
                     ("Habilitados", info["enabled"], f"{ui.pct(info['enabled_share'])} de los registrados")]
            if info.get("paid_people"):
                steps.append((f"Con pago en {MONTHS[int(info['paid_month'][5:]) - 1]}", info["paid_people"],
                              f"{ui.pct(info['paid_people'] / info['enabled'] * 100)} de los habilitados"))
            show_chart(charts.funnel_bars(steps), "youth_funnel")
        with right, st.container(border=True, key="card_youth_budget"):
            months = self.money.loc[self.money.devengado_mes.notna() & self.money.periodo_id.ge(str(info["start"])[:7])]
            ui.chart_title(f"Presupuesto devengado de la {info['phase_name'].lower()}", "Millones de USD por mes")
            labels = [MONTHS[int(p[5:]) - 1][:3].capitalize() for p in months.periodo_id]
            selected = list(months.periodo_id).index(self.period["id"]) if self.period["id"] in set(months.periodo_id) else None
            show_chart(charts.month_columns(labels, list(months.devengado_mes), selected=selected, money=True,
                                            full=[source.month_label(p) for p in months.periodo_id]), "youth_budget")
        if not self.paid.empty:
            ui.section_heading("Pagos acreditados por mes", "Jóvenes con un pago acreditado y monto de cada mes, por fase", "send")
            paid = self.paid.sort_values("periodo_id")
            labels = [source.month_label(p, short=True) for p in paid.periodo_id]
            full = [f"{source.month_label(p).capitalize()} · fase {f}" for p, f in zip(paid.periodo_id, paid.fase)]
            left, right = st.columns(2, gap="medium")
            with left, st.container(border=True, key="card_youth_paid_people"):
                ui.chart_title("Jóvenes con pago acreditado", "Personas con al menos un pago acreditado en el mes")
                show_chart(charts.phase_columns(labels, list(paid.personas), list(paid.fase), unit="jóvenes", full=full), "youth_paid_people")
            with right, st.container(border=True, key="card_youth_paid_amount"):
                ui.chart_title("Monto acreditado", "Millones de USD acreditados en el mes")
                show_chart(charts.phase_columns(labels, list(paid.monto), list(paid.fase), money=True, full=full), "youth_paid_amount")
        self._table()

    # ---------------------------------------------------------------------------------------------- tables
    LEVELS = {"Por fase": "fase", "Pagos por mes": "pagos", "Presupuesto por mes": "presupuesto"}

    def phase_table(self) -> pd.DataFrame:
        accredited = self.paid.groupby("fase").monto.sum() if not self.paid.empty else pd.Series(dtype=float)
        frame = self.table.copy()
        frame["acreditado"] = frame.fase.map(accredited)
        frame["periodo_fase"] = frame.periodo_texto.str.capitalize()
        frame["esquema"] = [f"{int(t)} × USD {ui.number(m)}" if pd.notna(t) and pd.notna(m) else "—"
                            for t, m in zip(frame.transferencias, frame.monto_transferencia_usd)]
        return frame

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        if level == "fase":
            frame = self.phase_table()
            columns = {"nombre": ("Fase", "text", 90), "periodo_fase": ("Periodo", "text", 260), "registrados": ("Registrados", "int"),
                       "participantes": ("Participantes", "int"), "esquema": ("Transferencias", "text", 130),
                       "presupuesto_usd": ("Presupuesto (USD)", "money", None, None, "Presupuesto"),
                       "ejecucion": ("Ejecución (USD)", "money", None, None, "Ejecución"),
                       "porcentaje_ejecucion": ("Ejecución (%)", "pct"), "acreditado": ("Pagos acreditados (USD)", "money", None, None, "Acreditado")}
            layout = [("Fase", "nombre", "text", 10.0), ("Periodo", "periodo_fase", "text", 34.0), ("Registrados", "registrados", "int", 14.0),
                      ("Participantes", "participantes", "int", 14.0), ("Transferencias", "esquema", "text", 16.0),
                      ("Presupuesto (USD)", "presupuesto_usd", "usd", 18.0), ("Ejecución (USD)", "ejecucion", "usd", 18.0),
                      ("Ejecución (%)", "porcentaje_ejecucion", "pct", 12.0), ("Pagos acreditados (USD)", "acreditado", "usd", 20.0)]
            return frame, columns, layout
        if level == "pagos":
            frame = self.paid.assign(mes=[source.month_label(p).capitalize() for p in self.paid.periodo_id],
                                     fase_nombre=[f"Fase {f}" for f in self.paid.fase])
            columns = {"mes": ("Mes", "text", 180), "fase_nombre": ("Fase", "text", 90), "personas": ("Jóvenes con pago", "int"),
                       "transferencias": ("Transferencias", "int"), "monto": ("Monto acreditado (USD)", "money", None, None, "Monto")}
            layout = [("Mes", "mes", "text", 22.0), ("Fase", "fase_nombre", "text", 10.0), ("Jóvenes con pago", "personas", "int", 16.0),
                      ("Transferencias", "transferencias", "int", 14.0), ("Monto acreditado (USD)", "monto", "usd", 20.0)]
            return frame, columns, layout
        frame = self.money.loc[self.money.devengado_mes.notna()].copy()
        frame["mes"] = [source.month_label(p).capitalize() for p in frame.periodo_id]
        frame["porcentaje_ejecucion"] = frame.devengado_acumulado / frame.presupuesto_aprobado * 100
        columns = {"mes": ("Mes", "text", 180), "devengado_mes": ("Devengado del mes (USD)", "money", None, None, "Devengado"),
                   "devengado_acumulado": ("Devengado acumulado (USD)", "money", None, None, "Acumulado"),
                   "porcentaje_ejecucion": ("Ejecución acumulada", "pct")}
        layout = [("Mes", "mes", "text", 22.0), ("Devengado del mes (USD)", "devengado_mes", "usd", 20.0),
                  ("Devengado acumulado (USD)", "devengado_acumulado", "usd", 20.0), ("Ejecución acumulada", "porcentaje_ejecucion", "pct", 14.0)]
        return frame, columns, layout

    def _table(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        if st.session_state.get("youth_level") not in self.LEVELS:
            st.session_state["youth_level"] = next(iter(self.LEVELS))
        name = st.segmented_control("Nivel de detalle", list(self.LEVELS), key="youth_level", required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(self.LEVELS[name])
        with st.container(border=True, key="card_youth_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="youth_table")
            download_table(frame, layout, title="Jóvenes en Acción", subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_jovenes_{self.period['id']}.xlsx", key="youth_xlsx",
                           share_fields=("porcentaje_ejecucion",))

    # --------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.label), ("Fases", self.programs_label), ("Territorio", "Nacional")]

    def products_notes(self) -> dict[str, str]:
        return {
            "resumen": "Una página en PDF con las cifras de la fase en curso, las fases del programa, el registro y los pagos, y los "
                       "aspectos destacados.",
            "presentacion": "Cuatro diapositivas editables en PowerPoint: cifras clave, fases del programa, registro y pagos de la fase "
                            "en curso, y pagos acreditados por mes.",
            "datos": "Libro de Excel con resumen, fases, pagos acreditados por mes, presupuesto y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        return ["Resumen", "Fases", "Pagos por mes", "Presupuesto", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        if kind == "datos":
            return [("grid", "Resumen", "Cifras clave y aspectos destacados"), ("graduation", "Fases", "Participantes, presupuesto y ejecución"),
                    ("send", "Pagos por mes", "Jóvenes con pago acreditado y monto por fase"),
                    ("banknote", "Presupuesto", "Devengado mensual y acumulado de la fase en curso"),
                    ("shield", "Ficha técnica", "Fuentes y definiciones")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores de la fase en curso"),
                    ("graduation", "Fases del programa", "Participantes, presupuesto y ejecución"),
                    ("user-plus", "Registro y pagos", "Del registro al pago y presupuesto devengado"),
                    ("send", "Pagos acreditados por mes", "Jóvenes y montos por fase")]
        return [("grid", "Cifras clave", "Habilitados, presupuesto, devengado y pagos"),
                ("graduation", "Fases del programa", "Participantes y recursos de cada fase"),
                ("award", "Aspectos destacados", "Conclusiones para la toma de decisiones")]

    def slide_titles(self) -> tuple[str, str]:
        return "Fases del programa", "Registro y pagos"

    def preview_visual(self) -> str:
        return self.phases_svg(night=False, width=300, height=170)

    def digest(self) -> str:
        return fingerprint(self.table, self.paid, self.money)

    def report_context(self, title: str) -> dict:
        from src.reports.areas import youth_context
        return youth_context(self, title=title)


def _count():
    from src.indicators import Indicator
    return Indicator("participantes", "Jóvenes", "count", "graduation", "jóvenes")
