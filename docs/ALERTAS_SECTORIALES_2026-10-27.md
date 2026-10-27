# Incorporación de reportes sectoriales

Se incorporan 11 filas a la misma colección `alertas`: cinco de Discapacidades y seis gerontológicas. Total: 21 registros; se conservan los 10 códigos UA originales. Los identificadores DIS/GER son claves de incorporación por fila, no códigos oficiales.

Las cinco filas de Discapacidades tienen fecha 25–26/10/2026. Las seis gerontológicas indican sucesos de agosto y reporte en octubre, sin día: `fecha=null` y `fecha_texto` conserva el mes. Se incluyen en el total y desagregaciones, pero no en la evolución diaria (15 registros con fecha exacta). Las fuentes declaran que no se interrumpe la prestación; no se agregan a las 99 unidades suspendidas.

Se conservan campos previos y se añaden origen, fuente, fila, mes y texto de fecha. Los archivos originales se identifican por SHA-256. No se publican nombres, cargos ni teléfonos de funcionarios. Kits y bonos permanecen sin cambios.

El PDF recupera la composición del modelo aprobado: indicadores y unidades suspendidas, registro de alertas y respuesta provincial. El registro omite columnas de estado y prioridad para contener las 21 filas en tres páginas; los campos completos permanecen en dashboard y Excel.
