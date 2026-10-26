"""Import the approved social budget without multiplying shared allocations."""
from pathlib import Path
import re
from decimal import Decimal

import pandas as pd
from openpyxl import load_workbook

from .historicos import MONTHS, money, norm, periods, sha256

PROGRAMS = {
    "BONO DE DESARROLLO HUMANO": "BDH",
    "BONO DE DESARROLLO HUMANO CON COMPONENTE VARIABLE": "BDHV",
    "BONO 1000 DIAS": "BMD",
    "PENSION MIS MEJORES ANOS": "MMA",
    "PENSION TODA UNA VIDA": "PTV",
    "BONO JOAQUIN GALLEGOS LARA": "BJGL",
    "BONO PARA NINOS, NINAS Y ADOLESCENTES EN SITUACION DE ORFANDAD POR MUERTE VIOLENTA DE LA MADRE O PROGENITORA.": "ORFANDAD_VIOLENCIA",
    "COBERTURA DE CONTINGENCIAS": "CONTINGENCIAS",
    "BONO PARA PERSONAS AFECTADAS POR EVENTOS DE ORIGEN NATURAL O ANTROPICO": "ANTROPICOS",
    "MECANISMO DE PROTECCION A LOS USUARIOS DEL TRANSPORTE": "COMPENSACION_GASOLINA",
    "MIGRANTES RETORNADOS": "MIGRANTES",
    "MECANISMO DE COMPENSACION DIESEL": "COMPENSACION_DIESEL",
    "COMISIONES BANCARIAS": "COMISIONES",
    'MECANISMO DE "JOVENES EN ACCION" - TERCER PERIODO': "JEA_F3",
}


def read_approved(path):
    book = load_workbook(path, data_only=True)
    try:
        sheet = book.active
        title = norm(sheet.cell(3, 1).value)
        match = re.fullmatch(r"([A-Z]+) (20\d{2})", title)
        if not match or match[1].lower() not in MONTHS:
            raise ValueError("El archivo aprobado debe documentar mes y año en su encabezado.")
        year, last_month = int(match[2]), MONTHS.index(match[1].lower()) + 1
        cut = f"{year}-{last_month:02d}"
        if [norm(sheet.cell(5, c).value).lower() for c in range(6, 18)] != MONTHS:
            raise ValueError("No se reconocen las doce columnas mensuales del presupuesto.")
        monthly, allocations = [], {}
        group = None
        source_totals = []
        for r in range(6, sheet.max_row+1):
            description = sheet.cell(r, 3).value
            if description is None:
                if norm(sheet.cell(r, 1).value).startswith("TOTAL"):
                    source_totals.append(r)
                continue
            key = norm(description)
            if key not in PROGRAMS:
                raise ValueError(f"Programa presupuestario sin homologar, fila {r}: {description}")
            pid = PROGRAMS[key]
            if sheet.cell(r, 2).value is not None:
                group = int(sheet.cell(r, 2).value)
            merged = next((rng for rng in sheet.merged_cells.ranges if rng.min_col == rng.max_col == 5 and rng.min_row <= r <= rng.max_row), None)
            owner = merged.min_row if merged else r
            member_rows = range(merged.min_row, merged.max_row+1) if merged else [r]
            members = [PROGRAMS[norm(sheet.cell(i, 3).value)] for i in member_rows]
            budget_group = "_".join(members)
            if budget_group not in allocations:
                approved = money(sheet.cell(owner, 5).value)
                if approved is None:
                    raise ValueError(f"Asignación vacía sin celda compartida: {description}")
                planned = sum(money(sheet.cell(i, 4).value) for i in member_rows)
                allocations[budget_group] = {"periodo": cut, "grupo_presupuestario": budget_group,
                    "programas": ", ".join(members), "grupo_gasto": group,
                    "planificado_anual": planned, "presupuesto_aprobado": approved}
            running = Decimal(0)
            for month in range(1, 13):
                value = sheet.cell(r, 5+month).value
                if month > last_month:
                    if value not in (None, 0):
                        raise ValueError("Hay ejecución posterior al corte declarado.")
                    continue
                if value is None:
                    raise ValueError(f"Devengado sin dato en fila {r}, mes {month}; no se imputa cero.")
                value = money(value)
                running += value
                monthly.append({"periodo": f"{year}-{month:02d}", "programa_id": pid,
                    "programa": str(description).strip(), "grupo_presupuestario": budget_group,
                    "grupo_gasto": group, "devengado_mes": value, "devengado_acumulado": running})
            if abs(running-money(sheet.cell(r, 18).value)) > Decimal("0.02"):
                raise ValueError(f"La suma mensual no concilia con TOTAL EJECUCIÓN, fila {r}.")
        if len(source_totals) != 1:
            raise ValueError("Se necesita una única fila TOTAL del presupuesto aprobado.")
        t = source_totals[0]
        expected = money(sheet.cell(t, 18).value)
        actual = sum(x["devengado_mes"] for x in monthly)
        if abs(expected-actual) > Decimal("0.05"):
            raise ValueError("Devengado total aprobado no concilia.")
        approved = sum(x["presupuesto_aprobado"] for x in allocations.values())
        planned = sum(x["planificado_anual"] for x in allocations.values())
        if abs(approved-money(sheet.cell(t, 5).value)) > Decimal("0.05") or abs(planned-money(sheet.cell(t, 4).value)) > Decimal("0.05"):
            raise ValueError("Asignaciones anuales no concilian con el total; revise celdas compartidas.")
        for m in range(1, last_month+1):
            observed = sum(x["devengado_mes"] for x in monthly if x["periodo"] == f"{year}-{m:02d}")
            if abs(observed-money(sheet.cell(t, 5+m).value)) > Decimal("0.05"):
                raise ValueError(f"Total del mes {m} no concilia.")
        return periods(pd.DataFrame(monthly)), periods(pd.DataFrame(allocations.values())), {
            "archivo": Path(path).name, "sha256": sha256(path), "periodo_corte": cut,
            "devengado_acumulado": str(actual), "presupuesto_aprobado": str(approved),
            "planificado_anual": str(planned), "totales_conciliados": True,
            "planificado_total_hoja": str(money(sheet.cell(t, 4).value)),
            "diferencia_redondeo_planificado": str(planned-money(sheet.cell(t, 4).value)),
            "asignaciones_compartidas": [k for k,v in allocations.items() if "," in v["programas"]],
            "universo": "Grupos de gasto 58, 57 y 78 del presupuesto social; no es todo el presupuesto institucional."}
    finally:
        book.close()


