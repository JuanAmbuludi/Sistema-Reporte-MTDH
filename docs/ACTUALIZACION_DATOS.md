# Actualización de cobertura y presupuesto — septiembre de 2026

## Decisión sobre las versiones

**Usar `Usuarios_vis_vie.xlsx` para cobertura y unidades y `Presupuesto_vis_vie.xlsx` para el devengado y codificado actuales. Conservar `Acumulado_VIS_VIE.xlsx` como fuente histórica.** Los archivos nuevos aportan detalle parroquial y fases presupuestarias explícitas, pero no reemplazan el acumulado 2023–2025 ni las referencias anuales 2024 y 2025.

No se elimina ninguna fuente. El dashboard sigue leyendo `data/processed/indicadores.parquet`, con los mismos 296 registros por periodo/programa/provincia y las 17 columnas originales. Se añaden columnas; no se renombran las anteriores ni los códigos de programa.

## Comparación verificada

| Contenido | Versión anterior | Versión nueva | Diferencia |
|---|---:|---:|---:|
| Beneficiarios de bonos y pensiones | 1.578.019 | 1.578.019 | 0 |
| Usuarios de servicios | 456.239 | 456.356 | +117 |
| Unidades de servicios | 11.158 | 11.215 | +57 |
| Usuarios de Desarrollo Infantil Integral | 274.975 | 274.884 | −91 |
| Usuarios de personas adultas mayores | 114.697 | 114.771 | +74 |
| Usuarios de personas con discapacidad | 37.039 | 37.076 | +37 |
| Usuarios de Protección Especial | 29.528 | 29.625 | +97 |

Unidades por servicio en la versión nueva: DII 6.814; personas adultas mayores 2.794; personas con discapacidad 1.230; Protección Especial 377. Son agregados reportados, sin identificadores que permitan verificar unidades físicas únicas. Se usan las unidades de cobertura: la fuente presupuestaria suma 11.718 y no sustituye este indicador.

Las seis transferencias con beneficiarios mantienen sus cifras: BDH 619.073; BDHV 367.289; BMD 164.983; BJGL 50.129; MMA 303.845; PTV 72.700. PAM y PCD se conservan por sus acumulados anteriores, sin cobertura ni ejecución actual.

`comparacion_versiones.csv` permite revisar los cambios en cada programa y provincia. Las diferencias no se presentan como crecimiento mensual: son dos versiones del mismo corte.

## Presupuesto VIS/VIE

| Magnitud | USD |
|---|---:|
| Devengado fiscal al corte | 1.180.002.197,25 |
| Codificado depurado | 1.781.225.672,52 |
| Acumulado anterior 2023–2025 conservado | 3.332.400.360,70 |
| Acumulado 2023–2026 recalculado | 4.512.402.557,95 |

La ejecución es **66,25 %**, calculada como suma de devengado / suma de codificado. El total VIS/VIE sirve para conciliar importes; beneficiarios y usuarios continúan mostrándose por ámbitos separados.

**Corrección crítica:** en VIS, `total_codificado` repite el presupuesto distrital por cada parroquia. Sumar esa columna completa daría USD 10.262.202.254,06. El ETL usa `presupuesto_codificado_corriente + presupuesto_codificado_inversion`, que ya están distribuidos, y valida la proporción y el total en los 160 grupos distrito/servicio. En VIE usa `total_codificado` de origen.

La cobertura tiene 10.849 filas y el presupuesto 9.299. Se concilian exactamente los usuarios por programa/parroquia antes de agregar por provincia. No se une el presupuesto a cada modalidad/cooperante, lo cual multiplicaría los importes. El presupuesto ejecutado se toma de `total_devengado`; no equivale a pago efectivo ni al gasto exclusivo de septiembre.

Se mantiene `monto_fiscal` como alias del devengado para compatibilidad con gráficos y exportadores. `monto_anterior` permanece intacto; `monto_gobierno = monto_anterior + monto_fiscal`. El acumulado histórico no acredita una fase presupuestaria homogénea en todos los años. La diferencia aproximada de USD 0,82 frente al fiscal anterior es consistente con la precisión de los valores de las fuentes; no se presenta como una variación sustantiva de ejecución. El ETL conserva seis decimales y la interfaz muestra centavos o millones.

## Base financiera institucional

`Base_de_datos_fin.xlsx` se conserva en su universo propio: 5.206 filas por dimensiones presupuestarias y unidad ejecutora. No se reparte entre bonos o servicios ni se suma a VIS/VIE.

- Codificado: **USD 2.137.233.099,36**.
- Devengado: **USD 978.122.861,16**.
- Certificado: **USD 33.300.921,50**.
- Ejecución: **45,77 %**, razón de totales; no promedio de porcentajes.

Juan confirmó expresamente **septiembre de 2026** como corte. El archivo no contiene fecha de reporte y mantiene el encabezado `PROGRAMADO 2024`; esta limitación se registra en la configuración y el manifiesto. La columna se guarda como `programado_origen`, sin reinterpretarla como programación de 2026. `programado_acumulado` tampoco se confunde con el acumulado multianual VIS/VIE.

Hay **11 repeticiones exactas adicionales**, que suman USD 45.570 de codificado y cero devengado. Se preservan con `fila_identica_previa = true`: faltan identificadores de partidas para decidir si deben eliminarse. Los totales reproducen el archivo completo y quedan pendientes de esa confirmación. No se han presentado como totales depurados de duplicados.

