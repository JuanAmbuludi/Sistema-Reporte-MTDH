"""Record real source changes after validation, independently of Excel formatting."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import gzip
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/enos_excel'
FILES = ('alertas.xlsx', 'kits.xlsx', 'unidades_suspendidas.xlsx', 'contingencias.xlsx')
sys.path.insert(0, str(ROOT))


def changed_at(relative: str, current: str) -> str:
    """Find the commit that introduced the current values, skipping re-saves."""
    from src import enos_excel as excel
    history = subprocess.check_output(['git', 'log', '--format=%H\t%cI', '--', relative], cwd=ROOT, text=True).splitlines()
    if not history:
        raise ValueError(f'No se encontró la publicación de {relative} en Git.')
    introduced = None
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / Path(relative).name
        for line in history:
            commit, moment = line.split('\t', 1)
            result = subprocess.run(['git', 'show', f'{commit}:{relative}'], cwd=ROOT, capture_output=True)
            if result.returncode:
                break
            path.write_bytes(result.stdout)
            # A temporary file can retain its size and filesystem clock across
            # historical versions; do not reuse a workbook cache entry.
            excel._read.cache_clear()
            try:
                same = excel.content_hash(path) == current
            except Exception:  # A historical invalid upload is not a usable data revision.
                same = False
            if not same:
                break
            introduced = moment
    value = introduced or history[0].split('\t', 1)[1]
    return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()


def build_stamp():
    from src import enos_excel as excel
    processed = ROOT / 'data/processed'
    stamp_path = FOLDER / excel.STAMP
    previous = json.loads(stamp_path.read_text(encoding='utf-8')) if stamp_path.exists() else {}
    hashes = excel.content_hashes(processed)
    sources = {}
    for name, fingerprint in hashes.items():
        before = previous.get('fuentes', {}).get(name, {})
        moment = (before.get('actualizado_utc') if before.get('contenido_sha256') == fingerprint else None)
        sources[name] = {'contenido_sha256': fingerprint,
                         'actualizado_utc': moment or changed_at(name, fingerprint)}
    latest = max(source['actualizado_utc'] for source in sources.values())
    # Preserve the already published clock on first migration and re-validation
    # when the exact protected sources are still the same.
    publication = excel.published(processed)
    if previous.get('generado_utc') and publication and not publication['pendiente']:
        latest = previous['generado_utc']
    return {'generado_utc': latest,
            'criterio': 'Último cambio real en registros o cortes de las fuentes ENOS; guardar, formatear o validar sin cambios no modifica la fecha.',
            'archivos': {name: hashlib.sha256((FOLDER / name).read_bytes()).hexdigest() for name in FILES},
            'fuentes': sources}


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
