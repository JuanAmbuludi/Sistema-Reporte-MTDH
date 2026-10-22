"""Separately scoped references; never merged into current-cut indicators."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.data import DEFAULT_DATA_DIR, aggregate, filter_data, load_history
from src.ui import number


def render_references(provincias=None, programas=None, secciones=None):
    with st.expander("Otras hojas del Excel · referencias históricas y cantonales", expanded=False):
        st.caption("Estas referencias tienen un alcance propio y no se incorporan a los indicadores ni al boletín del corte vigente.")
        historical, cantonal = st.tabs(["Referencias 2024–2025", "Referencia cantonal"])
        with historical:
            history = load_history()
            if history.empty:
                st.info("El insumo no incluye referencias históricas.")
            else:
                st.info("El mes de corte de estas hojas no está documentado. No se calculan variaciones interanuales ni se suman sus usuarios al corte vigente.")
                year = st.selectbox("Año de la hoja de referencia", sorted(history.anio_referencia.unique(), reverse=True), key="reference_year")
                subset = filter_data(history.loc[history.anio_referencia.eq(year)], provincias=provincias, programas=programas, secciones=secciones)
                if subset.empty:
                    st.info("No hay referencias para los filtros seleccionados.")
                else:
                    totals = aggregate(subset, ["programa"])
                    fig = px.bar(totals.sort_values("usuarios"), x="usuarios", y="programa", orientation="h", color_discrete_sequence=["#7651AA"], labels={"usuarios":"Conteo reportado", "programa":""})
                    fig.update_layout(height=420, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=20,t=20,b=30), font=dict(color="#302744",family="Arial"), xaxis=dict(gridcolor="#ECE8F2"))
                    st.plotly_chart(fig, width="stretch", theme=None, key="reference_history", config={"displaylogo":False})
                    display = totals[["programa","usuarios","unidades","monto_fiscal","monto_gobierno"]].rename(columns={"programa":"Programa", "usuarios":"Conteo reportado", "unidades":"Unidades", "monto_fiscal":f"Fiscal {year} (USD)", "monto_gobierno":"Acumulado de referencia (USD)"})
                    st.dataframe(display,hide_index=True,width="stretch")
                    st.download_button("Descargar referencia anual CSV", subset.to_csv(index=False).encode("utf-8-sig"), f"MTDH_referencia_{year}_corte_no_documentado.csv", "text/csv", key="reference_history_csv")
        with cantonal:
            path = DEFAULT_DATA_DIR / "auxiliar_cantonal.parquet"
            if not path.exists():
                st.info("El insumo no incluye una referencia cantonal.")
            else:
                st.info("Período no documentado. Los importes cantonales son prorrateos de presupuestos provinciales según cobertura; no son gasto cantonal observado. Hay campos incompletos.")
                frame = pd.read_parquet(path)
                for col in ["presupuesto_prorrateado", "presupuesto_provincial", "proporcion"]:
                    frame[col] = pd.to_numeric(frame[col], errors="coerce")
                frame = filter_data(frame, provincias=provincias, programas=programas, secciones=secciones)
                if frame.empty:
                    st.info("No hay referencias cantonales para los filtros seleccionados.")
                else:
                    st.caption(f"{number(len(frame))} filas de la hoja calculos dic. Se respetan los filtros de provincia, sección y programa.")
                    fields = ["provincia", "canton", "programa", "usuarios", "proporcion", "presupuesto_prorrateado"]
                    st.dataframe(frame[fields], hide_index=True, width="stretch", column_config={
                        "provincia":"Provincia", "canton":"Cantón", "programa":"Programa / servicio", "usuarios":"Conteo de referencia",
                        "proporcion":st.column_config.NumberColumn("Proporción provincial",format="%.4f"),
                        "presupuesto_prorrateado":st.column_config.NumberColumn("Prorrateo estimado (USD)",format="%.2f")
                    })
                    st.download_button("Descargar referencia cantonal CSV", frame.to_csv(index=False).encode("utf-8-sig"), "MTDH_referencia_cantonal_periodo_no_documentado.csv", "text/csv", key="reference_canton_csv")
