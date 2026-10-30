"""Dated aggregates for inclusion, employability and self-employment formation.

The Ferias area presents the two source lines separately. Its measures are
participation records; no event or unique-person count can be inferred.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/processed'
SOURCES = {'empleabilidad_autoempleo':'Empleabilidad y autoempleo', 'inclusion_economica':'Inclusión económica'}
MONTHS = ('enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre')


def manifest() -> dict:
    path=FOLDER/'ferias.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'fuentes':{}}


metadata = manifest


def _read(name: str) -> pd.DataFrame:
    path=FOLDER/name
    if not path.exists():
        return pd.DataFrame()
    frame=pd.read_parquet(path)
    frame['periodo']=frame['periodo_id']
    return frame


def load() -> pd.DataFrame:
    return _read('ferias_participaciones.parquet')


def profile() -> pd.DataFrame:
    return _read('ferias_perfil.parquet')


def select(frame=None, *, fuente=None, since=None, until=None, provinces=(), modalidad=None, tipo_capacitacion=None):
    frame=load() if frame is None else frame
    if frame.empty:
        return frame.copy()
    keep=pd.Series(True,index=frame.index)
    if fuente:keep &= frame.fuente.eq(fuente)
    if since:keep &= frame.periodo_id.ge(str(since)[:7])
    if until:keep &= frame.periodo_id.le(str(until)[:7])
    if provinces:keep &= frame.provincia_codigo.isin(provinces)
    if modalidad:keep &= frame.modalidad.eq(modalidad)
    if tipo_capacitacion:keep &= frame.tipo_capacitacion.eq(tipo_capacitacion)
    return frame.loc[keep].copy()


def catalog(fuente=None) -> list[dict]:
    frame=select(fuente=fuente)
    if frame.empty:return []
    return [{'id':p,'year':int(p[:4]),'month':int(p[5:7]),'label':f'{MONTHS[int(p[5:7])-1].capitalize()} {p[:4]}'}
            for p in sorted(frame.periodo_id.unique(),reverse=True)]


def summary(frame) -> dict:
    if frame.empty:
        return {'participaciones':0,'provincias':0,'cantones':0,'meses':0,'modalidades':0,'tipos':0}
    return {'participaciones':int(frame.participaciones.sum()),
        'provincias':int(frame.loc[frame.provincia_codigo.ne('99'),'provincia_codigo'].nunique()),
        'cantones':int(frame.loc[frame.canton.ne('Sin dato'),['provincia_codigo','canton']].drop_duplicates().shape[0]),
        'meses':int(frame.periodo_id.nunique()),'modalidades':int(frame.loc[frame.modalidad.ne('Sin dato'),'modalidad'].nunique()),
        'tipos':int(frame.loc[frame.tipo_capacitacion.ne('Sin dato'),'tipo_capacitacion'].nunique())}


def monthly(frame) -> pd.DataFrame:
    return frame.groupby(['fuente','periodo_id'],as_index=False).participaciones.sum() if not frame.empty else pd.DataFrame(columns=['fuente','periodo_id','participaciones'])


def territorial(frame) -> pd.DataFrame:
    return frame.groupby(['provincia_codigo','provincia'],as_index=False).participaciones.sum().sort_values('participaciones',ascending=False) if not frame.empty else pd.DataFrame(columns=['provincia_codigo','provincia','participaciones'])
