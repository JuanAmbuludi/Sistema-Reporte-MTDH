"""Respuesta del Ministerio ante El Niño, junto a la exposición de las unidades de atención en Riesgos.

Three actions with their own sources and cuts (see :mod:`src.enos`): reviewed alerts linked to identified MTDH units
since 14 September 2026, kits delivered (the weekend of 24–25 October) and the contingency bonus (payments managed and
cases in articulation for floods, and the national plan for El Niño 2026–2027).  Each keeps its unit: alerts are alerts,
kits are kits and bonus figures are nuclei with a managed payment or people in articulation; they are never added together.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd
import plotly.graph_objects as go

from src import charts, depuracion, enos, theme, ui

FILTERS_NOTE = ("El territorio se aplica a todas las acciones; el servicio, solo a las alertas según la UA registrada. "
                "Kits y bono no se asocian a un servicio. La planificación del bono es nacional.")
STATUS_TONES = {"Pendiente": "oro", "En seguimiento": "lila", "Resuelto": "ok"}
PRIORITY_TONES = {"Alta": "fucsia", "Media": "lila", "Baja": "gris"}


@lru_cache(maxsize=64)
def _code(province: str) -> str | None:
    return depuracion.gazetteer().province(province)


def _n(count: int, singular: str, plural: str | None = None) -> str:
    return f"{ui.number(count)} {singular if count == 1 else (plural or singular + 's')}"


def _date(value) -> str:
    return pd.Timestamp(value).strftime("%d/%m/%Y")


# Service of an alert when its unit is not in the inventory of the cut, from the wording of the source.
_SERVICE_WORDS = [(("infantil", "cnh", "creciendo", "cdi"), "DII"), (("adult",), "PAM_SERV"), (("discapacidad",), "PCD_SERV"),
                  (("protecci",), "PE"), (("acompañamiento", "acompanamiento"), "AF")]


def _service_of(text: str) -> str | None:
    words = str(text or "").lower()
    return next((program for keys, program in _SERVICE_WORDS if any(key in words for key in keys)), None)


class Response:
    """The actions of one cut of the follow-up, for the whole country and for the provinces of the consultation.

    With a service filter, the alerts keep only those of its units (the service of each unit comes from the inventory,
    or from the wording of the source when the unit is not in it); kits and the bonus have no service and keep the
    territory filter alone.
    """

    def __init__(self, data: dict, provinces=(), programs=(), unit_programs: dict | None = None):
        self.data = data
        national = enos.frames(data)
        for frame in national.values():
            frame["provincia_codigo"] = [_code(p) for p in frame.provincia]
        dates = pd.to_datetime(national["alertas"].fecha, errors="coerce")
        national["alertas"] = national["alertas"].loc[dates.between(pd.Timestamp(data["desde"]), pd.Timestamp(data["corte"]))].copy()
        if programs:
            alerts = national["alertas"]
            known = alerts.codigo_ua.astype(str).map(unit_programs or {})
            alerts["programa_id"] = known.where(known.notna(), alerts.servicio.map(_service_of))
            national["alertas"] = alerts.loc[alerts.programa_id.isin(set(programs))].copy()
        self.programs = list(programs)
        self.national = national
        chosen = set(provinces)
        self.frames = {k: (f.loc[f.provincia_codigo.isin(chosen)] if chosen else f).copy() for k, f in national.items()}
        self.alerts, self.kits = self.frames["alertas"], self.frames["kits"]
        self.managed, self.articulation = self.frames["gestionados"], self.frames["articulacion"]
        self.plan = data["bonos"]["planificacion"]
        self.cut, self.since = pd.Timestamp(data["corte"]), pd.Timestamp(data["desde"])
        self.cuts = data["cortes"]

    def count_note(self) -> str:
        confirmed = int(self.alerts.afectacion_servicio_confirmada.sum())
        parts = [f"{count} {service}" for service, count in self.alerts.groupby("servicio").size().sort_values(ascending=False).items()]
        return (f"{len(self.alerts)} alertas con {self.units} códigos UA distintos" + (": " + "; ".join(parts) if parts else "")
                + f". {confirmed} con afectación documentada y {len(self.alerts) - confirmed} por confirmar. "
                "Se excluyen los registros sin código UA; el código por sí solo no confirma una afectación.")

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
        return int(frame.provincia.nunique()), int(frame[["provincia", "canton"]].drop_duplicates().shape[0]) if "canton" in frame else 0

    def by_province(self, national: bool = False) -> pd.DataFrame:
        """Alerts, kits and bonus people (managed and in articulation) of each province, by DPA code."""
        frames = self.national if national else self.frames
        parts = [frames["alertas"].groupby("provincia_codigo").size().rename("alertas"),
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
        return f"Del {_date(self.since)} al {_date(self.cut)}"


# --------------------------------------------------------------------------------------------------- charts
def alerts_breakdown(r: Response, field: str) -> go.Figure:
    counts = r.alerts.groupby(field).size().sort_values(ascending=True)
    labels = [str(x).replace("Creciendo con Nuestros Hijos (CNH)", "Creciendo con Nuestros Hijos<br>(CNH)") for x in counts.index]
    fig = go.Figure(go.Bar(x=counts.values, y=labels, orientation="h", marker=dict(color=theme.MORADO, cornerradius=4),
                          text=counts.values, textposition="outside", cliponaxis=False,
                          hovertemplate="<b>%{y}</b><br>%{x} alertas<extra></extra>"))
    charts.base(fig, 240, dict(l=8, r=36, t=12, b=16))
    fig.update_xaxes(showgrid=False, showticklabels=False, range=[0, max(counts.max() if len(counts) else 0, 1) * 1.25])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12), categoryorder="array", categoryarray=labels)
    fig.update_layout(showlegend=False, bargap=0.4)
    return fig


def alerts_evolution(r: Response) -> go.Figure:
    """Alerts registered each day from the first day of the follow-up (columns) and their running total (step line)."""
    days = pd.date_range(r.since.normalize(), r.cut.normalize(), freq="D")
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
        fig.add_annotation(x=day, y=count, text=f"+{count}", showarrow=False, yshift=10, font=dict(size=11.5, color=theme.ORO_700))
    peak = max(int(total.iloc[-1]) if len(total) else 0, 1)
    fig.add_annotation(x=days[-1], y=total.iloc[-1] if len(total) else 0, text=f"<b>{int(total.iloc[-1]) if len(total) else 0} alertas</b>",
                       showarrow=False, xanchor="right", yshift=14, font=dict(size=12.5, color=theme.MORADO_900))
    fig.add_vline(x=days[0], line=dict(color=theme.LILA_200, width=1.2, dash="dot"))
    charts.base(fig, 260, dict(l=8, r=16, t=40, b=30))
    ticks = list(pd.date_range(days[0], days[-1], freq="7D"))
    fig.update_xaxes(range=[days[0] - pd.Timedelta(days=1), days[-1] + pd.Timedelta(days=1)], showgrid=False, tickvals=ticks,
                     ticktext=[f"{t.day} {ui._MONTHS_SHORT[t.month - 1]}" for t in ticks], tickfont=dict(size=11))
    fig.update_yaxes(range=[0, peak * 1.3], showgrid=True, gridcolor="#F1EEF6", dtick=max(1, round(peak / 4)), tickfont=dict(size=11),
                     rangemode="tozero")
    fig.update_layout(bargap=0.1, legend=dict(orientation="h", y=1.14, x=0, traceorder="normal"))
    return fig


def timeline(r: Response) -> go.Figure:
    """Alerts registered and kits delivered day by day, from the start of the follow-up to its cut."""
    rows = []
    for day, count in r.alerts.groupby("fecha").size().items():
        rows.append(("Alertas registradas", pd.Timestamp(day), int(count), f"{count} alerta" + ("" if count == 1 else "s"), theme.ORO_700))
    for day, count in r.kits.groupby("fecha").kits.sum().items():
        rows.append(("Kits entregados", pd.Timestamp(day), int(count), f"{ui.number(count)} kits", theme.VIOLETA_500))
    fig = go.Figure()
    for lane, color in [("Alertas registradas", theme.ORO), ("Kits entregados", theme.VIOLETA_500)]:
        part = [row for row in rows if row[0] == lane]
        if not part:
            continue
        peak = max(row[2] for row in part) or 1
        part.sort(key=lambda row: row[1])
        # Neighbouring days alternate their figure above and below the mark.
        positions, previous = [], None
        for row in part:
            close = previous is not None and (row[1] - previous[0]).days <= 2 and previous[1] == "top center"
            positions.append("bottom center" if close else "top center")
            previous = (row[1], positions[-1])
        fig.add_trace(go.Scatter(
            x=[row[1] for row in part], y=[lane] * len(part), mode="markers+text", text=[row[3] for row in part],
            textposition=positions, textfont=dict(size=11.5, color=theme.TINTA), cliponaxis=False,
            marker=dict(size=[14 + 22 * (row[2] / peak) ** 0.5 for row in part], color=color, line=dict(color="#FFFFFF", width=2),
                        opacity=0.95),
            customdata=[[f"{row[1].day} {ui._MONTHS_SHORT[row[1].month - 1]} {row[1].year}", row[3]] for row in part],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>", showlegend=False))
    charts.base(fig, 230, dict(l=8, r=24, t=26, b=30))
    start, end = r.since - pd.Timedelta(days=1), r.cut + pd.Timedelta(days=2)
    fig.add_vline(x=r.since, line=dict(color=theme.LILA_200, width=1.2, dash="dot"))
    fig.add_annotation(x=r.since, y=1.08, yref="paper", text="Inicio del seguimiento", showarrow=False, xanchor="left",
                       font=dict(size=11, color=theme.PIZARRA))
    ticks = list(pd.date_range(r.since, end, freq="7D"))
    fig.update_xaxes(range=[start, end], showgrid=True, gridcolor="#F1EEF6", tickvals=ticks,
                     ticktext=[f"{t.day} {ui._MONTHS_SHORT[t.month - 1]}" for t in ticks], tickfont=dict(size=11))
    fig.update_yaxes(categoryorder="array", categoryarray=["Kits entregados", "Alertas registradas"], tickfont=dict(size=12),
                     range=[-0.75, 1.7])
    return fig


# --------------------------------------------------------------------------------------------------- tables
def alerts_table(r: Response) -> None:
    rows = [{**row, "lugar": row["provincia"], "sub_lugar": row["canton"], "ua": row["unidad"] or "Sin nombre en la fuente",
             "sub_ua": " · ".join(x for x in [f"UA {row['codigo_ua']}" if row["codigo_ua"] else "", row["servicio"]] if x)}
            for row in r.alerts.sort_values(["fecha", "codigo"], ascending=[False, False]).to_dict("records")]
    ui.rich_table([{"key": "codigo", "label": "Alerta", "kind": "code", "sub": "fecha_texto"},
                   {"key": "ua", "label": "Unidad de atención", "kind": "strong", "sub": "sub_ua"},
                   {"key": "lugar", "label": "Territorio", "sub": "sub_lugar"},
                   {"key": "afectacion_servicio", "label": "Afectación al servicio"},
                   {"key": "estado", "label": "Estado", "kind": "pill", "tones": STATUS_TONES},
                   {"key": "prioridad", "label": "Prioridad", "kind": "pill", "tones": PRIORITY_TONES}],
                  [{**row, "fecha_texto": f"Registro: {ui._date_text(row['fecha'])}"} for row in rows])


def kits_table(r: Response) -> None:
    rows = r.kits.sort_values(["fecha", "kits"], ascending=[True, False]).to_dict("records")
    ui.rich_table([{"key": "fecha", "label": "Fecha", "kind": "date"}, {"key": "provincia", "label": "Provincia", "kind": "strong"},
                   {"key": "canton", "label": "Cantón"}, {"key": "kits", "label": "Kits entregados", "kind": "bar"}],
                  rows, total={"fecha": None, "provincia": "Total", "canton": f"{len(rows)} entregas", "kits": r.kits_total})


def plan_tiles(r: Response) -> None:
    plan = r.plan
    ui.focus_tile("users", "Personas potenciales", ui.number(plan["personas"]), "Proyección nacional del bono de contingencia")
    ui.focus_tile("layers", "Núcleos familiares potenciales", ui.number(plan["nucleos"]), "Proyección nacional")
    ui.focus_tile("banknote", "Inversión estimada", f"USD {ui.millions(plan['monto'], 2)} millones", "Planificación, no ejecución")
