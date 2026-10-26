"""Sección independiente de riesgos y detalle de unidades de atención."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import charts, names, riesgos, theme, ui
from src.views.common import compact, fingerprint, show_chart


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


def service_chart(data: pd.DataFrame) -> go.Figure:
    counts = data.groupby("servicio").unidades.sum().sort_values()
    labels = [label.replace("Desarrollo Infantil Integral", "Desarrollo Infantil<br>Integral")
              .replace("Personas con discapacidad", "Personas con<br>discapacidad")
              .replace("Personas adultas mayores", "Personas adultas<br>mayores") for label in counts.index]
    figure = go.Figure(go.Bar(x=counts.values, y=labels, orientation="h", marker_color=theme.MORADO,
                             text=[ui.number(value) for value in counts], textposition="outside", cliponaxis=False,
                             customdata=list(counts.index), hovertemplate="%{customdata}<br>%{x:,.0f} unidades<extra></extra>"))
    charts.base(figure, 310, dict(l=8, r=55, t=12, b=35))
    figure.update_layout(showlegend=False, bargap=.38)
    figure.update_xaxes(title="Unidades de atención", rangemode="tozero")
    return figure


def threat_chart(data: pd.DataFrame, threat=None, levels=riesgos.LEVELS) -> go.Figure:
    counts = riesgos.threat_counts(data, threat, levels)
    figure = go.Figure()
    for level, color in zip(riesgos.LEVELS, [theme.LILA_300, theme.MORADO, theme.FUCSIA_700]):
        rows = counts.loc[counts.nivel.eq(level)]
        if rows.empty:
            continue
        figure.add_trace(go.Bar(x=rows.unidades, y=rows.amenaza, name=level, orientation="h", marker_color=color,
                               text=[ui.number(value) if value else "" for value in rows.unidades], textposition="auto",
                               hovertemplate=f"%{{y}} · {level}<br>%{{x:,.0f}} unidades<extra></extra>"))
    charts.base(figure, 310, dict(l=8, r=20, t=42, b=35))
    figure.update_layout(barmode="stack", bargap=.35, legend=dict(y=1.03))
    figure.update_xaxes(title="Unidades de atención", rangemode="tozero")
    figure.update_yaxes(categoryorder="array", categoryarray=list(reversed(riesgos.THREATS.values())))
    return figure


class RiskView:
    id = "riesgos"
    label = "Riesgos"
    empty_message = "La matriz de riesgos no está disponible para este corte."
    summary_pages = 2

    def __init__(self):
        self.data = _read(riesgos.DATA_PATH.stat().st_mtime_ns) if riesgos.DATA_PATH.exists() else pd.DataFrame()
        self.inventory = (_read_details(riesgos.DETAIL_PATH.stat().st_mtime_ns) if riesgos.DETAIL_PATH.exists()
                          else pd.DataFrame(columns=riesgos.DETAIL_FIELDS))
        self.matrix = (_read_matrix(riesgos.MATRIX_PATH.stat().st_mtime_ns) if riesgos.MATRIX_PATH.exists()
                       else self.data.iloc[:0].rename(columns={"unidades": "registros"}))

    def catalog(self) -> list[dict]:
        from src.corte import MONTHS
        if self.data.empty:
            return []
        return [{"id": p, "year": int(p[:4]), "month": int(p[5:]),
                 "label": f"{MONTHS[int(p[5:]) - 1].capitalize()} {p[:4]}"}
                for p in sorted(self.data.periodo_id.unique())]

    def controls(self, period: dict) -> None:
        self.period = period
        scoped = self.data.loc[self.data.periodo_id.eq(period["id"])]
        province_names = scoped.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.map(names.place).to_dict()
        service_names = scoped.drop_duplicates("programa_id").set_index("programa_id").servicio.to_dict()
        for key, options in [("risk_provinces", province_names), ("risk_programs", service_names)]:
            if key in st.session_state:
                st.session_state[key] = [value for value in st.session_state[key] if value in options]
        left, right = st.columns(2, gap="small")
        with left:
            self.provinces = st.multiselect("Territorio", sorted(province_names, key=province_names.get),
                                            format_func=province_names.get, placeholder="Todo el país", key="risk_provinces")
        with right:
            self.programs = st.multiselect("Servicio", list(service_names), format_func=service_names.get,
                                           placeholder="Todos los servicios", key="risk_programs")
        left, right = st.columns(2, gap="small")
        with left:
            self.threat = st.selectbox("Amenaza", ["todas", *riesgos.THREATS],
                                      format_func=lambda value: riesgos.THREATS.get(value, "Todas las amenazas"), key="risk_threat")
        with right:
            level = st.selectbox("Susceptibilidad", ["Todos los niveles", *riesgos.LEVELS], key="risk_level")
        self.levels = riesgos.LEVELS if level == "Todos los niveles" else (level,)
        self.threat = None if self.threat == "todas" else self.threat

    def prepare(self) -> bool:
        self.scoped = riesgos.select(self.data, self.period["id"], self.provinces, self.programs)
        self.selected = riesgos.exposed(self.scoped, self.threat, self.levels)
        self.detail_selected = riesgos.exposed(
            riesgos.select(self.inventory, self.period["id"], self.provinces, self.programs), self.threat, self.levels)
        self.matrix_available = self.matrix.periodo_id.eq(self.period["id"]).any()
        matrix_selected = riesgos.exposed(
            riesgos.select(self.matrix, self.period["id"], self.provinces, self.programs), self.threat, self.levels)
        self.multihazard = riesgos.multihazard(matrix_selected, self.levels)
        self.territory_label = (", ".join(sorted(self.scoped.provincia.map(names.place).unique()))
                                if self.provinces else "Nacional")
        self.programs_label = (", ".join(sorted(self.scoped.servicio.unique())) if self.programs else "Todos los servicios")
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return (f"Corte {self.period['label'].lower()}", "Riesgos",
                "Unidades de atención expuestas a amenazas asociadas al evento El Niño. "
                "La susceptibilidad territorial no confirma daños ni afectaciones.")

    def update_stamp(self) -> dict:
        import json
        from datetime import datetime
        from src.corte import ECUADOR, long_date
        path = riesgos.DATA_PATH.with_name(f"riesgos_ua_{self.period['id']}.json")
        metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        value = metadata.get("generado_utc")
        updated = long_date(datetime.fromisoformat(value).astimezone(ECUADOR)) if value else ""
        return {"cut": self.period["label"], "updated": updated,
                "short": f"Corte: {self.period['label']}", "line": f"Corte: {self.period['label']}",
                "frequency": "Actualización según matriz disponible"}

    def hero_visual(self) -> None:
        from src import geo
        values = self.selected.groupby("provincia_codigo").unidades.sum().to_dict()
        labels = self.scoped.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.to_dict()
        titles = {code: f"{names.place(labels[code])}: {ui.number(value)} unidades expuestas" for code, value in values.items()}
        ui.hero_map(geo.svg_map(ui.map_fills(values), titles=titles), "Unidades expuestas por provincia")

    def kpi_cards(self) -> list[dict]:
        return [
            {"label": "Unidades expuestas", "value": riesgos.count_units(self.selected), "icon": "building", "note": "Unidades únicas en la selección"},
            {"label": "Multiamenaza", "value": riesgos.count_records(self.multihazard) if self.matrix_available else None,
             "icon": "storm", "tone": "fucsia", "note": "Inundaciones o movimientos en masa"},
            {"label": "Provincias con unidades expuestas", "value": self.selected.provincia_codigo.nunique(), "icon": "map",
             "note": "Territorios de la selección"},
        ]

    def dashboard(self) -> None:
        ui.section_heading("Exposición a amenazas", self.period["label"], "storm")
        st.caption(riesgos.MULTI_NOTE)
        if self.selected.empty:
            ui.info_note("No hay unidades con las categorías y filtros seleccionados.", "Sin resultados")
            self.methodology()
            return
        columns = [st.container(), st.container()] if compact() else st.columns(2, gap="medium")
        with columns[0], st.container(border=True, key="card_risk_services"):
            ui.chart_title("Unidades expuestas por servicio", "Cada código de unidad se cuenta una sola vez")
            show_chart(service_chart(self.selected), "risk_services_chart")
        with columns[1], st.container(border=True, key="card_risk_threats"):
            ui.chart_title("Amenazas y susceptibilidad", "Una unidad puede estar expuesta a varias amenazas")
            show_chart(threat_chart(self.selected, self.threat, self.levels), "risk_threats_chart")
        self.table()

    def table(self) -> None:
        with st.container(border=True, key="card_risk_table"):
            ui.chart_title("Unidades de atención expuestas", "Código, nombre, servicio y susceptibilidad por amenaza")
            query = st.text_input("Buscar código, unidad, provincia o servicio", key="risk_search",
                                  placeholder="Código o nombre de la unidad, provincia o servicio")
            detail = self.detail_selected.copy()
            detail["provincia"] = detail.provincia.map(names.place)
            if query.strip():
                mask = detail[["codigo_ua", "nombre", "provincia", "servicio"]].apply(
                    lambda column: column.str.contains(query.strip(), case=False, regex=False, na=False)).any(axis=1)
                detail = detail.loc[mask]
            detail = detail.assign(_rank=detail.susceptibilidad_maxima.map(riesgos.RANK)).sort_values(
                ["_rank", "servicio", "provincia", "nombre"], ascending=[False, True, True, True])
            labels = {"codigo_ua": "Código UA", "nombre": "Unidad de atención", "servicio": "Servicio",
                      "provincia": "Provincia", **riesgos.THREATS}
            detail = detail[list(labels)]
            ui.data_table(detail, {key: (label, "text", 260 if key in ("nombre", "servicio") else 160)
                                   for key, label in labels.items()}, height=350, key="risk_table")
            st.caption(f"{ui.number(len(detail))} unidades únicas en la tabla. "
                       "La búsqueda solo filtra esta tabla.")
            st.download_button("Descargar unidades de la tabla",
                               detail.rename(columns=labels).assign(Corte=self.period["label"]).to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"MTDH_riesgos_UA_{self.period['id']}.csv", mime="text/csv",
                               icon=":material/download:", key="risk_download")
        st.caption("Fuente: SIIMTDH · DGID / SGDE / MTDH. Capas: inundaciones y sequía, MAGAP 2015; "
                   "movimientos en masa, SNGR 2011; incendios forestales, SNGR 2015. "
                   "Los guiones o vacíos se muestran como «Sin categoría reportada» y no acreditan ausencia de riesgo. "
                   "Hay unidades sin coordenadas en la fuente. Los totales entre amenazas no se suman.")
        self.methodology()

    @staticmethod
    def methodology() -> None:
        ui.info_note(METHODOLOGY, "Nota metodológica")

    @staticmethod
    def geoportal() -> None:
        ui.geoportal_card("riesgos", "Consulte la ubicación de las unidades de atención y las zonas de amenaza natural "
                                    "y riesgo antrópico en el visor geográfico del Ministerio.")

    def scope_items(self) -> list[tuple[str, str]]:
        return [("Corte", self.period["label"]), ("Territorio", self.territory_label),
                ("Servicios", self.programs_label), ("Amenaza", riesgos.THREATS.get(self.threat, "Todas las amenazas")),
                ("Susceptibilidad", ", ".join(self.levels))]

    def products_notes(self) -> dict[str, str]:
        return {"resumen": "Dos páginas en PDF: cifras clave, servicios, amenazas, provincias y nota metodológica.",
                "presentacion": "Cuatro diapositivas editables: cifras clave, exposición, provincias y metodología.",
                "datos": "Excel con resumen, amenazas, provincias, detalle de unidades con código y nombre y ficha técnica."}

    def sheets(self) -> list[str]:
        return ["Resumen", "Amenazas", "Provincias", "Unidades", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        items = [("grid", "Cifras clave", "Unidades únicas expuestas y multiamenaza según la matriz fuente"),
                 ("chart", "Servicios y amenazas", "Distribución de la selección vigente"),
                 ("map", "Provincias", "Unidades expuestas por territorio")]
        if kind == "datos":
            items.append(("building", "Unidades de atención", "Código, nombre, servicio, provincia y amenazas"))
        return items + [("document", "Nota metodológica", "Alcance, fuentes y acceso al geoportal")]

    def slide_titles(self) -> tuple[str, str]:
        return "Exposición por servicio y amenaza", "Unidades expuestas por provincia"

    def preview_visual(self) -> str:
        counts = self.selected.groupby("programa_id").unidades.sum()
        return ui.svg_columns(counts.tolist(), counts.index.tolist(), width=300, height=170, night=False)

    def digest(self) -> str:
        return fingerprint(self.selected, self.detail_selected, self.multihazard, self.period, self.provinces, self.programs,
                           self.threat, self.levels, METHODOLOGY, self.update_stamp())

    def report_context(self, title: str) -> dict:
        from src.reports.risks import build_context
        return build_context(self, title=title)
