"""The interface: formal, strategic, one area at a time, by period, with no collapsible sections."""
from pathlib import Path
import time
import tomllib

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
BANNED = ["Cómo leer", "no certifica", "N/D", "No disponible", "Una misma persona", "polígono",
          "hoja provincial", "Huella", "SHA-256", "insumo", "Guion", "independiente del ámbito", "Ejecución fiscal al corte",
          "Referencia de la información", "contenido idéntico", "deduplicación", "InfoReportes"]
LEVELS = ["provincia", "canton", "parroquia"]


def _logged_in_app() -> AppTest:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    users = tomllib.loads((ROOT / "config/access.toml").read_text())["auth"]["users"]
    username = next(iter(users))
    now = time.monotonic()
    app.session_state["_auth_session"] = {"username": username, "issued": now, "last_seen": now,
                                          "credential_version": users[username]["password_hash"]}
    app.run()
    assert not app.exception
    return app


def _markdown(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def _generate_every_product(app: AppTest) -> None:
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert not app.exception
    assert len(app.expander) == 0
    for product in ["Resumen ejecutivo", "Presentación", "Libro de datos"]:
        app.segmented_control(key="report_product").set_value(product).run()
        name = product.lower()
        next(b for b in app.button if b.label == f"Generar {name}").click().run()
        assert not app.exception
        assert any(d.label == f"Descargar {name}" for d in app.download_button), product


def test_login_presents_the_product_name():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.run()
    html = _markdown(app)
    assert "<h1>InfoReport</h1>" in html and "Iniciar sesión" in html
    assert "Información estratégica para la toma de decisiones" not in html


def test_dashboard_is_formal_strategic_and_without_collapsibles():
    app = _logged_in_app()
    assert len(app.expander) == 0, "La interfaz no usa secciones desplegables"
    assert len(app.selectbox) == 0, "Los selectores se muestran como controles visibles"
    html = _markdown(app)
    for title in ["Transferencias monetarias no contributivas", "Resultados por programa", "Resultados por territorio", "Cuadro de resultados",
                  "Ejecución presupuestaria", "Beneficiarios por provincia", "Distribución por programa", "InfoReport"]:
        assert title in html, title
    assert html.count("<svg") >= 1 and "ec-map" in html and 'class="ec-mosaic"' in html, "El encabezado incluye el mapa parroquial"
    assert "Beneficiarios por parroquia" in html
    assert "1.578.019" in html and "71,0" in html
    assert "reach-strip" in html and "reúnen la mitad de los beneficiarios" in html and "1.256" in html
    for banned in BANNED:
        assert banned not in html, banned
    assert "Corte septiembre 2026" in html
    assert "update-stamp" in html and "Actualizado el" in html and "Actualización mensual" in html, "Corte y frecuencia visibles"
    assert "El corazón de Ecuador." not in html and "Velamos por la calidad de vida de los ecuatorianos" not in html
    assert app.segmented_control(key="module").options == ["Transferencias", "Servicios sociales", "ENOS", "Contingencias", "Jóvenes en Acción",
                                                           "Empleo", "Presupuesto"]


def test_every_territorial_chart_switches_between_province_canton_and_parish():
    app = _logged_in_app()
    for key in ["map_level", "lvl_rank", "lvl_execution", "lvl_matrix"]:
        control = app.segmented_control(key=key)
        assert control.options == ["Provincia", "Cantón", "Parroquia"] and not control.disabled, key
    app.segmented_control(key="map_level").set_value("canton").run()
    assert not app.exception and "Beneficiarios por cantón" in _markdown(app) and 'data-layer="canton"' in _markdown(app)
    app.segmented_control(key="lvl_rank").set_value("canton").run()
    app.segmented_control(key="lvl_execution").set_value("parroquia").run()
    app.segmented_control(key="lvl_matrix").set_value("parroquia").run()
    assert not app.exception
    html = _markdown(app)
    for title in ["Beneficiarios por cantón", "Los 25 primeros cantones del país", "Ejecución por parroquia",
                  "Las 25 primeras parroquias del país"]:
        assert title in html, title


def test_services_are_never_mixed_with_transfers():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("servicios").run()
    assert not app.exception
    html = _markdown(app)
    assert "Servicios de protección social" in html
    assert "453.994" in html and "11.215" in html and "47,2" in html
    assert "1.578.019" not in html and "2.034.375" not in html
    assert "Geoportal de unidades de atención y amenazas" not in html, "El geoportal se trasladó a Riesgos"


def test_periods_can_be_chosen_by_year():
    app = _logged_in_app()
    app.segmented_control(key="period_year").set_value(2025).run()
    assert not app.exception
    html = _markdown(app)
    assert "Año 2025" in html and "1.557.996" in html and "Presupuesto 2025" in html
    assert "Beneficiarios por provincia" in html and 'class="ec-mosaic"' not in html, "Sin detalle parroquial el mapa es provincial"
    assert "Ejecución presupuestaria" not in html
    assert app.segmented_control(key="period_month_annual").disabled
    for key in ["map_level", "lvl_rank", "lvl_matrix"]:
        assert app.segmented_control(key=key).disabled and app.segmented_control(key=key).value == "provincia", key


def test_territory_filter_zooms_into_the_province():
    app = _logged_in_app()
    app.multiselect(key="selected_provinces").set_value(["09"]).run()
    assert not app.exception
    html = _markdown(app)
    assert "Transferencias monetarias no contributivas en Guayas" in html
    assert "312.265" in html and "del total nacional" in html
    assert "ec-locator" in html and "clipPath" in html
    assert "Cantones" in html and "Parroquias" in html, "El alcance territorial de una provincia muestra cantones y parroquias"
    app.segmented_control(key="lvl_rank").set_value("parroquia").run()
    assert not app.exception and "Las 25 primeras parroquias de Guayas" in _markdown(app)
    app.segmented_control(key="detail_level").set_value("Por parroquia").run()
    assert not app.exception


def test_report_center_asks_for_the_territorial_level():
    app = _logged_in_app()
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert app.segmented_control(key="report_product").value == "Resumen ejecutivo"
    level = app.segmented_control(key="report_level")
    assert level.options == ["Provincia", "Cantón", "Parroquia", "Todo"] and level.value == "todo"
    _generate_every_product(app)
    app.segmented_control(key="report_level").set_value("canton").run()
    assert not app.exception
    html = _markdown(app)
    assert "Cantones" in html and "Nivel territorial" in html
    next(b for b in app.button if b.label == "Generar libro de datos").click().run()
    assert not app.exception and any(d.label == "Descargar libro de datos" for d in app.download_button)


def test_institutional_budget_is_an_area_of_its_own():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("presupuesto").run()
    assert not app.exception
    html = _markdown(app)
    for expected in ["Presupuesto fiscal", "342,2", "993,6", "34,4", "Saldo disponible", "Año fiscal 2026",
                     "Por programa"]:
        assert expected in html, expected
    for banned in BANNED:
        assert banned not in html, banned
    assert app.segmented_control(key="period_year").options == ["2026"]
    assert not any(m.key == "budget_zones" for m in app.multiselect)
    app.multiselect(key="presupuesto_fiscal_programa").set_value(["Desarrollo Infantil"]).run()
    assert not app.exception and "24,5" in _markdown(app)
    _generate_every_product(app)


def _labour_figures(provinces=()) -> list[str]:
    """Contracts and companies of the published daily cut (it changes every day, so the test reads it)."""
    from src.gestion_laboral import load_labour
    from src.ui import number
    from src.views.laboral import LabourView
    view = LabourView(load_labour())
    view.select(view.catalog()[0], provinces)
    assert view.prepare()
    return [number(card["value"]) for card in view.kpi_cards()[:2]]


def test_labour_management_shows_contracts_and_retirement():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("laboral").run()
    assert not app.exception
    html = _markdown(app)
    for expected in ["Gestión laboral", *_labour_figures(), "4.686", "Actualización diaria", "Contratos vigentes por provincia",
                     "Perfil de los contratos vigentes", "Compensación jubilar", "Contratos registrados por mes"]:
        assert expected in html, expected
    app.multiselect(key="labour_provinces").set_value(["09"]).run()
    assert not app.exception and "Gestión laboral en Guayas" in _markdown(app) and _labour_figures(["09"])[0] in _markdown(app)
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert app.segmented_control(key="report_level_labour").options == ["Provincia", "Cantón", "Todo"]
    app.segmented_control(key="workspace").set_value("Tablero").run()
    _generate_every_product(app)


def test_contingencies_show_closed_months_with_the_criterion_of_each_source():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("contingencias").run()
    assert not app.exception
    assert app.segmented_control(key="period_year").options == ["2026", "2025", "2024", "2023"]
    assert app.segmented_control(key="period_month").options[-1] == "Sep", "Octubre no se publica hasta que cierre el mes"
    html = _markdown(app)
    for expected in ["Contingencias y compensaciones", "Orfandad por femicidio", "Cobertura de contingencias", "464", "3.403",
                     "USD 83.681 acreditados", "Presupuesto devengado 2026", "87,8 % del aprobado", "Bonos habilitados por provincia",
                     "Geoportal de unidades de atención y amenazas", "Evolución mensual"]:
        assert expected in html, expected
    for banned in BANNED:
        assert banned not in html, banned
    app.segmented_control(key="cont_map_program").set_value("ANTROPICOS").run()
    assert not app.exception and app.segmented_control(key="cont_map_level").options == ["Provincia", "Cantón", "Parroquia"]
    app.multiselect(key="cont_programs").set_value(["ORFANDAD_VIOLENCIA"]).run()
    assert not app.exception and "Orfandad por femicidio" in _markdown(app)
    app.multiselect(key="cont_programs").set_value([]).run()
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert app.segmented_control(key="report_level_cont").value == "todo"
    app.segmented_control(key="workspace").set_value("Tablero").run()
    _generate_every_product(app)


def test_youth_area_reads_the_phases_and_the_current_phase():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("jovenes").run()
    assert not app.exception
    html = _markdown(app)
    for expected in ["Jóvenes en Acción", "150.000", "637.808", "Fases del programa", "Del registro al pago", "Pagos acreditados por mes",
                     "Actualización mensual"]:
        assert expected in html, expected
    _generate_every_product(app)


def test_budget_offers_the_institutional_and_the_social_budget():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("presupuesto").run()
    assert not app.exception
    assert app.segmented_control(key="budget_universe").options == ["Fiscal", "Social", "Gobierno"]
    app.segmented_control(key="budget_universe").set_value("social").run()
    assert not app.exception
    assert len(app.segmented_control(key="period_month").options) == 9
    html = _markdown(app)
    for expected in ["Presupuesto social", "1.715,7", "1.261,8", "73,5", "Ritmo necesario de octubre a diciembre",
                     "Por programa presupuestario", "Ejecución acumulada por mes"]:
        assert expected in html, expected
    app.multiselect(key="social_groups").set_value(["BDH_BDHV"]).run()
    assert not app.exception and "Bono de Desarrollo Humano (BDH y BDHV)" in _markdown(app)
    _generate_every_product(app)


def test_executive_summary_of_every_section_fits_three_pages():
    import pymupdf
    app = _logged_in_app()
    app.segmented_control(key="workspace").set_value("Reportes").run()
    app.segmented_control(key="report_product").set_value("Resumen ejecutivo").run()
    app.segmented_control(key="report_scope").set_value("todas").run()
    assert not app.exception
    next(b for b in app.button if b.label == "Generar resumen ejecutivo").click().run()
    assert not app.exception
    assert any(d.label == "Descargar resumen ejecutivo" for d in app.download_button)
    content = app.session_state["generated_report"]["content"]
    pdf = pymupdf.open(stream=content, filetype="pdf")
    assert 1 < len(pdf) <= 3, "Tres páginas como máximo"
    text = " ".join(page.get_text() for page in pdf)
    for section in ["Transferencias monetarias no contributivas", "Servicios de protección social", "Plan ENOS", "Contingencias y compensaciones",
                    "Jóvenes en Acción", "Gestión laboral", "Presupuesto fiscal", "Presupuesto social",
                    "Presupuesto acumulado de gobierno"]:
        assert section in text, section
    assert "1.578.019" in text and "13.390" in text and _labour_figures()[0] in text
    # One block for Riesgos (the response of the Ministry; the exposure stays internal) and a chart of its own in every section.
    assert text.count("Riesgos: respuesta del Ministerio") == 1 and "UA expuestas" not in text
    for chart in ["Beneficiarios por provincia", "Usuarios por servicio", "Alertas por provincia",
                  "Monto entregado por mes", "Jóvenes con pago acreditado por mes", "Contratos vigentes por rama de actividad",
                  "Ejecución presupuestaria por programa", "Ejecución acumulada frente al ritmo uniforme",
                  "Acumulado de gobierno por programa"]:
        assert chart in text, chart


def test_risks_area_reads_the_response_of_the_ministry():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("riesgos").run()
    assert not app.exception
    html = _markdown(app)
    # Each question with the visual its data asks for; the exposure of the units stays internal.
    for title in ["Continuidad de los servicios", "Dónde se suspendió la atención", "Por servicio", "Unidades suspendidas",
                  "Alertas en servicios MTDH", "Evolución de las alertas", "Cada alerta, una unidad", "Registro de alertas",
                  "Kits entregados", "Kits por provincia y entregas en el tiempo", "Bono de contingencia", "Cada etapa, por provincia",
                  "Planificación El Niño 2026–2027", "Resumen por provincia", "Nota metodológica"]:
        assert title in html, title
    for hidden in ["Exposición por amenaza", "Unidades de atención expuestas", "Sin cantón en la base", "No consta en la fuente"]:
        assert hidden not in html, hidden
    assert "13.390" in html and "33.200,80" in html and "13.405.351,02" in html and "Espíndola" in html
    for indicator in ["suspendidas", "kits", "alertas"]:
        app.segmented_control(key="risk_map_indicator").set_value(indicator).run()
        assert not app.exception
    app.multiselect(key="risk_provinces").set_value(["09"]).run()
    assert not app.exception
    assert "17 unidades suspendidas" in _markdown(app)
