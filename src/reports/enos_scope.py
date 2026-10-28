"""Shared ENOS scopes for institutional reports, independent of publication windows."""
from __future__ import annotations

import pandas as pd

from src import enos


def response_view(start: str | None = None, end: str | None = None):
    """Prepare the latest reconciled history for whole months, or all available history.

    A report with a cover period supplies both months as ``YYYY-MM``. The overview
    of the latest cut of each section supplies neither; it retains the actual
    historical bounds instead of inheriting a published bulletin's reporting window.
    """
    from src.views.riesgos import RiskView

    if (start is None) != (end is None):
        raise ValueError("Indique ambos meses del período o ninguno.")
    selection = {}
    if start is not None:
        first, last = pd.Period(start, freq="M"), pd.Period(end, freq="M")
        if first > last:
            raise ValueError("El mes inicial no puede ser posterior al mes final.")
        selection = {"since": first.start_time.normalize(), "until": last.end_time.normalize()}
    view = RiskView()
    catalog = view.catalog()
    if not catalog:
        return None
    view.select(catalog[-1], mode="periodo", **selection)
    return view if view.prepare() and view.response is not None else None


def bonus_scope(response) -> str:
    """Label the confirmed bonus balance without turning it into a period flow."""
    cut = response.cuts.get("bonos")
    if not cut:
        return "Acumulado confirmado · corte no disponible"
    day = enos.day(cut)
    label = f"Acumulado confirmado al {day:%d/%m/%Y}"
    if not enos.day(response.start) <= day <= enos.day(response.end):
        label += " · referencia fuera del período"
    return label
