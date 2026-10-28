# Seguimiento y respuesta en Riesgos

Acceso: **ENOS** (módulo interno `riesgos`). La interfaz inicia en **Por período**, con todo el historial disponible y controles **Desde/Hasta**. **Reportes publicados** permite recuperar una publicación guardada mediante **Fecha del reporte**. La exposición territorial se conserva como análisis interno. El reporte del 26/10 y el del 27/10 tienen bases y alcances propios; el PDF nacional del 26/10 reproduce el documento aprobado aportado por el responsable. Los nuevos PDF conservan el estilo del folleto y ajustan la paginación al detalle seleccionado.

| Publicación | Alertas | Kits | Casos del bono | Monto del bono (USD) | Unidades suspendidas | Brigadas |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 26/10/2026 | 10 | 13.390 | 1.171 | 354.987,39 | 99 | No reportado |
| 27/10/2026 | 44 | 11.207 | 1.171 | 354.987,39 | 124 | 1 |

El 26/10 se recuperó del commit `558f357`, cotejando las 89 entregas y cada una de las 20 provincias con el PDF aprobado. El bono se concilió con ese PDF y con la confirmación del responsable: Los Ríos incluye 111 personas y USD 33.641,04. Se preservó el documento original y su rótulo histórico (29/08–25/10), aunque sus fuentes contienen cortes posteriores (Kobo y continuidad del 26/10). La fecha de publicación, el rótulo del PDF y las fechas de cada fuente se conservan por separado en la trazabilidad.

El 27/10 usa entregas desde el 28/09. Por tanto, **13.390 y 11.207 no son acumulados de un mismo intervalo**: no deben interpretarse como una disminución diaria de kits. Sus bases originales y cifras se mantienen. Al cambiar las fechas consultadas, el bono confirmado conserva sus casos y montos; los filtros territoriales siguen aplicándose al desglose provincial. La publicación del 27/10 presenta el bono como **Familias / Habilitadas al pago**, según la confirmación del responsable.

## Consulta por período y reportes publicados

| Modalidad | Fechas y datos utilizados | Exportación |
| --- | --- | --- |
| **Por período** | Selecciona fechas de registro/reporte de alertas, entrega de kits y realización de brigadas en las versiones más recientes de las bases disponibles. Ambos límites se incluyen. | PDF y Excel se calculan con los mismos registros y filtros del tablero. |
| **Reportes publicados** | Recupera el boletín conservado y los cortes de sus fuentes. **Fecha del reporte** mantiene el inicio propio de esa publicación. | El PDF nacional completo del 26/10 devuelve el archivo aprobado exacto. Los filtros territoriales o de servicio generan su selección específica. |

**Todo el historial** restablece Desde/Hasta a los límites reales de los registros incorporados. Actualmente esos límites son **27/02/2026–27/10/2026**; no se fijan permanentemente en el código y se amplían cuando ingresan fuentes con otras fechas. Consultar días anteriores al 26/10 funciona en **Por período** aunque no exista un boletín emitido para ese día. La ausencia de filas en una selección no prueba que no hayan ocurrido eventos: describe exclusivamente los registros disponibles y sus criterios de inclusión.

Las versiones superpuestas se concilian por código de alerta, ID Kobo o ID de brigada. Para cada identificador se usa su versión más reciente antes de filtrar las fechas; los registros con identificadores distintos se conservan aunque compartan fecha o cantón. Una fuente declarada como reemplazo completo sustituye su registro anterior. Las publicaciones guardadas permanecen intactas.

Las unidades suspendidas se muestran como **el último estado territorial disponible hasta Hasta**, sin sumar cortes y sin exigir que el corte sea posterior a Desde. Si no existe una observación territorial aplicable, se informa su falta de disponibilidad. El Bono de Contingencia mantiene su acumulado confirmado: las fechas no convierten ese saldo en un flujo del período. El filtro territorial sí se aplica al bono, las entregas, las alertas y las brigadas; el filtro de servicio se aplica a alertas y continuidad.

