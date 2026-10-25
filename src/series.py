"""Small public API for the historical Parquet tables, separate from territorial snapshots."""
from pathlib import Path
import pandas as pd

DEFAULT = Path(__file__).resolve().parents[1]/"data/series"


def load_series(name, *, start=None, end=None, root=DEFAULT):
    """Read a relative catalog name, optionally filtering YYYY-MM reference periods.

    Example: load_series('bonos_vie', start='2026-01', end='2026-09').
    ``load_data`` in src/data.py remains the provincial dashboard snapshot.
    """
    base = Path(root).resolve()
    path = (base/(name+".parquet")).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Seleccione una base del catálogo de series.")
    filters = []
    if start:
        filters.append(("periodo", ">=", start))
    if end:
        filters.append(("periodo", "<=", end))
    return pd.read_parquet(path, filters=filters or None)


def latest_contracts(dimension="canton", *, root=DEFAULT):
    """One published daily cut; it must never be summed across snapshot dates."""
    allowed = {"base","canton","rama","tipo","etnia","nac","act","empresas"}
    if dimension not in allowed:
        raise ValueError("Desagregación laboral no publicada.")
    frame = load_series("laboral/contratos_"+dimension, root=root)
    return frame.loc[frame.fecha_corte.eq(frame.fecha_corte.max())].copy()
