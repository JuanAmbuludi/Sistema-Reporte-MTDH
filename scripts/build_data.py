#!/usr/bin/env python3
"""Genera las bases VIS/VIE y, opcionalmente, gestión laboral con fuentes web oficiales."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.etl import build_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Configuración reproducible de fuentes y cortes; rutas relativas a la raíz del proyecto.")
    parser.add_argument("excel", type=Path, nargs="?", help="Excel o fuente Parquet; por ejemplo data/source/Acumulado_VIS_VIE.")
    parser.add_argument("--period", "--periodo", help="Corte AAAA-MM; obligatorio al importar Excel.")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "processed")
    parser.add_argument("--period-source", default="Corte indicado por el operador; no consta en el Excel.", help="Documento o evidencia que respalda el mes del corte.")
    parser.add_argument("--sheet", default="provincial", help="Nombre de la hoja vigente.")
    parser.add_argument("--ejecucion", type=Path, help="Parquet o CSV complementario de presupuesto ejecutado verificado.")
    parser.add_argument("--usuarios", type=Path, help="Fuente de cobertura Usuarios_vis_vie.parquet.")
    parser.add_argument("--presupuesto", type=Path, help="Fuente de devengado y codificado Presupuesto_vis_vie.parquet.")
    parser.add_argument("--financiero", type=Path, help="Excel o Parquet de presupuesto institucional; se procesa separado de VIS/VIE.")
    parser.add_argument("--financiero-periodo", help="Corte AAAA-MM confirmado para el archivo financiero.")
    parser.add_argument("--financiero-period-source", help="Evidencia o confirmación del corte financiero.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--incluir-laboral", action="store_true", help="Generar VIS/VIE y gestión laboral en la misma ejecución.")
    mode.add_argument("--solo-laboral", action="store_true", help="Actualizar únicamente la base laboral.")
    parser.add_argument("--laboral-desde", help="Primer mes completo del SUT, AAAA-MM; por defecto enero del año del corte.")
    parser.add_argument("--laboral-hasta", help="Último mes completo del SUT, AAAA-MM; por defecto --period.")
    parser.add_argument("--fuentes-laborales", type=Path, help="JSON de URLs oficiales; por defecto config/fuentes_laborales.json.")
    parser.add_argument("--mostrar-navegador", action="store_true", help="Mostrar Chromium durante la extracción.")
    parser.add_argument("--laboral-evidencia", type=Path, help="Reproducir una extracción guardada, sin consultar internet (conserva fecha original).")
    args = parser.parse_args()
    if args.config:
        try:
            preset = json.loads(args.config.read_text(encoding="utf-8"))
            allowed = {"excel", "period", "period_source", "usuarios", "presupuesto", "financiero", "financiero_periodo", "financiero_period_source"}
            if not set(preset) <= allowed:
                raise ValueError(f"Opciones de configuración desconocidas: {set(preset) - allowed}")
            for name, value in preset.items():
                if getattr(args, name) is None or (name == "period_source" and "no consta" in args.period_source):
                    if name in {"excel", "usuarios", "presupuesto", "financiero"}:
                        value = Path(__file__).resolve().parents[1] / value
                    setattr(args, name, value)
        except (OSError, ValueError, TypeError) as error:
            parser.error(f"Configuración inválida: {error}")
    laboral = args.incluir_laboral or args.solo_laboral
    if bool(args.usuarios) != bool(args.presupuesto):
        parser.error("Indique --usuarios y --presupuesto juntos.")
    if args.usuarios and args.ejecucion:
        parser.error("El presupuesto actualizado ya aporta ejecución; no combine --ejecucion.")
    if args.financiero and not (args.financiero_periodo and args.financiero_period_source):
        parser.error("El archivo financiero necesita --financiero-periodo y --financiero-period-source.")
    if args.solo_laboral and any([args.usuarios, args.presupuesto, args.financiero]):
        parser.error("--solo-laboral no procesa fuentes VIS/VIE ni financieras.")
    if not args.solo_laboral and (not args.excel or not args.period):
        parser.error("Indique el Excel y --period, o use --solo-laboral.")
    if args.solo_laboral and (args.excel or args.ejecucion):
        parser.error("--solo-laboral no utiliza Excel ni ejecución presupuestaria.")
    if not laboral and any([args.laboral_desde, args.laboral_hasta, args.fuentes_laborales, args.mostrar_navegador, args.laboral_evidencia]):
        parser.error("Las opciones laborales requieren --incluir-laboral o --solo-laboral.")
    if laboral and not args.laboral_evidencia and not (args.laboral_hasta or args.period):
        parser.error("Indique --laboral-hasta o --period para la extracción laboral.")
    if args.laboral_evidencia and any([args.laboral_desde, args.laboral_hasta, args.fuentes_laborales, args.mostrar_navegador]):
        parser.error("La reproducción usa las fechas y fuentes originales; no admite cambiar filtros.")
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Network and data validation finish before any delivered file is replaced.
        with tempfile.TemporaryDirectory(prefix="mtdh_build_", dir=args.output.parent) as temp:
            staged = Path(temp)
            result = None
            labor_result = None
            financial_result = None
            if not args.solo_laboral:
                result = build_dataset(args.excel, staged, args.period, period_source=args.period_source,
                                       execution_csv=args.ejecucion, current_sheet=args.sheet)
                if args.usuarios:
                    from src.etl_actualizacion import refresh_vis_vie
                    result = refresh_vis_vie(staged, args.usuarios, args.presupuesto, args.period, period_source=args.period_source)
                if args.financiero:
                    from src.etl_actualizacion import build_financial
                    financial_result = build_financial(args.financiero, staged, args.financiero_periodo, args.financiero_period_source)
            if laboral:
                from src.laboral import build_laboral, month
                if args.laboral_evidencia:
                    evidence = json.loads(args.laboral_evidencia.read_text(encoding="utf-8"))
                else:
                    from src.laboral_scraper import collect_laboral, DEFAULT_CONFIG
                    hasta = args.laboral_hasta or args.period
                    desde = args.laboral_desde or f"{month(hasta).year}-01"
                    print(f"Consultando fuentes oficiales laborales: {desde} a {hasta}...", file=sys.stderr, flush=True)
                    evidence = collect_laboral(desde, hasta, config=args.fuentes_laborales or DEFAULT_CONFIG,
                                               headed=args.mostrar_navegador)
                labor_result = build_laboral(evidence, staged)
            # Manifests are replaced last. Historical evidence and snapshots are retained.
            for path in sorted(staged.rglob("*"), key=lambda p: (p.name.startswith("manifest"), str(p))):
                if path.is_file():
                    target = args.output / path.relative_to(staged)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    path.replace(target)
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        print(f"Actualización no completada: {error}", file=sys.stderr)
        return 1
    summary = {"resultado": "Importación completa", "salida": str(args.output.resolve())}
    if result:
        summary.update({"corte": result["periodo_label"], "filas": result["filas"],
                        "beneficiarios_reportados": result["totales"]["beneficiarios"],
                        "usuarios_servicios": result["totales"]["usuarios_servicios"],
                        "unidades": result["totales"]["unidades"]})
    if labor_result:
        summary["laboral"] = {"filas": labor_result["filas"], "meses": labor_result["meses_contratos"],
                              "consulta_id": labor_result["consulta_id"], "reproduccion_sin_red": bool(args.laboral_evidencia)}
    if financial_result:
        summary["financiero"] = {"filas": financial_result["filas"], "periodo": financial_result["periodo"], **financial_result["totales"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

