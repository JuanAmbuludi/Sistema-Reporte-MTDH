"""Approved three-page Plan ENOS template; current values come exclusively from the response context."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib.utils import ImageReader
from src import theme, ui
from .context import number
from .pdf import M,W,H,C,LOGO,_plate,_next_page,_fit,_kpis
from .risk_response import _pdf_table,_risk_bars,Markup
from .risks import _paragraph

SERVICES={'CNH':'CNH','CDI':'CDI','PAM':'Personas adultas mayores','PCD':'Personas con discapacidad','PE':'Protección especial','AF':'Acompañamiento familiar'}

def heading(c,text,x,y,width):
    c.setFillColor(C(theme.MORADO_900));c.setFont('Text-Bold',_fit(text,'Text-Bold',11,width,8.8));c.drawString(x,y,text)
    c.setStrokeColor(C(theme.LILA_200));c.setLineWidth(.8);c.line(x,y-6,x+width,y-6)

def header(c,ctx,title=None):
    from .charts import emblem_png
    cover=title is None;bottom=_plate(c,H,132 if cover else 74)
    logo=ImageReader(str(LOGO));iw,ih=logo.getSize();height=26
    x=M-4 if cover else W-M-height*iw/ih
    c.drawImage(logo,x,H-44,width=height*iw/ih,height=height,mask='auto')
    if cover:
        picture=emblem_png(set(ctx['selected_codes']));c.drawImage(ImageReader(BytesIO(picture)),W-M-150,bottom+6,width=150,height=124,mask='auto')
        c.setFillColor(C('#FFE7A3'));c.setFont('Text-Semi',9);c.drawString(M,H-61,f"Resumen ejecutivo · Del 29/08/2026 al {ctx['response']['cut']}")
        c.setFillColor(C('#FFFFFF'));c.setFont('Text-Semi',19)
        c.drawString(M,H-88,'Plan ENOS - Ministerio de Trabajo');c.drawString(M,H-110,'y Desarrollo Humano')
        c.setFont('Text',6.7);c.setFillColor(C('#E4DBF3'));c.drawString(M,H-125,f"Actualización: {ctx['update'].get('updated',ctx['generated_label'])}")
    else:
        c.setFillColor(C('#FFFFFF'));c.setFont('Text-Semi',_fit(title,'Text-Semi',20,W-2*M-130,16));c.drawString(M,H-48,title)
    return bottom-4

def evolution(c,rows,top,width):
    heading(c,'Evolución de las alertas',M,top,width)
    active=[r for r in rows if r['daily']];peak=max([r['daily'] for r in active] or [1]);slot=width/max(len(active),1);base=top-54
    for i,r in enumerate(active):
        center=M+(i+.5)*slot;h=24*r['daily']/peak
        c.setStrokeColor(C(theme.LILA_200));c.line(M+i*slot+10,base,M+(i+1)*slot-10,base)
        c.setFillColor(C(theme.ORO));c.roundRect(center-18,base,36,h,2,fill=1,stroke=0)
        c.setFillColor(C(theme.MORADO_900));c.setFont('Text-Bold',11);c.drawCentredString(center,base+h+5,number(r['daily']))
        day,month,_=r['date'].split('/');label=f"{int(day)} {ui._MONTHS_SHORT[int(month)-1]}";c.setFont('Text-Bold',8);c.drawCentredString(center,base-11,label)
        c.setFillColor(C(theme.MORADO));c.setFont('Text',7.4);c.drawCentredString(center,base-23,f"Acumulado: {r['total']}")
    return base-23

def render(c,ctx,pages):
    r=ctx['response'];full=W-2*M;half=(full-22)/2
    top=header(c,ctx)-16
    cards=[dict(k) for k in ctx['kpis'][:4]]
    cards[0].update(label='Unidades de atención con alertas',short='Unidades de atención con alertas',value=r['units'],note=f"{r['alert_count']} alertas reportadas")
    cards[1].update(short='Kits entregados',note=f"{r['kit_provinces']} provincias")
    cards[2].update(short='Personas · Bono de Contingencia',value=r['articulation_people'],note='En articulación para el pago')
    cards[3].update(short='Monto · Bono de Contingencia',value=r['articulation_amount'],display_value=f"USD {number(r['articulation_amount'],2)}",note=f"En gestión · corte {r['bonus_cut']}")
    top=_kpis(c,{**ctx,'kpis':cards,'share_word':''},top)-8
    c.setFillColor(C(theme.LILA_50));c.roundRect(M,top-34,full,34,6,fill=1,stroke=0)
    c.setFillColor(C(theme.MORADO_900));c.setFont('Text-Bold',23);c.drawString(M+12,top-25,number(r['continuity']['closed']))
    c.setFont('Text-Bold',9);c.drawString(M+70,top-13,'Unidades de atención cerradas / suspendidas')
    c.setFont('Text',7);c.drawString(M+70,top-25,r['continuity']['caption'])
    top-=55
    for i,(key,title) in enumerate([('by_province','Unidades de atención suspendidas por provincia'),('by_service','Unidades de atención suspendidas por servicio')]):
        x=M+i*(half+22);heading(c,title,x,top,half)
        rows=[{**a,'name':SERVICES.get(a['name'],a['name'])} for a in r['continuity'][key]]
        _risk_bars(c,rows,x,top-23,half,21)
    top-=23+max(len(r['continuity']['by_province']),len(r['continuity']['by_service']))*21+14
    heading(c,'Detalle de las unidades de atención suspendidas',M,top,full)
    rows=[]
    for g in r['continuity']['groups']:
        name_list=g['names'].split('; ') if g['names'] else []
        # The approved summary retains its dimensions. The full nominal directory is in the data export.
        first=name_list[0] if name_list else '—'
        first=first if len(first)<=56 else first[:53]+'…'
        shown=first+(f"; y {len(name_list)-1} " + ("unidad adicional" if len(name_list)==2 else "unidades adicionales") if len(name_list)>1 else '')
        rows.append([f"{g['province']}\n{g['canton']}",g['service'],number(g['units']),shown or '—'])
    rows.append(['Total','',number(r['continuity']['closed']),''])
    top=_pdf_table(c,top-18,['Provincia / cantón','Servicio','UA','Unidades identificadas'],rows,[114,45,30,full-189],size=7.1,padding=1.2,align=['L','L','R','L'],total=True)-12
    top=_paragraph(c,r['continuity']['note']+' Listado nominal completo en el dashboard y en Excel.',M,top,full,size=7)-6
    assert top>=62,top
    _next_page(c,ctx,1,3)

    top=header(c,ctx,'Detalle de las unidades de atención con alerta')-16
    c.setFillColor(C(theme.ORO_100));c.roundRect(M,top-36,full,36,4,fill=1,stroke=0)
    c.setFillColor(C(theme.ORO));c.rect(M,top-36,3,36,fill=1,stroke=0)
    _paragraph(c,r['count_note'],M+12,top-12,full-24,size=8.5);top-=50
    # This table is explicitly about identified UAs, as in the approved template.
    from .risk_response import _alert_cells
    coded=[a for a in r['alerts'] if a['ua']];rows=_alert_cells(coded)
    top=_pdf_table(c,top,['Alerta / registro','Unidad de atención y servicio','Territorio','Afectación al servicio','Estado'],[[a['identity'],a['unit_full'],a['place_full'],a['impact'],a['state']] for a in rows],[84,150,65,full-370,71],size=7.0,padding=2)-18
    for i,(key,title) in enumerate([('by_province','Alertas por provincia'),('by_service','Alertas por servicio')]):
        x=M+i*(half+22);heading(c,title,x,top,half)
        parts=[{**a,'name':a['name'].replace('Creciendo con Nuestros Hijos (CNH)','CNH').replace('Santo Domingo de los Tsáchilas','Santo Domingo de los Tsáchilas')} for a in r[key]]
        _risk_bars(c,parts,x,top-22,half,20)
    top-=24+max(len(r['by_province']),len(r['by_service']))*20+10
    top=evolution(c,r['daily'],top,full)
    unknown=sum(1 for a in r['alerts'] if 'sin día' in a['date'])
    if unknown:
        top=_paragraph(c,f"La evolución incluye {sum(d['daily'] for d in r['daily'])} registros con fecha exacta; {unknown} reportes gerontológicos de agosto no tienen día especificado. Los 11 reportes sectoriales se detallan en el dashboard y Excel.",M,top-12,full,size=6.8)
    assert top>=62,top
    _next_page(c,ctx,2,3)

    top=header(c,ctx,'Acciones del Ministerio')-42
    heading(c,'Respuesta por provincia',M,top,full);top-=40
    rows=[[a['name'],number(a['kits']) if a['kits'] else '—',number(a['articulation']) if a['articulation'] else '—',number(a['articulation_amount'],2) if a['articulation_amount'] else '—'] for a in r['actions']]
    rows.append(['Total',number(r['kits_total']),number(r['articulation_people']),number(r['articulation_amount'],2)])
    top=_pdf_table(c,top,['Provincia','Kits entregados',Markup('Personas<br/><font size="6.6">Bono de Contingencia</font>'),Markup('Monto (USD)<br/><font size="6.6">Bono de Contingencia</font>')],rows,[full*.44,full*.17,full*.18,full*.21],size=8,padding=3,align=['L','R','R','R'],total=True)-16
    _paragraph(c,f"Kits: corte {r['kits_cut_full']}. Bono de contingencia: en articulación para el pago, corte {r['bonus_cut']}.",M,top,full,size=7)
    sectorial=[a for a in r['alerts'] if not a['ua']]
    if sectorial:
        top-=27
        heading(c,'Reportes sectoriales incorporados',M,top,full)
        extra=[[a['code'],a['province'],a['service'],a['date'].replace(' (sin día)','')] for a in sectorial]
        _pdf_table(c,top-16,['Reporte','Provincia','Servicio','Fecha del suceso'],extra,[85,145,175,full-405],size=7,padding=1)
    assert pages==3
