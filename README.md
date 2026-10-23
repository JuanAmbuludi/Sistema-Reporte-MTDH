# InfoReport · MTDH

Sistema de indicadores estratégicos y reportes institucionales del Ministerio de Trabajo y Desarrollo Humano, construido en **Streamlit**. Reúne acceso con usuario y contraseña, un tablero con el mapa del Ecuador, consulta por **periodo (año y mes), ámbito, territorio y programa**, y un centro de reportes con tres productos generados con exactamente la misma selección: **resumen ejecutivo de una página (PDF), presentación de tres diapositivas (PowerPoint) y libro de datos (Excel)**.

## Descomprimir, subir y abrir

El paquete está preparado para subir su contenido directamente a GitHub. Incluye los Parquet depurados, el logo, los iconos, las tipografías y una cuenta lista para ingresar. **No necesitas ejecutar scripts de configuración ni pegar Secrets para el primer despliegue.**

| Acceso | Valor |
| --- | --- |
| Usuario | `admin` |
| Contraseña | `admin12345678` |

1. Descomprime el paquete y abre la carpeta del proyecto.
2. Sube **todo su contenido** a un repositorio privado de GitHub. `app.py` y `requirements.txt` deben quedar en la raíz del repositorio; conserva también las carpetas `config`, `src`, `assets`, `static`, `data` y `.streamlit` (allí viven el tema institucional y las tipografías web).
3. En Streamlit Community Cloud, selecciona **Create app**, tu repositorio, la rama `main` y **`app.py`**. Elige **Python 3.12** en las opciones avanzadas y despliega.
4. Ingresa con `admin` y `admin12345678`.

Cada cambio que llega a la rama `main` se refleja en la aplicación publicada.

## Inicio rápido en tu equipo

Requiere **Python 3.12**. Abre una terminal en esta carpeta:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Ingresa con la cuenta indicada arriba. La base Parquet ya está incluida; puedes abrir el sistema sin reprocesar el Excel.

En Windows también puedes ejecutar **INICIAR_WINDOWS.bat**. Instala las dependencias en un entorno propio y abre la aplicación con el acceso ya preparado.

## Configuración de acceso opcional

La cuenta inicial se encuentra en **`config/access.toml`**, con la contraseña almacenada como hash. Ese archivo forma parte del proyecto y permite el acceso inmediato.

Si después deseas usar otras cuentas, puedes configurar una sección **`[auth]`** en **Settings → Secrets** de Streamlit Cloud o en `.streamlit/secrets.toml` al trabajar localmente. Cuando existe esa sección, **sustituye por completo** el acceso incluido en `config/access.toml`; no mezcla automáticamente las cuentas. El archivo de Secrets personal está excluido del repositorio por `.gitignore`. No se incluye la cuenta personal del usuario en el acceso distribuido.

El script `scripts/configure_auth.py` se conserva como herramienta opcional: sus constantes `USERNAME`, `PASSWORD` y `NAME` permiten generar o actualizar una cuenta en un archivo de Secrets. No es necesario ejecutarlo para abrir esta entrega. Para desactivar una cuenta en tu configuración, establece `enabled = false`.

La contraseña se guarda como hash PBKDF2-SHA256 con sal aleatoria y 600.000 iteraciones. La sesión caduca tras 30 minutos sin actividad (comprobados al interactuar) y tiene una duración máxima de 8 horas. Cinco intentos fallidos bloquean temporalmente esa cuenta durante cinco minutos. El límite se comparte entre sesiones del mismo proceso; al reiniciar el servidor se reinicia ese contador. Para una instalación con múltiples servidores se recomienda integrar el proveedor de identidad institucional.

## Qué puedes hacer

