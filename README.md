# InfoReportes · MTDH

Sistema de estadísticas y reportes institucionales del Ministerio de Trabajo y Desarrollo Humano, construido en **Streamlit**. Reúne acceso con usuario y contraseña, un tablero con el mapa del Ecuador, filtros por ámbito, territorio y programa, y un centro de reportes que exporta exactamente la misma selección a **Excel, PDF, Word y PowerPoint**.

## Descomprimir, subir y abrir

El paquete está preparado para subir su contenido directamente a GitHub. Incluye los Parquet depurados, las plantillas, el logo, las tipografías y una cuenta lista para ingresar. **No necesitas ejecutar scripts de configuración ni pegar Secrets para el primer despliegue.**

| Acceso | Valor |
| --- | --- |
| Usuario | `admin` |
| Contraseña | `admin12345678` |

1. Descomprime el paquete y abre la carpeta del proyecto.
2. Sube **todo su contenido** a un repositorio privado de GitHub. `app.py` y `requirements.txt` deben quedar en la raíz del repositorio; conserva también las carpetas `config`, `src`, `assets`, `static`, `templates`, `data` y `.streamlit` (allí viven el tema institucional y las tipografías web).
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

- **Tablero:** una franja institucional con el mapa del Ecuador abre la consulta. Eliges el ámbito (panorama integral, bonos y pensiones o protección integral), las provincias y los programas; los indicadores principales muestran cuánto representa la selección del total nacional. Debajo están la cobertura por programa, los recursos y su distribución, el territorio (mapa interactivo, posición de cada provincia y composición por programa), el detalle verificable con descarga en Excel o CSV, las definiciones con los controles de calidad y las referencias históricas y cantonales.
- **Centro de reportes:** eliges formato, título y si incluir el análisis territorial; una vista previa muestra la pieza antes de generarla. El archivo conserva la selección del tablero, sus definiciones y los datos no disponibles.
- **Actualizar los datos:** ejecutar el proceso Excel → Parquet con validaciones de claves, programas, provincias, montos y conciliación de acumulados.
- **Agregar ejecución presupuestaria:** incorporar un CSV complementario validado; los valores ausentes siguen siendo nulos, no ceros.

### Formatos de reporte

| Formato | Contenido |
| --- | --- |
| **Excel** (formato principal) | Libro de hasta siete hojas: portada con mapa e índice enlazado, resumen ejecutivo con gráficos nativos, una hoja por ámbito, territorio (mapa, ranking y composición), detalle con filtros y totales que se recalculan, y notas metodológicas. Todas las cifras son números reales con formato, los totales son fórmulas y el libro trae un tema de Office «MTDH Institucional», así que lo que el lector agregue hereda la paleta. |
| **PDF** | Boletín listo para imprimir: portada con mapa, indicadores, capítulos por ámbito, página territorial y criterios de lectura. |
| **Word** | El mismo boletín, editable, para ajustar la redacción antes de publicar. |
| **PowerPoint** | Presentación 16:9 con gráficos nativos editables, mapa territorial y notas para quien expone. |

Las exportaciones se generan en memoria. No requieren Microsoft Office, LibreOffice, un navegador instalado ni servicios externos.

## Diseño e identidad visual

