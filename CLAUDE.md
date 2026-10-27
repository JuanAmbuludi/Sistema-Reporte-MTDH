# Indicaciones para este repositorio

## Riesgos: lo reportado un día no se reescribe

- Cada día reportado de Riesgos es una publicación propia en `data/processed/`: `seguimiento_enos_AAAA-MM-DD.json` (alertas, kits, bono y sus alcances en `notas`) y `continuidad_servicios_AAAA-MM-DD.json` (unidades suspendidas). **Fecha del reporte** recupera la publicación guardada completa, con el alcance de sus propias fuentes. No reconstruya un día anterior recortando la base de hoy. Antes de la primera publicación guardada no hay reporte disponible.
- Datos de un día nuevo: ejecute primero `python scripts/nuevo_corte_riesgos.py AAAA-MM-DD` y cargue los cambios solo en los archivos de ese día (sus notas en `notas` y, si cambia el bono, `bonos_periodos_confirmados`). Mientras sea el último día publicado puede actualizarse; los días anteriores no se editan y `tests/test_riesgos_periodo.py` falla si cambia un día cerrado.
- Los cortes, periodos y textos de alcance se leen de cada publicación: no los escriba fijos en el código.
- El bono de contingencia en articulación es un acumulado confirmado: la selección de fecha no cambia sus personas ni sus montos. El filtro territorial sí aplica a su desglose provincial.
- El 26/10/2026 está conciliado con el PDF aprobado: 10 alertas, 13.390 kits, 1.171 personas, USD 354.987,39 y 99 unidades suspendidas. Su PDF original está en `data/reports/`, con SHA-256 en `pdf_publicado`. La exportación nacional histórica devuelve ese documento exacto; una selección territorial se genera desde los registros filtrados. El 27/10 conserva 39 alertas, 10.607 kits y los mismos valores de bono y unidades suspendidas, sin modificar su diseño.