Con las fuentes actuales, la consulta **28/08/2026–27/10/2026** contiene **44 alertas, 14.581 kits en 22 provincias, 3 brigadas, 124 unidades suspendidas y el bono de 1.171 familias / USD 354.987,39**. El historial completo contiene **71 brigadas**. Los 117 IDs Kobo son únicos; la ampliación agrega 3.374 kits respecto al intervalo publicado desde el 28/09. Estos resultados se calculan desde las filas disponibles y no sustituyen los valores de los boletines publicados.

### Exportación desde la línea de comandos

Sin opciones de fecha se exporta todo el historial disponible. `--desde` y `--hasta` aceptan `AAAA-MM-DD`; si se omite uno se usa el extremo correspondiente del historial. `--publicacion` es exclusivo: no se combina con rangos ni con `--todo-historial`. La salida predeterminada queda en `docs/reportes/` con un nombre que identifica el período; `--salida` permite elegir otra ruta.

```bash
python scripts/generar_pdf_enos.py
python scripts/generar_pdf_enos.py --todo-historial --salida docs/reportes/Plan_ENOS_historial.pdf
python scripts/generar_pdf_enos.py --desde 2026-08-28 --hasta 2026-10-27
python scripts/generar_pdf_enos.py --desde 2026-08-31 --hasta 2026-08-31
python scripts/generar_pdf_enos.py --publicacion 2026-10-26
```

La API conserva las llamadas históricas existentes: `RiskView.select(..., mode="publicacion", until=...)`. Para consultar registros por fecha se usa `RiskView.select(..., mode="periodo", since=..., until=...)`; al omitir ambos límites toma todo el historial.

## Antecedentes de la elaboración del 26 de octubre (versiones preliminares)

- Se revisaron las **31 alertas** desde el 14/09. El criterio vigente solicitado por el responsable incluye **solo registros con código UA**: **10 alertas y 10 códigos UA distintos**, en 3 provincias y 4 cantones. Ocho registros corresponden a Desarrollo Infantil y dos a CNH. El primer registro con código es del 16/10. Los 21 registros sin código quedan fuera de este alcance.
- **Ocho alertas tienen afectación documentada y dos están por confirmar**. En ALT-2026-000315 / UA 58336 y ALT-2026-000316 / UA 58337 (Tenguel), la fuente vincula una UA pero solo describe inundación territorial. Se muestran con esa salvedad, sin atribuir un daño o interrupción no confirmados.
- El campo Afectados mezcla personas, familias y usuarios. No se presenta una suma como personas únicas. Una alerta no equivale necesariamente a un evento independiente y no acredita causalidad ENOS. Se conservan los códigos y nombres de UA existentes, sin inferir códigos faltantes.
- Kits en provincias priorizadas: siete entregas documentadas del 24–25/10, corte 25/10 a las 19:00; 802 kits en cuatro provincias priorizadas (Azuay, Esmeraldas, Guayas y Manabí) y cinco cantones. Las entregas repetidas en un cantón tienen cantidades distintas y no se eliminan. No es el acumulado desde el 14/09.
- Bono: la ayuda memoria contiene planificación explícita para El Niño 2026–2027: 145.523 personas potenciales, 44.098 núcleos familiares y USD 13.405.351,02 estimados. Es una proyección nacional y permanece nacional al aplicar filtros provinciales.
- Referencia por inundaciones: 113 núcleos familiares / USD 33.200,80 en pagos gestionados desde el 29/08, y 1.169 personas / USD 354.379,41 en articulación al 23/10. Se excluyen otros tipos de evento y la ejecución anual general. La fuente no permite atribuir exclusivamente esos pagos a ENOS ni recortarlos desde el 14/09; se explicita en pantalla y en los documentos. Se requiere un detalle individual fechado y una clasificación oficial de vinculación ENOS para publicar esa ejecución específica.
- La Gasca (ALT-2026-000346) se excluye: la fuente describe familias usuarias afectadas y ayuda, pero no acredita impacto en la prestación del servicio. Las dos alertas de Tenguel se distinguen como afectación por confirmar, según el criterio actualizado de código UA. Los kits y bonos se mantienen como acciones institucionales solicitadas, con sus propios alcances; no se presentan como prueba de afectación a las UA.

