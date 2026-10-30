"""The dated replacement reconciles source totals and inclusive period filters."""
from copy import deepcopy
import unittest
from src import enos


class DatedContingencies(unittest.TestCase):
    def test_source_totals_and_inclusive_dates(self):
        data = enos.history(live=True)
        self.assertTrue(data['bonos_con_fecha_individual'])
        self.assertEqual(len(data['bonos_detalle']), 32)
        self.assertEqual(sum(r['personas'] for r in data['bonos']['gestionados']), 692)
        self.assertAlmostEqual(sum(r['monto'] for r in data['bonos']['gestionados']), 209776.23)
        for start, end, count, amount in [
            ('2026-09-25','2026-10-29',1720,521322.45),
            ('2026-09-28','2026-10-29',1719,521019.51),
            ('2026-10-29','2026-10-29',15,4559.85),
            ('2026-10-28','2026-10-28',528,159952.32),
            ('2026-09-01','2026-09-24',0,0),
        ]:
            with self.subTest(start=start, end=end):
                selected = deepcopy(data)
                selected.update(desde=start, corte=end)
                frame = enos.frames(selected)['articulacion']
                self.assertEqual(frame.personas.sum(), count)
                self.assertAlmostEqual(frame.monto.sum(), amount)
                self.assertIn('fecha', frame)
                self.assertIn('canton', frame)

    def test_closed_publication_still_uses_original_balance(self):
        data = enos.load(enos.FOLDER / 'seguimiento_enos_2026-10-26.json')
        self.assertFalse(data.get('bonos_con_fecha_individual', False))
        self.assertTrue(enos.fixed_bonus(data, 'articulacion'))
        self.assertEqual(sum(r['personas'] for r in data['bonos']['articulacion']), 1171)


if __name__ == '__main__':
    unittest.main()
