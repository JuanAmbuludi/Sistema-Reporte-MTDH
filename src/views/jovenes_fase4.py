"""Separate fourth-phase payment monitoring, with no inferred calendar cut."""
from __future__ import annotations

from textwrap import wrap

import pandas as pd
import streamlit as st

from src import charts, corte, jovenes_fase4 as source, theme, ui
from src.indicators import Indicator
from src.views.area import AreaView
from src.views.common import compact, download_table, fingerprint, show_chart

TRANSFERS = Indicator("transferencias", "Transferencias", "count", "send", "transferencias")
ACCREDITATION = Indicator("tasa_acreditacion", "Acreditación", "rate", "target", "%")
SNAPSHOT = {"id": "fase4", "stamp": "fase4_monitoreo", "year": None, "month": None,
            "label": "Fase 4 · Monitoreo sin fecha de corte"}


def _entity_labels(codes) -> list[str]:
    return ["<br>".join(wrap(source.entity_name(code), 25, break_long_words=False)) for code in codes]


class PhaseFourView(AreaView):
    kind = id = "jovenes_fase4"
    label = "Jóvenes en Acción · Fase 4"
    file_id = "jovenes_fase4_monitoreo"
    empty_message = "No hay registros de monitoreo para las entidades seleccionadas."
    LEVELS = {"Por entidad": "entidad", "Por motivo": "motivo", "Entidad y motivo": "detalle"}

    def __init__(self):
        self.all_payments = source.payments()
        self.metadata = source.metadata()
        self.entities = []
        self.period = dict(SNAPSHOT)

    def catalog(self) -> list[dict]:
        return [dict(SNAPSHOT)] if not self.all_payments.empty else []

    def period_controls(self) -> dict:
        st.caption("La fuente identifica el cuarto período y no especifica una fecha de corte.")
        return dict(SNAPSHOT)

    def select(self, period: dict | None = None, entities=()) -> None:
        self.period, self.entities = dict(SNAPSHOT), list(entities)

    def controls(self, period: dict) -> None:
        self.period = dict(SNAPSHOT)
        options = list(self.all_payments.entidad)
        key = "youth4_entities"
        if key in st.session_state:
            st.session_state[key] = [value for value in st.session_state[key] if value in options]
        self.entities = st.multiselect("Entidad ejecutora", options, format_func=source.entity_name,
                                       placeholder="Todas las entidades", key=key)
        if self.entities:
            st.button("Restablecer filtros", icon=":material/restart_alt:", type="tertiary", key="youth4_reset",
                      on_click=self._clear)

    @staticmethod
    def _clear() -> None:
        st.session_state["youth4_entities"] = []

    def prepare(self) -> bool:
        selected = source.select(self.entities or None)
        self.payments, self.rejections, self.stats = selected["pagos"], selected["rechazos"], selected["resumen"]
        self.rejections["motivo"] = self.rejections.motivo.map(source.reason_label)
        if self.payments.empty:
            return False
        self.metadata = selected["metadata"]
        self.territory_label = (source.entity_name(self.entities[0]) if len(self.entities) == 1 else f"{len(self.entities)} entidades ejecutoras"
                                if self.entities else "Todas las entidades")
        self.programs_label = "Fase 4 · Monitoreo"
        self.context_label = f"{self.programs_label} · {self.territory_label}"
        self.causes = self.rejections.groupby(["codigo_rechazo", "motivo"], as_index=False).transferencias.sum()
        self.causes = self.causes.sort_values("transferencias", ascending=False).reset_index(drop=True)
        total = self.causes.transferencias.sum()
        self.causes["participacion"] = self.causes.transferencias / total * 100 if total else 0.0
        return True

    def hero_copy(self) -> tuple[str, str, str]:
        return ("Cuarto período · Monitoreo", self.label,
                "Jóvenes seleccionados y autorizados, transferencias acreditadas y no acreditadas, "
                "y motivos de rechazo por entidad ejecutora.")

    def update_stamp(self) -> dict:
        note = "Fuente sin fecha de corte"
        stamp = corte.stamp(self.id, self.period, cut_text=note)
        stamp.update(frequency="Según la fuente", frequency_word="según la fuente")
        stamp["line"] = note + (f" · Actualizado el {stamp['updated']}" if stamp["updated"] else "")
        stamp["short"] = note + (f" · Actualizado: {stamp['updated_short']}" if stamp["updated_short"] else "")
        return stamp

    def series_svg(self, night: bool = True, width: int = 640, height: int = 360) -> str:
        s = self.stats
        labels = ["Seleccionados", "Autorizados", "Acreditadas", "No acreditadas"]
        values = [s[field] for field in ("seleccionados", "autorizados", "acreditadas", "no_acreditadas")]
        return ui.svg_columns(values, labels, titles=[f"{name}: {ui.number(value)}" for name, value in zip(labels, values)],
                              width=width, height=height, night=night, highlight=2,
                              css_class="ec-columns" if night else "ec-columns mini",
                              value_text=lambda value: ui.number(value / 1000, 1) + " mil" if value >= 10000 else ui.number(value))

    def hero_visual(self) -> None:
        ui.hero_series(self.series_svg(), "Selección, autorización y resultado de las transferencias · fase 4")

    def preview_visual(self) -> str:
        return self.series_svg(night=False, width=300, height=170)

    def kpi_cards(self) -> list[dict]:
        s = self.stats
        return [
            {"label": "Jóvenes seleccionados", "value": s["seleccionados"], "icon": "graduation", "tone": "morado",
             "note": f"{ui.number(s['autorizados'])} autorizados · fase 4"},
            {"label": "Transferencias acreditadas", "value": s["acreditadas"], "icon": "send", "tone": "oro",
             "bar": s["tasa_acreditacion"], "bar_label": f"{ui.pct(s['tasa_acreditacion'])} de las autorizadas"},
            {"label": "Monto acreditado", "value": s["monto_acreditado"] / 1e6, "decimals": 2,
             "prefix": "USD", "suffix": "millones", "icon": "banknote", "tone": "lila",
             "note": f"{ui.number(s['entidades'])} entidades ejecutoras en la selección"},
            {"label": "Transferencias no acreditadas", "value": s["no_acreditadas"], "icon": "shield", "tone": "fucsia",
             "note": f"USD {ui.number(s['monto_no_acreditado'], 2)} sin acreditación"},
        ]

    def dashboard(self) -> None:
        s, rows = self.stats, self.payments
        ui.section_heading("Autorización y acreditación", self.context_label, "send")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_youth4_flow"):
            ui.chart_title("De la selección a la acreditación", "Totales reportados en el cuarto período")
            steps = [("Seleccionados", s["seleccionados"], "Jóvenes seleccionados según la fuente"),
                     ("Autorizados", s["autorizados"], f"{ui.pct(s['tasa_autorizacion'])} de los seleccionados"),
                     ("Acreditadas", s["acreditadas"], f"{ui.pct(s['tasa_acreditacion'])} de las transferencias autorizadas")]
            show_chart(charts.funnel_bars(steps), "youth4_flow")
            st.caption(f"{ui.number(s['sin_autorizacion'])} seleccionados sin autorización en la fuente.")
        with right, st.container(border=True, key="card_youth4_result"):
            ui.chart_title("Resultado de las transferencias", "Sobre el total autorizado")
            show_chart(charts.part_of_whole([("Acreditadas", s["acreditadas"]), ("No acreditadas", s["no_acreditadas"])],
                                            unit="transferencias"), "youth4_result")
            ui.focus_tile("wallet", "Monto autorizado", f"USD {ui.number(s['monto_autorizado'], 2)}",
                          f"{ui.number(s['autorizados'])} autorizaciones reportadas")

        ui.section_heading("Resultados por entidad ejecutora", "Autorización, acreditación y proporción acreditada", "building")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_youth4_entities"):
            ui.chart_title("Autorizadas y acreditadas", "Transferencias por entidad ejecutora")
            show_chart(charts.grouped_bars(_entity_labels(rows.entidad), [
                ("Autorizadas", list(rows.autorizados), theme.LILA_300),
                ("Acreditadas", list(rows.acreditadas), theme.MORADO)], money=False), "youth4_entities_chart")
        with right, st.container(border=True, key="card_youth4_rates"):
            rates = rows.sort_values("tasa_acreditacion", ascending=False)
            ui.chart_title("Tasa de acreditación", "Acreditadas sobre autorizadas · porcentaje")
            show_chart(charts.ranked_bars(_entity_labels(rates.entidad), list(rates.tasa_acreditacion), ACCREDITATION,
                                          hover=list(rates.entidad.map(source.entity_name)),
                                          height=max(300, len(rates) * 64 + 46)), "youth4_rates")

        ui.section_heading("Transferencias no acreditadas", "Motivos reportados y distribución por entidad", "shield")
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_youth4_causes"):
            causes = self.causes.loc[self.causes.transferencias.gt(0)]
            ui.chart_title("Motivos de rechazo", "Número de transferencias por motivo")
            if causes.empty:
                st.caption("La selección no registra transferencias no acreditadas.")
            else:
                labels = [name if len(name) < 54 else name[:51] + "…" for name in causes.motivo]
                show_chart(charts.ranked_bars(labels, list(causes.transferencias), TRANSFERS, hover=list(causes.motivo),
                                              share_total=s["no_acreditadas"], share_label="de las no acreditadas"), "youth4_causes")
        with right, st.container(border=True, key="card_youth4_rejected_entities"):
            rejected = rows.sort_values("no_acreditadas", ascending=False)
            ui.chart_title("No acreditadas por entidad", "Número de transferencias")
            show_chart(charts.ranked_bars(_entity_labels(rejected.entidad), list(rejected.no_acreditadas), TRANSFERS,
                                          hover=list(rejected.entidad.map(source.entity_name)),
                                          height=max(300, len(rejected) * 64 + 46),
                                          share_total=s["no_acreditadas"], share_label="de las no acreditadas"), "youth4_rejected_entities")
        self._table()
        st.caption("Fuente: monitoreo del cuarto período. Las transferencias de esta fase se presentan por separado de las fases 1–3; "
                   "el archivo no especifica fecha de corte ni permite determinar personas únicas entre fases.")

    def detail(self, level: str) -> tuple[pd.DataFrame, dict, list[tuple]]:
        if level == "entidad":
            rows = source.display_entities(self.payments)
            fields = [("Entidad", "entidad", "text", 52), ("Seleccionados", "seleccionados", "int", 16),
                      ("Autorizados", "autorizados", "int", 16), ("Acreditadas", "acreditadas", "int", 16),
                      ("No acreditadas", "no_acreditadas", "int", 16), ("Acreditación", "tasa_acreditacion", "pct", 16),
                      ("Monto autorizado (USD)", "monto_autorizado", "usd", 23),
                      ("Monto acreditado (USD)", "monto_acreditado", "usd", 23),
                      ("Monto no acreditado (USD)", "monto_no_acreditado", "usd", 24)]
        else:
            rows = self.causes.copy() if level == "motivo" else source.display_entities(self.rejections)
            fields = ([] if level == "motivo" else [("Entidad", "entidad", "text", 52)]) + [
                ("Código", "codigo_rechazo", "text", 12), ("Motivo", "motivo", "text", 65),
                ("Transferencias", "transferencias", "int", 18)]
            if level == "motivo":
                fields.append(("Participación", "participacion", "pct", 18))
        columns = {field: (label, "money" if kind == "usd" else kind) for label, field, kind, _ in fields}
        if "entidad" in columns:
            columns["entidad"] = ("Entidad", "text", 370)
        return rows, columns, fields

    def _table(self) -> None:
        ui.section_heading("Cuadro de resultados", self.context_label, "table")
        key = "youth4_level"
        if st.session_state.get(key) not in self.LEVELS:
            st.session_state[key] = next(iter(self.LEVELS))
        level = st.segmented_control("Nivel de detalle", list(self.LEVELS), key=key, required=True,
                                     width="stretch" if compact() else "content")
        frame, columns, layout = self.detail(self.LEVELS[level])
        with st.container(border=True, key="card_youth4_detail"):
            ui.data_table(frame, columns, height=min(640, 35 * (len(frame) + 1) + 3), key="youth4_table")
            download_table(frame, layout, title=self.label, subtitle=f"{self.context_label} · {level.lower()}",
                           period_label=self.period["label"], file_name=f"MTDH_cuadro_{self.file_id}.xlsx", key="youth4_xlsx",
                           share_fields=("participacion", "tasa_acreditacion"))

    def scope_items(self) -> list[tuple[str, str]]:
        return [("Ámbito", "Jóvenes en Acción"), ("Seguimiento", "Fase 4 · Monitoreo"),
                ("Entidades", self.territory_label), ("Corte", "No especificado en la fuente")]

    def products_notes(self) -> dict[str, str]:
        return {"resumen": "Dos páginas en PDF con indicadores, acreditaciones por entidad y motivos de rechazo de la fase 4.",
                "presentacion": "Tres diapositivas editables con cifras clave, acreditaciones y motivos de rechazo de la fase 4.",
                "datos": "Libro de Excel con entidades, pagos y montos, motivos de rechazo y ficha técnica de la fase 4."}

    def report_contents(self, kind: str) -> list[tuple[str, str, str]]:
        return [("grid", "Cifras clave", "Selección, acreditaciones y montos"),
                ("building", "Entidades ejecutoras", "Autorizaciones y resultados por entidad"),
                ("shield", "Motivos de rechazo", "Transferencias no acreditadas"),
                ("table", "Cuadros", "Conteos y montos exactos de la selección")]

    def slide_titles(self) -> tuple[str, str]:
        return "Acreditaciones por entidad", "Motivos de rechazo"

    def report_parts(self) -> dict:
        s, rows, causes = self.stats, self.payments, self.causes
        display_rows = source.display_entities(rows).to_dict("records")
        entity_cols = [("Entidad", "entidad", "text"), ("Autorizadas", "autorizados", "int"),
                       ("Acreditadas", "acreditadas", "int"), ("No acreditadas", "no_acreditadas", "int"),
                       ("Acreditación", "tasa_acreditacion", "pct")]
        all_fields = self.detail("entidad")[2]
        cause_fields = self.detail("motivo")[2]
        detail_fields = self.detail("detalle")[2]
        source_name = self.metadata.get("fuente", {}).get("nombre", "Monitoreo del cuarto período de Jóvenes en Acción")
        return {
            "insights": [
                {"icon": "send", "text": f"Se acreditaron {ui.number(s['acreditadas'])} transferencias por USD "
                                         f"{ui.number(s['monto_acreditado'], 2)}: {ui.pct(s['tasa_acreditacion'])} de las autorizadas."},
                {"icon": "shield", "text": f"{ui.number(s['no_acreditadas'])} transferencias no se acreditaron, por USD "
                                           f"{ui.number(s['monto_no_acreditado'], 2)}."},
                {"icon": "clock", "text": "Monitoreo independiente de la fase 4. La fuente no especifica fecha de corte."}],
            "charts": [{"title": "Acreditaciones por entidad", "note": "Transferencias acreditadas · fase 4", "unit": "transferencias",
                        "rows": [{"name": source.entity_name(row.entidad), "short_name": row.entidad,
                                  "value": row.acreditadas} for row in rows.itertuples()]},
                       {"title": "Motivos de rechazo", "note": "Transferencias no acreditadas", "unit": "transferencias",
                        "rows": [{"name": row.motivo, "value": row.transferencias} for row in causes.itertuples()]}],
            "tables": [{"key": "entidad", "label": "Entidades", "columns": entity_cols, "rows": display_rows},
                       {"key": "motivo", "label": "Motivos", "columns": [field[:3] for field in cause_fields],
                        "rows": causes.to_dict("records"), "pdf_widths": {"codigo_rechazo": 40}},
                       {"key": "pagos", "label": "Pagos y montos", "columns": [field[:3] for field in all_fields],
                        "rows": display_rows},
                       {"key": "detalle", "label": "Entidad y motivo", "columns": [field[:3] for field in detail_fields],
                        "rows": source.display_entities(self.rejections).to_dict("records")}],
            "definitions": [("Seleccionados y autorizados", "Conteos de jóvenes reportados por entidad ejecutora en el cuarto período."),
                            ("Transferencias acreditadas", "Transferencias con acreditación reportada en la fuente; no se suman a personas únicas de otras fases."),
                            ("Transferencias no acreditadas", "Autorizadas sin acreditación; los motivos de rechazo concilian con este total."),
                            ("Tasa de acreditación", "Transferencias acreditadas divididas para las autorizadas, multiplicado por 100."),
                            ("Corte", "La fuente no especifica una fecha de corte; estas cifras no se asignan a un mes o año."),
                            ("Fuente", source_name)]}

    def report_context(self, title: str) -> dict:
        context = super().report_context(title)
        context["tables_note"] = "Monitoreo de la fase 4 · fuente sin fecha de corte"
        return context

    def digest(self) -> str:
        return fingerprint(self.payments, self.rejections, self.metadata, tuple(self.entities), source.ENTITY_NAMES, "youth4-v3")