En InfoReport esta base es el ámbito **Presupuesto institucional**, consultado aparte de transferencias y servicios: codificado, devengado, ejecución y saldo por programa, zona de planificación, unidad ejecutora, grupo de gasto, fuente y tipo de gasto, con filtros propios de zona y programa. Sus reportes (resumen de dos páginas, cuatro diapositivas y libro de datos) exportan solo esa selección; los de transferencias y servicios exportan exclusivamente su selección VIS/VIE.

## Cobertura de las tablas del boletín

| Tabla | Estado | Diferencias o pendientes |
|---|---|---|
| 1. Bonos y pensiones | Beneficiarios, devengado, codificado y acumulados disponibles | Beneficiarios coinciden; fase actual explícita y acumulado histórico conservado |
| 2. Protección integral | Usuarios, unidades, devengado, codificado y acumulados disponibles | Cobertura revisada: +117 usuarios y +57 unidades frente al boletín |
| 3. Contingencias | Pendiente por instrucción del usuario | No se construye ni completa esa tabla; las partidas de la base general se conservan en su total de origen |
| 4. Gestión laboral y presupuesto | Base laboral y base financiera disponibles por separado | Los universos y cortes no permiten tratar todas las cifras como equivalentes a las del boletín |

La extracción laboral existente conserva 2.789.419 contratos vigentes al estado de consulta del 22/10/2026 frente a 2.789.437 del boletín. Los 4.676 jubilados anuales de la noticia difieren de 4.686; el monto publicado es **más de USD 229 millones**, no el valor exacto USD 229,84 millones. La fuente no documenta un cierre mensual para jubilaciones. Véase [GESTION_LABORAL.md](GESTION_LABORAL.md).

El presupuesto general nuevo tampoco coincide con USD 342,23 millones y 34,44 % del boletín. No se sustituye silenciosamente como si correspondiera al mismo universo. Para cerrar esa conciliación falta confirmar el alcance institucional y presupuestario de la tabla 4 original.

## Periodos realmente disponibles

- Cobertura VIS: fecha explícita **30/09/2026**. Las nuevas bases no contienen una serie mensual de meses anteriores.
- Bonos y presupuesto VIS/VIE: corte de septiembre asignado por el responsable y respaldado por conciliación de usuarios con la cobertura. Las fechas vacías no se rellenan como si estuvieran documentadas en origen.
- Base anterior: referencias **2024 y 2025**, sin mes de corte. Se conservan en el selector anual y no se presentan como cierres de septiembre.
- Laboral: nueve cohortes mensuales enero–septiembre de 2026 con **estado vigente al momento de la consulta**; no son stocks históricos al cierre de cada mes. Se conserva también el stock de consulta nacional y las referencias anuales de jubilación.

## Reproducir la actualización

Desde la raíz del repositorio:

```bash
python -m pip install -r requirements.txt
python scripts/build_data.py --config config/actualizacion_datos.json
```

El mismo comando genera cobertura, presupuesto territorial, indicadores compatibles, referencias históricas y presupuesto institucional. La configuración documenta archivos y cortes; las rutas se resuelven desde la raíz del proyecto, aunque se ejecute desde otra carpeta.

Para incluir también la consulta web oficial laboral en esa misma ejecución:

```bash
python -m pip install -r requirements-scraping.txt
python -m playwright install chromium
python scripts/build_data.py --config config/actualizacion_datos.json --incluir-laboral
```

Para reproducir las evidencias laborales entregadas sin consultar internet:

```bash
python scripts/build_data.py --config config/actualizacion_datos.json --incluir-laboral --laboral-evidencia data/processed/laboral_evidencias/20261022T232229581149Z_9cd411c6.json
```

Esta última opción conserva las fechas de consulta originales; no simula una actualización web. Las opciones previas del script siguen vigentes. El módulo de transformación nuevo es `src/etl_actualizacion.py`; el scraper sigue en `src/laboral_scraper.py`. Si falla una validación, se detiene la ejecución antes de reemplazar los archivos entregados. Las escrituras locales se realizan por archivo desde una carpeta temporal; la publicación en GitHub se hace en un único commit.

## Archivos generados

| Ruta dentro de `data/processed/` | Grano y función |
|---|---|
| `indicadores.parquet` | 296 filas; periodo/programa/provincia; fuente del dashboard |
| `historico_referencia.parquet` | 592 filas; referencias anuales 2024 y 2025 conservadas |
| `auxiliar_cantonal.parquet` | Auxiliar histórico previo, conservado |
| `cobertura_territorial.parquet` | 10.849 filas; programa/parroquia/modalidad/cooperante |
| `presupuesto_territorial.parquet` | 9.299 filas; programa/parroquia; importes sin repetir modalidades |
| `presupuesto_institucional.parquet` | 5.206 filas de la fuente financiera, con marcas de repetición |
| `comparacion_versiones.csv` | Antes/después por provincia y programa |
| `manifest.json` | Fuentes, hashes, definiciones, corte y controles VIS/VIE |
| `manifest_financiero.json` | Fuente, corte confirmado, controles y totales financieros |
| `gestion_laboral.parquet` / `manifest_laboral.json` | Extracción laboral existente conservada |

Las columnas originales `fuente_hoja` y `fuente_fila` de indicadores continúan identificando el respaldo del acumulado anterior. La procedencia de los nuevos valores está en `fuente_cobertura`, `fuente_presupuesto` y los Parquet territoriales, con archivo, hoja y fila. No se inventa una fila única para un agregado de varias filas fuente.
