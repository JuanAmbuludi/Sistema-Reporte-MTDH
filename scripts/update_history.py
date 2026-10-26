#!/usr/bin/env python3
"""Update complete monthly/daily partitions, validate, then publish all results.

Example: python scripts/update_history.py --entrada /path/to/files --web
Without --entrada, --web refreshes only the public labour sources. Input names can
carry download prefixes; exactly one matching source of each type is accepted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.historicos import (contingencies, incentives, coverage_tables, orphan_beneficiaries,
    periods, read_csv, sha256, upsert_partitions, write_parquet)
from src.presupuesto_social import read_approved


def find_source(folder, pattern):
    matches = [p for p in folder.glob(pattern) if not p.name.startswith(".")]
    if len(matches) > 1:
        raise ValueError(f"Hay más de un archivo para {pattern}; deje una única versión completa.")
    return matches[0] if matches else None


def expected_periods(inventory):
    """Assess gaps through the last supplied monthly cut, in every supplied year."""
    last_month = {}
    for item in inventory:
        if item["base"] in {"cobertura_vis.parquet", "bonos_vie.parquet", "presupuesto_social_mensual.parquet"}:
            for period in item["periodos"]:
                year, month = map(int, period.split("-"))
                last_month[year] = max(last_month.get(year, 0), month)
    return [f"{year}-{month:02d}" for year, last in sorted(last_month.items()) for month in range(1, last+1)]


def source_date(value):
    # ISO source dates are year-first even when Ecuadorian slash dates are day-first.
    return pd.to_datetime(value, errors="coerce", dayfirst=not bool(re.match(r"^\d{4}-", str(value))))


def update(data_dir, folder=None, web=False, sgde_local=None):
    data_dir = Path(data_dir)
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mtdh_history_") as temporary:
        stage = Path(temporary)/"data"
        if data_dir.exists():
            shutil.copytree(data_dir, stage)
        else:
            stage.mkdir()
        series = stage/"series"
        old_audit = series/"actualizacion.json"
        audit = json.loads(old_audit.read_text()) if old_audit.exists() else {"version": 2, "fuentes": {}, "controles": {}}
        changes = []

        def save(name, frame, keys, partitions, monies=(), note=""):
            path = series/f"{name}.parquet"
            previous = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=frame.columns)
            merged = upsert_partitions(previous, frame, keys=keys, partitions=partitions)
            write_parquet(merged, path, keys=keys, money_columns=monies, note=note)
            changes.append(name)

        def source(key, path):
            audit["fuentes"][key] = {"archivo": path.name, "sha256": sha256(path), "bytes": path.stat().st_size}

        if folder:
            folder = Path(folder)
            specs = [("VIS", "*VIS_usuarios_unidades*.parquet", "cobertura_vis", ["servicio", "modalidad"]),
                     ("VIE", "*VIE_beneficiarios_bonos*.parquet", "bonos_vie", ["bono"])]
            for kind, pattern, name, dims in specs:
                path = find_source(folder, pattern)
                if path:
                    source(name, path)
                    national, territorial, controls = coverage_tables(path, kind)
                    audit["controles"][name] = controls
                    save(name, national, ["periodo", *dims], ["periodo"],
                         note="Únicos dentro de cada grupo; no sumar entre meses ni suponer unicidad entre modalidades/bonos. Ámbito nacional.")
                    if territorial is not None:
                        save(name+"_territorial", territorial,
                             ["periodo", "nivel_territorial", "codigo_territorio", "provincia", "canton", "parroquia", *dims], ["periodo"],
                             note="Elegir un único nivel territorial. Únicos deduplicados en origen dentro de cada grupo; no sumar niveles ni sustituir el total nacional por la suma territorial.")
            path = find_source(folder, "*sanc01*.parquet")
            if path:
                source("incentivos", path)
                table, checks = incentives(path)
                audit["controles"]["incentivos"] = checks
                save("incentivos_mensuales", table, ["periodo", "programa_id", "fase"], ["periodo", "programa_id", "fase"],
                     ["monto_acreditado"], "Fecha efectiva de acreditación; respuesta SPI 1. No es devengado ni mes de derecho.")
            for kind, pattern in [("antropicos", "*sanc02*.csv"), ("contingencias", "*sanc03*.csv")]:
                path = find_source(folder, pattern)
                if path:
                    source(kind, path)
                    national, territorial, checks = contingencies(path, kind)
                    audit["controles"][kind] = checks
                    save(f"{kind}_mensuales", national, ["periodo", "criterio"], ["periodo", "criterio"], ["monto_usd"],
                         "Habilitado y cobrado usan fechas diferentes; no sumar ambos criterios. Beneficiarios distintos dentro del mes.")
                    dims = [c for c in ["provincia", "canton", "parroquia", "tipo"] if c in territorial]
                    save(f"{kind}_territorial", territorial, ["periodo", "criterio", *dims], ["periodo", "criterio"], ["monto_usd"],
                         "Desglose del resumen nacional; sus beneficiarios no son deduplicables entre territorios.")
            path = find_source(folder, "*Beneficiarios_Feminicidio.csv")
            if path:
                source("orfandad", path)
                save("beneficiarios_orfandad", orphan_beneficiaries(path), ["periodo"], ["periodo"],
                     note="Beneficiarios distintos reportados del bono por orfandad por violencia; no sumar con incentivos acreditados.")
            # The short supplied tabulations are controls, not extra beneficiaries.
            path = find_source(folder, "*Desagregacion_antropicos.csv")
            if path:
                source("control_antropicos", path)
                d = read_csv(path)
                d["periodo"] = d.anio_mes
                d = periods(d[["periodo", "habilitados", "habilitados_unicos", "monto_habilitado"]].groupby("periodo", as_index=False).sum())
                d = d.rename(columns={"habilitados_unicos": "suma_unicos_territoriales"})
                save("controles/antropicos_recibido", d, ["periodo"], ["periodo"], ["monto_habilitado"],
                     "Control recibido con versiones repetidas; NO utilizar como gasto o conteo oficial.")
            path = find_source(folder, "*Desagregacion_contingencias.csv")
            if path:
                source("control_contingencias", path)
                d = read_csv(path).rename(columns={"AÑO_MES": "periodo"})
                d = d.groupby("periodo", as_index=False)[["REG_HABILITADOS", "USUARIOS_HABILITADOS"]].sum()
                save("controles/contingencias_recibido", periods(d), ["periodo"], ["periodo"],
                     note="Control recibido; suma de únicos territoriales no garantiza únicos nacionales.")
            books = [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")]
            if len(books) > 1:
                raise ValueError("Deje únicamente el Excel de presupuesto aprobado en --entrada.")
            if books:
                path = books[0]
                source("presupuesto_aprobado", path)
                monthly, annual, checks = read_approved(path)
                audit["controles"]["presupuesto_aprobado"] = checks
                save("presupuesto_social_mensual", monthly, ["periodo", "programa_id"], ["periodo"],
                     ["devengado_mes", "devengado_acumulado"], "Devengado fiscal mensual y acumulado; sumar meses solo para devengado_mes.")
                save("presupuesto_social_asignado", annual, ["periodo", "grupo_presupuestario"], ["periodo"],
                     ["planificado_anual", "presupuesto_aprobado"], "Asignación anual al corte; BDH y BDHV comparten un solo presupuesto.")
        if web or sgde_local:
            from src.sgde_scraper import collect, contracts, retirement, youth, youth_phases, FILES
            raw, receipt = collect(sgde_local)
            tables, checks = contracts(raw[FILES[0]])
            audit["controles"]["contratos"] = checks
            for name, table in tables.items():
                dims = [c for c in table if c not in {"periodo", "anio", "mes", "mes_nombre", "fecha_corte", "contratos", "empresas"}]
                save("laboral/"+name, table, ["fecha_corte", *dims], ["fecha_corte"], note=checks["naturaleza"])
            table = retirement(raw)
            save("laboral/jubilados", table, ["fecha_corte", "anio", "dimension", "categoria", "codigo"], ["fecha_corte"],
                 ["monto_usd"], "Cada dimensión repite el universo; total, sexo, provincia y régimen nunca se suman entre sí.")
            audit["controles"]["jovenes_web"] = youth(raw)
            save("jovenes_accion_fases", youth_phases(raw), ["periodo", "fase"], ["periodo"],
                 ["monto_transferencia_usd", "presupuesto_usd", "ejecucion_usd"],
                 "Fases con ejecución o atención publicadas en SGDE; participantes son habilitados o atendidos de cada fase, no pagos mensuales.")
            evidence = series/"laboral"/f"fuentes_{checks['fecha_corte']}.json"
            # Preserve original receipt when the same source content is queried again.
            if evidence.exists():
                previous = json.loads(evidence.read_text())
                if previous.get("recursos") == receipt.get("recursos"):
                    receipt = previous
            evidence.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
            audit["fuentes"]["web"] = receipt
            update_current_labour(stage, tables["contratos_base"], checks, receipt, table)
        derived_tables(series, audit, save)
        inventory = []
        for path in sorted(series.rglob("*.parquet")):
            table = pq.ParquetFile(path)
            col = pq.read_table(path, columns=["periodo"]).column("periodo").to_pylist()
            inventory.append({"base": str(path.relative_to(series)), "filas": table.metadata.num_rows,
                "columnas": len(table.schema_arrow), "bytes": path.stat().st_size,
                "periodos": sorted(set(col)), "sha256": sha256(path)})
        audit["inventario"] = inventory
        audit["periodos_esperados"] = expected_periods(inventory)
        audit["periodos_ausentes"] = {
            item["base"]: [p for p in audit["periodos_esperados"] if p not in item["periodos"]]
            for item in inventory if "/" not in item["base"]}
        series.mkdir(exist_ok=True)
        old_audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n")
        # No data is changed until every input and cross-source check has completed.
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                target = data_dir/path.relative_to(stage)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != path.read_bytes():
                    target_temp = target.with_name(target.name+".tmp")
                    shutil.copyfile(path, target_temp)
                    target_temp.replace(target)
        return {"bases_actualizadas": changes, "bases_serie": len(inventory),
                "bytes_series": sum(v["bytes"] for v in inventory), "controles": audit["controles"]}


def derived_tables(series, audit, save):
    budget_path = series/"presupuesto_social_mensual.parquet"
    if budget_path.exists():
        budget = pd.read_parquet(budget_path)
        national = []
        vie_path = series/"bonos_vie.parquet"
        if vie_path.exists():
            vie = pd.read_parquet(vie_path).rename(columns={"bono": "programa_id", "beneficiarios_unicos": "beneficiarios"})
            # Budget PTV covers adults and minors. Keep its budget on a single grouped row.
            vie["programa_id"] = vie.programa_id.replace({"PTV_MENORES": "PTV"})
            national.append(vie.groupby(["periodo", "programa_id"], as_index=False).beneficiarios.sum())
        orphan_path = series/"beneficiarios_orfandad.parquet"
        if orphan_path.exists():
            d = pd.read_parquet(orphan_path)[["periodo", "beneficiarios"]].assign(programa_id="ORFANDAD_VIOLENCIA")
            national.append(d)
        counts = pd.concat(national, ignore_index=True) if national else pd.DataFrame(columns=["periodo", "programa_id", "beneficiarios"])
        out = budget.merge(counts, on=["periodo", "programa_id"], how="left", validate="one_to_one")
        # Habilitation is the available coverage series; dated collections remain
        # separately available in each source table and must not be added to it.
        for name, pid in [("antropicos", "ANTROPICOS"), ("contingencias", "CONTINGENCIAS")]:
            path = series/f"{name}_mensuales.parquet"
            if path.exists():
                d = pd.read_parquet(path)
                d = d.loc[d.criterio.eq("habilitado")].set_index("periodo")
                mask = out.programa_id.eq(pid)
                out.loc[mask, "beneficiarios"] = out.loc[mask, "periodo"].map(d.beneficiarios)
        out["criterio_beneficiarios"] = out.programa_id.map(lambda p: "habilitados_en_mes" if p in {"ANTROPICOS", "CONTINGENCIAS"} else "cobertura_mensual" if p in {"BDH","BDHV","BMD","MMA","PTV","BJGL","ORFANDAD_VIOLENCIA"} else "sin_dato_comparable")
        incentives_path = series/"incentivos_mensuales.parquet"
        if incentives_path.exists():
            paid = pd.read_parquet(incentives_path)
            for pid in ["COMPENSACION_GASOLINA", "COMPENSACION_DIESEL", "MIGRANTES"]:
                group = paid.loc[paid.programa_id.eq(pid)].set_index("periodo")
                mask = out.programa_id.eq(pid)
                out.loc[mask, "beneficiarios"] = out.loc[mask, "periodo"].map(group.beneficiarios)
                out.loc[mask & out.beneficiarios.notna(), "criterio_beneficiarios"] = "acreditados_en_mes"
        out["beneficiarios"] = pd.array(out.beneficiarios, dtype="Int32")
        save("resumen_social_mensual", out, ["periodo", "programa_id"], ["periodo"],
             ["devengado_mes", "devengado_acumulado"], "No sumar beneficiarios entre meses o programas. Conteos y devengado tienen criterios independientes.")
        web = audit["controles"].get("jovenes_web")
        if web:
            row = budget.loc[budget.programa_id.eq("JEA_F3") & budget.periodo.eq(web["periodo"])]
            if len(row) == 1:
                amount = row.devengado_acumulado.iloc[0]
                snapshot = periods(pd.DataFrame([{"periodo": web["periodo"], "fase": 3,
                    "habilitados_fase": web["habilitados"], "registrados_fase": web["registrados"],
                    "presupuesto_fase": Decimal(str(web["presupuesto_publicado"])),
                    "devengado_acumulado_aprobado": amount,
                    "ejecucion_publicada_web": Decimal(str(web["ejecucion_publicada"]))}]))
                save("jovenes_accion_fase3", snapshot, ["periodo", "fase"], ["periodo", "fase"],
                     ["presupuesto_fase", "devengado_acumulado_aprobado", "ejecucion_publicada_web"],
                     "150.000 son habilitados de la fase, no pagos mensuales. Prevalece devengado aprobado sobre tablero web.")
                audit["controles"]["conciliacion_jea"] = {"diferencia_aprobado_menos_web": str(amount-Decimal(str(web["ejecucion_publicada"]))),
                    "decision": "Usar archivo aprobado para devengado. SANC01 solo acredita pagos de julio de fase 3; cobertura bancaria parcial."}


def update_current_labour(stage, base, checks, receipt, retirees):
    """Refresh current stock; preserve the independently dated SUT monthly cohorts."""
    from src.laboral import SCHEMA
    import pyarrow as pa
    path = stage/"processed/gestion_laboral.parquet"
    if not path.exists():
        return
    rows = pq.read_table(path).to_pylist()
    template = next(r for r in rows if r["indicador_id"] == "contratos_vigentes_total")
    previous_date = source_date(template["actualizacion_fuente"])
    if pd.notna(previous_date) and previous_date.date() > pd.Timestamp(checks["fecha_corte"]).date():
        return  # A stale upstream file must never roll the live stock backwards.
    digest = next(r["sha256"] for r in receipt["recursos"] if r["url"].endswith("dashboard_data.json"))
    row = dict(template)
    row.update(consulta_id="sgde_"+checks["fecha_corte"]+"_"+digest[:8],
        valor=Decimal(str(checks["por_estado"].get("Vigente", 0))).quantize(Decimal("0.01")),
        fecha_consulta_utc=datetime.fromisoformat(receipt["consulta_utc"]),
        actualizacion_fuente=pd.Timestamp(checks.get("fecha_hora_corte") or checks["fecha_corte"]).strftime("%d/%m/%Y %H:%M:%S"),
        fuente_url="https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/MDTDH/kpi_contratos.html",
        fuente_id="sgde_contratos", evidencia_sha256=digest,
        filtros_json=json.dumps({"estado": "Vigente", "ambito": "nacional"}),
        filtro_desde=None, filtro_hasta=None,
        nota="Stock de contratos vigentes publicado por SGDE a su fecha_corte. No es flujo del mes. La serie mensual SUT conserva su fecha original.")
    rows = [r for r in rows if r["indicador_id"] != "contratos_vigentes_total"]+[row]
    current_retirees = next((r for r in rows if r["indicador_id"] == "jubilados_compensados"), None)
    totals = retirees.loc[retirees.dimension.eq("total")].sort_values("anio")
    if current_retirees and not totals.empty:
        latest = totals.iloc[-1]
        # The source explicitly documents a September 18 cut, later than the
        # previous August news release. Keep newer independent sources if any.
        prior = current_retirees.get("actualizacion_fuente") or current_retirees.get("publicacion_fuente")
        prior_date = source_date(prior)
        if pd.isna(prior_date) or prior_date.date() <= pd.Timestamp(latest.fecha_corte).date():
            for indicator, value, label, unit in [
                ("jubilados_compensados", latest.expedientes, "Expedientes de jubilación compensados", "expedientes"),
                ("compensaciones_jubilares_usd", latest.monto_usd, "Compensaciones jubilares", "USD")]:
                old = next(r for r in rows if r["indicador_id"] == indicator)
                new = dict(old)
                new.update(consulta_id=row["consulta_id"], valor=Decimal(str(value)).quantize(Decimal("0.01")),
                    indicador=label, unidad=unit, operador="=", anio=int(latest.anio),
                    periodo=pd.Timestamp(latest.periodo).date(), granularidad="acumulado_anual_al_corte",
                    fuente_id="sgde_jubilados", fuente_url="https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/MDTDH/kpis.html#/kpis-trabajo",
                    fecha_consulta_utc=row["fecha_consulta_utc"], actualizacion_fuente=str(latest.fecha_corte), publicacion_fuente=None,
                    evidencia_sha256=next(r["sha256"] for r in receipt["recursos"] if r["url"].endswith("jubilados/gestion.csv")),
                    filtros_json=json.dumps({"anio": int(latest.anio), "dimension": "total"}),
                    nota=f"Expedientes y monto acumulados del año al {latest.fecha_corte}. No son personas únicas ni gasto exclusivo de septiembre.")
                rows = [r for r in rows if r["indicador_id"] != indicator]+[new]
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), path, compression="zstd")
    manifest_path = path.parent/"manifest_laboral.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.setdefault("consulta_cohortes_original", {
        "consulta_id": manifest["consulta_id"], "fecha_consulta_utc": manifest["fecha_consulta_utc"]})
    manifest.update(schema_version="1.1.0", consulta_id=row["consulta_id"],
                    fecha_consulta_utc=receipt["consulta_utc"],
                    alcance_evidencia="evidencia y copia_del_corte respaldan la consulta SUT original, conservada como referencia. Los cortes actuales están en cortes_por_indicador y data/series/laboral.")
    manifest.update(parquet_sha256=sha256(path), actualizacion_stock_sgde=checks,
                    fuentes_stock=receipt, filas=len(rows))
    # List only sources used by the current rows. Earlier source configurations
    # remain in their dated evidence, not in the current source catalog.
    manifest["fuentes"] = {r["fuente_id"]: r["fuente_url"] for r in rows}
    manifest["cortes_por_indicador"] = {
        r["indicador_id"]: {"fecha_corte": r["actualizacion_fuente"] or r["publicacion_fuente"],
                            "fuente": r["fuente_url"], "unidad": r["unidad"]} for r in rows}
    manifest["advertencias"] = [
        "No sumar indicadores, unidades, cortes ni naturalezas diferentes.",
        "Los meses del SUT son cohortes con estado a su fecha de observación, no stocks históricos.",
        "El stock y las cohortes conservan cortes independientes; no calcular participaciones entre ellos.",
        "La jubilación SGDE mide expedientes y monto acumulado anual al corte publicado, no personas únicas ni gasto de un solo mes."]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--sgde-local", type=Path, help="Reproducir recursos públicos desde un checkout SGDE.")
    args = parser.parse_args()
    if not (args.entrada or args.web or args.sgde_local):
        parser.error("Indique --entrada y/o --web.")
    try:
        result = update(args.data, args.entrada, args.web, args.sgde_local)
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        print(f"Actualización cancelada; bases anteriores conservadas: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
