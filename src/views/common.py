"""Pieces shared by every view: charts, tables with their Excel download and the period controls."""
from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from src import ui

PLOTLY_CONFIG = {
    "displaylogo": False, "scrollZoom": False, "doubleClick": False, "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d",
                               "resetScale2d", "toggleHover"],
    "toImageButtonOptions": {"format": "png", "filename": "MTDH_InfoReport", "scale": 2},
}


def compact() -> bool:
    return ui.is_mobile()


def show_chart(figure, key: str) -> None:
    config = {**PLOTLY_CONFIG, "displayModeBar": False} if compact() else PLOTLY_CONFIG
    st.plotly_chart(figure, width="stretch", theme=None, key=key, config=config)


def show_wide_chart(figure, key: str, width: int = 760) -> None:
    """A chart that keeps its width on phones and scrolls sideways inside its card."""
    if compact():
        # A fixed size (not autosized) keeps Plotly from shrinking it to the scroll container on a resize.
        figure.update_layout(width=width, autosize=False)
        st.plotly_chart(figure, width="content", theme=None, key=key,
                        config={**PLOTLY_CONFIG, "displayModeBar": False, "responsive": False})
    else:
        show_chart(figure, key)


def fingerprint(*parts) -> str:
    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, pd.DataFrame):
            digest.update(pd.util.hash_pandas_object(part, index=True).values.tobytes())
        else:
            digest.update(repr(part).encode("utf-8"))
    return digest.hexdigest()[:10]


def records(frame: pd.DataFrame, fields: list[str]) -> list[dict]:
    """Rows for an Excel sheet: missing values become empty cells, never zeros."""
    out = []
    for row in frame[[f for f in fields if f in frame]].to_dict("records"):
        out.append({k: (None if not isinstance(v, str) and pd.isna(v) else v) for k, v in row.items()})
    return out


@st.cache_data(show_spinner=False, max_entries=32)
def table_workbook(rows: list[dict], layout: list[tuple], title: str, subtitle: str, period_label: str, selection: str,
                   sheet: str = "Resultados") -> bytes:
    """A dashboard table as an institutional Excel sheet; it opens well whatever the regional settings."""
    from src.reports import table_xlsx
    return table_xlsx(rows, layout, title=title, subtitle=subtitle, period_label=period_label, selection=selection, sheet=sheet)


def download_table(frame: pd.DataFrame, layout: list[tuple], *, title: str, subtitle: str, period_label: str, file_name: str,
                   key: str, share_fields: tuple[str, ...] = ("participacion",)) -> None:
    """Excel download of a table; ``layout`` items are (header, field, kind, width) and percentages travel as fractions."""
    view = frame.copy()
    for field in share_fields:
        if field in view:
            view[field] = pd.to_numeric(view[field], errors="coerce") / 100
    rows = records(view, [field for _h, field, _k, _w in layout])
    content = table_workbook(rows, layout, title, subtitle, period_label, fingerprint(view))
    st.download_button("Descargar cuadro en Excel", content, file_name=file_name,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/table_view:",
                       key=key, type="primary")


def period_controls(catalog: list[dict]) -> dict:
    """Year and month of the consultation, among the cuts the area really has."""
    years = sorted({p["year"] for p in catalog}, reverse=True)
    if st.session_state.get("period_year") not in years:
        st.session_state["period_year"] = years[0]
    year = st.session_state["period_year"]
    months = [p for p in catalog if p["year"] == year and p["month"]]
    # Many months need the room: the year keeps a narrow column and the months take the rest, oldest first; with more
    # than two years, each control takes its own row.
    many = len(months) > 3
    if len(years) > 2 and many:
        col_year, col_month = st.container(), st.container()
    else:
        col_year, col_month = st.columns([1, 2.6] if many else [1, 1], gap="small")
    with col_year:
        year = st.segmented_control("Año", years, key="period_year", required=True, format_func=str, width="stretch")
    months = sorted((p for p in catalog if p["year"] == year and p["month"]), key=lambda p: p["month"])
    with col_month:
        if months:
            month_ids = [p["id"] for p in months]
            if st.session_state.get("period_month") not in month_ids:
                st.session_state["period_month"] = month_ids[-1]
            month_names = {p["id"]: (p["label"].split()[0][:3] if len(months) > 3 else p["label"].split()[0]) for p in months}
            period_id = st.segmented_control("Mes", month_ids, format_func=month_names.get, key="period_month",
                                             required=True, width="stretch")
            return next(p for p in catalog if p["id"] == period_id)
        period = next(p for p in catalog if p["year"] == year)
        span = period.get("span")
        if span:
            st.segmented_control("Mes", [span], default=span, key=f"period_span_{period['id']}", disabled=True, width="stretch")
        else:
            st.segmented_control("Mes", ["Corte anual"], default="Corte anual", key="period_month_annual", disabled=True,
                                 width="stretch")
        return period
