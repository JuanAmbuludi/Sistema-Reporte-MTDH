"""Offline contract tests; live sources are not queried by the test suite."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.laboral import build_laboral, card_count, integer, parse_monthly, parse_retirement_html


def snapshot(*, monthly=False):
    value = {"tarjeta": "Cantidad de Contratos 100.", "actualizacion": "22/10/2026 3:56:59",
             "desde": "31/12/2015", "hasta": "21/10/2026",
             "estado": {"Finalizado": False, "Vigente": True},
             "otros_seleccionados": [], "desplegables": ["Todas"]}
    if monthly:
        value.update({"tarjeta": "Cantidad de Contratos 30.", "desde": "01/01/2026", "hasta": "28/02/2026",
                      "meses": ["ene", "feb"], "anios": ["2026"], "valores": ["10", "20"]})
    return value


def evidence():
    paragraph = ("Solo durante 2026, el Gobierno Nacional ha destinado más de USD 229 millones "
                 "para el pago de compensaciones jubilares, beneficiando a 4.676 exservidores y extrabajadores.")
    article = ('<meta property="article:published_time" content="2026-08-25T14:35:28+00:00"><p>' + paragraph + '</p>').encode()
    return {"fecha_consulta_utc": "2026-10-22T12:00:00+00:00", "desde": "2026-01", "hasta": "2026-02",
            "sut": {"landing_url": "https://sut.trabajo.gob.ec/", "powerbi_url": "https://app.powerbi.com/view?r=test",
                    "total": snapshot(), "series": [{"inicio": "2026-01-01", "fin": "2026-02-28", "snapshot": snapshot(monthly=True)}]},
            "jubilados": {**parse_retirement_html(article), "url": "https://www.trabajo.gob.ec/noticia/"}}


class SourceValidationTests(unittest.TestCase):
    def test_rounded_and_invalid_counts_rejected(self):
        self.assertEqual(integer("2.789.419"), 2789419)
        self.assertEqual(card_count("Cantidad de Contratos 507.451."), 507451)
        for value in ["52,1 mil", "1.23", "-1", "", None, "12,5", "1e3"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                integer(value)

    def test_monthly_reconciles_exact_values(self):
        self.assertEqual(parse_monthly(snapshot(monthly=True), date(2026, 1, 1), date(2026, 2, 28)),
                         [(date(2026, 1, 1), 10), (date(2026, 2, 1), 20)])

    def test_missing_month_wrong_year_wrong_filter_sum_and_status_fail(self):
        changes = [{"meses": ["ene"]}, {"anios": ["2025"]}, {"desde": "02/01/2026"},
                   {"valores": ["10", "21"]}, {"valores": ["10", "20 mil"]},
                   {"estado": {"Finalizado": True, "Vigente": True}},
                   {"otros_seleccionados": ["Mujer"]}, {"desplegables": ["Pichincha"]}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_monthly({**snapshot(monthly=True), **change}, date(2026, 1, 1), date(2026, 2, 28))

    def test_retirement_bound_is_not_an_exact_amount(self):
        row = evidence()["jubilados"]
        self.assertEqual(row["beneficiarios"], 4676)
        self.assertEqual(row["monto_usd"], "229000000")
        self.assertEqual(row["operador_monto"], ">")
        self.assertEqual(row["publicacion"], "2026-08-25T14:35:28+00:00")
        with self.assertRaises(ValueError):
            parse_retirement_html(b"<p>Fuente cambiada</p>")


class LaboralPersistenceTests(unittest.TestCase):
    def test_schema_dates_evidence_and_archived_cut(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = build_laboral(evidence(), temp)
            root = Path(temp)
            table = pq.read_table(root / "gestion_laboral.parquet")
            self.assertEqual(table.num_rows, 5)
            self.assertEqual(table.schema.field("valor").type.scale, 2)
            rows = {r["indicador_id"]: r for r in table.to_pylist()}
            pension = rows["compensaciones_jubilares_usd"]
            self.assertEqual(pension["valor"], Decimal("229000000.00"))
            self.assertEqual(pension["operador"], ">")
            self.assertIsNone(pension["periodo"])
            self.assertIsNone(pension["filtro_hasta"])
            self.assertEqual(pension["anio"], 2026)
            self.assertIsNone(rows["contratos_vigentes_total"]["periodo"])
            self.assertEqual(hashlib.sha256((root / manifest["evidencia"]).read_bytes()).hexdigest(), manifest["evidencia_sha256"])
            self.assertEqual((root / manifest["copia_del_corte"]).read_bytes(), (root / "gestion_laboral.parquet").read_bytes())
            replay = json.loads((root / manifest["evidencia"]).read_text())
            self.assertEqual(build_laboral(replay, temp)["consulta_id"], manifest["consulta_id"])

    def test_source_refresh_missing_interval_and_tampered_article_rejected_before_write(self):
        cases = []
        e = evidence(); e["sut"]["series"][0]["snapshot"]["actualizacion"] = "23/10/2026 3:56:59"; cases.append(e)
        e = evidence(); e["hasta"] = "2026-03"; cases.append(e)
        e = evidence(); e["jubilados"]["beneficiarios"] = 4686; cases.append(e)
        e = evidence(); e["sut"]["series"].append(copy.deepcopy(e["sut"]["series"][0])); cases.append(e)
        for case in cases:
            with self.subTest(case=cases.index(case)), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                sentinel = root / "gestion_laboral.parquet"
                sentinel.write_bytes(b"previous-valid-dataset")
                with self.assertRaises(ValueError):
                    build_laboral(case, root)
                self.assertEqual(sentinel.read_bytes(), b"previous-valid-dataset")

    def test_cli_replay_and_failed_combined_build_preserve_existing_bases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "evidence.json"
            raw.write_text(json.dumps(evidence()), encoding="utf-8")
            out = root / "out"
            command = [sys.executable, str(ROOT / "scripts/build_data.py")]
            completed = subprocess.run(command + ["--solo-laboral", "--laboral-evidencia", str(raw), "--output", str(out)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            before = (out / "gestion_laboral.parquet").read_bytes()
            (out / "indicadores.parquet").write_bytes(b"keep-existing-vis-vie")
            raw.write_text('{"invalid": true}', encoding="utf-8")
            failed = subprocess.run(command + [str(ROOT / "data/source/Acumulado_VIS_VIE"), "--period", "2026-09",
                                    "--incluir-laboral", "--laboral-evidencia", str(raw), "--output", str(out)], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((out / "gestion_laboral.parquet").read_bytes(), before)
            self.assertEqual((out / "indicadores.parquet").read_bytes(), b"keep-existing-vis-vie")


if __name__ == "__main__":
    unittest.main()
