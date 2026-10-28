"""Incorpora las bases de alertas (aplicativo y matriz Excel) a la publicación abierta de Riesgos.

Uso:  python -I scripts/update_alertas.py AAAA-MM-DD BASE_ALERTAS_AAAA.xlsx [GESTION_DE_ALERTAS_2025.xlsx ...]

Antes se abre el día con ``python scripts/nuevo_corte_riesgos.py AAAA-MM-DD``; este script solo escribe en la
publicación de ese día (``seguimiento_enos_AAAA-MM-DD.json``).

- Hoja «ALERTAS SISTEMA …» (aplicativo): cada alerta conserva su código oficial (ALT-AAAA-NNNNNN). Si el código ya está
  en el tablero, solo se actualizan su estado, prioridad y personas afectadas; los campos revisados (unidad, servicio y
  afectación) se conservan. Un código nuevo entra como alerta nueva.
- Hojas «DETALLE DE ALERTAS …» y «ALERTAS» (matriz Excel): cada fila es una alerta con código MAT-AAAA-…; una fila
  repetida (mismo lugar, fecha, servicio y resumen) solo cambia el estado de la alerta ya registrada.
- Tipo de alerta: el del aplicativo («Desastre natural» se presenta como «Emergencia»); en la matriz, «Emergencia» cuando
  el servicio reportado es Emergencia y «Prestación de servicios» en los demás casos. Las alertas que el tablero ya
  mostraba son de emergencia.
- No se copian narrativas libres, direcciones, responsables, cargos ni teléfonos: solo lugar, fecha, tipo, servicio,
  unidad de atención, estado, prioridad, personas afectadas y si se afecta la prestación del servicio.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import depuracion, enos  # noqa: E402

EMERGENCY = "Emergencia"
MATRIX_TYPE = "Prestación de servicios"
TYPES = {"desastre natural": EMERGENCY, "infraestructura servicios mdh": "Infraestructura de servicios",
         "talento humano": "Talento humano", "emprendimientos/cdh": "Emprendimientos y CDH"}
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
STATES = {"solventado": "Resuelto", "en proceso": "En seguimiento"}
PRIORITIES = {"critica": "Crítica", "crítica": "Crítica"}
NO_UNIT = {"", "—", "-", "sin unidad registrada", "nan", "none"}
UNIT_SERVICES = [(("cnh", "creciendo"), "Creciendo con Nuestros Hijos (CNH)"),
                 (("cibv", "cdi", "infantil"), "Desarrollo Infantil"),
                 (("adulto", "geront"), "Centros gerontológicos"),
                 (("acogimiento", "proteccion especial"), "Protección Especial"),
                 (("discapacidad",), "Discapacidades")]
SERVICES = {"desarrollo infantil integral": "Desarrollo Infantil", "desarrollo infantil": "Desarrollo Infantil",
            "intergeneracional": "Gestión Intergeneracional", "discapacidades": "Discapacidades",
            "todos los servicios": "Todos los servicios", "bonos y pensiones": "Bonos y pensiones",
            "vulneracion de derechos": "Vulneración de derechos", "proteccion especial": "Protección Especial"}
WITHOUT_SERVICE = "Sin servicio identificado"
# The matrix states whether the alert affects the service; its free narrative is not copied.
AFFECTS = {True: "Afecta la prestación del servicio", False: "No afecta la prestación del servicio"}


def _plain(value) -> str:
    text = unicodedata.normalize("NFKD", str(value if value is not None else "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def _text(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else re.sub(r"\s+", " ", str(value)).strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


GAZ = depuracion.gazetteer()


def _place(province, canton) -> tuple[str, str]:
    province, canton = _text(province), _text(canton)
    code = GAZ.province(province) if province else None
    parts = [GAZ.province(part) for part in re.split(r"\s+y\s+|,", province) if part.strip()]
    if len(parts) > 1 and all(parts):
        code = None  # an alert written for several provinces is not assigned to one of them
    elif code is None and province:
        # A canton written in the province column (Tena) belongs to its province.
        found = GAZ.canton(None, province)
        code = found[:2] if found else None
        canton = canton or province
    name = depuracion.PROVINCE_NAMES.get(code) if code else None
    if not name:
        name = ("Varias provincias" if len(parts) > 1 and all(parts) else
                "Nacional" if "nacional" in _plain(province) or not province else province.title())
    found = GAZ.canton(code, canton) if code and canton else None
    if found:
        named = GAZ.canton_name.get(found) if isinstance(GAZ.canton_name, dict) else GAZ.canton_name(found)
        canton = named or canton
    if _plain(canton).startswith("todos") or not canton:
        canton = "Todos los cantones"
    return name, canton if canton.isupper() is False else canton.title()


def _date(value, month, year: int) -> tuple[pd.Timestamp, str | None]:
    """The date of an alert and, when the source only gives an approximate one, its original text."""
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).normalize(), None
    text = _text(value)
    low = _plain(text)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}( 00:00:00)?", low):
        return pd.Timestamp(low[:10]), None
    found = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", low)
    if found:
        day, number, given = int(found[1]), int(found[2]), int(found[3])
        return pd.Timestamp(given if given >= 2000 else year, number, day), text
    found = re.search(r"(\d{1,2}) de (" + "|".join(MONTHS) + ")", low)
    if found:
        return pd.Timestamp(year, MONTHS[found[2]], int(found[1])), text
    named = sorted((low.find(name), number) for name, number in MONTHS.items() if name in low)
    if not named and _plain(month) in MONTHS:
        named = [(0, MONTHS[_plain(month)])]
    if not named:
        raise SystemExit(f"Fecha no reconocida: {text!r}")
    return pd.Timestamp(year, named[0][1], 1), text or None


def _people(value) -> int | None:
    if isinstance(value, (int, float)) and not pd.isna(value):
        return int(value)
    found = re.search(r"\d[\d.]*", _text(value))
    return int(found[0].replace(".", "")) if found else None


def _affects(value) -> bool | None:
    low = _plain(value)
    return True if low.startswith("si") else False if low.startswith("no") else None


def _unit_service(unit: str) -> str:
    low = _plain(unit)
    return next((service for keys, service in UNIT_SERVICES if any(k in low for k in keys)), WITHOUT_SERVICE)


def _service(value) -> str:
    text = _text(value)
    low = _plain(text)
    if not low:
        return WITHOUT_SERVICE
    return next((name for key, name in SERVICES.items() if low == key or low == _plain(key)), text[:1].upper() + text[1:])


def _type(value) -> str:
    text = re.sub(r"^\d+\.\s*", "", _text(value))
    return TYPES.get(_plain(text), text[:1].upper() + text[1:]) or "Otros"


def _record(code, moment, approximate, province, canton, **fields) -> dict:
    province, canton = _place(province, canton)
    return {"codigo": code, "fecha": f"{moment:%Y-%m-%d}", "provincia": province, "canton": canton, **fields,
            "fecha_texto": approximate or f"{moment:%Y-%m-%d}", "mes_reporte": f"{moment:%Y-%m}"}


def system_rows(path: Path, sheet: str, source: str) -> list[dict]:
    frame = pd.read_excel(path, sheet_name=sheet)
    rows = []
    for row in frame.to_dict("records"):
        moment, approximate = _date(row["Fecha"], None, int(str(row["Código"])[4:8]))
        unit = _text(row.get("Unidad de atención"))
        unit = "" if _plain(unit) in NO_UNIT else unit
        ua = _text(row.get("Código SIIMDH"))
        ua = "" if _plain(ua) in NO_UNIT else ua.split(".")[0]
        rows.append(_record(_text(row["Código"]), moment, approximate, row["Provincia"], row["Cantón"],
                            estado=_text(row["Estado"]), prioridad=PRIORITIES.get(_plain(row["Prioridad"]), _text(row["Prioridad"])),
                            codigo_ua=ua, unidad=unit, afectados_fuente=_people(row.get("Afectados")),
                            afectacion_servicio_confirmada=None, servicio=_unit_service(unit), afectacion_servicio="",
                            origen="aplicativo", fuente=source, tipo_alerta=_type(row["Tipo"])))
    return rows


def matrix_rows(path: Path, sheet: str, source: str, year: int) -> tuple[list[dict], int]:
    """Rows of the Excel matrix; a repeated alert (same place, date, service and summary) keeps its latest state."""
    frame = pd.read_excel(path, sheet_name=sheet)
    columns = {_plain(c): c for c in frame.columns}

    def column(*starts):
        return next(c for key, c in columns.items() if any(key.startswith(s) for s in starts))

    number, zone = column("no."), columns.get("zona")
    state, affects, people = column("solventado"), column("se afecta"), column("nro. aproximado")
    summary = column("alerta detectada")
    keys = frame[zone].astype(str).str.strip() + "-" + frame[number].astype(str) if zone else frame[number].astype(str)
    by_number = not keys.duplicated().any()
    found, repeated = {}, 0
    for index, row in enumerate(frame.to_dict("records")):
        moment, approximate = _date(row[column("fecha del suceso")], row.get(column("mes")), year)
        service = _service(row.get(column("servicio")))
        key = (_plain(row[column("provincia")]), _plain(row[column("canton")]), _plain(row.get(column("parroquia"))),
               f"{moment:%Y-%m-%d}", _plain(service), _plain(row.get(summary)))
        if zone:
            identifier = f"{_text(row[zone]).upper().replace(' ', '')}-{int(row[number]):03d}" if by_number else f"{index + 1:04d}"
        else:
            identifier = f"{int(row[number]):04d}"
        record = _record(f"MAT-{year}-{identifier}", moment, approximate, row[column("provincia")], row[column("canton")],
                         estado=STATES.get(_plain(row[state]), _text(row[state]) or "Pendiente"), prioridad="Sin prioridad",
                         codigo_ua="", unidad="", afectados_fuente=_people(row.get(people)),
                         afectacion_servicio_confirmada=_affects(row.get(affects)), servicio=service,
                         afectacion_servicio=AFFECTS.get(_affects(row.get(affects)), ""), origen="matriz_alertas", fuente=source,
                         tipo_alerta=EMERGENCY if _plain(service) == "emergencia" else MATRIX_TYPE)
        if key in found:
            repeated += 1
            found[key].update(estado=record["estado"], afectacion_servicio_confirmada=record["afectacion_servicio_confirmada"],
                              afectacion_servicio=record["afectacion_servicio"])
        else:
            found[key] = record
    return list(found.values()), repeated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dia")
    parser.add_argument("bases", nargs="+", type=Path)
    parser.add_argument("--nombre", action="append", default=[], help="Nombre original de cada base (mismo orden).")
    args = parser.parse_args()
    target = enos.FOLDER / f"seguimiento_enos_{args.dia}.json"
    if not target.exists():
        raise SystemExit(f"Abra primero el día: python scripts/nuevo_corte_riesgos.py {args.dia}")
    enos.ensure_open(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    current = {row["codigo"]: row for row in data["alertas"]}
    for row in current.values():
        row.setdefault("tipo_alerta", EMERGENCY)
    counts = {"actualizadas": 0, "cambios_estado": 0, "nuevas_aplicativo": 0, "nuevas_matriz": 0, "filas_repetidas_matriz": 0}
    sources = []
    for position, path in enumerate(args.bases):
        name = args.nombre[position] if position < len(args.nombre) else path.name
        book = pd.ExcelFile(path)
        rows = []
        for sheet in book.sheet_names:
            plain = _plain(sheet)
            if plain.startswith("alertas sistema"):
                rows += system_rows(path, sheet, name)
            elif plain.startswith("detalle de alertas") or plain == "alertas":
                year = int(re.search(r"20\d\d", name)[0]) if re.search(r"20\d\d", name) else int(args.dia[:4])
                found, repeated = matrix_rows(path, sheet, name, year)
                rows += found
                counts["filas_repetidas_matriz"] += repeated
        for row in rows:
            old = current.get(row["codigo"])
            if old is not None:
                # A reviewed alert keeps its unit, service and affectation: only its state changes.
                counts["actualizadas"] += 1
                counts["cambios_estado"] += int(old.get("estado") != row["estado"])
                old.update(estado=row["estado"], prioridad=row["prioridad"],
                           afectados_fuente=row["afectados_fuente"] if row["afectados_fuente"] is not None else old.get("afectados_fuente"))
                continue
            current[row["codigo"]] = row
            counts["nuevas_aplicativo" if row["origen"] == "aplicativo" else "nuevas_matriz"] += 1
        sources.append({"nombre": name, "sha256": _sha(path), "registros": len(rows)})
    alerts = sorted(current.values(), key=lambda r: (r["fecha"], r["codigo"]))
    data["alertas"] = alerts
    data.setdefault("cortes", {})["alertas"] = args.dia
    known = {(s.get("nombre"), s.get("sha256")) for s in data.get("fuentes", [])}
    data["fuentes"] = data.get("fuentes", []) + [s for s in sources if (s["nombre"], s["sha256"]) not in known]
    first = min(r["fecha"] for r in alerts)
    data["notas"]["alertas"] = (
        f"Seguimiento desde el {enos.cut_text(data['desde'])}; el historial de alertas inicia el {enos.cut_text(first)}. "
        "Incluye todas las alertas del aplicativo y de la matriz Excel, de todo tipo; el filtro «Tipo de alerta» permite "
        "consultar solo las de emergencia. Cada código se cuenta una vez con su estado más reciente; no equivale a eventos "
        "ni unidades únicas.")
    data["control"].update({"alertas_total": len(alerts), "alertas_actualizacion_bases": counts,
                            "alertas_tipos": dict(pd.Series([r["tipo_alerta"] for r in alerts]).value_counts())})
    data["control"]["alertas_tipos"] = {k: int(v) for k, v in data["control"]["alertas_tipos"].items()}
    data["generado_utc"] = datetime.now(timezone.utc).isoformat()
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"publicacion": target.name, "alertas": len(alerts), **counts,
                      "tipos": data["control"]["alertas_tipos"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
