"""Labour management: contracts in force by province and canton (SGDE daily cut), their profile, the contracts registered
each month of the year and retirement compensation.

Each source keeps its date: the stock of contracts carries the date and hour of its daily cut, the monthly
registrations the date they were observed and retirement compensation the cut of its publication.  They are shown side
by side and never added or divided across sources.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, geo, gestion_laboral as source, names as place_names, theme, ui
from src.indicators import AREAS
from src.views.common import compact, download_table, fingerprint, show_chart

LEVELS = {"provincia": "Provincia", "canton": "Cantón"}
REPORT_LEVELS = {**LEVELS, "todo": "Todo"}
MEASURES = {"contratos": "Contratos vigentes", "empresas": "Empresas"}


@st.cache_data(show_spinner=False, max_entries=24)
def _svg(layer: str, values: dict, titles: dict, focus: tuple, selected: tuple, night: bool = True, width: int = 640) -> str:
    if night:
        return geo.svg_map(ui.map_fills(values), layer=layer, titles=titles, focus=set(focus), selected=set(selected),
                           stroke=theme.MORADO_900, width=width)
    return geo.svg_map(ui.map_fills(values, theme.SEQUENTIAL[2:]), layer=layer, titles=titles, focus=set(focus), selected=set(selected),
                       width=width, pad=6, stroke="#FFFFFF", selected_fill=theme.ORO, equator=None, locator=False, empty_fill="#F1EEF6",
                       context_fill="#F1EEF6", border_color="rgba(81,47,141,.45)", frame_color="rgba(81,47,141,.35)",
                       label_color="rgba(81,47,141,.6)", css_class="ec-map mini")


def place(name: object) -> str:
    return place_names.place(str(name).upper()) if isinstance(name, str) else ""


class LabourView:
    kind = "laboral"
    id = "laboral"

    def __init__(self, frame: pd.DataFrame):
        self.frame = frame
        self.label = AREAS["laboral"]["label"]
        self.report_level = "todo"
        self.info = source.summary(frame) if not frame.empty else {}
        self.cut = source.sgde_cut()
        cut = self.cut.get("contracts")
        if cut is not None:
            self._catalog = [{"id": cut.strftime("%Y-%m"), "year": cut.year, "month": cut.month,
                              "label": f"{source.MONTHS[cut.month - 1].capitalize()} {cut.year}"}]
        else:
            span = source.month_span(self.info)
            self._catalog = [{**p, "span": span[:1].upper() + span[1:]} for p in source.catalog(frame)]
        names = source.contracts("base")
        self.province_names = (names.dropna(subset=["provincia_codigo"]).drop_duplicates("provincia_codigo")
                               .set_index("provincia_codigo").provincia.to_dict() if not names.empty else {})

    def catalog(self) -> list[dict]:
        return self._catalog

    # ------------------------------------------------------------------------------------------- consultation
    def select(self, period: dict, provinces=()) -> None:
        self.period, self.provinces = period, list(provinces)

    def controls(self, period: dict) -> None:
        self.period = period
        options = sorted(self.province_names, key=lambda c: self.province_names[c])
        if "labour_provinces" in st.session_state:
            st.session_state["labour_provinces"] = [c for c in st.session_state["labour_provinces"] if c in options]
        self.provinces = st.multiselect("Territorio", options, format_func=self.province_names.get, placeholder="Todo el país",
                                        key="labour_provinces")
        if self.provinces:
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary", key="reset_labour")

    @staticmethod
    def _clear() -> None:
        st.session_state["labour_provinces"] = []

    empty_message = "La información laboral no está disponible en este momento."

    def prepare(self) -> bool:
        if not self.cut.get("has_contracts"):
            return False
        provinces = self.provinces or None
        self.stock = source.stock(provinces)
        self.national_stock = source.stock()
        if not self.stock:
            return False
        if len(self.provinces) == 1:
            self.territory_label = self.province_names[self.provinces[0]]
        elif self.provinces:
            self.territory_label = f"{len(self.provinces)} provincias"
        else:
            self.territory_label = "Nacional"
        self.programs_label = f"Corte del {self.cut['contracts_label']}"
        self.context_label = f"Corte {self.cut['contracts_date']} · {self.territory_label}"
        self.years = source.retirement_years(provinces)
        self.year = int(self.years.anio.max()) if not self.years.empty else self.period["year"]
        self.map_measure, self.map_level = "contratos", "provincia"
        return True

    # ------------------------------------------------------------------------------------------------ band
    def hero_copy(self) -> tuple[str, str, str]:
        headline = f"{self.label} en {self.territory_label}" if self.provinces else self.label
        return f"Corte {self.cut['contracts_label']}", headline, AREAS["laboral"]["description"]

    def update_stamp(self) -> dict:
        from src import corte
        return corte.stamp(self.id, self.period)

    def _focus(self) -> set[str]:
        return {c for c in self.provinces if c != geo.NO_POLYGON}

    def map_svg(self, night: bool = True, width: int = 640, measure: str | None = None, level: str | None = None) -> tuple[str, str]:
        measure, level = measure or self.map_measure, level or self.map_level
        if measure == "empresas":
            level = "provincia"
        focus = self._focus() if night and level == "canton" else set()
        if measure == "empresas":
            rows = source.companies_by_province()
            values = {c: float(v) for c, v in zip(rows.provincia_codigo, rows.empresas)}
            titles = {c: f"{n}: {ui.number(v)} empresas" for c, n, v in zip(rows.provincia_codigo, rows.provincia, rows.empresas)}
        elif level == "canton":
            rows = source.by_territory("canton", list(focus) or None)
            rows = rows.loc[rows.canton_codigo.notna()]
            values = {c: float(v) for c, v in zip(rows.canton_codigo, rows.contratos)}
            titles = {c: f"{place(n)} · {p}: {ui.number(v)} contratos" for c, n, p, v in zip(rows.canton_codigo, rows.canton, rows.provincia, rows.contratos)}
        else:
            rows = source.by_territory("provincia")
            rows = rows.loc[rows.provincia_codigo.notna()]
            values = {c: float(v) for c, v in zip(rows.provincia_codigo, rows.contratos)}
            titles = {c: f"{n}: {ui.number(v)} contratos vigentes" for c, n, v in zip(rows.provincia_codigo, rows.provincia, rows.contratos)}
        svg = _svg(level, values, titles, tuple(sorted(focus)), tuple(sorted(self.provinces)), night, width)
        return svg, f"{MEASURES[measure]} por {LEVELS[level].lower()}"

    def hero_visual(self) -> None:
        if st.session_state.get("labour_measure") not in MEASURES:
            st.session_state["labour_measure"] = "contratos"
        self.map_measure = st.segmented_control("Indicador territorial", list(MEASURES), format_func=MEASURES.get, key="labour_measure",
                                                required=True, width="stretch")
        if self.map_measure == "empresas":
            st.session_state["labour_level"] = "provincia"
        elif st.session_state.get("labour_level") not in LEVELS:
            st.session_state["labour_level"] = "provincia"
        self.map_level = st.segmented_control("Nivel territorial", list(LEVELS), format_func=LEVELS.get, key="labour_level", required=True,
                                              disabled=self.map_measure == "empresas", width="stretch")
        svg, label = self.map_svg()
        selected = ("Provincia seleccionada" if len(self.provinces) == 1 else "Provincias seleccionadas") if self.provinces else ""
        ui.hero_map(svg, label, selected=selected)

    def kpi_cards(self) -> list[dict]:
        stock, national = self.stock, self.national_stock
        share = stock["vigentes"] / national["vigentes"] * 100 if self.provinces and national["vigentes"] else None
        cards = [{"label": "Contratos vigentes", "value": stock["vigentes"], "icon": "briefcase", "tone": "morado",
                  "share": share, "share_label": "del total nacional",
                  "note": f"De {ui.number(stock['registrados'])} contratos registrados" if share is None else ""}]
        cards.append({"label": "Empresas con contratos vigentes", "value": stock["empresas"], "icon": "factory", "tone": "violeta",
                      "note": "Empresas distintas del país" if not self.provinces else "Empresas de la selección, por provincia"})
        years = self.years
        if not years.empty:
            current = years.iloc[-1]
            cut = f"Al {self.cut['retirement_label']}" if current.parcial else f"Año {int(current.anio)}"
            cards.append({"label": f"Expedientes de jubilación {int(current.anio)}", "value": current.expedientes, "icon": "user-check",
                          "tone": "oro", "note": cut})
            cards.append({"label": f"Compensaciones jubilares {int(current.anio)}", "value": current.monto / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "coins", "tone": "fucsia",
                          "note": f"Promedio de USD {ui.number(current.promedio)} por expediente"})
        return cards

    # ------------------------------------------------------------------------------------------- dashboard
    def dashboard(self) -> None:
        provinces = self.provinces or None
        ui.section_heading("Contratos vigentes por territorio", self.context_label, "map")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_labour_rank"):
            head, toggle = st.columns([1.55, 1], gap="small", vertical_alignment="center")
            if st.session_state.get("lvl_labour") not in LEVELS:
                st.session_state["lvl_labour"] = "provincia"
            with toggle:
                level = st.segmented_control("Nivel territorial", list(LEVELS), format_func=LEVELS.get, key="lvl_labour", required=True,
                                             label_visibility="collapsed", width="stretch" if compact() else "content")
            rows = source.by_territory(level, provinces)
            rows = rows.loc[rows.provincia_codigo.notna()] if level == "provincia" else rows
            top = rows.head(25)
            with head:
                ui.chart_title(f"Contratos vigentes por {LEVELS[level].lower()}",
                               "Provincias ordenadas de mayor a menor" if level == "provincia" else f"Los {len(top)} primeros cantones de la selección")
            labels = [place(n) if level == "canton" else n for n in top.nombre]
            hover = [f"{place(c)} · {p}" for c, p in zip(top.canton, top.provincia)] if level == "canton" else list(top.provincia)
            figure = charts.ranked_bars(labels, list(top.contratos), _count("contratos"), hover=hover, share_total=float(rows.contratos.sum()),
                                        share_label="de la selección" if self.provinces else "del total nacional",
                                        height=charts.execution_height(len(top), 30))
            show_chart(figure, "labour_rank")
        with right, st.container(border=True, key="card_labour_profile"):
            ui.chart_title("Perfil de los contratos vigentes", "Sexo, grupo de edad y discapacidad de la persona contratada")
            for column, title in (("sexo", "Sexo"), ("grupo_edad", "Grupo de edad"), ("discapacidad", "Discapacidad")):
                parts = source.by_dimension("base", column, provinces)
                order = {"Mujeres": 0, "Hombres": 1, "Jóvenes (18–29)": 0, "Adultos (30 y más) y otros": 1, "Adolescentes (15–17)": 2,
                         "Con discapacidad": 0, "Sin discapacidad": 1}
                parts = parts.assign(orden=parts[column].map(order).fillna(9)).sort_values("orden")
                st.markdown(f'<p class="profile-label">{title}</p>', unsafe_allow_html=True)
                show_chart(charts.part_of_whole([(r[column], r.contratos) for _i, r in parts.iterrows()]), f"labour_profile_{column}")
        ui.section_heading("Actividad económica y tipo de contrato", self.context_label, "factory")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_labour_branch"):
            branches = source.by_dimension("rama", "rama_actividad", provinces, top=10)
            ui.chart_title("Contratos vigentes por rama de actividad", "Las 10 ramas con más contratos")
            show_chart(charts.ranked_bars([_short_branch(b) for b in branches.rama_actividad], list(branches.contratos), _count("contratos"),
                                          hover=list(branches.rama_actividad), share_total=float(source.by_dimension("rama", "rama_actividad", provinces).contratos.sum()),
                                          share_label="del total", height=charts.execution_height(len(branches), 34)), "labour_branch")
        with right, st.container(border=True, key="card_labour_type"):
            kinds = source.by_dimension("tipo", "tipo_contrato", provinces, top=10)
            ui.chart_title("Contratos vigentes por tipo de contrato", "Los 10 tipos con más contratos")
            show_chart(charts.ranked_bars([_short_type(k) for k in kinds.tipo_contrato], list(kinds.contratos), _count("contratos"),
                                          hover=list(kinds.tipo_contrato), share_total=float(source.by_dimension("tipo", "tipo_contrato", provinces).contratos.sum()),
                                          share_label="del total", height=charts.execution_height(len(kinds), 34)), "labour_type")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_labour_ethnicity"):
            groups = source.by_dimension("etnia", "etnia", provinces)
            ui.chart_title("Contratos vigentes por autoidentificación étnica", "Personas contratadas según su autoidentificación")
            show_chart(charts.ranked_bars(list(groups.etnia), list(groups.contratos), _count("contratos"), share_total=float(groups.contratos.sum()),
                                          share_label="del total", height=charts.execution_height(len(groups), 32)), "labour_ethnicity")
        with right, st.container(border=True, key="card_labour_foreign"):
            foreign = source.by_dimension("nac", "nacionalidad", provinces, top=10)
            total_foreign = float(source.by_dimension("nac", "nacionalidad", provinces).contratos.sum())
            ui.chart_title("Contratos vigentes de personas extranjeras", f"Las 10 nacionalidades con más contratos · {ui.number(total_foreign)} en total")
            show_chart(charts.ranked_bars(list(foreign.nacionalidad), list(foreign.contratos), _count("contratos"), share_total=total_foreign,
                                          share_label="de los contratos de extranjeros", height=charts.execution_height(len(foreign), 32)),
                       "labour_foreign")
        self._registrations()
        self._retirement()
        self._table()

    def _registrations(self) -> None:
        info = self.info
        if not info or not info.get("months") or self.provinces:
            return
        span = source.month_span(info)
        ui.section_heading("Contratación del año", f"Contratos registrados de {span} de {info['year']} que siguen vigentes · total nacional",
                           "file-check")
        months = info["months"]
        left, right = st.columns([1.35, 1], gap="medium")
        with left, st.container(border=True, key="card_labour_months"):
            ui.chart_title("Contratos registrados por mes", f"Estado vigente al {info['cohorts_label']}")
            show_chart(charts.monthly_columns([m["short"] for m in months], [m["value"] for m in months], average=info["average"],
                                              full_names=[f"{m['label']} {info['year']}" for m in months]), "labour_months")
        with right, st.container(border=True, key="card_labour_months_table"):
            table = pd.DataFrame({"mes": [m["label"] for m in months], "contratos": [m["value"] for m in months]})
            total = table.contratos.sum()
            table["participacion"] = table.contratos / total * 100 if total else 0.0
            ui.chart_title("Detalle mensual", f"{ui.number(total)} contratos de {span}")
            ui.data_table(table, {"mes": ("Mes", "text", 130), "contratos": ("Contratos", "int"),
                                  "participacion": ("Participación", "pct", None, None, "Peso")}, key="labour_months_table", bar="participacion")

    def _retirement(self) -> None:
        years = self.years
        if years.empty:
            return
        provinces = self.provinces or None
        ui.section_heading("Compensación jubilar", f"Exservidores y extrabajadores públicos · {self.territory_label} · "
                                                   f"{int(years.anio.min())} a {self.year} (al {self.cut['retirement_label']})", "user-check")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_labour_files"):
            ui.chart_title("Expedientes compensados por año", f"{self.year} hasta el {self.cut['retirement_label']}")
            show_chart(charts.month_columns([str(int(a)) for a in years.anio], list(years.expedientes), selected=len(years) - 1, unit="expedientes",
                                            full=[f"Año {int(a)}" + (f" (al {self.cut['retirement_label']})" if p else "")
                                                  for a, p in zip(years.anio, years.parcial)]), "labour_files")
        with right, st.container(border=True, key="card_labour_amount"):
            ui.chart_title("Compensaciones pagadas por año", "Millones de USD")
            show_chart(charts.month_columns([str(int(a)) for a in years.anio], list(years.monto), selected=len(years) - 1, money=True,
                                            full=[f"Año {int(a)}" for a in years.anio]), "labour_amount")
        regimes = source.retirement_by("regimen", self.year)
        by_province = source.retirement_by("provincia", self.year, provinces)
        left, right = st.columns(2, gap="medium")
        if not self.provinces:
            with left, st.container(border=True, key="card_labour_regime"):
                ui.chart_title(f"Expedientes por régimen laboral · {self.year}", "Ley de la que proviene el exservidor o extrabajador")
                show_chart(charts.ranked_bars(list(regimes.categoria), list(regimes.expedientes), _count("expedientes"),
                                              share_total=float(regimes.expedientes.sum()), share_label="del total",
                                              height=charts.execution_height(len(regimes), 40)), "labour_regime")
                sexes = source.retirement_by("sexo", self.year)
                st.markdown('<p class="profile-label">Sexo</p>', unsafe_allow_html=True)
                show_chart(charts.part_of_whole([(r.categoria, r.expedientes) for r in sexes.sort_values("categoria", ascending=False).itertuples()],
                                                unit="expedientes"), "labour_retirement_sex")
        target = right if not self.provinces else left
        with target, st.container(border=True, key="card_labour_ret_province"):
            ui.chart_title(f"Expedientes por provincia · {self.year}", "Provincias ordenadas de mayor a menor")
            show_chart(charts.ranked_bars(list(by_province.categoria), list(by_province.expedientes), _count("expedientes"),
                                          share_total=float(source.retirement_by("provincia", self.year).expedientes.sum()),
                                          share_label="del total nacional", height=charts.execution_height(len(by_province), 26)),
                       "labour_ret_province")

    # ---------------------------------------------------------------------------------------------- tables
    TABLES = {"Por provincia": "provincia", "Por cantón": "canton", "Por rama de actividad": "rama", "Por tipo de contrato": "tipo",
              "Por autoidentificación": "etnia", "Por nacionalidad": "nac", "Empresas": "empresas", "Jubilación por año": "jub_anio",
              "Jubilación por provincia": "jub_provincia", "Contratos por mes": "meses"}

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        provinces = self.provinces or None
        count = ("Contratos vigentes", "int")
        share = ("Participación", "pct", None, None, "Peso")
        if level in ("provincia", "canton"):
            frame = source.by_territory(level, provinces)
            if level == "canton":
                frame = frame.assign(canton=frame.canton.map(place))
            columns = {"provincia": ("Provincia", "text", 200)}
            layout = [("Provincia", "provincia", "text", 26.0)]
            if level == "canton":
                columns["canton"] = ("Cantón", "text", 200)
                layout.append(("Cantón", "canton", "text", 26.0))
            columns.update({"contratos": count, "participacion": share})
            layout += [("Contratos vigentes", "contratos", "int", 16.0), ("Participación", "participacion", "pct", 12.0)]
            return frame, columns, layout
        if level in ("rama", "tipo", "etnia", "nac"):
            column = {"rama": "rama_actividad", "tipo": "tipo_contrato", "etnia": "etnia", "nac": "nacionalidad"}[level]
            label = {"rama": "Rama de actividad", "tipo": "Tipo de contrato", "etnia": "Autoidentificación étnica", "nac": "Nacionalidad"}[level]
            frame = source.by_dimension(level, column, provinces)
            return (frame, {column: (label, "text", 380), "contratos": count, "participacion": share},
                    [(label, column, "text", 60.0), ("Contratos vigentes", "contratos", "int", 16.0), ("Participación", "participacion", "pct", 12.0)])
        if level == "empresas":
            frame = source.companies_by_province(provinces=provinces)
            return (frame, {"provincia": ("Provincia", "text", 240), "empresas": ("Empresas con contratos vigentes", "int")},
                    [("Provincia", "provincia", "text", 30.0), ("Empresas con contratos vigentes", "empresas", "int", 24.0)])
        if level == "jub_anio":
            frame = self.years.assign(anio_texto=[f"{int(a)}" + (f" (al {self.cut['retirement_label']})" if p else "")
                                                  for a, p in zip(self.years.anio, self.years.parcial)])
            columns = {"anio_texto": ("Año", "text", 200), "expedientes": ("Expedientes", "int"),
                       "monto": ("Compensaciones (USD)", "money", None, None, "Monto"), "promedio": ("Promedio por expediente (USD)", "money", None, None, "Promedio")}
            layout = [("Año", "anio_texto", "text", 26.0), ("Expedientes", "expedientes", "int", 14.0), ("Compensaciones (USD)", "monto", "usd", 20.0),
                      ("Promedio por expediente (USD)", "promedio", "usd", 20.0)]
            return frame, columns, layout
        if level == "jub_provincia":
            frame = source.retirement_by("provincia", self.year, provinces)
            columns = {"categoria": ("Provincia", "text", 220), "expedientes": ("Expedientes", "int"), "participacion": share,
                       "monto": ("Compensaciones (USD)", "money", None, None, "Monto")}
            layout = [("Provincia", "categoria", "text", 28.0), ("Expedientes", "expedientes", "int", 14.0), ("Participación", "participacion", "pct", 12.0),
                      ("Compensaciones (USD)", "monto", "usd", 20.0)]
            return frame, columns, layout
        months = self.info.get("months") or []
        frame = pd.DataFrame({"mes": [m["label"] for m in months], "contratos": [m["value"] for m in months]})
        total = frame.contratos.sum() if len(frame) else 0
        frame["participacion"] = frame.contratos / total * 100 if total else 0.0
        frame["acumulado"] = frame.contratos.cumsum() if len(frame) else []
        return (frame, {"mes": ("Mes", "text", 150), "contratos": ("Contratos registrados", "int"), "participacion": share,
                        "acumulado": ("Acumulado del año", "int", None, None, "Acumulado")},
                [("Mes", "mes", "text", 18.0), ("Contratos registrados", "contratos", "int", 18.0), ("Participación", "participacion", "pct", 14.0),
                 ("Acumulado del año", "acumulado", "int", 18.0)])

    def _table(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        levels = dict(self.TABLES)
        if self.provinces:
            levels.pop("Contratos por mes", None)
        if st.session_state.get("labour_detail") not in levels:
            st.session_state["labour_detail"] = next(iter(levels))
        name = st.segmented_control("Nivel de detalle", list(levels), key="labour_detail", required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(levels[name])
        with st.container(border=True, key="card_labour_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="labour_table",
                          bar="participacion" if "participacion" in columns else None)
            download_table(frame, layout, title="Gestión laboral", subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_laboral_{self.period['id']}.xlsx", key="labour_xlsx")

    # --------------------------------------------------------------------------------------------- reports
    def report_options(self) -> None:
        """Territorial level of the documents: provinces, cantons or both."""
        options = list(REPORT_LEVELS)
        if st.session_state.get("report_level_labour") not in options:
            st.session_state["report_level_labour"] = "todo"
        chosen = st.segmented_control("Nivel territorial", options, format_func=REPORT_LEVELS.get, key="report_level_labour",
                                      required=True, width="stretch")
        self.report_level = chosen if chosen in options else "todo"

    def scope_items(self) -> list[tuple[str, str]]:
        return [("Corte", self.cut["contracts_label"]), ("Ámbito", self.label), ("Territorio", self.territory_label),
                ("Nivel territorial", REPORT_LEVELS.get(self.report_level, "Todo"))]

    def products_notes(self) -> dict[str, str]:
        return {
            "resumen": "Dos páginas en PDF: cifras clave, mapa y provincias con más contratos, perfil de los contratos, actividad "
                       "económica, contratación del año y compensación jubilar.",
            "presentacion": "Cinco diapositivas editables en PowerPoint: cifras clave, territorio, perfil y actividad económica, "
                            "contratación del año y compensación jubilar.",
            "datos": "Libro de Excel con resumen, provincias, cantones, perfil y actividad, jubilación, contratos por mes y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        return ["Resumen", "Provincias", "Cantones", "Perfil y actividad", "Jubilación", "Contratos por mes", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        if kind == "datos":
            return [("grid", "Resumen", "Cifras clave, mapa y aspectos destacados"), ("map", "Provincias", "Contratos vigentes y empresas"),
                    ("landmark", "Cantones", "Contratos vigentes de cada cantón"),
                    ("users", "Perfil y actividad", "Sexo, edad, discapacidad, rama, tipo de contrato, autoidentificación y nacionalidad"),
                    ("user-check", "Jubilación", "Expedientes y compensaciones por año, régimen, sexo y provincia"),
                    ("file-check", "Contratos por mes", "Contratos registrados cada mes del año"),
                    ("shield", "Ficha técnica", "Fuentes, fechas de corte y definiciones")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores principales"), ("map", "Territorio", "Mapa y provincias con más contratos"),
                    ("users", "Perfil y actividad", "Quiénes tienen contrato y en qué actividades"),
                    ("file-check", "Contratación del año", "Contratos registrados por mes"),
                    ("user-check", "Compensación jubilar", "Expedientes y recursos por año y régimen")]
        return [("grid", "Cifras clave", "Contratos vigentes, empresas y jubilación"), ("map", "Territorio", "Mapa y principales provincias"),
                ("users", "Perfil y actividad", "Sexo, edad, ramas y tipos de contrato"),
                ("user-check", "Compensación jubilar", "Expedientes y montos por año")]

    def slide_titles(self) -> tuple[str, str]:
        return "Contratos vigentes por territorio", "Compensación jubilar"

    def preview_visual(self) -> str:
        svg, _label = self.map_svg(night=False, width=300, measure="contratos", level="provincia")
        return svg

    def digest(self) -> str:
        return fingerprint(self.stock, tuple(self.provinces), self.cut["contracts_label"], self.report_level)

    def report_context(self, title: str) -> dict:
        from src.reports.areas import labour_context
        return labour_context(self, title=title)


def _count(unit: str):
    from src.indicators import Indicator
    return Indicator("valor", unit.capitalize(), "count", "chart", unit)


def _short_branch(name: str) -> str:
    """Chart names of the branches of activity (tables keep the official name)."""
    short = {"Comercio al por Mayor y al por Menor; Reparacion de Vehiculos Automotores y Motocicletas": "Comercio y reparación de vehículos",
             "Agricultura, Ganaderia, Silvicultura y Pesca": "Agricultura, ganadería y pesca",
             "Actividades de Servicios Administrativos y de Apoyo": "Servicios administrativos y de apoyo",
             "Actividades Profesionales, Cientificas y Tecnicas": "Actividades profesionales y técnicas",
             "Administracion Publica y Defensa; Planes de Seguridad Social de Afiliacion Obligatoria": "Administración pública y defensa",
             "Actividades de Atencion de la Salud Humana y de Asistencia Social": "Salud y asistencia social",
             "Actividades de Alojamiento y de Servicio de Comidas": "Alojamiento y comidas",
             "Distribucion de Agua; Alcantarillado, Gestion de Desechos y Actividades de Saneamiento": "Agua, saneamiento y desechos",
             "Suministro de Electricidad, Gas, Vapor y Aire Acondicionado": "Electricidad y gas",
             "Actividades de los Hogares Como Empleadores; Actividades No Diferenciadas de los Hogares Como Productores de Bienes y Servicios para Uso Propio": "Hogares como empleadores",
             "Industrias Manufactureras": "Industrias manufactureras", "Transporte y Almacenamiento": "Transporte y almacenamiento",
             "Construccion": "Construcción", "Enseñanza": "Enseñanza", "Otras Actividades de Servicios": "Otras actividades de servicios",
             "Informacion y Comunicacion": "Información y comunicación", "Actividades Financieras y de Seguros": "Actividades financieras",
             "Explotacion de Minas y Canteras": "Minas y canteras", "Actividades Inmobiliarias": "Actividades inmobiliarias",
             "Artes, Entretenimiento y Recreacion": "Artes y recreación"}
    return short.get(name, name)


def _short_type(name: str) -> str:
    short = {"Contrato por obra o servicio determinado dentro del giro del negocio": "Obra o servicio dentro del giro del negocio",
             "Contrato de jornada parcial permanente": "Jornada parcial permanente"}
    return short.get(name, name.replace("Contrato ", "").capitalize() if name.startswith("Contrato ") else name)
