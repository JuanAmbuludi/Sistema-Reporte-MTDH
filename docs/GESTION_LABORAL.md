# Gestión laboral: fuentes y cortes

La actualización vigente está en [la revisión de bases](REVISION_BASES_2026.md) y el [catálogo de datos](../data/README.md). Las dos páginas SGDE solicitadas se consultan con `python scripts/update_history.py --web`; el workflow diario conserva cada nueva fecha de corte en Parquet.

El stock de contratos incluye provincia y cantón, estados, sexo, edad, discapacidad, actividad, tipo de contrato, etnia, nacionalidad extranjera y empresas. Son tabulaciones independientes del mismo universo. No hay parroquias ni fechas individuales de inicio en esas páginas. El archivo nacional `data/processed/gestion_laboral.parquet` alimenta el tablero y las exportaciones. La fecha del stock se presenta por separado de la fecha de las cohortes mensuales previas del SUT.

Los expedientes de jubilación y su monto están desagregados por año, provincia, sexo y régimen en `data/series/laboral/jubilados.parquet`. Cada dimensión reproduce el total: no se suman dimensiones entre sí. Los años completos no reciben un mes ficticio. El corte 2026 comprende enero al 18 de septiembre.

## Extracción SUT anterior

El scraper heredado `src/laboral_scraper.py` sigue disponible para consultar cohortes mensuales directamente al SUT mediante Playwright. Las evidencias del 22 de octubre permanecen en `data/processed/laboral_evidencias/` y `laboral_cortes/`. Estas cohortes indican contratos registrados en cada mes que seguían vigentes en la fecha de consulta; no son todos los contratos firmados ni stocks mensuales.

```bash
python -m pip install -r requirements-scraping.txt
python -m playwright install chromium
python scripts/build_data.py --solo-laboral --laboral-desde 2026-01 --laboral-hasta 2026-09
# Después, recuperar el último corte y desagregaciones SGDE:
python scripts/update_history.py --web
```

Para revisar la evidencia histórica sin sustituir la base actual:

```bash
python scripts/build_data.py --solo-laboral --laboral-evidencia data/processed/laboral_evidencias/20261022T232229581149Z_9cd411c6.json --output /tmp/reproduccion-laboral
```

Los importadores validan formatos, claves, conteos y conciliación antes de publicar los archivos. Los originales Excel y CSV eliminados de la versión actual siguen en el historial Git. Los contratos son contratos, los expedientes son expedientes y ninguna de esas medidas representa personas únicas.
