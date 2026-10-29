"""Motor independiente para cargar Excel ENOS a los contratos de datos actuales.

NO importa ni modifica app.py, src/views, src/reports o PDFs. Cada publicación
conserva las mismas claves JSON; los Parquet son productos auxiliares internos.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
import hashlib
import json
import re

import openpyxl
import pandas as pd

from scripts.build_enos import source_day, source_id
from src import names


def load_xlsx(binary):
    return openpyxl.load_workbook(BytesIO(binary), read_only=True, data_only=True)


def integer(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field}: se requiere un entero no negativo.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: valor no numérico.") from exc
    if not number.is_integer() or number < 0:
        raise ValueError(f"{field}: se requiere un entero no negativo.")
    return int(number)


def d(value):
    return source_day(value).date().isoformat()


def source(data, name, binary):
    digest = hashlib.sha256(binary).hexdigest()
    record = {"nombre": Path(name).name, "sha256": digest}
    if record not in data.setdefault("fuentes", []):
        data["fuentes"].append(record)
    return digest


def processed(data, binary):
    digest = hashlib.sha256(binary).hexdigest()
    return any(item.get("sha256") == digest for item in data.get("fuentes", []))


def find_header(values, fields):
    for idx, row in enumerate(values[:12]):
        cols = [str(c).strip() if c is not None else "" for c in row]
        if set(fields).issubset(cols):
            return idx, cols
    raise ValueError("Faltan encabezados requeridos: " + ", ".join(fields))


def classify(binary):
    wb = load_xlsx(binary)
    try:
        sheets = set(wb.sheetnames)
        if {'Datos', 'Control'}.issubset(sheets):
            from src.enos_excel import FILES, FORMAT
            control = dict(wb['Control'].iter_rows(min_row=2, max_row=8, max_col=2, values_only=True))
            if control.get('formato') == FORMAT and control.get('tipo') in FILES:
                return control['tipo']
        if {"DETALLE", "RESUMEN"}.issubset(sheets):
            return "suspendidas"
        if "Detalle" in sheets:
            rows = list(wb["Detalle"].iter_rows(min_row=1, max_row=12, values_only=True))
            try:
                find_header(rows, ["Código", "Fecha", "Provincia", "Estado"])
                return "alertas"
            except ValueError:
                pass
        if "Detalle de entregas" in sheets or "Detalle completo" in sheets:
            return "kits"
        rows = list(wb.active.iter_rows(min_row=1, max_row=12, values_only=True))
        try:
            find_header(rows, ["_id", "Provincia", "Cantón", "Número de kits entregados"])
            return "kits"
        except ValueError:
            return "desconocido"
    finally:
        wb.close()


def alerts(data, name, binary, cut):
    wb = load_xlsx(binary)
    try:
        rows = list(wb["Detalle"].values)
    finally:
        wb.close()
    idx, cols = find_header(rows, ["Código", "Fecha", "Tipo", "Código SIIMDH",
                                   "Unidad de atención", "Provincia", "Cantón",
                                   "Estado", "Prioridad", "Afectados"])
    received = [dict(zip(cols, row)) for row in rows[idx + 1:] if row and any(v is not None for v in row)]
    if not received:
        raise ValueError("El archivo de alertas no contiene registros.")
    previous = {str(a["codigo"]): a for a in data["alertas"]}
    if len(previous) != len(data["alertas"]):
        raise ValueError("El histórico publicado contiene códigos duplicados.")
    seen, new, updated, dates, review = set(), 0, 0, [], []
    for r in received:
        identifier = source_id(r["Código"], "Código alerta")
        if identifier in seen:
            raise ValueError(f"Código de alerta duplicado en el Excel: {identifier}")
        seen.add(identifier)
        when = d(r["Fecha"])
        if when > cut:
            raise ValueError(f"Alerta {identifier} con fecha posterior al reporte.")
        dates.append(when)
        affected = integer(r["Afectados"], "Afectados") if r["Afectados"] is not None else None
        if identifier in previous:
            old = previous[identifier]
            if old.get("fecha") != when or names.key(old.get("provincia")) != names.key(r["Provincia"]):
                raise ValueError(f"Alerta {identifier}: cambio de fecha o provincia; necesita revisión manual.")
            old.update(estado=str(r["Estado"] or ""), prioridad=str(r["Prioridad"] or ""),
                       afectados_fuente=affected, fuente=name)
            updated += 1
        else:
            ua = str(r["Código SIIMDH"] or "").strip()
            ua = "" if ua.lower() in {"", "none", "nan", "-", "—"} else (
                str(int(float(ua))) if re.fullmatch(r"\d+(?:\.0+)?", ua) else ua)
            if ua and any(old.get("codigo_ua") == ua and old.get("fecha") == when
                          and old.get("origen") == "aplicativo" for old in previous.values()):
                review.append(f"{identifier}: otro código del aplicativo coincide en UA {ua} y fecha {when}.")
            kind = str(r["Tipo"] or "")
            unit = str(r["Unidad de atención"] or "").strip()
            previous[identifier] = {
                "codigo": identifier, "fecha": when, "provincia": names.place(r["Provincia"]),
                "canton": names.place(r["Cantón"]), "estado": str(r["Estado"] or ""),
                "prioridad": str(r["Prioridad"] or ""), "codigo_ua": ua,
                "unidad": "" if unit.lower() in {"", "sin unidad registrada", "—", "-"} else unit,
                "afectados_fuente": affected, "afectacion_servicio_confirmada": None,
                "servicio": "Sin servicio identificado", "afectacion_servicio": "",
                "origen": "aplicativo", "tipo_alerta": ("Emergencia"
                    if names.key(kind) == "DESASTRE NATURAL" else kind),
                "fecha_texto": when, "mes_reporte": when[:7], "fuente": name,
            }
            new += 1
    if review:
        raise ValueError("Posibles reportes duplicados que requieren conciliación: " + " | ".join(review[:12]))
    data["alertas"] = sorted(previous.values(), key=lambda row: (row["fecha"], row["codigo"]))
    data.setdefault("control", {}).update({
        "alertas_total": len(previous),
        "alertas_actualizacion_aplicativo": len(received),
        "alertas_detalle_recibido": len(received),
        "alertas_actualizacion_bases": {"actualizadas": updated, "nuevas_aplicativo": new},
    })
    data.setdefault("cortes", {})["alertas"] = max(dates)
    source(data, name, binary)
    return {"filas_recibidas": len(received), "alertas_nuevas": new,
            "alertas_actualizadas": updated, "total_historico": len(previous)}


def _gazetteer():
    path = Path(__file__).resolve().parents[1] / "assets/geo/ecuador_dpa.json"
    geo = json.loads(path.read_text(encoding="utf-8"))
    provinces = {str(row["c"]): row["n"] for row in geo["provincias"]}
    cantons = {str(row["c"]): row["n"] for row in geo["cantones"]}
    pkeys = {names.key(name): code for code, name in provinces.items()}
    ckeys = {(code[:2], names.key(name)): code for code, name in cantons.items()}
    return provinces, cantons, pkeys, ckeys


def kits(data, name, binary, cut):
    wb = load_xlsx(binary)
    try:
        if "Detalle de entregas" in wb.sheetnames:
            rows = list(wb["Detalle de entregas"].values)
            mode = "normalizado"
            controls = dict(wb["Control y notas"].values) if "Control y notas" in wb.sheetnames else {}
        elif "Detalle completo" in wb.sheetnames:
            rows = list(wb["Detalle completo"].values)
            mode = "parcial"
            controls = {}
        else:
            rows = list(wb.active.values)
            mode = "kobo"
            controls = {}
    finally:
        wb.close()
    provinces, cantons, pkeys, ckeys = _gazetteer()
    if mode == "parcial":
        # Formato existente: fecha, provincia, canton, ..., kits, familias, ID Kobo.
        received = [{"id": r[8], "fecha": r[0], "prov": r[1], "canton": r[2],
                     "kits": r[6], "familias": r[7]} for r in rows[1:] if len(r) > 8 and r[8] is not None]
    else:
        mandatory = (["ID Kobo", "Fecha entrega", "Provincia", "Cantón", "Kits", "Familias"]
                     if mode == "normalizado" else
                     ["_id", "Fecha efectiva de la entrega", "Provincia", "Cantón",
                      "Número de kits entregados", "Número de familias beneficiadas"])
        idx, cols = find_header(rows, mandatory)
        records = [dict(zip(cols, r)) for r in rows[idx + 1:] if any(v is not None for v in r)]
        received = [{
            "id": r["ID Kobo"] if mode == "normalizado" else r["_id"],
            "fecha": r["Fecha entrega"] if mode == "normalizado" else r["Fecha efectiva de la entrega"],
            "prov": r["Provincia"], "canton": r["Cantón"],
            "kits": r["Kits"] if mode == "normalizado" else r["Número de kits entregados"],
            "familias": r["Familias"] if mode == "normalizado" else r["Número de familias beneficiadas"],
        } for r in records]
    if not received:
        raise ValueError("Kits: no hay entregas con ID.")
    seen, incoming = set(), {}
    for r in received:
        identifier = source_id(r["id"], "ID Kobo")
        if identifier in seen:
            raise ValueError(f"Kits: ID Kobo repetido: {identifier}")
        seen.add(identifier)
        p = str(r["prov"] or "").removeprefix("p_").strip()
        c = str(r["canton"] or "").removeprefix("c_").strip()
        pcode = p if p in provinces else pkeys.get(names.key(p))
        ccode = c if c in cantons else ckeys.get((pcode, names.key(c)))
        if not pcode or not ccode or not ccode.startswith(pcode):
            raise ValueError(f"Kits: provincia/cantón sin concordancia para ID {identifier}.")
        when = d(r["fecha"])
        if when > cut:
            raise ValueError(f"Kits: entrega {identifier} posterior a la publicación.")
        incoming[identifier] = {
            "id_kobo": identifier, "fecha": when, "provincia": names.place(provinces[pcode]),
            "canton": names.place(cantons[ccode]), "kits": integer(r["kits"], "Kits"),
            "familias": integer(r["familias"], "Familias")
        }
    previous = {str(r["id_kobo"]): r for r in data.get("kits", [])}
    if len(previous) != len(data.get("kits", [])):
        raise ValueError("Kits: el histórico anterior contiene IDs duplicados.")
    revised = sum(previous[identifier] != row for identifier, row in incoming.items() if
                  identifier in previous)
    if mode != "parcial":
        missing = set(previous) - set(incoming)
        if missing:
            raise ValueError(f"Histórico Kobo incompleto: faltan {len(missing)} IDs ya publicados; "
                             "no se sustituye el histórico sin revisión.")
        combined = incoming
    else:
        combined = {**previous, **incoming}
    if controls:
        for label, actual in (("Registros", len(incoming)),
                              ("Kits", sum(x["kits"] for x in incoming.values())),
                              ("Familias reportadas", sum(x["familias"] for x in incoming.values()))):
            if label in controls and integer(controls[label], label) != actual:
                raise ValueError(f"Kobo: el control {label} no concilia con el detalle.")
    data["kits"] = sorted(combined.values(), key=lambda row: (row["fecha"], row["provincia"], row["id_kobo"]))
    metadata = data.setdefault("kits_metadatos", {})
    metadata.update({
        "fuente": name, "corte": cut,
        "desde": min(row["fecha"] for row in combined.values()),
        "hasta": max(row["fecha"] for row in combined.values()),
        "registros": len(combined), "kits": sum(row["kits"] for row in combined.values()),
        "familias_reportadas": sum(row["familias"] for row in combined.values()),
        "reemplaza_corte_anterior": True,
        "registros_actualizacion": len(incoming),
        "modo_actualizacion": ("Histórico Kobo completo, por ID" if mode != "parcial"
                              else "Actualización parcial, conciliada por ID Kobo")
    })
    data.setdefault("cortes", {})["kits"] = cut
    source(data, name, binary)
    return {"registros_fuente": len(incoming), "ids_nuevos": len(set(incoming) - set(previous)),
            "kits_acumulados": metadata["kits"], "registros_acumulados": len(combined),
            "tipo_carga": mode, "registros_corregidos": revised}


def suspendidas(data, continuity, name, binary, cut):
    wb = load_xlsx(binary)
    try:
        if not {"DETALLE", "RESUMEN"}.issubset(wb.sheetnames):
            raise ValueError("Unidades: faltan hojas DETALLE / RESUMEN.")
        rows = list(wb["DETALLE"].values)
        summary = list(wb["RESUMEN"].values)
    finally:
        wb.close()
    detail, seen = [], set()
    for r in rows[1:]:
        if not r or r[0] is None:
            continue
        if len(r) < 8:
            raise ValueError("Unidades: DETALLE debe contener ocho columnas.")
        prov, canton, parish, unit, service, mode, _admin, coverage = r[:8]
        if not unit:
            raise ValueError("Unidades: fila sin nombre de unidad.")
        mode = str(mode or "")
        service = str(service or "")
        if "CNH" in mode.upper():
            short, program = "CNH", "DII"
        elif "CDI" in mode.upper():
            short, program = "CDI", "DII"
        elif "ACOMPAÑAMIENTO FAMILIAR" in mode.upper():
            short, program = "AF", "AF"
        elif "ADULTOS" in service.upper():
            short, program = "PAM", "PAM_SERV"
        elif "DISCAPACIDAD" in service.upper():
            short, program = "PCD", "PCD_SERV"
        else:
            short, program = "PE", "PE"
        row = {
            "provincia": names.place(prov), "canton": names.place(canton),
            "parroquia": names.place(parish), "servicio": short, "modalidad": mode,
            "unidad": str(unit).strip(), "codigo_ua": "", "estado": "Suspendida",
            "unidades": 1, "programa_id": program, "corte_fuente": cut,
            "cobertura": integer(coverage, "Cobertura")
        }
        key = (names.key(prov), names.key(canton), names.key(parish), short, names.key(mode), names.key(unit))
        if key in seen:
            raise ValueError("Unidades: identificador territorial repetido: " + str(unit))
        seen.add(key)
        detail.append(row)
    if not detail:
        raise ValueError("Unidades: el detalle está vacío.")
    total = next((r for r in summary if r and names.key(r[0]) == "TOTAL GENERAL"), None)
    if total is None or len(total) < 3:
        raise ValueError("Unidades: falta 'Total general' en RESUMEN.")
    if (len(detail), sum(r["cobertura"] for r in detail)) != (
            integer(total[1], "Total unidades"), integer(total[2], "Total cobertura")):
        raise ValueError("Unidades: DETALLE y RESUMEN no concilian en conteos y cobertura.")
    counts = Counter((r["provincia"], r["servicio"], r["programa_id"]) for r in detail)
    result = {
        "corte": cut, "fuente": name, "sha256": hashlib.sha256(binary).hexdigest(),
        "registros": [
            {"provincia": p, "servicio": s, "programa_id": g, "estado": "Suspendida",
             "unidades": n, "corte_fuente": cut}
            for (p, s, g), n in sorted(counts.items())
        ],
        "detalle": detail, "fuentes_por_provincia": {r["provincia"]: cut for r in detail},
        "validacion": {
            "registros_detalle": len(detail), "suspendidas_total": len(detail),
            "cobertura_total": sum(r["cobertura"] for r in detail),
            "criterio": "Último inventario disponible. Reemplaza, no acumula."
        }
    }
    source(data, name, binary)
    return result, {"unidades_suspendidas": len(detail),
                    "cobertura": sum(row["cobertura"] for row in detail),
                    "unidades_corte_anterior": len(continuity.get("detalle", []))}


def build(snapshot, continuity, files, publication, units_cut):
    """Construcción pura: no escribe a disco ni GitHub; devuelve binarios y control."""
    date.fromisoformat(publication)
    date.fromisoformat(units_cut)
    if units_cut > publication:
        raise ValueError("El corte fuente de unidades no puede superar la publicación.")
    data = json.loads(json.dumps(snapshot))
    cont = json.loads(json.dumps(continuity))
    results = {}
    for kind in ("alertas", "kits", "suspendidas"):
        if kind not in files:
            continue
        name, binary = files[kind]
        if processed(data, binary) or (kind == "suspendidas" and hashlib.sha256(binary).hexdigest() == cont.get("sha256")):
            results[kind] = {"archivo": name, "sin_cambios": "Este Excel ya fue incorporado"}
            continue
        if kind == "alertas":
            results[kind] = alerts(data, name, binary, publication)
        elif kind == "kits":
            results[kind] = kits(data, name, binary, publication)
        else:
            cont, results[kind] = suspendidas(data, cont, name, binary, units_cut)
    if not any("sin_cambios" not in r for r in results.values()):
        return {}, results
    # No se permiten cambios incidentales en otras secciones institucionales.
    for key in ("bonos", "brigadas", "notas", "criterio_alertas"):
        if data.get(key) != snapshot.get(key):
            raise ValueError(f"Se detectó modificación no autorizada en {key}.")
    data["corte"] = publication
    data["generado_utc"] = datetime.now(timezone.utc).isoformat()
    data.pop("pdf_publicado", None)
    # Contratos JSON preexistentes: claves y convenciones originales intactas.
    products = {
        "seguimiento": (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode(),
        "continuidad": (json.dumps(cont, ensure_ascii=False, indent=2) + "\n").encode(),
    }
    # Parquet interno: columnas operativas estables, excluyendo narrativas o listas.
    alert_fields = ["codigo", "fecha", "provincia", "canton", "estado", "prioridad",
                    "codigo_ua", "unidad", "afectados_fuente", "afectacion_servicio_confirmada",
                    "servicio", "afectacion_servicio", "origen", "tipo_alerta"]
    frames = {
        "parquet_alertas": pd.DataFrame(data["alertas"]).reindex(columns=alert_fields),
        "parquet_kits": pd.DataFrame(data["kits"]).reindex(columns=[
            "id_kobo", "fecha", "provincia", "canton", "kits", "familias"]),
        "parquet_unidades": pd.DataFrame(cont.get("detalle", [])).reindex(columns=[
            "provincia", "canton", "parroquia", "servicio", "modalidad", "unidad",
            "codigo_ua", "estado", "unidades", "programa_id", "corte_fuente", "cobertura"]),
    }
    for key, frame in frames.items():
        if key == "parquet_alertas":
            frame["afectados_fuente"] = pd.to_numeric(frame["afectados_fuente"], errors="coerce").astype("Int64")
            frame["afectacion_servicio_confirmada"] = frame["afectacion_servicio_confirmada"].astype("boolean")
        stream = BytesIO()
        frame.to_parquet(stream, engine="pyarrow", compression="zstd", index=False)
        products[key] = stream.getvalue()
    # Auditoría: diferenciar el histórico de códigos del universo del periodo.
    previous_ids = {str(x["codigo"]) for x in snapshot.get("alertas", [])}
    current_ids = {str(x["codigo"]) for x in data.get("alertas", [])}
    if not previous_ids.issubset(current_ids):
        raise ValueError("No se permite borrar códigos de alertas del histórico.")
    window = data.get("desde", "2026-09-28")
    latest = publication
    active = [r for r in data["alertas"] if window <= r.get("fecha", "") <= latest]
    from src.enos import included
    included_active = [r for r in active if included(r, data)]
    coincidences = {}
    for item in active:
        ua = str(item.get("codigo_ua") or "").strip()
        if ua:
            key = (ua, item.get("fecha", ""))
            coincidences.setdefault(key, set()).add(item["codigo"])
    suspicious = [{"ua": ua, "fecha": dt, "cantidad_codigos": len(codes)}
                  for (ua, dt), codes in coincidences.items() if len(codes) > 1]
    old_kits = {r["id_kobo"]: r for r in snapshot.get("kits", [])}
    new_kits = {r["id_kobo"]: r for r in data.get("kits", [])}
    if len(old_kits) != len(snapshot.get("kits", [])):
        raise ValueError("La base anterior de kits tiene identificadores duplicados.")
    results["auditoria"] = {
        "desde": window, "hasta": latest,
        "alertas_historico": len(data["alertas"]),
        "alertas_periodo_codigo": len(active),
        "alertas_periodo_con_criterio": len(included_active),
        "coincidencias_ua_fecha": suspicious[:25],
        "nuevos_codigos_historico": len(current_ids - previous_ids),
        "kits_historico": sum(r["kits"] for r in new_kits.values()),
        "kits_periodo": sum(r["kits"] for r in new_kits.values() if window <= r["fecha"] <= latest),
        "nuevos_ids_kobo": len(set(new_kits) - set(old_kits)),
        "unidades_suspendidas": len(cont.get("detalle", [])),
        "cobertura_suspendida": sum(r.get("cobertura", 0) for r in cont.get("detalle", [])),
        "corte_unidades": cont.get("corte"),
        "bonos_sin_modificar": data.get("bonos") == snapshot.get("bonos"),
        "brigadas_sin_modificar": data.get("brigadas") == snapshot.get("brigadas"),
    }
    return products, results
