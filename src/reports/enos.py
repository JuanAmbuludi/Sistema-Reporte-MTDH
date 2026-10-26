"""Operational risk products built with the existing institutional components."""
from src import enos, theme
import pandas as pd
from .areas import _base, _ranked, kpis_from_cards
from .context import number


def build_context(view,title):
    ctx=_base(view,'seguimiento_enos',title)
    ctx.update(period_label=f"{pd.Timestamp(view.data['desde']):%d/%m} al {pd.Timestamp(view.data['corte']):%d/%m/%Y}",source='Fuente: Subsecretaría Territorial · MTDH',
               kpis=kpis_from_cards(view.kpi_cards()), alerts=view.alerts.to_dict('records'), kits=view.kits.to_dict('records'),
               provinces=enos.summary(view.alerts,'provincia'), states=enos.summary(view.alerts,'estado'),
               days=enos.summary(view.alerts,'fecha'), plan=view.data['bonos']['planificacion'], scope=view.scope_items(),
               alert_note=enos.ALERT_NOTE,kit_note=enos.KIT_NOTE,bono_note=enos.BONO_NOTE,quality_note=enos.QUALITY_NOTE,
               reference=enos.REFERENCE, sources=view.data['fuentes'],
               bonos=[{**r,'stage':label} for key,label in [('gestionados','Gestionado'),('articulacion','En articulación')]
                       for r in view.frames[key].to_dict('records')],
               insights=[{'icon':'storm','text':f"{len(view.alerts)} alertas con código UA desde el 14/09 en {view.alerts.provincia.nunique()} provincias."},
                         {'icon':'life-buoy','text':f"{number(view.kits.kits.sum())} kits entregados en provincias priorizadas según el corte Kobo del 26/10, 22:26."}])
    return ctx


def plan_cards(ctx):
    p=ctx['plan']
    return kpis_from_cards([{'label':'Personas potenciales','value':p['personas'],'icon':'users','note':'Proyección nacional'},
                           {'label':'Núcleos familiares','value':p['nucleos'],'icon':'users','note':'Proyección nacional'},
                           {'label':'Inversión estimada','value':p['monto']/1e6,'prefix':'USD','suffix':'millones','icon':'banknote',
                            'note':'Planificación, no ejecución'}])


KIT_COLUMNS=[('Fecha','fecha',68,'text'),('Provincia','provincia',110,'text'),('Cantón','canton',None,'text'),('Kits','kits',55,'int')]


def _kit_provinces(ctx, limit=None):
    frame = pd.DataFrame(ctx['kits'])
    if frame.empty: return []
    rows = frame.groupby('provincia', as_index=False).kits.sum().sort_values('kits', ascending=False).to_dict('records')
    if limit and len(rows)>limit:
        rows = rows[:limit] + [{'provincia':'Otras provincias','kits':sum(r['kits'] for r in rows[limit:])}]
    return rows


def render_pdf(c,ctx,pages):
    from xml.sax.saxutils import escape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from .charts import emblem_png
    from .pdf import H,W,M,INK,_band,_kpis,_heading,_bars,_table,_next_page,_slim_band
    from .pdf_areas import _two_findings
    width=W-2*M
    def paragraph(text,y,size=8.5):
        p=Paragraph(escape(text),ParagraphStyle('enos',fontName='Text',fontSize=size,leading=size*1.4,textColor=INK))
        _,h=p.wrap(width,1000);p.drawOn(c,M,y-h);return y-h-10
    y=_kpis(c,ctx,_band(c,ctx,H,emblem_png())-12)
    _heading(c,'Alertas de servicios MTDH por provincia',M,y-12,width)
    y-=37;_bars(c,_ranked(ctx['provinces'],'value'),M,y,width,row_h=26);y-=26*len(ctx['provinces'])+16
    _heading(c,'Estado de las alertas',M,y,width)
    y=_table(c,M,y-16,width,[('Estado','name',None,'text'),('Alertas','value',100,'int')],ctx['states'],row_h=20)
    y=_two_findings(c,ctx['insights'],y-20,rows=1)
    y=paragraph(ctx['alert_note'],y-10)
    paragraph(ctx['quality_note'],y,8)
    _next_page(c,ctx,1,pages)
    y=_slim_band(c,ctx,'Kits y bono de contingencia',ctx['territory_label'])
    _heading(c,'Kits entregados en provincias priorizadas',M,y-15,width)
    y=_table(c,M,y-31,width,[('Provincia','provincia',None,'text'),('Kits','kits',90,'int')],_kit_provinces(ctx,5),row_h=16)
    y=paragraph(ctx['kit_note'],y-12,8)
    _heading(c,'Planificación nacional El Niño 2026–2027',M,y-6,width)
    y=_kpis(c,{**ctx,'kpis':plan_cards(ctx)},y-22)
    _heading(c,'Bono: referencia por inundaciones',M,y-12,width)
    # Currency stays in full USD with two decimals, using the shared table text cell.
    rows=[{**r,'money_text':f"{number(r['monto'],2)}"} for r in ctx['bonos']]
    cols=[('Estado','stage',95,'text'),('Provincia','provincia',None,'text'),('Personas','personas',60,'int'),('Monto (USD)','money_text',95,'text')]
    y=_table(c,M,y-28,width,cols,rows,row_h=15)
    y=paragraph(ctx['bono_note'],y-12,8)
    paragraph('Fuentes: análisis territorial de alertas 26/10; Kobo de kits 26/10, 22:26; ayuda memoria del bono 23/10. '+ctx['reference'],y,7.5)


