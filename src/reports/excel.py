"""Institutional Excel workbook: the data book of InfoReportes.

Built with XlsxWriter from the same report context as the one-page summary and the slides.  Five sheets:
Resumen, results by program (or service), Provincias, Detalle and Ficha técnica.  Design rules:
* every figure is a real number with a number format (no numbers as text);
* totals are live formulas that also carry their computed value, so they read correctly in Excel,
  LibreOffice, Google Sheets and phone previews;
* charts are native Excel charts, editable by the reader;
* colours, fonts and the Office theme of the file follow the MTDH identity, so tables or charts the reader
  adds later inherit the institutional palette.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

import xlsxwriter
from PIL import Image
from xlsxwriter.utility import xl_rowcol_to_cell

from src import theme
from .charts import map_png
from .context import number

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
ICONS = ROOT / "assets" / "icons" / "png"
DISPLAY = theme.OFFICE_DISPLAY
TEXT = theme.OFFICE_TEXT
WHITE = "#FFFFFF"
MUTED = "#6E6880"
SOFT_LINE = "#E7E2EF"
NA_COLOR = "#8A80A0"
TONES = [theme.MORADO, theme.VIOLETA_500, theme.ORO, theme.FUCSIA]

INT = "#,##0"
USD = "#,##0.00"
MILL = "#,##0.00,,"
MILL_KPI = '"USD "#,##0.0,," M"'
PCT = "0.0%"
NUMERIC = ("int", "units", "usd", "mill", "pct")


def _share(part, whole):
    return (part or 0) / whole if whole else None


class Workbook:
    def __init__(self, context: dict):
        self.ctx = context
        self.out = BytesIO()
        self.wb = xlsxwriter.Workbook(self.out, {"in_memory": True, "strings_to_numbers": False,
                                                 "strings_to_formulas": False, "strings_to_urls": False})
        self._formats: dict = {}
        self.year = context.get("year", 0)
        self._col_widths: dict[str, list[float]] = {}
        self._logo_png = self._trimmed_logo()

    # ------------------------------------------------------------------ styles
    def f(self, **props):
        base = {"font_name": TEXT, "font_size": 10.5, "font_color": theme.TINTA, "valign": "vcenter"}
        base.update(props)
        key = tuple(sorted((k, str(v)) for k, v in base.items()))
        if key not in self._formats:
            self._formats[key] = self.wb.add_format(base)
        return self._formats[key]

    def cell_format(self, kind, fill, **extra):
        props = dict(bg_color=fill, bottom=7, bottom_color=SOFT_LINE)
        if kind in NUMERIC:
            props.update(num_format={"int": INT, "units": INT, "usd": USD, "mill": MILL, "pct": PCT}[kind], align="right")
        elif kind == "code":
            props.update(align="left", font_color=MUTED, indent=1)
        elif kind == "center":
            props.update(align="center", font_color=MUTED)
        else:
            props.update(align="left", indent=1, text_wrap=True)
        props.update(extra)
        return self.f(**props)

    def na_format(self, fill, **extra):
        return self.f(bg_color=fill, italic=True, font_color=NA_COLOR, align="right", bottom=7, bottom_color=SOFT_LINE, **extra)

    # ------------------------------------------------------------- utilities
    def widths(self, ws, values):
        self._col_widths[ws.name] = list(values)
        for col, width in enumerate(values):
            ws.set_column(col, col, width)

    @staticmethod
    def px(width: float) -> int:
        """Excel column width (characters) to pixels, as XlsxWriter computes it."""
        return int(width * 12 + 0.5) if width < 1 else int(width * 7 + 0.5) + 5

    def page(self, ws, landscape=True, tall=0):
        ws.hide_gridlines(2)
        ws.set_paper(9)
        if landscape:
            ws.set_landscape()
        ws.set_margins(left=0.35, right=0.35, top=0.6, bottom=0.55)
        ws.fit_to_pages(1, tall)
        ws.center_horizontally()
        ws.set_header(f'&L&"{DISPLAY},Bold"&9&K512F8DMinisterio de Trabajo y Desarrollo Humano'
                      f'&R&"{TEXT},Regular"&9&K5A5765{self.ctx["period_label"]}')
        ws.set_footer(f'&L&"{TEXT},Regular"&8&K5A5765InfoReportes · Indicadores estratégicos'
                      f'&C&"{TEXT},Regular"&8&K5A5765Página &P de &N'
                      f'&R&"{TEXT},Regular"&8&K5A5765Fuente: Ministerio de Trabajo y Desarrollo Humano')

    def _trimmed_logo(self) -> bytes | None:
        if not LOGO.exists():
            return None
        with Image.open(LOGO) as image:
            image = image.convert("RGBA")
            box = image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
            if box:
                image = image.crop(box)
            buffer = BytesIO()
            image.save(buffer, format="PNG", dpi=(96, 96))
        return buffer.getvalue()

    def image(self, ws, row, col, data: bytes, width_px: float, name: str, x_offset=0, y_offset=0, description=""):
        with Image.open(BytesIO(data)) as picture:
            dpi = picture.info.get("dpi", (96, 96))[0] or 96
            native = picture.size[0] * 96 / dpi
        scale = width_px / native
        ws.insert_image(row, col, name, {"image_data": BytesIO(data), "x_scale": scale, "y_scale": scale,
                                          "x_offset": x_offset, "y_offset": y_offset, "object_position": 3,
                                          "description": description or name})

    def logo(self, ws, row, col, height_px, x_offset=0, y_offset=0, right_edge: int | None = None):
        """Insert the official logo; with ``right_edge`` it ends at that column's right border."""
        if not self._logo_png:
            return
        with Image.open(BytesIO(self._logo_png)) as picture:
            width, height = picture.size
        width_px = width * height_px / height
        if right_edge is not None:
            widths = self._col_widths.get(ws.name, [])
            room, col = 0, right_edge
            while col > 0:
                room += self.px(widths[col] if col < len(widths) else 8.43)
                if room >= width_px + 14:
                    break
                col -= 1
            x_offset = max(0, int(room - width_px - 14))
        self.image(ws, row, col, self._logo_png, width_px, "logo_mtdh.png", x_offset, y_offset,
                   "Gobierno del Ecuador · Ministerio de Trabajo y Desarrollo Humano")

    # ------------------------------------------------------------- components
    def band(self, ws, title: str, subtitle: str, last: int, compact=False) -> int:
        """Purple header plate with logo, title and context, closed by a gold rule."""
        heights = [8, 32, 20, 10] if compact else [12, 40, 22, 14]
        for row, height in enumerate(heights):
            ws.set_row(row, height)
            for col in range(last + 1):
                ws.write_blank(row, col, None, self.f(bg_color=theme.MORADO))
        ws.write(1, 1, title, self.f(bg_color=theme.MORADO, font_name=DISPLAY, font_size=17 if compact else 20, bold=True, font_color=WHITE))
        ws.write(2, 1, subtitle, self.f(bg_color=theme.MORADO, font_size=10, font_color="#E4DBF3"))
        gold = len(heights)
        ws.set_row(gold, 5)
        for col in range(last + 1):
            ws.write_blank(gold, col, None, self.f(bg_color=theme.ORO))
        self.logo(ws, 1, 0, 34 if compact else 40, y_offset=2, right_edge=last - 1)
        return gold + 1

    def heading(self, ws, row, text, note="", first=1, last=12) -> int:
        ws.set_row(row, 27)
        line = dict(bottom=2, bottom_color=theme.LILA_200)
        ws.write(row, first, text, self.f(font_name=DISPLAY, font_size=13, bold=True, font_color=theme.MORADO_900, **line))
        for col in range(first + 1, last + 1):
            ws.write_blank(row, col, None, self.f(**line))
        if note:
            ws.write(row, last, note, self.f(font_size=9, italic=True, font_color=MUTED, align="right", **line))
        return row + 1

    def note(self, ws, row, text, first=1, last=12, height=32, tone="info") -> int:
        bg, color, edge = ((theme.LILA_50, theme.MORADO_800, theme.MORADO) if tone == "info"
                           else (theme.ORO_100, "#6B4A00", theme.ORO))
        ws.set_row(row, height)
        ws.merge_range(row, first, row, last, text, self.f(bg_color=bg, font_size=9.5, font_color=color, text_wrap=True,
                                                           indent=1, left=5, left_color=edge))
        return row + 1

    def kpi(self, ws, row, col, span, label, value, num_format, note, accent):
        bg = theme.NIEBLA
        last = col + span - 1
        self._put(ws, row, col, span, label, self.f(bg_color=bg, font_size=9.5, bold=True, font_color=theme.PIZARRA,
                                                    top=5, top_color=accent, indent=1, text_wrap=True))
        if value is None:
            ws.merge_range(row + 1, col, row + 2, last, "—", self.f(bg_color=bg, font_name=DISPLAY, font_size=15, bold=True,
                                                                                font_color=NA_COLOR, indent=1))
        else:
            ws.merge_range(row + 1, col, row + 2, last, None, self.f(bg_color=bg))
            ws.write_number(row + 1, col, value, self.f(bg_color=bg, font_name=DISPLAY, font_size=22, bold=True, font_color=theme.MORADO_900,
                                                        num_format=num_format, align="left", indent=1, shrink=True))
        self._put(ws, row + 3, col, span, note, self.f(bg_color=bg, font_size=9, font_color=MUTED, indent=1,
                                                       text_wrap=True, valign="top"))

    def kpi_row(self, ws, row, cards, first=1, last=12) -> int:
        """Tiles spread over the columns first..last (leaving a one-column gutter between them)."""
        ws.set_row(row, 24)
        ws.set_row(row + 1, 21)
        ws.set_row(row + 2, 21)
        ws.set_row(row + 3, 30)
        widths = self._col_widths.get(ws.name, [])
        cols = list(range(first, last + 1))
        sizes = [self.px(widths[c]) if c < len(widths) else 64 for c in cols]
        cumulative = [sum(sizes[:i + 1]) for i in range(len(sizes))]
        target = cumulative[-1] / len(cards)
        cuts, previous = [], -1
        for k in range(1, len(cards)):
            # Cut where the running width is closest to k equal shares, leaving a column per remaining tile.
            options = range(previous + 1, len(cols) - (len(cards) - k))
            best = min(options, key=lambda i: abs(cumulative[i] - k * target))
            cuts.append(best)
            previous = best
        bounds = [-1] + cuts + [len(cols) - 1]
        for k, card in enumerate(cards):
            group = cols[bounds[k] + 1: bounds[k + 1] + 1]
            self.kpi(ws, row, group[0], len(group), *card)
        return row + 4

    def table(self, ws, row, layout, rows, *, total=None, label_index=0, subtotal=False, header_height=34, height=19):
        """Styled table on a column layout.

        ``layout`` items are (header, key, kind, first_col, span).  Kinds: text,
        code, center, int, units, usd, mill, pct.  Missing numbers read as a dash.
        Returns (first, last, next).
        """
        ws.set_row(row, header_height)
        for index, (header, _key, kind, col, span) in enumerate(layout):
            align = "right" if kind in NUMERIC else ("center" if kind == "center" else "left")
            # A hairline between header cells keeps neighbouring wrapped titles from reading as one.
            divider = dict(left=1, left_color="#7458AE") if index else {}
            fmt = self.f(bg_color=theme.MORADO, font_name=DISPLAY, font_size=9, bold=True, font_color=WHITE, text_wrap=True,
                         align=align, indent=1 if align == "left" else 0, **divider)
            self._put(ws, row, col, span, header, fmt)
        first = row + 1
        for i, item in enumerate(rows):
            r = first + i
            ws.set_row(r, height)
            fill = theme.NIEBLA if i % 2 else WHITE
            for index, (_header, key, kind, col, span) in enumerate(layout):
                value = item.get(key) if isinstance(item, dict) else item[key]
                strong = index == label_index
                self._value(ws, r, col, span, value, kind, fill, strong)
        last = first + len(rows) - 1
        nxt = last + 1
        if total is not None and rows:
            ws.set_row(nxt, 22)
            edge = dict(top=2, top_color=theme.MORADO)
            for index, (_header, key, kind, col, span) in enumerate(layout):
                if index == label_index:
                    self._put(ws, nxt, col, span, total.get("_label", "Total de la selección"),
                              self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
                    continue
                if key not in total or kind not in NUMERIC:
                    self._put(ws, nxt, col, span, None, self.f(bg_color=theme.LAVANDA, **edge))
                    continue
                value = total[key]
                fmt = self.cell_format(kind, theme.LAVANDA, bold=True, **edge)
                if value is None:
                    self._put(ws, nxt, col, span, "—", self.f(bg_color=theme.LAVANDA, bold=True, italic=True, font_color=NA_COLOR,
                                                                 align="right", **edge))
                    continue
                if span > 1:
                    ws.merge_range(nxt, col, nxt, col + span - 1, None, fmt)
                if kind == "pct":
                    ws.write_number(nxt, col, value, fmt)
                else:
                    rng = f"{xl_rowcol_to_cell(first, col)}:{xl_rowcol_to_cell(last, col)}"
                    ws.write_formula(nxt, col, f"=SUBTOTAL(109,{rng})" if subtotal else f"=SUM({rng})", fmt, value)
            nxt += 1
        return first, last, nxt

    def _put(self, ws, row, col, span, value, fmt):
        if span > 1:
            ws.merge_range(row, col, row, col + span - 1, value, fmt)
        elif value is None:
            ws.write_blank(row, col, None, fmt)
        else:
            ws.write(row, col, value, fmt)

    def _value(self, ws, row, col, span, value, kind, fill, strong=False):
        if kind in NUMERIC:
            if value is None or value != value:
                self._put(ws, row, col, span, "—", self.na_format(fill))
                return
            fmt = self.cell_format(kind, fill, bold=strong)
            if span > 1:
                ws.merge_range(row, col, row, col + span - 1, None, fmt)
            ws.write_number(row, col, float(value), fmt)
            return
        extra = dict(bold=True, font_color=theme.MORADO_900) if strong else {}
        self._put(ws, row, col, span, "" if value is None else str(value), self.cell_format(kind, fill, **extra))

    def data_bar(self, ws, first, last, col, color, maximum=None):
        options = {"type": "data_bar", "bar_color": color, "bar_solid": True, "bar_no_border": True,
                   "min_type": "num", "min_value": 0}
        if maximum is not None:
            options.update(max_type="num", max_value=maximum)
        ws.conditional_format(first, col, last, col, options)

    def bar_chart(self, sheet, first, last, cat_col, val_col, title, colors, number_format=INT, width=560, height=340):
        chart = self.wb.add_chart({"type": "bar"})
        series = {
            "name": title, "categories": [sheet, first, cat_col, last, cat_col], "values": [sheet, first, val_col, last, val_col],
            "fill": {"color": colors[0]}, "border": {"none": True}, "gap": 55,
            "data_labels": {"value": True, "num_format": number_format, "position": "outside_end",
                            "font": {"name": TEXT, "size": 9, "color": theme.TINTA}},
        }
        if len(colors) > 1:
            series["points"] = [{"fill": {"color": color}, "border": {"none": True}} for color in colors]
        chart.add_series(series)
        chart.set_title({"name": title, "overlay": False,
                         "name_font": {"name": DISPLAY, "size": 11, "bold": True, "color": theme.MORADO_900}})
        # In an Excel bar chart the horizontal x axis carries the values and the
        # vertical y axis the categories; reversing it keeps the table order.
        chart.set_x_axis({"num_format": number_format, "num_font": {"name": TEXT, "size": 8, "color": MUTED},
                          "major_gridlines": {"visible": True, "line": {"color": "#EEEAF4", "width": 0.75}},
                          "line": {"none": True}, "major_tick_mark": "none", "min": 0, "label_position": "none"})
        chart.set_y_axis({"reverse": True, "num_font": {"name": TEXT, "size": 9, "color": theme.TINTA},
                          "line": {"color": theme.LILA_100}, "major_tick_mark": "none"})
        chart.set_legend({"none": True})
        chart.set_chartarea({"border": {"color": SOFT_LINE}, "fill": {"color": WHITE}})
        chart.set_plotarea({"border": {"none": True}, "fill": {"none": True}})
        chart.set_size({"width": width, "height": height})
        return chart

    # ------------------------------------------------------------------ data
    def kpi_cards(self):
        cards = []
        for index, kpi in enumerate(self.ctx["kpis"][:4]):
            num_format = MILL_KPI if kpi["kind"] == "money" else INT
            note = (f"{number(kpi['share'], 1)} % del total nacional" if kpi.get("share") is not None else kpi.get("note", ""))
            cards.append((kpi["label"], kpi["value"], num_format, note, TONES[index]))
        return cards

    def subtitle(self) -> str:
        ctx = self.ctx
        return f"{ctx['period_label']} · {ctx['territory_label']} · {ctx['programs_label']}"

    def icon_png(self, name: str, variant: str = "morado") -> bytes | None:
        path = ICONS / f"{name}-{variant}.png"
        return path.read_bytes() if path.exists() else None

    # ----------------------------------------------------------------- sheets
    def summary(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        ws = self.wb.add_worksheet("Resumen")
        self.widths(ws, [2.4] + [12.6] * 12 + [2.4])
        self.page(ws, tall=1)
        ws.set_tab_color(theme.MORADO)
        row = self.band(ws, ctx["title"], self.subtitle(), last=13)
        row = self.heading(ws, row + 1, "Cifras clave", ctx["period_label"])
        row = self.kpi_row(ws, row + 1, self.kpi_cards())
        top = row + 1
        self.heading(ws, top, f"Resultados por {labels['item']}", last=7)
        ws.merge_range(top, 8, top, 12, f"{labels['people']} por provincia",
                       self.f(font_name=DISPLAY, font_size=13, bold=True, font_color=theme.MORADO_900, bottom=2, bottom_color=theme.LILA_200))
        total_people = ctx["totals"]["people"]
        rows = [{**p, "share": _share(p["people"], total_people)} for p in ctx["programs"]]
        layout = [(labels["item"].capitalize(), "short", "text", 1, 3), (labels["people"], "people", "int", 4, 1),
                  ("Participación", "share", "pct", 5, 1), (f"{labels['fiscal']} (millones de USD)", "fiscal", "mill", 6, 2)]
        total = {"people": total_people, "share": 1.0 if total_people else None, "fiscal": ctx["totals"]["fiscal"]}
        first, last, nxt = self.table(ws, top + 1, layout, rows, total=total, header_height=36)
        self.data_bar(ws, first, last, 5, theme.LILA_300, maximum=1)
        picture = map_png(ctx["map_values"], mode="light", selected=set(ctx["selected_codes"]), label=labels["people"],
                          annotate=0, width=5.4, height=4.8, dpi=200)
        self.image(ws, top + 1, 8, picture, 440, "mapa_resumen.png", x_offset=10, y_offset=4,
                   description=f"Mapa del Ecuador: {labels['people'].lower()} por provincia")
        row = max(nxt, top + 1 + 18) + 1
        row = self.heading(ws, row, "Aspectos destacados")
        for item in ctx["insights"][:3]:
            ws.set_row(row, 34)
            ws.write_blank(row, 1, None, self.f(bg_color=theme.LILA_50))
            ws.merge_range(row, 2, row, 12, item["text"], self.f(bg_color=theme.LILA_50, font_size=10.5, text_wrap=True, indent=1))
            icon = self.icon_png(item["icon"])
            if icon:
                self.image(ws, row, 1, icon, 26, f"icono_{item['icon']}.png", x_offset=30, y_offset=10)
            row += 1
            ws.set_row(row, 6)
            row += 1
        ws.print_area(0, 0, row, 13)
        ws.activate()
        ws.set_first_sheet()
        ws.set_zoom(90)

    def programs_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        name = labels["items"].capitalize()
        units = bool(labels["units"])
        ws = self.wb.add_worksheet(name)
        columns = [2.4, 6.0, 40.0, 15.0, 13.0] + ([14.0] if units else []) + [18.0, 22.0, 22.0, 2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws, tall=1)
        ws.set_tab_color(theme.VIOLETA_500)
        row = self.band(ws, f"Resultados por {labels['item']}", self.subtitle(), last=last_col)
        row = self.heading(ws, row + 1, f"{labels['people']} y presupuesto por {labels['item']}", "Montos en USD", last=last_col - 1)
        total_people = ctx["totals"]["people"]
        rows = [{**p, "n": i + 1, "share": _share(p["people"], total_people)} for i, p in enumerate(ctx["programs"])]
        layout = [("N.º", "n", "center", 1, 1), (labels["item"].capitalize(), "label", "text", 2, 1),
                  (labels["people"], "people", "int", 3, 1), ("Participación", "share", "pct", 4, 1)]
        col = 5
        if units:
            layout.append((labels["units"], "units", "int", col, 1))
            col += 1
        layout += [(labels["fiscal"], "fiscal", "usd", col, 1), (labels["previous"], "previous", "usd", col + 1, 1),
                   (labels["government"], "government", "usd", col + 2, 1)]
        totals = ctx["totals"]
        total = {"people": totals["people"], "share": 1.0 if totals["people"] else None, "units": totals["units"],
                 "fiscal": totals["fiscal"], "previous": totals["previous"], "government": totals["government"]}
        first, last, nxt = self.table(ws, row, layout, rows, total=total, label_index=1, header_height=36)
        self.data_bar(ws, first, last, 4, theme.LILA_300, maximum=1)
        ws.freeze_panes(row + 1, 0)
        if len(rows) > 1:
            height = max(300, 32 * len(rows) + 80)
            ws.insert_chart(nxt + 1, 2, self.bar_chart(name, first, last, 2, 3, f"{labels['people']} por {labels['item']}", [theme.SERIE_BONOS],
                                                       width=560, height=height), {"y_offset": 10, "object_position": 3})
            fiscal_col = 6 if units else 5
            ws.insert_chart(nxt + 1, 4, self.bar_chart(name, first, last, 2, fiscal_col, f"{labels['fiscal']} (millones de USD)",
                                                       [theme.VIOLETA_500], number_format="#,##0.0,,", width=560, height=height),
                            {"x_offset": 40, "y_offset": 10, "object_position": 3})
        ws.set_zoom(90)

    def provinces_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        units = bool(labels["units"])
        ws = self.wb.add_worksheet("Provincias")
        columns = [2.4, 9.0, 8.0, 30.0, 12.0, 15.0, 13.0] + ([14.0] if units else []) + [18.0, 22.0, 2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.ORO)
        row = self.band(ws, "Resultados por provincia", f"{labels['people']} · {ctx['period_label']} · {ctx['programs_label']}", last=last_col)
        row = self.heading(ws, row + 1, f"{labels['people']} por provincia",
                           "Provincias seleccionadas en dorado" if ctx["selected_codes"] else "", last=last_col - 1)
        picture = map_png(ctx["map_values"], mode="light", selected=set(ctx["selected_codes"]), label=labels["people"],
                          annotate=5, width=6.6, height=5.6, dpi=200)
        self.image(ws, row + 1, 2, picture, 600, "mapa_provincias.png", x_offset=4, y_offset=6,
                   description=f"Mapa del Ecuador: {labels['people'].lower()} por provincia")
        row += 27
        ws.set_h_pagebreaks([row])
        row = self.heading(ws, row, "Posición de cada provincia en el país", "Montos en USD", last=last_col - 1)
        headers = ["Posición", "Código", "Provincia", "Región", labels["people"], "Participación nacional"]
        kinds = ["center", "code", "text", "code", "int", "pct"]
        keys = ["position", "code", "name", "region", "people", "share"]
        if units:
            headers.append(labels["units"]), kinds.append("int"), keys.append("units")
        headers += [labels["fiscal"], labels["government"]]
        kinds += ["usd", "usd"]
        keys += ["fiscal", "government"]
        ws.set_row(row, 36)
        for i, header in enumerate(headers):
            align = "right" if kinds[i] in NUMERIC else ("center" if kinds[i] in ("center", "code") else "left")
            divider = dict(left=1, left_color="#7458AE") if i else {}
            ws.write(row, 1 + i, header, self.f(bg_color=theme.MORADO, font_name=DISPLAY, font_size=9, bold=True, font_color=WHITE,
                                                text_wrap=True, align=align, indent=1 if align == "left" else 0, **divider))
        first = row + 1
        for r, province in enumerate(ctx["provinces"]):
            line = first + r
            ws.set_row(line, 19)
            chosen = province["selected"]
            fill = theme.ORO_100 if chosen else (theme.NIEBLA if r % 2 else WHITE)
            record = {**province, "share": (province["share"] or 0) / 100 if province["share"] is not None else None,
                      "position": province["position"] if province["position"] else "—"}
            for i, key in enumerate(keys):
                kind = kinds[i]
                value = record.get(key)
                if key == "position":
                    ws.write(line, 1 + i, value, self.f(bg_color=fill, align="center", bold=chosen, font_color=theme.MORADO_900,
                                                        bottom=7, bottom_color=SOFT_LINE))
                    continue
                self._value(ws, line, 1 + i, 1, value, kind, fill, strong=(key == "name") or chosen)
        last = first + len(ctx["provinces"]) - 1
        total_row = last + 1
        ws.set_row(total_row, 22)
        edge = dict(top=2, top_color=theme.MORADO)
        ws.merge_range(total_row, 1, total_row, 4, "Total nacional", self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900,
                                                                            indent=1, **edge))
        national = ctx["national"]
        for i, key in enumerate(keys[4:], start=4):
            col = 1 + i
            kind = kinds[i]
            if key == "share":
                ws.write_number(total_row, col, 1.0, self.cell_format("pct", theme.LAVANDA, bold=True, **edge))
                continue
            value = national.get(key)
            if value is None:
                ws.write(total_row, col, "—", self.f(bg_color=theme.LAVANDA, bold=True, align="right", **edge))
                continue
            rng = f"{xl_rowcol_to_cell(first, col)}:{xl_rowcol_to_cell(last, col)}"
            ws.write_formula(total_row, col, f"=SUM({rng})", self.cell_format(kind, theme.LAVANDA, bold=True, **edge), value)
        self.data_bar(ws, first, last, 6, theme.LILA_300)
        ws.autofilter(row, 1, last, len(keys))
        ws.set_zoom(90)

    def detail_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        units = bool(labels["units"])
        ws = self.wb.add_worksheet("Detalle")
        columns = [2.4, 38.0, 9.0, 28.0, 12.0, 15.0] + ([14.0] if units else []) + [18.0, 22.0, 22.0, 2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.LILA_300)
        row = self.band(ws, f"Detalle por {labels['item']} y provincia", self.subtitle(), last=last_col, compact=True)
        layout = [(labels["item"].capitalize(), "program", "text", 1, 1), ("Código", "code", "code", 2, 1),
                  ("Provincia", "province", "text", 3, 1), ("Región", "region", "code", 4, 1), (labels["people"], "people", "int", 5, 1)]
        col = 6
        if units:
            layout.append((labels["units"], "units", "int", col, 1))
            col += 1
        layout += [(labels["fiscal"], "fiscal", "usd", col, 1), (labels["previous"], "previous", "usd", col + 1, 1),
                   (labels["government"], "government", "usd", col + 2, 1)]
        detail = ctx["detail"]
        totals_row, header_row = row + 1, row + 3
        first, last = header_row + 1, header_row + max(1, len(detail))
        edge = dict(top=2, top_color=theme.MORADO)
        ws.set_row(totals_row, 24)
        ws.merge_range(totals_row, 1, totals_row, 4, "Total de las filas visibles",
                       self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
        for _header, key, kind, column, _span in layout[4:]:
            values = [d[key] for d in detail if d[key] is not None]
            if values:
                rng = f"{xl_rowcol_to_cell(first, column)}:{xl_rowcol_to_cell(last, column)}"
                ws.write_formula(totals_row, column, f"=SUBTOTAL(109,{rng})", self.cell_format(kind, theme.LAVANDA, bold=True, **edge), sum(values))
            else:
                ws.write(totals_row, column, "—", self.f(bg_color=theme.LAVANDA, bold=True, align="right", **edge))
        ws.set_row(totals_row + 1, 6)
        self.table(ws, header_row, layout, detail, label_index=0, header_height=36, height=18)
        ws.autofilter(header_row, 1, last, last_col - 1)
        ws.freeze_panes(first, 2)
        ws.repeat_rows(header_row)
        self.data_bar(ws, first, last, 5, theme.LILA_200)
        ws.set_zoom(90)

    def technical_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        from src.indicators import MODULES
        module = MODULES[ctx["module_id"]]
        ws = self.wb.add_worksheet("Ficha técnica")
        self.widths(ws, [2.4, 34.0, 96.0, 2.4])
        self.page(ws, landscape=False)
        ws.set_tab_color(theme.PIZARRA)
        row = self.band(ws, "Ficha técnica", self.subtitle(), last=3)
        row = self.heading(ws, row + 1, "Identificación", last=2)
        facts = [("Institución", ctx["institution"]), ("Producto", "Libro de datos de InfoReportes"),
                 ("Ámbito", ctx["module_label"]), ("Periodo", ctx["period_label"]), ("Territorio", ctx["territory_label"]),
                 (labels["items"].capitalize(), ctx["programs_label"]), ("Fecha de generación", ctx["generated_label"].capitalize()),
                 ("Unidad monetaria", "Dólares de los Estados Unidos (USD)")]
        _f, _l, row = self.table(ws, row, [("Elemento", 0, "text", 1, 1), ("Descripción", 1, "text", 2, 1)], facts, height=22)
        row = self.heading(ws, row + 1, "Indicadores", last=2)
        _f, _l, row = self.table(ws, row, [("Indicador", 0, "text", 1, 1), ("Definición", 1, "text", 2, 1)],
                                 module.definitions(ctx["year"], executed=ctx.get("executed_available", False)), height=38)
        row = self.heading(ws, row + 1, "Contenido del libro", last=2)
        contents = [("Resumen", "Cifras clave, resultados por " + labels["item"] + ", mapa y aspectos destacados"),
                    (labels["items"].capitalize(), f"{labels['people']}, participación y presupuesto por {labels['item']}"),
                    ("Provincias", "Mapa y posición de cada provincia en el país"),
                    ("Detalle", f"Cada {labels['item']} en cada provincia, con filtros y totales que se recalculan"),
                    ("Ficha técnica", "Identificación del producto y definiciones")]
        line = dict(bottom=7, bottom_color=SOFT_LINE)
        for name, description in contents:
            ws.set_row(row, 22)
            ws.write_url(row, 1, f"internal:'{name}'!A1", self.f(font_name=DISPLAY, font_size=10.5, bold=True, font_color=theme.MORADO,
                                                                 indent=1, **line), string=name, tip=f"Ir a la hoja {name}")
            ws.write(row, 2, description, self.f(font_size=10, font_color=theme.PIZARRA, **line))
            row += 1
        ws.set_zoom(95)

    # ---------------------------------------------------------------- build
    def build(self) -> bytes:
        ctx = self.ctx
        self.wb.set_properties({
            "title": ctx["title"], "subject": f"{ctx['module_label']} · {ctx['period_label']} · {ctx['territory_label']}",
            "author": ctx["institution"], "company": ctx["institution"], "manager": "InfoReportes",
            "category": "Indicadores estratégicos", "keywords": "MTDH, InfoReportes, indicadores",
        })
        self.wb.set_size(1680, 1040)
        self.summary()
        self.programs_sheet()
        self.provinces_sheet()
        self.detail_sheet()
        self.technical_sheet()
        self.wb.close()
        return _institutional_theme(self.out.getvalue())


_THEME_COLORS = {
    "dk2": "2B164F", "lt2": "EBE5F3", "accent1": "512F8D", "accent2": "C33F8D", "accent3": "F8C018",
    "accent4": "7657B9", "accent5": "A995E0", "accent6": "3D216D", "hlink": "512F8D", "folHlink": "7657B9",
}


def _institutional_theme(xlsx: bytes) -> bytes:
    """Give the file an MTDH Office theme: colours and fonts for anything the reader adds."""
    source = ZipFile(BytesIO(xlsx))
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "xl/theme/theme1.xml":
                text = data.decode("utf-8")
                for slot, color in _THEME_COLORS.items():
                    text = re.sub(rf"<a:{slot}>.*?</a:{slot}>", f'<a:{slot}><a:srgbClr val="{color}"/></a:{slot}>', text, count=1, flags=re.S)
                text = re.sub(r'(<a:majorFont>\s*<a:latin typeface=")[^"]*(")', rf"\g<1>{DISPLAY}\g<2>", text, count=1)
                text = re.sub(r'(<a:minorFont>\s*<a:latin typeface=")[^"]*(")', rf"\g<1>{TEXT}\g<2>", text, count=1)
                text = text.replace('name="Office Theme"', 'name="MTDH Institucional"', 1)
                text = re.sub(r'<a:clrScheme name="[^"]*">', '<a:clrScheme name="MTDH">', text, count=1)
                data = text.encode("utf-8")
            target.writestr(item, data)
    return out.getvalue()


def generate_xlsx(context: dict) -> bytes:
    if not context.get("programs"):
        raise ValueError("El reporte no contiene información para la selección.")
    return Workbook(context).build()


def table_xlsx(rows: list[dict], layout: list[tuple[str, str, str, float]], *, title: str, subtitle: str,
               period_label: str, selection: str = "", note: str = "", sheet: str = "Detalle") -> bytes:
    """A dashboard table as one institutional sheet: header plate, live totals of the visible rows, filters.

    ``layout`` items are (header, key, kind, width) with the kinds of :meth:`Workbook.table`; ``pct`` values are
    fractions (0.25 reads 25,0 %).  Used by the dashboard downloads, so they open correctly in any Excel locale.
    """
    book = Workbook({"year": 0, "period_label": period_label, "selection_hash": selection})
    ws = book.wb.add_worksheet(sheet[:31])
    widths = [2.4] + [width for *_rest, width in layout] + [2.4]
    book.widths(ws, widths)
    book.page(ws)
    ws.set_tab_color(theme.MORADO)
    last_col = len(widths) - 1
    row = book.band(ws, title, subtitle, last=last_col, compact=True)
    table_layout = [(header, key, kind, i + 1, 1) for i, (header, key, kind, _width) in enumerate(layout)]
    numeric = [(key, kind, col) for _h, key, kind, col, _s in table_layout if kind in NUMERIC]
    labels = [col for _h, _k, kind, col, _s in table_layout if kind not in NUMERIC]
    totals_row, header_row = row + 1, row + 3
    first, last = header_row + 1, header_row + max(1, len(rows))
    edge = dict(top=2, top_color=theme.MORADO)
    ws.set_row(totals_row, 24)
    label_last = max(labels) if labels else 1
    book._put(ws, totals_row, 1, label_last, "Total de las filas visibles",
              book.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
    for key, kind, col in numeric:
        values = [r.get(key) for r in rows if r.get(key) is not None and r.get(key) == r.get(key)]
        if values and (key != "presupuesto_ejecutado" or len(values) == len(rows)):
            rng = f"{xl_rowcol_to_cell(first, col)}:{xl_rowcol_to_cell(last, col)}"
            ws.write_formula(totals_row, col, f"=SUBTOTAL(109,{rng})", book.cell_format(kind, theme.LAVANDA, bold=True, **edge), sum(values))
        else:
            ws.write(totals_row, col, "—", book.f(bg_color=theme.LAVANDA, bold=True, italic=True, font_color=NA_COLOR, align="right", **edge))
    ws.set_row(totals_row + 1, 6)
    book.table(ws, header_row, table_layout, rows, label_index=labels[-1] - 1 if labels else 0, header_height=36, height=19)
    ws.autofilter(header_row, 1, last, last_col - 1)
    ws.freeze_panes(first, (labels[-1] + 1) if labels else 1)
    ws.repeat_rows(header_row)
    for key, kind, col in numeric:
        if kind == "pct":
            book.data_bar(ws, first, last, col, theme.LILA_200)
    if note:
        book.note(ws, last + 2, note, first=1, last=last_col - 1, height=34)
    book.wb.set_properties({"title": title, "subject": subtitle, "author": "Ministerio de Trabajo y Desarrollo Humano",
                            "company": "Ministerio de Trabajo y Desarrollo Humano", "manager": "InfoReportes",
                            "category": "Estadística institucional", "comments": f"Selección {selection}"})
    ws.set_zoom(95)
    book.wb.close()
    return _institutional_theme(book.out.getvalue())
