"""Executive summary of every section of the dashboard, in three A4 pages at most.

Each section is read at its latest cut, for the whole country and every program, exactly as its own summary reads it:
a block with its cut and update, its four key figures beside a chart of its own kind (a map, bars, columns, the
threats by category or the execution against the even pace) and its two leading findings.  Sections never mix: each
block keeps its own unit, criterion and cut.  The last page closes with the cut, update and frequency of every section.
"""
from __future__ import annotations

from io import BytesIO
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Paragraph
from xml.sax.saxutils import escape

from src import corte, theme
from .areas import kpis_from_cards
from .context import INSTITUTION, PRODUCT, stamp

LOG = logging.getLogger(__name__)
SHORT = {"transferencias": "Transferencias", "servicios": "Servicios sociales", "riesgos": "ENOS", "contingencias": "Contingencias",
         "jovenes": "Jóvenes en Acción", "laboral": "Empleo", "presupuesto": "Presupuesto", "cdh": "Crédito de Desarrollo Humano",
         "brigadas": "Brigadas sociales", "ferias": "Ferias", "jovenes_fase4": "Jóvenes · Fase 4"}
TITLE = "Informe ejecutivo institucional"
SECTIONS = [
    ("transferencias", "Transferencias monetarias no contributivas", "hand-coins"),
    ("servicios", "Servicios de protección social", "users"),
    ("riesgos", "Plan ENOS: respuesta del Ministerio", "storm"),
    ("brigadas", "Brigadas sociales", "users"),
    ("cdh", "Crédito de Desarrollo Humano", "coins"),
    ("jovenes", "Jóvenes en Acción", "graduation"),
    ("jovenes_fase4", "Jóvenes en Acción · Fase 4", "graduation"),
    ("laboral", "Empleo", "briefcase"),
    ("ferias", "Ferias de Inclusión Económica, Empleabilidad y Autoempleo", "graduation"),
    # Contingencies and the budget close the report.
    ("contingencias", "Contingencias y compensaciones", "shield"),
    ("presupuesto", "Presupuesto", "landmark"),
]
MAX_PAGES = 4


def section_views(bases: dict) -> dict:
    """Fresh views of every section (the ones on screen keep the reader's selection)."""
    from src.indicators import MODULES
    from src.views.contingencias import ContingencyView
    from src.views.jovenes import YouthView
    from src.views.laboral import LabourView
    from src.views.presupuesto import BudgetView, SocialBudgetView
    from src.views.finanzas import FinanceView
    from src.views.riesgos import RiskView
    from src.views.territorial import TerritorialView
    views = {module_id: TerritorialView(module_id, bases["data"], bases["catalog"], bases["territory"], bases["program_budget"])
             for module_id in MODULES}
    views["riesgos"] = RiskView()
    if bases.get("contingency_catalog"):
        views["contingencias"] = ContingencyView(bases["contingencies"], bases["contingency_places"], bases["contingency_catalog"])
    views["jovenes"] = YouthView()
    views["laboral"] = LabourView(bases["labour"])
    if not bases["budget"].empty:
        views["presupuesto"] = (FinanceView(bases["budget"], metadata=bases["budget_manifest"])
                                 if "codificado" in bases["budget"] else BudgetView(bases["budget"], bases["budget_manifest"]))
    if not bases["social_groups"].empty:
        views["presupuesto_social"] = SocialBudgetView(bases["social_groups"], bases["social_programs"])
    if bases.get("government_budget") is not None and not bases["government_budget"].empty:
        views["presupuesto_gobierno"] = FinanceView(bases["government_budget"], government=True)
    try:
        from src.views.cdh import CreditView
        from src.views.brigadas import BrigadeView
        for key, view in (("cdh", CreditView()), ("brigadas", BrigadeView())):
            if view.catalog():
                views[key] = view
    except ImportError:  # noqa: PERF203 - the new areas are optional in older deployments
        pass
    try:
        from src.views.ferias import FairView
        fair = FairView()
        if fair.catalog():
            views["ferias"] = fair
    except ImportError:
        pass
    return views


