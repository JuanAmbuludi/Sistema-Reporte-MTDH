"""Historical monthly source integration keeps published observations authoritative."""
import json
from pathlib import Path

import pandas as pd

from scripts.integrar_vis_vie_historico import append_missing
from src import depuracion, mensual

SERIES = Path(__file__).resolve().parents[1] / 'data' / 'series'


def test_append_missing_keeps_deduplicated_observation_and_is_idempotent():
    current = pd.DataFrame({'periodo': ['2026-09'], 'usuarios_unicos': [453994]})
    incoming = pd.DataFrame({'periodo': ['2023-11', '2026-09'], 'usuarios_unicos': [464140, 456353]})
    combined = append_missing(current, incoming)
    assert combined.usuarios_unicos.tolist() == [453994, 464140]
    pd.testing.assert_frame_equal(append_missing(combined, incoming), combined)


def test_imported_months_are_identified_and_retired_pensions_remain_available():
    metadata = json.loads((SERIES / 'integracion_vis_vie_historico.json').read_text())
    for name in ['VIS', 'VIE']:
        source = metadata['fuentes'][name]
        assert (source['desde'], source['hasta'], source['meses']) == ('2023-11', '2026-09', 35)
        assert len(metadata['series'][name]['meses_incorporados']) == 26
        assert len(metadata['series'][name]['meses_existentes_conservados']) == 9
    current = mensual.coverage()
    historic = current.loc[current.periodo_id.eq('2023-11') & current.nivel.eq('provincia')]
    assert historic.loc[historic.programa_id.isin(['PAM', 'PCD']), 'usuarios'].sum() > 0
    assert historic.loc[historic.seccion.eq('bonos_pensiones'), 'usuarios'].sum() == 1434699
    assert historic.loc[historic.seccion.eq('proteccion_integral'), 'usuarios'].sum() == 464140


def test_obsolete_canton_with_null_parish_can_be_logged_without_losing_counts():
    row = dict(periodo='2023-11', nivel_territorial='Cantón', codigo_territorio='0808',
               codigo_provincia='23', provincia='SANTO DOMINGO DE LOS TSACHILAS',
               codigo_canton='0808', canton='LA CONCORDIA', codigo_parroquia=None,
               parroquia=None, codigo_ambiguo=True, beneficiarios_unicos=9, registros=9)
    clean, log = depuracion.clean_codes(pd.DataFrame([row]), ['beneficiarios_unicos', 'registros'])
    assert clean.codigo_territorio.tolist() == ['2302']
    assert clean.beneficiarios_unicos.sum() == log.beneficiarios_unicos.sum() == 9
    assert log.codigo_destino.tolist() == ['2302']
