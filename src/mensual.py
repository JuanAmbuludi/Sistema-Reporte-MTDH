"""Monthly coverage of transfers (VIE) and services (VIS) by province, canton and parish, and the monthly budget.

Every month of the series (January to the latest cut) is read from the monthly tabulations, settled territorially
(:mod:`src.depuracion`), so months compare like for like: beneficiaries and users are the unique people of each
program, service modality and territory; units of attention are the distinct units.  The September operational base
(``data/processed``) contributes what only it has: the budget by province and parish and the accumulated budget of
2023–2025.  The approved social budget gives the accrued budget of each transfer program for every month.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from src import depuracion

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data" / "series"
PROCESSED = ROOT / "data" / "processed"

# Bono of the VIE series -> program of the dashboard.  The pension for minors belongs to Pensión Toda Una Vida, as
# in its budget.
TRANSFER_PROGRAMS = {"BDH": "BDH", "BDHV": "BDHV", "BJGL": "BJGL", "BMD": "BMD", "MMA": "MMA", "PTV": "PTV", "PTV_MENORES": "PTV"}
SERVICE_PROGRAMS = {"DESARROLLO INFANTIL INTEGRAL": "DII", "PERSONAS ADULTOS MAYORES - PEJ": "PAM_SERV",
                    "PERSONAS CON DISCAPACIDAD": "PCD_SERV", "PROTECCION ESPECIAL": "PE"}
PROGRAM_NAMES = {
    "BDH": "Bono de Desarrollo Humano", "BDHV": "Bono de Desarrollo Humano Variable", "BJGL": "Bono Joaquín Gallegos Lara",
    "BMD": "Bono 1.000 Días", "MMA": "Pensión Mis Mejores Años", "PTV": "Pensión Toda Una Vida",
    "DII": "Desarrollo Infantil Integral", "PAM_SERV": "Personas adultas mayores", "PCD_SERV": "Personas con discapacidad",
    "PE": "Protección Especial",
}
SECTION = {"BDH": "bonos_pensiones", "BDHV": "bonos_pensiones", "BJGL": "bonos_pensiones", "BMD": "bonos_pensiones",
           "MMA": "bonos_pensiones", "PTV": "bonos_pensiones", "DII": "proteccion_integral", "PAM_SERV": "proteccion_integral",
           "PCD_SERV": "proteccion_integral", "PE": "proteccion_integral"}
LEVEL = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}


def _program_names() -> dict[str, str]:
    """Program names as the September base writes them (the dashboard and documents keep them)."""
    names = dict(PROGRAM_NAMES)
    path = PROCESSED / "indicadores.parquet"
    if path.exists():
        rows = pd.read_parquet(path, columns=["programa_id", "programa"]).drop_duplicates("programa_id")
        names.update(dict(zip(rows.programa_id.astype(str), rows.programa.astype(str))))
    return names


@lru_cache(maxsize=1)
def coverage() -> pd.DataFrame:
    """Coverage of every month, program and territory at the three levels (one table per level, never added).

    Columns: ``periodo_id``, ``nivel`` (provincia, canton, parroquia), ``seccion``, ``programa_id``, ``programa``,
    ``provincia_codigo``, ``provincia``, ``canton_codigo``, ``canton``, ``parroquia_codigo``, ``parroquia``,
    ``usuarios`` and ``unidades`` (services).
    """
    names = _program_names()
    frames = []
    for series, column, mapping, people, units in [
        ("bonos_vie_territorial", "bono", TRANSFER_PROGRAMS, "beneficiarios_unicos", None),
        ("cobertura_vis_territorial", "servicio", SERVICE_PROGRAMS, "usuarios_unicos", "unidades_unicas"),
    ]:
        if not (SERIES / f"{series}.parquet").exists():
            continue
        rows = depuracion.cleaned_series(series)
        rows = rows.assign(programa_id=rows[column].map(mapping))
        rows = rows.loc[rows.programa_id.notna()]
        metrics = {"usuarios": rows[people].astype(float)}
        metrics["unidades"] = rows[units].astype(float) if units else float("nan")
        rows = rows.assign(**metrics)
        keys = ["periodo", "nivel_territorial", "programa_id", "codigo_provincia", "provincia", "codigo_canton", "canton",
                "codigo_parroquia", "parroquia"]
        grouped = rows.groupby(keys, as_index=False, dropna=False)[["usuarios", "unidades"]].sum(min_count=1)
        frames.append(grouped)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    inverse = {v: k for k, v in LEVEL.items()}
    out = out.rename(columns={"periodo": "periodo_id", "codigo_provincia": "provincia_codigo", "codigo_canton": "canton_codigo",
                              "codigo_parroquia": "parroquia_codigo"})
    out["nivel"] = out.pop("nivel_territorial").map(inverse)
    out["seccion"] = out.programa_id.map(SECTION)
    out["programa"] = out.programa_id.map(names)
    for col in ["provincia_codigo", "canton_codigo", "parroquia_codigo", "canton", "parroquia"]:
        out[col] = out[col].astype(object).where(out[col].notna(), None)
    return out


def months() -> list[str]:
    """Months of the coverage series, oldest first (``2026-01`` …)."""
    frame = coverage()
    return sorted(frame.periodo_id.unique()) if not frame.empty else []


@lru_cache(maxsize=1)
def program_budget() -> pd.DataFrame:
    """Accrued budget of each transfer program for every month, with its coded budget and earlier accumulation.

    ``devengado_mes`` and ``devengado_acumulado`` come from the approved social budget (the accumulated figure is a
    snapshot of the year: it is never added across months).  ``presupuesto_codificado`` and ``monto_anterior``
    (2023–2025) come from the September base, which carries them by program; the coded budget of the latest cut is
    the reference of the execution of every month.
    """
    path = SERIES / "presupuesto_social_mensual.parquet"
    base = PROCESSED / "indicadores.parquet"
    if not path.exists() or not base.exists():
        return pd.DataFrame()
    social = pd.read_parquet(path)
    social = social.loc[social.programa_id.isin(set(TRANSFER_PROGRAMS.values()))]
    for col in ["devengado_mes", "devengado_acumulado"]:
        social[col] = pd.to_numeric(social[col], errors="coerce").astype(float)
    reference = pd.read_parquet(base)
    reference = reference.loc[reference.seccion.eq("bonos_pensiones")]
    for col in ["presupuesto_codificado", "monto_anterior"]:
        reference[col] = pd.to_numeric(reference[col], errors="coerce").astype(float)
    by_program = reference.groupby("programa_id", as_index=False)[["presupuesto_codificado", "monto_anterior"]].sum(min_count=1)
    out = social[["periodo", "programa_id", "devengado_mes", "devengado_acumulado"]].merge(by_program, on="programa_id", how="left")
    out = out.rename(columns={"periodo": "periodo_id"})
    out["programa"] = out.programa_id.map(_program_names())
    out["porcentaje_ejecucion"] = out.devengado_acumulado / out.presupuesto_codificado.where(out.presupuesto_codificado > 0) * 100
    out["monto_gobierno"] = out.monto_anterior + out.devengado_acumulado
    return out.sort_values(["periodo_id", "programa_id"]).reset_index(drop=True)


def province_rows(processed: pd.DataFrame) -> pd.DataFrame:
    """Rows by month, program and province in the shape of the dashboard base.

    Months of the series take their coverage from it; the latest cut of the September base keeps its budget columns
    (and programs that only carry an earlier accumulation).  Months without a territorial budget leave it empty.
    """
    cover = coverage()
    if cover.empty:
        return processed
    provinces = cover.loc[cover.nivel.eq("provincia")]
    people = provinces.groupby(["periodo_id", "seccion", "programa_id", "programa", "provincia_codigo", "provincia"],
                               as_index=False, dropna=False)[["usuarios", "unidades"]].sum(min_count=1)
    rows = []
    processed_periods = set(processed.periodo_id.unique()) if not processed.empty else set()
    for period_id, group in people.groupby("periodo_id"):
        if period_id in processed_periods:
            base = processed.loc[processed.periodo_id.eq(period_id)].drop(columns=["usuarios", "unidades"])
            merged = base.merge(group[["programa_id", "provincia_codigo", "usuarios", "unidades"]], on=["programa_id", "provincia_codigo"],
                                how="outer", indicator=True)
            extra = merged._merge.eq("right_only")
            if extra.any():
                # A province of the series that the September base does not list keeps its coverage without budget.
                fill = group.set_index(["programa_id", "provincia_codigo"])
                for col in ["seccion", "programa", "provincia"]:
                    merged.loc[extra, col] = [fill.loc[(p, c), col] for p, c in zip(merged.loc[extra, "programa_id"],
                                                                                  merged.loc[extra, "provincia_codigo"])]
                for col in ["periodo", "anio", "periodo_anio", "periodo_mes"]:
                    merged.loc[extra, col] = base[col].iloc[0]
                merged.loc[extra, "periodo_id"] = period_id
            merged = merged.drop(columns="_merge")
            merged["usuarios"] = merged.usuarios.fillna(0)
            rows.append(merged)
        else:
            year, month = map(int, period_id.split("-"))
            frame = group.assign(periodo=pd.Timestamp(year=year, month=month, day=1), anio=year, periodo_anio=year, periodo_mes=month,
                                 monto_fiscal=float("nan"), monto_gobierno=float("nan"), monto_anterior=float("nan"),
                                 presupuesto_ejecutado=float("nan"), presupuesto_codificado=float("nan"))
            rows.append(frame)
    current = pd.concat(rows, ignore_index=True)
    others = processed.loc[~processed.periodo_id.isin(set(people.periodo_id))] if not processed.empty else processed
    return pd.concat([current, others], ignore_index=True) if not others.empty else current


def parish_rows(budget: pd.DataFrame | None = None) -> pd.DataFrame:
    """Rows by month, program and parish (the shape of :func:`src.data.load_territory`), with the parish budget of the
    cuts that have it.  Budget rows of a parish without coverage in the month are kept, so no amount is lost."""
    cover = coverage()
    if cover.empty:
        return pd.DataFrame()
    parishes = cover.loc[cover.nivel.eq("parroquia")].drop(columns=["nivel"])
    keys = ["periodo_id", "seccion", "programa_id", "programa", "provincia_codigo", "provincia", "canton_codigo", "canton",
            "parroquia_codigo", "parroquia"]
    frame = parishes.groupby(keys, as_index=False, dropna=False)[["usuarios", "unidades"]].sum(min_count=1)
    if budget is not None and not budget.empty:
        amounts = budget.groupby(["periodo_id", "programa_id", "parroquia_codigo"], as_index=False)[
            ["presupuesto_ejecutado", "presupuesto_codificado"]].sum(min_count=1)
        frame = frame.merge(amounts, on=["periodo_id", "programa_id", "parroquia_codigo"], how="outer", indicator=True)
        orphan = frame._merge.eq("right_only")
        if orphan.any():
            gaz = depuracion.gazetteer()
            names = _program_names()
            frame.loc[orphan, "seccion"] = frame.loc[orphan, "programa_id"].map(SECTION)
            frame.loc[orphan, "programa"] = frame.loc[orphan, "programa_id"].map(names)
            codes = frame.loc[orphan, "parroquia_codigo"].astype(str)
            frame.loc[orphan, "provincia_codigo"] = codes.str[:2]
            frame.loc[orphan, "provincia"] = codes.str[:2].map(depuracion.PROVINCE_NAMES)
            frame.loc[orphan, "canton_codigo"] = codes.str[:4]
            frame.loc[orphan, "canton"] = codes.str[:4].map(gaz.canton_name)
            frame.loc[orphan, "parroquia"] = codes.map(gaz.parish_name)
            frame.loc[orphan, "usuarios"] = 0.0
        frame = frame.drop(columns="_merge")
    for col in ["presupuesto_ejecutado", "presupuesto_codificado"]:
        if col not in frame:
            frame[col] = float("nan")
    for col in keys:
        frame[col] = frame[col].astype(str)
    return frame