def _latest(catalog: list[dict]) -> dict | None:
    """The latest monthly cut (annual references come after it in the catalogs)."""
    monthly = [p for p in catalog if p.get("month")]
    pool = monthly or catalog
    return max(pool, key=lambda p: str(p["id"])) if pool else None


def _visual(key: str, ctx: dict) -> dict | None:
    """One chart per section, each of its own kind, so the summary reads as a panorama and not as a wall of figures."""
    from src import names
    if key == "transferencias":
        provinces = sorted([p for p in ctx["provinces"] if p.get("people")], key=lambda p: -p["people"])
        return {"kind": "map_bars", "title": "Beneficiarios por provincia", "map": {p["code"]: p["people"] for p in ctx["provinces"]},
                "rows": [{"name": names.place(p["name"]), "value": p["people"], "text": f"{_number(p['people'])} · {_number(p['share'], 1)} %"}
                         for p in provinces[:5]], "note": "Cinco principales · % nacional"}
    if key == "servicios":
        programs = sorted([p for p in ctx["programs"] if p.get("people")], key=lambda p: -p["people"])
        return {"kind": "bars", "title": "Usuarios por servicio", "note": "Usuarios · unidades de atención",
                "rows": [{"name": p["short"], "value": p["people"], "text": f"{_number(p['people'])} · {_number(p['units'])} UA"}
                         for p in programs[:5]]}
    if key == "riesgos":
        rows = [dict(r, text=_number(r["value"])) for r in ctx["response"]["by_province"]]
        # Two columns of five rows fit the block; with more provinces, the ten with most alerts.
        note = "Diez principales · alertas registradas" if len(rows) > 10 else "Alertas y reportes registrados"
        return {"kind": "bars", "title": "Alertas por provincia", "rows": rows[:10], "note": note}
    if key == "contingencias":
        months = [m for m in ctx["months"] if m.get("amount")]
        return {"kind": "columns", "title": "Monto entregado por mes (USD)", "labels": [m["short"] for m in months],
                "values": [m["amount"] for m in months], "money": True, "note": "Todos los programas con información en el mes"}
    if key == "jovenes":
        payments = ctx["payments"][-12:]
        tones = {1: theme.LILA_300, 2: theme.VIOLETA_500, 3: theme.MORADO}
        return {"kind": "columns", "title": "Jóvenes con pago acreditado por mes", "labels": [p["short"].replace(" ", "\n") for p in payments],
                "values": [p["people"] for p in payments], "colors": [tones.get(p["phase"], theme.MORADO) for p in payments],
                "legend": [(tones[phase], f"Fase {phase}") for phase in sorted({p["phase"] for p in payments}) if phase in tones],
                "value_text": lambda v: f"{_number(v / 1000, 0)} mil" if v >= 1000 else _number(v)}
    if key == "laboral":
        rows = ctx["branches"][:5]
        peak = max([r.get("share") or 0 for r in rows] or [1]) or 1
        return {"kind": "bars", "title": "Contratos vigentes por rama de actividad", "note": "Cinco ramas principales · participación",
                "rows": [{"name": r["name"], "fraction": (r.get("share") or 0) / peak,
                          "text": f"{_number(r['contracts'])} · {_number(r['share'], 1)} %"} for r in rows]}
    if key == "presupuesto":
        if ctx.get("kind") == "presupuesto_conciliado":
            from src.views.finanzas import short
            return {"kind": "rates", "title": "Ejecución presupuestaria por programa", "note": "Devengado sobre codificado · SGDE",
                    "rows": [{"name": short(r["name"]), "fraction": (r.get("ejecucion") or 0)/100,
                              "text": f"{_number(r.get('ejecucion'), 1)} %"} for r in ctx["tables"][0]["rows"]]}
        zones = ctx["zones"]
        return {"kind": "rates", "title": "Ejecución presupuestaria por zona", "note": "Devengado sobre codificado",
                "rows": [{"name": z["short"], "fraction": (z.get("execution") or 0) / 100, "text": f"{_number(z['execution'], 1)} %"}
                         for z in zones]}
    if key == "presupuesto_gobierno":
        rows = sorted(ctx["tables"][0]["rows"], key=lambda r: -(r.get("acumulado") or 0))[:6]
        peak = max([r.get("acumulado") or 0 for r in rows] or [1]) or 1
        return {"kind": "bars", "title": "Acumulado de gobierno por programa", "note": "Seis principales · millones de USD",
                "rows": [{"name": r["name"], "fraction": (r.get("acumulado") or 0) / peak,
                          "text": f"USD {_number((r.get('acumulado') or 0) / 1e6, 1)} M"} for r in rows]}
    if key == "cdh":
        months = ctx["charts"][0]["rows"]
        return {"kind": "columns", "title": "Créditos desembolsados por mes", "note": "Créditos de Desarrollo Humano",
                "labels": [m["name"][:3] for m in months], "values": [m["value"] for m in months],
                "value_text": lambda v: f"{_number(v / 1000, 1)} mil" if v >= 1000 else _number(v)}
    if key == "brigadas":
        rows = ctx["tables"][0]["rows"][:5]
        return {"kind": "bars", "title": "Personas atendidas por provincia", "note": "Cinco principales · % del total",
                "rows": [{"name": r["provincia"], "value": r["atendida"], "text": f"{_number(r['atendida'])} · {_number(r['participacion'], 1)} %"}
                         for r in rows]}
    if key == "presupuesto_social":
        months = ctx["months"]
        return {"kind": "execution", "title": "Ejecución acumulada frente al ritmo uniforme", "labels": [m["short"] for m in months],
                "rates": [m.get("execution") for m in months], "months": [m["month"] for m in months]}
    return None


