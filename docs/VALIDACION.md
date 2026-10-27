# Validación de la actualización de datos

Revisión del 26 de octubre de 2026 (Ecuador). Véase [ACTUALIZACION_DATOS.md](ACTUALIZACION_DATOS.md) para decisiones, comparación y límites de las fuentes, y [REVISION_BASES_2026.md](REVISION_BASES_2026.md) para las conciliaciones de las bases.

## Datos y compatibilidad

Se mantienen `indicadores.parquet`, los 296 agregados por programa/provincia y las 17 columnas originales. La base operativa de septiembre suma 456.356 usuarios de servicios como conteo agregado por modalidad; el tablero lee la serie mensual depurada, con usuarios únicos por programa y territorio: **1.578.019 beneficiarios de bonos y pensiones, 453.994 usuarios de servicios y 11.215 unidades de atención** en septiembre de 2026. Las series VIS y VIE cubren enero a septiembre de 2026, con 1.300 parroquias con información en septiembre.

La depuración territorial ocurre al leer las series (`src/depuracion.py`) y no altera los totales: 49 combinaciones de VIE (38.101 beneficiarios, sobre todo Sevilla Don Bosco registrada con códigos de Morona hasta abril de 2026) pasan al territorio que nombran. En contingencias, todos los registros se ubican en su cantón; 462 de 10.628 (4,3 %) quedan sin parroquia identificable. En eventos antrópicos, 64 registros habilitados quedan sin cantón y se conservan en su provincia.

Contingencias y compensaciones publican solo meses cerrados (enero de 2023 a septiembre de 2026); octubre se incorporará cuando se cierre. Los contratos laborales conservan su corte diario (23 de octubre de 2026, 02:21).

Riesgos: 9.869 registros de la matriz y 9.860 UA únicas; 9.460 expuestas (95,9 %), 6.220 registros de multiamenaza según la matriz fuente, 1.341 UA con alguna amenaza en susceptibilidad muy alta y 6.344 UA con dos o más amenazas. El detalle de unidades reconcilia exactamente con los agregados para cada combinación de filtros.

## Comprobaciones ejecutadas

**125 pruebas aprobadas** y 30 subpruebas (una prueba heredada se omite sin el Excel original). Incluyen:

- Reconstrucción del Excel anterior y del conjunto actualizado, manteniendo importes decimales; conciliación de cobertura y presupuesto, códigos territoriales, distribución distrital, nulos y porcentajes calculados desde los totales.
- Depuración territorial con totales intactos; ubicación de bases nominales por nombre; meses abiertos excluidos de contingencias.
- Filtros, periodos, autenticación y separación de los ámbitos: transferencias, servicios, riesgos (exposición y seguimiento), contingencias, Jóvenes en Acción, gestión laboral y presupuesto institucional y social.
- Riesgos: respuesta del Ministerio desde el 14/09 (99 UA suspendidas, 10 alertas con código UA, 13.390 kits, bono y planificación), sin la exposición interna en el tablero ni en los exportables; filtros de territorio y servicio; nombres de cantones y UA legibles y vacíos de la fuente como guion; exportables con el mismo recorte (PDF de tres páginas, o dos sin alertas ni unidades suspendidas; hasta diez diapositivas; nueve hojas con fechas reales y un tipo de gráfico nativo por pregunta) y con código y nombre de cada UA.
- Cartografía: cada provincia, cantón, parroquia y zona con su polígono; selectores Provincia · Cantón · Parroquia en el mapa y en cada gráfico territorial.
- Centro de reportes: nivel territorial (Provincia, Cantón, Parroquia o Todo), resumen ejecutivo de dos páginas como máximo (una en Jóvenes en Acción), presentación y libro de datos de cada ámbito, y el **resumen de todas las secciones en tres páginas como máximo**, con un gráfico propio por sección y Riesgos en un solo bloque.
- Arranque concurrente de sesiones sin descargar módulos en uso.

Comando utilizado:

```bash
MTDH_SOURCE_EXCEL=data/source/Acumulado_VIS_VIE/ python -m pytest -q
```

En Windows puede definir esa variable de entorno previamente o ejecutar `python -m pytest -q`; en este último caso se omite únicamente la prueba heredada opcional del Excel original.

Se comprobó la aplicación en Chromium, en escritorio (1.440 px) y en teléfono (390 px): todos los ámbitos, los niveles territoriales del mapa y de cada gráfico, la selección de provincias y el centro de reportes, sin excepciones ni desbordamiento horizontal. Se revisaron visualmente los resúmenes ejecutivos, las presentaciones y los libros de datos de cada ámbito: importes con su unidad («USD 21,3 M»), conteos con lo que cuentan y sin espacios desaprovechados.

Los avisos de openpyxl corresponden a extensiones de formato de Excel no soportadas durante la lectura. Los Excel de origen se copiaron sin modificarlos. No se usan macros ni se evalúan vínculos externos.

## Límites de la validación

Las referencias 2024 y 2025 siguen sin mes documentado. Los totales de la base financiera reproducen las filas suministradas; queda pendiente confirmar las 11 repeticiones señaladas y el universo necesario para conciliar el presupuesto de la tabla 4 del boletín. No se declara equivalencia entre ese presupuesto, el institucional y el social.

La matriz de Riesgos se publica por provincia: el mapa por cantón y parroquia requiere volver a procesar la matriz fuente con sus códigos de cantón y parroquia. La susceptibilidad territorial no equivale a una afectación confirmada.

El comando principal y sus opciones anteriores siguen funcionando. Los cambios de esta entrega no incluyen secretos ni datos nominales de personas.
