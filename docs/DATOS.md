# Datos y reglas de cálculo

La aplicación utiliza la hoja **provincial** de `Acumulado VIS-VIE.xlsx`. El archivo es un consolidado agregado: contiene una fila por programa y provincia, sin cédulas ni identificadores de unidades. El corte **septiembre de 2026** se toma del boletín PDF adjunto y sus cifras nacionales concilian con la hoja vigente. El Excel por sí solo no informa el mes.

## Estructura que consume la aplicación

| Archivo | Contenido | Uso |
|---|---|---|
| `indicadores.parquet` | 296 registros del corte provincial vigente | Dashboard y reportes |
| `historico_referencia.parquet` | 592 registros de las hojas de referencia 2024 y 2025 | Consulta separada; mes de corte no documentado |
| `auxiliar_cantonal.parquet` | 746 registros de la hoja `calculos dic` | Archivo auxiliar de trazabilidad; no se incorpora al corte vigente |
| `manifest.json` | Fuente, huellas SHA-256, corte, controles, definiciones y advertencias | Reproducibilidad y revisión |

Los archivos usan compresión Zstandard. El esquema vigente almacena conteos enteros, códigos territoriales de dos caracteres, fechas como `date32` e importes como `decimal128(24,6)`. Se preservan seis decimales para no redondear prematuramente la fuente; la presentación muestra los decimales apropiados para cada indicador. El acceso de la aplicación convierte los importes a números para construir gráficos.

## Indicadores

| Campo | Interpretación y regla |
|---|---|
| `usuarios` | Conteo reportado en la columna Usuarios. En bonos se rotula beneficiarios reportados. Se suma dentro del mismo corte y dimensiones; no acredita personas únicas entre programas. |
| `unidades` | Unidades de atención reportadas de servicios. Los ceros de bonos se convierten en nulo porque no aplica; `unidades_origen` conserva el valor original. |
| `monto_fiscal` | Columna `Presupuesto 2026`, en USD. El insumo no documenta si es devengado, pagado, codificado u otra fase. No equivale automáticamente a ejecución ni a transferencias mensuales. |
| `monto_anterior` | Columna `acumulado 2023-2025`, en USD. |
| `monto_gobierno` | Columna `acumulado`, en USD. Se verifica que sea anterior + fiscal para cada fila; no se vuelve a sumar con ambos componentes. |
| `presupuesto_ejecutado` | Nulo en la fuente entregada. Puede completarse mediante un CSV complementario con montos verificados, corte y claves coincidentes. |
| `fuente_hoja`, `fuente_fila` | Procedencia exacta del dato en el Excel, conservada en todas las tablas. |

La cobertura nacional tiene **24 provincias**. `Zona en estudio` se conserva bajo el código interno **90** y se incluye en los totales, pero no se cuenta como una provincia número 25. No se excluye Galápagos: la fuente provincial lo incluye.

No se suman beneficiarios de bonos y usuarios de servicios para presentarlos como personas únicas. Tampoco se suman cortes diferentes ni se presentan las referencias anteriores como una serie mensual. Un dato ausente se muestra como no disponible; un cero explícito se mantiene como cero.

## Conciliación del corte entregado

| Apartado / programa | Conteo reportado | Unidades |
|---|---:|---:|
| Bonos y pensiones, ocho programas | 1.578.019 | No aplica |
| Desarrollo Infantil Integral | 274.975 | 6.759 |
| Personas adultas mayores | 114.697 | 2.792 |
| Personas con discapacidad | 37.039 | 1.229 |
| Protección Especial | 29.528 | 378 |
| Servicios de protección integral | 456.239 | 11.158 |

Las pensiones PAM y PCD tienen cero beneficiarios y cero presupuesto fiscal en el corte vigente, pero conservan saldos en el acumulado de gobierno. Se mantienen como programas para no perder esos importes. Por ello, un reporte que omita esos dos programas tiene un acumulado de gobierno distinto al total de los ocho programas.

## Referencias históricas y auxiliar cantonal

La hoja `provincial (2025)` contiene usuarios y presupuesto 2025, pero no el mes. Su encabezado `acumulado 2023-2024` es inconsistente con la fórmula: incluye `solo dic` + `Presupuesto 2024` + `Presupuesto 2025`. El ETL conserva la hoja y fila de origen, concilia esa identidad y usa el valor como acumulado de la referencia 2025. Ese acumulado coincide fila por fila con el acumulado anterior de la hoja vigente.

