"""Riesgos: the executive summary, the slides and the data workbook of the units of attention exposed to hazards.

Same filtered snapshot as the dashboard: unique units of attention (UA) by threat and category, threats faced at once,
their combinations, services and provinces; multihazard keeps the record count of the source matrix.  Summary (two A4
pages): key figures, the map, threats and categories, threats at once, combinations and findings; then services,
provinces with their threats, the units with the highest susceptibility when there is room, and the methodological
note.  Slides: cover, threats, combinations and services, territory, provinces and the methodological note.  Workbook:
Resumen, Amenazas, Servicios, Provincias, Unidades and Ficha técnica.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from src import names, riesgos, theme, ui
from .areas import _base, kpis_from_cards, note
from .context import number

PALETTE = [theme.LILA_300, theme.MORADO, theme.FUCSIA_700]
LEVEL_KEYS = ["media", "alta", "muy_alta"]
CONCURRENCY_COLORS = [theme.LILA_300, theme.VIOLETA_500, theme.MORADO, theme.MORADO_900]
SHORT_THREATS = {"Inundaciones": "Inundaciones", "Movimientos en masa": "Mov. en masa", "Sequía": "Sequía",
                 "Incendios forestales": "Incendios"}
SOURCES = ("SIIMTDH · DGID / SGDE / MTDH. Capas de inundaciones y sequía: MAGAP 2015; "
           "movimientos en masa: SNGR 2011; incendios forestales: SNGR 2015.")
CAUTION = ("Una unidad puede estar expuesta a varias amenazas: los totales entre amenazas no se suman. "
           "«Sin categoría reportada» no acredita ausencia de riesgo. Hay unidades sin coordenadas en la fuente.")


def pct(value) -> str:
    return "—" if value is None or value != value else f"{number(value, 1)} %"


def _phrase(names_list: list[str]) -> str:
    """«movimientos en masa e incendios forestales» · «inundaciones, sequía y movimientos en masa»."""
    words = [n[:1].lower() + n[1:] for n in names_list]
    if len(words) == 1:
        return words[0]
    last = words[-1]
    joint = "e" if last.startswith(("i", "hi")) and not last.startswith("hie") else "y"
    return f"{', '.join(words[:-1])} {joint} {last}"


def _combo_text(name: str) -> str:
    return _phrase(name.split(" + "))


# ------------------------------------------------------------------------------------------------ context
def _province_row(row: dict, total: float, selected: set[str]) -> dict:
    return {"code": str(row["provincia_codigo"]), "name": names.place(str(row["provincia"])), "units": int(row["expuestas"]),
            "multihazard": int(row.get("multiamenaza", 0) or 0), "share": row["expuestas"] / total if total else 0.0,
            "inventory": int(row["inventario"]), "exposure": row["porcentaje"], "very_high": int(row["Muy alta"]),
            "media": int(row["Media"]), "alta": int(row["Alta"]), "muy_alta": int(row["Muy alta"]),
            "threats": [int(row[name]) for name in riesgos.THREATS.values()],
            "threat_shares": [row[name] / row["inventario"] * 100 if row["inventario"] else None for name in riesgos.THREATS.values()],
            "selected": str(row["provincia_codigo"]) in selected}


def _insights(view, ctx: dict) -> list[dict]:
    inventory, exposed = ctx["inventory"], ctx["exposed"]
    levels = view.levels
    level_text = _phrase([level.lower() for level in levels]).replace(" y ", " o ").replace(" e ", " o ")
    keys = riesgos.threat_keys(view.threat)
    if len(keys) == len(riesgos.THREATS):
        against = "al menos una de las cuatro amenazas"
    elif len(keys) == 1:
        against = riesgos.THREATS[keys[0]].lower()
    else:
        against = f"al menos una de estas amenazas: {_phrase([riesgos.THREATS[k] for k in keys])}"
    out = [{"icon": "building", "text": f"{number(exposed)} de las {number(inventory)} UA de la selección "
                                        f"({pct(ctx['exposed_share'])}) se ubican en zonas de susceptibilidad {level_text} ante {against}."}]
    threats = sorted(ctx["threats"], key=lambda t: -t["units"])
    if len(threats) > 1 and threats[0]["units"]:
        first, rest = threats[0], [t for t in threats[1:3] if t["units"]]
        text = (f"{first['name']} es la amenaza con más UA expuestas: {number(first['units'])} ({pct(first['share'])} de las UA "
                f"de la selección)")
        if rest:
            text += "; le " + ("sigue " if len(rest) == 1 else "siguen ") + " y ".join(
                f"{t['name'].lower()} ({number(t['units'])})" for t in rest)
        out.append({"icon": "storm", "text": text + "."})
    elif threats and threats[0]["units"]:
        t = threats[0]
        parts = [f"{number(t[key])} en categoría {level.lower()}" for key, level in zip(LEVEL_KEYS, riesgos.LEVELS) if t[key]]
        if len(parts) > 1:
            out.append({"icon": "storm", "text": f"En {t['name'].lower()}, las {number(t['units'])} UA expuestas se reparten así: "
                                                 f"{_phrase(parts)}."})
    several = ctx["several"]
    if several and exposed:
        text = f"{number(several)} UA expuestas ({pct(several / exposed * 100)}) enfrentan dos o más amenazas a la vez"
        combo = next((c for c in ctx["combinations"] if c["threats"] > 1), None)
        if combo:
            text += f"; la combinación más frecuente es {_combo_text(combo['name'])} ({number(combo['units'])} UA)"
        out.append({"icon": "layers", "text": text + "."})
    very_high = ctx["very_high"]
    provinces = ctx["provinces"]
    if very_high:
        leader = max(provinces, key=lambda p: p["very_high"])
        out.append({"icon": "flame", "text": f"{number(very_high)} UA tienen al menos una amenaza en susceptibilidad muy alta; "
                                             f"{leader['name']} registra la mayor cantidad ({number(leader['very_high'])} UA, "
                                             f"{pct(leader['very_high'] / very_high * 100)})."})
    with_units = [p for p in provinces if p["units"]]
    if len(with_units) > 2:
        a, b = with_units[0], with_units[1]
        share = (a["units"] + b["units"]) / exposed * 100 if exposed else 0
        half = ctx["reach"][0]["half"] if ctx["reach"] else 0
        out.append({"icon": "map", "text": f"{a['name']} ({number(a['units'])} UA) y {b['name']} ({number(b['units'])}) concentran el "
                                           f"{pct(share)} de las UA expuestas; {number(half)} provincias reúnen la mitad."})
    elif with_units and len(view.provinces) == 1:
        # One province: its place among the provinces of the country, with the same services, threats and categories.
        p = with_units[0]
        national = next((r for r in ctx["national_provinces"] if r["code"] == p["code"]), None)
        whole = sum(r["units"] for r in ctx["national_provinces"])
        if national and whole:
            out.append({"icon": "map", "text": f"{p['name']} reúne {number(p['units'])} de las {number(whole)} UA expuestas del país con "
                                               f"esta selección ({pct(p['units'] / whole * 100)}) y ocupa el {national['position']}.º lugar "
                                               f"entre {len([r for r in ctx['national_provinces'] if r['units']])} provincias."})
    services = [s for s in ctx["services"] if s["units"]]
    if len(services) > 1:
        lead = services[0]
        text = f"{lead['name']} concentra {number(lead['units'])} UA expuestas ({pct(lead['share'])} del total)"
        exposure = max(services, key=lambda s: s["exposure"] or 0)
        if exposure["name"] != lead["name"]:
            text += f"; {exposure['name']} tiene la mayor proporción de sus UA expuestas ({pct(exposure['exposure'])})"
        out.append({"icon": "building", "text": text + "."})
    if ctx["multihazard"]:
        lead = max(provinces, key=lambda p: p["multihazard"])
        text = f"La matriz fuente registra {number(ctx['multihazard'])} registros de multiamenaza (inundaciones o movimientos en masa)"
        if len(provinces) > 1 and lead["multihazard"]:
            text += f"; {lead['name']} aporta {number(lead['multihazard'])}"
        out.append({"icon": "storm", "text": text + "."})
    out.append({"icon": "shield", "text": "La exposición territorial no confirma una afectación efectiva."})
    return out


def build_context(view, *, title: str) -> dict:
    from src.views.riesgos import DEFINITIONS, METHODOLOGY
    if getattr(view, "selected", None) is None or view.selected.empty:
        raise ValueError("No hay unidades expuestas con los filtros seleccionados.")
    if not view.matrix_available:
        raise ValueError("La matriz fuente de multiamenaza no está disponible para este corte.")
    total = riesgos.count_units(view.selected)
    detail = view.detail_selected
    if len(detail) != total or detail.codigo_ua.duplicated().any():
        raise ValueError("El detalle de unidades no coincide con el resumen de este corte.")
    units = view.unit_rows()
    units["nivel_maximo"] = riesgos.max_level(units, view.threat, view.levels)
    selected = set(view.provinces)
    threats = []
    for row in view.threats.to_dict("records"):
        item = {"name": row["amenaza"], **{key: int(row[level]) for key, level in zip(LEVEL_KEYS, riesgos.LEVELS)}}
        item["units"] = int(row["expuestas"])
        item["share"] = row["porcentaje"]
        threats.append(item)
    services = []
    for row in view.service_rows.to_dict("records"):
        if not row["inventario"]:
            continue
        services.append({"name": row["servicio"], "units": int(row["expuestas"]), "inventory": int(row["inventario"]),
                         "exposure": row["porcentaje"], "share": row["participacion"], "very_high": int(row["Muy alta"]),
                         "multihazard": int(row.get("multiamenaza", 0) or 0),
                         **{key: int(row[level]) for key, level in zip(LEVEL_KEYS, riesgos.LEVELS)},
                         "threat_shares": [row[n] / row["inventario"] * 100 for n in riesgos.THREATS.values()],
                         "threats": [int(row[n]) for n in riesgos.THREATS.values()]})
    provinces = [_province_row(r, total, selected) for r in view.province_rows.to_dict("records") if r["inventario"]]
    national_total = float(view.national_rows.expuestas.sum())
    national = [_province_row(r, national_total, selected) for r in view.national_rows.to_dict("records") if r["inventario"]]
    for index, row in enumerate(sorted(national, key=lambda p: -p["units"]), start=1):
        row["position"] = index
    multihazard = riesgos.count_records(view.multihazard)
    ctx = _base(view, "riesgos", title)
    if len(ctx["territory_label"]) > 48:
        ctx["territory_label"] = f"{len(view.provinces)} provincias seleccionadas"
    if len(ctx["programs_label"]) > 48:
        ctx["programs_label"] = f"{len(view.programs)} servicios seleccionados"
    ctx.update(
        source="Fuente: SIIMTDH · DGID / SGDE / MTDH", kpis=kpis_from_cards(view.kpi_cards()),
        inventory=view.inventory_units, exposed=total, exposed_share=total / view.inventory_units * 100 if view.inventory_units else None,
        very_high=view.very_high, several=view.several, multihazard=multihazard,
        threats=threats,
        concurrency=[{"label": f"{r['amenazas']} amenaza" + ("" if r["amenazas"] == 1 else "s"), "threats": int(r["amenazas"]),
                      "units": int(r["unidades"]), "share": r["porcentaje"]} for r in view.concurrent.to_dict("records")],
        combinations=[{"name": r["combinacion"], "threats": int(r["amenazas"]), "units": int(r["unidades"]), "share": r["porcentaje"]}
                      for r in view.combos.to_dict("records")],
        services=services, provinces=provinces, national_provinces=national,
        map_values={p["code"]: p["units"] for p in national}, selected_codes=sorted(selected),
        reach=view.reach_tiles(), units=units.to_dict("records"), levels=list(view.levels),
        scope=view.scope_items(), methodology=METHODOLOGY, definitions=DEFINITIONS, sources=SOURCES, caution=CAUTION,
        multi_note=riesgos.MULTI_NOTE, geoportal=ui.GEOPORTAL_URL, selection=view.selection_label,
        threat_label=view.threat_label, levels_label=view.levels_label,
    )
    kpis = ctx["kpis"]
    note(kpis, 0, f"{pct(ctx['exposed_share'])} del inventario de UA")
    note(kpis, 1, "Inundaciones o mov. en masa")
    if view.very_high is not None:
        note(kpis, 2, "Al menos una amenaza")
    note(kpis, 3, f"{pct(view.several / total * 100)} de las UA expuestas")
    ctx["insights"] = _insights(view, ctx)
    return ctx


# --------------------------------------------------------------------------------------------- summary (PDF)
def _level_rows(c, rows: list[dict], x: float, top: float, width: float, *, row_h: float = 31, share_key: str = "share",
                share_word: str = "") -> float:
    """Each row: its name and, at the right, its units and share; under them one bar split by category, figures inside."""
    from reportlab.lib import colors as rl_colors
    from reportlab.pdfbase import pdfmetrics
    from .pdf import C, INK, NIGHT, _clip
    peak = max([r["units"] for r in rows] or [1]) or 1
    y = top
    for row in rows:
        figure = f"{number(row['units'])} UA · {pct(row.get(share_key))}{share_word}"
        c.setFillColor(NIGHT)
        c.setFont("Text-Bold", 8.2)
        c.drawRightString(x + width, y, figure)
        c.setFillColor(INK)
        c.setFont("Text-Semi", 8.2)
        c.drawString(x, y, _clip(row["name"], "Text-Semi", 8.2, width - pdfmetrics.stringWidth(figure, "Text-Bold", 8.2) - 10))
        bar_y = y - 15
        c.setFillColor(C("#F1EEF6"))
        c.roundRect(x, bar_y, width, 10.5, 2.5, stroke=0, fill=1)
        cx = x
        for key, color in zip(LEVEL_KEYS, PALETTE):
            value = row.get(key) or 0
            length = width * value / peak
            if length <= 0:
                continue
            c.setFillColor(C(color))
            c.rect(cx, bar_y, max(0.6, length - 1.2), 10.5, stroke=0, fill=1)
            text = number(value)
            if pdfmetrics.stringWidth(text, "Text-Semi", 6.8) + 6 <= length - 1.2:
                c.setFillColor(rl_colors.white if key != "media" else C(theme.MORADO_900))
                c.setFont("Text-Semi", 6.8)
                c.drawCentredString(cx + (length - 1.2) / 2, bar_y + 3, text)
            cx += length
        y -= row_h
    return y


def _exposure_matrix(c, x: float, top: float, width: float, rows: list[dict], *, label: str = "Provincia", numbered: bool = True,
                     row_h: float = 12.2) -> float:
    """Rows (provinces or services) with their units, the share exposed, units in «muy alta», multihazard records and the
    share of their units exposed to each threat, shaded."""
    from reportlab.lib import colors as rl_colors
    from .pdf import C, INK, MIST, MUTED, NIGHT, PURPLE, _clip
    columns = ([("N.º", 18, "center")] if numbered else []) + [
        (label, None, "text"), ("UA", 40, "int"), ("Expuestas", 46, "int"), ("% expuesto", 46, "pct"), ("Muy alta", 40, "int"),
        ("Multi-\namenaza", 48, "int")]
    threat_w = 44
    fixed = sum(w for _h, w, _k in columns if w) + threat_w * 4
    widths = [w if w else width - fixed for _h, w, _k in columns]
    header_h = 24
    c.setFillColor(PURPLE)
    c.roundRect(x, top - header_h, width, header_h, 3.5, stroke=0, fill=1)
    cx = x
    c.setFillColor(rl_colors.white)
    c.setFont("Text-Bold", 6.7)
    for (header, _w, kind), w in zip(columns, widths):
        lines = header.split("\n")
        for index, line in enumerate(lines):
            y = top - header_h / 2 + (len(lines) - 1) * 3.8 - index * 7.6 - 2.3
            if kind == "text":
                c.drawString(cx + 5, y, line)
            elif kind == "center":
                c.drawCentredString(cx + w / 2, y, line)
            else:
                c.drawRightString(cx + w - 5, y, line)
        cx += w
    for index, name in enumerate(riesgos.THREATS.values()):
        c.drawCentredString(cx + threat_w * index + threat_w / 2, top - header_h / 2 - 2.3, SHORT_THREATS[name])
    y = top - header_h
    for i, row in enumerate(rows):
        y -= row_h
        chosen = row.get("selected")
        c.setFillColor(C(theme.ORO_100) if chosen else (MIST if i % 2 else rl_colors.white))
        c.rect(x, y, width, row_h, stroke=0, fill=1)
        values = ([row.get("position")] if numbered else []) + [row["name"], row["inventory"], row["units"], row["exposure"],
                                                                 row["very_high"], row["multihazard"]]
        cx = x
        base = y + row_h / 2 - 2.5
        for (_header, _w, kind), w, value in zip(columns, widths, values):
            if kind == "text":
                c.setFillColor(NIGHT if chosen else INK)
                c.setFont("Text-Bold" if chosen else "Text-Medium", 7.2)
                c.drawString(cx + 5, base, _clip(str(value), "Text-Medium", 7.2, w - 8))
            elif kind == "center":
                c.setFillColor(MUTED)
                c.setFont("Text-Semi", 7)
                c.drawCentredString(cx + w / 2, base, "" if value is None else str(value))
            else:
                c.setFillColor(INK)
                c.setFont("Text-Bold" if chosen else "Text-Medium", 7.2)
                c.drawRightString(cx + w - 5, base, pct(value) if kind == "pct" else number(value))
            cx += w
        for index, share in enumerate(row["threat_shares"]):
            t = (share or 0) / 100
            c.setFillColor(C(theme.ramp_at(t, theme.SEQUENTIAL[1:])) if share else C("#F4F2F8"))
            c.rect(cx + threat_w * index + 0.7, y + 0.7, threat_w - 1.4, row_h - 1.4, stroke=0, fill=1)
            c.setFillColor(rl_colors.white if t > 0.5 else INK)
            c.setFont("Text-Semi", 6.8)
            c.drawCentredString(cx + threat_w * index + threat_w / 2, base + 0.2, pct(share) if share else "—")
    c.setStrokeColor(C(theme.LILA_200))
    c.setLineWidth(0.8)
    c.line(x, y, x + width, y)
    return y


def _paragraph(c, text: str, x: float, top: float, width: float, *, size: float = 7.8, color=None, font: str = "Text") -> float:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from .pdf import INK
    para = Paragraph(escape(text), ParagraphStyle("risk", fontName=font, fontSize=size, leading=size * 1.36, textColor=color or INK))
    _w, height = para.wrap(width, 1000)
    para.drawOn(c, x, top - height)
    return top - height


def _paragraph_height(text: str, width: float, size: float = 7.8) -> float:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    return Paragraph(escape(text), ParagraphStyle("risk", fontName="Text", fontSize=size, leading=size * 1.36)).wrap(width, 1000)[1]


def _units_table(c, ctx: dict, top: float, bottom: float) -> float:
    """The units with the highest susceptibility of the selection, as many as the page holds."""
    from .pdf import M, W, _heading, _table
    width = W - 2 * M
    room = top - 30 - 22 - bottom
    count = int(room // 12.4)
    if count < 4:
        return top
    order = {"Muy alta": 3, "Alta": 2, "Media": 1}
    units = sorted(ctx["units"], key=lambda u: (-order.get(u.get("nivel_maximo"), 0), -u["amenazas"], u["provincia"], u["nombre"]))
    rows = [{"code": u["codigo_ua"], "name": u["nombre"], "service": u["servicio"], "province": u["provincia"],
             "level": u.get("nivel_maximo") or "—", "threats": u["amenazas"]} for u in units[:count]]
    _heading(c, "Unidades con la susceptibilidad más alta", M, top - 12, width,
             f"{number(len(rows))} de {number(len(ctx['units']))} UA expuestas")
    columns = [("Código UA", "code", 52, "text"), ("Unidad de atención", "name", None, "text"), ("Servicio", "service", 120, "text"),
               ("Provincia", "province", 78, "text"), ("Más alta", "level", 50, "text"), ("Amenazas", "threats", 46, "int")]
    return _table(c, M, top - 24, width, columns, rows, row_h=12.4)


def _method_height(ctx: dict, width: float) -> float:
    half = (width - 14) / 2
    definitions = sum(max(_paragraph_height(ctx["definitions"][i][1], half, 7), _paragraph_height(ctx["definitions"][i + 1][1], half, 7)
                          if i + 1 < len(ctx["definitions"]) else 0) + 16 for i in range(0, len(ctx["definitions"]), 2))
    return (26 + _paragraph_height(ctx["methodology"], width) + 8 + definitions
            + _paragraph_height(f"Fuentes: {ctx['sources']} {CAUTION_SHORT}", width, 7.2) + 22)


CAUTION_SHORT = "Los totales entre amenazas no se suman. Hay unidades sin coordenadas en la fuente."


def _method(c, ctx: dict, top: float) -> float:
    """Methodological note, definitions in two columns, sources and the link to the geoportal."""
    from .pdf import M, W, C, _heading
    width = W - 2 * M
    _heading(c, "Nota metodológica", M, top - 14, width)
    top = _paragraph(c, ctx["methodology"], M, top - 24, width) - 8
    half = (width - 14) / 2
    for start in range(0, len(ctx["definitions"]), 2):
        bottom = top
        for index, (term, text) in enumerate(ctx["definitions"][start:start + 2]):
            x = M + index * (half + 14)
            c.setFillColor(C(theme.MORADO_900))
            c.setFont("Text-Bold", 7.4)
            c.drawString(x, top - 8, term)
            bottom = min(bottom, _paragraph(c, text, x, top - 11, half, size=7))
        top = bottom - 5
    top = _paragraph(c, f"Fuentes: {ctx['sources']} {CAUTION_SHORT}", M, top - 1, width, size=7.2, color=C(theme.PIZARRA)) - 6
    c.setFillColor(C(theme.MORADO))
    c.setFont("Text-Bold", 8)
    c.drawString(M, top - 6, "Consultar el geoportal de unidades de atención y amenazas del Ministerio")
    c.linkURL(ctx["geoportal"], (M, top - 9, M + 320, top + 4), relative=0)
    return top - 12


def render_pdf(c, ctx: dict, pages: int) -> None:
    from .charts import emblem_png, map_png
    from .pdf import BOTTOM, H, M, _band, _bars, _heading, _kpis, _next_page, _picture, _slim_band
    from .pdf_areas import COLUMN, FULL, RIGHT, _caption, _columns, _legend, _two_findings

    selected = set(ctx["selected_codes"])
    y = _band(c, ctx, H, emblem_png(selected))
    y = _kpis(c, {**ctx, "share_word": ""}, y - 18)
    top = y - 20
    # The map of the country (with the service and threat filters) and the threats by category.
    _heading(c, "UA expuestas por provincia", M, top - 12, COLUMN, "En dorado, la selección" if selected else "")
    picture = map_png(ctx["map_values"], layer="provincia", selected=selected, mode="light", label="UA expuestas", width=4.8,
                      height=3.45, dpi=220)
    map_bottom = _picture(c, picture, M - 6, top - 22, COLUMN + 12, 3.45 / 4.8)
    _heading(c, "Amenazas y susceptibilidad", RIGHT, top - 12, COLUMN)
    _legend(c, [(color, level) for color, level in zip(PALETTE, riesgos.LEVELS) if level in ctx["levels"]], RIGHT, top - 32)
    step = 36 if len(ctx["threats"]) > 2 else 44
    threats_bottom = _level_rows(c, ctx["threats"], RIGHT, top - 52, COLUMN, row_h=step)
    _caption(c, f"% sobre las {number(ctx['inventory'])} UA de la selección.", RIGHT, threats_bottom + step - 26, COLUMN)
    right_bottom = threats_bottom + step - 32
    free = right_bottom - map_bottom
    if free > 74:
        # A short list of threats leaves room for the provinces of the country with the same selection.
        ranked = sorted(ctx["national_provinces"], key=lambda r: r["position"])
        count = int((free - 34) // 19.5)
        rows = ranked[:count]
        chosen = [r for r in ranked if r["selected"] and r not in rows]
        if chosen:
            rows = rows[:max(1, count - len(chosen))] + chosen[:count - 1]
        peak = max([r["units"] for r in rows] or [1]) or 1
        _heading(c, "Provincias con más UA expuestas", RIGHT, right_bottom - 14, COLUMN, "En el país, con esta selección")
        _bars(c, [{"name": r["name"], "position": r["position"], "selected": r["selected"], "fraction": r["units"] / peak,
                   "text": f"{number(r['units'])} UA"} for r in rows], RIGHT, right_bottom - 38, COLUMN, 19.5)
        right_bottom = right_bottom - 38 - len(rows) * 19.5
    top = min(map_bottom, right_bottom) - 10
    # Threats at once and their combinations.
    chart_h = 104
    _heading(c, "Amenazas simultáneas", M, top - 12, COLUMN, "UA expuestas · % del total")
    labels = [f"{r['label']}\n{pct(r['share'])}" for r in ctx["concurrency"]]
    _columns(c, labels, [r["units"] for r in ctx["concurrency"]], M - 4, top - 22, COLUMN + 8, chart_h,
             colors=CONCURRENCY_COLORS[:len(labels)], value_text=lambda v: f"{number(v)} UA", label_size=7.6)
    combos = ctx["combinations"][:6]
    _heading(c, "Combinaciones más frecuentes", RIGHT, top - 12, COLUMN, "UA · % de las expuestas")
    rows = [{"name": r["name"].replace("Movimientos en masa", "Mov. en masa"), "text": f"{number(r['units'])} · {pct(r['share'])}",
             "fraction": r["units"] / (combos[0]["units"] or 1)} for r in combos]
    _bars(c, rows, RIGHT, top - 36, COLUMN, 19.5)
    top = min(top - 22 - chart_h, top - 36 - len(rows) * 19.5) - 10
    _heading(c, "Aspectos destacados", M, top - 12, FULL)
    _two_findings(c, ctx["insights"], top - 24, rows=3, bottom=46)
    _next_page(c, ctx, 1, pages)

    # Page 2: services and provinces with their threats, the units with the highest susceptibility (when there is room)
    # and the methodological note.
    y = _slim_band(c, ctx, "Servicios, provincias y metodología", f"{ctx['territory_label']} · {ctx['programs_label']} · {ctx['selection']}")
    top = y - 22
    services = ctx["services"]
    levels_text = ctx["levels_label"].lower()
    _heading(c, "Servicios: exposición y amenazas", M, top - 12, FULL, f"Por amenaza: % de las UA con susceptibilidad {levels_text}")
    top = _exposure_matrix(c, M, top - 24, FULL, services, label="Servicio", numbered=False, row_h=15) - 16
    province_rows = sorted(ctx["national_provinces"], key=lambda r: r["position"]) if selected else list(ctx["provinces"])
    if not selected:
        for index, row in enumerate(province_rows, start=1):
            row["position"] = index
    method_h = _method_height(ctx, FULL)
    room = top - 24 - 24 - method_h - BOTTOM - 8
    row_h = max(10.4, min(12.6, room / max(1, len(province_rows))))
    _heading(c, "Provincias: exposición y amenazas", M, top - 12, FULL,
             ("En dorado, la selección · " if selected else "") + f"Por amenaza: % de las UA con susceptibilidad {levels_text}")
    top = _exposure_matrix(c, M, top - 24, FULL, province_rows, row_h=row_h) - 10
    if top - method_h - BOTTOM > 110:
        top = _units_table(c, ctx, top, BOTTOM + method_h + 6) - 10
    _method(c, ctx, top)


# --------------------------------------------------------------------------------------------- slides (PPTX)
def render_pptx(prs, ctx: dict) -> None:
    from lxml import etree
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
    from pptx.oxml.ns import qn
    from pptx.util import Inches, Pt
    from .charts import emblem_png, map_png
    from .pptx import TEXT, _bar_chart, _cover, _footer, _header, _picture, _rgb, _text
    from .pptx_areas import _columns_chart, _table, _title
    total_slides = 6
    _cover(prs, ctx, emblem_png(set(ctx["selected_codes"])), total_slides, share_word="")

    def slide(title, page):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        _header(s, title, f"{ctx['period_label']} · {ctx['territory_label']} · {ctx['selection']}")
        _footer(s, ctx, page, total_slides)
        s.notes_slide.notes_text_frame.text = "\n".join(f"{k}: {v}" for k, v in ctx["scope"]) + "\n" + ctx["sources"]
        return s

    def stacked(s, categories, rows, keys_levels, *, x, y, w, h, legend_names=None):
        data = CategoryChartData(number_format="#,##0")
        data.categories = categories
        for key, level in keys_levels:
            data.add_series(legend_names.get(level, level) if legend_names else level, [r[key] for r in rows])
        chart = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(x), Inches(y), Inches(w), Inches(h), data).chart
        chart.font.name = TEXT
        chart.font.size = Pt(11)
        chart.font.color.rgb = _rgb(theme.TINTA)
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.value_axis.minimum_scale = 0
        chart.value_axis.has_major_gridlines = False
        chart.value_axis.visible = False
        chart.category_axis.format.line.fill.background()
        chart.category_axis.reverse_order = True
        chart.plots[0].gap_width = 55
        chart.plots[0].overlap = 100
        level_colors = dict(zip(riesgos.LEVELS, PALETTE))
        for series, (_key, level) in zip(chart.series, keys_levels):
            series.format.fill.solid()
            series.format.fill.fore_color.rgb = _rgb(level_colors[level])
            series.format.line.color.rgb = _rgb("#FFFFFF")
            series.format.line.width = Pt(1.5)
        chart.plots[0].has_data_labels = True
        labels = chart.plots[0].data_labels
        labels.position = XL_LABEL_POSITION.CENTER
        labels.number_format = '#,##0;-#,##0;""'
        labels.number_format_is_linked = False
        labels.font.size = Pt(10)
        labels.font.color.rgb = _rgb("#FFFFFF")
        # Segments too short for their figure keep it out of sight (the table of the slide or the book carries it).
        reach = max([sum(r[key] for key, _level in keys_levels) for r in rows] or [1]) or 1
        for series, (key, _level) in zip(chart.series, keys_levels):
            short = [index for index, row in enumerate(rows) if row[key] and row[key] < reach * 0.075]
            if not short:
                continue
            # A label of its own on one point needs the labels of the whole series (they would otherwise hide).
            own = series.data_labels
            own.show_value = True
            own.position = XL_LABEL_POSITION.CENTER
            own.number_format = '#,##0;-#,##0;""'
            own.number_format_is_linked = False
            own.font.size = Pt(10)
            own.font.color.rgb = _rgb("#FFFFFF")
            for index in short:
                label = series.points[index].data_label._get_or_add_dLbl()
                for child in list(label):
                    if child.tag != qn("c:idx"):
                        label.remove(child)
                etree.SubElement(label, qn("c:delete")).set("val", "1")
        return chart

    levels = [(key, level) for key, level in zip(LEVEL_KEYS, riesgos.LEVELS) if level in ctx["levels"]]
    # 2. Threats by category and threats at once.
    s = slide("Exposición por amenaza", 2)
    _title(s, "Unidades expuestas por amenaza", 0.55, 1.36, 6.2, "UA por categoría de susceptibilidad")
    stacked(s, [t["name"] for t in ctx["threats"]], ctx["threats"], levels, x=0.45, y=2.1, w=6.4, h=3.95)
    _text(s, 0.55, 6.1, 6.2, 0.7, [f"{t['name']}: {number(t['units'])} UA ({pct(t['share'])} de las UA de la selección)"
                                   for t in ctx["threats"]][:4], size=10, color=theme.PIZARRA, spacing=0.95)
    _title(s, "Amenazas simultáneas", 7.05, 1.36, 5.8, "UA expuestas según cuántas amenazas enfrentan a la vez")
    _columns_chart(s, [r["label"] for r in ctx["concurrency"]], [r["units"] for r in ctx["concurrency"]], "UA expuestas",
                   x=6.95, y=2.1, w=5.95, h=3.95, colors=CONCURRENCY_COLORS[:len(ctx["concurrency"])], number_format='#,##0" UA"')
    _text(s, 7.05, 6.1, 5.8, 0.6, "   ·   ".join(f"{r['label']}: {pct(r['share'])}" for r in ctx["concurrency"]), size=10.5,
          color=theme.PIZARRA)
    # 3. Combinations and services.
    s = slide("Combinaciones y servicios", 3)
    combos = ctx["combinations"][:8]
    _title(s, "Combinaciones más frecuentes", 0.55, 1.36, 6.2, "UA expuestas en cada combinación de amenazas")
    chart = _bar_chart(s, [r["name"].replace("Movimientos en masa", "Mov. en masa") for r in combos], [r["units"] for r in combos], "UA",
                       x=0.45, y=2.05, w=6.4, h=4.75, number_format='#,##0" UA"')
    chart.category_axis.reverse_order = True
    chart.font.size = Pt(11)
    chart.plots[0].data_labels.font.size = Pt(11)
    _title(s, "UA expuestas por servicio", 7.05, 1.36, 5.8, "Según la susceptibilidad más alta de cada UA")
    stacked(s, [r["name"] for r in ctx["services"]], ctx["services"], levels, x=6.95, y=2.05, w=5.95, h=4.2,
            legend_names={level: f"Más alta: {level.lower()}" for level in riesgos.LEVELS})
    _text(s, 7.05, 6.25, 5.8, 0.6, "UA expuestas: " + "   ·   ".join(f"{r['name']}: {number(r['units'])} ({pct(r['exposure'])} de sus UA)"
                                                               for r in ctx["services"]), size=9.5, color=theme.PIZARRA)
    # 4. Territory: the map and the leading provinces.
    s = slide("Unidades expuestas por provincia", 4)
    picture = map_png(ctx["map_values"], layer="provincia", selected=set(ctx["selected_codes"]), mode="light", label="UA expuestas",
                      width=5.6, height=5.0, dpi=200)
    _picture(s, picture, 0.45, 1.4, h=5.5)
    ranked = sorted(ctx["national_provinces"], key=lambda p: -p["units"])[:12]
    _title(s, "Provincias con más UA expuestas", 7.05, 1.36, 5.8, "En dorado, la selección" if ctx["selected_codes"] else
           "UA expuestas de cada provincia")
    chart = _bar_chart(s, [p["name"] for p in ranked], [p["units"] for p in ranked], "UA expuestas", x=6.95, y=2.0, w=5.95, h=4.95,
                       number_format='#,##0" UA"')
    chart.category_axis.reverse_order = True
    chart.font.size = Pt(11)
    chart.plots[0].data_labels.font.size = Pt(11)
    for index, row in enumerate(ranked):
        point = chart.plots[0].series[0].points[index]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = _rgb(theme.ORO if row["selected"] else theme.SERIE_BONOS)
    # 5. Provinces in full.
    s = slide("Provincias: exposición y multiamenaza", 5)
    rows = sorted(ctx["national_provinces"] if ctx["selected_codes"] else ctx["provinces"], key=lambda p: -p["units"])
    columns = [("Provincia", "name", None, "text"), ("UA", "inventory", 0.8, "int"), ("Expuestas", "units", 0.95, "int"),
               ("% expuesto", "exposure", 1.0, "pct"), ("Multiamenaza*", "multihazard", 1.2, "int")]
    split = (len(rows) + 1) // 2 if len(rows) > 6 else len(rows)
    row_h = min(0.4, 4.45 / max(1, split))
    for x, part in [(0.5, rows[:split]), (6.9, rows[split:])]:
        if part:
            _table(s, x, 1.42, 5.95, columns, part, row_h=row_h, header_h=0.42, size=10.5 if split > 9 else 11.5)
    _text(s, 0.55, 6.5, 12.2, 0.5, "* " + ctx["multi_note"], size=10, color=theme.PIZARRA)
    # 6. Methodological note.
    s = slide("Nota metodológica", 6)
    _text(s, 0.65, 1.45, 12, 2.0, ctx["methodology"], size=15.5, spacing=1.12)
    half = 5.9
    for index, (term, text) in enumerate(ctx["definitions"]):
        x = 0.65 + (index % 2) * (half + 0.3)
        y = 3.62 + (index // 2) * 0.92
        _text(s, x, y, half, 0.3, term, size=12.5, color=theme.MORADO_900, bold=True)
        _text(s, x, y + 0.3, half, 0.6, text, size=11, color=theme.PIZARRA)
    _text(s, 0.65, 5.55, 12, 0.6, ctx["caution"], size=11.5, color=theme.PIZARRA)
    _text(s, 0.65, 6.1, 12, 0.4, f"Fuentes: {ctx['sources']}", size=11, color=theme.PIZARRA)
    link = _text(s, 0.65, 6.55, 12, 0.35, "Consultar el geoportal del Ministerio", size=14, color=theme.MORADO, bold=True)
    link.text_frame.paragraphs[0].runs[0].hyperlink.address = ctx["geoportal"]
    prs.slides[0].notes_slide.notes_text_frame.text += "\n" + "\n".join(f"{k}: {v}" for k, v in ctx["scope"])


# --------------------------------------------------------------------------------------------- workbook (XLSX)
def render_workbook(book) -> None:
    from .excel import DISPLAY, TEXT
    from .excel_areas import _block, _finish_summary, _sheet, _summary
    from .charts import map_png
    ctx = book.ctx
    levels = [(key, level) for key, level in zip(LEVEL_KEYS, riesgos.LEVELS) if level in ctx["levels"]]

    def stacked_chart(sheet, first, end, columns, title, names_map=None, width=760, height=320):
        chart = book.wb.add_chart({"type": "bar", "subtype": "stacked"})
        for col, level in columns:
            chart.add_series({"name": (names_map or {}).get(level, level), "categories": [sheet, first, 1, end, 1],
                              "values": [sheet, first, col, end, col], "fill": {"color": dict(zip(riesgos.LEVELS, PALETTE))[level]},
                              "border": {"color": "#FFFFFF", "width": 1.25}, "gap": 60,
                              "data_labels": {"value": True, "num_format": '#,##0;-#,##0;""',
                                              "font": {"name": TEXT, "size": 9, "color": "#FFFFFF"}}})
        chart.set_title({"name": title, "name_font": {"name": DISPLAY, "size": 12, "color": theme.MORADO_900}})
        chart.set_legend({"position": "top", "font": {"name": TEXT, "size": 10}})
        chart.set_y_axis({"reverse": True, "num_font": {"name": TEXT, "size": 10}, "line": {"none": True}})
        chart.set_x_axis({"min": 0, "num_format": "#,##0", "num_font": {"name": TEXT, "size": 9}, "major_gridlines": {"visible": False},
                          "label_position": "none"})
        chart.set_chartarea({"border": {"none": True}})
        chart.set_size({"width": width, "height": height})
        return chart

    # Resumen: key figures, threats by category with their chart, the map and the findings.
    ws, row = _summary(book, "")
    threats = [{**t, "share_f": (t["share"] or 0) / 100} for t in ctx["threats"]]
    columns = [("Amenaza", "name", "text", 1, 3)]
    columns += [(level, key, "int", 4 + i, 1) for i, (key, level) in enumerate(levels)]
    columns += [("UA expuestas", "units", "int", 4 + len(levels), 2), ("% de las UA", "share_f", "pct", 6 + len(levels), 2)]
    row = book.heading(ws, row, "Amenazas y susceptibilidad", ctx["selection"], last=12)
    first, end, row = book.table(ws, row, columns, threats, header_height=30, height=22)
    chart = stacked_chart("Resumen", first, end, [(4 + i, level) for i, (_k, level) in enumerate(levels)],
                          "Unidades expuestas por amenaza y susceptibilidad", width=520, height=300)
    ws.insert_chart(row + 1, 1, chart)
    picture = map_png(ctx["map_values"], layer="provincia", selected=set(ctx["selected_codes"]), label="UA expuestas", width=4.6,
                      height=4.0, dpi=200)
    book.image(ws, row + 1, 8, picture, 330, "mapa_riesgos.png", description="Mapa del Ecuador: UA expuestas por provincia")
    _finish_summary(book, ws, row + 18, ctx["insights"][:6])

    # Amenazas: categories, threats at once and combinations.
    ws, row = _sheet(book, "Amenazas", theme.FUCSIA_700, "Amenazas y susceptibilidad", [2.4, 46, 15, 15, 15, 17, 17, 2.4])
    columns = [("Amenaza", "name", "text")] + [(level, key, "int") for key, level in levels] + \
              [("UA expuestas", "units", "int"), ("% de las UA", "share_f", "pct")]
    first, end, row = _block(book, ws, row + 1, "Unidades por amenaza y categoría", columns, threats, note=ctx["selection"],
                             last=len(columns), height=24, bar="share_f")
    ws.insert_chart(row + 1, 1, stacked_chart("Amenazas", first, end, [(2 + i, level) for i, (_k, level) in enumerate(levels)],
                                              "Unidades por amenaza y susceptibilidad"))
    row += 18
    concurrency = [{**r, "share_f": (r["share"] or 0) / 100} for r in ctx["concurrency"]]
    first, end, row = _block(book, ws, row, "Amenazas simultáneas", [("Amenazas a la vez", "label", "text"), ("UA expuestas", "units", "int"),
                             ("% de las UA expuestas", "share_f", "pct")], concurrency, total={"units": ctx["exposed"], "share_f": 1},
                             last=3, height=22, bar="share_f")
    ws.insert_chart(first - 2, 5, book.column_chart("Amenazas", first, end, 1, 2, "UA según amenazas a la vez", width=430, height=250))
    row = max(row, first + 12) + 1
    combos = [{**r, "share_f": (r["share"] or 0) / 100} for r in ctx["combinations"]]
    first, end, row = _block(book, ws, row, "Combinaciones de amenazas", [("Combinación", "name", "text"), ("Amenazas", "threats", "int"),
                             ("UA expuestas", "units", "int"), ("% de las UA expuestas", "share_f", "pct")], combos,
                             total={"units": ctx["exposed"], "share_f": 1}, last=4, height=22, bar="share_f", autofilter=True)
    ws.freeze_panes(4, 0)

    # Servicios.
    ws, row = _sheet(book, "Servicios", theme.VIOLETA_500, "Unidades expuestas por servicio",
                     [2.4, 34, 13, 13, 13, 13, 13, 13, 15, 15, 15, 15, 2.4])
    services = [{**s, "exposure_f": (s["exposure"] or 0) / 100, "share_f": (s["share"] or 0) / 100,
                 **{f"t{i}": v for i, v in enumerate(s["threats"])}} for s in ctx["services"]]
    columns = [("Servicio", "name", "text"), ("UA del servicio", "inventory", "int"), ("UA expuestas", "units", "int"),
               ("% expuesto", "exposure_f", "pct"), ("Participación", "share_f", "pct")]
    columns += [(f"Más alta: {level.lower()}", key, "int") for key, level in levels]
    columns += [(name, f"t{i}", "int") for i, name in enumerate(riesgos.THREATS.values())]
    total = {"inventory": ctx["inventory"], "units": ctx["exposed"], "share_f": 1}
    first, end, row = _block(book, ws, row + 1, "Servicios de la selección", columns, services, total=total, last=len(columns),
                             note=ctx["selection"], height=24, bar="exposure_f")
    ws.insert_chart(row + 1, 1, stacked_chart("Servicios", first, end, [(6 + i, level) for i, (_k, level) in enumerate(levels)],
                                              "UA expuestas por servicio según su susceptibilidad más alta",
                                              {level: f"Más alta: {level.lower()}" for level in riesgos.LEVELS}, width=820, height=300))
    ws.merge_range(row + 17, 1, row + 17, len(columns), "Las columnas de amenazas cuentan las UA del servicio con la amenaza en las "
                   "categorías elegidas; una unidad puede estar en varias amenazas, por lo que no se suman.",
                   book.f(font_size=10, text_wrap=True, font_color=theme.PIZARRA))
    ws.set_row(row + 17, 32)
    ws.freeze_panes(first, 2)

    # Provincias (the selection; columns B to E keep the layout of the first version of the book).
    ws, row = _sheet(book, "Provincias", theme.MORADO, "Unidades expuestas por provincia",
                     [2.4, 30, 15, 17, 14, 14, 13, 13, 15, 15, 15, 15, 2.4])
    provinces = [{**p, "share_f": p["share"], "exposure_f": (p["exposure"] or 0) / 100,
                  **{f"t{i}": v for i, v in enumerate(p["threats"])}} for p in ctx["provinces"]]
    columns = [("Provincia", "name", "text"), ("UA expuestas", "units", "int"), ("Multiamenaza*", "multihazard", "int"),
               ("Participación", "share_f", "pct"), ("UA de la provincia", "inventory", "int"), ("% expuesto", "exposure_f", "pct"),
               ("Muy alta", "very_high", "int")]
    columns += [(name, f"t{i}", "int") for i, name in enumerate(riesgos.THREATS.values())]
    total = {"units": ctx["exposed"], "multihazard": sum(p["multihazard"] for p in ctx["provinces"]), "share_f": 1,
             "inventory": ctx["inventory"], "very_high": ctx["very_high"] or 0}
    first, end, row = _block(book, ws, row + 1, "Distribución territorial", columns, provinces, last=len(columns), note=ctx["selection"],
                             total=total, autofilter=True, height=22, bar="exposure_f")
    ws.merge_range(row + 1, 1, row + 1, len(columns), "* " + ctx["multi_note"],
                   book.f(font_size=10, text_wrap=True, font_color=theme.PIZARRA))
    ws.set_row(row + 1, 40)
    picture = map_png(ctx["map_values"], layer="provincia", selected=set(ctx["selected_codes"]), label="UA expuestas", width=5.0,
                      height=4.3, dpi=200)
    book.image(ws, row + 3, 1, picture, 420, "mapa_provincias.png", description="Mapa del Ecuador: UA expuestas por provincia")
    ws.freeze_panes(first, 2)

    # Unidades (code and name of every exposed unit, as on the dashboard).
    ws, row = _sheet(book, "Unidades", theme.FUCSIA, "Unidades de atención expuestas", [2.4, 17, 58, 36, 28, 25, 25, 25, 25, 13, 2.4])
    columns = [("Código UA", "codigo_ua", "code"), ("Unidad de atención", "nombre", "text"), ("Servicio", "servicio", "text"),
               ("Provincia", "provincia", "text")]
    columns += [(label, key, "text") for key, label in riesgos.THREATS.items()]
    columns.append(("Amenazas", "amenazas", "int"))
    first, end, row = _block(book, ws, row + 1, "Detalle de la selección", columns, ctx["units"], last=len(columns),
                             note=ctx["selection"], height=30, autofilter=True)
    for offset, unit in enumerate(ctx["units"]):
        if len(unit["nombre"]) > 52:
            ws.set_row(first + offset, 15 * ((len(unit["nombre"]) + 51) // 52) + 4)
    ws.freeze_panes(first, 3)
    ws.repeat_rows(first - 1)
    ws.set_zoom(80)

    facts = [("Institución", ctx["institution"]), *ctx["scope"], *book.update_facts(),
             ("Generado", ctx["generated_label"]),
             ("Unidad de medida", "UA únicas; multiamenaza conserva el conteo de registros de la matriz fuente.")]
    book.facts_sheet(facts,
        [("UA expuestas", "Unidades únicas con susceptibilidad media, alta o muy alta en las amenazas seleccionadas."),
         ("Multiamenaza", ctx["multi_note"]),
         *[(term, text) for term, text in ctx["definitions"] if term not in ("UA expuesta", "Multiamenaza")],
         ("Detalle", "Una fila por código UA; las cuatro amenazas conservan la categoría reportada en la fuente.")],
        [("Resumen", "Cifras clave, amenazas, mapa y aspectos destacados"), ("Amenazas", "Categorías, amenazas simultáneas y combinaciones"),
         ("Servicios", "Exposición de cada servicio"), ("Provincias", "Distribución territorial y mapa"),
         ("Unidades", "Código, nombre, servicio, provincia y susceptibilidad")],
        sources=[("Fuentes", ctx["sources"], ""), ("Geoportal", "Visor geográfico del Ministerio", ctx["geoportal"])])
    ws = book.wb.get_worksheet_by_name("Ficha técnica")
    # The shared fact template uses compact rows; expand its long scope/source entries.
    strings = {index: text for text, index in book.wb.str_table.string_table.items()}
    for r, cells in ws.table.items():
        cell = cells.get(2)
        if cell is not None and hasattr(cell, "string"):
            text = strings.get(cell.string, "")
            if len(text) > 95:
                ws.set_row(r, max(38, 15 * ((len(text) + 84) // 85)))
    row = book.heading(ws, ws.dim_rowmax + 2, "Nota metodológica", last=2)
    ws.merge_range(row, 1, row, 2, ctx["methodology"], book.f(font_size=11, text_wrap=True, valign="top", font_color=theme.TINTA))
    ws.set_row(row, 130)
    ws.merge_range(row + 2, 1, row + 2, 2, ctx["caution"], book.f(font_size=10, text_wrap=True, font_color=theme.PIZARRA))
    ws.set_row(row + 2, 50)
