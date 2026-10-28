"""Source-backed operational monitoring; dates and measures retain their source scope.

Every day the follow-up is reported is kept as a publication of its own, named by that day:
``seguimiento_enos_AAAA-MM-DD.json`` (alerts, kits and the contingency bonus, with the scopes written that day in
``notas``) and ``continuidad_servicios_AAAA-MM-DD.json`` (units whose attention was suspended).  A report for a period
can either recover the publication in force on its last day or query the complete available event history by date.
The historical-publication mode reproduces what was reported after new data arrive. A published day is never edited: new data open a new
publication (``scripts/nuevo_corte_riesgos.py``), and the days already closed keep their SHA-256 in ``cortes_riesgos.json``.

Inside a publication every source is cut by its own dates (``filtro_temporal_estricto``): alerts by their date of
registration or report, kits by their date of delivery and the suspended units by the date of their territorial report.
The confirmed contingency bonus is an accumulated reference, not a daily flow: its people and amounts remain unchanged
when the report date changes. Earlier dates without a saved publication have no archived bulletin; their available
dated records can still be queried through ``history()`` using the latest known version of each source identifier.
"""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "data/processed"
SNAPSHOT = "seguimiento_enos_*.json"
CONTINUITY = "continuidad_servicios_*.json"
LEDGER = FOLDER / "cortes_riesgos.json"
REPORTS = ROOT / "data/reports"

QUALITY_NOTE = ""

START = "2026-09-28"   # start of the reporting period: alerts, kits and territorial reports from this date
REFERENCE = "Ámbito: alertas y reportes sectoriales y acciones institucionales de respuesta."

ALERT_COLUMNS = ['codigo','fecha','provincia','canton','estado','prioridad','codigo_ua','unidad',
                 'afectados_fuente','afectacion_servicio_confirmada','servicio','afectacion_servicio','origen','fecha_texto','mes_reporte',
                 'tipo_alerta']
# Every alert published before the type of alert was recorded is an emergency alert (Fenómeno El Niño).
DEFAULT_ALERT_TYPE = "Emergencia"
# Origins whose alerts are included by their source and service (application, sectoral reports and the Excel matrix).
LISTED_ORIGINS = ("reporte_sectorial", "aplicativo", "matriz_alertas")


# ------------------------------------------------------------------------------------------------ publications
def publications(pattern: str = SNAPSHOT) -> list[tuple[pd.Timestamp, Path]]:
    """The publications of one source, oldest first; the date in the name is the day it was reported."""
    found = []
    for path in FOLDER.glob(pattern):
        day = pd.to_datetime(path.stem[-10:], format="%Y-%m-%d", errors="coerce")
        if pd.notna(day):
            found.append((day, path))
    return sorted(found)


def snapshots() -> list[Path]:
    return [path for _day, path in publications(SNAPSHOT)]


def publication_day(path) -> pd.Timestamp:
    return pd.Timestamp(Path(path).stem[-10:])


def in_force(pattern: str, until=None) -> tuple[Path | None, bool]:
    """Latest publication reported on or before ``until``. Never use a later file to invent an earlier publication."""
    found = publications(pattern)
    if not found:
        return None, False
    if until is None:
        return found[-1][1], True
    until = pd.Timestamp(until).normalize()
    earlier = [path for day, path in found if day <= until]
    return (earlier[-1], True) if earlier else (None, False)


def fingerprint(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ledger() -> dict:
    """The days already closed: each publication file with the SHA-256 it had when the next day was opened."""
    return json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"cerrados": {}}