def render_pptx(prs,ctx):
    from .charts import emblem_png
    from .pptx import _cover,_header,_footer,_text,_bar_chart,_box
    from .pptx_areas import _table
    _cover(prs,ctx,emblem_png(),4,share_word='')
    def slide(title,subtitle):
        s=prs.slides.add_slide(prs.slide_layouts[6]);_header(s,title,subtitle);_footer(s,ctx,len(prs.slides),4)
        s.notes_slide.notes_text_frame.text='\n'.join(f'{k}: {v}' for k,v in ctx['scope'])+'\n'+ctx['alert_note']+'\n'+ctx['bono_note']
        return s
    s=slide('Afectaciones a servicios MTDH',ctx['period_label']+' · '+ctx['territory_label'])
    rows=ctx['provinces'][::-1]
    if rows:_bar_chart(s,[r['name'] for r in rows],[r['value'] for r in rows],'Alertas',x=.5,y=1.4,w=7.3,h=4.55)
    _table(s,8.1,1.7,4.6,[('Estado','name',None,'text'),('Alertas','value',1.1,'int')],ctx['states'],row_h=.5)
    _text(s,8.1,4,4.6,1.6,'Alertas con código UA. El seguimiento utiliza la fecha de registro de cada alerta.',size=15)
    _text(s,.6,6.25,12,.5,'Se utiliza la fecha de registro desde el 14/09. La atribución causal a ENOS no está certificada en la base.',size=12,color=theme.PIZARRA)
    s=slide('Kits en provincias priorizadas','Kobo: corte 26/10/2026, 22:26 · '+ctx['territory_label'])
    _text(s,.65,1.4,12,.6,f"{number(sum(r['kits'] for r in ctx['kits']))} kits documentados",size=28,bold=True,color=theme.MORADO)
    for i in range(0,len(_kit_provinces(ctx)),10):
        _table(s,.65+(i//10)*6.1,2.2,5.8,[('Provincia','provincia',None,'text'),('Kits','kits',1.2,'int')],_kit_provinces(ctx)[i:i+10],row_h=.32,size=10)
    _text(s,.65,6.15,12,.6,ctx['kit_note'],size=13,color=theme.PIZARRA)
    s=slide('Bono de contingencia','Planificación ENOS y referencia por inundaciones · corte 23/10/2026')
    p=ctx['plan']
    for i,(label,value) in enumerate([('Personas potenciales',number(p['personas'])),('Núcleos familiares',number(p['nucleos'])),('Inversión estimada',f"USD {number(p['monto']/1e6,2)} M")]):
        x=.6+4.2*i;_box(s,x,1.35,3.95,1.05,theme.LILA_50);_text(s,x+.18,1.48,3.6,.3,label,size=13)
        _text(s,x+.18,1.85,3.6,.4,value,size=24,bold=True,color=theme.MORADO)
    _text(s,.65,2.52,12,.3,'Proyección nacional 2026–2027. No representa ejecución ni cambia con el filtro provincial.',size=12,color=theme.PIZARRA)
    rows=[{**r,'amount':f"USD {number(r['monto'],2)}"} for r in ctx['bonos']]
    _table(s,.65,3,12,[('Estado','stage',2.3,'text'),('Provincia','provincia',None,'text'),('Personas','personas',1.3,'int'),('Monto','amount',2.3,'text')],rows,row_h=.28,header_h=.4,size=10.5)
    _text(s,.65,5.88,12,.88,ctx['bono_note'],size=11.5,color=theme.PIZARRA)


def render_workbook(book):
    from .excel_areas import _summary,_finish_summary,_sheet,_block
    ctx=book.ctx
    ws,row=_summary(book,'')
    row=book.heading(ws,row,'Alertas por provincia',last=12)
    first,end,row=book.table(ws,row,[('Provincia','name','text',1,8),('Alertas','value','int',9,4)],ctx['provinces'],total={'value':len(ctx['alerts'])},height=23)
    if ctx['provinces']:
        ws.insert_chart(row+1,1,book.bar_chart('Resumen',first,end,1,9,'Alertas por provincia',[theme.MORADO],width=800,height=290));row+=18
    _finish_summary(book,ws,row+1,ctx['insights'])
    ws,row=_sheet(book,'Alertas',theme.MORADO,'Afectaciones a servicios MTDH',[2.4,23,16,25,30,21,18,48,30,65,24,2.4])
    columns=[('Alerta','codigo','text'),('Fecha de registro','fecha','text'),('Provincia','provincia','text'),('Cantón','canton','text'),
             ('Estado','estado','text'),('Código UA','codigo_ua','code'),('Unidad de atención','unidad','text'),('Servicio','servicio','text'),('Afectación al servicio','afectacion_servicio','text'),('Afectados (campo fuente)','afectados_fuente','int')]
    first,end,row=_block(book,ws,row+1,'Detalle desde el 14/09',columns,ctx['alerts'],last=10,height=45,autofilter=True)
    ws.freeze_panes(first,3);book.note(ws,row+1,ctx['alert_note'],last=10,height=70)
    ws,row=_sheet(book,'Kits',theme.VIOLETA_500,'Kits entregados en provincias priorizadas',[2.4,18,28,32,18,2.4])
    _f,_e,row=_block(book,ws,row+1,'Entregas del corte Kobo',[(h,k,'int' if k=='kits' else 'text') for h,k,_w,_t in KIT_COLUMNS],
                     ctx['kits'],total={'kits':sum(r['kits'] for r in ctx['kits'])},last=4,height=23,autofilter=True)
    book.note(ws,row+1,ctx['kit_note'],last=4,height=45)
    ws,row=_sheet(book,'Bonos',theme.FUCSIA_700,'Bono de contingencia',[2.4,26,30,18,24,2.4])
    row=book.heading(ws,row+1,'Planificación nacional ENOS 2026–2027',last=4)
    plan=[{'name':'Personas potenciales','count':ctx['plan']['personas']},{'name':'Núcleos familiares','count':ctx['plan']['nucleos']},
          {'name':'Inversión estimada','amount':ctx['plan']['monto']}]
    _f,_e,row=book.table(ws,row,[('Indicador','name','text',1,2),('Cantidad','count','int',3,1),('Monto (USD)','amount','usd',4,1)],plan,height=25)
    row=book.note(ws,row+1,'Planificación nacional, no ejecución. El filtro territorial se aplica a las tablas de inundaciones.',last=4,height=40)
    for stage in ('Gestionado','En articulación'):
        records=[r for r in ctx['bonos'] if r['stage']==stage]
        _f,_e,row=_block(book,ws,row+1,stage+' por inundaciones',[('Provincia','provincia','text'),('Evento','evento','text'),('Personas','personas','int'),('Monto (USD)','monto','usd')],
                         records,last=4,total={'personas':sum(r['personas'] for r in records),'monto':sum(r['monto'] for r in records)},height=24)
    book.note(ws,row+1,ctx['bono_note'],last=4,height=100)
    book.facts_sheet([('Periodo de alertas',ctx['period_label']),('Territorio',ctx['territory_label']),('Kits','31/08–26/10/2026; corte Kobo 26/10, 22:26'),
                      ('Bonos','Corte 23/10/2026; pagos gestionados desde el 29/08')],
                     [('Alertas',ctx['alert_note']),('Kits',ctx['kit_note']),('Bonos',ctx['bono_note']),('Control de calidad',ctx['quality_note'])],
                     [('Resumen','Cifras clave'),('Alertas','Detalle sin domicilios ni nombres personales'),('Kits','Entregas documentadas'),('Bonos','Planificación y referencia de inundaciones')],
                     sources=[('Fuente '+str(i+1),s['nombre'],'') for i,s in enumerate(ctx['sources'])])
    ws=book.wb.get_worksheet_by_name('Ficha técnica')
    strings={idx:text for text,idx in book.wb.str_table.string_table.items()}
    for row,cells in ws.table.items():
        c=cells.get(2)
        if c is not None and hasattr(c,'string'):
            text=strings.get(c.string,'')
            if len(text)>95:ws.set_row(row,max(40,15*((len(text)+84)//85)))
