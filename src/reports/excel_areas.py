"""Data workbooks of the areas with their own structure: contingencies and compensation, Jóvenes en Acción, labour
management and the social budget.

Same rules as the territorial workbook: real numbers with number formats, live totals that carry their value, native
editable charts, the institutional band with the cut, update and frequency of the information on every sheet, and a
technical sheet with sources and definitions.  Amounts are in USD; percentages travel as fractions with a percent
format.
"""
from __future__ import annotations

from src import theme
from .charts import map_png
from .context import PRODUCT

LEVEL_LABELS = {"provincia": "Provincia", "canton": "Cantón", "parroquia": "Parroquia"}
LEVEL_PLURALS = {"provincia": "Provincias", "canton": "Cantones", "parroquia": "Parroquias"}
SHORT_UNITS = {"beneficiarios": "Beneficiarios", "personas habilitadas": "Personas habilitadas",
               "personas con pago acreditado": "Personas con pago acreditado"}


def _f(value) -> float | None:
    return None if value is None or value != value else value / 100


def _sheet(book, name: str, tab: str, title: str, widths: list[float], *, subtitle: str | None = None, landscape: bool = True):
    ws = book.wb.add_worksheet(name)
    book.widths(ws, widths)
    book.page(ws, landscape=landscape)
    ws.set_tab_color(tab)
    row = book.band(ws, title, subtitle or book.subtitle(), last=len(widths) - 1)
    return ws, row


def _layout(columns: list[tuple]) -> list[tuple]:
    """(header, key, kind) columns placed from the second column of the sheet."""
    return [(header, key, kind, index + 1, 1) for index, (header, key, kind) in enumerate(columns)]


def _block(book, ws, row: int, title: str, columns: list[tuple], rows: list[dict], *, note: str = "", total: dict | None = None,
           bar: str | None = None, last: int, height: int = 19, autofilter: bool = False, gold: bool = True) -> tuple[int, int, int]:
    """A heading and its table; ``bar`` names a fraction column that gets a data bar; selected rows in gold."""
    row = book.heading(ws, row, title, note, last=last)
    layout = _layout(columns)
    first, end, nxt = book.table(ws, row, layout, rows, total=total, header_height=36, height=height, gold=gold)
    if bar:
        col = next(c for _h, key, _k, c, _s in layout if key == bar)
        book.data_bar(ws, first, end, col, theme.LILA_300, maximum=1)
    if autofilter and rows:
        ws.autofilter(row, 1, end, len(columns))
    return first, end, nxt


def _summary(book, cards_share: str = "del total nacional") -> tuple:
    """The Resumen sheet: band, key figures and the row where the content starts."""
    ctx = book.ctx
    ws = book.wb.add_worksheet("Resumen")
    book.widths(ws, [2.4] + [12.6] * 12 + [2.4])
    book.page(ws, tall=1)
    ws.set_tab_color(theme.MORADO)
    row = book.band(ws, ctx["title"], book.subtitle(), last=13)
    row = book.heading(ws, row + 1, "Cifras clave", ctx["period_label"])
    row = book.kpi_row(ws, row + 1, book.kpi_cards(cards_share))
    return ws, row + 1


def _finish_summary(book, ws, row: int, items: list[dict]) -> None:
    row = book.findings(ws, row, items)
    ws.print_area(0, 0, row, 13)
    ws.activate()
    ws.set_first_sheet()
    ws.set_zoom(90)


def _facts(book, extra: list[tuple[str, str]]) -> list[tuple[str, str]]:
    ctx = book.ctx
    return ([("Institución", ctx["institution"]), ("Producto", f"Libro de datos de {PRODUCT}"), ("Ámbito", ctx["module_label"]),
             ("Periodo", ctx["period_label"]), ("Territorio", ctx["territory_label"])] + extra + book.update_facts()
            + [("Fecha de generación", ctx["generated_label"].capitalize()), ("Unidad monetaria", "Dólares de los Estados Unidos (USD)")])


