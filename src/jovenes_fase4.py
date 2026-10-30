"""Independent fourth-period JEA payment monitor; no invented calendar period."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

import pandas as pd

PATH = Path(__file__).resolve().parents[1] / "data/processed/jovenes_fase4.json"
PAYMENT_COLUMNS = ["entidad", "seleccionados", "autorizados", "monto_autorizado", "acreditadas",
                   "monto_acreditado", "no_acreditadas", "monto_no_acreditado"]
REJECTION_COLUMNS = ["entidad", "codigo_rechazo", "motivo", "transferencias"]
RATE_FIELDS = {"tasa_autorizacion": ("autorizados", "seleccionados"),
               "tasa_acreditacion": ("acreditadas", "autorizados"),
               "tasa_no_acreditacion": ("no_acreditadas", "autorizados")}
ENTITY_NAMES = {
    "MIT": "Ministerio de Infraestructura y Tecnología",
    "MINEDEC": "Ministerio de Educación, Deporte y Cultura",
    "MSP": "Ministerio de Salud Pública",
    "SNGR": "Secretaría Nacional de Gestión de Riesgos",
    "MAE": "Ministerio de Ambiente y Energía",
    "MDEP": "Ministerio de Desarrollo Económico y Productivo",
    "MDG": "Ministerio de Gobierno",
}


def entity_name(code: str) -> str:
    """Display names; source codes remain stable identifiers for filtering."""
    return ENTITY_NAMES.get(code, code)


def display_entities(frame: pd.DataFrame) -> pd.DataFrame:
    """Expand institution labels on a copy without changing source identifiers."""
    result = frame.copy()
    result["entidad"] = result.entidad.map(entity_name)
    return result


@lru_cache(maxsize=4)
def _read(path: str, modified: int, size: int) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load() -> dict:
    if not PATH.exists():
        return {}
    stat = PATH.stat()
    return deepcopy(_read(str(PATH), stat.st_mtime_ns, stat.st_size))


def metadata() -> dict:
    """Source scope, traceability and reconciliation controls without detail arrays."""
    return {key: value for key, value in load().items() if key not in ("pagos", "rechazos", "totales")}


manifest = metadata


def _select(frame: pd.DataFrame, entities=None) -> pd.DataFrame:
    if entities is None:
        return frame.copy()
    selected = [entities] if isinstance(entities, str) else list(entities)
    return frame.loc[frame.entidad.isin(selected)].copy().reset_index(drop=True)


def _rates(frame: pd.DataFrame) -> pd.DataFrame:
    for rate, (numerator, denominator) in RATE_FIELDS.items():
        frame[rate] = frame[numerator].div(frame[denominator].where(frame[denominator].gt(0))) * 100
    return frame


def payments(entidades=None) -> pd.DataFrame:
    """One row per executing entity; rates are percentages from 0 to 100."""
    rows = pd.DataFrame(load().get("pagos", []), columns=PAYMENT_COLUMNS)
    return _rates(_select(rows, entidades))


def rejections(entidades=None) -> pd.DataFrame:
    """Source counts by executing entity and rejection code, including observed zeros."""
    rows = pd.DataFrame(load().get("rechazos", []), columns=REJECTION_COLUMNS)
    return _select(rows, entidades)


def entities() -> list[str]:
    return payments().entidad.tolist()


def summary(entidades=None) -> dict:
    """Aggregate the selected entities and recompute each rate from its denominator."""
    rows = payments(entidades)
    result = {field: float(rows[field].sum()) if field.startswith("monto_") else int(rows[field].sum())
              for field in PAYMENT_COLUMNS if field != "entidad"}
    result.update(entidades=len(rows), sin_autorizacion=result["seleccionados"] - result["autorizados"])
    for rate, (numerator, denominator) in RATE_FIELDS.items():
        result[rate] = result[numerator] / result[denominator] * 100 if result[denominator] else None
    return result


def select(entidades=None) -> dict:
    """Both panels share exactly the same executing-entity selection."""
    return {"pagos": payments(entidades), "rechazos": rejections(entidades),
            "resumen": summary(entidades), "metadata": metadata()}