- **Tablero:** la franja institucional abre la consulta con el **año** y el **mes** del corte, el **ámbito** (transferencias monetarias o servicios de protección integral, nunca mezclados), las provincias y los programas. El mapa del Ecuador muestra el indicador territorial elegido (beneficiarios o usuarios, unidades de atención, presupuesto del año o presupuesto acumulado) y resalta en oro el territorio seleccionado. Siguen las cifras clave, con su peso en el total nacional cuando hay un filtro; los resultados por programa (personas y presupuesto); los resultados por provincia (posición de cada provincia y distribución por programa), y el cuadro de resultados con descarga en Excel.
- **Centro de reportes:** eliges el producto y el título; una vista previa muestra la pieza antes de generarla. Cada documento conserva el periodo, el ámbito y el territorio seleccionados, y su nombre de archivo los identifica (por ejemplo, `MTDH_resumen_transferencias_2026-09.pdf`).
- **Actualizar los datos:** ejecutar el proceso Excel → Parquet con validaciones de claves, programas, provincias, montos y conciliación de acumulados.
- **Agregar ejecución presupuestaria:** incorporar un CSV complementario validado. El tablero muestra esa columna solo cuando la selección tiene ejecución registrada.

### Periodos disponibles

| Año | Mes | Etiqueta en pantalla y documentos |
| --- | --- | --- |
| 2026 | Septiembre | Corte septiembre 2026 |
| 2025 | Corte anual | Año 2025 |
| 2024 | Corte anual | Año 2024 |

Cada periodo se consulta por separado: las cifras no se suman ni se comparan entre periodos. Cuando la base incorpore nuevos cortes mensuales, el selector de mes los mostrará automáticamente.

### Productos del centro de reportes

| Producto | Contenido |
| --- | --- |
| **Resumen ejecutivo** (PDF, una página) | Placa institucional con el mapa, cuatro cifras clave con iconos, mapa y principales provincias, resultados por programa y tres aspectos destacados redactados para la toma de decisiones. |
| **Presentación** (PowerPoint, tres diapositivas) | 1) Portada con las cifras clave; 2) resultados por provincia, con mapa, principales provincias y un hallazgo territorial; 3) resultados por programa, con gráfico nativo editable y aspectos destacados. Iconos, formas y textos son objetos de PowerPoint editables, con notas para quien expone. |
| **Libro de datos** (Excel) | Cinco hojas: resumen, resultados por programa o servicio, provincias, detalle con filtros y totales que se recalculan, y ficha técnica. Las cifras son números reales con formato y el libro trae un tema de Office «MTDH Institucional». |

Las exportaciones se generan en memoria. No requieren Microsoft Office, LibreOffice, un navegador instalado ni servicios externos. Hay ejemplos en `examples/`.

## Diseño e identidad visual

- **Información estratégica, sin notas aclaratorias.** El tablero y los documentos usan títulos formales y descriptivos, sin preguntas, instrucciones de uso ni advertencias técnicas, y no repiten la misma cifra en varios gráficos.
- **Un ámbito a la vez.** Transferencias monetarias y servicios de protección integral se consultan y exportan por separado; ningún gráfico ni total los combina.
- **Gráficos neutros.** Los gráficos reciben un indicador (nombre, unidad y formato) en lugar de una columna fija, así que sirven igual para beneficiarios, usuarios, unidades o presupuesto y para los indicadores que se agreguen después (ver «Agregar nuevos indicadores»).
- **Paleta institucional en un solo lugar.** `src/theme.py` reúne el morado del logo y del boletín, la lavanda y la niebla de sus superficies, el oro del escudo y una rampa morada generada en OKLCH. La aplicación, los gráficos y los tres productos leen esos valores; el tema de Streamlit vive en `.streamlit/config.toml`. Procedencia de cada color: [assets/brand/PROCEDENCIA.md](assets/brand/PROCEDENCIA.md).
- **Tipografías e iconos.** Montserrat para títulos y cifras y Public Sans para el texto, servidas por la propia aplicación desde `static/fonts`. Excel y PowerPoint usan Century Gothic y Calibri, instaladas con Microsoft Office. Los iconos (Lucide, licencia ISC) están en `assets/icons/png` en blanco, morado y oro.
- **Mapas.** Se dibujan con la cartografía del INEC 2015 (parroquias, cantones, provincias y zonas de planificación) incluida en el proyecto, sin teselas ni servicios externos, con Galápagos en recuadro y la línea ecuatorial. Detalles: [assets/geo/PROCEDENCIA.md](assets/geo/PROCEDENCIA.md).
- **Sin secciones desplegables.** Todo el contenido está a la vista; las opciones se eligen con controles segmentados.
- **Teléfonos.** En el teléfono las cifras clave pasan a dos columnas, los gráficos se compactan, la matriz territorial y las tablas se deslizan de lado y la primera columna de las tablas queda fija.
- **Movimiento con intención.** Una sola secuencia de entrada: las provincias del mapa se encienden de oeste a este y las cifras clave cuentan hasta su valor. Si el sistema pide reducir el movimiento, la aplicación lo respeta.
- **Cifras en formato ecuatoriano.** Pantalla, gráficos y tablas muestran `1.234.567,89` sin importar el idioma del navegador; las tablas siguen ordenándose por el valor numérico. En los archivos de Office las cifras son números reales y se presentan según la configuración regional del equipo.

