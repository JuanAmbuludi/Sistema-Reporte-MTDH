"""Transfers and services: coverage, budget and its execution by program, province and parish.

Each module reads only its own rows (transfers are never mixed with services).  The map, the rankings and the
tables use the parish detail when the cut has it, and the provinces otherwise.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, geo, territory, theme, ui
from src.data import aggregate, filter_data, summarize
from src.indicators import MODULES
from src.views.common import compact, download_table, fingerprint, show_chart, show_wide_chart


@st.cache_data(show_spinner=False, max_entries=48)
def _svg(layer: str, values: dict, titles: dict, regions: dict, focus: tuple, selected: tuple, night: bool = True,
         width: int = 640) -> str:
    if night:
        fills = ui.map_fills(values)
        return geo.svg_map(fills, layer=layer, titles=titles, regions=regions, focus=set(focus), selected=set(selected),
                           stroke=theme.MORADO_900, width=width)
    fills = ui.map_fills(values, theme.SEQUENTIAL[2:])
    return geo.svg_map(fills, layer=layer, titles=titles, regions=regions, focus=set(focus), selected=set(selected),
                       width=width, pad=6, stroke="#FFFFFF", selected_fill=theme.ORO, equator=None, locator=False,
                       empty_fill="#F1EEF6", context_fill="#F1EEF6", border_color="rgba(81,47,141,.45)",
                       frame_color="rgba(81,47,141,.35)", label_color="rgba(81,47,141,.6)", css_class="ec-map mini")


def parish_title(indicator) -> str:
    """``Parroquias con más beneficiarios`` · ``Parroquias con mayor presupuesto ejecutado 2026``."""
    if indicator.is_money:
        return f"Parroquias con mayor {indicator.label[:1].lower()}{indicator.label[1:]}"
    return f"Parroquias con más {indicator.label.lower()}"


class TerritorialView:
    kind = "territorial"

    def __init__(self, module_id: str, data: pd.DataFrame, catalog: list[dict], parish_data: pd.DataFrame):
        self.id, self.module = module_id, MODULES[module_id]
        self.label = self.module.label
        self.data, self._catalog, self.parish_data = data, catalog, parish_data
        self.province_names = data.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.to_dict()
        # Chart-length program names; official names stay in tables, except on phones where the label column is narrow.
        self.short_programs = {row.programa: theme.program_label(row.programa_id, row.programa)
                               for row in data.drop_duplicates("programa_id").itertuples()}

    def catalog(self) -> list[dict]:
        return self._catalog

    # ------------------------------------------------------------------------------------------- consultation
    def controls(self, period: dict) -> None:
        module = self.module
        self.period = period
        self.scoped = filter_data(self.data.loc[self.data.periodo_id.eq(period["id"])], secciones=list(module.sections))
        parish = self.parish_data
        self.parish_scope = (parish.loc[parish.periodo_id.eq(period["id"]) & parish.seccion.isin(module.sections)]
                             if not parish.empty else parish)
        self.has_parishes = not self.parish_scope.empty
        names = self.province_names
        provinces = sorted(self.scoped.provincia_codigo.unique(), key=lambda c: (c == geo.NO_POLYGON, names[c]))
        programs = list(self.scoped.groupby("programa_id").usuarios.sum().sort_values(ascending=False).index)
        self.program_lookup = self.scoped.drop_duplicates("programa_id").set_index("programa_id").programa.to_dict()
        # A change of period or module must not leave hidden selections behind.
        for key, available in [("selected_provinces", provinces), ("selected_programs", programs)]:
            if key in st.session_state:
                st.session_state[key] = [v for v in st.session_state[key] if v in available]
        col_territory, col_program = st.columns(2, gap="small")
        with col_territory:
            self.provinces = st.multiselect("Territorio", provinces, format_func=names.get, placeholder="Todo el país",
                                            key="selected_provinces")
        with col_program:
            self.programs = st.multiselect(module.item.capitalize(), programs, format_func=self.program_lookup.get,
                                           placeholder=f"Todos los {module.items}", key="selected_programs")
        if self.provinces or self.programs:
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary",
                      key="reset_filters")

    @staticmethod
    def _clear() -> None:
        st.session_state["selected_provinces"] = []
        st.session_state["selected_programs"] = []

    empty_message = "La combinación elegida no registra información. Ajuste el territorio o la selección de programas."

    def prepare(self) -> bool:
        module, period = self.module, self.period
        provinces, programs = self.provinces or None, self.programs or None
        self.filtered = filter_data(self.scoped, provincias=provinces, programas=programs)
        if self.filtered.empty:
            return False
        # National context: same period, module and programs, every province.  Shares, maps and rankings use it.
        self.national = filter_data(self.scoped, programas=programs)
        self.parish_filtered = filter_data(self.parish_scope, provincias=provinces, programas=programs) if self.has_parishes else self.parish_scope
        self.parish_national = filter_data(self.parish_scope, programas=programs) if self.has_parishes else self.parish_scope
        self.stats, self.national_stats, self.scope_stats = summarize(self.filtered), summarize(self.national), summarize(self.scoped)
        self.executed = bool(self.scoped["presupuesto_ejecutado"].notna().all() and self.scoped["presupuesto_codificado"].notna().all())
        self.money = module.money(period["year"], executed=self.executed)
        self.people = module.people_indicator()
        self.selected = set(self.provinces)
        if len(self.provinces) == 1:
            self.territory_label = self.province_names[self.provinces[0]]
        elif self.provinces:
            self.territory_label = f"{len(self.provinces)} provincias"
        else:
            self.territory_label = "Nacional"
        self.programs_label = (self.program_lookup[self.programs[0]] if len(self.programs) == 1 else
                               f"{len(self.programs)} {module.items}" if self.programs else f"Todos los {module.items}")
        self.context_label = f"{period['label']} · {self.territory_label}"
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        period = self.period
        chip = f"Corte {period['label'].lower()}" if period["month"] else period["label"]
        headline = f"{self.module.label} en {self.territory_label}" if self.provinces else self.module.label
        return chip, headline, self.module.description

    # ------------------------------------------------------------------------------------------------- map
    def hero_visual(self) -> None:
        indicators = self.module.indicators(self.period["year"], executed=self.executed, parishes=self.has_parishes)
        by_key = {indicator.key: indicator for indicator in indicators}
        if st.session_state.get("map_indicator") not in by_key:
            st.session_state["map_indicator"] = indicators[0].key
        key = st.segmented_control("Indicador territorial", list(by_key), format_func=lambda k: by_key[k].compact,
                                   key="map_indicator", required=True, width="stretch")
        self.indicator = by_key[key]
        svg, label, selected_key, equator = self.map_svg(night=True)
        ui.hero_map(svg, label, selected=selected_key, equator=equator)

    def _focus(self) -> set[str]:
        return {c for c in self.selected if c != geo.NO_POLYGON}

    def map_svg(self, night: bool = True, width: int = 640, indicator=None) -> tuple[str, str, str, bool]:
        """The map of the selection: its SVG, the key label, the selection key and whether the equator shows."""
        indicator = indicator or self.indicator
        key = indicator.key
        value_text = lambda v: charts.fmt_value(v, indicator)  # noqa: E731
        focus = self._focus() if night else set()
        names = self.province_names
        province_values = charts.province_values(self.national, key).set_index("provincia_codigo")[key].astype(float).to_dict()
        if self.has_parishes:
            source = self.parish_filtered if focus else self.parish_national
            values, members = territory.polygon_values(source, key)
            titles, regions = {}, {}
            if focus:
                parishes, cantons = geo.features("parroquia"), geo.features("canton")
                for polygon, codes in members.items():
                    meta = parishes.get(polygon, {})
                    name, canton = meta.get("name", polygon), cantons.get(meta.get("canton"), {}).get("name", "")
                    place = name if not canton or canton == name else f"{name} · {canton}"
                    extra = f"\nIncluye {len(codes)} parroquias" if len(codes) > 1 else ""
                    titles[polygon] = f"{place}\n{value_text(values.get(polygon))}{extra}"
            else:
                regions = {code: f"{names.get(code, code)}\n{value_text(value)}" for code, value in province_values.items()
                           if code != geo.NO_POLYGON}
            svg = _svg("parroquia", values, titles, regions, tuple(sorted(focus)), tuple(sorted(self.selected)), night, width)
            label = f"{indicator.label} por parroquia"
        else:
            values = {c: v for c, v in province_values.items() if c != geo.NO_POLYGON}
            titles = {c: f"{names.get(c, c)}: {value_text(v)}" for c, v in values.items()}
            svg = _svg("provincia", values, titles, {}, (), tuple(sorted(self.selected)), night, width)
            label = f"{indicator.label} por provincia"
        selected_key = ("Provincia seleccionada" if len(self.selected) == 1 else "Provincias seleccionadas") if self.selected else ""
        equator = True
        if focus:
            _x0, y0, _x1, y1 = geo.bounds("provincia", focus, inset=False)
            equator = y0 < 0 < y1
        return svg, label, selected_key, equator

    # ------------------------------------------------------------------------------------------------ KPIs
    def kpi_cards(self) -> list[dict]:
        module, stats = self.module, self.stats
        filters_active = bool(self.provinces or self.programs)
        share_label = "del total nacional" if self.provinces else "del total del ámbito"
        reference = self.national_stats if self.provinces else self.scope_stats

        def share(key):
            value, whole = stats.get(key), reference.get(key)
            return value / whole * 100 if filters_active and value is not None and whole else None

        cards = [{"label": self.people.label, "value": stats["usuarios"], "icon": self.people.icon, "tone": "morado",
                  "share": share("usuarios"), "share_label": share_label}]
        for extra in module.extra:
            cards.append({"label": extra.label, "value": stats[extra.key], "icon": extra.icon, "tone": "violeta",
                          "share": share(extra.key), "share_label": share_label})
        fiscal = self.money["fiscal"]
        if self.executed:
            cards.append({"label": fiscal.label, "value": (stats["presupuesto_ejecutado"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "banknote", "tone": "oro", "share": share("presupuesto_ejecutado"),
                          "share_label": share_label})
            cards.append({"label": "Ejecución presupuestaria", "value": stats["porcentaje_ejecucion"], "decimals": 1, "suffix": "%",
                          "icon": "target", "tone": "lila", "bar": stats["porcentaje_ejecucion"],
                          "bar_label": f"Codificado: USD {ui.millions(stats['presupuesto_codificado'])} millones"})
        else:
            cards.append({"label": fiscal.label, "value": (stats["monto_fiscal"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "banknote", "tone": "oro", "share": share("monto_fiscal"),
                          "share_label": share_label})
            if not module.extra:
                active = int(self.filtered.groupby("programa_id").usuarios.sum().gt(0).sum())
                total = int(self.filtered.programa_id.nunique())
                cards.insert(1, {"label": f"{module.items.capitalize()} con {self.people.label.lower()}", "value": active,
                                 "icon": "layers", "tone": "violeta",
                                 "note": f"De {total} {module.items if total != 1 else module.item} en la selección"})
        government = self.money["government"]
        cards.append({"label": government.label, "value": (stats["monto_gobierno"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                      "suffix": "millones", "icon": "landmark", "tone": "fucsia", "share": share("monto_gobierno"),
                      "share_label": share_label})
        return cards

    # ------------------------------------------------------------------------------------------- dashboard
    def dashboard(self) -> None:
        module, people, money = self.module, self.people, self.money
        ui.section_heading(f"Resultados por {module.item}", self.context_label, "chart")
        budget_subtitle = f"Millones de USD · {money['previous'].label} y {money['fiscal'].label.lower()}"
        cards = [("card_people", f"{people.label} por {module.item}", "Número de personas",
                  lambda: charts.category_bars(self.filtered, people, self.short_programs), "category_people")]
        if module.extra:
            extra = module.extra[0]
            cards.append(("card_extra", f"{extra.label} por {module.item}", "Número de unidades",
                          lambda: charts.category_bars(self.filtered, extra, self.short_programs), "category_extra"))
        if self.executed:
            rows = aggregate(self.filtered, ["programa_id", "programa"]).sort_values("presupuesto_codificado", ascending=False)
            rows["nombre"] = rows.programa.map(lambda p: self.short_programs.get(p, p))
            cards.append(("card_execution", f"Ejecución presupuestaria por {module.item}",
                          "Presupuesto devengado sobre codificado · la línea dorada marca el total",
                          lambda: charts.execution_bullets(rows, "nombre", hover_label="programa", reference=self.stats["porcentaje_ejecucion"]),
                          "category_execution"))
        cards.append(("card_budget", f"Presupuesto por {module.item}", budget_subtitle,
                      lambda: charts.resources_stack(self.filtered, money, self.short_programs), "category_budget"))
        for start in range(0, len(cards), 2):
            pair = cards[start:start + 2]
            columns = st.columns(2, gap="medium") if len(pair) == 2 else [st.container()]
            for column, (key, title, subtitle, build, chart_key) in zip(columns, pair):
                with column, st.container(border=True, key=key):
                    ui.chart_title(title, subtitle)
                    show_chart(build(), chart_key)
        self._territory_section()
        self._table_section()

    def _territory_section(self) -> None:
        module, indicator = self.module, self.indicator
        ui.section_heading("Resultados por territorio", f"{indicator.label} · {self.period['label']}", "map")
        share_label = "del total nacional"
        ranking = ("card_rank", f"{indicator.label} por provincia",
                   "Provincias seleccionadas en dorado" if self.selected else "Provincias ordenadas de mayor a menor",
                   lambda: show_chart(charts.province_ranking(self.national, indicator, highlight=self.selected,
                                                              share_label=share_label), "province_ranking"))
        matrix = ("card_matrix", f"Distribución por {module.item}", f"Participación de cada {module.item} en la provincia",
                  lambda: show_wide_chart(charts.composition_matrix(self.national, indicator, self.short_programs,
                                                                    highlight=self.selected), "province_matrix"))
        layout = [(ranking, matrix)]
        if self.has_parishes:
            scope = self.parish_filtered
            table = territory.parish_table(scope, [indicator.key]).head(20)
            where = self.territory_label if self.provinces else "el país"
            rows = None
            if self.executed:
                rows = aggregate(self.national, ["provincia_codigo", "provincia"])
                rows = rows.loc[rows.provincia_codigo.ne(geo.NO_POLYGON)].sort_values("presupuesto_codificado", ascending=False)
            height = charts.execution_height(len(rows), 30) if rows is not None else None
            parish = ("card_parish", parish_title(indicator), f"Las {len(table)} primeras de {where}",
                      lambda: show_chart(charts.ranked_bars([territory.parish_label(r) for _i, r in table.iterrows()],
                                                            list(table[indicator.key]), indicator, height=height,
                                                            hover=[f"{r.parroquia_nombre}, {r.canton_nombre} · {r.provincia}" for r in table.itertuples()],
                                                            share_total=float(pd.to_numeric(scope[indicator.key], errors="coerce").sum()),
                                                            share_label="de la selección"), "parish_ranking"))
            second = [parish]
            if rows is not None:
                highlight = {self.province_names[c] for c in self.selected if c in self.province_names}
                second.append(("card_province_execution", "Ejecución presupuestaria por provincia",
                               "Devengado sobre codificado · la línea dorada marca el total nacional",
                               lambda: show_chart(charts.execution_bullets(rows, "provincia", highlight=highlight, per=30,
                                                                           reference=self.national_stats["porcentaje_ejecucion"],
                                                                           reference_label="Nacional"), "province_execution")))
            layout.append(tuple(second))
        for row in layout:
            columns = st.columns([1, 1.15] if len(row) == 2 else [1], gap="medium")
            for column, (key, title, subtitle, draw) in zip(columns, row):
                with column, st.container(border=True, key=key):
                    ui.chart_title(title, subtitle)
                    draw()

    def _levels(self) -> dict[str, str]:
        item = self.module.item
        levels = {f"Por {item}": "programa", "Por provincia": "provincia", f"Por provincia y {item}": "provincia_programa"}
        if self.has_parishes:
            levels.update({"Por cantón": "canton", "Por parroquia": "parroquia"})
        return levels

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        """Table of a level: rows, on-screen columns and the Excel layout."""
        module, money, people = self.module, self.money, self.people
        extras = [extra for extra in module.extra]
        if level in ("canton", "parroquia"):
            keys = ["usuarios", *[e.key for e in extras], "presupuesto_ejecutado"]
            frame = (territory.canton_table(self.parish_filtered, keys) if level == "canton"
                     else territory.parish_table(self.parish_filtered, keys))
            total = pd.to_numeric(frame.usuarios, errors="coerce").sum()
            frame["participacion"] = pd.to_numeric(frame.usuarios, errors="coerce") / total * 100 if total else 0.0
            columns = {"provincia": ("Provincia", "text", 170), "canton_nombre": ("Cantón", "text", 190)}
            layout = [("Provincia", "provincia", "text", 24.0), ("Cantón", "canton_nombre", "text", 26.0)]
            if level == "parroquia":
                columns["parroquia_nombre"] = ("Parroquia", "text", 210)
                columns["parroquia_codigo"] = ("Código", "text", 90)
                layout += [("Parroquia", "parroquia_nombre", "text", 30.0), ("Código DPA", "parroquia_codigo", "text", 12.0)]
            columns.update({"usuarios": (people.label, "int", None, None, people.label),
                            "participacion": ("Participación", "pct", None, None, "Peso")})
            layout += [(people.label, "usuarios", "int", 14.0), ("Participación", "participacion", "pct", 12.0)]
            for extra in extras:
                columns[extra.key] = (extra.label, "int", 150, None, extra.compact.split()[0])
                layout.append((extra.label, extra.key, "int", 13.0))
            columns["presupuesto_ejecutado"] = (f"{money['fiscal'].label} (USD)", "money")
            layout.append((f"{money['fiscal'].label} (USD)", "presupuesto_ejecutado", "usd", 20.0))
            return frame.sort_values("usuarios", ascending=False), columns, layout
        groups = {"programa": ["programa"], "provincia": ["provincia"], "provincia_programa": ["provincia", "programa"]}[level]
        frame = aggregate(self.filtered, groups)
        total = frame.usuarios.sum()
        frame["participacion"] = (frame.usuarios.astype(float) / total * 100) if total else 0.0
        frame = frame.sort_values("usuarios", ascending=False)
        if compact() and "programa" in frame:
            frame = frame.assign(programa=frame.programa.map(lambda name: self.short_programs.get(name, name)))
        columns = {"provincia": ("Provincia", "text", 190), "programa": (module.item.capitalize(), "text", 292),
                   "usuarios": (people.label, "int", None, None, people.label),
                   "participacion": ("Participación", "pct", None, None, "Peso")}
        layout = [("Provincia", "provincia", "text", 26.0), (module.item.capitalize(), "programa", "text", 36.0),
                  (people.label, "usuarios", "int", 14.0), ("Participación", "participacion", "pct", 12.0)]
        for extra in extras:
            columns[extra.key] = (extra.label, "int", 156, None, extra.compact.split()[0])
            layout.append((extra.label, extra.key, "int", 13.0))
        columns[money["fiscal"].key] = (f"{money['fiscal'].label} (USD)", "money")
        layout.append((f"{money['fiscal'].label} (USD)", money["fiscal"].key, "usd", 19.0))
        if self.executed:
            columns["presupuesto_codificado"] = (f"{money['coded'].label} (USD)", "money")
            columns["porcentaje_ejecucion"] = ("Ejecución (%)", "pct")
            layout += [(f"{money['coded'].label} (USD)", "presupuesto_codificado", "usd", 19.0),
                       ("Ejecución", "porcentaje_ejecucion", "pct", 12.0)]
        columns[money["previous"].key] = (f"{money['previous'].compact} (USD)", "money")
        columns[money["government"].key] = (f"{money['government'].compact} (USD)", "money")
        layout += [(f"{money['previous'].label} (USD)", money["previous"].key, "usd", 21.0),
                   (f"{money['government'].label} (USD)", money["government"].key, "usd", 21.0)]
        layout = [item for item in layout if item[1] in frame]
        return frame, columns, layout

    def _table_section(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        levels = self._levels()
        if st.session_state.get("detail_level") not in levels:
            st.session_state["detail_level"] = next(iter(levels))
        name = st.segmented_control("Nivel de detalle", list(levels), key="detail_level", required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(levels[name])
        with st.container(border=True, key="card_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="detail_table", bar="participacion")
            subtitle = f"{self.period['label']} · {self.module.label} · {self.territory_label} · {name.lower()}"
            download_table(frame, layout, title="Cuadro de resultados", subtitle=subtitle, period_label=self.period["label"],
                           file_name=f"MTDH_cuadro_{self.id}_{self.period['id']}.xlsx", key="detail_xlsx",
                           share_fields=("participacion", "porcentaje_ejecucion"))

    # --------------------------------------------------------------------------------------------- reports
    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.module.label), ("Territorio", self.territory_label),
                (self.module.items.capitalize(), self.programs_label)]

    def products_notes(self) -> dict[str, str]:
        item, territory_word = self.module.item, "parroquia" if self.has_parishes else "provincia"
        return {
            "resumen": f"Una página en PDF con las cifras clave, el mapa por {territory_word}, los resultados por {item} y los aspectos destacados.",
            "presentacion": f"Tres diapositivas editables en PowerPoint: cifras clave, resultados por territorio y por {item}.",
            "datos": f"Libro de Excel con resumen, resultados por {item}, provincias{', parroquias' if self.has_parishes else ''}, detalle con filtros y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        sheets = ["Resumen", self.module.items.capitalize(), "Provincias"]
        if self.has_parishes:
            sheets.append("Parroquias")
        return sheets + ["Detalle", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        module, people = self.module, self.people
        if kind == "datos":
            items = [("grid", "Resumen", "Cifras clave, mapa y aspectos destacados"),
                     ("chart", module.items.capitalize(), f"{people.label}, participación, presupuesto y ejecución por {module.item}"),
                     ("map", "Provincias", "Posición de cada provincia en el país")]
            if self.has_parishes:
                items.append(("pin", "Parroquias", "Cada parroquia con su cantón, cobertura y presupuesto ejecutado"))
            return items + [("table", "Detalle", f"Cada {module.item} en cada provincia, con filtros y totales"),
                            ("shield", "Ficha técnica", "Periodo, ámbito, territorio e indicadores")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores principales"),
                    ("map", "Resultados por territorio", "Mapa y territorios con mayor cobertura"),
                    ("chart", f"Resultados por {module.item}", "Gráfico editable y aspectos destacados")]
        return [("grid", "Cifras clave", "Indicadores principales del periodo"),
                ("map", "Territorio", "Mapa y territorios con mayor cobertura"),
                ("chart", f"Resultados por {module.item}", f"{people.label} por {module.item}"),
                ("award", "Aspectos destacados", "Conclusiones para la toma de decisiones")]

    def slide_titles(self) -> tuple[str, str]:
        return "Resultados por territorio", f"Resultados por {self.module.item}"

    def preview_visual(self) -> str:
        values = charts.province_values(self.national, "usuarios").set_index("provincia_codigo")["usuarios"].astype(float).to_dict()
        values = {c: v for c, v in values.items() if c != geo.NO_POLYGON}
        return _svg("provincia", values, {}, {}, (), tuple(sorted(self.selected)), False, 300)

    def digest(self) -> str:
        return fingerprint(self.filtered, self.parish_filtered)

    def report_context(self, title: str) -> dict:
        from src.reports import build_report_context
        return build_report_context(self.filtered, national=self.national, title=title, period_label=self.period["label"],
                                    territory_label=self.territory_label, programs_label=self.programs_label,
                                    selected_codes=self.selected, parishes=self.parish_filtered,
                                    parishes_national=self.parish_national)