def archived_pdf(metadata: dict) -> bytes:
    """The approved document exactly as issued, with its integrity verified before download."""
    name = metadata["archivo"]
    if Path(name).name != name or not name.endswith(".pdf"):
        raise ValueError("Nombre de documento histórico inválido.")
    content = (REPORTS / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
        raise ValueError("El PDF histórico no coincide con el documento aprobado.")
    return content


def window(data: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The reporting period of a publication: from its start (``desde``) to its cut."""
    return pd.Timestamp(data["desde"]).normalize(), pd.Timestamp(data["corte"]).normalize()


def day(value) -> pd.Timestamp:
    """Calendar day recorded by the source, including rows carrying a time."""
    value = pd.Timestamp(value)
    return value.normalize().tz_localize(None) if pd.notna(value) else pd.NaT


def dates(values) -> pd.Series:
    """Comparable calendar days; do not drop events on the final afternoon."""
    return pd.Series([day(value) for value in values], index=values.index if isinstance(values, pd.Series) else None,
                     dtype="datetime64[ns]")


def ensure_open(path) -> None:
    """Ingestion may write the open publication, never a previously issued day."""
    path = Path(path)
    if any(path.name in files for files in ledger().get("cerrados", {}).values()):
        raise ValueError(f"{path.name} es una publicación cerrada; abra un corte nuevo antes de cargar datos.")
    if path.name.startswith("seguimiento_enos_"):
        found = publications(SNAPSHOT)
        if found and publication_day(path) < found[-1][0]:
            raise ValueError(f"{path.name} precede al último corte; las publicaciones anteriores no se reescriben.")


def history_paths() -> list[Path]:
    paths = [path for pattern in (SNAPSHOT, CONTINUITY) for _date, path in publications(pattern)]
    brigades = FOLDER / "brigadas_emergencia.json"
    return paths + ([brigades] if brigades.exists() else [])


def history() -> dict:
    """Current known event history, reconciled by source ID before applying dates.

    Daily publications remain immutable. A newer version of an ID replaces the
    older version even when its date or inclusion decision changes. A source
    explicitly marked as a complete replacement replaces its own register.
    Continuity and the bonus are observations/balances, never summed over cuts.
    """
    found = publications()
    if not found:
        raise ValueError("No hay bases de seguimiento disponibles.")
    registers = {"alertas": {}, "kits": {}}
    brigade_sources, sources = [], {}
    data = None
    for published, path in found:
        current = json.loads(path.read_text(encoding="utf-8"))
        data = deepcopy(current)
        for name, key in (("alertas", "codigo"), ("kits", "id_kobo")):
            full = current.get(f"{name}_metadatos", {}).get("reemplaza_corte_anterior", False)
            if full:
                registers[name].clear()
            seen = set()
            for row in current.get(name, []):
                identifier = str(row.get(key) or "").strip()
                if not identifier or identifier in seen:
                    raise ValueError(f"{path.name}: {name} requiere identificadores únicos y no vacíos.")
                seen.add(identifier)
                # Keep an explicit exclusion as the winning version, rather than reviving an older row.
                registers[name][identifier] = (deepcopy(row), name != "alertas" or included(row, current))
        for identifier in current.get("control", {}).get("alertas_excluidas_codigos", []):
            registers["alertas"].pop(str(identifier).strip(), None)
        if "brigadas" in current:
            brigade_sources.append((day(current.get("cortes", {}).get("brigadas", published)), 0,
                                    current["brigadas"], False))
        for source in current.get("fuentes", []):
            sources[(source.get("nombre"), source.get("sha256"))] = source
    assert data is not None
    for name in registers:
        data[name] = [row for row, keep in registers[name].values() if keep]
    from src import brigadas
    complete = brigadas.load(FOLDER / "brigadas_emergencia.json")
    if complete.get("corte"):
        brigade_sources.append((day(complete["corte"]), 1, complete.get("brigadas", []), True))
        for source in complete.get("fuentes", []):
            sources[(source.get("nombre"), source.get("sha256"))] = source
    brigade_rows = {}
    for cut, _priority, rows, full in sorted(brigade_sources, key=lambda s: (s[0], s[1])):
        if full:
            brigade_rows.clear()
        seen = set()
        for row in rows:
            identifier = str(row.get("id") or "").strip()
            if not identifier or identifier in seen:
                raise ValueError("La base de brigadas requiere identificadores únicos y no vacíos.")
            seen.add(identifier)
            brigade_rows[identifier] = deepcopy(row)
        data.setdefault("cortes", {})["brigadas"] = cut.strftime("%Y-%m-%d")
    data["brigadas"] = list(brigade_rows.values())
    recorded_days, coverage = [], {}
    for name in ("alertas", "kits", "brigadas"):
        for row in data[name]:
            moment = day(row.get("fecha"))
            if pd.isna(moment):
                raise ValueError(f"La base de {name} contiene un registro sin fecha válida.")
            row["fecha"] = moment.strftime("%Y-%m-%d")
        data[name].sort(key=lambda row: (row["fecha"], str(row.get("codigo", row.get("id_kobo", row.get("id"))))))
        days = [day(row["fecha"]) for row in data[name]]
        if days:
            coverage[name] = {"desde": min(days).strftime("%Y-%m-%d"), "hasta": max(days).strftime("%Y-%m-%d"),
                              "registros": len(days)}
            recorded_days.extend(days)
    for _published, path in publications(CONTINUITY):
        cut = continuity_cut(continuity(path))
        if cut is not None:
            recorded_days.append(day(cut))
    if not recorded_days:
        raise ValueError("Las bases no contienen registros con fecha para consultar.")
    data.update(desde=min(recorded_days).strftime("%Y-%m-%d"), corte=max(recorded_days).strftime("%Y-%m-%d"),
                consulta="periodo", cobertura_registros=coverage, fuentes=list(sources.values()),
                publicacion_fuente=found[-1][0].strftime("%Y-%m-%d"))
    data.pop("pdf_publicado", None)
    data.setdefault("notas", {}).update(
        alertas="Alertas del aplicativo, de la matriz Excel y de los reportes sectoriales, de todo tipo (el filtro «Tipo de "
                "alerta» permite consultar solo las de emergencia). Cada código se cuenta una vez con su estado más reciente; "
                "no equivale a eventos ni unidades únicas.",
        bono="El Bono de Contingencia conserva su acumulado confirmado al cambiar el período consultado. "
             f"Corte de la fuente: {cut_text(data['cortes']['bonos'])}.")
    return data


def history_window(data: dict | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    return window(history() if data is None else data)


def continuity_at(until) -> dict:
    """One latest territorial observation at/before the end, never summed cuts."""
    available = []
    for published, path in publications(CONTINUITY):
        data = continuity(path)
        cut = continuity_cut(data)
        if cut is not None and day(cut) <= day(until):
            available.append((cut, published, data))
    if not available:
        return {"registros": [], "detalle": [], "disponible": False}
    return max(available, key=lambda item: (item[0], item[1]))[2]


# ------------------------------------------------------------------------------------------------ texts
def cut_text(value) -> str:
    """A cut as the documents write it: «27/10/2026, 13:35:45», «26/10/2026, 16:00» or «23/10/2026»."""
    moment = pd.Timestamp(value)
    if (moment.hour, moment.minute, moment.second) == (0, 0, 0):
        return f"{moment:%d/%m/%Y}"
    return f"{moment:%d/%m/%Y, %H:%M}" + (f":{moment:%S}" if moment.second else "")


def short_cut(value) -> str:
    """The cut of a key figure: «27/10, 13:35» or «23/10»."""
    moment = pd.Timestamp(value)
    return f"{moment:%d/%m, %H:%M}" if (moment.hour, moment.minute) != (0, 0) else f"{moment:%d/%m}"


def notes(data: dict) -> dict:
    """The scopes written for one publication (``notas``): alerts, the observations of the kits and the bonus."""
    stored = data.get("notas") or {}
    return {key: stored.get(key, "") for key in ("alertas", "kits", "bono", "calidad")}


def kit_note(data: dict, start=None, end=None) -> str:
    """The deliveries of the period and the Kobo cut they come from, then the observations of the publication."""
    first, last = window(data)
    start = pd.Timestamp(start).normalize() if start is not None else first
    end = pd.Timestamp(end).normalize() if end is not None else last
    cut = pd.Timestamp(data["cortes"]["kits"])
    if end >= cut.normalize():
        text = f"Kits en provincias priorizadas: entregas desde el {start:%d/%m/%Y} hasta el corte Kobo del {cut_text(cut)}."
    else:
        days = f"del {start:%d/%m/%Y}" if start == end else f"del {start:%d/%m/%Y} al {end:%d/%m/%Y}"
        text = f"Kits en provincias priorizadas: entregas {days}, según el corte Kobo del {cut_text(cut)}."
    return " ".join(part for part in (text, notes(data)["kits"]) if part)


def continuity_cut(data: dict):
    cut = pd.to_datetime(data.get("corte"), errors="coerce")
    return None if pd.isna(cut) else cut


def continuity_note(data: dict) -> str:
    cut = continuity_cut(data)
    if cut is None:
        return ""
    return f"Unidades con suspensión reportada al {cut_text(cut)}. Este indicador corresponde a ese corte territorial."


def continuity_cuts(data: dict) -> str:
    """«corte territorial: 26/10/2026, 16:00», or each province with its own day when the sources differ."""
    days = {province: pd.Timestamp(day) for province, day in (data.get("fuentes_por_provincia") or {}).items() if day}
    if len(set(days.values())) > 1:
        groups: dict[pd.Timestamp, list[str]] = {}
        for province, day in sorted(days.items(), key=lambda item: (-item[1].value, item[0])):
            groups.setdefault(day, []).append(province)
        named = [(p[0] if len(p) == 1 else ", ".join(p[:-1]) + " y " + p[-1]) + f" {day:%d/%m}" for day, p in groups.items()]
        return "cortes: " + "; ".join(named)
    cut = continuity_cut(data)
    return f"corte territorial: {cut_text(cut)}" if cut is not None else ""


# ------------------------------------------------------------------------------------------------ records
def included(row, data):
    if row.get("origen") in LISTED_ORIGINS and data.get("criterio_alertas") == "codigo_ua_y_reportes_sectoriales":
        return bool(row.get("fuente")) and bool(row.get("servicio"))
    if data.get("criterio_alertas") in ("codigo_ua", "codigo_ua_y_reportes_sectoriales"):
        return (str(row.get("codigo_ua", "")).strip() not in ("", "—", "-", "nan", "None")
                and isinstance(row.get("afectacion_servicio_confirmada"), bool) and bool(row.get("servicio")))
    return row.get("afectacion_servicio_confirmada") is True


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    data['alertas'] = [r for r in data['alertas'] if included(r, data)]
    return data


def period_confirmed(data, stage, since=None, until=None):
    """A stage of the bonus belongs to the period consulted (by default, the whole reporting period): the person in charge
    confirmed a period for it and that period lies within the one consulted."""
    period = data.get('bonos_periodos_confirmados', {}).get(stage, {})
    since = pd.Timestamp(since if since is not None else data['desde']).strftime('%Y-%m-%d')
    until = pd.Timestamp(until if until is not None else data['corte']).strftime('%Y-%m-%d')
    return bool(period.get('confirmacion') and period.get('desde') and period.get('hasta')
                and since <= period['desde'] <= period['hasta'] <= until)


def fixed_bonus(data, stage):
    """The approved articulation balance remains independent of the selected report dates."""
    if stage != "articulacion":
        return False
    return any(data.get(key, {}).get(stage, {}).get("confirmacion")
               for key in ("bonos_periodos_confirmados", "bonos_referencia_confirmada"))


def frames(data, provinces=()):
    result = {}
    for name, rows in [('alertas', data['alertas']), ('kits', data['kits']),
                       ('gestionados', data['bonos']['gestionados']), ('articulacion', data['bonos']['articulacion'])]:
        if name == 'alertas' and data.get('consulta') != 'periodo':
            # history() already evaluated the winning record using its own source's criteria.
            rows = [r for r in rows if included(r, data)]
        columns = ALERT_COLUMNS if name == 'alertas' else ['fecha','provincia','canton','kits','familias','id_kobo'] if name == 'kits' else ['provincia','evento','personas','monto']
        frame = pd.DataFrame(rows, columns=columns)
        if name == 'alertas':
            frame['tipo_alerta'] = frame.tipo_alerta.fillna(DEFAULT_ALERT_TYPE).replace('', DEFAULT_ALERT_TYPE)
        if name in ('alertas', 'kits'):
            recorded = dates(frame.fecha)
            frame = frame.loc[recorded.between(day(data['desde']), day(data['corte']))]
        elif data.get('filtro_temporal_estricto') and not (fixed_bonus(data, name) or period_confirmed(data, name)):
            recorded = dates(pd.Series([r.get('fecha') for r in rows], index=frame.index))
            frame = frame.loc[recorded.between(day(data['desde']), day(data['corte']))]
        if provinces:
            frame = frame.loc[frame.provincia.isin(provinces)]
        result[name] = frame.copy()
    return result


def summary(frame, group, value=None):
    result = frame.groupby(group)[value].sum() if value else frame.groupby(group).size()
    return [{'name': str(name), 'value': int(value)} for name, value in result.sort_values(ascending=False).items()]


def continuity(path=None) -> dict:
    """One publication of the continuity of the services (by default, the latest)."""
    path = path or in_force(CONTINUITY)[0]
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {"registros": [], "detalle": []}
