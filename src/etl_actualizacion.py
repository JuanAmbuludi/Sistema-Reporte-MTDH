"""Actualización compatible de coberturas, ejecución y acumulados VIS/VIE.

Los tres insumos nuevos tienen granos distintos. Se concilian los usuarios por
programa/parroquia antes de agregar por provincia; el presupuesto nunca se une
a cada modalidad. La base anterior aporta exclusivamente el acumulado previo.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from .table_source import load_workbook

from .etl import MONEY_TYPE, PROGRAMS, PROVINCES, SCHEMA, _sha256, _write_table, norm, number, parse_period
from .data import load_data, summarize

ALIASES = {name: definition[0] for name, definition in PROGRAMS.items()}
ALIASES.update({"BONO JOAQUIN GALLEGOS LARA": "BJGL", "BONO DE DESARROLLO HUMANO": "BDH",
                "BONO DE DESARROLLO HUMANO CON COMPONENTE VARIABLE": "BDHV", "BONO 1000 DIAS": "BMD",
                "PENSION MIS MEJORES ANOS": "MMA", "PENSION TODA UNA VIDA": "PTV"})
DEFINITIONS = {value[0]: value for value in PROGRAMS.values()}
PROVINCE_NAMES = {value[0]: value[1] for value in PROVINCES.values()}
ZERO = Decimal("0.000000")
UPDATED_SCHEMA = SCHEMA.append(pa.field("presupuesto_codificado", MONEY_TYPE)).append(
    pa.field("estado_registro", pa.string())).append(pa.field("fuente_cobertura", pa.string())).append(
    pa.field("fuente_presupuesto", pa.string())).append(pa.field("fuente_acumulado", pa.string()))
UPDATED_SCHEMA = UPDATED_SCHEMA.with_metadata({**(SCHEMA.metadata or {}), b"mtdh.schema_version": b"1.1.0"})


def read_rows(path: Path, required: set[str], sheet: str | None = None) -> list[dict]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = book[sheet] if sheet else book.active
        values = ws.iter_rows(values_only=True)
        headers = next(values)
        if len(set(headers)) != len(headers) or not required <= set(headers):
            raise ValueError(f"Encabezados inválidos en {path.name}: faltan {sorted(required - set(headers))}.")
        rows = []
        for index, cells in enumerate(values, 2):
            if all(v is None or v == "" for v in cells):
                continue
            row = dict(zip(headers, cells))
            row["fuente_fila"] = index
            row["fuente_hoja"] = ws.title
            rows.append(row)
        if not rows:
            raise ValueError(f"La fuente {path.name} está vacía.")
        return rows
    finally:
        book.close()


def code(value, length: int, name: str) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit() or len(text) > length:
        raise ValueError(f"Código {name} inválido: {value!r}.")
    return text.zfill(length)


def identify(row, *, coverage=False):
    name = row["modalidad"] if coverage and norm(row["servicio"]) == "SANCCO" else row["servicio"]
    try:
        pid = ALIASES[norm(name)]
    except KeyError:
        raise ValueError(f"Servicio o bono no homologado, fila {row['fuente_fila']}: {name!r}.") from None
    province = code(row["id_provincia"], 2, "provincia")
    canton = code(row["id_canton"], 4, "cantón")
    parish = code(row["id_parroquia"], 6, "parroquia")
    if province not in PROVINCE_NAMES or not canton.startswith(province) or not parish.startswith(canton):
        raise ValueError(f"Jerarquía territorial inválida en fila {row['fuente_fila']}.")
    expected_province = norm(PROVINCE_NAMES[province])
    if norm(row["provincia"]) != expected_province:
        raise ValueError(f"Código y nombre provincial no coinciden, fila {row['fuente_fila']}.")
    return pid, province, canton, parish


def money(value, context):
    return number(value, context)


def source_metadata(path):
    return {"archivo": Path(path).name, "sha256": _sha256(path)}


def write_detail(rows: list[dict], path: Path, grain: str) -> None:
    """Stable monetary precision and explicit grain for the new detail tables."""
    schema = pa.Table.from_pylist(rows).schema
    fields = [pa.field(field.name, MONEY_TYPE if field.name.startswith("presupuesto_") or
                        field.name in {"total_codificado_origen", "programado_origen", "programado_acumulado"}
                        else field.type, nullable=field.nullable) for field in schema]
    schema = pa.schema(fields, metadata={b"mtdh.schema_version": b"1.0.0", b"mtdh.grain": grain.encode("utf-8")})
    _write_table(rows, path, schema)


def refresh_vis_vie(output: Path, users_path: Path, budget_path: Path, period: str, *, period_source: str) -> dict:
    cut = parse_period(period)
    old_rows = pq.read_table(output / "indicadores.parquet").to_pylist()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest["periodo"] != cut.isoformat():
        raise ValueError("El corte inicial y la actualización no coinciden.")
    # The old workbook explicitly supplies 2023–2025; it must not be silently relabelled for another year.
    if cut.year != 2026:
        raise ValueError("El acumulado anterior de este insumo corresponde a 2023–2025. Para otro año debe actualizarse su fuente y mapeo.")
    users = read_rows(users_path, {"servicio", "modalidad", "id_provincia", "provincia", "id_canton", "id_parroquia",
                                  "sumsumusuario", "sumunidad", "cooperante", "fecha"})
    budgets = read_rows(budget_path, {"servicio", "vice", "id_provincia", "provincia", "id_canton", "id_parroquia",
                                    "sumusuarios", "total_devengado", "total_codificado", "codigo", "distribucion",
                                    "presupuesto_devengado_corriente", "presupuesto_devengado_inversion",
                                    "presupuesto_codificado_corriente", "presupuesto_codificado_inversion"})
    coverage = defaultdict(lambda: {"usuarios": 0, "unidades": 0})
    user_parishes = defaultdict(int)
    seen_coverage = set()
    user_detail, budget_detail = [], []
    observed_dates = set()
    for row in users:
        pid, province, canton, parish = identify(row, coverage=True)
        section = DEFINITIONS[pid][2]
        key = (pid, parish, norm(row["modalidad"]), norm(row["cooperante"]))
        if key in seen_coverage:
            raise ValueError(f"Cobertura duplicada por programa/parroquia/modalidad/cooperante: {key}.")
        seen_coverage.add(key)
        count = number(row["sumsumusuario"], f"usuarios fila {row['fuente_fila']}", count=True)
        units = None if section == "bonos_pensiones" else number(row["sumunidad"], f"unidades fila {row['fuente_fila']}", count=True)
        raw_date = row["fecha"]
        source_date = None
        if raw_date not in (None, ""):
            source_date = pd.Timestamp(raw_date).date()
            if source_date.year != cut.year or source_date.month != cut.month:
                raise ValueError(f"Fecha de cobertura distinta del corte solicitado: {source_date}.")
            observed_dates.add(source_date.isoformat())
        elif section == "proteccion_integral":
            raise ValueError("Una fila de servicios no tiene fecha de cobertura.")
        coverage[(pid, province)]["usuarios"] += count
        coverage[(pid, province)]["unidades"] += units or 0
        user_parishes[(pid, parish)] += count
        user_detail.append({"periodo": cut, "programa_id": pid, "programa": DEFINITIONS[pid][1], "seccion": section,
                            "provincia_codigo": province, "provincia": PROVINCE_NAMES[province], "canton_codigo": canton,
                            "canton": str(row["canton"]).strip(), "parroquia_codigo": parish, "parroquia": str(row["parroquia"]).strip(),
                            "modalidad": str(row["modalidad"]).strip(), "cooperante": str(row["cooperante"] or "").strip(),
                            "usuarios": count, "unidades": units, "fecha_origen": source_date,
                            "fuente_archivo": users_path.name, "fuente_hoja": row["fuente_hoja"], "fuente_fila": row["fuente_fila"]})
    if not observed_dates:
        raise ValueError("La cobertura no documenta ninguna fecha de servicios.")
    budget_parishes, totals = {}, defaultdict(lambda: {"ejecutado": ZERO, "codificado": ZERO})
    allocations = defaultdict(list)
    raw_cod_total = ZERO
    changed_cod_rows = 0
    max_dev_rounding = ZERO
    for row in budgets:
        pid, province, canton, parish = identify(row)
        section = DEFINITIONS[pid][2]
        if norm(row["vice"]) != ("VIS" if section == "proteccion_integral" else "VIE"):
            raise ValueError("La columna vice no coincide con el programa homologado.")
        key = (pid, parish)
        if key in budget_parishes:
            raise ValueError(f"Presupuesto duplicado por programa y parroquia: {key}.")
        budget_parishes[key] = number(row["sumusuarios"], "usuarios del presupuesto", count=True)
        executed = money(row["total_devengado"], "total_devengado")
        original_cod = money(row["total_codificado"], "total_codificado")
        raw_cod_total += original_cod
        distribution = None
        if section == "proteccion_integral":
            current = money(row["presupuesto_codificado_corriente"], "codificado corriente")
            investment = money(row["presupuesto_codificado_inversion"], "codificado inversión")
            codified = current + investment
            components_dev = money(row["presupuesto_devengado_corriente"], "devengado corriente") + money(row["presupuesto_devengado_inversion"], "devengado inversión")
            # The source stores single-precision amounts. Validate within its precision, not with fictitious exact cents.
            tolerance = max(Decimal("0.01"), max(executed, original_cod) * Decimal("0.0000002"))
            dev_difference = abs(executed - components_dev)
            max_dev_rounding = max(max_dev_rounding, dev_difference)
            if dev_difference > tolerance:
                raise ValueError(f"Devengado no concilia con sus componentes, fila {row['fuente_fila']}.")
            distribution = Decimal(str(row["distribucion"]))
            if not distribution.is_finite() or distribution <= 0 or distribution > 1:
                raise ValueError("Proporción territorial fuera de (0,1].")
            if abs(original_cod * distribution - codified) > tolerance:
                raise ValueError(f"Codificado distribuido no concilia, fila {row['fuente_fila']}.")
            district = str(row["codigo"] or "").strip()
            if not district:
                raise ValueError("Falta la clave de distribución distrital.")
            allocations[(pid, district)].append((distribution, original_cod))
            changed_cod_rows += int(abs(original_cod - codified) > Decimal("0.01"))
        else:
            codified = original_cod
        if executed - codified > max(Decimal("0.01"), codified * Decimal("0.0000002")):
            raise ValueError(f"Devengado mayor al codificado, fila {row['fuente_fila']}.")
        totals[(pid, province)]["ejecutado"] += executed
        totals[(pid, province)]["codificado"] += codified
        budget_detail.append({"periodo": cut, "programa_id": pid, "programa": DEFINITIONS[pid][1], "seccion": section,
                              "provincia_codigo": province, "provincia": PROVINCE_NAMES[province], "canton_codigo": canton,
                              "parroquia_codigo": parish, "usuarios_control": budget_parishes[key],
                              "presupuesto_ejecutado": executed, "presupuesto_codificado": codified,
                              "total_codificado_origen": original_cod, "distribucion": float(distribution) if distribution else None,
                              "metodo_codificado": "corriente + inversión distribuidos" if section == "proteccion_integral" else "total_codificado origen",
                              "fuente_archivo": budget_path.name, "fuente_hoja": row["fuente_hoja"], "fuente_fila": row["fuente_fila"]})
    if dict(user_parishes) != budget_parishes:
        raise ValueError("Los usuarios de cobertura y presupuesto no concilian por programa y parroquia.")
    for key, group in allocations.items():
        if abs(sum(v[0] for v in group) - 1) > Decimal("0.00001") or len({v[1] for v in group}) != 1:
            raise ValueError(f"Distribución distrital incompleta o inconsistente: {key}.")
    old_keys = {(r["programa_id"], r["provincia_codigo"]) for r in old_rows}
    if set(coverage) - old_keys or set(totals) != set(coverage):
        raise ValueError("No se dispone de acumulado anterior o presupuesto para todas las claves nuevas.")
    rows, reconciliation = [], []
    for old in old_rows:
        key = old["programa_id"], old["provincia_codigo"]
        row = dict(old)
        empty_reference = old["usuarios"] == 0 and old["monto_fiscal"] == 0
        if key not in coverage and old["programa_id"] not in {"PAM", "PCD"} and not empty_reference:
            raise ValueError(f"Falta un programa/provincia vigente: {key}.")
        counts, cash = coverage[key], totals[key]
        row.update(usuarios=counts["usuarios"], unidades=counts["unidades"] if old["seccion"] == "proteccion_integral" else None,
                   unidades_origen=counts["unidades"], monto_fiscal=cash["ejecutado"], presupuesto_ejecutado=cash["ejecutado"],
                   presupuesto_codificado=cash["codificado"], monto_gobierno=old["monto_anterior"] + cash["ejecutado"])
        row["estado_registro"] = "solo_acumulado_anterior" if old["programa_id"] in {"PAM", "PCD"} else "vigente"
        row.update(fuente_cobertura=users_path.name, fuente_presupuesto=budget_path.name,
                   fuente_acumulado=manifest["fuente"]["archivo"])
        rows.append(row)
        reconciliation.append({"programa_id": key[0], "provincia_codigo": key[1], "programa": row["programa"], "provincia": row["provincia"],
                               "usuarios_antes": old["usuarios"], "usuarios_ahora": row["usuarios"],
                               "diferencia_usuarios": row["usuarios"] - old["usuarios"],
                               "unidades_antes": old["unidades"], "unidades_ahora": row["unidades"],
                               "fiscal_antes": old["monto_fiscal"], "ejecutado_ahora": row["presupuesto_ejecutado"],
                               "diferencia_fiscal": row["monto_fiscal"] - old["monto_fiscal"],
                               "acumulado_anterior_conservado": old["monto_anterior"]})
    _write_table(rows, output / "indicadores.parquet", UPDATED_SCHEMA)
    write_detail(user_detail, output / "cobertura_territorial.parquet", "periodo/programa_id/parroquia_codigo/modalidad/cooperante")
    write_detail(budget_detail, output / "presupuesto_territorial.parquet", "periodo/programa_id/parroquia_codigo")
    pd.DataFrame(reconciliation).to_parquet(output / "comparacion_versiones.parquet", index=False, compression="zstd")
    manifest["schema_version"] = "1.1.0"
    manifest["generado_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["periodo_origen"] = period_source
    manifest["fuentes"] = {"acumulado_anterior": manifest["fuente"], "cobertura": source_metadata(users_path), "presupuesto": source_metadata(budget_path)}
    # Retain the legacy primary source reference for consumers of this field.
    # Per-metric provenance is explicit in fuentes, rather than a synthetic file hash.
    manifest["fuente"]["uso"] = "Referencia histórica del acumulado; cobertura y ejecución actuales en fuentes."
    manifest["totales"] = summarize(load_data(output))
    manifest["ejecucion_complementaria"] = {"archivo": budget_path.name, "fase": "devengado", "cobertura_pct": 100,
                                             "filas": len(rows), "periodo_origen": "Corte del operador; conciliación con la cobertura por programa y parroquia."}
    manifest["control_calidad"].update({"ejecucion_disponible_filas": len(rows), "filas_cobertura": len(users),
        "filas_presupuesto": len(budgets), "usuarios_conciliados_parroquia": True, "grupos_distribucion_validados": len(allocations),
        "codificados_repetidos_no_sumados": changed_cod_rows, "max_diferencia_redondeo_devengado_usd": float(max_dev_rounding),
        "codificado_suma_columna_original_no_utilizable": float(raw_cod_total),
        "codificado_depurado": float(sum(v["presupuesto_codificado"] for v in rows)),
        "fechas_cobertura_servicios": sorted(observed_dates)})
    manifest["advertencias"] = [
        "Cobertura: agregados reportados, sin identificadores para deduplicar personas o unidades entre modalidades, cooperantes o períodos.",
        "Servicios: fecha explícita en la cobertura. Bonos y presupuesto: corte asignado por el operador y conciliado por programa/parroquia; no contienen una serie mensual.",
        "El presupuesto ejecutado corresponde a total_devengado; no es pago efectivo ni monto exclusivamente del mes.",
        "Codificado VIS: suma de componentes corriente e inversión distribuidos. total_codificado repite el total distrital en cada parroquia y no se suma.",
        "Se preserva el acumulado anterior 2023–2025; el acumulado de gobierno suma ese valor y el devengado fiscal actual. No implica una fase presupuestaria homogénea en años anteriores.",
        "Las pensiones PAM y PCD solo aportan acumulados anteriores; no tienen registros vigentes en las nuevas fuentes.",
        "Unidades: se utilizan las de Usuarios_vis_vie, no las de la base presupuestaria, cuyos conteos difieren.",
        "Las referencias 2024 y 2025 no documentan mes; no se convierten en cierres mensuales.",
        "La base financiera institucional tiene su propio universo y no se suma ni se distribuye sobre VIS/VIE."]
    manifest["definiciones"].update({
        "usuarios": "Suma de sumsumusuario de la base de cobertura, conciliada con sumusuarios de presupuesto por programa/parroquia.",
        "unidades": "Suma de sumunidad de cobertura para servicios; sin identificadores de unidad para verificar unicidad. No aplica a bonos.",
        "monto_fiscal": "Alias compatible del presupuesto ejecutado fiscal (total_devengado) para conservar los nombres del dashboard.",
        "presupuesto_ejecutado": "Total devengado fiscal informado en Presupuesto_vis_vie; agregado territorialmente sin repetir modalidades.",
        "presupuesto_codificado": "VIE: total_codificado. VIS: presupuesto_codificado_corriente + presupuesto_codificado_inversion, ya distribuidos.",
        "monto_gobierno": "Acumulado anterior 2023–2025 más devengado fiscal del corte actual; no sumar otra vez sus componentes.",
        "fuente_hoja / fuente_fila": "Fila del Excel anterior que respalda el acumulado previo. La procedencia del detalle nuevo está en los Parquet territoriales.",
    })
    manifest["decision_versiones"] = "Usar Usuarios_vis_vie.parquet y Presupuesto_vis_vie.parquet para el detalle territorial. Conservar Acumulado_VIS_VIE/ como fuente histórica del acumulado 2023–2025. El presupuesto social aprobado nacional se consulta por separado en data/series."
    manifest["comparacion"] = {"usuarios_servicios_antes": sum(r["usuarios"] for r in old_rows if r["seccion"] == "proteccion_integral"),
                               "usuarios_servicios_ahora": manifest["totales"]["usuarios_servicios"],
                               "unidades_antes": sum(r["unidades"] or 0 for r in old_rows), "unidades_ahora": manifest["totales"]["unidades"],
                               "detalle": "comparacion_versiones.parquet"}
    for name in ["indicadores.parquet", "cobertura_territorial.parquet", "presupuesto_territorial.parquet"]:
        manifest["archivos"][name] = {"sha256": _sha256(output / name), "bytes": (output / name).stat().st_size,
                                      "filas": pq.ParquetFile(output / name).metadata.num_rows}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def build_financial(path: Path, output: Path, period: str, period_source: str) -> dict:
    """Preserve financial source lines. Identical rows are flagged, never silently deleted."""
    cut = parse_period(period)
    if not period_source.strip():
        raise ValueError("Debe documentarse el origen del corte financiero.")
    raw = read_rows(path, {"CODIFICADO", "CERTIFICADO", "DEVENGADO", "PROGRAMA", "COD. PROGRAMA", "COD. EOD",
                          "UNIDAD EJECUTORA", "PROGRAMADO 2024", "PROGRAMADO acum", "% EJECUCIÓN", "TIPO DE GASTO"})
    seen, rows = set(), []
    duplicate_count = 0
    duplicate_cod = ZERO
    for item in raw:
        # Exclude source row number; identical content can still be distinct budget lines when item codes are absent.
        fingerprint = tuple((k, str(v)) for k, v in item.items() if k not in {"fuente_fila", "fuente_hoja"})
        duplicate = fingerprint in seen
        seen.add(fingerprint)
        codified, certified, executed = [money(item[k], k) for k in ["CODIFICADO", "CERTIFICADO", "DEVENGADO"]]
        if executed - codified > Decimal("0.01"):
            raise ValueError("Devengado institucional excede el codificado de su fila.")
        source_ratio = float(item["% EJECUCIÓN"])
        ratio = float(executed / codified) if codified else 0.0
        if abs(source_ratio - ratio) > 0.000001:
            raise ValueError("Porcentaje institucional no concilia con devengado/codificado.")
        duplicate_count += int(duplicate)
        duplicate_cod += codified if duplicate else ZERO
        rows.append({"periodo": cut, "anio": cut.year, "zona": str(item["ZONA"]).strip(),
                     "eod_codigo": str(item["COD. EOD"]), "unidad_ejecutora": str(item["UNIDAD EJECUTORA"]).strip(),
                     "programa_codigo": str(item["COD. PROGRAMA"]), "programa": str(item["PROGRAMA"]).strip(),
                     "proyecto_codigo": str(item["COD. PROYECTO"]), "proyecto": str(item["PROYECTO"]).strip(),
                     "actividad_codigo": str(item["COD. ACTIVIDAD"]), "actividad": str(item["ACTIVIDAD"]).strip(),
                     "grupo_gasto_codigo": str(item["COD. GRUPO DE GASTO"]), "grupo_gasto": str(item["GRUPO DE GASTO"]).strip(),
                     "fuente_financiamiento_codigo": str(item["COD. FUENTE DE FINANCIAMIENTO"]),
                     "fuente_financiamiento": str(item["FUENTE DE FINANCIAMIENTO"]).strip(), "tipo_gasto": str(item["TIPO DE GASTO"]).strip(),
                     "presupuesto_codificado": codified, "presupuesto_certificado": certified, "presupuesto_ejecutado": executed,
                     "programado_origen": money(item["PROGRAMADO 2024"], "programado origen"),
                     "programado_acumulado": money(item["PROGRAMADO acum"], "programado acumulado"),
                     "fila_identica_previa": duplicate, "fuente_archivo": path.name,
                     "fuente_hoja": item["fuente_hoja"], "fuente_fila": item["fuente_fila"]})
    write_detail(rows, output / "presupuesto_institucional.parquet", "periodo/fuente_archivo/fuente_hoja/fuente_fila")
    codified = sum(r["presupuesto_codificado"] for r in rows)
    executed = sum(r["presupuesto_ejecutado"] for r in rows)
    result = {"schema_version": "1.0.0", "periodo": cut.isoformat(), "periodo_origen": period_source,
              "fuente": source_metadata(path), "filas": len(rows), "generado_utc": datetime.now(timezone.utc).isoformat(),
              "totales": {"presupuesto_codificado": float(codified), "presupuesto_ejecutado": float(executed),
                          "presupuesto_certificado": float(sum(r["presupuesto_certificado"] for r in rows)),
                          "porcentaje_ejecucion": float(executed / codified * 100) if codified else None},
              "control_calidad": {"repeticiones_exactas_conservadas": duplicate_count, "codificado_repeticiones": float(duplicate_cod)},
              "advertencias": ["Corte confirmado por el operador; el archivo no documenta una fecha de reporte y mantiene el encabezado PROGRAMADO 2024.",
                               "Los totales corresponden al universo de esta base financiera; no se suman con los de VIS/VIE ni se presume equivalencia con todo el MTDH.",
                               "Hay filas de contenido idéntico sin identificador de partida suficiente para determinar si son duplicados; se conservan y se marcan.",
                               "El porcentaje se calcula como suma de devengado / suma de codificado; no se suman ni promedian los porcentajes de las filas."],
              "archivo": "presupuesto_institucional.parquet", "sha256": _sha256(output / "presupuesto_institucional.parquet")}
    (output / "manifest_financiero.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
