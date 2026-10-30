"""Record the last committed Excel publication time; run after ENOS validation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import gzip
import sys

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/enos_excel'
FILES = ('alertas.xlsx', 'kits.xlsx', 'unidades_suspendidas.xlsx', 'contingencias.xlsx')
sys.path.insert(0, str(ROOT))


def build_stamp():
    paths = [f'data/enos_excel/{name}' for name in FILES] + ['data/processed/alertas_historicas.json']
    value = subprocess.check_output(['git', 'log', '-1', '--format=%cI', '--', *paths], cwd=ROOT, text=True).strip()
    if not value:
        raise ValueError('No se encontró la publicación de los Excel en Git.')
    moment = datetime.fromisoformat(value).astimezone(timezone.utc)
    return {'generado_utc': moment.isoformat(),
            'criterio': 'Fecha y hora del último commit que actualizó las bases Excel o el histórico de alertas ENOS.',
            'archivos': {name: hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() for name in FILES}}


def publish():
    from src import enos, enos_excel as excel
    from scripts.validar_enos_excel import validate
    controls = validate()
    stamp = build_stamp()
    data = enos.history(live=True)
    data['generado_utc'] = stamp['generado_utc']
    observations = enos._editable_observations(live=True)
    previous = excel.published(enos.FOLDER)
    if previous and observations:
        observations = [r for r in previous['observaciones'] if r['corte'] < observations[0]['corte']] + observations
    publication = {'formato':'ENOS_VALIDADO_1', 'datos':data, 'observaciones':observations,
                   'fuentes':excel.source_hashes(enos.FOLDER), 'identificadores':excel.registry_ids(enos.FOLDER)}
    payload = gzip.compress(json.dumps(publication, ensure_ascii=False).encode('utf-8'), mtime=0)
    target = FOLDER / excel.VALIDATED
    temporary = target.with_suffix('.tmp')
    temporary.write_bytes(payload)
    temporary.replace(target)
    (FOLDER / 'actualizacion.json').write_text(json.dumps(stamp, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return controls


if __name__ == '__main__':
    print(json.dumps(publish(), ensure_ascii=False, indent=2))