# ------------------------------------------------------------------------------------------ contingencies
def contingency_book(book) -> None:
    ctx = book.ctx
    budget = ctx.get("budget")
    ws, row = _summary(book, "")
    programs = [{**p, "criterion_text": SHORT_UNITS.get(p["unit"], ""), "execution_f": _f(p["execution"])} for p in ctx["programs"]]
    columns = [("Programa", "name", "text"), ("Criterio", "criterion_text", "text"), ("Personas", "people", "int"),
               ("Monto del mes (USD)", "amount", "usd")]
    if budget:
        columns += [("Devengado acumulado (USD)", "accrued", "usd"), ("Ejecución", "execution_f", "pct")]
    layout = [(h, k, kind, 1 + 2 * i if i < 2 else 3 + i, 2 if i < 2 else 1) for i, (h, k, kind) in enumerate(columns)]
    row = book.heading(ws, row, "Resultados por programa", ctx["when"].capitalize(), last=12)
    first, end, nxt = book.table(ws, row, layout, programs, header_height=36)
    if budget:
        col = next(c for _h, key, _k, c, _s in layout if key == "execution_f")
        book.data_bar(ws, first, end, col, theme.LILA_300, maximum=1)
    row = nxt + 1
    levels = ctx["levels"]
    if levels and ctx["territories"].get(levels[0]):
        level = levels[0]
        row = book.heading(ws, row, f"Bonos habilitados por {LEVEL_LABELS[level].lower()}", f"{ctx['map_program_label']} · {ctx['span']}",
                           last=12)
        picture = map_png(ctx["level_maps"][level], layer=level, label=f"Bonos habilitados de {ctx['span']}", width=5.4, height=4.6, dpi=200)
        book.image(ws, row, 1, picture, 430, "mapa_bonos.png", y_offset=4, description="Mapa del Ecuador: bonos habilitados en el año")
        rows = [{**r, "share_f": _f(r["share"])} for r in ctx["territories"][level][:12]]
        place_layout = [(LEVEL_LABELS[level], "detail", "text", 8, 3), ("Bonos", "records", "int", 11, 1), ("Participación", "share_f", "pct", 12, 1)]
        first, end, nxt = book.table(ws, row, place_layout, rows, header_height=30)
        book.data_bar(ws, first, end, 12, theme.LILA_300, maximum=1)
        row = max(nxt, row + 23) + 1
    _finish_summary(book, ws, row, ctx["insights"][:6])

    # Programs in full.
    ws, row = _sheet(book, "Programas", theme.VIOLETA_500, "Resultados por programa",
                     [2.4, 34.0, 26.0, 13.0, 13.0, 18.0, 18.0, 18.0, 19.0, 19.0, 12.0, 2.4])
    columns = [("Programa", "name", "text"), ("Criterio", "criterion_text", "text"), ("Personas", "people", "int"),
               ("Personas que cobraron", "collected", "int"), ("Monto del mes (USD)", "amount", "usd"),
               ("Monto cobrado (USD)", "collected_amount", "usd"), ("Devengado del mes (USD)", "month_accrued", "usd"),
               ("Devengado acumulado (USD)", "accrued", "usd"), ("Presupuesto aprobado (USD)", "approved", "usd"), ("Ejecución", "execution_f", "pct")]
    _f1, _e1, nxt = _block(book, ws, row + 1, "Programas del mes", columns, programs, note=ctx["when"].capitalize(),
                           bar="execution_f" if budget else None, last=10, height=22)
    row = book.heading(ws, nxt + 2, "Nombre oficial de cada programa", last=10)
    book.table(ws, row, [("Programa", "name", "text", 1, 1), ("Nombre oficial", "full", "text", 2, 6)],
               [{"name": p["name"], "full": p["full"]} for p in ctx["programs"]], header_height=30, height=24)
    ws.set_zoom(90)

    # The year month by month.
    months = ctx["months"]
    ids = [p["id"] for p in ctx["programs"] if any(m["people"].get(p["id"]) is not None for m in months)]
    names = {p["id"]: p["name"] for p in ctx["programs"]}
    widths = [2.4, 16.0] + [17.0] * len(ids) + [19.0, 19.0, 19.0, 13.0, 2.4]
    ws, row = _sheet(book, "Serie mensual", theme.ORO, "El año mes a mes", widths)
    columns = [("Mes", "label", "text")] + [(f"{names[i]} (personas)", i, "int") for i in ids] + [
        ("Monto habilitado o acreditado (USD)", "amount", "usd")]
    if budget:
        columns += [("Devengado del mes (USD)", "month_accrued", "usd"), ("Devengado acumulado (USD)", "accrued", "usd"),
                    ("Ejecución acumulada", "execution_f", "pct")]
    rows = [{"label": f"{m['label']} {ctx['year']}", **{i: m["people"].get(i) for i in ids}, "amount": m["amount"],
             "month_accrued": m["month_accrued"], "accrued": m["accrued"], "execution_f": _f(m["execution"]), "selected": m["selected"]}
            for m in months]
    first, end, nxt = _block(book, ws, row + 1, f"Personas, montos y presupuesto de {ctx['span']}", columns, rows,
                             note="Las personas no se suman entre meses", last=len(widths) - 2)
    amount_col = next(i for i, c in enumerate(columns) if c[1] == ("month_accrued" if budget else "amount")) + 1
    ws.insert_chart(nxt + 1, 1, book.column_chart("Serie mensual", first, end, 1, amount_col,
                                                  "Presupuesto devengado por mes (USD)" if budget else "Monto habilitado o acreditado por mes (USD)",
                                                  number_format="#,##0", width=720, height=320), {"y_offset": 8, "object_position": 3})
    ws.set_zoom(90)

    # Territory: every level chosen, every place.
    for level in levels:
        rows = ctx["territories"].get(level)
        if not rows:
            continue
        places = [("N.º", "n", "center"), (LEVEL_LABELS[level], "place", "text")]
        widths = [2.4, 6.0, 34.0]
        if level == "parroquia":
            places.append(("Cantón", "canton", "text"))
            widths.append(26.0)
        if level != "provincia":
            places.append(("Provincia", "province", "text"))
            widths.append(26.0)
        places += [("Bonos habilitados", "records", "int"), ("Participación", "share_f", "pct"), ("Personas", "people", "int"),
                   ("Monto habilitado (USD)", "amount", "usd")]
        widths += [16.0, 14.0, 14.0, 18.0, 2.4]
        ws, row = _sheet(book, LEVEL_PLURALS[level], theme.LILA_300, f"Bonos habilitados por {LEVEL_LABELS[level].lower()}", widths)
        whole = ctx["level_totals"][level]
        data = [{"n": i + 1, "place": r["place"], "canton": r["canton"], "province": r["province"], "records": r["records"],
                 "share_f": _f(r["share"]), "people": r["people"], "amount": r["amount"]} for i, r in enumerate(rows)]
        _block(book, ws, row + 1, f"{LEVEL_PLURALS[level]} con bonos habilitados", places, data,
               note=f"{ctx['map_program_label']} · {ctx['span']} · {len(rows)} de {whole['count']}", bar="share_f", last=len(places),
               autofilter=True)
        ws.freeze_panes(row + 3, 3)
        ws.set_zoom(90)

    # Types of contingency.
    if ctx["types"]:
        ws, row = _sheet(book, "Tipos", theme.FUCSIA, "Bonos habilitados por tipo", [2.4, 34.0, 50.0, 16.0, 14.0, 14.0, 18.0, 2.4])
        data = [{"program": t["program"], "name": t["name"], "records": t["records"], "share_f": _f(t["share"]), "people": t["people"],
                 "amount": t["amount"]} for t in ctx["types"]]
        total = {"records": sum(t["records"] or 0 for t in ctx["types"]), "amount": sum(t["amount"] or 0 for t in ctx["types"]), "share_f": 1.0,
                 "_label": "Total"}
        _block(book, ws, row + 1, f"Tipos de contingencia o evento · {ctx['span']}", [
            ("Programa", "program", "text"), ("Tipo", "name", "text"), ("Bonos habilitados", "records", "int"), ("Participación", "share_f", "pct"),
            ("Personas", "people", "int"), ("Monto habilitado (USD)", "amount", "usd")], data, total=total, bar="share_f", last=6)
        ws.set_zoom(90)

    contents = [("Resumen", "Cifras clave, resultados por programa, mapa y aspectos destacados"),
                ("Programas", "Personas, cobros, montos y presupuesto de cada programa"),
                ("Serie mensual", "Cada programa, los montos y el presupuesto mes a mes")]
    contents += [(LEVEL_PLURALS[level], f"Bonos habilitados, personas y monto de cada {LEVEL_LABELS[level].lower()}") for level in levels
                 if ctx["territories"].get(level)]
    if ctx["types"]:
        contents.append(("Tipos", "Bonos habilitados por tipo de contingencia o evento"))
    contents.append(("Ficha técnica", "Identificación, definiciones y fuentes"))
    extra = [("Programas", ctx["programs_label"])]
    if levels:
        extra.append(("Nivel territorial", ", ".join(LEVEL_PLURALS[level] for level in levels)))
    book.facts_sheet(_facts(book, extra), ctx["definitions"], contents, sources=ctx.get("sources"))


