# InfoReport · MTDH

Sistema de indicadores estratégicos y reportes institucionales del Ministerio de Trabajo y Desarrollo Humano, construido en **Streamlit**. Reúne acceso con usuario y contraseña, un tablero con el mapa del Ecuador por **provincia, cantón y parroquia**, consulta por **periodo (año y mes), ámbito, territorio y programa**, y un centro de reportes que genera, con exactamente la misma selección, el **resumen ejecutivo (PDF), la presentación (PowerPoint) y el libro de datos (Excel)**.

Ámbitos disponibles, siempre por separado: **transferencias monetarias**, **servicios de protección integral**, **contingencias y compensaciones**, **Jóvenes en Acción**, **gestión laboral** y **presupuesto** (institucional y social). Cada pantalla y cada documento indican la fecha y hora de actualización de la información, su corte y su frecuencia (mensual; diaria para los contratos), y llevan el lema institucional: **«El corazón de Ecuador. Velamos por la calidad de vida de los ecuatorianos»**.

## Bases históricas y presupuesto aprobado

Las bases están organizadas en Parquet. [El catálogo](data/README.md) explica qué tabla usar y cómo incorporar meses anteriores o posteriores sin duplicar registros. [La revisión de octubre](docs/REVISION_BASES_2026.md) documenta las conciliaciones, faltantes y la validación de Jóvenes en Acción. VIS, VIE y el presupuesto social aprobado cubren enero a septiembre de 2026, y el tablero ofrece **cada uno de esos meses** con su detalle de provincia, cantón y parroquia. Los nombres y códigos territoriales se depuran al leer las series (sin alterar los totales) y los meses que todavía no se cierran en una fuente no se publican.

El scraping diario de las páginas SGDE incorpora contratos por provincia y cantón y actualiza el stock del tablero. Las fuentes no publican parroquias.

## Descomprimir, subir y abrir

El paquete está preparado para subir su contenido directamente a GitHub. Incluye los Parquet depurados, la cartografía, el logo, los iconos, las tipografías y una cuenta lista para ingresar. **No necesitas ejecutar scripts de configuración ni pegar Secrets para el primer despliegue.**

La configuración inicial de acceso está en `config/access.toml`. Para definir tus propias credenciales, consulta **Configuración de acceso opcional**.

1. Descomprime el paquete y abre la carpeta del proyecto.
2. Sube **todo su contenido** a un repositorio privado de GitHub. `app.py` y `requirements.txt` deben quedar en la raíz del repositorio; conserva también las carpetas `config`, `src`, `assets`, `static`, `data` y `.streamlit` (allí viven el tema institucional y las tipografías web).
3. En Streamlit Community Cloud, selecciona **Create app**, tu repositorio, la rama `main` y **`app.py`**. Elige **Python 3.12** en las opciones avanzadas y despliega.
4. Ingresa con las credenciales configuradas.

Cada cambio que llega a la rama `main` se refleja en la aplicación publicada. La aplicación vuelve a cargar sus propios módulos cuando su código cambia, de modo que un despliegue nuevo no queda mezclado con la versión anterior; si la nube conservara una sesión antigua, **Reboot app** en Streamlit Cloud la reinicia.

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

Ingresa con las credenciales configuradas. Las bases Parquet ya están incluidas; puedes abrir el sistema sin reprocesar los Excel.

En Windows también puedes ejecutar **INICIAR_WINDOWS.bat**. Instala las dependencias en un entorno propio y abre la aplicación con el acceso ya preparado.

## Configuración de acceso opcional

La cuenta inicial se encuentra en **`config/access.toml`**, con la contraseña almacenada como hash. Ese archivo forma parte del proyecto y permite el acceso inmediato.

Si después deseas usar otras cuentas, puedes configurar una sección **`[auth]`** en **Settings → Secrets** de Streamlit Cloud o en `.streamlit/secrets.toml` al trabajar localmente. Cuando existe esa sección, **sustituye por completo** el acceso incluido en `config/access.toml`; no mezcla automáticamente las cuentas. El archivo de Secrets personal está excluido del repositorio por `.gitignore`. No se incluye la cuenta personal del usuario en el acceso distribuido.

