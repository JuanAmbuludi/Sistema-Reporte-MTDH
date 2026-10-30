"""Report snapshots of the areas with their own structure: contingencies and compensation, Jóvenes en Acción, labour
management (SGDE) and the approved social budget.

Each snapshot is built from the view on screen (period, programs, territory and level already chosen), so the executive
summary, the slides and the data workbook print exactly what the reader sees.  The key figures are the cards of the
dashboard, the findings are written for an authority and every snapshot carries the cut, the update and the frequency
of its information.
"""
from __future__ import annotations

import pandas as pd

from src.indicators import AREAS
from src.names import key
from .context import INSTITUTION, MONTHS, millions, number, stamp

LEVEL_LABELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}
LEVEL_PLURALS = {"provincia": "Provincias", "canton": "Cantones", "parroquia": "Parroquias"}
SGDE = "https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano"
REGIMES = {"LOEI": "Educación Intercultural (LOEI)", "LOSEP": "Servicio Público (LOSEP)", "LOSE": "Servicio Exterior (LOSE)",
           "Código del Trabajo": "Código del Trabajo"}
SHORT_GROUPS = {"Transferencias o donaciones corrientes": "Transferencias corrientes",
                "Transferencias o donaciones para inversión": "Transferencias para inversión",
                "Otros egresos corrientes": "Otros egresos corrientes"}
SHORT_CRITERIA = {"beneficiarios": "Beneficiarios", "habilitados": "Personas habilitadas", "acreditados": "Con pago acreditado"}


