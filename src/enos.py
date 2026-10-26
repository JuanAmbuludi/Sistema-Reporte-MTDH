"""Source-backed operational monitoring; dates and measures retain their source scope."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALERT_NOTE = ("Se muestran únicamente alertas revisadas con código UA registrado, desde el 14 de septiembre de 2026. "
              "El conteo corresponde a códigos de alerta distintos vinculados a unidades identificadas. "
              "Los registros sin código quedan fuera de este alcance. La fecha corresponde al registro y una alerta no equivale necesariamente a un evento único. "
              "El campo Afectados mezcla personas, familias y usuarios; no se suma como personas únicas. La base no certifica atribución causal a ENOS.")
BONO_NOTE = ("La ayuda memoria no identifica pagos exclusivamente atribuibles a ENOS ni fechas individuales para recortar desde el 14/09. "
             "Se muestran únicamente las filas de inundación como referencia: pagos gestionados desde el 29/08 y casos en articulación al 23/10. "
             "Articulación no equivale a pago. Las proyecciones corresponden a planificación nacional 2026–2027.")
KIT_NOTE = "Kits entregados en provincias priorizadas el 24–25/10/2026; corte 25/10, 19:00. No es el acumulado desde el 14/09."
QUALITY_NOTE = ("En el corte nacional hay 10 alertas con 10 códigos UA distintos: 8 con afectación documentada y 2 por confirmar. "
                "ALT-2026-000315 y ALT-2026-000316 (Tenguel) tienen código UA, pero el relato solo describe inundación territorial; "
                "no se presentan como daños confirmados al servicio.")
START = "2026-09-14"   # start of the follow-up: alerts registered from this date
REFERENCE = "Ámbito: alertas con código UA y acciones institucionales de respuesta."

ALERT_COLUMNS = ['codigo','fecha','provincia','canton','estado','prioridad','codigo_ua','unidad',
                 'afectados_fuente','afectacion_servicio_confirmada','servicio','afectacion_servicio']


def snapshots():
    return sorted((ROOT/'data/processed').glob('seguimiento_enos_*.json'))


def included(row, data):
    if data.get("criterio_alertas") == "codigo_ua":
        return (str(row.get("codigo_ua", "")).strip() not in ("", "—", "-", "nan", "None")
                and isinstance(row.get("afectacion_servicio_confirmada"), bool) and bool(row.get("servicio")))
    return row.get("afectacion_servicio_confirmada") is True


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    data['alertas'] = [r for r in data['alertas'] if included(r, data)]
    return data


def frames(data, provinces=()):
    result = {}
    for name, rows in [('alertas', data['alertas']), ('kits', data['kits']),
                       ('gestionados', data['bonos']['gestionados']), ('articulacion', data['bonos']['articulacion'])]:
        if name == 'alertas':
            rows = [r for r in rows if included(r, data)]
        columns = ALERT_COLUMNS if name == 'alertas' else ['fecha','provincia','canton','kits'] if name == 'kits' else ['provincia','evento','personas','monto']
        frame = pd.DataFrame(rows, columns=columns)
        if name == 'alertas':
            dates = pd.to_datetime(frame.fecha, errors='coerce')
            frame = frame.loc[dates.between(pd.Timestamp(data['desde']), pd.Timestamp(data['corte']))]
        if provinces:
            frame = frame.loc[frame.provincia.isin(provinces)]
        result[name] = frame.copy()
    return result


def summary(frame, group, value=None):
    result = frame.groupby(group)[value].sum() if value else frame.groupby(group).size()
    return [{'name': str(name), 'value': int(value)} for name, value in result.sort_values(ascending=False).items()]


CONTINUITY_PATH = ROOT / "data/processed/continuidad_servicios_2026-10-26.json"
CONTINUITY_NOTE = ("Fuente: base territorial de afectaciones por lluvias, corte 26/10/2026, 16:00. "
                   "Cerradas corresponde al estado Suspendida (18 CDI y 1 CNH). Los 63 CNH con suspensión presencial "
                   "y los 11 CDI en atención virtual se muestran por separado. Son cifras reportadas, sin códigos UA "
                   "en esta base; no se suman a las 10 alertas ni constituyen un censo nacional de cierres.")

def continuity():
    return json.loads(CONTINUITY_PATH.read_text(encoding="utf-8"))
