"""Territorial cleaning of the monthly series: codes whose names disagree, and bases that only carry names.

The Parquet series stay exactly as they were received; these rules apply when the dashboard reads them, so every
view and export draws the same territories.

1. **Codes with several names** (``codigo_ambiguo`` in the VIE series).  A row keeps its code when its names are
   those of the territory of that code, even written another way (``JIMA`` and ``GIMA``, ``LA CAROLINA`` and
   ``CAROLINA``).  When province, canton and parish name, without doubt, another territory of the political and
   administrative division, the row moves to that territory: the canton of Sevilla Don Bosco (1413) was recorded
   with the codes of Morona (1401, 140157) until April 2026, and single records carried the code of Morona
   Santiago with the names of other provinces.  When the names identify no other territory, the code stands.
2. **Bases without codes** (coverage of contingencies and natural or anthropic events) are located by name: the
   province, the canton within it and the parish within the canton.  Spelling variants of a name are recognised;
   an office written in the province column (``AZOGUEZ``, ``MILAGRO``) is resolved by its canton.

National totals never change: the rules only decide where a record is drawn.  :func:`cleaning_log` lists every
reassignment for the data documentation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data" / "series"
PROCESSED = ROOT / "data" / "processed"

PROVINCE_NAMES = {
    "01": "Azuay", "02": "Bolívar", "03": "Cañar", "04": "Carchi", "05": "Cotopaxi", "06": "Chimborazo", "07": "El Oro",
    "08": "Esmeraldas", "09": "Guayas", "10": "Imbabura", "11": "Loja", "12": "Los Ríos", "13": "Manabí",
    "14": "Morona Santiago", "15": "Napo", "16": "Pastaza", "17": "Pichincha", "18": "Tungurahua", "19": "Zamora Chinchipe",
    "20": "Galápagos", "21": "Sucumbíos", "22": "Orellana", "23": "Santo Domingo de los Tsáchilas", "24": "Santa Elena",
    "90": "Zona en estudio",
}
# Words written short in the sources.
_ABBREVIATIONS = {"STO": "SANTO", "STA": "SANTA", "FCO": "FRANCISCO", "GRAL": "GENERAL", "CRNEL": "CORONEL", "CRNL": "CORONEL",
                  "DR": "DOCTOR", "SN": "SAN", "PTO": "PUERTO"}
# Province column values that are not provinces: the canton column decides.
_NOT_PROVINCES = {"AZOGUEZ", "AZOGUES", "MILAGRO"}
_PROVINCE_ALIASES = {"SANTO DOMINGO": "23", "SANTO DOMINGO DE TSACHILAS": "23", "SANTO DOMINGO DE LOS TSACHILAS": "23",
                     "TSACHILAS": "23", "GALAPAGOS": "20"}
# Short or older canton names of the sources -> name of the canton in the division.
_CANTON_ALIASES = {"QUITO": "DISTRITO METROPOLITANO DE QUITO", "CHACO": "EL CHACO", "CONCORDIA": "LA CONCORDIA",
                   "COJIMIES": "PEDERNALES", "ECHANDIA": "ECHEANDIA", "CAMILO PONCE": "CAMILO PONCE ENRIQUEZ",
                   "CARLOS JULIO AROSEMENA": "CARLOS JULIO AROSEMENA TOLA", "FRANCISCO DE ORELLANA": "FRANCISCO DE ORELLANA",
                   "ORELLANA": "FRANCISCO DE ORELLANA", "BANOS": "BANOS DE AGUA SANTA", "YAGUACHI": "SAN JACINTO DE YAGUACHI",
                   "SAN JACINTO DE YAGUACHI": "SAN JACINTO DE YAGUACHI", "EL TRIUNFO": "EL TRIUNFO",
                   "VELASCO IBARRA": "EL EMPALME", "MONTALVO": "MONTALVO", "RIOVERDE": "RIO VERDE",
                   "GENERAL VILLAMIL": "PLAYAS", "BUCAY": "GENERAL ANTONIO ELIZALDE", "PULILI": "PUJILI", "PUYO": "PASTAZA",
                   "JIMBURA": "ESPINDOLA", "CHALTURA": "ANTONIO ANTE", "PINTAG": "DISTRITO METROPOLITANO DE QUITO",
                   "CALDERON": "PORTOVIEJO", "TARQUI": "MANTA", "NUEVA LOJA": "LAGO AGRIO", "MACAS": "MORONA",
                   "TENA": "TENA", "PUERTO BAQUERIZO MORENO": "SAN CRISTOBAL"}


def key(text: object) -> str:
    """Comparable form of a place name: capitals without accents, punctuation or repeated spaces."""
    if text is None or (isinstance(text, float) and text != text):
        return ""
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").upper()
    plain = re.sub(r"[_\-./,;:()'\"]", " ", plain)
    plain = re.sub(r"[^A-Z0-9 ]", "", plain)
    return " ".join(_ABBREVIATIONS.get(word, word) for word in plain.split())


def similar(a: str, b: str) -> float:
    """Closeness of two keys (0–1); one name inside the other reads as the same place."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def same_place(a: str, b: str, threshold: float = 0.84) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= 4 and (longer.startswith(shorter + " ") or longer.endswith(" " + shorter) or f" {shorter} " in f" {longer} "):
        return True
    return similar(a, b) >= threshold


