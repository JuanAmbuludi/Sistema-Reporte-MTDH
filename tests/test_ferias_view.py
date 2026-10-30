"""Ferias keeps source lines, dates and territorial/profile filters aligned."""
from datetime import date

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src import ferias
from src.views.area import period
from src.views.ferias import FairView


@pytest.mark.parametrize("source_key", ["empleabilidad_autoempleo", "inclusion_economica"])
def test_filters_apply_to_year_month_history_profile_and_export(source_key):
    view = FairView(source_key)
    category = view.rows_frame.tipo_capacitacion.iloc[0]
    view.select(period("2024-05"), provinces=["17"], categories=[category])
    assert view.prepare()
    expected = ferias.select(fuente=source_key, until="2024-05", provinces=["17"], tipo_capacitacion=category)
    year = expected.loc[expected.periodo_id.ge("2024-01")]
    assert view.stats["total"] == expected.participaciones.sum()
    assert view.stats["participations"] == year.participaciones.sum()
    assert view.stats["month"] == year.loc[year.periodo_id.eq("2024-05"), "participaciones"].sum()
    assert set(view.year_rows.fuente) == {source_key}
    for dimension in ("sexo", "edad", "sector", "actividad"):
        assert view.profile_by(dimension).participaciones.sum() == view.stats["participations"]
    context = view.report_context(view.label)
    assert ("Línea de formación", view.line_label) in context["scope_items"]
    assert sum(r["participaciones"] for r in context["tables"][0]["rows"]) == view.stats["participations"]
    for level in view.LEVELS.values():
        frame, _, _ = view.detail(level)
        assert frame.participaciones.sum() == view.stats["participations"]
    view.select(period("2023-11"))
    assert view.prepare()
    assert view.span == "noviembre de 2023"
    assert view.stats["participations"] == view.stats["total"] == view.stats["month"]


def test_absent_sources_leave_area_unregistered(monkeypatch):
    monkeypatch.setattr(ferias, "load", lambda: pd.DataFrame())
    monkeypatch.setattr(ferias, "profile", lambda: pd.DataFrame())
    assert FairView().catalog() == []


def test_dashboard_switches_source_year_and_filters_without_key_collisions():
    app = AppTest.from_string('''
from src.views.ferias import FairView
from src.views.common import period_controls
from src import ui
ui.inject_styles()
view = FairView()
view.pre_controls()
view.controls(period_controls(view.catalog()))
if view.prepare():
    ui.hero_copy(*view.hero_copy())
    view.hero_visual()
    ui.kpi_grid(view.kpi_cards())
    view.dashboard()
''', default_timeout=30).run()
    assert not app.exception
    assert app.segmented_control(key="ferias_source").value == "empleabilidad_autoempleo"
    assert len(app.get("plotly_chart")) == 7
    app.multiselect(key="ferias_categories").set_value(["Técnico"]).run()
    assert not app.exception
    app.segmented_control(key="ferias_source").set_value("inclusion_economica").run()
    assert not app.exception
    assert app.multiselect(key="ferias_categories").value == []
    app.segmented_control(key="period_year").set_value(2023).run()
    assert not app.exception
    assert app.segmented_control(key="period_month").options == ["Noviembre", "Diciembre"]
    app.segmented_control(key="period_month").set_value("2023-11").run()
    app.multiselect(key="ferias_provinces").set_value(["17"]).run()
    assert not app.exception
    app.segmented_control(key="ferias_level").set_value("Por cantón").run()
    assert not app.exception
    assert "canton" in app.dataframe[0].value.columns
    app.button(key="ferias_reset").click().run()
    assert not app.exception
    assert app.multiselect(key="ferias_provinces").value == []


def test_registered_ferias_navigation_preserves_enos_default():
    from test_interface import _logged_in_app, _markdown

    app = _logged_in_app()
    assert "Ferias" in app.segmented_control(key="module").options
    app.segmented_control(key="module").set_value("riesgos").run()
    assert not app.exception
    assert app.date_input(key="risk_period_since").value == date(2026, 8, 28)
    app.segmented_control(key="module").set_value("ferias").run()
    assert not app.exception
    assert "Ferias de Inclusión Económica, Empleabilidad y Autoempleo" in _markdown(app)
    assert app.segmented_control(key="ferias_source").value == "empleabilidad_autoempleo"
    app.segmented_control(key="period_year").set_value(2023).run()
    app.segmented_control(key="period_month").set_value("2023-11").run()
    assert not app.exception
    assert "noviembre de 2023" in _markdown(app)
    app.segmented_control(key="ferias_source").set_value("inclusion_economica").run()
    assert not app.exception
    assert app.segmented_control(key="period_month").value == "2023-11"
    assert "Inclusión económica" in _markdown(app)
    app.segmented_control(key="module").set_value("riesgos").run()
    assert not app.exception
    assert app.date_input(key="risk_period_since").value == date(2026, 8, 28)
