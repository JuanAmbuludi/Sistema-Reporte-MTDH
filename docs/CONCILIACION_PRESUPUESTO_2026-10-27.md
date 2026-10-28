# Conciliación presupuestaria al 27 de octubre de 2026

Se contrastaron los tres Excel entregados con sus Parquet y con la publicación fiscal SGDE indicada por el usuario. No se imputaron montos ni se cambiaron usuarios, beneficiarios, unidades de atención o información de ENOS. Los resultados reproducibles están en `scripts/conciliar_presupuesto.py` y `data/processed/conciliacion_presupuesto_2026-10-27.json`.

## Fuentes y cifras que se muestran

| Consulta | Fuente | Corte / período | Montos en USD |
|---|---|---|---:|
| Fiscal | [Portal fiscal SGDE](https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/MDTDH/presupuesto.html#/presupuesto-fiscal) | Año fiscal 2026, corte 30/09/2026 | Codificado **993.606.130,45**; devengado **342.231.701,21**; ejecución **34,44 %** |
| Fiscal | Misma publicación | Mismo corte | Certificado **46.556.969,04**; comprometido **390.954.520,12**; disponible **554.031.624,67** |
| Social | Ejecución Presupuestaria SEPTIEMBRE 2026, grupos 58, 57 y 78 | Enero–septiembre 2026, MDH–MTDH | Aprobado **1.715.698.112,49**; devengado **1.261.791.379,87**; ejecución **73,54 %** |
| Gobierno | Acumulado VIS VIE, hoja provincial | Acumulado 2023–2026 al corte septiembre 2026 | Anterior **3.332.400.360,70**; componente 2026 **1.180.002.196,43**; total **4.512.402.557,13** |
| Transferencias y servicios | Presupuesto VIS VIE | Detalle territorial del corte septiembre 2026 | Devengado **1.180.002.197,25**; codificado VIS–VIE distribuido **1.781.225.672,52** |

Los universos se consultan por separado. El acumulado de gobierno ya incluye el componente 2026. Ni el presupuesto social ni el fiscal SGDE se suman al acumulado VIS–VIE.

La fuente social indica expresamente: enero–julio a cargo del MDH, desde agosto a cargo del MTDH. También indica que los mecanismos de transporte, migrantes retornados y compensación diésel no son administrados por el MTDH. El JSON fiscal SGDE **no identifica el mes inicial de su ejecución**; no se le asigna uno por inferencia.

El libro Acumulado no contiene fecha mensual en su encabezado provincial. Septiembre 2026 se conserva del corte documentado previamente en el repositorio y de la referencia de cobertura suministrada; no se inventa una fecha de transacción.

## Qué concilia y qué diferencia permanece

- **Acumulado VIS VIE:** las 296 filas y los siete campos de la hoja provincial son idénticos al Parquet original del repositorio. Se toma directamente su columna `acumulado` como fuente principal de gobierno. Antes el procesamiento la recalculaba con el devengado de otra base: el total era 4.512.402.557,95; ahora es 4.512.402.557,13. La diferencia nacional es **USD −0,82**. El devengado territorial se conserva.
- **Presupuesto VIS VIE:** coinciden las 9.299 filas, claves territoriales, servicios, usuarios de control y columnas monetarias con el Parquet. La columna bruta `total_codificado` **no es sumable en servicios**: repite asignaciones distritales. Se conserva la distribución ya validada por corriente e inversión (160 grupos). No se sustituye el monto distribuido por la suma bruta de USD 10.262.202.254,06.
- Los codificados de transferencias en VIS–VIE son próximos al campo **PLANIFICADO 2026** del Excel social, y difieren de su campo **PRESUPUESTO MDH–MTDH 2026**. Se conservan los importes y nombres de campo de origen, identificando la base como **Codificado VIS–VIE** / **Ejecución VIS–VIE**. No se presentan como el aprobado MDH–MTDH ni como el fiscal SGDE.
- **Ejecución social:** al ordenar por claves, las 126 observaciones mensuales y 13 asignaciones son idénticas a los Parquet existentes. BDH y BDHV comparten una asignación; se cuenta una sola vez. El total planificado redondeado por programa difiere en **USD 0,01** del total de la hoja; el aprobado y el devengado concilian a centavos.
- **Fiscal SGDE:** se conserva una copia de los 83 registros y sus catálogos. Corriente **34,92 %**, inversión **32,12 %**, total **34,44 %**. Todos los agrupamientos reconcilian con la suma de las filas y las tasas se calculan como razón de sumas.
- **Saldo disponible SGDE:** no se cambia ni se deduce de otras columnas. Codificado menos devengado es **651.374.429,24**, que es *saldo por devengar*, no disponible. Además, codificado menos certificado, comprometido y disponible deja **2.063.016,62**; las columnas publicadas no explican esa diferencia. Requiere aclaración de la fuente contable si se desea cerrar esa identidad. No se modifican los valores para forzarla.
- La base institucional anterior (`presupuesto_institucional.parquet`: codificado 2.137.233.099,36; devengado 978.122.861,16) se conserva en el repositorio para trazabilidad, pero la consulta Fiscal y su resumen usan la publicación SGDE solicitada. No se inventa una conciliación partida a partida entre bases de distinta granularidad.

## Usuarios: revisión sin cambios

Los beneficiarios de bonos y pensiones coinciden: **1.578.019**. Los usuarios de servicios **no son iguales** entre el libro principal, la base operativa y la serie mensual ya validada que usa el tablero:

| Servicio | Acumulado VIS VIE | Base territorial operativa | Dashboard validado |
|---|---:|---:|---:|
| Desarrollo Infantil Integral | 274.975 | 274.884 | 274.877 |
| Personas adultas mayores | 114.697 | 114.771 | 114.771 |
| Personas con discapacidad | 37.039 | 37.076 | 37.076 |
| Protección Especial | 29.528 | 29.625 | 27.270 |
| **Total servicios** | **456.239** | **456.356** | **453.994** |
| Unidades de atención | 11.158 | 11.215 | 11.215 |

El tablero sigue leyendo la serie mensual de cobertura, como documenta `docs/VALIDACION.md`. Se conserva su cobertura validada. El conteo de usuarios del Acumulado no se usa para reemplazarla. La vista Gobierno no mezcla estos conteos con los importes.

## Reproducción

```bash
python scripts/conciliar_presupuesto.py \
  --acumulado 'Acumulado VIS-VIE.xlsx' \
  --territorial 'Presupuesto_vis_vie.xlsx' \
  --ejecucion '09 Ejecución Presupuestaria SEPTIEMBRE 2026.xlsx'
```

La salida registra SHA-256 de cada Excel, comparaciones fila a fila y totales. Los archivos recibidos no se sobrescriben. Las pruebas de presupuesto verifican filtros, razón de sumas, gobierno, cobertura preservada y exportación a PDF, PowerPoint y Excel.

## Validación de la publicación

- 58 pruebas aprobadas, 11 subpruebas, una prueba heredada omitida por ausencia de su Excel original. Se cubrieron datos, reconstrucción, filtros y exportables, incluidos Fiscal y Gobierno.
- En `indicadores.parquet`, la única columna modificada es `monto_gobierno`; las otras 21 columnas y las 296 filas se conservan. Los Parquet de cobertura, las series mensuales y todos los archivos de ENOS conservan sus hashes.
- ENOS se comparó contra el commit previo: mismos seis KPIs, texto idéntico y píxeles idénticos en las cinco páginas del PDF vigente. Sus pruebas antiguas que todavía esperaban 39 alertas/99 unidades/cuatro páginas ya fallaban antes de este cambio; no se alteraron ni sus datos ni sus pruebas para este trabajo.
- Los PDF de Fiscal y Gobierno se generaron y revisaron visualmente; sus dos páginas conservan tipografía, colores y componentes institucionales.