# --------------------------------------------------------------------------------------- Jóvenes en Acción
def youth_book(book) -> None:
    ctx = book.ctx
    ws, row = _summary(book)
    phases = [{**p, "execution_f": _f(p["execution"]), "period_text": p["period_short"].capitalize(), "selected": p["current"]}
              for p in ctx["phases"]]
    layout = [("Fase", "name", "text", 1, 1), ("Periodo", "period_text", "text", 2, 2), ("Jóvenes participantes", "participants", "int", 4, 2),
              ("Presupuesto (USD)", "budget", "usd", 6, 2), ("Ejecutado (USD)", "execution_amount", "usd", 8, 2),
              ("Ejecución", "execution_f", "pct", 10, 1), ("Pagos acreditados (USD)", "accredited", "usd", 11, 2)]
    row = book.heading(ws, row, "Fases del programa", "Montos en USD", last=12)
    first, end, nxt = book.table(ws, row, layout, phases, header_height=36, gold=True)
    ws.insert_chart(nxt + 1, 1, book.column_chart("Resumen", first, end, 1, 4, "Jóvenes participantes por fase", width=820, height=280),
                    {"y_offset": 8, "object_position": 3})
    _finish_summary(book, ws, nxt + 17, ctx["insights"])

    ws, row = _sheet(book, "Fases", theme.VIOLETA_500, "Fases del programa", [2.4, 10.0, 26.0, 14.0, 14.0, 14.0, 16.0, 18.0, 18.0, 12.0, 20.0, 2.4])
    _block(book, ws, row + 1, "Participantes, presupuesto, ejecución y pagos", [
        ("Fase", "name", "text"), ("Periodo", "period_text", "text"), ("Registrados", "registered", "int"),
        ("Participantes", "participants", "int"), ("Transferencias por joven", "transfers", "int"), ("Valor de cada transferencia (USD)",
                                                                                                       "transfer_amount", "usd"),
        ("Presupuesto (USD)", "budget", "usd"), ("Ejecutado (USD)", "execution_amount", "usd"), ("Ejecución", "execution_f", "pct"),
        ("Pagos acreditados (USD)", "accredited", "usd")], phases, note="Fuente de las fases: SGDE", last=10, height=22)
    ws.set_zoom(90)

    payments = ctx["payments"]
    if payments:
        ws, row = _sheet(book, "Pagos por mes", theme.ORO, "Pagos acreditados por mes", [2.4, 22.0, 10.0, 18.0, 16.0, 20.0, 2.4],
                         landscape=False)
        data = [{**p, "phase_text": f"Fase {p['phase']}"} for p in payments]
        total = {"transfers": sum(p["transfers"] or 0 for p in payments), "amount": sum(p["amount"] or 0 for p in payments), "_label": "Total"}
        first, end, nxt = _block(book, ws, row + 1, "Jóvenes con pago acreditado y monto de cada mes", [
            ("Mes", "label", "text"), ("Fase", "phase_text", "text"), ("Jóvenes con pago", "people", "int"), ("Transferencias", "transfers", "int"),
            ("Monto acreditado (USD)", "amount", "usd")], data, total=total, note="Las personas no se suman entre meses", last=5)
        ws.insert_chart(nxt + 1, 1, book.column_chart("Pagos por mes", first, end, 1, 5, "Monto acreditado por mes (USD)", number_format="#,##0",
                                                      width=640, height=300), {"y_offset": 8, "object_position": 3})
        ws.set_zoom(95)

    months = ctx["budget_months"]
    if months:
        ws, row = _sheet(book, "Presupuesto", theme.FUCSIA, f"Presupuesto de la {ctx['info']['phase_name'].lower()}",
                         [2.4, 20.0, 22.0, 24.0, 16.0, 2.4], landscape=False)
        data = [{**m, "execution_f": _f(m["execution"])} for m in months]
        first, end, nxt = _block(book, ws, row + 1, "Devengado mensual y acumulado", [
            ("Mes", "label", "text"), ("Devengado del mes (USD)", "month_accrued", "usd"), ("Devengado acumulado (USD)", "accrued", "usd"),
            ("Ejecución acumulada", "execution_f", "pct")], data, note=f"Presupuesto aprobado: USD {ctx['info']['budget']:,.0f}".replace(",", "."),
            bar="execution_f", last=4)
        ws.insert_chart(nxt + 1, 1, book.column_chart("Presupuesto", first, end, 1, 2, "Presupuesto devengado por mes (USD)", number_format="#,##0",
                                                      width=600, height=300), {"y_offset": 8, "object_position": 3})
        ws.set_zoom(95)

    contents = [("Resumen", "Cifras clave, fases y aspectos destacados"), ("Fases", "Registrados, participantes, presupuesto, ejecución y pagos"),
                ("Pagos por mes", "Jóvenes con pago acreditado y monto de cada mes"), ("Presupuesto", "Devengado mensual y acumulado de la fase en curso"),
                ("Ficha técnica", "Identificación, definiciones y fuentes")]
    book.facts_sheet(_facts(book, [("Fases", ctx["programs_label"])]), ctx["definitions"], contents, sources=ctx.get("sources"))


