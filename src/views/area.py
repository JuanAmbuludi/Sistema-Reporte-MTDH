"""Shared frame of the monthly areas built from one aggregated base (Crédito de Desarrollo Humano, Brigadas sociales).

A subclass reads its base, prepares the month, the year to date and the series of the year, and declares its cards,
charts and tables; this frame gives the consultation (period, province and one category), the band, the results table
with its Excel download and everything the report center and the documents need.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src import corte, theme, ui
from src.data import MONTHS
from src.views.common import compact, download_table, fingerprint

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"


def manifest() -> dict:
    path = PROCESSED / "cdh_brigadas.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def period(period_id: str) -> dict:
    year, month = int(period_id[:4]), int(period_id[5:7])
    return {"id": period_id, "year": year, "month": month, "label": f"{MONTHS[month - 1].capitalize()} {year}"}


def span(p: dict) -> str:
    """«enero a septiembre de 2026»."""
    return f"enero a {MONTHS[p['month'] - 1]} de {p['year']}" if p["month"] > 1 else f"enero de {p['year']}"


class AreaView:
    kind = id = ""
    label = file_id = ""
    category = ("tipo", "Tipo", "Todos los tipos")   # field, label and placeholder of the second filter
    empty_message = "La selección no registra información. Ajuste los filtros."
    summary_pages = 2
    LEVELS: dict[str, str] = {}

    rows_frame: pd.DataFrame = pd.DataFrame()

    def catalog(self) -> list[dict]:
        if self.rows_frame.empty:
            return []
        return [period(p) for p in sorted(self.rows_frame.periodo.unique(), reverse=True)]

    def select(self, p: dict, provinces=(), categories=()) -> None:
        self.period, self.provinces, self.categories = p, list(provinces), list(categories)

    def controls(self, p: dict) -> None:
        self.period = p
        frame = self.rows_frame
        names = dict(frame.drop_duplicates("provincia_codigo").dropna(subset=["provincia_codigo"])[["provincia_codigo", "provincia"]]
                     .sort_values("provincia").itertuples(index=False, name=None))
        field, label, placeholder = self.category
        options = list(frame.groupby(field)[self.weight].sum().sort_values(ascending=False).index)
        keys = (f"{self.id}_provinces", f"{self.id}_categories")
        for key, available in zip(keys, (list(names), options)):
            if key in st.session_state:
                st.session_state[key] = [v for v in st.session_state[key] if v in available]
        left, right = st.columns(2, gap="small")
        with left:
            self.provinces = st.multiselect("Territorio", list(names), format_func=names.get, placeholder="Todo el país", key=keys[0])
        with right:
            self.categories = st.multiselect(label, options, placeholder=placeholder, key=keys[1])
        if self.provinces or self.categories:
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary", key=f"{self.id}_reset")

    def _clear(self) -> None:
        st.session_state[f"{self.id}_provinces"] = []
        st.session_state[f"{self.id}_categories"] = []

    def scoped(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.provinces:
            frame = frame.loc[frame.provincia_codigo.isin(self.provinces)]
        if self.categories:
            frame = frame.loc[frame[self.category[0]].isin(self.categories)]
        return frame

    def labels(self) -> None:
        names = dict(self.rows_frame[["provincia_codigo", "provincia"]].drop_duplicates().itertuples(index=False, name=None))
        self.territory_label = (names.get(self.provinces[0], "Selección") if len(self.provinces) == 1 else
                                f"{len(self.provinces)} provincias" if self.provinces else "Total nacional")
        self.programs_label = (self.categories[0] if len(self.categories) == 1 else f"{len(self.categories)} categorías"
                               if self.categories else self.category[2].replace("Todos los", "Todos los").replace("Todas las", "Todas las"))
        self.context_label = f"{self.period['label']} · {self.territory_label}"
        self.span = span(self.period)

    # ------------------------------------------------------------------------------------------------- band
    def update_stamp(self) -> dict:
        stamp = corte.stamp("presupuesto", self.period)
        info = manifest().get(self.id, {})
        stamp["frequency"] = "Actualización mensual"
        if info.get("corte"):
            stamp["cut"] = info["corte"]
        return stamp

    def series_svg(self, night: bool = True, width: int = 640, height: int = 360) -> str:
        series = self.series
        months = [MONTHS[int(p[5:]) - 1] for p in series.periodo]
        values = [float(v) for v in series[self.series_field]]
        selected = list(series.periodo).index(self.period["id"]) if self.period["id"] in set(series.periodo) else None
        unit = self.series_unit
        return ui.svg_columns(values, [m[:3].capitalize() for m in months],
                              titles=[f"{m.capitalize()} {self.period['year']}: {ui.number(v)} {unit}" for m, v in zip(months, values)],
                              width=width, height=height, night=night, highlight=selected, css_class="ec-columns" if night else "ec-columns mini",
                              value_text=lambda v: ui.number(v / 1000, 1) + " mil" if v >= 10000 else ui.number(v))

    def hero_visual(self) -> None:
        ui.hero_series(self.series_svg(), f"{self.series_title} · {self.period['year']} · {self.territory_label}")

    def preview_visual(self) -> str:
        return self.series_svg(night=False, width=300, height=170)

    # ------------------------------------------------------------------------------------------------ table
    def _table(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        key = f"{self.id}_level"
        if st.session_state.get(key) not in self.LEVELS:
            st.session_state[key] = next(iter(self.LEVELS))
        name = st.segmented_control("Nivel de detalle", list(self.LEVELS), key=key, required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(self.LEVELS[name])
        with st.container(border=True, key=f"card_{self.id}_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key=f"{self.id}_table",
                          bar="participacion" if "participacion" in columns else None)
            download_table(frame, layout, title=self.label, subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_{self.file_id}_{self.period['id']}.xlsx",
                           key=f"{self.id}_xlsx", share_fields=("participacion",))

    # ---------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.label), ("Territorio", self.territory_label),
                (self.category[1], self.programs_label)]

    def products_notes(self) -> dict[str, str]:
        return {"resumen": "Dos páginas en PDF: cifras clave, evolución del año, distribución territorial y por categoría, hallazgos y cuadro "
                           "por provincia.",
                "presentacion": "Tres diapositivas editables en PowerPoint: cifras clave, resultados y territorio.",
                "datos": "Libro de Excel con resumen, cuadros por provincia, categoría y mes, y ficha técnica."}

    def sheets(self) -> list[str]:
        return ["Resumen", *[t["label"] for t in self.report_parts()["tables"]], "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        return [("grid", "Cifras clave", f"{self.label}: año, mes y acumulado"), ("trending-up", "Evolución", "Cada mes del año"),
                ("map", "Territorio", "Provincias con su participación"), ("table", "Cuadros", "Montos y conteos exactos")]

    def slide_titles(self) -> tuple[str, str]:
        return "Resultados", "Territorio"

    def digest(self) -> str:
        return fingerprint(self.year_rows, self.id, tuple(self.provinces), tuple(self.categories), "area-v1")

    def report_context(self, title: str) -> dict:
        from src.reports.simple import context
        return context(self, title)

    # ------------------------------------------------------------------------------------------------ helpers
    @staticmethod
    def light_map(values: dict[str, float], titles: dict[str, str], width: int = 520) -> str:
        from src import geo
        return geo.svg_map(ui.map_fills(values, theme.SEQUENTIAL[2:]), layer="provincia", titles=titles, width=width, pad=6,
                           stroke="#FFFFFF", equator=None, empty_fill="#F1EEF6", border_color="rgba(81,47,141,.45)",
                           frame_color="rgba(81,47,141,.35)", label_color="rgba(81,47,141,.6)", css_class="ec-map mini")
