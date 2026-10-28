"""Respuesta del Ministerio ante El Niño, junto a la exposición de las unidades de atención en Riesgos.

Three actions with their own sources and cuts (see :mod:`src.enos`): reviewed alerts linked to identified MTDH units
since 28 September 2026, kits delivered (the supplied Kobo cut) and the contingency bonus (payments managed and
cases in articulation for floods, and the national plan for El Niño 2026–2027).  Each keeps its unit: alerts are alerts,
kits are kits and bonus figures are nuclei with a managed payment or people in articulation; they are never added together.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from src import charts, depuracion, enos, names, theme, ui

# Services of the continuity report: CNH and CDI keep the acronyms of the approved bulletin; the rest read by their names.
SERVICE_NAMES = {"PAM": "Personas Adultas Mayores", "PCD": "Personas con Discapacidad", "PE": "Protección Especial",
                 "AF": "Acompañamiento Familiar"}

# Markers some sources write where a canton or a unit name is missing; they read as missing values (a dash).
_MISSING = {"sin cantón en la base", "sin nombre", "sin nombre en la base", "sin nombre en la fuente", "nan", "none"}

FILTERS_NOTE =("El territorio se aplica a todas las acciones; el servicio, a las alertas y al seguimiento de continuidad de atención. "
                "Kits y bono no se asocian a un servicio. La planificación del bono es nacional.")
STATUS_TONES = {"Pendiente": "oro", "En seguimiento": "lila", "Resuelto": "ok"}
PRIORITY_TONES = {"Crítica": "fucsia", "Alta": "fucsia", "Media": "lila", "Baja": "gris"}


@lru_cache(maxsize=64)
def _code(province: str) -> str | None:
    return depuracion.gazetteer().province(province)


def _n(count: int, singular: str, plural: str | None = None) -> str:
    return f"{ui.number(count)} {singular if count == 1 else (plural or singular + 's')}"


def _date(value) -> str:
    return pd.Timestamp(value).strftime("%d/%m/%Y")


# Service of an alert when its unit is not in the inventory of the cut, from the wording of the source.
_SERVICE_WORDS = [(("infantil", "cnh", "creciendo", "cdi"), "DII"), (("adult", "geront"), "PAM_SERV"), (("discapacidad",), "PCD_SERV"),
                  (("protecci",), "PE"), (("acompañamiento", "acompanamiento"), "AF")]


def _service_of(text: str) -> str | None:
    words = str(text or "").lower()
    return next((program for keys, program in _SERVICE_WORDS if any(key in words for key in keys)), None)


def _two_lines(name: str, width: int = 18) -> str:
    """A long place name split in two lines at the space nearest its middle (for the narrow axes of phones)."""
    if len(name) <= width or " " not in name:
        return name
    cut = min((i for i, c in enumerate(name) if c == " "), key=lambda i: abs(i - len(name) / 2))
    return name[:cut] + "<br>" + name[cut + 1:]


def _clean(value, style) -> str:
    """A canton or unit name in its readable form; the markers of a missing value become an empty text."""
    text = " ".join(str(value).split()) if value is not None and value == value else ""
    return "" if not text or text.lower() in _MISSING else style(text)


_CONTINUITY_COLUMNS = ["provincia", "canton", "servicio", "unidad", "codigo_ua", "estado", "unidades", "programa_id", "corte_fuente"]


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """The rows of a source with at least these columns (an empty source keeps its shape)."""
    frame = pd.DataFrame(rows)
    for column in columns:
        if column not in frame:
            frame[column] = pd.Series(dtype=object)
    return frame


class Response:
    """The actions of one publication of the follow-up in a period, for the whole country and for the provinces of the
    consultation.

    The period (``since`` to ``until``; by default the reporting period of the publication) cuts every source by its own
    dates: alerts by their date of registration or report, kits by their date of delivery and the suspended units by the
    date of their territorial report. The confirmed contingency bonus is an accumulated balance, independent of the
    date selection; the territory filter still applies to its provincial breakdown.

    With a service filter, the alerts keep only those of its units (the service of each unit comes from the inventory,
    or from the wording of the source when the unit is not in it); kits and the bonus have no service and keep the
    territory filter alone.
    """

    def __init__(self, data: dict, provinces=(), programs=(), unit_programs: dict | None = None, *, since=None, until=None,
                 continuity: dict | None = None, publication: dict | None = None, types=()):
        self.data = data
        self.by_period = data.get("consulta") == "periodo"
        self.first, self.last = enos.window(data)
        self.start = pd.Timestamp(since).normalize() if since is not None else self.first
        self.end = pd.Timestamp(until).normalize() if until is not None else self.last
        if self.start > self.end:
            raise ValueError("La fecha Desde no puede ser posterior a Hasta.")
        # The day the figures were reported and whether that publication was in force at the end of the period (False: a
        # reconstruction with a later publication, cut by the dates of its records).
        self.publication = publication or {"dia": self.last, "exacta": True}
        self.strict = bool(data.get("filtro_temporal_estricto")) and not data.get("bonos_con_fecha_individual", False)
        national = enos.frames(data)
        for frame in national.values():
            frame["provincia_codigo"] = [_code(p) for p in frame.provincia]
            if "canton" in frame:
                # Kobo writes some cantons in capitals without accents (ESPINDOLA): they read as the gazetteer writes them.
                frame["canton"] = [_clean(c, names.place) for c in frame.canton]
        national["alertas"]["unidad"] = [_clean(u, names.unit) for u in national["alertas"].unidad]
        # Alerts and kits: their own dates, inside the reporting period and the period consulted.
        for key in ("alertas", "kits"):
            frame = national[key]
            dates = enos.dates(frame.fecha)
            national[key] = frame.loc[dates.between(max(self.start, self.first), min(self.end, self.last))].copy()
        self.cuts = data["cortes"]
        self.available = {"gestionados": self._stage("gestionados", self.cuts.get("bonos_gestionados") or self.cuts.get("bonos")),
                          "articulacion": self._stage("articulacion", self.cuts.get("bonos"))}
        for key, shown in self.available.items():
            if not shown:
                national[key] = national[key].iloc[0:0].copy()
            elif data.get("bonos_con_fecha_individual"):
                # Records with a date of their own (when a source gives them) are cut by it.
                dates = enos.dates(pd.Series([r.get("fecha") for r in data["bonos"][key]]).reindex(national[key].index))
                national[key] = national[key].loc[dates.between(self.start, self.end)].copy()
        self.bonus_period_available = self.available["articulacion"]
        # The type of alert (emergency, agreements, staff…) applies to the alerts only.
        self.types = list(types)
        if self.types:
            national["alertas"] = national["alertas"].loc[national["alertas"].tipo_alerta.isin(set(self.types))].copy()
        if programs:
            alerts = national["alertas"]
            known = alerts.codigo_ua.astype(str).map(unit_programs or {})
            alerts["programa_id"] = known.where(known.notna(), alerts.servicio.map(_service_of))
            national["alertas"] = alerts.loc[alerts.programa_id.isin(set(programs))].copy()
        self.programs = list(programs)
        self.national = national
        chosen = set(provinces)
        self.brigadas = [row for row in data.get("brigadas", [])
                         if max(self.start, self.first) <= enos.day(row["fecha"]) <= min(self.end, self.last)
                         and (not chosen or _code(row["provincia"]) in chosen)]
        self.frames = {k: (f.loc[f.provincia_codigo.isin(chosen)] if chosen else f).copy() for k, f in national.items()}
        self.alerts, self.kits = self.frames["alertas"], self.frames["kits"]
        self.managed, self.articulation = self.frames["gestionados"], self.frames["articulacion"]
        self.plan = data["bonos"]["planificacion"]
        # The days of the period inside the reporting period: the daily evolution of the alerts runs from «since» to «cut».
        self.since = self.start if self.by_period else max(self.first, self.start)
        self.cut = self.end if self.by_period else min(self.last, self.end)
        # Continuity of the services: each territorial report by its date.
        self.continuity_data = continuity if continuity is not None else (
            enos.continuity_at(self.end) if self.by_period else enos.continuity())
        records = _frame(self.continuity_data.get("registros", []), _CONTINUITY_COLUMNS)
        observation_dates = enos.dates(records.corte_fuente)
        inside = observation_dates.le(self.end) if self.by_period else observation_dates.between(self.start, self.end)
        self.available["continuidad"] = self.continuity_data.get("disponible", bool(inside.any()) or records.empty)
        continuity = records.loc[inside].copy()
        continuity["unidades"] = pd.to_numeric(continuity.unidades, errors="coerce").fillna(0).astype(int)
        continuity["servicio"] = continuity.servicio.replace(SERVICE_NAMES)
        continuity["provincia_codigo"] = continuity.provincia.map(_code)
        if programs:
            continuity = continuity.loc[continuity.programa_id.isin(programs)]
        self.national_continuity = continuity
        if chosen:
            continuity = continuity.loc[continuity.provincia_codigo.isin(chosen)]
        self.continuity = continuity
        detail = pd.DataFrame(self.continuity_data.get("detalle", []))
        if not detail.empty:
            observation_dates = enos.dates(detail.corte_fuente)
            inside = observation_dates.le(self.end) if self.by_period else observation_dates.between(self.start, self.end)
            detail = detail.loc[inside].copy()
            detail["servicio"] = detail.servicio.replace(SERVICE_NAMES)
            detail["canton"] = [_clean(c, names.place) for c in detail.canton]
            detail["unidad"] = [_clean(u, names.unit) for u in detail.unidad]
            detail["provincia_codigo"] = detail.provincia.map(_code)
            if chosen: detail = detail.loc[detail.provincia_codigo.isin(chosen)]
            if programs: detail = detail.loc[detail.programa_id.isin(programs)]
        self.continuity_detail = detail

    def _stage(self, key: str, cut) -> bool:
        """A stage of the bonus belongs to the period: with the strict filter, its confirmed period lies within the one
        consulted; with dates of its own, always (its records are cut by them); otherwise, its cut falls inside the period."""
        if enos.fixed_bonus(self.data, key):
            return True
        if self.data.get("bonos_con_fecha_individual"):
            return True
        if self.data.get("filtro_temporal_estricto"):
            return enos.period_confirmed(self.data, key, self.start, self.end)
        return cut is None or pd.Timestamp(cut).normalize() <= self.end

    @property
    def whole(self) -> bool:
        """The period holds the whole reporting period of the publication."""
        return self.start <= self.first and self.end >= self.last

    @property
    def continuity_cut(self):
        return enos.continuity_cut(self.continuity_data)

    def continuity_cut_text(self) -> str:
        cut = self.continuity_cut
        return enos.cut_text(cut) if cut is not None else ""

    def missing_text(self) -> str:
        """What the period cannot show and why (a figure that is not available, never a zero)."""
        parts = []
        if not self.available["articulacion"]:
            parts.append("Bono de contingencia: sin desglose temporal disponible para este período." if self.data.get("filtro_temporal_estricto")
                         else f"Bono de contingencia: corte {enos.cut_text(self.cuts['bonos'])}, posterior al periodo.")
        if not self.available["continuidad"]:
            parts.append("Unidades suspendidas: no hay un corte territorial disponible hasta la fecha seleccionada."
                         if self.by_period else f"Unidades suspendidas: el reporte territorial del {self.continuity_cut_text()} queda fuera del periodo.")
        return " ".join(parts)

    def publication_text(self) -> str:
        """«Cifras tal como se reportaron el 27/10/2026» or, before the first publication, how the period is reconstructed."""
        if self.by_period:
            return "Consulta por fecha de registro con las versiones más recientes de las bases disponibles."
        day = pd.Timestamp(self.publication["dia"])
        if self.publication.get("exacta", True):
            return f"Cifras tal como se reportaron el {_date(day)}."
        return (f"No hay una publicación guardada al {_date(self.end)}: las cifras se reconstruyen con la del {_date(day)}, "
                "según la fecha de cada registro.")

    def period_note(self) -> str:
        if self.by_period:
            text = (f"Periodo del {_date(self.start)} al {_date(self.end)}, ambos días incluidos. Alertas por fecha de registro o reporte; "
                    "kits por fecha de entrega; brigadas por fecha de realización. Unidades suspendidas: último corte territorial "
                    "disponible hasta la fecha final, sin sumar cortes. El bono conserva su acumulado confirmado y no representa "
                    "un flujo diario. " + self.publication_text())
            missing = self.missing_text()
            return f"{text} {missing}" if missing else text
        text = (f"Periodo del {_date(self.start)} al {_date(self.end)}. Alertas por su fecha de registro o reporte validada; kits por su "
                "fecha de entrega; unidades suspendidas por la fecha del corte territorial. El bono de contingencia se mantiene "
                "como acumulado confirmado al cambiar la fecha del reporte; no representa un flujo diario. "
                + self.publication_text())
        missing = self.missing_text()
        return f"{text} {missing}" if missing else text

    def notes(self) -> dict:
        """The scopes of the documents: those written for the publication, with the period consulted."""
        stored = enos.notes(self.data)
        return {"alerts": stored["alertas"], "kits": enos.kit_note(self.data, self.since, self.cut), "bonus": stored["bono"],
                "quality": stored["calidad"], "filters": FILTERS_NOTE, "continuity": enos.continuity_note(self.continuity_data),
                "period": self.period_note()}

    @property
    def closed_units(self) -> int:
        return int(self.continuity.loc[self.continuity.estado.isin(["Suspendida", "Suspendida presencial"]), "unidades"].sum())

    def continuity_summary(self) -> dict:
        f = self.continuity
        closed = f.loc[f.estado.isin(["Suspendida", "Suspendida presencial"])].copy()
        statuses = f.copy()
        statuses["lectura"] = statuses.estado
        suspended = statuses.estado.isin(["Suspendida", "Suspendida presencial"])
        statuses.loc[suspended, "lectura"] = statuses.loc[suspended, "servicio"] + ": atención suspendida"
        statuses["lectura"] = statuses.lectura.replace({"Atención virtual": "CDI: atención virtual",
            "Operativa con afectación": "CDI: operativos con afectación", "Afectada; modalidad por confirmar": "CDI: modalidad por confirmar"})
        return {"closed": self.closed_units, "by_province": enos.summary(closed, "provincia", "unidades"),
                "by_service": enos.summary(closed, "servicio", "unidades"),
                "by_status": enos.summary(statuses, "lectura", "unidades"),
                "note": enos.continuity_note(self.continuity_data), "cut": self.continuity_cut_text().replace(", ", " · "),
                "available": self.available["continuidad"], "heading": enos.continuity_cuts(self.continuity_data)}

    def suspended_groups(self) -> list[dict]:
        """Suspended units by province, canton and service, with the names the source gives; provinces and groups from the
        largest.  A canton or names the source does not give stay empty."""
        f = self.continuity_detail
        if f.empty: return []
        f = f.loc[f.estado.isin(["Suspendida", "Suspendida presencial"])]
        weight = f.groupby("provincia").unidades.sum()
        rows = []
        for (province, canton, service), part in f.groupby(["provincia", "canton", "servicio"], sort=True):
            rows.append({"province": province, "canton": canton, "service": service, "units": int(part.unidades.sum()),
                         "names": "; ".join(n for n in part.unidad if n)})
        return sorted(rows, key=lambda g: (-weight[g["province"]], g["province"], -g["units"], g["canton"]))

    def suspension_caption(self) -> str:
        return " · ".join(f"{a['value']} {a['name']}" for a in self.continuity_summary()["by_service"]) or "Sin suspensiones reportadas en la selección"

    def suspension_short(self) -> str:
        """The caption of a key figure: CNH and CDI with their units, the other services together (their names are in the
        chart by service)."""
        rows = self.continuity_summary()["by_service"]
        main = [f"{a['value']} {a['name']}" for a in rows if a["name"] in ("CNH", "CDI")]
        rest = sum(a["value"] for a in rows if a["name"] not in ("CNH", "CDI"))
        parts = main + ([f"{rest} en otros servicios"] if rest else [])
        return " · ".join(parts) or "Sin suspensiones reportadas en la selección"

    @property
    def kit_records(self) -> int:
        return len(self.kits)

    def kits_summary(self) -> list[dict]:
        rows = self.kits.groupby("provincia").agg(kits=("kits", "sum"), familias=("familias", "sum"), registros=("kits", "size")).reset_index()
        return rows.sort_values("kits", ascending=False).to_dict("records")

    def count_note(self) -> str:
        parts = [f"{count} {service}" for service, count in self.alerts.groupby("servicio").size().sort_values(ascending=False).items()]
        sectorial = int(self.alerts.origen.eq('reporte_sectorial').sum())
        matrix = int(self.alerts.origen.eq('matriz_alertas').sum())
        if not matrix:
            return f"{len(self.alerts)} registros: {len(self.alerts)-sectorial} alertas del aplicativo y {sectorial} reportes sectoriales. No equivalen a eventos únicos."
        return (f"{len(self.alerts)} registros: {len(self.alerts)-sectorial-matrix} alertas del aplicativo, {matrix} de la matriz Excel "
                f"y {sectorial} reportes sectoriales. No equivalen a eventos únicos.")

    # ------------------------------------------------------------------------------------------- figures
    @property
    def pending(self) -> int:
        return int(self.alerts.estado.eq("Pendiente").sum())

    @property
    def following(self) -> int:
        return int(self.alerts.estado.eq("En seguimiento").sum())

    @property
    def resolved(self) -> int:
        return int(self.alerts.estado.eq("Resuelto").sum())

    @property
    def units(self) -> int:
        return int(self.alerts.loc[self.alerts.codigo_ua.ne(""), "codigo_ua"].nunique())

    @property
    def kits_total(self) -> int:
        return int(self.kits.kits.sum())

    def places(self, frame: pd.DataFrame) -> tuple[int, int]:
        if "cantones" in frame and frame.cantones.notna().all():
            return int(frame.provincia.nunique()), int(frame.cantones.sum())
        return int(frame.provincia.nunique()), int(frame[["provincia", "canton"]].drop_duplicates().shape[0]) if "canton" in frame else 0

    def by_province(self, national: bool = False) -> pd.DataFrame:
        """Alerts, kits and bonus people (managed and in articulation) of each province, by DPA code."""
        frames = self.national if national else self.frames
        continuity = self.national_continuity if national else self.continuity
        closed = continuity.loc[continuity.estado.isin(["Suspendida", "Suspendida presencial"])]
        parts = [frames["alertas"].groupby("provincia_codigo").size().rename("alertas"),
                 closed.groupby("provincia_codigo").unidades.sum().rename("suspendidas"),
                 frames["kits"].groupby("provincia_codigo").kits.sum().rename("kits"),
                 frames["gestionados"].groupby("provincia_codigo").personas.sum().rename("gestionados"),
                 frames["gestionados"].groupby("provincia_codigo").monto.sum().rename("monto_gestionado"),
                 frames["articulacion"].groupby("provincia_codigo").personas.sum().rename("articulacion"),
                 frames["articulacion"].groupby("provincia_codigo").monto.sum().rename("monto_articulacion")]
        out = pd.concat(parts, axis=1).fillna(0)
        out.index.name = "provincia_codigo"
        return out.reset_index()

    def details_by_province(self, national: bool = False) -> dict[str, dict]:
        """For each province (DPA code): the status of its alerts, its deliveries of kits and the cantons with actions."""
        frames = self.national if national else self.frames
        out: dict[str, dict] = {}
        for code, part in frames["alertas"].groupby("provincia_codigo"):
            counts = part.estado.value_counts()
            states = [_n(int(counts.get("Pendiente", 0)), "pendiente"), f"{ui.number(int(counts.get('En seguimiento', 0)))} en seguimiento",
                      _n(int(counts.get("Resuelto", 0)), "resuelta")]
            out.setdefault(code, {})["alert_states"] = " · ".join(t for t, n in zip(states, [counts.get("Pendiente", 0),
                                                                                              counts.get("En seguimiento", 0),
                                                                                              counts.get("Resuelto", 0)]) if n)
        for code, part in frames["kits"].groupby("provincia_codigo"):
            out.setdefault(code, {})["deliveries"] = _n(len(part), "entrega")
        places = pd.concat([frames["alertas"][["provincia_codigo", "canton"]], frames["kits"][["provincia_codigo", "canton"]]])
        for code, part in places.groupby("provincia_codigo"):
            cantons = sorted({c for c in part.canton if c})
            out.setdefault(code, {})["cantons"] = ", ".join(cantons)
        return out

    def cut_text(self, key: str) -> str:
        """Cut of one source of the follow-up (alertas, kits, bonos or bonos_desde) as dd/mm/aaaa."""
        return _date(self.cuts[key])

    def scope_text(self) -> str:
        """The period of the consultation: «Del 28/09/2026 al 27/10/2026»."""
        return f"Del {_date(self.start)} al {_date(self.end)}"


# --------------------------------------------------------------------------------------------------- charts
def alerts_evolution(r: Response, height: int | None = None) -> go.Figure:
    """Alerts registered each day from the first day of the follow-up (columns) and their running total (step line)."""
    days = pd.date_range(r.since.normalize(), r.cut.normalize(), freq="D")
    if not len(days):
        return _empty(go.Figure(), "Sin alertas en el periodo")
    daily = (pd.to_datetime(r.alerts.fecha).dt.normalize().value_counts().reindex(days, fill_value=0) if not r.alerts.empty
             else pd.Series(0, index=days))
    total = daily.cumsum()
    labels = [f"{d.day} {ui._MONTHS_SHORT[d.month - 1]} {d.year}" for d in days]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=days, y=total, mode="lines", name="Acumuladas", line=dict(color=theme.MORADO, width=2.4, shape="hv"), fill="tozeroy",
        fillcolor="rgba(118,87,185,.12)", customdata=labels,
        hovertemplate="<b>%{customdata}</b><br>%{y} alertas acumuladas<extra></extra>"))
    fig.add_trace(go.Bar(
        x=days, y=daily, name="Registradas en el día", marker=dict(color=theme.ORO, cornerradius=3), width=86400000 * 0.8,
        customdata=labels, hovertemplate="<b>%{customdata}</b><br>%{y} alertas registradas<extra></extra>"))
    for day, count in daily[daily > 0].items():
        fig.add_annotation(x=day, y=count, text=f"<b>+{count}</b>", showarrow=False, yshift=11, font=dict(size=11.5, color=theme.ORO_700),
                           bgcolor="rgba(255,255,255,.92)", borderpad=2)
    peak = max(int(total.iloc[-1]) if len(total) else 0, 1)
    fig.add_annotation(x=days[-1], y=total.iloc[-1] if len(total) else 0, text=f"<b>{int(total.iloc[-1]) if len(total) else 0} alertas</b>",
                       showarrow=False, xanchor="right", yshift=14, font=dict(size=12.5, color=theme.MORADO_900))
    fig.add_vline(x=days[0], line=dict(color=theme.LILA_200, width=1.2, dash="dot"))
    charts.base(fig, height or 260, dict(l=8, r=16, t=40, b=30))
    ticks = list(pd.date_range(days[0], days[-1], freq="7D"))
    fig.update_xaxes(range=[days[0] - pd.Timedelta(days=1), days[-1] + pd.Timedelta(days=1)], showgrid=False, tickvals=ticks,
                     ticktext=[f"{t.day} {ui._MONTHS_SHORT[t.month - 1]}" for t in ticks], tickfont=dict(size=11))
    fig.update_yaxes(range=[0, peak * 1.3], showgrid=True, gridcolor="#F1EEF6", dtick=max(1, round(peak / 4)), tickfont=dict(size=11),
                     rangemode="tozero")
    fig.update_layout(bargap=0.1, legend=dict(orientation="h", y=1.14, x=0, traceorder="normal"))
    return fig


# ------------------------------------------------------------------------------ the visuals of the section
# Services keep one colour everywhere: Desarrollo Infantil (CDI) purple, Creciendo con Nuestros Hijos (CNH) lilac.
SERVICE_TONES = {"Desarrollo Infantil": theme.MORADO, "CDI": theme.MORADO, "Creciendo con Nuestros Hijos (CNH)": theme.LILA_300,
                 "CNH": theme.LILA_300, "Centros gerontológicos": theme.ORO, "Discapacidades · AHC": theme.FUCSIA_700}
# Provinces of the contingency bonus keep their colour in both stages.
PROVINCE_TONES = {"Guayas": theme.MORADO, "Esmeraldas": theme.VIOLETA_500, "El Oro": theme.LILA_300, "Los Ríos": theme.FUCSIA_700,
                  "Imbabura": theme.FUCSIA_300, "Manabí": theme.ORO, "Azuay": theme.MORADO_900}
_DARK_TEXT = {theme.LILA_300, theme.LILA_200, theme.LILA_100, theme.ORO, theme.FUCSIA_300}


def _ink(color: str) -> str:
    return theme.MORADO_900 if color in _DARK_TEXT else "#FFFFFF"


def _share(value: float, total: float) -> str:
    return ui.pct(value / total * 100 if total else 0)


def _empty(fig: go.Figure, text: str, height: int = 160) -> go.Figure:
    charts.base(fig, height, dict(l=8, r=8, t=8, b=8))
    fig.add_annotation(text=text, x=.5, y=.5, xref="paper", yref="paper", showarrow=False, font=dict(size=12.5, color=theme.PIZARRA))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def alerts_units(r: Response) -> go.Figure:
    """Each alert as one square, in the row of its province; the colour gives its service (a unit chart)."""
    fig = go.Figure()
    if r.alerts.empty:
        return _empty(fig, "Sin alertas en la selección")
    alerts = r.alerts.copy()
    services = list(alerts.servicio.value_counts().index)
    alerts["_rank"] = alerts.servicio.map({s: i for i, s in enumerate(services)})
    provinces = list(alerts.provincia.value_counts().sort_values(ascending=False, kind="stable").index)
    placed = []
    for province in provinces:
        part = alerts.loc[alerts.provincia.eq(province)].sort_values(["_rank", "fecha", "codigo"])
        placed += [{**row, "x": index, "y": province} for index, row in enumerate(part.to_dict("records"))]
    for service in services:
        rows = [p for p in placed if p["servicio"] == service]
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in rows], y=[p["y"] for p in rows], mode="markers", name={"Creciendo con Nuestros Hijos (CNH)": "CNH", "Centros gerontológicos": "Gerontología", "Discapacidades · AHC": "AHC"}.get(service, service),
            marker=dict(symbol="square", size=30, color=SERVICE_TONES.get(service, theme.VIOLETA_500), line=dict(color="#FFFFFF", width=3)),
            customdata=[[p["codigo"], ui._date_text(p["fecha"]) if pd.notna(p["fecha"]) else str(p.get("fecha_texto", "Sin fecha diaria")), p["unidad"], p["canton"], p["estado"], p["servicio"]] for p in rows],
            hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{customdata[2]}<br>%{customdata[5]}"
                           "<br>%{y} · %{customdata[3]}<br>Estado: %{customdata[4]}<extra></extra>")))
    counts = alerts.provincia.value_counts()
    widest = int(counts.max())
    charts.base(fig, 64 * len(provinces) + 76, dict(l=8, r=8, t=44, b=8))
    fig.update_xaxes(visible=False, range=[-0.7, max(widest, 5) - 0.3])
    fig.update_yaxes(categoryorder="array", categoryarray=provinces[::-1], tickvals=provinces,
                     ticktext=[f"<b>{_two_lines(p, 24)}</b>  <span style='color:{theme.PIZARRA}'>{counts[p]}</span>" for p in provinces],
                     tickfont=dict(size=12.5), range=[-0.6, len(provinces) - 0.4])
    fig.update_layout(legend=dict(orientation="h", y=1.04, yanchor="bottom", x=0, traceorder="normal"), hovermode="closest")
    return fig


def continuity_treemap(r: Response) -> go.Figure:
    """Where the suspended units are: provinces and their cantons, each tile in the colour of its service."""
    fig = go.Figure()
    f = r.continuity_detail
    if f.empty:
        return _empty(fig, "Sin unidades suspendidas en la selección", 220)
    closed = f.loc[f.estado.isin(["Suspendida", "Suspendida presencial"])]
    groups = closed.groupby(["provincia", "canton", "servicio"], as_index=False).unidades.sum()
    total = int(groups.unidades.sum())
    ids, labels, parents, values, colors, inks, notes = [], [], [], [], [], [], []
    for province, part in sorted(groups.groupby("provincia"), key=lambda item: -item[1].unidades.sum()):
        units = int(part.unidades.sum())
        ids.append(province); labels.append(province); parents.append(""); values.append(units)
        colors.append(theme.LILA_50); inks.append(theme.MORADO_900)
        notes.append(f"{units} UA · {_share(units, total)}")
        for row in part.sort_values("unidades", ascending=False).to_dict("records"):
            color = SERVICE_TONES.get(row["servicio"], theme.VIOLETA_500)
            ids.append(f"{province}/{row['canton']}/{row['servicio']}"); parents.append(province)
            # Without a canton in the source, the tile is named by its service.
            labels.append(row["canton"] or row["servicio"]); values.append(int(row["unidades"]))
            colors.append(color); inks.append(_ink(color))
            # A long service name (Personas Adultas Mayores) takes two lines so the tile keeps its label.
            service = row["servicio"] if len(row["servicio"]) <= 14 else _two_lines(row["servicio"], 14)
            joint = "<br>" if "<br>" in service else " · "
            notes.append(f"{service}{joint}{int(row['unidades'])} UA" if row["canton"] else f"{int(row['unidades'])} UA")
    fig.add_trace(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="total", sort=True, customdata=notes,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=3), pad=dict(t=26, l=5, r=5, b=5), cornerradius=6),
        texttemplate="<b>%{label}</b><br>%{customdata}", textposition="top left", textfont=dict(size=12.5, color=inks),
        hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>", tiling=dict(pad=4), root=dict(color="rgba(0,0,0,0)"),
        pathbar=dict(visible=False)))
    charts.base(fig, 330, dict(l=4, r=4, t=4, b=4))
    fig.update_layout(uniformtext=dict(minsize=10, mode="hide"))
    return fig


def continuity_donut(r: Response) -> go.Figure:
    """The share of each service in the suspended units, with the total at the centre."""
    fig = go.Figure()
    rows = r.continuity_summary()["by_service"]
    total = sum(row["value"] for row in rows)
    if not total:
        return _empty(fig, "Sin unidades suspendidas en la selección", 220)
    fig.add_trace(go.Pie(
        labels=[f"{row['name']} · {row['value']} UA ({_share(row['value'], total)})" for row in rows], values=[row["value"] for row in rows],
        hole=0.66, sort=False, direction="clockwise", rotation=90, textinfo="none",
        marker=dict(colors=[SERVICE_TONES.get(row["name"], theme.VIOLETA_500) for row in rows], line=dict(color="#FFFFFF", width=4)),
        hovertemplate="<b>%{label}</b><extra></extra>"))
    fig.add_annotation(text=f"<b>{ui.number(total)}</b>", x=0.5, y=0.56, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=34, color=theme.MORADO_900, family=theme.WEB_DISPLAY_STACK))
    fig.add_annotation(text="UA suspendidas", x=0.5, y=0.41, xref="paper", yref="paper", showarrow=False,
                       font=dict(size=12.5, color=theme.PIZARRA))
    charts.base(fig, 330, dict(l=8, r=8, t=8, b=8))
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.02, yanchor="top", x=0.5, xanchor="center",
                                                   font=dict(size=12.5, color=theme.TINTA)))
    return fig


def kits_overview(r: Response, compact: bool = False) -> go.Figure:
    """Kits of each province (a lollipop with the total and its share) and, beside it on the same rows, every delivery
    over time (a circle sized by its kits)."""
    from plotly.subplots import make_subplots
    summary = r.kits_summary()
    if not summary:
        return _empty(go.Figure(), "Sin entregas de kits en la selección")
    provinces = [row["provincia"] for row in summary]
    total = sum(row["kits"] for row in summary)
    peak = max(row["kits"] for row in summary) or 1
    fig = go.Figure() if compact else make_subplots(rows=1, cols=2, shared_yaxes=True, column_widths=[0.42, 0.58],
                                                     horizontal_spacing=0.035)
    where = {} if compact else dict(row=1, col=1)
    xs, ys = [], []
    for row in summary:
        xs += [0, row["kits"], None]
        ys += [row["provincia"], row["provincia"], None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=theme.LILA_200, width=2.2), hoverinfo="skip", showlegend=False),
                  **where)
    fig.add_trace(go.Scatter(
        x=[row["kits"] for row in summary], y=provinces, mode="markers+text", showlegend=False, cliponaxis=False,
        marker=dict(size=12, color=theme.MORADO, line=dict(color="#FFFFFF", width=2)),
        text=[f"  <b>{ui.number(row['kits'])}</b> · {_share(row['kits'], total)}" for row in summary], textposition="middle right",
        textfont=dict(size=11.5, color=theme.TINTA),
        customdata=[[ui.number(row["kits"]), ui.number(row["familias"]), _n(row["registros"], "entrega"), _share(row["kits"], total)]
                    for row in summary],
        hovertemplate=("<b>%{y}</b><br>%{customdata[0]} kits · %{customdata[3]} del total<br>%{customdata[1]} núcleos familiares "
                       "reportados<br>%{customdata[2]}<extra></extra>")), **where)
    height = 27 * len(provinces) + 76
    if compact:
        # On phones the longest names take two lines and the figures keep room at the right of their dots.
        charts.base(fig, height + 12, dict(l=8, r=8, t=8, b=8))
        fig.update_xaxes(visible=False, range=[0, peak * 2.25])
        fig.update_yaxes(tickvals=provinces, ticktext=[_two_lines(p) for p in provinces])
    else:
        kits = r.kits.assign(dia=pd.to_datetime(r.kits.fecha))
        sizeref = 2.0 * float(kits.kits.max() or 1) / (34 ** 2)
        fig.add_trace(go.Scatter(
            x=kits.dia, y=kits.provincia, mode="markers", showlegend=False,
            marker=dict(size=kits.kits, sizemode="area", sizeref=sizeref, sizemin=4, color=theme.VIOLETA_500, opacity=0.72,
                        line=dict(color="#FFFFFF", width=1)),
            customdata=[[ui._date_text(d), c, ui.number(k), ui.number(f or 0)] for d, c, k, f in
                        zip(kits.dia, kits.canton, kits.kits, kits.familias)],
            hovertemplate=("<b>%{y}</b> · %{customdata[1]}<br>%{customdata[0]}<br>%{customdata[2]} kits · %{customdata[3]} núcleos "
                           "familiares reportados<extra></extra>")), row=1, col=2)
        start, end = kits.dia.min() - pd.Timedelta(days=3), kits.dia.max() + pd.Timedelta(days=3)
        ticks = list(pd.date_range(kits.dia.min().normalize(), kits.dia.max(), freq="14D"))
        charts.base(fig, height, dict(l=8, r=12, t=40, b=30))
        fig.update_xaxes(visible=False, range=[0, peak * 1.62], row=1, col=1)
        fig.update_xaxes(range=[start, end], tickvals=ticks, ticktext=[f"{t.day} {ui._MONTHS_SHORT[t.month - 1]}" for t in ticks],
                         showgrid=True, gridcolor="#F1EEF6", tickfont=dict(size=11), row=1, col=2)
        if r.since >= start:
            fig.add_vline(x=r.since, line=dict(color=theme.ORO, width=1.4, dash="dot"), row=1, col=2)
            fig.add_annotation(x=r.since, y=1.0, xref="x2", yref="paper", text="Inicio del período reportado", showarrow=False,
                               xanchor="left", yanchor="bottom", font=dict(size=11, color=theme.ORO_700))
        fig.add_annotation(x=0, y=1.0, xref="paper", yref="paper", text="<b>Total por provincia</b>", showarrow=False, xanchor="left",
                           yanchor="bottom", font=dict(size=12, color=theme.MORADO_900))
    fig.update_yaxes(categoryorder="array", categoryarray=provinces[::-1], tickfont=dict(size=12), showgrid=False)
    return fig


def bonus_strips(r: Response, compact: bool = False) -> go.Figure:
    """Each stage of the bonus as a 100 % strip split by province: managed payments (families) and cases in articulation
    (people).  Stages keep their own unit and are never added.  On phones (``compact``) each stage is named above its
    bar instead of at its left."""
    stages = [("Pago gestionado", r.managed, "núcleos familiares"), ("En articulación", r.articulation, "personas")]
    stages = [(name, frame, unit) for name, frame, unit in stages if not frame.empty]
    fig = go.Figure()
    if not stages:
        return _empty(fig, "Sin registros del bono en la selección")
    labels = [f"<b>{name}</b><br><span style='color:{theme.PIZARRA}'>{ui.number(frame.personas.sum())} {unit} · "
              f"USD {ui.number(frame.monto.sum(), 2)}</span>" for name, frame, unit in stages]
    weight = pd.concat([frame.groupby("provincia").personas.sum() / frame.personas.sum() for _n_, frame, _u in stages]).groupby(level=0).sum()
    for province in weight.sort_values(ascending=False).index:
        color = PROVINCE_TONES.get(province, theme.LILA_200)
        shares, texts, custom = [], [], []
        for (name, frame, unit), label in zip(stages, labels):
            part = frame.loc[frame.provincia.eq(province)]
            value, amount = int(part.personas.sum()), float(part.monto.sum())
            share = value / frame.personas.sum() * 100 if value else 0
            shares.append(share)
            texts.append(f"<b>{province}</b><br>{ui.number(value)}" if share >= 13 else (f"{ui.number(value)}" if share >= 5 else ""))
            custom.append([province, f"{ui.number(value)} {unit}", f"USD {ui.number(amount, 2)}", ui.pct(share), name])
        fig.add_trace(go.Bar(
            y=labels, x=shares, orientation="h", name=province, marker=dict(color=color, line=dict(color="#FFFFFF", width=2.5)),
            text=texts, textposition="inside", insidetextanchor="middle", textfont=dict(size=12, color=_ink(color)), customdata=custom,
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[4]}<br>%{customdata[1]} · %{customdata[3]}<br>%{customdata[2]}<extra></extra>"))
    fig.update_xaxes(visible=False, range=[0, 100])
    fig.update_yaxes(categoryorder="array", categoryarray=labels[::-1], tickfont=dict(size=12.5))
    if compact:
        for position, label in enumerate(labels[::-1]):
            fig.add_annotation(x=0, xref="paper", y=position + 0.3, text=label, showarrow=False,
                               xanchor="left", yanchor="bottom", align="left", font=dict(size=12, color=theme.MORADO_900))
        charts.base(fig, 128 * len(stages) + 120, dict(l=4, r=4, t=8, b=8))
        fig.update_yaxes(showticklabels=False, range=[-0.5, len(stages) - 0.5 + 0.55])
        fig.update_layout(barmode="stack", bargap=0.5, uniformtext=dict(minsize=10, mode="hide"),
                          legend=dict(orientation="h", y=-0.04, yanchor="top", x=0, traceorder="normal", font=dict(size=12)))
        return fig
    charts.base(fig, 92 * len(stages) + 96, dict(l=8, r=8, t=8, b=8))
    fig.update_layout(barmode="stack", bargap=0.42, uniformtext=dict(minsize=10, mode="hide"),
                      legend=dict(orientation="h", y=-0.08, yanchor="top", x=0, traceorder="normal"))
    return fig


def plan_panel(r: Response) -> None:
    """The national plan of the bonus for El Niño 2026–2027: three figures in one gold panel."""
    plan = r.plan
    rows = [("users", ui.number(plan["personas"]), "personas potenciales"),
            ("layers", ui.number(plan["nucleos"]), "núcleos familiares potenciales"),
            ("banknote", f"USD {ui.number(plan['monto'], 2)}", "inversión estimada")]
    items = "".join(f'<li><span class="pp-icon">{ui.icon(symbol, 20)}</span><div><b>{ui._esc(value)}</b><small>{ui._esc(label)}</small></div></li>'
                    for symbol, value, label in rows)
    st.markdown(f'<div class="plan-panel"><ul>{items}</ul><p>Proyección nacional del bono de contingencia · planificación, no '
                f'ejecución.</p></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------------------------------- tables
def alerts_table(r: Response) -> None:
    rows = [{**row, "lugar": row["provincia"], "sub_lugar": row["canton"], "ua": row["unidad"] or "—",
             "sub_ua": " · ".join(x for x in [f"UA {row['codigo_ua']}" if row["codigo_ua"] else "", row["servicio"]] if x)}
            for row in r.alerts.sort_values(["fecha", "codigo"], ascending=[False, False]).to_dict("records")]
    ui.rich_table([{"key": "codigo", "label": "Alerta", "kind": "code", "sub": "fecha_texto"},
                   {"key": "ua", "label": "Unidad de atención", "kind": "strong", "sub": "sub_ua"},
                   {"key": "lugar", "label": "Territorio", "sub": "sub_lugar", "nowrap": True},
                   {"key": "afectacion_servicio", "label": "Afectación al servicio"},
                   {"key": "estado", "label": "Estado", "kind": "pill", "tones": STATUS_TONES},
                   {"key": "prioridad", "label": "Prioridad", "kind": "pill", "tones": PRIORITY_TONES}],
                  [{**row, "fecha_texto": ui._date_text(row["fecha"]) if pd.notna(row["fecha"]) else str(row.get("fecha_texto", "Sin fecha diaria"))} for row in rows], min_width=980)


def kits_detail(r: Response) -> None:
    """The scope of the kits figures and every Kobo delivery behind them."""
    with st.expander(f"Detalle de las {r.kit_records} entregas Kobo"):
        rows = r.kits.sort_values(["fecha", "kits"], ascending=[True, False]).to_dict("records")
        ui.rich_table([{"key": "fecha", "label": "Fecha", "kind": "date"}, {"key": "provincia", "label": "Provincia", "kind": "strong"},
                       {"key": "canton", "label": "Cantón"}, {"key": "kits", "label": "Kits", "kind": "bar"},
                       {"key": "familias", "label": "Núcleos familiares reportados", "kind": "num"}], rows,
                      total={"fecha": None, "provincia": "Total", "canton": _n(r.kit_records, "entrega"), "kits": r.kits_total,
                             "familias": int(r.kits.familias.sum())}, height=420)


def suspended_table(r: Response) -> None:
    rows = [{**g, "canton": g["canton"] or "—", "names": g["names"] or "—"} for g in r.suspended_groups()]
    ui.rich_table([{"key": "province", "label": "Provincia", "kind": "strong", "nowrap": True}, {"key": "canton", "label": "Cantón", "nowrap": True},
                   {"key": "service", "label": "Servicio"}, {"key": "units", "label": "UA suspendidas", "kind": "num"},
                   {"key": "names", "label": "Unidades identificadas"}], rows,
                  total={"province": "Total", "units": r.closed_units}, min_width=760)
