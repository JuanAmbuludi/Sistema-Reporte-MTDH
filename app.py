"""InfoReportes MTDH: tablero estadístico y centro de reportes institucionales.

Run from the repository root with ``streamlit run app.py``.
All views and report exports receive the same filtered, validated snapshot.
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
from src.data import DEFAULT_DATA_DIR, aggregate, filter_data, load_data, load_manifest, summarize
from src.reference_views import render_references

ui.inject_styles()
user = require_login()
COMPACT = ui.is_mobile()

SCOPES = {
    "Panorama integral": None,
    "Bonos y pensiones": ["bonos_pensiones"],
    "Protección integral": ["proteccion_integral"],
}
WORKSPACES = {"Tablero": ":material/insights: Tablero", "Reportes": ":material/description: Reportes"}
PLOTLY_CONFIG = {
    "displaylogo": False, "scrollZoom": False, "doubleClick": False, "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d", "zoom2d", "pan2d", "zoomIn2d", "zoomOut2d",
                               "resetScale2d", "zoomInGeo", "zoomOutGeo", "resetGeo", "hoverClosestGeo", "toggleHover"],
    "toImageButtonOptions": {"format": "png", "filename": "MTDH_InfoReportes", "scale": 2},
}


@st.cache_data(show_spinner=False)
def read_snapshot(version: int):
    """Invalidated when the authoritative parquet changes."""
    return load_data(), load_manifest()


def clear_filters() -> None:
    st.session_state["selected_provinces"] = []
    st.session_state["selected_programs"] = []


def show_chart(figure, key: str) -> None:
    config = {**PLOTLY_CONFIG, "displayModeBar": False} if COMPACT else PLOTLY_CONFIG
    st.plotly_chart(figure, width="stretch", theme=None, key=key, config=config)


def money_millions(value) -> str:
    return "No disponible" if value is None or pd.isna(value) else f"USD {ui.millions(value)} M"


try:
    data_path = DEFAULT_DATA_DIR / "indicadores.parquet"
    manifest_path = DEFAULT_DATA_DIR / "manifest.json"
    snapshot_version = max(data_path.stat().st_mtime_ns, manifest_path.stat().st_mtime_ns)
    data, manifest = read_snapshot(snapshot_version)
except (FileNotFoundError, ValueError, OSError) as exc:
    ui.info_note("No se pudo abrir la base validada. Genera los datos con scripts/build_data.py y vuelve a cargar la aplicación.",
                 "Base de datos no disponible", tone="warn")
    st.code(str(exc), language=None)
    st.stop()

period_label = manifest.get("periodo_label", "Corte vigente")
fiscal_year = int(data.anio.iloc[0])
source_file = manifest.get("fuente", {}).get("archivo", "Fuente institucional")
province_names = data.drop_duplicates("provincia_codigo").set_index("provincia_codigo").provincia.to_dict()
# Chart-length program names (official names stay in tables, except on phones where the label column is narrow).
short_programs = {row.programa: theme.program_label(row.programa_id, row.programa)
                  for row in data.drop_duplicates("programa_id").itertuples()}
st.session_state.setdefault("scope_label", "Panorama integral")
st.session_state.setdefault("workspace", "Tablero")

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
            scope_label = st.segmented_control("Ámbito de la consulta", list(SCOPES), key="scope_label", required=True, width="stretch")
            sections = SCOPES[scope_label]
            scoped = filter_data(data, secciones=sections)
            province_options = list(scoped.drop_duplicates("provincia_codigo").sort_values("provincia_codigo").provincia_codigo)
            province_options.sort(key=lambda c: (c == geo.NO_POLYGON, province_names[c]))
            program_frame = scoped[["programa_id", "programa", "seccion"]].drop_duplicates()
            program_lookup = program_frame.set_index("programa_id").programa.to_dict()
            program_order = list(program_frame.sort_values(["seccion", "programa"]).programa_id)
            # Scope changes must not leave hidden, stale selections in another section.
            for key, available in [("selected_provinces", province_options), ("selected_programs", program_order)]:
                if key in st.session_state:
                    st.session_state[key] = [v for v in st.session_state[key] if v in available]
            col_territory, col_program = st.columns(2, gap="small")
            with col_territory:
                selected_provinces = st.multiselect("Territorio", province_options, format_func=province_names.get,
                                                    placeholder="Todo el país", key="selected_provinces")
            with col_program:
                selected_programs = st.multiselect("Programa o servicio", program_order, format_func=program_lookup.get,
                                                   placeholder="Todos los programas", key="selected_programs")
            if selected_provinces or selected_programs:
                st.button("Ver todo el país y todos los programas", icon=":material/restart_alt:", on_click=clear_filters,
                          type="tertiary", key="reset_filters")
    map_slot = hero_right.empty()

filtered = filter_data(scoped, provincias=selected_provinces or None, programas=selected_programs or None)
if filtered.empty:
    ui.info_note("La combinación elegida no tiene registros. Cambia el territorio o el programa para continuar.",
                 "Sin datos para esta selección", tone="warn")
    st.stop()

stats = summarize(filtered)
national = summarize(filter_data(scoped, programas=selected_programs or None))
scope_total = summarize(scoped)
active_sections = set(filtered.seccion)
filters_active = bool(selected_provinces or selected_programs)
selected_codes = set(selected_provinces)
selection_hash = hashlib.sha256(pd.util.hash_pandas_object(filtered, index=True).values.tobytes()).hexdigest()[:10]

if len(selected_provinces) == 1:
    headline = f"Protección social en {province_names[selected_provinces[0]]}"
    territory_label = province_names[selected_provinces[0]]
elif selected_provinces:
    headline = f"Protección social en {len(selected_provinces)} territorios"
    territory_label = f"{len(selected_provinces)} territorios"
else:
    headline = "Protección social, provincia por provincia"
    territory_label = "Cobertura nacional"
program_count = stats["programas"]
province_count = stats["provincias"]
zone_included = filtered.provincia_codigo.eq(geo.NO_POLYGON).any()
lead = (f"{scope_label}: {program_count} {'programa' if program_count == 1 else 'programas'} con presencia en "
        f"{province_count} {'provincia' if province_count == 1 else 'provincias'}"
        + (" y la zona en estudio." if zone_included else "."))
with copy_slot:
    ui.hero_copy(period_label, headline, lead)

map_data = filter_data(scoped, programas=selected_programs or None)
map_values = charts.province_values(map_data, "usuarios").set_index("provincia_codigo")["usuarios"].astype(float).to_dict()
zone_value = map_values.get(geo.NO_POLYGON)
zone_note = f"Zona en estudio: {ui.number(zone_value)} registros sin polígono en el mapa." if zone_value else ""
with map_slot:
    ui.hero_map(map_values, province_names, selected_codes, "Cobertura reportada", zone_note=zone_note)


# ---------------------------------------------------------------------------
# Headline indicators
# ---------------------------------------------------------------------------
def share_of(value, base):
    if not filters_active or value is None or not base:
        return None
    return value / base * 100


def kpi_cards() -> list[dict]:
    bonos_programs = filtered.loc[filtered.seccion.eq("bonos_pensiones"), "programa_id"].nunique()
    service_programs = filtered.loc[filtered.seccion.eq("proteccion_integral"), "programa_id"].nunique()
    fiscal = {"label": f"Monto fiscal {fiscal_year}", "value": (stats["monto_fiscal"] or 0) / 1e6, "decimals": 1,
              "prefix": "USD", "suffix": "millones", "icon": "banknote", "tone": "oro",
              "note": f"Acumulado de gobierno: USD {ui.millions(stats['monto_gobierno'])} millones",
              "share": share_of(stats["monto_fiscal"], national["monto_fiscal"] if selected_provinces else scope_total["monto_fiscal"])}
    government = {"label": "Acumulado de gobierno", "value": (stats["monto_gobierno"] or 0) / 1e6, "decimals": 1,
                  "prefix": "USD", "suffix": "millones", "icon": "landmark", "tone": "violeta",
                  "note": f"Incluye el acumulado 2023–{fiscal_year - 1} y el monto fiscal {fiscal_year}",
                  "share": share_of(stats["monto_gobierno"], national["monto_gobierno"] if selected_provinces else scope_total["monto_gobierno"])}
    base_label = "del total nacional" if selected_provinces else "del total del ámbito"
    beneficiaries = {"label": "Beneficiarios de bonos y pensiones", "value": stats["beneficiarios"], "icon": "hand-coins",
                     "tone": "morado", "note": f"{bonos_programs} {'programa' if bonos_programs == 1 else 'programas'} de transferencias monetarias",
                     "share": share_of(stats["beneficiarios"], national["beneficiarios"] if selected_provinces else scope_total["beneficiarios"]),
                     "share_label": base_label}
    users = {"label": "Usuarios de servicios de protección integral", "value": stats["usuarios_servicios"], "icon": "users",
             "tone": "fucsia", "note": f"{service_programs} {'servicio' if service_programs == 1 else 'servicios'} de atención directa",
             "share": share_of(stats["usuarios_servicios"], national["usuarios_servicios"] if selected_provinces else scope_total["usuarios_servicios"]),
             "share_label": base_label}
    units = {"label": "Unidades de atención", "value": stats["unidades"], "icon": "building", "tone": "violeta",
             "note": "Reportadas por los servicios de protección integral",
             "share": share_of(stats["unidades"], national["unidades"] if selected_provinces else scope_total["unidades"]),
             "share_label": base_label}
    fiscal["share_label"] = government["share_label"] = base_label
    if active_sections == {"bonos_pensiones"}:
        covered = filtered.groupby("programa_id").usuarios.sum().gt(0).sum()
        programs = {"label": "Programas con beneficiarios", "value": int(covered), "icon": "layers", "tone": "fucsia",
                    "note": f"De {bonos_programs} programas en la selección; los demás conservan saldos históricos"}
        return [beneficiaries, fiscal, government, programs]
    if active_sections == {"proteccion_integral"}:
        return [users, units, fiscal, government]
    return [beneficiaries, users, units, fiscal]


ui.kpi_grid(kpi_cards())


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def display_table(frame: pd.DataFrame, height: int | str = "auto", key: str | None = None) -> None:
    # Amounts follow the budget strip: previous accumulated + fiscal amount = government accumulated.
    # Execution only takes a column when the selection has verified figures; the strip above already says when it does not.
    if "presupuesto_ejecutado" in frame and pd.to_numeric(frame.presupuesto_ejecutado, errors="coerce").isna().all():
        frame = frame.drop(columns="presupuesto_ejecutado")
    if COMPACT and "programa" in frame:
        frame = frame.assign(programa=frame.programa.map(lambda name: short_programs.get(name, name)))
    meaning = theme.definitions(fiscal_year)
    ui.data_table(frame, {
        "provincia": ("Provincia o territorio", "text", 190),
        "programa": ("Programa o servicio", "text", 292),
        "usuarios": ("Beneficiarios y usuarios", "int", None, meaning["usuarios"], "Cobertura"),
        "participacion": ("Participación", "pct", None, "Peso de cada fila en los beneficiarios y usuarios de la tabla.", "Peso"),
        "unidades": ("Unidades de atención", "int", None, meaning["unidades"], "Unidades"),
        # Amounts are in USD (said in the caption and the header help), which keeps the table inside the card.
        "monto_anterior": (f"Acumulado 2023–{fiscal_year - 1}", "money", None, meaning["monto_anterior"]),
        "monto_fiscal": (f"Monto fiscal {fiscal_year}", "money", None, meaning["monto_fiscal"]),
        "monto_gobierno": ("Acumulado de gobierno", "money", None, meaning["monto_gobierno"]),
        "presupuesto_ejecutado": ("Presupuesto ejecutado", "money", None, meaning["presupuesto_ejecutado"]),
    }, height=height, key=key, bar="participacion")


@st.cache_data(show_spinner=False, max_entries=24)
def detail_workbook(detail: pd.DataFrame, subtitle: str, selection: str) -> bytes:
    """The detail table as an institutional Excel sheet; it opens well whatever the regional settings."""
    from src.reports import table_xlsx
    layout = [("Provincia o territorio", "provincia", "text", 26.0), ("Programa o servicio", "programa", "text", 36.0),
              ("Beneficiarios y usuarios", "usuarios", "int", 14.0), ("Participación", "participacion", "pct", 12.0),
              ("Unidades de atención", "unidades", "units", 12.5),
              (f"Acumulado 2023–{fiscal_year - 1} (USD)", "monto_anterior", "usd", 19.0),
              (f"Monto fiscal {fiscal_year} (USD)", "monto_fiscal", "usd", 19.0),
              ("Acumulado de gobierno (USD)", "monto_gobierno", "usd", 19.0),
              ("Presupuesto ejecutado (USD)", "presupuesto_ejecutado", "usd", 19.0)]
    layout = [item for item in layout if item[1] in detail]
    records = []
    for item in detail.to_dict("records"):
        record = {k: (None if not isinstance(v, str) and pd.isna(v) else v) for k, v in item.items()}
        record["participacion"] = (record.get("participacion") or 0) / 100
        records.append(record)
    return table_xlsx(records, layout, title="Detalle verificable", subtitle=subtitle,
                      period_label=period_label, selection=selection,
                      note="Una misma persona puede constar en más de un programa; los conteos no se suman como personas únicas. "
                           "N/D: dato no disponible. No aplica: unidades de atención en bonos y pensiones.")


def with_share(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    total = frame.usuarios.sum()
    frame["participacion"] = (frame.usuarios.astype(float) / total * 100) if total else 0.0
    return frame.sort_values("usuarios", ascending=False)


def dashboard() -> None:
    ui.section_heading("Cobertura por programa", "Beneficiarios y usuarios reportados en el corte, junto con los recursos acumulados de cada programa.", "chart")
    left, right = st.columns(2, gap="medium")
    with left, st.container(border=True, key="card_coverage"):
        ui.chart_title("Cobertura reportada", "Personas registradas por programa o servicio", period_label)
        show_chart(charts.program_bars(filtered), "program_coverage")
    with right, st.container(border=True, key="card_budget"):
        ui.chart_title("Recursos acumulados por programa", f"Acumulado de gobierno = acumulado 2023–{fiscal_year - 1} + monto fiscal {fiscal_year}", "Millones de USD")
        show_chart(charts.budget_stack(filtered), "program_budget")
    ui.info_note("Los conteos son agregados por programa. Una misma persona puede figurar en más de uno, por eso no se suman como personas únicas.")

    ui.section_heading("Recursos", "Montos tomados de la fuente y expresados en USD. No equivalen a transferencias mensuales.", "banknote")
    execution = stats["presupuesto_ejecutado"]
    ui.budget_strip([
        (f"Acumulado 2023–{fiscal_year - 1}", f"USD {ui.millions(stats['monto_anterior'])}", "millones", "Saldo reportado de años anteriores", True),
        (f"Monto fiscal {fiscal_year}", f"USD {ui.millions(stats['monto_fiscal'])}", "millones", f"Columna Presupuesto {fiscal_year} de la fuente", True),
        ("Acumulado de gobierno", f"USD {ui.millions(stats['monto_gobierno'])}", "millones", "Suma del acumulado previo y el monto fiscal", True),
        ("Presupuesto ejecutado", f"USD {ui.millions(execution)}" if execution is not None else "No disponible", "millones",
         "Ejecución verificada" if execution is not None else "La fuente no certifica la fase de ejecución", execution is not None),
    ])
    if execution is None and stats.get("presupuesto_ejecutado_parcial") is not None:
        st.caption(f"Hay ejecución verificada para {ui.number(stats['ejecucion_cobertura_pct'], 1)} % de las filas "
                   f"({ui.money(stats['presupuesto_ejecutado_parcial'])}). Ese monto parcial no se presenta como total.")
    fiscal_by_program = aggregate(filtered, ["seccion", "programa_id", "programa"]).sort_values("monto_fiscal", ascending=False)
    fiscal_total = fiscal_by_program.monto_fiscal.sum()
    if fiscal_total and fiscal_total > 0:
        tree, legend = st.columns([1.35, 1], gap="medium")
        with tree, st.container(border=True, key="card_treemap"):
            ui.chart_title(f"¿Cómo se distribuye el monto fiscal {fiscal_year}?", "Cada bloque es proporcional al monto del programa", money_millions(fiscal_total))
            show_chart(charts.fiscal_treemap(filtered), "fiscal_treemap")
        with legend, st.container(border=True, key="card_share"):
            ui.chart_title("Participación por programa", f"Porcentaje del monto fiscal {fiscal_year} de la selección")
            rows = []
            for row in fiscal_by_program.itertuples():
                if not row.monto_fiscal or row.monto_fiscal <= 0:
                    continue
                rows.append((theme.program_label(row.programa_id, row.programa), row.monto_fiscal / fiscal_total * 100,
                             f"USD {ui.millions(row.monto_fiscal)} M", theme.SECTION_COLORS[row.seccion]))
            ui.share_list(rows)
            zero = [theme.program_label(r.programa_id, r.programa) for r in fiscal_by_program.itertuples() if not r.monto_fiscal]
            if zero:
                st.caption("Sin monto fiscal en el corte: " + ", ".join(zero) + ". Conservan saldos en el acumulado de gobierno.")

    ui.section_heading("Territorio", "Ubica la cobertura y los recursos en el mapa, compara provincias y revisa la composición de cada una.", "map")
    options = ["Cobertura reportada", f"Monto fiscal {fiscal_year}"] + (["Unidades de atención"] if "proteccion_integral" in active_sections else [])
    if st.session_state.get("territorial_metric") not in options:
        st.session_state["territorial_metric"] = options[0]
    metric_label = st.segmented_control("Indicador del mapa", options, key="territorial_metric", required=True,
                                        width="stretch" if COMPACT else "content")
    metric_key = {"Cobertura reportada": "usuarios", f"Monto fiscal {fiscal_year}": "monto_fiscal", "Unidades de atención": "unidades"}[metric_label]

    def by_metric(frame: pd.DataFrame) -> pd.DataFrame:
        return frame if metric_key != "unidades" else frame.loc[frame.seccion.eq("proteccion_integral")]

    terrain = by_metric(filtered)
    # With territories chosen, the map and the ranking keep the whole country as context and mark the selection in gold.
    context = by_metric(map_data) if selected_provinces else terrain
    chosen_names = [province_names[c] for c in selected_provinces]
    if len(chosen_names) == 1:
        chosen_text = f"{chosen_names[0]} aparece en oro"
    elif chosen_names:
        chosen_text = "Los territorios elegidos aparecen en oro"
    share_label = "del total nacional" if selected_provinces else "de la selección"
    map_col, rank_col = st.columns([1.25, 1], gap="medium")
    with map_col, st.container(border=True, key="card_map"):
        subtitle = (f"{chosen_text}; el resto del país sirve de referencia" if selected_provinces
                    else "Toca o pasa el cursor sobre una provincia para ver su valor")
        ui.chart_title(f"{metric_label} por provincia", subtitle, "Mapa")
        show_chart(charts.province_map(context, metric_key, compact=COMPACT, highlight=selected_codes, share_label=share_label), "province_map")
    with rank_col, st.container(border=True, key="card_rank"):
        if selected_provinces:
            ui.chart_title("Posición en el país", f"{chosen_text}, con su lugar entre las provincias")
        else:
            ui.chart_title("Ranking territorial", "Las tres provincias con mayor valor se destacan en morado")
        show_chart(charts.province_bars(context, metric_key, highlight=selected_codes, share_label=share_label), "province_bars")
    zone = context.loc[context.provincia_codigo.eq(geo.NO_POLYGON), metric_key].sum()
    if zone and zone > 0:
        st.caption(f"Zona en estudio: {charts.fmt_value(zone, metric_key)}. Se incluye en los totales y el ranking, pero no tiene polígono en el mapa.")
    with st.container(border=True, key="card_matrix"):
        if len(chosen_names) == 1:
            ui.chart_title(f"Composición de {chosen_names[0]}", "Porcentaje que aporta cada programa en la provincia; el valor exacto aparece al pasar el cursor", "Mapa de calor")
        else:
            ui.chart_title("Composición de cada territorio", "Porcentaje que aporta cada programa dentro de la provincia; el detalle aparece al pasar el cursor", "Mapa de calor")
        matrix = charts.territorial_matrix(terrain, metric_key)
        if COMPACT:
            # Phones scroll the matrix sideways instead of squeezing twelve columns.
            # A fixed size (not autosized) keeps Plotly from shrinking it to the scroll container on a resize.
            matrix.update_layout(width=760, autosize=False)
            st.plotly_chart(matrix, width="content", theme=None, key="province_matrix",
                            config={**PLOTLY_CONFIG, "displayModeBar": False, "responsive": False})
        else:
            show_chart(matrix, "province_matrix")
    abbreviations = sorted({(theme.PROGRAM_ABBR[r.programa_id], r.programa) for r in terrain.drop_duplicates("programa_id").itertuples()})
    st.caption("Siglas: " + "; ".join(f"{a}: {name}" for a, name in abbreviations) + ".")

    ui.section_heading("Detalle verificable", "Las mismas cifras de los gráficos, listas para revisar, ordenar y descargar.", "table")
    level = st.segmented_control("Nivel de detalle", ["Por programa", "Por provincia", "Por provincia y programa"],
                                 default="Por programa", key="detail_level", required=True, width="stretch" if COMPACT else "content")
    groups = {"Por programa": ["programa"], "Por provincia": ["provincia"], "Por provincia y programa": ["provincia", "programa"]}[level]
    detail = with_share(aggregate(filtered, groups))
    with st.container(border=True, key="card_detail"):
        display_table(detail, height=min(640, 35 * (len(detail) + 1) + 3), key="detail_table")
        with st.container(horizontal=True, gap="small", key="detail_downloads"):
            sheet_subtitle = f"{period_label} · {scope_label} · {territory_label} · {level.lower()}"
            st.download_button("Descargar en Excel", detail_workbook(detail, sheet_subtitle, selection_hash),
                               file_name=f'MTDH_detalle_{manifest["periodo"][:7]}.xlsx',
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/table_view:",
                               key="detail_xlsx", type="primary")
            st.download_button("Descargar CSV", detail.drop(columns=["participacion"]).to_csv(index=False).encode("utf-8-sig"),
                               file_name=f'MTDH_detalle_{manifest["periodo"][:7]}.csv', mime="text/csv", icon=":material/download:",
                               key="detail_csv", help="Datos planos con separador de coma y punto decimal, para otros sistemas")
    st.caption("Montos en USD, con la precisión de la fuente. Guion: dato no disponible o no aplicable. El presupuesto ejecutado "
               "aparece como columna cuando la selección tiene ejecución verificada.")

    ui.section_heading("Fuentes, definiciones y calidad", "Qué mide cada cifra y qué controles superó la base antes de publicarse.", "shield")
    definitions = theme.definitions(fiscal_year)
    evidence = str(manifest.get("periodo_origen", "")).strip().rstrip(".")
    ui.definition_grid([
        ("users", "Beneficiarios y usuarios", definitions["usuarios"]),
        ("building", "Unidades de atención", definitions["unidades"]),
        ("banknote", f"Monto fiscal {fiscal_year}", definitions["monto_fiscal"]),
        ("landmark", "Acumulado de gobierno", definitions["monto_gobierno"]),
        ("wallet", "Presupuesto ejecutado", definitions["presupuesto_ejecutado"]),
        ("calendar", "Corte de la información", f"{period_label}. Evidencia registrada: {evidence}." if evidence else period_label),
    ])
    controls = manifest.get("control_calidad", {})
    ui.quality_badges([
        ("Registros del corte", ui.number(manifest.get("filas")), True),
        ("Claves duplicadas", ui.number(controls.get("claves_duplicadas", 0)), controls.get("claves_duplicadas", 0) == 0),
        ("Valores negativos", ui.number(controls.get("valores_negativos", 0)), controls.get("valores_negativos", 0) == 0),
        ("Acumulados no conciliados", ui.number(controls.get("acumulados_no_conciliados", 0)), controls.get("acumulados_no_conciliados", 0) == 0),
        ("Diferencias con la referencia 2025", ui.number(controls.get("diferencias_acumulado_2025", 0)), controls.get("diferencias_acumulado_2025", 0) == 0),
        ("Filas con ejecución verificada", ui.number(controls.get("ejecucion_disponible_filas", 0)), controls.get("ejecucion_disponible_filas", 0) > 0),
    ])
    sha = manifest.get("fuente", {}).get("sha256", "")
    st.caption(f"Fuente: {source_file}, hoja provincial. Huella SHA-256: {sha[:16]}… Filas seleccionadas: {stats['registros']}. "
               "Base agregada, sin identificadores personales. Las referencias históricas no se suman al corte vigente.")

    ui.section_heading("Referencias históricas y cantonales", "Otras hojas del Excel, con alcance propio. No se mezclan con el corte vigente.", "history")
    render_references(provincias=selected_provinces or None, programas=selected_programs or None, secciones=sections)


# ---------------------------------------------------------------------------
# Report center
# ---------------------------------------------------------------------------
FORMATS = {
    "Excel": {"label": ":material/table_view: Excel", "kind": "excel", "ext": "xlsx",
              "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "slug": "reporte"},
    "PDF": {"label": ":material/picture_as_pdf: PDF", "kind": "pdf", "ext": "pdf", "mime": "application/pdf", "slug": "boletin"},
    "Word": {"label": ":material/article: Word", "kind": "word", "ext": "docx",
             "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "slug": "boletin"},
    "PowerPoint": {"label": ":material/slideshow: PowerPoint", "kind": "ppt", "ext": "pptx",
                   "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "slug": "presentacion"},
}
FORMAT_NOTES = {
    "Excel": "Libro con portada, resumen ejecutivo, hojas por ámbito, mapa territorial, detalle filtrable y notas metodológicas.",
    "PDF": "Boletín listo para imprimir o enviar, con portada, indicadores, tablas, mapa y criterios de lectura.",
    "Word": "Documento editable con la misma estructura del boletín, para ajustar redacción antes de publicar.",
    "PowerPoint": "Presentación editable 16:9 con gráficos nativos, mapa territorial y notas para quien expone.",
}


def excel_sheets(include_territory: bool) -> list[str]:
    sheets = ["Portada", "Resumen"]
    if "bonos_pensiones" in active_sections:
        sheets.append("Bonos y pensiones")
    if "proteccion_integral" in active_sections:
        sheets.append("Protección integral")
    if include_territory:
        sheets.append("Territorio")
    return sheets + ["Detalle", "Notas"]


def report_contents(kind: str, include_territory: bool) -> list[tuple[str, str, str]]:
    if kind == "excel":
        items = [("grid", "Portada", "Título, corte, alcance, mapa y accesos a cada hoja"),
                 ("chart", "Resumen ejecutivo", "Indicadores clave, lectura del corte y gráficos nativos de Excel")]
        if "bonos_pensiones" in active_sections:
            items.append(("hand-coins", "Bonos y pensiones", "Tabla por programa con barras de participación y provincias principales"))
        if "proteccion_integral" in active_sections:
            items.append(("users", "Protección integral", "Usuarios, unidades de atención y recursos por servicio"))
        if include_territory:
            items.append(("map", "Territorio", "Mapa coroplético, ranking provincial y matriz de composición"))
        items += [("table", "Detalle", "Provincia por programa, con filtros y totales"),
                  ("shield", "Notas", "Definiciones, controles de calidad y trazabilidad de la fuente")]
        return items
    items = [("grid", "Portada e indicadores", "Cifras clave del corte y alcance territorial"),
             ("table", "Capítulos por ámbito", "Tablas por programa o servicio con totales de la selección")]
    if include_territory:
        items.append(("map", "Mapa y ranking territorial", "Distribución provincial de la cobertura reportada"))
    items.append(("shield", "Criterios de lectura", "Definiciones y advertencias de interpretación"))
    return items


def report_center() -> None:
    ui.section_heading("Centro de reportes", "Genera piezas institucionales con exactamente la misma selección del tablero.", "document")
    left, right = st.columns([1, 1.08], gap="large")
    with left, st.container(border=True, key="card_report_form"):
        ui.chart_title("Configura el reporte", "Formato, título y contenido territorial")
        output_format = st.segmented_control("Formato", list(FORMATS), format_func=lambda k: FORMATS[k]["label"],
                                             default="Excel", key="report_format", required=True, width="stretch")
        spec = FORMATS[output_format]
        st.caption(FORMAT_NOTES[output_format])
        title = st.text_input("Título del reporte", value="Boletín de protección social", max_chars=95, key="report_title").strip() \
            or "Boletín de protección social"
        include_territory = st.toggle("Incluir análisis territorial y mapa", value=True, key="include_territory")
        programs_label = (f"{len(selected_programs)} seleccionados" if selected_programs else f"Todos ({stats['programas']})")
        ui.scope_chips([("Ámbito", scope_label), ("Territorio", territory_label), ("Programas", programs_label), ("Corte", period_label)])
        options = {"title": title, "include_territory": include_territory}
        # A fresh fingerprint prevents a previously generated download from surviving a filter change.
        digest = hashlib.sha256(pd.util.hash_pandas_object(filtered, index=True).values.tobytes()
                                + json.dumps(options, sort_keys=True).encode() + output_format.encode()).hexdigest()
        if st.button(f"Generar {output_format}", type="primary", icon=":material/auto_awesome:", width="stretch", key="generate_report"):
            with st.spinner("Componiendo tablas, gráficos y mapa del reporte…"):
                try:
                    from src.reports import build_report_context, generate_docx, generate_pdf, generate_pptx, generate_xlsx
                    context = build_report_context(filtered, manifest, options=options)
                    generator = {"Excel": generate_xlsx, "PDF": generate_pdf, "Word": generate_docx, "PowerPoint": generate_pptx}[output_format]
                    st.session_state.generated_report = {"digest": digest, "content": generator(context)}
                except Exception as exc:  # noqa: BLE001 - shown to the operator with its reason
                    st.session_state.pop("generated_report", None)
                    ui.info_note(f"No se pudo generar el archivo: {exc}", "Revisa la selección e inténtalo de nuevo", tone="warn")
        generated = st.session_state.get("generated_report", {})
        if generated.get("digest") == digest:
            ui.info_note("El archivo conserva los filtros, las definiciones y los datos no disponibles de esta selección.",
                         f"{output_format} listo para descargar", tone="ok")
            st.download_button(f"Descargar {output_format}", generated["content"],
                               file_name=f'MTDH_{spec["slug"]}_{manifest["periodo"][:7]}.{spec["ext"]}', mime=spec["mime"],
                               icon=":material/download:", type="primary", width="stretch", key="download_report")
    with right:
        kpis = [(card["label"], (card.get("prefix", "") + " " + ui.number(card["value"], card.get("decimals", 0)) + (" M" if card.get("suffix") == "millones" else "")).strip())
                for card in kpi_cards()]
        ui.report_preview(spec["kind"], title, period_label, territory_label, kpis, excel_sheets(include_territory), selected_codes, map_values)
        ui.content_list(report_contents(spec["kind"], include_territory))
    ui.section_heading("Cifras que se incluirán", "Totales por programa de la selección actual, idénticos a los del archivo.", "table")
    with st.container(border=True, key="card_report_table"):
        display_table(with_share(aggregate(filtered, ["programa"])), key="report_table")
    st.caption("Montos en USD, con la precisión de la fuente. Guion: dato no disponible o no aplicable.")


if st.session_state.workspace == "Tablero":
    dashboard()
else:
    report_center()

ui.footer(period_label, source_file, selection_hash)
