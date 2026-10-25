"""Labour management: contracts in force, contracts registered in the year and retirement compensation."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, gestion_laboral, ui
from src.indicators import AREAS
from src.views.common import download_table, fingerprint, show_chart


class LabourView:
    kind = "laboral"
    id = "laboral"

    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.label = AREAS["laboral"]["label"]
        self.info = gestion_laboral.summary(frame)
        span = gestion_laboral.month_span(self.info)
        self._catalog = [{**p, "span": span[:1].upper() + span[1:]} for p in gestion_laboral.catalog(frame)]

    def catalog(self) -> list[dict]:
        return self._catalog

    def controls(self, period: dict) -> None:
        self.period = period

    empty_message = "La información laboral no está disponible en este momento."

    def prepare(self) -> bool:
        info = self.info
        if not info or info.get("stock") is None:
            return False
        self.territory_label, self.programs_label = "Nacional", "Todos los indicadores"
        self.context_label = f"{self.period['label']} · Total nacional"
        months = info["months"]
        self.table = pd.DataFrame({"mes": [m["label"] for m in months], "contratos": [m["value"] for m in months]})
        total = self.table.contratos.sum()
        self.table["participacion"] = self.table.contratos / total * 100 if total else 0.0
        self.table["acumulado"] = self.table.contratos.cumsum()
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return self.period["label"], self.label, AREAS["laboral"]["description"]

    def series_svg(self, night: bool = True, width: int = 640, height: int = 360, *, narrow: bool = False) -> str:
        """Monthly contracts as columns; the narrow version (phones) writes the figures in thousands without the unit."""
        months = self.info["months"]
        unit = "" if narrow else " mil"
        css_class = "ec-columns" if night else "ec-columns mini"
        return ui.svg_columns([m["value"] for m in months], [m["short"] for m in months],
                              titles=[f"{m['label']} {self.info['year']}: {ui.number(m['value'])} contratos" for m in months],
                              average=self.info["average"], width=width, height=height, night=night,
                              value_text=lambda v: f"{ui.number(v / 1000, 1)}{unit}",
                              css_class=css_class + (" narrow" if narrow else ""))

    def hero_visual(self) -> None:
        info = self.info
        ui.hero_series(self.series_svg(), f"Contratos registrados cada mes de {info['year']} que siguen vigentes",
                       f"Promedio mensual: {ui.number(info['average'])}",
                       narrow=self.series_svg(width=360, height=280, narrow=True), narrow_note="Cifras en miles de contratos")

    def kpi_cards(self) -> list[dict]:
        info = self.info
        span = gestion_laboral.month_span(info)
        compensation = info["compensation"]
        return [
            {"label": "Contratos vigentes", "value": info["stock"], "icon": "briefcase", "tone": "morado",
             "note": f"Registro nacional al {info['stock_label']}"},
            {"label": f"Contratos registrados en {info['year']}", "value": info["cohorts"], "icon": "file-check", "tone": "violeta",
             "note": f"De {span}; estado al {info['cohorts_label']}", "bar": info["cohorts_share"],
             "bar_label": f"{ui.pct(info['cohorts_share'])} de los contratos vigentes"},
            {"label": "Expedientes de jubilación compensados" if info.get("retirees_unit") == "expedientes" else "Personas jubiladas compensadas", "value": info["retirees"], "icon": "user-check", "tone": "oro",
             "note": f"Al {info['retirement_cut']}" if info.get("retirement_cut") else f"Exservidores y extrabajadores públicos en {info['retirees_year']}"},
            {"label": "Compensaciones jubilares", "value": compensation / 1e6 if compensation else None, "decimals": 0,
             "prefix": "Más de USD" if info["compensation_lower_bound"] else "USD", "suffix": "millones", "icon": "coins",
             "tone": "fucsia", "note": f"Pagadas en {info['retirees_year']}"},
        ]

    def dashboard(self) -> None:
        info = self.info
        span = gestion_laboral.month_span(info)
        ui.section_heading("Contratación laboral", f"Total nacional · contratos registrados de {span} de {info['year']}", "briefcase")
        left, right = st.columns([1, 1.15], gap="medium")
        with left, st.container(border=True, key="card_labour_split"):
            if info.get("same_cut", True):
                ui.chart_title("Contratos vigentes según su registro", f"Total nacional al {info['stock_label']}")
                parts = [(f"Registrados de {span} de {info['year']}", info["cohorts"]),
                         ("Registrados en otros periodos", info["stock"] - info["cohorts"])]
                show_chart(charts.part_of_whole(parts), "labour_split")
            else:
                ui.chart_title("Fechas de referencia", "Cada fuente conserva su fecha de actualización")
                st.metric("Contratos vigentes", ui.number(info["stock"]))
                st.caption(f"Stock nacional: {info['stock_label']}. Serie mensual: estado al {info['cohorts_label']}.")
        columns = {"mes": ("Mes", "text", 150), "contratos": ("Contratos registrados", "int"),
                   "participacion": ("Participación en el año", "pct", None, None, "Peso"),
                   "acumulado": ("Acumulado del año", "int", None, None, "Acumulado")}
        layout = [("Mes", "mes", "text", 18.0), ("Contratos registrados", "contratos", "int", 18.0),
                  ("Participación en el año", "participacion", "pct", 16.0), ("Acumulado del año", "acumulado", "int", 18.0)]
        with right, st.container(border=True, key="card_labour_detail"):
            ui.chart_title("Contratos registrados por mes", f"Estado vigente al {info['cohorts_label']}")
            ui.data_table(self.table, columns, key="labour_table", bar="participacion")
            download_table(self.table, layout, title="Contratos registrados por mes",
                           subtitle=f"{self.period['label']} · Total nacional · contratos que siguen vigentes",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_laboral_{self.period['id']}.xlsx",
                           key="labour_xlsx")

    # --------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.label), ("Territorio", "Nacional"),
                ("Consulta", self.info["consulted_label"])]

    def products_notes(self) -> dict[str, str]:
        return {
            "resumen": "Una página en PDF con las cifras clave, la contratación mensual, las compensaciones jubilares y los aspectos destacados.",
            "presentacion": "Tres diapositivas editables en PowerPoint: cifras clave, contratación laboral y compensaciones jubilares.",
            "datos": "Libro de Excel con resumen, contratos por mes y ficha técnica con las fuentes oficiales.",
        }

    def sheets(self) -> list[str]:
        return ["Resumen", "Contratos por mes", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        if kind == "datos":
            return [("grid", "Resumen", "Cifras clave, serie mensual y aspectos destacados"),
                    ("chart", "Contratos por mes", "Contratos registrados cada mes, participación y acumulado"),
                    ("shield", "Ficha técnica", "Fuentes oficiales, fechas de consulta y definiciones")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores principales"),
                    ("chart", "Contratación laboral", "Gráfico editable de los contratos por mes"),
                    ("award", "Compensaciones jubilares", "Personas compensadas, recursos y aspectos destacados")]
        return [("grid", "Cifras clave", "Contratos vigentes, registros del año y jubilación"),
                ("chart", "Contratación laboral", "Contratos registrados por mes"),
                ("award", "Aspectos destacados", "Conclusiones para la toma de decisiones")]

    def slide_titles(self) -> tuple[str, str]:
        return "Contratación laboral", "Compensaciones jubilares"

    def preview_visual(self) -> str:
        return self.series_svg(night=False, width=300, height=170)

    def digest(self) -> str:
        return fingerprint(self.table, self.info.get("consulted"))

    def report_context(self, title: str) -> dict:
        from src.reports.national import labour_context
        return labour_context(self.info, title=title, period=self.period)
