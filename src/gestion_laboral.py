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
