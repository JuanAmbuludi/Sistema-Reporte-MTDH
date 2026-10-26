from io import BytesIO
import json
import pandas as pd
import pymupdf
from openpyxl import load_workbook
from pptx import Presentation
from src import enos
from src.views.enos import EnosView
from src.reports import generate_pdf, generate_pptx, generate_xlsx


def view(provinces=()):
    v=EnosView();v.data=enos.load(v.paths[-1]);v.period=v.catalog()[-1];v.provinces=provinces;v.prepare()
    return v


def test_alert_window_and_source_units():
    v=view();a=v.alerts
    assert len(a)==17 and a.codigo.nunique()==17
    assert pd.to_datetime(a.fecha).ge('2026-09-29').all()
    assert a.estado.value_counts().to_dict()=={'Pendiente':9,'En seguimiento':7,'Resuelto':1}
    assert a.provincia.nunique()==7
    assert a.loc[a.codigo_ua.ne(''),'codigo_ua'].nunique()==10
    assert [k['value'] for k in v.kpi_cards()]==[17,16,10,802]
    assert set(a.columns)=={'codigo','fecha','provincia','canton','estado','prioridad','codigo_ua','unidad','afectados_fuente'}
    assert v.data['control']['alertas_detalle_original']==31


def test_kit_deliveries_bono_scopes_and_merged_province():
    v=view()
    assert len(v.kits)==7
    assert v.kits.groupby('provincia').kits.sum().to_dict()=={'Azuay':197,'Esmeraldas':150,'Guayas':400,'Manabí':55}
    assert v.kits[['provincia','canton']].drop_duplicates().shape[0]==5
    a,b=v.frames['gestionados'],v.frames['articulacion']
    assert a.personas.sum()==113 and round(a.monto.sum(),2)==33200.80
    assert b.personas.sum()==1169 and round(b.monto.sum(),2)==354379.41
    assert b.loc[b.provincia.eq('Los Ríos'),'personas'].item()==109
    assert set(a.evento)|set(b.evento)=={'Inundación'}
    assert v.data['bonos']['planificacion']=={'personas':145523,'nucleos':44098,'monto':13405351.02}
    g=view(['Guayas']);assert len(g.alerts)==7 and g.kits.kits.sum()==400
    assert g.frames['gestionados'].personas.sum()==67
    assert g.digest()!=v.digest()


def test_three_products_keep_counts_and_explicit_limits():
    v=view();ctx=v.report_context('Seguimiento ENOS')
    pdf=pymupdf.open(stream=generate_pdf(ctx),filetype='pdf');assert len(pdf)==2
    text=' '.join(' '.join(p.get_text().split()) for p in pdf)
    for term in ['802','Los Ríos','145.523','29/09','articulación','no identifica pagos exclusivamente atribuibles a ENOS']:
        assert term in text
    ppt=Presentation(BytesIO(generate_pptx(ctx)));assert len(ppt.slides)==4
    wb=load_workbook(BytesIO(generate_xlsx(ctx)),data_only=True)
    assert wb.sheetnames==v.sheets()
    assert 802 in [c.value for row in wb['Resumen'] for c in row]
    assert 'Los Ríos' in [c.value for row in wb['Bonos'] for c in row]
    assert enos.BONO_NOTE in [c.value for row in wb['Ficha técnica'] for c in row]
