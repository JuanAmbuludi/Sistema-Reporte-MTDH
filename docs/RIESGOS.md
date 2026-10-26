# Riesgos en unidades de atención

El ámbito **Riesgos** muestra el inventario de UA de septiembre de 2026, sus servicios, territorio y susceptibilidad a inundaciones, movimientos en masa, sequía e incendios forestales. Los filtros de corte, provincia, servicio, amenaza y nivel actualizan los indicadores, el mapa, los dos gráficos y la tabla. La búsqueda adicional afecta solo a la tabla y su descarga CSV. En Reportes se generan PDF, PowerPoint y Excel con la selección vigente y la línea gráfica institucional.

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
