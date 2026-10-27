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
    assert len(r.kits)==r.kits.id_kobo.nunique()==80
    assert r.kits_total==10607 and r.kits.familias.sum()==9761
    assert r.kits.provincia.nunique()==21
    assert d['kits_metadatos']['variacion_kits']==591
    assert d['kits_metadatos']['registros_nuevos']==22
    assert d['cortes']['kits']=='2026-10-27T13:35:45'


def test_publication_uses_the_99_unit_territorial_cut():
    d=enos.load(enos.snapshots()[-1]);r=Response(d)
    assert r.closed_units==99
    assert Response(d,provinces=['07']).closed_units==75
    assert Response(d,provinces=['09']).closed_units==17
    assert Response(d,provinces=['24']).closed_units==7
    assert Response(d,programs=['PAM_SERV']).closed_units==0
    assert Response(d,programs=['PCD_SERV']).closed_units==0
    assert Response(d,programs=['PE']).closed_units==0
    assert Response(d,programs=['DII']).closed_units==99
    assert len(r.alerts)==39 and r.units==10


def test_new_provincial_bono_table_reconciles():
    d=enos.load(enos.snapshots()[-1])
    assert sum(r['personas'] for r in d['bonos']['articulacion'])==1171
    assert sum(Decimal(str(r['monto'])) for r in d['bonos']['articulacion'])==Decimal('354987.39')
    assert sum(Decimal(str(r['monto'])) for r in d['bonos']['gestionados'])==Decimal('33200.80')
    assert d['cortes']['bonos']=='2026-10-27'


def test_approved_template_preserves_all_chart_types_and_updated_totals():
    v=RiskView();v.select(v.catalog()[-1]);assert v.prepare();ctx=v.report_context('Riesgos')
    pdf=fitz.open(stream=generate_pdf(ctx),filetype='pdf');assert len(pdf)==4
    text=' '.join(' '.join(p.get_text() for p in pdf).split())
    for label in ['Plan ENOS - Ministerio de Trabajo','Unidades de atención con alerta','Detalle de las unidades de atención con alertas','Acciones del Ministerio','Alertas por provincia','Alertas por servicio','10.607','99','Bono de contingencia: sin desglose temporal disponible']:
        assert label in text
    # Vice's review (27/10): the alerts page opens with the charts, without the history or the breakdown by code.
    page=pdf[1].get_text()
    assert page.index('Alertas por provincia')<page.index('Detalle de las unidades de atención con alertas')
    assert 'Evolución de las alertas' not in text and 'con código UA' not in page and 'reportes sectoriales' not in page
    assert '39 alertas reportadas.' in page
    for a in ctx['response']['alerts']:assert a['code'] in (pdf[1].get_text()+pdf[2].get_text())
    assert 'Reportes sectoriales incorporados' not in text
    for a in ctx['response']['alerts']:assert a['code'] in text
    book=openpyxl.load_workbook(BytesIO(generate_xlsx(ctx)),data_only=True)
    cells=[str(c.value) for s in book for row in s for c in row if c.value is not None]
    for a in ctx['response']['alerts']:assert a['code'] in cells
    for u in ctx['response']['continuity']['detail']:assert (u['unidad'] or '—') in cells


def test_pdf_tables_recover_padding_space_without_dropping_rows():
    from reportlab.pdfgen.canvas import Canvas
    from src.reports.risk_response import _pdf_table
    out=BytesIO();c=Canvas(out)
    bottom=_pdf_table(c,96,['Código'],[['REG-A'],['REG-B']],[180],size=8,padding=5)
    assert bottom>=52
    c.save();doc=fitz.open(stream=out.getvalue(),filetype='pdf')
    assert 'REG-A' in doc[0].get_text() and 'REG-B' in doc[0].get_text()


def test_pdf_headline_uses_the_dashboard_alert_count_and_filtered_scope():
    for provinces, programs, expected in [((), (), 39), (("09",), (), 15), ((), ("PAM_SERV",), 6)]:
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


def test_consolidated_alerts_are_unique_and_preserve_prior_alerts():
    d=enos.load(enos.snapshots()[-1]);r=Response(d)
    new=[a for a in d['alertas'] if a['codigo'].startswith('DII-')]
    assert len(new)==18 and len({a['codigo'] for a in d['alertas']})==39
    assert len({(a['provincia'],a['canton'],a['unidad'].lower(),a['fecha']) for a in new})==18
    assert len(d['control']['filas_duplicadas_consolidada'])==11
    assert sum(a['provincia']=='Guayas' for a in new)==8
    assert sum(a['provincia']=='Santa Elena' for a in new)==7
    assert sum(a['provincia']=='Manabí' for a in new)==2
    assert sum(a['provincia']=='Los Ríos' for a in new)==1
    assert len(r.continuity_detail)==99
    assert sum(x['value'] for x in r.continuity_summary()['by_province'])==99
    assert sum(x['value'] for x in r.continuity_summary()['by_service'])==99
    assert r.articulation.empty and not r.bonus_period_available


def test_reporting_window_filters_all_dated_sources_and_unknown_bonus():
    from copy import deepcopy
    import pandas as pd
    d=enos.load(enos.snapshots()[-1]);r=Response(d)
    assert d['desde']=='2026-09-28'
    assert len(d['kits'])==111 and sum(x['kits'] for x in d['kits'])==13981
    assert len(r.kits)==80 and r.kits_total==10607
    assert r.kits.fecha.min()>='2026-09-28'
    assert r.alerts.fecha.min()>='2026-09-28'
    assert r.managed.empty and r.articulation.empty
    assert not r.bonus_period_available
    assert r.closed_units==99
    copy=deepcopy(d);old=deepcopy(copy['alertas'][-1]);old['fecha']='2026-09-27';old['codigo']='TEST-OUTSIDE';copy['alertas'].append(old)
    assert len(Response(copy).alerts)==39
    v=RiskView();v.select(v.catalog()[-1]);assert v.prepare();ctx=v.report_context('Riesgos')
    assert ctx['kpis'][2]['value'] is None and ctx['kpis'][3]['value'] is None
    assert ctx['response']['articulation_people'] is None
    assert all(a['articulation'] is None for a in ctx['response']['actions'])
    assert sum(a['kits'] for a in ctx['response']['actions'])==10607
