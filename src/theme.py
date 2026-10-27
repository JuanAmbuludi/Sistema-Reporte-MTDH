"""Institutional design tokens shared by the interface, charts and every export.

Anchors come from the MTDH bulletin in ``docs/reference`` (header plate, table
surfaces and text) and from the official logo (the gold of the national coat of
arms).  Every other step is generated in OKLCH at the institutional hue, so the
interface, Plotly, matplotlib, Excel, Word, PDF and PowerPoint speak the same
visual language.  Change a value here and every output follows.
"""
from __future__ import annotations

# --- Brand anchors -----------------------------------------------------------
MORADO = "#512F8D"        # Morado institucional: placa del logo y cabeceras del boletín
LAVANDA = "#EBE5F3"       # Superficie lavanda del boletín
NIEBLA = "#F7F5FA"        # Fondo claro del boletín
TINTA = "#20202B"         # Texto principal
PIZARRA = "#5A5765"       # Texto secundario
LINEA = "#ECE9F0"         # Divisores y bordes suaves
ORO = "#F8C018"           # Oro del escudo nacional, tomado del logo oficial
FUCSIA = "#C33F8D"        # Acento secundario: servicios de protección social
BLANCO = "#FFFFFF"

# --- Purple ramp at the institutional hue (OKLCH 295.6°) ----------------------
MORADO_950 = "#1B0D35"
MORADO_900 = "#2B164F"
MORADO_800 = "#3D216D"
MORADO_600 = "#603EA0"
VIOLETA_500 = "#7657B9"
VIOLETA_400 = "#8F75CF"
LILA_300 = "#A995E0"
LILA_200 = "#C1B4EC"
LILA_100 = "#D8D0F4"
LILA_50 = "#F1EDFA"

# --- Fuchsia ramp (OKLCH 348°) and gold support steps -------------------------
FUCSIA_700 = "#A32C74"
FUCSIA_300 = "#E6A3C5"
FUCSIA_100 = "#FAE9F1"
ORO_700 = "#B07A00"       # Oro oscuro para texto sobre fondos claros
ORO_100 = "#FDF5DB"

# --- Chart roles ---------------------------------------------------------------
# Categorical pair validated with the dataviz checks (lightness band, CVD
# separation, normal-vision floor and 3:1 contrast on white).
SERIE_BONOS = "#5A369A"
SERIE_SERVICIOS = FUCSIA
ACUMULADO_PREVIO = LILA_200
# Sequential magnitude: one hue, light to dark (exactly ten steps for Streamlit).
SEQUENTIAL = ["#F7F6FD", "#EAE7F9", "#D8D0F4", "#C1B4EC", "#A995E0",
              "#8F75CF", "#7657B9", "#603EA0", "#512F8D", "#3D216D"]
PLOTLY_SEQUENTIAL = [[i / (len(SEQUENTIAL) - 1), c] for i, c in enumerate(SEQUENTIAL)]
# On the dark hero the ramp flips: more coverage reads lighter (OKLCH L 0.40→0.95).
NIGHT_SEQUENTIAL = ["#4E3680", "#62479D", "#795DB9", "#9077CF", "#A793DF", "#BFB0EC", "#D7CEF5", "#EFECFC"]

# --- Typography ----------------------------------------------------------------
FONT_DISPLAY = "Montserrat"   # Familia del nombre del Ministerio en el logo oficial
FONT_TEXT = "Public Sans"     # Sans neutra diseñada para servicios públicos
WEB_FONT_STACK = "'Public Sans', 'Segoe UI', Arial, sans-serif"
WEB_DISPLAY_STACK = "Montserrat, 'Public Sans', 'Segoe UI', Arial, sans-serif"
# Office documents use fonts installed with Microsoft Office on Windows and Mac.
OFFICE_DISPLAY = "Century Gothic"
OFFICE_TEXT = "Calibri"

# --- Program vocabulary ----------------------------------------------------------
# Official names stay in tables; these labels keep charts legible.
PROGRAM_SHORT = {
    "BDH": "Bono de Desarrollo Humano",
    "BDHV": "BDH con componente variable",
    "BMD": "Bono 1.000 Días",
    "BJGL": "Bono Joaquín Gallegos Lara",
    "MMA": "Pensión Mis Mejores Años",
    "PTV": "Pensión Toda Una Vida",
    "PAM": "Pensión Adultos Mayores",
    "PCD": "Pensión Discapacidad",
    "DII": "Desarrollo Infantil Integral",
    "PAM_SERV": "Personas adultas mayores",
    "PCD_SERV": "Personas con discapacidad",
    "PE": "Protección Especial",
}
PROGRAM_ABBR = {
    "BDH": "BDH", "BDHV": "BDH-V", "BMD": "B1000", "BJGL": "BJGL", "MMA": "PMMA", "PTV": "PTUV",
    "PAM": "PAM", "PCD": "PCD", "DII": "DII", "PAM_SERV": "S-PAM", "PCD_SERV": "S-PCD", "PE": "PE",
}
SECTIONS = {
    "bonos_pensiones": "Bonos y pensiones",
    "proteccion_integral": "Servicios de protección social",
}

# Natural regions used to group provinces in tables and maps.
REGIONS = {
    "01": "Sierra", "02": "Sierra", "03": "Sierra", "04": "Sierra", "05": "Sierra", "06": "Sierra",
    "07": "Costa", "08": "Costa", "09": "Costa", "10": "Sierra", "11": "Sierra", "12": "Costa",
    "13": "Costa", "14": "Amazonía", "15": "Amazonía", "16": "Amazonía", "17": "Sierra", "18": "Sierra",
    "19": "Amazonía", "20": "Insular", "21": "Amazonía", "22": "Amazonía", "23": "Costa", "24": "Costa",
    "90": "Sin delimitar",
}


def program_label(program_id: str | None, fallback: str) -> str:
    """Chart label for a program; the full official name stays in tables."""
    return PROGRAM_SHORT.get(str(program_id), fallback) if program_id is not None else fallback


def rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(color: str, other: str, amount: float) -> str:
    """Linear sRGB mix used for small UI tints, never for data encoding."""
    a, b = rgb(color), rgb(other)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def ramp_at(t: float, stops: list[str] | None = None) -> str:
    """Continuous position (0–1) on a ramp, interpolated between its steps."""
    stops = stops or SEQUENTIAL[1:]
    t = min(1.0, max(0.0, float(t)))
    position = t * (len(stops) - 1)
    index = int(position)
    if index >= len(stops) - 1:
        return stops[-1]
    return mix(stops[index], stops[index + 1], position - index)


def ramp(values, palette=SEQUENTIAL, mode: str = "quantile"):
    """Map numbers to a sequential ramp; missing values return None.

    ``quantile`` ranks the values (an ordinal reading: lower → higher) so very
    skewed territories still show their order; ``linear`` keeps proportions.
    """
    values = list(values)
    present = sorted({v for v in values if v is not None and v == v})
    if not present:
        return [None for _ in values]
    last = len(palette) - 1
    out = []
    for v in values:
        if v is None or v != v:
            out.append(None)
        elif len(present) == 1:
            out.append(palette[last])
        elif mode == "linear":
            lo, hi = present[0], present[-1]
            out.append(palette[min(last, int(round((v - lo) / (hi - lo) * last)))])
        else:
            out.append(palette[min(last, int(round(present.index(v) / (len(present) - 1) * last)))])
    return out
