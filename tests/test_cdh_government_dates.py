"""The government window excludes November disbursements reported in December."""
import pandas as pd
import pytest

from scripts.preparar_cdh_historico import prepare_dated
from src.reports.gestion import _within


def test_disbursement_month_precedes_reporting_month_and_missing_dates_stay_explicit():
    source = pd.DataFrame({
        "FECHA_DESEMBOLSO": ["2023-11-30", "2023-12-01", "2023-12-31", None],
        "PERIODO_ARCHIVO": ["2023-12", "2023-12", "2024-01", "2023-12"],
        "MONTO": [600.00, 1108.49, 600.00, 1108.49],
        "TIPO_SUBSIDIO": ["Bono de Desarrollo Humano"] * 4,
        "GENERO": ["Femenino", "Masculino", "Femenino", "Femenino"],
    })
    rows, metadata = prepare_dated(source)
    government = _within(rows, "2023-12", "2026-09", "periodo")
    assert government.creditos.sum() == 3
    assert government.monto.sum() == pytest.approx(2816.98)
    assert government.loc[government.fecha_precision.eq("mes_reporte"), "creditos"].sum() == 1
    assert set(government.periodo) == {"2023-12"}
    assert rows.creditos.sum() == len(source) == metadata["creditos"]
    assert metadata["sin_fecha_diaria"] == 1
    assert metadata["monto"] == pytest.approx(source.MONTO.sum())
