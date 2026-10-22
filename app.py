"""MTDH statistical dashboard and report studio.

Run from the repository root with ``streamlit run app.py``.
All views and report exports receive the same filtered, validated snapshot.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MTDH · Estadística institucional", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

from src.auth import logout, require_login
from src.charts import PALETTE, budget_stack, fiscal_allocation, program_bars, province_bars, territorial_matrix
from src.data import DEFAULT_DATA_DIR, aggregate, filter_data, load_data, load_history, load_manifest, summarize
from src.reference_views import render_references
from src.ui import SECTIONS, chart_title, footer, hero, icon, info_note, inject_styles, metric, money, number, pretty_label, report_cover, section_heading

inject_styles()
user = require_login()


@st.cache_data(show_spinner=False)
def read_snapshot(version: int):
    """Invalidated when the authoritative parquet changes."""
    return load_data(), load_manifest()


@st.cache_data(show_spinner=False)
def read_references(version: int):
    return load_history()


def clear_filters() -> None:
    st.session_state["selected_provinces"] = []
    st.session_state["selected_programs"] = []


def show_chart(figure, key: str) -> None:
    st.plotly_chart(figure, width="stretch", theme=None, key=key, config={
        "displaylogo": False,
        "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"],
        "toImageButtonOptions": {"format": "png", "filename": "MTDH_estadistica", "scale": 2},
    })


def display_table(frame: pd.DataFrame, detail: bool = False) -> None:
    columns = [c for c in ["provincia", "programa", "usuarios", "unidades", "monto_fiscal", "monto_gobierno", "presupuesto_ejecutado"] if c in frame]
    st.dataframe(frame[columns], hide_index=True, width="stretch", column_config={
        "provincia": st.column_config.TextColumn("Provincia / territorio", width="medium"),
        "programa": st.column_config.TextColumn("Programa o servicio", width="large"),
        "usuarios": st.column_config.NumberColumn("Conteo reportado", format="localized"),
        "unidades": st.column_config.NumberColumn("Unidades de atención", format="localized"),
        "monto_fiscal": st.column_config.NumberColumn(f"Fiscal {fiscal_year} (USD)", format="dollar"),
        "monto_gobierno": st.column_config.NumberColumn("Acum. gobierno (USD)", format="dollar"),
        "presupuesto_ejecutado": st.column_config.NumberColumn("Ejecución verificada (USD)", format="dollar"),
    }, height=min(620, 40 + len(frame) * 35) if detail else "auto")


try:
    data_path = DEFAULT_DATA_DIR / "indicadores.parquet"
    manifest_path = DEFAULT_DATA_DIR / "manifest.json"
    snapshot_version = max(data_path.stat().st_mtime_ns, manifest_path.stat().st_mtime_ns)
    data, manifest = read_snapshot(snapshot_version)
except (FileNotFoundError, ValueError, OSError) as exc:
    st.error("No se pudo abrir la base validada. Genera los datos con el script scripts/build_data.py y vuelve a cargar la aplicación.")
    with st.expander("Detalle para administración"):
        st.code(str(exc))
    st.stop()

period_label = manifest.get("periodo_label", "Corte vigente")
fiscal_year = int(data.anio.iloc[0])
scope_options = {"Panorama integral": None, "Bonos y pensiones": ["bonos_pensiones"], "Protección integral": ["proteccion_integral"]}

with st.sidebar:
    st.markdown(f'<div class="sidebar-brand"><div class="sidebar-icon">{icon("dashboard",25)}</div><div><strong>MTDH</strong><span>ESTADÍSTICA</span></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-kicker">ALCANCE DE LA CONSULTA</div>', unsafe_allow_html=True)
    scope_label = st.selectbox("Sección", list(scope_options), key="scope_label")
    sections = scope_options[scope_label]
    scoped = filter_data(data, secciones=sections)
    st.markdown(f'<div class="sidebar-period"><strong>{html.escape(period_label)}</strong><span>Corte vinculado al boletín de referencia.<br/>Montos fiscales acumulados del año.</span></div>', unsafe_allow_html=True)
    province_options = sorted(scoped.provincia.dropna().unique())
    program_lookup = scoped[["programa_id", "programa"]].drop_duplicates().set_index("programa_id").programa.to_dict()
    # Scope changes must not leave hidden, stale selections in another section.
    for key, available in [("selected_provinces", province_options), ("selected_programs", list(program_lookup))]:
        if key in st.session_state:
            st.session_state[key] = [v for v in st.session_state[key] if v in available]
    selected_provinces = st.multiselect("Provincia o territorio", province_options, format_func=pretty_label, placeholder="Todos los territorios", key="selected_provinces")
    selected_programs = st.multiselect("Programa o servicio", list(program_lookup), format_func=program_lookup.get, placeholder="Todos los programas", key="selected_programs")
    st.caption("Sin selección se incluyen todas las opciones disponibles.")
    st.button("Restablecer filtros", icon=":material/restart_alt:", width="stretch", on_click=clear_filters)
    st.divider()
    st.markdown('<div class="sidebar-kicker">DOS MIRADAS, UNA MISMA BASE</div>', unsafe_allow_html=True)
    st.caption("Explora la información y genera un informe con exactamente los mismos filtros.")
    st.markdown(f'<div class="sidebar-user"><strong>{html.escape(user.get("name", user.get("username", "Usuario")))}</strong>Sesión autenticada</div>', unsafe_allow_html=True)
    st.button("Cerrar sesión", icon=":material/logout:", on_click=logout, width="stretch")

filtered = filter_data(scoped, provincias=selected_provinces or None, programas=selected_programs or None)
if filtered.empty:
    st.warning("La combinación seleccionada no tiene registros. Cambia los filtros para continuar.")
    st.stop()
stats = summarize(filtered)
territory_label = pretty_label(selected_provinces[0]) if len(selected_provinces) == 1 else f"{len(selected_provinces)} territorios seleccionados" if selected_provinces else "Cobertura nacional"
hero(period_label, territory_label)

if "workspace" not in st.session_state:
    st.session_state.workspace = "dashboard"
nav1, nav2 = st.columns(2, gap="small")
with nav1:
    if st.button("Dashboard estadístico", icon=":material/space_dashboard:", type="primary" if st.session_state.workspace == "dashboard" else "secondary", width="stretch"):
        st.session_state.workspace = "dashboard"
        st.rerun()
with nav2:
    if st.button("Centro de reportes", icon=":material/description:", type="primary" if st.session_state.workspace == "reports" else "secondary", width="stretch"):
        st.session_state.workspace = "reports"
        st.rerun()

zone = " + zona en estudio" if filtered.provincia_codigo.eq("90").any() else ""
st.markdown(f'<div class="scope-line"><span><strong>{html.escape(scope_label)}</strong> · {stats["programas"]} programas · {stats["provincias"]} provincias{zone}</span><span class="scope-badge">{html.escape(period_label)} · USD</span></div>', unsafe_allow_html=True)


def kpi_strip() -> None:
    cols = st.columns(4, gap="small")
    active_sections = set(filtered.seccion)
    if len(active_sections) == 2:
        with cols[0]: metric("Beneficiarios reportados", number(stats["beneficiarios"]), "Bonos y pensiones", "wallet")
        with cols[1]: metric("Usuarios reportados", number(stats["usuarios_servicios"]), "Servicios de protección integral", "users", "rose")
        with cols[2]: metric("Unidades de atención", number(stats["unidades"]), "Unidades reportadas por servicios", "building", "blue")
        with cols[3]: metric(f"Monto fiscal {fiscal_year}", money(stats["monto_fiscal"], True), "M = millones · presupuesto de la fuente", "chart", "slate", "USD")
    else:
        is_bonos = "bonos_pensiones" in active_sections
        with cols[0]: metric("Beneficiarios reportados" if is_bonos else "Usuarios reportados", number(stats["usuarios"]), "Suma de los programas seleccionados", "wallet" if is_bonos else "users")
        with cols[1]: metric(f"Monto fiscal {fiscal_year}", money(stats["monto_fiscal"], True), "M = millones · presupuesto de la fuente", "chart", "rose", "USD")
        with cols[2]: metric("Acumulado de gobierno", money(stats["monto_gobierno"], True), "Incluye acumulado previo y fiscal vigente", "wallet", "blue", "USD")
        with cols[3]: metric("Programas seleccionados" if is_bonos else "Unidades de atención", number(stats["programas"] if is_bonos else stats["unidades"]), "Unidades de atención: no aplica" if is_bonos else "Unidades reportadas por servicios", "building", "slate")


def dashboard() -> None:
    kpi_strip()
    info_note("Los conteos corresponden a agregados por programa; una misma persona puede figurar en más de uno. El insumo no permite identificar beneficiarios ni usuarios únicos.")
    section_heading("Alcance de la protección social", "Distribución de las coberturas y composición de los recursos reportados.", "shield", "01 / PANORAMA")
    left, right = st.columns(2, gap="medium")
    with left, st.container(border=True):
        chart_title("Cobertura por programa", "Beneficiarios y usuarios reportados en el corte seleccionado")
        show_chart(program_bars(filtered), "program_coverage")
    with right, st.container(border=True):
        chart_title("Recursos acumulados por programa", "Acumulado de gobierno = acumulado previo + monto fiscal vigente")
        show_chart(budget_stack(filtered), "program_budget")

    section_heading("Los recursos, en contexto", "Montos de la fuente, expresados en USD. No corresponden a una transferencia mensual.", "wallet", "02 / PRESUPUESTO")
    execution = stats["presupuesto_ejecutado"]
    execution_label = money(execution, True) if execution is not None else "No disponible"
    execution_note = "Millones de USD · ejecución verificada" if execution is not None else "La fuente no certifica la fase de ejecución"
    st.markdown(f'<div class="budget-strip"><div><span>ACUMULADO PREVIO · 2023–{fiscal_year - 1}</span><strong>USD {money(stats["monto_anterior"], True)}</strong><small>Referencia acumulada anterior</small></div><div><span>ACUMULADO DE GOBIERNO</span><strong>USD {money(stats["monto_gobierno"], True)}</strong><small>Incluye el monto fiscal {fiscal_year}</small></div><div><span>PRESUPUESTO EJECUTADO</span><strong>{"USD " if execution is not None else ""}{execution_label}</strong><small>{execution_note}</small></div></div>', unsafe_allow_html=True)
    if execution is None and stats.get("presupuesto_ejecutado_parcial") is not None:
        st.caption(f'Hay ejecución verificada para {number(stats["ejecucion_cobertura_pct"],1)}% de las filas: {money(stats["presupuesto_ejecutado_parcial"])}. No se presenta ese monto parcial como total.')
    with st.expander("Ver distribución del monto fiscal", expanded=False):
        a, b = st.columns([1, 1.25], gap="large")
        with a: show_chart(fiscal_allocation(filtered), "fiscal_donut")
        grouped = aggregate(filtered, "programa").sort_values("monto_fiscal", ascending=False)
        with b:
            total = grouped.monto_fiscal.sum()
            items = []
            for i, row in enumerate(grouped.itertuples()):
                proportion = row.monto_fiscal / total * 100 if total else 0
                items.append(f'<div class="legend-item"><span><i style="background:{PALETTE[i % len(PALETTE)]}"></i>{html.escape(row.programa)}</span><strong>{number(proportion,1)}%</strong></div>')
            st.markdown('<div class="legend-list">'+"".join(items)+'</div>', unsafe_allow_html=True)

    section_heading("Una mirada al territorio", "Compara provincias y explora la composición de los programas en cada una.", "pin", "03 / TERRITORIO")
    controls1, controls2 = st.columns([2, 1])
    with controls1:
        territorial_metric_label = st.segmented_control("Indicador territorial", ["Cobertura reportada", "Monto fiscal", "Unidades de atención"], default="Cobertura reportada", key="territorial_metric")
    with controls2:
        province_limit = st.selectbox("Territorios en el gráfico", ["Todos", "12 principales"], label_visibility="collapsed", key="territory_limit")
    metric_key = {"Cobertura reportada": "usuarios", "Monto fiscal": "monto_fiscal", "Unidades de atención": "unidades"}.get(territorial_metric_label, "usuarios")
    terrain = filtered if metric_key != "unidades" else filtered.loc[filtered.seccion.eq("proteccion_integral")]
    max_territories = 25 if province_limit == "Todos" else 12
    if terrain.empty:
        st.info("Las unidades de atención corresponden a servicios de protección integral; no aplican a bonos y pensiones.")
    else:
        left, right = st.columns([1, 1.1], gap="medium")
        with left, st.container(border=True):
            chart_title(territorial_metric_label or "Cobertura reportada", "Valores por provincia y zona en estudio, cuando corresponde")
            show_chart(province_bars(terrain, metric_key, max_territories), "province_bars")
        with right, st.container(border=True):
            chart_title("Composición de cada territorio", "% del indicador dentro de cada territorio · pasa el cursor para ver valores")
            show_chart(territorial_matrix(terrain, metric_key, max_territories), "province_matrix")

    section_heading("Detalle verificable", "Cada visual puede contrastarse con el mismo corte de información.", "document", "04 / CONSULTA")
    with st.expander("Detalle por programa y territorio", expanded=False):
        level = st.radio("Nivel de detalle", ["Programa", "Provincia y programa"], horizontal=True)
        detail = aggregate(filtered, ["provincia", "programa"] if level == "Provincia y programa" else ["programa"])
        display_table(detail, True)
        st.caption("Guion: no disponible o no aplicable. Los montos están en USD y mantienen la precisión de la fuente.")
        st.download_button("Descargar detalle CSV", detail.to_csv(index=False).encode("utf-8-sig"), file_name=f'MTDH_detalle_{manifest["periodo"][:7]}.csv', mime="text/csv", icon=":material/download:")
    with st.expander("Fuentes, definiciones y calidad de los datos", expanded=False):
        st.markdown(f'**Fuente:** {manifest.get("fuente",{}).get("archivo", "Excel institucional")} · hoja provincial. **Filas seleccionadas:** {stats["registros"]}.')
        st.caption(manifest.get("periodo_origen", ""))
        definitions = manifest.get("definiciones", {})
        for field in ["usuarios", "unidades", "monto_fiscal", "monto_gobierno", "presupuesto_ejecutado"]:
            if field in definitions: st.markdown(f'**{field.replace("_", " ").capitalize()}:** {definitions[field]}')
        st.caption("Base agregada, sin identificadores personales. No se suman referencias históricas al corte vigente.")
    render_references(provincias=selected_provinces or None, programas=selected_programs or None, secciones=sections)


def report_center() -> None:
    section_heading("Del análisis al informe", "Crea una pieza institucional lista para compartir con el alcance de esta consulta.", "document", "CENTRO DE REPORTES")
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        st.markdown('<div class="report-intro">Una misma base, dos formas de comunicar. El resumen ejecutivo reúne cifras, gráficos y notas de lectura; la presentación organiza los resultados en diapositivas editables.</div>', unsafe_allow_html=True)
        report_type = st.segmented_control("Tipo de informe", ["Resumen ejecutivo", "Presentación"], default="Resumen ejecutivo", key="report_type") or "Resumen ejecutivo"
        title = st.text_input("Título del informe", value="Boletín de protección social", max_chars=95, key="report_title")
        if not title.strip(): title = "Boletín de protección social"
        include_territory = st.checkbox("Incluir análisis territorial", value=True, key="include_territory")
        if report_type == "Resumen ejecutivo":
            output_format = st.radio("Formato de descarga", ["PDF", "Word"], horizontal=True, key="executive_format")
        else:
            output_format = "PowerPoint"
            st.markdown('<span class="export-badge">'+icon("presentation", 16)+' PowerPoint editable · 16:9</span>', unsafe_allow_html=True)
        st.markdown("**Alcance del informe**")
        st.caption(f'{scope_label} · {territory_label} · {stats["programas"]} programas · {period_label}. Los filtros del panel lateral se aplican también a la descarga.')
        selected_scope = " · ".join(SECTIONS[s] for s in filtered.seccion.unique())
        options = {"title": title.strip(), "include_territory": include_territory}
        # A fresh fingerprint prevents a previously generated download from surviving a filter change.
        digest = hashlib.sha256(pd.util.hash_pandas_object(filtered, index=True).values.tobytes() + json.dumps(options, sort_keys=True).encode() + output_format.encode()).hexdigest()
        if st.button(f"Generar {output_format}", type="primary", icon=":material/auto_awesome:", width="stretch"):
            with st.spinner("Componiendo gráficos y páginas del informe…"):
                try:
                    from src.reports import build_report_context, generate_docx, generate_pdf, generate_pptx
                    context = build_report_context(filtered, manifest, options=options)
                    generator, extension, mime = {
                        "PDF": (generate_pdf, "pdf", "application/pdf"),
                        "Word": (generate_docx, "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                        "PowerPoint": (generate_pptx, "pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
                    }[output_format]
                    artifact = generator(context)
                    st.session_state.generated_report = {"digest": digest, "content": artifact, "extension": extension, "mime": mime}
                except Exception as exc:
                    st.error("No se pudo generar el archivo. Revisa el detalle y vuelve a intentarlo.")
                    with st.expander("Detalle del error"):
                        st.code(str(exc))
        generated = st.session_state.get("generated_report", {})
        if generated.get("digest") == digest:
            st.success("Informe listo. Incluye los filtros seleccionados.")
            st.download_button(f"Descargar {output_format}", generated["content"], file_name=f'MTDH_{manifest["periodo"][:7]}_{"ejecutivo" if report_type == "Resumen ejecutivo" else "presentacion"}.{generated["extension"]}', mime=generated["mime"], icon=":material/download:", type="primary", width="stretch")
        info_note("Las exportaciones conservan las definiciones y los datos no disponibles. El presupuesto ejecutado solo se muestra cuando existe una fuente complementaria verificada.", "Cifras consistentes")
    with right:
        report_cover(title, period_label, selected_scope, stats, report_type == "Presentación")
        st.caption("Vista conceptual de portada · la composición final se adapta al formato elegido.")
    with st.expander("Revisar cifras que se incluirán", expanded=False):
        display_table(aggregate(filtered, ["programa"]))


if st.session_state.workspace == "dashboard":
    dashboard()
else:
    report_center()

footer(period_label, manifest.get("fuente", {}).get("archivo", "Fuente institucional"))
