"""Independent national financial view; never joined to VIS/VIE coverage."""
from __future__ import annotations

import json
from pathlib import Path
import textwrap

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import theme, ui
from src.data import MONTHS

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
MONEY = ["presupuesto_codificado", "presupuesto_ejecutado", "presupuesto_certificado"]


@st.cache_data(show_spinner=False)
def financial_data(path: str, version: int) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    for field in MONEY:
        frame[field] = pd.to_numeric(frame[field])
    return frame


def financial_programs(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby(["programa_codigo", "programa"], as_index=False)[MONEY].sum(min_count=1)
    grouped["porcentaje_ejecucion"] = (100 * grouped.presupuesto_ejecutado /
                                      grouped.presupuesto_codificado.replace(0, float("nan")))
    return grouped.sort_values("presupuesto_ejecutado", ascending=False)


def show_institutional(period_id: str) -> None:
    manifest_path, path = DATA / "manifest_financiero.json", DATA / "presupuesto_institucional.parquet"
    if not manifest_path.exists() or not path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["periodo"][:7] != period_id:
        return
    frame = financial_data(str(path), path.stat().st_mtime_ns)
    values = manifest["totales"]
    year, month = map(int, period_id.split("-"))
    period_label = f"{MONTHS[month - 1]} {year}"
    ui.section_heading("Presupuesto institucional", f"Base financiera · {period_label.capitalize()} · Total nacional", "landmark")
    ui.info_note("Este bloque corresponde al universo de la base financiera nacional. Es independiente del ámbito y las provincias "
                 "seleccionados arriba; sus montos no se suman con los de bonos y servicios.", "Ámbito del presupuesto")
    ui.kpi_grid([
        {"label": "Presupuesto ejecutado", "value": values["presupuesto_ejecutado"] / 1e6,
         "decimals": 2, "prefix": "USD", "suffix": "M", "icon": "banknote", "note": "Devengado fiscal al corte"},
        {"label": "Presupuesto codificado", "value": values["presupuesto_codificado"] / 1e6,
         "decimals": 2, "prefix": "USD", "suffix": "M", "icon": "wallet", "note": "Universo de la base financiera"},
        {"label": "Ejecución presupuestaria", "value": values["porcentaje_ejecucion"],
         "decimals": 2, "suffix": "%", "icon": "chart", "note": "Devengado / codificado"},
        {"label": "Presupuesto certificado", "value": values["presupuesto_certificado"] / 1e6,
         "decimals": 2, "prefix": "USD", "suffix": "M", "icon": "shield", "note": "Fase distinta del devengado"},
    ], overlap=False)
    programs = financial_programs(frame)
    with st.container(border=True, key="card_financial_national"):
        ui.chart_title("Ejecución por programa presupuestario", "Porcentaje del presupuesto codificado · Total nacional")
        plot = programs.sort_values("porcentaje_ejecucion")
        compact = ui.is_mobile()
        labels = ["<br>".join(textwrap.wrap(ui.place_name(name), width=24 if compact else 40)) for name in plot.programa]
        figure = go.Figure(go.Bar(y=labels, x=plot.porcentaje_ejecucion, customdata=plot.programa.map(ui.place_name),
                                  orientation="h", marker_color=theme.MORADO,
                                  text=[ui.pct(v, 2) for v in plot.porcentaje_ejecucion], textposition="outside",
                                  hovertemplate="%{customdata}<br>Ejecución: %{x:.2f} %<extra></extra>"))
        figure.update_layout(height=600 if compact else 470, margin=dict(l=10, r=40, t=10, b=35), paper_bgcolor="rgba(0,0,0,0)",
                             plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Arial", color=theme.MORADO_900),
                             xaxis=dict(range=[0, 110], title="Ejecución (%)", gridcolor="#EEEAF4"),
                             yaxis=dict(title=None, automargin=True, tickfont=dict(size=10 if compact else 12)), showlegend=False)
        st.plotly_chart(figure, width="stretch", theme=None, key="financial_execution",
                        config={"displayModeBar": False})
        ui.data_table(programs, {"programa": ("Programa presupuestario", "text"),
            "presupuesto_codificado": ("Codificado (USD)", "money"),
            "presupuesto_ejecutado": ("Devengado (USD)", "money"),
            "presupuesto_certificado": ("Certificado (USD)", "money"),
            "porcentaje_ejecucion": ("Ejecución (%)", "pct")}, key="financial_programs")
        st.download_button("Descargar presupuesto nacional en CSV", programs.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"MTDH_presupuesto_institucional_{period_id}.csv", mime="text/csv",
                           icon=":material/download:", key="financial_csv")
    duplicates = manifest["control_calidad"]["repeticiones_exactas_conservadas"]
    ui.info_note(f"Corte de {period_label} confirmado por el responsable de la base. Se conservan {duplicates} filas "
                 "con contenido idéntico pendientes de confirmar con el detalle de partidas presupuestarias.", "Referencia de la información")
