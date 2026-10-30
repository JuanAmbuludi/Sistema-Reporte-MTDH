"""Incorpora el histórico de CDH sin duplicar meses existentes ni mezclar cartera.

Uso: python scripts/preparar_cdh_historico.py --fuente CDH_PERIODO_GOBIERNO.parquet
Solo se escriben agregados; el insumo de operaciones no se copia al repositorio.
El período conserva el mes de reporte utilizado por el tablero y los boletines.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import depuracion
from scripts.preparar_cdh_brigadas import _title

OUT = ROOT / 'data' / 'processed'
TERRITORY = ['fuente', 'periodo', 'provincia_codigo', 'provincia', 'canton_codigo', 'canton',
             'parroquia_codigo', 'parroquia', 'bono', 'plazo']
PROFILE = ['fuente', 'periodo', 'provincia_codigo', 'bono', 'sexo', 'edad', 'actividad', 'area']
BONUS = {'BONO DE DESARROLLO HUMANO':'Bono de Desarrollo Humano', 'BONO VARIABLE':'BDH con componente variable',
         'PENSION TODA UNA VIDA':'Pensión Toda Una Vida', 'MIS MEJORES ANOS':'Pensión Mis Mejores Años',
         'BONO MIL DIAS':'Bono Mil Días'}
ACTIVITY = {'AGRICULTURA GANADERIA SILVICULTURA Y PESCA':'Agricultura, ganadería, silvicultura y pesca',
            'COMERCIO AL POR MAYOR Y AL POR MENOR REPARACION DE VEHICULOS AUTOMOTORES Y MOTOCICLETAS':'Comercio',
            'ACTIVIDADES DE ALOJAMIENTO Y DE SERVICIO DE COMIDAS':'Alojamiento y servicio de comidas',
            'INDUSTRIA MANUFACTURERA':'Industria manufacturera', 'OTRAS ACTIVIDADES DE SERVICIOS':'Otras actividades de servicios'}


def totals(frame):
    return frame.groupby('periodo')[['creditos', 'monto']].sum().sort_index()


def prepare_dated(source):
    """Monthly flows for period reports, using disbursement dates when present.

    The original report-month aggregates stay untouched. Missing daily dates
    retain their declared report month and an explicit precision flag.
    """
    dates = pd.to_datetime(source.FECHA_DESEMBOLSO, errors='coerce')
    reported = source.PERIODO_ARCHIVO.astype(str)
    amount = pd.to_numeric(source.MONTO, errors='raise')
    frame = pd.DataFrame({
        'periodo': dates.dt.strftime('%Y-%m').fillna(reported),
        'periodo_reporte': reported,
        'fecha_precision': dates.notna().map({True: 'fecha_desembolso', False: 'mes_reporte'}),
        'bono': source.TIPO_SUBSIDIO.map(depuracion.key).map(BONUS).fillna(source.TIPO_SUBSIDIO.map(_title)),
        'sexo': source.GENERO.map(depuracion.key).map({'FEMENINO': 'Mujeres', 'MASCULINO': 'Hombres'}).fillna('Sin dato'),
        'centavos': (amount * 100).round().astype('int64'),
    })
    keys = ['periodo', 'periodo_reporte', 'fecha_precision', 'bono', 'sexo']
    grouped = frame.groupby(keys, as_index=False, dropna=False).agg(creditos=('centavos', 'size'), centavos=('centavos', 'sum'))
    grouped['monto'] = grouped.pop('centavos') / 100
    info = {
        'criterio_periodo': 'Mes de FECHA_DESEMBOLSO; cuando falta la fecha diaria se conserva PERIODO_ARCHIVO y se identifica como mes_reporte.',
        'filas_fuente': int(len(source)), 'creditos': int(grouped.creditos.sum()),
        'monto': round(float(grouped.monto.sum()), 2),
        'sin_fecha_diaria': int(dates.isna().sum()),
        'fecha_desembolso_desde': dates.min().strftime('%Y-%m-%d'),
        'fecha_desembolso_hasta': dates.max().strftime('%Y-%m-%d'),
        'periodo_desde': str(grouped.periodo.min()), 'periodo_hasta': str(grouped.periodo.max()),
    }
    return grouped, info


def reconcile_merge(existing, incoming):
    """Preserve matching published months; add only new months; never sum overlap."""
    old = existing.loc[existing.fuente.eq('desembolso')]
    before, new = totals(old), totals(incoming)
    overlap = sorted(set(before.index) & set(new.index))
    for period in overlap:
        if int(before.loc[period, 'creditos']) != int(new.loc[period, 'creditos']) or round(float(before.loc[period, 'monto']), 2) != round(float(new.loc[period, 'monto']), 2):
            raise ValueError(f'CDH {period}: la fuente no concilia con los agregados publicados; no se reemplaza automáticamente.')
    added = incoming.loc[~incoming.periodo.isin(before.index)]
    result = pd.concat([existing, added], ignore_index=True)
    result['creditos'] = result.creditos.astype('int64')
    result['monto'] = result.monto.astype('float64')
    return result.sort_values(list(result.columns[:-2])).reset_index(drop=True), overlap, sorted(added.periodo.unique())


def prepare(source):
    required = ['FUENTE', 'PERIODO_ARCHIVO', 'PROVINCIA', 'CANTON', 'PARROQUIA', 'TIPO_SUBSIDIO',
                'TIPO_CREDITO', 'TIPO_ACTIVIDAD', 'GENERO', 'EDAD', 'TIPO_ZONA', 'MONTO', 'FECHA_DESEMBOLSO']
    missing = set(required) - set(source)
    if missing:
        raise ValueError('Faltan columnas de CDH: ' + ', '.join(sorted(missing)))
    if not source.FUENTE.map(depuracion.key).eq('DESEMBOLSO').all():
        raise ValueError('El histórico debe contener únicamente DESEMBOLSO; la cartera vigente se conserva separada.')
    periods = source.PERIODO_ARCHIVO.astype(str)
    if not periods.str.fullmatch(r'\d{4}-(0[1-9]|1[0-2])').all():
        raise ValueError('PERIODO_ARCHIVO debe ser AAAA-MM.')
    amount = pd.to_numeric(source.MONTO, errors='coerce')
    if amount.isna().any() or amount.lt(0).any() or ((amount * 100 - (amount * 100).round()).abs() > 0.00001).any():
        raise ValueError('MONTO debe ser no negativo y expresado en centavos.')
    # Resolve each distinct place once with the same gazetteer as the dashboard.
    places = source[['PROVINCIA', 'CANTON', 'PARROQUIA']].drop_duplicates().rename(columns=str.lower)
    original = places.copy()
    places['canton'] = places.canton.replace({'URBINA JADO':'SALITRE', 'PABLO VI':'PABLO SEXTO'})
    mapped = depuracion.locate_frame(places, parish='parroquia')
    for field in ('provincia', 'canton', 'parroquia'):
        mapped['original_' + field] = original[field].to_numpy()
    lookup = {}
    for row in mapped.to_dict('records'):
        lookup[(row['original_provincia'], row['original_canton'], row['original_parroquia'])] = row
    resolved = [lookup[tuple(values)] for values in source[['PROVINCIA', 'CANTON', 'PARROQUIA']].itertuples(index=False, name=None)]
    frame = pd.DataFrame({'fuente':'desembolso', 'periodo':periods, 'centavos':(amount * 100).round().astype('int64')})
    for field in ('provincia', 'canton', 'parroquia'):
        frame[field + '_codigo'] = [r[field + '_codigo'] or '' for r in resolved]
        frame[field] = [_title(r[field + '_nombre'] or r['original_' + field]) for r in resolved]
    frame['bono'] = source.TIPO_SUBSIDIO.map(depuracion.key).map(BONUS).fillna(source.TIPO_SUBSIDIO.map(_title))
    terms = {'24 MESES':'24 meses', '12 MESES':'12 meses', 'ASOCIATIVO':'Asociativo (plazo no informado)', 'INDIVIDUAL':'Individual (plazo no informado)'}
    frame['plazo'] = source.TIPO_CREDITO.map(depuracion.key).map({depuracion.key(k):v for k,v in terms.items()}).fillna(source.TIPO_CREDITO.map(_title))
    frame['actividad'] = source.TIPO_ACTIVIDAD.map(depuracion.key).map(ACTIVITY).fillna(source.TIPO_ACTIVIDAD.map(_title))
    frame['sexo'] = source.GENERO.map(depuracion.key).map({'FEMENINO':'Mujeres', 'MASCULINO':'Hombres'}).fillna('Sin dato')
    ages = pd.to_numeric(source.EDAD, errors='coerce')
    frame['edad'] = pd.cut(ages, [17,29,45,65,float('inf')], labels=['18 a 29 años','30 a 45 años','46 a 65 años','Más de 65 años']).astype('object').fillna('Sin dato')
    frame['area'] = source.TIPO_ZONA.map(depuracion.key).map({'URBANA':'Urbana','RURAL':'Rural'}).fillna('Sin dato')
    def aggregate(keys):
        grouped = frame.groupby(keys, as_index=False, dropna=False).agg(creditos=('centavos','size'), centavos=('centavos','sum'))
        grouped['monto'] = grouped.pop('centavos') / 100
        return grouped
    dates = pd.to_datetime(source.FECHA_DESEMBOLSO, errors='coerce')
    stats = {'filas_fuente':len(source), 'monto_fuente':round(float(amount.sum()),2),
             'periodos_reporte':sorted(periods.unique().tolist()),
             'fecha_desembolso_desde':dates.min().strftime('%Y-%m-%d'),
             'fecha_desembolso_hasta':dates.max().strftime('%Y-%m-%d'),
             'sin_fecha_desembolso':int(dates.isna().sum()),
             'sin_codigo_provincia':int(frame.provincia_codigo.eq('').sum()),
             'sin_codigo_canton':int(frame.canton_codigo.eq('').sum()),
             'sin_codigo_parroquia':int(frame.parroquia_codigo.eq('').sum()),
             'filas_iguales_en_atributos':int(source.duplicated().sum())}
    return aggregate(TERRITORY), aggregate(PROFILE), stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fuente', type=Path, required=True)
    args = parser.parse_args()
    source = pd.read_parquet(args.fuente)
    incoming_t, incoming_p, stats = prepare(source)
    dated, dated_info = prepare_dated(source)
    territory, overlap, added = reconcile_merge(pd.read_parquet(OUT / 'cdh_territorio.parquet'), incoming_t)
    profile, profile_overlap, profile_added = reconcile_merge(pd.read_parquet(OUT / 'cdh_perfil.parquet'), incoming_p)
    if overlap != profile_overlap or added != profile_added:
        raise ValueError('Territorio y perfil no cubren los mismos meses.')
    if not totals(territory).round(2).equals(totals(profile).round(2)):
        raise ValueError('Los agregados territoriales y de perfil no concilian.')
    manifest_path = OUT / 'cdh_brigadas.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['generado_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    info = manifest['cdh']
    info['desembolsos_fechados'] = {**dated_info, 'archivo': args.fuente.name,
                                  'sha256': hashlib.sha256(args.fuente.read_bytes()).hexdigest()}
    info['fuentes']['historico_gobierno'] = args.fuente.name
    info['historico_gobierno'] = {**stats, 'sha256':hashlib.sha256(args.fuente.read_bytes()).hexdigest(),
        'meses_conciliados_sin_duplicar':overlap,
        'criterio_periodo':'Mes de reporte PERIODO_ARCHIVO, igual al histórico 2026 previamente publicado.',
        'criterio_filas':'Una operación por fila. No deduplicar por atributos demográficos: la fuente no contiene un identificador único de crédito.',
        'nota_fecha':f"El reporte de diciembre de 2023 incluye desembolsos desde el 23 de noviembre de 2023. Se conservan {stats['sin_fecha_desembolso']} operaciones sin fecha diaria, con mes de reporte informado.",
        'nota_geografia':'Los códigos ausentes en la fuente se resuelven con el catálogo territorial del tablero; las parroquias no ubicadas conservan su nombre y el código vacío.'}
    info['alcance'] = ('CDH desembolsados desde el inicio de gobierno (23/11/2023), reportados entre diciembre de 2023 y septiembre de 2026. '
                      'Se conservan los agregados 2026 conciliados y se añaden los meses anteriores sin duplicarlos. La cartera vigente es un estado separado. Agregados sin datos personales.')
    for kind in ('desembolso','vigente'):
        rows = territory.loc[territory.fuente.eq(kind)]
        info['control'][kind] = {'creditos':int(rows.creditos.sum()), 'monto':round(float(rows.monto.sum()),2), 'periodos':sorted(rows.periodo.unique().tolist())}
    territory.to_parquet(OUT / 'cdh_territorio.parquet', index=False, compression='zstd')
    profile.to_parquet(OUT / 'cdh_perfil.parquet', index=False, compression='zstd')
    dated.to_parquet(OUT / 'cdh_desembolsos_fechados.parquet', index=False, compression='zstd')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'agregados':added, 'conciliados':overlap,'control':info['control'],'fuente':stats},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
