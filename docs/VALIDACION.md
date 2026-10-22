# Validación de la entrega

Versión revisada el 22 de octubre de 2026 con Python 3.12 y Streamlit 1.66.1.

## Fuente y cifras

Se procesó el Excel original incluido en `data/source/`. Los 296 agregados vigentes se conciliaron por provincia y programa. Los controles verifican 1.578.019 beneficiarios reportados de bonos y pensiones, 456.239 usuarios de servicios y 11.158 unidades en septiembre de 2026. Se conservaron los saldos históricos de las dos pensiones con cobertura actual cero.

Las hojas de referencia anual se consultan como periodos propios: «Año 2025» (1.557.996 beneficiarios y 443.903 usuarios) y «Año 2024» (1.428.909 beneficiarios y 453.391 usuarios). Cada periodo se lee por separado; la aplicación rechaza cualquier suma o comparación entre periodos.

La reorganización no cambia datos ni reglas: la base Parquet, el manifiesto y los cálculos son los mismos; cambian la presentación, las etiquetas y los productos de salida.

## Aplicación y documentos

- **Pruebas automáticas:** 46 aprobadas y 1 omitida a propósito (la que reprocesa el Excel original solo corre si se define `MTDH_SOURCE_EXCEL`). Cubren depuración, claves, filtros, acumulados, nulos, periodos, autenticación, la interfaz sin secciones desplegables, la separación de transferencias y servicios, la selección por año, los filtros que alcanzan a cada indicador, la redacción formal sin notas técnicas, los mapas y el contenido de los tres productos.
- **Navegador real (Chromium):** inicio de sesión; tablero nacional, por provincia, por ámbito y por año; centro de reportes y descarga efectiva del resumen ejecutivo, la presentación, el libro de datos y el cuadro de resultados para septiembre de 2026 (transferencias) y el año 2024 (servicios), sin errores de página. Los nombres de archivo identifican ámbito y periodo.
- **Pantallas:** escritorio de 1.440 px y teléfono de 390 px con agente de iPhone, sin desbordamiento horizontal del documento.
- **Documentos:** resumen ejecutivo de una página, presentación de tres diapositivas con gráfico nativo editable e iconos, y libro de datos de cinco hojas. Se abrieron con LibreOffice y se inspeccionaron página por página, nacionales y con provincia seleccionada.

Los tests que contienen cifras esperadas corresponden al insumo de septiembre de 2026 y a sus hojas de referencia. Al sustituir ese corte por datos nuevos, actualiza esas referencias de regresión con cifras previamente conciliadas.

## Publicación

La aplicación queda lista para desplegar desde `app.py`, con dependencias, datos, iconos, tipografías y cuenta inicial incluidos. El acceso `admin` / `admin12345678` se lee de `config/access.toml`, que contiene el hash de la contraseña. No requiere ejecutar el asistente ni configurar Secrets para el primer despliegue. Una sección `[auth]` configurada posteriormente en Secrets sustituye por completo ese acceso inicial.

El repositorio no incluye el archivo privado `.streamlit/secrets.toml` ni la cuenta personal del usuario; `.gitignore` lo excluye. El tema institucional (`.streamlit/config.toml`) y las tipografías web (`static/fonts`) sí forman parte del repositorio, porque Streamlit los necesita al desplegar.
