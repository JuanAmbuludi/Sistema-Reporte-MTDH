# Cargador interno de ENOS

Esta aplicación es independiente de `app.py` y de `src/views/`. No modifica ni reconstruye el exportable ENOS.

## Abrir en Windows

Desde la carpeta local del repositorio, ejecutar:

```powershell
python -m pip install -r requirements.txt
python -m pip install requests
python -m streamlit run herramientas/ENOS_Cargador.py
```

Al abrirse, escribir un **token de acceso personal de GitHub** con permiso `Contents: Read and write` únicamente sobre `JuanAmbuludi/Sistema-Reporte-MTDH`. No colocar este token en código ni incorporarlo al repositorio. El token permanece en la sesión de la aplicación.

## Operación habitual

1. Elegir la fecha de publicación y la fecha de corte de unidades (esta última únicamente importa cuando se cargan unidades).
2. Subir uno, dos o los tres Excel: alertas de aplicativo (hoja `Detalle`), Kobo histórico (`_id`), libro preparado de kits (`Detalle de entregas`) o actualización parcial de kits (`Detalle completo`), inventario de suspendidas (hojas `DETALLE` y `RESUMEN`).
3. Pulsar **Validar y preparar**. Ante inconsistencias, no se publica.
4. Revisar los recuentos y confirmar. Pulsar **Publicar cambios en GitHub**.

Se ejecuta una sola actualización Git atómica con los siguientes destinos:

- `data/processed/seguimiento_enos_AAAA-MM-DD.json`
- `data/processed/continuidad_servicios_AAAA-MM-DD.json`
- `data/processed/enos_internal/alertas.parquet`
- `data/processed/enos_internal/kits.parquet`
- `data/processed/enos_internal/unidades_suspendidas.parquet`
- `data/processed/cortes_riesgos.json` solo al cerrar un día previo

Los Parquet son auxiliares y **no reemplazan los contratos JSON** del tablero. Ningún Excel de entrada se sube al repositorio.

## Criterios de conciliación

- **Alertas:** el código conserva su identidad al cambiar estado; se actualizan los atributos sin generar un nuevo evento. Nuevos códigos de una misma unidad y fecha se bloquean para revisión; pueden ser eventos distintos, así que no se fusionan sin evidencia. No se atribuye automáticamente afectación a la prestación del servicio.
- **Kits:** el `ID Kobo` es la clave. El histórico completo sustituye por ID tras comprobar que no falten registros anteriores; el archivo parcial actualiza los mismos IDs y agrega los nuevos, sin sumar dos veces.
- **Unidades suspendidas:** se trata de un inventario vigente, no de un flujo. El detalle debe coincidir con el resumen en unidades y cobertura; no se acumulan los cortes anteriores.
- **Versiones:** los reportes cerrados no se alteran. La publicación correspondiente al día nuevo crea nuevos JSON y registra la huella SHA-256 del día anterior.

## Alcance y limitaciones

- Se admiten únicamente los formatos identificados; una exportación que cambie encabezados o estructura deberá ser revisada.
- Los cambios sospechosos de identificadores o territorios se bloquean en lugar de asignar coincidencias por aproximación.
- La interfaz requiere acceso a GitHub desde el equipo y un token autorizado. La publicación solo se ejecuta después de la revisión humana.
- No hay pruebas de ejecución de extremo a extremo con nuevos Excel adjuntos; ejecutar una prueba controlada antes del primer corte real.
- No cambia los bonos de contingencia ni brigadas: el alcance de esta herramienta son alertas, kits y unidades suspendidas.