El boletín N.º 0044 de Educación (25/10) se emplea como referencia de estructura. No se suman sus 1.378 eventos ni sus cifras educativas a los datos MTDH, y su pronóstico hasta el 25/10 no se presenta como pronóstico vigente.

## Fuentes y actualización

Cada publicación `data/processed/seguimiento_enos_AAAA-MM-DD.json` publica únicamente campos operativos necesarios. Omite relatos libres, domicilios, responsables, teléfonos y datos personales de familias. Conserva las huellas de las fuentes.

### Bases utilizadas por la consulta actual

`src.enos.history()` concilia los registros de las publicaciones disponibles con la base completa de brigadas. Conserva la identidad y las huellas de las fuentes; no utiliza los totales de un PDF como filas adicionales ni recorta la carga al inicio de un boletín.

| Registro incorporado | Cobertura de filas actualmente disponibles | Control |
| --- | --- | --- |
| Alertas del aplicativo y reportes sectoriales | 05/10/2026–27/10/2026 | 44 códigos; aplicar los criterios documentados de cada fuente. Una alerta no equivale a un evento o una unidad únicos. |
| Matriz global Kobo de kits, conciliada al 27/10 | 31/08/2026–27/10/2026 | 117 IDs únicos; 14.581 kits reportados. El registro de Cañar con 1 kit conserva la observación de solicitud no recibida, pendiente de validación territorial. |
| Matriz completa de brigadas de emergencia, corte 22/10 | 27/02/2026–13/10/2026 | 71 filas de tipo EMERGENCIA entre las 3.038 filas operativas de la matriz; IDs administrativos únicos. |
| Continuidad territorial | Cortes disponibles del 26 y 27/10 | Último corte aplicable a la fecha final; no sumar observaciones. |
| Bono de Contingencia | Acumulado confirmado de la fuente | 1.171 familias y USD 354.987,39; conservación por fecha y desglose por provincia. |

Estas coberturas describen las filas incorporadas; no acreditan ausencia de eventos fuera de ellas. La fecha de corte de una fuente y la primera/última fecha de sus registros se conservan por separado.

Para actualizar brigadas se importa la matriz completa, sin aplicar el filtro de fechas del tablero:

```bash
python scripts/update_brigadas.py "matriz_brigadas.xlsx" --corte 2026-10-22
```

El importador escribe `data/processed/brigadas_emergencia.json`, conserva únicamente identificador, fecha, provincia, cantón y tipo, y registra el SHA-256 de la fuente. Rechaza IDs contradictorios y fechas posteriores al corte declarado. No reemplaza los archivos `seguimiento_enos_*` ni `continuidad_servicios_*`.

La carga de alertas y kits conserva los registros anteriores a `--start`: ese parámetro define el alcance del boletín, no elimina historia de la base. Las alertas requieren una decisión documental para cada código y conservan las exclusiones explícitas para no recuperar una versión descartada. Los kits requieren IDs de origen, únicos y normalizados. Los importadores rechazan la escritura sobre publicaciones cerradas; primero debe abrirse un corte nuevo.

### Construcción inicial de la publicación del 26/10

```bash
python scripts/build_enos.py \
  --alerts "analisis-alertas-2026-10-26 (2).xlsx" \
  --service-review data/reference/enos_revision_servicios_2026-10-26.csv \
  --bonos "Bono de Contingencia - Fenómeno del Niño.docx" \
  --kits data/reference/enos_kits_2026-10-25.csv --allow-legacy-kits \
  --start 2026-09-14 --cut 2026-10-26 --kits-cut 2026-10-25 --bonos-cut 2026-10-23
```

Este comando documenta la construcción inicial y no debe ejecutarse sobre el corte cerrado. El CSV de kits es una transcripción revisada de `Reporte_ministerial_kits_provincias_priorizadas_rev.pdf`; la opción de compatibilidad permite reproducir esa fuente sin inventar IDs y no la convierte en una base conciliable de eventos. Para nuevos cortes se debe suministrar el archivo actualizado con identificadores. El parser de bonos conserva la provincia de las celdas verticalmente combinadas del Word. Los alcances narrativos de cada fuente deben revisarse cuando cambien sus periodos o criterios.

## Periodo y trazabilidad de lo reportado

