"""Approved three-page Plan ENOS template; current values come exclusively from the response context."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib.utils import ImageReader
from src import theme, ui
from .context import number
from .pdf import M,W,H,C,LOGO,_plate,_next_page,_fit,_kpis
from .risk_response import _pdf_table,_risk_bars,Markup
from .risks import _paragraph

# CNH and CDI in the words of the approved bulletin; the other services arrive with their names (Personas Adultas Mayores…).
SERVICES={'CNH':'Servicio Creciendo con Nuestros Hijos (CNH)','CDI':'Centros de Desarrollo Infantil (CDI)'}
CAPTION={'CNH':'unidades del servicio Creciendo con Nuestros Hijos (CNH)','CDI':'Centros de Desarrollo Infantil (CDI)'}

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
    # Use the dashboard KPI unchanged: alerts and identified UA are different measures.
    cards[0]['short'] = cards[0]['label']
    cards[1].update(short='Kits entregados',note=f"{r['kit_provinces']} provincias")
    cards[2].update(short='Personas · Bono de Contingencia',value=r['articulation_people'],note='En articulación para el pago')
    cards[3].update(short='Monto · Bono de Contingencia',value=r['articulation_amount'],display_value=f"USD {number(r['articulation_amount'],2)}",note=f"En gestión · corte {r['bonus_cut']}")
    top=_kpis(c,{**ctx,'kpis':cards,'share_word':''},top)-8
    caption=' · '.join(f"{number(a['value'])} {CAPTION.get(a['name'],'de '+a['name'])}" for a in r['continuity']['by_service'])
    from .risks import _paragraph_height
    band=max(34,22+_paragraph_height(caption,full-82,7.2))
    c.setFillColor(C(theme.LILA_50));c.roundRect(M,top-band,full,band,6,fill=1,stroke=0)
    c.setFillColor(C(theme.MORADO_900));c.setFont('Text-Bold',23);c.drawString(M+12,top-band/2-8,number(r['continuity']['closed']))
    c.setFont('Text-Bold',9);c.drawString(M+70,top-13,'Unidades de atención cerradas / suspendidas')
    _paragraph(c,caption,M+70,top-17,full-82,size=7.2,color=C(theme.MORADO))
    top-=band+21
    lines=max(len(r['continuity']['by_province']),len(r['continuity']['by_service']))
    step=21  # a name over its bar, as in the approved bulletin
    for i,(key,title) in enumerate([('by_province','Unidades de atención suspendidas por provincia'),('by_service','Unidades de atención suspendidas por servicio')]):
        x=M+i*(half+22);heading(c,title,x,top,half)
        rows=[{**a,'name':SERVICES.get(a['name'],a['name'])} for a in r['continuity'][key]]
        _risk_bars(c,rows,x,top-23,half,step)
    top-=23+lines*step+10
    heading(c,'Detalle de las unidades de atención suspendidas',M,top,full)
    rows=[]
    for g in r['continuity']['groups']:
        name_list=g['names'].split('; ') if g['names'] else []
        # The approved summary retains its dimensions. The full nominal directory is in the data export.
        first=name_list[0] if name_list else '—'
        first=first if len(first)<=46 else first[:43]+'…'
        shown=first+(f"; y {len(name_list)-1} " + ("unidad adicional" if len(name_list)==2 else "unidades adicionales") if len(name_list)>1 else '')
        rows.append([Markup(f"<b>{escape(g['province'])}</b>"+(f"<br/>{escape(g['canton'])}" if g['canton'] else '')),g['service'],number(g['units']),shown or '—'])
    rows.append(['Total','',number(r['continuity']['closed']),''])
    top=_pdf_table(c,top-18,['Provincia / cantón','Servicio','UA','Unidades identificadas'],rows,[100,104,28,full-232],size=7.1,padding=1.2,align=['L','L','R','L'],total=True)-12
    top=_paragraph(c,r['continuity']['note']+' Listado nominal completo en el dashboard y en Excel.',M,top,full,size=7)-6
    assert top>=62,top
    _next_page(c,ctx,1,pages)

    chunks=[r['alerts'][i:i+24] for i in range(0,len(r['alerts']),24)] or [[]]
    for index,part in enumerate(chunks):
        last=index==len(chunks)-1
        top=header(c,ctx,'Detalle de las unidades de atención con alerta')-16
        c.setFillColor(C(theme.ORO_100));c.roundRect(M,top-30,full,30,4,fill=1,stroke=0)
        c.setFillColor(C(theme.ORO));c.rect(M,top-30,3,30,fill=1,stroke=0)
        _paragraph(c,r['count_note'],M+12,top-10,full-24,size=8.5);top-=40
        # Every alert, with or without a UA code; the alerts by province and service and their evolution follow on the same
        # page, as in the approved bulletin: the table takes the largest type that leaves them room.
        from .risk_response import _alert_cells
        rows=_alert_cells(part)
        lines=max(len(r['by_province']),len(r['by_service']))
        step=21  # a name over its bar, as in the approved bulletin
        unknown=sum(1 for a in r['alerts'] if 'sin día' in a['date'])
        below=20+24+lines*step+4+80+(14 if unknown else 0)
        headers=['Alerta / registro','Unidad de atención y servicio','Territorio','Afectación al servicio','Estado']
        cells=[[a['identity'],a['unit_full'],a['place_full'],a['impact'],a['state']] for a in rows]
        widths=[80,160,70,full-392,82]
        top=_fitted_table(c,top,headers,cells,widths,room=top-62-(below if last else 0))-20
        if last:
            for i,(key,title) in enumerate([('by_province','Alertas por provincia'),('by_service','Alertas por servicio')]):
                x=M+i*(half+22);heading(c,title,x,top,half)
                _risk_bars(c,r[key],x,top-22,half,step)
            top-=24+lines*step+4
            top=evolution(c,r['daily'],top,full)
            if unknown:
                top=_paragraph(c,f"La evolución incluye {sum(d['daily'] for d in r['daily'])} registros con fecha exacta; {unknown} reportes gerontológicos de agosto no tienen día especificado. Los {r['alert_count']} registros constan en la tabla de alertas.",M,top-8,full,size=6.8)
        assert top>=62,top
        _next_page(c,ctx,2+index,pages)

    top=header(c,ctx,'Acciones del Ministerio')-24
    heading(c,'Respuesta por provincia',M,top,full);top-=28
    rows=[[a['name'],number(a['kits']) if a['kits'] else '—',number(a['articulation']) if a['articulation'] else '—',number(a['articulation_amount'],2) if a['articulation_amount'] else '—'] for a in r['actions']]
    rows.append(['Total',number(r['kits_total']),number(r['articulation_people']),number(r['articulation_amount'],2)])
    top=_pdf_table(c,top,['Provincia','Kits entregados',Markup('Personas<br/><font size="6.6">Bono de Contingencia</font>'),Markup('Monto (USD)<br/><font size="6.6">Bono de Contingencia</font>')],rows,[full*.44,full*.17,full*.18,full*.21],size=8.2,padding=2.6,align=['L','L','L','L'],total=True)-16
    top=_paragraph(c,f"Kits: corte {r['kits_cut_full']}. Bono de contingencia: en articulación para el pago, corte {r['bonus_cut']}.",M,top,full,size=7)
    assert top>=62,top
    assert pages==2+len(chunks)


def _fitted_table(c,top,headers,rows,widths,room):
    """The alerts table in the largest type (and padding) that keeps it within ``room`` points."""
    from reportlab.pdfgen.canvas import Canvas
    for size,padding in ((6.9,1.2),(6.6,1),(6.3,.8),(6.0,.6),(5.8,.4)):
        if 3000-_pdf_table(Canvas(BytesIO()),3000,headers,rows,widths,size=size,padding=padding)<=room:
            break
    return _pdf_table(c,top,headers,rows,widths,size=size,padding=padding)
