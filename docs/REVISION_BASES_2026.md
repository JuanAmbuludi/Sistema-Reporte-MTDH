# Revisión de las bases — 25 de octubre de 2026

## Resultado y cobertura

Se mantienen las bases que consume la aplicación y se añade un catálogo de series compacto en `data/series/`. Todas las bases de datos de `data/` son Parquet con compresión Zstandard; JSON se utiliza exclusivamente para configuración, evidencias y controles. Los Excel y CSV anteriores quedan disponibles en el historial Git. La cartografía y los archivos de exportación de ejemplo conservan su formato propio.

| Fuente | Cobertura disponible | Tratamiento |
|---|---|---|
| VIS | Enero–septiembre 2026: 206 filas nacionales y 51.462 territoriales | Usuarios y unidades únicos dentro de servicio/modalidad y territorio |
| VIE | Enero–septiembre 2026: 63 filas nacionales y 81.909 territoriales | Beneficiarios por bono y territorio; PTV de menores separado en el detalle |
| Presupuesto social aprobado | Enero–septiembre 2026, 14 programas | 126 filas mensuales y 13 asignaciones anuales al corte |
| Feminicidio / orfandad | Enero 2023–septiembre 2026 | 44 meses reportados; junio 2026 está ausente |
| Incentivos acreditados | Enero 2023–septiembre 2026 | Resumen por programa/fase/mes; cobertura distinta entre programas |
| Eventos naturales y antrópicos | Febrero 2024–octubre 2026 | Habilitación y cobro según fechas reales; octubre es parcial |
| Contingencias | Diciembre 2023–octubre 2026 | Habilitación y cobro separados; octubre es parcial |
| Contratos SGDE | Corte 23 de octubre de 2026, 02:21 | Stock diario por provincia/cantón y otras dimensiones |
| Cohortes mensuales SUT previas | Enero–septiembre 2026, observadas el 22 de octubre | Se conserva la evidencia previa y su fecha independiente |
| Jubilaciones SGDE | 2023–2025 completos; 2026 al 18 de septiembre | Expedientes, montos, provincia, sexo y régimen |

No hay una fuente completa para octubre–diciembre 2026 de VIS, VIE o presupuesto aprobado. Tampoco hay fotos diarias retrospectivas de contratos para todo el año. Los meses no recibidos no se inventan ni se llenan con cero. Las referencias provinciales de 2024 y 2025 permanecen anuales porque su fuente no documenta un mes.

El detalle operativo de septiembre continúa en `data/processed/`, con su estructura anterior de modalidad/cooperante y presupuesto. Las versiones territoriales aportadas al final sustituyen las entradas nacionales iniciales en las nuevas series: contienen nacional, provincia, cantón y parroquia para enero–septiembre. Cada nivel se conserva como tabulación independiente: sus registros concilian con el nacional por mes y programa/modalidad, pero sumar únicos de territorios no demuestra personas únicas nacionales.

Se mantuvieron separados CDI directos, convenios y emblemáticos usando `modalidad_descripcion`; la etiqueta amplia de CDI los habría mezclado. Se retiraron las descripciones redundantes y los prefijos numéricos.

**Control territorial de VIE:** 518 filas pertenecen a combinaciones mes/nivel/código asociadas a más de un nombre de lugar (`codigo_ambiguo=True`). La serie se conserva tal como se recibió; al leerla, `src/depuracion.py` mantiene el código cuando los nombres corresponden a su territorio y reasigna la fila cuando provincia, cantón y parroquia identifican sin duda otra unidad de la división político-administrativa: 49 combinaciones (38.101 beneficiarios), principalmente Sevilla Don Bosco, registrada con los códigos de Morona hasta abril de 2026. Los totales nacionales no cambian y `cleaning_log()` lista cada reasignación. VIS no presenta estas colisiones.

## Presupuesto y ejecución

Fuente: `01-09-Ejecuci-n-Presupuestaria-SEPTIEMBRE-2026.xlsx`, aportado como presupuesto aprobado por planificación social. Se leyó el corte explícito de la hoja y se conciliaron los doce encabezados mensuales, las sumas por programa y mes y la fila total.

| Concepto | USD |
|---|---:|
| Presupuesto aprobado anual | 1.715.698.112,49 |
| Devengado acumulado enero–septiembre | 1.261.791.379,87 |
| Planificado anual, suma de partidas redondeadas a centavos | 1.767.164.544,76 |
| Planificado anual, total almacenado en la hoja | 1.767.164.544,77 |
| Asignación compartida BDH + BDHV | 694.079.253,04 |

