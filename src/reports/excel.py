"""Institutional Excel workbook: the flagship report format of InfoReportes.

Built with XlsxWriter from the same report context as every other export.
Design rules:
* every figure is a real number with a number format (no numbers as text);
* totals are live formulas that also carry their computed value, so they
  read correctly in Excel, LibreOffice, Google Sheets and phone previews;
* charts are native Excel charts, editable by the reader;
* colours, fonts and the Office theme of the file follow the MTDH identity,
  so tables or charts the reader adds later inherit the institutional palette.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

import xlsxwriter
from PIL import Image
from xlsxwriter.utility import xl_rowcol_to_cell

from src import theme
from .charts import map_png
from .context import MONTHS, number

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
DISPLAY = theme.OFFICE_DISPLAY
TEXT = theme.OFFICE_TEXT
WHITE = "#FFFFFF"
MUTED = "#6E6880"
SOFT_LINE = "#E7E2EF"
NA_COLOR = "#8A80A0"

INT = "#,##0"
USD = "#,##0.00"
MILL = "#,##0.00,,"
MILL_KPI = '"USD "#,##0.0,," M"'
PCT = "0.0%"
NUMERIC = ("int", "units", "usd", "mill", "pct")

SECTION_SHEETS = {"bonos_pensiones": "Bonos y pensiones", "proteccion_integral": "Protección integral"}
SECTION_TAB = {"bonos_pensiones": theme.MORADO_600, "proteccion_integral": theme.FUCSIA}
SECTION_SUB = {
    "bonos_pensiones": "Programas de transferencias monetarias",
    "proteccion_integral": "Servicios de atención directa",
}


def _ts(context: dict) -> str:
    try:
        moment = datetime.fromisoformat(context["generated_at"])
    except (KeyError, ValueError):
        return ""
    return f"{moment.day} de {MONTHS[moment.month]} de {moment.year}, {moment:%H:%M} (hora de Ecuador)"


def _share(part, whole):
    return (part or 0) / whole if whole else None


class Workbook:
    def __init__(self, context: dict):
        self.ctx = context
        self.out = BytesIO()
        self.wb = xlsxwriter.Workbook(self.out, {"in_memory": True, "strings_to_numbers": False,
                                                 "strings_to_formulas": False, "strings_to_urls": False})
        self._formats: dict = {}
        self.year = context["year"]
        self.sections = {s["id"]: s for s in context["sections"]}
        self.plan: list[tuple[str, str]] = []
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
        ws.set_footer(f'&L&"{TEXT},Regular"&8&K5A5765InfoReportes · Estadística institucional'
                      f'&C&"{TEXT},Regular"&8&K5A5765Página &P de &N'
                      f'&R&"{TEXT},Regular"&8&K5A5765Selección {self.ctx.get("selection_hash", "")}')

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
            ws.merge_range(row + 1, col, row + 2, last, "No disponible", self.f(bg_color=bg, font_name=DISPLAY, font_size=15, bold=True,
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
        code, center, int, units, usd, mill, pct.  Missing numbers read N/D
        (units that do not apply read No aplica).  Returns (first, last, next).
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
                    self._put(ws, nxt, col, span, "N/D", self.f(bg_color=theme.LAVANDA, bold=True, italic=True, font_color=NA_COLOR,
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
                self._put(ws, row, col, span, "No aplica" if kind == "units" else "N/D", self.na_format(fill))
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
        ctx, s = self.ctx, self.sections
        cards = []
        if "bonos_pensiones" in s:
            b = s["bonos_pensiones"]
            n = len(b["rows"])
            cards.append(("Beneficiarios de bonos y pensiones", b["people"], INT,
                          f"{n} {'programa' if n == 1 else 'programas'} de transferencias monetarias", theme.MORADO))
        if "proteccion_integral" in s:
            p = s["proteccion_integral"]
            n = len(p["rows"])
            cards.append(("Usuarios de servicios de protección integral", p["people"], INT,
                          f"{n} {'servicio' if n == 1 else 'servicios'} de atención directa", theme.FUCSIA))
            cards.append(("Unidades de atención", p["units"], INT, "Reportadas por los servicios de protección integral", theme.VIOLETA_500))
        cards.append((f"Monto fiscal {self.year}", ctx["fiscal_total"], MILL_KPI,
                      f"Acumulado de gobierno: USD {number((ctx['government_total'] or 0) / 1e6, 1)} millones", theme.ORO))
        if len(cards) < 4:
            cards.append(("Acumulado de gobierno", ctx["government_total"], MILL_KPI,
                          f"{ctx['previous_label']} más el monto fiscal {self.year}", theme.VIOLETA_500))
        if len(cards) < 4:
            executed = ctx.get("executed_total")
            cards.append(("Presupuesto ejecutado", executed, MILL_KPI,
                          "Ejecución verificada" if executed is not None else "La fuente no certifica la fase de ejecución", theme.LILA_300))
        return cards[:4]

    # ----------------------------------------------------------------- sheets
    def cover(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Portada")
        self.widths(ws, [2.4] + [12.6] * 12 + [2.4])
        self.page(ws, tall=1)
        ws.set_tab_color(theme.MORADO)
        heights = [14, 46, 12, 20, 36, 36, 28, 20, 20, 16, 18, 16]
        for row, height in enumerate(heights):
            ws.set_row(row, height)
            for col in range(14):
                ws.write_blank(row, col, None, self.f(bg_color=theme.MORADO))
        self.logo(ws, 1, 1, 48, y_offset=4)
        purple = dict(bg_color=theme.MORADO)
        ws.write(3, 1, "Reporte estadístico institucional", self.f(**purple, font_size=10.5, bold=True, font_color="#D9CCF0"))
        ws.merge_range(4, 1, 5, 7, ctx["title"], self.f(**purple, font_name=DISPLAY, font_size=25, bold=True, font_color=WHITE, text_wrap=True))
        ws.write(6, 1, ctx["period_label"], self.f(**purple, font_name=DISPLAY, font_size=15, bold=True, font_color=theme.ORO))
        ws.write(7, 1, f"Alcance: {ctx['scope_label']}", self.f(**purple, font_size=10.5, font_color="#E9E2F6"))
        titles = [s["title"] for s in ctx["sections"]]
        ws.write(8, 1, "Ámbitos: " + (" y ".join([titles[0]] + [t.lower() for t in titles[1:]])), self.f(**purple, font_size=10.5, font_color="#E9E2F6"))
        ws.write(10, 1, f"Generado el {_ts(ctx)}", self.f(**purple, font_size=9, italic=True, font_color="#CBBEE3"))
        values = {t["code"]: t["people"] for t in ctx["territory"]}
        few = {t["code"] for t in ctx["territory"] if t["code"] != "90"}
        cover_map = map_png(values, mode="night", selected=few if len(few) <= 3 else set(), annotate=0, legend=False,
                            scale="quantile", width=6.0, height=5.0)
        self.image(ws, 0, 8, cover_map, 452, "mapa_portada.png", x_offset=16, y_offset=4,
                   description="Mapa del Ecuador con la cobertura reportada por provincia")
        ws.set_row(12, 6)
        for col in range(14):
            ws.write_blank(12, col, None, self.f(bg_color=theme.ORO))
        row = self.heading(ws, 14, "Indicadores principales", ctx["period_label"])
        row = self.kpi_row(ws, row + 1, self.kpi_cards())
        row = self.heading(ws, row + 1, "Contenido del libro", "Haz clic en el nombre de una hoja para abrirla")
        line = dict(bottom=7, bottom_color=SOFT_LINE)
        for name, description in self.plan:
            ws.set_row(row, 24)
            ws.merge_range(row, 1, row, 3, None, self.f(**line))
            ws.write_url(row, 1, f"internal:'{name}'!A1", self.f(font_name=DISPLAY, font_size=11, bold=True, font_color=theme.MORADO,
                                                                 indent=1, **line), string=name, tip=f"Ir a la hoja {name}")
            ws.merge_range(row, 4, row, 12, description, self.f(font_size=10, font_color=theme.PIZARRA, **line))
            row += 1
        row = self.heading(ws, row + 1, "Ficha técnica")
        facts = [
            ("Fuente", f"{ctx['source_label']} (hoja provincial)"),
            ("Identificación del corte", ctx.get("source_period") or ctx["period_label"]),
            ("Huella SHA-256 de la fuente", ctx.get("source_sha256") or "No registrada"),
            ("Selección exportada", f"Código {ctx['selection_hash']}; {number(len(ctx['detail']))} registros de programa por provincia"),
            ("Unidad monetaria", "Dólares de los Estados Unidos (USD). Montos acumulados; no son transferencias mensuales."),
            ("Elaborado por", ctx["author"]),
        ]
        for label, value in facts:
            ws.set_row(row, 21)
            ws.merge_range(row, 1, row, 3, label, self.f(font_size=9.5, bold=True, font_color=theme.MORADO_800, indent=1, **line))
            ws.merge_range(row, 4, row, 12, value, self.f(font_size=9.5, font_color=theme.PIZARRA, text_wrap=True, **line))
            row += 1
        row = self.note(ws, row + 1, "Las cifras son agregados por programa y provincia. Una misma persona puede constar en más de un programa, "
                                     "por eso beneficiarios y usuarios no se suman como personas únicas. N/D indica información no disponible.")
        ws.print_area(0, 0, row, 13)
        ws.activate()
        ws.set_first_sheet()
        ws.set_zoom(90)

    def summary(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Resumen")
        self.widths(ws, [2.4] + [12.6] * 12 + [2.4])
        self.page(ws)
        ws.set_tab_color(theme.VIOLETA_500)
        row = self.band(ws, "Resumen ejecutivo", f"{ctx['period_label']} · {ctx['scope_label']}", last=13)
        row = self.heading(ws, row + 1, "Indicadores principales")
        row = self.kpi_row(ws, row + 1, self.kpi_cards())
        row = self.heading(ws, row + 1, "Lectura del corte")
        for section in ctx["sections"]:
            for text in section["insights"][:3]:
                ws.set_row(row, 30)
                ws.write(row, 1, "●", self.f(font_color=theme.ORO, align="center", font_size=9))
                ws.merge_range(row, 2, row, 12, text, self.f(font_size=10.5, text_wrap=True))
                row += 1
        row = self.heading(ws, row + 1, "Indicadores por ámbito", "Montos en millones de USD")
        layout = [("Ámbito", "label", "text", 1, 3), ("Programas", "programs", "int", 4, 1), ("Beneficiarios o usuarios", "people", "int", 5, 2),
                  ("Unidades de atención", "units", "units", 7, 1), (f"Monto fiscal {self.year}", "fiscal", "mill", 8, 1),
                  (ctx["previous_label"], "previous", "mill", 9, 2), ("Acumulado de gobierno", "government", "mill", 11, 1),
                  ("Presupuesto ejecutado", "executed", "mill", 12, 1)]
        rows = [{**s, "label": s["title"], "programs": len(s["rows"])} for s in ctx["sections"]]
        _f, _l, row = self.table(ws, row, layout, rows, header_height=36)
        program_break = row + 1
        row = self.heading(ws, row + 1, "Cobertura y recursos por programa", "Montos en millones de USD")
        program_rows = sorted(ctx["program_rows"], key=lambda r: -(r["people"] or 0))
        total_people = sum(r["people"] or 0 for r in program_rows)
        rows = [{**r, "section_name": theme.SECTIONS.get(r.get("section", ""), ""), "share": _share(r["people"], total_people)} for r in program_rows]
        layout = [("Programa o servicio", "label", "text", 1, 4), ("Ámbito", "section_name", "code", 5, 3),
                  ("Beneficiarios o usuarios", "people", "int", 8, 2), ("Participación en la cobertura", "share", "pct", 10, 1),
                  (f"Monto fiscal {self.year}", "fiscal", "mill", 11, 1), ("Acumulado de gobierno", "government", "mill", 12, 1)]
        total = {"people": total_people, "share": 1.0 if total_people else None, "fiscal": ctx["fiscal_total"], "government": ctx["government_total"]}
        first, last, row = self.table(ws, row, layout, rows, total=total, header_height=36)
        self.data_bar(ws, first, last, 10, theme.LILA_300, maximum=1)
        colors = [theme.SECTION_COLORS.get(r.get("section"), theme.SERIE_BONOS) for r in rows]
        height = max(320, 30 * len(rows) + 90)
        chart_row = row + 1
        ws.set_h_pagebreaks([program_break, chart_row])
        if len(rows) > 1:
            ws.insert_chart(chart_row, 1, self.bar_chart("Resumen", first, last, 1, 8, "Beneficiarios y usuarios por programa", colors, width=548, height=height),
                            {"x_offset": 2, "y_offset": 6, "object_position": 3})
            ws.insert_chart(chart_row, 7, self.bar_chart("Resumen", first, last, 1, 11, f"Monto fiscal {self.year} por programa (millones de USD)",
                                                         colors, number_format="#,##0.0,,", width=548, height=height),
                            {"x_offset": 6, "y_offset": 6, "object_position": 3})
        ws.print_area(0, 0, chart_row + int(height / 20) + 2, 13)
        ws.set_zoom(90)

    def section_sheet(self, section):
        ctx = self.ctx
        sid = section["id"]
        name = SECTION_SHEETS[sid]
        service = sid == "proteccion_integral"
        accent = SECTION_TAB[sid]
        soft = theme.mix(accent, "#FFFFFF", 0.5)
        ws = self.wb.add_worksheet(name)
        # A | N.º | Programa | people | share | units? | fiscal | previous | government | executed | margin
        columns = [2.4, 6.0, 40.0, 15.0, 13.0] + ([14.0] if service else []) + [17.5, 17.5, 17.5, 17.5, 2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(accent)
        row = self.band(ws, section["title"], f"{SECTION_SUB[sid]} · {ctx['period_label']} · {ctx['scope_label']}", last=last_col)
        people_label = "Usuarios" if service else "Beneficiarios"
        cards = [(f"{people_label} reportados", section["people"], INT, "Conteos agregados; no equivalen a personas únicas", accent)]
        if service:
            cards.append(("Unidades de atención", section["units"], INT, "Centros y modalidades reportados por los servicios", theme.VIOLETA_500))
        cards.append((f"Monto fiscal {self.year}", section["fiscal"], MILL_KPI, f"Columna Presupuesto {self.year} de la fuente", theme.ORO))
        cards.append(("Acumulado de gobierno", section["government"], MILL_KPI, f"{ctx['previous_label']} más el monto fiscal", theme.LILA_300))
        row = self.heading(ws, row + 1, "Indicadores del ámbito", last=last_col - 1)
        row = self.kpi_row(ws, row + 1, cards, first=1, last=last_col - 1)
        row = self.heading(ws, row + 1, "Detalle por servicio" if service else "Detalle por programa", "Montos en USD", last=last_col - 1)
        total_people = section["people"] or 0
        rows = [{**r, "n": i + 1, "share": _share(r["people"], total_people)} for i, r in enumerate(section["rows"])]
        layout = [("N.º", "n", "center", 1, 1), ("Servicio" if service else "Programa", "label", "text", 2, 1),
                  (people_label, "people", "int", 3, 1), ("Participación", "share", "pct", 4, 1)]
        col = 5
        if service:
            layout.append(("Unidades de atención", "units", "units", col, 1))
            col += 1
        layout += [(f"Monto fiscal {self.year}", "fiscal", "usd", col, 1), (ctx["previous_label"], "previous", "usd", col + 1, 1),
                   ("Acumulado de gobierno", "government", "usd", col + 2, 1), ("Presupuesto ejecutado", "executed", "usd", col + 3, 1)]
        total = {"people": section["people"], "share": 1.0 if total_people else None, "units": section["units"], "fiscal": section["fiscal"],
                 "previous": section.get("previous"), "government": section["government"], "executed": section["executed"]}
        first, last, nxt = self.table(ws, row, layout, rows, total=total, label_index=1)
        self.data_bar(ws, first, last, 4, soft, maximum=1)
        ws.freeze_panes(row + 1, 0)
        row = self.note(ws, nxt + 1, "El acumulado de gobierno ya incluye el monto fiscal; no se suman entre sí. "
                                     "Presupuesto ejecutado: N/D mientras no exista una fuente verificada.", last=last_col - 1)
        height = max(300, 32 * len(rows) + 80)
        breaks = [row + 1]
        if len(rows) > 1:
            ws.insert_chart(row + 1, 2, self.bar_chart(name, first, last, 2, 3, f"{people_label} por {'servicio' if service else 'programa'}",
                                                       [accent], width=680, height=height), {"y_offset": 8, "object_position": 3})
            row = row + 2 + int(height / 20) + 1
            breaks.append(row)
        else:
            row += 1
        ws.set_h_pagebreaks(breaks)
        row = self.heading(ws, row, "Provincias con mayor cobertura", "Diez principales de la selección", last=last_col - 1)
        top = section["territories"][:10]
        rows = [{**t, "n": i + 1, "share": _share(t["people"], total_people)} for i, t in enumerate(top)]
        layout = [("N.º", "n", "center", 1, 1), ("Provincia o territorio", "label", "text", 2, 1), (people_label, "people", "int", 3, 1),
                  ("Participación", "share", "pct", 4, 1)]
        col = 5
        if service:
            layout.append(("Unidades de atención", "units", "units", col, 1))
            col += 1
        layout += [(f"Monto fiscal {self.year}", "fiscal", "usd", col, 1), ("Región natural", "region", "code", col + 1, 1)]
        first, last, nxt = self.table(ws, row, layout, rows, label_index=1)
        self.data_bar(ws, first, last, 4, soft, maximum=1)
        if len(top) > 1:
            ws.insert_chart(nxt + 1, 2, self.bar_chart(name, first, last, 2, 3, f"{people_label} en las provincias principales", [accent],
                                                       width=680, height=max(280, 30 * len(top) + 80)), {"y_offset": 8, "object_position": 3})
        ws.set_zoom(90)

    def territory_sheet(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Territorio")
        # A | code | province | 12 data columns | margin  (the matrix needs twelve program columns)
        columns = [2.4, 8.0, 30.0] + [13.0] * 12 + [2.4]
        self.widths(ws, columns)
        last_col = len(columns) - 1
        self.page(ws)
        ws.set_tab_color(theme.ORO)
        row = self.band(ws, "Territorio", f"Cobertura y recursos por provincia · {ctx['period_label']} · {ctx['scope_label']}", last=last_col)
        row = self.heading(ws, row + 1, "Mapa de la cobertura reportada", "Galápagos se muestra en un recuadro", last=last_col - 1)
        territory = ctx["territory"]
        values = {t["code"]: t["people"] for t in territory}
        self.image(ws, row + 1, 1, map_png(values, label="Cobertura reportada", annotate=6, width=6.6, height=5.6), 600,
                   "mapa_territorial.png", x_offset=4, y_offset=6, description="Mapa coroplético de la cobertura reportada por provincia")
        top = [t for t in territory if t["code"] != "90"][:10]
        total_people = sum(t["people"] or 0 for t in territory)
        r0 = row + 2
        ws.merge_range(r0, 8, r0, 13, "Ranking provincial de la cobertura", self.f(font_name=DISPLAY, font_size=12, bold=True, font_color=theme.MORADO_900,
                                                                                   bottom=2, bottom_color=theme.LILA_200))
        for i, t in enumerate(top):
            r = r0 + 1 + i
            ws.set_row(r, 22)
            fill = theme.NIEBLA if i % 2 else WHITE
            leader = i < 3
            ws.write_number(r, 8, i + 1, self.f(bg_color=theme.MORADO if leader else fill, font_name=DISPLAY, bold=True,
                                                font_color=WHITE if leader else theme.MORADO, align="center"))
            ws.merge_range(r, 9, r, 11, t["label"], self.f(bg_color=fill, bold=leader, indent=1, font_color=theme.MORADO_900))
            ws.write_number(r, 12, t["people"] or 0, self.f(bg_color=fill, num_format=INT, align="right"))
            ws.write_number(r, 13, _share(t["people"], total_people) or 0, self.f(bg_color=fill, num_format=PCT, align="right", font_color=theme.PIZARRA))
        if top:
            self.data_bar(ws, r0 + 1, r0 + len(top), 13, theme.LILA_300)
        ws.merge_range(r0 + len(top) + 2, 8, r0 + len(top) + 4, 13,
                       "Participación de cada provincia en la cobertura reportada de la selección. Las tres primeras se destacan en morado. "
                       "La cobertura suma registros de distintos programas; no son personas únicas.",
                       self.f(font_size=9, italic=True, font_color=MUTED, text_wrap=True, valign="top"))
        row = row + 27
        territory_breaks = [row]
        row = self.heading(ws, row, "Indicadores por provincia", "Montos en millones de USD", last=last_col - 1)
        fields = [("Código", "code", "code"), ("Provincia o territorio", "label", "text"), ("Región natural", "region", "code")]
        if "bonos_pensiones" in self.sections:
            fields.append(("Beneficiarios de bonos", "beneficiaries", "int"))
        if "proteccion_integral" in self.sections:
            fields += [("Usuarios de servicios", "service_users", "int"), ("Unidades de atención", "units", "units")]
        if len(self.sections) > 1:
            fields.append(("Cobertura reportada total", "people", "int"))
        fields += [("Participación", "share", "pct"), (f"Monto fiscal {self.year}", "fiscal", "mill"),
                   (ctx["previous_label"], "previous", "mill"), ("Acumulado de gobierno", "government", "mill")]
        layout = [(header, key, kind, 1 + i, 1) for i, (header, key, kind) in enumerate(fields)]
        position = {key: 1 + i for i, (_h, key, _k) in enumerate(fields)}
        rows = [{**t, "share": _share(t["people"], total_people)} for t in territory]

        def maybe(key):
            return sum(t[key] or 0 for t in territory) if any(t[key] is not None for t in territory) else None

        total = {"beneficiaries": maybe("beneficiaries"), "service_users": maybe("service_users"), "units": maybe("units"),
                 "people": total_people, "share": 1.0 if total_people else None, "fiscal": ctx["fiscal_total"],
                 "previous": ctx.get("previous_total"), "government": ctx["government_total"]}
        first, last, nxt = self.table(ws, row, layout, rows, total=total, label_index=1, header_height=36)
        coverage_col = position.get("people", position.get("beneficiaries", position.get("service_users")))
        ws.conditional_format(first, coverage_col, last, coverage_col, {"type": "2_color_scale", "min_color": "#FFFFFF", "max_color": theme.LILA_300})
        self.data_bar(ws, first, last, position["share"], theme.LILA_300)
        ws.conditional_format(first, position["fiscal"], last, position["fiscal"], {"type": "2_color_scale", "min_color": "#FFFFFF", "max_color": "#F9E2A0"})
        row = self.note(ws, nxt + 1, "La zona en estudio se incluye en los totales, pero no tiene polígono en el mapa. "
                                     "Las unidades de atención corresponden solo a servicios de protección integral.", last=last_col - 1)
        territory_breaks.append(row + 1)
        ws.set_h_pagebreaks(territory_breaks)
        row = self.heading(ws, row + 1, "Composición por programa", "Beneficiarios o usuarios por provincia y programa", last=last_col - 1)
        self.matrix(ws, row)
        ws.set_zoom(90)

    def matrix(self, ws, row):
        ctx = self.ctx
        programs = [(item.get("id"), theme.PROGRAM_ABBR.get(item.get("id"), item["label"]), item["label"])
                    for item in sorted(ctx["program_rows"], key=lambda r: -(r["people"] or 0))][:12]
        provinces = [(t["code"], t["label"]) for t in ctx["territory"]]
        lookup = {(d["code"], d["program_id"]): d["people"] for d in ctx["detail"]}
        ws.set_row(row, 30)
        ws.merge_range(row, 1, row, 2, "Provincia o territorio", self.f(bg_color=theme.MORADO, font_name=DISPLAY, font_size=9, bold=True,
                                                                         font_color=WHITE, indent=1))
        for j, (_pid, abbr, full) in enumerate(programs):
            ws.write(row, 3 + j, abbr, self.f(bg_color=theme.MORADO, font_name=DISPLAY, font_size=9, bold=True, font_color=WHITE, align="right"))
        line = dict(bottom=7, bottom_color=SOFT_LINE)
        for i, (code, label) in enumerate(provinces):
            r = row + 1 + i
            ws.set_row(r, 18)
            fill = theme.NIEBLA if i % 2 else WHITE
            ws.merge_range(r, 1, r, 2, label, self.f(bg_color=fill, bold=True, font_color=theme.MORADO_900, indent=1, **line))
            for j, (pid, _abbr, _full) in enumerate(programs):
                value = lookup.get((code, pid))
                if value is None:
                    ws.write_blank(r, 3 + j, None, self.f(bg_color=fill, **line))
                else:
                    ws.write_number(r, 3 + j, value, self.f(bg_color=fill, num_format=INT, align="right", font_size=9.5, **line))
        last = row + len(provinces)
        if programs and provinces:
            ws.conditional_format(row + 1, 3, last, 2 + len(programs),
                                  {"type": "3_color_scale", "min_color": "#FFFFFF", "mid_color": theme.LILA_100, "max_color": theme.LILA_300,
                                   "mid_type": "percentile", "mid_value": 60})
        legend = last + 2
        ws.set_row(legend, 22)
        ws.set_row(legend + 1, 22)
        ws.merge_range(legend, 1, legend + 1, 14, "Siglas: " + "; ".join(f"{abbr}: {full}" for _pid, abbr, full in programs) + ".",
                       self.f(font_size=9, italic=True, font_color=MUTED, text_wrap=True, valign="top"))

    def detail_sheet(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Detalle")
        columns = [2.4, 26.0, 11.0, 38.0, 10.0, 30.0, 13.0, 15.0, 13.0, 17.5, 17.5, 17.5, 17.5, 2.4]
        self.widths(ws, columns)
        self.page(ws)
        ws.set_tab_color(theme.LILA_300)
        row = self.band(ws, "Detalle por programa y provincia", f"{ctx['period_label']} · {ctx['scope_label']} · usa los filtros del encabezado",
                        last=len(columns) - 1, compact=True)
        layout = [("Ámbito", "section", "text", 1, 1), ("Código del programa", "program_id", "code", 2, 1),
                  ("Programa o servicio", "program", "text", 3, 1), ("Código provincial", "code", "code", 4, 1),
                  ("Provincia o territorio", "province", "text", 5, 1), ("Región natural", "region", "code", 6, 1),
                  ("Beneficiarios o usuarios", "people", "int", 7, 1), ("Unidades de atención", "units", "units", 8, 1),
                  (f"Monto fiscal {self.year} (USD)", "fiscal", "usd", 9, 1), (f"{ctx['previous_label']} (USD)", "previous", "usd", 10, 1),
                  ("Acumulado de gobierno (USD)", "government", "usd", 11, 1), ("Presupuesto ejecutado (USD)", "executed", "usd", 12, 1)]
        detail = ctx["detail"]
        totals_row, header_row = row + 1, row + 3
        first, last = header_row + 1, header_row + len(detail)
        edge = dict(top=2, top_color=theme.MORADO)
        ws.set_row(totals_row, 24)
        ws.merge_range(totals_row, 1, totals_row, 6, "Total de las filas visibles (se recalcula al filtrar)",
                       self.f(bg_color=theme.LAVANDA, bold=True, font_color=theme.MORADO_900, indent=1, **edge))
        for header, key, kind, col, _span in layout[6:]:
            values = [d[key] for d in detail if d[key] is not None]
            if values and (key != "executed" or len(values) == len(detail)):
                rng = f"{xl_rowcol_to_cell(first, col)}:{xl_rowcol_to_cell(last, col)}"
                ws.write_formula(totals_row, col, f"=SUBTOTAL(109,{rng})", self.cell_format(kind, theme.LAVANDA, bold=True, **edge), sum(values))
            else:
                ws.write(totals_row, col, "N/D", self.f(bg_color=theme.LAVANDA, bold=True, italic=True, font_color=NA_COLOR, align="right", **edge))
        ws.set_row(totals_row + 1, 6)
        self.table(ws, header_row, layout, detail, label_index=2, header_height=38, height=18)
        ws.autofilter(header_row, 1, last, 12)
        ws.freeze_panes(first, 4)
        ws.repeat_rows(header_row)
        self.data_bar(ws, first, last, 7, theme.LILA_200)
        ws.set_zoom(90)

    def notes_sheet(self):
        ctx = self.ctx
        ws = self.wb.add_worksheet("Notas")
        self.widths(ws, [2.4, 34.0, 96.0, 2.4])
        self.page(ws, landscape=False)
        ws.set_tab_color(theme.PIZARRA)
        row = self.band(ws, "Notas metodológicas", f"Cómo leer las cifras de este libro · {ctx['period_label']}", last=3)
        row = self.heading(ws, row + 1, "Criterios de lectura", last=2)
        rows = [(f"Criterio {i}", text) for i, text in enumerate(ctx["notes"], 1)]
        layout = [("Criterio", 0, "text", 1, 1), ("Descripción", 1, "text", 2, 1)]
        first, _last, row = self.table(ws, row, layout, rows, height=46)
        labels = {"usuarios": "Beneficiarios y usuarios", "unidades": "Unidades de atención", "monto_fiscal": f"Monto fiscal {self.year}",
                  "monto_anterior": ctx["previous_label"], "monto_gobierno": "Acumulado de gobierno", "presupuesto_ejecutado": "Presupuesto ejecutado",
                  "periodo": "Corte", "provincia_codigo": "Código provincial", "fuente_hoja / fuente_fila": "Procedencia del registro"}
        definitions = [(labels.get(k, k), v) for k, v in ctx.get("definitions", {}).items()]
        if definitions:
            row = self.heading(ws, row + 1, "Definiciones", last=2)
            _f, _l, row = self.table(ws, row, [("Indicador", 0, "text", 1, 1), ("Definición", 1, "text", 2, 1)], definitions, height=34)
        quality = ctx.get("quality", {})
        if quality:
            names = {"claves_duplicadas": "Claves duplicadas", "valores_negativos": "Valores negativos", "conteos_fraccionarios": "Conteos fraccionarios",
                     "acumulados_no_conciliados": "Acumulados no conciliados", "diferencias_acumulado_2025": "Diferencias con la referencia 2025",
                     "ejecucion_disponible_filas": "Filas con ejecución verificada", "precision_monetaria_decimales": "Decimales monetarios conservados",
                     "tolerancia_conciliacion_usd": "Tolerancia de conciliación (USD)"}
            rows = [(names.get(k, k), number(v, 2) if isinstance(v, float) and not float(v).is_integer() else number(v)) for k, v in quality.items()]
            row = self.heading(ws, row + 1, "Controles de calidad de la base", last=2)
            _f, _l, row = self.table(ws, row, [("Control", 0, "text", 1, 1), ("Resultado", 1, "text", 2, 1)], rows, height=20)
        trace = [("Fuente", ctx["source_label"]), ("Huella SHA-256", ctx.get("source_sha256") or "No registrada"),
                 ("Identificación del corte", ctx.get("source_period") or ctx["period_label"]), ("Generado", _ts(ctx)),
                 ("Selección", ctx["selection_hash"]), ("Registros exportados", number(len(ctx["detail"]))),
                 ("Provincias y territorios", ", ".join(ctx["provinces"]))]
        row = self.heading(ws, row + 1, "Trazabilidad", last=2)
        first, last, row = self.table(ws, row, [("Elemento", 0, "text", 1, 1), ("Valor", 1, "text", 2, 1)], trace, height=22)
        ws.set_row(last, max(22, 15 * (len(", ".join(ctx["provinces"])) // 110 + 1)))
        sigla_rows = [(theme.PROGRAM_ABBR.get(r.get("id"), ""), r["label"]) for r in sorted(ctx["program_rows"], key=lambda r: r["label"])]
        row = self.heading(ws, row + 1, "Siglas de programas y servicios", last=2)
        self.table(ws, row, [("Sigla", 0, "text", 1, 1), ("Programa o servicio", 1, "text", 2, 1)], sigla_rows, height=19)
        ws.set_zoom(95)

    # ---------------------------------------------------------------- build
    def build(self) -> bytes:
        ctx = self.ctx
        plan = [("Portada", "Título, alcance, indicadores principales y este índice"),
                ("Resumen", "Lectura del corte, indicadores por ámbito y gráficos por programa")]
        if "bonos_pensiones" in self.sections:
            plan.append((SECTION_SHEETS["bonos_pensiones"], "Tabla por programa con participación, recursos y provincias principales"))
        if "proteccion_integral" in self.sections:
            plan.append((SECTION_SHEETS["proteccion_integral"], "Usuarios, unidades de atención y recursos por servicio"))
        if ctx.get("include_territory", True):
            plan.append(("Territorio", "Mapa coroplético, ranking, indicadores por provincia y composición por programa"))
        plan += [("Detalle", "Cada programa en cada provincia, con filtros y totales que se recalculan"),
                 ("Notas", "Criterios de lectura, definiciones, controles de calidad y trazabilidad")]
        self.plan = plan
        self.wb.set_properties({
            "title": ctx["title"], "subject": f"Estadísticas agregadas de protección social · {ctx['period_label']}",
            "author": ctx["author"], "company": "Ministerio de Trabajo y Desarrollo Humano", "manager": "InfoReportes",
            "category": "Estadística institucional", "keywords": "MTDH, protección social, bonos, pensiones, servicios, Ecuador",
            "comments": f"Selección {ctx['selection_hash']}. Fuente: {ctx['source_label']}.",
        })
        self.wb.set_size(1680, 1040)
        self.cover()
        self.summary()
        for sid in ("bonos_pensiones", "proteccion_integral"):
            if sid in self.sections:
                self.section_sheet(self.sections[sid])
        if ctx.get("include_territory", True):
            self.territory_sheet()
        self.detail_sheet()
        self.notes_sheet()
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
    if not context.get("sections"):
        raise ValueError("El reporte no contiene secciones.")
    return Workbook(context).build()


def table_xlsx(rows: list[dict], layout: list[tuple[str, str, str, float]], *, title: str, subtitle: str,
               period_label: str, selection: str = "", note: str = "", sheet: str = "Detalle") -> bytes:
    """A dashboard table as one institutional sheet: header plate, live totals of the visible rows, filters.

    ``layout`` items are (header, key, kind, width) with the kinds of :meth:`Workbook.table`; ``pct`` values are
    fractions (0.25 reads 25,0 %).  Used by the dashboard downloads, so they open correctly in any Excel locale.
    """
    book = Workbook({"year": 0, "sections": [], "period_label": period_label, "selection_hash": selection})
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
            ws.write(totals_row, col, "N/D", book.f(bg_color=theme.LAVANDA, bold=True, italic=True, font_color=NA_COLOR, align="right", **edge))
    ws.set_row(totals_row + 1, 6)
    book.table(ws, header_row, table_layout, rows, label_index=labels[-1] - 1 if labels else 0, header_height=36, height=19)
    ws.autofilter(header_row, 1, last, last_col - 1)
    ws.freeze_panes(first, (labels[-1] + 1) if labels else 1)
    ws.repeat_rows(header_row)
    for key, kind, col in numeric:
        if kind == "pct":
            book.data_bar(ws, first, last, col, theme.LILA_200)
    note = " ".join(part for part in ["El total superior suma solo las filas visibles y se recalcula al filtrar.", note] if part)
    book.note(ws, last + 2, note, first=1, last=last_col - 1, height=34)
    book.wb.set_properties({"title": title, "subject": subtitle, "author": "Ministerio de Trabajo y Desarrollo Humano",
                            "company": "Ministerio de Trabajo y Desarrollo Humano", "manager": "InfoReportes",
                            "category": "Estadística institucional", "comments": f"Selección {selection}"})
    ws.set_zoom(95)
    book.wb.close()
    return _institutional_theme(book.out.getvalue())
