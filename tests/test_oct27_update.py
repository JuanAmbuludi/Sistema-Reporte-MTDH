from io import BytesIO
from decimal import Decimal
import fitz
import openpyxl
from src import enos
from src.views.riesgos import RiskView
from src.views.respuesta import Response
from src.reports import generate_pdf,generate_xlsx


def test_new_cumulative_kit_cut_is_reconciled_not_appended():
    d=enos.load(enos.snapshots()[-1]);r=Response(d)
    assert len(r.kits)==r.kits.id_kobo.nunique()==111
    assert r.kits_total==13981 and r.kits.familias.sum()==12987
    assert r.kits.provincia.nunique()==22
    assert d['kits_metadatos']['variacion_kits']==591
    assert d['kits_metadatos']['registros_nuevos']==22
    assert d['cortes']['kits']=='2026-10-27T13:35:45'


def test_territorial_cut_replaces_el_oro_and_retains_other_latest_reports():
    d=enos.load(enos.snapshots()[-1]);r=Response(d)
    assert r.closed_units==143
    assert Response(d,provinces=['07']).closed_units==119
    assert Response(d,provinces=['09']).closed_units==17
    assert Response(d,provinces=['24']).closed_units==7
    assert Response(d,programs=['PAM_SERV']).closed_units==18
    assert Response(d,programs=['PCD_SERV']).closed_units==12
    assert Response(d,programs=['PE']).closed_units==7
    assert Response(d,programs=['DII']).closed_units==106
    assert len(r.alerts)==21 and r.units==10


def test_reference_pdf_does_not_replace_the_documented_bono_source():
    d=enos.load(enos.snapshots()[-1])
    assert sum(r['personas'] for r in d['bonos']['articulacion'])==1169
    assert sum(Decimal(str(r['monto'])) for r in d['bonos']['articulacion'])==Decimal('354379.41')
    assert sum(Decimal(str(r['monto'])) for r in d['bonos']['gestionados'])==Decimal('33200.80')
    assert d['cortes']['bonos']=='2026-10-23'


def test_approved_template_preserves_all_chart_types_and_updated_totals():
    v=RiskView();v.select(v.catalog()[-1]);assert v.prepare();ctx=v.report_context('Riesgos')
    pdf=fitz.open(stream=generate_pdf(ctx),filetype='pdf');assert len(pdf)==3
    text=' '.join(p.get_text() for p in pdf)
    for label in ['Plan ENOS - Ministerio de Trabajo','Detalle de las unidades de atención con alerta','Acciones del Ministerio','Alertas por provincia','Alertas por servicio','Evolución de las alertas','13.981','143','354.379,41']:
        assert label in text
    assert 'Evolución de las alertas' in text
    for a in ctx['response']['alerts']:assert a['code'] in pdf[1].get_text()
    assert 'Reportes sectoriales incorporados' not in text
    for a in ctx['response']['alerts']:assert a['code'] in text
    book=openpyxl.load_workbook(BytesIO(generate_xlsx(ctx)),data_only=True)
    cells=[str(c.value) for s in book for row in s for c in row if c.value is not None]
    for a in ctx['response']['alerts']:assert a['code'] in cells
    for u in ctx['response']['continuity']['detail']:assert u['unidad'] in cells


def test_pdf_tables_recover_padding_space_without_dropping_rows():
    from reportlab.pdfgen.canvas import Canvas
    from src.reports.risk_response import _pdf_table
    out=BytesIO();c=Canvas(out)
    bottom=_pdf_table(c,96,['Código'],[['REG-A'],['REG-B']],[180],size=8,padding=5)
    assert bottom>=52
    c.save();doc=fitz.open(stream=out.getvalue(),filetype='pdf')
    assert 'REG-A' in doc[0].get_text() and 'REG-B' in doc[0].get_text()


def test_pdf_headline_uses_the_dashboard_alert_count_and_filtered_scope():
    for provinces, programs, expected in [((), (), 21), (("09",), (), 7), ((), ("PAM_SERV",), 6)]:
        v=RiskView();v.select(v.catalog()[-1],provinces,programs);assert v.prepare()
        ctx=v.report_context("Riesgos")
        assert v.kpi_cards()[0]["value"]==ctx["response"]["alert_count"]==expected
        pdf=fitz.open(stream=generate_pdf(ctx),filetype="pdf")
        headline=pdf[0].get_text().split("Kits entregados")[0]
        assert f"Alertas reportadas\n{expected}\n" in headline
        assert "Unidades de atención\ncon alertas" not in headline
        assert sum(x["value"] for x in ctx["response"]["by_province"])==expected
        assert sum(x["value"] for x in ctx["response"]["by_service"])==expected
        dated=sum(x["daily"] for x in ctx["response"]["daily"])
        undated=sum("sin día" in x["date"] for x in ctx["response"]["alerts"])
        assert dated+undated==expected
        text=" ".join(page.get_text() for page in pdf)
        for alert in ctx["response"]["alerts"]:assert alert["code"] in text