@dataclass
class Gazetteer:
    """Codes and names of the political and administrative division as the series write them."""
    province_key: dict[str, str] = field(default_factory=dict)            # code -> key
    province_by_key: dict[str, str] = field(default_factory=dict)         # key -> code
    canton_key: dict[str, str] = field(default_factory=dict)              # code -> key
    canton_name: dict[str, str] = field(default_factory=dict)             # code -> display name
    cantons_of: dict[str, dict[str, str]] = field(default_factory=dict)   # province -> key -> code
    cantons_by_key: dict[str, list[str]] = field(default_factory=dict)    # key -> codes (whole country)
    parish_key: dict[str, str] = field(default_factory=dict)              # code -> key
    parish_name: dict[str, str] = field(default_factory=dict)             # code -> display name
    parishes_of: dict[str, dict[str, str]] = field(default_factory=dict)  # canton -> key -> code

    # ----------------------------------------------------------------------------------------- lookups
    def province(self, name: object) -> str | None:
        k = key(name)
        if not k or k in _NOT_PROVINCES:
            return None
        if k in _PROVINCE_ALIASES:
            return _PROVINCE_ALIASES[k]
        if k in self.province_by_key:
            return self.province_by_key[k]
        best = max(self.province_by_key, key=lambda candidate: similar(k, candidate), default=None)
        return self.province_by_key[best] if best and similar(k, best) >= 0.86 else None

    def _match(self, k: str, options: dict[str, str]) -> str | None:
        if not k or not options:
            return None
        if k in options:
            return options[k]
        contained = [code for candidate, code in options.items() if same_place(k, candidate, threshold=2.0)]
        if len(set(contained)) == 1:
            return contained[0]
        scored = sorted(((similar(k, candidate), code) for candidate, code in options.items()), reverse=True)
        if scored and scored[0][0] >= 0.84 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.04):
            return scored[0][1]
        return None

    def canton(self, province: str | None, name: object) -> str | None:
        """Canton code: within the province first, then the whole country when the name is unique."""
        k = key(name)
        k = _CANTON_ALIASES.get(k, k)
        if province:
            found = self._match(k, self.cantons_of.get(province, {}))
            if found:
                return found
        codes = self.cantons_by_key.get(k, [])
        if len(codes) == 1:
            return codes[0]
        # A canton recorded under another province (or an office) is found in the whole country when its name is unique.
        national = {candidate: code[0] for candidate, code in self.cantons_by_key.items() if len(code) == 1}
        contained = {code for candidate, code in national.items() if same_place(k, candidate, threshold=2.0)}
        if len(contained) == 1:
            return contained.pop()
        return self._match(k, national) if not province else None

    def parish(self, canton: str | None, name: object) -> str | None:
        if not canton:
            return None
        return self._match(key(name), self.parishes_of.get(canton, {}))

    def locate(self, province: object, canton: object = None, parish: object = None) -> tuple[str | None, str | None, str | None]:
        """Province, canton and parish codes of a place written by name (each ``None`` when it cannot be told)."""
        p = self.province(province)
        k = self.canton(p, canton) if canton is not None else None
        if k:
            p = k[:2]
        q = self.parish(k, parish) if parish is not None else None
        return p, k, q


def _mode(counter: Counter) -> str:
    return counter.most_common(1)[0][0] if counter else ""


