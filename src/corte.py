"""Cut and update of the information of each area: shown on the dashboard and printed on every document.

The *cut* is the period the figures describe (September 2026, or the date and hour of the daily labour cut); the
*update* is when the bases were processed and published (the manifests record it in UTC).  Social programs and the
budget are updated every month; labour contracts every day.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
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


@lru_cache(maxsize=4)
def _updated(stamp: float) -> datetime | None:
    moments = []
    for name in ("manifest.json", "manifest_financiero.json", "manifest_laboral.json"):
        path = PROCESSED / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("generado_utc") or data.get("fecha_consulta_utc")
        if value:
            try:
                moments.append(datetime.fromisoformat(value))
            except ValueError:
                continue
    return max(moments).astimezone(ECUADOR) if moments else None


def updated_at() -> datetime | None:
    """When the bases were last processed and published, in Ecuador time."""
    paths = [PROCESSED / n for n in ("manifest.json", "manifest_financiero.json", "manifest_laboral.json")]
    stamp = max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)
    return _updated(stamp)


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


def stamp(area: str, period: dict | None = None) -> dict:
    """Cut, update and frequency of an area, in words for the dashboard and the documents."""
    frequency = FREQUENCY.get(area, "mensual")
    updated = labour_consulted_at() if area == "laboral" else updated_at()
    updated_label = "Última consulta:" if area == "laboral" else "Actualizado el"
    if area == "laboral":
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
        parts.append(f"última consulta: {updated_text}" if area == "laboral" else f"actualizada el {updated_text}")
    parts.append(f"actualización {frequency}")
    line = " · ".join(parts)
    short_label = "Última consulta" if area == "laboral" else "Actualizado"
    short = " · ".join(([f"Corte: {cut_text}"] if cut_text else []) + ([f"{short_label}: {updated:%d/%m/%Y %H:%M}"] if updated else [])
                       + [f"Actualización {frequency}"])
    return {"cut": cut_text, "updated": updated_text, "updated_short": f"{updated:%d/%m/%Y %H:%M}" if updated else "",
            "frequency": f"Actualización {frequency}", "frequency_word": frequency, "line": line[:1].upper() + line[1:],
            "short": short, "updated_label": updated_label}
