"""The undated fourth phase is distinct, and every delivery fits on one cover."""
from collections import Counter
import re

import pymupdf
import pytest

from src import jovenes, jovenes_fase4
from src.reports import gestion, panorama
from src.reports.context import number
from test_reports_historico_ferias import bases  # noqa: F401 - shared source fixture


@pytest.mark.parametrize("mode", ["anual", "gobierno"])
def test_fourth_phase_is_an_independent_undated_reference(bases, mode):
    ctx = gestion.build(bases, mode)
    blocks = {item["key"]: item for item in ctx["blocks"]}
    fourth = blocks["jovenes_fase4"]
    stats = jovenes_fase4.summary()
    assert "corte sin fecha" in fourth["period"]
    assert fourth["stats"]["acreditadas"] == 685867
    assert sum(r["acreditadas"] for r in fourth["table"]["rows"][:-1]) == stats["acreditadas"]
    assert sum(r["no_acreditadas"] for r in fourth["table"]["rows"][:-1]) == stats["no_acreditadas"] == 14021
    reasons = fourth["tables"][0]["rows"][:-1]
    assert len(reasons) == 10
    assert sum(r["transferencias"] for r in reasons) == 14021
    payments = jovenes.payments()
    start = "2026-01" if mode == "anual" else "2023-12"
    expected = payments.loc[payments.periodo_id.between(start, "2026-09")].transferencias.sum()
    assert blocks["jovenes"]["kpis"][0]["value"] == expected
    assert ctx["programs_label"] == "10 secciones del Ministerio"
    order = [item["key"] for item in ctx["blocks"]]
    assert order.index("jovenes_fase4") == order.index("jovenes") + 1


def test_latest_overview_includes_the_separate_phase_four_reference(bases):
    ctx = panorama.build_panorama(bases, "Informe")
    fourth = next(b for b in ctx["blocks"] if b["key"] == "jovenes_fase4")
    assert fourth["stats"]["monto_acreditado"] == 274346800
    assert fourth["stats"]["monto_no_acreditado"] == 5608400
    assert "sin fecha" in fourth["period"]
    assert ctx["programs_label"] == "10 secciones"


def test_every_government_delivery_is_complete_on_the_first_page(bases):
    ctx = gestion.build(bases, "gobierno")
    assert len(ctx["deliveries"]) == 15
    content = gestion.generate(ctx)
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        first = re.sub(r"\s+", " ", doc[0].get_text())
        expected_labels = Counter(d["what"] for d in ctx["deliveries"])
        for label, count in expected_labels.items():
            assert first.count(label) >= count, label
        for delivery in ctx["deliveries"]:
            assert number(delivery["amount_people"]) in first
            assert delivery["detail"] in first
            if delivery.get("money"):
                assert gestion._money(delivery["money"]) in first
            assert delivery["context"] in first
        assert "Continuación de las entregas" not in " ".join(page.get_text() for page in doc)
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    assert 0 <= x0 < x1 <= doc[0].rect.width
                    assert 0 <= y0 < y1 <= doc[0].rect.height
