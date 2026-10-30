"""Overlapping CDH reports must reconcile without adding the portfolio to flows."""
import pandas as pd
import pytest
from scripts.preparar_cdh_historico import reconcile_merge
from src.views.cdh import CreditView


def test_month_overlap_is_preserved_and_import_is_idempotent():
    existing = pd.DataFrame([
        {'fuente':'desembolso','periodo':'2026-01','creditos':5,'monto':500.},
        {'fuente':'vigente','periodo':'2026-01','creditos':20,'monto':2000.},
    ])
    incoming = pd.DataFrame([
        {'fuente':'desembolso','periodo':'2025-12','creditos':4,'monto':400.},
        {'fuente':'desembolso','periodo':'2026-01','creditos':5,'monto':500.},
    ])
    merged, overlap, added = reconcile_merge(existing, incoming)
    assert overlap == ['2026-01'] and added == ['2025-12']
    assert merged.loc[merged.fuente.eq('desembolso'),'creditos'].sum() == 9
    assert merged.loc[merged.fuente.eq('vigente'),'creditos'].sum() == 20
    again, _, added_again = reconcile_merge(merged, incoming)
    pd.testing.assert_frame_equal(merged, again)
    assert added_again == []


def test_changed_overlap_is_rejected_instead_of_double_counted():
    old = pd.DataFrame([{'fuente':'desembolso','periodo':'2026-01','creditos':5,'monto':500.}])
    new = old.assign(creditos=6)
    with pytest.raises(ValueError, match='no concilia'):
        reconcile_merge(old, new)


def test_historical_credit_view_uses_available_span():
    view = CreditView()
    historical = next(period for period in view.catalog() if period['id'] == '2023-12')
    view.select(historical)
    assert view.prepare()
    assert view.span == 'diciembre de 2023'
    assert view.stats['credits'] == 1741
    assert view.stats['portfolio'] == 95986
    current = next(period for period in view.catalog() if period['id'] == '2026-09')
    view.select(current)
    assert view.prepare()
    assert view.stats['credits'] == 44834
    assert round(view.stats['amount'],2) == 48036993.87
