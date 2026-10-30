"""Build a supplemental alert history without changing operational or issued files.

Usage: python -I scripts/preparar_alertas_historicas.py BASE_2023.xlsx BASE_2024.xlsx BASE_2025.xlsx BASE_2026.xlsx

The 2023 workbook contains action plans, not dated alerts, and is retained only
as an aggregate antecedent. The 2024 register deduplicates identical cases whose
follow-up actions changed. Missing event days retain an explicit reporting-month
interval; malformed and multiple-year dates are excluded, never silently fixed.
2025/26 use the established MAT/ALT identifiers so current reviewed records win.
Only an allowlisted operational schema and aggregate quality controls are saved.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import update_alertas as existing  # noqa: E402
from src import enos, enos_excel  # noqa: E402

OUTPUT = enos.FOLDER / "alertas_historicas.json"
FIELDS = set(enos.ALERT_COLUMNS) | {"fuente", "fecha_hasta", "fecha_precision", "fecha_tipo",
                                    "hoja_fuente", "numero_fuente"}


class UncertainDate(ValueError):
    """A source value cannot be assigned a supported event interval."""


def date_span(value, report_month=None, year=None, *, cut="2026-10-29") -> dict:
    """Read only explicit calendar dates or a single stated month; do not infer days.

    Multiple explicitly listed dates in one month are retained as an interval.
    Multiple years, malformed years and unavailable dates remain unallocated.
    ``fecha`` is the interval's lower bound, not an invented day of occurrence.
    """
    text = existing._text(value)
    low = existing._plain(text)
    precision, kind = "dia", "suceso"
    def moment(y, m, d):
        try:
            return pd.Timestamp(int(y), int(m), int(d))
        except ValueError as exc:
            raise UncertainDate("fecha_invalida") from exc

    if isinstance(value, (datetime, pd.Timestamp)) and pd.notna(value):
        dates = [pd.Timestamp(value).normalize()]
    else:
        dates = []
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}(?: 00:00:00)?", low):
            y, m, d = low[:10].split("-")
            dates = [moment(y, m, d)]
        else:
            found = re.findall(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)", low)
            if found:
                dates = [moment(y, m, d) for d, m, y in found]
            else:
                named = re.fullmatch(r"(\d{1,2}) de (\w+) de (20\d{2})", low)
                if named and named[2] in existing.MONTHS:
                    dates = [moment(named[3], existing.MONTHS[named[2]], named[1])]
        if not dates:
            # A nonempty malformed date is not replaced by its report month.
            if low:
                raise UncertainDate("fecha_no_interpretable")
            month = existing._plain(report_month)
            months = sorted({n for name, n in existing.MONTHS.items() if re.search(r"\b" + name + r"\b", month)})
            if year is None or len(months) != 1:
                raise UncertainDate("sin_fecha_ni_mes_univoco")
            start = pd.Timestamp(year, months[0], 1)
            dates = [start, start + pd.offsets.MonthEnd(0)]
            precision, kind = "mes_reporte", "reporte"
    if any(d.year < 2000 or d > pd.Timestamp(cut).normalize() for d in dates):
        raise UncertainDate("fecha_fuera_de_corte")
    start, end = min(dates), max(dates)
    if (start.year, start.month) != (end.year, end.month):
        raise UncertainDate("fechas_multiples_sin_periodo_univoco")
    if start != end and precision == "dia":
        precision = "intervalo"
    # Retain date-only source text, never a free narrative from another column.
    words = set(re.findall(r"[a-z]+", low))
    date_only = words <= ({"de"} | set(existing.MONTHS))
    safe_text = text if date_only else (f"{start:%Y-%m-%d}" if start == end else f"{start:%Y-%m-%d} / {end:%Y-%m-%d}")
    date_text = (f"{start:%Y-%m} (mes de reporte)" if precision == "mes_reporte" else safe_text)
    return {"fecha": f"{start:%Y-%m-%d}", "fecha_hasta": f"{end:%Y-%m-%d}",
            "fecha_precision": precision, "fecha_tipo": kind,
            "fecha_texto": date_text or f"{start:%Y-%m-%d}", "mes_reporte": f"{start:%Y-%m}"}


def _counts(values) -> dict:
    return dict(sorted(Counter(values).items()))


def antecedent_2023(path: Path) -> tuple[dict, dict]:
    frame = pd.read_excel(path, sheet_name="Hoja1", header=2)
    frame = frame[frame.iloc[:, 0].notna()]
    columns = {existing._plain(c): c for c in frame.columns}
    status = columns["cumplimiento si/no"]
    aggregate = {
        "anio": 2023, "fuente": path.name, "registros": len(frame),
        "unidad": "Nudos críticos y planes de acción",
        "por_servicio": _counts(existing._service(v) for v in frame[columns["servicio"]]),
        "por_cumplimiento": _counts(existing._text(v).upper() or "Sin dato" for v in frame[status]),
        "fecha_disponible": "FECHA POSIBLE DE EJECUCIÓN",
        "nota": "No contiene fecha de ocurrencia ni de reporte de la alerta. La fecha posible de ejecución es "
                "planificación; estos antecedentes no se atribuyen al período de gobierno ni se suman a alertas fechadas.",
    }
    metadata = {"nombre": path.name, "sha256": existing._sha(path), "anio": 2023,
                "hojas": ["Hoja1"], "registros_fuente": len(frame), "alertas_fechadas": 0,
                "antecedentes_sin_fecha": len(frame)}
    return aggregate, metadata


def matrix_2024(path: Path, *, cut="2026-10-29") -> tuple[list[dict], dict]:
    frame = pd.read_excel(path, sheet_name="Hoja1", header=3)
    columns = {existing._plain(c): c for c in frame.columns}

    def col(start):
        return next(c for key, c in columns.items() if key.startswith(start))

    number, state = col("no."), col("solventado")
    frame = frame[frame[number].notna()]
    if frame[number].duplicated().any():
        raise ValueError("2024: números de registro duplicados; revisar identidad antes de importar.")
    skip = {number, state} | {c for key, c in columns.items() if key.startswith(
        ("acciones realizadas", "acciones pendientes", "acciones dir", "observacion", "actualizacion"))}
    unique, repeated = {}, []
    # Canonical ID is the first original number, independent of physical row order.
    for row in frame.sort_values(number).to_dict("records"):
        key = tuple(existing._plain(existing._text(row.get(c))) for c in frame.columns if c not in skip)
        identifier = f"MAT-2024-{int(row[number]):04d}"
        if key in unique:
            previous = unique[key]
            repeated.append({"codigo": identifier, "conservado": previous["codigo"]})
            previous["row"][state] = row[state]
        else:
            unique[key] = {"codigo": identifier, "row": row}
    records, excluded = [], []
    for item in unique.values():
        row, code = item["row"], item["codigo"]
        try:
            span = date_span(row[col("fecha del suceso")], row[col("mes")], 2024, cut=cut)
        except UncertainDate as exc:
            excluded.append({"codigo": code, "motivo": str(exc)})
            continue
        service = existing._service(row[col("servicio")])
        affects = existing._affects(row[col("se afecta")])
        province, canton = existing._place(row[col("provincia")], row[col("canton")])
        records.append({"codigo": code, **span, "provincia": province, "canton": canton,
            "estado": existing.STATES.get(existing._plain(row[state]), existing._text(row[state]) or "Pendiente"),
            "prioridad": "Sin prioridad", "codigo_ua": "", "unidad": "",
            "afectados_fuente": existing._people(row[col("nro. aproximado")]),
            "afectacion_servicio_confirmada": affects, "servicio": service,
            "afectacion_servicio": existing.AFFECTS.get(affects, ""), "origen": "matriz_alertas",
            "fuente": path.name, "hoja_fuente": "Hoja1", "numero_fuente": int(row[number]),
            "tipo_alerta": existing.EMERGENCY if existing._plain(service) in ("emergencia", "emergencias") else existing.MATRIX_TYPE})
    metadata = {"nombre": path.name, "sha256": existing._sha(path), "anio": 2024,
                "hojas": ["Hoja1"], "fila_encabezados": 4, "registros_fuente": len(frame),
                "registros_unicos": len(unique), "seguimientos_repetidos": repeated,
                "alertas_fechadas": len(records), "precision_fecha": _counts(r["fecha_precision"] for r in records),
                "excluidos_fecha": excluded,
                "desde": min(r["fecha"] for r in records), "hasta": max(r["fecha_hasta"] for r in records)}
    return records, metadata


def recent_register(path: Path, year: int, *, cut="2026-10-29") -> tuple[list[dict], dict]:
    records, sheets, texts, duplicates = [], [], {}, 0
    for sheet in pd.ExcelFile(path).sheet_names:
        plain = existing._plain(sheet)
        if plain.startswith("alertas sistema"):
            rows = existing.system_rows(path, sheet, path.name, texts)
        elif plain.startswith("detalle de alertas") or plain == "alertas":
            rows, repeated = existing.matrix_rows(path, sheet, path.name, year, texts)
            duplicates += repeated
        else:
            continue
        sheets.append(sheet)
        for row in rows:
            if row["fecha"] > cut:
                raise ValueError(f"{row['codigo']}: fecha posterior al corte.")
            # Reviewed operational rows remain authoritative. Keep the established
            # identity/date interpretation so this archive never changes that scope.
            row = {key: value for key, value in row.items() if key in FIELDS}
            row.update(hoja_fuente=sheet)
            try:
                span = date_span(row.get("fecha_texto"), cut=cut)
            except UncertainDate:
                # Existing imports may contain an approximate month. It is not an
                # additional alert, and the current operational version takes priority.
                row["fecha_precision"] = "referencia_preexistente"
                row["fecha_texto"] = row["fecha"] + " (referencia del registro operativo)"
                row["fecha_hasta"] = row["fecha"]
                row["fecha_tipo"] = "registro_operativo"
            else:
                row.update(span)
            records.append(row)
    metadata = {"nombre": path.name, "sha256": existing._sha(path), "anio": year,
                "hojas": sheets, "alertas_fechadas": len(records), "seguimientos_repetidos": duplicates,
                "desde": min(r["fecha"] for r in records), "hasta": max(r["fecha_hasta"] for r in records)}
    return records, metadata


def current_register(processed: Path) -> dict:
    """Read reviewed identifiers, including exclusions, without invoking history()."""
    rows = {}
    for path in sorted(processed.glob("seguimiento_enos_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.update({r["codigo"]: r for r in data.get("alertas", [])})
        for code in data.get("control", {}).get("alertas_excluidas_codigos", []):
            rows.setdefault(code, {"codigo": code})
    workbook = enos_excel.read(processed, "alertas")
    if workbook:
        for _line, row in workbook[2]:
            code = existing._text(row["codigo"])
            rows[code] = {**rows.get(code, {}), **row}
    return rows


def build(paths: list[Path], *, cut="2026-10-29", processed=enos.FOLDER) -> dict:
    records, sources, antecedents = [], [], []
    seen_years = set()
    for path in paths:
        found = re.search(r"20(?:23|24|25|26)", path.name)
        if not found:
            raise ValueError("El nombre de cada base debe identificar su año 2023–2026.")
        year = int(found[0])
        if year in seen_years:
            raise ValueError(f"Más de una base para {year}; concilie las versiones antes de importar.")
        seen_years.add(year)
        if year == 2023:
            aggregate, metadata = antecedent_2023(path)
            antecedents.append(aggregate)
            rows = []
        elif year == 2024:
            rows, metadata = matrix_2024(path, cut=cut)
        else:
            rows, metadata = recent_register(path, year, cut=cut)
        records.extend(rows)
        sources.append(metadata)
    if seen_years != {2023, 2024, 2025, 2026}:
        raise ValueError("Se requieren las cuatro bases 2023, 2024, 2025 y 2026.")
    ids = [r["codigo"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("El histórico contiene códigos repetidos.")
    known = current_register(Path(processed))
    matched = [r for r in records if r["codigo"] in known]
    changes = Counter()
    for row in matched:
        for key in ("fecha", "provincia", "canton", "estado", "tipo_alerta", "servicio"):
            before, after = known[row["codigo"]].get(key), row.get(key)
            if key == "fecha":
                before, after = pd.Timestamp(before).date(), pd.Timestamp(after).date()
            if str(before) != str(after):
                changes[key] += 1
    return {"version": 1, "corte": cut,
        "desde": min(r["fecha"] for r in records), "hasta": max(r["fecha_hasta"] for r in records),
        "criterio_alertas": "codigo_ua_y_reportes_sectoriales",
        "alertas": sorted(records, key=lambda r: (r["fecha"], r["codigo"])),
        "fuentes": sorted(sources, key=lambda s: s["anio"]), "antecedentes": antecedents,
        "control": {"alertas_total": len(records), "ya_presentes_en_operativo": len(matched),
            "nuevas_alertas": len(records) - len(matched), "diferencias_con_revision_operativa": dict(changes),
            "prioridad": "Publicaciones y Excel operativo conservan sus registros revisados y exclusiones; "
                         "este archivo solo complementa los identificadores ausentes.",
            "alertas_por_anio": _counts(r["fecha"][:4] for r in records)},
        "notas": {"alertas": "Cada código representa un reporte de alerta, no un evento ni una unidad única. "
                "Los seguimientos idénticos de 2024 actualizan un solo registro. Los intervalos y meses de reporte "
                "se incluyen únicamente cuando el filtro contiene el rango completo; el inicio del rango no es "
                "una fecha de ocurrencia inventada. Las fechas ambiguas quedan fuera del total fechado.",
            "privacidad": "No se publican narrativas, direcciones, informantes, responsables ni teléfonos.",
            "antecedentes": "Los 572 nudos críticos de 2023 no tienen fecha de ocurrencia y se conservan como "
                            "antecedentes agregados, separados del acumulado de gobierno."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bases", nargs="+", type=Path)
    parser.add_argument("--corte", default="2026-10-29")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--processed", type=Path, default=enos.FOLDER)
    args = parser.parse_args()
    data = build(args.bases, cut=args.corte, processed=args.processed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archivo": args.output.name, **data["control"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
