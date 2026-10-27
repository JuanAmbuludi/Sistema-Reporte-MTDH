"""Riesgos by period: every source is cut by its own dates, and a period that ends on a day reproduces what was reported
that day, also after new data arrive."""
from datetime import date
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import shutil

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
    # The territorial report of 26/10 is inside the period; the bonus has no date per record and its confirmed period
    # (28/09–27/10) is not inside 20/10–27/10: no figure for it, never a zero.
    assert part.closed_units == 99
    cards = v.kpi_cards()
    assert cards[2]["value"] is None and cards[3]["value"] is None
    assert "sin desglose temporal" in part.missing_text()
    early = view(until="2026-10-20")
    assert early.response.available["continuidad"] is False and early.kpi_cards()[4]["value"] is None
    assert len(early.response.alerts) == int(alert_days.le("2026-10-20").sum())
    # The alerts of a province or a service stay inside the period too.
    assert len(view(since="2026-10-20", provinces=("09",)).response.alerts) <= len(view(provinces=("09",)).response.alerts)


def test_before_the_first_publication_the_period_is_rebuilt_and_says_so():
    r = view(until="2026-10-20").response
    assert r.publication == {"dia": pd.Timestamp("2026-10-27"), "exacta": False}
    assert r.publication_text().startswith("No hay una publicación guardada al 20/10/2026")
    assert "Periodo del 28/09/2026 al 20/10/2026" in r.notes()["period"]


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
    # The bonus has no figure for this period: a dash, not a zero.
    headline = cover.split("Unidades de atención cerradas")[0]
    assert "Sin desglose temporal" in headline and "USD 0" not in headline
    wb = openpyxl.load_workbook(BytesIO(generate_xlsx(ctx)), data_only=True)
    cells = [str(c.value) for row in wb["Ficha técnica"].iter_rows() for c in row if c.value is not None]
    assert "Del 20/10/2026 al 27/10/2026" in cells and "27/10/2026" in cells
    assert any(c.startswith("Periodo del 20/10/2026 al 27/10/2026") for c in cells)


def test_the_dashboard_reads_a_period_of_days():
    from test_interface import _logged_in_app, _markdown
    app = _logged_in_app()
    app.segmented_control(key="module").set_value("riesgos").run()
    assert not app.exception
    assert [(d.label, d.value) for d in app.date_input] == [("Desde", date(2026, 9, 28)), ("Hasta", date(2026, 10, 27))]
    assert "Del 28/09/2026 al 27/10/2026" in _markdown(app)
    app.date_input(key="risk_until").set_value(date(2026, 10, 20)).run()
    assert not app.exception
    html = _markdown(app)
    assert "Del 28/09/2026 al 20/10/2026" in html and "No hay una publicación guardada al 20/10/2026" in html
    # «Desde» after «Hasta» moves the end with it.
    app.date_input(key="risk_since").set_value(date(2026, 10, 25)).run()
    assert [d.value for d in app.date_input] == [date(2026, 10, 25), date(2026, 10, 25)]
    next(b for b in app.button if b.label == "Restablecer filtros").click().run()
    assert [d.value for d in app.date_input] == [date(2026, 9, 28), date(2026, 10, 27)]
