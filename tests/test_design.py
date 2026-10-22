"""Design details that are easy to break silently: wording, number formats, highlights and table exports."""
from io import BytesIO

from openpyxl import load_workbook

from src import charts, theme, ui
from src.data import load_data
from src.reports import table_xlsx


def test_definitions_use_plain_language():
    for key, text in theme.definitions(2026).items():
        assert "_" not in text, f"La definición de {key} no debe mostrar nombres internos de columnas"
    assert "2023–2025" in theme.definitions(2026)["monto_gobierno"]


def test_numbers_follow_ecuadorian_format():
    assert ui.number(1578019) == "1.578.019"
    assert ui.number(55867299.384, 2) == "55.867.299,38"
    assert ui.pct(19.84) == "19,8 %"
    assert ui.number(None) == "—"


def test_place_names_from_upper_case_sources():
    assert ui.place_name("SAN MIGUEL DE LOS BANCOS") == "San Miguel de los Bancos"
    assert ui.place_name("ALFREDO BAQUERIZO MORENO (JUJAN)") == "Alfredo Baquerizo Moreno (Jujan)"
    assert ui.place_name("Santo Domingo de los Tsáchilas") == "Santo Domingo de los Tsáchilas"


def test_ranking_marks_the_chosen_province_in_gold_with_its_position():
    fig = charts.province_bars(load_data(), "usuarios", highlight={"09"})
    bar = fig.data[0]
    index = list(bar.y).index("<b>Guayas</b>")
    assert bar.marker.color[index] == theme.ORO
    assert "1.º" in bar.text[index]
    assert all(color in (theme.ORO, theme.LILA_200) for color in bar.marker.color)


def test_map_outlines_the_chosen_province():
    plain = charts.province_map(load_data(), "usuarios")
    marked = charts.province_map(load_data(), "usuarios", highlight={"09"})
    gold = [t for t in marked.data if getattr(t.line, "color", None) == theme.ORO]
    assert len(gold) == 1 and len(marked.data) == len(plain.data) + 2


def test_table_export_is_an_institutional_sheet_with_live_totals():
    rows = [{"programa": "Bono de Desarrollo Humano", "usuarios": 619073, "participacion": 0.6, "unidades": None, "monto_fiscal": 10.5},
            {"programa": "Desarrollo Infantil Integral", "usuarios": 274975, "participacion": 0.4, "unidades": 6759, "monto_fiscal": None}]
    layout = [("Programa o servicio", "programa", "text", 36.0), ("Beneficiarios y usuarios", "usuarios", "int", 14.0),
              ("Participación", "participacion", "pct", 12.0), ("Unidades de atención", "unidades", "units", 12.5),
              ("Monto fiscal 2026 (USD)", "monto_fiscal", "usd", 18.0)]
    content = table_xlsx(rows, layout, title="Detalle verificable", subtitle="Septiembre 2026", period_label="Septiembre 2026",
                         selection="abc123", note="Nota de lectura.")
    book = load_workbook(BytesIO(content))
    sheet = book["Detalle"]
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]
    flat = [v for row in values for v in row if v is not None]
    assert "Detalle verificable" in flat and "Beneficiarios y usuarios" in flat
    assert any(isinstance(v, str) and v.startswith("=SUBTOTAL(109,") for v in flat)
    assert 619073 in flat and "No aplica" in flat and "N/D" in flat
    assert sheet.auto_filter.ref and sheet.freeze_panes
    with __import__("zipfile").ZipFile(BytesIO(content)) as archive:
        assert 'name="MTDH Institucional"' in archive.read("xl/theme/theme1.xml").decode()
