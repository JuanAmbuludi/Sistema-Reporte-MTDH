"""Jóvenes en Acción: phases of the program, accredited transfers and the budget of the current phase.

Three sources, never mixed: the phases published by SGDE (registered and participating young people, transfers,
budget and execution of each phase), the accredited payments of the transfer system (people with an accredited payment
and amount, by month and phase) and the approved social budget (accrued budget of the third phase).  The execution of
the third phase is the accrued budget of the approved file; the figure published by SGDE travels next to it.  The 150.000
young people of the third phase are those enabled for it, not monthly payments.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data" / "series"
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
          "diciembre")
PHASE_NAMES = {1: "Fase 1", 2: "Fase 2", 3: "Fase 3"}


def _read(name: str) -> pd.DataFrame:
    path = SERIES / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def month_label(period_id: str, *, short: bool = False) -> str:
    year, month = period_id.split("-")
    name = MONTHS[int(month) - 1]
    return f"{name[:3].capitalize()} {year[2:]}" if short else f"{name} de {year}"


@lru_cache(maxsize=1)
def phases() -> pd.DataFrame:
    """One row per phase with documented execution or attention, oldest first."""
    frame = _read("jovenes_accion_fases")
    if frame.empty:
        return frame
    frame = frame.loc[frame.periodo.eq(frame.periodo.max())].copy()
    for column in ["monto_transferencia_usd", "presupuesto_usd", "ejecucion_usd"]:
        frame[column] = _money(frame[column])
    for column in ["registrados", "participantes", "transferencias"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    frame["fase"] = frame.fase.astype(int)
    frame["nombre"] = frame.fase.map(PHASE_NAMES)
    snapshot = _read("jovenes_accion_fase3")
    if not snapshot.empty:
        row = snapshot.sort_values("periodo").iloc[-1]
        mask = frame.fase.eq(int(row.fase))
        frame.loc[mask, "devengado_aprobado"] = float(row.devengado_acumulado_aprobado)
        frame.loc[mask, "ejecucion_publicada"] = float(row.ejecucion_publicada_web)
        frame.loc[mask, "corte_devengado"] = str(row.periodo)
    for column in ["devengado_aprobado", "ejecucion_publicada"]:
        if column not in frame:
            frame[column] = float("nan")
    # Execution of each phase: the approved accrued budget when it exists, otherwise the published execution.
    frame["ejecucion"] = frame.devengado_aprobado.where(frame.devengado_aprobado.notna(), frame.ejecucion_usd)
    frame["porcentaje_ejecucion"] = frame.ejecucion / frame.presupuesto_usd.where(frame.presupuesto_usd > 0) * 100
    frame["periodo_texto"] = [period_text(start, end) for start, end in zip(frame.inicio, frame.fin)]
    return frame.sort_values("fase").reset_index(drop=True)


def period_text(start: object, end: object) -> str:
    """«diciembre de 2024 a agosto de 2025» · «desde junio de 2026»."""
    if not isinstance(start, str) or not start:
        return ""
    if isinstance(end, str) and end:
        return f"{month_label(start)} a {month_label(end)}"
    return f"desde {month_label(start)}"


@lru_cache(maxsize=1)
def payments() -> pd.DataFrame:
    """Accredited payments of the program by month and phase (people are never added across months)."""
    frame = _read("incentivos_mensuales")
    if frame.empty:
        return frame
    frame = frame.loc[frame.programa_id.eq("JEA")].copy()
    frame["monto"] = _money(frame.monto_acreditado)
    frame = frame.rename(columns={"periodo": "periodo_id", "beneficiarios": "personas"})
    frame["fase"] = frame.fase.astype(int)
    return frame[["periodo_id", "fase", "personas", "transferencias", "monto"]].sort_values(["periodo_id", "fase"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def budget() -> pd.DataFrame:
    """Accrued budget of the third phase month by month, with its approved allocation."""
    frame = _read("presupuesto_social_mensual")
    if frame.empty:
        return frame
    frame = frame.loc[frame.programa_id.eq("JEA_F3")].copy()
    frame["devengado_mes"] = _money(frame.devengado_mes)
    frame["devengado_acumulado"] = _money(frame.devengado_acumulado)
    allocation = _read("presupuesto_social_asignado")
    approved = None
    if not allocation.empty:
        row = allocation.loc[allocation.grupo_presupuestario.eq("JEA_F3")]
        approved = float(_money(row.presupuesto_aprobado).iloc[0]) if len(row) else None
    frame["presupuesto_aprobado"] = approved
    return frame.rename(columns={"periodo": "periodo_id"})[["periodo_id", "devengado_mes", "devengado_acumulado", "presupuesto_aprobado"]]


def catalog() -> list[dict]:
    """The cut of the information of the current phase (the latest month of its accrued budget)."""
    table = phases()
    if table.empty:
        return []
    money = budget()
    cut = money.loc[money.devengado_mes.notna()].periodo_id.max() if not money.empty else table.periodo.max()
    year, month = map(int, cut.split("-"))
    return [{"id": cut, "year": year, "month": month, "label": f"{MONTHS[month - 1].capitalize()} {year}"}]


def summary() -> dict:
    """Figures of the current phase and of the program for the key figures and the documents."""
    table = phases()
    if table.empty:
        return {}
    current = table.iloc[-1]
    paid = payments()
    phase_paid = paid.loc[paid.fase.eq(int(current.fase))] if not paid.empty else paid
    latest = phase_paid.sort_values("periodo_id").iloc[-1] if len(phase_paid) else None
    money = budget()
    accrued = money.loc[money.devengado_mes.notna()] if not money.empty else money
    return {
        "phase": int(current.fase), "phase_name": PHASE_NAMES.get(int(current.fase), f"Fase {int(current.fase)}"),
        "registered": current.registrados, "enabled": current.participantes, "budget": current.presupuesto_usd,
        "accrued": current.ejecucion, "published": current.ejecucion_publicada, "execution": current.porcentaje_ejecucion,
        "transfers": current.transferencias, "transfer_amount": current.monto_transferencia_usd,
        "enabled_share": current.participantes / current.registrados * 100 if current.registrados else None,
        "paid_month": latest.periodo_id if latest is not None else None,
        "paid_people": float(latest.personas) if latest is not None else None,
        "paid_amount": float(latest.monto) if latest is not None else None,
        "start": current.inicio, "cut": accrued.periodo_id.max() if len(accrued) else current.periodo,
        "total_participants": float(table.participantes.sum()),
        "accredited_total": float(paid.monto.sum()) if not paid.empty else None,
    }
