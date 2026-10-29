"""Run from the repository root: python scripts/validar_enos_excel.py."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import enos, enos_excel


def validate():
    if len(enos_excel.paths(enos.FOLDER)) != 4:
        raise ValueError('Faltan las cuatro bases de data/enos_excel.')
    data = enos.history()
    units = enos._editable_observations()[-1]
    enabled, collected = data['bonos']['articulacion'], data['bonos']['gestionados']
    for closed in enos.ledger().get('cerrados', {}).values():
        for name, expected in closed.items():
            if enos.fingerprint(enos.FOLDER / name) != expected:
                raise ValueError(f'La publicación cerrada {name} fue alterada.')
    return {
        'alertas_historicas': len(data['alertas']),
        'entregas_kits': len(data['kits']), 'kits_historicos': sum(r['kits'] for r in data['kits']),
        'corte_unidades': units['corte'], 'unidades_suspendidas': len(units['detalle']),
        'cobertura_suspendida': sum(r['cobertura'] for r in units['detalle']),
        'nucleos_habilitados': sum(r['personas'] for r in enabled),
        'monto_habilitado': round(sum(r['monto'] for r in enabled), 2),
        'nucleos_cobrados': sum(r['personas'] for r in collected),
        'monto_cobrado': round(sum(r['monto'] for r in collected), 2),
    }


if __name__ == '__main__':
    try:
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        sys.exit(f'Validación ENOS: {exc}')
