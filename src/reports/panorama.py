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
         "jovenes": "Jóvenes en Acción", "laboral": "Empleo", "presupuesto": "Presupuesto fiscal",
         "presupuesto_social": "Presupuesto social", "presupuesto_gobierno": "Presupuesto de gobierno"}
SECTIONS = [
    ("transferencias", "Transferencias monetarias no contributivas", "hand-coins"),
    ("servicios", "Servicios de protección social", "users"),
    ("riesgos", "Plan ENOS: respuesta del Ministerio", "storm"),
    ("contingencias", "Contingencias y compensaciones", "shield"),
    ("jovenes", "Jóvenes en Acción", "graduation"),
    ("laboral", "Gestión laboral", "briefcase"),
    ("presupuesto", "Presupuesto fiscal", "landmark"),
    ("presupuesto_social", "Presupuesto social", "wallet"),
    ("presupuesto_gobierno", "Presupuesto acumulado de gobierno", "landmark"),
]
MAX_PAGES = 3


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
        return {"kind": "bars", "title": "Alertas por provincia", "rows": [dict(r, text=str(r["value"])) for r in ctx["response"]["by_province"]],
                "note": "Alertas revisadas con código UA"}
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
    view.select(period)
    if not view.prepare():
        return None
    context = view.report_context(label)
    # The figures as the section's own summary prints them (short captions), the dashboard cards otherwise.
    kpis = [k for k in (context.get("kpis") or kpis_from_cards(view.kpi_cards())) if k.get("value") is not None][:4]
    update = view.update_stamp() if hasattr(view, "update_stamp") else corte.stamp(view.id, period)
    findings = [i for i in context.get("insights", []) if i.get("text")][:2]
    try:
        visual = _visual(key, context)
    except Exception:  # noqa: BLE001 - a section without its chart keeps its figures and findings
        LOG.exception("Sección sin gráfico: %s", key)
        visual = None
    return {"key": key, "label": label, "icon": icon, "period": period["label"], "kpis": kpis, "findings": findings,
            "visual": visual, "update": update or {}, "source": context.get("source", f"Fuente: {INSTITUTION}")}


def build_panorama(bases: dict, title: str) -> dict:
    views = section_views(bases)
    blocks = []
    for key, label, icon in SECTIONS:
        view = views.get(key)
        if view is None:
            continue
        try:
            block = _block(key, label, icon, view)
        except Exception:  # noqa: BLE001 - one section without its data never stops the others
            LOG.exception("Sección sin resumen: %s", key)
            block = None
        if block:
            blocks.append(block)
    if not blocks:
        raise ValueError("Ninguna sección tiene información para resumir.")
    generated_at, generated_label = stamp()
    return {"kind": "panorama", "title": str(title or "Resumen de todas las secciones")[:100], "blocks": blocks,
            "institution": INSTITUTION, "source": f"Fuente: {INSTITUTION}", "generated_at": generated_at,
            "generated_label": generated_label, "period_label": "Último corte de cada sección", "territory_label": "Nacional",
            "programs_label": f"{len(blocks)} secciones", "module_label": "Todas las secciones", "update": {}}


# ------------------------------------------------------------------------------------------------- drawing
BODY_H = 112    # the key figures at the left and the chart of the section at the right
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
        c.setFont("Text-Semi", 6.5)
        shown = _clip(label, "Text-Semi", 6.5, room)
        c.drawString(x + 8, y - 21.5, shown)
        used = c.stringWidth(shown + " · ", "Text-Semi", 6.5)
        if note and room - used > 30:
            c.setFillColor(PURPLE)
            c.setFont("Text", 6.3)
            c.drawString(x + 8 + used, y - 21.5, _clip(note, "Text", 6.3, room - used))


def _bar_rows(c, rows: list[dict], x: float, top: float, width: float, height: float) -> None:
    """Bars with their figure; more than five rows share two columns."""
    from .pdf import _bars
    if rows and "fraction" not in rows[0]:
        peak = max([r.get("value") or 0 for r in rows] or [1]) or 1
        rows = [{**r, "fraction": (r.get("value") or 0) / peak} for r in rows]
    columns = 2 if len(rows) > 5 else 1
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
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 8.2)
    c.drawString(x, top - 7, _clip(visual["title"], "Display-Bold", 8.2, width * 0.62))
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
        c.drawRightString(x + width, top - 7, _clip(visual["note"], "Text", 6.6, width * 0.4))
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


def _block_height(block: dict, width: float) -> float:
    w = _finding_width(block, width)
    findings = max([_finding_height(f["text"], w) for f in block["findings"]] or [0])
    return 24 + BODY_H + (max(28, findings + 11) + 8 if block["findings"] else 0) + 16


def _cut_text(block: dict) -> str:
    update = block["update"]
    cut = update.get("cut") or block["period"]
    text = update.get("short") if len(cut) > 34 and update.get("short") else f"Corte: {cut}"
    frequency = update.get("frequency_short") or update.get("frequency")
    return f"{text} · {frequency}" if frequency else text


def _draw_block(c, block: dict, x: float, top: float, width: float) -> float:
    """A section: its name and cut, its key figures beside its own chart, and its two leading findings."""
    from .pdf import C, INK, MUTED, NIGHT, _badge, _clip
    _badge(c, block["icon"], x + 9, top - 8, 9)
    c.setFillColor(NIGHT)
    c.setFont("Display-Bold", 10.6)
    cut = _cut_text(block)
    cut_w = min(width * 0.52, c.stringWidth(cut, "Text", 7))
    c.drawString(x + 24, top - 11.5, _clip(block["label"], "Display-Bold", 10.6, width - cut_w - 34))
    c.setFillColor(MUTED)
    c.setFont("Text", 7)
    c.drawRightString(x + width, top - 11, _clip(cut, "Text", 7, width * 0.52))
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.7)
    c.line(x, top - 18, x + width, top - 18)
    body = top - 26
    if block.get("visual"):
        _kpi_list(c, block["kpis"], x, body, KPI_W)
        c.setStrokeColor(C("#ECE8F3"))
        c.line(x + KPI_W + 7, body - 2, x + KPI_W + 7, body - BODY_H + 4)
        _draw_visual(c, block["visual"], x + KPI_W + 16, body, width - KPI_W - 16)
    else:
        half = (width - 14) / 2
        _kpi_list(c, block["kpis"][:2], x, body, half, BODY_H / 2)
        _kpi_list(c, block["kpis"][2:4], x + half + 14, body, half, BODY_H / 2)
    y = body - BODY_H - 2
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
    cuts_h = 24 + 22 + 13.4 * len(ctx["blocks"]) + 10
    total = len(pages) + (1 if room < cuts_h and len(pages) < MAX_PAGES else 0)
    total = min(total, MAX_PAGES)
    for number, blocks in enumerate(pages, start=1):
        c.setFillColor(colors.white)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        if number == 1:
            y = _band(c, ctx, H, emblem_png()) - 18
        else:
            y = _slim_band(c, ctx, "Todas las secciones", "Cada sección con su último corte, sus cifras clave, su gráfico y sus hallazgos") - 20
        for block in blocks:
            y = _draw_block(c, block, M, y, width)
        if number == len(pages) and y - cuts_h > BOTTOM:
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