En **Reportes publicados**, **Fecha del reporte** selecciona la publicación guardada de cada día, por omisión la más reciente. Cada publicación conserva sus entregas, alertas, continuidad y cortes; el bono en articulación permanece como acumulado confirmado. No se cambia el inicio de un reporte histórico por el de una publicación posterior. La modalidad **Por período** es una consulta actual de registros por fecha y no sustituye al documento que se emitió.

**Cada día reportado es una publicación propia**, nombrada por ese día: `seguimiento_enos_AAAA-MM-DD.json` (alertas, kits, bono y sus alcances en `notas`) y `continuidad_servicios_AAAA-MM-DD.json` (unidades suspendidas). Antes de la primera publicación guardada (26/10/2026) no existe un boletín histórico para recuperar; sí pueden consultarse los registros disponibles mediante **Por período**. El documento aprobado está en `data/reports/riesgos_2026-10-26.pdf`: la descarga histórica nacional valida su SHA-256 y entrega los bytes originales. Los exportables con filtros territoriales o de servicio se calculan desde los registros de esa publicación y nunca devuelven el PDF nacional por error.

Para reportar un día nuevo no se edita el anterior:

```bash
python scripts/nuevo_corte_riesgos.py 2026-10-28
```

El script copia la última publicación de cada fuente a los archivos del nuevo día y cierra el día anterior: registra la huella SHA-256 de sus archivos en `data/processed/cortes_riesgos.json`. Los datos nuevos se cargan después en los archivos del nuevo día (`scripts/update_kobo_kits.py` actualiza por omisión la última publicación). La prueba `tests/test_riesgos_periodo.py` falla si un día cerrado cambia.

## Estabilidad de la aplicación

Se eliminó la invalidación manual de `sys.modules` al arrancar cada sesión: podía borrar un módulo mientras otra sesión lo importaba y causar el KeyError observado. La recarga de código queda a cargo de Streamlit.

### Visibilidad y unidades de medida

Por instrucción del responsable, la exposición territorial se conserva como análisis interno y deja de mostrarse en el tablero, los mapas, los indicadores, las tablas y los exportables públicos de Riesgos, incluido el resumen de todas las secciones. Los exportables completos usan únicamente la respuesta institucional visible y sus filtros.

El indicador de bonos gestionados se presenta como **113 núcleos familiares**, con **USD 33.200,80**, por aclaración del responsable. La columna original de la ayuda memoria se titula PERSONAS; se conserva su nombre técnico `personas` en el dato de origen para mantener la trazabilidad. No se cambia el conteo, no se estima el tamaño de los núcleos y no se reinterpreta la columna de casos en articulación (personas).

### Criterio confirmado para la publicación del 26/10

Este apartado conserva el alcance de la publicación del 26/10. La publicación del 27/10 incorpora además registros del aplicativo y reportes sectoriales con su propia trazabilidad; su consulta actual contiene 44 alertas.

Se muestran **solo registros revisados con código UA**: **10 alertas y 10 códigos UA distintos**, ocho en Desarrollo Infantil y dos en CNH. Se verificó el filtro de la columna Código SIIMDH del Excel original, descartando guiones y valores vacíos. El seguimiento sigue desde el 14/09/2026; la primera alerta con código es del 16/10/2026. La ausencia de registros con código en septiembre no acredita ausencia de eventos.

De estas diez, **ocho tienen afectación documentada y dos están por confirmar**: ALT-2026-000315 / UA 58336 y ALT-2026-000316 / UA 58337, en Tenguel. El código las vincula a una UA, pero sus relatos solo documentan inundación territorial. Se incorporan por el criterio expresamente confirmado por el responsable y se muestran como afectación por confirmar, sin afirmar daño ni interrupción del servicio. Las cinco alertas anteriormente incluidas sin código quedan fuera del alcance público. La Gasca permanece excluida.

La revisión CSV registra inclusión y confirmación de afectación por separado. El snapshot de esquema 3 declara `criterio_alertas=codigo_ua`: 31 registros originales, 10 incluidos, 21 excluidos, 8 con impacto documentado y 2 por confirmar. Tablero, gráficas y exportables usan ese mismo criterio.
