"""Aggregate training sources for Ferias without publishing nominal information.

The source files contain participation records, not fair/event identifiers or
employment placements. They are kept as separate lines of formation. Fase 1
has no person identifier: repeated demographic combinations are retained.
Only wholly identical nominal CSV rows are removed. No names, IDs, tax IDs,
phones, business names or individual pseudonyms leave this importer.

Usage:
    python scripts/preparar_ferias.py --fase1 BASE.xlsx --empleabilidad BASE.csv
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.depuracion import PROVINCE_NAMES

MONTHS = dict(zip(('ENERO','FEBRERO','MARZO','ABRIL','MAYO','JUNIO','JULIO','AGOSTO','SEPTIEMBRE','OCTUBRE','NOVIEMBRE','DICIEMBRE'), range(1,13)))
MONTHS['SETIEMBRE'] = 9
BASE_FIELDS = ['fuente','periodo_id','provincia_codigo','provincia','canton','modalidad','tipo_capacitacion']
PROFILE_FIELDS = ['fuente','periodo_id','provincia_codigo','modalidad','tipo_capacitacion','dimension','categoria']


def key(value) -> str:
    if value is None or pd.isna(value):
        return ''
    return ' '.join(unicodedata.normalize('NFKD', str(value)).encode('ascii','ignore').decode().upper().split())


def period(year, month) -> str:
    y = int(float(year))
    text = key(month)
    m = int(float(text)) if re.fullmatch(r'\d+(?:\.0+)?', text) else MONTHS.get(text)
    if not m or not 1 <= m <= 12 or not 2000 <= y <= 2100:
        raise ValueError(f'Año/mes inválidos: {year!r}/{month!r}.')
    return f'{y:04d}-{m:02d}'


@lru_cache(maxsize=10000)
def label(value) -> str:
    text = ' '.join(str(value or '').split())
    if key(text) in {'','NONE','NAN','S/R','S/D','SIN DATO','SIN DATOS','0'}:
        return 'Sin dato'
    return text[:1].upper() + text[1:].lower()


_PROVINCES = {key(name): (code,name) for code,name in PROVINCE_NAMES.items()}
_PROVINCES.update({'SANTO DOMINGO':('23','Santo Domingo de los Tsáchilas'),
                   'SANTO DOMINGO DE TSACHILAS':('23','Santo Domingo de los Tsáchilas'),
                   'STO. DOMINGO DE LOS TSACHILAS':('23','Santo Domingo de los Tsáchilas')})


@lru_cache(maxsize=1000)
def province(value):
    return _PROVINCES.get(key(value), ('99', label(value)))


def _gender(value):
    return {'FEMENINO':'Mujeres','FEMENINA':'Mujeres','MUJER':'Mujeres','MASCULINO':'Hombres','MASCULINA':'Hombres','HOMBRE':'Hombres'}.get(key(value), 'Sin dato')


def _age(value):
    text = key(value)
    if text in {'','S/R','NONE','NAN'}:
        return 'Sin dato'
    if '18' in text and '29' in text:
        return '18 a 29 años'
    if '30' in text and '45' in text:
        return '30 a 45 años'
    if '46' in text and ('64' in text or '65' in text):
        return '46 a 64/65 años'
    if '65' in text:
        return '65 años o más'
    return label(value)


def _modality(value):
    return {'PRESENCIAL':'Presencial','VIRTUAL':'Virtual','SEMIPRESENCIAL':'Semipresencial'}.get(key(value), label(value))


def _component(value):
    return {'TECNICO':'Técnico','ADMINISTRATIVO':'Administrativo','AUTOCONOCIMIENTO':'Autoconocimiento'}.get(key(value),label(value))


class Aggregates:
    def __init__(self):
        self.rows = Counter()
        self.profiles = Counter()

    def add(self, source, when, prov, canton, modality, kind, profiles):
        code, name = province(prov)
        base = (source, when, code, name, label(canton), _modality(modality), kind)
        self.rows[base] += 1
        for dimension, category in profiles.items():
            self.profiles[(source, when, code, base[5], kind, dimension, category)] += 1

    def frames(self):
        rows = pd.DataFrame([(*k,n) for k,n in self.rows.items()], columns=BASE_FIELDS+['participaciones'])
        profiles = pd.DataFrame([(*k,n) for k,n in self.profiles.items()], columns=PROFILE_FIELDS+['participaciones'])
        return (rows.sort_values(BASE_FIELDS).reset_index(drop=True),
                profiles.sort_values(PROFILE_FIELDS).reset_index(drop=True))


def read_phase(source: Path, aggregate: Aggregates, since: str):
    book = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = book.worksheets[0]
        # This export incorrectly declares A1 as its used range.
        sheet.reset_dimensions()
        iterator = sheet.iter_rows(values_only=True)
        headers = next(iterator)
        required = {'AÑO','MES','PROVINCIA','CANTÓN','MODALIDAD','TIPO DE  CAPACITACION','GÉNERO','RANGO DE EDAD','SECTOR','ACTIVIDAD'}
        if not required.issubset(headers):
            raise ValueError('Fase 1: faltan columnas requeridas: ' + ', '.join(sorted(required-set(headers))))
        total = selected = 0
        bounds = []
        for line, row in enumerate(iterator,2):
            if not any(v is not None for v in row):
                continue
            total += 1
            d = dict(zip(headers,row))
            try:
                when = period(d['AÑO'],d['MES'])
            except (TypeError,ValueError) as exc:
                raise ValueError(f'Fase 1 fila {line}: año/mes inválidos.') from exc
            bounds.append(when)
            if when < since:
                continue
            selected += 1
            aggregate.add('inclusion_economica', when, d['PROVINCIA'], d['CANTÓN'],d['MODALIDAD'],label(d['TIPO DE  CAPACITACION']),
                {'sexo':_gender(d['GÉNERO']), 'edad':_age(d['RANGO DE EDAD']),
                 'sector':label(d['SECTOR']), 'actividad':label(d['ACTIVIDAD'])})
        return {'filas_fuente':total,'registros':selected,'filas_anteriores_al_inicio':total-selected,
                'duplicados_eliminados':0,'desde_fuente':min(bounds),'hasta_fuente':max(bounds),
                'deduplicacion':'Sin identificador personal: se conservan filas demográficas coincidentes; no se interpretan como duplicados.'}
    finally:
        book.close()


def read_employment(source: Path, aggregate: Aggregates, since: str):
    frame = pd.read_csv(source, encoding='cp1252', dtype=str, keep_default_na=False)
    required = {'Año','Mes','Cedula','Provincia','Canton','Modalidad','Componente','Genero','Rango de Edad','Tipo Zona','Tipo Actividad','Institucion'}
    if not required.issubset(frame):
        raise ValueError('Empleabilidad: faltan columnas requeridas: ' + ', '.join(sorted(required-set(frame))))
    periods = pd.Series([period(y,m) for y,m in zip(frame['Año'],frame.Mes)],index=frame.index)
    selected = periods.ge(since)
    raw_selected = int(selected.sum())
    duplicate = frame.duplicated(keep='first')
    original_total = len(frame)
    frame = frame.loc[selected & ~duplicate].copy()
    frame['_periodo'] = periods.loc[frame.index]
    for d in frame.to_dict('records'):
        aggregate.add('empleabilidad_autoempleo',d['_periodo'],d['Provincia'],d['Canton'],d['Modalidad'],_component(d['Componente']),
            {'sexo':_gender(d['Genero']),'edad':_age(d['Rango de Edad']),'sector':label(d['Tipo Zona']),
             'actividad':label(d['Tipo Actividad']),'institucion':label(d['Institucion'])})
    return {'filas_fuente':original_total,'registros':len(frame),'filas_periodo_antes_deduplicacion':raw_selected,
            'filas_anteriores_al_inicio':int((~selected).sum()),'duplicados_eliminados':int((duplicate & selected).sum()),
            'duplicados_identicos_fuente_completa':int(duplicate.sum()),'desde_fuente':periods.min(),'hasta_fuente':periods.max(),
            'deduplicacion':'Se elimina solo la repetición exacta de todas las columnas de la fila nominal. No se deduplican distintas capacitaciones de una misma persona.'}


def build(fase1: Path, employment: Path, *, since='2023-11'):
    aggregate = Aggregates()
    controls = {'inclusion_economica':read_phase(Path(fase1),aggregate,since),
                'empleabilidad_autoempleo':read_employment(Path(employment),aggregate,since)}
    rows, profiles = aggregate.frames()
    sources = {}
    definitions = [('inclusion_economica',Path(fase1),'Inclusión económica',
                    'Registros de formación de fase 1. Las sesiones 3 y 4 corresponden al fortalecimiento para la inclusión económica; cada fila se cuenta una vez.'),
                   ('empleabilidad_autoempleo',Path(employment),'Empleabilidad y autoempleo',
                    'Registros de participación en capacitación de empleabilidad y autoempleo por componente, modalidad e institución.')]
    for source,path,name,scope in definitions:
        selected = rows.loc[rows.fuente.eq(source)]
        sources[source] = {**controls[source], 'label':name,'archivo':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'desde':str(selected.periodo_id.min()),'hasta':str(selected.periodo_id.max()),'unidad':'Registros de participación',
            'alcance':scope,'meses':int(selected.periodo_id.nunique()),'provincias':int(selected.loc[selected.provincia_codigo.ne('99'),'provincia_codigo'].nunique()),
            'sin_provincia_codificada':int(selected.loc[selected.provincia_codigo.eq('99'),'participaciones'].sum())}
        if int(selected.participaciones.sum()) != controls[source]['registros']:
            raise AssertionError('Los agregados no concilian con las filas de origen.')
        for _, p in profiles.loc[profiles.fuente.eq(source)].groupby('dimension'):
            if int(p.participaciones.sum()) != controls[source]['registros']:
                raise AssertionError('Los perfiles no concilian con las filas de origen.')
    manifest = {'schema':1,'generado_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'inicio_publicado':since,'fuentes':sources,
        'criterio_temporal':'Mes y año informados por la fuente; noviembre de 2023 se incluye completo porque no existe fecha diaria en fase 1.',
        'criterio_conteo':'Registros de participación por línea de formación. No equivalen a personas únicas, número de ferias, emprendimientos creados ni colocaciones laborales.',
        'cruce_fuentes':'Las fuentes se presentan separadas. Fase 1 no contiene identificador personal para deduplicar personas entre ambas líneas.',
        'privacidad':'Solo agregados territoriales y perfiles por dimensión. No se publican nombres, cédulas, RUC, teléfonos ni emprendimientos individuales.'}
    return rows,profiles,manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--fase1',type=Path,required=True)
    parser.add_argument('--empleabilidad',type=Path,required=True)
    parser.add_argument('--desde',default='2023-11')
    parser.add_argument('--salida',type=Path,default=ROOT/'data/processed')
    args=parser.parse_args()
    rows,profiles,manifest=build(args.fase1,args.empleabilidad,since=args.desde)
    args.salida.mkdir(parents=True,exist_ok=True)
    rows.to_parquet(args.salida/'ferias_participaciones.parquet',index=False,compression='zstd')
    profiles.to_parquet(args.salida/'ferias_perfil.parquet',index=False,compression='zstd')
    (args.salida/'ferias.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
