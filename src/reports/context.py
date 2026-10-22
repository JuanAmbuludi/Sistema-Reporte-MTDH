"""One immutable report snapshot shared by Word, PDF and PowerPoint.

All values come from the already-filtered dashboard dataframe.  No exporter
reopens the full source or changes the scope behind the user's selection.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo
import json
import math

import pandas as pd

SECTION_NAMES = {
    "bonos_pensiones": "Bonos y pensiones",
    "proteccion_integral": "Servicios de protección integral",
}
MONTHS = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def number(value, decimals=0):
    """Spanish display conventions, keeping a missing value distinct from zero."""
    if value is None or pd.isna(value):
        return "N/D"
    return f"{value:,.{decimals}f}".replace(",", "~").replace(".", ",").replace("~", ".")


def money(value, millions=False):
    if value is None or pd.isna(value):
        return "N/D"
    return number(value / (1_000_000 if millions else 1), 2)


def _sum(df, name, integer=False, require_complete=False):
    if name not in df or df.empty:
        return None
    values = pd.to_numeric(df[name], errors="coerce")
    if values.notna().sum() == 0 or (require_complete and values.isna().any()):
        return None
    out = float(values.sum(min_count=1))
    return int(round(out)) if integer else out


def _record(df, label, id_=None):
    result = {
        "label": str(label),
        "people": _sum(df, "usuarios", integer=True),
        "units": _sum(df, "unidades", integer=True),
        "fiscal": _sum(df, "monto_fiscal"),
        "government": _sum(df, "monto_gobierno"),
        "executed": _sum(df, "presupuesto_ejecutado", require_complete=True),
    }
    if id_ is not None:
        result["id"] = str(id_)
    return result


def _group_records(df, field, id_field=None):
    rows = []
    for value, group in df.groupby(field, sort=False, dropna=False):
        rows.append(_record(group, value, group[id_field].iloc[0] if id_field else None))
    return sorted(rows, key=lambda r: (-(r["people"] or 0), r["label"]))


def build_report_context(filtered_df: pd.DataFrame, manifest: dict | None = None, options: dict | None = None) -> dict:
    """Create a serializable, auditable report from the active dashboard filters.

    ``options`` accepts title, include_territory, author and scope_label.  It
    cannot override numbers. Empty selections are rejected explicitly.
    """
    manifest, options = manifest or {}, options or {}
    if filtered_df.empty:
        raise ValueError("No hay datos en la selección. Cambie los filtros antes de generar el informe.")
    required = {"periodo", "seccion", "programa", "programa_id", "provincia", "usuarios", "unidades", "monto_fiscal", "monto_gobierno"}
    absent = required - set(filtered_df.columns)
    if absent:
        raise ValueError("Faltan campos del modelo de reporte: " + ", ".join(sorted(absent)))
    frame = filtered_df.copy()
    periods = pd.to_datetime(frame["periodo"]).dt.to_period("M").unique()
    if len(periods) != 1:
        raise ValueError("El boletín requiere un único corte mensual. No se suman personas entre meses.")
    period = periods[0].to_timestamp()
    period_label = f"{MONTHS[period.month].capitalize()} {period.year}"
    provinces = sorted(frame["provincia"].dropna().astype(str).unique())
    programs = sorted(frame["programa"].dropna().astype(str).unique())
    real_provinces = [p for p in provinces if p.casefold() != "zona en estudio"]
    scope_label = options.get("scope_label") or (
        "Nacional - 24 provincias" + (" y zona en estudio" if len(provinces) > 24 else "")
        if len(real_provinces) == 24 else (
            ", ".join(provinces) if len(provinces) <= 3 else f"{len(real_provinces)} provincias seleccionadas" + (" y zona en estudio" if len(real_provinces) < len(provinces) else "")
        )
    )
    notes = [
        "Beneficiarios y usuarios corresponden a conteos reportados en una base agregada. La fuente no permite comprobar personas únicas ni eliminar coincidencias entre programas.",
        f"El monto fiscal corresponde a la columna Presupuesto {period.year} de la fuente. El acumulado de gobierno incluye el monto fiscal y los períodos anteriores. No deben sumarse entre sí.",
        "Los montos no representan transferencias del mes. La fuente no certifica por sí sola el presupuesto ejecutado, que se presenta como N/D cuando no existe una validación adicional.",
        "Las unidades corresponden a servicios de protección integral. En bonos y pensiones este indicador no aplica. N/D distingue información no disponible de un cero reportado.",
    ]
    period_origin = manifest.get("periodo_origen", "")
    if period_origin:
        notes.append(f"Identificación del corte: {str(period_origin).rstrip('.')}.")
    sections = []
    for id_, title in SECTION_NAMES.items():
        part = frame.loc[frame["seccion"] == id_]
        if part.empty:
            continue
        metrics = _record(part, title, id_)
        rows = _group_records(part, "programa", "programa_id")
        territories = _group_records(part, "provincia")
        people_label = "Beneficiarios reportados" if id_ == "bonos_pensiones" else "Usuarios reportados"
        lead = rows[0]
        share = ((lead["people"] or 0) / metrics["people"] * 100) if metrics["people"] else 0
        insights = [
            f"La selección reúne {number(metrics['people'])} {people_label.lower()} en {len(rows)} " + ("programas." if id_ == "bonos_pensiones" else "servicios."),
            f"{lead['label']} concentra el {number(share, 1)} % del total seleccionado, con {number(lead['people'])} registros reportados.",
        ]
        if territories and metrics["people"]:
            top3 = territories[:3]
            share3 = sum(r["people"] or 0 for r in top3) / metrics["people"] * 100
            insights.append(f"Los {len(top3)} ámbitos con mayor cobertura concentran el {number(share3, 1)} % del total seleccionado.")
        if id_ == "proteccion_integral" and metrics["units"]:
            insights.append(f"La fuente reporta {number(metrics['units'])} unidades de atención en los servicios seleccionados.")
        sections.append({**metrics, "title": title, "people_label": people_label,
                         "rows": rows, "territories": territories, "insights": insights,
                         "notes": [notes[0], notes[1]]})
    if not sections:
        raise ValueError("La selección no contiene los apartados admitidos por el boletín.")
    source = manifest.get("fuente", {})
    if isinstance(source, dict):
        source_label = source.get("archivo", "Acumulado VIS-VIE.xlsx")
        source_sha = source.get("sha256", "")
    else:
        source_label, source_sha = str(source), ""
    identity = frame.sort_values(["seccion", "programa_id", "provincia"]).to_json(orient="records", date_format="iso")
    return {
        "title": str(options.get("title") or "Boletín estadístico institucional")[:100],
        "period": period.strftime("%Y-%m-%d"), "period_label": period_label,
        "year": period.year, "scope_label": scope_label,
        "source_label": source_label, "source_sha256": source_sha,
        "generated_at": datetime.now(ZoneInfo("America/Guayaquil")).isoformat(timespec="seconds"),
        "author": str(options.get("author") or "Ministerio de Trabajo y Desarrollo Humano"),
        "include_territory": bool(options.get("include_territory", True)),
        "people_total": _sum(frame, "usuarios", integer=True),
        "units_total": _sum(frame, "unidades", integer=True),
        "fiscal_total": _sum(frame, "monto_fiscal"),
        "government_total": _sum(frame, "monto_gobierno"),
        "executed_total": _sum(frame, "presupuesto_ejecutado", require_complete=True),
        "fiscal_label": f"Acumulado fiscal {period.year} (USD)",
        "government_label": "Acumulado de gobierno (USD)",
        "provinces": provinces, "programs": programs,
        "selection_hash": sha256(identity.encode()).hexdigest()[:12],
        "sections": sections, "notes": notes,
    }