@lru_cache(maxsize=1)
def gazetteer() -> Gazetteer:
    """Reference names from the rows of the VIE and VIS series whose codes carry one name, and the September detail."""
    frames = []
    for name in ("bonos_vie_territorial", "cobertura_vis_territorial"):
        path = SERIES / f"{name}.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path, columns=["nivel_territorial", "codigo_provincia", "provincia", "codigo_canton", "canton",
                                                         "codigo_parroquia", "parroquia", "codigo_ambiguo"]))
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    gaz = Gazetteer()
    if rows.empty:
        return gaz
    clean = rows.loc[~rows.codigo_ambiguo.astype(bool)]
    provinces: dict[str, Counter] = defaultdict(Counter)
    cantons: dict[str, Counter] = defaultdict(Counter)
    parishes: dict[str, Counter] = defaultdict(Counter)
    for row in clean.itertuples():
        if row.codigo_provincia:
            provinces[str(row.codigo_provincia)][key(row.provincia)] += 1
        if row.nivel_territorial in ("Cantón", "Parroquia") and row.codigo_canton:
            cantons[str(row.codigo_canton)][str(row.canton)] += 1
        if row.nivel_territorial == "Parroquia" and row.codigo_parroquia:
            parishes[str(row.codigo_parroquia)][str(row.parroquia)] += 1
    # Codes that only appear with several names take their most frequent name.
    for row in rows.loc[rows.codigo_ambiguo.astype(bool)].itertuples():
        if row.nivel_territorial == "Parroquia" and row.codigo_parroquia and str(row.codigo_parroquia) not in parishes:
            parishes.setdefault(f"~{row.codigo_parroquia}", Counter())[str(row.parroquia)] += 1
    for code, names in list(parishes.items()):
        if code.startswith("~"):
            parishes.pop(code)
            parishes.setdefault(code[1:], names)
    processed = PROCESSED / "cobertura_territorial.parquet"
    display_parish, display_canton = {}, {}
    if processed.exists():
        detail = pd.read_parquet(processed, columns=["canton_codigo", "canton", "parroquia_codigo", "parroquia"]).drop_duplicates()
        display_parish = dict(zip(detail.parroquia_codigo.astype(str), detail.parroquia.astype(str)))
        display_canton = dict(zip(detail.canton_codigo.astype(str), detail.canton.astype(str)))
    for code, names in provinces.items():
        gaz.province_key[code] = _mode(names)
        for name in names:
            gaz.province_by_key.setdefault(name, code)
    for code, names in sorted(cantons.items()):
        name = _mode(names)
        gaz.canton_key[code] = key(name)
        gaz.canton_name[code] = display_canton.get(code, name)
        gaz.cantons_of.setdefault(code[:2], {})[key(name)] = code
        gaz.cantons_by_key.setdefault(key(name), []).append(code)
    for code, names in sorted(parishes.items()):
        name = _mode(names)
        gaz.parish_key[code] = key(name)
        gaz.parish_name[code] = display_parish.get(code, name)
        gaz.parishes_of.setdefault(code[:4], {}).setdefault(key(name), code)
    return gaz


# --------------------------------------------------------------------------------------------- coded series
LEVEL_CODE = {"Provincia": "codigo_provincia", "Cantón": "codigo_canton", "Parroquia": "codigo_parroquia"}


def _target(gaz: Gazetteer, level: str, code: str, province: str, canton: str, parish: str) -> str:
    """Code a flagged row belongs to (its own code unless the names point, without doubt, to another territory)."""
    p_ok = same_place(key(province), gaz.province_key.get(code[:2], ""))
    if level == "Provincia":
        if p_ok:
            return code
        found = gaz.province(province)
        return found or code
    canton_code = code[:4]
    k_ok = same_place(key(canton), gaz.canton_key.get(canton_code, ""))
    if level == "Cantón":
        if p_ok and k_ok:
            return code
        p = gaz.province(province)
        found = gaz.canton(p, canton) if p else None
        return found or code
    q_ok = same_place(key(parish), gaz.parish_key.get(code, ""))
    if p_ok and k_ok and q_ok:
        return code
    p = gaz.province(province)
    k = gaz.canton(p, canton) if p else None
    found = gaz.parish(k, parish) if k else None
    return found or code


