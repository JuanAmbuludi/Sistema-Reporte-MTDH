"""Labour management indicators for the dashboard and the exports: contracts and retirement compensation.

The base (``src/laboral.py`` builds it) keeps three kinds of figures that are never added together: the national
stock of contracts in force when the source was consulted, the contracts registered each month that remain in force,
and the annual balance of retirement compensation.  Here they are read, typed and described for an authority.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import DEFAULT_DATA_DIR, MONTHS

STOCK, MONTHLY = "contratos_vigentes_total", "contratos_del_mes_vigentes"
RETIREES, COMPENSATION = "jubilados_compensados", "compensaciones_jubilares_usd"
ECUADOR = ZoneInfo("America/Guayaquil")


def load_labour(data_dir: str | Path | None = None) -> pd.DataFrame:
    path = Path(data_dir or DEFAULT_DATA_DIR) / "gestion_laboral.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    frame["valor"] = pd.to_numeric(frame["valor"].astype(str), errors="coerce").astype(float)
    frame["periodo"] = pd.to_datetime(frame["periodo"], errors="coerce")
    return frame


def _long_date(moment: date) -> str:
    return f"{moment.day} de {MONTHS[moment.month - 1]} de {moment.year}"


def _source_date(text: object) -> date | None:
    """``22/10/2026 3:56:59`` (SUT update) or an ISO timestamp (publication) as a calendar date."""
    if not isinstance(text, str) or not text.strip():
        return None
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", text.strip())
    if match:
        return date(int(match[3]), int(match[2]), int(match[1]))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip()):
        return date.fromisoformat(text.strip())
    try:
        moment = datetime.fromisoformat(text.strip())
        return moment.astimezone(ECUADOR).date() if moment.tzinfo else moment.date()
    except ValueError:
        return None


def summary(frame: pd.DataFrame) -> dict:
    """Figures of the latest extraction, with their reference dates in words."""
    if frame.empty:
        return {}
    # Stock and monthly cohorts may come from different independently dated
    # sources; a fresh stock must not hide the retained monthly series.
    latest = frame.sort_values("fecha_consulta_utc").drop_duplicates(
        ["indicador_id", "periodo", "territorio"], keep="last")
    stock = latest.loc[latest.indicador_id.eq(STOCK)]
    monthly = latest.loc[latest.indicador_id.eq(MONTHLY)].sort_values("periodo")
    if len(monthly):
        monthly = monthly.loc[monthly.periodo.dt.year.eq(monthly.periodo.dt.year.max())]
    retirees = latest.loc[latest.indicador_id.eq(RETIREES)]
    compensation = latest.loc[latest.indicador_id.eq(COMPENSATION)]
    consulted = latest.fecha_consulta_utc.max().tz_convert(ECUADOR).date()
    stock_date = _source_date(stock.actualizacion_fuente.iloc[0]) if len(stock) else None
    cohorts_date = _source_date(monthly.actualizacion_fuente.iloc[-1]) if len(monthly) else None
    same_cut = bool(len(stock) and len(monthly) and stock_date == cohorts_date
                    and monthly.actualizacion_fuente.eq(stock.actualizacion_fuente.iloc[0]).all()
                    and monthly.fuente_id.eq(stock.fuente_id.iloc[0]).all())
    months = [{"period": p.date(), "id": p.strftime("%Y-%m"), "label": MONTHS[p.month - 1].capitalize(),
               "short": MONTHS[p.month - 1][:3].capitalize(), "value": float(v)}
              for p, v in zip(monthly.periodo, monthly.valor)]
    cohorts = sum(m["value"] for m in months) if months else None
    stock_value = float(stock.valor.iloc[0]) if len(stock) else None
    year = int(monthly.periodo.dt.year.max()) if len(monthly) else (int(retirees.anio.iloc[0]) if len(retirees) else consulted.year)
    published = _source_date(retirees.publicacion_fuente.iloc[0]) if len(retirees) else None
    retirement_cut = _source_date(retirees.actualizacion_fuente.iloc[0]) if len(retirees) else None
    return {
        "year": year,
        "consulted": consulted, "consulted_label": _long_date(consulted),
        "stock": stock_value, "stock_date": stock_date or consulted,
        "stock_label": _long_date(stock_date or consulted),
        "cohorts_date": cohorts_date, "cohorts_label": _long_date(cohorts_date or consulted),
        "same_cut": same_cut,
        "months": months, "cohorts": cohorts,
        "cohorts_share": cohorts / stock_value * 100 if cohorts and stock_value and same_cut else None,
        "average": cohorts / len(months) if months else None,
        "first_month": months[0]["label"].lower() if months else None, "last_month": months[-1]["label"].lower() if months else None,
        "retirees": float(retirees.valor.iloc[0]) if len(retirees) else None,
        "retirees_unit": str(retirees.unidad.iloc[0]) if len(retirees) else "personas",
        "retirement_cut": _long_date(retirement_cut) if retirement_cut else None,
        "retirees_year": int(retirees.anio.iloc[0]) if len(retirees) and pd.notna(retirees.anio.iloc[0]) else year,
        "compensation": float(compensation.valor.iloc[0]) if len(compensation) else None,
        "compensation_lower_bound": bool(len(compensation) and compensation.operador.iloc[0] == ">"),
        "published": published, "published_label": _long_date(published) if published else None,
        "sources": sorted({(r.fuente_id, r.fuente_url) for r in latest.itertuples()}),
    }


def catalog(frame: pd.DataFrame) -> list[dict]:
    """The labour figures form one annual view (monthly registrations within it)."""
    info = summary(frame)
    if not info:
        return []
    return [{"id": str(info["year"]), "year": info["year"], "month": None, "label": f"Año {info['year']}",
             "months": [m["id"] for m in info["months"]]}]


def month_span(info: dict) -> str:
    """``enero a septiembre`` (or one month)."""
    if not info.get("months"):
        return ""
    first, last = info["first_month"], info["last_month"]
    return first if first == last else f"{first} a {last}"


# ------------------------------------------------------------------------------------------------- SGDE daily cut
# The published tabulations of contracts (SGDE) are a stock at the date and hour of their cut: contracts in force and
# ended by state, sex, age group, disability, province and canton, and parallel tables by branch of activity, type of
# contract, ethnicity, foreign nationality and distinct companies.  Tables are never joined row by row; each answers
# its own question.  Retirement compensation is published by year (2023 to the current year) and by province, regime
# and sex; each dimension repeats the total of the year.
SGDE = Path(__file__).resolve().parents[1] / "data" / "series" / "laboral"
DIMENSIONS = {"base": None, "canton": "canton", "rama": "rama_actividad", "tipo": "tipo_contrato", "etnia": "etnia",
              "nac": "nacionalidad", "act": "actividad", "empresas": None}


def _sgde(name: str) -> pd.DataFrame:
    path = SGDE / f"contratos_{name}.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    return frame.loc[frame.fecha_corte.eq(frame.fecha_corte.max())].copy()


def _province_code(name: object) -> str | None:
    from src import depuracion
    if not isinstance(name, str) or name in ("Sin provincia", "TOTAL"):
        return None
    return depuracion.gazetteer().province(name)


_TABLES: dict[str, pd.DataFrame] = {}


def contracts(name: str) -> pd.DataFrame:
    """Latest cut of a contract tabulation, with the DPA code of its province (and canton)."""
    if name not in _TABLES:
        frame = _sgde(name)
        if not frame.empty and "provincia" in frame:
            codes = {p: _province_code(p) for p in frame.provincia.unique()}
            frame["provincia_codigo"] = frame.provincia.map(codes)
            if name == "canton":
                from src import depuracion
                gaz = depuracion.gazetteer()
                pairs = {(p, c): gaz.canton(codes.get(p), c) for p, c in frame[["provincia", "canton"]].drop_duplicates().itertuples(index=False)}
                frame["canton_codigo"] = [pairs[(p, c)] for p, c in zip(frame.provincia, frame.canton)]
        _TABLES[name] = frame
    return _TABLES[name]


def retirement_table() -> pd.DataFrame:
    path = SGDE / "jubilados.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    frame = frame.loc[frame.fecha_corte.eq(frame.fecha_corte.max())].copy()
    frame["monto"] = pd.to_numeric(frame.monto_usd, errors="coerce").astype(float)
    frame["provincia_codigo"] = frame.codigo.where(frame.dimension.eq("provincia") & frame.codigo.ne(""), None)
    return frame


def sgde_cut() -> dict:
    """Date and hour of the latest published cut of contracts and of retirement compensation."""
    from src import corte
    base = contracts("base")
    retirement = retirement_table()
    cut = corte.labour_cut()
    retirement_cut = pd.Timestamp(retirement.fecha_corte.iloc[0]).date() if not retirement.empty else None
    return {"contracts": cut, "contracts_label": corte.long_date(cut) if cut else "",
            "contracts_date": _long_date(cut.date()) if cut else "",
            "retirement": retirement_cut, "retirement_label": _long_date(retirement_cut) if retirement_cut else "",
            "has_contracts": not base.empty}


def stock(provinces=None, state: str = "Vigente") -> dict:
    """Contracts of a state (and the registered total) of the country or of the chosen provinces."""
    base = contracts("base")
    if base.empty:
        return {}
    rows = base.loc[base.provincia_codigo.isin(provinces)] if provinces else base
    by_state = rows.groupby("estado").contratos.sum()
    companies = contracts("empresas")
    if provinces:
        firms = companies.loc[companies.estado.eq(state) & companies.provincia_codigo.isin(provinces)].empresas
        firms_total = int(firms.sum()) if len(firms) else None
    else:
        total = companies.loc[companies.estado.eq(state) & companies.provincia.eq("TOTAL")].empresas
        firms_total = int(total.iloc[0]) if len(total) else None
    return {"vigentes": int(by_state.get("Vigente", 0)), "finalizados": int(by_state.get("Finalizado", 0)),
            "registrados": int(by_state.sum()), "empresas": firms_total}


def by_territory(level: str = "provincia", provinces=None, state: str = "Vigente") -> pd.DataFrame:
    """Contracts of a state by province or canton, largest first, with the share of the selection."""
    table = contracts("canton" if level == "canton" else "base")
    if table.empty:
        return pd.DataFrame()
    rows = table.loc[table.estado.eq(state)]
    if provinces:
        rows = rows.loc[rows.provincia_codigo.isin(provinces)]
    keys = ["provincia", "provincia_codigo"] + (["canton", "canton_codigo"] if level == "canton" else [])
    out = rows.groupby(keys, as_index=False, dropna=False).contratos.sum()
    total = out.contratos.sum()
    out["participacion"] = out.contratos / total * 100 if total else 0.0
    out["nombre"] = out.canton if level == "canton" else out.provincia
    out["detalle"] = [f"{c} · {p}" for c, p in zip(out.canton, out.provincia)] if level == "canton" else out.provincia
    return out.sort_values("contratos", ascending=False).reset_index(drop=True)


def by_dimension(name: str, column: str, provinces=None, state: str = "Vigente", top: int | None = None) -> pd.DataFrame:
    """Contracts of a state by one published dimension (branch, type, ethnicity, nationality, sex, age, disability)."""
    table = contracts(name)
    if table.empty:
        return pd.DataFrame(columns=[column, "contratos", "participacion"])
    rows = table.loc[table.estado.eq(state)]
    if provinces:
        rows = rows.loc[rows.provincia_codigo.isin(provinces)]
    out = rows.groupby(column, as_index=False).contratos.sum().sort_values("contratos", ascending=False)
    total = out.contratos.sum()
    out["participacion"] = out.contratos / total * 100 if total else 0.0
    out = out.reset_index(drop=True)
    return out.head(top) if top else out


def companies_by_province(state: str = "Vigente", provinces=None) -> pd.DataFrame:
    table = contracts("empresas")
    if table.empty:
        return pd.DataFrame()
    rows = table.loc[table.estado.eq(state) & table.provincia_codigo.notna()]
    if provinces:
        rows = rows.loc[rows.provincia_codigo.isin(provinces)]
    return rows[["provincia", "provincia_codigo", "empresas"]].sort_values("empresas", ascending=False).reset_index(drop=True)


def retirement_years(provinces=None) -> pd.DataFrame:
    """Files and amount of retirement compensation of every published year (the current year to its cut)."""
    table = retirement_table()
    if table.empty:
        return pd.DataFrame()
    if provinces:
        rows = table.loc[table.dimension.eq("provincia") & table.provincia_codigo.isin(provinces)]
        out = rows.groupby(["anio", "parcial", "mes_fin"], as_index=False)[["expedientes", "monto"]].sum()
    else:
        out = table.loc[table.dimension.eq("total"), ["anio", "parcial", "mes_fin", "expedientes", "monto"]]
    out = out.sort_values("anio").reset_index(drop=True)
    out["promedio"] = out.monto / out.expedientes.where(out.expedientes > 0)
    return out


def retirement_by(dimension: str, year: int, provinces=None) -> pd.DataFrame:
    """Files and amount of a year by province, regime or sex."""
    table = retirement_table()
    if table.empty:
        return pd.DataFrame()
    rows = table.loc[table.dimension.eq(dimension) & table.anio.eq(year)]
    if provinces and dimension == "provincia":
        rows = rows.loc[rows.provincia_codigo.isin(provinces)]
    out = rows[["categoria", "provincia_codigo", "expedientes", "monto"]].sort_values("expedientes", ascending=False).reset_index(drop=True)
    total = out.expedientes.sum()
    out["participacion"] = out.expedientes / total * 100 if total else 0.0
    return out
