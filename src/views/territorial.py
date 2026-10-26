"""Transfers and services: coverage, budget and its execution by program, province, canton and parish, month by month.

Each module reads only its own rows (transfers are never mixed with services).  Every month of the series has the
parish detail, so the map and every territorial chart offer the three levels (Provincia · Cantón · Parroquia) with a
selector on top of the chart; annual references keep the provinces and show the selector disabled.  The latest cut
carries the budget by territory; the other months of the transfers carry the national accrued budget of each program,
shown only while no territory is chosen.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, geo, names as place_names, territory, theme, ui
from src.data import MONTHS, aggregate, filter_data, summarize
from src.indicators import MODULES
from src.territory import LEVEL_GENDER, LEVEL_LABELS, LEVEL_PLURALS, LEVELS
from src.views.common import compact, download_table, fingerprint, show_chart, show_wide_chart

# Territories in a canton or parish chart: as many rows as provinces, so every level reads alike.
TOP = 25
LEVEL_ICONS = {"provincia": "map", "canton": "landmark", "parroquia": "pin"}
REPORT_LEVELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia", "todo": "Todo"}


@st.cache_data(show_spinner=False, max_entries=64)
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


def phrase(level: str, shown: int, total: int, where: str) -> str:
    """«Los 25 primeros cantones del país» · «Las 71 parroquias de Guayas» · «El cantón de Galápagos»."""
    masculine = LEVEL_GENDER[level] == "m"
    if total == 1:
        return f"{'El' if masculine else 'La'} {LEVEL_LABELS[level].lower()} {where}"
    article, plural = ("Los" if masculine else "Las"), LEVEL_PLURALS[level].lower()
    if shown >= total:
        return f"{article} {ui.number(total)} {plural} {where}"
    return f"{article} {shown} {'primeros' if masculine else 'primeras'} {plural} {where}"


def month_change_text(change: float, previous: str) -> str:
    """«380 más que en agosto» · «1.234 menos que en agosto» · «Igual que en agosto»."""
    if not change:
        return f"Igual que en {previous}"
    return f"{ui.number(abs(change))} {'más' if change > 0 else 'menos'} que en {previous}"


def report_levels(level: str) -> list[str]:
    """Levels a document covers: one, or the three when the reader asks for everything."""
    return list(LEVELS) if level == "todo" else [level]


class TerritorialView:
    kind = "territorial"

    def __init__(self, module_id: str, data: pd.DataFrame, catalog: list[dict], parish_data: pd.DataFrame,
                 program_budget: pd.DataFrame | None = None):
        self.id, self.module = module_id, MODULES[module_id]
        self.label = self.module.label
        self.data, self._catalog, self.parish_data = data, catalog, parish_data
        # National accrued budget of each program for every month (transfers); September also has it by territory.
        budget = program_budget if program_budget is not None else pd.DataFrame()
        self.program_budget = budget.loc[budget.programa_id.isin(data.loc[data.seccion.isin(self.module.sections), "programa_id"].unique())] \
            if not budget.empty else budget
        self.province_names = data.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.to_dict()
        # Chart-length program names; official names stay in tables, except on phones where the label column is narrow.
        self.short_programs = {row.programa: theme.program_label(row.programa_id, row.programa)
                               for row in data.drop_duplicates("programa_id").itertuples()}
        self.report_level = "todo"

    def catalog(self) -> list[dict]:
        return self._catalog

    # ------------------------------------------------------------------------------------------- consultation
    def _scope(self, period: dict) -> tuple[list[str], list[str]]:
        """Rows of the period and module, and the provinces and programs a reader can choose."""
        module = self.module
        self.period = period
        scoped = filter_data(self.data.loc[self.data.periodo_id.eq(period["id"])], secciones=list(module.sections))
        # Programs without people or money in the period (pensions closed in earlier years) are left out of the reading.
        measures = [c for c in ("usuarios", "unidades", "presupuesto_ejecutado", "presupuesto_codificado", "monto_fiscal") if c in scoped]
        totals = scoped.groupby("programa_id")[measures].sum(min_count=1).apply(pd.to_numeric, errors="coerce").fillna(0)
        funded = set()
        if not self.program_budget.empty:
            month = self.program_budget.loc[self.program_budget.periodo_id.eq(period["id"])]
            funded = set(month.loc[pd.to_numeric(month.devengado_acumulado, errors="coerce").fillna(0) > 0].programa_id)
        active = {code for code, row in totals.iterrows() if row.abs().sum() > 0} | funded
        self.scoped = scoped.loc[scoped.programa_id.isin(active)] if active else scoped
        parish = self.parish_data
        self.parish_scope = (parish.loc[parish.periodo_id.eq(period["id"]) & parish.seccion.isin(module.sections)]
                             if not parish.empty else parish)
        self.has_parishes = not self.parish_scope.empty
        names = self.province_names
        provinces = sorted(self.scoped.provincia_codigo.unique(), key=lambda c: (c == geo.NO_POLYGON, names.get(c, c)))
        programs = list(self.scoped.groupby("programa_id").usuarios.sum().sort_values(ascending=False).index)
        self.program_lookup = self.scoped.drop_duplicates("programa_id").set_index("programa_id").programa.to_dict()
        return provinces, programs

    def select(self, period: dict, provinces=(), programs=()) -> None:
        """A period and a selection without widgets (scripts and tests build documents through it)."""
        self._scope(period)
        self.provinces, self.programs = list(provinces), list(programs)

    def controls(self, period: dict) -> None:
        module = self.module
        provinces, programs = self._scope(period)
        names = self.province_names
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
        scoped = self.scoped
        # What budget the cut carries: by territory (latest cut), national by program (every month of the transfers),
        # an annual reference by province (earlier years) or none (months of the services).
        period_budget = self.program_budget.loc[self.program_budget.periodo_id.eq(period["id"])] if not self.program_budget.empty else self.program_budget
        if scoped["presupuesto_ejecutado"].notna().all() and scoped["presupuesto_codificado"].notna().all():
            self.budget_mode = "territorial"
        elif scoped["monto_fiscal"].notna().any():
            self.budget_mode = "reference"
        elif not period_budget.empty:
            self.budget_mode = "national"
        else:
            self.budget_mode = "none"
        self.executed = self.budget_mode == "territorial"
        # A national budget never describes a province: with a territory chosen it is left out.
        self.budget_shown = self.budget_mode in ("territorial", "reference") or (self.budget_mode == "national" and not self.provinces)
        self.money = module.money(period["year"], executed=self.budget_mode in ("territorial", "national"))
        self.people = module.people_indicator()
        self.program_money = self._program_money(period_budget)
        self.budget = self._budget_totals()
        self.monthly = self._monthly()
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
        self.indicator = self.people
        self.map_level = "parroquia" if self.has_parishes else "provincia"
        # The level of the documents is read early: the report form describes the products before its selector.
        level = st.session_state.get("report_level", "todo")
        self.report_level = (level if level in REPORT_LEVELS else "todo") if self.has_parishes else "provincia"
        return True

    # ------------------------------------------------------------------------------------- budget and months
    def _program_money(self, period_budget: pd.DataFrame) -> pd.DataFrame:
        """Budget of each program of the selection: by territory, national or the annual reference (empty without one)."""
        columns = ["programa_id", "programa", "presupuesto_ejecutado", "presupuesto_codificado", "porcentaje_ejecucion", "monto_fiscal",
                   "monto_anterior", "monto_gobierno", "devengado_mes"]
        if self.budget_mode in ("territorial", "reference"):
            rows = aggregate(self.filtered, ["programa_id", "programa"])
            rows = rows.loc[rows[["monto_fiscal", "monto_anterior", "presupuesto_codificado"]].fillna(0).sum(axis=1) > 0]
            if self.budget_mode == "territorial" and not self.program_budget.empty and not self.provinces:
                month = self.program_budget.loc[self.program_budget.periodo_id.eq(self.period["id"])].set_index("programa_id").devengado_mes
                rows = rows.assign(devengado_mes=rows.programa_id.map(month))
            return rows.reindex(columns=columns)
        if self.budget_mode == "national" and not self.provinces:
            rows = period_budget.loc[period_budget.programa_id.isin(self.programs)] if self.programs else period_budget
            rows = rows.assign(presupuesto_ejecutado=rows.devengado_acumulado, monto_fiscal=rows.devengado_acumulado)
            return rows.reindex(columns=columns).reset_index(drop=True)
        return pd.DataFrame(columns=columns)

    def _budget_totals(self) -> dict:
        rows = self.program_money

        def total(column):
            values = pd.to_numeric(rows[column], errors="coerce") if column in rows else pd.Series(dtype=float)
            return float(values.sum()) if values.notna().any() else None

        executed, coded = total("presupuesto_ejecutado"), total("presupuesto_codificado")
        return {"ejecutado": executed, "codificado": coded, "fiscal": total("monto_fiscal"), "anterior": total("monto_anterior"),
                "gobierno": total("monto_gobierno"), "mes": total("devengado_mes"),
                "ejecucion": executed / coded * 100 if executed is not None and coded else None}

    def _monthly(self) -> pd.DataFrame:
        """The selection month by month in the year of the consultation: people, units and the national budget."""
        period = self.period
        if not period.get("month"):
            return pd.DataFrame()
        months = [p for p in self._catalog if p["year"] == period["year"] and p["month"]]
        if len(months) < 2:
            return pd.DataFrame()
        ids = {p["id"] for p in months}
        rows = self.data.loc[self.data.periodo_id.isin(ids) & self.data.seccion.isin(self.module.sections)]
        rows = filter_data(rows, provincias=self.provinces or None, programas=self.programs or None)
        grouped = rows.groupby(["periodo_id", "periodo_mes"], as_index=False)[["usuarios", "unidades"]].sum(min_count=1)
        grouped = grouped.sort_values("periodo_id").reset_index(drop=True)
        grouped["mes"] = [MONTHS[m - 1].capitalize() for m in grouped.periodo_mes]
        grouped["corto"] = [MONTHS[m - 1][:3].capitalize() for m in grouped.periodo_mes]
        grouped["variacion"] = grouped.usuarios.astype(float).diff()
        if not self.program_budget.empty and not self.provinces:
            budget = self.program_budget.loc[self.program_budget.periodo_id.isin(ids)]
            if self.programs:
                budget = budget.loc[budget.programa_id.isin(self.programs)]
            money = budget.groupby("periodo_id", as_index=False)[["devengado_mes", "devengado_acumulado", "presupuesto_codificado"]].sum(min_count=1)
            grouped = grouped.merge(money, on="periodo_id", how="left")
            coded = grouped.presupuesto_codificado
            grouped["porcentaje_ejecucion"] = grouped.devengado_acumulado / coded.where(coded > 0) * 100
        return grouped

    def month_change(self) -> float | None:
        """Change of the people of the selection from the previous month (None for the first month)."""
        monthly = self.monthly
        if monthly.empty:
            return None
        row = monthly.loc[monthly.periodo_id.eq(self.period["id"])]
        if row.empty or pd.isna(row.variacion.iloc[0]):
            return None
        return float(row.variacion.iloc[0])

    def previous_month(self) -> str:
        monthly = self.monthly
        if monthly.empty:
            return ""
        index = monthly.index[monthly.periodo_id.eq(self.period["id"])]
        return monthly.mes.iloc[index[0] - 1].lower() if len(index) and index[0] > 0 else ""

    def hero_copy(self) -> tuple[str, str, str]:
        period = self.period
        chip = f"Corte {period['label'].lower()}" if period["month"] else period["label"]
        headline = f"{self.module.label} en {self.territory_label}" if self.provinces else self.module.label
        return chip, headline, self.module.description

    def _where(self) -> str:
        """«del país» · «de Guayas» · «de la selección»."""
        if not self.provinces:
            return "del país"
        return f"de {self.territory_label}" if len(self.provinces) == 1 else "de la selección"

    def level_control(self, key: str, label: str = "Nivel territorial", *, default: str = "provincia",
                      show_label: bool = False) -> str:
        """Provincia · Cantón · Parroquia; cuts without parish detail keep the province with the selector disabled."""
        options = list(LEVELS)
        if not self.has_parishes:
            st.session_state[key] = "provincia"
        elif st.session_state.get(key) not in options:
            st.session_state[key] = default
        chosen = st.segmented_control(label, options, format_func=LEVEL_LABELS.get, key=key, required=True,
                                      disabled=not self.has_parishes, width="stretch" if show_label or compact() else "content",
                                      label_visibility="visible" if show_label else "collapsed")
        return chosen if chosen in options and self.has_parishes else "provincia"

    # ------------------------------------------------------------------------------------------------- map
    def hero_visual(self) -> None:
        indicators = self.module.indicators(self.period["year"], executed=self.executed, parishes=self.has_parishes,
                                            budget=self.budget_mode in ("territorial", "reference"))
        by_key = {indicator.key: indicator for indicator in indicators}
        if st.session_state.get("map_indicator") not in by_key:
            st.session_state["map_indicator"] = indicators[0].key
        # Indicator and level stacked at full width: three indicators (services, annual references) need the room.
        key = st.segmented_control("Indicador territorial", list(by_key), format_func=lambda k: by_key[k].compact,
                                   key="map_indicator", required=True, width="stretch")
        self.map_level = self.level_control("map_level", default="parroquia", show_label=True)
        self.indicator = by_key[key]
        svg, label, selected_key, equator = self.map_svg(night=True)
        ui.hero_map(svg, label, selected=selected_key, equator=equator)

    def _focus(self) -> set[str]:
        return {c for c in self.selected if c != geo.NO_POLYGON}

    def map_svg(self, night: bool = True, width: int = 640, indicator=None, level: str | None = None) -> tuple[str, str, str, bool]:
        """The map of the selection at a level: its SVG, the key label, the selection key and whether the equator shows."""
        indicator = indicator or self.indicator
        level = (level or self.map_level) if self.has_parishes else "provincia"
        key = indicator.key
        value_text = lambda v: charts.fmt_value(v, indicator)  # noqa: E731
        focus = self._focus() if night and level != "provincia" else set()
        names = self.province_names
        titles, regions = {}, {}
        if level == "parroquia":
            source = self.parish_filtered if focus else self.parish_national
            values, members = territory.polygon_values(source, key)
            if focus:
                parishes, cantons = geo.features("parroquia"), geo.features("canton")
                for polygon, codes in members.items():
                    meta = parishes.get(polygon, {})
                    name, canton = meta.get("name", polygon), cantons.get(meta.get("canton"), {}).get("name", "")
                    place = name if not canton or canton == name else f"{name} · {canton}"
                    extra = f"\nIncluye {len(codes)} parroquias" if len(codes) > 1 else ""
                    titles[polygon] = f"{place}\n{value_text(values.get(polygon))}{extra}"
            else:
                province_values = charts.province_values(self.national, key).set_index("provincia_codigo")[key].astype(float).to_dict()
                regions = {code: f"{names.get(code, code)}\n{value_text(value)}" for code, value in province_values.items()
                           if code != geo.NO_POLYGON}
        elif level == "canton":
            source = self.parish_filtered if focus else self.parish_national
            values, members = territory.canton_values(source, key)
            cantons = geo.features("canton")
            unique = source.drop_duplicates("canton_codigo")
            data_names = {str(c): place_names.place(n) for c, n in zip(unique.canton_codigo, unique.canton)}
            for code, value in values.items():
                meta = cantons.get(code, {})
                others = [data_names.get(c, c) for c in members.get(code, []) if c != code]
                extra = f"\nIncluye {', '.join(others)}" if others else ""
                titles[code] = f"{meta.get('name', code)} · {names.get(meta.get('province'), '')}\n{value_text(value)}{extra}"
        else:
            province_values = charts.province_values(self.national, key).set_index("provincia_codigo")[key].astype(float).to_dict()
            values = {c: v for c, v in province_values.items() if c != geo.NO_POLYGON}
            titles = {c: f"{names.get(c, c)}: {value_text(v)}" for c, v in values.items()}
        svg = _svg(level, values, titles, regions, tuple(sorted(focus)), tuple(sorted(self.selected)), night, width)
        label = f"{indicator.label} por {LEVEL_LABELS[level].lower()}"
        selected_key = ("Provincia seleccionada" if len(self.selected) == 1 else "Provincias seleccionadas") if self.selected else ""
        equator = True
        if focus:
            _x0, y0, _x1, y1 = geo.bounds("provincia", focus, inset=False)
            equator = y0 < 0 < y1
        return svg, label, selected_key, equator

    # ------------------------------------------------------------------------------------------------ KPIs
    def kpi_cards(self) -> list[dict]:
        module, stats, budget = self.module, self.stats, self.budget
        filters_active = bool(self.provinces or self.programs)
        share_label = "del total nacional" if self.provinces else "del total del ámbito"
        reference = self.national_stats if self.provinces else self.scope_stats

        def share(key):
            value, whole = stats.get(key), reference.get(key)
            return value / whole * 100 if filters_active and value is not None and whole else None

        people = {"label": self.people.label, "value": stats["usuarios"], "icon": self.people.icon, "tone": "morado",
                  "share": share("usuarios"), "share_label": share_label}
        change, previous = self.month_change(), self.previous_month()
        if people["share"] is None and change is not None and previous:
            people["note"] = month_change_text(change, previous)
        cards = [people]
        for extra in module.extra:
            cards.append({"label": extra.label, "value": stats[extra.key], "icon": extra.icon, "tone": "violeta",
                          "share": share(extra.key), "share_label": share_label})
        fiscal, government = self.money["fiscal"], self.money["government"]
        span = self.month_span()
        if self.budget_mode in ("territorial", "national") and self.budget_shown:
            cards.append({"label": fiscal.label, "value": (budget["ejecutado"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "banknote", "tone": "oro", "share": share("presupuesto_ejecutado") if self.executed else None,
                          "share_label": share_label, "note": f"Devengado de {span}" if span else ""})
            cards.append({"label": "Ejecución presupuestaria", "value": budget["ejecucion"], "decimals": 1, "suffix": "%",
                          "icon": "target", "tone": "lila", "bar": budget["ejecucion"],
                          "bar_label": f"Codificado: USD {ui.millions(budget['codificado'])} millones"})
            cards.append({"label": government.label, "value": (budget["gobierno"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "landmark", "tone": "fucsia", "share": share("monto_gobierno") if self.executed else None,
                          "share_label": share_label})
            return cards
        if self.budget_mode == "reference":
            cards.append({"label": fiscal.label, "value": (stats["monto_fiscal"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "banknote", "tone": "oro", "share": share("monto_fiscal"),
                          "share_label": share_label})
            if not module.extra:
                cards.insert(1, self._programs_card())
            cards.append({"label": government.label, "value": (stats["monto_gobierno"] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                          "suffix": "millones", "icon": "landmark", "tone": "fucsia", "share": share("monto_gobierno"),
                          "share_label": share_label})
            return cards
        # Months without a budget for the selection: how far the coverage reaches.
        if not module.extra:
            cards.append(self._programs_card())
        if self.has_parishes:
            reach = territory.reach(self.parish_filtered, "usuarios", ["canton", "parroquia"])
            word = self.people.label.lower()
            for level, tone in (("canton", "oro"), ("parroquia", "fucsia")):
                item = reach[level]
                cards.append({"label": f"{LEVEL_PLURALS[level]} con {word}", "value": item["count"], "icon": LEVEL_ICONS[level],
                              "tone": tone, "note": f"{ui.number(item['half'])} {'reúne' if item['half'] == 1 else 'reúnen'} la mitad de los {word}"})
        return cards

    def _programs_card(self) -> dict:
        module = self.module
        active = int(self.filtered.groupby("programa_id").usuarios.sum().gt(0).sum())
        total = int(self.filtered.programa_id.nunique())
        return {"label": f"{module.items.capitalize()} con {self.people.label.lower()}", "value": active, "icon": "layers",
                "tone": "violeta", "note": f"De {total} {module.items if total != 1 else module.item} en la selección"}

    def month_span(self) -> str:
        """«enero a septiembre de 2026» for a monthly cut; empty for an annual reference."""
        month = self.period.get("month")
        if not month:
            return ""
        first = MONTHS[0]
        last = MONTHS[month - 1]
        return f"{first} de {self.period['year']}" if month == 1 else f"{first} a {last} de {self.period['year']}"

    # ------------------------------------------------------------------------------------------- dashboard
    def dashboard(self) -> None:
        module, people, money = self.module, self.people, self.money
        ui.section_heading(f"Resultados por {module.item}", self.context_label, "chart")
        cards = [("card_people", f"{people.label} por {module.item}", "Número de personas",
                  lambda: charts.category_bars(self.filtered, people, self.short_programs), "category_people")]
        if module.extra:
            extra = module.extra[0]
            cards.append(("card_extra", f"{extra.label} por {module.item}", "Número de unidades",
                          lambda: charts.category_bars(self.filtered, extra, self.short_programs), "category_extra"))
        money_rows = self.program_money.copy()
        if self.budget_mode in ("territorial", "national") and self.budget_shown and not money_rows.empty:
            rows = money_rows.sort_values("presupuesto_codificado", ascending=False)
            rows["nombre"] = rows.programa.map(lambda p: self.short_programs.get(p, p))
            span = self.month_span()
            cards.append(("card_execution", f"Ejecución presupuestaria por {module.item}",
                          f"Devengado de {span} sobre codificado · la línea dorada marca el total" if span else
                          "Presupuesto devengado sobre codificado · la línea dorada marca el total",
                          lambda: charts.execution_bullets(rows, "nombre", hover_label="programa", reference=self.budget["ejecucion"]),
                          "category_execution"))
        if self.budget_shown and not money_rows.empty:
            budget_subtitle = f"Millones de USD · {money['previous'].label} y {money['fiscal'].label.lower()}"
            cards.append(("card_budget", f"Presupuesto por {module.item}", budget_subtitle,
                          lambda: charts.resources_stack(money_rows, money, self.short_programs), "category_budget"))
        for start in range(0, len(cards), 2):
            pair = cards[start:start + 2]
            columns = st.columns(2, gap="medium") if len(pair) == 2 else [st.container()]
            for column, (key, title, subtitle, build, chart_key) in zip(columns, pair):
                with column, st.container(border=True, key=key):
                    ui.chart_title(title, subtitle)
                    show_chart(build(), chart_key)
        if len(self.monthly) >= 2:
            self._monthly_section()
        self._territory_section()
        self._table_section()

    # ---------------------------------------------------------------------------------------- monthly view
    def program_months(self, key: str = "usuarios") -> pd.DataFrame:
        """People (or units) of each program of the selection in every month of the year."""
        ids = set(self.monthly.periodo_id)
        rows = self.data.loc[self.data.periodo_id.isin(ids) & self.data.seccion.isin(self.module.sections)]
        rows = filter_data(rows, provincias=self.provinces or None, programas=self.programs or None)
        return rows.groupby(["periodo_id", "programa_id", "programa"], as_index=False)[key].sum(min_count=1)

    def change_window(self) -> tuple[str, str]:
        """Months compared by the change chart: January and the month of the consultation (or the last month)."""
        months = list(self.monthly.periodo_id)
        end = self.period["id"] if self.period["id"] != months[0] else months[-1]
        return months[0], end

    def program_changes(self, key: str = "usuarios") -> pd.DataFrame:
        first, end = self.change_window()
        table = self.program_months(key).pivot_table(index=["programa_id", "programa"], columns="periodo_id", values=key, aggfunc="sum")
        table = table.reindex(columns=[first, end]).fillna(0).reset_index()
        table["inicio"], table["fin"] = table[first].astype(float), table[end].astype(float)
        table["cambio"] = table.fin - table.inicio
        table = table.loc[(table.inicio > 0) | (table.fin > 0)]
        return table[["programa_id", "programa", "inicio", "fin", "cambio"]]

    def _monthly_section(self) -> None:
        monthly, people = self.monthly, self.people
        labels, full = list(monthly.corto), [f"{m} de {self.period['year']}" for m in monthly.mes]
        selected = int(monthly.index[monthly.periodo_id.eq(self.period["id"])][0]) if self.period["id"] in set(monthly.periodo_id) else None
        first_month, last_month = monthly.mes.iloc[0].lower(), monthly.mes.iloc[-1].lower()
        ui.section_heading("Evolución mensual", f"{people.label} de {first_month} a {last_month} de {self.period['year']} · "
                                                f"{self.territory_label} · {self.programs_label}", "trending-up")
        notes = [month_change_text(v, monthly.mes.iloc[i - 1].lower()) if i and pd.notna(v) else "" for i, v in enumerate(monthly.variacion)]
        first, end = self.change_window()
        names = {p["id"]: p["label"].split()[0].lower() for p in self._catalog if p.get("month")}
        changes = self.program_changes()
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_month_people"):
            ui.chart_title(f"{people.label} por mes", "El mes de la consulta en dorado")
            show_chart(charts.month_trend(labels, [float(v) for v in monthly.usuarios.fillna(0)], selected=selected, unit=people.unit,
                                          full=full, notes=notes), "month_people")
        with right, st.container(border=True, key="card_month_change"):
            ui.chart_title(f"Variación por {self.module.item}", f"De {names[first]} a {names[end]} · aumentos en morado, reducciones en fucsia")
            show_chart(charts.change_bars([self.short_programs.get(p, p) for p in changes.programa], list(changes.cambio), unit=people.unit,
                                          full=list(changes.programa), since=names[first]), "month_change")
        if "porcentaje_ejecucion" in monthly and monthly.porcentaje_ejecucion.notna().any():
            left, right = st.columns(2, gap="medium")
            with left, st.container(border=True, key="card_month_accrued"):
                ui.chart_title("Presupuesto devengado por mes", "Millones de USD · total nacional de los programas de la selección")
                show_chart(charts.month_columns(labels, list(monthly.devengado_mes.fillna(0)), selected=selected, money=True, full=full),
                           "month_accrued")
            with right, st.container(border=True, key="card_month_execution"):
                ui.chart_title("Ejecución presupuestaria acumulada", "Devengado acumulado sobre codificado, frente a un ritmo uniforme")
                show_chart(charts.cumulative_execution(labels, list(monthly.porcentaje_ejecucion), selected=selected,
                                                       months=list(monthly.periodo_mes), full=full), "month_execution")
        elif self.module.extra:
            extra = self.module.extra[0]
            unit_changes = self.program_changes(extra.key)
            left, right = st.columns(2, gap="medium")
            with left, st.container(border=True, key="card_month_units"):
                ui.chart_title(f"{extra.label} por mes", "El mes de la consulta en dorado")
                show_chart(charts.month_trend(labels, [float(v) for v in monthly.unidades.fillna(0)], selected=selected, unit=extra.unit,
                                              full=full), "month_units")
            with right, st.container(border=True, key="card_month_units_change"):
                ui.chart_title(f"{extra.label}: variación por {self.module.item}", f"De {names[first]} a {names[end]}")
                show_chart(charts.change_bars([self.short_programs.get(p, p) for p in unit_changes.programa], list(unit_changes.cambio),
                                              unit=extra.unit, full=list(unit_changes.programa), since=names[first]), "month_units_change")

    def territories(self, level: str, keys: list[str], *, positive: bool = True) -> pd.DataFrame:
        """Cantons or parishes of the selection (delimited territories only), largest first by ``keys[0]``."""
        table = territory.level_table(self.parish_filtered, level, keys)
        table = table.loc[table.provincia_codigo.astype(str).ne(geo.NO_POLYGON)]
        if positive:
            table = table.loc[pd.to_numeric(table[keys[0]], errors="coerce").fillna(0) > 0]
        return table.reset_index(drop=True)

    def _reach_words(self, indicator, half: int) -> tuple[str, str]:
        verb = "reúne" if half == 1 else "reúnen"
        if indicator.is_money:
            return "con presupuesto ejecutado", f"{verb} la mitad del {indicator.label[:1].lower()}{indicator.label[1:]}"
        if indicator.key == "unidades":
            return "con unidades de atención", f"{verb} la mitad de las unidades de atención"
        return f"con {indicator.unit}", f"{verb} la mitad de los {indicator.unit}"

    def reach_tiles(self, indicator) -> list[dict]:
        """Territories with the indicator at each level and how many of them gather half of it."""
        levels = ["canton", "parroquia"] if len(self._focus()) == 1 else list(LEVELS)
        reach = territory.reach(self.parish_filtered, indicator.key, levels)
        tiles = []
        for level in levels:
            item = reach[level]
            if not item["count"]:
                continue
            with_text, half_text = self._reach_words(indicator, item["half"])
            tiles.append({"level": level, "icon": LEVEL_ICONS[level], "title": LEVEL_PLURALS[level], "count": item["count"],
                          "with_text": with_text, "half": item["half"], "half_text": half_text})
        return tiles

    def _card_head(self, key: str):
        """Title slot and the level selector on top of a chart (stacked on phones)."""
        head, toggle = st.columns([1.55, 1], gap="small", vertical_alignment="center")
        with toggle:
            level = self.level_control(key)
        return level, head

    def _territory_section(self) -> None:
        indicator = self.indicator
        ui.section_heading("Resultados por territorio", f"{indicator.label} · {self.context_label}", "map")
        if self.has_parishes:
            tiles = self.reach_tiles(indicator)
            if tiles:
                ui.reach_strip(tiles)
        if self.executed:
            layout = [[("card_rank", self._ranking_card), ("card_territory_execution", self._execution_card)],
                      [("card_matrix", self._matrix_card)]]
        else:
            layout = [[("card_rank", self._ranking_card), ("card_matrix", self._matrix_card)]]
        for row in layout:
            columns = st.columns(2, gap="medium") if len(row) == 2 else [st.container()]
            for column, (key, draw) in zip(columns, row):
                with column, st.container(border=True, key=key):
                    draw(wide=len(row) == 1)
        if self.id == "servicios":
            # The institutional geoportal places every unit of attention next to the hazard zones of the territory.
            ui.geoportal_card("servicios", "Visor geográfico del Ministerio con las unidades de atención de los servicios y las zonas "
                                           "de amenaza natural y riesgo antrópico.")

    def _ranking_card(self, wide: bool = False) -> None:
        indicator = self.indicator
        level, head = self._card_head("lvl_rank")
        if level == "provincia":
            rows = len(charts.province_values(self.national, indicator.key))
            subtitle = "Provincias seleccionadas en dorado" if self.selected else "Provincias ordenadas de mayor a menor"
            figure = charts.province_ranking(self.national, indicator, highlight=self.selected, share_label="del total nacional",
                                             height=charts.execution_height(rows, 30))
        else:
            table = self.territories(level, [indicator.key])
            top = table.head(TOP)
            subtitle = phrase(level, len(top), len(table), self._where())
            total = float(pd.to_numeric(table[indicator.key], errors="coerce").sum())
            figure = charts.ranked_bars(list(top.etiqueta), list(top[indicator.key]), indicator, hover=list(top.detalle),
                                        share_total=total, share_label="de la selección" if self.provinces else "del total nacional",
                                        height=charts.execution_height(len(top), 30))
        with head:
            ui.chart_title(f"{indicator.label} por {LEVEL_LABELS[level].lower()}", subtitle)
        show_chart(figure, "territory_ranking")

    def _execution_card(self, wide: bool = False) -> None:
        level, head = self._card_head("lvl_execution")
        if level == "provincia":
            rows = aggregate(self.national, ["provincia_codigo", "provincia"])
            rows = rows.loc[rows.provincia_codigo.ne(geo.NO_POLYGON)].sort_values("presupuesto_codificado", ascending=False)
            highlight = {self.province_names[c] for c in self.selected if c in self.province_names}
            figure = charts.execution_bullets(rows, "provincia", highlight=highlight, per=30,
                                              reference=self.national_stats["porcentaje_ejecucion"], reference_label="Nacional")
            subtitle = "Devengado sobre codificado · la línea dorada marca el total nacional"
            if highlight:
                subtitle += " · selección en dorado"
        else:
            table = self.territories(level, ["presupuesto_codificado", "presupuesto_ejecutado"])
            top = table.head(TOP)
            reference_label = "Nacional" if not self.provinces else (self.territory_label if len(self.provinces) == 1 else "Selección")
            figure = charts.execution_bullets(top, "etiqueta", hover_label="detalle", per=30, reference=self.stats["porcentaje_ejecucion"],
                                              reference_label=reference_label)
            subtitle = f"{phrase(level, len(top), len(table), self._where())} por presupuesto codificado · la línea dorada marca el total"
        with head:
            ui.chart_title(f"Ejecución presupuestaria por {LEVEL_LABELS[level].lower()}", subtitle)
        show_chart(figure, "territory_execution")

    def _matrix_card(self, wide: bool = False) -> None:
        module, indicator = self.module, self.indicator
        level, head = self._card_head("lvl_matrix")
        if level == "provincia":
            figure = charts.composition_matrix(self.national, indicator, self.short_programs, highlight=self.selected,
                                               show_values=wide)
            subtitle = f"Participación de cada {module.item} en la provincia"
        else:
            table = self.territories(level, [indicator.key])
            top = table.head(TOP)
            frame = territory.level_programs(self.parish_filtered, level, indicator.key, top)
            figure = charts.composition_matrix(frame, indicator, self.short_programs, rows=("fila_codigo", "fila"),
                                               row_word="el cantón" if level == "canton" else "la parroquia", show_values=wide)
            where = phrase(level, len(top), len(table), self._where())
            subtitle = f"Participación de cada {module.item} en {where[:1].lower()}{where[1:]}"
        with head:
            ui.chart_title(f"Distribución por {module.item}", subtitle)
        show_wide_chart(figure, "territory_matrix")

    def _levels(self) -> dict[str, str]:
        item = self.module.item
        levels = {f"Por {item}": "programa", "Por provincia": "provincia"}
        if self.has_parishes:
            levels.update({"Por cantón": "canton", "Por parroquia": "parroquia"})
        levels[f"Por provincia y {item}"] = "provincia_programa"
        if len(self.monthly) >= 2:
            levels["Por mes"] = "mes"
        return levels

    def _territorial_money(self) -> bool:
        """Whether the rows of territories carry a budget (the latest cut and the annual references)."""
        return self.budget_mode in ("territorial", "reference")

    def month_table(self) -> tuple[pd.DataFrame, dict, list[tuple]]:
        """Each month of the year for the selection: people, change, units and the national accrued budget."""
        people = self.people
        frame = self.monthly.copy()
        frame["mes_nombre"] = [f"{m} {self.period['year']}" for m in frame.mes]
        columns = {"mes_nombre": ("Mes", "text", 150), "usuarios": (people.label, "int", None, None, people.label),
                   "variacion": ("Variación mensual", "int", None, None, "Variación")}
        layout = [("Mes", "mes_nombre", "text", 18.0), (people.label, "usuarios", "int", 16.0), ("Variación mensual", "variacion", "int", 16.0)]
        for extra in self.module.extra:
            columns[extra.key] = (extra.label, "int", 150, None, extra.compact.split()[0])
            layout.append((extra.label, extra.key, "int", 14.0))
        if "porcentaje_ejecucion" in frame and frame.porcentaje_ejecucion.notna().any():
            columns.update({"devengado_mes": ("Devengado del mes (USD)", "money", None, None, "Devengado"),
                            "devengado_acumulado": ("Devengado acumulado (USD)", "money", None, None, "Acumulado"),
                            "porcentaje_ejecucion": ("Ejecución acumulada", "pct", None, None, "Ejecución")})
            layout += [("Devengado del mes (USD)", "devengado_mes", "usd", 20.0), ("Devengado acumulado (USD)", "devengado_acumulado", "usd", 21.0),
                       ("Ejecución acumulada", "porcentaje_ejecucion", "pct", 14.0)]
        return frame, columns, layout

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        """Table of a level: rows, on-screen columns and the Excel layout."""
        if level == "mes":
            return self.month_table()
        module, money, people = self.module, self.money, self.people
        extras = [extra for extra in module.extra]
        territorial_money = self._territorial_money()
        if level in ("canton", "parroquia"):
            keys = ["usuarios", *[e.key for e in extras], "presupuesto_ejecutado", "presupuesto_codificado"]
            frame = (territory.canton_table(self.parish_filtered, keys) if level == "canton"
                     else territory.parish_table(self.parish_filtered, keys))
            total = pd.to_numeric(frame.usuarios, errors="coerce").sum()
            frame["participacion"] = pd.to_numeric(frame.usuarios, errors="coerce") / total * 100 if total else 0.0
            coded = pd.to_numeric(frame.presupuesto_codificado, errors="coerce")
            frame["porcentaje_ejecucion"] = pd.to_numeric(frame.presupuesto_ejecutado, errors="coerce") / coded.where(coded > 0) * 100
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
            if self.executed:
                columns["presupuesto_ejecutado"] = (f"{money['fiscal'].label} (USD)", "money")
                columns["presupuesto_codificado"] = (f"{money['coded'].label} (USD)", "money")
                columns["porcentaje_ejecucion"] = ("Ejecución (%)", "pct")
                layout += [(f"{money['fiscal'].label} (USD)", "presupuesto_ejecutado", "usd", 20.0),
                           (f"{money['coded'].label} (USD)", "presupuesto_codificado", "usd", 19.0),
                           ("Ejecución", "porcentaje_ejecucion", "pct", 12.0)]
            return frame.sort_values("usuarios", ascending=False), columns, layout
        groups = {"programa": ["programa"], "provincia": ["provincia"], "provincia_programa": ["provincia", "programa"]}[level]
        frame = aggregate(self.filtered, groups)
        if level == "programa" and self.budget_mode == "national" and self.budget_shown:
            # The national budget of each program joins its coverage (it has no territorial detail).
            money_rows = self.program_money.set_index("programa")
            for column in ["presupuesto_ejecutado", "presupuesto_codificado", "porcentaje_ejecucion", "monto_fiscal", "monto_anterior", "monto_gobierno"]:
                frame[column] = frame.programa.map(money_rows[column]) if column in money_rows else float("nan")
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
        with_money = territorial_money or (level == "programa" and self.budget_mode == "national" and self.budget_shown)
        if with_money:
            columns[money["fiscal"].key] = (f"{money['fiscal'].label} (USD)", "money")
            layout.append((f"{money['fiscal'].label} (USD)", money["fiscal"].key, "usd", 19.0))
            if self.budget_mode in ("territorial", "national"):
                columns["presupuesto_codificado"] = (f"{money['coded'].label} (USD)", "money")
                columns["porcentaje_ejecucion"] = ("Ejecución (%)", "pct")
                layout += [(f"{money['coded'].label} (USD)", "presupuesto_codificado", "usd", 19.0),
                           ("Ejecución", "porcentaje_ejecucion", "pct", 12.0)]
            columns[money["previous"].key] = (f"{money['previous'].compact} (USD)", "money")
            columns[money["government"].key] = (f"{money['government'].compact} (USD)", "money")
            layout += [(f"{money['previous'].label} (USD)", money["previous"].key, "usd", 21.0),
                       (f"{money['government'].label} (USD)", money["government"].key, "usd", 21.0)]
        columns = {k: v for k, v in columns.items() if k in frame}
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
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="detail_table",
                          bar="participacion" if "participacion" in columns else None)
            subtitle = f"{self.period['label']} · {self.module.label} · {self.territory_label} · {name.lower()}"
            download_table(frame, layout, title="Cuadro de resultados", subtitle=subtitle, period_label=self.period["label"],
                           file_name=f"MTDH_cuadro_{self.id}_{self.period['id']}.xlsx", key="detail_xlsx",
                           share_fields=("participacion", "porcentaje_ejecucion"))

    # --------------------------------------------------------------------------------------------- reports
    def report_options(self) -> None:
        """Territorial level of the documents: one level or everything (cuts without parishes keep the provinces)."""
        options = list(REPORT_LEVELS)
        if not self.has_parishes:
            st.session_state["report_level"] = "provincia"
        elif st.session_state.get("report_level") not in options:
            st.session_state["report_level"] = "todo"
        chosen = st.segmented_control("Nivel territorial", options, format_func=REPORT_LEVELS.get, key="report_level",
                                      required=True, disabled=not self.has_parishes, width="stretch")
        self.report_level = chosen if chosen in options and self.has_parishes else "provincia"

    def _report_word(self) -> str:
        """«provincias, cantones y parroquias» · «cantones»."""
        plurals = [LEVEL_PLURALS[level].lower() for level in report_levels(self.report_level)]
        return plurals[0] if len(plurals) == 1 else ", ".join(plurals[:-1]) + " y " + plurals[-1]

    def scope_items(self) -> list[tuple[str, str]]:
        return [("Periodo", self.period["label"]), ("Ámbito", self.module.label), ("Territorio", self.territory_label),
                (self.module.items.capitalize(), self.programs_label), ("Nivel territorial", REPORT_LEVELS[self.report_level])]

    def products_notes(self) -> dict[str, str]:
        item, word = self.module.item, self._report_word()
        slides = 3 + len(report_levels(self.report_level)) + (1 if self.executed else 0) - 1
        return {
            "resumen": f"Dos páginas en PDF: cifras clave, mapa, resultados por {item} y aspectos destacados; detalle de {word}.",
            "presentacion": f"{slides} diapositivas editables en PowerPoint: cifras clave, resultados de {word}"
                            f"{', ejecución presupuestaria' if self.executed else ''} y resultados por {item}.",
            "datos": f"Libro de Excel con resumen, resultados por {item}, {word}, detalle con filtros y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        sheets = ["Resumen", self.module.items.capitalize()]
        sheets += [LEVEL_PLURALS[level] for level in report_levels(self.report_level)]
        return sheets + ["Detalle", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        module, people = self.module, self.people
        levels = report_levels(self.report_level)
        if kind == "datos":
            items = [("grid", "Resumen", "Cifras clave, mapa y aspectos destacados"),
                     ("chart", module.items.capitalize(), f"{people.label}, participación, presupuesto y ejecución por {module.item}")]
            for level in levels:
                items.append((LEVEL_ICONS[level], LEVEL_PLURALS[level],
                              f"Mapa y cada {LEVEL_LABELS[level].lower()} con su cobertura, presupuesto y ejecución"))
            return items + [("table", "Detalle", f"Cada {module.item} en cada {LEVEL_LABELS[levels[-1]].lower()}, con filtros y totales"),
                            ("shield", "Ficha técnica", "Periodo, ámbito, territorio e indicadores")]
        if kind == "presentacion":
            items = [("grid", "Cifras clave", "Portada con los indicadores principales")]
            items += [(LEVEL_ICONS[level], f"Resultados por {LEVEL_LABELS[level].lower()}", "Mapa y territorios con mayor cobertura")
                      for level in levels]
            if self.executed:
                items.append(("target", "Ejecución presupuestaria", f"Por {module.item} y por territorio"))
            return items + [("chart", f"Resultados por {module.item}", "Gráfico editable y aspectos destacados")]
        return [("grid", "Cifras clave", "Indicadores principales del periodo"),
                ("map", "Territorio", f"Mapa y principales {self._report_word()}"),
                ("chart", f"Resultados por {module.item}", f"{people.label} por {module.item} y aspectos destacados"),
                ("layers", "Detalle territorial", "Alcance, ranking, ejecución y distribución por territorio")]

    def slide_titles(self) -> tuple[str, str]:
        level = report_levels(self.report_level)[0]
        return f"Resultados por {LEVEL_LABELS[level].lower()}", f"Resultados por {self.module.item}"

    def preview_visual(self) -> str:
        level = report_levels(self.report_level)[-1] if self.has_parishes else "provincia"
        svg, *_rest = self.map_svg(night=False, width=300, indicator=self.people, level=level)
        return svg

    def digest(self) -> str:
        return fingerprint(self.filtered, self.parish_filtered, self.report_level)

    def report_budget(self) -> dict:
        """The budget of the cut as the dashboard shows it, for the documents."""
        programs = {}
        for row in self.program_money.itertuples():
            def value(column):
                item = getattr(row, column, None)
                return None if item is None or pd.isna(item) else float(item)
            programs[str(row.programa_id)] = {"fiscal": value("presupuesto_ejecutado"), "coded": value("presupuesto_codificado"),
                                              "execution": value("porcentaje_ejecucion"), "previous": value("monto_anterior"),
                                              "government": value("monto_gobierno"), "month": value("devengado_mes")}
        return {"mode": self.budget_mode, "shown": self.budget_shown, "programs": programs, "totals": self.budget,
                "span": self.month_span()}

    def report_monthly(self) -> dict | None:
        """The selection month by month: people, change, units, national budget and the change of each program."""
        monthly = self.monthly
        if len(monthly) < 2:
            return None
        names = {p["id"]: p["label"].split()[0].lower() for p in self._catalog if p.get("month")}
        first, end = self.change_window()

        def number_or_none(value):
            return None if value is None or pd.isna(value) else float(value)

        months = [{"id": r.periodo_id, "label": r.mes, "short": r.corto, "month": int(r.periodo_mes),
                   "people": number_or_none(r.usuarios), "units": number_or_none(r.unidades), "change": number_or_none(r.variacion),
                   "accrued_month": number_or_none(getattr(r, "devengado_mes", None)),
                   "accrued": number_or_none(getattr(r, "devengado_acumulado", None)),
                   "execution": number_or_none(getattr(r, "porcentaje_ejecucion", None)), "selected": r.periodo_id == self.period["id"]}
                  for r in monthly.itertuples()]
        changes = [{"program": r.programa, "short": self.short_programs.get(r.programa, r.programa), "first": r.inicio, "last": r.fin,
                    "change": r.cambio} for r in self.program_changes().itertuples()]
        matrix = self.program_months().pivot_table(index="programa", columns="periodo_id", values="usuarios", aggfunc="sum")
        programs = [{"program": name, "short": self.short_programs.get(name, name),
                     "values": [number_or_none(matrix.loc[name].get(m["id"])) for m in months]} for name in matrix.index]
        programs.sort(key=lambda r: -(r["values"][-1] or 0))
        return {"months": months, "changes": changes, "programs": programs, "window": (names[first], names[end]),
                "change": self.month_change(), "previous": self.previous_month(), "year": self.period["year"],
                "budget": bool("porcentaje_ejecucion" in monthly and monthly.porcentaje_ejecucion.notna().any())}

    def report_context(self, title: str) -> dict:
        from src.reports import build_report_context
        from src import corte
        return build_report_context(self.filtered, national=self.national, title=title, period_label=self.period["label"],
                                    territory_label=self.territory_label, programs_label=self.programs_label,
                                    selected_codes=self.selected, parishes=self.parish_filtered,
                                    parishes_national=self.parish_national, level=self.report_level, budget=self.report_budget(),
                                    monthly=self.report_monthly(), update=corte.stamp(self.id, self.period))