# --------------------------------------------------------------------------------------- labour management
def labour_book(book) -> None:
    ctx = book.ctx
    ws, row = _summary(book)
    level = ctx["map_level"]
    row = book.heading(ws, row, f"Contratos vigentes por {LEVEL_LABELS[level].lower()}", ctx["cut"].get("contracts_label", ""), last=12)
    picture = map_png(ctx["map_values"], layer=level, selected=set(ctx["selected"]) if level == "provincia" else None,
                      focus=set(ctx["selected"]) if level == "canton" else None, label=f"Contratos vigentes por {LEVEL_LABELS[level].lower()}",
                      width=5.4, height=4.6, dpi=200)
    book.image(ws, row, 1, picture, 430, "mapa_contratos.png", y_offset=4, description="Mapa del Ecuador: contratos vigentes")
    rank_level = "canton" if level == "canton" or len(ctx["selected"]) == 1 else "provincia"
    rows = [{**r, "share_f": _f(r["share"])} for r in ctx["territories"][rank_level][:14]]
    first, end, nxt = book.table(ws, row, [(LEVEL_LABELS[rank_level], "name", "text", 8, 3), ("Contratos", "contracts", "int", 11, 1),
                                           ("Participación", "share_f", "pct", 12, 1)], rows, header_height=30)
    book.data_bar(ws, first, end, 12, theme.LILA_300, maximum=1)
    _finish_summary(book, ws, max(nxt, row + 23) + 1, ctx["insights"])

    for lvl in ("provincia", "canton"):
        rows = ctx["territories"].get(lvl) or []
        if not rows or (lvl == "canton" and "canton" not in ctx["levels"] and "provincia" in ctx["levels"] and len(ctx["levels"]) == 1):
            continue
        canton = lvl == "canton"
        widths = [2.4, 6.0, 40.0] + ([26.0] if canton else []) + [18.0, 14.0, 2.4]
        ws, row = _sheet(book, LEVEL_PLURALS[lvl], theme.VIOLETA_500 if lvl == "provincia" else theme.LILA_300,
                         f"Contratos vigentes por {LEVEL_LABELS[lvl].lower()}", widths, landscape=False)
        data = [{"n": i + 1, "place": r["name"], "province": r["province"], "contracts": r["contracts"], "share_f": _f(r["share"]),
                 "selected": r.get("selected")} for i, r in enumerate(rows)]
        total = {"contracts": sum(r["contracts"] or 0 for r in rows), "share_f": 1.0, "_label": "Total de la selección"}
        columns = [("N.º", "n", "center"), (LEVEL_LABELS[lvl], "place", "text")] + ([("Provincia", "province", "text")] if canton else []) + [
            ("Contratos vigentes", "contracts", "int"), ("Participación", "share_f", "pct")]
        _f1, _e1, nxt = _block(book, ws, row + 1, f"{LEVEL_PLURALS[lvl]}", columns, data, total=total, bar="share_f",
                               note=f"Corte: {ctx['cut'].get('contracts_label', '')}", last=len(columns), autofilter=canton)
        if lvl == "provincia" and ctx["companies"]:
            row = book.heading(ws, nxt + 2, "Empresas con contratos vigentes por provincia", last=len(columns))
            book.table(ws, row, [("Provincia", "name", "text", 2, 1), ("Empresas", "companies", "int", 3, 1)], ctx["companies"],
                       header_height=30)
        ws.set_zoom(95)

    ws, row = _sheet(book, "Perfil y actividad", theme.ORO, "Perfil y actividad económica", [2.4, 58.0, 18.0, 14.0, 2.4],
                     landscape=False)
    row += 1
    blocks = [(title, [{"name": p["name"], "contracts": p.get("contracts"), "share_f": _f(p["share"])} for p in parts])
              for title, parts in ctx["profile"].items()]
    blocks += [("Autoidentificación étnica", [{**r, "share_f": _f(r["share"])} for r in ctx["ethnicity"]]),
               ("Rama de actividad", [{**r, "share_f": _f(r["share"])} for r in ctx["branches"]]),
               ("Tipo de contrato", [{**r, "name": r["full"], "share_f": _f(r["share"])} for r in ctx["kinds"]]),
               ("Personas extranjeras por nacionalidad (10 principales)", [{**r, "share_f": _f(r["contracts"] / ctx["foreign_total"] * 100
                                                                                                  if ctx.get("foreign_total") else None)}
                                                                            for r in ctx["foreign"]])]
    for title, rows in blocks:
        if not rows:
            continue
        _f1, _e1, nxt = _block(book, ws, row, title, [("Categoría", "name", "text"), ("Contratos vigentes", "contracts", "int"),
                                                       ("Participación", "share_f", "pct")], rows, bar="share_f", last=3)
        row = nxt + 1
    ws.set_zoom(95)

    retirement = ctx["retirement"]
    if retirement:
        ws, row = _sheet(book, "Jubilación", theme.FUCSIA, "Compensación jubilar", [2.4, 40.0, 16.0, 20.0, 22.0, 14.0, 2.4], landscape=False)
        data = [{**r, "selected": r is retirement[-1]} for r in retirement]
        first, end, nxt = _block(book, ws, row + 1, "Expedientes y compensaciones por año", [
            ("Año", "label", "text"), ("Expedientes", "files", "int"), ("Compensaciones pagadas (USD)", "amount", "usd"),
            ("Promedio por expediente (USD)", "average", "usd")], data, note=f"Corte: {ctx['cut'].get('retirement_label', '')}", last=5)
        ws.insert_chart(nxt + 1, 1, book.column_chart("Jubilación", first, end, 1, 3, "Compensaciones pagadas por año (USD)", number_format="#,##0",
                                                      width=600, height=280), {"y_offset": 8, "object_position": 3})
        row = nxt + 17
        parts = ctx["retirement_parts"]
        for title, rows, amount in ((f"Por régimen laboral · {ctx['retirement_year']}", parts["regimes"], True),
                                    (f"Por sexo · {ctx['retirement_year']}", parts["sexes"], False),
                                    (f"Por provincia · {ctx['retirement_year']}", parts["provinces"], True)):
            if not rows:
                continue
            columns = [("Categoría", "name", "text"), ("Expedientes", "files", "int"), ("Participación", "share_f", "pct")]
            if amount:
                columns.append(("Compensaciones (USD)", "amount", "usd"))
            _f1, _e1, nxt = _block(book, ws, row, title, columns, [{**r, "share_f": _f(r["share"])} for r in rows], bar="share_f", last=5)
            row = nxt + 1
        ws.set_zoom(95)

    months = ctx["months"]
    if months:
        ws, row = _sheet(book, "Contratos por mes", theme.LILA_300, "Contratos por mes", [2.4, 22.0, 22.0, 16.0, 20.0, 2.4],
                         landscape=False)
        data = [{**m, "share_f": _f(m["share"])} for m in months]
        registrations = ctx["registrations"]
        first, end, nxt = _block(book, ws, row + 1, f"Contratos registrados en {registrations['year']} que siguen vigentes", [
            ("Mes", "label", "text"), ("Contratos registrados", "value", "int"), ("Participación", "share_f", "pct"),
            ("Acumulado del año", "cumulative", "int")], data, total={"value": registrations["total"], "share_f": 1.0, "_label": "Total del año"},
            note=f"Estado al {registrations['observed']}", bar="share_f", last=4)
        ws.insert_chart(nxt + 1, 1, book.column_chart("Contratos por mes", first, end, 1, 2, "Contratos registrados por mes", width=600, height=300),
                        {"y_offset": 8, "object_position": 3})
        ws.set_zoom(95)

    contents = [("Resumen", "Cifras clave, mapa, territorios principales y aspectos destacados"),
                ("Provincias", "Contratos vigentes y empresas de cada provincia")]
    if ctx["territories"].get("canton") and not ("canton" not in ctx["levels"] and len(ctx["levels"]) == 1):
        contents.append(("Cantones", "Contratos vigentes de cada cantón"))
    contents.append(("Perfil y actividad", "Sexo, edad, discapacidad, autoidentificación, rama, tipo de contrato y nacionalidad"))
    if retirement:
        contents.append(("Jubilación", "Expedientes y compensaciones por año, régimen, sexo y provincia"))
    if months:
        contents.append(("Contratos por mes", "Contratos registrados cada mes del año"))
    contents.append(("Ficha técnica", "Identificación, fechas de corte, definiciones y fuentes"))
    extra = [("Nivel territorial", ", ".join(LEVEL_PLURALS[lvl] for lvl in ctx["levels"])),
             ("Corte de contratos", ctx["cut"].get("contracts_label", "")), ("Corte de jubilación", ctx["cut"].get("retirement_label", ""))]
    book.facts_sheet(_facts(book, extra), ctx["definitions"], contents, sources=ctx.get("sources"))


