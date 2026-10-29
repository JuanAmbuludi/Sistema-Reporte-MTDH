"""Actualiza ENOS con los cuatro Excel recibidos el 29/10/2026.

Autor: Juan Ambuludi Maza. Conserva los cortes publicados y la estructura JSON.
Uso: python scripts/actualizar_enos_29_octubre.py --alertas archivo.xlsx
     --suspendidas archivo.xlsx --kits archivo.xlsx --contingencias archivo.xlsx
Kits es un histórico completo por ID Kobo; unidades es un corte, no un flujo.
No modifica plantillas ni archivos de los informes exportables.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import enos, names
from src.depuracion import key as territory_key
from scripts.nuevo_corte_riesgos import open_day

DAY = '2026-10-29'


def read_rows(path, sheet=None):
    book = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        return list((book[sheet] if sheet else book.active).values)
    finally:
        book.close()


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


def count(value):
    if value is None or int(value) != value or value < 0:
        raise ValueError(f'Conteo inválido: {value}')
    return int(value)


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def update(alertas, suspendidas, kits, contingencias):
    target = enos.FOLDER / f'seguimiento_enos_{DAY}.json'
    if not target.exists():
        open_day(DAY)
    enos.ensure_open(target)
    data = json.loads(target.read_text(encoding='utf-8'))
    # Alertas: mismo código = mismo registro, incluso si cambia su estado.
    current = {r['codigo']: r for r in data['alertas']}
    source = read_rows(alertas, 'Detalle')
    incoming = [dict(zip(source[3], r)) for r in source[4:] if r[0]]
    assert len(incoming) == len({r['Código'] for r in incoming})
    new_count = sum(r['Código'] not in current for r in incoming)
    for row in incoming:
        code = row['Código']
        if code not in current:
            current[code] = dict(codigo=code, fecha=str(row['Fecha'])[:10],
                provincia=names.place(row['Provincia']), canton=names.place(row['Cantón']),
                codigo_ua='' if str(row['Código SIIMDH']) in ('—', '-', 'None') else str(row['Código SIIMDH']),
                unidad='' if row['Unidad de atención'] == 'Sin unidad registrada' else row['Unidad de atención'],
                afectacion_servicio_confirmada=None, servicio='Sin servicio identificado',
                afectacion_servicio='', origen='aplicativo', tipo_alerta='Emergencia' if row['Tipo'] == 'Desastre natural' else row['Tipo'],
                fecha_texto=str(row['Fecha'])[:10], mes_reporte=str(row['Fecha'])[:7])
        current[code].update(estado=row['Estado'], prioridad=row['Prioridad'],
                             afectados_fuente=count(row['Afectados']), fuente=Path(alertas).name)
    data['alertas'] = sorted(current.values(), key=lambda r: (r['fecha'], r['codigo']))
    data['control'].update(alertas_total=len(current), alertas_actualizacion_aplicativo=len(incoming),
        alertas_detalle_recibido=len(incoming), encabezado_alertas_fuente=source[1][0],
        alertas_actualizacion_bases={'actualizadas': len(incoming)-new_count, 'nuevas_aplicativo': new_count})
    data['cortes']['alertas'] = max(str(r['Fecha'])[:10] for r in incoming)

    # Histórico Kobo completo: sustituye, no suma, el snapshot anterior.
    geo = json.loads((ROOT / 'assets/geo/ecuador_dpa.json').read_text())
    provinces = {r['c']: r['n'] for r in geo['provincias']}
    cantons = {r['c']: r['n'] for r in geo['cantones']}
    province_codes = {territory_key(r['n']): r['c'] for r in geo['provincias']}
    canton_codes = {(r['p'], territory_key(r['n'])): r['c'] for r in geo['cantones']}
    values = read_rows(kits)
    raw = [dict(zip(values[0], row)) for row in values[1:] if any(v is not None for v in row)]
    deliveries = []
    for row in raw:
        province, canton = str(row['Provincia']).removeprefix('p_'), str(row['Cantón']).removeprefix('c_')
        if province not in provinces:
            province = province_codes.get(territory_key(province))
        if canton not in cantons:
            canton = canton_codes.get((province, territory_key(canton)))
        assert province in provinces and canton in cantons and canton.startswith(province)
        day = row['Fecha efectiva de la entrega'].date().isoformat()
        assert day <= DAY
        deliveries.append(dict(id_kobo=str(count(row['_id'])), fecha=day, provincia=names.place(provinces[province]),
            canton=names.place(cantons[canton]), kits=count(row['Número de kits entregados']),
            familias=count(row['Número de familias beneficiadas'])))
    assert len(deliveries) == len({r['id_kobo'] for r in deliveries})
    data['kits'] = sorted(deliveries, key=lambda r: (r['fecha'], r['provincia'], r['id_kobo']))
    data['cortes']['kits'] = DAY
    data['kits_metadatos'].update(fuente=Path(kits).name, corte=DAY,
        desde=min(r['fecha'] for r in deliveries), hasta=max(r['fecha'] for r in deliveries),
        registros=len(deliveries), kits=sum(r['kits'] for r in deliveries),
        familias_reportadas=sum(r['familias'] for r in deliveries), reemplaza_corte_anterior=True,
        registros_actualizacion=len(deliveries), modo_actualizacion='Histórico completo, reemplazo por ID Kobo único.',
        exportacion_fuente='2026-10-29T13:24:57')

    # Unidades suspendidas: reemplazo del inventario, conciliado con RESUMEN.
    details = []
    for prov, canton, parish, unit, service, mode, admin, coverage in read_rows(suspendidas, 'DETALLE')[1:]:
        if not prov:
            continue
        if 'CNH' in mode: service, program = 'CNH', 'DII'
        elif 'CDI' in mode: service, program = 'CDI', 'DII'
        elif 'ACOMPAÑAMIENTO FAMILIAR' in mode: service, program = 'AF', 'AF'
        elif 'ADULTOS' in service: service, program = 'PAM', 'PAM_SERV'
        elif 'DISCAPACIDAD' in service: service, program = 'PCD', 'PCD_SERV'
        else: service, program = 'PE', 'PE'
        details.append(dict(provincia=names.place(prov), canton=names.place(canton), parroquia=names.place(parish),
            servicio=service, modalidad=mode, unidad=unit, codigo_ua='', estado='Suspendida', unidades=1,
            programa_id=program, corte_fuente='2026-10-28', cobertura=count(coverage)))
    assert len(details) == len({(r['provincia'], r['canton'], r['servicio'], r['unidad']) for r in details})
    total = next(r for r in read_rows(suspendidas, 'RESUMEN') if r[0] == 'Total general')
    assert (len(details), sum(r['cobertura'] for r in details)) == (total[1], total[2])
    counts = Counter((r['provincia'], r['servicio'], r['programa_id']) for r in details)
    continuity = dict(corte='2026-10-28', fuente=Path(suspendidas).name,
        sha256=hashlib.sha256(Path(suspendidas).read_bytes()).hexdigest(),
        registros=[dict(provincia=p, servicio=s, programa_id=g, estado='Suspendida', unidades=n,
                         corte_fuente='2026-10-28') for (p,s,g),n in sorted(counts.items())],
        detalle=details, fuentes_por_provincia={r['provincia']: '2026-10-28' for r in details},
        validacion=dict(registros_detalle=len(details), suspendidas_total=len(details), cobertura_total=total[2],
            criterio='Corte completo del 28/10/2026. Reemplaza el inventario anterior; no se acumulan cortes.'))

    # Contingencias: conciliar los dos cuadros sin sumarlos entre sí.
    values = read_rows(contingencias)
    prov_rows = values[1:10]
    event_rows = values[14:17]
    expected = (1705, Decimal('516762.60'), 503, Decimal('147906.12'))
    for rows in (prov_rows, event_rows):
        actual = (sum(count(r[1]) for r in rows), sum(money(r[2]) for r in rows),
                  sum(count(r[3]) for r in rows), sum(money(r[4]) for r in rows))
        assert actual == expected, (actual, expected)
    for row in (values[10], values[17]):
        assert (count(row[1]), money(row[2]), count(row[3]), money(row[4])) == expected
    data['bonos']['articulacion'] = [dict(provincia=names.place(r[0]), evento='Todos los eventos',
        personas=count(r[1]), monto=float(money(r[2]))) for r in prov_rows]
    data['bonos']['gestionados'] = [dict(provincia=names.place(r[0]), evento='Todos los eventos',
        personas=count(r[3]), monto=float(money(r[4]))) for r in prov_rows]
    data['bonos']['fuente_articulacion'] = Path(contingencias).name
    # La fuente no declara período ni fecha individual. No atribuir el total a un mes.
    data['bonos_periodos_confirmados'] = {}
    data['bonos_referencia_confirmada'] = {'articulacion': dict(confirmacion='Totales del Excel CONTINGENCIAS recibido el 29/10/2026; sin período desglosado.',
        personas=1705, monto=516762.60)}
    data['bonos_presentacion'] = dict(unidad='Familias habilitadas', estado='Habilitadas al pago', cobro_confirmado=True,
        confirmacion='Núcleos familiares habilitados y cobrados según CONTINGENCIAS.xlsx. Campos técnicos conservados.')
    data['cortes'].update(bonos=DAY, bonos_gestionados=DAY)
    data['cortes'].pop('bonos_desde', None)
    data['notas']['bono'] = ('CONTINGENCIAS.xlsx: 1.705 núcleos familiares habilitados, USD 516.762,60; '
        '503 núcleos familiares cobrados, USD 147.906,12. Fuente sin período desglosado, recibida el 29/10/2026. '
        'Los cuadros por provincia y tipo de evento concilian; no se suman entre sí. No hay cruce provincia-evento.')
    data['control']['bonos_revision'] = data['notas']['bono']
    data['control']['criterio_temporal'] = ('Alertas por fecha de registro; kits por fecha efectiva de entrega; '
        'unidades según último corte territorial. Bonos: total de la fuente, sin distribución temporal.')
    for path in (alertas, suspendidas, kits, contingencias):
        item = dict(nombre=Path(path).name, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
        if item not in data['fuentes']:
            data['fuentes'].append(item)
    data['generado_utc'] = datetime.now(timezone.utc).isoformat()
    write(target, data)
    write(enos.FOLDER / f'continuidad_servicios_{DAY}.json', continuity)
    print(json.dumps(dict(alertas=len(current), alertas_nuevas=new_count, unidades=len(details),
        kits_historico=data['kits_metadatos']['kits'], registros_kits=len(deliveries),
        kits_desde_28_septiembre=sum(r['kits'] for r in deliveries if r['fecha'] >= '2026-09-28'),
        habilitados=1705, monto_habilitado=516762.60, cobrados=503, monto_cobrado=147906.12)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('alertas', 'suspendidas', 'kits', 'contingencias'):
        parser.add_argument('--' + key, required=True)
    update(**vars(parser.parse_args()))
