"""Brigadas sociales por el Nuevo Ecuador: brigades of each month, people reached and attended, territory and type."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, ui
from src.data import MONTHS
from src.indicators import Indicator
from src.views.area import PROCESSED, AreaView, manifest
from src.views.common import show_chart

PEOPLE = Indicator("atendida", "Personas atendidas", "count", "users", "personas")


class BrigadeView(AreaView):
    kind = id = "brigadas"
    label = "Brigadas sociales"
    file_id = "brigadas_sociales"
    category = ("tipo", "Tipo de brigada", "Todos los tipos")
    weight = "brigadas"
    series_field, series_unit, series_title = "brigadas", "brigadas", "Brigadas realizadas por mes"
    LEVELS = {"Por provincia": "provincia", "Por cantón": "canton", "Por parroquia": "parroquia", "Por tipo": "tipo", "Por mes": "mes"}

    def __init__(self):
        path = PROCESSED / "brigadas.parquet"
        frame = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["periodo", "provincia_codigo", "provincia", "tipo"])
        self.rows_frame = frame.assign(brigadas=1)

    def prepare(self) -> bool:
        p = self.period
        scoped = self.scoped(self.rows_frame)
        year = scoped.loc[scoped.periodo.str[:4].eq(str(p["year"])) & scoped.periodo.le(p["id"])]
        if year.empty:
            return False
        self.year_rows, self.month_rows = year, year.loc[year.periodo.eq(p["id"])]
        self.all_rows = scoped.loc[scoped.periodo.le(p["id"])]
        self.series = year.groupby("periodo", as_index=False)[["brigadas", "alcanzada", "atendida"]].sum()
        self.history = self.all_rows.groupby("periodo", as_index=False)[["brigadas", "atendida"]].sum()
        reached, attended = int(year.alcanzada.sum()), int(year.atendida.sum())
        self.stats = {"brigades": int(len(year)), "reached": reached, "attended": attended,
                      "rate": attended / reached * 100 if reached else None,
                      "month_brigades": int(len(self.month_rows)), "month_attended": int(self.month_rows.atendida.sum()),
                      "total": int(len(self.all_rows)), "total_attended": int(self.all_rows.atendida.sum()),
                      "since": self.all_rows.fecha.min() if not self.all_rows.empty else None,
                      "average": attended / len(year) if len(year) else None}
        self.labels()
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return (f"Corte {self.period['label'].lower()}", self.label,
                "Brigadas sociales por el Nuevo Ecuador: jornadas en territorio con la población alcanzada y atendida, por mes, "
                "provincia, cantón, parroquia y tipo de brigada.")

    def kpi_cards(self) -> list[dict]:
        s, month = self.stats, MONTHS[self.period["month"] - 1]
        since = s["since"]
        since_text = f"{MONTHS[int(since[5:7]) - 1]} de {since[:4]}" if since else ""
        return [
            {"label": f"Brigadas realizadas {self.period['year']}", "value": s["brigades"], "icon": "users", "tone": "morado",
             "note": f"De {self.span}"},
            {"label": f"Personas atendidas {self.period['year']}", "value": s["attended"], "icon": "heart", "tone": "oro",
             "bar": s["rate"], "bar_label": f"{ui.pct(s['rate'])} de {ui.number(s['reached'])} alcanzadas"},
            {"label": f"Brigadas de {month}", "value": s["month_brigades"], "icon": "calendar", "tone": "lila",
             "note": f"{ui.number(s['month_attended'])} personas atendidas"},
            {"label": "Brigadas desde el inicio", "value": s["total"], "icon": "map", "tone": "fucsia",
             "note": f"Desde {since_text} · {ui.number(s['total_attended'])} personas"},
        ]

    def by(self, field: str, frame: pd.DataFrame | None = None) -> pd.DataFrame:
        frame = self.year_rows if frame is None else frame
        rows = (frame.groupby(field, as_index=False)[["brigadas", "alcanzada", "atendida"]].sum()
                .sort_values("atendida", ascending=False).reset_index(drop=True))
        total = rows.atendida.sum()
        rows["participacion"] = rows.atendida / total * 100 if total else 0.0
        return rows

    def dashboard(self) -> None:
        p = self.period
        labels = [MONTHS[int(x[5:]) - 1][:3].capitalize() for x in self.series.periodo]
        full = [f"{MONTHS[int(x[5:]) - 1].capitalize()} {p['year']}" for x in self.series.periodo]
        selected = list(self.series.periodo).index(p["id"]) if p["id"] in set(self.series.periodo) else None
        ui.section_heading("Evolución", f"{self.context_label} · brigadas y personas atendidas", "trending-up")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_brigades_people"):
            ui.chart_title("Personas atendidas por mes", "El mes de la consulta en dorado")
            show_chart(charts.month_columns(labels, list(self.series.atendida), selected=selected, unit="personas", full=full), "brigades_people")
        with right, st.container(border=True, key="card_brigades_history"):
            history = self.history
            ui.chart_title("Brigadas por mes desde el inicio", "Toda la serie disponible · el mes de la consulta en dorado")
            hl = [f"{MONTHS[int(x[5:]) - 1][:3].capitalize()} {x[2:4]}" for x in history.periodo]
            show_chart(charts.history_line(hl, [("Brigadas", [float(v) for v in history.brigadas], charts.BAR)], selected=len(history) - 1,
                                           unit="brigadas", full=[f"{MONTHS[int(x[5:]) - 1].capitalize()} {x[:4]}" for x in history.periodo]),
                       "brigades_history")
        ui.section_heading("Territorio y tipo de brigada", f"{self.context_label} · de {self.span}", "map")
        left, right = st.columns(2, gap="medium")
        provinces = self.by("provincia")
        with left, st.container(border=True, key="card_brigades_provinces"):
            ui.chart_title("Personas atendidas por provincia", "Provincias ordenadas de mayor a menor")
            show_chart(charts.ranked_bars(list(provinces.provincia), list(provinces.atendida), PEOPLE,
                                          share_total=float(provinces.atendida.sum()), share_label="del total",
                                          hover=[f"{r.provincia} · {ui.number(r.brigadas)} brigadas" for r in provinces.itertuples()]),
                       "brigades_provinces")
        with right, st.container(border=True, key="card_brigades_map"):
            codes = self.year_rows.groupby("provincia_codigo").brigadas.sum()
            ui.chart_title("Mapa de brigadas realizadas", "Más oscuro, más brigadas")
            titles = {c: f"{n}: {ui.number(codes.get(c, 0))} brigadas" for c, n in
                      self.year_rows[["provincia_codigo", "provincia"]].drop_duplicates().itertuples(index=False, name=None)}
            st.markdown(self.light_map(codes.to_dict(), titles), unsafe_allow_html=True)
            kinds = self.by("tipo")
            main = kinds.head(2)
            parts = [(r.tipo, r.brigadas) for r in main.itertuples()]
            if len(kinds) > 2:
                parts.append(("Otros tipos", int(kinds.brigadas.iloc[2:].sum())))
            ui.chart_title("Tipo de brigada", "Participación en las brigadas del año")
            show_chart(charts.part_of_whole(parts, unit="brigadas"), "brigades_kinds")
        self._table()

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        if level == "mes":
            frame = self.series.assign(mes=[f"{MONTHS[int(x[5:]) - 1].capitalize()} {x[:4]}" for x in self.series.periodo])
            name, label = "mes", "Mes"
        else:
            keys = {"provincia": ["provincia"], "canton": ["provincia", "canton"], "parroquia": ["provincia", "canton", "parroquia"],
                    "tipo": ["tipo"]}[level]
            frame = self.year_rows.groupby(keys, as_index=False)[["brigadas", "alcanzada", "atendida"]].sum().sort_values("atendida", ascending=False)
            name, label = keys[-1], {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia", "tipo": "Tipo de brigada"}[level]
        total = frame.atendida.sum()
        frame["participacion"] = frame.atendida / total * 100 if total else 0.0
        frame["cobertura"] = frame.atendida / frame.alcanzada.where(frame.alcanzada > 0) * 100
        columns, layout = {}, []
        for key in (["provincia", "canton"] if level in ("canton", "parroquia") else []):
            if key != name:
                columns[key] = ({"provincia": "Provincia", "canton": "Cantón"}[key], "text", 170)
                layout.append(({"provincia": "Provincia", "canton": "Cantón"}[key], key, "text", 22.0))
        columns.update({name: (label, "text", 240), "brigadas": ("Brigadas", "int"), "alcanzada": ("Población alcanzada", "int", None, None, "Alcanzada"),
                        "atendida": ("Personas atendidas", "int", None, None, "Atendida"), "cobertura": ("Atendida / alcanzada", "pct"),
                        "participacion": ("Participación", "pct", None, None, "Peso")})
        layout += [(label, name, "text", 30.0), ("Brigadas", "brigadas", "int", 12.0), ("Población alcanzada", "alcanzada", "int", 16.0),
                   ("Personas atendidas", "atendida", "int", 16.0), ("Atendida / alcanzada", "cobertura", "pct", 14.0),
                   ("Participación", "participacion", "pct", 14.0)]
        return frame.reset_index(drop=True), columns, layout

    def report_parts(self) -> dict:
        s = self.stats
        provinces, kinds = self.by("provincia"), self.by("tipo")
        leaders = provinces.head(3)
        since = s["since"]
        insights = [
            {"icon": "users", "text": f"De {self.span} se realizaron {ui.number(s['brigades'])} brigadas que atendieron a "
                                      f"{ui.number(s['attended'])} personas, el {ui.pct(s['rate'])} de la población alcanzada."},
            {"icon": "map", "text": ", ".join(leaders.provincia) + f" reúnen el {ui.pct(leaders.participacion.sum())} de las personas atendidas."},
            {"icon": "calendar", "text": f"Desde {MONTHS[int(since[5:7]) - 1]} de {since[:4]} suman {ui.number(s['total'])} brigadas y "
                                         f"{ui.number(s['total_attended'])} personas atendidas." if since else ""},
        ]
        table_cols = [("Provincia", "provincia", "text"), ("Brigadas", "brigadas", "int"), ("Personas atendidas", "atendida", "int"),
                      ("Participación", "participacion", "pct")]
        months = [{"name": MONTHS[int(x[5:]) - 1].capitalize(), "value": v} for x, v in zip(self.series.periodo, self.series.atendida)]
        return {"insights": [i for i in insights if i["text"]],
                "charts": [{"title": "Personas atendidas por mes", "note": f"De {self.span}", "rows": months, "unit": "personas"},
                           {"title": "Personas atendidas por provincia", "note": "Ocho principales",
                            "rows": [{"name": r.provincia, "value": r.atendida} for r in provinces.head(8).itertuples()], "unit": "personas"}],
                "tables": [{"key": "provincia", "label": "Provincias", "columns": table_cols, "rows": provinces.to_dict("records")},
                           {"key": "tipo", "label": "Tipos", "columns": [("Tipo de brigada", "tipo", "text"), *table_cols[1:]],
                            "rows": kinds.to_dict("records")},
                           {"key": "mes", "label": "Meses", "columns": [("Mes", "periodo", "text"), *table_cols[1:3]],
                            "rows": self.series.to_dict("records")}],
                "definitions": [("Población alcanzada", "Personas convocadas o alcanzadas por la brigada, según la matriz de resultados."),
                                ("Personas atendidas", "Personas que recibieron atención en la brigada."),
                                ("Fuente", manifest().get("brigadas", {}).get("fuente", "Matriz de resultados de Brigadas sociales"))]}
