"""Source-backed operational monitoring; dates and measures retain their source scope."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALERT_NOTE = ("Solo se incluyen alertas con afectación documentada a instalaciones, acceso, continuidad o modalidad de atención de los servicios MTDH, registradas desde el 29 de septiembre de 2026. "
              "Se excluyen daños externos o a viviendas de familias usuarias sin impacto documentado en el servicio. Un código UA por sí solo no acredita afectación. "
              "La fecha corresponde al registro de la alerta; una alerta no equivale necesariamente a un evento único. "
              "El campo Afectados mezcla personas, familias y usuarios, por lo que no se presenta un total de personas únicas. "
              "La base no certifica atribución causal a ENOS.")
BONO_NOTE = ("La ayuda memoria no identifica pagos exclusivamente atribuibles a ENOS ni fechas individuales para recortar desde el 29/09. "
             "Se muestran únicamente las filas de inundación como referencia: pagos gestionados desde el 29/08 y casos en articulación al 23/10. "
             "Gestionado no acredita cobro; articulación no equivale a pago. Las proyecciones corresponden a planificación nacional 2026–2027.")
KIT_NOTE = "Entregas documentadas del 24 y 25 de octubre de 2026, corte 25/10 a las 19:00. No representan el acumulado desde el 29/09."
QUALITY_NOTE = ("Se revisaron Detalle y Acciones realizadas de cada alerta. Los casos sin evidencia de afectación al servicio no se incorporan a indicadores ni exportables.")
REFERENCE = "Ámbito: afectaciones a servicios MTDH y acciones institucionales de respuesta."

ALERT_COLUMNS = ['codigo','fecha','provincia','canton','estado','prioridad','codigo_ua','unidad',
                 'afectados_fuente','afectacion_servicio_confirmada','servicio','afectacion_servicio']


def snapshots():
    return sorted((ROOT/'data/processed').glob('seguimiento_enos_*.json'))


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    data['alertas'] = [r for r in data['alertas'] if r.get('afectacion_servicio_confirmada') is True]
    return data


def frames(data, provinces=()):
    result = {}
    for name, rows in [('alertas', data['alertas']), ('kits', data['kits']),
                       ('gestionados', data['bonos']['gestionados']), ('articulacion', data['bonos']['articulacion'])]:
        if name == 'alertas':
            rows = [r for r in rows if r.get('afectacion_servicio_confirmada') is True]
        columns = ALERT_COLUMNS if name == 'alertas' else ['fecha','provincia','canton','kits'] if name == 'kits' else ['provincia','evento','personas','monto']
        frame = pd.DataFrame(rows, columns=columns)
        if provinces:
            frame = frame.loc[frame.provincia.isin(provinces)]
        result[name] = frame.copy()
    return result


def summary(frame, group, value=None):
    result = frame.groupby(group)[value].sum() if value else frame.groupby(group).size()
    return [{'name': str(name), 'value': int(value)} for name, value in result.sort_values(ascending=False).items()]
