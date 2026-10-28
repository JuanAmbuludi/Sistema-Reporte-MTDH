"""Informe de Gestión Institucional: everything the Ministry delivered in a period, with the structure of the monthly
executive report (one block per section: key figures, its chart, its table and its findings).

Two periods: January to the latest month of the year, and the government period (from November 2023).  The cover
carries the eight key figures and the table of deliveries; the sections follow in the order of the dashboard and the
highlights of the period close the document.
"""
from __future__ import annotations

import logging
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.pdfgen import canvas as pdf_canvas

from src import theme
from src.data import MONTHS
from .context import INSTITUTION, PRODUCT, millions, number, stamp

LOG = logging.getLogger(__name__)
GOVERNMENT_START = "2023-11"
TITLES = {"anual": "Informe de Gestión Institucional", "gobierno": "Informe de Gestión del Periodo de Gobierno"}


def _month(period_id: str) -> str:
    return f"{MONTHS[int(period_id[5:7]) - 1]} de {period_id[:4]}"


def _short(period_id: str, yearly: bool = False) -> str:
    if len(period_id) == 4:
        return period_id
    text = MONTHS[int(period_id[5:7]) - 1][:3].capitalize()
    return f"{text} {period_id[2:4]}" if yearly else text


def _within(frame: pd.DataFrame, start: str, end: str, field: str = "periodo_id") -> pd.DataFrame:
    ids = frame[field].astype(str)
    return frame.loc[ids.str.len().eq(7) & ids.ge(start) & ids.le(end)]


def _kpi(label: str, value, kind: str = "count", note: str = "", decimals: int = 1, icon: str = "chart") -> dict:
    kpi = {"label": label, "value": value, "kind": kind, "note": note, "decimals": decimals, "icon": icon}
    if kind == "money" and value is not None and value < 1e6:
        kpi["display_value"] = f"USD {number(value, 2)}"
    return kpi


def _people(value: float) -> str:
    return f"{number(value / 1e6, 2)} M" if value >= 1e6 else (f"{number(value / 1e3, 0)} mil" if value >= 1e4 else number(value))


def _money_m(value: float) -> str:
    return number(value / 1e6, 1)


def _block(key: str, label: str, icon: str, span: str, kpis: list, visual: dict | None, table: dict | None, findings: list) -> dict:
    return {"key": key, "label": label, "icon": icon, "period": span, "kpis": kpis[:4], "visual": visual, "table": table,
            "findings": [f for f in findings if f.get("text")][:2], "update": {"label": span}}


