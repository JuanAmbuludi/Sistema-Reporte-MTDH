# Indicaciones para este repositorio

## Riesgos: lo reportado un día no se reescribe

- Cada día reportado de Riesgos es una publicación propia en `data/processed/`: `seguimiento_enos_AAAA-MM-DD.json` (alertas, kits, bono y sus alcances en `notas`) y `continuidad_servicios_AAAA-MM-DD.json` (unidades suspendidas). El filtro **Desde / Hasta** del tablero y de los exportables elige la publicación vigente en la fecha final, así que reproduce lo reportado cualquier día.
- Datos de un día nuevo: ejecute primero `python scripts/nuevo_corte_riesgos.py AAAA-MM-DD` y cargue los cambios solo en los archivos de ese día (sus notas en `notas` y, si cambia el bono, `bonos_periodos_confirmados`). Mientras sea el último día publicado puede actualizarse; los días anteriores no se editan y `tests/test_riesgos_periodo.py` falla si cambia un día cerrado.
- Los cortes, periodos y textos de alcance se leen de cada publicación: no los escriba fijos en el código.