# ----------------------------------------------------------------------------------------------- dashboard reading
GROUP_NAMES = {
    "BDH_BDHV": "Bono de Desarrollo Humano (BDH y BDHV)", "BJGL": "Bono Joaquín Gallegos Lara", "BMD": "Bono 1.000 Días",
    "MMA": "Pensión Mis Mejores Años", "PTV": "Pensión Toda Una Vida", "ORFANDAD_VIOLENCIA": "Orfandad por femicidio",
    "CONTINGENCIAS": "Cobertura de contingencias", "ANTROPICOS": "Eventos naturales y antrópicos",
    "COMPENSACION_GASOLINA": "Compensación al transporte", "COMPENSACION_DIESEL": "Compensación diésel",
    "MIGRANTES": "Migrantes retornados", "JEA_F3": "Jóvenes en Acción (tercera fase)", "COMISIONES": "Comisiones bancarias",
}
SPENDING_GROUPS = {57: "Otros egresos corrientes", 58: "Transferencias o donaciones corrientes",
                   78: "Transferencias o donaciones para inversión"}
SERIES = Path(__file__).resolve().parents[1] / "data" / "series"


def load_social_budget() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Accrued budget of every month by budget group (programs that share an allocation add up), and the allocations.

    ``devengado_acumulado`` is a snapshot of the year (never added across months).  Execution of a group is its accrued
    budget over its approved budget.
    """
    monthly_path, annual_path = SERIES / "presupuesto_social_mensual.parquet", SERIES / "presupuesto_social_asignado.parquet"
    if not monthly_path.exists() or not annual_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    monthly = pd.read_parquet(monthly_path)
    for column in ["devengado_mes", "devengado_acumulado"]:
        monthly[column] = pd.to_numeric(monthly[column], errors="coerce").astype(float)
    groups = monthly.groupby(["periodo", "grupo_presupuestario", "grupo_gasto"], as_index=False)[["devengado_mes", "devengado_acumulado"]].sum()
    annual = pd.read_parquet(annual_path)
    for column in ["planificado_anual", "presupuesto_aprobado"]:
        annual[column] = pd.to_numeric(annual[column], errors="coerce").astype(float)
    annual = annual.loc[annual.periodo.eq(annual.periodo.max())]
    groups = groups.merge(annual[["grupo_presupuestario", "programas", "planificado_anual", "presupuesto_aprobado"]],
                          on="grupo_presupuestario", how="left")
    groups = groups.rename(columns={"periodo": "periodo_id"})
    groups["nombre"] = groups.grupo_presupuestario.map(GROUP_NAMES).fillna(groups.grupo_presupuestario)
    groups["grupo_gasto_nombre"] = groups.grupo_gasto.map(SPENDING_GROUPS)
    groups["porcentaje_ejecucion"] = groups.devengado_acumulado / groups.presupuesto_aprobado.where(groups.presupuesto_aprobado > 0) * 100
    groups["saldo"] = groups.presupuesto_aprobado - groups.devengado_acumulado
    programs = monthly.rename(columns={"periodo": "periodo_id"})
    return groups.sort_values(["periodo_id", "presupuesto_aprobado"], ascending=[True, False]).reset_index(drop=True), programs
