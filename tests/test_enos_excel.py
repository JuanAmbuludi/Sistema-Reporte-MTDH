"""Excel reconciliation protects identities, stock cuts and collected balances."""
from copy import deepcopy
from datetime import datetime
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
        with self.assertRaisesRegex(ValueError, 'incompleto'):
            self.units()
        self.rows['unidades_suspendidas'][-1]['corte_fuente'] = '2026-10-28'
        with self.assertRaisesRegex(ValueError, 'duplicado'):
            self.units()

    def test_only_part_of_excel_database_cannot_silently_fall_back(self):
        with TemporaryDirectory() as tmp:
            processed = Path(tmp) / 'processed'
            excel.directory(processed).mkdir()
            (excel.directory(processed) / 'kits.xlsx').touch()
            with self.assertRaisesRegex(ValueError, 'incompleta'):
                excel.paths(processed)


class RealWorkbooks(unittest.TestCase):
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
            self.assertIsInstance(control['corte'], datetime)
            self.assertTrue(rows)
        self.assertTrue(set(excel.paths(enos.FOLDER)).issubset(enos.history_paths()))

    def test_archived_sources_remain_read_only(self):
        before = {path:enos.fingerprint(path) for path in enos.history_paths()}
        enos.history()
        enos.continuity_at('2099-01-01')
        self.assertEqual(before, {path:enos.fingerprint(path) for path in before})


if __name__ == '__main__':
    unittest.main()
