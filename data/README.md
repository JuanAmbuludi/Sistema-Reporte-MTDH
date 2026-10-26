# Bases de InfoReport

Las bases se guardan en **Parquet con compresión Zstandard**. Cada serie mensual incluye `periodo` (`2026-09`), `anio`, `mes` y `mes_nombre` (`septiembre`). Los cortes laborales además incluyen `fecha_corte`, tomada de la fuente, no del día de descarga. Las referencias anuales sin mes documentado conservan el mes vacío.

## Organización

| Carpeta | Contenido |
|---|---|
| `series/` | Series mensuales nacionales, presupuesto social aprobado y resúmenes de transferencias |
| `series/laboral/` | Cortes diarios publicados de contratos y desagregaciones de jubilaciones |
| `series/controles/` | Comparaciones con los tabulados recibidos; no se suman a las bases operativas |
| `processed/` | Bases compatibles con la aplicación: cobertura y presupuesto territorial, presupuesto institucional y gestión laboral |
| `source/` | Fuentes agregadas anteriores convertidas a Parquet; catálogo de procedencia y hashes originales |
| `entrada_local/` | Carpeta local opcional, excluida de Git. Aquí pueden colocarse nuevos insumos nominales |

## Qué base utilizar

| Base en `series/` | Una fila representa | Uso |
|---|---|---|
| `cobertura_vis.parquet` | Mes × servicio × modalidad | Usuarios únicos dentro del grupo, unidades únicas dentro del grupo y registros |
| `cobertura_vis_territorial.parquet` | Mes × nivel × código y nombre territorial × servicio × modalidad | Usuarios, unidades y registros por provincia, cantón o parroquia |
| `bonos_vie_territorial.parquet` | Mes × nivel × código y nombre territorial × bono | Beneficiarios y registros por provincia, cantón o parroquia |
| `bonos_vie.parquet` | Mes × bono | Beneficiarios únicos dentro del bono y registros; PTV menores permanece separado |
| `resumen_social_mensual.parquet` | Mes × programa | Consulta compacta: beneficiarios disponibles, criterio del conteo, devengado mensual y acumulado aprobado |
| `presupuesto_social_mensual.parquet` | Mes × programa | Devengado aprobado; enero–septiembre 2026 en esta entrega |
| `presupuesto_social_asignado.parquet` | Corte × grupo presupuestario | Planificado y presupuesto aprobado anual. BDH+BDHV comparten una sola asignación |
| `beneficiarios_orfandad.parquet` | Mes | Beneficiarios distintos y registros reportados; no existe junio 2026 en la fuente |
| `incentivos_mensuales.parquet` | Mes de acreditación × programa × fase | Personas con pago acreditado, transacciones y monto acreditado; fases JEA separadas |
| `antropicos_mensuales.parquet` | Mes × criterio | Beneficiarios y monto habilitado o cobrado, según su fecha correspondiente |
| `contingencias_mensuales.parquet` | Mes × criterio | Igual tratamiento para cobertura de contingencias |
| `antropicos_territorial.parquet` | Mes × criterio × provincia × cantón × tipo | Desglose territorial, con una única versión de cada fuente |
| `contingencias_territorial.parquet` | Mes × criterio × provincia × cantón × parroquia × tipo | Desglose territorial de contingencias |
| `jovenes_accion_fase3.parquet` | Corte × fase | Habilitados y presupuesto de la fase; ejecución aprobada frente a la publicada |
| `jovenes_accion_fases.parquet` | Corte × fase | Las tres fases publicadas por SGDE: registrados, participantes, transferencias, presupuesto y ejecución |
| `laboral/contratos_base.parquet` | Fecha de corte × estado × sexo × edad × discapacidad × provincia | Total de contratos, vigentes y finalizados |
| `laboral/contratos_canton.parquet` | Fecha de corte × estado × sexo × edad × discapacidad × provincia × cantón | Territorialización cantonal; no existe parroquia en la fuente |
| `laboral/contratos_rama.parquet`, `contratos_tipo.parquet`, `contratos_etnia.parquet` | Corte y dimensiones identificadas en cada tabla | Tabulaciones independientes; no unirlas fila a fila |
| `laboral/contratos_nac.parquet` | Corte y nacionalidad extranjera | Subconjunto extranjero, no todo el universo de contratos |
| `laboral/contratos_act.parquet` | Corte × estado × provincia × rama × actividad | Actividad económica publicada |
| `laboral/contratos_empresas.parquet` | Corte × estado × provincia | Empresas distintas. `TOTAL` no se suma a sus componentes |
| `laboral/jubilados.parquet` | Corte × año × dimensión × categoría | Expedientes y monto. Cada dimensión reproduce el total y no debe sumarse con otras |

El inventario exacto de filas, tamaños, periodos y hashes está en [`series/actualizacion.json`](series/actualizacion.json). Las reglas y discrepancias de esta entrega están en [`docs/REVISION_BASES_2026.md`](../docs/REVISION_BASES_2026.md).

## Reglas de cálculo

