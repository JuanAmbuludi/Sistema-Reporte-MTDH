"""Reconciliación del corte de 27/10, incluyendo filtros y conservación del día cerrado."""
import hashlib
import json
from pathlib import Path
import pymupdf
from src import enos
from src.views.riesgos import RiskView
from src.reports import generate_pdf

ROOT=Path(__file__).resolve().parents[1]

def view(**selection):
    v=RiskView();v.select(v.catalog()[-1],**selection);assert v.prepare();return v

def test_totals_and_source_identity():
    v=view();r=v.response
    assert [k['value'] for k in v.kpi_cards()]==[44,11207,1171,354987.39,124,1]
    assert r.alerts.codigo.nunique()==44
    assert r.alerts.codigo.str.startswith('ALT-').sum()==15
    assert r.data['control']['alertas_detalle_recibido']==5
    assert r.data['kits_metadatos']['registros']==117
    assert r.data['kits_metadatos']['kits']==14581
    assert len({k['id_kobo'] for k in r.data['kits']})==117
    assert r.continuity.groupby('provincia').unidades.sum().to_dict()=={'El Oro':119,'Guayas':5}
    assert len(r.continuity_detail)==124

def test_brigade_territory_date_and_history():
    assert view(provinces=('09',)).kpi_cards()[-1]['value']==1
    assert view(provinces=('07',)).kpi_cards()[-1]['value']==0
    assert view(since='2026-10-14').kpi_cards()[-1]['value']==0
    assert view().response.brigadas[0]['canton']=='Balao'
    for day,files in enos.ledger()['cerrados'].items():
        for name,digest in files.items(): assert enos.fingerprint(enos.FOLDER/name)==digest
    history=view(until='2026-10-26')
    assert [k['value'] for k in history.kpi_cards()]==[10,13390,1171,354987.39,99]

def test_pdf_uses_dashboard_context_and_contains_every_alert():
    v=view();ctx=v.report_context('Plan ENOS')
    pdf=pymupdf.open(stream=generate_pdf(ctx),filetype='pdf')
    text=' '.join(p.get_text() for p in pdf)
    assert len(pdf)==ctx['pdf_pages']
    assert 'Familias' in text and 'Habilitadas al pago' in text
    assert 'Brigadas de emergencia' in text and 'Balao' in text and '11.207' in text and '124' in text
    assert all(a['codigo'] in text for a in v.response.data['alertas'])
    for page in pdf:
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    x0,y0,x1,y1=span['bbox']
                    assert x0>=0 and y0>=0 and x1<=page.rect.width+1 and y1<=page.rect.height+1
