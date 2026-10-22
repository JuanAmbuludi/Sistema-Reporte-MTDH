# Gestión laboral · fuentes de la tabla 4

La tercera base se construye desde fuentes públicas del Ministerio del Trabajo. Se conserva separada de los agregados provinciales VIS/VIE porque sus indicadores, ámbitos y cortes no son equivalentes. No contiene datos nominales.

## Fuentes y alcance de esta entrega

| Indicador | Fuente | Período y significado |
| --- | --- | --- |
| Contratos vigentes, total | [Tablero oficial SUT](https://sut.trabajo.gob.ec/contratos-web/mrl/contenido/indicadores/indiContratos.xhtml), tarjeta «Cantidad de Contratos», Estado contrato = Vigente, demás filtros sin selección | Total nacional del tablero al consultar. Se guarda el rango de fechas visible y la actualización indicada por la fuente. No es el total al cierre de septiembre. |
| Contratos del mes con estado vigente al consultar | El mismo tablero, página «Evolución contratos», gráfico «Evolución mensual y acumulada de contratos» | Enero–septiembre de 2026 en la entrega inicial. La fecha se interpreta conforme al filtro y eje «Mes» de la fuente. No se afirma que sea una serie de stocks al cierre mensual ni el total de nuevas contrataciones de todos los estados. |
| Exservidores y extrabajadores compensados | [Noticia oficial de compensaciones jubilares](https://www.trabajo.gob.ec/el-gobierno-del-presidente-daniel-noboa-cumple-con-cerca-de-15-mil-exservidores-y-extrabajadores-mediante-el-pago-de-sus-compensaciones-jubilares/) | Balance durante 2026, sin mes de cierre explícito en la frase anual. Publicada el 25 de agosto de 2026. |
| Recursos para compensaciones jubilares | Misma noticia | Límite inferior publicado en USD; `operador = ">"`. No equivale a ejecución presupuestaria general del Ministerio. |

La noticia también contiene un balance plurianual. El extractor identifica **solo la frase anual**; no mezcla ambos universos. La fecha de publicación, la actualización del tablero y la fecha de consulta son campos distintos del período estadístico.

No se incorporan las cifras del boletín original como sustituto de una fuente web faltante. Tampoco se incluyen contingencias, el porcentaje de ejecución ni la ejecución presupuestaria general.

## Archivos

| Archivo | Uso |
| --- | --- |
| `data/processed/gestion_laboral.parquet` | Última extracción completa, con esquema Arrow tipado y valores decimales. |
| `data/processed/gestion_laboral.csv` | La misma base, visible en GitHub e importable en Excel. CSV separado por comas, decimales con punto, UTF-8 con BOM. |
| `data/processed/manifest_laboral.json` | Períodos disponibles, controles, huellas SHA-256 y ubicación de la evidencia. |
| `data/processed/laboral_evidencias/<consulta_id>.json` | Etiquetas exactas leídas del DOM, filtros, frase anual utilizada y metadatos de procedencia. No se guardan cookies ni credenciales. |
| `data/processed/laboral_cortes/<consulta_id>.parquet` | Copia de cada extracción para revisar cambios posteriores. No sumar cortes entre sí. |
| `config/fuentes_laborales.json` | URLs oficiales y título del iframe del tablero. |
| `src/laboral_scraper.py` | Descarga del HTML y lectura del tablero público con Chromium/Playwright. |
| `src/laboral.py` | Validaciones, esquema y construcción de la base. |

La clave de cada observación es `consulta_id + indicador_id + periodo + territorio`; para observaciones sin mes, `periodo` es nulo y el identificador del indicador distingue el total y el balance anual.

## Diccionario de datos

| Campos | Interpretación |
| --- | --- |
| `consulta_id`, `fecha_consulta_utc` | Identificación y fecha UTC de la extracción. Reproducir evidencia mantiene esta fecha, no simula una consulta nueva. |
| `indicador_id`, `indicador` | Identificador estable y etiqueta legible de la métrica. |
| `territorio` | Ecuador; no se imputan valores provinciales. |
| `periodo`, `anio` | Primer día del mes como clave mensual; no es una fecha de evento. En jubilaciones solo se conoce el año. En el total consultado ambos quedan nulos. |
| `granularidad` | `mensual`, `consulta` o `anual_corte_no_documentado`. |
| `naturaleza` | `cohorte_con_estado_actual`, `stock_consultado` o `acumulado_anual_publicado`. Impide tratar las tres como una misma serie. |
| `valor`, `operador`, `unidad` | Decimal de 2 posiciones, relación `=` o `>`, y contratos/personas/USD. Cuando el operador es `>`, el valor es un límite inferior, no una estimación puntual. |
| `filtro_desde`, `filtro_hasta` | Fechas del filtro utilizado en el SUT. En una consulta anual se repiten en sus filas mensuales. Nulas para jubilaciones. |
| `actualizacion_fuente` | Fecha/hora tal como la publica el SUT, sin inventar una zona horaria. |
| `publicacion_fuente` | Metadato de publicación de la noticia; no es su corte estadístico. |
| `fuente_url`, `fuente_id` | Enlace y código de la fuente que respalda la observación. |
| `evidencia_sha256`, `filtros_json`, `nota` | Huella del registro de extracción, filtros y límites de interpretación. |

No sumar unidades distintas, el stock y sus cohortes, ni observaciones de diferentes consultas. Una misma persona puede tener más de un contrato. La suma mensual solo se utiliza para conciliar el gráfico con la tarjeta filtrada del mismo intervalo.

## Ejecutar y actualizar

Python 3.12, acceso a internet y Chromium instalado:

```bash
pip install -r requirements-scraping.txt
python -m playwright install chromium
python scripts/build_data.py data/source/Acumulado_VIS_VIE.xlsx --period 2026-09 --period-source "Boletín de septiembre 2026" --incluir-laboral
```

En Linux, si faltan bibliotecas del sistema para Chromium, la instalación oficial es `python -m playwright install --with-deps chromium` (puede requerir permisos de administrador en ese equipo). Las dependencias del scraping están separadas de `requirements.txt`; Streamlit no necesita navegador ni consulta sitios externos al iniciarse.

Para consultar otro intervalo completo o años anteriores disponibles:

```bash
python scripts/build_data.py --solo-laboral --laboral-desde 2025-01 --laboral-hasta 2026-09
```

El rango se contrasta con la disponibilidad visible y se consulta un año por vez. Si un mes falta o el eje no identifica el año, se interrumpe sin inventar ceros. La entrega inicial contiene nueve meses; otros años se obtienen ejecutando el comando y dependen de la disponibilidad de la fuente. Cada actualización reemplaza la base vigente y conserva los cortes y evidencias previos.

`--mostrar-navegador` permite observar los filtros durante la extracción. `--fuentes-laborales ruta/config.json` admite otro archivo de configuración, restringido a los dominios oficiales. No se busca automáticamente la noticia más reciente de jubilaciones: una nueva publicación debe revisarse y configurarse. Si cambia su redacción, el parser exige revisión en vez de tomar otra cifra por aproximación.

Para reconstruir exactamente un corte sin conectarte a internet, copia la ruta `evidencia` que figura en el manifiesto:

```bash
python scripts/build_data.py --solo-laboral --laboral-evidencia data/processed/laboral_evidencias/ARCHIVO_INDICADO_EN_EL_MANIFIESTO.json
```

Este modo sirve para reproducir y auditar, **no para actualizar**. Puede combinarse con el Excel y `--incluir-laboral`; conserva los períodos y la fecha original de la evidencia.

## Controles y fallos

- Conteos exactos desde etiquetas accesibles del gráfico; nunca se convierten rótulos como «52,1 mil» en cifras exactas.
- Estado = Vigente, otros filtros sin selección, fechas visibles coincidentes, año correcto, meses completos y sin duplicados.
- Suma de cada serie igual a la tarjeta del intervalo, y cohortes incluidas no mayores que el total consultado.
- Actualización de fuente idéntica entre el total y todas las series. Si cambia durante la ejecución, se exige repetirla.
- Noticia anual reconocida con conteo, moneda y operador conservados. Ausencias y cambios de formato generan errores.
- Todos los insumos se validan en una carpeta temporal antes de reemplazar archivos. Un fallo de red o validación conserva las bases entregadas. La publicación local reemplaza archivos individualmente y los manifiestos al final; no ofrece una transacción de sistema de archivos frente a cortes de energía.

El scraper no incluye valores de respaldo ni utiliza credenciales. Si el tablero cambia de diseño, revise los selectores en `src/laboral_scraper.py`. Si el sitio requiere acceso o verificación humana, el proceso falla; no intenta evadir controles. Se puede seguir usando la última extracción validada, con su fecha visible.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

`tests/test_laboral.py` verifica formatos, precisión, filtros, conciliación, ausencia de corte mensual en jubilados, trazabilidad, reproducción y conservación de las bases ante un fallo en una ejecución combinada. Las pruebas son locales y no dependen de que el Ministerio esté disponible.

Para el consumo posterior en Streamlit:

```python
import pandas as pd
laboral = pd.read_parquet("data/processed/gestion_laboral.parquet")
serie = laboral.loc[laboral["indicador_id"].eq("contratos_del_mes_vigentes")].sort_values("periodo")
```

La interfaz y sus exportaciones deben mostrar `operador`, `naturaleza`, fuente y fecha de consulta antes de incorporar estos indicadores. Esta entrega añade la base y su generador; no modifica todavía los capítulos visibles del tablero.
