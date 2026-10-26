"""Build a dated, minimal operational snapshot from the supplied territorial sources.

python scripts/build_enos.py --alerts alertas.xlsx --bonos bono.docx --cut 2026-10-26
Kit rows are transcribed from Reporte_ministerial_kits_provincias_priorizadas_rev.pdf,
cut 25/10/2026 19:00. Source narratives, addresses and staff names are not published.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import names


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text).upper()) if unicodedata.category(c) != 'Mn').strip()


def money(text):
    return float(re.sub(r'[^\d,.-]', '', text).replace('.', '').replace(',', '.'))


def alert_rows(path, start, cut, review_path):
    frame = pd.read_excel(path, sheet_name='Detalle', header=3).dropna(subset=['Código'])
    dates = pd.to_datetime(frame.Fecha, errors='raise')
    chosen = frame.loc[dates.between(pd.Timestamp(start), pd.Timestamp(cut)) & frame.Tipo.eq('Desastre natural')].copy()
    if chosen.Código.duplicated().any():
        raise ValueError('Hay códigos de alerta repetidos; revisar el corte antes de publicarlo.')
    review = pd.read_csv(review_path, dtype=str).fillna('')
    if review.codigo.duplicated().any() or not review.incluir.isin(['si', 'no']).all():
        raise ValueError('Revisar las decisiones de afectación a servicios: códigos únicos y si/no.')
    decisions = review.set_index('codigo').to_dict('index')
    rows = []
    for r in chosen.to_dict('records'):
        decision = decisions.get(str(r['Código']).strip(), {})
        # An identified UA alone does not establish a service impact. Unreviewed cases stay out.
        if decision.get('incluir') != 'si':
            continue
        if not decision.get('afectacion_servicio') or not decision.get('servicio'):
            raise ValueError('Una alerta incluida requiere servicio y afectación documentada.')
        code = str(r['Código SIIMDH']).strip()
        code = '' if code in ('—', '-', 'nan', '') else re.sub(r'\.0$', '', code)
        rows.append({'codigo': str(r['Código']).strip(), 'fecha': str(r['Fecha'])[:10],
                     'provincia': names.place(r['Provincia']), 'canton': names.place(r['Cantón']),
                     'estado': r['Estado'], 'prioridad': r['Prioridad'], 'codigo_ua': code,
                     'unidad': str(r['Unidad de atención']).strip() if code else 'Sin unidad registrada',
                     'afectacion_servicio_confirmada': True, 'servicio': decision['servicio'],
                     'afectacion_servicio': decision['afectacion_servicio'],
                     'afectados_fuente': int(r['Afectados']) if pd.notna(r['Afectados']) else None})
    return rows, {'alertas_detalle_original': len(frame), 'alertas_desde_inicio': len(chosen),
                  'alertas_con_afectacion_servicios': len(rows), 'alertas_excluidas': len(chosen)-len(rows),
                  'alertas_sin_revision': sum(str(code).strip() not in decisions for code in chosen.Código)}


def bono_rows(path):
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    text = ' '.join(n.text or '' for n in root.findall('.//w:t', ns))
    tables = []
    for table in root.findall('.//w:tbl', ns):
        rows = []
        previous_province = ''
        for tr in table.findall('w:tr', ns)[1:]:
            nodes = tr.findall('w:tc', ns)
            cells = [''.join(n.text or '' for n in c.findall('.//w:t', ns)).strip() for c in nodes]
            if len(cells) == 4:
                if not cells[0] and nodes[0].find('w:tcPr/w:vMerge', ns) is not None:
                    cells[0] = previous_province
                elif cells[0]:
                    previous_province = cells[0]
            if len(cells) != 4 or plain(cells[0]) == 'TOTAL':
                continue
            if plain(cells[1]) != 'INUNDACION':
                continue
            if not cells[0]:
                raise ValueError('Provincia vacía en la tabla de bonos.')
            rows.append({'provincia': names.place(cells[0]), 'evento': 'Inundación',
                         'personas': int(cells[2].replace('.', '')), 'monto': money(cells[3])})
        tables.append(rows)
    if len(tables) != 2:
        raise ValueError('Se esperaban las tablas de pagos gestionados y casos en articulación.')
    potential = re.search(r'potencial de\s+([\d.]+)', text)
    families = re.search(r'aproximadamente\s+([\d.]+)', text)
    investment = re.search(r'USD\s+([\d.,]+)', text)
    if not all((potential, families, investment)):
        raise ValueError('No se encontró la planificación ENOS en la ayuda memoria.')
    return {'gestionados': tables[0], 'articulacion': tables[1],
            'planificacion': {'personas': int(potential[1].replace('.', '')), 'nucleos': int(families[1].replace('.', '')),
                             'monto': money(investment[1])}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--alerts', type=Path, required=True)
    p.add_argument('--bonos', type=Path, required=True)
    p.add_argument('--service-review', type=Path, required=True,
                   help='CSV de revisión documental: solo incluir=si con impacto en servicios se publica.')
    p.add_argument('--kits', type=Path, default=ROOT/'data/reference/enos_kits_2026-10-25.csv')
    p.add_argument('--start', default='2026-09-29')
    p.add_argument('--cut', required=True)
    p.add_argument('--kits-cut', default='2026-10-25')
    p.add_argument('--bonos-cut', default='2026-10-23')
    p.add_argument('--bonos-start', default='2026-08-29')
    a = p.parse_args()
    for date in (a.start, a.cut, a.kits_cut, a.bonos_cut, a.bonos_start):
        datetime.strptime(date, '%Y-%m-%d')
    alerts, control = alert_rows(a.alerts, a.start, a.cut, a.service_review)
    kits = pd.read_csv(a.kits)
    if kits.kits.lt(0).any() or not pd.to_datetime(kits.fecha).between(a.start, a.kits_cut).all():
        raise ValueError('Las entregas de kits no corresponden a su corte.')
    result = {'schema': 2, 'corte': a.cut, 'desde': a.start, 'generado_utc': datetime.now(timezone.utc).isoformat(),
              'alertas': alerts, 'kits': kits.to_dict('records'), 'bonos': bono_rows(a.bonos),
              'cortes': {'alertas': a.cut, 'kits': a.kits_cut, 'bonos': a.bonos_cut, 'bonos_desde': a.bonos_start},
              'control': {**control,
                          'resumen_excel_no_utilizado': 'Las hojas resumen incluyen otras categorías y fechas.'},
              'fuentes': [{'nombre': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()} for f in (a.alerts, a.bonos, a.kits, a.service_review)]}
    out = ROOT/f'data/processed/seguimiento_enos_{a.cut}.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'alertas': len(alerts), 'kits': int(kits.kits.sum()),
                      'bonos_inundacion': {k: sum(r['personas'] for r in result['bonos'][k]) for k in ('gestionados','articulacion')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
