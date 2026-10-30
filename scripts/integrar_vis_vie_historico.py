"""Extend monthly VIS/VIE coverage without replacing independently deduplicated cuts.

Usage:
    python scripts/integrar_vis_vie_historico.py --vis VIS_inforeport_resumen.parquet --vie VIE_inforeport_resumen.parquet

The input files contain parish/group aggregates, not nominal identifiers. Known
monthly partitions remain authoritative. Missing months are added once; the
source's reported users are never interpreted as distinct people across months.
No budget is estimated or replicated into a month without a budget source.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.historicos import norm, periods, sha256, write_parquet

SERIES = ROOT / 'data/series'
BONOS = {
    'BONO DE DESARROLLO HUMANO': 'BDH',
    'BONO DE DESARROLLO HUMANO CON COMPONENTE VARIABLE': 'BDHV',
    'BONO JOAQUIN GALLEGOS LARA': 'BJGL',
    'BONO 1000 DIAS': 'BMD',
    'PENSION MIS MEJORES ANOS': 'MMA',
    'PENSION TODA UNA VIDA': 'PTV',
    'PENSION PARA ADULTOS MAYORES': 'PAM',
    'PENSION PARA PERSONAS CON DISCAPACIDAD': 'PCD',
}
MODALIDADES = {
    'ATENCION DOMICILIARIA': 'DOMICILIAR',
    'CENTRO GERONTOLOGICOS RESIDENCIALES': 'RESIDENCIALES',
    'CENTRO GERONTOLOGICOS DE ATENCION DIURNA': 'DIURNOS',
    'ESPACIOS DE SOCIALIZACION Y ENCUENTRO': 'ACTIVOS',
    'ATENCION EN EL HOGAR Y LA COMUNIDAD': 'DOMICILIAR',
    'CENTROS DE REFERENCIA Y ACOGIDA INCLUSIVOS': 'REFERENCIA',
    'CENTROS DIURNOS DE DESARROLLO INTEGRAL PARA PERSONAS CON DISCAPACIDAD': 'DIURNOS',
    'ERRADICACION DEL TRABAJO INFANTIL': 'ETI',
    'ERRADICACION PROGRESIVA DE LA MENDICIDAD': 'MENDICIDAD',
    'MOVILIDAD HUMANA - CIUDADES DE ACOGIDA': 'CIUDADES DE ACOGIDA',
    'ACOGIMIENTO INSTITUCIONAL': 'INSTITUCIONAL',
    'ACOGIMIENTO FAMILIAR': 'FAMILIAR',
    'APOYO FAMILIAR Y CUSTODIA FAMILIAR': 'CUSTODIA',
    'ACOGIMIENTO INSTITUCIONAL TRATA DE PERSONAS': 'AI TRATA DE PERSONAS',
    'ATENCION Y PROTECCION EMERGENTE - ABRIGO TEMPORAL': 'APE ABRIGO TEMPORAL',
}
GEOGRAPHY = ['codigo_provincia', 'provincia', 'codigo_canton', 'canton', 'codigo_parroquia', 'parroquia']
LEVELS = [('Provincia', 2), ('Cantón', 4), ('Parroquia', 6)]
NOTE = ('Cortes mensuales. Los meses existentes conservan las tabulaciones deduplicadas originales. '
        'Los meses agregados desde resúmenes VIS/VIE suman los conteos de sus grupos de origen; '
        'no acreditan personas únicas entre grupos, modalidades, territorios o meses. '
        'En VIS 2026 se conserva el conteo deduplicado anterior porque el resumen nuevo casi coincide con registros. '
        'No se imputan presupuestos a meses sin fuente financiera.')


def read_source(path: Path, kind: str) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    dims = ['servicio', 'modalidad', 'tipo_administracion', 'cooperante', 'convenio'] if kind == 'VIS' else ['bono']
    counts = ['usuarios_unicos', 'unidades_unicas', 'registros'] if kind == 'VIS' else ['beneficiarios_unicos', 'registros']
    required = ['periodo_inforeport', 'anio_inforeport', 'mes_inforeport', 'provincia_codigo', 'provincia',
                'canton_codigo', 'canton', 'parroquia_codigo', 'parroquia', *dims, *counts]
    if not set(required) <= set(frame):
        raise ValueError(f'{kind}: faltan columnas {sorted(set(required) - set(frame))}')
    if frame.duplicated([c for c in required if c not in counts]).any():
        raise ValueError(f'{kind}: grupos de origen repetidos; no se suman duplicados automáticamente.')
    for col in counts:
        values = pd.to_numeric(frame[col], errors='raise')
        if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
            raise ValueError(f'{kind}: conteo inválido en {col}')
        frame[col] = values.astype('int32')
    for col, width in [('provincia_codigo', 2), ('canton_codigo', 4), ('parroquia_codigo', 6)]:
        frame[col] = frame[col].astype(str).str.strip().str.zfill(width)
        if not frame[col].str.fullmatch(r'\d{' + str(width) + '}').all():
            raise ValueError(f'{kind}: código territorial inválido en {col}')
    # Some VIE rows retain obsolete DPA parent codes (e.g. La Concordia).
    # Keep and flag their original labels for the shared territorial resolver.
    out = periods(frame.rename(columns={'periodo_inforeport': 'periodo'}))
    if not (out.anio.eq(frame.anio_inforeport) & out.mes.eq(frame.mes_inforeport)).all():
        raise ValueError(f'{kind}: año/mes no concilian con periodo.')
    return out


def source_tables(frame: pd.DataFrame, kind: str):
    d = frame.rename(columns={'provincia_codigo':'codigo_provincia', 'canton_codigo':'codigo_canton',
                              'parroquia_codigo':'codigo_parroquia'}).copy()
    if kind == 'VIS':
        d['servicio'] = d.servicio.map(norm)
        original = d.modalidad.map(norm)
        d['modalidad'] = original.map(MODALIDADES).fillna(original)
        cdi = original.eq('CENTROS DE DESARROLLO INFANTIL - CDI')
        d.loc[cdi & d.tipo_administracion.map(norm).eq('POR CONVENIO'), 'modalidad'] = 'CDI CONVENIOS'
        d.loc[cdi & d.tipo_administracion.map(norm).eq('ADMINISTRACION DIRECTA'), 'modalidad'] = 'CDI DIRECTOS'
        dims, counts = ['servicio', 'modalidad'], ['usuarios_unicos', 'unidades_unicas', 'registros']
    else:
        d['bono'] = d.bono.map(norm).map(BONOS)
        if d.bono.isna().any():
            raise ValueError('VIE: bono sin correspondencia; amplíe el catálogo antes de importar.')
        dims, counts = ['bono'], ['beneficiarios_unicos', 'registros']
    date_cols = ['periodo', 'anio', 'mes', 'mes_nombre']
    national = d.groupby([*date_cols, *dims], as_index=False, dropna=False)[counts].sum()
    blocks = []
    for level, width in LEVELS:
        geo = GEOGRAPHY[:2] if width == 2 else GEOGRAPHY[:4] if width == 4 else GEOGRAPHY
        block = d.groupby([*date_cols, *geo, *dims], as_index=False, dropna=False)[counts].sum()
        for col in GEOGRAPHY:
            if col not in block:
                block[col] = None
        block['nivel_territorial'] = level
        block['codigo_territorio'] = block[{2:'codigo_provincia',4:'codigo_canton',6:'codigo_parroquia'}[width]]
        # Preserve conflicting source labels for the existing gazetteer to resolve,
        # rather than silently accepting a name paired with the wrong code.
        code_names = block[['codigo_territorio', *[c for c in geo if not c.startswith('codigo_')]]].copy()
        for col in code_names.columns[1:]:
            code_names[col] = code_names[col].map(norm)
        ambiguity = code_names.drop_duplicates().groupby('codigo_territorio').size().gt(1)
        block['codigo_ambiguo'] = block.codigo_territorio.map(ambiguity).fillna(False).astype(bool)
        if width >= 4:
            block['codigo_ambiguo'] |= block.codigo_canton.str[:2].ne(block.codigo_provincia)
        if width == 6:
            block['codigo_ambiguo'] |= block.codigo_parroquia.str[:4].ne(block.codigo_canton)
        block = block[[*date_cols, 'nivel_territorial', 'codigo_territorio', *GEOGRAPHY, 'codigo_ambiguo', *dims, *counts]]
        blocks.append(block)
    return national, pd.concat(blocks, ignore_index=True), dims, counts


def append_missing(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Known partitions win, including independently deduplicated 2026 coverage."""
    absent = incoming.loc[~incoming.periodo.isin(set(existing.periodo))]
    return pd.concat([existing, absent], ignore_index=True)