- **Paleta institucional en un solo lugar.** `src/theme.py` reúne el morado del logo y del boletín, la lavanda y la niebla de sus superficies, el oro del escudo y una rampa morada generada en OKLCH. La aplicación, los gráficos y los cuatro formatos de reporte leen esos valores; el tema de Streamlit vive en `.streamlit/config.toml`. Procedencia de cada color: [assets/brand/PROCEDENCIA.md](assets/brand/PROCEDENCIA.md).
- **Tipografías.** Montserrat para títulos y cifras, Public Sans para el texto, ambas servidas por la propia aplicación desde `static/fonts` (sin depender de Google Fonts en tiempo de ejecución). Excel, Word y PowerPoint usan Century Gothic y Calibri, instaladas con Microsoft Office.
- **Mapas.** El encabezado muestra la cobertura por provincia y resalta en oro el territorio elegido; el tablero tiene un mapa interactivo y los reportes incluyen mapas estáticos. Todos se dibujan con un GeoJSON local de Natural Earth, sin teselas ni servicios externos, con Galápagos en recuadro y la línea ecuatorial. Detalles: [assets/geo/PROCEDENCIA.md](assets/geo/PROCEDENCIA.md).
- **Sin secciones desplegables.** Todo el contenido está a la vista; las opciones se eligen con controles segmentados y pestañas.
- **Teléfonos.** La aplicación detecta el dispositivo: en el teléfono los indicadores pasan a dos columnas, los gráficos se compactan, la barra de herramientas de los gráficos se oculta y la matriz territorial se desliza de lado en lugar de comprimirse.
- **Movimiento con intención.** Una sola secuencia de entrada: las provincias del mapa se encienden de oeste a este y las cifras clave cuentan hasta su valor. Si el sistema pide reducir el movimiento, la aplicación lo respeta.
- **Cifras en formato ecuatoriano.** Pantalla, gráficos y tablas muestran `1.234.567,89` sin importar el idioma del navegador; las tablas siguen ordenándose por el valor numérico. En los archivos de Office las cifras son números reales y se presentan según la configuración regional del equipo.

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
- **Ejecución presupuestaria:** aparece como no disponible hasta aportar un insumo complementario validado.
- **Pensión PAM y Pensión PCD:** tienen cero beneficiarios actuales, pero saldos históricos; se conservan para conciliar todos los montos.
- **Referencias 2024/2025:** no tienen mes de corte documentado. Se consultan por separado, sin tasas interanuales que impliquen períodos equivalentes.
- **Referencia cantonal:** la hoja `calculos dic` contiene prorrateos, período desconocido y campos incompletos. No representa gasto cantonal observado ni se suma al corte vigente.

Las otras dos secciones del boletín original no están respaldadas por este Excel. Esta versión implementa los dos ámbitos solicitados; no incorpora contratos, contingencias u otros indicadores sin fuente.

Consulta [docs/DATOS.md](docs/DATOS.md) para el diccionario, reglas y controles completos. El boletín original se conserva en `docs/reference/` como referencia de conciliación y marca, y su logo institucional se utiliza sin recrearlo. La propuesta visual toma sus colores y marca; no sustituye la aprobación de Comunicación.

## Estructura modular

```text
app.py                     Punto de entrada: franja institucional, tablero y centro de reportes
src/theme.py               Paleta, rampas, tipografías, vocabulario y definiciones institucionales
src/geo.py                 Provincias del Ecuador: polígonos, recuadro de Galápagos y mapa SVG
src/ui.py                  Componentes visuales y tablas con cifras en formato ecuatoriano
src/charts.py              Gráficos interactivos y mapa del tablero (Plotly)
src/auth.py                Acceso, sesión y salida
src/security.py            Hashes y control de intentos
src/etl.py                 Depuración y esquema Parquet
src/data.py                Lectura, filtros y agregación compartida
src/reference_views.py     Referencias históricas y cantonales
src/reports/               Contexto común y exportadores Excel, PDF, Word y PowerPoint
src/reports/excel.py       Libro Excel institucional (formato principal)
src/reports/charts.py      Gráficos y mapas de los reportes (matplotlib)
.streamlit/config.toml     Tema institucional de Streamlit y tipografías web
static/fonts/              Montserrat y Public Sans para la interfaz (SIL OFL)
assets/                    Estilos, logo, escudo, tipografías de los reportes y límites provinciales
config/access.toml         Cuenta inicial incluida, con contraseña en hash
scripts/build_data.py      Actualización del insumo
scripts/configure_auth.py  Configuración opcional de cuentas
templates/                 Plantilla PowerPoint editable
data/processed/            Base vigente, referencias y manifiesto
data/source/               Excel original agregado
data/templates/            Insumos complementarios
tests/                     Validación de datos, seguridad, interfaz, mapas y exportaciones
examples/                  Ejemplos de los reportes generados
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
- [Natural Earth, límites de primer nivel](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/)
- [Public Sans](https://public-sans.digital.gov/) y [Montserrat](https://fonts.google.com/specimen/Montserrat)
- [XlsxWriter](https://xlsxwriter.readthedocs.io/)

Los datos pertenecen al insumo aportado por el usuario. La identidad institucional y sus marcas pertenecen a sus titulares.
