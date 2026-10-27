# Riesgos en unidades de atención

El ámbito **Riesgos** muestra la **respuesta del Ministerio** ante El Niño desde el 14 de septiembre de 2026. Por instrucción del responsable, la exposición de las unidades de atención a amenazas (inventario de septiembre de 2026, descrito más abajo) se conserva como análisis interno y no aparece en el tablero ni en sus exportables. Los filtros de territorio y servicio actualizan todo el tablero; el servicio se aplica a las alertas y a la continuidad, y los kits y el bono se leen por territorio.

Cada pregunta tiene el gráfico que pide su dato, y ningún tipo de gráfico se repite:

- **Mapa** por provincia con tres indicadores: alertas con código UA, UA suspendidas y kits; las provincias elegidas se marcan en dorado.
- **Cifras clave:** alertas con código UA, kits entregados, núcleos familiares con bono gestionado, monto gestionado y unidades suspendidas.
- **Continuidad de los servicios:** dónde se suspendió la atención (mosaico de provincias y cantones, en el color de cada servicio), la participación de cada servicio (anillo con el total al centro) y el detalle de las unidades suspendidas con sus nombres. Cuando la fuente no registra cantón o nombre, la celda queda con un guion.
- **Alertas en servicios MTDH:** evolución diaria sobre el acumulado desde el 14/09, una marca por alerta en la fila de su provincia y el registro completo, de la más reciente a la más antigua.
- **Kits entregados:** total y participación de cada provincia junto a cada entrega en el tiempo (el área de cada círculo sigue sus kits) y el detalle de las entregas Kobo.
- **Bono de contingencia:** una barra al 100 % por etapa (pago gestionado en núcleos familiares; articulación en personas), que nunca se suman, y la planificación El Niño 2026–2027.
- **Resumen por provincia** con cantones, kits e importes del bono, y la nota metodológica con los alcances de cada fuente.

Los cantones que Kobo escribe en mayúsculas sin tildes (ESPINDOLA) y los nombres de UA de las alertas se leen como los escribe el nomenclátor («Espíndola», «CDI Los Niños del Cisne»).

En Reportes se generan, con la selección vigente, un **PDF** de tres páginas (cifras y gráficos; registro de alertas y unidades suspendidas; kits, bono y alcances; dos páginas si la selección no tiene alertas ni unidades suspendidas), un **PowerPoint** de hasta diez diapositivas (solo las secciones con registros; gráficos nativos de anillo y de barras al 100 %) y un **Excel** de nueve hojas con fechas reales y un tipo de gráfico nativo por pregunta: anillo de servicios, columnas diarias sobre el acumulado de alertas, acumulado de kits por entrega y barra al 100 % por etapa del bono. El detalle de las fuentes de la respuesta está en [SEGUIMIENTO_ENOS.md](SEGUIMIENTO_ENOS.md).

## Exposición de las unidades de atención (análisis interno)

Fuente: `UA_SEP26_AMENAZAS(1).xlsx`, hoja `UA_SEPTIEMBRE_2026`, elaborado por DGID / SGDE / MTDH a partir del reporte territorial SIIMTDH. Capas espaciales: MAGAP 2015 (inundaciones y sequía), SNGR 2011 (movimientos en masa) y SNGR 2015 (incendios forestales). La fecha del inventario no cambia la antigüedad de estas capas.

## Criterios

- **UA expuesta:** código único con susceptibilidad media, alta o muy alta en al menos una amenaza seleccionada. No se interpreta como una afectación confirmada.
- El archivo tiene 9.869 registros y 9.860 códigos distintos. Se consolidan las modalidades repetidas y se conserva la categoría máxima reportada por amenaza; se rechazan códigos con servicios o territorios contradictorios.
- Resultado nacional: 9.460 UA únicas con al menos una categoría de exposición, **6.220 registros de multiamenaza** según la matriz fuente y 23 provincias con unidades expuestas. Las 400 UA restantes no tienen categoría reportada en las cuatro amenazas; esto no demuestra ausencia de riesgo.
- La variable `multiamenaza` de la fuente significa **inundaciones O movimientos en masa**, no dos amenazas simultáneas. La tarjeta y la columna provincial reproducen los 6.220 registros de la fuente; corresponden a 6.211 códigos UA distintos y nueve repeticiones adicionales. El cálculo aplica los filtros vigentes y cuenta una fila una sola vez aunque tenga ambas amenazas. La antigua tarjeta de 6.788 medía alta o muy alta en cualquiera de las cuatro amenazas; se reemplazó por multiamenaza, con su definición y unidad de conteo explícitas. Los demás indicadores, gráficos y el detalle siguen contando códigos UA únicos.
- Los gráficos e indicadores usan conteos agregados por provincia, servicio y combinación de categorías. La tabla y su descarga incluyen código y nombre de la UA, servicio, provincia y susceptibilidad por amenaza, a solicitud del responsable del dashboard. No se incluyen cantones, parroquias, direcciones, RUC, coordenadas ni datos de usuarios. El detalle conserva una fila por corte y código, y reconcilia exactamente con los agregados.

## Nota metodológica

La clasificación de las Unidades de Atención (UA) se realizó mediante el análisis espacial de sus coordenadas geográficas validadas respecto a las capas de susceptibilidad consideradas. Se clasifican como expuestas aquellas UA ubicadas en zonas de susceptibilidad media, alta o muy alta, y como no expuestas aquellas que se encuentran fuera de estas categorías. Esta clasificación no implica una afectación efectiva ni descarta la existencia de amenazas o riesgos fuera de las zonas identificadas. Los posibles impactos dependen de las condiciones territoriales, la intensidad de los eventos y la vulnerabilidad de los elementos expuestos.

El enlace al geoportal de unidades de atención y amenazas se encuentra al inicio de **Riesgos**, tanto en Tablero como en Reportes. La tabla mantiene los vacíos y guiones de la fuente como «Sin categoría reportada»; no los reclasifica como no expuestos.

## Actualización

```bash
python scripts/build_risks.py --input "UA_SEP26_AMENAZAS(1).xlsx" --period 2026-09
```

El script detecta la hoja y encabezado, valida que el campo `corte` coincida con el periodo solicitado y guarda `data/processed/riesgos_ua.parquet`, `riesgos_ua_detalle.parquet` y `riesgos_ua_matriz.parquet` con compresión Zstandard. La última base conserva exclusivamente conteos de registros por provincia, servicio y combinación de categorías, sin identificadores, para reproducir multiamenaza. Reprocesar un corte reemplaza solo ese corte y conserva los demás. `riesgos_ua_AAAA-MM.json` documenta la fuente, su huella, controles, ambos criterios de conteo y fecha de procesamiento. La aplicación ofrece únicamente cortes existentes en esta base.