# ------------------------------------------------------------------------------------------------- helpers
def num(value) -> float | None:
    """A plain float, or ``None`` for a missing value."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if value != value else value


def pct(value) -> str:
    return "—" if value is None or value != value else f"{number(value, 1)} %"


def month_label(period_id: str, *, short: bool = False) -> str:
    """«septiembre de 2026» · «Sep 26»."""
    year, month = period_id.split("-")
    name = MONTHS[int(month)]
    return f"{name[:3].capitalize()} {year[2:]}" if short else f"{name} de {year}"


def short_period(start: object, end: object) -> str:
    """«dic 2024 – ago 2025» · «desde jun 2026»."""
    def short(value: str) -> str:
        year, month = str(value).split("-")[:2]
        return f"{MONTHS[int(month)][:3]} {year}"
    if not isinstance(start, str) or not start:
        return ""
    return f"{short(start)} – {short(end)}" if isinstance(end, str) and end else f"desde {short(start)}"


def note(kpis: list[dict], index: int, text: str, label: str | None = None) -> None:
    """The short caption (and label) a key figure carries in the documents."""
    if index < len(kpis):
        kpis[index]["note"] = text
        if label:
            kpis[index]["label"] = label


def span_text(period: dict) -> str:
    """«enero a septiembre de 2026» · «enero de 2026»."""
    month = period.get("month") or 12
    return f"enero a {MONTHS[month]} de {period['year']}" if month > 1 else f"enero de {period['year']}"


def kpis_from_cards(cards: list[dict]) -> list[dict]:
    """The key figures of the dashboard as the documents print them (money in USD, rates in percent)."""
    out = []
    for index, card in enumerate(cards):
        value = num(card.get("value"))
        if card.get("suffix") == "%":
            kind = "rate"
        elif card.get("prefix") == "USD":
            kind = "money"
            value = value * 1_000_000 if value is not None and card.get("suffix") == "millones" else value
        else:
            kind = "count"
        # Documents print the short form of a rate's caption: «87,8 % del aprobado» (the amount travels in the findings).
        note = card.get("note") or (card.get("bar_label") or "").split(" (")[0]
        out.append({"key": f"k{index}", "label": card["label"], "value": value, "kind": kind, "icon": card.get("icon", "chart"),
                    "share": num(card.get("share")), "note": note, "decimals": card.get("decimals", 1), "bar": num(card.get("bar")),
                    "tone": card.get("tone")})
    return out


def _base(view, kind: str, title: str, *, label: str | None = None) -> dict:
    period = view.period
    generated_at, generated_label = stamp()
    label = label or view.label
    update = view.update_stamp() if hasattr(view, "update_stamp") else {}
    return {
        "kind": kind, "module_id": view.id, "module_label": label, "title": str(title or label)[:100],
        "period_id": period["id"], "period_label": period["label"], "year": period["year"], "month": period.get("month"),
        "territory_label": view.territory_label, "programs_label": view.programs_label,
        "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}", "generated_at": generated_at,
        "generated_label": generated_label, "update": update,
    }


def _ranked(rows: list[dict], key: str, *, limit: int | None = None, money: bool = False, unit: str = "") -> list[dict]:
    """Rows for the bars of a document: name, figure text and the bar length relative to the largest."""
    rows = rows[:limit] if limit else rows
    peak = max([(r.get(key) or 0) for r in rows] or [1]) or 1
    out = []
    for row in rows:
        value = row.get(key)
        text = f"USD {millions(value, 1)} M" if money else (f"{number(value)} {unit}".strip() if value is not None else "—")
        out.append({**row, "text": text, "fraction": (value or 0) / peak})
    return out


# ------------------------------------------------------------------------------------------ contingencies
def _contingency_places(view, program: str, level: str, limit: int | None = None) -> list[dict]:
    """Every place of a level with bonuses enabled in the year (largest first); ``limit`` keeps the leading ones."""
    from src import territory
    frame = view.place_values(program, level)
    if frame.empty:
        return []
    rows = []
    for row in (frame.head(limit) if limit else frame).itertuples():
        canton = getattr(row, "canton_nombre", None) if level == "parroquia" else None
        rows.append({"code": str(row.codigo), "name": str(row.etiqueta), "place": str(row.nombre), "detail": str(row.detalle),
                     "province": str(row.provincia_nombre), "canton": territory.short_canton(str(canton)) if isinstance(canton, str) else "",
                     "records": num(row.registros), "people": num(row.beneficiarios), "amount": num(row.monto), "share": num(row.participacion)})
    return rows


def _contingency_map(view, program: str, level: str) -> dict:
    """Bonuses enabled in the year by map unit (parishes through their polygons)."""
    whole = view.place_values(program, level)
    if whole.empty:
        return {}
    if level == "parroquia":
        from src import territory
        frame = whole.rename(columns={"codigo": "parroquia_codigo", "nombre": "parroquia", "canton_nombre": "canton"})
        frame["provincia_codigo"] = frame.parroquia_codigo.astype(str).str[:2]
        values, _members = territory.polygon_values(frame.assign(registros=frame.registros.astype(float)), "registros")
        return values
    return {str(c): float(v) for c, v in zip(whole.codigo, whole.registros) if pd.notna(v)}


def contingency_context(view, *, title: str) -> dict:
    """Snapshot of contingencies and compensation: people of each program, the year month by month, territory and budget."""
    from src import contingencias as source
    from src.views.contingencias import COMPENSATION, CONTINGENCY, MAP_PROGRAMS, ORDER
    period = view.period
    ctx = _base(view, "contingencias", title)
    frame = view.program_rows()
    if frame.empty:
        raise ValueError("Los programas elegidos no registran información en este mes.")
    when = f"{MONTHS[period['month']]} de {period['year']}"
    span = view.span
    programs = []
    for row in frame.itertuples():
        programs.append({"id": row.programa_id, "name": row.programa, "full": row.nombre_oficial, "criterion": row.criterio,
                         "group": row.grupo, "people": num(row.personas), "amount": num(row.monto), "collected": num(row.cobrados),
                         "collected_amount": num(row.monto_cobrado), "month_accrued": num(row.devengado_mes),
                         "accrued": num(row.presupuesto_ejecutado), "approved": num(row.presupuesto_codificado),
                         "execution": num(row.porcentaje_ejecucion), "unit": source.PROGRAMS[row.programa_id]["unit"]})
    by_id = {p["id"]: p for p in programs}

    # The year month by month: amounts and budget of the selection, and the people of each program.
    year_rows = view.year_rows
    totals = view.budget_totals()
    approved = totals.get("approved")
    months = []
    for pid, rows in year_rows.groupby("periodo_id"):
        accrued = num(rows.devengado_acumulado.sum(min_count=1))
        months.append({"id": pid, "label": MONTHS[int(pid[5:])].capitalize(), "short": MONTHS[int(pid[5:])][:3].capitalize(),
                       "month": int(pid[5:]), "selected": pid == period["id"], "amount": num(rows.monto.sum(min_count=1)),
                       "month_accrued": num(rows.devengado_mes.sum(min_count=1)), "accrued": accrued,
                       "execution": accrued / approved * 100 if accrued is not None and approved else None,
                       "people": {p: num(v) for p, v in zip(rows.programa_id, rows.personas)},
                       "records": {p: num(v) for p, v in zip(rows.programa_id, rows.registros)},
                       "amounts": {p: num(v) for p, v in zip(rows.programa_id, rows.monto)},
                       "collected": {p: num(v) for p, v in zip(rows.programa_id, rows.cobrados)}})
    # Each program over the last twelve months up to the consultation (people are never added across months).
    history = []
    ids = [p.strftime("%Y-%m") for p in pd.period_range(end=period["id"], periods=12, freq="M")]
    for pid in ORDER:
        if view.programs and pid not in view.programs:
            continue
        rows = view.history.loc[view.history.programa_id.eq(pid)].set_index("periodo_id").personas.reindex(ids)
        values = [num(v) for v in rows]
        if len([v for v in values if v is not None]) < 2:
            continue
        meta = source.PROGRAMS[pid]
        last = max(i for i, v in enumerate(values) if v is not None)
        history.append({"id": pid, "name": meta["label"], "criterion": source.CRITERIA[meta["criterion"]], "unit": meta["unit"],
                        "short_criterion": SHORT_CRITERIA[meta["criterion"]], "labels": [month_label(i, short=True) for i in ids],
                        "values": values, "latest": values[last], "latest_label": month_label(ids[last], short=True),
                        "highlight": len(ids) - 1 if values[-1] is not None else None})

    # Territory: the bonuses enabled in the year of the program on the map, at the levels the reader chose.
    map_program = view.map_program
    level_choice = getattr(view, "report_level", "provincia")
    levels = [] if not map_program else (["provincia", "canton"] + (["parroquia"] if map_program == "CONTINGENCIAS" else [])
                                         if level_choice == "todo" else [level_choice])
    if map_program == "ANTROPICOS" and "parroquia" in levels:
        levels = [lvl for lvl in levels if lvl != "parroquia"] or ["canton"]
    territories = {lvl: _contingency_places(view, map_program, lvl) for lvl in levels}
    totals_by_level = {}
    for lvl in levels:
        whole = view.place_values(map_program, lvl)
        totals_by_level[lvl] = {"count": int(len(whole)), "records": num(whole.registros.sum()) if not whole.empty else 0.0}
    level_maps = {lvl: _contingency_map(view, map_program, lvl) for lvl in levels}
    map_level = levels[0] if levels else "provincia"
    map_values = level_maps.get(map_level, {})
    types = []
    year_places = view.year_places
    if not year_places.empty:
        enabled = year_places.loc[year_places.criterio.eq("habilitado")]
        grouped = enabled.groupby(["programa_id", "tipo_nombre"], as_index=False)[["registros", "beneficiarios", "monto"]].sum(min_count=1)
        total = grouped.registros.sum()
        for row in grouped.sort_values("registros", ascending=False).itertuples():
            types.append({"name": row.tipo_nombre, "program": MAP_PROGRAMS.get(row.programa_id, row.programa_id), "program_id": row.programa_id,
                          "records": num(row.registros), "people": num(row.beneficiarios), "amount": num(row.monto),
                          "share": row.registros / total * 100 if total else None})

    # Findings for an authority, program by program, with the criterion of each source.
    insights = []
    month_word = MONTHS[period["month"]]
    orphan = by_id.get("ORFANDAD_VIOLENCIA")
    if orphan and orphan["people"] is not None:
        before, previous_month = view.previous("ORFANDAD_VIOLENCIA")
        change = ""
        if before is not None and before != orphan["people"]:
            delta = orphan["people"] - before
            change = f", {number(abs(delta))} {'más' if delta > 0 else 'menos'} que en {previous_month}"
        amount = f" (USD {number(orphan['amount'])})" if orphan.get("amount") else ""
        insights.append({"icon": "heart", "text": f"En {month_word}, {number(orphan['people'])} niñas, niños y adolescentes en orfandad por "
                                                  f"femicidio recibieron el bono{amount}{change}."})
    cover = by_id.get("CONTINGENCIAS")
    if cover and cover["people"] is not None:
        text = f"La cobertura de contingencias habilitó a {number(cover['people'])} personas en {month_word}"
        text += f" (USD {number(cover['amount'])})" if cover.get("amount") else ""
        kinds = [t for t in types if t["program_id"] == "CONTINGENCIAS"]
        if kinds:
            whole = sum(t["records"] or 0 for t in kinds)
            lead = kinds[0]
            text += (f"; el {pct(lead['records'] / whole * 100 if whole else None)} de sus bonos del año corresponde a "
                     f"{lead['name'][:1].lower() + lead['name'][1:]}")
        insights.append({"icon": "life-buoy", "text": text + "."})
    events = by_id.get("ANTROPICOS")
    if events and events["people"] is not None:
        text = f"Los eventos naturales y antrópicos habilitaron a {number(events['people'])} personas en {month_word}"
        text += f" (USD {number(events['amount'])})" if events.get("amount") else ""
        places = _contingency_places(view, "ANTROPICOS", "provincia", limit=1)
        if places:
            text += f"; {places[0]['name']} concentra el {pct(places[0]['share'])} de los bonos del año"
        insights.append({"icon": "storm", "text": text + "."})
    if map_program and len(programs) <= 2 and levels:
        level = levels[0]
        whole = totals_by_level.get(level, {})
        places = territories.get(level, [])
        amount = sum(m["amounts"].get(map_program) or 0 for m in months)
        if whole.get("records") and places:
            insights.append({"icon": "map", "text": f"De {span} se habilitaron {number(whole['records'])} bonos de "
                                                    f"{MAP_PROGRAMS[map_program].lower()} por USD {number(amount)} en "
                                                    f"{number(whole['count'])} {LEVEL_PLURALS[level].lower()}; {places[0]['name']} concentra "
                                                    f"el {pct(places[0]['share'])}."})
    if len(programs) <= 2:
        for item in programs:
            series = [(m["label"], m["people"].get(item["id"])) for m in months if m["people"].get(item["id"]) is not None]
            if len(series) >= 3:
                peak = max(series, key=lambda pair: pair[1])
                name = item["name"][:1].lower() + item["name"][1:]
                insights.append({"icon": "trending-up", "text": f"El mes con más {item['unit']} de {name} en el año fue "
                                                                f"{peak[0].lower()} ({number(peak[1])})."})
    compensation = [by_id[p] for p in COMPENSATION if p in by_id and by_id[p]["people"] is not None]
    if compensation:
        people = sum(p["people"] for p in compensation)
        amount = sum(p["amount"] or 0 for p in compensation)
        if len(compensation) == 1:
            name = compensation[0]["name"]
            subject = f"La {name[:1].lower() + name[1:]}" if name.startswith("Compensación") else f"El programa {name}"
            verb = "acreditó"
        else:
            subject, verb = "Los mecanismos de compensación", "acreditaron"
        insights.append({"icon": "fuel", "text": f"{subject} {verb} pagos a {number(people)} personas en {month_word}, por USD "
                                                 f"{millions(amount, 2)} millones."})
    if totals:
        text = (f"El presupuesto devengado de {span} suma USD {millions(totals['accrued'])} millones, el {pct(totals['execution'])} "
                f"de los USD {millions(totals['approved'])} millones aprobados")
        relevant = [p for p in programs if p["execution"] is not None and (p["approved"] or 0) >= 1_000_000]
        if len(relevant) > 1:
            high = max(relevant, key=lambda p: p["execution"])
            text += f"; {high['name']} registra la mayor ejecución ({pct(high['execution'])})"
        insights.append({"icon": "target", "text": text + "."})
    if not insights:
        insights.append({"icon": "chart", "text": f"Los programas de la selección no registran personas en {when}."})

    cards = view.kpi_cards()
    if len(cards) > 4:
        cards = cards[:3] + [cards[-1]]
    ctx.update({
        "kpis": kpis_from_cards(cards), "programs": programs, "months": months, "history": history, "types": types,
        "territories": territories, "level_totals": totals_by_level, "levels": levels, "map_level": map_level,
        "map_values": map_values, "level_maps": level_maps, "map_program": map_program, "map_program_label": MAP_PROGRAMS.get(map_program, ""),
        "budget": totals, "span": span, "when": when, "insights": insights,
        "definitions": [
            ("Niñas, niños y adolescentes en orfandad por femicidio", "Beneficiarios del bono en el mes, por muerte violenta de la madre o progenitora."),
            ("Personas habilitadas", "Personas habilitadas en el mes para el bono de cobertura de contingencias o de eventos de origen natural o "
                                     "antrópico, por fecha de habilitación."),
            ("Bonos habilitados", "Registros de habilitación del bono; se suman en los meses del año para la lectura territorial."),
            ("Personas que cobraron", "Personas que cobraron el bono en el mes, por fecha de cobro."),
            ("Personas con pago acreditado", "Personas con al menos un pago acreditado en el mes por un mecanismo de compensación."),
            ("Presupuesto devengado y ejecución", "Devengado acumulado del año sobre el presupuesto aprobado de cada programa."),
        ],
        "sources": [("Beneficiarios, habilitaciones y cobros", "Bases del Ministerio de Trabajo y Desarrollo Humano", ""),
                    ("Pagos acreditados", "Sistema de transferencias del Ministerio", ""),
                    ("Presupuesto aprobado y devengado", "Ejecución presupuestaria del presupuesto de programas y servicios", "")],
    })
    return ctx


# --------------------------------------------------------------------------------------- Jóvenes en Acción
def youth_context(view, *, title: str) -> dict:
    """Snapshot of Jóvenes en Acción: phases, registration and enabling of the current phase, payments and budget."""
    from src import jovenes as source
    info, table = view.info, view.table
    if table.empty or not info:
        raise ValueError("La información de Jóvenes en Acción no está disponible.")
    ctx = _base(view, "jovenes", title)
    accredited = view.paid.groupby("fase").monto.sum() if not view.paid.empty else pd.Series(dtype=float)
    phases = []
    for row in table.itertuples():
        phases.append({"phase": int(row.fase), "name": row.nombre, "period": str(row.periodo_texto),
                       "period_short": short_period(row.inicio, row.fin), "registered": num(row.registrados),
                       "participants": num(row.participantes), "transfers": num(row.transferencias), "transfer_amount": num(row.monto_transferencia_usd),
                       "budget": num(row.presupuesto_usd), "execution_amount": num(row.ejecucion), "execution": num(row.porcentaje_ejecucion),
                       "accredited": num(accredited.get(row.fase)), "current": int(row.fase) == info["phase"]})
    money = view.money.loc[view.money.devengado_mes.notna()] if not view.money.empty else view.money
    budget_months = []
    for row in money.itertuples():
        budget_months.append({"id": row.periodo_id, "label": MONTHS[int(row.periodo_id[5:])].capitalize(),
                              "short": MONTHS[int(row.periodo_id[5:])][:3].capitalize(), "month": int(row.periodo_id[5:]),
                              "month_accrued": num(row.devengado_mes), "accrued": num(row.devengado_acumulado),
                              "execution": row.devengado_acumulado / row.presupuesto_aprobado * 100 if row.presupuesto_aprobado else None,
                              "selected": row.periodo_id == view.period["id"]})
    payments = []
    for row in view.paid.sort_values("periodo_id").itertuples():
        payments.append({"id": row.periodo_id, "label": month_label(row.periodo_id).capitalize(), "short": month_label(row.periodo_id, short=True),
                         "phase": int(row.fase), "people": num(row.personas), "transfers": num(row.transferencias), "amount": num(row.monto)})
    funnel = [("Registrados", info["registered"]), ("Habilitados", info["enabled"])]
    if info.get("paid_people"):
        funnel.append((f"Con pago en {MONTHS[int(info['paid_month'][5:])]}", info["paid_people"]))
    phase = info["phase_name"].lower()
    start = source.month_label(info["start"]) if info.get("start") else ""
    insights = [
        {"icon": "graduation", "text": f"La {phase} habilitó a {number(info['enabled'])} jóvenes, el {pct(info['enabled_share'])} de los "
                                       f"{number(info['registered'])} registrados{f' desde {start}' if start else ''}."},
        {"icon": "wallet", "text": f"El presupuesto de la {phase} es de USD {millions(info['budget'])} millones: {number(info['transfers'])} "
                                   f"transferencias de USD {number(info['transfer_amount'])} por joven habilitado."},
        {"icon": "banknote", "text": f"El presupuesto devengado de la fase alcanza USD {millions(info['accrued'])} millones, el "
                                     f"{pct(info['execution'])} del presupuesto de la fase, al corte de {month_label(info['cut'])}."},
    ]
    accrued_months = [m for m in budget_months if m["month_accrued"]]
    if accrued_months:
        parts = [f"{MONTHS[m['month']]} (USD {millions(m['month_accrued'])} millones)" for m in accrued_months]
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " y " + parts[-1]
        insights.append({"icon": "calendar", "text": f"El devengado de la {phase} se registró en {joined}."})
    if info.get("paid_people"):
        insights.append({"icon": "send", "text": f"En {month_label(info['paid_month'])}, {number(info['paid_people'])} jóvenes recibieron un "
                                                 f"pago acreditado por USD {millions(info['paid_amount'])} millones, el "
                                                 f"{pct(info['paid_people'] / info['enabled'] * 100 if info['enabled'] else None)} de los habilitados."})
    if info.get("accredited_total"):
        insights.append({"icon": "layers", "text": f"Las tres fases del programa suman USD {millions(info['accredited_total'])} millones en "
                                                   f"pagos acreditados a jóvenes participantes."})
    kpis = kpis_from_cards(view.kpi_cards())
    note(kpis, 1, f"{number(info['transfers'])} pagos de USD {number(info['transfer_amount'])} por joven")
    note(kpis, 2, f"{pct(info['execution'])} de ejecución")
    if info.get("paid_month"):
        paid = info["paid_month"]
        note(kpis, 3, f"USD {millions(info['paid_amount'])} M acreditados", label=f"Con pago acreditado · {MONTHS[int(paid[5:])]} {paid[:4]}")
    ctx.update({
        "kpis": kpis, "phases": phases, "budget_months": budget_months, "payments": payments,
        "funnel": funnel, "info": {k: (num(v) if isinstance(v, (int, float)) else v) for k, v in info.items()}, "insights": insights,
        "definitions": [
            ("Jóvenes registrados", "Jóvenes que se registraron para participar en la fase."),
            ("Jóvenes habilitados o participantes", "Jóvenes habilitados para recibir las transferencias de la fase (o atendidos en las fases anteriores)."),
            ("Pago acreditado", "Transferencia acreditada a la cuenta del joven en el mes; las personas no se suman entre meses."),
            ("Presupuesto devengado", "Devengado acumulado del presupuesto aprobado de la fase en curso."),
        ],
        "sources": [("Fases del programa", "Indicadores publicados por el Ministerio (SGDE)", f"{SGDE}/datos/kpis/jovenes_accion/periodos.csv"),
                    ("Pagos acreditados", "Sistema de transferencias del Ministerio", ""),
                    ("Presupuesto devengado", "Ejecución presupuestaria del presupuesto de programas y servicios", "")],
    })
    return ctx


# --------------------------------------------------------------------------------------- labour management
def labour_context(view, *, title: str) -> dict:
    """Snapshot of labour management: contracts in force by territory and profile, registrations and retirement."""
    from src import gestion_laboral as source
    from src.views.laboral import _short_branch, _short_type, place
    if not view.stock:
        raise ValueError("La información laboral no está disponible.")
    ctx = _base(view, "laboral", title)
    provinces = view.provinces or None
    stock, national, cut = view.stock, view.national_stock, view.cut
    level_choice = getattr(view, "report_level", "provincia")
    levels = ["provincia", "canton"] if level_choice == "todo" else [level_choice]
    territories = {}
    for lvl in ("provincia", "canton"):
        rows = source.by_territory(lvl, provinces)
        if lvl == "provincia":
            rows = rows.loc[rows.provincia_codigo.notna()]
        items = []
        for row in rows.itertuples():
            name = place(row.canton) if lvl == "canton" else row.provincia
            same = lvl == "canton" and key(name) in (key(row.provincia), key(row.provincia.split(" de ")[0]))
            items.append({"code": None if pd.isna(getattr(row, "canton_codigo" if lvl == "canton" else "provincia_codigo")) else
                          str(getattr(row, "canton_codigo" if lvl == "canton" else "provincia_codigo")),
                          "name": name, "province": row.provincia,
                          "detail": (name if same else f"{name} · {row.provincia}") if lvl == "canton" else name,
                          "contracts": num(row.contratos), "share": num(row.participacion),
                          "selected": bool(provinces) and lvl == "provincia" and row.provincia_codigo in provinces})
        territories[lvl] = items
    map_level = levels[0]
    map_values = {i["code"]: i["contracts"] for i in territories[map_level] if i["code"]}
    companies = source.companies_by_province(provinces=provinces)
    profile = {}
    order = {"Mujeres": 0, "Hombres": 1, "Jóvenes (18–29)": 0, "Adultos (30 y más) y otros": 1, "Adolescentes (15–17)": 2,
             "Con discapacidad": 0, "Sin discapacidad": 1}
    for column, label in (("sexo", "Sexo"), ("grupo_edad", "Grupo de edad"), ("discapacidad", "Discapacidad")):
        parts = source.by_dimension("base", column, provinces)
        parts = parts.assign(orden=parts[column].map(order).fillna(9)).sort_values("orden")
        profile[label] = [{"name": r[column], "contracts": num(r.contratos), "share": num(r.participacion)} for _i, r in parts.iterrows()]

    def dimension(name, column, top=None, short=None):
        rows = source.by_dimension(name, column, provinces, top=top)
        return [{"name": short(r[column]) if short else r[column], "full": r[column], "contracts": num(r.contratos),
                 "share": num(r.participacion)} for _i, r in rows.iterrows()]

    branches = dimension("rama", "rama_actividad", short=_short_branch)
    kinds = dimension("tipo", "tipo_contrato", short=_short_type)
    ethnicity = dimension("etnia", "etnia")
    foreign_all = source.by_dimension("nac", "nacionalidad", provinces)
    foreign = dimension("nac", "nacionalidad", top=10)
    years = view.years
    cut_date = cut.get("retirement")
    until = f" (al {cut_date.day} {MONTHS[cut_date.month][:3]}.)" if cut_date else ""
    retirement = [{"year": int(r.anio), "partial": bool(r.parcial), "files": num(r.expedientes), "amount": num(r.monto),
                   "average": num(r.promedio), "label": f"{int(r.anio)}" + (until if r.parcial else "")}
                  for r in years.itertuples()] if not years.empty else []
    regimes = source.retirement_by("regimen", view.year) if not provinces else pd.DataFrame()
    sexes = source.retirement_by("sexo", view.year) if not provinces else pd.DataFrame()
    by_province = source.retirement_by("provincia", view.year, provinces)
    retirement_parts = {
        "regimes": [{"name": REGIMES.get(r.categoria, r.categoria), "short": r.categoria, "files": num(r.expedientes), "amount": num(r.monto),
                     "share": num(r.participacion)} for r in regimes.itertuples()],
        "sexes": [{"name": r.categoria, "files": num(r.expedientes), "share": num(r.participacion)} for r in sexes.itertuples()],
        "provinces": [{"name": r.categoria, "files": num(r.expedientes), "amount": num(r.monto), "share": num(r.participacion)}
                      for r in by_province.itertuples()],
    }
    info = view.info or {}
    months = []
    if info.get("months") and not provinces:
        running = 0.0
        total = info.get("cohorts") or sum(m["value"] for m in info["months"])
        for m in info["months"]:
            running += m["value"]
            months.append({"label": m["label"], "short": m["short"], "value": num(m["value"]), "cumulative": running,
                           "share": m["value"] / total * 100 if total else None})

    # Findings.
    where = view.territory_label
    insights = []
    if provinces:
        share = stock["vigentes"] / national["vigentes"] * 100 if national.get("vigentes") else None
        insights.append({"icon": "briefcase", "text": f"{where} registra {number(stock['vigentes'])} contratos de trabajo vigentes, el "
                                                      f"{pct(share)} del total nacional, al {cut['contracts_label']}."})
    else:
        insights.append({"icon": "briefcase", "text": f"El país registra {number(stock['vigentes'])} contratos de trabajo vigentes en "
                                                      f"{number(stock['empresas'])} empresas, al {cut['contracts_label']}."})
    lead_level = "canton" if provinces and len(provinces) == 1 else "provincia"
    leaders = territories[lead_level][:3]
    if len(leaders) >= 3:
        insights.append({"icon": "map", "text": f"{leaders[0]['name']} concentra el {pct(leaders[0]['share'])} de los contratos vigentes"
                                                f"{' de la selección' if provinces else ''}; le siguen {leaders[1]['name']} "
                                                f"({pct(leaders[1]['share'])}) y {leaders[2]['name']} ({pct(leaders[2]['share'])})."})
    women = next((p for p in profile.get("Sexo", []) if p["name"] == "Mujeres"), None)
    young = next((p for p in profile.get("Grupo de edad", []) if p["name"].startswith("Jóvenes")), None)
    disabled = next((p for p in profile.get("Discapacidad", []) if p["name"] == "Con discapacidad"), None)
    if women and young:
        text = (f"Las mujeres tienen el {pct(women['share'])} de los contratos vigentes y las personas jóvenes de 18 a 29 años el "
                f"{pct(young['share'])}")
        if disabled:
            text += f"; {number(disabled['contracts'])} contratos corresponden a personas con discapacidad"
        insights.append({"icon": "users", "text": text + "."})
    if branches:
        insights.append({"icon": "factory", "text": f"{branches[0]['name']} es la rama de actividad con más contratos vigentes "
                                                    f"({pct(branches[0]['share'])}), seguida de {branches[1]['name'].lower()} "
                                                    f"({pct(branches[1]['share'])})." if len(branches) > 1 else
                                                    f"{branches[0]['name']} es la rama de actividad con más contratos vigentes."})
    if retirement:
        current = retirement[-1]
        until = f"al {cut['retirement_label']}" if current["partial"] else f"en {current['year']}"
        insights.append({"icon": "user-check", "text": f"Se compensaron {number(current['files'])} expedientes de jubilación {until}, por USD "
                                                       f"{millions(current['amount'])} millones; el promedio por expediente es de USD "
                                                       f"{number(current['average'])}."})
    if months:
        span = source.month_span(info)
        average = info.get("average")
        insights.append({"icon": "file-check", "text": f"De {span} de {info['year']} se registraron {number(info['cohorts'])} contratos que "
                                                       f"siguen vigentes; en promedio, {number(average)} por mes."})
    kpis = kpis_from_cards(view.kpi_cards())
    if not provinces:
        note(kpis, 0, f"De {number(stock['registrados'])} registrados")
    else:
        note(kpis, 1, "Empresas de la selección")
    if retirement:
        note(kpis, 3, f"USD {number(retirement[-1]['average'])} por expediente")
    ctx.update({
        "kpis": kpis, "stock": stock, "national": national, "cut": {k: v for k, v in cut.items() if isinstance(v, str)},
        "levels": levels, "map_level": map_level, "map_values": map_values, "selected": sorted(provinces or []),
        "territories": territories, "companies": [{"name": r.provincia, "companies": num(r.empresas)} for r in companies.itertuples()],
        "profile": profile, "branches": branches, "kinds": kinds, "ethnicity": ethnicity, "foreign": foreign,
        "foreign_total": num(foreign_all.contratos.sum()) if not foreign_all.empty else None,
        "retirement": retirement, "retirement_parts": retirement_parts, "retirement_year": view.year, "months": months,
        "registrations": {"year": info.get("year"), "span": source.month_span(info) if info else "", "total": num(info.get("cohorts")),
                          "average": num(info.get("average")), "observed": info.get("cohorts_label", "")},
        "share_word": "del total nacional", "insights": insights,
        "definitions": [
            ("Contratos vigentes", "Contratos de trabajo en estado vigente registrados en el Sistema Único de Trabajo, al corte diario publicado."),
            ("Empresas con contratos vigentes", "Empresas distintas que registran al menos un contrato vigente; por provincia, cada empresa se "
                                               "cuenta en cada provincia donde contrata."),
            ("Contratos registrados en el año", "Contratos registrados cada mes del año que se mantienen vigentes a la fecha de consulta."),
            ("Expedientes de jubilación", "Expedientes de compensación jubilar de exservidores y extrabajadores públicos, por año, hasta el "
                                          "corte publicado; no representan necesariamente personas únicas."),
            ("Compensaciones jubilares", "Monto pagado por compensación jubilar en el año."),
        ],
        "sources": [("Contratos vigentes, empresas y perfil", f"SGDE, corte del {cut['contracts_label']}", f"{SGDE}/MDTDH/kpi_contratos.html"),
                    ("Compensación jubilar", f"SGDE, corte del {cut['retirement_label']}", f"{SGDE}/datos/kpis/jubilados/gestion.csv")]
                   + ([("Contratos registrados por mes", f"Sistema Único de Trabajo, estado al {info['cohorts_label']}", "")] if months else []),
    })
    return ctx


# ------------------------------------------------------------------------------------------- social budget
def social_budget_context(view, *, title: str) -> dict:
    """Snapshot of the approved social budget: allocations, accrued budget of every month and execution by program."""
    period, stats = view.period, view.stats
    ctx = _base(view, "presupuesto_social", title, label=view.label)
    month_rows = view.month.sort_values("presupuesto_aprobado", ascending=False)
    total = float(month_rows.presupuesto_aprobado.sum())
    programs = [{"id": r.grupo_presupuestario, "name": r.nombre, "short": r.nombre, "group": r.grupo_gasto_nombre,
                 "approved": num(r.presupuesto_aprobado), "planned": num(r.planificado_anual), "month_accrued": num(r.devengado_mes),
                 "accrued": num(r.devengado_acumulado), "execution": num(r.porcentaje_ejecucion), "balance": num(r.saldo),
                 "share": r.presupuesto_aprobado / total * 100 if total else None} for r in month_rows.itertuples()]
    series = view.series
    months = [{"id": r.periodo_id, "label": r.mes, "short": r.mes[:3], "month": int(r.periodo_id[5:]), "month_accrued": num(r.devengado_mes),
               "accrued": num(r.devengado_acumulado), "execution": num(r.porcentaje_ejecucion), "selected": r.periodo_id == period["id"]}
              for r in series.itertuples()]
    spending = month_rows.groupby("grupo_gasto_nombre", as_index=False)[["presupuesto_aprobado", "devengado_acumulado"]].sum()
    groups = [{"name": r.grupo_gasto_nombre, "short": SHORT_GROUPS.get(r.grupo_gasto_nombre, r.grupo_gasto_nombre),
               "approved": num(r.presupuesto_aprobado), "accrued": num(r.devengado_acumulado),
               "execution": r.devengado_acumulado / r.presupuesto_aprobado * 100 if r.presupuesto_aprobado else None,
               "share": r.devengado_acumulado / stats["accrued"] * 100 if stats["accrued"] else None}
              for r in spending.sort_values("presupuesto_aprobado", ascending=False).itertuples()]
    matrix = view.year_rows.pivot_table(index="nombre", columns="periodo_id", values="devengado_mes", aggfunc="sum")
    matrix = matrix.reindex([p["name"] for p in programs])
    matrix_rows = [{"name": name, "values": [num(v) for v in values], "total": num(values.sum())} for name, values in matrix.iterrows()]
    matrix_months = [MONTHS[int(p[5:])][:3].capitalize() for p in matrix.columns]

    # The pace the remaining months need to accrue the whole approved budget, against the average month of the year.
    elapsed = period["month"]
    remaining = 12 - elapsed
    closing = None
    if remaining > 0 and stats["approved"]:
        average = stats["accrued"] / elapsed
        required = max(0.0, stats["balance"]) / remaining
        closing = {"average": average, "required": required, "remaining": remaining, "ratio": required / average * 100 if average else None,
                   "months": f"{MONTHS[elapsed + 1]} a diciembre" if remaining > 1 else "diciembre"}
        for program in programs:
            spent = program["accrued"] or 0
            program["average"] = spent / elapsed
            program["required"] = max(0.0, program["balance"] or 0) / remaining
    insights = [{"icon": "target", "text": f"El devengado de programas y servicios de {view.span} suma USD {millions(stats['accrued'])} millones, el "
                                           f"{pct(stats['execution'])} del presupuesto aprobado de USD {millions(stats['approved'])} millones; "
                                           f"el ritmo uniforme del año es del {pct(stats['pace'])}."}]
    selected = next((i for i, m in enumerate(months) if m["selected"]), None)
    if selected is not None:
        current = months[selected]
        text = f"En {MONTHS[current['month']]} se devengaron USD {millions(current['month_accrued'])} millones"
        if selected > 0 and months[selected - 1]["month_accrued"]:
            before = months[selected - 1]
            change = (current["month_accrued"] - before["month_accrued"]) / before["month_accrued"] * 100
            if abs(change) < 0.5:
                text += f", un monto similar al de {MONTHS[before['month']]} (USD {millions(before['month_accrued'])} millones)"
            else:
                text += f", {pct(abs(change))} {'más' if change > 0 else 'menos'} que en {MONTHS[before['month']]}"
        insights.append({"icon": "calendar", "text": text + "."})
    if len(programs) > 1:
        leader = programs[0]
        insights.append({"icon": "award", "text": f"{leader['name']} concentra el {pct(leader['share'])} del presupuesto aprobado y ejecuta el "
                                                  f"{pct(leader['execution'])}."})
        relevant = [p for p in programs if (p["share"] or 0) >= 2 and p["execution"] is not None]
        if len(relevant) > 1:
            high = max(relevant, key=lambda p: p["execution"])
            low = min(relevant, key=lambda p: p["execution"])
            if low is not high:
                insights.append({"icon": "trending-up", "text": f"Entre los programas de mayor peso, {high['name']} alcanza la mayor ejecución "
                                                                f"({pct(high['execution'])}) y {low['name']} la menor ({pct(low['execution'])})."})
    if closing:
        insights.append({"icon": "hourglass", "text": f"Para devengar todo el presupuesto aprobado se requieren USD {millions(closing['required'])} "
                                                      f"millones por mes de {closing['months']}, frente a un promedio de USD "
                                                      f"{millions(closing['average'])} millones por mes en lo que va del año."})
    if len(groups) > 1:
        lead = groups[0]
        insights.append({"icon": "layers", "text": f"Las {lead['name'].lower()} concentran el {pct(lead['share'])} del presupuesto devengado del "
                                                   f"año."})
    kpis = kpis_from_cards(view.kpi_cards())
    note(kpis, 0, f"Planificado: USD {millions(stats['planned'])} M")
    note(kpis, 3, f"Saldo: USD {millions(stats['balance'])} M")
    ctx.update({
        "kpis": kpis, "stats": stats, "programs": programs, "months": months, "groups": groups, "closing": closing,
        "matrix": {"months": matrix_months, "rows": matrix_rows}, "span": view.span, "insights": insights,
        "definitions": [
            ("Presupuesto aprobado", "Asignación aprobada del año para cada programa o servicio (grupos de gasto 58, 57 y 78)."),
            ("Perímetro institucional", "La fuente integra ejecución MDH de enero a julio de 2026 y MTDH desde agosto. Es distinta de la publicación fiscal SGDE."),
            ("Mecanismos de compensación", "La fuente indica que transporte, migrantes retornados y compensación diésel no son administrados por el MTDH."),
            ("Presupuesto devengado del mes", "Obligaciones de pago reconocidas en el mes."),
            ("Devengado acumulado", "Presupuesto devengado de enero al mes de la consulta."),
            ("Ejecución presupuestaria", "Devengado acumulado sobre presupuesto aprobado, en porcentaje."),
            ("Ritmo uniforme del año", "Una doceava parte del presupuesto por mes: la ejecución esperada si el gasto fuera parejo."),
            ("Saldo por devengar", "Presupuesto aprobado menos devengado acumulado."),
        ],
        "sources": [("Presupuesto aprobado y devengado", "Ejecución presupuestaria del presupuesto de programas y servicios del Ministerio", "")],
    })
    return ctx