## Agregar nuevos indicadores

Los ámbitos y sus indicadores se declaran en `src/indicators.py`. Cada `Module` define su nombre, la sección de datos que lee, el nombre de sus personas (beneficiarios, usuarios) y sus indicadores adicionales. El tablero, el mapa, los rankings, el cuadro de resultados y los tres productos leen esa declaración, de modo que un nuevo ámbito (por ejemplo, indicadores de contingencia o laborales) se integra al agregar sus filas a la base con la misma estructura de periodo, categoría y provincia, y declarar su `Module`. Si los nuevos datos tienen otra estructura, conviene ajustar primero el proceso de `src/etl.py`.

## Actualizar la base Parquet

El Excel agregado original está en `data/source/Acumulado_VIS_VIE.xlsx`. Para reproducir la base incluida:

```bash
python scripts/build_data.py data/source/Acumulado_VIS_VIE.xlsx --period 2026-09 --period-source "Boletín de septiembre 2026; conciliación con los totales del Excel"
```

Para otro corte, sustituye el archivo y el mes por el corte real. El mes es obligatorio porque no está identificado dentro del Excel. El proceso conserva la procedencia de cada fila, una huella SHA-256 del insumo, un manifiesto de calidad y un esquema Arrow tipado. Los montos se almacenan con precisión decimal en Parquet.

La actualización reemplaza el corte vigente. Las hojas históricas del insumo se mantienen como referencias separadas; el sistema no fabrica una serie mensual ni acumula conteos entre meses. Revisa los controles y vuelve a subir `data/processed/` al repositorio para que Streamlit use la nueva base.

Para incorporar presupuesto ejecutado:

```bash
python scripts/build_data.py data/source/Acumulado_VIS_VIE.xlsx --period 2026-09 --period-source "Corte institucional validado" --ejecucion ruta/ejecucion_validada.csv
```

La plantilla está en `data/templates/ejecucion_presupuestaria.csv`. Las claves deben corresponder a período, programa y provincia ya existentes. Si solo se completa parte de la selección, el sistema no presenta la suma parcial como ejecución total.

## Cómo interpretar las cifras

El insumo contiene **296 agregados provinciales**, no una base nominal de personas. En septiembre de 2026 reporta **1.578.019 beneficiarios de bonos y pensiones**, **456.239 usuarios de servicios** y **11.158 unidades de atención**. Esos conteos no permiten calcular personas únicas entre programas, provincias o períodos. Tampoco identifican físicamente las unidades para deduplicarlas.

