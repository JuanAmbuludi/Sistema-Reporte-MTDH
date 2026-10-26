"""InfoReport MTDH: tablero de indicadores estratégicos y centro de reportes institucionales.

Run from the repository root with ``streamlit run app.py``.
Each view reads one period and one area (transfers, services, contingencies and compensation, Jóvenes en Acción,
labour management or the budget; they are never mixed), and every export receives exactly the rows shown on screen.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
st.set_page_config(
    page_title="InfoReport · Ministerio de Trabajo y Desarrollo Humano",
    page_icon=str(ROOT / "assets" / "brand" / "favicon.png"),
    layout="wide",
    initial_sidebar_state="collapsed",
)


# Streamlit manages code reloads. Never delete shared modules while other sessions import them.

from src import corte, ui  # noqa: E402
from src.auth import logout, require_login  # noqa: E402
from src.data import DEFAULT_DATA_DIR, load_periods, load_territory  # noqa: E402
from src.gestion_laboral import load_labour  # noqa: E402
from src.indicators import AREAS, MODULES  # noqa: E402
from src.institutional import load_budget  # noqa: E402
from src.views.common import period_controls  # noqa: E402
from src.views.contingencias import ContingencyView  # noqa: E402
from src.views.jovenes import YouthView  # noqa: E402
from src.views.laboral import LabourView  # noqa: E402
from src.views.presupuesto import BudgetArea, BudgetView, SocialBudgetView  # noqa: E402
from src.views.territorial import TerritorialView  # noqa: E402
from src.views.riesgos import RiskView  # noqa: E402
from src.views.enos import RiskArea  # noqa: E402

ui.inject_styles()
user = require_login()

WORKSPACES = {"Tablero": ":material/insights: Tablero", "Reportes": ":material/description: Reportes"}


def _clear_module_caches() -> None:
    """Forget what the modules read from the previous version of the bases."""
    from src import contingencias, depuracion, gestion_laboral, jovenes, mensual
    for function in (contingencias.extraction, contingencias.monthly, contingencias.territorial, jovenes.phases, jovenes.payments,
                     jovenes.budget, mensual.coverage, mensual.program_budget, depuracion.gazetteer, depuracion._cleaned):
        function.cache_clear()
    gestion_laboral._TABLES.clear()


@st.cache_data(show_spinner=False)
def read_bases(version: int) -> dict:
    """Every base of the dashboard; invalidated when any of them changes."""
    from src import contingencias, mensual, presupuesto_social
    _clear_module_caches()
    data, catalog = load_periods()
    budget, manifest = load_budget()
    groups, programs = presupuesto_social.load_social_budget()
    return {"data": data, "catalog": catalog, "territory": load_territory(), "budget": budget, "budget_manifest": manifest,
            "labour": load_labour(), "program_budget": mensual.program_budget(), "contingencies": contingencias.monthly(),
            "contingency_places": contingencias.territorial(), "contingency_catalog": contingencias.catalog(),
            "social_groups": groups, "social_programs": programs}


def bases_version() -> int:
    """Latest change of any base (processed bases and monthly series)."""
    folders = [DEFAULT_DATA_DIR, DEFAULT_DATA_DIR.parent / "series", DEFAULT_DATA_DIR.parent / "series" / "laboral"]
    return max(path.stat().st_mtime_ns for folder in folders if folder.exists() for path in folder.glob("*") if path.is_file())


try:
    version = bases_version()
    bases = read_bases(version)
except (FileNotFoundError, ValueError, OSError):
    ui.info_note("La información no está disponible en este momento. Vuelva a cargar la página en unos minutos.",
                 "Información no disponible", tone="warn")
    st.stop()

views = {module_id: TerritorialView(module_id, bases["data"], bases["catalog"], bases["territory"], bases["program_budget"])
         for module_id in MODULES}
risk_view = RiskView()
if risk_view.catalog():
    views["riesgos"] = RiskArea(risk_view)
if bases["contingency_catalog"]:
    views["contingencias"] = ContingencyView(bases["contingencies"], bases["contingency_places"], bases["contingency_catalog"])
youth = YouthView()
if youth.catalog():
    views["jovenes"] = youth
labour = LabourView(bases["labour"])
if labour.catalog():
    views["laboral"] = labour
institutional = BudgetView(bases["budget"], bases["budget_manifest"]) if not bases["budget"].empty else None
social = SocialBudgetView(bases["social_groups"], bases["social_programs"]) if not bases["social_groups"].empty else None
budget_area = BudgetArea(institutional, social)
if budget_area.views:
    views["presupuesto"] = budget_area
st.session_state.setdefault("workspace", "Tablero")
if st.session_state.get("module") not in views:
    st.session_state["module"] = next(iter(views))

# ---------------------------------------------------------------------------
# Institutional band: top bar, consultation and the map (or series) of the area
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
            area = st.segmented_control("Ámbito", list(views), format_func=lambda a: AREAS[a]["short"], key="module",
                                        required=True, width="stretch")
            view = views[area]
            if hasattr(view, "pre_controls"):
                view.pre_controls()
            period = period_controls(view.catalog())
            view.controls(period)
    ready = view.prepare()
    stamp = view.update_stamp() if hasattr(view, "update_stamp") else corte.stamp(view.id, period)
    if ready:
        with copy_slot.container():
            ui.hero_copy(*view.hero_copy())
            ui.update_stamp(stamp)
        with hero_right:
            view.hero_visual()

if not ready:
    ui.info_note(view.empty_message, "Sin resultados para esta selección", tone="warn")
    st.stop()

if area == "riesgos":
    view.geoportal()
ui.kpi_grid(view.kpi_cards(), overlap=area != "riesgos")


# ---------------------------------------------------------------------------
# Report center
# ---------------------------------------------------------------------------
PRODUCTS = {
    "Resumen ejecutivo": {"label": ":material/picture_as_pdf: Resumen ejecutivo", "kind": "resumen", "ext": "pdf",
                          "mime": "application/pdf", "slug": "resumen"},
    "Presentación": {"label": ":material/slideshow: Presentación", "kind": "presentacion", "ext": "pptx",
                     "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "slug": "presentacion"},
    "Libro de datos": {"label": ":material/table_view: Libro de datos", "kind": "datos", "ext": "xlsx",
                       "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "slug": "datos"},
}


# Documents of a single territorial level name it in the file; the complete set needs no suffix.
LEVEL_SUFFIX = {"provincia": "_provincias", "canton": "_cantones", "parroquia": "_parroquias"}


def kpi_text(card: dict) -> str:
    value = ui.number(card["value"], card.get("decimals", 0))
    if card.get("suffix") == "%":
        return f"{value} %"
    if card.get("prefix"):
        return f"{card['prefix']} {value} M"
    return value


def report_center() -> None:
    ui.section_heading("Centro de reportes", "Productos institucionales con el periodo, el ámbito y la selección vigentes.", "document")
    left, right = st.columns([1, 1.08], gap="large")
    with left, st.container(border=True, key="card_report_form"):
        ui.chart_title("Configuración del reporte", "Producto y título")
        product = st.segmented_control("Producto", list(PRODUCTS), format_func=lambda k: PRODUCTS[k]["label"],
                                       default="Resumen ejecutivo", key="report_product", required=True, width="stretch")
        spec = PRODUCTS[product]
        st.caption(view.products_notes()[spec["kind"]])
        file_id = getattr(view, "file_id", view.id)
        title = st.text_input("Título", value=view.label, max_chars=80, key=f"report_title_{file_id}").strip() or view.label
        if hasattr(view, "report_options"):
            view.report_options()
        ui.scope_chips(view.scope_items())
        # A fresh fingerprint prevents a previously generated download from surviving a change of selection.
        digest = hashlib.sha256((view.digest() + json.dumps({"title": title, "product": product, "area": file_id},
                                                             sort_keys=True)).encode("utf-8")).hexdigest()
        name = product.lower()
        if st.button(f"Generar {name}", type="primary", icon=":material/auto_awesome:", width="stretch", key="generate_report"):
            with st.spinner("Preparando el documento…"):
                try:
                    from src.reports import generate_pdf, generate_pptx, generate_xlsx
                    context = view.report_context(title)
                    generator = {"resumen": generate_pdf, "presentacion": generate_pptx, "datos": generate_xlsx}[spec["kind"]]
                    st.session_state.generated_report = {"digest": digest, "content": generator(context)}
                except Exception as exc:  # noqa: BLE001 - shown to the operator with its reason
                    st.session_state.pop("generated_report", None)
                    ui.info_note(f"No se pudo generar el documento: {exc}", "Revise la selección e intente nuevamente", tone="warn")
        generated = st.session_state.get("generated_report", {})
        if generated.get("digest") == digest:
            ui.info_note("El documento conserva el periodo, el ámbito y la selección vigentes.", f"{product} listo", tone="ok")
            level = LEVEL_SUFFIX.get(getattr(view, "report_level", ""), "") if hasattr(view, "report_options") else ""
            st.download_button(f"Descargar {name}", generated["content"],
                               file_name=f'MTDH_{spec["slug"]}_{file_id}_{period["id"]}{level}.{spec["ext"]}', mime=spec["mime"],
                               icon=":material/download:", type="primary", width="stretch", key="download_report")
    with right:
        kpis = [(card["label"], kpi_text(card), card["icon"]) for card in view.kpi_cards()]
        ui.report_preview(spec["kind"], title, period["label"], view.territory_label, kpis, view.sheets(), view.preview_visual(),
                          view.slide_titles(), pages=getattr(view, "summary_pages", 2))
        ui.content_list(view.report_contents(spec["kind"]))


if st.session_state.workspace == "Tablero":
    view.dashboard()
else:
    report_center()

ui.footer(period["label"], stamp)
