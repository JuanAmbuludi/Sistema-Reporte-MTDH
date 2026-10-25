"""Compact public aggregates and idempotent updates of complete monthly partitions.

Nominal inputs are processed locally; identifiers never leave this module's inputs.
Dates of habilitation, accreditation and budget execution are different measures.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import hashlib
import re
import unicodedata

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

MONTHS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
MONEY = pa.decimal128(22, 2)


def norm(value):
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()).strip().upper()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path, **kwargs):
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin1", **kwargs)


def periods(frame, column="periodo"):
    out = frame.copy()
    values = pd.to_datetime(out[column], errors="raise")
    if values.isna().any():
        raise ValueError("Un periodo mensual no puede estar vacío.")
    out["periodo"] = values.dt.strftime("%Y-%m")
    out["anio"] = values.dt.year.astype("int16")
    out["mes"] = values.dt.month.astype("int8")
    out["mes_nombre"] = out.mes.map(lambda x: MONTHS[x-1])
    return out[["periodo", "anio", "mes", "mes_nombre", *[c for c in out if c not in {"periodo", "anio", "mes", "mes_nombre"}]]]


def money(value):
    if value is None or pd.isna(value):
        return None
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not amount.is_finite():
        raise ValueError("Monto no finito.")
    return amount


def write_parquet(frame, path, *, keys=None, money_columns=(), note=""):
    path = Path(path)
    if keys:
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            raise ValueError(f"Clave incompleta o repetida en {path.name}: {keys}")
        frame = frame.sort_values(keys, kind="stable").reset_index(drop=True)
    arrays = {}
    for column in frame:
        if column in money_columns:
            arrays[column] = pa.array([money(v) for v in frame[column]], type=MONEY)
        else:
            arrays[column] = pa.array(frame[column], from_pandas=True)
    table = pa.table(arrays).replace_schema_metadata({b"mtdh.grain": "/".join(keys or []).encode(),
                                                     b"mtdh.definition": note.encode()})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd", compression_level=9, use_dictionary=True)
    temporary.replace(path)


def upsert_partitions(old, new, *, keys, partitions, replace_partitions=None):
    """A correction replaces complete supplied partitions; never adds two versions.

    Empty corrected partitions require an explicit replacement list. Callers stage
    the entire batch before publishing, so validation failure preserves old files.
    """
    for data in [old, new]:
        if not data.empty and (data[keys].isna().any().any() or data.duplicated(keys).any()):
            raise ValueError(f"Claves inválidas: {keys}")
    replacements = set(map(tuple, new[partitions].itertuples(index=False, name=None)))
    replacements.update(tuple(v) for v in (replace_partitions or []))
    if not old.empty:
        keep = [tuple(row) not in replacements for row in old[partitions].itertuples(index=False, name=None)]
        old = old.loc[keep]
    result = pd.concat([x for x in [old, new] if not x.empty], ignore_index=True) if not old.empty or not new.empty else new.copy()
    if result.duplicated(keys).any():
        raise ValueError("La actualización produciría duplicados.")
    return result.sort_values(keys, kind="stable").reset_index(drop=True)


def _coverage_frame(d, kind):
    d = d.reset_index(drop=True)
    dims = ["servicio", "modalidad"] if kind == "VIS" else ["bono"]
    counts = ["usuarios_unicos", "unidades_unicas", "registros"] if kind == "VIS" else ["beneficiarios_unicos", "registros"]
    required = ["periodo", "anio", "mes", *dims, *counts]
    if not set(required) <= set(d):
        raise ValueError(f"Columnas incompletas en {path}.")
    parsed = periods(d[required])
    if not (parsed.anio.eq(d.anio) & parsed.mes.eq(d.mes)).all():
        raise ValueError("Año/mes no concilian con periodo.")
    for c in dims:
        parsed[c] = parsed[c].fillna("SIN CLASIFICAR").map(lambda x: str(x).strip())
    for c in counts:
        n = pd.to_numeric(parsed[c], errors="raise")
        if n.isna().any() or (n < 0).any() or (n % 1 != 0).any():
            raise ValueError(f"Conteos inválidos: {c}")
        parsed[c] = n.astype("int32")
    primary = "usuarios_unicos" if kind == "VIS" else "beneficiarios_unicos"
    if (parsed[primary] > parsed.registros).any():
        raise ValueError("Beneficiarios únicos exceden registros.")
    if parsed.duplicated(["periodo", *dims]).any():
        raise ValueError("Clave mensual de cobertura repetida.")
    return parsed


def coverage_tables(path, kind):
    """Keep independently deduplicated national and territorial tabulations apart."""
    d = pd.read_parquet(path)
    if kind == "VIS" and "modalidad_descripcion" in d:
        # The broad CDI label contains direct, agreement and emblematic centres.
        # Use the supplied detailed modality, without its display-only ordinal.
        d["modalidad"] = d.modalidad_descripcion.map(lambda v: re.sub(r"^\d+\s*[.\-]+\s*", "", norm(v)))
        if d.modalidad.eq("").any():
            raise ValueError("Modalidad detallada vacía en cobertura VIS.")
    dims = ["servicio", "modalidad"] if kind == "VIS" else ["bono"]
    for c in dims:
        d[c] = d[c].map(lambda v: norm(v) or "SIN CLASIFICAR")
    if "nivel_territorial" not in d:
        return _coverage_frame(d, kind), None, {"ambito": "nacional", "registros_por_nivel_conciliados": None}
    levels = {"NACIONAL": "Nacional", "PROVINCIA": "Provincia", "CANTON": "Cantón", "PARROQUIA": "Parroquia"}
    d["nivel_territorial"] = d.nivel_territorial.map(norm).map(levels)
    if d.nivel_territorial.isna().any() or set(d.nivel_territorial) != set(levels.values()):
        raise ValueError("Se requieren los cuatro niveles: nacional, provincia, cantón y parroquia.")
    national = _coverage_frame(d.loc[d.nivel_territorial.eq("Nacional")], kind)
    keys = ["periodo", *dims]
    control = national.set_index(keys).registros.sort_index()
    blocks = []
    geography = ["codigo_provincia", "provincia", "codigo_canton", "canton", "codigo_parroquia", "parroquia"]
    for level, code, width in [("Provincia", "codigo_provincia", 2), ("Cantón", "codigo_canton", 4), ("Parroquia", "codigo_parroquia", 6)]:
        block = d.loc[d.nivel_territorial.eq(level)].reset_index(drop=True).copy()
        for column in geography:
            block[column] = block[column].astype("string").str.strip()
        names = ["provincia", "canton", "parroquia"]
        for column in names:
            block[column] = block[column].map(norm)
        for column, size in [("codigo_provincia", 2), ("codigo_canton", 4), ("codigo_parroquia", 6)]:
            expected = size <= width
            if expected and not block[column].str.fullmatch(rf"\d{{{size}}}").fillna(False).all():
                raise ValueError(f"Código territorial inválido: {level}/{column}")
            if not expected and block[column].notna().any():
                raise ValueError(f"Código de un nivel inferior presente en {level}.")
        if not block[code].str[:2].eq(block.codigo_provincia).all() or (width == 6 and not block[code].str[:4].eq(block.codigo_canton).all()):
            raise ValueError("La jerarquía de códigos territoriales no concilia.")
        block["codigo_territorio"] = block[code]
        if block.duplicated([*keys, "codigo_territorio", *names]).any():
            raise ValueError(f"Clave territorial duplicada en {level}.")
        # Some supplied codes identify conflicting place names (notably VIE
        # January). Preserve those separate aggregates; never guess a location
        # or add their distinct counts as though they were one territory.
        labels = block[["periodo", code, *names]].drop_duplicates()
        collisions = labels.groupby(["periodo", code]).size().gt(1)
        block["codigo_ambiguo"] = [bool(collisions.loc[(p, c)]) for p, c in zip(block.periodo, block[code])]
        # Validate counts/periods with territorial codes as part of the grouping.
        for count in (["usuarios_unicos", "unidades_unicas", "registros"] if kind == "VIS" else ["beneficiarios_unicos", "registros"]):
            values = pd.to_numeric(block[count], errors="raise")
            if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
                raise ValueError(f"Conteos territoriales inválidos: {count}")
            block[count] = values.astype("int32")
        unique = "usuarios_unicos" if kind == "VIS" else "beneficiarios_unicos"
        if (block[unique] > block.registros).any():
            raise ValueError("Los únicos territoriales exceden registros.")
        parsed = periods(block)
        if not (parsed.anio.eq(block.anio) & parsed.mes.eq(block.mes)).all():
            raise ValueError("Año/mes territorial no concilia con periodo.")
        observed = parsed.groupby(keys).registros.sum().sort_index()
        if not observed.equals(control):
            raise ValueError(f"Los registros por grupo de {level} no concilian con la tabulación nacional.")
        counts = [c for c in national if c not in {"periodo", "anio", "mes", "mes_nombre", *dims}]
        blocks.append(parsed[["periodo", "anio", "mes", "mes_nombre", "nivel_territorial", "codigo_territorio", *geography, "codigo_ambiguo", *dims, *counts]])
    territorial = pd.concat(blocks, ignore_index=True)
    return national, territorial, {"ambito": "Nacional, provincia, cantón y parroquia",
        "registros_por_nivel_conciliados": True, "filas_nacionales": len(national),
        "filas_territoriales": len(territorial),
        "filas_con_codigo_ambiguo": int(territorial.codigo_ambiguo.sum()),
        "codigos_ambiguos": territorial.loc[territorial.codigo_ambiguo, ["periodo", "nivel_territorial", "codigo_territorio"]].drop_duplicates().to_dict("records"),
        "unicos": "Cada nivel fue deduplicado en origen. No sumar únicos territoriales para sustituir el nacional ni sumar niveles entre sí.",
        "modalidad_vis": "Se conserva la modalidad detallada; CDI directos, convenios y emblemáticos permanecen separados." if kind == "VIS" else None}


def national_coverage(path, kind):
    return coverage_tables(path, kind)[0]


def aggregate_people(d, date_column, dimensions, amount_column, *, measure):
    dates = pd.to_datetime(d[date_column], format="mixed", dayfirst=True, errors="coerce")
    selected = d.loc[dates.notna()].copy()
    selected["periodo"] = dates.loc[dates.notna()].dt.strftime("%Y-%m")
    for c in dimensions:
        selected[c] = selected[c].fillna("SIN DATO").map(lambda v: norm(v) or "SIN DATO")
    # Monetary sums use integer cents, not binary floats.
    selected["centavos"] = pd.to_numeric(selected[amount_column], errors="raise").mul(100).round().astype("Int64")
    selected["cedula"] = selected.cedula.astype("string").str.strip().replace("", pd.NA)
    keys = ["periodo", *dimensions]
    out = selected.groupby(keys, dropna=False, observed=True).agg(
        beneficiarios=("cedula", "nunique"), registros=("cedula", "size"),
        monto_centavos=("centavos", lambda x: x.sum(min_count=1)),
        montos_validos=("centavos", "count")).reset_index()
    out["monto_usd"] = [Decimal(int(c))/100 if valid == n and pd.notna(c) else None
                        for c, valid, n in zip(out.monto_centavos, out.montos_validos, out.registros)]
    out = out.drop(columns=["monto_centavos", "montos_validos"])
    out["criterio"] = measure
    for c in ["beneficiarios", "registros"]:
        out[c] = out[c].astype("int32")
    return periods(out)


def incentives(path):
    cols = ["cedula", "valor", "codigo_rechazo", "fecha_acreditacion", "numero_referencia", "observacion", "nombre_archivo", "grupo_carga"]
    d = pd.read_parquet(path, columns=cols)
    d["programa_id"] = d.grupo_carga.map({"1 JOVENES EN ACCION": "JEA", "3 FEMICIDIO": "ORFANDAD_VIOLENCIA",
        "4 COMBUSTIBLES GASOLINA EXTRA Y EXTRA CON ETANOL": "COMPENSACION_GASOLINA", "5 DIESEL": "COMPENSACION_DIESEL", "9 BONO MIGRANTES": "MIGRANTES"})
    if d.programa_id.isna().any():
        raise ValueError("Hay un grupo de incentivos nuevo: actualice el catálogo.")
    d["fase"] = pd.to_numeric(d.nombre_archivo.str.extract(r"(\d+)ETAPA", expand=False), errors="coerce").fillna(0).astype("int8")
    if d.loc[d.programa_id.eq("JEA"), "fase"].eq(0).any():
        raise ValueError("No se identifica la fase de Jóvenes en Acción.")
    # Same bank transaction was loaded under several institution filenames.
    identity = ["programa_id", "fase", "cedula", "valor", "codigo_rechazo", "fecha_acreditacion", "numero_referencia", "observacion"]
    before = len(d)
    d = d.drop_duplicates(identity)
    paid = d.loc[d.codigo_rechazo.astype(str).str.strip().eq("1")].copy()
    dates = pd.to_datetime(paid.fecha_acreditacion, format="mixed", dayfirst=True, errors="coerce")
    if dates.isna().any() or paid.cedula.isna().any():
        raise ValueError("Una acreditación no tiene fecha o identificador; revise la fuente.")
    # Successful response '1' is documented by the MEF transfer manual.
    out = aggregate_people(paid, "fecha_acreditacion", ["programa_id", "fase"], "valor", measure="acreditado")
    out["fase"] = pd.to_numeric(out.fase).astype("int8")
    out = out.drop(columns="criterio").rename(columns={"registros": "transferencias", "monto_usd": "monto_acreditado"})
    unique = paid.groupby(["programa_id", "fase"]).cedula.nunique()
    phase_totals = paid.groupby(["programa_id", "fase"]).valor.apply(lambda x: sum(money(v) for v in x))
    audit = {"filas_entrada": before, "repeticiones_transaccion_eliminadas": before-len(d),
             "respuestas_no_acreditadas": int(len(d)-len(paid)),
             "jea_fase3_beneficiarios_acreditados": int(unique.get(("JEA", 3), 0)),
             "jea_fase3_monto_acreditado": str(phase_totals.get(("JEA", 3), Decimal(0))),
             "fecha_min": dates.min().isoformat(), "fecha_max": dates.max().isoformat(),
             "clave_deduplicacion": identity}
    return out, audit


def source_rank(filename):
    """Choose a complete version per source family/year, never add successive dumps."""
    years = re.findall(r"20\d{2}", filename)
    year = int(years[0]) if years else 0
    key = norm(filename)
    month = max([i for i, label in enumerate(MONTHS, 1) if label.upper() in key] or [0])
    match = re.search(r"(?:A_|DE_)(\d{1,2})_(?:DE_)?[A-Z]+_20\d{2}", key)
    day = int(match[1]) if match else 31 if month else 0
    family = "JAIBA_MORA" if "JAIBA" in key else "GENERAL"
    return family, year, month, day


def contingencies(path, kind):
    d = read_csv(path, dtype=str)
    input_rows = len(d)
    versions = []
    if kind == "antropicos":
        candidates = {}
        for filename in d.origen_archivo.unique():
            family, year, month, day = source_rank(filename)
            candidates.setdefault((family, year), []).append((month, day, filename))
        chosen = []
        for key, choices in candidates.items():
            choices.sort()
            best = choices[-1]
            if sum((v[0], v[1]) == best[:2] for v in choices) != 1:
                raise ValueError(f"Dos versiones sin prioridad inequívoca: {key}.")
            chosen.append(best[2])
            versions.append({"familia": key[0], "anio": key[1], "archivo_elegido": best[2]})
        d = d.loc[d.origen_archivo.isin(chosen)].copy()
        d["tipo"] = d.origen_archivo.map(lambda x: source_rank(x)[0])
        d["habilitacion"] = d.fecha_hab.fillna(d.desde)
        d["cobro"] = d.fecha_cobro
        territory = ["provincia", "canton"]
        excluded = ["nro", "origen_archivo", "fecha_carga"]
    else:
        d["tipo"] = d.tipo_de_contingencia.map(norm)
        d["habilitacion"] = d.fecha_de_memorando_habilitacion
        d["cobro"] = d.fecha_de_cobro
        territory = ["provincia", "canton", "parroquia"]
        excluded = ["n", "origen_archivo", "fecha_carga"]
    selected_rows = len(d)
    identity = [c for c in d if c not in excluded]
    d = d.drop_duplicates(identity).copy()
    null_amounts = int(pd.to_numeric(d.monto, errors="coerce").isna().sum())
    # Do not count a textual COBRADO without an actual collection date as dated spending.
    national, geographic = [], []
    for date_col, measure in [("habilitacion", "habilitado"), ("cobro", "cobrado")]:
        national.append(aggregate_people(d, date_col, [], "monto", measure=measure))
        geographic.append(aggregate_people(d, date_col, territory+["tipo"], "monto", measure=measure))
    audit = {"filas_entrada": input_rows, "filas_versiones_elegidas": selected_rows,
             "duplicados_exactos_eliminados": selected_rows-len(d), "filas_depuradas": len(d),
             "montos_faltantes": null_amounts, "versiones": versions,
             "sin_fecha_habilitacion": int(pd.to_datetime(d.habilitacion, format="mixed", dayfirst=True, errors="coerce").isna().sum()),
             "sin_fecha_cobro": int(pd.to_datetime(d.cobro, format="mixed", dayfirst=True, errors="coerce").isna().sum())}
    return pd.concat(national, ignore_index=True), pd.concat(geographic, ignore_index=True), audit


def orphan_beneficiaries(path):
    d = read_csv(path)
    d["periodo"] = pd.to_datetime(dict(year=d["AÑO"], month=d.MES, day=1)).dt.strftime("%Y-%m")
    if (d.BENEFICIARIOS_DISTINTOS > d.TOTAL_REGISTROS).any():
        raise ValueError("Beneficiarios de orfandad exceden registros.")
    return periods(d[["periodo", "BENEFICIARIOS_DISTINTOS", "TOTAL_REGISTROS"]].rename(columns={
        "BENEFICIARIOS_DISTINTOS": "beneficiarios", "TOTAL_REGISTROS": "registros"}))
