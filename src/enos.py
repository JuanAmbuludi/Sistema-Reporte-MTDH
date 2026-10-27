"""Source-backed operational monitoring; dates and measures retain their source scope."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALERT_NOTE = ("Seguimiento desde el 14/09/2026, complementado con reportes sectoriales de octubre. "
              "Los reportes gerontológicos utilizan su fecha de reporte. Los identificadores DIS/GER/DII permiten localizar las filas incorporadas; no son códigos oficiales ni códigos UA. "
              "Los registros repetidos de la base consolidada se cuentan una sola vez. Alertas, unidades y personas son medidas distintas.")
BONO_NOTE = ("Bono en articulación actualizado con la tabla provincial remitida el 27/10/2026: inundación, colapso estructural y vendaval. "
             "Pagos gestionados: ayuda memoria del 23/10, desde el 29/08. Articulación no equivale a pago. "
             "Las proyecciones corresponden a planificación nacional 2026–2027.")
KIT_NOTE = ("Kits en provincias priorizadas: Kobo, corte 27/10/2026, 13:35:45. Entregas del 31/08 al 27/10; reemplaza el corte anterior. "
            "13.981 kits reportados en 111 registros. Núcleos familiares: suma por entrega, no núcleos únicos. "
            "El registro de Cañar declara 1 kit, pero su observación indica una solicitud no recibida; pendiente de validación territorial.")
QUALITY_NOTE = ""

START = "2026-09-14"   # start of the follow-up: alerts registered from this date
REFERENCE = "Ámbito: alertas y reportes sectoriales y acciones institucionales de respuesta."

ALERT_COLUMNS = ['codigo','fecha','provincia','canton','estado','prioridad','codigo_ua','unidad',
                 'afectados_fuente','afectacion_servicio_confirmada','servicio','afectacion_servicio','origen','fecha_texto','mes_reporte']


def snapshots():
    return sorted((ROOT/'data/processed').glob('seguimiento_enos_*.json'))


def included(row, data):
    if row.get("origen") == "reporte_sectorial" and data.get("criterio_alertas") == "codigo_ua_y_reportes_sectoriales":
        return bool(row.get("fuente")) and bool(row.get("servicio"))
    if data.get("criterio_alertas") in ("codigo_ua", "codigo_ua_y_reportes_sectoriales"):
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
        columns = ALERT_COLUMNS if name == 'alertas' else ['fecha','provincia','canton','kits','familias','id_kobo'] if name == 'kits' else ['provincia','evento','personas','monto']
        frame = pd.DataFrame(rows, columns=columns)
        if name == 'alertas':
            dates = pd.to_datetime(frame.fecha, errors='coerce')
            frame = frame.loc[dates.between(pd.Timestamp(data['desde']), pd.Timestamp(data['corte'])) | frame.origen.eq("reporte_sectorial")]
        if provinces:
            frame = frame.loc[frame.provincia.isin(provinces)]
        result[name] = frame.copy()
    return result


def summary(frame, group, value=None):
    result = frame.groupby(group)[value].sum() if value else frame.groupby(group).size()
    return [{'name': str(name), 'value': int(value)} for name, value in result.sort_values(ascending=False).items()]


CONTINUITY_PATH = ROOT / "data/processed/continuidad_servicios_2026-10-26.json"
CONTINUITY_NOTE = "Unidades con suspensión reportada al 26/10/2026, 16:00. Este indicador corresponde a ese corte territorial."

def continuity():
    return json.loads(CONTINUITY_PATH.read_text(encoding="utf-8"))
