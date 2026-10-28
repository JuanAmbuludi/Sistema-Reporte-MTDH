"""Replace the kit snapshot from a processed Kobo workbook; never append cumulative cuts.

Usage: python scripts/update_kobo_kits.py source.xlsx [--snapshot path]
Only administrative delivery identifiers, dates, territories and totals are published.
"""
from pathlib import Path
import argparse, hashlib, json, sys
from datetime import datetime, timezone
import openpyxl
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import depuracion, enos, names
from scripts.build_enos import source_day, source_id


def update(source, snapshot):
    source, snapshot = Path(source), Path(snapshot)
    enos.ensure_open(snapshot)
    wb = openpyxl.load_workbook(source, data_only=True)
    try:
        values = list(wb['Detalle de entregas'].values)
        raw = [dict(zip(values[0], row)) for row in values[1:] if any(value is not None for value in row)]
        controls = dict(wb['Control y notas'].values)
        provincial = list(wb['Resumen provincial'].values)[1:-1]
    finally:
        wb.close()
    ids = [source_id(r['ID Kobo'], 'ID Kobo') for r in raw]
    if len(ids) != len(set(ids)):
        raise ValueError('Identificadores Kobo duplicados: revisar antes de publicar.')
    declared_cut = controls['Corte'].split(' (')[0].strip()
    cut = None
    for pattern in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            cut = datetime.strptime(declared_cut, pattern)
            break
        except ValueError:
            pass
    if cut is None:
        raise ValueError('Fecha de corte Kobo inválida.')
    gaz = depuracion.gazetteer(); rows = []
    for r, identifier in zip(raw, ids):
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
        delivered = source_day(r['Fecha entrega'], 'Fecha de entrega')
        if delivered > source_day(cut):
            raise ValueError('Las entregas de kits contienen fechas posteriores a su corte.')
        rows.append({'id_kobo': identifier, 'fecha': delivered.strftime('%Y-%m-%d'),
                     'provincia': depuracion.PROVINCE_NAMES[code], 'canton': canton,
                     'kits': kits, 'familias': families})
    expected = (controls['Registros'], controls['Kits'], controls['Familias reportadas'], controls['Provincias'])
    actual = (len(rows), sum(r['kits'] for r in rows), sum(r['familias'] for r in rows), len({r['provincia'] for r in rows}))
    if actual != expected:
        raise ValueError('El detalle de entregas no coincide con los controles de la fuente.')
    for province, count, kits, families, _ in provincial:
        code = gaz.province(province); part = [r for r in rows if r['provincia'] == depuracion.PROVINCE_NAMES[code]]
        if (len(part), sum(r['kits'] for r in part), sum(r['familias'] for r in part)) != (count, kits, families):
            raise ValueError('El detalle de entregas no coincide con el resumen provincial de la fuente.')
    data = json.loads(snapshot.read_text())
    data.pop('kits_nivel', None)
    data['kits'] = sorted(rows, key=lambda r: (r['fecha'], r['provincia'], r['id_kobo']))
    data['cortes']['kits'] = cut.isoformat()
    data['kits_metadatos'] = {'fuente': source.name, 'corte': controls['Corte'],
                            'desde': min((r['fecha'] for r in rows), default=None), 'hasta': max((r['fecha'] for r in rows), default=None),
                            'registros': len(rows), 'kits': sum(r['kits'] for r in rows),
                            'familias_reportadas': sum(r['familias'] for r in rows), 'reemplaza_corte_anterior': True}
    data['generado_utc'] = datetime.now(timezone.utc).isoformat()
    data['fuentes'] = [s for s in data.get('fuentes', []) if 'kits' not in s['nombre'].lower() and 'kobo' not in s['nombre'].lower()]
    data['fuentes'].append({'nombre': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    snapshot.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(data['kits_metadatos'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('source')
    # By default, the publication of the day being reported (open it first with scripts/nuevo_corte_riesgos.py).
    parser.add_argument('--snapshot', default=None)
    args = parser.parse_args()
    from src import enos
    update(args.source, args.snapshot or enos.snapshots()[-1])
