"""Data correctness gates shared by the dashboard and all output formats.

Run: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import aggregate, filter_data, load_data, load_history, load_manifest, summarize
from src.etl import build_dataset, join_execution, number, parse_period


class DeliveredSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_data()

    def test_expected_grain_and_source_totals(self):
        self.assertEqual(len(self.df), 296)
        self.assertFalse(self.df.duplicated(["periodo", "programa_id", "provincia_codigo"]).any())
        stats = summarize(self.df)
        self.assertEqual(stats["beneficiarios"], 1578019)
        self.assertEqual(stats["usuarios_servicios"], 456239)
        self.assertEqual(stats["unidades"], 11158)
        self.assertEqual(stats["provincias"], 24)
        self.assertIsNone(stats["presupuesto_ejecutado"])

    def test_each_service_matches_supplied_bulletin(self):
        totals = aggregate(self.df, "programa_id").set_index("programa_id")
        expected = {"DII": (274975, 6759), "PAM_SERV": (114697, 2792),
                    "PCD_SERV": (37039, 1229), "PE": (29528, 378)}
        for key, (users, units) in expected.items():
            self.assertEqual(totals.loc[key, "usuarios"], users)
            self.assertEqual(totals.loc[key, "unidades"], units)

    def test_money_reconciles_without_readding_components(self):
        errors = (self.df.monto_anterior + self.df.monto_fiscal - self.df.monto_gobierno).abs()
        self.assertLess(errors.max(), 0.00001)
        totals = aggregate(self.df, "seccion")
        self.assertAlmostEqual(totals.monto_gobierno.sum(), self.df.monto_gobierno.sum(), places=4)

    def test_null_does_not_become_zero(self):
        bonos = filter_data(self.df, secciones=["bonos_pensiones"])
        self.assertTrue(bonos.unidades.isna().all())
        self.assertTrue(aggregate(bonos).unidades.isna().all())
        self.assertTrue(aggregate(self.df).presupuesto_ejecutado.isna().all())
        self.assertIsNone(summarize(bonos)["unidades"])

    def test_filters_are_intersections_and_explicit_empty_means_empty(self):
        selection = filter_data(self.df, provincias=["01"], programas=["DII"], secciones=["proteccion_integral"])
        self.assertEqual(len(selection), 1)
        self.assertEqual(selection.usuarios.iloc[0], 8270)
        self.assertEqual(len(filter_data(self.df, provincias=[])), 0)
        self.assertEqual(len(filter_data(self.df, provincias=["Azuay"])), 12)

    def test_snapshot_cannot_be_added_to_another_month(self):
        modified = self.df.copy()
        modified.loc[0, "periodo"] = pd.Timestamp("2026-08-01")
        with self.assertRaisesRegex(ValueError, "un solo corte"):
            summarize(modified)
        with self.assertRaisesRegex(ValueError, "un solo corte"):
            aggregate(modified)

    def test_history_cannot_be_misread_as_monthly(self):
        history = load_history()
        self.assertEqual(len(history), 592)
        self.assertTrue(history.periodo.isna().all())
        self.assertFalse(history.corte_documentado.any())
        with self.assertRaisesRegex(ValueError, "referencias históricas"):
            aggregate(history)

    def test_prior_only_bonuses_are_retained(self):
        prior_only = filter_data(self.df, programas=["PAM", "PCD"])
        self.assertEqual(prior_only.usuarios.sum(), 0)
        self.assertEqual(prior_only.monto_fiscal.sum(), 0)
        self.assertGreater(prior_only.monto_gobierno.sum(), 284000)


class InputValidationTests(unittest.TestCase):
    def test_negative_fractional_and_missing_counts_rejected(self):
        for value in [-1, 1.2, None, float("nan"), "#VALUE!", True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value, "prueba", count=True)
        self.assertEqual(number(0, "cero", count=True), 0)
        self.assertIsNone(number(None, "sin dato", allow_none=True))

    def test_cutoff_required_and_validated(self):
        self.assertEqual(parse_period("2026-09"), date(2026, 9, 1))
        for value in ["2026", "2026-13", "2026-9", "2026-09-01"]:
            with self.assertRaises(ValueError):
                parse_period(value)

    def _execution_file(self, directory, rows):
        path = Path(directory) / "execution.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["periodo", "programa_id", "provincia_codigo", "presupuesto_ejecutado"])
            writer.writerows(rows)
        return path

    def test_execution_exact_key_join_and_partial_totals(self):
        records = [{"programa_id": "DII", "provincia_codigo": "01", "presupuesto_ejecutado": None},
                   {"programa_id": "DII", "provincia_codigo": "02", "presupuesto_ejecutado": None}]
        with tempfile.TemporaryDirectory() as temp:
            source = self._execution_file(temp, [["2026-09", "DII", "01", "12.34"]])
            audit = join_execution(records, source, date(2026, 9, 1))
        self.assertEqual(audit["cobertura_pct"], 50)
        self.assertEqual(records[0]["presupuesto_ejecutado"], Decimal("12.340000"))
        self.assertIsNone(records[1]["presupuesto_ejecutado"])
        df = load_data().iloc[:2].copy()
        df.loc[df.index[0], "presupuesto_ejecutado"] = 12.34
        self.assertIsNone(summarize(df)["presupuesto_ejecutado"])
        self.assertEqual(summarize(df)["presupuesto_ejecutado_parcial"], 12.34)
        self.assertTrue(aggregate(df, "programa_id").presupuesto_ejecutado.isna().all())

    def test_execution_rejects_duplicates_orphans_wrong_period_negative_and_empty(self):
        invalid = [
            [["2026-09", "DII", "01", "1"], ["2026-09", "DII", "01", "2"]],
            [["2026-09", "UNKNOWN", "01", "1"]],
            [["2026-08", "DII", "01", "1"]],
            [["2026-09", "DII", "01", "-1"]], [],
        ]
        with tempfile.TemporaryDirectory() as temp:
            for rows in invalid:
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    join_execution([{"programa_id": "DII", "provincia_codigo": "01"}],
                                   self._execution_file(temp, rows), date(2026, 9, 1))


class RebuildTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("MTDH_SOURCE_EXCEL"), "Set MTDH_SOURCE_EXCEL to exercise the original Excel end to end.")
    def test_full_rebuild_retains_totals_and_decimal_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            result = build_dataset(os.environ["MTDH_SOURCE_EXCEL"], temp, "2026-09", period_source="Prueba de conciliación")
            self.assertEqual(result["totales"]["beneficiarios"], 1578019)
            self.assertEqual(result["control_calidad"]["diferencias_acumulado_2025"], 0)
            self.assertEqual(pq.read_schema(Path(temp) / "indicadores.parquet").field("monto_fiscal").type.scale, 6)
            self.assertEqual(summarize(load_data(temp))["usuarios_servicios"], 456239)


if __name__ == "__main__":
    unittest.main()
