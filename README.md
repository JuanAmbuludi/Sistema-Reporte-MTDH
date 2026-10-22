# InfoReportes · MTDH

Sistema modular de estadísticas y reportes institucionales en **Streamlit**. Incluye acceso con usuario y contraseña, dashboard interactivo, filtros de provincia y programa, y exportación de la misma selección a **Word, PDF y PowerPoint**.

## Descomprimir, subir y abrir

El paquete está preparado para subir su contenido directamente a GitHub. Incluye los Parquet depurados, las plantillas, el logo y una cuenta lista para ingresar. **No necesitas ejecutar scripts de configuración ni pegar Secrets para el primer despliegue.**

| Acceso | Valor |
| --- | --- |
| Usuario | `admin` |
| Contraseña | `admin12345678` |

1. Descomprime el paquete y abre la carpeta del proyecto.
2. Sube **todo su contenido** a un repositorio privado de GitHub. `app.py` y `requirements.txt` deben quedar en la raíz del repositorio; conserva también las carpetas `config`, `src`, `assets`, `templates`, `data` y `.streamlit`.
3. En Streamlit Community Cloud, selecciona **Create app**, tu repositorio, la rama `main` y **`app.py`**. Elige **Python 3.12** en las opciones avanzadas y despliega.
4. Ingresa con `admin` y `admin12345678`.

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

- **Dashboard:** explorar bonos y pensiones, servicios de protección integral, cobertura, unidades, montos fiscales y montos acumulados de gobierno; filtrar por provincia y programa; consultar el detalle y las referencias de la fuente.
- **Centro de reportes:** generar un resumen ejecutivo en Word/PDF y una presentación institucional en PowerPoint, conservando la selección del dashboard. Los reportes incluyen cifras, gráficos, alcance territorial y notas de interpretación.
- **Actualizar los datos:** ejecutar el proceso Excel → Parquet con validaciones de claves, programas, provincias, montos y conciliación de acumulados.
- **Agregar ejecución presupuestaria:** incorporar un CSV complementario validado; los valores ausentes siguen siendo nulos, no ceros.

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
app.py                    Punto de entrada y navegación
src/auth.py               Acceso, sesión y salida
src/security.py           Hashes y control de intentos
src/etl.py                Depuración y esquema Parquet
src/data.py               Lectura, filtros y agregación compartida
src/ui.py                 Componentes visuales
src/charts.py             Gráficos interactivos
src/reports/              Contexto y exportadores Word, PDF y PPTX
config/access.toml        Cuenta inicial incluida, con contraseña en hash
scripts/build_data.py     Actualización del insumo
scripts/configure_auth.py Configuración opcional de cuentas
assets/                   Estilos, logo, iconos y plantillas
templates/                Plantilla PowerPoint editable
data/processed/           Base vigente, referencias y manifiesto
data/source/              Excel original agregado
data/templates/           Insumos complementarios
tests/                    Validación de datos, seguridad y exportación
examples/                 Ejemplos de los reportes generados
```

## Comprobar la instalación

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Las exportaciones se generan en memoria. No requieren Microsoft Office, LibreOffice, un navegador instalado ni servicios de generación externos en Streamlit. La plantilla PowerPoint está incluida y el contenido se actualiza con la selección.

## Fuentes técnicas

- [Dependencias en Streamlit](https://docs.streamlit.io/deploy/concepts/dependencies)
- [Gestión de secretos](https://docs.streamlit.io/deploy/concepts/secrets)
- [Despliegue en Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)

Los datos pertenecen al insumo aportado por el usuario. La identidad institucional y sus marcas pertenecen a sus titulares.