def _number(value, decimals: int = 0) -> str:
    from .context import number
    return number(value, decimals)


def _block(key: str, label: str, icon: str, view) -> dict | None:
    catalog = view.catalog()
    period = _latest(catalog)
    if period is None:
        return None
    if key == "riesgos":
        # Adding an archival alert source expands government queries; the monthly
        # overview retains the operational history it already summarized.
        operative = view._history().get("ventana_operativa", {})
        scope = {"since": operative["desde"], "until": operative["hasta"]} if operative else {}
        view.select(period, mode="periodo", **scope)
        period = view.period
    else:
        view.select(period)
    if not view.prepare():
        return None
    context = view.report_context(label)
    # The figures as the section's own summary prints them (short captions), the dashboard cards otherwise.
    kpis = [k for k in (context.get("kpis") or kpis_from_cards(view.kpi_cards())) if k.get("value") is not None]
    update = view.update_stamp() if hasattr(view, "update_stamp") else corte.stamp(view.id, period)
    if key == "riesgos":
        update = {**(update or {}), "label": view.response.scope_text()}
    findings = [i for i in context.get("insights", []) if i.get("text")]
    kpis, findings, table = _adjust(key, kpis, findings, context, view)
    kpis, findings = kpis[:4], findings[:2]
    try:
        visual = _visual(key, context)
    except Exception:  # noqa: BLE001 - a section without its chart keeps its figures and findings
        LOG.exception("Sección sin gráfico: %s", key)
        visual = None
    return {"key": key, "label": label, "icon": icon, "period": period["label"], "kpis": kpis, "findings": findings,
            "visual": visual, "table": table, "update": update or {}, "source": context.get("source", f"Fuente: {INSTITUTION}")}


def _card(label: str, value, *, money: bool = False, rate: bool = False, note: str = "", icon: str = "wallet") -> dict:
    """A key figure in the shape of the dashboard cards (money in USD, rates in percent)."""
    card = {"label": label, "value": value, "decimals": 1, "icon": icon, "note": note}
    if money:
        card.update(value=(value or 0) / 1e6, prefix="USD", suffix="millones")
    if rate:
        card["suffix"] = "%"
    return kpis_from_cards([card])[0]