# ------------------------------------------------------------------------------------------- social budget
def social_budget_book(book) -> None:
    ctx = book.ctx
    stats = ctx["stats"]
    ws, row = _summary(book, "")
    months = ctx["months"]
    data = [{"label": m["label"], "month_accrued": m["month_accrued"], "accrued": m["accrued"], "execution_f": _f(m["execution"]),
             "pace_f": m["month"] / 12, "selected": m["selected"]} for m in months]
    layout = [("Mes", "label", "text", 1, 2), ("Devengado del mes (USD)", "month_accrued", "usd", 3, 2),
              ("Devengado acumulado (USD)", "accrued", "usd", 5, 2), ("Ejecución acumulada", "execution_f", "pct", 7, 1),
              ("Ritmo uniforme", "pace_f", "pct", 8, 1)]
    row = book.heading(ws, row, "El año mes a mes", ctx["span"].capitalize(), last=12)
    first, end, nxt = book.table(ws, row, layout, data, header_height=36, gold=True)
    ws.insert_chart(nxt + 1, 1, book.column_chart("Resumen", first, end, 1, 3, "Presupuesto devengado por mes (millones de USD)",
                                                  number_format='#,##0.0,,', width=900, height=270), {"y_offset": 6, "object_position": 3})
    row = nxt + 16
    closing = ctx.get("closing")
    if closing:
        row = book.note(ws, row, f"Ritmo necesario de {closing['months']}: USD {closing['required']:,.0f} por mes para devengar el 100 % del "
                                 f"presupuesto aprobado; el promedio del año es de USD {closing['average']:,.0f} por mes."
                        .replace(",", "."), last=12, tone="gold") + 1
    _finish_summary(book, ws, row, ctx["insights"])

    ws, row = _sheet(book, "Programas", theme.VIOLETA_500, "Ejecución por programa presupuestario",
                     [2.4, 40.0, 38.0, 18.0, 18.0, 18.0, 19.0, 12.0, 18.0, 12.0, 18.0, 18.0, 2.4])
    programs = [{**p, "execution_f": _f(p["execution"]), "share_f": _f(p["share"])} for p in ctx["programs"]]
    columns = [("Programa presupuestario", "name", "text"), ("Grupo de gasto", "group", "text"), ("Planificado anual (USD)", "planned", "usd"),
               ("Presupuesto aprobado (USD)", "approved", "usd"), ("Devengado del mes (USD)", "month_accrued", "usd"),
               ("Devengado acumulado (USD)", "accrued", "usd"), ("Ejecución", "execution_f", "pct"), ("Saldo por devengar (USD)", "balance", "usd"),
               ("Peso en el aprobado", "share_f", "pct")]
    if closing:
        columns += [("Promedio mensual devengado (USD)", "average", "usd"), ("Necesario por mes hasta diciembre (USD)", "required", "usd")]
    total = {"planned": stats["planned"], "approved": stats["approved"], "month_accrued": stats["month"], "accrued": stats["accrued"],
             "execution_f": _f(stats["execution"]), "balance": stats["balance"], "share_f": 1.0, "_label": "Total de la selección"}
    if closing:
        total.update(average=closing["average"], required=closing["required"])
    _block(book, ws, row + 1, "Presupuesto aprobado, devengado y ejecución", columns, programs, total=total, bar="execution_f",
           note=ctx["span"].capitalize(), last=len(columns), height=22, autofilter=True)
    ws.set_zoom(90)

    matrix = ctx["matrix"]
    widths = [2.4, 40.0] + [15.0] * len(matrix["months"]) + [17.0, 2.4]
    ws, row = _sheet(book, "Programa y mes", theme.ORO, "Devengado de cada programa por mes", widths)
    rows = [{"name": r["name"], **{f"m{i}": v for i, v in enumerate(r["values"])}, "total": r["total"]} for r in matrix["rows"]]
    totals = {f"m{i}": sum((r["values"][i] or 0) for r in matrix["rows"]) for i in range(len(matrix["months"]))}
    totals.update(total=sum(r["total"] or 0 for r in matrix["rows"]), _label="Total")
    _block(book, ws, row + 1, "Devengado del mes (USD)", [("Programa presupuestario", "name", "text")] + [
        (month, f"m{i}", "usd") for i, month in enumerate(matrix["months"])] + [("Total del año", "total", "usd")], rows, total=totals,
        note=ctx["span"].capitalize(), last=len(widths) - 2, height=21)
    ws.set_zoom(90)

    contents = [("Resumen", "Cifras clave, el año mes a mes y aspectos destacados"),
                ("Programas", "Planificado, aprobado, devengado, ejecución, saldo y ritmo necesario de cada programa"),
                ("Programa y mes", "Devengado de cada programa en cada mes"), ("Ficha técnica", "Identificación, definiciones y fuentes")]
    book.facts_sheet(_facts(book, [("Programas", ctx["programs_label"]), ("Universo", "Grupos de gasto 58, 57 y 78")]), ctx["definitions"],
                     contents, sources=ctx.get("sources"))


from .risks import render_workbook as risk_book
from .enos import render_workbook as enos_book

BOOKS = {"contingencias": contingency_book, "jovenes": youth_book, "laboral": labour_book, "presupuesto_social": social_budget_book,
         "riesgos": risk_book, "seguimiento_enos": enos_book}
