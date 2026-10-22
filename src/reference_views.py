"""Separately scoped references; never merged into current-cut indicators."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src import ui
from src.charts import reference_bars
from src.data import DEFAULT_DATA_DIR, aggregate, filter_data, load_history

PLOTLY_CONFIG = {"displaylogo": False, "scrollZoom": False, "doubleClick": False, "responsive": True,
                 "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d", "resetScale2d", "toggleHover"]}


@st.cache_data(show_spinner=False)
def _history() -> pd.DataFrame:
    return load_history()


@st.cache_data(show_spinner=False)
def _cantonal() -> pd.DataFrame:
    path = DEFAULT_DATA_DIR / "auxiliar_cantonal.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    for col in ["presupuesto_prorrateado", "presupuesto_provincial", "proporcion"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def render_references(provincias=None, programas=None, secciones=None):
    with st.container(border=True, key="card_references"):
        historical, cantonal = st.tabs(["Referencias anuales 2024 y 2025", "Referencia cantonal"], key="reference_tabs")
        with historical:
            history = _history()
            if history.empty:
                ui.info_note("El insumo no incluye referencias históricas.", "Sin referencias")
            else:
                ui.info_note("El mes de corte de estas hojas no está documentado. Por eso no se calculan variaciones interanuales "
                             "ni se suman sus registros al corte vigente.", "Alcance de la referencia", tone="warn")
                years = sorted(history.anio_referencia.unique(), reverse=True)
                year = st.segmented_control("Año de la hoja de referencia", years, default=years[0], key="reference_year",
                                            required=True, format_func=str)
                subset = filter_data(history.loc[history.anio_referencia.eq(year)], provincias=provincias, programas=programas, secciones=secciones)
                if subset.empty:
                    ui.info_note("No hay referencias para los filtros seleccionados.", "Sin coincidencias")
                else:
                    totals = aggregate(subset, ["programa_id", "programa"])
                    st.plotly_chart(reference_bars(totals), width="stretch", theme=None, key="reference_history", config=PLOTLY_CONFIG)
                    ui.data_table(totals.sort_values("usuarios", ascending=False), {
                        "programa": ("Programa o servicio", "text", "large"),
                        "usuarios": ("Registros de referencia", "int"),
                        "unidades": ("Unidades de atención", "int"),
                        "monto_fiscal": (f"Presupuesto {year} (USD)", "money"),
                        "monto_gobierno": ("Acumulado de referencia (USD)", "money"),
                    }, key="reference_history_table")
                    st.download_button("Descargar referencia anual en CSV", subset.to_csv(index=False).encode("utf-8-sig"),
                                       f"MTDH_referencia_{year}_corte_no_documentado.csv", "text/csv", key="reference_history_csv",
                                       icon=":material/download:")
        with cantonal:
            frame = _cantonal()
            if frame.empty:
                ui.info_note("El insumo no incluye una referencia cantonal.", "Sin referencia cantonal")
            else:
                ui.info_note("Período no documentado. Los importes cantonales son prorrateos de presupuestos provinciales según cobertura; "
                             "no son gasto cantonal observado y hay campos incompletos.", "Alcance de la referencia", tone="warn")
                frame = filter_data(frame, provincias=provincias, programas=programas, secciones=secciones)
                if frame.empty:
                    ui.info_note("No hay referencias cantonales para los filtros seleccionados.", "Sin coincidencias")
                else:
                    st.caption(f"{ui.number(len(frame))} filas de la hoja «calculos dic», con los mismos filtros de provincia, ámbito y programa.")
                    view = frame.assign(canton=frame.canton.map(ui.place_name))
                    ui.data_table(view, {
                        "provincia": ("Provincia", "text", "small"),
                        "canton": ("Cantón", "text", "medium"),
                        "programa": ("Programa o servicio", "text", "medium"),
                        "usuarios": ("Registros de referencia", "int"),
                        "proporcion": ("Peso en la provincia", "share"),
                        "presupuesto_prorrateado": ("Prorrateo estimado (USD)", "money"),
                    }, height=420, key="reference_canton_table")
                    st.download_button("Descargar referencia cantonal en CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                                       "MTDH_referencia_cantonal_periodo_no_documentado.csv", "text/csv", key="reference_canton_csv",
                                       icon=":material/download:")
