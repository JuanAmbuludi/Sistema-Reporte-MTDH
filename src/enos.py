"""Source-backed operational monitoring; dates and measures retain their source scope."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ALERT_NOTE = ("Seguimiento desde el 28/09/2026, complementado con reportes sectoriales de octubre. "
              "Los reportes gerontológicos utilizan su fecha de reporte. Los identificadores DIS/GER/DII permiten localizar las filas incorporadas; no son códigos oficiales ni códigos UA. "
              "Los registros repetidos de la base consolidada se cuentan una sola vez. Alertas, unidades y personas son medidas distintas.")
BONO_NOTE = "Bono en articulación: 1.171 personas y USD 354.987,39 correspondientes al período 28/09–27/10/2026. Los bonos gestionados no cuentan con desglose temporal para este período. Las proyecciones son una referencia de planificación."
KIT_NOTE = ("Kits en provincias priorizadas: entregas desde el 28/09/2026 hasta el corte Kobo del 27/10/2026, 13:35:45. "
            "El registro de Cañar declara 1 kit, pero su observación indica una solicitud no recibida; pendiente de validación territorial.")
QUALITY_NOTE = ""

START = "2026-09-28"   # start of the follow-up: alerts registered from this date
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


def period_confirmed(data, stage):
    period = data.get('bonos_periodos_confirmados', {}).get(stage, {})
    return bool(period.get('confirmacion') and period.get('desde') and period.get('hasta')
                and data['desde'] <= period['desde'] <= period['hasta'] <= data['corte'])


def frames(data, provinces=()):
    result = {}
    for name, rows in [('alertas', data['alertas']), ('kits', data['kits']),
                       ('gestionados', data['bonos']['gestionados']), ('articulacion', data['bonos']['articulacion'])]:
        if name == 'alertas':
            rows = [r for r in rows if included(r, data)]
        columns = ALERT_COLUMNS if name == 'alertas' else ['fecha','provincia','canton','kits','familias','id_kobo'] if name == 'kits' else ['provincia','evento','personas','monto']
        frame = pd.DataFrame(rows, columns=columns)
        if name in ('alertas', 'kits'):
            dates = pd.to_datetime(frame.fecha, errors='coerce')
            frame = frame.loc[dates.between(pd.Timestamp(data['desde']), pd.Timestamp(data['corte']))]
        elif data.get('filtro_temporal_estricto') and not period_confirmed(data, name):
            dates = pd.to_datetime(pd.Series([r.get('fecha') for r in rows], index=frame.index), errors='coerce')
            frame = frame.loc[dates.between(pd.Timestamp(data['desde']), pd.Timestamp(data['corte']))]
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
