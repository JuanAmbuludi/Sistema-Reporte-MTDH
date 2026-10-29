"""Validate editable Excel registers before atomically replacing them in GitHub."""
from pathlib import Path
from tempfile import TemporaryDirectory

from src import enos, enos_excel as excel

FOLDER = 'data/enos_excel'


def row_keys(kind, rows):
    if kind in ('alertas', 'kits'):
        field = 'codigo' if kind == 'alertas' else 'id_kobo'
        return {excel._identifier(row[field]) for _, row in rows}
    if kind == 'unidades_suspendidas':
        return {(excel._date(row['corte_fuente'], 'corte_fuente'), excel._identifier(row['id_unidad'])) for _, row in rows}
    return {(excel._date(row['corte'], 'corte')[:10], excel._text(row['provincia']), excel._text(row['evento'])) for _, row in rows}


def build(snapshot, continuity, current_files, uploads):
    """Return only replacement XLSX bytes and an audit. Never rewrite issued JSON."""
    if set(current_files) != set(excel.FILES):
        raise ValueError('Se requieren las cuatro bases Excel actuales para validar una actualización.')
    if not uploads or not set(uploads).issubset(excel.FILES):
        raise ValueError('Use las plantillas de data/enos_excel: alertas, kits, unidades suspendidas o contingencias.')
    with TemporaryDirectory(prefix='enos_excel_') as temporary:
        processed = Path(temporary) / 'data/processed'
        folder = excel.directory(processed)
        folder.mkdir(parents=True)
        for kind, content in current_files.items():
            (folder / excel.FILES[kind]).write_bytes(content)
        before = excel.overlay(snapshot, processed)
        excel.observations(processed, continuity)
        originals = {kind: excel.read(processed, kind) for kind in excel.FILES}
        for kind, (_name, content) in uploads.items():
            (folder / excel.FILES[kind]).write_bytes(content)
        # Validate whole workbooks, not cached summary cells or only uploaded rows.
        after = excel.overlay(snapshot, processed)
        after_units = excel.observations(processed, continuity)[-1]
        for kind in uploads:
            cut, _, rows = excel.read(processed, kind)
            old_cut, _, old_rows = originals[kind]
            if cut < old_cut:
                raise ValueError(f'{excel.FILES[kind]}: el corte retrocede. Descargue la versión vigente.')
            missing = row_keys(kind, old_rows) - row_keys(kind, rows)
            if missing:
                raise ValueError(f'{excel.FILES[kind]}: faltan {len(missing)} filas ya registradas. '
                                 'Conserve los identificadores y cortes anteriores; use incluir=No o Reanudada según corresponda.')
        cuts = [excel.read(processed, kind)[0][:10] for kind in excel.FILES]
    since, until = snapshot.get('desde', enos.START), max(cuts)
    active = [r for r in after['alertas'] if since <= r['fecha'] <= until]
    previous_ids = {r['codigo'] for r in before['alertas']}
    current_ids = {r['codigo'] for r in after['alertas']}
    old_kits = {r['id_kobo'] for r in before['kits']}
    coincidences = {}
    for row in active:
        if row.get('codigo_ua'):
            coincidences.setdefault((row['codigo_ua'], row['fecha']), set()).add(row['codigo'])
    audit = {
        'desde': since, 'hasta': until, 'formato_excel': True,
        'alertas_historico': len(after['alertas']), 'alertas_periodo_codigo': len(active),
        'alertas_periodo_con_criterio': sum(enos.included(r, after) for r in active),
        'nuevos_codigos_historico': len(current_ids - previous_ids),
        'coincidencias_ua_fecha': [{'ua': ua, 'fecha': when, 'cantidad_codigos': len(ids)}
                                 for (ua, when), ids in coincidences.items() if len(ids) > 1],
        'kits_historico': sum(r['kits'] for r in after['kits']),
        'kits_periodo': sum(r['kits'] for r in after['kits'] if since <= r['fecha'] <= until),
        'nuevos_ids_kobo': len({r['id_kobo'] for r in after['kits']} - old_kits),
        'unidades_suspendidas': len(after_units['detalle']),
        'cobertura_suspendida': sum(r['cobertura'] for r in after_units['detalle']),
        'corte_unidades': after_units['corte'],
        'bonos_sin_modificar': after['bonos'] == before['bonos'],
        'brigadas_sin_modificar': after.get('brigadas') == before.get('brigadas'),
        'contingencias_autorizadas': 'contingencias' in uploads,
        'nucleos_habilitados': sum(r['personas'] for r in after['bonos']['articulacion']),
        'monto_habilitado': round(sum(r['monto'] for r in after['bonos']['articulacion']), 2),
        'nucleos_cobrados': sum(r['personas'] for r in after['bonos']['gestionados']),
        'monto_cobrado': round(sum(r['monto'] for r in after['bonos']['gestionados']), 2),
    }
    changes = {f'{FOLDER}/{excel.FILES[kind]}': content for kind, (_, content) in uploads.items()
               if content != current_files[kind]}
    return changes, {'auditoria': audit, 'archivos': list(changes)}