def _adjust(key: str, kpis: list[dict], findings: list[dict], ctx: dict, view) -> tuple[list[dict], list[dict], dict | None]:
    """What the institutional summary says of each section beyond its own cards: units in every label, the breakdown
    of each bonus and of each sex, and no register counts that only the technical team reads."""
    from .context import millions
    table = None
    if key == "transferencias":
        rows = sorted([p for p in ctx.get("programs", []) if p.get("people")], key=lambda p: -(p["people"] or 0))
        table = {"title": "Cobertura y presupuesto por bono y pensión", "note": "Devengado y ejecución de enero al mes del corte",
                 "columns": [("Bono o pensión", "short", None, "text"), ("Beneficiarios", "people", 70, "int"),
                             ("Participación", "share", 64, "pct"), ("Devengado (USD M)", "fiscal", 84, "mill"),
                             ("Ejecución", "execution", 58, "pct")],
                 "rows": rows}
    elif key == "riesgos":
        response = getattr(view, "response", None)
        units = None
        if response is not None and "codigo_ua" in response.alerts:
            units = int(response.alerts.codigo_ua.dropna().astype(str).str.strip().replace("", None).dropna().nunique())
        delivered = response.managed if response is not None else None
        adjusted = []
        for kpi in kpis:
            label = kpi["label"]
            if label.startswith("Alertas reportadas"):
                if units is None:
                    continue
                kpi = {**kpi, "label": "Unidades de atención con alertas", "short": None, "value": units, "note": ""}
            elif label.startswith("Monto"):
                continue
            elif label.startswith("Familias") and response is not None:
                kpi = {**kpi, "note": f"USD {_number(response.articulation.monto.sum(), 2)} · acumulado al {response.cut_text('bonos')}"}
            adjusted.append(kpi)
        if delivered is not None and not delivered.empty:
            adjusted.insert(2, _card("Núcleos familiares · pago gestionado", float(delivered.personas.sum()),
                                     note=f"USD {_number(delivered.monto.sum(), 2)} gestionados", icon="hand-coins"))
        kpis = adjusted
        findings = [f for f in findings if " registros:" not in f["text"] and "reportes sectoriales" not in f["text"]]
    elif key == "contingencias":
        kpis = [{**k, "label": k["label"] if k["kind"] == "money" or k["label"].startswith("Personas") else f"Personas · {k['label'][:1].lower()}{k['label'][1:]}",
                 "short": None} for k in kpis]
    elif key == "laboral":
        sexes = (ctx.get("profile") or {}).get("Sexo") or []
        if sexes:
            table = {"title": "Contratos vigentes por sexo", "note": "Personas contratadas",
                     "columns": [("Sexo", "name", None, "text"), ("Contratos vigentes", "contracts", 96, "int"),
                                 ("Participación", "share", 72, "pct")], "rows": sexes}
    return kpis, findings, table