- No sumar usuarios o beneficiarios entre meses para calcular personas únicas anuales. Tampoco sumar modalidades/bonos y llamar al resultado personas únicas nacionales.
- `registros`, `transferencias`, `beneficiarios`, `habilitados`, `acreditados`, `devengado` y `pagado` tienen significados diferentes.
- El devengado acumulado es una fotografía del acumulado fiscal: **no se suma entre meses**. Para el gasto del año, sumar `devengado_mes` o tomar el último acumulado, nunca ambos.
- La asignación BDH+BDHV se suma una vez. No repartirla entre ambos bonos sin una fuente que sustente esa distribución.
- El presupuesto social aprobado cubre grupos 58, 57 y 78. El presupuesto institucional y los presupuestos territoriales tienen universos distintos; no sumarlos al presupuesto social.
- Las nuevas versiones VIS/VIE incluyen tabulaciones nacionales y territoriales independientes de enero a septiembre. Seleccione un solo `nivel_territorial`; sumar provincia, cantón y parroquia triplicaría los registros. La aplicación conserva el detalle operativo anterior por modalidad/cooperante en sus nombres habituales, porque su estructura y presupuesto tienen un alcance distinto.
- En VIS se usa la modalidad detallada para mantener separados CDI directos, convenios y emblemáticos; se eliminan sus prefijos numéricos de presentación.
- `codigo_ambiguo` señala un código asociado a distintos nombres en el mismo mes y nivel. Las series se guardan tal como llegan; la depuración territorial ocurre al leerlas (`src/depuracion.py`) y nunca altera los totales:
  - si los nombres de un mismo código coinciden (tildes, abreviaturas, «SAN JOSE» frente a «SAN JOSÉ»), el código se conserva;
  - si provincia, cantón y parroquia identifican otra unidad de la división político-administrativa, la fila se reasigna a ese código;
  - las bases que solo traen nombres (contingencias y eventos antrópicos) se ubican con el nomenclátor de VIS y VIE: alias de cantones, coincidencia aproximada dentro de la provincia y, como último recurso, el único cantón del país con ese nombre;
  - lo que no puede ubicarse queda en los totales nacionales y fuera de los mapas. `cleaning_log()` lista cada reasignación.
- Las bases de contingencias y eventos antrópicos llegan con el mes de su extracción todavía abierto (por ejemplo, octubre al 23). Ese mes no se publica en el tablero ni en los documentos hasta que se cierre con la siguiente entrega; `contingencias.closed_until()` indica el último mes cerrado.
- Un nulo significa que la fuente no permite medir el dato; un cero existe solo si está documentado.
- En `resumen_social_mensual`, PTV agrupa adultos y menores para coincidir con el presupuesto. El detalle original se conserva en `bonos_vie`.

## Actualizar meses anteriores o posteriores

```bash
pip install -r requirements-data.txt
python scripts/update_history.py --entrada "/ruta/a/insumos" --web
```

En Windows también puede ejecutar `ACTUALIZAR_DATOS.bat "C:\ruta\a\insumos"`. Se aceptan los nombres aportados en esta entrega, con prefijos de descarga y fechas al final. Mantenga una sola versión de cada tipo de archivo en esa carpeta. El Excel de presupuesto debe contener su mes y año en el encabezado, como el aprobado de septiembre.

**Cada archivo debe contener completas las particiones que corrige.** Un nuevo mes se agrega; un mes existente se sustituye por su nueva versión, sin duplicarlo. Los demás meses se conservan. Puede entregar solo VIS, solo VIE, solo presupuesto o cualquier combinación. La actualización valida todos los insumos antes de publicar cambios. Los meses ausentes no se rellenan con ceros. No es una importación de registros nominales incrementales: para modificar un mes debe entregar el agregado completo de ese mes o la fuente completa correspondiente.

```bash
# Únicamente las páginas públicas laborales
python scripts/update_history.py --web

# Reproducir fuentes públicas sin red a partir de su checkout
python scripts/update_history.py --sgde-local "/ruta/al/repositorio-SGDE"

# Validación
python -m pytest tests/test_history.py -q
```

El workflow [`actualizar-datos-laborales.yml`](../.github/workflows/actualizar-datos-laborales.yml) consulta diariamente a las 07:15 de Ecuador y admite ejecución manual en Actions. Solo confirma cambios si la extracción y los controles pasan. Una fuente con igual fecha de corte sustituye esa fecha; una fecha nueva se incorpora al histórico. No reconstruye retrospectivamente fotos diarias que nunca se capturaron. La serie mensual previa del SUT conserva su fecha de observación.

Los insumos nominales se procesan localmente y no se guardan en GitHub: las salidas no contienen cédulas, nombres, cuentas ni teléfonos. Las fuentes agregadas anteriores pueden reconstruirse con `python scripts/build_data.py --config config/actualizacion_datos.json`. Ese comando reproduce el detalle territorial original; `update_history.py` incorpora las nuevas series y los nuevos cortes laborales.

## Lectura desde Python

```python
from src.series import load_series, latest_contracts
bonos = load_series("bonos_vie", start="2026-01", end="2026-09")
presupuesto = load_series("presupuesto_social_mensual")
cantones = latest_contracts("canton")
vis_territorial = load_series("cobertura_vis_territorial", start="2026-01", end="2026-09")
vis_parroquias = vis_territorial.loc[vis_territorial.nivel_territorial.eq("Parroquia")]
```
