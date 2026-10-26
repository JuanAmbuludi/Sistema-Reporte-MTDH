"""Contingencies and compensation mechanisms: people of each program in the month, the year month by month, where the
bonuses were enabled and the budget of 2026.

Each program keeps the criterion of its source (beneficiaries, people enabled, people with an accredited payment), so
people are compared program by program and never added across months.  Bonuses enabled and amounts add up over the
months of the year for the territorial reading.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, contingencias as source, geo, names as place_names, territory, theme, ui
from src.indicators import AREAS
from src.views.common import compact, download_table, fingerprint, show_chart

ORDER = list(source.PROGRAMS)
CONTINGENCY = ["ORFANDAD_VIOLENCIA", "CONTINGENCIAS", "ANTROPICOS"]
COMPENSATION = ["COMPENSACION_GASOLINA", "COMPENSACION_DIESEL", "MIGRANTES"]
MAP_PROGRAMS = {"CONTINGENCIAS": "Contingencias", "ANTROPICOS": "Eventos naturales y antrópicos"}
LEVELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}
REPORT_LEVELS = {**LEVELS, "todo": "Todo"}
MONTHS = source.MONTHS


@st.cache_data(show_spinner=False, max_entries=32)
def _svg(layer: str, values: dict, titles: dict, night: bool = True, width: int = 640) -> str:
    if night:
        return geo.svg_map(ui.map_fills(values), layer=layer, titles=titles, stroke=theme.MORADO_900, width=width)
    return geo.svg_map(ui.map_fills(values, theme.SEQUENTIAL[2:]), layer=layer, titles=titles, width=width, pad=6, stroke="#FFFFFF",
                       equator=None, locator=False, empty_fill="#F1EEF6", context_fill="#F1EEF6", border_color="rgba(81,47,141,.45)",
                       frame_color="rgba(81,47,141,.35)", label_color="rgba(81,47,141,.6)", css_class="ec-map mini")


def short_month(period_id: str) -> str:
    year, month = period_id.split("-")
    return f"{MONTHS[int(month) - 1][:3].capitalize()} {year[2:]}"


def long_month(period_id: str) -> str:
    year, month = period_id.split("-")
    return f"{MONTHS[int(month) - 1]} de {year}"


class ContingencyView:
    kind = "contingencias"
    id = "contingencias"

    def __init__(self, monthly: pd.DataFrame, places: pd.DataFrame, catalog: list[dict]):
        self.data, self.places, self._catalog = monthly, places, catalog
        self.label = AREAS["contingencias"]["label"]
        self.report_level = "todo"

    def catalog(self) -> list[dict]:
        return self._catalog

    # ------------------------------------------------------------------------------------------- consultation
    def select(self, period: dict, programs=()) -> None:
        self.period, self.programs = period, list(programs)

    def controls(self, period: dict) -> None:
        self.period = period
        available = [p for p in ORDER if p in set(self.data.programa_id)]
        if "cont_programs" in st.session_state:
            st.session_state["cont_programs"] = [p for p in st.session_state["cont_programs"] if p in available]
        self.programs = st.multiselect("Programa", available, format_func=lambda p: source.PROGRAMS[p]["label"],
                                       placeholder="Todos los programas", key="cont_programs")
        if self.programs:
            st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=self._clear, type="tertiary", key="reset_cont")

    @staticmethod
    def _clear() -> None:
        st.session_state["cont_programs"] = []

    empty_message = "Los programas elegidos no registran información en este mes. Ajuste el mes o los programas."

    def chosen(self, frame: pd.DataFrame) -> pd.DataFrame:
        return frame.loc[frame.programa_id.isin(self.programs)] if self.programs else frame

    def prepare(self) -> bool:
        period = self.period
        data = self.chosen(self.data)
        self.month_rows = data.loc[data.periodo_id.eq(period["id"])]
        if self.month_rows[["personas", "devengado_mes", "monto"]].notna().sum().sum() == 0:
            return False
        self.history = data.loc[data.periodo_id.le(period["id"])]
        self.year_rows = source.year_to_date(data, period["id"])
        places = self.chosen(self.places) if not self.places.empty else self.places
        self.year_places = source.year_to_date(places, period["id"]) if not places.empty else places
        self.programs_label = (source.PROGRAMS[self.programs[0]]["label"] if len(self.programs) == 1 else
                               f"{len(self.programs)} programas" if self.programs else "Todos los programas")
        self.territory_label = "Nacional"
        self.context_label = f"{period['label']} · {self.programs_label}"
        self.span = (f"enero a {MONTHS[period['month'] - 1]} de {period['year']}" if period["month"] > 1 else f"enero de {period['year']}")
        budget = self.year_rows.loc[self.year_rows.periodo_id.eq(period["id"])]
        self.has_budget = bool(budget.devengado_acumulado.notna().any())
        self.map_program = next((p for p in MAP_PROGRAMS if not self.programs or p in self.programs), None)
        self.map_level = "provincia"
        return True

    # ---------------------------------------------------------------------------------------------- figures
    def program_rows(self) -> pd.DataFrame:
        """Programs of the month in reading order, with their criterion and the budget of the year."""
        rows = self.month_rows.set_index("programa_id")
        out = []
        for pid in ORDER:
            if pid not in rows.index:
                continue
            row = rows.loc[pid]
            meta = source.PROGRAMS[pid]
            accrued, approved = row.devengado_acumulado, row.presupuesto_aprobado
            out.append({"programa_id": pid, "programa": meta["label"], "nombre_oficial": meta["full"], "criterio": source.CRITERIA[meta["criterion"]],
                        "personas": row.personas, "monto": row.monto, "cobrados": row.cobrados, "monto_cobrado": row.monto_cobrado,
                        "devengado_mes": row.devengado_mes, "presupuesto_ejecutado": accrued, "presupuesto_codificado": approved,
                        "porcentaje_ejecucion": accrued / approved * 100 if pd.notna(accrued) and pd.notna(approved) and approved else None,
                        "grupo": "Contingencias" if meta["group"] == "contingencia" else "Compensaciones"})
        return pd.DataFrame(out)

    def budget_totals(self) -> dict:
        rows = self.program_rows()
        if rows.empty or not self.has_budget:
            return {}
        accrued = pd.to_numeric(rows.presupuesto_ejecutado, errors="coerce").sum()
        approved = pd.to_numeric(rows.presupuesto_codificado, errors="coerce").sum()
        month = pd.to_numeric(rows.devengado_mes, errors="coerce").sum()
        return {"accrued": float(accrued), "approved": float(approved), "month": float(month),
                "execution": float(accrued / approved * 100) if approved else None}

    def previous(self, pid: str) -> tuple[float | None, str]:
        """People of a program in the previous month (when it was recorded) and the name of that month."""
        year, month = self.period["year"], self.period["month"]
        previous_id = f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"
        row = self.data.loc[self.data.periodo_id.eq(previous_id) & self.data.programa_id.eq(pid)]
        value = row.personas.iloc[0] if len(row) else None
        return (None if value is None or pd.isna(value) else float(value)), MONTHS[(month - 2) % 12]

    def kpi_cards(self) -> list[dict]:
        rows = self.program_rows().set_index("programa_id") if not self.program_rows().empty else pd.DataFrame()
        cards = []
        for pid in CONTINGENCY:
            if pid not in rows.index or pd.isna(rows.loc[pid, "personas"]):
                continue
            row, meta = rows.loc[pid], source.PROGRAMS[pid]
            note = ""
            before, month_name = self.previous(pid)
            if pd.notna(row.monto) and row.monto:
                note = f"USD {ui.number(row.monto)} {'habilitados' if meta['criterion'] == 'habilitados' else 'acreditados'}"
            elif before is not None:
                change = row.personas - before
                note = f"{ui.number(abs(change))} {'más' if change > 0 else 'menos'} que en {month_name}" if change else f"Igual que en {month_name}"
            cards.append({"label": meta["label"], "value": row.personas, "icon": meta["icon"], "tone": meta["tone"],
                          "note": note or source.CRITERIA[meta["criterion"]]})
        compensation = [pid for pid in COMPENSATION if pid in rows.index and pd.notna(rows.loc[pid, "personas"])]
        if compensation:
            people = float(sum(rows.loc[pid, "personas"] for pid in compensation))
            amount = float(sum(rows.loc[pid, "monto"] or 0 for pid in compensation if pd.notna(rows.loc[pid, "monto"])))
            label = source.PROGRAMS[compensation[0]]["label"] if len(compensation) == 1 else "Compensaciones acreditadas"
            cards.append({"label": label, "value": people, "icon": "fuel", "tone": "oro", "note": f"USD {ui.millions(amount)} millones acreditados"})
        totals = self.budget_totals()
        if totals:
            cards.append({"label": f"Presupuesto devengado {self.period['year']}", "value": totals["accrued"] / 1e6, "decimals": 1,
                          "prefix": "USD", "suffix": "millones", "icon": "banknote", "tone": "lila", "bar": totals["execution"],
                          "bar_label": f"{ui.pct(totals['execution'])} del aprobado (USD {ui.millions(totals['approved'])} M)"})
        return cards[:5]

    # ------------------------------------------------------------------------------------------------ band
    def hero_copy(self) -> tuple[str, str, str]:
        period = self.period
        chip = f"Corte {period['label'].lower()}"
        headline = self.label if not self.programs else (self.programs_label if len(self.programs) == 1 else self.label)
        return chip, headline, AREAS["contingencias"]["description"]

    def update_stamp(self) -> dict:
        from src import corte
        return corte.stamp(self.id, self.period)

    def place_values(self, program: str, level: str, key: str = "registros") -> pd.DataFrame:
        """Bonuses enabled in the year by territory for one program (rows of the level, largest first)."""
        rows = self.year_places
        if rows.empty:
            return pd.DataFrame()
        rows = rows.loc[rows.programa_id.eq(program) & rows.criterio.eq("habilitado")]
        code, name = {"provincia": ("provincia_codigo", "provincia_nombre"), "canton": ("canton_codigo", "canton_nombre"),
                      "parroquia": ("parroquia_codigo", "parroquia_nombre")}[level]
        rows = rows.loc[rows[code].notna()]
        keys = [code, name, "provincia_codigo", "provincia_nombre"] if level != "provincia" else [code, name]
        if level == "parroquia":
            keys.append("canton_nombre")
        grouped = rows.groupby(keys, as_index=False, dropna=False)[["registros", "beneficiarios", "monto"]].sum(min_count=1)
        grouped = grouped.rename(columns={code: "codigo", name: "nombre"})
        if level == "provincia":
            grouped["provincia_nombre"] = grouped.nombre
        grouped["nombre"] = grouped.nombre.map(lambda n: place_names.place(n) if level != "provincia" else n)
        if level == "parroquia":
            grouped["canton_nombre"] = grouped.canton_nombre.map(place_names.place)
            grouped["detalle"] = [f"{n} · {territory.short_canton(c)}, {p}" for n, c, p in zip(grouped.nombre, grouped.canton_nombre,
                                                                                               grouped.provincia_nombre)]
        elif level == "canton":
            grouped["detalle"] = [f"{n} · {p}" for n, p in zip(grouped.nombre, grouped.provincia_nombre)]
        else:
            grouped["detalle"] = grouped.nombre
        grouped["etiqueta"] = territory.unique_labels([territory.short_canton(n) for n in grouped.nombre], list(grouped.provincia_nombre))
        total = grouped.registros.sum()
        grouped["participacion"] = grouped.registros / total * 100 if total else 0.0
        return grouped.sort_values(key, ascending=False).reset_index(drop=True)

    def map_svg(self, night: bool = True, width: int = 640, program: str | None = None, level: str | None = None) -> tuple[str, str]:
        program = program or self.map_program
        level = level or self.map_level
        if program == "ANTROPICOS" and level == "parroquia":
            level = "canton"
        rows = self.place_values(program, level) if program else pd.DataFrame()
        values, titles = {}, {}
        if not rows.empty:
            if level == "parroquia":
                frame = rows.rename(columns={"codigo": "parroquia_codigo", "nombre": "parroquia", "canton_nombre": "canton"})
                frame["provincia_codigo"] = frame.parroquia_codigo.astype(str).str[:2]
                polygon_values, members = territory.polygon_values(frame.assign(registros=frame.registros.astype(float)), "registros")
                values = polygon_values
                features = geo.features("parroquia")
                titles = {code: f"{features.get(code, {}).get('name', code)}\n{ui.number(v)} bonos habilitados" for code, v in values.items()}
            else:
                values = {str(c): float(v) for c, v in zip(rows.codigo, rows.registros) if pd.notna(v)}
                titles = {str(c): f"{d}: {ui.number(v)} bonos habilitados" for c, d, v in zip(rows.codigo, rows.detalle, rows.registros)}
        svg = _svg(level, values, titles, night, width)
        label = f"Bonos habilitados de {self.span} por {LEVELS[level].lower()}"
        return svg, label

    def hero_visual(self) -> None:
        if not self.map_program:
            # Programs without territorial detail: their people month by month in the year.
            months = self.year_rows.groupby("periodo_id").personas.sum(min_count=1).dropna()
            labels = [MONTHS[int(p[5:]) - 1][:3].capitalize() for p in months.index]
            svg = ui.svg_columns([float(v) for v in months], labels, titles=[f"{long_month(p).capitalize()}: {ui.number(v)}" for p, v in months.items()],
                                 value_text=lambda v: charts.compact_number(v))
            ui.hero_series(svg, f"Personas por mes · {self.programs_label}")
            return
        options = [p for p in MAP_PROGRAMS if not self.programs or p in self.programs]
        if st.session_state.get("cont_map_program") not in options:
            st.session_state["cont_map_program"] = options[0]
        self.map_program = st.segmented_control("Programa en el mapa", options, format_func=MAP_PROGRAMS.get, key="cont_map_program",
                                                required=True, width="stretch")
        levels = ["provincia", "canton", "parroquia"]
        if st.session_state.get("cont_map_level") not in levels:
            st.session_state["cont_map_level"] = "provincia"
        if self.map_program == "ANTROPICOS" and st.session_state.get("cont_map_level") == "parroquia":
            st.session_state["cont_map_level"] = "canton"
        self.map_level = st.segmented_control("Nivel territorial", levels, format_func=LEVELS.get, key="cont_map_level", required=True,
                                              width="stretch")
        svg, label = self.map_svg()
        ui.hero_map(svg, label)

    # ------------------------------------------------------------------------------------------- dashboard
    def dashboard(self) -> None:
        period = self.period
        rows = self.program_rows()
        ui.section_heading("Resultados por programa", f"{self.context_label} · cada programa con el criterio de su fuente", "chart")
        names = dict(zip(rows.programa, rows.nombre_oficial))
        people = rows.loc[rows.personas.notna()]
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_cont_people"):
            ui.chart_title("Personas por programa", "Beneficiarios, personas habilitadas o con pago acreditado, según el programa")
            frame = people.assign(usuarios=people.personas)
            show_chart(charts.ranked_bars(list(frame.programa), list(frame.usuarios), _count("personas"),
                                          hover=[f"{p} · {c.lower()}" for p, c in zip(frame.programa, frame.criterio)],
                                          height=charts.execution_height(len(frame), 44)), "cont_people")
        amounts = rows.loc[rows.monto.notna() & rows.monto.gt(0)]
        with right, st.container(border=True, key="card_cont_amount"):
            ui.chart_title("Monto del mes por programa", "Millones de USD habilitados o acreditados en el mes")
            show_chart(charts.ranked_bars(list(amounts.programa), list(amounts.monto), _money("monto"),
                                          hover=list(amounts.programa), height=charts.execution_height(max(1, len(amounts)), 44)), "cont_amount")
        if self.has_budget:
            budget = rows.loc[pd.to_numeric(rows.presupuesto_codificado, errors="coerce").gt(0)].copy()
            budget["nombre"] = budget.programa
            totals = self.budget_totals()
            monthly = self.year_rows.groupby("periodo_id", as_index=False).devengado_mes.sum(min_count=1)
            monthly = monthly.loc[monthly.devengado_mes.notna()]
            left, right = st.columns(2, gap="medium")
            with left, st.container(border=True, key="card_cont_execution"):
                ui.chart_title(f"Ejecución presupuestaria {period['year']} por programa",
                               f"Devengado de {self.span} sobre el presupuesto aprobado · la línea dorada marca el total")
                show_chart(charts.execution_bullets(budget.sort_values("presupuesto_codificado", ascending=False), "nombre",
                                                    hover_label="nombre_oficial", reference=totals.get("execution")), "cont_execution")
            with right, st.container(border=True, key="card_cont_accrued"):
                ui.chart_title("Presupuesto devengado por mes", "Millones de USD · programas de la selección")
                labels = [MONTHS[int(p[5:]) - 1][:3].capitalize() for p in monthly.periodo_id]
                selected = list(monthly.periodo_id).index(period["id"]) if period["id"] in set(monthly.periodo_id) else None
                show_chart(charts.month_columns(labels, list(monthly.devengado_mes), selected=selected, money=True,
                                                full=[long_month(p) for p in monthly.periodo_id]), "cont_accrued")
        self._evolution()
        self._territory()
        self._table()

    def _series(self, pid: str, column: str = "personas") -> tuple[list[str], list, list[str]]:
        rows = self.history.loc[self.history.programa_id.eq(pid)]
        rows = rows.loc[rows[column].notna() | rows.personas.notna()]
        if rows.empty:
            return [], [], []
        start, end = rows.periodo_id.min(), self.period["id"]
        ids = [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]
        values = rows.set_index("periodo_id")[column].reindex(ids)
        return ids, [None if pd.isna(v) else float(v) for v in values], [long_month(p).capitalize() for p in ids]

    def _evolution(self) -> None:
        wanted = [p for p in ORDER if (not self.programs or p in self.programs) and p in set(self.history.programa_id)]
        cards = []
        for pid in wanted:
            ids, values, full = self._series(pid)
            if len([v for v in values if v is not None]) < 2:
                continue
            meta = source.PROGRAMS[pid]
            selected = ids.index(self.period["id"]) if self.period["id"] in ids else None
            labels = [short_month(p) for p in ids]
            if pid in ("CONTINGENCIAS", "ANTROPICOS"):
                _ids, collected, _full = self._series(pid, "cobrados")
                series = [(meta["people"], values, theme.SERIE_BONOS)]
                if any(v for v in collected if v):
                    series.append(("Personas que cobraron", collected, theme.FUCSIA))
                build = (lambda lb=labels, sr=series, sl=selected, fl=full: charts.history_line(lb, sr, selected=sl, full=fl))
                subtitle = "Personas habilitadas por fecha de habilitación y personas que cobraron por fecha de cobro"
            else:
                build = (lambda lb=labels, v=values, sl=selected, fl=full, u=meta["unit"]:
                         charts.history_line(lb, [(source.CRITERIA[source.PROGRAMS[pid]["criterion"]], v, theme.SERIE_BONOS)],
                                             selected=sl, full=fl, unit=u))
                subtitle = f"{source.CRITERIA[meta['criterion']]} · {full[0].lower()} a {full[-1].lower()}"
            cards.append((pid, meta["label"], subtitle, build))
        if not cards:
            return
        ui.section_heading("Evolución mensual", f"Cada programa desde su primer registro hasta {long_month(self.period['id'])}", "trending-up")
        for start in range(0, len(cards), 2):
            pair = cards[start:start + 2]
            columns = st.columns(2, gap="medium") if len(pair) == 2 else [st.container()]
            for column, (pid, title, subtitle, build) in zip(columns, pair):
                with column, st.container(border=True, key=f"card_cont_series_{pid.lower()}"):
                    ui.chart_title(title, subtitle)
                    show_chart(build(), f"cont_series_{pid.lower()}")

    def _territory(self) -> None:
        if self.year_places.empty or not self.map_program:
            ui.geoportal_card("contingencias", "Visor geográfico del Ministerio con las unidades de atención y las zonas de amenaza.")
            return
        ui.section_heading("Resultados por territorio", f"Bonos habilitados de {self.span} · {MAP_PROGRAMS[self.map_program]}", "map")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_cont_rank"):
            head, toggle = st.columns([1.55, 1], gap="small", vertical_alignment="center")
            options = ["provincia", "canton"] + (["parroquia"] if self.map_program == "CONTINGENCIAS" else [])
            if st.session_state.get("lvl_cont_rank") not in options:
                st.session_state["lvl_cont_rank"] = "provincia"
            with toggle:
                level = st.segmented_control("Nivel territorial", options, format_func=LEVELS.get, key="lvl_cont_rank", required=True,
                                             label_visibility="collapsed", width="stretch" if compact() else "content")
            rows = self.place_values(self.map_program, level).head(25)
            with head:
                ui.chart_title(f"Bonos habilitados por {LEVELS[level].lower()}", f"{MAP_PROGRAMS[self.map_program]} · {self.span}")
            total = float(self.place_values(self.map_program, level).registros.sum()) if not rows.empty else 0.0
            show_chart(charts.ranked_bars(list(rows.etiqueta), list(rows.registros), _count("bonos"), hover=list(rows.detalle),
                                          share_total=total, share_label="del total", height=charts.execution_height(len(rows), 30)),
                       "cont_rank")
        with right:
            types = self.type_rows()
            with st.container(border=True, key="card_cont_types"):
                ui.chart_title("Bonos habilitados por tipo", f"{self.span[:1].upper()}{self.span[1:]} · contingencias y eventos de la selección")
                show_chart(charts.ranked_bars(list(types.tipo_nombre), list(types.registros), _count("bonos"),
                                              share_total=float(types.registros.sum()), share_label="del total",
                                              height=charts.execution_height(len(types), 36)), "cont_types")
            amounts = types.sort_values("monto", ascending=False)
            with st.container(border=True, key="card_cont_type_amount"):
                ui.chart_title("Monto habilitado por tipo", f"Dólares de {self.span} · contingencias y eventos de la selección")
                show_chart(charts.ranked_bars(list(amounts.tipo_nombre), list(amounts.monto), _money("monto"),
                                              share_total=float(amounts.monto.sum()), share_label="del monto",
                                              height=charts.execution_height(len(amounts), 36)), "cont_type_amount")
        ui.geoportal_card("contingencias", "Visor geográfico del Ministerio con las unidades de atención y las zonas de amenaza.")

    def type_rows(self) -> pd.DataFrame:
        rows = self.year_places
        if rows.empty:
            return pd.DataFrame(columns=["tipo_nombre", "registros", "beneficiarios", "monto"])
        rows = rows.loc[rows.criterio.eq("habilitado")]
        grouped = rows.groupby("tipo_nombre", as_index=False)[["registros", "beneficiarios", "monto"]].sum(min_count=1)
        total = grouped.registros.sum()
        grouped["participacion"] = grouped.registros / total * 100 if total else 0.0
        return grouped.sort_values("registros", ascending=False).reset_index(drop=True)

    # ---------------------------------------------------------------------------------------------- tables
    LEVELS_TABLE = {"Por programa": "programa", "Por mes": "mes", "Por provincia": "provincia", "Por cantón": "canton",
                    "Por tipo": "tipo"}

    def month_matrix(self) -> pd.DataFrame:
        rows = self.year_rows.pivot_table(index="periodo_id", columns="programa_id", values="personas", aggfunc="sum")
        rows = rows.reindex(columns=[p for p in ORDER if p in rows.columns])
        rows.columns = [source.PROGRAMS[p]["label"] for p in rows.columns]
        money = self.year_rows.groupby("periodo_id")[["monto", "devengado_mes"]].sum(min_count=1)
        out = rows.join(money).reset_index()
        out["mes"] = [long_month(p).capitalize() for p in out.periodo_id]
        return out

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        if level == "programa":
            frame = self.program_rows()
            columns = {"programa": ("Programa", "text", 230), "criterio": ("Criterio", "text", 260),
                       "personas": ("Personas", "int"), "monto": ("Monto del mes (USD)", "money", None, None, "Monto"),
                       "cobrados": ("Personas que cobraron", "int", None, None, "Cobraron")}
            layout = [("Programa", "programa", "text", 30.0), ("Criterio", "criterio", "text", 30.0), ("Personas", "personas", "int", 14.0),
                      ("Monto del mes (USD)", "monto", "usd", 18.0), ("Personas que cobraron", "cobrados", "int", 16.0)]
            if self.has_budget:
                columns.update({"devengado_mes": ("Devengado del mes (USD)", "money", None, None, "Devengado"),
                                "presupuesto_ejecutado": ("Devengado acumulado (USD)", "money", None, None, "Acumulado"),
                                "presupuesto_codificado": ("Presupuesto aprobado (USD)", "money", None, None, "Aprobado"),
                                "porcentaje_ejecucion": ("Ejecución", "pct")})
                layout += [("Devengado del mes (USD)", "devengado_mes", "usd", 18.0), ("Devengado acumulado (USD)", "presupuesto_ejecutado", "usd", 19.0),
                           ("Presupuesto aprobado (USD)", "presupuesto_codificado", "usd", 19.0), ("Ejecución", "porcentaje_ejecucion", "pct", 12.0)]
            return frame, columns, layout
        if level == "mes":
            frame = self.month_matrix()
            programs = [c for c in frame.columns if c not in ("periodo_id", "mes", "monto", "devengado_mes")]
            columns = {"mes": ("Mes", "text", 150)}
            layout = [("Mes", "mes", "text", 18.0)]
            for name in programs:
                columns[name] = (name, "int")
                layout.append((name, name, "int", 16.0))
            columns["monto"] = ("Monto habilitado o acreditado (USD)", "money", None, None, "Monto")
            layout.append(("Monto habilitado o acreditado (USD)", "monto", "usd", 20.0))
            if frame.devengado_mes.notna().any():
                columns["devengado_mes"] = ("Devengado del mes (USD)", "money", None, None, "Devengado")
                layout.append(("Devengado del mes (USD)", "devengado_mes", "usd", 19.0))
            return frame, columns, layout
        if level == "tipo":
            frame = self.type_rows()
            columns = {"tipo_nombre": ("Tipo", "text", 300), "registros": ("Bonos habilitados", "int"),
                       "participacion": ("Participación", "pct", None, None, "Peso"), "beneficiarios": ("Personas", "int"),
                       "monto": ("Monto habilitado (USD)", "money", None, None, "Monto")}
            layout = [("Tipo", "tipo_nombre", "text", 40.0), ("Bonos habilitados", "registros", "int", 16.0),
                      ("Participación", "participacion", "pct", 12.0), ("Personas", "beneficiarios", "int", 12.0),
                      ("Monto habilitado (USD)", "monto", "usd", 19.0)]
            return frame, columns, layout
        frames = []
        for pid in MAP_PROGRAMS:
            if self.programs and pid not in self.programs:
                continue
            part = self.place_values(pid, level)
            if not part.empty:
                frames.append(part.assign(programa=MAP_PROGRAMS[pid]))
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["programa", "detalle", "registros"])
        columns = {"programa": ("Programa", "text", 200), "detalle": (LEVELS[level], "text", 260), "registros": ("Bonos habilitados", "int"),
                   "participacion": ("Participación", "pct", None, None, "Peso"), "beneficiarios": ("Personas", "int"),
                   "monto": ("Monto habilitado (USD)", "money", None, None, "Monto")}
        layout = [("Programa", "programa", "text", 28.0), (LEVELS[level], "detalle", "text", 36.0), ("Bonos habilitados", "registros", "int", 16.0),
                  ("Participación", "participacion", "pct", 12.0), ("Personas", "beneficiarios", "int", 12.0),
                  ("Monto habilitado (USD)", "monto", "usd", 19.0)]
        return frame, columns, layout

    def _table(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        levels = self.LEVELS_TABLE
        if st.session_state.get("cont_detail_level") not in levels:
            st.session_state["cont_detail_level"] = next(iter(levels))
        name = st.segmented_control("Nivel de detalle", list(levels), key="cont_detail_level", required=True,
                                    width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(levels[name])
        with st.container(border=True, key="card_cont_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="cont_table",
                          bar="participacion" if "participacion" in columns else None)
            download_table(frame, layout, title="Contingencias y compensaciones", subtitle=f"{self.context_label} · {name.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_contingencias_{self.period['id']}.xlsx",
                           key="cont_xlsx", share_fields=("participacion", "porcentaje_ejecucion"))

    # --------------------------------------------------------------------------------------------- reports
    def report_levels(self) -> list[str]:
        """Levels of the documents: the events base reaches the canton, contingencies the parish."""
        return ["provincia", "canton"] + (["parroquia"] if self.map_program == "CONTINGENCIAS" else [])

    def report_options(self) -> None:
        """Territorial level of the documents: one level or everything."""
        if not self.map_program:
            self.report_level = "todo"
            return
        options = self.report_levels() + ["todo"]
        if st.session_state.get("report_level_cont") not in options:
            st.session_state["report_level_cont"] = "todo"
        chosen = st.segmented_control("Nivel territorial", options, format_func=REPORT_LEVELS.get, key="report_level_cont",
                                      required=True, width="stretch")
        self.report_level = chosen if chosen in options else "todo"

    def _level_word(self) -> str:
        """«provincias, cantones y parroquias» · «cantones»."""
        levels = self.report_levels() if self.report_level == "todo" else [self.report_level]
        plurals = [{"provincia": "provincias", "canton": "cantones", "parroquia": "parroquias"}[lvl] for lvl in levels]
        return plurals[0] if len(plurals) == 1 else ", ".join(plurals[:-1]) + " y " + plurals[-1]

    def scope_items(self) -> list[tuple[str, str]]:
        items = [("Periodo", self.period["label"]), ("Ámbito", self.label), ("Programas", self.programs_label)]
        if self.map_program:
            items.append(("Nivel territorial", REPORT_LEVELS.get(self.report_level, "Todo")))
        else:
            items.append(("Territorio", "Nacional"))
        return items

    def products_notes(self) -> dict[str, str]:
        word = self._level_word() if self.map_program else ""
        territory_pdf = f"bonos habilitados por {word}, " if word else ""
        return {
            "resumen": f"Dos páginas en PDF: cifras clave, mapa y {territory_pdf}personas por programa, evolución mensual, tipos de "
                       f"contingencia, ejecución presupuestaria y aspectos destacados.",
            "presentacion": "Cinco diapositivas editables en PowerPoint: cifras clave, resultados por programa, evolución mensual, "
                            f"territorio{f' ({word})' if word else ''} y presupuesto.",
            "datos": f"Libro de Excel con resumen, programas, serie mensual, {word + ', ' if word else ''}tipos de contingencia y ficha técnica.",
        }

    def sheets(self) -> list[str]:
        return ["Resumen", "Programas", "Serie mensual", "Territorio", "Tipos", "Ficha técnica"]

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        if kind == "datos":
            return [("grid", "Resumen", "Cifras clave, mapa y aspectos destacados"),
                    ("chart", "Programas", "Personas, montos y presupuesto de cada programa"),
                    ("trending-up", "Serie mensual", "Cada programa mes a mes"),
                    ("map", "Territorio", "Bonos habilitados por provincia y cantón"),
                    ("layers", "Tipos", "Bonos habilitados por tipo de contingencia"),
                    ("shield", "Ficha técnica", "Criterios, fuentes y definiciones")]
        if kind == "presentacion":
            return [("grid", "Cifras clave", "Portada con los indicadores principales"),
                    ("chart", "Resultados por programa", "Personas y montos del mes"),
                    ("trending-up", "Evolución mensual", "Orfandad, contingencias, eventos y compensaciones"),
                    ("map", "Territorio", "Mapa y provincias con más bonos habilitados"),
                    ("target", "Presupuesto", "Ejecución presupuestaria por programa")]
        return [("grid", "Cifras clave", "Personas de cada programa y presupuesto"),
                ("map", "Territorio", "Mapa de los bonos habilitados en el año"),
                ("trending-up", "Evolución mensual", "Cada programa mes a mes"),
                ("award", "Aspectos destacados", "Conclusiones para la toma de decisiones")]

    def slide_titles(self) -> tuple[str, str]:
        return "Resultados por programa", "Evolución mensual"

    def preview_visual(self) -> str:
        svg, _label = self.map_svg(night=False, width=300, program=self.map_program or "CONTINGENCIAS", level="provincia")
        return svg

    def digest(self) -> str:
        return fingerprint(self.month_rows, self.year_rows, self.period["id"], tuple(self.programs), self.map_program, self.report_level)

    def report_context(self, title: str) -> dict:
        from src.reports.areas import contingency_context
        return contingency_context(self, title=title)


def _count(unit: str):
    from src.indicators import Indicator
    return Indicator("valor", unit.capitalize(), "count", "chart", unit)


def _money(key: str):
    from src.indicators import Indicator
    return Indicator(key, "Monto", "money", "banknote")
