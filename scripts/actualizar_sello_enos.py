"""Record the last committed Excel publication time; run after ENOS validation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/enos_excel'
FILES = ('alertas.xlsx', 'kits.xlsx', 'unidades_suspendidas.xlsx', 'contingencias.xlsx')


def build_stamp():
    paths = [f'data/enos_excel/{name}' for name in FILES]
    value = subprocess.check_output(['git', 'log', '-1', '--format=%cI', '--', *paths], cwd=ROOT, text=True).strip()
    if not value:
        raise ValueError('No se encontró la publicación de los Excel en Git.')
    moment = datetime.fromisoformat(value).astimezone(timezone.utc)
    return {'generado_utc': moment.isoformat(),
            'criterio': 'Fecha y hora del último commit que actualizó las bases Excel ENOS.',
            'archivos': {name: hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() for name in FILES}}


if __name__ == '__main__':
    (FOLDER / 'actualizacion.json').write_text(json.dumps(build_stamp(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
