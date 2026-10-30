"""Cut and update of the information of each area: shown on the dashboard and printed on every document.

The *cut* is the period the figures describe (September 2026, or the date and hour of the daily labour cut); the
*update* is the last substantive change in each area's own sources. A query,
file re-save, deployment or change in another area never advances this clock.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
SERIES = ROOT / "data" / "series"
ECUADOR = ZoneInfo("America/Guayaquil")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
          "diciembre")
FREQUENCY = {"transferencias": "mensual", "servicios": "mensual", "contingencias": "mensual", "jovenes": "mensual",
             "presupuesto": "mensual", "laboral": "diaria"}


def long_date(moment: datetime, *, hour: bool = True) -> str:
    """«25 de octubre de 2026, 18:03» (or without the hour)."""
    text = f"{moment.day} de {MONTHS[moment.month - 1]} de {moment.year}"
    return f"{text}, {moment:%H:%M}" if hour else text


def _moment(value) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
        return moment.astimezone(ECUADOR) if moment.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def updated_at(area: str | None = None) -> datetime | None:
    """The persisted content revision; never infer it from filesystem times."""
    path = PROCESSED / "actualizacion_secciones.json"
    if not path.exists():
        return None
    areas = json.loads(path.read_text(encoding="utf-8")).get("areas", {})
    if area == "presupuesto":
        moments = [_moment(areas.get(key, {}).get("actualizado_utc"))
                   for key in ("presupuesto_social", "presupuesto_fiscal", "presupuesto_gobierno")]
        return max((moment for moment in moments if moment is not None), default=None)
    if area is not None:
        return _moment(areas.get(area, {}).get("actualizado_utc"))
    moments = [_moment(item.get("actualizado_utc")) for item in areas.values()]
    return max((moment for moment in moments if moment is not None), default=None)


def labour_updated_at() -> datetime | None:
    path = SERIES / "laboral/ultima_consulta.json"
    if path.exists():
        return _moment(json.loads(path.read_text(encoding="utf-8")).get("actualizado_datos_utc"))
    return None


def labour_cut() -> datetime | None:
    """Date and hour of the daily cut of the contracts published by SGDE (Ecuador time)."""
    path = SERIES / "actualizacion.json"
    if not path.exists():
        return None
    controls = json.loads(path.read_text(encoding="utf-8")).get("controles", {}).get("contratos", {})
    value = controls.get("fecha_hora_corte") or controls.get("fecha_corte")
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.replace(tzinfo=ECUADOR) if moment.tzinfo is None else moment.astimezone(ECUADOR)


def labour_consulted_at() -> datetime | None:
    """Last validated labour query, independent of unrelated modules and source cuts."""
    for path, field in ((SERIES / "laboral/ultima_consulta.json", "consulta_utc"),
                        (PROCESSED / "manifest_laboral.json", "fecha_consulta_utc")):
        if path.exists():
            try:
                value = json.loads(path.read_text(encoding="utf-8")).get(field)
                if value:
                    moment = datetime.fromisoformat(value)
                    if moment.tzinfo is not None:
                        return moment.astimezone(ECUADOR)
            except (OSError, ValueError, TypeError):
                continue
    return None


def stamp(area: str, period: dict | None = None, *, cut_text: str | None = None) -> dict:
    """Cut, update and frequency of an area, in words for the dashboard and the documents."""
    frequency = FREQUENCY.get(area, "mensual")
    updated = labour_updated_at() if area == "laboral" else updated_at(area)
    updated_label = "Actualizado el"
    if cut_text is not None:
        pass
    elif area == "laboral":
        cut = labour_cut()
        cut_text = long_date(cut) if cut else ""
    elif period and period.get("month"):
        cut_text = f"{MONTHS[period['month'] - 1]} de {period['year']}"
    elif period:
        cut_text = f"año {period['year']}"
    else:
        cut_text = ""
    updated_text = long_date(updated) if updated else ""
    parts = []
    if cut_text:
        parts.append(f"Corte de la información: {cut_text}")
    if updated_text:
        parts.append(f"actualizada el {updated_text}")
    frequency_text = "Consulta diaria" if area == "laboral" else f"Actualización {frequency}"
    parts.append(frequency_text.lower())
    line = " · ".join(parts)
    short_label = "Actualizado"
    short = " · ".join(([f"Corte: {cut_text}"] if cut_text else []) + ([f"{short_label}: {updated:%d/%m/%Y %H:%M}"] if updated else [])
                       + [frequency_text])
    return {"cut": cut_text, "updated": updated_text, "updated_short": f"{updated:%d/%m/%Y %H:%M}" if updated else "",
            "frequency": frequency_text, "frequency_word": frequency, "line": line[:1].upper() + line[1:],
            "short": short, "updated_label": updated_label}
