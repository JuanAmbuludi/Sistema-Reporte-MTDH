from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src import charts, enos, geo, names, theme, ui
from src.views.common import compact, fingerprint, show_chart
from src.views.riesgos import RiskView


class EnosView:
    id = 'seguimiento_enos'
    file_id = 'riesgos_seguimiento'
    label = 'Seguimiento y respuesta'
    summary_pages = 2
    empty_message = 'No hay información de seguimiento para este corte.'

    def __init__(self):
        self.paths = enos.snapshots()

    def catalog(self):
        from src.corte import MONTHS
        return [{'id': pid, 'year': int(pid[:4]), 'month': int(pid[5:]),
                 'label': f'{MONTHS[int(pid[5:])-1].capitalize()} {pid[:4]}'}
                for pid in sorted({p.stem[-10:-3] for p in self.paths})]

    def select(self, period, provinces=()):
        """The latest cut of the month without widgets (the summary of every section)."""
        self.period = period
        paths = [p for p in self.paths if p.stem[-10:].startswith(period['id'])]
        self.data = enos.load(paths[-1])
        self.provinces = list(provinces)

    def controls(self, period):
        self.period = period
        dates = [p.stem[-10:] for p in self.paths if p.stem[-10:].startswith(period['id'])]
        if st.session_state.get('enos_cut') not in dates:
            st.session_state['enos_cut'] = dates[-1]
        cut = st.selectbox('Corte del seguimiento', dates, key='enos_cut', format_func=lambda x: pd.Timestamp(x).strftime('%d/%m/%Y'))
        self.data = enos.load(next(p for p in self.paths if p.stem.endswith(cut)))
        options = sorted({r['provincia'] for key in ['alertas','kits'] for r in self.data[key]} |
                         {r['provincia'] for key in ['gestionados','articulacion'] for r in self.data['bonos'][key]})
        if 'enos_provinces' in st.session_state:
            st.session_state['enos_provinces'] = [p for p in st.session_state['enos_provinces'] if p in options]
        self.provinces = st.multiselect('Territorio del seguimiento', options, placeholder='Todo el país', key='enos_provinces')

    def prepare(self):
        self.frames = enos.frames(self.data, self.provinces)
        self.alerts, self.kits = self.frames['alertas'], self.frames['kits']
        self.territory_label = ', '.join(self.provinces) if self.provinces else 'Nacional'
        self.programs_label = 'Alertas, kits y bono de contingencia'
        return True

    def hero_copy(self):
        return ('Seguimiento desde el 14 de septiembre', 'Riesgos y respuesta',
                'Afectaciones a servicios MTDH, entregas de kits y estado de la información sobre el bono de contingencia ante El Niño.')

    def update_stamp(self):
        from datetime import datetime
        from src.corte import ECUADOR, long_date
        cut = pd.Timestamp(self.data['corte']).strftime('%d/%m/%Y')
        kits_cut = pd.Timestamp(self.data['cortes']['kits']).strftime('%d/%m/%Y')
        bonos_cut = pd.Timestamp(self.data['cortes']['bonos']).strftime('%d/%m/%Y')
        return {'cut': f'Alertas: {cut} · Kits: {kits_cut} · Bonos: {bonos_cut}',
                'updated': long_date(datetime.fromisoformat(self.data['generado_utc']).astimezone(ECUADOR)),
                'frequency': 'Actualización según los cortes recibidos', 'short': f'Alertas al {cut}', 'line': f'Alertas al {cut}'}

    def kpi_cards(self):
        return [{'label': 'Alertas de servicios MTDH', 'value': len(self.alerts), 'icon': 'storm', 'note': 'Desde el 14/09/2026'},
                {'label': 'Alertas abiertas', 'value': int(self.alerts.estado.ne('Resuelto').sum()), 'icon': 'clock',
                 'note': 'Pendientes o en seguimiento'},
                {'label': 'UA afectadas con código', 'value': self.alerts.loc[self.alerts.codigo_ua.ne(''),'codigo_ua'].nunique(),
                 'icon': 'building', 'note': 'Solo códigos registrados en la fuente'},
                {'label': 'Kits entregados', 'value': int(self.kits.kits.sum()), 'icon': 'life-buoy', 'note': 'Provincias priorizadas · 24–25/10'}]

    def hero_visual(self):
        inventory = pd.read_parquet(ROOT/'data/processed/riesgos_ua.parquet')
        codes = {names.place(p): str(c) for p,c in zip(inventory.provincia, inventory.provincia_codigo)}
        values = {codes[r['name']]:r['value'] for r in enos.summary(self.alerts,'provincia') if r['name'] in codes}
        ui.hero_map(geo.svg_map(ui.map_fills(values)), 'Alertas de servicios MTDH por provincia')

    geoportal = staticmethod(RiskView.geoportal)

    @staticmethod
    def _bars(rows, unit, key, color=theme.SERIE_BONOS):
        labels = [r['name'] for r in rows][::-1]
        values = [r['value'] for r in rows][::-1]
        singular = {'alertas': 'alerta', 'kits': 'kit'}.get(unit, unit)
        fig = go.Figure(go.Bar(x=values, y=labels, orientation='h', marker=dict(color=color, cornerradius=4),
                               text=[f"{ui.number(v)} {singular if v == 1 else unit}" for v in values], textposition='outside',
                               cliponaxis=False, textfont=dict(size=12, color=theme.TINTA),
                               hovertemplate='<b>%{y}</b><br>%{x:,.0f} ' + unit + '<extra></extra>'))
        charts.base(fig, max(200, len(rows) * 46 + 30), dict(l=8, r=90, t=8, b=8))
        fig.update_xaxes(showticklabels=False, showgrid=False, rangemode='tozero')
        fig.update_yaxes(tickfont=dict(size=12.5))
        fig.update_layout(bargap=0.42, showlegend=False)
        show_chart(fig, key)

    @staticmethod
    def _table(frame, labels, key):
        wide = len(labels) > 5
        ui.data_table(frame, {k:(v,'money' if k=='monto' else 'int' if pd.api.types.is_numeric_dtype(frame[k]) else 'text',
                                 (180 if wide else None) if not pd.api.types.is_numeric_dtype(frame[k]) else None) for k,v in labels.items()},
                      height=320 if len(frame)>7 else 'auto', key=key)

    def dashboard(self):
        ui.section_heading('Afectaciones a servicios MTDH', f"14/09/2026 al {pd.Timestamp(self.data['corte']):%d/%m/%Y}", 'storm')
        st.caption(f'{self.alerts.provincia.nunique()} provincias · {self.alerts[["provincia","canton"]].drop_duplicates().shape[0]} cantones · '
                   f'{int(self.alerts.estado.eq("Resuelto").sum())} alertas resueltas. La ausencia de registros no prueba ausencia de afectación.')
        columns = [st.container(),st.container()] if compact() else st.columns(2, gap='medium')
        for box,field,title,subtitle,color in [(columns[0],'provincia','Alertas por provincia','Alertas con afectación documentada al servicio',theme.SERIE_BONOS),
                                              (columns[1],'estado','Estado de las alertas','Pendientes, en seguimiento o resueltas',theme.FUCSIA)]:
            with box, st.container(border=True, key=f'card_enos_{field}'):
                ui.chart_title(title, subtitle)
                self._bars(enos.summary(self.alerts,field), 'alertas', 'enos_'+field, color)
        with st.container(border=True, key='card_enos_alerts'):
            ui.chart_title('Detalle de alertas', 'Código y nombre de UA cuando constan en la fuente')
            self._table(self.alerts, {'codigo':'Alerta','fecha':'Fecha de registro','provincia':'Provincia','canton':'Cantón',
                        'estado':'Estado','codigo_ua':'Código UA','unidad':'Unidad de atención','servicio':'Servicio','afectacion_servicio':'Afectación al servicio','afectados_fuente':'Afectados (campo fuente)'}, 'enos_alerts')
        ui.info_note(enos.ALERT_NOTE,'Alcance de las alertas')
        st.caption(enos.QUALITY_NOTE)
        ui.section_heading('Kits entregados en provincias priorizadas', 'Entregas documentadas del fin de semana', 'life-buoy')
        st.caption(enos.KIT_NOTE)
        st.caption(f'{self.kits.provincia.nunique()} provincias · {self.kits[["provincia","canton"]].drop_duplicates().shape[0]} cantones · '
                   f'{len(self.kits)} entregas registradas')
        columns = [st.container(),st.container()] if compact() else st.columns([1, 1.25], gap='medium')
        with columns[0], st.container(border=True, key='card_enos_kits_chart'):
            ui.chart_title('Kits en provincias priorizadas', 'Entregas del 24 y 25 de octubre de 2026')
            self._bars(enos.summary(self.kits, 'provincia', 'kits'), 'kits', 'enos_kits_chart', theme.VIOLETA_500)
        with columns[1], st.container(border=True, key='card_enos_kits'):
            ui.chart_title('Entregas registradas', 'Fecha, provincia, cantón y kits de cada entrega')
            self._table(self.kits, {'fecha':'Fecha','provincia':'Provincia','canton':'Cantón','kits':'Kits entregados'}, 'enos_kits')
        ui.section_heading('Bono de contingencia', 'Planificación El Niño 2026–2027 y referencia de inundaciones', 'banknote')
        plan = self.data['bonos']['planificacion']
        ui.kpi_grid([{'label':'Personas potenciales','value':plan['personas'],'icon':'users','note':'Proyección nacional'},
                     {'label':'Núcleos familiares potenciales','value':plan['nucleos'],'icon':'users','note':'Proyección nacional'},
                     {'label':'Inversión estimada','value':plan['monto']/1e6,'decimals':2,'prefix':'USD','suffix':'millones',
                      'icon':'banknote','note':'Planificación, no ejecución'}],overlap=False)
        ui.info_note(enos.BONO_NOTE,'Alcance disponible del bono',tone='warn')
        columns = [st.container(),st.container()] if compact() else st.columns(2, gap='medium')
        for box,(key,title) in zip(columns, [('gestionados','Pagos gestionados por inundaciones'),('articulacion','En articulación por inundaciones')]):
            frame = self.frames[key]
            with box, st.container(border=True, key=f'card_enos_{key}'):
                ui.chart_title(title, f"{ui.number(frame.personas.sum())} personas · USD {ui.number(frame.monto.sum(),2)} · corte 23/10/2026")
                self._table(frame,{'provincia':'Provincia','evento':'Evento','personas':'Personas','monto':'Monto (USD)'},'enos_'+key)
        st.caption('Fuentes: Subsecretaría Territorial, análisis de alertas del 26/10; reporte ministerial de kits al 25/10; ayuda memoria del bono al 23/10.')

    def scope_items(self):
        return [('Ámbito','Solo afectaciones documentadas a servicios MTDH'),('Alertas desde','14/09/2026'),('Corte',self.data['corte']),('Territorio',self.territory_label),
                ('Kits','24–25/10/2026'),('Bonos','Referencia al 23/10; sin atribución ENOS confirmada')]

    def digest(self):
        return fingerprint(self.data,self.provinces)

    def products_notes(self):
        return {'resumen':'Dos páginas: alertas desde el 14/09, kits, planificación y estado del bono con sus alcances.',
                'presentacion':'Cuatro diapositivas institucionales: cifras clave, alertas, kits y bono.',
                'datos':'Libro con alertas, kits, bonos por inundaciones, planificación y fuentes.'}

    def sheets(self):
        return ['Resumen','Alertas','Kits','Bonos','Ficha técnica']

    def preview_visual(self):
        rows=enos.summary(self.alerts,'provincia')
        return ui.svg_columns([r['value'] for r in rows],[r['name'][:8] for r in rows],width=300,height=170,night=False)

    def slide_titles(self):
        return 'Afectaciones a servicios MTDH','Kits y bono de contingencia'

    def report_contents(self,kind):
        return [('storm','Alertas desde el 14/09','Estado, territorio y unidades identificadas'),
                ('life-buoy','Kits entregados','Entregas del fin de semana, con fecha y cantón'),
                ('banknote','Bono de contingencia','Planificación ENOS y referencia de inundaciones'),
                ('document','Fuentes y alcances','Cortes distintos y datos pendientes de validación')]

    def report_context(self,title):
        from src.reports.enos import build_context
        return build_context(self,title)


ROOT = enos.ROOT
