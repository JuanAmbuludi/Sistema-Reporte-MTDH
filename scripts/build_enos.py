"""Build a dated, minimal operational snapshot from the supplied territorial sources.

python scripts/build_enos.py --alerts alertas.xlsx --bonos bono.docx --service-review revision.csv --kits kits.csv --start AAAA-MM-DD --cut AAAA-MM-DD
The source rows retain their full history up to their own cuts. --start only
sets the publication's visible scope. Kit IDs must come from the source; the
legacy transcribed CSV requires --allow-legacy-kits and cannot be reconciled
as an event history. Source narratives, addresses and staff names are omitted.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from numbers import Real
from pathlib import Path
import re
import sys
import unicodedata
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import enos, names


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text).upper()) if unicodedata.category(c) != 'Mn').strip()


def money(text):
    return float(re.sub(r'[^\d,.-]', '', text).replace('.', '').replace(',', '.'))


def source_id(value, label='Identificador'):
    """Use source identifiers only; normalize Excel integer representations."""
    if value is None or isinstance(value, bool) or pd.isna(value):
        raise ValueError(f'{label}: falta un identificador de la fuente.')
    text = str(value).strip()
    if text.lower() in ('', '-', '—', 'none', 'nan', 'n/a'):
        raise ValueError(f'{label}: falta un identificador de la fuente.')
    if re.fullmatch(r'\d+(?:\.0+)?', text):
        number = int(text.split('.')[0])
        if number <= 0:
            raise ValueError(f'{label}: identificador numérico inválido.')
        return str(number)
    if isinstance(value, Real) or re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text):
        raise ValueError(f'{label}: identificador numérico inválido.')
    return text


def source_day(value, label='Fecha'):
    """Preserve the local calendar day, including the last day's late events."""
    if value is None or isinstance(value, Real) or pd.isna(value):
        raise ValueError(f'{label}: fecha ausente o inválida.')
    try:
        moment = pd.to_datetime(value, format='mixed', dayfirst=True, errors='raise')
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: fecha ausente o inválida.') from exc
    if pd.isna(moment):
        raise ValueError(f'{label}: fecha ausente o inválida.')
    return moment.normalize().tz_localize(None)


def alert_rows(path, start, cut, review_path):
    frame = pd.read_excel(path, sheet_name='Detalle', header=3)
    candidates = frame.loc[frame.Tipo.map(plain).eq('DESASTRE NATURAL')].copy()
    candidates['Código'] = [source_id(value, 'Código de alerta') for value in candidates['Código']]
    if candidates.Código.duplicated().any():
        raise ValueError('Hay códigos de alerta repetidos; revisar el corte antes de publicarlo.')
    candidates['Fecha'] = pd.Series([source_day(value, 'Fecha de alerta') for value in candidates.Fecha],
                                   index=candidates.index, dtype='datetime64[ns]')
    # Retain all source history; the dashboard applies the publication's start.
    chosen = candidates.loc[candidates.Fecha.le(source_day(cut))].copy()
    review = pd.read_csv(review_path, dtype=str).fillna('')
    review['codigo'] = [source_id(value, 'Código de revisión') for value in review.codigo]
    review['incluir'] = review.incluir.str.strip().str.lower()
    if review.codigo.duplicated().any() or not review.incluir.isin(['si', 'no']).all():
        raise ValueError('Revisar las decisiones de afectación a servicios: códigos únicos y si/no.')
    decisions = review.set_index('codigo').to_dict('index')
    missing = sorted(set(chosen.Código) - set(decisions))
    if missing:
        raise ValueError('Falta revisión documental de alertas: ' + ', '.join(missing))
    rows, excluded = [], []
    for r in chosen.to_dict('records'):
        decision = decisions[r['Código']]
        # Public scope: reviewed alerts with a valid UA code; impact confirmation remains a separate field.
        if decision.get('incluir') != 'si':
            excluded.append(r['Código'])
            continue
        if not decision.get('afectacion_servicio') or not decision.get('servicio'):
            raise ValueError('Una alerta incluida requiere servicio y afectación documentada.')
        raw_code = r['Código SIIMDH']
        code = '' if pd.isna(raw_code) or str(raw_code).strip().lower() in ('—', '-', 'nan', 'none', 'n/a', 'na', '') else source_id(raw_code, 'Código UA')
        if not code:
            excluded.append(r['Código'])
            continue
        unit = str(r['Unidad de atención']).strip()
        if unit in ('—', '-', 'nan', '', 'Sin unidad registrada'):
            unit = decision.get('unidad_fuente') or 'Sin unidad registrada'
        rows.append({'codigo': r['Código'], 'fecha': r['Fecha'].strftime('%Y-%m-%d'),
                     'provincia': names.place(r['Provincia']), 'canton': names.place(r['Cantón']),
                     'estado': r['Estado'], 'prioridad': r['Prioridad'], 'codigo_ua': code,
                     'unidad': unit,
                     'afectacion_servicio_confirmada': str(decision.get('afectacion_confirmada', '')).strip().lower() == 'si', 'servicio': decision['servicio'],
                     'afectacion_servicio': decision['afectacion_servicio'],
                     'afectados_fuente': int(r['Afectados']) if pd.notna(r['Afectados']) else None})
    return rows, {'alertas_detalle_original': int(frame.Código.notna().sum()), 'alertas_desde_inicio': len(chosen),
                  'alertas_candidatas_hasta_corte': len(chosen),
                  'alertas_anteriores_inicio': int(chosen.Fecha.lt(source_day(start)).sum()),
                  'alertas_con_afectacion_servicios': sum(r['afectacion_servicio_confirmada'] for r in rows), 'alertas_con_codigo_ua': len(rows), 'alertas_excluidas': len(chosen)-len(rows),
                  'alertas_excluidas_codigos': sorted(excluded),
                  'alertas_revision_inicio_solicitado': start,
                  'alertas_sin_revision': 0}