def _budget_block(views: dict) -> dict | None:
    """The three budgets in one block: the fiscal SGDE execution, the social budget and the government accumulation."""
    fiscal, social, government = views.get("presupuesto"), views.get("presupuesto_social"), views.get("presupuesto_gobierno")
    kpis, findings, visual, update, period = [], [], None, {}, None
    if fiscal is not None and (period := _latest(fiscal.catalog())):
        fiscal.select(period)
        if fiscal.prepare():
            stats = fiscal.stats
            kpis.append(_card(f"Presupuesto fiscal codificado {period['year']}", stats["codificado"], money=True,
                              note=f"Devengado: USD {_number(stats['devengado'] / 1e6, 1)} M"))
            kpis.append(_card("Ejecución del presupuesto fiscal", stats["ejecucion"], rate=True, note=f"SGDE, al {fiscal.cut_text}",
                              icon="target"))
            update = fiscal.update_stamp()
            findings.append({"icon": "wallet", "text": f"Presupuesto fiscal SGDE: USD {_number(stats['devengado'] / 1e6, 1)} millones devengados "
                                                       f"de USD {_number(stats['codificado'] / 1e6, 1)} millones codificados al {fiscal.cut_text}."})
    if social is not None and (social_period := _latest(social.catalog())):
        social.select(social_period)
        if social.prepare():
            stats = social.stats
            kpis.append(_card("Ejecución de programas y servicios", stats["execution"], rate=True,
                              note=f"Devengado: USD {_number(stats['accrued'] / 1e6, 1)} M", icon="target"))
            context = social.report_context("Presupuesto de programas y servicios")
            visual = _visual("presupuesto_social", context)
            if visual:
                visual["title"] = "Ejecución de programas y servicios"
            text = next((i["text"] for i in context.get("insights", []) if i.get("text")), "")
            if text:
                findings.append({"icon": "trending-up", "text": text})
            period = period or social_period
    if government is not None and (gov_period := _latest(government.catalog())):
        government.select(gov_period)
        if government.prepare():
            kpis.append(_card(f"Acumulado de gobierno 2023–{gov_period['year']}", government.stats["acumulado"], money=True,
                              note="Transferencias y servicios", icon="landmark"))
    if not kpis or period is None:
        return None
    # This block combines all three budget sources, so its revision follows
    # whichever of those sources changed most recently, not fiscal alone.
    update = corte.stamp("presupuesto", period, cut_text=update.get("cut"))
    return {"key": "presupuesto", "label": "Presupuesto", "icon": "landmark", "period": period["label"], "kpis": kpis[:4],
            "findings": findings[:2], "visual": visual, "table": None, "update": update or {}, "source": f"Fuente: {INSTITUTION}"}


def build_panorama(bases: dict, title: str) -> dict:
    views = section_views(bases)
    blocks = []
    for key, label, icon in SECTIONS:
        view = views.get(key)
        if view is None and key not in ("ferias", "jovenes_fase4"):
            continue
        try:
            if key == "ferias":
                from .ferias import latest_block
                block = latest_block()
            elif key == "jovenes_fase4":
                from .jovenes_fase4 import block as phase_four_block
                block = phase_four_block()
            else:
                block = _budget_block(views) if key == "presupuesto" else _block(key, label, icon, view)
        except Exception:  # noqa: BLE001 - one section without its data never stops the others
            LOG.exception("Sección sin resumen: %s", key)
            block = None
        if block:
            blocks.append(block)
    if not blocks:
        raise ValueError("Ninguna sección tiene información para resumir.")
    generated_at, generated_label = stamp()
    return {"kind": "panorama", "title": str(title or TITLE)[:100], "blocks": blocks,
            "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}", "generated_at": generated_at,
            "generated_label": generated_label, "period_label": "Último corte de cada sección", "territory_label": "Nacional",
            "programs_label": f"{len({b['key'].split('_fase')[0] for b in blocks})} secciones", "module_label": "Informe ejecutivo", "update": {}}


# ------------------------------------------------------------------------------------------------- drawing
BODY_H = 112    # the key figures at the left and the chart of the section at the right
SHORT_PLACES = {"Santo Domingo de los Tsáchilas": "Santo Domingo"}
KPI_W = 172


def _kpi_list(c, kpis: list[dict], x: float, top: float, width: float, height: float = BODY_H) -> None:
    """The key figures of a section, one under the other, each with its own unit and note."""
    from .pdf import C, NIGHT, PURPLE, TONES, _clip, _fit, value_text
    step = height / max(4, len(kpis))
    for index, kpi in enumerate(kpis):
        y = top - index * step
        c.setFillColor(C(TONES[index % len(TONES)]))
        c.rect(x, y - step + 5, 2.4, step - 8, stroke=0, fill=1)
        value = value_text(kpi)
        c.setFillColor(NIGHT)
        c.setFont("Display", _fit(value, "Display", 13, width - 12, 8))
        c.drawString(x + 8, y - 12.5, value)
        label = kpi.get("short") or kpi["label"]
        note = kpi.get("note") or ""
        room = width - 12
        c.setFillColor(C(theme.PIZARRA))
        size = _fit(label, "Text-Semi", 6.5, room, 5.4)
        c.setFont("Text-Semi", size)
        c.drawString(x + 8, y - 21.5, label)
        used = c.stringWidth(label + " · ", "Text-Semi", size)
        # A note reads whole or not at all (never cut with an ellipsis).
        if note and c.stringWidth(note, "Text", 6.3) <= room - used:
            c.setFillColor(PURPLE)
            c.setFont("Text", 6.3)
            c.drawString(x + 8 + used, y - 21.5, note)


