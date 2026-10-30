# Actualizar ENOS: completar y subir el Excel

La operación habitual es **descargar la versión vigente, completar la hoja de registros y subir el archivo con el mismo nombre**. No hay que editar Control, escribir la hora de actualización, generar Parquet ni ejecutar scripts.

1. Descargue de esta carpeta el Excel vigente. En GitHub, abra el archivo y pulse **Download raw file**.
2. Complete únicamente la hoja **Datos** (en contingencias, **Hoja1**), conservando sus columnas y los registros anteriores. Las fechas de las filas son las fechas reales de las entregas o reportes recibidos.
3. Guarde y súbalo en esta misma carpeta con **Add file → Upload files**. Puede subir solo los archivos modificados. El [cargador interno](../../herramientas/README_ENOS_CARGADOR.md) es otra opción para revisar las cifras antes de enviarlas.

Al subir los archivos, GitHub valida el conjunto y publica automáticamente la nueva versión del tablero. El sello **Actualizado el** corresponde al último cambio real de los registros o cortes, en horario de Ecuador. Guardar un archivo solamente en la computadora no lo sube al sistema.

## Fecha de actualización y trazabilidad

- Agregar una alerta o entrega, corregir un monto o fecha, cambiar un estado, registrar una reapertura o actualizar un cobro sí constituye una actualización.
- Abrir y volver a guardar el mismo Excel, cambiar colores o anchos, ordenar las mismas filas, editar el resumen automático de Control, ejecutar la validación o volver a desplegar la aplicación **no cambia la fecha de los datos**.
- Cada fuente conserva su propia fecha de último cambio. El sello general de ENOS muestra la más reciente de las fuentes que alimentan esta sección; no toma la fecha diaria de otra sección.
- El **corte** describe hasta cuándo llegan los registros. **Actualizado el** indica cuándo se publicó su última modificación real. La fecha **Generado el** de un PDF indica cuándo se creó ese documento: descargar otro PDF no actualiza los datos.
- Las consultas y exportaciones usan la misma publicación validada. Una carga inválida conserva los datos y la fecha anteriores hasta que se corrija; el aviso de validación pendiente permite identificarla.

Las huellas de los archivos completos siguen protegiendo la validación. Por separado, el sistema compara sus valores normalizados para distinguir modificaciones reales de cambios de formato. No hay que escribir ninguna hora manualmente.

## Qué llenar en cada base

| Archivo | Cómo actualizar |
|---|---|
| [alertas.xlsx](alertas.xlsx) | Una fila por `codigo`. Cambie el estado en su misma fila. Agregue solo códigos nuevos, con su fecha real. |
| [kits.xlsx](kits.xlsx) | Una fila por `id_kobo`. Corrija una entrega en su misma fila o agregue una nueva. Conserve todo el histórico. |
| [unidades_suspendidas.xlsx](unidades_suspendidas.xlsx) | Para un reporte nuevo, agregue solo las filas de las unidades que cambiaron. Conserve `id_unidad`, escriba la fecha real en `corte_fuente` y seleccione el estado. |
| [contingencias.xlsx](contingencias.xlsx) | Una fila por FECHA HAB + PROVINCIA + CANTON + TIPO EVENTO en Hoja1. Corrija esa misma fila o agregue una nueva habilitación. Conserve el histórico y los encabezados de la fila 3. |

**Unidades suspendidas:** el sistema conserva el último estado de las unidades sin cambios; los cortes no se suman. **Contingencias:** se suman las habilitaciones dentro del período consultado, sin sumar nuevamente la fila Total general.

## Unidades suspendidas

Si una unidad reanuda la atención, copie su última fila al final, conserve `id_unidad`, registre la nueva fecha del reporte y cambie `estado` a **Reanudada**. Si vuelve a suspenderse, agregue el nuevo reporte con el mismo ID y estado **Suspendida**. Las demás unidades conservan su último estado.

Para corregir un error en un reporte existente, edite esa misma fila. Una unidad puede tener varios reportes en fechas diferentes; repetir el mismo ID y la misma fecha bloquea la carga. Una unidad nueva recibe un identificador único y estable, por ejemplo `UA-2026-0001`. No reutilice ese ID para otra unidad.

Catálogo de `servicio` / `programa_id`: `CNH` y `CDI` → `DII`; `PAM` → `PAM_SERV`; `PCD` → `PCD_SERV`; `PE` → `PE`; `AF` → `AF`.

## Contingencias

La base vigente reemplaza el saldo provincial sin fecha por el reporte **Bono contingecias al 29 de octubre.xlsx**: 32 filas, 1.720 habilitados / USD 521.322,45 y 692 cobrados / USD 209.776,23. El archivo conserva exactamente el reporte recibido.

`FECHA HAB` es la fecha de habilitación. El filtro Desde/Hasta es inclusivo y se aplica también al estado de cobro de esas habilitaciones; no equivale a fecha de pago. Las fechas abreviadas del reporte recibido se interpretan explícitamente en **2026**. Para nuevas fechas use fechas completas de Excel o `AAAA-MM-DD` (obligatorio si cambia el año).

La clave es fecha + provincia + cantón + evento: si cambia el cobro, actualice la misma fila. No agregue un segundo saldo de esa clave. Los dos campos de cobro vacíos del reporte significan sin cobro registrado; si solo uno está vacío, se rechaza. Lo cobrado no puede superar lo habilitado. Si mantiene la fila `Total general`, actualice sus valores para que concilien con el detalle; nunca se suma como registro.

Los montos se ingresan como números, sin escribir «USD» en la celda. Los pequeños residuos de precisión de Excel se normalizan a centavos automáticamente. Los importes con más de dos decimales reales requieren corrección.

## Reglas comunes

- Mantenga nombres de archivo, hojas, encabezados y orden de columnas. Las cuatro bases deben seguir en esta carpeta.
- Conserve IDs y filas anteriores. Para excluir una alerta o entrega errónea, use `incluir=No`. Para una reapertura, use `Reanudada`.
- Los identificadores son texto. Los conteos son enteros no negativos. Un blanco no equivale a cero.
- Use fechas reales de Excel o `AAAA-MM-DD` y los nombres territoriales ya presentes.
- Agregue filas dentro de la tabla (desde su última celda, pulse Tab) para extender formatos y listas. No agregue filas de totales ni fórmulas a Datos.
- **Control es automático y de consulta.** No es necesario editarlo ni recalcularlo para subir el archivo. Sus resúmenes de últimos estados usan funciones de Excel 365/2024; el tablero calcula directamente a partir de Datos.

## Si una carga tiene errores

La nueva carga no sustituye los datos validados. El tablero conserva la versión anterior y muestra **Carga pendiente de validación**. Consulte la ejecución más reciente de **Validar bases Excel ENOS** en la pestaña Actions de GitHub: el error indica el archivo y el campo o fila que debe corregirse. Suba nuevamente el Excel corregido; no se necesita intervención técnica para reintentar.

Las consultas **Por período** y sus exportaciones usan la última versión validada. Los **Reportes publicados** mantienen sus datos originales. No se emite automáticamente un nuevo boletín histórico aprobado.
