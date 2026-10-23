# Validación de la actualización de datos

Actualización revisada el 23 de octubre de 2026 (Ecuador). Véase [ACTUALIZACION_DATOS.md](ACTUALIZACION_DATOS.md) para decisiones, comparación y límites de las fuentes.

## Datos y compatibilidad

Se mantienen `indicadores.parquet`, los 296 agregados por programa/provincia y las 17 columnas originales. La cobertura nueva suma 1.578.019 beneficiarios de bonos, 456.356 usuarios de servicios y 11.215 unidades. Los usuarios de cobertura y presupuesto concilian por programa/parroquia. El codificado VIS se distribuye sin sumar el total distrital repetido.

Los acumulados anteriores coinciden exactamente, fila por fila, con el Excel original. `historico_referencia.parquet` se conserva idéntico. La base financiera nacional se procesa por separado, con 5.206 filas y 11 repeticiones marcadas y conservadas. Su corte de septiembre de 2026 fue confirmado por el responsable; no se dedujo del encabezado antiguo de programación.

## Comprobaciones ejecutadas

**78 pruebas aprobadas**, sin omisiones, más 30 subpruebas. Incluyen:

- Reconstrucción del Excel anterior y del conjunto actualizado, manteniendo importes decimales.
- Conciliación de cobertura y presupuesto, códigos territoriales, distribución distrital, ausencia de multiplicación por modalidad, nulos y porcentajes calculados desde los totales.
- Conservación de nombres, claves y acumulados históricos; reproducción de los Parquet a partir de las fuentes entregadas.
- Reproducción de la base laboral con la evidencia guardada en la misma ejecución, sin cambiar la fecha de consulta.
- Rechazo de cobertura repetida, parroquias presupuestarias faltantes, fechas incoherentes y distribución inválida; ante fallo se conservan los archivos previamente entregados.
- Filtros, periodos, autenticación y separación de los cuatro ámbitos (transferencias, servicios, gestión laboral y presupuesto institucional).
- Cartografía: cada provincia, cantón, parroquia y zona con su polígono; cada parroquia de las bases encuentra su polígono (salvo la zona en estudio); los anillos se cierran al disolver cualquier grupo de parroquias.
- Selectores Provincia · Cantón · Parroquia en el mapa y en cada gráfico territorial; en los años de referencia quedan en provincia y deshabilitados.
- Nivel territorial de los reportes (Provincia, Cantón, Parroquia o Todo): resumen ejecutivo de dos páginas como máximo (una en gestión laboral), presentación con una diapositiva por nivel y libro de datos con una hoja por nivel, valores numéricos, fórmulas y ficha técnica.

Comando utilizado:

```bash
MTDH_SOURCE_EXCEL=data/source/Acumulado_VIS_VIE.xlsx python -m pytest -q
```

En Windows puede definir esa variable de entorno previamente o ejecutar `python -m pytest -q`; en este último caso se omite únicamente la prueba heredada opcional del Excel original. Las pruebas de actualización sí reconstruyen los nuevos insumos.

Se comprobó la aplicación en Chromium, en escritorio (1.440 px) y en teléfono (390 px): los cuatro ámbitos, los tres niveles territoriales del mapa y de cada gráfico, la selección de una provincia y el centro de reportes. Cero excepciones de la aplicación y ningún desbordamiento horizontal del documento en el teléfono. Se revisaron visualmente los resúmenes ejecutivos, las presentaciones y los libros de datos de cada ámbito y nivel; los importes, unidades y textos se muestran sin solapamientos.

Los avisos de openpyxl corresponden a extensiones de formato de Excel no soportadas durante la lectura. Los Excel de origen se copiaron sin modificarlos. No se usan macros ni se evalúan vínculos externos.

## Límites de la validación

Los conteos son agregados reportados, no personas o unidades deduplicadas. Las fuentes actualizadas no aportan una serie mensual VIS/VIE anterior a septiembre. Las referencias 2024 y 2025 siguen sin mes documentado.

Los totales de la base financiera reproducen las filas suministradas; queda pendiente confirmar las 11 repeticiones y el universo necesario para conciliar el presupuesto de la tabla 4 del boletín. No se declara equivalencia entre ese presupuesto, el institucional nuevo y VIS/VIE. La tabla 3 queda pendiente por instrucción del usuario.

El comando principal y sus opciones anteriores siguen funcionando. El inicio de sesión y su configuración permanecen intactos. Los cambios de esta entrega no incluyen secretos ni cuentas de pruebas.