def clean_codes(frame: pd.DataFrame, measures: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Series rows with their territories settled, and the log of the rows that moved.

    Flagged rows get the code their names identify; every row takes the reference names of its code, so spelling
    variants add up as one territory.  Returns ``(clean, log)``.
    """
    gaz = gazetteer()
    out = frame.copy()
    log = []
    flagged = out.codigo_ambiguo.astype(bool) if "codigo_ambiguo" in out else pd.Series(False, index=out.index)
    if flagged.any():
        combos = out.loc[flagged, ["periodo", "nivel_territorial", "codigo_territorio", "provincia", "canton", "parroquia"]].drop_duplicates()
        targets = {}
        for row in combos.itertuples(index=False):
            targets[(row.nivel_territorial, row.codigo_territorio, row.provincia, row.canton, row.parroquia)] = _target(
                gaz, row.nivel_territorial, str(row.codigo_territorio), str(row.provincia or ""), str(row.canton or ""), str(row.parroquia or ""))
        keys = list(zip(out.nivel_territorial, out.codigo_territorio, out.provincia, out.canton, out.parroquia))
        new_codes = [targets.get(k, k[1]) if f else k[1] for k, f in zip(keys, flagged)]
        moved = [f and new != k[1] for k, new, f in zip(keys, new_codes, flagged)]
        if any(moved):
            subset = out.loc[moved]
            first = measures[0]
            for (period, level, old, province, canton, parish), group in subset.groupby(
                    ["periodo", "nivel_territorial", "codigo_territorio", "provincia", "canton", "parroquia"], dropna=False):
                new = targets[(level, old, province, canton, parish)]
                log.append({"periodo": period, "nivel_territorial": level, "codigo_origen": old, "codigo_destino": new,
                            "provincia": province, "canton": canton, "parroquia": parish, first: int(group[first].sum())})
        out["codigo_territorio"] = new_codes
    level = out.nivel_territorial
    code = out.codigo_territorio.astype(str)
    out["codigo_provincia"] = code.str[:2]
    out["codigo_canton"] = code.where(level.ne("Provincia")).str[:4]
    out["codigo_parroquia"] = code.where(level.eq("Parroquia"))
    out["provincia"] = out.codigo_provincia.map(PROVINCE_NAMES).fillna(out.provincia)
    out["canton"] = out.codigo_canton.map(gaz.canton_name).where(out.codigo_canton.notna()).fillna(out.canton.where(out.codigo_canton.notna()))
    out["parroquia"] = out.codigo_parroquia.map(gaz.parish_name).where(out.codigo_parroquia.notna()).fillna(
        out.parroquia.where(out.codigo_parroquia.notna()))
    dims = [c for c in out.columns if c not in measures and c != "codigo_ambiguo"]
    clean = out.groupby(dims, as_index=False, dropna=False, sort=False)[measures].sum()
    return clean, pd.DataFrame(log)


@lru_cache(maxsize=4)
def _cleaned(name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.read_parquet(SERIES / f"{name}.parquet")
    measures = [c for c in ("beneficiarios_unicos", "usuarios_unicos", "unidades_unicas", "registros") if c in frame]
    return clean_codes(frame, measures)


def cleaned_series(name: str) -> pd.DataFrame:
    """A territorial VIE or VIS series with its territories settled (a copy)."""
    return _cleaned(name)[0].copy()


def cleaning_log() -> pd.DataFrame:
    """Every row of the coded series that moved to another territory, for the data documentation."""
    logs = []
    for name in ("bonos_vie_territorial", "cobertura_vis_territorial"):
        if (SERIES / f"{name}.parquet").exists():
            log = _cleaned(name)[1]
            if not log.empty:
                logs.append(log.assign(serie=name))
    return pd.concat(logs, ignore_index=True) if logs else pd.DataFrame()


# ------------------------------------------------------------------------------------------ bases by name
def locate_frame(frame: pd.DataFrame, *, province: str = "provincia", canton: str = "canton", parish: str | None = None) -> pd.DataFrame:
    """Add ``provincia_codigo``, ``canton_codigo`` and ``parroquia_codigo`` to rows that only carry names."""
    gaz = gazetteer()
    columns = [province, canton] + ([parish] if parish else [])
    places = frame[columns].drop_duplicates()
    found = {}
    for row in places.itertuples(index=False):
        values = list(row)
        found[tuple(values)] = gaz.locate(values[0], values[1], values[2] if parish else None)
    codes = [found[tuple(values)] for values in frame[columns].itertuples(index=False, name=None)]
    out = frame.copy()
    out["provincia_codigo"] = [c[0] for c in codes]
    out["canton_codigo"] = [c[1] for c in codes]
    out["parroquia_codigo"] = [c[2] for c in codes]
    out["provincia_nombre"] = out.provincia_codigo.map(PROVINCE_NAMES)
    out["canton_nombre"] = out.canton_codigo.map(gaz.canton_name)
    out["parroquia_nombre"] = out.parroquia_codigo.map(gaz.parish_name)
    return out