La diferencia de un centavo en planificado se registra como redondeo; no se altera una partida para ocultarla. La celda combinada BDH/BDHV se guarda una sola vez en `presupuesto_social_asignado.parquet`. El devengado sí se conserva por bono. No se confunden planificado, aprobado, codificado, devengado, habilitado y acreditado.

El nuevo presupuesto cubre los grupos de gasto 58, 57 y 78. Es distinto del universo de `presupuesto_institucional.parquet` y del detalle territorial VIS/VIE. Se conserva cada universo por separado. Las diferencias inferiores a USD 1 entre los devengados acumulados de los bonos regulares del detalle territorial anterior y el archivo aprobado quedan sin distribuir geográficamente: el aprobado nacional prevalece en las nuevas series sociales. Las 11 repeticiones idénticas señaladas en la fuente institucional anterior se mantienen con su marca de revisión; no se eliminan sin una clave presupuestaria que demuestre duplicidad contable.

El resumen `resumen_social_mensual.parquet` cruza beneficiarios disponibles con devengado mensual y acumulado. El campo `criterio_beneficiarios` identifica cobertura, habilitación o acreditación. Un conteo de habilitados no prueba que todos hayan cobrado; un devengado tampoco equivale a una acreditación bancaria. Comisiones bancarias no tiene beneficiarios. PTV agrupa adultos y menores únicamente para corresponder al programa presupuestario.

## Jóvenes en Acción

