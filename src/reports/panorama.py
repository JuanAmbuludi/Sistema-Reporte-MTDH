"""Executive summary of every section of the dashboard, in three A4 pages at most.

Each section is read at its latest cut, for the whole country and every program, exactly as its own summary reads it:
a block with its cut and update, its four key figures and its two leading findings.  Sections never mix: each block
keeps its own unit, criterion and cut.  The last page closes with the cut, update and frequency of every section.
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
SHORT = {"transferencias": "Transferencias", "servicios": "Servicios", "riesgos": "Riesgos: exposición",
         "seguimiento_enos": "Riesgos: seguimiento", "contingencias": "Contingencias", "jovenes": "Jóvenes en Acción",
         "laboral": "Gestión laboral", "presupuesto": "Presupuesto institucional", "presupuesto_social": "Presupuesto social"}
SECTIONS = [
    ("transferencias", "Transferencias monetarias", "hand-coins"),
    ("servicios", "Servicios de protección integral", "users"),
    ("riesgos", "Riesgos: exposición de las unidades de atención", "storm"),
    ("seguimiento_enos", "Riesgos: seguimiento y respuesta", "life-buoy"),
    ("contingencias", "Contingencias y compensaciones", "shield"),
    ("jovenes", "Jóvenes en Acción", "graduation"),
    ("laboral", "Gestión laboral", "briefcase"),
    ("presupuesto", "Presupuesto institucional", "landmark"),
    ("presupuesto_social", "Presupuesto social", "wallet"),
]
MAX_PAGES = 3


def section_views(bases: dict) -> dict:
    """Fresh views of every section (the ones on screen keep the reader's selection)."""
    from src.indicators import MODULES
    from src.views.contingencias import ContingencyView
    from src.views.enos import EnosView
    from src.views.jovenes import YouthView
    from src.views.laboral import LabourView
    from src.views.presupuesto import BudgetView, SocialBudgetView
    from src.views.riesgos import RiskView
    from src.views.territorial import TerritorialView
    views = {module_id: TerritorialView(module_id, bases["data"], bases["catalog"], bases["territory"], bases["program_budget"])
             for module_id in MODULES}
    views["riesgos"] = RiskView()
    views["seguimiento_enos"] = EnosView()
    if bases.get("contingency_catalog"):
        views["contingencias"] = ContingencyView(bases["contingencies"], bases["contingency_places"], bases["contingency_catalog"])
    views["jovenes"] = YouthView()
    views["laboral"] = LabourView(bases["labour"])
    if not bases["budget"].empty:
        views["presupuesto"] = BudgetView(bases["budget"], bases["budget_manifest"])
    if not bases["social_groups"].empty:
        views["presupuesto_social"] = SocialBudgetView(bases["social_groups"], bases["social_programs"])
    return views


def _latest(catalog: list[dict]) -> dict | None:
    """The latest monthly cut (annual references come after it in the catalogs)."""
    monthly = [p for p in catalog if p.get("month")]
    pool = monthly or catalog
    return max(pool, key=lambda p: str(p["id"])) if pool else None


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
    findings = [i for i in context.get("insights", []) if i.get("text")][:3]
    return {"key": key, "label": label, "icon": icon, "period": period["label"], "kpis": kpis, "findings": findings,
            "update": update or {}, "source": context.get("source", f"Fuente: {INSTITUTION}")}


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
def _kpi_tiles(c, kpis: list[dict], x: float, top: float, width: float, height: float = 54) -> float:
    from .pdf import C, MIST, NIGHT, PURPLE, TONES, _badge, _clip, _fit, _wrap, value_text
    gap = 8
    count = max(1, len(kpis))
    w = (width - gap * (count - 1)) / count
    for index, kpi in enumerate(kpis):
        tx = x + index * (w + gap)
        c.setFillColor(MIST)
        c.roundRect(tx, top - height, w, height, 6, stroke=0, fill=1)
        c.setFillColor(C(TONES[index % len(TONES)]))
        c.rect(tx, top - height + 7, 2.6, height - 14, stroke=0, fill=1)
        _badge(c, kpi["icon"], tx + 15, top - 13, 7.5, fill=C(theme.LILA_50), variant="morado")
        c.setFillColor(C(theme.PIZARRA))
        c.setFont("Text-Semi", 6.6)
        lines = _wrap(kpi.get("short") or kpi["label"], "Text-Semi", 6.6, w - 30, 2)
        for row, line in enumerate(lines):
            c.drawString(tx + 26, top - 11.5 - row * 7.6 + (3.8 if len(lines) == 1 else 0), line)
        value = value_text(kpi)
        size = _fit(value, "Display", 13.5, w - 16, 8)
        c.setFillColor(NIGHT)
        c.setFont("Display", size)
        c.drawString(tx + 9, top - 37, value)
        note = kpi.get("note") or ""
        if note:
            c.setFillColor(PURPLE)
            c.setFont("Text-Semi", 6.3)
            c.drawString(tx + 9, top - 48, _clip(note, "Text-Semi", 6.3, w - 14))
    return top - height


def _finding_height(text: str, width: float) -> float:
    style = ParagraphStyle("pf", fontName="Text", fontSize=7.3, leading=9.6)
    return Paragraph(escape(text), style).wrap(width - 30, 200)[1]


def _finding_width(block: dict, width: float) -> float:
    count = max(1, len(block["findings"]))
    return (width - 8 * (count - 1)) / count


def _block_height(block: dict, width: float) -> float:
    w = _finding_width(block, width)
    findings = max([_finding_height(f["text"], w) for f in block["findings"]] or [0])
    return 24 + 54 + (max(30, findings + 12) + 7 if block["findings"] else 0) + 15


def _cut_text(block: dict) -> str:
    update = block["update"]
    cut = update.get("cut") or block["period"]
    text = update.get("short") if len(cut) > 34 and update.get("short") else f"Corte: {cut}"
    return f"{text} · {update['frequency']}" if update.get("frequency") else text


def _overview(c, ctx: dict, top: float) -> float:
    """The leading figure of every section, three to a row."""
    from .pdf import C, M, MIST, MUTED, NIGHT, W, _badge, _clip, _fit, _heading, value_text
    width = W - 2 * M
    _heading(c, "Cifra principal de cada sección", M, top - 12, width, "Cada una con su propio corte")
    gap, h = 8, 46
    w = (width - 2 * gap) / 3
    y = top - 24
    for index, block in enumerate(ctx["blocks"]):
        if not block["kpis"]:
            continue
        kpi = block["kpis"][0]
        tx = M + (index % 3) * (w + gap)
        ty = y - (index // 3) * (h + gap)
        c.setFillColor(MIST)
        c.roundRect(tx, ty - h, w, h, 6, stroke=0, fill=1)
        _badge(c, block["icon"], tx + 16, ty - h / 2, 10)
        c.setFillColor(C(theme.MORADO))
        c.setFont("Text-Bold", 6.8)
        c.drawString(tx + 33, ty - 12, _clip(SHORT.get(block["key"], block["label"]), "Text-Bold", 6.8, w - 40))
        value = value_text(kpi)
        c.setFillColor(NIGHT)
        c.setFont("Display", _fit(value, "Display", 13, w - 40, 8))
        c.drawString(tx + 33, ty - 27, value)
        c.setFillColor(MUTED)
        c.setFont("Text", 6.4)
        c.drawString(tx + 33, ty - 38, _clip(kpi["label"], "Text", 6.4, w - 40))
    rows = (len(ctx["blocks"]) + 2) // 3
    return y - rows * (h + gap) - 6


def _draw_block(c, block: dict, x: float, top: float, width: float) -> float:
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
    y = _kpi_tiles(c, block["kpis"], x, top - 24, width)
    if block["findings"]:
        w = _finding_width(block, width)
        style = ParagraphStyle("pf", fontName="Text", fontSize=7.3, leading=9.6, textColor=INK)
        box = max(30, max(_finding_height(f["text"], w) for f in block["findings"]) + 12)
        for index, finding in enumerate(block["findings"]):
            fx = x + index * (w + 8)
            c.setFillColor(C(theme.LILA_50))
            c.roundRect(fx, y - 7 - box, w, box, 6, stroke=0, fill=1)
            _badge(c, finding["icon"], fx + 12, y - 7 - box / 2, 7.5)
            para = Paragraph(escape(finding["text"]), style)
            _w, h = para.wrap(w - 30, box)
            para.drawOn(c, fx + 24, y - 7 - box / 2 - h / 2)
        y -= 7 + box
    return y - 15


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
    overview_h = 24 + ((len(ctx["blocks"]) + 2) // 3) * 54 + 6
    pages, current, room = [], [], H - 136 - 22 - overview_h - 8 - BOTTOM
    for block, height in zip(ctx["blocks"], heights):
        if height > room and current:
            pages.append(current)
            current, room = [], H - 78 - 26 - BOTTOM
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
            y = _overview(c, ctx, _band(c, ctx, H, emblem_png()) - 18) - 8
        else:
            y = _slim_band(c, ctx, "Todas las secciones", "Cada sección con su último corte, sus cifras clave y sus hallazgos") - 20
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
