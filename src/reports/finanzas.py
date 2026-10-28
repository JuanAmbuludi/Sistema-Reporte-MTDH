"""The reconciled budget selection, rendered with the existing institutional report components."""
from __future__ import annotations

from src import finanzas, theme
from .areas import _base, kpis_from_cards
from .context import millions, number


def context(view, title):
    ctx = _base(view, "presupuesto_conciliado", title)
    tables = []
    for dimension, label in view.dimensions.items():
        frame = finanzas.by(view.filtered, dimension, view.government).rename(columns={dimension: "name"})
        tables.append({"key": dimension, "label": label, "rows": frame.to_dict("records")})
    stats = view.stats
    measure = "acumulado" if view.government else "devengado"
    leader = max(tables[0]["rows"], key=lambda r: r[measure])
    insights = [{"icon": "calendar", "text": f"Año fiscal {view.period['year']}. Corte: {view.period['label'].lower()}."},
                {"icon": "info", "text": view.scope_note},
                {"icon": "award", "text": f"{leader['name']}: USD {number(leader[measure], 2)} "
                                            f"{'acumulados de gobierno' if view.government else 'devengados'}."}]
    if view.government:
        insights.append({"icon": "wallet", "text": f"USD {number(stats['anterior'], 2)} acumulados de {view.span} + "
                         f"USD {number(stats['fiscal'], 2)} ejecutados en {view.period['year']} = "
                         f"USD {number(stats['acumulado'], 2)} acumulados de gobierno."})
    else:
        insights.append({"icon": "wallet", "text": f"Saldo por devengar: USD {number(stats['saldo_por_devengar'], 2)}. "
                         f"Saldo disponible publicado por SGDE: USD {number(stats['saldo_disponible'], 2)}."})
    source = ("presupuesto acumulado de gobierno de transferencias y servicios, por programa y provincia" if view.government
              else "SGDE, ejecución presupuestaria fiscal del Ministerio")
    cards = kpis_from_cards(view.kpi_cards())
    return {**ctx, "government": view.government, "stats": stats, "kpis": cards, "tables": tables,
            "columns": view.columns(), "detail": view.filtered.to_dict("records"), "insights": insights,
            "scope": view.scope_note, "scope_items": view.scope_items(), "pdf_pages": 2,
            "source": "Fuente: " + source,
            "source_url": "" if view.government else view.metadata["procedencia"]["url"],
            "definitions": [("Alcance", view.scope_note),
                            (f"Acumulado {view.span}", f"Presupuesto acumulado de {view.span.replace('–', ' a ')} de cada programa y provincia."),
                            (f"Ejecutado {view.period['year']}", f"Presupuesto ejecutado en {view.period['year']} al corte; forma parte del acumulado."),
                            ("Acumulado de gobierno", f"Acumulado de {view.span} más el ejecutado en {view.period['year']}, tal como lo reporta la fuente; "
                                                      "no se suma de nuevo el componente del año.")]
                           if view.government else [("Ejecución presupuestaria", "Devengado dividido para codificado, calculado después de sumar los importes de la selección."),
                                                   ("Saldo disponible", "Valor publicado por SGDE; se conserva sin reemplazarlo por codificado menos devengado."),
                                                   ("Saldo por devengar", "Codificado menos devengado."), ("Alcance", view.scope_note)]}


def render_pdf(c, ctx, pages):
    from .pdf import H, M, W, _band, _bars, _findings, _heading, _kpis, _next_page, _slim_band, _table
    full = W - 2*M
    y = _kpis(c, ctx, _band(c, ctx, H, None) - 18) - 30
    measure = "acumulado" if ctx["government"] else "devengado"
    rows = sorted(ctx["tables"][0]["rows"], key=lambda r: -r[measure])
    peak = max(r[measure] for r in rows) or 1
    chart_rows = [{"name": r["name"], "text": f"USD {millions(r[measure], 1)} M", "fraction": r[measure]/peak} for r in rows]
    _heading(c, "Acumulado de gobierno por programa" if ctx["government"] else "Presupuesto devengado por programa", M, y, full)
    _bars(c, chart_rows, M, y-26, full, 24)
    bottom = y-26-24*len(chart_rows)-22
    _heading(c, "Alcance y cifras de control", M, bottom, full)
    _findings(c, ctx["insights"], M, bottom-18, full, limit=4)
    _next_page(c, ctx, 1, pages)
    y = _slim_band(c, ctx, "Detalle presupuestario", f"Año fiscal {ctx['year']} · {ctx['territory_label']}") - 27
    if ctx["government"]:
        table = next(t for t in ctx["tables"] if t["key"] == "provincia")
        _heading(c, "Acumulado por provincia", M, y, full, "Montos en USD")
        formatted = [{**r, **{k: number(r[k], 2) for k in finanzas.GOVERNMENT_MEASURES}} for r in table["rows"]]
        columns = [("Provincia", "name", None, "text"), ("2023–2025", "anterior", 105, "text"),
                   (str(ctx["year"]), "fiscal", 105, "text"), ("Acumulado", "acumulado", 105, "text")]
        y = _table(c, M, y-13, full, columns, formatted, row_h=17)
        total = {"name": "TOTAL", **{k: number(ctx['stats'][k],2) for k in finanzas.GOVERNMENT_MEASURES}}
        _table(c, M, y-12, full, columns, [total], row_h=20)
    else:
        for table in ctx["tables"]:
            if table["key"] == "programa":
                continue
            _heading(c, "Por " + table["label"].lower(), M, y, full, "Millones de USD")
            columns = [(table["label"], "name", None, "text"), ("Codificado", "codificado", 61, "mill"),
                       ("Certificado", "certificado", 56, "mill"), ("Comprometido", "comprometido", 64, "mill"),
                       ("Devengado", "devengado", 61, "mill"), ("Disponible", "saldo_disponible", 61, "mill"),
                       ("Ejecución", "ejecucion", 46, "pct")]
            y = _table(c, M, y-13, full, columns, table["rows"], row_h=18) - 28


