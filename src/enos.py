"""Source-backed operational monitoring; dates and measures retain their source scope."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALERT_NOTE = ("Alertas de desastre natural registradas desde el 29 de septiembre de 2026. "
              "La fecha corresponde al registro de la alerta; una alerta no equivale necesariamente a un evento único. "
              "El campo Afectados mezcla personas, familias y usuarios, por lo que no se presenta un total de personas únicas. "
              "La base no certifica atribución causal a ENOS.")
BONO_NOTE = ("La ayuda memoria no identifica pagos exclusivamente atribuibles a ENOS ni fechas individuales para recortar desde el 29/09. "
             "Se muestran únicamente las filas de inundación como referencia: pagos gestionados desde el 29/08 y casos en articulación al 23/10. "
             "Gestionado no acredita cobro; articulación no equivale a pago. Las proyecciones corresponden a planificación nacional 2026–2027.")
KIT_NOTE = "Entregas documentadas del 24 y 25 de octubre de 2026, corte 25/10 a las 19:00. No representan el acumulado desde el 29/09."
QUALITY_NOTE = ("Se usó la hoja Detalle: los resúmenes del Excel abarcan otras fechas y categorías. "
                "El registro ALT-2026-000301 consigna Nobol, pero su descripción menciona Balao; se conserva el territorio de la fuente, pendiente de validación.")
REFERENCE = ("Estructura de referencia: reporte de monitoreo N.º 0044 del Ministerio de Educación, Deporte y Cultura, 25/10/2026. "
             "Sus cifras educativas y su pronóstico con vigencia hasta el 25/10 no se incorporan a los resultados del MTDH.")


def snapshots():
    return sorted((ROOT/'data/processed').glob('seguimiento_enos_*.json'))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def frames(data, provinces=()):
    result = {}
    for name, rows in [('alertas', data['alertas']), ('kits', data['kits']),
                       ('gestionados', data['bonos']['gestionados']), ('articulacion', data['bonos']['articulacion'])]:
        frame = pd.DataFrame(rows)
        if provinces:
            frame = frame.loc[frame.provincia.isin(provinces)]
        result[name] = frame.copy()
    return result


def summary(frame, group, value=None):
    result = frame.groupby(group)[value].sum() if value else frame.groupby(group).size()
    return [{'name': str(name), 'value': int(value)} for name, value in result.sort_values(ascending=False).items()]