def build(bases: dict, mode: str, title: str = "") -> dict:
    from .panorama import _budget_block, _block as month_block, section_views
    data = bases["data"]
    monthly_ids = sorted(p for p in data.periodo_id.astype(str).unique() if len(p) == 7)
    end = monthly_ids[-1]
    start = f"{end[:4]}-01" if mode == "anual" else GOVERNMENT_START
    yearly = mode == "gobierno"
    span = (f"Enero a {MONTHS[int(end[5:]) - 1]} de {end[:4]}" if mode == "anual" else f"Noviembre de 2023 a {_month(end)}")
    blocks, deliveries, cover, highlights = [], [], [], []
    last = data.loc[data.periodo_id.eq(end)]

    # ------------------------------------------------------------------ transfers and services
    for section, key, label, icon, word in (("bonos_pensiones", "transferencias", "Transferencias monetarias no contributivas",
                                             "hand-coins", "Beneficiarios"),
                                            ("proteccion_integral", "servicios", "Servicios de protección social", "users", "Usuarios")):
        rows = last.loc[last.seccion.eq(section)]
        programs = rows.groupby("programa", as_index=False)[["usuarios", "unidades", "presupuesto_ejecutado", "presupuesto_codificado",
                                                             "monto_gobierno"]].sum(min_count=1)
        programs = programs.loc[programs.usuarios.fillna(0).gt(0) | (yearly & programs.monto_gobierno.fillna(0).gt(0))]
        total_people = float(programs.usuarios.sum())
        programs["participacion"] = programs.usuarios / total_people * 100 if total_people else 0
        programs["ejecucion"] = programs.presupuesto_ejecutado / programs.presupuesto_codificado.where(programs.presupuesto_codificado > 0) * 100
        programs = programs.sort_values("usuarios", ascending=False)
        accrued, coded = float(programs.presupuesto_ejecutado.sum()), float(programs.presupuesto_codificado.sum())
        points = data.loc[data.seccion.eq(section)].groupby("periodo_id").usuarios.sum()
        keep = [p for p in sorted(points.index) if (len(p) == 7 and start <= p <= end) or (yearly and len(p) == 4)]
        first = float(points[[p for p in keep if len(p) == 7][0]]) if keep else 0
        change = total_people - first
        units = float(rows.unidades.sum()) if section == "proteccion_integral" else None
        kpis = [_kpi(word, total_people, note=f"{_month(end).capitalize()} · {'+' if change >= 0 else '−'}{number(abs(change))} desde enero de {end[:4]}"),
                *([_kpi("Unidades de atención", units, note=_month(end).capitalize())] if units else []),
                _kpi(f"Presupuesto devengado {end[:4]}", accrued, "money", note=f"Enero a {MONTHS[int(end[5:]) - 1]}"),
                _kpi("Ejecución presupuestaria", accrued / coded * 100 if coded else None, "rate", note=f"Codificado: USD {_money_m(coded)} M")]
        if section == "bonos_pensiones":
            kpis.append(_kpi(f"Presupuesto acumulado 2023–{end[:4]}", float(programs.monto_gobierno.sum()), "money", note="Gestión de gobierno"))
        columns = [("Bono o pensión" if section == "bonos_pensiones" else "Servicio", "programa", None, "text"),
                   (word, "usuarios", 70, "int"), ("Participación", "participacion", 62, "pct"),
                   *([("Unidades", "unidades", 56, "int")] if section == "proteccion_integral" else []),
                   (f"Devengado {end[:4]}", "presupuesto_ejecutado", 78, "mill"), ("Ejecución", "ejecucion", 58, "pct"),
                   *([(f"Acumulado 2023–{end[:4]}", "monto_gobierno", 96, "mill")] if yearly else [])]
        leader = programs.iloc[0] if not programs.empty else None
        visual = {"kind": "columns", "title": f"{word} por " + ("periodo" if yearly else "mes"),
                  "note": "2024 y 2025: referencia anual" if yearly else "Personas", "labels": [_short(p, yearly) for p in keep],
                  "values": [float(points[p]) for p in keep],
                  "value_text": _people}
        findings = [{"icon": "award", "text": f"{leader.programa} reúne el {number(leader.participacion, 1)} % de los "
                                              f"{word.lower()}, con {number(leader.usuarios)} personas." if leader is not None else ""},
                    {"icon": "wallet", "text": f"De enero a {_month(end)} se devengaron USD {_money_m(accrued)} millones, el "
                                               f"{number(accrued / coded * 100 if coded else 0, 1)} % del presupuesto codificado."}]
        blocks.append(_block(key, label, icon, span, kpis, visual,
                             {"title": "Cobertura y presupuesto por " + ("bono y pensión" if section == "bonos_pensiones" else "servicio"),
                              "note": f"Personas de {_month(end)} · montos en millones de USD",
                              "columns": columns, "rows": programs.to_dict("records")}, findings))
        deliveries.append({"what": label if section == "bonos_pensiones" else "Servicios de protección social",
                           "detail": ("personas con bono o pensión en " if section == "bonos_pensiones" else "personas atendidas en ")
                                     + MONTHS[int(end[5:]) - 1],
                           "amount_people": total_people, "money": accrued, "money_word": "devengados",
                           "icon": "hand-coins" if section == "bonos_pensiones" else "users",
                           "context": f"{len(programs)} bonos y pensiones" if section == "bonos_pensiones" else f"{number(units)} unidades de atención"})
        cover.append(_kpi("Beneficiarios de bonos y pensiones" if section == "bonos_pensiones" else "Usuarios de servicios sociales",
                          total_people, note=_month(end).capitalize(), icon="hand-coins" if section == "bonos_pensiones" else "users"))

    # ------------------------------------------------------------------------------ El Niño (ENOS)
    try:
        from .enos_scope import response_view, bonus_scope
        risk = response_view(start, end)
        if risk is not None:
            r = risk.response
            kits = (r.kits.groupby(["provincia_codigo", "provincia"], as_index=False).agg(kits=("kits", "sum"), familias=("familias", "sum"))
                    .sort_values("kits", ascending=False))
            bono = r.articulation.groupby("provincia", as_index=False).agg(bono_familias=("personas", "sum"), bono_monto=("monto", "sum"))
            table = kits.merge(bono, on="provincia", how="outer").fillna({"kits": 0, "familias": 0, "bono_familias": 0, "bono_monto": 0})
            table = table.sort_values(["kits", "bono_familias"], ascending=False).reset_index(drop=True)
            for column in ("bono_familias", "bono_monto"):
                table[column] = table[column].where(table[column] > 0)
            province_rows = table.to_dict("records")
            province_rows.append({"provincia": "Total nacional", "kits": float(table.kits.sum()),
                                  "familias": float(table.familias.sum()), "bono_familias": float(table.bono_familias.sum()),
                                  "bono_monto": float(table.bono_monto.sum()), "selected": True})
            units = int(r.alerts.codigo_ua.dropna().astype(str).str.strip().replace("", None).dropna().nunique())
            delivered = r.managed
            delivered_people = int(delivered.personas.sum())
            delivered_amount = float(delivered.monto.sum())
            total_kits = float(r.kits_total)
            kit_provinces = int(kits.provincia_codigo.nunique())
            kit_scope = (f"{kit_provinces} provincias · registros desde {pd.Timestamp(r.kits.fecha.min()):%d/%m/%Y}"
                         if not r.kits.empty else "Sin entregas registradas en el período")
            visual = {"kind": "map_bars", "title": "Kits entregados por provincia", "note": "Cinco principales · % del total",
                      "map": {c: float(v) for c, v in zip(kits.provincia_codigo, kits.kits)},
                      "rows": [{"name": n, "value": v, "text": f"{number(v)} · {number(v / total_kits * 100, 1)} %"}
                               for n, v in zip(kits.provincia.head(5), kits.kits.head(5))]}
            kpis = [_kpi("Kits entregados", total_kits, note=kit_scope),
                    _kpi("Familias · bono de contingencia", float(r.articulation.personas.sum()), note="Habilitadas al pago · acumulado confirmado"),
                    _kpi("Monto · bono de contingencia", float(r.articulation.monto.sum()), "money", note=bonus_scope(r), decimals=2),
                    _kpi("UA con alertas registradas", units, note=f"{number(len(r.alerts))} alertas en la base para el período")]
            continuity_text = (f"{number(r.closed_units)} unidades de atención registran atención suspendida "
                               f"({r.suspension_short()})." if r.available["continuidad"] else
                               f"No hay un corte territorial de unidades suspendidas hasta el {r.end:%d/%m/%Y}.")
            first_alert = r.data.get("cobertura_registros", {}).get("alertas", {}).get("desde")
            if first_alert and pd.Timestamp(first_alert) > r.end:
                continuity_text = f"La base de alertas inicia el {pd.Timestamp(first_alert):%d/%m/%Y}, después del período. " + continuity_text
            findings = [{"icon": "calendar", "text": f"{bonus_scope(r)}. El bono se conserva como referencia y no se contabiliza como pago del período."},
                        {"icon": "shield", "text": continuity_text}]
            blocks.append(_block("riesgos", "Plan ENOS: respuesta ante el Fenómeno El Niño", "storm",
                                 r.scope_text(), kpis, visual,
                                 {"title": "Kits y bono de contingencia por provincia", "note": "Kits del período · familias reportadas por entrega · bono de referencia",
                                  "columns": [("Provincia", "provincia", None, "text"), ("Kits entregados", "kits", 78, "int"),
                                              ("Familias con kit", "familias", 78, "int"), ("Familias con bono", "bono_familias", 84, "int"),
                                              ("Monto del bono (USD)", "bono_monto", 96, "usd")],
                                  "rows": province_rows}, findings))
            deliveries += [{"what": "Kits humanitarios · Fenómeno El Niño", "detail": "kits entregados a familias afectadas",
                            "amount_people": total_kits, "money": None, "icon": "life-buoy", "context": f"{kit_provinces} provincias priorizadas"},
                           {"what": "Bono de contingencia · referencia", "detail": "familias habilitadas al pago",
                            "amount_people": float(r.articulation.personas.sum()), "money": float(r.articulation.monto.sum()),
                            "money_word": "en articulación", "icon": "hand-coins", "context": f"Acumulado al {r.cut_text('bonos')}"}]
            if not delivered.empty:
                deliveries.append({"what": "Bono de contingencia · pago gestionado", "detail": "núcleos familiares con pago gestionado",
                                   "amount_people": float(delivered_people), "money": delivered_amount, "money_word": "gestionados",
                                   "icon": "banknote", "context": f"Corte {r.cut_text('bonos_gestionados')}"})
            cover.append(_kpi("Kits entregados · Plan ENOS", total_kits, note=f"{kit_provinces} provincias", icon="life-buoy"))
            highlights.append({"icon": "life-buoy", "text": f"Ante el Fenómeno El Niño se entregaron {number(total_kits)} kits en {kit_provinces} "
                                                            f"provincias durante el período. El bono de referencia mantiene "
                                                            f"{number(r.articulation.personas.sum())} familias al {r.cut_text('bonos')}."})
    except Exception:  # noqa: BLE001 - one section without its data never stops the report
        LOG.exception("Plan ENOS sin datos para el informe de gestión")

    # --------------------------------------------------------------------- contingencies
    contingencies = bases.get("contingencies")
    if contingencies is not None and not contingencies.empty:
        rows = _within(contingencies, start, end)
        if not rows.empty:
            key = rows.periodo_id.str[:4] if yearly else rows.periodo_id
            months = rows.groupby(key).monto.sum()
            programs = rows.groupby("programa", as_index=False).agg(monto=("monto", "sum"), personas=("personas", "sum")).sort_values("monto", ascending=False)
            total = float(programs.monto.sum())
            programs["participacion"] = programs.monto / total * 100 if total else 0
            kpis = [_kpi("Monto entregado", total, "money", note=f"{len(programs)} programas")]
            for p in programs.head(3).itertuples():
                kpis.append(_kpi(p.programa, float(p.monto), "money", note=f"{number(p.personas)} pagos"))
            visual = {"kind": "columns", "title": "Monto entregado por " + ("año" if yearly else "mes"), "note": "Millones de USD",
                      "labels": [p if yearly else _short(p) for p in months.index], "values": [float(v) for v in months], "money": True}
            findings = [{"icon": "award", "text": f"{programs.iloc[0].programa} representa el {number(programs.iloc[0].participacion, 1)} % del "
                                                  f"monto de contingencias y compensaciones."},
                        {"icon": "calendar", "text": f"El mes con mayor monto fue {_month(months.idxmax()) if not yearly else months.idxmax()}, con USD "
                                                     f"{_money_m(months.max())} millones."}]
            blocks.append(_block("contingencias", "Contingencias y compensaciones", "shield", span, kpis, visual,
                                 {"title": "Monto por programa", "note": "Pagos (personas por mes) y monto en millones de USD",
                                  "columns": [("Programa", "programa", None, "text"), ("Pagos", "personas", 74, "int"),
                                              ("Monto (USD M)", "monto", 84, "mill"), ("Participación", "participacion", 70, "pct")],
                                  "rows": programs.to_dict("records")}, findings))
            deliveries.append({"what": "Contingencias y compensaciones", "detail": "pagos de bonos y compensaciones",
                               "amount_people": float(programs.personas.sum()), "money": total, "money_word": "entregados",
                               "icon": "shield", "context": f"{len(programs)} programas"})
            cover.append(_kpi("Contingencias y compensaciones", total, "money", note="Monto entregado", icon="shield"))

    # ------------------------------------------------------------------------------- youth
    try:
        from src import jovenes
        payments = _within(jovenes.payments(), start, end)
        if not payments.empty:
            phases = sorted(int(phase) for phase in payments.fase.unique())
            phase_note = ("Fase " + str(phases[0]) if len(phases) == 1 else
                          "Fases " + ", ".join(map(str, phases[:-1])) + " y " + str(phases[-1]))
            key = payments.periodo_id.str[:4] if yearly else payments.periodo_id
            months = payments.groupby(key).agg(transferencias=("transferencias", "sum"), personas=("personas", "sum"))
            last_month = payments.periodo_id.max()
            kpis = [_kpi("Transferencias acreditadas", float(payments.transferencias.sum()), note=f"{len(months)} {'años' if yearly else 'meses'} con pago"),
                    _kpi("Monto acreditado", float(payments.monto.sum()), "money", note=f"{phase_note} · acreditaciones disponibles"),
                    _kpi(f"Jóvenes con pago en {MONTHS[int(last_month[5:]) - 1]}", float(payments.loc[payments.periodo_id.eq(last_month), "personas"].sum()),
                         note=_month(last_month).capitalize())]
            visual = {"kind": "columns", "title": "Transferencias acreditadas por " + ("año" if yearly else "mes"), "note": "Meses con pago",
                      "labels": [p if yearly else _short(p) for p in months.index], "values": [float(v) for v in months.transferencias],
                      "value_text": _people}
            blocks.append(_block("jovenes", "Jóvenes en Acción", "graduation", span, kpis, visual, None,
                                 [{"icon": "graduation", "text": f"Se acreditaron {number(payments.transferencias.sum())} transferencias por USD "
                                                                 f"{_money_m(payments.monto.sum())} millones a jóvenes del programa."}]))
            deliveries.append({"what": "Jóvenes en Acción", "detail": "transferencias acreditadas a jóvenes",
                               "amount_people": float(payments.transferencias.sum()), "money": float(payments.monto.sum()),
                               "money_word": "acreditados", "icon": "graduation", "context": phase_note})
            cover.append(_kpi("Transferencias · Jóvenes en Acción", float(payments.transferencias.sum()), note=f"USD {_money_m(payments.monto.sum())} M",
                              icon="graduation"))
    except Exception:  # noqa: BLE001
        LOG.exception("Jóvenes en Acción sin datos para el informe de gestión")

    # ------------------------------------------------------------------ credit and brigades
    from src.views.area import PROCESSED
    cdh_path = PROCESSED / "cdh_territorio.parquet"
    if cdh_path.exists():
        cdh = pd.read_parquet(cdh_path)
        disbursed = _within(cdh.loc[cdh.fuente.eq("desembolso")], start, end, "periodo")
        if not disbursed.empty:
            profile_path = PROCESSED / "cdh_perfil.parquet"
            profile = _within(pd.read_parquet(profile_path), start, end, "periodo") if profile_path.exists() else pd.DataFrame()
            profile = profile.loc[profile.fuente.eq("desembolso")] if not profile.empty else profile
            women = profile.loc[profile.sexo.eq("Mujeres"), "creditos"].sum() / profile.creditos.sum() * 100 if not profile.empty else None
            months = disbursed.groupby("periodo").creditos.sum()
            bonus = disbursed.groupby("bono", as_index=False)[["creditos", "monto"]].sum().sort_values("creditos", ascending=False)
            credits, amount = float(disbursed.creditos.sum()), float(disbursed.monto.sum())
            bonus["participacion"] = bonus.creditos / credits * 100
            kpis = [_kpi("Créditos desembolsados", credits, note=f"{_month(months.index.min()).capitalize()} a {_month(months.index.max())}"),
                    _kpi("Monto desembolsado", amount, "money", note=f"USD {number(amount / credits)} por crédito"),
                    _kpi("Créditos para mujeres", women, "rate", note="Participación en los créditos"),
                    _kpi("Cartera vigente", float(cdh.loc[cdh.fuente.eq("vigente"), "creditos"].sum()),
                         note=f"USD {_money_m(cdh.loc[cdh.fuente.eq('vigente'), 'monto'].sum())} M al corte")]
            visual = {"kind": "columns", "title": "Créditos desembolsados por mes", "note": "Créditos de Desarrollo Humano",
                      "labels": [_short(p, yearly) for p in months.index], "values": [float(v) for v in months], "value_text": _people}
            blocks.append(_block("cdh", "Crédito de Desarrollo Humano", "coins", span, kpis, visual, None,
                                 [{"icon": "users", "text": f"El {number(women, 1)} % de los créditos se entregó a mujeres." if women else ""},
                                  {"icon": "coins", "text": f"Los usuarios del Bono de Desarrollo Humano recibieron el "
                                                            f"{number(bonus.iloc[0].participacion, 1)} % de los créditos."}]))
            deliveries.append({"what": "Crédito de Desarrollo Humano", "detail": "créditos desembolsados para emprender",
                               "amount_people": credits, "money": amount, "money_word": "desembolsados", "icon": "coins",
                               "context": f"{number(women, 1)} % para mujeres" if women else ""})
            cover.append(_kpi("Créditos de Desarrollo Humano", credits, note=f"USD {_money_m(amount)} M", icon="coins"))
    brigades_path = PROCESSED / "brigadas.parquet"
    if brigades_path.exists():
        brig = _within(pd.read_parquet(brigades_path), start, end, "periodo")
        if not brig.empty:
            provinces = (brig.groupby(["provincia_codigo", "provincia"], as_index=False)
                         .agg(brigadas=("periodo", "size"), atendida=("atendida", "sum")).sort_values("atendida", ascending=False))
            attended, reached = float(brig.atendida.sum()), float(brig.alcanzada.sum())
            kpis = [_kpi("Brigadas realizadas", float(len(brig)), note=f"{brig.provincia.nunique()} provincias"),
                    _kpi("Personas atendidas", attended, note=f"{number(attended / reached * 100 if reached else 0, 1)} % de las alcanzadas"),
                    _kpi("Población alcanzada", reached, note="Personas convocadas"),
                    _kpi("Personas por brigada", attended / len(brig), note="Promedio del periodo", decimals=0)]
            visual = {"kind": "map_bars", "title": "Personas atendidas por provincia", "note": "Cinco principales · % del total",
                      "map": {c: float(v) for c, v in zip(provinces.provincia_codigo, provinces.atendida) if c},
                      "rows": [{"name": r.provincia, "value": r.atendida, "text": f"{number(r.atendida)} · {number(r.atendida / attended * 100, 1)} %"}
                               for r in provinces.head(5).itertuples()]}
            blocks.append(_block("brigadas", "Brigadas sociales por el Nuevo Ecuador", "users", span, kpis, visual, None,
                                 [{"icon": "map", "text": f"{', '.join(provinces.provincia.head(3))} concentran el "
                                                          f"{number(provinces.atendida.head(3).sum() / attended * 100, 1)} % de las personas atendidas."},
                                  {"icon": "users", "text": f"Cada brigada atendió en promedio a {number(attended / len(brig))} personas."}]))
            deliveries.append({"what": "Brigadas sociales por el Nuevo Ecuador", "detail": f"personas atendidas en {number(len(brig))} brigadas",
                               "amount_people": attended, "money": None, "icon": "heart", "context": f"{brig.provincia.nunique()} provincias"})
            cover.append(_kpi("Personas atendidas en brigadas", attended, note=f"{number(len(brig))} brigadas", icon="heart"))

    # --------------------------------------------------------------- employment and budget
    views = section_views(bases)
    for key, label, icon in (("laboral", "Empleo", "briefcase"),):
        view = views.get(key)
        if view is not None:
            try:
                block = month_block(key, label, icon, view)
                if block:
                    block["update"] = {"label": f"Corte {block['update'].get('cut', block['period'])}"}
                    blocks.append(block)
                    cards = {k["label"]: k for k in block["kpis"]}
                    retirement = next((k for k in block["kpis"] if k["label"].startswith("Compensaciones jubilares")), None)
                    files = next((k for k in block["kpis"] if k["label"].startswith("Expedientes")), None)
                    if retirement and files:
                        deliveries.append({"what": "Compensaciones jubilares", "detail": "expedientes de jubilación pagados",
                                           "amount_people": files["value"], "money": retirement["value"], "money_word": "pagados",
                                           "icon": "briefcase", "context": "Exservidores y extrabajadores públicos"})
            except Exception:  # noqa: BLE001
                LOG.exception("Empleo sin datos para el informe de gestión")
    budget = _budget_block(views)
    if budget:
        budget["label"] = "Presupuesto institucional"
        budget["update"] = {"label": f"Año fiscal {end[:4]} · corte {_month(end)}"}
        blocks.append(budget)
    accrued_total = sum(d["money"] or 0 for d in deliveries[:2])
    priority = ["Transferencias", "Servicios", "Kits", "Bono de contingencia", "Brigadas",
                "Crédito", "Jóvenes", "Contingencias", "Compensaciones"]
    deliveries.sort(key=lambda d: next((i for i, word in enumerate(priority) if d["what"].startswith(word)), len(priority)))
    cover.insert(2, _kpi(f"Presupuesto devengado {end[:4]}", accrued_total, "money", note="Transferencias y servicios", icon="banknote"))
    # The order of the report: coverage first, then El Niño and the brigades, then credit, contingencies, youth and employment.
    order = ["transferencias", "servicios", "riesgos", "brigadas", "cdh", "jovenes", "laboral", "contingencias", "presupuesto"]
    blocks.sort(key=lambda b: order.index(b["key"]) if b["key"] in order else len(order))
    by_key = {b["key"]: b for b in blocks}
    picks = [("transferencias", 0), ("servicios", 0), ("brigadas", 0), ("cdh", 0), ("contingencias", 0)]
    highlights = [*highlights, *[by_key[k]["findings"][i] for k, i in picks if k in by_key and len(by_key[k]["findings"]) > i]][:4]
    generated_at, generated_label = stamp()
    label = TITLES[mode]
    return {"kind": "gestion", "title": (title or label)[:100], "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}",
            "generated_at": generated_at, "generated_label": generated_label, "period_label": span, "territory_label": "Nacional",
            "programs_label": f"{len(blocks)} secciones del Ministerio", "module_label": label, "share_word": "",
            "update": {"line": f"Información de {span.lower()} · referencias con corte propio"},
            "kpis": cover[:8], "deliveries": deliveries, "blocks": blocks, "highlights": highlights, "mode": mode}