def _bar_rows(c, rows: list[dict], x: float, top: float, width: float, height: float) -> None:
    """Bars with their figure; more than five rows share two columns."""
    from .pdf import _bars
    if rows and "fraction" not in rows[0]:
        peak = max([r.get("value") or 0 for r in rows] or [1]) or 1
        rows = [{**r, "fraction": (r.get("value") or 0) / peak} for r in rows]
    columns = 2 if len(rows) > 5 else 1
    # A name over its bar needs 17 points: never more rows than fit, so no name lands on the bar above it.
    fits = max(1, int((height - 10) // 17))
    # Names read whole: the province keeps its usual short name.
    rows = [{**r, "name": SHORT_PLACES.get(r["name"], r["name"])} for r in rows[:fits * columns]]
    per = (len(rows) + columns - 1) // columns
    gap = 16
    w = (width - gap * (columns - 1)) / columns
    row_h = min(19, (height - 10) / max(1, per))
    for index in range(columns):
        part = rows[index * per:(index + 1) * per]
        if part:
            _bars(c, part, x + index * (w + gap), top - 8, w, row_h)


def _draw_visual(c, visual: dict, x: float, top: float, width: float, height: float = BODY_H) -> None:
    from .charts import execution_png, map_png
    from .pdf import MUTED, NIGHT, _clip, _picture
    from .pdf_areas import _columns, _legend
    from reportlab.pdfbase import pdfmetrics
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 8.2)
    title = _clip(visual["title"], "Display-Bold", 8.2, width * 0.62)
    c.drawString(x, top - 7, title)
    legend = visual.get("legend")
    if visual["kind"] == "levels":
        from .risks import PALETTE
        from src import riesgos
        legend = [(color, level) for color, level in zip(PALETTE, riesgos.LEVELS) if level in visual["levels"]]
    if legend:
        _legend(c, legend, x + width, top - 8.5, right=True)
    elif visual.get("note"):
        c.setFillColor(MUTED)
        c.setFont("Text", 6.6)
        # The note takes the room the title leaves, so it reads whole.
        room = width - pdfmetrics.stringWidth(title, "Display-Bold", 8.2) - 14
        c.drawRightString(x + width, top - 7, _clip(visual["note"], "Text", 6.6, max(width * 0.4, room)))
    body_top, body_h = top - 16, height - 16
    kind = visual["kind"]
    if kind in ("bars", "rates"):
        _bar_rows(c, visual["rows"], x, body_top, width, body_h)
    elif kind == "map_bars":
        map_w = 118
        picture = map_png(visual["map"], layer="provincia", mode="light", legend=False, marks=False, width=map_w / 72,
                          height=body_h / 72, dpi=200)
        _picture(c, picture, x - 6, body_top + 2, map_w, body_h / map_w)
        _bar_rows(c, visual["rows"], x + map_w + 8, body_top, width - map_w - 8, body_h)
    elif kind == "levels":
        from .risks import _level_rows
        rows = visual["rows"]
        _level_rows(c, rows, x, body_top - 6, width, row_h=min(23.5, (body_h - 8) / max(1, len(rows))), bar_gap=11.5, bar_h=8.4)
    elif kind == "columns":
        _columns(c, visual["labels"], visual["values"], x - 4, body_top, width + 8, body_h, money=visual.get("money", False),
                 colors=visual.get("colors"), value_text=visual.get("value_text"), label_size=6.6)
    elif kind == "execution":
        picture = execution_png(visual["labels"], visual["rates"], visual["months"], highlight=len(visual["labels"]) - 1,
                                width=(width + 8) / 72, height=body_h / 72, dpi=220)
        _picture(c, picture, x - 4, body_top + 4, width + 8, body_h / (width + 8))


def _finding_height(text: str, width: float) -> float:
    style = ParagraphStyle("pf", fontName="Text", fontSize=7.2, leading=9.4)
    return Paragraph(escape(text), style).wrap(width - 30, 200)[1]


def _finding_width(block: dict, width: float) -> float:
    count = max(1, len(block["findings"]))
    return (width - 8 * (count - 1)) / count


def _table_height(block: dict) -> float:
    return sum(16 + 16 + 12.4 * len(table["rows"]) + 6 for table in _block_tables(block) if table["rows"])


def _block_tables(block: dict) -> list[dict]:
    return ([block["table"]] if block.get("table") else []) + block.get("tables", [])


def _block_height(block: dict, width: float) -> float:
    w = _finding_width(block, width)
    findings = max([_finding_height(f["text"], w) for f in block["findings"]] or [0])
    # A block with five key figures takes a taller body, so every figure keeps its own line.
    return _header_height(block, width) + block.get("body_h", BODY_H) + _table_height(block) + (max(28, findings + 11) + 8 if block["findings"] else 0) + 16


def _cut_text(block: dict) -> str:
    update = block["update"]
    revision = update.get("updated_short")
    if update.get("label"):
        return update["label"] + (f" · Actualizado: {revision}" if revision else "")
    cut = update.get("cut") or block["period"]
    if revision:
        return f"Corte: {cut} · Actualizado: {revision}"
    text = update.get("short") if len(cut) > 34 and update.get("short") else f"Corte: {cut}"
    frequency = update.get("frequency_short") or update.get("frequency")
    return f"{text} · {frequency}" if frequency else text


def _header_height(block: dict, width: float) -> float:
    from reportlab.pdfbase import pdfmetrics
    full_cut_w = pdfmetrics.stringWidth(_cut_text(block), "Text", 7)
    cut_w = min(width * 0.52, full_cut_w)
    title_w = pdfmetrics.stringWidth(block["label"], "Display-Bold", 10.6)
    return 36 if title_w > width - cut_w - 34 or full_cut_w > width * 0.52 else 24


def _draw_block(c, block: dict, x: float, top: float, width: float) -> float:
    """A section: its name and cut, its key figures beside its own chart, and its two leading findings."""
    from .pdf import C, INK, MUTED, NIGHT, _badge, _clip
    _badge(c, block["icon"], x + 9, top - 8, 9)
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 10.6)
    cut = _cut_text(block)
    cut_w = min(width * 0.52, c.stringWidth(cut, "Text", 7))
    extended = _header_height(block, width) == 36
    c.drawString(x + 24, top - 11.5, _clip(block["label"], "Display-Bold", 10.6, width - 24 if extended else width - cut_w - 34))
    c.setFillColor(MUTED)
    c.setFont("Text", 7)
    c.drawRightString(x + width, top - (24 if extended else 11), _clip(cut, "Text", 7, width - 24 if extended else width * 0.52))
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.7)
    c.line(x, top - (30 if extended else 18), x + width, top - (30 if extended else 18))
    body = top - (38 if extended else 26)
    body_h = block.get("body_h", BODY_H)
    if block.get("visual"):
        _kpi_list(c, block["kpis"], x, body, KPI_W, body_h)
        c.setStrokeColor(C("#ECE8F3"))
        c.line(x + KPI_W + 7, body - 2, x + KPI_W + 7, body - body_h + 4)
        _draw_visual(c, block["visual"], x + KPI_W + 16, body, width - KPI_W - 16, body_h)
    else:
        half = (width - 14) / 2
        _kpi_list(c, block["kpis"][:2], x, body, half, body_h / 2)
        _kpi_list(c, block["kpis"][2:4], x + half + 14, body, half, body_h / 2)
    y = body - body_h - 2
    for table in _block_tables(block):
        if not table["rows"]:
            continue
        from .pdf import _table
        c.setFillColor(NIGHT)
        c.setFont("Display-Bold", 8.2)
        c.drawString(x, y - 9, table["title"])
        c.setFillColor(MUTED)
        c.setFont("Text", 6.6)
        c.drawRightString(x + width, y - 9, table.get("note", ""))
        y = _table(c, x, y - 15, width, table["columns"], table["rows"], row_h=12.4, header_h=16) - 6
    if block["findings"]:
        w = _finding_width(block, width)
        style = ParagraphStyle("pf", fontName="Text", fontSize=7.2, leading=9.4, textColor=INK)
        box = max(28, max(_finding_height(f["text"], w) for f in block["findings"]) + 11)
        for index, finding in enumerate(block["findings"]):
            fx = x + index * (w + 8)
            c.setFillColor(C(theme.LILA_50))
            c.roundRect(fx, y - 6 - box, w, box, 6, stroke=0, fill=1)
            _badge(c, finding["icon"], fx + 12, y - 6 - box / 2, 7.5)
            para = Paragraph(escape(finding["text"]), style)
            _w, h = para.wrap(w - 30, box)
            para.drawOn(c, fx + 24, y - 6 - box / 2 - h / 2)
        y -= 6 + box
    return y - 16