- **Monto fiscal:** valor de la columna `Presupuesto 2026`. El archivo no certifica si corresponde a devengado, pagado, codificado u otra fase presupuestaria; por eso no se redefine como ejecución ni como monto mensual transferido.
- **Monto de gobierno:** acumulado anterior más monto fiscal; sus componentes no se suman nuevamente al total.
- **Ejecución presupuestaria:** no forma parte de esta base; la aplicación la muestra solo si se incorpora un insumo complementario validado.
- **Pensión PAM y Pensión PCD:** tienen cero beneficiarios actuales, pero saldos históricos; se conservan para conciliar todos los montos.
- **Periodos 2024 y 2025:** provienen de las hojas de referencia anual del Excel, sin mes de corte. Se consultan como «Año 2024» y «Año 2025», cada uno por separado y sin tasas interanuales.
- **Referencia cantonal:** la hoja `calculos dic` contiene prorrateos con período desconocido y campos incompletos. Se conserva en `data/processed/` para trazabilidad, pero no se muestra en el tablero ni en los reportes.

Las otras dos secciones del boletín original no están respaldadas por este Excel. Esta versión implementa los dos ámbitos solicitados; no incorpora contratos, contingencias u otros indicadores sin fuente.

Consulta [docs/DATOS.md](docs/DATOS.md) para el diccionario, reglas y controles completos. El boletín original se conserva en `docs/reference/` como referencia de conciliación y marca, y su logo institucional se utiliza sin recrearlo. La propuesta visual toma sus colores y marca; no sustituye la aprobación de Comunicación.

## Estructura modular

```text
app.py                     Punto de entrada: franja institucional, tablero y centro de reportes
src/indicators.py          Ámbitos (transferencias, servicios) e indicadores neutrales por periodo
src/theme.py               Paleta, rampas, tipografías y vocabulario institucional
src/geo.py                 Provincias del Ecuador: polígonos, recuadro de Galápagos y mapa SVG
src/ui.py                  Componentes visuales, iconos y tablas con cifras en formato ecuatoriano
src/charts.py              Gráficos del tablero (Plotly), comunes a todos los indicadores
src/data.py                Lectura de periodos, filtros y agregación compartida
src/auth.py                Acceso, sesión y salida
src/security.py            Hashes y control de intentos
src/etl.py                 Depuración y esquema Parquet
src/reports/context.py     Contexto común de los tres productos (cifras, hallazgos y etiquetas)
src/reports/pdf.py         Resumen ejecutivo de una página
src/reports/pptx.py        Presentación de tres diapositivas
src/reports/excel.py       Libro de datos y cuadro de resultados en Excel
src/reports/charts.py      Mapas de los documentos (matplotlib)
.streamlit/config.toml     Tema institucional de Streamlit y tipografías web
static/fonts/              Montserrat y Public Sans para la interfaz (SIL OFL)
assets/                    Estilos, logo, escudo, iconos, tipografías de los documentos y límites provinciales
config/access.toml         Cuenta inicial incluida, con contraseña en hash
scripts/build_data.py      Actualización del insumo
scripts/configure_auth.py  Configuración opcional de cuentas
data/processed/            Base vigente, periodos anuales y manifiesto
data/source/               Excel original agregado
data/templates/            Insumos complementarios
tests/                     Validación de datos, seguridad, interfaz, mapas y documentos
examples/                  Ejemplos de los tres productos
```

## Comprobar la instalación

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Fuentes técnicas

- [Dependencias en Streamlit](https://docs.streamlit.io/deploy/concepts/dependencies)
- [Gestión de secretos](https://docs.streamlit.io/deploy/concepts/secrets)
- [Despliegue en Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Temas y tipografías en Streamlit](https://docs.streamlit.io/develop/concepts/configuration/theming)
- [Geoportal del INEC](https://www.ecuadorencifras.gob.ec/documentos/web-inec/Geografia_Estadistica/Micrositio_geoportal/index.html) y [ec-atlas](https://github.com/ccalobeto/ec-atlas) (límites 2015, licencia MIT)
- [Public Sans](https://public-sans.digital.gov/) y [Montserrat](https://fonts.google.com/specimen/Montserrat)
- [XlsxWriter](https://xlsxwriter.readthedocs.io/) y [python-pptx](https://python-pptx.readthedocs.io/)
- [Lucide](https://lucide.dev/) (iconos, licencia ISC)

Los datos pertenecen al insumo aportado por el usuario. La identidad institucional y sus marcas pertenecen a sus titulares.