# --------------------------------------------------------------------------------------------------- drawing
TONES = [theme.MORADO, theme.ORO, theme.VIOLETA_500, theme.FUCSIA]


def _money(value) -> str:
    if not value:
        return ""
    return f"USD {millions(value, 1)} M" if value >= 1e6 else f"USD {number(value, 2)}"


def _deliveries(c, items: list[dict], x: float, top: float, width: float, height: float = 98, gap: float = 11) -> float:
    """What was delivered, as an infographic: one card per delivery with its icon, its figure, what it counts and its amount."""
    from reportlab.lib.colors import HexColor as C
    from .pdf import _badge
    columns = 2
    w = (width - gap) / columns
    for index, item in enumerate(items):
        row, col = divmod(index, columns)
        bx, by = x + col * (w + gap), top - row * (height + gap)
        tone = TONES[index % len(TONES)]
        c.setFillColor(C(theme.LILA_50))
        c.roundRect(bx, by - height, w, height, 10, stroke=0, fill=1)
        c.setFillColor(C(tone))
        c.roundRect(bx, by - height, 3.2, height, 1.6, stroke=0, fill=1)
        _badge(c, item.get("icon", "chart"), bx + 28, by - height / 2, 17, fill=C(tone))
        tx, room = bx + 56, w - 66
        c.setFillColor(C(theme.PIZARRA))
        size = 7.2
        while size > 5.8 and c.stringWidth(item["what"], "Text-Semi", size) > room:
            size -= 0.2
        c.setFont("Text-Semi", size)
        c.drawString(tx, by - 19, item["what"])
        figure = number(item["amount_people"])
        c.setFillColor(C(theme.MORADO_900))
        c.setFont("Display-Bold", 22)
        c.drawString(tx, by - 44, figure)
        c.setFillColor(C(theme.TINTA))
        size = 7.8
        while size > 6 and c.stringWidth(item["detail"], "Text", size) > room:
            size -= 0.2
        c.setFont("Text", size)
        c.drawString(tx, by - 58, item["detail"])
        money = _money(item.get("money"))
        line = " ".join(part for part in (money, item.get("money_word", "") if money else "") if part)
        context = item.get("context") or ""
        c.setFont("Text-Semi", 7.6)
        c.setFillColor(C(theme.ORO_700))
        c.drawString(tx, by - 76, line)
        if context:
            used = c.stringWidth(line + ("   " if line else ""), "Text-Semi", 7.6)
            c.setFillColor(C("#6E6880"))
            size = 7
            separate = c.stringWidth(context, "Text", size) > room - used
            if separate:
                used = 0
            while size > 6 and c.stringWidth(context, "Text", size) > room - used:
                size -= 0.2
            c.setFont("Text", size)
            c.drawString(tx + used, by - (88 if separate else 76), context)
    rows = (len(items) + columns - 1) // columns
    return top - rows * (height + gap)


