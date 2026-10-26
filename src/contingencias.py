"""Contingencies and compensation mechanisms: orphanhood by femicide, coverage of contingencies, natural and anthropic
events, and the compensations for transport, diesel and returning migrants.

Each program is counted as its source measures it, and the criterion travels with every figure: children and
adolescents who receive the orphanhood bonus each month, people *enabled* for a contingency or event bonus (and those
who *collected* it, by the date of collection), and people with an *accredited* compensation payment.  People are never
added across months; bonuses enabled (records) and amounts are.  The approved social budget gives the accrued budget of
2026.  Only closed months are published: the month of the extraction of the event bases is still open, so it waits for
the next update.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path
import re

import pandas as pd

from src import depuracion

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data" / "series"
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
          "diciembre")

PROGRAMS: dict[str, dict] = {
    "ORFANDAD_VIOLENCIA": {"label": "Orfandad por femicidio", "group": "contingencia", "icon": "heart", "tone": "fucsia",
                           "full": "Bono para niñas, niños y adolescentes en situación de orfandad por muerte violenta de la madre o progenitora",
                           "people": "Niñas, niños y adolescentes", "criterion": "beneficiarios", "unit": "beneficiarios"},
    "CONTINGENCIAS": {"label": "Cobertura de contingencias", "group": "contingencia", "icon": "life-buoy", "tone": "morado",
                      "full": "Cobertura de contingencias", "people": "Personas habilitadas", "criterion": "habilitados",
                      "unit": "personas habilitadas"},
    "ANTROPICOS": {"label": "Eventos naturales y antrópicos", "group": "contingencia", "icon": "storm", "tone": "violeta",
                   "full": "Bono para personas afectadas por eventos de origen natural o antrópico", "people": "Personas habilitadas",
                   "criterion": "habilitados", "unit": "personas habilitadas"},
    "COMPENSACION_GASOLINA": {"label": "Compensación al transporte", "group": "compensacion", "icon": "fuel", "tone": "oro",
                              "full": "Mecanismo de protección a los usuarios del transporte", "people": "Personas con pago acreditado",
                              "criterion": "acreditados", "unit": "personas con pago acreditado"},
    "COMPENSACION_DIESEL": {"label": "Compensación diésel", "group": "compensacion", "icon": "fuel", "tone": "oro",
                            "full": "Mecanismo de compensación diésel", "people": "Personas con pago acreditado",
                            "criterion": "acreditados", "unit": "personas con pago acreditado"},
    "MIGRANTES": {"label": "Migrantes retornados", "group": "compensacion", "icon": "plane", "tone": "lila",
                  "full": "Migrantes retornados", "people": "Personas con pago acreditado", "criterion": "acreditados",
                  "unit": "personas con pago acreditado"},
}
CRITERIA = {"beneficiarios": "Beneficiarios del mes", "habilitados": "Personas habilitadas en el mes",
            "acreditados": "Personas con pago acreditado en el mes"}

# Types of contingency as the source writes them -> readable name (spelling variants add up).
TYPES = [
    (r"SEPELIO.*HOSPITALES", "Sepelio por fallecimiento en hospitales del MSP"),
    (r"SEPELIO.*MUERTES? VIOLENTAS?", "Sepelio por muerte violenta"),
    (r"SEPELIO.*FUENTE.*INGRESO", "Sepelio del sostén del hogar"),
    (r"SEPELIO.*ACCIDENTES", "Sepelio por accidente de tránsito"),
    (r"INCENDIO", "Incendios"),
    (r"CALAMIDADES|DESASTRES", "Calamidades por desastres naturales"),
    (r"ORFANDAD", "Orfandad total"),
    (r"DESAPARICION", "Atención humanitaria por desaparición"),
    (r"^GENERAL$", "Eventos naturales y antrópicos"),
    (r"JAIBA", "Contingencia jaiba mora"),
]


def type_name(raw: object) -> str:
    text = depuracion.key(raw)
    for pattern, name in TYPES:
        if re.search(pattern, text):
            return name
    return str(raw).capitalize()


def _money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def _read(name: str) -> pd.DataFrame:
    path = SERIES / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def extraction() -> datetime | None:
    """Date and hour the event bases were extracted (written in their source file names)."""
    path = SERIES / "actualizacion.json"
    if not path.exists():
        return None
    sources = json.loads(path.read_text(encoding="utf-8")).get("fuentes", {})
    moments = []
    for key in ("antropicos", "contingencias"):
        match = re.search(r"_(\d{12})\.", str((sources.get(key) or {}).get("archivo", "")))
        if match:
            moments.append(datetime.strptime(match[1], "%Y%m%d%H%M"))
    return min(moments) if moments else None


def closed_until() -> str | None:
    """Last closed month of the area: the month before the extraction of the event bases («2026-09»)."""
    moment = extraction()
    if moment is None:
        return None
    year, month = (moment.year, moment.month - 1) if moment.month > 1 else (moment.year - 1, 12)
    return f"{year}-{month:02d}"


def _closed(frame: pd.DataFrame, column: str = "periodo_id") -> pd.DataFrame:
    limit = closed_until()
    return frame.loc[frame[column].astype(str).le(limit)] if limit and not frame.empty else frame


@lru_cache(maxsize=1)
def monthly() -> pd.DataFrame:
    """One row per month and program: people (by the program's criterion), records, amounts, collections and budget."""
    rows = []
    orphans = _read("beneficiarios_orfandad")
    if not orphans.empty:
        rows.append(pd.DataFrame({"periodo_id": orphans.periodo, "programa_id": "ORFANDAD_VIOLENCIA",
                                  "personas": orphans.beneficiarios.astype(float), "registros": orphans.registros.astype(float)}))
    payments = _read("incentivos_mensuales")
    if not payments.empty:
        payments = payments.assign(monto=_money(payments.monto_acreditado))
        payments = payments.loc[payments.programa_id.isin(PROGRAMS)]
        grouped = payments.groupby(["periodo", "programa_id"], as_index=False).agg(acreditados=("beneficiarios", "sum"),
                                                                                    transferencias=("transferencias", "sum"),
                                                                                    monto=("monto", "sum"))
        compensation = grouped.loc[grouped.programa_id.ne("ORFANDAD_VIOLENCIA")]
        rows.append(pd.DataFrame({"periodo_id": compensation.periodo, "programa_id": compensation.programa_id,
                                  "personas": compensation.acreditados.astype(float), "registros": compensation.transferencias.astype(float),
                                  "monto": compensation.monto, "acreditados": compensation.acreditados.astype(float)}))
        orphan_pay = grouped.loc[grouped.programa_id.eq("ORFANDAD_VIOLENCIA")]
        rows.append(pd.DataFrame({"periodo_id": orphan_pay.periodo, "programa_id": "ORFANDAD_VIOLENCIA", "monto": orphan_pay.monto,
                                  "acreditados": orphan_pay.acreditados.astype(float)}))
    for name, program in (("contingencias_mensuales", "CONTINGENCIAS"), ("antropicos_mensuales", "ANTROPICOS")):
        events = _read(name)
        if events.empty:
            continue
        events = events.assign(monto_usd=_money(events.monto_usd))
        enabled = events.loc[events.criterio.eq("habilitado")]
        collected = events.loc[events.criterio.eq("cobrado")]
        rows.append(pd.DataFrame({"periodo_id": enabled.periodo, "programa_id": program, "personas": enabled.beneficiarios.astype(float),
                                  "registros": enabled.registros.astype(float), "monto": enabled.monto_usd}))
        rows.append(pd.DataFrame({"periodo_id": collected.periodo, "programa_id": program, "cobrados": collected.beneficiarios.astype(float),
                                  "monto_cobrado": collected.monto_usd}))
    budget = _read("presupuesto_social_mensual")
    if not budget.empty:
        budget = budget.loc[budget.programa_id.isin(PROGRAMS)]
        rows.append(pd.DataFrame({"periodo_id": budget.periodo, "programa_id": budget.programa_id,
                                  "devengado_mes": _money(budget.devengado_mes), "devengado_acumulado": _money(budget.devengado_acumulado)}))
    if not rows:
        return pd.DataFrame()
    frame = pd.concat(rows, ignore_index=True)
    columns = ["personas", "registros", "monto", "acreditados", "cobrados", "monto_cobrado", "devengado_mes", "devengado_acumulado"]
    for column in columns:
        if column not in frame:
            frame[column] = float("nan")
    frame = frame.groupby(["periodo_id", "programa_id"], as_index=False)[columns].sum(min_count=1)
    allocations = _read("presupuesto_social_asignado")
    if not allocations.empty:
        approved = dict(zip(allocations.grupo_presupuestario, _money(allocations.presupuesto_aprobado)))
        year = int(str(allocations.periodo.max())[:4])
        frame["presupuesto_aprobado"] = [approved.get(p) if int(m[:4]) == year else None for p, m in zip(frame.programa_id, frame.periodo_id)]
        frame["presupuesto_aprobado"] = pd.to_numeric(frame.presupuesto_aprobado, errors="coerce")
    else:
        frame["presupuesto_aprobado"] = float("nan")
    frame["anio"] = frame.periodo_id.str[:4].astype(int)
    frame["mes"] = frame.periodo_id.str[5:7].astype(int)
    frame["programa"] = frame.programa_id.map(lambda p: PROGRAMS[p]["label"])
    frame["criterio"] = frame.programa_id.map(lambda p: PROGRAMS[p]["criterion"])
    # The month of the extraction is still open: it is published once it closes.
    frame = _closed(frame)
    return frame.sort_values(["periodo_id", "programa_id"]).reset_index(drop=True)


def catalog() -> list[dict]:
    """Closed months with information, newest first."""
    frame = monthly()
    if frame.empty:
        return []
    out = []
    for period_id in sorted(frame.loc[frame[["personas", "devengado_mes"]].notna().any(axis=1)].periodo_id.unique(), reverse=True):
        year, month = map(int, period_id.split("-"))
        out.append({"id": period_id, "year": year, "month": month, "label": f"{MONTHS[month - 1].capitalize()} {year}"})
    return out


@lru_cache(maxsize=1)
def territorial() -> pd.DataFrame:
    """Enabled and collected bonuses of contingencies and events by month, place and type, located in the DPA."""
    frames = []
    for name, program, parish in (("contingencias_territorial", "CONTINGENCIAS", "parroquia"), ("antropicos_territorial", "ANTROPICOS", None)):
        rows = _read(name)
        if rows.empty:
            continue
        rows = depuracion.locate_frame(rows, province="provincia", canton="canton", parish=parish)
        rows = rows.assign(programa_id=program, monto=_money(rows.monto_usd), tipo_nombre=rows.tipo.map(type_name))
        frames.append(rows)
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True)
    keep = ["periodo", "anio", "mes", "programa_id", "criterio", "tipo_nombre", "provincia_codigo", "provincia_nombre", "canton_codigo",
            "canton_nombre", "parroquia_codigo", "parroquia_nombre", "beneficiarios", "registros", "monto"]
    frame = frame[[c for c in keep if c in frame]].rename(columns={"periodo": "periodo_id"})
    return _closed(frame)


def year_to_date(frame: pd.DataFrame, period_id: str) -> pd.DataFrame:
    """Rows of the year of ``period_id`` up to that month (bonuses and amounts add up over months)."""
    year = period_id[:4]
    return frame.loc[frame.periodo_id.str[:4].eq(year) & frame.periodo_id.le(period_id)]
