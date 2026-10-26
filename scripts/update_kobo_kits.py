"""Replace the kit snapshot from a processed Kobo workbook; never append cumulative cuts.

Usage: python scripts/update_kobo_kits.py source.xlsx [--snapshot path]
Only administrative delivery identifiers, dates, territories and totals are published.
"""
from pathlib import Path
import argparse, hashlib, json, sys
from collections import defaultdict
from datetime import datetime, timezone
import openpyxl
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import depuracion, names


def update(source, snapshot):
    source, snapshot = Path(source), Path(snapshot)
    wb = openpyxl.load_workbook(source, data_only=True)
    values = list(wb['Detalle de entregas'].values)
    raw = [dict(zip(values[0], row)) for row in values[1:] if row[0] is not None]
    controls = dict(wb['Control y notas'].values)
    ids = [str(r['ID Kobo']) for r in raw]
    if len(ids) != len(set(ids)):
        raise ValueError('Identificadores Kobo duplicados: revisar antes de publicar.')
    gaz = depuracion.gazetteer(); rows = []
    for r in raw:
        code = gaz.province(r['Provincia'])
        if code is None:
            raise ValueError('Provincia sin correspondencia: ' + str(r['Provincia']))
        canton = str(r['Cantón'])
        if canton.startswith('c_'):
            canton = gaz.canton_name.get(canton[2:], canton)
        else:
            canton = names.place(canton)
        kits, families = int(r['Kits']), int(r['Familias'])
        if kits < 0 or families < 0 or kits != r['Kits'] or families != r['Familias']:
            raise ValueError('Conteos de kits/familias no válidos.')
        rows.append({'id_kobo': str(r['ID Kobo']), 'fecha': r['Fecha entrega'].strftime('%Y-%m-%d'),
                     'provincia': depuracion.PROVINCE_NAMES[code], 'canton': canton,
                     'kits': kits, 'familias': families})
    assert len(rows) == controls['Registros']
    assert sum(r['kits'] for r in rows) == controls['Kits']
    assert sum(r['familias'] for r in rows) == controls['Familias reportadas']
    assert len({r['provincia'] for r in rows}) == controls['Provincias']
    for province, count, kits, families, _ in list(wb['Resumen provincial'].values)[1:-1]:
        code = gaz.province(province); part = [r for r in rows if r['provincia'] == depuracion.PROVINCE_NAMES[code]]
        assert (len(part), sum(r['kits'] for r in part), sum(r['familias'] for r in part)) == (count, kits, families)
    data = json.loads(snapshot.read_text())
    data.pop('kits_nivel', None)
    data['kits'] = sorted(rows, key=lambda r: (r['fecha'], r['provincia'], r['id_kobo']))
    data['cortes']['kits'] = datetime.strptime(controls['Corte'].split(' (')[0], '%d/%m/%Y %H:%M:%S').isoformat()
    data['kits_metadatos'] = {'fuente': source.name, 'corte': controls['Corte'],
                            'desde': min(r['fecha'] for r in rows), 'hasta': max(r['fecha'] for r in rows),
                            'registros': len(rows), 'kits': sum(r['kits'] for r in rows),
                            'familias_reportadas': sum(r['familias'] for r in rows), 'reemplaza_corte_anterior': True}
    data['generado_utc'] = datetime.now(timezone.utc).isoformat()
    data['fuentes'] = [s for s in data['fuentes'] if 'kits' not in s['nombre'].lower() and 'kobo' not in s['nombre'].lower()]
    data['fuentes'].append({'nombre': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    snapshot.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(data['kits_metadatos'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('source')
    parser.add_argument('--snapshot', default=ROOT/'data/processed/seguimiento_enos_2026-10-26.json')
    args = parser.parse_args(); update(args.source, args.snapshot)
