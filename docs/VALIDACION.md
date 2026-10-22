# Validación de la entrega

Rediseño visual revisado el 22 de octubre de 2026 con Python 3.12 y Streamlit 1.66.1.

## Fuente y cifras

Se procesó el Excel original incluido en `data/source/`. Los 296 agregados vigentes se conciliaron por provincia y programa. Los controles verifican 1.578.019 beneficiarios reportados de bonos y pensiones, 456.239 usuarios de servicios y 11.158 unidades. Se conservaron los saldos históricos de las dos pensiones con cobertura actual cero.

El presupuesto ejecutado permanece nulo porque el insumo no certifica esa fase presupuestaria. Los datos agregados no permiten verificar personas únicas. Estas condiciones se mantienen en pantalla y en las exportaciones.

El rediseño no cambia datos ni reglas: la base Parquet, el manifiesto y los cálculos son los mismos; cambian la presentación, las etiquetas y los formatos de salida.

## Aplicación y exportaciones

- **Pruebas automáticas:** 40 aprobadas y 1 omitida a propósito (la que reprocesa el Excel original solo corre si se define `MTDH_SOURCE_EXCEL`). Cubren depuración, claves, filtros, acumulados, nulos, ejecución parcial, autenticación, la interfaz sin secciones desplegables, los filtros que alcanzan a cada indicador, la geometría de los mapas, el formato ecuatoriano de las cifras, las definiciones en lenguaje claro y el contenido de los cuatro formatos de reporte y del detalle en Excel.
- **Navegador real (Chromium):** inicio de sesión, tablero nacional y filtrado por provincia, centro de reportes y descarga efectiva de Excel, PDF, Word, PowerPoint y del detalle en Excel, sin errores de página.
- **Pantallas:** escritorio de 1.440 px y teléfono de 390 px con agente de iPhone, sin desbordamiento horizontal del documento. En el teléfono la matriz territorial y las tablas se deslizan de lado dentro de su tarjeta.
- **Reportes nacionales:** Excel de siete hojas (portada, resumen, bonos y pensiones, protección integral, territorio, detalle y notas), PDF de cinco páginas, Word de cuatro páginas y PowerPoint de diez diapositivas. Los archivos se abrieron con LibreOffice y se inspeccionaron página por página, también para selecciones provinciales y por ámbito.
- **Coherencia:** el detalle del tablero, la tabla del centro de reportes y los archivos usan la misma selección filtrada; los totales del Excel son fórmulas que se recalculan al filtrar y guardan su valor calculado.

Los tests que contienen cifras esperadas corresponden al insumo de septiembre de 2026. Al sustituir ese corte por datos nuevos, actualiza esas referencias de regresión con cifras previamente conciliadas.

## Publicación

La aplicación queda lista para desplegar desde `app.py`, con dependencias, datos, tipografías y cuenta inicial incluidos. El acceso `admin` / `admin12345678` se lee de `config/access.toml`, que contiene el hash de la contraseña. No requiere ejecutar el asistente ni configurar Secrets para el primer despliegue. Una sección `[auth]` configurada posteriormente en Secrets sustituye por completo ese acceso inicial.

El repositorio no incluye el archivo privado `.streamlit/secrets.toml` ni la cuenta personal del usuario; `.gitignore` lo excluye. El tema institucional (`.streamlit/config.toml`) y las tipografías web (`static/fonts`) sí forman parte del repositorio, porque Streamlit los necesita al desplegar.
