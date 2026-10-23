"""InfoReportes MTDH: tablero de indicadores estratégicos y centro de reportes institucionales.

Run from the repository root with ``streamlit run app.py``.
Each view reads one period and one thematic module (transfers and services are never mixed), and every
export receives exactly the rows shown on screen.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
st.set_page_config(
    page_title="InfoReportes · Ministerio de Trabajo y Desarrollo Humano",
    page_icon=str(ROOT / "assets" / "brand" / "favicon.png"),
    layout="wide",
    initial_sidebar_state="collapsed",
)

from src import charts, geo, theme, ui
from src.auth import logout, require_login
from src.data import DEFAULT_DATA_DIR, aggregate, filter_data, load_periods, summarize
from src.indicators import MODULES

ui.inject_styles()
user = require_login()
COMPACT = ui.is_mobile()

WORKSPACES = {"Tablero": ":material/insights: Tablero", "Reportes": ":material/description: Reportes"}
PLOTLY_CONFIG = {
    "displaylogo": False, "scrollZoom": False, "doubleClick": False, "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d",
                               "resetScale2d", "toggleHover"],
    "toImageButtonOptions": {"format": "png", "filename": "MTDH_InfoReportes", "scale": 2},
}


@st.cache_data(show_spinner=False)
def read_periods(version: int):
    """Invalidated when any processed file changes."""
    return load_periods()


def clear_filters() -> None:
    st.session_state["selected_provinces"] = []
    st.session_state["selected_programs"] = []


def show_chart(figure, key: str) -> None:
    config = {**PLOTLY_CONFIG, "displayModeBar": False} if COMPACT else PLOTLY_CONFIG
    st.plotly_chart(figure, width="stretch", theme=None, key=key, config=config)


try:
    processed = [DEFAULT_DATA_DIR / name for name in ("indicadores.parquet", "historico_referencia.parquet", "manifest.json")]
    data, catalog = read_periods(max(path.stat().st_mtime_ns for path in processed if path.exists()))
except (FileNotFoundError, ValueError, OSError):
    ui.info_note("La información no está disponible en este momento. Vuelva a cargar la página en unos minutos.",
                 "Información no disponible", tone="warn")
    st.stop()

province_names = data.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.to_dict()
# Chart-length program names; official names stay in tables, except on phones where the label column is narrow.
short_programs = {row.programa: theme.program_label(row.programa_id, row.programa)
                  for row in data.drop_duplicates("programa_id").itertuples()}
years = sorted({p["year"] for p in catalog}, reverse=True)
st.session_state.setdefault("workspace", "Tablero")
st.session_state.setdefault("module", next(iter(MODULES)))
if st.session_state.get("period_year") not in years:
    st.session_state["period_year"] = years[0]

# ---------------------------------------------------------------------------
# Institutional band: top bar, consultation and the map of Ecuador
# ---------------------------------------------------------------------------
with st.container(key="band"):
    with st.container(key="topbar", horizontal=True, vertical_alignment="center", gap="small"):
        ui.brand_mark()
        st.segmented_control("Espacio de trabajo", list(WORKSPACES), format_func=WORKSPACES.get, key="workspace",
                             required=True, label_visibility="collapsed")
        ui.user_chip(user.get("name", user.get("username", "Usuario")))
        st.button("Salir", icon=":material/logout:", key="logout_button", on_click=logout, type="tertiary",
                  help="Cerrar la sesión")

    hero_left, hero_right = st.columns([1.02, 1], gap="large", vertical_alignment="center")
    with hero_left:
        copy_slot = st.empty()
        with st.container(key="consulta"):
            col_year, col_month = st.columns(2, gap="small")
            with col_year:
                year = st.segmented_control("Año", years, key="period_year", required=True, format_func=str, width="stretch")
            months = [p for p in catalog if p["year"] == year and p["month"]]
            with col_month:
                if months:
                    month_ids = [p["id"] for p in months]
                    if st.session_state.get("period_month") not in month_ids:
                        st.session_state["period_month"] = month_ids[0]
                    month_names = {p["id"]: p["label"].split()[0] for p in months}
                    period_id = st.segmented_control("Mes", month_ids, format_func=month_names.get, key="period_month",
                                                     required=True, width="stretch")
                else:
                    period_id = next(p["id"] for p in catalog if p["year"] == year)
                    st.segmented_control("Mes", ["Corte anual"], default="Corte anual", key="period_month_annual",
                                         disabled=True, width="stretch")
            period = next(p for p in catalog if p["id"] == period_id)
            module_id = st.segmented_control("Ámbito", list(MODULES), format_func=lambda m: MODULES[m].label, key="module",
                                             required=True, width="stretch")
            module = MODULES[module_id]
            scoped = filter_data(data.loc[data.periodo_id.eq(period_id)], secciones=list(module.sections))
            province_options = sorted(scoped.provincia_codigo.unique(), key=lambda c: (c == geo.NO_POLYGON, province_names[c]))
            program_order = list(scoped.groupby("programa_id").usuarios.sum().sort_values(ascending=False).index)
            program_lookup = scoped.drop_duplicates("programa_id").set_index("programa_id").programa.to_dict()
            # A change of period or module must not leave hidden selections behind.
            for key, available in [("selected_provinces", province_options), ("selected_programs", program_order)]:
                if key in st.session_state:
                    st.session_state[key] = [v for v in st.session_state[key] if v in available]
            col_territory, col_program = st.columns(2, gap="small")
            with col_territory:
                selected_provinces = st.multiselect("Territorio", province_options, format_func=province_names.get,
                                                    placeholder="Todo el país", key="selected_provinces")
            with col_program:
                selected_programs = st.multiselect(module.item.capitalize(), program_order, format_func=program_lookup.get,
                                                   placeholder=f"Todos los {module.items}", key="selected_programs")
            if selected_provinces or selected_programs:
                st.button("Restablecer filtros", icon=":material/restart_alt:", on_click=clear_filters,
                          type="tertiary", key="reset_filters")

    executed_available = scoped["presupuesto_ejecutado"].notna().all()
    indicators = module.indicators(period["year"], executed=executed_available)
    by_key = {indicator.key: indicator for indicator in indicators}
    if st.session_state.get("map_indicator") not in by_key:
        st.session_state["map_indicator"] = indicators[0].key
    with hero_right:
        map_key = st.segmented_control("Indicador territorial", list(by_key), format_func=lambda k: by_key[k].compact,
                                       key="map_indicator", required=True, width="stretch")
        map_slot = st.empty()
    indicator = by_key[map_key]

filtered = filter_data(scoped, provincias=selected_provinces or None, programas=selected_programs or None)
if filtered.empty:
    ui.info_note("La combinación elegida no registra información. Ajuste el territorio o la selección de programas.",
                 "Sin resultados para esta selección", tone="warn")
    st.stop()

# National context: same period, module and programs, every province.  Shares, maps and rankings use it.
national = filter_data(scoped, programas=selected_programs or None)
stats, national_stats, scope_stats = summarize(filtered), summarize(national), summarize(scoped)
selected_codes = set(selected_provinces)
money = module.money(period["year"], executed=executed_available)
people = module.people_indicator()
selection_hash = hashlib.sha256(pd.util.hash_pandas_object(filtered, index=True).values.tobytes()).hexdigest()[:10]

if len(selected_provinces) == 1:
    territory_label = province_names[selected_provinces[0]]
    headline = f"{module.label} en {territory_label}"
elif selected_provinces:
    territory_label = f"{len(selected_provinces)} provincias"
    headline = f"{module.label} en {territory_label}"
else:
    territory_label = "Nacional"
    headline = module.label
programs_label = (program_lookup[selected_programs[0]] if len(selected_programs) == 1 else
                  f"{len(selected_programs)} {module.items}" if selected_programs else f"Todos los {module.items}")
period_chip = f"Corte {period['label'].lower()}" if period["month"] else period["label"]
context_label = f"{period['label']} · {territory_label}"
with copy_slot:
    ui.hero_copy(period_chip, headline, module.description)


def value_text(value, ind) -> str:
    return charts.fmt_value(value, ind)


map_values = charts.province_values(national, indicator.key).set_index("provincia_codigo")[indicator.key].astype(float).to_dict()
with map_slot:
    ui.hero_map(map_values, province_names, selected_codes, indicator.label, lambda v: value_text(v, indicator))


# ---------------------------------------------------------------------------
# Headline indicators
# ---------------------------------------------------------------------------
def kpi_cards() -> list[dict]:
    filters_active = bool(selected_provinces or selected_programs)
    share_label = "del total nacional" if selected_provinces else "del total del ámbito"
    reference = national_stats if selected_provinces else scope_stats

    def share(key):
        value, whole = stats.get(key), reference.get(key)
        return value / whole * 100 if filters_active and value is not None and whole else None

    cards = [{"label": people.label, "value": stats["usuarios"], "icon": people.icon, "tone": "morado",
              "share": share("usuarios"), "share_label": share_label}]
    if module.extra:
        for extra in module.extra:
            cards.append({"label": extra.label, "value": stats[extra.key], "icon": extra.icon, "tone": "violeta",
                          "share": share(extra.key), "share_label": share_label})
    else:
        active = int(filtered.groupby("programa_id").usuarios.sum().gt(0).sum())
        total = int(filtered.programa_id.nunique())
        cards.append({"label": f"{module.items.capitalize()} con {people.label.lower()}", "value": active, "icon": "layers",
                      "tone": "violeta", "note": f"De {total} {module.items if total != 1 else module.item} en la selección"})
    for role, icon, tone in [("fiscal", "banknote", "oro"), ("government", "landmark", "fucsia")]:
        key = money[role].key
        cards.append({"label": money[role].label, "value": (stats[key] or 0) / 1e6, "decimals": 1, "prefix": "USD",
                      "suffix": "millones", "icon": icon, "tone": tone, "share": share(key), "share_label": share_label})
    return cards


ui.kpi_grid(kpi_cards())


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
TABLE_LEVELS = {f"Por {module.item}": ["programa"], "Por provincia": ["provincia"],
                f"Por provincia y {module.item}": ["provincia", "programa"]}


def with_share(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    total = frame.usuarios.sum()
    frame["participacion"] = (frame.usuarios.astype(float) / total * 100) if total else 0.0
    return frame.sort_values("usuarios", ascending=False)


def display_table(frame: pd.DataFrame, key: str, height: int | str = "auto") -> None:
    if COMPACT and "programa" in frame:
        frame = frame.assign(programa=frame.programa.map(lambda name: short_programs.get(name, name)))
    columns = {
        "provincia": ("Provincia", "text", 190),
        "programa": (module.item.capitalize(), "text", 292),
        "usuarios": (people.label, "int", None, None, people.label),
        "participacion": ("Participación", "pct", None, None, "Peso"),
    }
    for extra in module.extra:
        columns[extra.key] = (extra.label, "int", 156, None, extra.compact.split()[0])
    columns.update({
        money["fiscal"].key: (f"{money['fiscal'].label} (USD)", "money"),
        money["previous"].key: (f"{money['previous'].compact} (USD)", "money"),
        money["government"].key: (f"{money['government'].compact} (USD)", "money"),
    })
    if frame["presupuesto_ejecutado"].notna().any() and not executed_available:
        columns["presupuesto_ejecutado"] = ("Presupuesto ejecutado (USD)", "money")
    if frame.get("presupuesto_codificado", pd.Series(dtype=float)).notna().any():
        columns["presupuesto_codificado"] = ("Presupuesto codificado (USD)", "money")
        columns["porcentaje_ejecucion"] = ("Ejecución (%)", "pct")
    ui.data_table(frame, columns, height=height, key=key, bar="participacion")


@st.cache_data(show_spinner=False, max_entries=24)
def table_workbook(detail: pd.DataFrame, module_id: str, year: int, subtitle: str, selection: str, period_label: str) -> bytes:
    """The results table as an institutional Excel sheet; it opens well whatever the regional settings."""
    from src.reports import table_xlsx
    mod = MODULES[module_id]
    cash = mod.money(year, executed=detail["presupuesto_ejecutado"].notna().all())
    layout = [("Provincia", "provincia", "text", 26.0), (mod.item.capitalize(), "programa", "text", 36.0),
              (mod.people, "usuarios", "int", 14.0), ("Participación", "participacion", "pct", 12.0)]
    layout += [(extra.label, extra.key, "int", 13.0) for extra in mod.extra]
    layout += [(f"{cash['fiscal'].label} (USD)", cash["fiscal"].key, "usd", 19.0),
               (f"{cash['previous'].label} (USD)", cash["previous"].key, "usd", 21.0),
               (f"{cash['government'].label} (USD)", cash["government"].key, "usd", 21.0)]
    if detail.get("presupuesto_codificado", pd.Series(dtype=float)).notna().any():
        layout += [("Presupuesto codificado (USD)", "presupuesto_codificado", "usd", 21.0)]
    layout = [item for item in layout if item[1] in detail]
    records = []
    for item in detail.to_dict("records"):
        record = {k: (None if not isinstance(v, str) and pd.isna(v) else v) for k, v in item.items()}
        record["participacion"] = (record.get("participacion") or 0) / 100
        records.append(record)
    return table_xlsx(records, layout, title="Cuadro de resultados", subtitle=subtitle, period_label=period_label,
                      selection=selection, sheet="Resultados")


def dashboard() -> None:
    if stats["porcentaje_ejecucion"] is not None:
        ui.info_note(f"El devengado representa el {ui.number(stats['porcentaje_ejecucion'], 2)} % del presupuesto codificado "
                     f"de USD {ui.number(stats['presupuesto_codificado'] / 1e6, 2)} millones para esta selección.",
                     "Ejecución fiscal al corte")
    ui.section_heading(f"Resultados por {module.item}", context_label, "chart")
    if module.extra:
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_people"):
            ui.chart_title(f"{people.label} por {module.item}", "Número de personas")
            show_chart(charts.category_bars(filtered, people, short_programs), "category_people")
        extra = module.extra[0]
        with right, st.container(border=True, key="card_extra"):
            ui.chart_title(f"{extra.label} por {module.item}", "Número de unidades")
            show_chart(charts.category_bars(filtered, extra, short_programs), "category_extra")
        with st.container(border=True, key="card_budget"):
            ui.chart_title(f"Presupuesto por {module.item}", f"Millones de USD · {money['previous'].label} y {money['fiscal'].label.lower()}")
            show_chart(charts.resources_stack(filtered, money, short_programs), "category_budget")
    else:
        left, right = st.columns(2, gap="medium")
        with left, st.container(border=True, key="card_people"):
            ui.chart_title(f"{people.label} por {module.item}", "Número de personas")
            show_chart(charts.category_bars(filtered, people, short_programs), "category_people")
        with right, st.container(border=True, key="card_budget"):
            ui.chart_title(f"Presupuesto por {module.item}", f"Millones de USD · {money['previous'].label} y {money['fiscal'].label.lower()}")
            show_chart(charts.resources_stack(filtered, money, short_programs), "category_budget")

    ui.section_heading("Resultados por provincia", f"{indicator.label} · {period['label']}", "map")
    share_label = "del total nacional"
    rank_col, matrix_col = st.columns([1, 1.15], gap="medium")
    with rank_col, st.container(border=True, key="card_rank"):
        ui.chart_title(f"{indicator.label} por provincia",
                       "Provincias seleccionadas en dorado" if selected_codes else "Provincias ordenadas de mayor a menor")
        show_chart(charts.province_ranking(national, indicator, highlight=selected_codes, share_label=share_label), "province_ranking")
    with matrix_col, st.container(border=True, key="card_matrix"):
        ui.chart_title(f"Distribución por {module.item}", f"Participación de cada {module.item} en la provincia")
        matrix = charts.composition_matrix(national, indicator, short_programs, highlight=selected_codes)
        if COMPACT:
            # A fixed size (not autosized) keeps Plotly from shrinking it to the scroll container on a resize.
            matrix.update_layout(width=760, autosize=False)
            st.plotly_chart(matrix, width="content", theme=None, key="province_matrix",
                            config={**PLOTLY_CONFIG, "displayModeBar": False, "responsive": False})
        else:
            show_chart(matrix, "province_matrix")

    ui.section_heading("Cuadro de resultados", context_label, "table")
    if st.session_state.get("detail_level") not in TABLE_LEVELS:
        st.session_state["detail_level"] = next(iter(TABLE_LEVELS))
    level = st.segmented_control("Nivel de detalle", list(TABLE_LEVELS), key="detail_level", required=True,
                                 width="stretch" if COMPACT else "content")
    detail = with_share(aggregate(filtered, TABLE_LEVELS[level]))
    with st.container(border=True, key="card_detail"):
        display_table(detail, key="detail_table", height=min(640, 35 * (len(detail) + 1) + 3))
        sheet_subtitle = f"{period['label']} · {module.label} · {territory_label} · {level.lower()}"
        st.download_button("Descargar cuadro en Excel",
                           table_workbook(detail, module.id, period["year"], sheet_subtitle, selection_hash, period["label"]),
                           file_name=f"MTDH_cuadro_{module.id}_{period_id}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/table_view:",
                           key="detail_xlsx", type="primary")
    from src.institutional import show_institutional
    show_institutional(period_id)


# ---------------------------------------------------------------------------
# Report center
# ---------------------------------------------------------------------------
PRODUCTS = {
    "Resumen ejecutivo": {"label": ":material/picture_as_pdf: Resumen ejecutivo", "kind": "resumen", "ext": "pdf",
                          "mime": "application/pdf", "slug": "resumen",
                          "note": "Una página en PDF con las cifras clave, el mapa, los resultados por programa y los aspectos destacados."},
    "Presentación": {"label": ":material/slideshow: Presentación", "kind": "presentacion", "ext": "pptx",
                     "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "slug": "presentacion",
                     "note": "Tres diapositivas editables en PowerPoint: cifras clave, resultados por provincia y por programa."},
    "Libro de datos": {"label": ":material/table_view: Libro de datos", "kind": "datos", "ext": "xlsx",
                       "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "slug": "datos",
                       "note": "Libro de Excel con resumen, resultados por programa y por provincia, detalle con filtros y ficha técnica."},
}


def data_sheets() -> list[str]:
    return ["Resumen", module.items.capitalize(), "Provincias", "Detalle", "Ficha técnica"]


def report_contents(kind: str) -> list[tuple[str, str, str]]:
    if kind == "datos":
        return [("grid", "Resumen", "Cifras clave, mapa y aspectos destacados"),
                ("chart", module.items.capitalize(), f"{people.label}, participación y presupuesto por {module.item}"),
                ("map", "Provincias", "Posición de cada provincia en el país"),
                ("table", "Detalle", f"Cada {module.item} en cada provincia, con filtros y totales"),
                ("shield", "Ficha técnica", "Periodo, ámbito, territorio e indicadores")]
    if kind == "presentacion":
        return [("grid", "Cifras clave", "Portada con los indicadores principales"),
                ("map", "Resultados por provincia", "Mapa y provincias con mayor cobertura"),
                ("chart", f"Resultados por {module.item}", "Gráfico editable y aspectos destacados")]
    return [("grid", "Cifras clave", "Indicadores principales del periodo"),
            ("map", "Territorio", "Mapa y provincias con mayor cobertura"),
            ("chart", f"Resultados por {module.item}", f"{people.label} por {module.item}"),
            ("award", "Aspectos destacados", "Tres conclusiones para la toma de decisiones")]


def report_center() -> None:
    ui.section_heading("Centro de reportes", "Productos institucionales con el periodo, el ámbito y el territorio seleccionados.", "document")
    left, right = st.columns([1, 1.08], gap="large")
    with left, st.container(border=True, key="card_report_form"):
        ui.chart_title("Configuración del reporte", "Producto y título")
        product = st.segmented_control("Producto", list(PRODUCTS), format_func=lambda k: PRODUCTS[k]["label"],
                                       default="Resumen ejecutivo", key="report_product", required=True, width="stretch")
        spec = PRODUCTS[product]
        st.caption(spec["note"])
        title = st.text_input("Título", value=module.label, max_chars=80, key=f"report_title_{module.id}").strip() or module.label
        ui.scope_chips([("Periodo", period["label"]), ("Ámbito", module.label), ("Territorio", territory_label),
                        (module.items.capitalize(), programs_label)])
        # A fresh fingerprint prevents a previously generated download from surviving a change of selection.
        digest = hashlib.sha256(pd.util.hash_pandas_object(filtered, index=True).values.tobytes()
                                + json.dumps({"title": title, "product": product}, sort_keys=True).encode()).hexdigest()
        name = product.lower()
        if st.button(f"Generar {name}", type="primary", icon=":material/auto_awesome:", width="stretch", key="generate_report"):
            with st.spinner("Preparando el documento…"):
                try:
                    from src.reports import build_report_context, generate_pdf, generate_pptx, generate_xlsx
                    context = build_report_context(filtered, national=national, title=title, period_label=period["label"],
                                                   territory_label=territory_label, programs_label=programs_label,
                                                   selected_codes=selected_codes)
                    generator = {"resumen": generate_pdf, "presentacion": generate_pptx, "datos": generate_xlsx}[spec["kind"]]
                    st.session_state.generated_report = {"digest": digest, "content": generator(context)}
                except Exception as exc:  # noqa: BLE001 - shown to the operator with its reason
                    st.session_state.pop("generated_report", None)
                    ui.info_note(f"No se pudo generar el documento: {exc}", "Revise la selección e intente nuevamente", tone="warn")
        generated = st.session_state.get("generated_report", {})
        if generated.get("digest") == digest:
            ui.info_note("El documento conserva el periodo, el ámbito y el territorio seleccionados.", f"{product} listo", tone="ok")
            st.download_button(f"Descargar {name}", generated["content"],
                               file_name=f'MTDH_{spec["slug"]}_{module.id}_{period_id}.{spec["ext"]}', mime=spec["mime"],
                               icon=":material/download:", type="primary", width="stretch", key="download_report")
    with right:
        kpis = []
        for card in kpi_cards():
            text = ui.number(card["value"], card.get("decimals", 0))
            if card.get("prefix"):
                text = f"{card['prefix']} {text} M"
            kpis.append((card["label"], text, card["icon"]))
        ui.report_preview(spec["kind"], title, period["label"], territory_label, kpis, data_sheets(), selected_codes, map_values)
        ui.content_list(report_contents(spec["kind"]))


if st.session_state.workspace == "Tablero":
    dashboard()
else:
    report_center()

ui.footer(period["label"])
