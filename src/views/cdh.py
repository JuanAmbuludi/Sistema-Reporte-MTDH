"""Crédito de Desarrollo Humano: credits disbursed each month of the year, their profile and the current portfolio."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import charts, theme, ui
from src.data import MONTHS
from src.indicators import Indicator
from src.views.area import PROCESSED, AreaView, manifest
from src.views.common import show_chart

CREDITS = Indicator("creditos", "Créditos", "count", "coins", "créditos")
AMOUNT = Indicator("monto", "Monto desembolsado", "money", "banknote")


class CreditView(AreaView):
    kind = id = "cdh"
    label = "Crédito de Desarrollo Humano"
    file_id = "credito_desarrollo_humano"
    category = ("bono", "Bono o pensión", "Todos los bonos")
    weight = "creditos"
    series_field, series_unit, series_title = "creditos", "créditos", "Créditos desembolsados por mes"
    LEVELS = {"Por provincia": "provincia", "Por cantón": "canton", "Por parroquia": "parroquia", "Por bono": "bono", "Por mes": "mes"}

    def __init__(self):
        path = PROCESSED / "cdh_territorio.parquet"
        self.territory = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["fuente", "periodo"])
        profile = PROCESSED / "cdh_perfil.parquet"
        self.profile = pd.read_parquet(profile) if profile.exists() else pd.DataFrame(columns=["fuente", "periodo"])
        self.rows_frame = self.territory.loc[self.territory.fuente.eq("desembolso")]
        self.portfolio_all = self.territory.loc[self.territory.fuente.eq("vigente")]

    def prepare(self) -> bool:
        p = self.period
        year = self.scoped(self.rows_frame.loc[self.rows_frame.periodo.str[:4].eq(str(p["year"])) & self.rows_frame.periodo.le(p["id"])])
        if year.empty:
            return False
        self.year_rows, self.month_rows = year, year.loc[year.periodo.eq(p["id"])]
        self.series = year.groupby("periodo", as_index=False)[["creditos", "monto"]].sum()
        profile = self.profile.loc[self.profile.fuente.eq("desembolso") & self.profile.periodo.str[:4].eq(str(p["year"]))
                                   & self.profile.periodo.le(p["id"])]
        if self.provinces:
            profile = profile.loc[profile.provincia_codigo.isin(self.provinces)]
        if self.categories:
            profile = profile.loc[profile.bono.isin(self.categories)]
        self.profile_rows = profile
        self.portfolio = self.scoped(self.portfolio_all)
        self.portfolio_cut = self.portfolio_all.periodo.max() if not self.portfolio_all.empty else None
        whole = self.rows_frame.loc[self.rows_frame.periodo.str[:4].eq(str(p["year"])) & self.rows_frame.periodo.le(p["id"])]
        credits, amount = int(year.creditos.sum()), float(year.monto.sum())
        previous = self.series.loc[self.series.periodo.lt(p["id"])].tail(1)
        women = profile.loc[profile.sexo.eq("Mujeres"), "creditos"].sum()
        self.stats = {"credits": credits, "amount": amount, "average": amount / credits if credits else None,
                      "month_credits": int(self.month_rows.creditos.sum()), "month_amount": float(self.month_rows.monto.sum()),
                      "previous": int(previous.creditos.iloc[0]) if not previous.empty else None,
                      "portfolio": int(self.portfolio.creditos.sum()), "portfolio_amount": float(self.portfolio.monto.sum()),
                      "women": women / profile.creditos.sum() * 100 if profile.creditos.sum() else None,
                      "share": credits / whole.creditos.sum() * 100 if (self.provinces or self.categories) and whole.creditos.sum() else None}
        self.labels()
        first_month = int(year.periodo.min()[5:7])
        self.span = (f"{MONTHS[first_month - 1]} a {MONTHS[p['month'] - 1]} de {p['year']}"
                     if first_month != p['month'] else f"{MONTHS[first_month - 1]} de {p['year']}")
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return (f"Corte {self.period['label'].lower()}", self.label,
                "Créditos desembolsados a personas usuarias de bonos y pensiones para emprendimientos productivos: cada mes del año, "
                "su perfil, su actividad y su territorio, con la cartera vigente.")

    def kpi_cards(self) -> list[dict]:
        s, month = self.stats, MONTHS[self.period["month"] - 1]
        cut = self.portfolio_cut
        return [
            {"label": f"Créditos desembolsados {self.period['year']}", "value": s["credits"], "icon": "coins", "tone": "morado",
             **({"share": s["share"], "share_label": "del total nacional"} if s["share"] is not None else {"note": f"De {self.span}"})},
            {"label": f"Monto desembolsado {self.period['year']}", "value": s["amount"] / 1e6, "decimals": 1, "prefix": "USD", "suffix": "millones",
             "icon": "banknote", "tone": "oro", "note": f"USD {ui.number(s['average'])} por crédito"},
            {"label": f"Créditos de {month}", "value": s["month_credits"], "icon": "calendar", "tone": "lila",
             "note": f"USD {ui.millions(s['month_amount'])} M desembolsados"},
            {"label": "Cartera vigente", "value": s["portfolio"], "icon": "wallet", "tone": "fucsia",
             "note": f"USD {ui.millions(s['portfolio_amount'])} M · {MONTHS[int(cut[5:]) - 1]} {cut[:4]}" if cut else ""},
        ]

    # ------------------------------------------------------------------------------------------- dashboard
    def by(self, field: str, frame: pd.DataFrame | None = None) -> pd.DataFrame:
        frame = self.year_rows if frame is None else frame
        rows = frame.groupby(field, as_index=False)[["creditos", "monto"]].sum().sort_values("creditos", ascending=False)
        total = rows.creditos.sum()
        rows["participacion"] = rows.creditos / total * 100 if total else 0.0
        return rows.reset_index(drop=True)

    def dashboard(self) -> None:
        p, s = self.period, self.stats
        labels = [MONTHS[int(x[5:]) - 1][:3].capitalize() for x in self.series.periodo]
        full = [f"{MONTHS[int(x[5:]) - 1].capitalize()} {p['year']}" for x in self.series.periodo]
        selected = list(self.series.periodo).index(p["id"]) if p["id"] in set(self.series.periodo) else None
        ui.section_heading("Desembolsos del año", f"{self.context_label} · de {self.span}", "trending-up")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_cdh_months"):
            ui.chart_title("Créditos desembolsados por mes", "El mes de la consulta en dorado")
            show_chart(charts.month_columns(labels, list(self.series.creditos), selected=selected, unit="créditos", full=full), "cdh_months")
        with right, st.container(border=True, key="card_cdh_bonus"):
            bonus = self.by("bono")
            ui.chart_title("Por bono o pensión de origen", "Créditos desembolsados en el año")
            show_chart(charts.ranked_bars(list(bonus.bono), list(bonus.creditos), CREDITS, share_total=float(bonus.creditos.sum()),
                                          share_label="de los créditos", height=max(170, len(bonus) * 40 + 40)), "cdh_bonus")
            terms = self.by("plazo")
            ui.chart_title("Plazo o tipo de crédito", "Participación en los créditos del año")
            show_chart(charts.part_of_whole([(f"{r.plazo}", r.creditos) for r in terms.itertuples()], unit="créditos"), "cdh_terms")
        ui.section_heading("Perfil y actividad productiva", f"{self.context_label} · personas con crédito en el año", "users")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_cdh_activity"):
            activity = self.profile_rows.groupby("actividad", as_index=False)[["creditos", "monto"]].sum().sort_values("creditos", ascending=False)
            ui.chart_title("Actividad productiva financiada", "Créditos desembolsados en el año")
            show_chart(charts.grouped_bars(list(activity.actividad), [("Créditos", list(activity.creditos), theme.SERIE_BONOS)], money=False,
                                           height=max(220, len(activity) * 62 + 50)), "cdh_activity")
        with right, st.container(border=True, key="card_cdh_profile"):
            ui.chart_title("Perfil de las personas con crédito", "Sexo, edad y área de residencia")
            for field, title in (("sexo", "Sexo"), ("edad", "Grupo de edad"), ("area", "Área")):
                parts = self.profile_rows.groupby(field).creditos.sum().sort_values(ascending=False)
                # Three parts at most (one colour each): the two largest and the rest together.
                shown = [(k, v) for k, v in parts.head(2).items()] + ([("Otros", int(parts.iloc[2:].sum()))] if len(parts) > 2 else [])
                st.markdown(f'<p class="profile-label">{title}</p>', unsafe_allow_html=True)
                show_chart(charts.part_of_whole(shown, unit="créditos"), f"cdh_profile_{field}")
        ui.section_heading("Territorio", f"{self.context_label} · créditos desembolsados en el año", "map")
        left, right = st.columns(2, gap="medium")
        provinces = self.by("provincia")
        with left, st.container(border=True, key="card_cdh_provinces"):
            ui.chart_title("Créditos por provincia", "Provincias ordenadas de mayor a menor")
            show_chart(charts.ranked_bars(list(provinces.provincia), list(provinces.creditos), CREDITS,
                                          share_total=float(provinces.creditos.sum()), share_label="del total"), "cdh_chart_provinces")
        with right, st.container(border=True, key="card_cdh_map"):
            codes = self.year_rows.groupby("provincia_codigo").creditos.sum()
            ui.chart_title("Mapa de créditos desembolsados", "Más oscuro, más créditos")
            titles = {c: f"{n}: {ui.number(codes.get(c, 0))} créditos" for c, n in
                      self.year_rows[["provincia_codigo", "provincia"]].drop_duplicates().itertuples(index=False, name=None)}
            st.markdown(self.light_map(codes.to_dict(), titles), unsafe_allow_html=True)
            ui.focus_tile("wallet", "Cartera vigente", f"{ui.number(s['portfolio'])} créditos",
                          f"USD {ui.millions(s['portfolio_amount'])} millones en créditos que aún se pagan, al corte de la cartera.")
        self._table()

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        if level == "mes":
            frame = self.series.assign(mes=[f"{MONTHS[int(x[5:]) - 1].capitalize()} {x[:4]}" for x in self.series.periodo])
            total = frame.creditos.sum()
            frame["participacion"] = frame.creditos / total * 100 if total else 0.0
            name, label = "mes", "Mes"
        else:
            keys = {"provincia": ["provincia"], "canton": ["provincia", "canton"], "parroquia": ["provincia", "canton", "parroquia"],
                    "bono": ["bono"]}[level]
            frame = self.year_rows.groupby(keys, as_index=False)[["creditos", "monto"]].sum().sort_values("creditos", ascending=False)
            total = frame.creditos.sum()
            frame["participacion"] = frame.creditos / total * 100 if total else 0.0
            name, label = keys[-1], {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia", "bono": "Bono o pensión"}[level]
        frame["promedio"] = frame.monto / frame.creditos.where(frame.creditos > 0)
        columns, layout = {}, []
        for key in (["provincia", "canton"] if level in ("canton", "parroquia") else []):
            if key != name:
                columns[key] = ({"provincia": "Provincia", "canton": "Cantón"}[key], "text", 170)
                layout.append(({"provincia": "Provincia", "canton": "Cantón"}[key], key, "text", 22.0))
        columns.update({name: (label, "text", 240), "creditos": ("Créditos", "int"), "monto": ("Monto (USD)", "money", None, None, "Monto"),
                        "promedio": ("Promedio por crédito (USD)", "money", None, None, "Promedio"),
                        "participacion": ("Participación", "pct", None, None, "Peso")})
        layout += [(label, name, "text", 30.0), ("Créditos", "creditos", "int", 14.0), ("Monto (USD)", "monto", "usd", 18.0),
                   ("Promedio por crédito (USD)", "promedio", "usd", 18.0), ("Participación", "participacion", "pct", 14.0)]
        return frame.reset_index(drop=True), columns, layout

    def report_parts(self) -> dict:
        s = self.stats
        provinces, bonus = self.by("provincia"), self.by("bono")
        leaders = provinces.head(3)
        months = [{"name": f"{MONTHS[int(x[5:]) - 1].capitalize()}", "value": v} for x, v in zip(self.series.periodo, self.series.creditos)]
        insights = [
            {"icon": "coins", "text": f"De {self.span} se desembolsaron {ui.number(s['credits'])} créditos por USD {ui.millions(s['amount'])} "
                                      f"millones; el promedio por crédito es de USD {ui.number(s['average'])}."},
            {"icon": "users", "text": f"Las mujeres reciben el {ui.pct(s['women'])} de los créditos del año." if s["women"] is not None else ""},
            {"icon": "map", "text": ", ".join(leaders.provincia) + f" reúnen el {ui.pct(leaders.participacion.sum())} de los créditos."},
            {"icon": "wallet", "text": f"La cartera vigente suma {ui.number(s['portfolio'])} créditos por USD {ui.millions(s['portfolio_amount'])} millones."},
        ]
        table_cols = [("Provincia", "provincia", "text"), ("Créditos", "creditos", "int"), ("Monto (USD)", "monto", "usd"),
                      ("Participación", "participacion", "pct")]
        return {"insights": [i for i in insights if i["text"]],
                "charts": [{"title": "Créditos desembolsados por mes", "note": f"De {self.span}", "rows": months, "unit": "créditos"},
                           {"title": "Por bono o pensión de origen", "note": "Créditos del año",
                            "rows": [{"name": r.bono, "value": r.creditos} for r in bonus.itertuples()], "unit": "créditos"}],
                "tables": [{"key": "provincia", "label": "Provincias", "columns": table_cols, "rows": provinces.to_dict("records")},
                           {"key": "bono", "label": "Bonos", "columns": [("Bono o pensión", "bono", "text"), *table_cols[1:]],
                            "rows": bonus.to_dict("records")},
                           {"key": "mes", "label": "Meses", "columns": [("Mes", "periodo", "text"), *table_cols[1:3]],
                            "rows": self.series.to_dict("records")}],
                "definitions": [("Créditos desembolsados", "Créditos de Desarrollo Humano entregados en el mes del archivo de desembolsos."),
                                ("Cartera vigente", "Créditos desembolsados que mantienen cuotas por pagar al corte de la base vigente."),
                                ("Fuente", ", ".join(manifest().get("cdh", {}).get("fuentes", {}).values()))]}