def kit_rows(path, cut, *, allow_legacy=False):
    frame = pd.read_csv(path, dtype={'id_kobo': 'string'})
    frame['fecha'] = pd.Series([source_day(value, 'Fecha de entrega') for value in frame.fecha],
                              index=frame.index, dtype='datetime64[ns]')
    if not frame.fecha.le(source_day(cut)).all():
        raise ValueError('Las entregas de kits contienen fechas posteriores a su corte.')
    for column in ('kits', 'familias'):
        if column not in frame:
            continue
        values = pd.to_numeric(frame[column], errors='raise')
        if values.isna().any() or values.lt(0).any() or values.mod(1).ne(0).any():
            raise ValueError(f'Conteos de {column} no válidos.')
        frame[column] = values.astype(int)
    legacy = 'id_kobo' not in frame
    if legacy and not allow_legacy:
        raise ValueError('La base de kits requiere id_kobo de la fuente para conciliar el historial. '
                         'Use --allow-legacy-kits solo para una publicación antigua sin identificadores; no se inventarán IDs.')
    if not legacy:
        frame['id_kobo'] = [source_id(value, 'ID Kobo') for value in frame.id_kobo]
        if frame.id_kobo.duplicated().any():
            raise ValueError('Identificadores Kobo duplicados: revisar antes de publicar.')
    frame['fecha'] = frame.fecha.dt.strftime('%Y-%m-%d')
    columns = [column for column in ('id_kobo', 'fecha', 'provincia', 'canton', 'kits', 'familias') if column in frame]
    return frame[columns].to_dict('records'), {'kits_sin_identificador': legacy,
                                     'kits_registros': len(frame),
                                     'kits_conciliables_por_id': not legacy}


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
                   help='CSV de revisión documental: incluir=si y código UA; afectacion_confirmada=si/no distingue evidencia de impacto.')
    p.add_argument('--kits', type=Path, default=ROOT/'data/reference/enos_kits_2026-10-25.csv')
    p.add_argument('--allow-legacy-kits', action='store_true',
                   help='Permite el CSV antiguo sin id_kobo únicamente para una publicación no conciliable como historial.')
    p.add_argument('--start', default='2026-09-28')
    p.add_argument('--cut', required=True)
    p.add_argument('--kits-cut', default='2026-10-25')
    p.add_argument('--bonos-cut', default='2026-10-23')
    p.add_argument('--bonos-start', default='2026-08-29')
    a = p.parse_args()
    for date in (a.start, a.cut, a.kits_cut, a.bonos_cut, a.bonos_start):
        datetime.strptime(date, '%Y-%m-%d')
    out = ROOT/f'data/processed/seguimiento_enos_{a.cut}.json'
    enos.ensure_open(out)
    alerts, control = alert_rows(a.alerts, a.start, a.cut, a.service_review)
    kits, kit_control = kit_rows(a.kits, a.kits_cut, allow_legacy=a.allow_legacy_kits)
    if kit_control['kits_sin_identificador']:
        print('Advertencia: kits sin ID de origen; publicación antigua no conciliable con el historial por identificador.', file=sys.stderr)
    result = {'schema': 3, 'criterio_alertas': 'codigo_ua', 'corte': a.cut, 'desde': a.start, 'generado_utc': datetime.now(timezone.utc).isoformat(),
              'alertas': alerts, 'kits': kits, 'bonos': bono_rows(a.bonos),
              'filtro_temporal_estricto': True, 'bonos_con_fecha_individual': False,
              'cortes': {'alertas': a.cut, 'kits': a.kits_cut, 'bonos': a.bonos_cut, 'bonos_desde': a.bonos_start},
              'control': {**control, **kit_control,
                          'resumen_excel_no_utilizado': 'Las hojas resumen incluyen otras categorías y fechas.'},
              'fuentes': [{'nombre': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()} for f in (a.alerts, a.bonos, a.kits, a.service_review)]}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'alertas': len(alerts), 'kits': sum(row['kits'] for row in kits),
                      'bonos_inundacion': {k: sum(r['personas'] for r in result['bonos'][k]) for k in ('gestionados','articulacion')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
