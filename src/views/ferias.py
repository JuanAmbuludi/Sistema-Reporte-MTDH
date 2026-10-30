"""Training for economic inclusion, employability and self-employment.

The supplied registers describe training participations, not fair events or
employment placements. Each line retains its own register and is never added
to another line as a count of distinct people.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src import charts, corte, ferias as source, ui
from src.data import MONTHS
from src.indicators import Indicator
from src.views.area import AreaView
from src.views.common import fingerprint, show_chart

PARTICIPATIONS = Indicator("participaciones", "Participaciones", "count", "users", "participaciones")
SOURCE_LABELS = {"empleabilidad_autoempleo": "Empleabilidad y autoempleo", "inclusion_economica": "Inclusión económica"}
DIMENSION_LABELS = {"sexo": "Sexo", "edad": "Grupo de edad", "sector": "Área de residencia", "actividad": "Actividad",
                    "componente": "Componente de formación", "institucion": "Institución capacitadora"}


class FairView(AreaView):
    kind = id = "ferias"
    label = "Ferias de Inclusión Económica, Empleabilidad y Autoempleo"
    file_id = "ferias_inclusion_economica_empleabilidad_autoempleo"
    category = ("tipo_capacitacion", "Tipo de capacitación", "Todos los tipos")
    weight = "participaciones"
    series_field, series_unit, series_title = "participaciones", "participaciones", "Participaciones en capacitación por mes"
    LEVELS = {"Por provincia": "provincia", "Por cantón": "canton", "Por modalidad": "modalidad",
              "Por capacitación": "tipo_capacitacion", "Por mes": "mes"}
    empty_message = "La línea de formación no registra información para la selección. Ajuste los filtros."

    def __init__(self, source_key: str | None = None):
        self.registers = source.load()
        self.profiles = source.profile()
        self.metadata = source.manifest()
        self.sources = [key for key in SOURCE_LABELS if key in set(self.registers.fuente)] if not self.registers.empty else []
        self.source_key = source_key if source_key in self.sources else (self.sources[0] if self.sources else "empleabilidad_autoempleo")
        self._choose_source(self.source_key)
        self.provinces, self.categories = [], []

    def _choose_source(self, key: str) -> None:
        self.source_key = key
        self.rows_frame = self.registers.loc[self.registers.fuente.eq(key)].copy() if not self.registers.empty else self.registers.copy()
        self.source_info = self.metadata.get("fuentes", {}).get(key, {})
        self.line_label = self.source_info.get("label", SOURCE_LABELS.get(key, key))

    def pre_controls(self) -> None:
        if not self.sources:
            return
        if st.session_state.get("ferias_source") not in self.sources:
            st.session_state["ferias_source"] = self.source_key
        selected = st.segmented_control("Línea de formación", self.sources, format_func=SOURCE_LABELS.get,
                                        key="ferias_source", required=True, width="stretch")
        self._choose_source(selected)

    def select(self, p: dict, provinces=(), categories=(), *, source_key: str | None = None) -> None:
        if source_key is not None:
            if source_key not in self.sources:
                raise ValueError("La línea de formación seleccionada no está disponible.")
            self._choose_source(source_key)
        super().select(p, provinces, categories)

    def prepare(self) -> bool:
        p = self.period
        scoped = self.scoped(self.rows_frame)
        year = scoped.loc[scoped.periodo.str[:4].eq(str(p["year"])) & scoped.periodo.le(p["id"])].copy()
        if year.empty:
            return False
        self.year_rows, self.month_rows = year, year.loc[year.periodo.eq(p["id"])]
        self.history_rows = scoped.loc[scoped.periodo.le(p["id"])]
        self.series = year.groupby("periodo", as_index=False).participaciones.sum().sort_values("periodo")
        self.history = self.history_rows.groupby("periodo", as_index=False).participaciones.sum().sort_values("periodo")
        profile = (self.profiles.loc[self.profiles.fuente.eq(self.source_key)] if not self.profiles.empty else
                   pd.DataFrame(columns=["periodo", "provincia_codigo", "tipo_capacitacion", "dimension", "categoria", "participaciones"]))
        self.profile_rows = self.scoped(profile.loc[profile.periodo.str[:4].eq(str(p["year"])) & profile.periodo.le(p["id"])])
        count = int(year.participaciones.sum())
        national = self.rows_frame.loc[self.rows_frame.periodo.str[:4].eq(str(p["year"])) & self.rows_frame.periodo.le(p["id"])]
        total = int(national.participaciones.sum())
        self.stats = {"participations": count, "month": int(self.month_rows.participaciones.sum()),
                      "total": int(self.history_rows.participaciones.sum()), "since": self.history_rows.periodo.min(),
                      "provinces": int(year.loc[year.provincia_codigo.notna() & year.provincia_codigo.ne(""), "provincia_codigo"].nunique()),
                      "modalities": int(year.modalidad.nunique()),
                      "share": count / total * 100 if total and (self.provinces or self.categories) else None}
        self.labels()
        self.programs_label = self.line_label + (f" · {self.categories[0]}" if len(self.categories) == 1 else
                                                f" · {len(self.categories)} tipos" if self.categories else "")
        self.context_label = f"{p['label']} · {self.territory_label} · {self.line_label}"
        first = int(year.periodo.min()[5:7])
        self.span = (f"{MONTHS[first - 1]} a {MONTHS[p['month'] - 1]} de {p['year']}" if first != p["month"] else
                     f"{MONTHS[first - 1]} de {p['year']}")
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return (f"Corte {self.period['label'].lower()}", self.label,
                "Formación para la inclusión económica, la empleabilidad y el autoempleo: participaciones registradas por mes, "
                "tipo de capacitación, modalidad y territorio.")

    def update_stamp(self) -> dict:
        stamp = corte.stamp(self.id, self.period)
        value = self.metadata.get("generado_utc")
        if value:
            moment = datetime.fromisoformat(value).astimezone(corte.ECUADOR)
            stamp.update(updated=corte.long_date(moment), updated_short=f"{moment:%d/%m/%Y %H:%M}")
            stamp["line"] = f"Corte de la información: {stamp['cut']} · actualizada el {stamp['updated']} · actualización mensual"
            stamp["short"] = f"Corte: {stamp['cut']} · Actualizado: {stamp['updated_short']} · Actualización mensual"
        return stamp

    def kpi_cards(self) -> list[dict]:
        s, month = self.stats, MONTHS[self.period["month"] - 1]
        since = str(s["since"])
        since_label = f"{MONTHS[int(since[5:7]) - 1]} de {since[:4]}"
        return [
            {"label": f"Participaciones {self.period['year']}", "value": s["participations"], "icon": "users", "tone": "morado",
             **({"share": s["share"], "share_label": "del registro nacional"} if s["share"] is not None else {"note": f"De {self.span}"})},
            {"label": f"Participaciones de {month}", "value": s["month"], "icon": "calendar", "tone": "oro",
             "note": self.line_label},
            {"label": "Provincias con registros", "value": s["provinces"], "icon": "map", "tone": "lila",
             "note": f"{ui.number(s['modalities'])} modalidades de capacitación en el año"},
            {"label": "Participaciones acumuladas", "value": s["total"], "icon": "graduation", "tone": "fucsia",
             "note": f"Desde {since_label} · misma línea de formación"},
        ]

    def by(self, field: str, frame: pd.DataFrame | None = None) -> pd.DataFrame:
        frame = self.year_rows if frame is None else frame
        rows = frame.groupby(field, as_index=False, dropna=False).participaciones.sum().sort_values("participaciones", ascending=False)
        total = rows.participaciones.sum()
        rows["participacion"] = rows.participaciones / total * 100 if total else 0.0
        return rows.reset_index(drop=True)

    def profile_by(self, dimension: str) -> pd.DataFrame:
        rows = self.profile_rows.loc[self.profile_rows.dimension.eq(dimension)]
        return rows.groupby("categoria", as_index=False).participaciones.sum().sort_values("participaciones", ascending=False)

    def dashboard(self) -> None:
        p = self.period
        ui.section_heading("Formación y participación", f"{self.line_label} · de {self.span}", "graduation")
        labels = [MONTHS[int(x[5:7]) - 1][:3].capitalize() for x in self.series.periodo]
        full = [f"{MONTHS[int(x[5:7]) - 1].capitalize()} {x[:4]}" for x in self.series.periodo]
        selected = list(self.series.periodo).index(p["id"]) if p["id"] in set(self.series.periodo) else None
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_ferias_months"):
            ui.chart_title("Participaciones en capacitación por mes", "El mes de la consulta en dorado")
            show_chart(charts.month_columns(labels, list(self.series.participaciones), selected=selected,
                                            unit="participaciones", full=full), "ferias_months")
        with right, st.container(border=True, key="card_ferias_types"):
            kinds = self.by("tipo_capacitacion")
            ui.chart_title("Tipo de capacitación", "Participaciones registradas en el año")
            show_chart(charts.ranked_bars(list(kinds.tipo_capacitacion), list(kinds.participaciones), PARTICIPATIONS,
                                          share_total=float(kinds.participaciones.sum()), share_label="del registro",
                                          height=max(230, len(kinds) * 40 + 40)), "ferias_types")
            modalities = self.by("modalidad")
            ui.chart_title("Modalidad de capacitación", "Distribución de las participaciones")
            parts = [(r.modalidad, r.participaciones) for r in modalities.head(3).itertuples()]
            if len(modalities) > 3:
                parts.append(("Otras modalidades", int(modalities.participaciones.iloc[3:].sum())))
            show_chart(charts.part_of_whole(parts, unit="participaciones"), "ferias_modalities")

        ui.section_heading("Territorio", f"{self.territory_label} · participaciones en capacitación", "map")
        provinces = self.by("provincia")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_ferias_provinces"):
            ui.chart_title("Participaciones por provincia", "Provincias ordenadas de mayor a menor")
            show_chart(charts.ranked_bars(list(provinces.provincia), list(provinces.participaciones), PARTICIPATIONS,
                                          share_total=float(provinces.participaciones.sum()), share_label="del total"), "ferias_territory_bars")
        with right, st.container(border=True, key="card_ferias_map"):
            codes = self.year_rows.groupby("provincia_codigo").participaciones.sum()
            ui.chart_title("Mapa de participaciones", "Más oscuro, más registros de capacitación")
            titles = {c: f"{n}: {ui.number(codes.get(c, 0))} participaciones" for c, n in
                      self.year_rows[["provincia_codigo", "provincia"]].drop_duplicates().itertuples(index=False, name=None)}
            st.markdown(self.light_map(codes.to_dict(), titles), unsafe_allow_html=True)
            ui.focus_tile("map", "Alcance territorial", f"{ui.number(self.stats['provinces'])} provincias",
                          "Los territorios sin registros no acreditan ausencia de actividades.")

        if not self.profile_rows.empty:
            ui.section_heading("Perfil de las participaciones", f"{self.line_label} · de {self.span}", "users")
            left, right = st.columns(2, gap="medium")
            with left, st.container(border=True, key="card_ferias_profile"):
                for dimension in ("sexo", "sector"):
                    rows = self.profile_by(dimension)
                    if rows.empty:
                        continue
                    ui.chart_title(DIMENSION_LABELS[dimension], "Participaciones registradas")
                    parts = [(r.categoria, r.participaciones) for r in rows.head(3).itertuples()]
                    if len(rows) > 3:
                        parts.append(("Otros registros", int(rows.participaciones.iloc[3:].sum())))
                    show_chart(charts.part_of_whole(parts, unit="participaciones"), f"ferias_profile_{dimension}")
            with right, st.container(border=True, key="card_ferias_age"):
                rows = self.profile_by("edad")
                if not rows.empty:
                    ui.chart_title("Grupo de edad", "Participaciones por grupo reportado")
                    show_chart(charts.ranked_bars(list(rows.categoria), list(rows.participaciones), PARTICIPATIONS,
                                                  share_total=float(rows.participaciones.sum()), share_label="del registro",
                                                  height=max(260, len(rows) * 34 + 45)), "ferias_age")
                else:
                    rows = self.profile_by("actividad").head(8)
                    ui.chart_title("Actividad reportada", "Ocho principales del registro")
                    show_chart(charts.ranked_bars(list(rows.categoria), list(rows.participaciones), PARTICIPATIONS), "ferias_activity")
        self._table()
        st.caption("Alcance: participaciones en capacitación, no personas únicas, ferias realizadas ni empleos obtenidos. "
                   "Las líneas de formación se consultan por separado.")

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        labels = {"provincia": "Provincia", "canton": "Cantón", "modalidad": "Modalidad",
                  "tipo_capacitacion": "Tipo de capacitación", "mes": "Mes"}
        if level == "mes":
            frame = self.series.assign(mes=[f"{MONTHS[int(x[5:7]) - 1].capitalize()} {x[:4]}" for x in self.series.periodo])
            keys = ["mes"]
        else:
            keys = ["provincia", "canton"] if level == "canton" else [level]
            frame = self.year_rows.groupby(keys, as_index=False, dropna=False).participaciones.sum().sort_values("participaciones", ascending=False)
        total = frame.participaciones.sum()
        frame["participacion"] = frame.participaciones / total * 100 if total else 0.0
        columns = {key: (labels[key], "text", 230) for key in keys}
        columns.update(participaciones=("Participaciones", "int"), participacion=("Participación", "pct", None, None, "Peso"))
        layout = [(labels[key], key, "text", 34.0) for key in keys]
        layout.extend([("Participaciones", "participaciones", "int", 18.0), ("Participación", "participacion", "pct", 18.0)])
        return frame.reset_index(drop=True), columns, layout

    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.label), ("Línea de formación", self.line_label),
                ("Territorio", self.territory_label), ("Tipo de capacitación", ", ".join(self.categories) or "Todos los tipos")]

    def report_parts(self) -> dict:
        provinces, kinds = self.by("provincia"), self.by("tipo_capacitacion")
        leaders = provinces.head(3)
        insights = [
            {"icon": "graduation", "text": f"De {self.span} se registran {ui.number(self.stats['participations'])} participaciones "
                                             f"en {self.line_label.lower()}."},
            {"icon": "map", "text": f"{ui.number(self.stats['provinces'])} provincias tienen registros; " +
                                      ", ".join(leaders.provincia) + f" concentran el {ui.pct(leaders.participacion.sum())}."},
            {"icon": "users", "text": "Una persona puede participar en varias capacitaciones. Las líneas se presentan por separado."},
        ]
        value_cols = [("Participaciones", "participaciones", "int"), ("Participación", "participacion", "pct")]
        months = [{"name": MONTHS[int(p[5:7]) - 1].capitalize(), "value": v} for p, v in zip(self.series.periodo, self.series.participaciones)]
        return {"insights": insights,
                "charts": [{"title": "Participaciones en capacitación por mes", "note": f"De {self.span}", "rows": months, "unit": "participaciones"},
                           {"title": "Participaciones por provincia", "note": "Ocho principales · " + self.line_label,
                            "rows": [{"name": r.provincia, "value": r.participaciones} for r in provinces.head(8).itertuples()], "unit": "participaciones"}],
                "tables": [{"key": "provincia", "label": "Provincias", "columns": [("Provincia", "provincia", "text"), *value_cols],
                            "rows": provinces.to_dict("records")},
                           {"key": "tipo_capacitacion", "label": "Capacitaciones", "columns": [("Tipo de capacitación", "tipo_capacitacion", "text"), *value_cols],
                            "rows": kinds.to_dict("records")},
                           {"key": "mes", "label": "Meses", "columns": [("Mes", "periodo", "text"), value_cols[0]],
                            "rows": self.series.to_dict("records")}],
                "definitions": [("Participaciones", "Registros de participación en capacitación según la línea seleccionada; no equivalen a personas únicas."),
                                ("Línea de formación", self.line_label),
                                ("Alcance", self.source_info.get("alcance", "Las fuentes no identifican ferias realizadas ni resultados de inserción laboral.")),
                                ("Fuente", self.source_info.get("archivo", self.source_info.get("fuente", self.line_label)))]}

    def digest(self) -> str:
        return fingerprint(self.history_rows, self.profile_rows, self.source_key, self.period["id"], tuple(self.provinces),
                           tuple(self.categories), "ferias-v1")
