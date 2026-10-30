"""Documents of the monthly areas built on ``src.views.area`` (Crédito de Desarrollo Humano, Brigadas sociales).

The view declares its key figures, findings, two charts and its tables; this module prints them with the institutional
components: a two-page summary in PDF, three editable slides and a data workbook with its technical sheet.
"""
from __future__ import annotations

from src import theme
from .areas import _base, kpis_from_cards
from .context import number


def context(view, title: str) -> dict:
    ctx = _base(view, "area_simple", title)
    parts = view.report_parts()
    return {**ctx, "kpis": kpis_from_cards(view.kpi_cards()), "insights": parts["insights"], "charts": parts["charts"],
            "tables": parts["tables"], "definitions": parts["definitions"], "scope_items": view.scope_items(), "pdf_pages": 2,
            "source": f"Fuente: Ministerio de Trabajo y Desarrollo Humano · {view.label}"}


def _text(value, kind: str) -> str:
    if value is None or value != value:
        return "—"
    if kind == "int":
        return number(value)
    if kind == "usd":
        return number(value, 2)
    if kind == "pct":
        return f"{number(value, 1)} %"
    return str(value)


def render_pdf(c, ctx, pages):
    from .pdf import H, M, W, _band, _bars, _findings, _heading, _kpis, _next_page, _slim_band, _table
    from .pdf_areas import _columns
    full = W - 2 * M
    half = (full - 22) / 2
    y = _kpis(c, ctx, _band(c, ctx, H, None) - 18) - 30
    first, second = ctx["charts"][:2]
    _heading(c, first["title"], M, y, half, first.get("note", ""))
    _columns(c, [r.get("short_name", r["name"][:3]) for r in first["rows"]], [r["value"] for r in first["rows"]], M, y - 22, half, 170,
             highlight=len(first["rows"]) - 1, label_size=7,
             value_text=lambda v: f"{number(v / 1000, 0)} mil" if v >= 10000 else number(v))
    _heading(c, second["title"], M + half + 22, y, half, second.get("note", ""))
    peak = max([r["value"] or 0 for r in second["rows"]] or [1]) or 1
    rows = [{"name": r["name"], "text": number(r["value"]), "fraction": (r["value"] or 0) / peak} for r in second["rows"]]
    _bars(c, rows, M + half + 22, y - 26, half, min(22, 168 / max(1, len(rows))))
    bottom = y - 22 - 170 - 26
    _heading(c, "Aspectos destacados", M, bottom, full)
    _findings(c, ctx["insights"], M, bottom - 18, full, limit=4)
    _next_page(c, ctx, 1, pages)
    y = _slim_band(c, ctx, "Cuadros de resultados", f"{ctx['period_label']} · {ctx['territory_label']}") - 27
    for table in ctx["tables"][:2]:
        rows = table["rows"][:24]
        widths = {"int": 74, "usd": 96, "pct": 64}
        formatted = [{k: _text(r.get(k), kind) for _h, k, kind in table["columns"]} for r in rows]
        columns = [(h, k, table.get("pdf_widths", {}).get(k, None if kind == "text" else widths[kind]), "text")
                   for h, k, kind in table["columns"]]
        _heading(c, f"Por {table['label'].lower()}", M, y, full, ctx.get("tables_note", "Año a la fecha de la consulta"))
        y = _table(c, M, y - 13, full, columns, formatted, row_h=14.2) - 26
        if y < 140:
            break


def render_book(book):
    from .excel_areas import _block, _facts, _finish_summary, _sheet, _summary
    ctx = book.ctx
    ws, row = _summary(book, "")
    _finish_summary(book, ws, row + 1, ctx["insights"])
    contents = [("Resumen", "Cifras clave y aspectos destacados")]
    for table in ctx["tables"]:
        cols = [(h, k, kind) for h, k, kind in table["columns"]]
        widths = [2.4] + [40 if kind == "text" else 20 for _h, _k, kind in cols] + [2.4]
        ws, row = _sheet(book, table["label"][:31], theme.MORADO, f"{ctx['module_label']} por {table['label'].lower()}", widths)
        rows = [{**r, **{k: (r.get(k) / 100 if r.get(k) is not None else None) for _h, k, kind in cols if kind == "pct"}} for r in table["rows"]]
        _block(book, ws, row + 1, ctx["period_label"], cols, rows, last=len(cols), height=26, autofilter=True)
        contents.append((table["label"][:31], f"Resultados por {table['label'].lower()}"))
    book.facts_sheet(_facts(book, [*ctx["scope_items"], ("Fuente", ctx["source"])]), ctx["definitions"], contents)


def render_slides(prs, ctx):
    from .charts import emblem_png
    from .pptx import _bar_chart, _cover, _findings_column, _footer, _header, _ranked
    total = 3
    _cover(prs, ctx, emblem_png(width=4.2, height=3.7, dpi=200), total, share_word="")
    first, second = ctx["charts"][:2]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, first["title"], f"{ctx['period_label']} · {ctx['territory_label']}")
    _bar_chart(slide, [r["name"] for r in first["rows"]], [r["value"] or 0 for r in first["rows"]], first.get("unit", "").capitalize() or "Valor",
               x=0.5, y=1.4, w=7.2, h=5.5)
    _findings_column(slide, ctx["insights"][:3])
    _footer(slide, ctx, 2, total)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, second["title"], ctx["period_label"])
    peak = max([r["value"] or 0 for r in second["rows"]] or [1]) or 1
    rows = [{"name": r["name"], "text": number(r["value"]), "fraction": (r["value"] or 0) / peak} for r in second["rows"][:10]]
    _ranked(slide, rows[:5], 0.55, 1.7, 5.9, step=0.54)
    if len(rows) > 5:
        _ranked(slide, rows[5:], 7.05, 1.7, 5.9, step=0.54)
    _footer(slide, ctx, 3, total)
