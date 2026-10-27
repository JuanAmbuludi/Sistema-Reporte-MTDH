from src import enos
from src.views.respuesta import Response


def test_sectorial_alerts_extend_the_register_without_inventing_units_or_dates():
    data = enos.load(enos.snapshots()[-1])
    r = Response(data)
    assert len(r.alerts) == r.alerts.codigo.nunique() == 21
    sectorial = r.alerts.loc[r.alerts.origen.eq("reporte_sectorial")]
    assert len(sectorial) == 11 and sectorial.codigo_ua.eq("").all()
    assert not sectorial.afectacion_servicio_confirmada.any()
    # Every report has its date: the gerontological ones, 26/10/2026 (date of report given by the person in charge).
    assert sectorial.fecha.notna().all()
    assert set(sectorial.loc[sectorial.servicio.eq("Centros gerontológicos"), "fecha"]) == {"2026-10-26"}
    assert r.units == 10 and r.closed_units == 99
    assert len(Response(data, programs=["PAM_SERV"]).alerts) == 6
    assert len(Response(data, programs=["PCD_SERV"]).alerts) == 5
    assert r.kits_total == 13390
    assert round(r.managed.monto.sum(), 2) == 33200.80
