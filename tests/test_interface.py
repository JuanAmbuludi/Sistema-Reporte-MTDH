"""The interface: formal, strategic, one module at a time, by period, with no collapsible sections."""
from pathlib import Path
import time
import tomllib

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
BANNED = ["Cómo leer", "no certifica", "N/D", "No disponible", "Una misma persona", "polígono",
          "hoja provincial", "Huella", "SHA-256", "insumo", "Guion"]


def _logged_in_app() -> AppTest:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
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


def test_dashboard_is_formal_strategic_and_without_collapsibles():
    app = _logged_in_app()
    assert len(app.expander) == 0, "La interfaz no usa secciones desplegables"
    assert len(app.selectbox) == 0, "Los selectores se muestran como controles visibles"
    html = _markdown(app)
    for title in ["Transferencias monetarias", "Resultados por programa", "Resultados por provincia", "Cuadro de resultados"]:
        assert title in html
    assert html.count("<svg") >= 1 and "ec-map" in html, "El encabezado incluye el mapa del Ecuador"
    assert "1.578.019" in html
    for banned in BANNED:
        assert banned not in html, banned
    assert "Corte septiembre 2026" in html


def test_services_are_never_mixed_with_transfers():
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("servicios").run()
    assert not app.exception
    html = _markdown(app)
    assert "Servicios de protección integral" in html
    assert "456.356" in html and "11.215" in html
    assert "1.578.019" not in html and "2.034.375" not in html


def test_periods_can_be_chosen_by_year():
    app = _logged_in_app()
    app.segmented_control(key="period_year").set_value(2025).run()
    assert not app.exception
    html = _markdown(app)
    assert "Año 2025" in html and "1.557.996" in html and "Presupuesto 2025" in html
    assert app.segmented_control(key="period_month_annual").disabled


def test_territory_filter_scopes_every_indicator():
    app = _logged_in_app()
    app.multiselect(key="selected_provinces").set_value(["09"]).run()
    assert not app.exception
    html = _markdown(app)
    assert "Transferencias monetarias en Guayas" in html
    assert "312.265" in html and "del total nacional" in html


def test_report_center_generates_the_three_products():
    app = _logged_in_app()
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert not app.exception
    assert len(app.expander) == 0
    assert app.segmented_control(key="report_product").value == "Resumen ejecutivo"
    for product in ["Resumen ejecutivo", "Presentación", "Libro de datos"]:
        app.segmented_control(key="report_product").set_value(product).run()
        name = product.lower()
        next(b for b in app.button if b.label == f"Generar {name}").click().run()
        assert not app.exception
        assert any(d.label == f"Descargar {name}" for d in app.download_button), product


def test_financial_scope_is_explicit_and_not_shown_in_historical_year():
    app = _logged_in_app()
    html = _markdown(app)
    assert "Presupuesto institucional" in html and "978,12" in html and "45,77" in html
    assert "independiente del ámbito y las provincias" in html
    app.segmented_control(key="period_year").set_value(2025).run()
    assert not app.exception
    assert "Presupuesto institucional" not in _markdown(app)
