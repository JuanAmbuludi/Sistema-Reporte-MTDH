"""Excel reconciliation protects identities, stock cuts and collected balances."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src import enos, enos_excel as excel
from scripts.ingesta_enos_excel import build


class ExcelRegisters(unittest.TestCase):
    def setUp(self):
        self.alert = dict(codigo='A1', fecha='2026-10-28', provincia='Guayas', canton='Balao',
            estado='Pendiente', prioridad='Alta', tipo_alerta='Emergencia', codigo_ua='001',
            unidad='Unidad', servicio='CDI', afectados_fuente=0,
            afectacion_servicio_confirmada=None, afectacion_servicio='', incluir='Sí')
        self.kit = dict(id_kobo='K1', fecha='2026-10-28', provincia='Guayas', canton='Balao', kits=7, familias=6, incluir='Sí')
        self.unit = dict(id_unidad='U1', corte_fuente='2026-10-28', provincia='Guayas', canton='Balao',
            parroquia='Balao', unidad='Unidad', codigo_ua='001', servicio='CDI', modalidad='CDI',
            programa_id='DII', estado='Suspendida', cobertura=40)
        self.bonus = dict(corte='2026-10-28', provincia='Guayas', evento='Todos los eventos',
            nucleos_habilitados=10, monto_habilitado=3000, nucleos_cobrados=2, monto_cobrado=600)
        self.data = dict(alertas=[{**{k:v for k,v in self.alert.items() if k != 'incluir'},
                                  'origen':'reporte_sectorial', 'fuente':'fuente previa', 'revision':'conservar'}],
            kits=[{k:v for k,v in self.kit.items() if k != 'incluir'}],
            bonos={'articulacion':[dict(provincia='Guayas', evento='Todos los eventos', personas=10, monto=3000)],
                   'gestionados':[], 'planificacion':{}}, cortes={}, notas={}, brigadas=[])
        self.rows = dict(alertas=[self.alert], kits=[self.kit], unidades_suspendidas=[self.unit], contingencias=[self.bonus])

    def read(self, _processed, kind):
        return '2026-11-01', {}, list(enumerate(deepcopy(self.rows[kind]), 2))

    def overlay(self):
        with patch.object(excel, 'read', side_effect=self.read):
            return excel.overlay(self.data, enos.FOLDER)

    def units(self):
        with patch.object(excel, 'read', side_effect=self.read):
            return excel.observations(enos.FOLDER)

    def test_update_alert_in_place_preserves_optional_metadata(self):
        self.alert['estado'] = 'Resuelto'
        result = self.overlay()
        self.assertEqual(len(result['alertas']), 1)
        self.assertEqual(result['alertas'][0]['estado'], 'Resuelto')
        self.assertEqual(result['alertas'][0]['revision'], 'conservar')
        self.assertEqual(self.data['alertas'][0]['estado'], 'Pendiente')

    def test_new_ids_append_once_and_explicit_exclusion_does_not_revive_old_row(self):
        self.rows['alertas'].append({**self.alert, 'codigo':'A2'})
        self.alert['incluir'] = 'No'
        self.rows['kits'].append({**self.kit, 'id_kobo':'K2', 'kits':3})
        result = self.overlay()
        self.assertEqual([r['codigo'] for r in result['alertas']], ['A2'])
        self.assertEqual(sum(r['kits'] for r in result['kits']), 10)

    def test_revised_kit_replaces_quantity_instead_of_accumulating(self):
        self.kit['kits'] = 9
        self.assertEqual([r['kits'] for r in self.overlay()['kits']], [9])

    def test_duplicate_identifiers_are_rejected(self):
        for kind in ('alertas', 'kits', 'contingencias'):
            with self.subTest(kind=kind):
                self.rows[kind].append(deepcopy(self.rows[kind][0]))
                with self.assertRaisesRegex(ValueError, 'duplicado'):
                    self.overlay()
                self.rows[kind].pop()

    def test_missing_history_is_rejected(self):
        self.rows['kits'] = []
        with self.assertRaisesRegex(ValueError, 'histórico'):
            self.overlay()

    def test_missing_or_negative_count_is_not_zero(self):
        for invalid in (None, -1, 1.5, True):
            with self.subTest(value=invalid):
                self.kit['kits'] = invalid
                with self.assertRaises(ValueError):
                    self.overlay()
        self.kit['kits'] = 0
        self.assertEqual(self.overlay()['kits'][0]['kits'], 0)

    def test_source_cut_cannot_precede_record(self):
        self.kit['fecha'] = '2026-11-02'
        with self.assertRaisesRegex(ValueError, 'supera el corte'):
            self.overlay()

    def test_contingency_uses_latest_balance_without_summing_cuts(self):
        self.rows['contingencias'].append({**self.bonus, 'corte':'2026-10-30',
            'nucleos_habilitados':12, 'monto_habilitado':3600, 'nucleos_cobrados':3, 'monto_cobrado':900})
        result = self.overlay()
        self.assertEqual(result['bonos']['articulacion'][0]['personas'], 12)
        self.assertEqual(result['bonos']['gestionados'][0]['monto'], 900)
        self.assertTrue(result['bonos_presentacion']['cobro_confirmado'])

    def test_contingency_rejects_overpayment_rounding_and_total_detail_mix(self):
        for field, value in [('monto_cobrado',3001), ('nucleos_cobrados',11), ('monto_cobrado',1.001)]:
            previous = self.bonus[field]
            self.bonus[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.overlay()
            self.bonus[field] = previous
        self.rows['contingencias'].append({**self.bonus, 'evento':'Inundación'})
        with self.assertRaisesRegex(ValueError, 'duplicaría'):
            self.overlay()

    def test_excel_binary_residues_are_normalized_to_cents(self):
        for raw, expected in [(23711.220000000023, 23711.22),
                              (53923.3200000001, 53923.32),
                              (98801.49000000028, 98801.49),
                              (2127.9300000000003, 2127.93), (0.1 + 0.2, 0.30)]:
            with self.subTest(raw=raw):
                self.assertEqual(excel._number(raw, 'monto'), expected)
        for raw in [1.001, 1.999, '1.00000001']:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'dos decimales'):
                excel._number(raw, 'monto')

    def test_new_inventory_uses_full_stock_and_reopened_units_are_zero(self):
        self.rows['unidades_suspendidas'].append({**self.unit, 'corte_fuente':'2026-10-30', 'estado':'Reanudada'})
        observations = self.units()
        self.assertEqual([len(x['detalle']) for x in observations], [1, 0])
        self.assertEqual(observations[-1]['validacion']['cobertura_total'], 0)
        with patch.object(enos, 'publications', return_value=[]), patch.object(enos, '_editable_observations', return_value=observations):
            self.assertEqual(len(enos.continuity_at('2026-10-29')['detalle']), 1)
            self.assertEqual(enos.continuity_at('2026-10-30')['detalle'], [])
            self.assertFalse(enos.continuity_at('2026-10-27')['disponible'])

    def test_new_inventory_must_retain_prior_ids_and_not_duplicate_units(self):
        self.rows['unidades_suspendidas'].append({**self.unit, 'corte_fuente':'2026-10-30', 'id_unidad':'U2'})
        with self.assertRaisesRegex(ValueError, 'dos identificadores'):
            self.units()
        self.rows['unidades_suspendidas'][-1]['corte_fuente'] = '2026-10-28'
        with self.assertRaisesRegex(ValueError, 'dos identificadores'):
            self.units()

    def test_partial_reopening_keeps_unchanged_units_in_the_stock(self):
        self.rows['unidades_suspendidas'].append({**self.unit, 'id_unidad':'U2', 'unidad':'Otra unidad'})
        self.rows['unidades_suspendidas'].append({**self.unit, 'corte_fuente':'2026-10-30', 'estado':'Reanudada'})
        observations = self.units()
        self.assertEqual([len(r['detalle']) for r in observations], [2, 1])
        self.assertEqual(observations[-1]['detalle'][0]['unidad'], 'Otra unidad')

    def test_partial_provincial_balance_does_not_remove_other_provinces(self):
        self.rows['contingencias'].append({**self.bonus, 'provincia':'El Oro'})
        self.rows['contingencias'].append({**self.bonus, 'corte':'2026-10-30', 'nucleos_habilitados':12})
        result = self.overlay()
        self.assertEqual({r['provincia']:r['personas'] for r in result['bonos']['articulacion']}, {'Guayas':12,'El Oro':10})

    def test_only_part_of_excel_database_cannot_silently_fall_back(self):
        with TemporaryDirectory() as tmp:
            processed = Path(tmp) / 'processed'
            excel.directory(processed).mkdir()
            (excel.directory(processed) / 'kits.xlsx').touch()
            with self.assertRaisesRegex(ValueError, 'incompleta'):
                excel.paths(processed)


class RealWorkbooks(unittest.TestCase):
    def test_publication_stamp_changes_only_current_history_metadata(self):
        with patch.object(excel, 'updated_at', return_value=None):
            previous = enos.history(live=True)
        with patch.object(excel, 'updated_at', return_value='2026-10-30T02:26:51+00:00'):
            current = enos.history(live=True)
        self.assertEqual(current['generado_utc'], '2026-10-30T02:26:51+00:00')
        current['generado_utc'] = previous['generado_utc']
        self.assertEqual(current, previous)
        self.assertNotEqual(enos.load(enos.in_force(enos.SNAPSHOT)[0])['generado_utc'], '2026-10-30T02:26:51+00:00')

    def test_stale_stamp_is_not_assigned_to_different_excel_bytes(self):
        with TemporaryDirectory() as temporary:
            processed = Path(temporary) / 'data/processed'
            folder = excel.directory(processed)
            folder.mkdir(parents=True)
            hashes = {}
            for name in excel.FILES.values():
                binary = (excel.directory(enos.FOLDER) / name).read_bytes()
                (folder / name).write_bytes(binary)
                hashes[name] = hashlib.sha256(binary).hexdigest()
            metadata = {'generado_utc':'2026-10-30T02:26:51+00:00', 'archivos':hashes}
            stamp = folder / excel.STAMP
            stamp.write_text(json.dumps(metadata))
            self.assertEqual(excel.updated_at(processed), metadata['generado_utc'])
            metadata['archivos']['kits.xlsx'] = 'obsolete'
            stamp.write_text(json.dumps(metadata))
            self.assertIsNone(excel.updated_at(processed))

    def test_current_workbooks_are_typed_and_validate_without_changes(self):
        current = {kind:(excel.directory(enos.FOLDER) / name).read_bytes() for kind,name in excel.FILES.items()}
        snapshot = enos.load(enos.in_force(enos.SNAPSHOT)[0])
        continuity = enos.continuity()
        changes, report = build(snapshot, continuity, current, {kind:(excel.FILES[kind], blob) for kind,blob in current.items()})
        self.assertEqual(changes, {})
        self.assertTrue(report['auditoria']['bonos_sin_modificar'])
        self.assertTrue(report['auditoria']['brigadas_sin_modificar'])
        for kind in excel.FILES:
            _, control, rows = excel.read(enos.FOLDER, kind)
            self.assertEqual(excel.read(enos.FOLDER, kind)[0], max(excel._date(row[{'alertas':'fecha','kits':'fecha','unidades_suspendidas':'corte_fuente','contingencias':'corte'}[kind]],'fecha') for _,row in rows))
            self.assertTrue(rows)
        self.assertTrue(set(excel.paths(enos.FOLDER)).issubset(enos.history_paths()))

    def test_archived_sources_remain_read_only(self):
        before = {path:enos.fingerprint(path) for path in enos.history_paths()}
        enos.history()
        enos.continuity_at('2099-01-01')
        self.assertEqual(before, {path:enos.fingerprint(path) for path in before})


class PublishedSafety(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.processed = Path(self.temporary.name) / 'data/processed'
        self.processed.mkdir(parents=True)
        self.folder = excel.directory(self.processed)
        self.folder.mkdir()
        for name in excel.FILES.values():
            (self.folder / name).write_bytes((excel.directory(enos.FOLDER) / name).read_bytes())
        self.data = enos.history(live=True)
        self.observations = enos._editable_observations(live=True)
        self.publication = {'formato':'ENOS_VALIDADO_1','datos':self.data,'observaciones':self.observations,
                            'fuentes':excel.source_hashes(self.processed),'identificadores':excel.registry_ids(self.processed)}
        self.save()

    def save(self):
        (self.folder / excel.VALIDATED).write_bytes(gzip.compress(json.dumps(self.publication).encode(),mtime=0))

    def test_validated_data_are_unchanged_when_inputs_match(self):
        with patch.object(enos, 'FOLDER', self.processed):
            self.assertEqual(enos.history(), self.data)
        self.assertFalse(excel.published(self.processed)['pendiente'])

    def test_broken_excel_keeps_previous_counts_and_shows_pending_validation(self):
        (self.folder / 'kits.xlsx').write_bytes(b'corrupted upload')
        with patch.object(enos, 'FOLDER', self.processed):
            shown = enos.history()
            self.assertTrue(shown.pop('carga_pendiente'))
            self.assertEqual(shown, self.data)
            self.assertEqual(enos.continuity_at(self.data['corte']), self.observations[-1])
            enos.history_paths()  # export cache can still be computed

    def test_deleted_excel_keeps_last_valid_publication_available(self):
        (self.folder / 'unidades_suspendidas.xlsx').unlink()
        with patch.object(enos, 'FOLDER', self.processed):
            self.assertTrue(enos.history()['carga_pendiente'])
            enos.history_paths()

    def test_identifiers_added_after_migration_cannot_silently_disappear(self):
        self.publication['identificadores']['kits'].append('PREVIOUSLY-VALIDATED-ID')
        self.save()
        with self.assertRaisesRegex(ValueError, 'identificadores'):
            excel.check_retention(self.processed)


if __name__ == '__main__':
    unittest.main()
