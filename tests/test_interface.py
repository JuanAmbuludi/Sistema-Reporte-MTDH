"""The redesigned interface: no collapsible sections, shared filters and live exports."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def _logged_in_app() -> AppTest:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.run()
    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("admin12345678")
    next(b for b in app.button if "Ingresar al sistema" in b.label).click().run()
    assert not app.exception
    return app


def _markdown(app: AppTest) -> str:
    return "\n".join(m.value for m in app.markdown)


def test_dashboard_is_fully_visible_with_maps():
    app = _logged_in_app()
    assert len(app.expander) == 0, "La interfaz no usa secciones desplegables"
    assert len(app.selectbox) == 0, "Los selectores se muestran como controles visibles"
    html = _markdown(app)
    for title in ["Cobertura por programa", "Recursos", "Territorio", "Detalle verificable", "Fuentes, definiciones y calidad"]:
        assert title in html
    assert html.count("<svg") >= 1 and "ec-map" in html, "El encabezado incluye el mapa del Ecuador"
    assert "1.578.019" in html and "456.239" in html and "11.158" in html


def test_territory_filter_scopes_every_indicator():
    app = _logged_in_app()
    app.multiselect(key="selected_provinces").set_value(["09"]).run()
    assert not app.exception
    html = _markdown(app)
    assert "Protección social en Guayas" in html
    assert "312.265" in html and "87.943" in html
    assert "del total nacional" in html


def test_report_center_generates_excel_without_collapsibles():
    app = _logged_in_app()
    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert not app.exception
    assert len(app.expander) == 0
    assert app.segmented_control(key="report_format").value == "Excel"
    next(b for b in app.button if b.label == "Generar Excel").click().run()
    assert not app.exception
    assert any(d.label == "Descargar Excel" for d in app.download_button)