def integrate(vis: Path, vie: Path, series: Path = SERIES) -> dict:
    target = series / 'integracion_vis_vie_historico.json'
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    audit = {'generado_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'), 'criterio':NOTE, 'fuentes':{}, 'series':{}}
    outputs = []
    for kind, path, basename in [('VIS', vis, 'cobertura_vis'), ('VIE', vie, 'bonos_vie')]:
        frame = read_source(path, kind)
        national, territorial, dims, counts = source_tables(frame, kind)
        hierarchy = frame.parroquia_codigo.str[:4].eq(frame.canton_codigo) & frame.canton_codigo.str[:2].eq(frame.provincia_codigo)
        audit['fuentes'][kind] = {'archivo':path.name, 'sha256':sha256(path), 'filas':len(frame), 'filas_jerarquia_dpa_discordante':int((~hierarchy).sum()),
            'desde':frame.periodo.min(), 'hasta':frame.periodo.max(), 'meses':int(frame.periodo.nunique())}
        existing_national = pd.read_parquet(series / f'{basename}.parquet')
        existing_territory = pd.read_parquet(series / f'{basename}_territorial.parquet')
        original_periods = set(existing_national.periodo)
        overlap = sorted(original_periods & set(frame.periodo))
        comparisons = []
        for month in overlap:
            before = existing_national.loc[existing_national.periodo.eq(month)]
            after = national.loc[national.periodo.eq(month)]
            comparisons.append({'periodo':month, **{f'{c}_vigente':int(before[c].sum()) for c in counts},
                                 **{f'{c}_resumen_recibido':int(after[c].sum()) for c in counts}})
        result_n = append_missing(existing_national, national)
        result_t = append_missing(existing_territory, territorial)
        keys_n = ['periodo', *dims]
        keys_t = ['periodo','nivel_territorial','codigo_territorio','provincia','canton','parroquia',*dims]
        if result_n.duplicated(keys_n).any() or result_t.duplicated(keys_t).any():
            raise ValueError(f'{kind}: resultado contiene claves repetidas.')
        expected = result_n.groupby('periodo').registros.sum()
        for level, block in result_t.groupby('nivel_territorial'):
            if not block.groupby('periodo').registros.sum().equals(expected):
                raise ValueError(f'{kind}: registros nacionales y {level} no concilian.')
        # Preserve existing values exactly, without any duplicate historic/current partition.
        pd.testing.assert_frame_equal(result_n.loc[result_n.periodo.isin(original_periods)].reset_index(drop=True),
                                      existing_national.reset_index(drop=True), check_dtype=False)
        pd.testing.assert_frame_equal(result_t.loc[result_t.periodo.isin(set(existing_territory.periodo))].reset_index(drop=True),
                                      existing_territory.reset_index(drop=True), check_dtype=False)
        outputs += [(result_n, series / f'{basename}.parquet', keys_n),
                    (result_t, series / f'{basename}_territorial.parquet', keys_t)]
        past = previous.get('series', {}).get(kind, {})
        imported = set(past.get('meses_incorporados', [])) | (set(frame.periodo)-original_periods)
        authoritative = sorted(set(overlap) - imported)
        audit['series'][kind] = {'meses_incorporados':sorted(imported),
            'meses_existentes_conservados':authoritative, 'desde_resultado':result_n.periodo.min(),
            'hasta_resultado':result_n.periodo.max(),
            'conciliacion_superposicion':[item for item in comparisons if item['periodo'] in authoritative]}
        if kind == 'VIS':
            # This is a separate descriptive view, never added on top of coverage.
            group = ['periodo','anio','mes','mes_nombre','tipo_administracion','servicio','modalidad',
                     'provincia_codigo','provincia','canton_codigo','canton','parroquia_codigo','parroquia']
            admin = frame.groupby(group, as_index=False, dropna=False)[counts].sum().rename(
                columns={'usuarios_unicos':'usuarios_reportados','unidades_unicas':'unidades_reportadas'})
            outputs.append((admin, series / 'cobertura_vis_administracion.parquet', group))
    for frame, path, keys in outputs:
        # Lower levels are intentionally null in province/canton source partitions.
        frame = frame.sort_values(keys, kind='stable').reset_index(drop=True)
        write_parquet(frame, path, keys=keys if all(frame[c].notna().all() for c in keys) else None, note=NOTE)
        if not all(frame[c].notna().all() for c in keys):
            # Keep nullable territorial grain documented in metadata.
            import pyarrow.parquet as pq
            table = pq.read_table(path)
            metadata = dict(table.schema.metadata or {})
            metadata[b'mtdh.grain'] = '/'.join(keys).encode()
            pq.write_table(table.replace_schema_metadata(metadata), path, compression='zstd', compression_level=9, use_dictionary=True)
    target.write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--vis',type=Path,required=True)
    parser.add_argument('--vie',type=Path,required=True)
    parser.add_argument('--series',type=Path,default=SERIES)
    args=parser.parse_args()
    result=integrate(args.vis,args.vie,args.series)
    print(json.dumps({k:{x:v for x,v in values.items() if x!='conciliacion_superposicion'} for k,values in result['series'].items()},ensure_ascii=False,indent=2))
