"""Riesgos by period: every source is cut by its own dates, and a period that ends on a day reproduces what was reported
that day, also after new data arrive."""
from datetime import date
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import shutil
import hashlib
import pytest

import openpyxl
import pandas as pd
import pymupdf

from src import enos
from src.reports import generate_pdf, generate_xlsx
from src.views.riesgos import RiskView

ROOT = Path(__file__).resolve().parents[1]


def view(**period) -> RiskView:
    v = RiskView()
    v.select(v.catalog()[-1], **period)
    assert v.prepare()
    return v


def values(v: RiskView) -> list:
    return [card["value"] for card in v.kpi_cards()]


def open_day(day: str):
    spec = importlib.util.spec_from_file_location("nuevo_corte_riesgos", ROOT / "scripts/nuevo_corte_riesgos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.open_day(day)


def test_publications_are_named_by_the_day_they_were_reported_and_carry_their_scopes():
    found = enos.publications(enos.SNAPSHOT)
    assert found and enos.publications(enos.CONTINUITY)
    for day, path in found:
        data = enos.load(path)
        start, cut = enos.window(data)
        # Nothing in a publication comes after the day it was reported, and its scopes travel with it.
        assert start <= cut <= day, path.name
        assert all(enos.notes(data)[key] for key in ("alertas", "kits", "bono")), path.name
    for day, path in enos.publications(enos.CONTINUITY):
        cut = enos.continuity_cut(enos.continuity(path))
        assert cut is None or cut.normalize() <= day, path.name


def test_closed_days_are_never_edited():
    for day, files in enos.ledger()["cerrados"].items():
        for name, digest in files.items():
            path = enos.FOLDER / name
            assert path.exists(), name
            assert enos.fingerprint(path) == digest, (f"{name} pertenece al {day}, un día ya reportado: los datos nuevos se publican "
                                                      "en un día nuevo con scripts/nuevo_corte_riesgos.py.")


def test_the_whole_reporting_period_is_the_default():
    v = view()
    r = v.response
    assert (v.since, v.until) == (pd.Timestamp("2026-09-28"), pd.Timestamp("2026-10-27"))
    assert r.whole and r.publication == {"dia": pd.Timestamp("2026-10-27"), "exacta": True}
    assert v.period["label"] == r.scope_text() == "Del 28/09/2026 al 27/10/2026"
    assert v.period["stamp"] == "2026-09-28_al_2026-10-27"
    assert values(v) == [39, 10607, 1171, 354987.39, 99]
    assert r.notes()["kits"].startswith("Kits en provincias priorizadas: entregas desde el 28/09/2026 hasta el corte Kobo del 27/10/2026, 13:35:45.")


def test_a_period_cuts_alerts_kits_and_territorial_reports_by_their_own_dates():
    full = view().response
    v = view(since="2026-10-20")
    part = v.response
    alert_days, kit_days = pd.to_datetime(full.alerts.fecha), pd.to_datetime(full.kits.fecha)
    assert len(part.alerts) == int(alert_days.ge("2026-10-20").sum()) == 34
    assert part.kits_total == int(full.kits.loc[kit_days.ge("2026-10-20"), "kits"].sum())
    assert pd.to_datetime(part.alerts.fecha).ge("2026-10-20").all() and pd.to_datetime(part.kits.fecha).ge("2026-10-20").all()
    # The confirmed bonus is an accumulated reference, independent of the selected dates.
    assert part.closed_units == 99
    cards = v.kpi_cards()
    assert cards[2]["value"] == 1171 and cards[3]["value"] == 354987.39
    assert "flujo diario" in part.period_note()
    # The alerts of a province or a service stay inside the period too.
    assert len(view(since="2026-10-20", provinces=("09",)).response.alerts) <= len(view(provinces=("09",)).response.alerts)


def test_before_the_first_publication_no_later_data_are_used():
    assert enos.in_force(enos.SNAPSHOT, "2026-10-25") == (None, False)
    assert enos.in_force(enos.CONTINUITY, "2026-10-25") == (None, False)
    v = RiskView()
    v.select(v.catalog()[-1], until="2026-10-25")
    assert not v.prepare()
    assert v.response is None and v.kpi_cards() == []
    with pytest.raises(ValueError, match="No hay un corte"):
        v.report_context("Riesgos")


def test_the_end_of_a_period_reproduces_what_was_reported_that_day(tmp_path, monkeypatch):
    for _day, path in enos.publications(enos.SNAPSHOT) + enos.publications(enos.CONTINUITY):
        shutil.copy(path, tmp_path / path.name)
    monkeypatch.setattr(enos, "FOLDER", tmp_path)
    monkeypatch.setattr(enos, "LEDGER", tmp_path / "cortes_riesgos.json")
    reported = values(view())
    # The next day: the script copies the latest publication and closes the day reported.
    created = open_day("2026-10-28")
    assert {path.name for path in created.values()} == {"seguimiento_enos_2026-10-28.json", "continuidad_servicios_2026-10-28.json"}
    closed = json.loads((tmp_path / "cortes_riesgos.json").read_text(encoding="utf-8"))["cerrados"]["2026-10-27"]
    assert closed == {name: enos.fingerprint(tmp_path / name) for name in ("seguimiento_enos_2026-10-27.json",
                                                                         "continuidad_servicios_2026-10-27.json")}
    # New data reach the new day only: one more alert, one more delivery and a new total of the bonus.
    path = created["seguimiento_enos"]
    data = json.loads(path.read_text(encoding="utf-8"))
    alert = dict(data["alertas"][0], codigo="ALT-2026-000999", fecha="2026-10-28")
    data["alertas"].append(alert)
    data["kits"].append(dict(data["kits"][-1], id_kobo="999999999", fecha="2026-10-28", kits=50, familias=50))
    data["bonos"]["articulacion"].append({"provincia": "Manabí", "evento": "Inundación", "personas": 10, "monto": 3039.9})
    data["bonos_periodos_confirmados"]["articulacion"].update(hasta="2026-10-28", personas=1181, monto=358027.29)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = view()
    assert latest.until == pd.Timestamp("2026-10-28") and latest.response.publication["dia"] == pd.Timestamp("2026-10-28")
    assert values(latest)[:3] == [reported[0] + 1, reported[1] + 50, 1181]
    # Ending the period on 27/10 gives back exactly the report of that day, from its own publication.
    again = view(until="2026-10-27")
    assert again.response.publication == {"dia": pd.Timestamp("2026-10-27"), "exacta": True}
    assert values(again) == reported
    pdf = pymupdf.open(stream=generate_pdf(again.report_context("Riesgos")), filetype="pdf")
    assert "Del 28/09/2026 al 27/10/2026" in pdf[0].get_text() and "ALT-2026-000999" not in " ".join(p.get_text() for p in pdf)


def test_documents_carry_the_period_and_the_publication():
    v = view(since="2026-10-20")
    ctx = v.report_context("Riesgos")
    assert ctx["period_label"] == "Del 20/10/2026 al 27/10/2026"
    pdf = pymupdf.open(stream=generate_pdf(ctx), filetype="pdf")
    cover = pdf[0].get_text()
    assert "Resumen ejecutivo · Del 20/10/2026 al 27/10/2026" in cover
    # The bonus keeps the approved accumulated balance when the dates change.
    headline = cover.split("Unidades de atención cerradas")[0]
    assert "1.171" in headline and "354.987,39" in headline and "Sin desglose temporal" not in headline
    wb = openpyxl.load_workbook(BytesIO(generate_xlsx(ctx)), data_only=True)
    cells = [str(c.value) for row in wb["Ficha técnica"].iter_rows() for c in row if c.value is not None]
    assert "Del 20/10/2026 al 27/10/2026" in cells and "27/10/2026" in cells
    assert any(c.startswith("Periodo del 20/10/2026 al 27/10/2026") for c in cells)


def test_the_dashboard_selects_the_reported_day_and_can_return_to_today():
    from test_interface import _logged_in_app, _markdown
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("riesgos").run()
    assert not app.exception
    assert [(d.label, d.value) for d in app.date_input] == [("Fecha del reporte", date(2026, 10, 27))]
    assert "Del 28/09/2026 al 27/10/2026" in _markdown(app)
    app.date_input(key="risk_until").set_value(date(2026, 10, 26)).run()
    assert not app.exception
    html = _markdown(app)
    assert "Del 29/08/2026 al 26/10/2026" in html
    assert "13.390" in html and "1.171" in html and "354.987,39" in html
    assert "Sin desglose temporal disponible" not in html
    next(b for b in app.button if b.label == "Restablecer filtros").click().run()
    assert [d.value for d in app.date_input] == [date(2026, 10, 27)]
    assert "10.607" in _markdown(app) and "1.171" in _markdown(app)


def test_yesterday_matches_the_approved_pdf_and_every_provincial_total():
    v = view(until="2026-10-26")
    assert values(v) == [10, 13390, 1171, 354987.39, 99]
    assert v.response.publication == {"dia": pd.Timestamp("2026-10-26"), "exacta": True}
    assert set(v.response.alerts.codigo) == {f"ALT-2026-{n:06d}" for n in (325, 323, 322, 321, 319, 318, 316, 315, 310, 309)}
    expected = {"Azuay": 527, "Bolívar": 141, "Carchi": 780, "Chimborazo": 7, "Cotopaxi": 250,
        "El Oro": 66, "Esmeraldas": 3820, "Guayas": 6850, "Imbabura": 498, "Loja": 79, "Los Ríos": 64,
        "Manabí": 75, "Napo": 60, "Pastaza": 7, "Pichincha": 64, "Santa Elena": 13,
        "Santo Domingo de los Tsáchilas": 17, "Sucumbíos": 44, "Tungurahua": 17, "Zamora Chinchipe": 11}
    assert v.response.kits.groupby("provincia").kits.sum().to_dict() == expected
    assert v.response.alerts.groupby("provincia").size().to_dict() == {"El Oro": 2, "Guayas": 6, "Manabí": 2}
    continuity = v.response.continuity_summary()
    assert {r["name"]: r["value"] for r in continuity["by_province"]} == {"El Oro": 75, "Guayas": 17, "Santa Elena": 7}
    assert {r["name"]: r["value"] for r in continuity["by_service"]} == {"CNH": 64, "CDI": 35}
    ctx = v.report_context("Riesgos")
    content = generate_pdf(ctx)
    assert hashlib.sha256(content).hexdigest() == "da6fb7c6032c1824a41834e5a34867abe934e94fb201712af2a51737b9ffa905"
    assert len(pymupdf.open(stream=content, filetype="pdf")) == ctx["pdf_pages"] == 3


def test_bonus_keeps_every_provincial_person_and_cent_between_report_dates():
    yesterday, today = view(until="2026-10-26"), view(until="2026-10-27")
    a = yesterday.response.articulation.groupby("provincia")[["personas", "monto"]].sum()
    b = today.response.articulation.groupby("provincia")[["personas", "monto"]].sum()
    pd.testing.assert_frame_equal(a, b)
    assert a.personas.to_dict() == {"El Oro": 181, "Esmeraldas": 530, "Guayas": 344, "Imbabura": 5, "Los Ríos": 111}
    assert a.monto.round(2).to_dict() == {"El Oro": 55022.19, "Esmeraldas": 160558.20, "Guayas": 104246.01,
                                       "Imbabura": 1519.95, "Los Ríos": 33641.04}
    assert values(view(since="2026-10-26", until="2026-10-27"))[2:4] == [1171, 354987.39]


def test_a_filtered_historical_report_never_returns_the_national_archive():
    v = view(until="2026-10-26", provinces=("09",))
    assert values(v) == [6, 6850, 344, 104246.01, 17]
    ctx = v.report_context("Riesgos de Guayas")
    assert "archived_risk_pdf" not in ctx
    doc = pymupdf.open(stream=generate_pdf(ctx), filetype="pdf")
    cover = doc[0].get_text()
    assert "6.850" in cover and "104.246,01" in cover and "13.390" not in cover


def test_original_pdf_integrity_is_verified_before_returning_it():
    metadata = dict(view(until="2026-10-26").response.data["pdf_publicado"])
    metadata["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="no coincide"):
        enos.archived_pdf(metadata)
