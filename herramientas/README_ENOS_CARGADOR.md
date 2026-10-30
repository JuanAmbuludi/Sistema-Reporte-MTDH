# Cargador interno de ENOS

Actualiza las cuatro bases editables de [data/enos_excel](../data/enos_excel) sin modificar el diseño del tablero ni los reportes ya publicados. Las consultas actuales y sus exportaciones leen los Excel publicados.

## Abrir en Windows

Desde la carpeta local actualizada del repositorio:

```powershell
python -m pip install -r requirements.txt
python -m pip install requests
python -m streamlit run herramientas/ENOS_Cargador.py
```

Escriba un token personal de GitHub con permiso **Contents: Read and write** únicamente sobre `JuanAmbuludi/Sistema-Reporte-MTDH`. El token permanece en la sesión; no se incorpora al código ni a los archivos publicados.

## Operación habitual

1. Descargue las bases vigentes desde GitHub y edite Datos siguiendo [las instrucciones de cada base](../data/enos_excel/README.md). No necesita editar la hoja Control.
2. Suba uno o varios archivos: `alertas.xlsx`, `kits.xlsx`, `unidades_suspendidas.xlsx` o `contingencias.xlsx`, con hojas Datos y Control.
3. Pulse **Validar archivos y comparar con GitHub**. El cargador lee las otras bases vigentes y valida el conjunto antes de preparar cambios.
4. Revise recuentos, cortes, kits históricos, núcleos y montos habilitados/cobrados. Confirme la revisión y pulse **Publicar datos validados en GitHub**.

Se crea un único commit que reemplaza solamente los Excel modificados en `data/enos_excel/`. No genera Parquet ni modifica los JSON de los reportes publicados. Las exportaciones originales del aplicativo, Kobo o DETALLE/RESUMEN deben trasladarse a las columnas de las plantillas: no se publican directamente sobre las bases normalizadas.

## Qué verifica

- Alertas por código y kits por ID, sin duplicados ni desaparición de registros. Use `incluir=No` para excluirlos.
- Último estado por unidad: admite cambios parciales y conserva las unidades sin cambios. Las `Reanudada` dejan de contarse.
- Último saldo completo de cada provincia: admite actualizar provincias por separado, comprueba cobrado menor o igual a habilitado y evita mezclar total y detalle.
- Columnas, fechas reales de los registros, valores y conservación de los identificadores ya registrados. El corte técnico se calcula automáticamente.
- Una publicación concurrente en GitHub obliga a recargar y validar nuevamente.

La aplicación del cargador es independiente y se abre con el comando anterior. Para una carga desde el navegador de GitHub puede usar **Add file → Upload files** en la carpeta de las bases; esa ruta no ofrece la revisión previa del cargador. Después de publicar, espere a que el despliegue incorpore el commit y recargue la consulta del tablero.

Después de subir los Excel, GitHub publica automáticamente la versión validada y su fecha y hora. Mientras una carga tenga errores, el tablero conserva la última versión validada y avisa que hay una carga pendiente.