def _cuts_table(c, ctx: dict, top: float) -> float:
    from .pdf import M, W, _heading, _table
    rows = [{"place": SHORT.get(b["key"], b["label"]), "cut": b["update"].get("cut") or b["period"],
             "updated": b["update"].get("updated") or "—", "frequency": b["update"].get("frequency") or "—"} for b in ctx["blocks"]]
    _heading(c, "Corte, actualización y frecuencia de cada sección", M, top - 12, W - 2 * M)
    columns = [("Sección", "place", None, "text"), ("Corte de la información", "cut", 156, "text"),
               ("Actualizado", "updated", 128, "text"), ("Frecuencia", "frequency", 126, "text")]
    return _table(c, M, top - 24, W - 2 * M, columns, rows, row_h=13.4)


def generate_panorama_pdf(ctx: dict) -> bytes:
    from .charts import emblem_png
    from .pdf import BOTTOM, H, M, W, _band, _footer, _slim_band
    out = BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=A4, pageCompression=1)
    c.setTitle(f"{ctx['title']} · Resumen ejecutivo")
    c.setAuthor(ctx["institution"])
    c.setSubject("Todas las secciones · último corte de cada una")
    c.setCreator(PRODUCT)
    width = W - 2 * M
    heights = [_block_height(b, width) for b in ctx["blocks"]]
    # Plan the pages first: the first one carries the institutional plate, the last one the table of cuts.
    pages, current, room = [], [], H - 150 - 18 - BOTTOM
    for block, height in zip(ctx["blocks"], heights):
        if height > room and current:
            pages.append(current)
            current, room = [], H - 78 - 20 - BOTTOM
        current.append(block)
        room -= height
    pages.append(current)
    cuts_h = 0  # The cut and frequency of each section already head its block: no closing table.
    total = len(pages) + (1 if room < cuts_h and len(pages) < MAX_PAGES else 0)
    # Every new section is paginated; the printed total must match the pages drawn.
    for number, blocks in enumerate(pages, start=1):
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        if number == 1:
            y = _band(c, ctx, H, emblem_png()) - 18
        else:
            y = _slim_band(c, ctx, ctx["title"], "Cada sección con su último corte, sus cifras clave, su gráfico y sus hallazgos") - 20
        for block in blocks:
            y = _draw_block(c, block, M, y, width)
        if False:  # noqa: SIM108 - kept for a closing table if it is ever needed again
            _cuts_table(c, ctx, y + 4)
        elif number == len(pages) and total > len(pages):
            _footer(c, ctx, number, total)
            c.showPage()
            c.setFillColor(colors.white)
            c.rect(0, 0, W, H, stroke=0, fill=1)
            y = _slim_band(c, ctx, "Cortes de la información", "Cada sección conserva su propio corte y frecuencia") - 20
            _cuts_table(c, ctx, y)
            number += 1
        _footer(c, ctx, number, total)
        c.showPage()
    c.save()
    return out.getvalue()