El script `scripts/configure_auth.py` se conserva como herramienta opcional: sus constantes `USERNAME`, `PASSWORD` y `NAME` permiten generar o actualizar una cuenta en un archivo de Secrets. No es necesario ejecutarlo para abrir esta entrega. Para desactivar una cuenta en tu configuración, establece `enabled = false`.

La contraseña se guarda como hash PBKDF2-SHA256 con sal aleatoria y 600.000 iteraciones. La sesión caduca tras 30 minutos sin actividad (comprobados al interactuar) y tiene una duración máxima de 8 horas. Cinco intentos fallidos bloquean temporalmente esa cuenta durante cinco minutos. El límite se comparte entre sesiones del mismo proceso; al reiniciar el servidor se reinicia ese contador. Para una instalación con múltiples servidores se recomienda integrar el proveedor de identidad institucional.

## Qué puedes hacer

- **Tablero.** La franja institucional abre la consulta con el **ámbito**, el **año** y el **mes** del corte, el territorio y los programas. Junto a ella, el mapa del Ecuador muestra el indicador elegido y cambia de nivel con el selector **Provincia · Cantón · Parroquia**; al elegir una provincia, el mapa se acerca a ella y un localizador indica su ubicación. Siguen las cifras clave, los resultados por programa (personas, ejecución y presupuesto), los resultados por territorio y el cuadro de resultados con descarga en Excel.
- **Resultados por territorio.** El alcance territorial resume cuántas provincias, cantones y parroquias registran el indicador y cuántas reúnen la mitad. Cada gráfico de barras territorial (ranking, ejecución presupuestaria y distribución por programa) tiene su propio selector **Provincia · Cantón · Parroquia** en la parte superior.
- **Centro de reportes.** Eliges el producto, el título y el **nivel territorial** de los archivos: **Provincia, Cantón, Parroquia o Todo** (en contingencias y gestión laboral, los niveles que tiene su fuente). Una vista previa muestra la pieza antes de generarla y su nombre de archivo identifica ámbito, periodo y nivel (por ejemplo, `MTDH_resumen_transferencias_2026-09_cantones.pdf`).
- **Corte y actualización.** Bajo el título de cada ámbito y al pie de la página se leen la fecha y hora de la última actualización y su frecuencia; los documentos repiten el corte, la actualización y la frecuencia en su encabezado y en la ficha técnica.
- **Geoportal.** Servicios y contingencias enlazan el [geoportal de unidades de atención y amenazas](https://geoportal.trabajo.gob.ec/ua_amenazas) del Ministerio, que se abre en una pestaña nueva.

### Ámbitos

| Ámbito | Indicadores | Desagregación |
| --- | --- | --- |
| Transferencias monetarias | Beneficiarios, presupuesto ejecutado, codificado, ejecución presupuestaria y presupuesto acumulado 2023–2026 por bono o pensión | Provincia, cantón y parroquia (corte mensual); provincia (años de referencia) |
| Servicios de protección integral | Usuarios, unidades de atención, presupuesto ejecutado, codificado, ejecución y acumulado por servicio | Provincia, cantón y parroquia (corte mensual); provincia (años de referencia) |
| Contingencias y compensaciones | Niñas, niños y adolescentes en orfandad por femicidio; personas habilitadas y que cobraron el bono de contingencias y el de eventos naturales y antrópicos; personas con pago acreditado de las compensaciones (transporte, diésel, migrantes retornados); montos, tipos de contingencia y presupuesto aprobado, devengado y ejecución 2026 | Nacional por programa; bonos habilitados por provincia, cantón y parroquia (eventos antrópicos hasta cantón) |
| Jóvenes en Acción | Registrados, habilitados y participantes de cada fase, transferencias, presupuesto, ejecución y pagos acreditados por mes | Nacional, fases 1 a 3 |
| Gestión laboral | Contratos vigentes y empresas (corte diario de SGDE), perfil por sexo, edad, discapacidad y autoidentificación, rama de actividad, tipo de contrato, nacionalidad, contratos registrados cada mes y compensación jubilar por año, régimen, sexo y provincia | Provincia y cantón |
| Presupuesto institucional | Codificado, devengado, ejecución y saldo por programa, zona de planificación, unidad ejecutora, grupo de gasto, fuente y tipo de gasto | Planta central y zonas de planificación |
| Presupuesto social | Presupuesto aprobado, devengado de cada mes y acumulado, ejecución frente al ritmo uniforme del año, saldo y ritmo necesario para cerrar el año, por programa y grupo de gasto (58, 57 y 78) | Nacional por programa presupuestario |

### Periodos disponibles

| Ámbito | Periodos | Etiqueta en pantalla y documentos |
| --- | --- | --- |
| Transferencias y servicios | Enero a septiembre de 2026, cada mes; años 2025 y 2024 | Corte septiembre 2026 · Año 2025 · Año 2024 |
| Contingencias y compensaciones | Cada mes cerrado desde enero de 2023 hasta septiembre de 2026 | Corte septiembre 2026 |
| Jóvenes en Acción | Fases 1 a 3, corte de septiembre de 2026 | Corte septiembre 2026 |
| Gestión laboral | Corte diario de contratos (23 de octubre de 2026, 02:21) y compensación jubilar al 18 de septiembre de 2026 | Corte del 23 de octubre de 2026, 02:21 |
| Presupuesto institucional | Septiembre 2026 | Corte septiembre 2026 |
| Presupuesto social | Enero a septiembre de 2026, cada mes | Corte septiembre 2026 |

Cada periodo se consulta por separado: las personas no se suman entre meses. Las series mensuales se leen además en «Evolución mensual»: personas de cada mes, variación por programa y, cuando existe, el presupuesto devengado de cada mes y la ejecución acumulada frente al ritmo uniforme del año. Los años de referencia no tienen detalle parroquial; en ellos los selectores de nivel quedan en «Provincia». Cuando la base incorpore nuevos meses, el selector los mostrará automáticamente.

### Productos del centro de reportes

| Ámbito | Resumen ejecutivo (PDF) | Presentación (PowerPoint) | Libro de datos (Excel) |
| --- | --- | --- | --- |
| Transferencias y servicios | Dos páginas: cifras clave, mapa, ejecución y resultados por programa, aspectos destacados; evolución mensual y detalle de provincias, cantones o parroquias | Portada, una diapositiva por nivel elegido, evolución mensual, ejecución presupuestaria y resultados por programa | Resumen, programas, serie mensual, una hoja por nivel, detalle con filtros y ficha técnica |
| Contingencias y compensaciones | Dos páginas: cifras clave, mapa y territorios con más bonos, presupuesto devengado por mes y ejecución por programa, aspectos destacados; resultados por programa, evolución de cada programa en doce meses, niveles territoriales, tipos y el año mes a mes | Portada, resultados por programa, evolución mensual, territorio y presupuesto | Resumen, programas, serie mensual, provincias, cantones y parroquias, tipos y ficha técnica |
| Jóvenes en Acción | Una página: cifras de la fase en curso, participantes por fase, del registro al pago, presupuesto y ejecución por fase, pagos por mes y aspectos destacados | Portada, fases, registro y pagos, pagos acreditados por mes | Resumen, fases, pagos por mes, presupuesto y ficha técnica |
| Gestión laboral | Dos páginas: cifras clave, mapa y territorios con más contratos, perfil, aspectos destacados; actividad económica, contratación del año, compensación jubilar y cantones | Portada, territorio, perfil y actividad, contratación del año, compensación jubilar | Resumen, provincias, cantones, perfil y actividad, jubilación, contratos por mes y ficha técnica |
| Presupuesto institucional | Dos páginas: cifras clave, mapa y ejecución por zona y por programa; composición del gasto y unidades ejecutoras | Portada, ejecución por zona, por programa y composición del gasto | Resumen, programas, zonas y unidades, grupos de gasto, detalle y ficha técnica |
| Presupuesto social | Dos páginas: devengado de cada mes, ejecución acumulada, grupos de gasto y ritmo necesario para cerrar el año; cada programa con su aprobado, devengado, ejecución y saldo, el devengado de cada mes y el ritmo que necesita | Portada, ejecución por programa, evolución mensual y detalle por programa | Resumen, programas, programa y mes, y ficha técnica |

Cada cifra lleva su unidad: los conteos dicen qué cuentan, los montos se leen «USD 21,3 M» o en dólares completos y los porcentajes con «%». Los documentos aprovechan su espacio: con pocos programas o un solo nivel territorial, los bloques crecen o se suman otros contenidos de la misma selección.

En la presentación, iconos, formas, textos y gráficos son objetos de PowerPoint editables, con notas para quien expone. En el libro de datos las cifras son números reales con formato, los totales son fórmulas que se recalculan con los filtros y el archivo trae un tema de Office «MTDH Institucional». Las exportaciones se generan en memoria; no requieren Microsoft Office, LibreOffice, un navegador instalado ni servicios externos. Hay ejemplos en `examples/`.

## Diseño e identidad visual

- **Información estratégica, sin notas aclaratorias.** El tablero y los documentos usan títulos formales y descriptivos, sin preguntas, instrucciones de uso ni advertencias técnicas, y no repiten el mismo gráfico: las portadas llevan la silueta del país con el territorio del reporte en oro, no una copia del mapa del cuerpo.
- **Un ámbito a la vez.** Transferencias, servicios, contingencias, Jóvenes en Acción, gestión laboral y presupuesto se consultan y exportan por separado; ningún gráfico ni total los combina.
- **Tres niveles territoriales.** Provincia, cantón y parroquia se leen con el mismo selector en el mapa, en cada gráfico territorial y en los archivos. Los cantones y parroquias de una provincia elegida se muestran completos cuando caben en el gráfico; a escala nacional, los 25 primeros.
- **Gráficos neutros.** Los gráficos reciben un indicador (nombre, unidad y formato) en lugar de una columna fija, así que sirven igual para beneficiarios, usuarios, unidades o presupuesto y para los indicadores que se agreguen después (ver «Agregar nuevos indicadores»).
- **Paleta institucional en un solo lugar.** `src/theme.py` reúne el morado del logo y del boletín, la lavanda y la niebla de sus superficies, el oro del escudo y una rampa morada generada en OKLCH. La aplicación, los gráficos y los tres productos leen esos valores; el tema de Streamlit vive en `.streamlit/config.toml`. Procedencia de cada color: [assets/brand/PROCEDENCIA.md](assets/brand/PROCEDENCIA.md).
- **Tipografías e iconos.** Montserrat para títulos y cifras y Public Sans para el texto, servidas por la propia aplicación desde `static/fonts`. Excel y PowerPoint usan Century Gothic y Calibri, instaladas con Microsoft Office. Los iconos (Lucide, licencia ISC) están en `assets/icons/png` en blanco, morado y oro.
- **Mapas.** Se dibujan con la cartografía del INEC 2015 (1.040 parroquias, 224 cantones, 24 provincias y las zonas de planificación) incluida en el proyecto, sin teselas ni servicios externos, con Galápagos en recuadro y la línea ecuatorial. Detalles y licencia: [assets/geo/PROCEDENCIA.md](assets/geo/PROCEDENCIA.md).
- **Sin secciones desplegables.** Todo el contenido está a la vista; las opciones se eligen con controles segmentados.
- **Teléfonos.** En el teléfono las cifras clave pasan a dos columnas, los selectores ocupan el ancho completo sobre su gráfico, la serie mensual usa una versión con cifras más grandes, la matriz territorial y las tablas se deslizan de lado y la primera columna de las tablas queda fija.
- **Movimiento con intención.** Una sola secuencia de entrada: el mapa se enciende de oeste a este y las cifras clave cuentan hasta su valor. Si el sistema pide reducir el movimiento, la aplicación lo respeta.
- **Cifras en formato ecuatoriano.** Pantalla, gráficos y tablas muestran `1.234.567,89` sin importar el idioma del navegador; las tablas siguen ordenándose por el valor numérico. En los archivos de Office las cifras son números reales y se presentan según la configuración regional del equipo.

## Agregar nuevos indicadores

Los ámbitos y sus indicadores se declaran en `src/indicators.py` (`MODULES` para los ámbitos territoriales y `AREAS` para el selector). Cada `Module` define su nombre, la sección de datos que lee, el nombre de sus personas (beneficiarios, usuarios) y sus indicadores adicionales. El tablero, el mapa, los rankings por nivel, el cuadro de resultados y los tres productos leen esa declaración, de modo que un nuevo ámbito territorial (por ejemplo, indicadores de contingencia) se integra al agregar sus filas a la base con la misma estructura de periodo, categoría y territorio, y declarar su `Module`. Si los nuevos datos tienen otra estructura, conviene ajustar primero el proceso de `src/etl_actualizacion.py`.

## Actualizar los datos

Desde la raíz del repositorio:

```bash
python -m pip install -r requirements-data.txt
python scripts/update_history.py --entrada "/ruta/a/insumos" --web
```

Para actualizar únicamente las fuentes laborales públicas, omita `--entrada`. También puede ejecutar manualmente **Actualizar datos laborales** en GitHub Actions; la consulta automática está programada a las 07:15 de Ecuador. El procedimiento y las reglas de sustitución de meses están en [data/README.md](data/README.md).

Para reconstruir el detalle territorial anterior desde sus fuentes Parquet, use `python scripts/build_data.py --config config/actualizacion_datos.json`. Su metodología está en [docs/ACTUALIZACION_DATOS.md](docs/ACTUALIZACION_DATOS.md).

Si cambia la división político-administrativa de las bases (por ejemplo, un cantón nuevo), la cartografía se regenera con `python scripts/build_geo.py <archivo TopoJSON>`, como se describe en [assets/geo/PROCEDENCIA.md](assets/geo/PROCEDENCIA.md).

## Cómo interpretar las cifras

- **Cobertura.** Beneficiarios, usuarios y unidades de atención son personas y unidades distintas dentro de cada programa, mes y territorio; no se suman entre meses. En septiembre de 2026 hay 1.578.019 beneficiarios de bonos y pensiones, 453.994 usuarios de servicios y 11.215 unidades de atención.
- **Contingencias y compensaciones.** Cada programa se lee con el criterio de su fuente: beneficiarios del bono de orfandad por femicidio, personas habilitadas (y las que cobraron, por fecha de cobro) de contingencias y eventos, y personas con pago acreditado de las compensaciones. Los bonos habilitados y los montos se suman en los meses del año para la lectura territorial.
- **Jóvenes en Acción.** La información disponible llega a la fase 3: 150.000 jóvenes habilitados de 637.808 registrados, presupuesto de USD 180,0 millones y devengado de USD 107,5 millones (59,7 %) a septiembre de 2026.
- **Presupuesto social.** El ritmo uniforme supone una doceava parte del presupuesto por mes; el ritmo necesario divide el saldo por devengar para los meses que quedan del año.
- **Presupuesto ejecutado y ejecución.** El presupuesto ejecutado es el devengado al corte; la ejecución presupuestaria es devengado sobre codificado, calculada con la suma de cada selección (nunca como promedio de porcentajes).
- **Presupuesto acumulado.** Suma el presupuesto de 2023 a 2025 y el del año del corte; existe por provincia, no por cantón ni parroquia.
- **Parroquias.** Las parroquias urbanas que la cartografía 2015 dibuja dentro de su cabecera cantonal se muestran con su nombre en tablas y rankings, y en el mapa dentro de esa cabecera. La zona en estudio (código 90) se incluye en los totales, no entre provincias, cantones o parroquias.
- **Gestión laboral.** El país registra 2.789.748 contratos vigentes en 325.877 empresas al 23 de octubre de 2026. Los contratos registrados cada mes son los que siguen vigentes a la fecha de consulta, no el total de contratos firmados en ese mes. La fuente SGDE informa 4.686 expedientes y USD 229.841.799,89 de compensación jubilar al 18 de septiembre de 2026. Cada fuente conserva su fecha de corte.
- **Presupuesto institucional y social.** Son universos distintos: el institucional es el presupuesto del Ministerio por programa y zona; el social es el aprobado de bonos, pensiones, contingencias, compensaciones y Jóvenes en Acción. No se suman entre sí ni con los presupuestos territoriales.

El boletín original se conserva en `docs/reference/` como referencia de conciliación y marca, y su logo institucional se utiliza sin recrearlo. La propuesta visual toma sus colores y marca; no sustituye la aprobación de Comunicación.

## Estructura modular

```text
app.py                     Punto de entrada: franja institucional, tablero y centro de reportes
src/indicators.py          Ámbitos e indicadores neutrales por periodo
src/views/                 Una vista por ámbito: territorial, contingencias, Jóvenes en Acción, gestión laboral y presupuesto
src/territory.py           Provincias, cantones y parroquias: tablas, rankings, alcance y valores de mapa
src/geo.py                 Cartografía: polígonos por nivel, recuadro de Galápagos, zonas y mapa SVG
src/names.py               Nombres oficiales con tildes de territorios, programas y partidas
src/theme.py               Paleta, rampas, tipografías y vocabulario institucional
src/ui.py                  Componentes visuales, iconos y tablas con cifras en formato ecuatoriano
src/charts.py              Gráficos del tablero (Plotly), comunes a todos los indicadores
src/data.py                Lectura de periodos y del detalle territorial, filtros y agregación
src/institutional.py       Presupuesto institucional por programa, zona, unidad, grupo y fuente
src/gestion_laboral.py     Indicadores de gestión laboral (cortes diarios de SGDE y compensación jubilar)
src/contingencias.py       Contingencias y compensaciones: meses cerrados, criterios, territorio y presupuesto
src/jovenes.py             Fases, pagos y presupuesto de Jóvenes en Acción
src/presupuesto_social.py  Presupuesto social aprobado y devengado por programa
src/mensual.py             Meses de cobertura y presupuesto de transferencias y servicios
src/depuracion.py          Depuración de provincias, cantones y parroquias al leer las series
src/corte.py               Corte, fecha y hora de actualización y frecuencia de cada ámbito
src/auth.py, security.py   Acceso, sesión, hashes y control de intentos
src/etl*.py, laboral*.py   Depuración de las bases y extracción de las fuentes laborales
src/reports/context.py     Contexto de transferencias y servicios (cifras, niveles y hallazgos)
src/reports/national.py    Contexto del presupuesto institucional
src/reports/areas.py       Contextos de contingencias, Jóvenes en Acción, gestión laboral y presupuesto social
src/reports/pdf.py         Resumen ejecutivo (pdf_areas.py: ámbitos con estructura propia)
src/reports/pptx.py        Presentación (pptx_areas.py: ámbitos con estructura propia)
src/reports/excel.py       Libro de datos y cuadros del tablero en Excel (excel_areas.py: ámbitos con estructura propia)
src/reports/charts.py      Mapas, siluetas y series de los documentos (matplotlib)
assets/geo/                Cartografía del Ecuador y su procedencia
scripts/build_data.py      Actualización de las bases
scripts/build_geo.py       Generación de la cartografía
config/                    Cuenta inicial, configuración de la actualización y fuentes laborales
data/processed/            Bases vigentes, periodos anuales y manifiestos
tests/                     Validación de datos, seguridad, interfaz, mapas y documentos
examples/                  Ejemplos de los productos
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
- [Indicadores SGDE del Ministerio](https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/MDTDH/kpis.html) (contratos, jubilación y fases de Jóvenes en Acción)
- [Geoportal de unidades de atención y amenazas](https://geoportal.trabajo.gob.ec/ua_amenazas)

Los datos pertenecen a las bases aportadas por el usuario y a las fuentes oficiales citadas. La identidad institucional y sus marcas pertenecen a sus titulares.