def render_book(book):
    from .excel_areas import _block, _facts, _finish_summary, _sheet, _summary
    ctx = book.ctx
    ws, row = _summary(book, "")
    _finish_summary(book, ws, row+1, ctx["insights"])
    contents = [("Resumen", "Cifras clave y alcance")]
    columns = [(label + " (USD)" if kind == "money" else label, key, "usd" if kind == "money" else kind)
               for label,key,kind in ctx["columns"]]
    for table in ctx["tables"]:
        title = table["label"]
        sheet_name = title[:31]
        cols = [(title, "name", "text"), *columns]
        ws, row = _sheet(book, sheet_name, theme.MORADO, "Presupuesto por " + title.lower(), [2.4,48]+[22]*len(columns)+[2.4])
        rows = [{**r, **({"ejecucion": r["ejecucion"]/100 if r["ejecucion"] is not None else None} if "ejecucion" in r else {})}
                for r in table["rows"]]
        _block(book, ws, row+1, ctx["period_label"], cols, rows, last=len(cols), height=26, autofilter=True)
        contents.append((sheet_name, "Montos de la selección por " + title.lower()))
    raw = ctx["detail"]
    keys = (["provincia", "programa", "ambito", *finanzas.GOVERNMENT_MEASURES] if ctx["government"] else
            ["programa", "tipo_gasto", "grupo_gasto", "fuente", *finanzas.FISCAL_MEASURES])
    numeric = set(finanzas.GOVERNMENT_MEASURES if ctx["government"] else finanzas.FISCAL_MEASURES)
    labels = {key: label for label,key,_kind in ctx["columns"]}
    columns = [(labels.get(k, k.replace("_", " ").capitalize()), k, "usd" if k in numeric else "text") for k in keys]
    ws, row = _sheet(book, "Detalle", theme.ORO, ctx["title"], [2.4]+[22 if k in numeric else 42 for k in keys]+[2.4])
    _block(book, ws, row+1, "Registros de la selección", columns, raw, last=len(keys), autofilter=True)
    contents.append(("Detalle", "Registros originales del universo seleccionado"))
    book.facts_sheet(_facts(book, [*ctx["scope_items"], ("Fuente", ctx["source"]), ("URL", ctx["source_url"])]),
                     ctx["definitions"], contents)


def render_slides(prs, ctx):
    from .charts import emblem_png
    from .pptx import _bar_chart, _cover, _findings_column, _footer, _header, _ranked
    total = 3
    _cover(prs, ctx, emblem_png(width=4.2, height=3.7, dpi=200), total, share_word="")
    measure = "acumulado" if ctx["government"] else "devengado"
    rows = sorted(ctx["tables"][0]["rows"], key=lambda r: r[measure])
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, "Presupuesto por programa", f"Año fiscal {ctx['year']} · millones de USD")
    _bar_chart(slide, [r["name"] for r in rows], [r[measure]/1e6 for r in rows], "Acumulado" if ctx["government"] else "Devengado",
               x=0.5,y=1.4,w=7.2,h=5.5)
    _findings_column(slide, ctx["insights"][:3])
    _footer(slide, ctx, 2, total)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, "Desagregación presupuestaria", ctx["period_label"])
    dimensions = ["ambito", "provincia"] if ctx["government"] else ["tipo_gasto", "fuente"]
    for index, dimension in enumerate(dimensions):
        rows = next(t["rows"] for t in ctx["tables"] if t["key"] == dimension)
        peak = max(r[measure] for r in rows) or 1
        display = [{"name": r["name"], "text": f"USD {millions(r[measure])} M", "fraction": r[measure]/peak} for r in rows[:9]]
        _ranked(slide, display, 0.55+index*6.5, 1.7, 5.9, step=0.54)
    _footer(slide, ctx, 3, total)
