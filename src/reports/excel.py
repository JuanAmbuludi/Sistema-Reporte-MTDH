"""Institutional Excel workbook: the data book of InfoReport.

Built with XlsxWriter from the same report context as the summary and the slides.  Transfers and services get
Resumen, results by program (or service), one sheet for each territorial level the reader chose (Provincias,
Cantones, Parroquias), Detalle at the finest of those levels and Ficha técnica; the institutional budget gets its own
sheets, and the books of contingencies, Jóvenes en Acción, labour management and the social budget live in
``excel_areas``.  Design rules:
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
from .charts import map_png, nice_bounds
from .context import PRODUCT, number

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
        ws.set_footer(f'&L&"{TEXT},Regular"&8&K5A5765InfoReport · Indicadores estratégicos'
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
        """Purple header plate with logo, title, context and the cut and update of the information, closed by a gold rule."""
        update = (self.ctx.get("update") or {}).get("short", "")
        heights = [8, 32, 20, 10] if compact else ([12, 40, 22, 20] if update else [12, 40, 22, 14])
        for row, height in enumerate(heights):
            ws.set_row(row, height)
            for col in range(last + 1):
                ws.write_blank(row, col, None, self.f(bg_color=theme.MORADO))
        ws.write(1, 1, title, self.f(bg_color=theme.MORADO, font_name=DISPLAY, font_size=17 if compact else 20, bold=True, font_color=WHITE))
        ws.write(2, 1, subtitle, self.f(bg_color=theme.MORADO, font_size=10, font_color="#E4DBF3"))
        if update and not compact:
            ws.write(3, 1, update, self.f(bg_color=theme.MORADO, font_size=9, font_color="#FFE7A3", valign="top"))
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

    def table(self, ws, row, layout, rows, *, total=None, label_index=0, subtotal=False, header_height=34, height=19, gold=False):
        """Styled table on a column layout.

        ``layout`` items are (header, key, kind, first_col, span).  Kinds: text,
        code, center, int, units, usd, mill, pct.  Missing numbers read as a dash.
        With ``gold`` the rows marked ``selected`` (the month or the year of the report) read in gold.
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
            chosen = gold and isinstance(item, dict) and item.get("selected")
            fill = theme.ORO_100 if chosen else (theme.NIEBLA if i % 2 else WHITE)
            for index, (_header, key, kind, col, span) in enumerate(layout):
                value = item.get(key) if isinstance(item, dict) else item[key]
                strong = index == label_index or bool(chosen)
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

    def column_chart(self, sheet, first, last, cat_col, val_col, title, number_format=INT, width=760, height=340):
        chart = self.wb.add_chart({"type": "column"})
        chart.add_series({
            "name": title, "categories": [sheet, first, cat_col, last, cat_col], "values": [sheet, first, val_col, last, val_col],
            "fill": {"color": theme.SERIE_BONOS}, "border": {"none": True}, "gap": 60,
            "data_labels": {"value": True, "num_format": number_format, "position": "outside_end",
                            "font": {"name": TEXT, "size": 9, "color": theme.TINTA}},
        })
        chart.set_title({"name": title, "overlay": False,
                         "name_font": {"name": DISPLAY, "size": 11, "bold": True, "color": theme.MORADO_900}})
        chart.set_y_axis({"num_format": number_format, "num_font": {"name": TEXT, "size": 8, "color": MUTED},
                          "major_gridlines": {"visible": True, "line": {"color": "#EEEAF4", "width": 0.75}},
                          "line": {"none": True}, "major_tick_mark": "none", "min": 0})
        chart.set_x_axis({"num_font": {"name": TEXT, "size": 9, "color": theme.TINTA}, "line": {"color": theme.LILA_100},
                          "major_tick_mark": "none"})
        chart.set_legend({"none": True})
        chart.set_chartarea({"border": {"color": SOFT_LINE}, "fill": {"color": WHITE}})
        chart.set_plotarea({"border": {"none": True}, "fill": {"none": True}})
        chart.set_size({"width": width, "height": height})
        return chart

    # ------------------------------------------------------------------ data
    @staticmethod
    def kpi_format(kpi: dict) -> str:
        if kpi.get("exact_money"):
            return '"USD "#,##0.00'
        if kpi["kind"] == "rate":
            return PCT
        if kpi["kind"] == "money":
            decimals = kpi.get("decimals", 1)
            digits = "#,##0" + ("." + "0" * decimals if decimals else "")
            prefix = '"Más de USD "' if kpi.get("lower_bound") else '"USD "'
            return f'{prefix}{digits},," M"'
        return INT

    def kpi_cards(self, share_word: str = "del total nacional"):
        cards = []
        for index, kpi in enumerate(self.ctx["kpis"][:4]):
            value = kpi["value"]
            if kpi["kind"] == "rate" and value is not None:
                value = value / 100
            note = (f"{number(kpi['share'], 1)} % {share_word}" if kpi.get("share") is not None else kpi.get("note", ""))
            cards.append((kpi["label"], value, self.kpi_format(kpi), note, TONES[index]))
        return cards

    def subtitle(self) -> str:
        ctx = self.ctx
        return f"{ctx['period_label']} · {ctx['territory_label']} · {ctx['programs_label']}"

    def icon_png(self, name: str, variant: str = "morado") -> bytes | None:
        path = ICONS / f"{name}-{variant}.png"
        return path.read_bytes() if path.exists() else None

    def findings(self, ws, row: int, items: list[dict], last: int = 12) -> int:
        row = self.heading(ws, row, "Aspectos destacados", last=last)
        for item in items:
            ws.set_row(row, 34)
            ws.write_blank(row, 1, None, self.f(bg_color=theme.LILA_50))
            ws.merge_range(row, 2, row, last, item["text"], self.f(bg_color=theme.LILA_50, font_size=10.5, text_wrap=True, indent=1))
            icon = self.icon_png(item["icon"])
            if icon:
                self.image(ws, row, 1, icon, 26, f"icono_{item['icon']}.png", x_offset=30, y_offset=10)
            row += 1
            ws.set_row(row, 6)
            row += 1
        return row

    def facts_sheet(self, facts: list[tuple[str, str]], definitions: list[tuple[str, str]], contents: list[tuple[str, str]],
                    sources: list[tuple[str, str, str]] | None = None) -> None:
        ws = self.wb.add_worksheet("Ficha técnica")
        self.widths(ws, [2.4, 34.0, 96.0, 2.4])
        self.page(ws, landscape=False)
        ws.set_tab_color(theme.PIZARRA)
        row = self.band(ws, "Ficha técnica", self.subtitle(), last=3)
        row = self.heading(ws, row + 1, "Identificación", last=2)
        _f, _l, row = self.table(ws, row, [("Elemento", 0, "text", 1, 1), ("Descripción", 1, "text", 2, 1)], facts, height=22)
        row = self.heading(ws, row + 1, "Indicadores", last=2)
        _f, _l, row = self.table(ws, row, [("Indicador", 0, "text", 1, 1), ("Definición", 1, "text", 2, 1)], definitions, height=38)
        if sources:
            row = self.heading(ws, row + 1, "Fuentes oficiales", last=2)
            line = dict(bottom=7, bottom_color=SOFT_LINE)
            for label, origin, url in sources:
                ws.set_row(row, 34)
                ws.write(row, 1, label, self.f(font_size=10, bold=True, font_color=theme.MORADO_900, text_wrap=True, indent=1, **line))
                if url:
                    ws.write_url(row, 2, url, self.f(font_size=10, font_color=theme.MORADO, underline=1, text_wrap=True, **line),
                                 string=origin, tip=url)
                else:
                    ws.write(row, 2, origin, self.f(font_size=10, font_color=theme.PIZARRA, text_wrap=True, **line))
                row += 1
        row = self.heading(ws, row + 1, "Contenido del libro", last=2)
        line = dict(bottom=7, bottom_color=SOFT_LINE)
        for name, description in contents:
            ws.set_row(row, 22)
            ws.write_url(row, 1, f"internal:'{name}'!A1", self.f(font_name=DISPLAY, font_size=10.5, bold=True, font_color=theme.MORADO,
                                                                 indent=1, **line), string=name, tip=f"Ir a la hoja {name}")
            ws.write(row, 2, description, self.f(font_size=10, font_color=theme.PIZARRA, **line))
            row += 1
        ws.set_zoom(95)

    def update_facts(self) -> list[tuple[str, str]]:
        """Cut, update and frequency of the information for the technical sheet."""
        update = self.ctx.get("update") or {}
        facts = []
        if update.get("cut"):
            facts.append(("Corte de la información", update["cut"][:1].upper() + update["cut"][1:]))
        if update.get("updated"):
            facts.append(("Fecha y hora de actualización", f"{update['updated']} (hora de Ecuador)"))
        if update.get("frequency"):
            facts.append(("Frecuencia de actualización", update["frequency"]))
        return facts

    def generic_table(self, ws, row: int, layout: list[tuple], rows: list[dict], *, total: dict | None = None, label_index: int = 0,
                      subtotal: bool = False, bar_key: str | None = None, height: int = 19) -> tuple[int, int, int]:
        first, last, nxt = self.table(ws, row, layout, rows, total=total, label_index=label_index, subtotal=subtotal,
                                      header_height=36, height=height)
        if bar_key:
            col = next(c for _h, key, _k, c, _s in layout if key == bar_key)
            self.data_bar(ws, first, last, col, theme.LILA_300, maximum=1)
        return first, last, nxt

    # ------------------------------------------------------------ territorial
    def _scope_word(self) -> str:
        return {"parroquia": "parroquia", "canton": "cantón"}.get(self.ctx.get("map_layer"), "provincia")

    def summary(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        executed = ctx.get("executed_available")
        ws = self.wb.add_worksheet("Resumen")
        self.widths(ws, [2.4] + [12.6] * 12 + [2.4])
        self.page(ws, tall=1)
        ws.set_tab_color(theme.MORADO)
        row = self.band(ws, ctx["title"], self.subtitle(), last=13)
        row = self.heading(ws, row + 1, "Cifras clave", ctx["period_label"])
        row = self.kpi_row(ws, row + 1, self.kpi_cards())
        top = row + 1
        self.heading(ws, top, f"Resultados por {labels['item']}", last=7)
        ws.merge_range(top, 8, top, 12, f"{labels['people']} por {self._scope_word()}",
                       self.f(font_name=DISPLAY, font_size=13, bold=True, font_color=theme.MORADO_900, bottom=2, bottom_color=theme.LILA_200))
        total_people = ctx["totals"]["people"]
        rows = [{**p, "share": _share(p["people"], total_people),
                 "execution_f": (p["execution"] / 100) if p.get("execution") is not None else None} for p in ctx["programs"]]
        layout = [(labels["item"].capitalize(), "short", "text", 1, 3), (labels["people"], "people", "int", 4, 1),
                  ("Participación", "share", "pct", 5, 1)]
        if executed:
            layout += [(f"{labels['fiscal']} (millones de USD)", "fiscal", "mill", 6, 1), ("Ejecución", "execution_f", "pct", 7, 1)]
        elif ctx.get("reference_budget"):
            layout.append((f"{labels['fiscal']} (millones de USD)", "fiscal", "mill", 6, 2))
        elif labels.get("units"):
            layout.append((labels["units"], "units", "int", 6, 2))
        else:
            layout[0] = (labels["item"].capitalize(), "short", "text", 1, 5)
            layout[1:] = [(labels["people"], "people", "int", 6, 1), ("Participación", "share", "pct", 7, 1)]
        total = {"people": total_people, "share": 1.0 if total_people else None, "fiscal": ctx["totals"]["fiscal"],
                 "units": ctx["totals"].get("units"),
                 "execution_f": (ctx["totals"]["execution"] / 100) if ctx["totals"].get("execution") is not None else None}
        first, last, nxt = self.table(ws, top + 1, layout, rows, total=total, header_height=36)
        share_col = next(col for _h, key, _k, col, _s in layout if key == "share")
        self.data_bar(ws, first, last, share_col, theme.LILA_300, maximum=1)
        picture = map_png(ctx["map_values"], layer=ctx.get("map_layer", "provincia"), focus=ctx.get("map_focus", []),
                          selected=set(ctx["selected_codes"]), label=f"{labels['people']} por {self._scope_word()}",
                          width=5.4, height=4.8, dpi=200)
        self.image(ws, top + 1, 8, picture, 440, "mapa_resumen.png", x_offset=10, y_offset=4,
                   description=f"Mapa del Ecuador: {labels['people'].lower()} por {self._scope_word()}")
        row = max(nxt, top + 1 + 18) + 1
        row = self.findings(ws, row, ctx["insights"][:4])
        ws.print_area(0, 0, row, 13)
        ws.activate()
        ws.set_first_sheet()
        ws.set_zoom(90)

    def programs_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        executed = ctx.get("executed_available")
        name = labels["items"].capitalize()
        units = bool(labels["units"])
        ws = self.wb.add_worksheet(name)
        with_money = executed or ctx.get("reference_budget")
        columns = ([2.4, 6.0, 40.0, 15.0, 13.0] + ([14.0] if units else []) + ([18.0] if with_money else [])
                   + ([18.0, 12.0] if executed else []) + ([22.0, 22.0] if with_money else []) + [2.4])
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws, tall=1)
        ws.set_tab_color(theme.VIOLETA_500)
        row = self.band(ws, f"Resultados por {labels['item']}", self.subtitle(), last=last_col)
        row = self.heading(ws, row + 1, f"{labels['people']} y presupuesto por {labels['item']}", "Montos en USD", last=last_col - 1)
        total_people = ctx["totals"]["people"]
        rows = [{**p, "n": i + 1, "share": _share(p["people"], total_people),
                 "execution_f": (p["execution"] / 100) if p.get("execution") is not None else None} for i, p in enumerate(ctx["programs"])]
        layout = [("N.º", "n", "center", 1, 1), (labels["item"].capitalize(), "label", "text", 2, 1),
                  (labels["people"], "people", "int", 3, 1), ("Participación", "share", "pct", 4, 1)]
        col = 5
        if units:
            layout.append((labels["units"], "units", "int", col, 1))
            col += 1
        fiscal_col = col
        with_money = executed or ctx.get("reference_budget")
        if with_money:
            layout.append((labels["fiscal"], "fiscal", "usd", col, 1))
            col += 1
            if executed:
                layout += [(labels["coded"], "coded", "usd", col, 1), ("Ejecución", "execution_f", "pct", col + 1, 1)]
                col += 2
            layout += [(labels["previous"], "previous", "usd", col, 1), (labels["government"], "government", "usd", col + 1, 1)]
        totals = ctx["totals"]
        total = {"people": totals["people"], "share": 1.0 if totals["people"] else None, "units": totals["units"],
                 "fiscal": totals["fiscal"], "coded": totals.get("coded"),
                 "execution_f": (totals["execution"] / 100) if totals.get("execution") is not None else None,
                 "previous": totals["previous"], "government": totals["government"]}
        first, last, nxt = self.table(ws, row, layout, rows, total=total, label_index=1, header_height=36)
        self.data_bar(ws, first, last, 4, theme.LILA_300, maximum=1)
        ws.freeze_panes(row + 1, 0)
        if len(rows) > 1:
            height = max(300, 32 * len(rows) + 80)
            ws.insert_chart(nxt + 1, 2, self.bar_chart(name, first, last, 2, 3, f"{labels['people']} por {labels['item']}", [theme.SERIE_BONOS],
                                                       width=560, height=height), {"y_offset": 10, "object_position": 3})
            if with_money:
                ws.insert_chart(nxt + 1, 4, self.bar_chart(name, first, last, 2, fiscal_col, f"{labels['fiscal']} (millones de USD)",
                                                           [theme.VIOLETA_500], number_format="#,##0.0,,", width=560, height=height),
                                {"x_offset": 40, "y_offset": 10, "object_position": 3})
            elif units:
                ws.insert_chart(nxt + 1, 4, self.bar_chart(name, first, last, 2, 5, f"{labels['units']} por {labels['item']}",
                                                           [theme.VIOLETA_500], width=560, height=height),
                                {"x_offset": 40, "y_offset": 10, "object_position": 3})
        ws.set_zoom(90)

    def provinces_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        executed = ctx.get("territorial_budget")
        with_money = executed or ctx.get("reference_budget")
        units = bool(labels["units"])
        ws = self.wb.add_worksheet("Provincias")
        columns = ([2.4, 9.0, 8.0, 30.0, 12.0, 15.0, 13.0] + ([14.0] if units else []) + ([18.0] if with_money else [])
                   + ([12.0] if executed else []) + ([22.0] if with_money else []) + [2.4])
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.ORO)
        row = self.band(ws, "Resultados por provincia", f"{labels['people']} · {ctx['period_label']} · {ctx['programs_label']}", last=last_col)
        row = self.heading(ws, row + 1, f"{labels['people']} por provincia",
                           "Provincias seleccionadas en dorado" if ctx["selected_codes"] else "", last=last_col - 1)
        values = {p["code"]: p["people"] for p in ctx["provinces"]}
        picture = map_png(values, layer="provincia", selected=set(ctx["selected_codes"]), label=f"{labels['people']} por provincia",
                          annotate=5, width=6.6, height=5.6, dpi=200)
        self.image(ws, row + 1, 2, picture, 600, "mapa_provincias.png", x_offset=4, y_offset=6,
                   description=f"Mapa del Ecuador: {labels['people'].lower()} por provincia")
        row += 27
        ws.set_h_pagebreaks([row])
        row = self.heading(ws, row, "Posición de cada provincia en el país", "Montos en USD" if with_money else "", last=last_col - 1)
        headers = ["Posición", "Código", "Provincia", "Región", labels["people"], "Participación nacional"]
        kinds = ["center", "code", "text", "code", "int", "pct"]
        keys = ["position", "code", "name", "region", "people", "share"]
        if units:
            headers.append(labels["units"]), kinds.append("int"), keys.append("units")
        if with_money:
            headers.append(labels["fiscal"]), kinds.append("usd"), keys.append("fiscal")
            if executed:
                headers.append("Ejecución"), kinds.append("pct"), keys.append("execution_f")
            headers.append(labels["government"]), kinds.append("usd"), keys.append("government")
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
                      "execution_f": province["execution"] / 100 if province.get("execution") is not None else None,
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
            if key == "execution_f":
                value = national.get("execution")
                if value is None:
                    ws.write(total_row, col, "—", self.f(bg_color=theme.LAVANDA, bold=True, align="right", **edge))
                else:
                    ws.write_number(total_row, col, value / 100, self.cell_format("pct", theme.LAVANDA, bold=True, **edge))
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

    def territory_sheet(self, level: str):
        """Cantons or parishes of the selection: their map and every territory with coverage, budget and execution."""
        ctx, labels = self.ctx, self.ctx["labels"]
        executed = ctx.get("territorial_budget")
        units = bool(labels["units"])
        parish = level == "parroquia"
        word, plural = ("parroquia", "Parroquias") if parish else ("cantón", "Cantones")
        ws = self.wb.add_worksheet(plural)
        columns = ([2.4, 24.0, 26.0] + ([30.0] if parish else []) + [12.0, 14.0, 13.0] + ([14.0] if units else [])
                   + ([20.0, 20.0, 12.0] if executed else []) + [2.4])
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.FUCSIA if parish else theme.VIOLETA_500)
        row = self.band(ws, f"Resultados por {word}", f"{labels['people']} · {ctx['period_label']} · {ctx['territory_label']}", last=last_col)
        row = self.heading(ws, row + 1, f"{labels['people']} por {word}",
                           "Provincias seleccionadas con borde dorado" if ctx["selected_codes"] else "", last=last_col - 1)
        chosen = (ctx.get("maps") or {}).get(level)
        if chosen:
            picture = map_png(chosen["values"], layer=chosen["layer"], focus=chosen["focus"], selected=set(ctx["selected_codes"]),
                              label=f"{labels['people']} por {word}", width=6.6, height=5.6, dpi=200)
            self.image(ws, row + 1, 2, picture, 600, f"mapa_{plural.lower()}.png", x_offset=4, y_offset=6,
                       description=f"Mapa del Ecuador: {labels['people'].lower()} por {word}")
            row += 27
            ws.set_h_pagebreaks([row])
        row = self.heading(ws, row, f"{plural} de la selección", "Montos en USD" if executed else "", last=last_col - 1)
        layout = [("Provincia", "province", "text", 1, 1)]
        col = 2
        if parish:
            layout += [("Cantón", "canton", "text", 2, 1), ("Parroquia", "name", "text", 3, 1)]
            col = 4
        else:
            layout.append(("Cantón", "name", "text", 2, 1))
            col = 3
        layout += [("Código DPA", "code", "code", col, 1), (labels["people"], "people", "int", col + 1, 1),
                   ("Participación", "share_f", "pct", col + 2, 1)]
        share_col = col + 2
        col += 3
        if units:
            layout.append((labels["units"], "units", "int", col, 1))
            col += 1
        if executed:
            layout += [(labels["fiscal"], "fiscal", "usd", col, 1), (labels["coded"], "coded", "usd", col + 1, 1),
                       ("Ejecución", "execution_f", "pct", col + 2, 1)]
            col += 3
        territories = ctx.get("territories", {}).get(level, [])
        rows = [{**r, "share_f": r["share"] / 100 if r.get("share") is not None else None,
                 "execution_f": r["execution"] / 100 if r.get("execution") is not None else None} for r in territories]
        totals = {"people": sum(r["people"] or 0 for r in rows), "share_f": 1.0,
                  "units": sum(r["units"] or 0 for r in rows) if units else None,
                  "fiscal": sum(r["fiscal"] or 0 for r in rows), "coded": sum(r["coded"] or 0 for r in rows),
                  "_label": "Total de las filas visibles"}
        label_index = 2 if parish else 1
        first, last, nxt = self.table(ws, row, layout, rows, total=totals, label_index=label_index, subtotal=True,
                                      header_height=36, height=18)
        ws.autofilter(row, 1, last, col - 1)
        ws.freeze_panes(row + 1, 3 if parish else 2)
        ws.repeat_rows(row)
        self.data_bar(ws, first, last, share_col, theme.LILA_300, maximum=1)
        ws.set_zoom(90)

    def detail_sheet(self):
        if self.ctx.get("detail_level", "provincia") != "provincia":
            self.territory_detail_sheet()
            return
        ctx, labels = self.ctx, self.ctx["labels"]
        executed = ctx.get("territorial_budget")
        with_money = executed or ctx.get("reference_budget")
        units = bool(labels["units"])
        ws = self.wb.add_worksheet("Detalle")
        columns = ([2.4, 38.0, 9.0, 28.0, 12.0, 15.0] + ([14.0] if units else []) + ([18.0] if with_money else [])
                   + ([18.0, 12.0] if executed else []) + ([22.0, 22.0] if with_money else []) + [2.4])
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
        if with_money:
            layout.append((labels["fiscal"], "fiscal", "usd", col, 1))
            col += 1
            if executed:
                layout += [(labels["coded"], "coded", "usd", col, 1), ("Ejecución", "execution_f", "pct", col + 1, 1)]
                col += 2
            layout += [(labels["previous"], "previous", "usd", col, 1), (labels["government"], "government", "usd", col + 1, 1)]
        detail = [{**d, "execution_f": d["execution"] / 100 if d.get("execution") is not None else None} for d in ctx["detail"]]
        totals_row, header_row = row + 1, row + 3
        first, last = header_row + 1, header_row + max(1, len(detail))
        edge = dict(top=2, top_color=theme.MORADO)
        ws.set_row(totals_row, 24)
        ws.merge_range(totals_row, 1, totals_row, 4, "Total de las filas visibles",
                       self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
        for _header, key, kind, column, _span in layout[4:]:
            values = [d[key] for d in detail if d.get(key) is not None]
            if kind == "pct":
                ws.write(totals_row, column, "", self.f(bg_color=theme.LAVANDA, **edge))
            elif values:
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

    def territory_detail_sheet(self):
        """Each program in each canton or parish, with filters and totals of the visible rows."""
        ctx, labels = self.ctx, self.ctx["labels"]
        executed = ctx.get("territorial_budget")
        units = bool(labels["units"])
        parish = ctx["detail_level"] == "parroquia"
        ws = self.wb.add_worksheet("Detalle")
        columns = ([2.4, 36.0, 20.0, 24.0] + ([28.0] if parish else []) + [12.0, 14.0] + ([14.0] if units else [])
                   + ([18.0, 18.0, 12.0] if executed else []) + [2.4])
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.LILA_300)
        word = "parroquia" if parish else "cantón"
        row = self.band(ws, f"Detalle por {labels['item']} y {word}", self.subtitle(), last=last_col, compact=True)
        layout = [(labels["item"].capitalize(), "program", "text", 1, 1), ("Provincia", "province", "text", 2, 1),
                  ("Cantón", "canton", "text", 3, 1)]
        col = 4
        if parish:
            layout.append(("Parroquia", "parish", "text", 4, 1))
            col = 5
        layout += [("Código DPA", "code", "code", col, 1), (labels["people"], "people", "int", col + 1, 1)]
        people_col = col + 1
        col += 2
        if units:
            layout.append((labels["units"], "units", "int", col, 1))
            col += 1
        if executed:
            layout += [(labels["fiscal"], "fiscal", "usd", col, 1), (labels["coded"], "coded", "usd", col + 1, 1),
                       ("Ejecución", "execution_f", "pct", col + 2, 1)]
            col += 3
        detail = [{**d, "execution_f": d["execution"] / 100 if d.get("execution") is not None else None} for d in ctx["detail"]]
        totals_row, header_row = row + 1, row + 3
        first, last = header_row + 1, header_row + max(1, len(detail))
        edge = dict(top=2, top_color=theme.MORADO)
        ws.set_row(totals_row, 24)
        label_last = 4 if parish else 3
        ws.merge_range(totals_row, 1, totals_row, label_last + 1, "Total de las filas visibles",
                       self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
        for _header, key, kind, column, _span in layout:
            if column <= label_last + 1:
                continue
            values = [d[key] for d in detail if d.get(key) is not None]
            if kind == "pct":
                ws.write(totals_row, column, "", self.f(bg_color=theme.LAVANDA, **edge))
            elif values:
                rng = f"{xl_rowcol_to_cell(first, column)}:{xl_rowcol_to_cell(last, column)}"
                ws.write_formula(totals_row, column, f"=SUBTOTAL(109,{rng})", self.cell_format(kind, theme.LAVANDA, bold=True, **edge), sum(values))
            else:
                ws.write(totals_row, column, "—", self.f(bg_color=theme.LAVANDA, bold=True, align="right", **edge))
        ws.set_row(totals_row + 1, 6)
        self.table(ws, header_row, layout, detail, label_index=0, header_height=36, height=18)
        ws.autofilter(header_row, 1, last, last_col - 1)
        ws.freeze_panes(first, 2)
        ws.repeat_rows(header_row)
        self.data_bar(ws, first, last, people_col, theme.LILA_200)
        ws.set_zoom(90)

    def monthly_sheet(self):
        """The selection month by month: people, change, units and the national budget; each program by month."""
        ctx, labels = self.ctx, self.ctx["labels"]
        monthly = ctx["monthly"]
        months = monthly["months"]
        budget = monthly.get("budget")
        units = bool(labels["units"]) and any(m["units"] for m in months)
        ws = self.wb.add_worksheet("Serie mensual")
        columns = [2.4, 30.0, 16.0, 15.0] + ([15.0] if units else []) + ([19.0, 20.0, 14.0] if budget else [])
        columns = columns + [13.0] * max(0, len(months) + 2 - len(columns)) + [2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.ORO)
        span = f"{months[0]['label']} a {months[-1]['label'].lower()} de {monthly['year']}"
        row = self.band(ws, "Evolución mensual", f"{labels['people']} · {span} · {ctx['territory_label']} · {ctx['programs_label']}",
                        last=last_col)
        row = self.heading(ws, row + 1, f"{labels['people']} por mes", "Montos en USD" if budget else "", last=last_col - 1)
        rows = [{**m, "name": f"{m['label']} {monthly['year']}", "execution_f": m["execution"] / 100 if m.get("execution") is not None else None}
                for m in months]
        layout = [("Mes", "name", "text", 1, 1), (labels["people"], "people", "int", 2, 1), ("Variación mensual", "change", "int", 3, 1)]
        col = 4
        if units:
            layout.append((labels["units"], "units", "int", col, 1))
            col += 1
        if budget:
            layout += [("Devengado del mes", "accrued_month", "usd", col, 1), ("Devengado acumulado", "accrued", "usd", col + 1, 1),
                       ("Ejecución acumulada", "execution_f", "pct", col + 2, 1)]
            col += 3
        first, last, nxt = self.table(ws, row, layout, rows, header_height=36)
        for index, month in enumerate(rows):
            if month.get("selected"):
                for position, (_header, key, kind, col_, span_) in enumerate(layout):
                    self._value(ws, first + index, col_, span_, month.get(key), kind, theme.ORO_100, strong=position == 0)
        chart = self.wb.add_chart({"type": "line"})
        chart.add_series({"name": labels["people"], "categories": ["Serie mensual", first, 1, last, 1], "values": ["Serie mensual", first, 2, last, 2],
                          "line": {"color": theme.SERIE_BONOS, "width": 2.25},
                          "marker": {"type": "circle", "size": 6, "fill": {"color": theme.SERIE_BONOS}, "border": {"color": WHITE}},
                          "points": [({"fill": {"color": theme.ORO}, "border": {"color": WHITE}} if m.get("selected") else None) for m in months]})
        chart.set_title({"name": f"{labels['people']} por mes", "overlay": False,
                         "name_font": {"name": DISPLAY, "size": 11, "bold": True, "color": theme.MORADO_900}})
        present = [m["people"] for m in months if m.get("people") is not None] or [0]
        bottom, top, step = nice_bounds(min(present), max(present))
        chart.set_y_axis({"num_format": INT, "min": bottom, "max": top, "major_unit": step,
                          "num_font": {"name": TEXT, "size": 8, "color": MUTED},
                          "major_gridlines": {"visible": True, "line": {"color": "#EEEAF4", "width": 0.75}}, "line": {"none": True}})
        chart.set_x_axis({"num_font": {"name": TEXT, "size": 9, "color": theme.TINTA}, "line": {"color": theme.LILA_100}})
        chart.set_legend({"none": True})
        chart.set_chartarea({"border": {"color": SOFT_LINE}, "fill": {"color": WHITE}})
        chart.set_size({"width": 560, "height": 300})
        ws.insert_chart(nxt + 1, 1, chart, {"y_offset": 8, "object_position": 3})
        if budget:
            # The second chart starts on the first column past the first one.
            widths = self._col_widths.get(ws.name, [])
            room, col_ = 0, 1
            while col_ < len(widths) and room < 560 + 16:
                room += self.px(widths[col_])
                col_ += 1
            accrued_col = next(c for _h, key, _k, c, _s in layout if key == "accrued_month")
            ws.insert_chart(nxt + 1, col_, self.column_chart("Serie mensual", first, last, 1, accrued_col,
                                                             "Presupuesto devengado por mes (millones de USD)",
                                                             number_format="#,##0.0,,", width=520, height=300),
                            {"x_offset": 6, "y_offset": 8, "object_position": 3})
        # Each program month by month.
        row = nxt + 18
        row = self.heading(ws, row, f"{labels['people']} por {labels['item']} y mes", last=last_col - 1)
        matrix_layout = [(labels["item"].capitalize(), "short", "text", 1, 1)] + [
            (m["short"], f"m{index}", "int", 2 + index, 1) for index, m in enumerate(months)]
        matrix = [{"short": r["short"], **{f"m{index}": value for index, value in enumerate(r["values"])}} for r in monthly["programs"]]
        totals = {f"m{index}": m["people"] for index, m in enumerate(months)}
        totals["_label"] = "Total"
        self.table(ws, row, matrix_layout, matrix, total=totals, header_height=30)
        ws.set_zoom(90)

    def technical_sheet(self):
        ctx, labels = self.ctx, self.ctx["labels"]
        from src.indicators import MODULES
        module = MODULES[ctx["module_id"]]
        levels = ctx.get("levels") or ["provincia"]
        level_names = {"provincia": "Provincias", "canton": "Cantones", "parroquia": "Parroquias"}
        facts = [("Institución", ctx["institution"]), ("Producto", f"Libro de datos de {PRODUCT}"),
                 ("Ámbito", ctx["module_label"]), ("Periodo", ctx["period_label"]), ("Territorio", ctx["territory_label"]),
                 ("Nivel territorial", ", ".join(level_names[level] for level in levels)),
                 (labels["items"].capitalize(), ctx["programs_label"])] + self.update_facts() + [
                 ("Fecha de generación", ctx["generated_label"].capitalize()), ("Unidad monetaria", "Dólares de los Estados Unidos (USD)")]
        contents = [("Resumen", "Cifras clave, resultados por " + labels["item"] + ", mapa y aspectos destacados"),
                    (labels["items"].capitalize(), f"{labels['people']}, participación, presupuesto y ejecución por {labels['item']}")]
        if ctx.get("monthly"):
            contents.append(("Serie mensual", f"{labels['people']} de cada mes, variación, cada {labels['item']} por mes"
                                              + (" y presupuesto devengado" if ctx["monthly"].get("budget") else "")))
        descriptions = {"provincia": "Mapa y posición de cada provincia en el país",
                        "canton": "Mapa y cada cantón con su cobertura, presupuesto y ejecución",
                        "parroquia": "Mapa y cada parroquia con su cantón, cobertura, presupuesto y ejecución"}
        contents += [(level_names[level], descriptions[level]) for level in levels]
        finest = {"provincia": "provincia", "canton": "cantón", "parroquia": "parroquia"}[ctx.get("detail_level", "provincia")]
        contents += [("Detalle", f"Cada {labels['item']} en cada {finest}, con filtros y totales que se recalculan"),
                     ("Ficha técnica", "Identificación del producto y definiciones")]
        definitions = module.definitions(ctx["year"], executed=ctx.get("executed_available", False))
        if ctx.get("monthly"):
            definitions = definitions + [("Variación mensual", f"Diferencia de los {labels['people'].lower()} de un mes frente al mes anterior.")]
            if ctx["monthly"].get("budget"):
                definitions.append(("Ejecución acumulada", "Presupuesto devengado de enero al mes, sobre el presupuesto codificado del "
                                                           "año; el ritmo uniforme supone una doceava parte del presupuesto por mes."))
        self.facts_sheet(facts, definitions, contents)

    # ------------------------------------------------------------------- budget
    def _money_rows(self, rows: list[dict]) -> list[dict]:
        return [{**r, "n": i + 1, "execution_f": r["execution"] / 100 if r.get("execution") is not None else None,
                 "share_f": r["share"] / 100 if r.get("share") is not None else None} for i, r in enumerate(rows)]

    def _money_total(self, rows: list[dict], label: str = "Total de la selección") -> dict:
        coded = sum(r["coded"] for r in rows)
        accrued = sum(r["accrued"] for r in rows)
        certified = sum(r["certified"] or 0 for r in rows)
        return {"coded": coded, "accrued": accrued, "balance": coded - accrued, "certified": certified, "share_f": 1.0,
                "execution_f": accrued / coded if coded else None, "_label": label}

    def budget_summary(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Resumen")
        self.widths(ws, [2.4] + [12.6] * 12 + [2.4])
        self.page(ws, tall=1)
        ws.set_tab_color(theme.MORADO)
        row = self.band(ws, ctx["title"], self.subtitle(), last=13)
        row = self.heading(ws, row + 1, "Cifras clave", ctx["period_label"])
        row = self.kpi_row(ws, row + 1, self.kpi_cards("del total institucional"))
        top = row + 1
        self.heading(ws, top, "Ejecución por programa presupuestario", last=7)
        ws.merge_range(top, 8, top, 12, "Ejecución por zona",
                       self.f(font_name=DISPLAY, font_size=13, bold=True, font_color=theme.MORADO_900, bottom=2, bottom_color=theme.LILA_200))
        rows = self._money_rows(ctx["programs"])
        layout = [("Programa", "short", "text", 1, 3), ("Codificado (millones de USD)", "coded", "mill", 4, 1),
                  ("Devengado (millones de USD)", "accrued", "mill", 5, 1), ("Ejecución", "execution_f", "pct", 6, 1),
                  ("Participación", "share_f", "pct", 7, 1)]
        first, last, nxt = self.table(ws, top + 1, layout, rows, total=self._money_total(ctx["programs"]), header_height=36)
        self.data_bar(ws, first, last, 6, theme.LILA_300, maximum=1)
        picture = map_png(ctx["map_values"], layer="zona", selected=set(ctx["selected_zones"]), rate=True,
                          label="Ejecución presupuestaria por zona", width=5.4, height=4.8, dpi=200)
        self.image(ws, top + 1, 8, picture, 440, "mapa_zonas.png", x_offset=10, y_offset=4,
                   description="Mapa del Ecuador: ejecución presupuestaria por zona")
        row = max(nxt, top + 1 + 18) + 1
        row = self.findings(ws, row, ctx["insights"][:4])
        ws.print_area(0, 0, row, 13)
        ws.activate()
        ws.set_first_sheet()
        ws.set_zoom(90)

    def _money_sheet(self, name: str, tab: str, title: str, blocks: list[tuple[str, list[dict], str, bool]], picture: bytes | None = None,
                     tall_names: bool = False):
        """A sheet of budget tables: (heading, rows, label header, whether the last column names the zone)."""
        ws = self.wb.add_worksheet(name)
        columns = [2.4, 6.0, 60.0, 18.0, 18.0, 12.0, 18.0, 17.0, 15.0, 2.4]
        self.widths(ws, columns)
        self.page(ws)
        ws.set_tab_color(tab)
        row = self.band(ws, title, self.subtitle(), last=len(columns) - 1)
        if picture:
            row = self.heading(ws, row + 1, "Ejecución presupuestaria por zona", "Zonas seleccionadas en dorado" if self.ctx["selected_zones"] else "",
                               last=len(columns) - 2)
            self.image(ws, row + 1, 2, picture, 600, "mapa_zonas_detalle.png", x_offset=4, y_offset=6,
                       description="Mapa del Ecuador: ejecución presupuestaria por zona")
            row += 27
            ws.set_h_pagebreaks([row])
        for heading, rows, label, zone in blocks:
            row = self.heading(ws, row + 1, heading, "Montos en USD", last=len(columns) - 2)
            layout = [("N.º", "n", "center", 1, 1), (label, "name", "text", 2, 1), ("Codificado", "coded", "usd", 3, 1),
                      ("Devengado", "accrued", "usd", 4, 1), ("Ejecución", "execution_f", "pct", 5, 1),
                      ("Saldo por devengar", "balance", "usd", 6, 1), ("Certificado", "certified", "usd", 7, 1)]
            layout.append(("Zona", "zone", "code", 8, 1) if zone else ("Participación", "share_f", "pct", 8, 1))
            first, last, nxt = self.table(ws, row, layout, self._money_rows(rows), total=self._money_total(rows), label_index=1,
                                          header_height=36, height=30 if tall_names else 19)
            if zone:
                ws.autofilter(row, 1, last, 8)
            else:
                self.data_bar(ws, first, last, 8, theme.LILA_300, maximum=1)
            row = nxt + 1
        ws.set_zoom(90)
        return ws

    def budget_detail(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Detalle")
        columns = [2.4, 16.0, 40.0, 44.0, 34.0, 26.0, 16.0, 18.0, 18.0, 12.0, 18.0, 2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.LILA_300)
        row = self.band(ws, "Detalle del presupuesto institucional", self.subtitle(), last=last_col, compact=True)
        layout = [("Zona", "zone", "code", 1, 1), ("Unidad ejecutora", "unit", "text", 2, 1), ("Programa", "program", "text", 3, 1),
                  ("Grupo de gasto", "group", "text", 4, 1), ("Fuente de financiamiento", "source", "text", 5, 1),
                  ("Tipo de gasto", "kind", "code", 6, 1), ("Codificado", "coded", "usd", 7, 1), ("Devengado", "accrued", "usd", 8, 1),
                  ("Ejecución", "execution_f", "pct", 9, 1), ("Saldo por devengar", "balance", "usd", 10, 1)]
        detail = [{**d, "execution_f": d["execution"] / 100 if d.get("execution") is not None else None} for d in ctx["detail"]]
        totals_row, header_row = row + 1, row + 3
        first, last = header_row + 1, header_row + max(1, len(detail))
        edge = dict(top=2, top_color=theme.MORADO)
        ws.set_row(totals_row, 24)
        ws.merge_range(totals_row, 1, totals_row, 6, "Total de las filas visibles",
                       self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
        for _header, key, kind, column, _span in layout[6:]:
            if kind == "pct":
                ws.write(totals_row, column, "", self.f(bg_color=theme.LAVANDA, **edge))
                continue
            rng = f"{xl_rowcol_to_cell(first, column)}:{xl_rowcol_to_cell(last, column)}"
            ws.write_formula(totals_row, column, f"=SUBTOTAL(109,{rng})", self.cell_format(kind, theme.LAVANDA, bold=True, **edge),
                             sum(d[key] or 0 for d in detail))
        ws.set_row(totals_row + 1, 6)
        self.table(ws, header_row, layout, detail, label_index=1, header_height=36, height=18)
        ws.autofilter(header_row, 1, last, last_col - 1)
        ws.freeze_panes(first, 3)
        ws.repeat_rows(header_row)
        ws.set_zoom(90)

    def budget_book(self):
        ctx = self.ctx
        self.budget_summary()
        self._money_sheet("Programas", theme.VIOLETA_500, "Ejecución por programa presupuestario",
                          [("Programas presupuestarios", ctx["programs"], "Programa presupuestario", False)], tall_names=True)
        picture = map_png(ctx["map_values"], layer="zona", selected=set(ctx["selected_zones"]), rate=True,
                          label="Ejecución presupuestaria por zona", annotate=0, width=6.6, height=5.6, dpi=200)
        self._money_sheet("Zonas", theme.ORO, "Ejecución por zona y unidad ejecutora",
                          [("Planta central y zonas", ctx["zones"], "Zona", False),
                           ("Unidades ejecutoras", ctx["units"], "Unidad ejecutora", True)], picture=picture)
        self._money_sheet("Grupos de gasto", theme.FUCSIA, "Ejecución por grupo y tipo de gasto",
                          [("Grupos de gasto", ctx["groups"], "Grupo de gasto", False),
                           ("Tipos de gasto", ctx["kinds"], "Tipo de gasto", False),
                           ("Fuentes de financiamiento", ctx["sources"], "Fuente de financiamiento", False)])
        self.budget_detail()
        facts = [("Institución", ctx["institution"]), ("Producto", f"Libro de datos de {PRODUCT}"), ("Ámbito", ctx["module_label"]),
                 ("Periodo", ctx["period_label"]), ("Zona", ctx["territory_label"]), ("Programas", ctx["programs_label"]),
                 ("Fecha de generación", ctx["generated_label"].capitalize()), ("Unidad monetaria", "Dólares de los Estados Unidos (USD)")]
        contents = [("Resumen", "Cifras clave, ejecución por programa, mapa por zona y aspectos destacados"),
                    ("Programas", "Codificado, devengado, ejecución, saldo y certificado por programa presupuestario"),
                    ("Zonas", "Ejecución por zona y por unidad ejecutora"),
                    ("Grupos de gasto", "Ejecución por grupo de gasto, tipo de gasto y fuente de financiamiento"),
                    ("Detalle", "Cada unidad, programa, grupo y fuente, con filtros y totales que se recalculan"),
                    ("Ficha técnica", "Identificación del producto y definiciones")]
        self.facts_sheet(facts, ctx["definitions"], contents)

    # ---------------------------------------------------------------- build
    def build(self) -> bytes:
        ctx = self.ctx
        self.wb.set_properties({
            "title": ctx["title"], "subject": f"{ctx['module_label']} · {ctx['period_label']} · {ctx['territory_label']}",
            "author": ctx["institution"], "company": ctx["institution"], "manager": PRODUCT,
            "category": "Indicadores estratégicos", "keywords": f"MTDH, {PRODUCT}, indicadores",
        })
        self.wb.set_size(1680, 1040)
        kind = ctx.get("kind", "territorial")
        from .excel_areas import BOOKS
        if kind == "presupuesto":
            self.budget_book()
        elif kind in BOOKS:
            BOOKS[kind](self)
        else:
            self.summary()
            self.programs_sheet()
            if ctx.get("monthly"):
                self.monthly_sheet()
            levels = ctx.get("levels") or ["provincia"]
            if "provincia" in levels:
                self.provinces_sheet()
            for level in ("canton", "parroquia"):
                if level in levels and ctx.get("territories", {}).get(level):
                    self.territory_sheet(level)
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
    if context.get("kind", "territorial") == "territorial" and not context.get("programs"):
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
                            "company": "Ministerio de Trabajo y Desarrollo Humano", "manager": PRODUCT,
                            "category": "Estadística institucional", "comments": f"Selección {selection}"})
    ws.set_zoom(95)
    book.wb.close()
    return _institutional_theme(book.out.getvalue())
