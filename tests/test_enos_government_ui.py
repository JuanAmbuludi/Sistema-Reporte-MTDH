"""Government alert history stays dated from the live controls through exports."""
from datetime import date
from io import BytesIO

import openpyxl
import pandas as pd
import pymupdf

from src import enos, ui


def _generate(app, product):
    app.segmented_control(key="report_product").set_value(product).run()
    app.button(key="generate_report").click().run()
    assert not app.exception
    assert any(button.key == "download_report" for button in app.download_button)
    return app.session_state["generated_report"]["content"]


def test_government_shortcut_daily_alerts_and_exports_keep_the_same_records():
    from test_interface import _logged_in_app, _markdown

    history = enos.history()
    first, last = (moment.date() for moment in enos.history_window(history))
    assert first.year == 2024
    daily = [row for row in history["alertas"] if str(row["fecha"]).startswith("2024-")
             and row.get("fecha_precision") not in ("mes_reporte", "intervalo")]
    selected_day = min(pd.Timestamp(row["fecha"]).date() for row in daily)
    selected = [row for row in daily if pd.Timestamp(row["fecha"]).date() == selected_day]
    expected_codes = {row["codigo"] for row in selected}
    all_codes = {row["codigo"] for row in history["alertas"]}
    assert expected_codes

    app = _logged_in_app()
    app.segmented_control(key="module").set_value("riesgos").run()
    assert not app.exception
    assert app.date_input(key="risk_period_since").value == date(2026, 8, 28)
    app.button(key="risk_government").click().run()
    assert not app.exception
    assert app.date_input(key="risk_period_since").value == first
    assert app.date_input(key="risk_period_until").value == last
    assert f"{ui.number(len(history['alertas']))} alertas" in _markdown(app)

    app.date_input(key="risk_period_since").set_value(selected_day).run()
    app.date_input(key="risk_period_until").set_value(selected_day).run()
    assert not app.exception
    html = _markdown(app)
    assert f"{len(selected)} alerta" in html
    for row in selected:
        assert row["codigo"] in html
        assert row["estado"] in html

    app.segmented_control(key="workspace").set_value("Reportes").run()
    assert not app.exception
    pdf = _generate(app, "Resumen ejecutivo")
    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
        assert f"Del {selected_day:%d/%m/%Y} al {selected_day:%d/%m/%Y}" in text
        assert all(code in text for code in expected_codes)

    book = openpyxl.load_workbook(BytesIO(_generate(app, "Libro de datos")), data_only=True)
    rows = list(book["Alertas"].iter_rows(values_only=True))
    cells = {str(cell) for row in rows for cell in row if cell is not None}
    assert all_codes & cells == expected_codes
    for record in selected:
        row = next(row for row in rows if record["codigo"] in row)
        assert record["estado"] in row
        assert any(isinstance(value, date) and value.strftime("%Y-%m-%d") == selected_day.isoformat() for value in row)
    app.segmented_control(key="workspace").set_value("Tablero").run()
    app.button(key="risk_reset_filters").click().run()
    assert not app.exception
    assert app.date_input(key="risk_period_since").value == date(2026, 8, 28)


def test_month_only_historical_reports_require_the_complete_month():
    from test_interface import _logged_in_app, _markdown

    monthly = [row for row in enos.history()["alertas"] if row.get("fecha_precision") == "mes_reporte"
               and str(row["fecha"]).startswith("2024-")]
    assert monthly
    month = pd.Period(monthly[0]["fecha"], freq="M")
    first, last = month.start_time.date(), month.end_time.date()
    records = [row for row in monthly if pd.Period(row["fecha"], freq="M") == month]
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("riesgos").run()
    app.date_input(key="risk_period_since").set_value(first).run()
    app.date_input(key="risk_period_until").set_value(last).run()
    assert not app.exception
    html = _markdown(app)
    assert "mes de reporte" in html
    assert all(row["codigo"] in html for row in records)
    app.date_input(key="risk_period_until").set_value(first.replace(day=15)).run()
    assert not app.exception
    assert all(row["codigo"] not in _markdown(app) for row in records)


def test_ferias_full_title_and_source_controls_remain_available():
    from test_interface import _logged_in_app, _markdown

    app = _logged_in_app()
    app.segmented_control(key="module").set_value("ferias").run()
    assert not app.exception
    title = "Ferias de Inclusión Económica, Empleabilidad y Autoempleo"
    assert title in _markdown(app)
    assert app.segmented_control(key="ferias_source").options == ["Empleabilidad y autoempleo", "Inclusión económica"]
    app.segmented_control(key="period_year").set_value(2023).run()
    app.segmented_control(key="period_month").set_value("2023-11").run()
    for source in ("inclusion_economica", "empleabilidad_autoempleo"):
        app.segmented_control(key="ferias_source").set_value(source).run()
        assert not app.exception
        assert app.segmented_control(key="period_month").value == "2023-11"
        assert title in _markdown(app)
        assert len(app.get("plotly_chart")) == 7
