"""Independent, content-based publication dates for each dashboard area.

Re-saving a source, changing its compression, or running a query is not a data
revision. Source cuts, periods, values and definitions remain part of the hash.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "data/processed/actualizacion_secciones.json"
VOLATILE = {"generado_utc", "fecha_consulta_utc", "consulta_utc", "actualizado_utc",
            "fecha_procesamiento", "sha256", "evidencia_sha256", "archivo", "ruta",
            "procedencia", "fuente_archivo", "fuente_hoja", "fuente_fila"}


@dataclass(frozen=True)
class Source:
    path: str
    field: str = ""
    values: tuple[str, ...] = ()
    json_key: str = ""
    ordered: bool = False
    omit_json: tuple[str, ...] = ()


def _p(name: str, field: str = "", values=()) -> Source:
    return Source("data/processed/" + name, field, tuple(values))


def _s(name: str, field: str = "", values=()) -> Source:
    return Source("data/series/" + name, field, tuple(values))


TRANSFERS = ("BDH", "BDHV", "BJGL", "BMD", "MMA", "PTV", "PAM", "PCD")
CONTINGENCIES = ("ORFANDAD_VIOLENCIA", "CONTINGENCIAS", "ANTROPICOS", "COMPENSACION_GASOLINA",
                 "COMPENSACION_DIESEL", "MIGRANTES")


def _shared(section: str) -> list[Source]:
    return [_p(name, "seccion", (section,)) for name in
            ("indicadores.parquet", "historico_referencia.parquet", "cobertura_territorial.parquet", "presupuesto_territorial.parquet")]


SOURCES = {
    "transferencias": _shared("bonos_pensiones") + [_s("bonos_vie.parquet"), _s("bonos_vie_territorial.parquet"),
                        _s("presupuesto_social_mensual.parquet", "programa_id", TRANSFERS)],
    "servicios": _shared("proteccion_integral") + [_s("cobertura_vis.parquet"), _s("cobertura_vis_territorial.parquet"),
                                                   _s("cobertura_vis_administracion.parquet")],
    "contingencias": [_s(n + ".parquet") for n in ("beneficiarios_orfandad", "contingencias_mensuales", "contingencias_territorial",
                                                    "antropicos_mensuales", "antropicos_territorial")]
                     + [_s("incentivos_mensuales.parquet", "programa_id", CONTINGENCIES),
                        _s("presupuesto_social_mensual.parquet", "programa_id", CONTINGENCIES),
                        _s("presupuesto_social_asignado.parquet", "grupo_presupuestario", CONTINGENCIES)],
    "jovenes": [_s("jovenes_accion_fases.parquet"), _s("jovenes_accion_fase3.parquet"),
                 _s("incentivos_mensuales.parquet", "programa_id", ("JEA",)),
                 _s("presupuesto_social_mensual.parquet", "programa_id", ("JEA_F3",)),
                 _s("presupuesto_social_asignado.parquet", "grupo_presupuestario", ("JEA_F3",))],
    "jovenes_fase4": [Source("data/processed/jovenes_fase4.json", omit_json=("fuente",))],
    "presupuesto_social": [_s("presupuesto_social_mensual.parquet"), _s("presupuesto_social_asignado.parquet")],
    "presupuesto_fiscal": [_p("presupuesto_fiscal_2026-09.json")],
    "presupuesto_gobierno": [Source("data/source/Acumulado_VIS_VIE/01_provincial.parquet", ordered=True),
                              Source("data/processed/manifest.json", json_key="periodo")],
    "cdh": [_p("cdh_territorio.parquet"), _p("cdh_perfil.parquet"), _p("cdh_desembolsos_fechados.parquet"),
             Source("data/processed/cdh_brigadas.json", json_key="cdh", omit_json=("fuentes",))],
    "brigadas": [_p("brigadas.parquet"), Source("data/processed/cdh_brigadas.json", json_key="brigadas", omit_json=("fuentes",))],
    "ferias": [_p("ferias_participaciones.parquet"), _p("ferias_perfil.parquet"), _p("ferias.json")],
}


def _json_content(value, key=""):
    if isinstance(value, dict):
        return {field: _json_content(item, field) for field, item in value.items() if field not in VOLATILE}
    if isinstance(value, list):
        rows = [_json_content(item) for item in value]
        # Order of records is immaterial, but positions inside each record and
        # the order of column definitions still carry meaning.
        if key in {"pagos", "rechazos", "registros"}:
            rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True))
        return rows
    return value


def content_hash(content: bytes | None, source: Source) -> str:
    """Canonical values; row multiplicity is preserved and Parquet bytes are ignored."""
    if content is None:
        return "ausente"
    if source.path.endswith(".parquet"):
        frame = pd.read_parquet(BytesIO(content))
        if source.field:
            if source.field not in frame:
                raise ValueError(f"Falta {source.field} en {source.path}")
            frame = frame.loc[frame[source.field].isin(source.values)]
        columns = sorted(c for c in frame.columns if c not in VOLATILE)
        frame = frame[columns]
        # Two independent row hashes retain exact duplicates without expensive
        # object serialization of large territorial tables. SHA-256 seals the result.
        first = pd.util.hash_pandas_object(frame, index=False, hash_key="0123456789123456").to_numpy(dtype="uint64")
        second = pd.util.hash_pandas_object(frame, index=False, hash_key="9876543210987654").to_numpy(dtype="uint64")
        rows = np.column_stack((first, second))
        if not source.ordered and len(rows):
            rows = rows[np.lexsort((rows[:, 1], rows[:, 0]))]
        header = json.dumps(columns, ensure_ascii=False, separators=(",", ":")).encode()
        return sha256(header + rows.astype("<u8").tobytes()).hexdigest()
    value = json.loads(content)
    if source.json_key:
        for part in source.json_key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
    if isinstance(value, dict) and source.omit_json:
        value = {key: item for key, item in value.items() if key not in source.omit_json}
    canonical = json.dumps(_json_content(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()


@lru_cache(maxsize=512)
def _git_content(root: str, revision: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=root, capture_output=True)
    return result.stdout if result.returncode == 0 else None


def fingerprints(root: Path, sources: list[Source], revision: str | None = None) -> dict:
    out = {}
    for source in sources:
        path = root / source.path
        data = _git_content(str(root), revision, source.path) if revision else (path.read_bytes() if path.exists() else None)
        out[source.path] = content_hash(data, source)
    return out


def _digest(fingerprints_: dict) -> str:
    return sha256(json.dumps(fingerprints_, sort_keys=True).encode()).hexdigest()


def _utc(value: str) -> str:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("La fecha de revisión debe incluir zona horaria.")
    return moment.astimezone(timezone.utc).isoformat()


def first_revision(root: Path, sources: list[Source], current: dict, now: str) -> tuple[str | None, str]:
    """Recover the newest substantive Git revision, skipping metadata-only commits."""
    result = subprocess.run(["git", "log", "--format=%H %cI", "--", *[s.path for s in sources]],
                            cwd=root, capture_output=True, text=True)
    if result.returncode or not result.stdout.strip():
        return None, "Sin revisión histórica verificable"
    last = None
    for line in result.stdout.splitlines():
        commit, when = line.split(" ", 1)
        previous = fingerprints(root, sources, commit)
        if previous != current:
            return (last if last is not None else (now, "Cambio de datos en la publicación actual"))
        last = (_utc(when), commit)
    return last or (None, "Sin revisión histórica verificable")


def build(root: Path = ROOT, *, previous: dict | None = None, now: str | None = None,
          sources: dict[str, list[Source]] | None = None) -> dict:
    root = Path(root)
    path = root / REGISTRY
    if previous is None:
        previous = json.loads(path.read_text()) if path.exists() else {}
    now = _utc(now or datetime.now(timezone.utc).isoformat())
    areas = {}
    for area, specs in (sources or SOURCES).items():
        hashes = fingerprints(root, specs)
        digest = _digest(hashes)
        old = previous.get("areas", {}).get(area, {})
        if old.get("huella_datos") == digest:
            areas[area] = old
            continue
        if old:
            updated, origin = now, "Cambio de contenido de las fuentes"
        else:
            updated, origin = first_revision(root, specs, hashes, now)
        areas[area] = {"actualizado_utc": updated, "huella_datos": digest,
                       "origen_fecha": origin, "fuentes": hashes}
    return {"version": 1, "criterio": "Último cambio de contenido por sección; consulta y generación no alteran la fecha.", "areas": areas}


def update(root: Path = ROOT, *, now: str | None = None) -> tuple[dict, bool]:
    path = Path(root) / REGISTRY
    value = build(Path(root), now=now)
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    changed = not path.exists() or path.read_text(encoding="utf-8") != encoded
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    return value, changed