La hoja `Hoja1 (2)` contiene presupuesto 2024 con cifras distintas a la columna 2024 de la referencia 2025; no hay evidencia suficiente para igualar sus cortes. Sus valores se conservan en una referencia separada de 2024. No se calculan tasas interanuales sobre presupuestos de períodos no homologados.

`calculos dic` distribuye un presupuesto provincial en función de participaciones de usuarios cantonales. **No son ejecuciones cantonales independientes ni necesariamente datos de septiembre de 2026.** Tiene celdas vacías en participaciones y presupuestos provinciales; los nulos se preservan. La tabla auxiliar no alimenta las tarjetas, los rankings ni los reportes del corte actual.

## Regenerar la base

Desde la raíz del proyecto, con las dependencias instaladas:

```bash
python scripts/build_data.py "ruta/Acumulado VIS-VIE.xlsx" --period 2026-09 --period-source "Boletín institucional de septiembre de 2026"
```

`--period` es obligatorio porque el mes no está en el Excel. El año del corte debe coincidir con el encabezado presupuestario de la hoja. Puede cambiar la hoja vigente con `--sheet` y la carpeta de salida con `--output`. El script valida encabezados, categorías, provincias, claves duplicadas, conteos enteros, importes no negativos y conciliación de acumulados. Ante un error, detiene la importación en lugar de eliminar filas o reemplazar faltantes por ceros.

El formato de hojas antiguas se conserva explícitamente como referencia. Si cambia la estructura del Excel, revise el mapeo en `src/etl.py`; no basta con renombrar columnas que tienen otro significado. Cuando un Excel contiene fórmulas, debe guardarse con sus resultados calculados: el ETL lee y valida los resultados almacenados, no ejecuta macros ni fórmulas externas.

## Incorporar presupuesto ejecutado

Complete una copia de `data/templates/ejecucion_presupuestaria.csv` con las columnas:

```csv
periodo,programa_id,provincia_codigo,presupuesto_ejecutado
```

Use corte `AAAA-MM` o `AAAA-MM-01`, códigos provinciales de dos dígitos e importes en USD con punto decimal y sin separadores de miles. Cada combinación programa/provincia debe aparecer una sola vez, existir en el Excel y corresponder al mismo corte. No complete datos faltantes con cero; use cero solo si la ejecución verificada es efectivamente cero.

```bash
python scripts/build_data.py "ruta/Acumulado VIS-VIE.xlsx" --period 2026-09 --ejecucion "ruta/ejecucion_verificada.csv" --period-source "Corte validado por el área responsable"
```

| Código de programa | Programa |
|---|---|
| BDH | Bono de Desarrollo Humano |
| BDHV | Bono de Desarrollo Humano Variable |
| BMD | Bono 1.000 Días |
| BJGL | Bono Joaquín Gallegos Lara |
| MMA | Pensión Mis Mejores Años |
| PTV | Pensión Toda Una Vida |
| PAM | Pensión para Adultos Mayores |
| PCD | Pensión para Personas con Discapacidad |
| DII | Desarrollo Infantil Integral |
| PAM_SERV | Servicios de personas adultas mayores |
| PCD_SERV | Servicios de personas con discapacidad |
| PE | Protección Especial |

Puede incorporar una cobertura parcial, pero el total de ejecución se mantiene como no disponible hasta que todas las filas seleccionadas estén cubiertas. La API devuelve además `presupuesto_ejecutado_parcial` y `ejecucion_cobertura_pct` para documentar el avance. No se calcula un porcentaje de ejecución dividiendo por `monto_fiscal`, porque el insumo no certifica que esa columna sea presupuesto codificado.

## Verificación

```bash
python -m unittest discover -s tests -v
```

Las pruebas verifican las cifras suministradas, separación de cortes, tratamiento de nulos, integridad de acumulados, filtro conjunto y controles del archivo de ejecución. Para probar además la regeneración íntegra desde el Excel original, establezca la variable `MTDH_SOURCE_EXCEL` con su ruta antes de ejecutar las pruebas.
