"""The interface: formal, strategic, one area at a time, by period, with no collapsible sections."""
from pathlib import Path
import time
import tomllib

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
BANNED = ["Cómo leer", "no certifica", "N/D", "No disponible", "Una misma persona", "polígono",
          "hoja provincial", "Huella", "SHA-256", "insumo", "Guion", "independiente del ámbito", "Ejecución fiscal al corte",
          "Referencia de la información", "contenido idéntico", "deduplicación", "InfoReportes"]


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
                  "Ejecución presupuestaria", "Parroquias con más beneficiarios", "InfoReport"]:
        assert title in html, title
    assert html.count("<svg") >= 1 and "ec-map" in html and 'class="ec-mosaic"' in html, "El encabezado incluye el mapa parroquial"
    assert "Beneficiarios por parroquia" in html
    assert "1.578.019" in html and "71,0" in html
    for banned in BANNED:
        assert banned not in html, banned
    assert "Corte septiembre 2026" in html
    assert app.segmented_control(key="module").options == ["Transferencias", "Servicios", "Gestión laboral", "Presupuesto"]


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


def test_territory_filter_zooms_into_the_province():
    app = _logged_in_app()
    app.multiselect(key="selected_provinces").set_value(["09"]).run()
    assert not app.exception
    html = _markdown(app)
    assert "Transferencias monetarias en Guayas" in html
    assert "312.265" in html and "del total nacional" in html
    assert "ec-locator" in html and "clipPath" in html and "Las 20 primeras de Guayas" in html
    app.segmented_control(key="detail_level").set_value("Por parroquia").run()
    assert not app.exception


def test_report_center_generates_the_three_products():
    app = _logged_in_app()
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert app.segmented_control(key="report_product").value == "Resumen ejecutivo"
    _generate_every_product(app)


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
    for expected in ["Gestión laboral", "2.789.419", "507.451", "4.676", "Más de USD", "Contratos registrados por mes", "ec-columns"]:
        assert expected in html, expected
    _generate_every_product(app)
