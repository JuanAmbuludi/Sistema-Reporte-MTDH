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
    assert "<h1>InfoReport</h1>" in html and "Acceso a InfoReport" in html
    assert "Información estratégica para la toma de decisiones" not in html


def test_dashboard_is_formal_strategic_and_without_collapsibles():
    app = _logged_in_app()
    assert len(app.expander) == 0, "La interfaz no usa secciones desplegables"
    assert len(app.selectbox) == 0, "Los selectores se muestran como controles visibles"
    html = _markdown(app)
    for title in ["Transferencias monetarias", "Resultados por programa", "Resultados por territorio", "Cuadro de resultados",
                  "Ejecución presupuestaria", "Beneficiarios por provincia", "Distribución por programa", "InfoReport"]:
        assert title in html, title
    assert html.count("<svg") >= 1 and "ec-map" in html and 'class="ec-mosaic"' in html, "El encabezado incluye el mapa parroquial"
    assert "Beneficiarios por parroquia" in html
    assert "1.578.019" in html and "71,0" in html
    assert "reach-strip" in html and "reúnen la mitad de los beneficiarios" in html and "1.283" in html
    for banned in BANNED:
        assert banned not in html, banned
    assert "Corte septiembre 2026" in html
    assert app.segmented_control(key="module").options == ["Transferencias", "Servicios", "Gestión laboral", "Presupuesto"]


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
    for title in ["Beneficiarios por cantón", "Los 25 primeros cantones del país", "Ejecución presupuestaria por parroquia",
                  "Las 25 primeras parroquias del país"]:
        assert title in html, title


def test_services_are_never_mixed_with_transfers():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("servicios").run()
    assert not app.exception
    html = _markdown(app)
    assert "Servicios de protección integral" in html
    assert "456.356" in html and "11.215" in html and "47,2" in html
    assert "1.578.019" not in html and "2.034.375" not in html


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
    assert "Transferencias monetarias en Guayas" in html
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
    level.set_value("canton").run()
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
    for expected in ["Presupuesto institucional", "978,1", "2.137,2", "45,8", "Saldo por devengar", "Ejecución presupuestaria por zona",
                     "Por programa presupuestario"]:
        assert expected in html, expected
    for banned in BANNED:
        assert banned not in html, banned
    assert app.segmented_control(key="period_year").options == ["2026"]
    app.multiselect(key="budget_zones").set_value(["Z5"]).run()
    assert not app.exception and "Presupuesto institucional en la Zona 5" in _markdown(app)
    _generate_every_product(app)


def test_labour_management_shows_contracts_and_retirement():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("laboral").run()
    assert not app.exception
    html = _markdown(app)
    from src.gestion_laboral import load_labour, summary
    from src.ui import number
    current = summary(load_labour())
    for expected in ["Gestión laboral", number(current["stock"]), "507.451", number(current["retirees"]), "USD", "Contratos registrados por mes", "ec-columns"]:
        assert expected in html, expected
    _generate_every_product(app)
