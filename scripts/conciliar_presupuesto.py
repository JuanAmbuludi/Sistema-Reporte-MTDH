"""Read-only reconciliation of the three supplied workbooks and dashboard sources.

Run from the repository root with --acumulado, --territorial and --ejecucion.
The command prints its controls as JSON and never changes coverage or source files.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from src import finanzas
from src.data import load_data, load_periods
from src.etl import PROGRAMS, norm
from src.presupuesto_social import read_approved


def reconcile(acumulado: Path, territorial: Path, ejecucion: Path) -> dict:
    principal = pd.read_excel(acumulado, sheet_name="provincial", usecols="A:G")
    stored = pd.read_parquet(ROOT / "data/source/Acumulado_VIS_VIE/01_provincial.parquet")
    pd.testing.assert_frame_equal(principal, stored, check_exact=True)
    detail = pd.read_excel(territorial)
    old_detail = pd.read_parquet(ROOT / "data/source/Presupuesto_vis_vie.parquet")
    money_columns = ["total_devengado", "total_codificado", "presupuesto_devengado_corriente", "presupuesto_devengado_inversion",
                     "presupuesto_codificado_corriente", "presupuesto_codificado_inversion", "distribucion", "sumusuarios"]
    pd.testing.assert_frame_equal(detail[money_columns], old_detail[money_columns], check_exact=True)
    for key in ["id_provincia", "id_canton", "id_parroquia"]:
        assert pd.to_numeric(detail[key]).equals(pd.to_numeric(old_detail[key])), key
    assert detail.servicio.equals(old_detail.servicio)
    monthly, annual, control = read_approved(ejecucion)
    for new, name, keys in [(monthly, "presupuesto_social_mensual", ["periodo", "programa_id"]),
                            (annual, "presupuesto_social_asignado", ["periodo", "grupo_presupuestario"])]:
        stored = pd.read_parquet(ROOT / f"data/series/{name}.parquet")
        pd.testing.assert_frame_equal(new.sort_values(keys).reset_index(drop=True), stored.sort_values(keys).reset_index(drop=True))
    data, _ = load_periods()
    period = control["periodo_corte"]
    displayed = data.loc[data.periodo_id.eq(period)]
    prior = principal.assign(programa_id=principal.servicio.map(lambda s: PROGRAMS[norm(s)][0]))
    users = prior.groupby("programa_id").Usuarios.sum().rename("acumulado_vis_vie").to_frame()
    users["base_territorial"] = load_data().groupby("programa_id").usuarios.sum()
    users["dashboard_validado"] = displayed.groupby("programa_id").usuarios.sum()
    users["diferencia_dashboard_menos_acumulado"] = users.dashboard_validado - users.acumulado_vis_vie
    government = finanzas.load_government()
    fiscal, meta = finanzas.load_fiscal()
    totals = {key: str(sum(Decimal(str(v)) for v in fiscal[key]).quantize(Decimal("0.01"))) for key in finanzas.FISCAL_MEASURES}
    gov = {key: str(sum(Decimal(str(v)) for v in government[key]).quantize(Decimal("0.01"))) for key in finanzas.GOVERNMENT_MEASURES}
    gap = sum(Decimal(str(r.codificado))-Decimal(str(r.certificado))-Decimal(str(r.comprometido))-Decimal(str(r.saldo_disponible))
              for r in fiscal.itertuples())
    return {"periodo": period, "archivos": [{"archivo": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                                for p in [acumulado, territorial, ejecucion]],
            "controles": {"acumulado_identico_al_parquet": True, "territorial_importes_usuarios_y_claves_identicos": True,
                           "ejecucion_social_identica_al_parquet": True, "filas_acumulado": len(principal),
                           "filas_territorial": len(detail), "filas_fiscal_sgde": len(fiscal)},
            "gobierno": gov, "social": control, "fiscal_sgde": {"totales": totals, "fuente": meta["procedencia"],
                "porcentaje_ejecucion": float(fiscal.devengado.sum()/fiscal.codificado.sum()*100),
                "diferencia_codificado_menos_certificado_comprometido_y_disponible": str(gap.quantize(Decimal('0.01'))),
                "tratamiento_saldo": "Se conserva el saldo disponible publicado. La fuente no permite explicar la diferencia contable con las otras etapas."},
            "usuarios_por_programa": json.loads(users.reset_index().to_json(orient="records")),
            "cobertura": {"beneficiarios_dashboard": int(displayed.loc[displayed.seccion.eq('bonos_pensiones'), 'usuarios'].sum()),
                          "usuarios_servicios_dashboard": int(displayed.loc[displayed.seccion.eq('proteccion_integral'), 'usuarios'].sum()),
                          "unidades_dashboard": int(displayed.unidades.sum()), "modificada": False}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acumulado", type=Path, required=True)
    parser.add_argument("--territorial", type=Path, required=True)
    parser.add_argument("--ejecucion", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.acumulado, args.territorial, args.ejecucion), ensure_ascii=False, indent=2))
