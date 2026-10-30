# Actualizar ENOS: completar y subir el Excel

La operación habitual es **descargar la versión vigente, completar Datos y subir el archivo con el mismo nombre**. No hay que editar Control, escribir la hora de actualización, generar Parquet ni ejecutar scripts.

1. Descargue de esta carpeta el Excel vigente. En GitHub, abra el archivo y pulse **Download raw file**.
2. Complete únicamente la hoja **Datos**, conservando sus columnas y los registros anteriores. Las fechas de las filas son las fechas reales de las entregas o reportes recibidos.
3. Guarde y súbalo en esta misma carpeta con **Add file → Upload files**. Puede subir solo los archivos modificados. El [cargador interno](../../herramientas/README_ENOS_CARGADOR.md) es otra opción para revisar las cifras antes de enviarlas.

Al subir los archivos, GitHub valida el conjunto y publica automáticamente la nueva versión del tablero. El sello **Actualizado el** toma la fecha y hora real de publicación en horario de Ecuador. Guardar un archivo solamente en la computadora no lo sube al sistema.

## Qué llenar en cada base

| Archivo | Cómo actualizar |
|---|---|
| [alertas.xlsx](alertas.xlsx) | Una fila por `codigo`. Cambie el estado en su misma fila. Agregue solo códigos nuevos, con su fecha real. |
| [kits.xlsx](kits.xlsx) | Una fila por `id_kobo`. Corrija una entrega en su misma fila o agregue una nueva. Conserve todo el histórico. |
| [unidades_suspendidas.xlsx](unidades_suspendidas.xlsx) | Para un reporte nuevo, agregue solo las filas de las unidades que cambiaron. Conserve `id_unidad`, escriba la fecha real en `corte_fuente` y seleccione el estado. |
| [contingencias.xlsx](contingencias.xlsx) | Para un reporte nuevo, agregue las provincias que tienen cifras nuevas. Registre su fecha real en `corte` y los saldos provinciales completos habilitado y cobrado. |

**No necesita copiar un inventario completo ni repetir todas las provincias.** El sistema conserva el último estado de las unidades sin cambios y el último saldo de cada provincia. Los reportes de fechas diferentes no se suman.

## Unidades suspendidas

Si una unidad reanuda la atención, copie su última fila al final, conserve `id_unidad`, registre la nueva fecha del reporte y cambie `estado` a **Reanudada**. Si vuelve a suspenderse, agregue el nuevo reporte con el mismo ID y estado **Suspendida**. Las demás unidades conservan su último estado.

Para corregir un error en un reporte existente, edite esa misma fila. Una unidad puede tener varios reportes en fechas diferentes; repetir el mismo ID y la misma fecha bloquea la carga. Una unidad nueva recibe un identificador único y estable, por ejemplo `UA-2026-0001`. No reutilice ese ID para otra unidad.

Catálogo de `servicio` / `programa_id`: `CNH` y `CDI` → `DII`; `PAM` → `PAM_SERV`; `PCD` → `PCD_SERV`; `PE` → `PE`; `AF` → `AF`.

## Contingencias

Si solo cambia El Oro, agregue únicamente el nuevo reporte de El Oro. El sistema conservará los últimos saldos de las demás provincias. Escriba los saldos completos de esa provincia, no solo el aumento del día. Para corregir un corte existente, modifique su fila.

Use `evento=Todos los eventos` mientras la fuente entregue un total provincial. No mezcle ese total con sus eventos detallados. Si la fuente entrega detalle por eventos, el reporte nuevo debe contener el desglose completo de esa provincia. Conserve las provincias anteriores, incluso con saldo cero. Lo cobrado no puede superar lo habilitado.

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