La tercera fase tiene **150.000 habilitados** y presupuesto de **USD 180.000.000**, consistentes con la [publicación oficial del MDH sobre la tercera edición](https://www.desarrollohumano.gob.ec/en-quevedo-la-distrital-del-mdh-hizo-el-lanzamiento-de-la-tercera-edicion-del-programa-jovenes-en-accion/) y con el [recurso público de fases de SGDE](https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/datos/kpis/jovenes_accion/periodos.csv). No se presenta ese número como personas pagadas cada mes.

| Medida de la fase 3 | Valor |
|---|---:|
| Registrados, tablero SGDE | 637.808 |
| Habilitados de la fase | 150.000 |
| Devengado acumulado del archivo aprobado, septiembre | USD 107.526.000,00 |
| Ejecución acumulada publicada en SGDE, septiembre | USD 107.475.600,00 |
| Diferencia aprobado menos SGDE | **USD 50.400,00** |
| Personas acreditadas en SANC01, julio | 126.681 |
| Acreditaciones disponibles de fase 3 en SANC01 | USD 50.672.400,00 |

Para ejecución se utiliza el archivo aprobado; ambas cifras se conservan en `jovenes_accion_fase3.parquet`. Las acreditaciones SANC01 solo aportan julio para esta fase y no permiten verificar todos sus pagos. No se fuerza su igualdad con habilitados o devengado.

Al 25 de octubre la cuarta fase ya estaba anunciada, pero su ejecución estaba prevista para el **4 de noviembre al 31 de diciembre de 2026**. La [publicación oficial del MDH del 21 de octubre](https://www.desarrollohumano.gob.ec/el-gobierno-nacional-y-la-camara-de-industrias-y-produccion-firman-acuerdo-para-promover-la-participacion-del-sector-privado-en-el-programa-jovenes-en-accion/) describe una meta de 700.000 jóvenes. Esa meta no se incorpora como beneficiarios efectivos. La última fase con ejecución documentada en los insumos disponibles es la tercera. Cuando SGDE publique una fase posterior con ejecución, el importador exige revisar su homologación y respaldo oficial.

## Transferencias simplificadas y calidad

- **SANC01:** se procesaron 2.712.029 registros; 422.587 repetían la misma transacción bajo archivos distintos. La clave incluye programa, fase, identificador, valor, respuesta, fecha de acreditación, referencia y observación. Se excluyeron 76.838 respuestas que no estaban acreditadas. El código SPI `1` corresponde a acreditación según el [instructivo de giros y transferencias del MEF](https://esigef.finanzas.gob.ec/esigef/Ayuda/RUP-DS-048%20INSTRUCTIVO%20GESTION%20DE%20GIROS%20Y%20TRANSFERENCIAS.pdf). Las salidas solo contienen conteos e importes.
- **Antrópicos:** los 226.616 registros incluían versiones sucesivas. Se seleccionó la última versión identificable por familia y año: 91.832 registros. No se sumaron versiones de julio, agosto y septiembre. El tabulado agregado recibido muestra sobreconteos asociados a esas repeticiones y queda únicamente como control. No se aplicó una división general por cuatro.
- **Contingencias:** 5.877 registros. Se revisaron duplicados de negocio completos; las coincidencias parciales de persona y fecha no se eliminaron cuando los demás datos eran diferentes.
- **Fechas de cobro:** faltan en 24.949 registros antrópicos y 1.051 de contingencias. Los cobros con fecha llegan hasta junio y julio de 2026, respectivamente. Las habilitaciones llegan a octubre. No se usó el nombre del archivo ni el mes de habilitación como fecha ficticia de pago.
- **Orfandad:** septiembre reporta 464 beneficiarios; su devengado aprobado es USD 83.680,80 del mes y USD 709.024,20 acumulados. Julio contiene 873 registros, pero 443 beneficiarios distintos. Junio carece de conteo en el archivo recibido; el cero explícito del presupuesto de junio no autoriza imputar cero beneficiarios.
- **Territorio:** los únicos nacionales se calculan directamente sobre los registros de entrada. Sumar únicos territoriales puede contar dos veces a una persona; no se usa esa suma como total nacional.

No se publican cédulas, nombres personales, cuentas, referencias bancarias ni teléfonos de los insumos recibidos. Se conservan los hashes de entrada para trazabilidad y los controles agregados para revisión.

## Scraping laboral

Se extrajeron los recursos JSON/CSV que utilizan las dos páginas solicitadas:

- [Contratos](https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/MDTDH/kpi_contratos.html).
- [KPIs de trabajo](https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/MDTDH/kpis.html#/kpis-trabajo).

El corte publicado es **23 de octubre de 2026**: **13.511.660** contratos registrados, **2.789.748** vigentes y **10.721.912** finalizados. Se guardan las ocho tabulaciones publicadas. Los desgloses por cantón, rama, tipo, etnia y actividad concilian con la base por estado y provincia. La tabla de nacionalidad solo cubre personas extranjeras. Las empresas tienen agregados `TOTAL` independientes de sus provincias. No hay parroquias publicadas.

Los jubilados se describen como **expedientes**, según la fuente: en 2026, **4.686 expedientes** y **USD 229.841.799,89**, acumulados al 18 de septiembre. Se sustituyó la noticia anterior, que solo permitía expresar «más de USD 229 millones». Las cifras y sus fechas aparecen en el tablero y en sus exportaciones.

El stock del 23 de octubre no se divide ni se compara como parte del mismo corte con las cohortes mensuales observadas el 22. Sus fechas se presentan por separado. El workflow diario agrega nuevas fotos por `fecha_corte` y sustituye una foto de la misma fecha cuando la fuente la corrige; no duplica el mismo corte por volver a consultar.

## Actualización y comprobaciones

La guía operativa y el diccionario de tablas están en [data/README.md](../data/README.md). `update_history.py` acepta archivos parciales por tipo, pero cada partición de mes/programa que se entrega debe estar completa. No elimina otros meses. Valida toda la carga en una carpeta temporal antes de reemplazar archivos; la escritura local es por archivo y la publicación Git se realiza en un único commit.

Se verifican claves, periodos, conteos, asignaciones compartidas, importes decimales, conciliaciones territoriales, ausencia de identificadores nominales, conservación de faltantes y recuperación ante entradas inválidas. Las pruebas de la aplicación y de sus exportaciones comprueban que cada indicador mantenga su fuente, unidad y fecha de corte.

Comprobación final de esta entrega: **93 pruebas y 30 subpruebas satisfactorias**, incluyendo reconstrucción desde las fuentes Parquet. Dos cargas completas consecutivas de los insumos produjeron los mismos hashes en todos los archivos; la repetición del scraping reproducido también fue idéntica. Se revisó visualmente el PDF laboral y se verificaron los contenidos y fuentes de las exportaciones PowerPoint y Excel.

El conjunto de 42 Parquet ocupa 2.067.887 bytes; las 25 nuevas series ocupan 1.106.503 bytes. Estos tamaños corresponden a esta entrega y crecerán al incorporar nuevos meses y cortes.