def _highlights(c, items: list[dict], x: float, top: float, width: float, gap: float = 10, measure: bool = False) -> float:
    """The highlights of the period in two columns of boxes, each with its icon."""
    from reportlab.lib.colors import HexColor as C
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape
    from .pdf import _badge
    style = ParagraphStyle("hl", fontName="Text", fontSize=8.2, leading=11.2, textColor=C(theme.TINTA))
    w = (width - gap) / 2
    y = top
    for start in range(0, len(items), 2):
        pair = items[start:start + 2]
        paragraphs = [Paragraph(escape(item["text"]), style) for item in pair]
        sizes = [para.wrap(w - 46, 120)[1] for para in paragraphs]
        box = max(44, max(sizes) + 18)
        if not measure:
            for k, (item, para, h) in enumerate(zip(pair, paragraphs, sizes)):
                bx = x + k * (w + gap)
                c.setFillColor(C(theme.LILA_50))
                c.roundRect(bx, y - box, w, box, 8, stroke=0, fill=1)
                _badge(c, item["icon"], bx + 20, y - box / 2, 11.5)
                para.drawOn(c, bx + 38, y - box / 2 - h / 2 + 1)
        y -= box + 7
    return y


def generate(ctx: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from .charts import emblem_png
    from .panorama import _block_height, _draw_block
    from .pdf import BOTTOM, H, M, W, _band, _footer, _heading, _slim_band
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle(ctx["title"])
    c.setAuthor(ctx["institution"])
    c.setSubject(ctx["period_label"])
    c.setCreator(PRODUCT)
    width = W - 2 * M
    highlights_h = 30 - _highlights(c, ctx["highlights"], M, 0, width, measure=True)
    # Plan: the cover tells what was delivered; the sections follow; the highlights close the report.
    pages, current, room = [[]], [], H - 78 - 20 - BOTTOM
    for block in ctx["blocks"]:
        height = _block_height(block, width)
        if height > room and current:
            pages.append(current)
            current, room = [], H - 78 - 20 - BOTTOM
        current.append(block)
        room -= height
    pages.append(current)
    closing_page = room < highlights_h
    total = len(pages) + (1 if closing_page else 0)

    def blank():
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)

    for number_, blocks in enumerate(pages, start=1):
        blank()
        if number_ == 1:
            y = _band(c, ctx, H, emblem_png(), kind_label="Ministerio de Trabajo y Desarrollo Humano") - 26
            since = ctx["period_label"].lower().replace(" a ", " hasta ", 1)
            _heading(c, f"Gestión realizada desde {since}", M, y, width, "Cada entrega con su cantidad y su monto")
            _deliveries(c, ctx["deliveries"], M, y - 22, width)
        else:
            y = _slim_band(c, ctx, ctx["title"], ctx["period_label"]) - 20
        for block in blocks:
            y = _draw_block(c, block, M, y, width)
        if number_ == len(pages) and not closing_page:
            _heading(c, "Aspectos destacados del periodo", M, y, width)
            _highlights(c, ctx["highlights"], M, y - 20, width)
        _footer(c, ctx, number_, total)
        c.showPage()
    if closing_page:
        blank()
        y = _slim_band(c, ctx, ctx["title"], ctx["period_label"]) - 26
        _heading(c, "Aspectos destacados del periodo", M, y, width)
        _highlights(c, ctx["highlights"], M, y - 20, width)
        _footer(c, ctx, total, total)
        c.showPage()
    c.save()
    return out.getvalue()
