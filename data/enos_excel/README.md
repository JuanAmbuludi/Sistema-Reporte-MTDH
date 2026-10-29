# Actualizar ENOS con Excel

Estas cuatro bases contienen la información vigente y alimentan las consultas **Por período** del tablero, incluidos sus PDF y Excel. Las cifras y el diseño se conservaron en la migración. Los **Reportes publicados** y sus documentos aprobados mantienen sus datos originales.

## Cada vez que llegue información

1. Descargue de esta carpeta la versión vigente del archivo que necesita. En GitHub, abra el archivo y pulse **Download raw file**. Trabaje sobre esa copia para conservar lo ya registrado.
2. Edite la hoja **Datos**, manteniendo las columnas. Actualice la fecha amarilla **Control → B4 (corte)** al corte de la fuente. Guarde con el mismo nombre y extensión `.xlsx`.
3. Abra el [cargador interno](../../herramientas/README_ENOS_CARGADOR.md), suba los archivos modificados, pulse **Validar archivos y comparar con GitHub**, revise las cifras y pulse **Publicar datos validados en GitHub**. Al actualizarse la aplicación desde GitHub, las consultas leen los nuevos Excel.

También puede usar **Add file → Upload files** dentro de esta carpeta en GitHub y reemplazar los archivos conservando sus nombres. Esta vía publica directamente: la validación de GitHub Actions ocurre **después** del commit. Para revisar y bloquear errores **antes** de publicar, use el cargador interno. Editar una copia en su computadora sin subirla no actualiza el tablero.

## Qué modificar

| Archivo | Identificador | Actualización |
|---|---|---|
| [alertas.xlsx](alertas.xlsx) | `codigo` | Modifique el estado u otros campos en la misma fila. Agregue solo códigos nuevos al final. |
| [kits.xlsx](kits.xlsx) | `id_kobo` | Histórico completo de entregas. Corrija la misma fila por ID o agregue una entrega nueva. |
| [unidades_suspendidas.xlsx](unidades_suspendidas.xlsx) | `corte_fuente` + `id_unidad` | Cada corte contiene el inventario completo. Se utiliza el último corte disponible a la fecha consultada. |
| [contingencias.xlsx](contingencias.xlsx) | `corte` + `provincia` + `evento` | Cada corte contiene el saldo provincial completo, habilitado y cobrado. Se utiliza el último saldo, sin sumar cortes. |

En cada archivo, **Control** contiene el significado y tipo de todas las columnas y un resumen calculado. **Datos** es la única hoja con registros. Agregue filas dentro de la tabla de Excel (en la última celda, pulse Tab) para extender formatos, listas y fórmulas de resumen. El lector valida los registros, no los totales calculados del libro.

### Alertas

Para pasar una alerta de `Pendiente` a `Resuelto`, cambie `estado` en su fila original. Conserve `codigo`. Una alerta nueva recibe su código real del aplicativo y una fila nueva. Seleccione `incluir=Sí`. No atribuya una afectación confirmada si la fuente no la confirma: ese campo admite blanco.

Para excluir una alerta registrada por error, seleccione `incluir=No` y conserve la fila. No pegue la misma alerta otra vez para actualizarla. Un código repetido bloquea la carga.

### Kits

Se conserva **todo el histórico**, incluidas las entregas anteriores al período del tablero. El tablero filtra por `fecha`; el resumen del libro muestra el total histórico. Conserve el ID Kobo como texto y registre kits y familias como números enteros.

Corrija una entrega en su misma fila. Agregue únicamente las nuevas. No pegue otro histórico completo debajo del actual. Para excluir una entrega, use `incluir=No`.

### Unidades suspendidas

Para un nuevo corte, copie **todas** las filas del último corte al final y cambie `corte_fuente` a la misma fecha/hora nueva. Conserve `id_unidad`. Marque `Reanudada` en las unidades que vuelven a atender, actualice las demás y agregue las nuevas con un identificador único y estable, por ejemplo `UA-2026-0001`. Para corregir el corte existente, edite su fila sin duplicarla.

Mantenga también las filas `Reanudada` en los siguientes cortes: no se cuentan como suspendidas y permiten distinguir una reapertura de una omisión. Si todas reanudaron, márquelas todas así; no vacíe la hoja. Conserve los cortes previos.

Catálogo de `servicio` / `programa_id`: `CNH` y `CDI` → `DII`; `PAM` → `PAM_SERV`; `PCD` → `PCD_SERV`; `PE` → `PE`; `AF` → `AF`.

### Contingencias

Para un nuevo corte, copie todas las provincias del corte vigente, cambie `corte` y escriba los **saldos completos** en `nucleos_habilitados`, `monto_habilitado`, `nucleos_cobrados` y `monto_cobrado`. Mantenga las provincias con saldo cero. Los cobros no pueden superar lo habilitado. Para corregir el mismo corte, edite la fila existente.

Conserve `evento=Todos los eventos` mientras la fuente entregue un total provincial. No agregue eventos detallados junto a ese total: duplicaría las cifras. Los montos se escriben como números con máximo dos decimales, sin teclear «USD» en el valor. El KPI de bonos conserva lo cobrado en su subtítulo.

## Reglas de carga

- Conserve nombres de archivo, hojas, encabezados y orden de columnas. Las cuatro bases deben permanecer en esta carpeta, aunque actualice solo una.
- Use fechas reales de Excel o texto `AAAA-MM-DD`. El corte de Control debe alcanzar todas las fechas de los registros.
- Los identificadores son texto. Los conteos son enteros no negativos. Un blanco no equivale a cero.
- Use los nombres territoriales y categorías ya presentes. No agregue filas de totales ni fórmulas a Datos.
- El cargador compara la versión vigente de GitHub: bloquea duplicados, borrado de identificadores/cortes previos, fechas incoherentes y valores inválidos. Si otra persona publica mientras usted revisa, debe volver a validar.
- Las publicaciones JSON históricas se conservan como respaldo y archivo. La carga de Excel actualiza las consultas actuales; no emite automáticamente un nuevo boletín histórico aprobado.

Para validar desde una copia local del repositorio:

```bash
python scripts/validar_enos_excel.py
python -m unittest discover -s tests -p test_enos_excel.py
```
