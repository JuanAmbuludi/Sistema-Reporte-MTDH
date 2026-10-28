# Plan ENOS: actualización del 27/10/2026

- Alertas: 39 registros existentes más 5 códigos oficiales nuevos = 44 registros. El encabezado del Excel anuncia 7, pero hay 5 filas de detalle. No se inventan las dos faltantes. Se conservan los reportes sectoriales históricos y se vinculan los posibles antecedentes de Huaquillas, Portoviejo, Pedernales y Salitre mediante `reportes_relacionados`. El indicador cuenta registros de alerta y reportes sectoriales, no eventos ni unidades únicas.
- Unidades sin atención: el corte completo de las 19:00 reemplaza las 99 anteriores. Se concilian 124 filas únicas: El Oro 119 y Guayas 5. Cobertura reportada: 5.764, sin interpretarla como personas únicas. No se infieren códigos UA ausentes.
- Kits: el resumen del 26–27/10 contiene 12 entregas / 857 kits. Siete IDs ya existían; cinco nuevos aportan 360 kits. Se conservan las entregas anteriores: 116 registros y 14.341 kits en toda la base, de los cuales 10.967 corresponden al período 28/09–27/10. La nueva fuente no indica hora de corte. La observación de validación pendiente de Cañar se conserva.
- Brigadas: una de tipo EMERGENCIA desde el 28/09, realizada el 13/10 en Guayas, Balao. Fuente: matriz al 22/10. Se añade solamente el KPI y la nota territorial, con los filtros de fecha y provincia; no se añade un desglose.
- Bonos: se conservan personas y montos. Las publicaciones del 26/10 permanecen intactas.

El script `scripts/actualizar_enos_27_octubre.py` procesa los cuatro archivos con validación de identificadores y controles. `scripts/generar_pdf_enos.py` genera el PDF desde el contexto compartido por el dashboard.

## Conciliación con la matriz global recibida posteriormente

La matriz exportada el 28/10 a las 00:14 (zona horaria no indicada) contiene 117 entregas y 14.581 kits. Incorpora el ID 902026998: Bolívar, Las Naves, 09/10, 240 kits y 80 familias. Los restantes 116 registros no cambian. Para el período 28/09–27/10 corresponden 11.207 kits; los 3.374 anteriores permanecen fuera del indicador. Se conserva la publicación histórica del 26/10.

Por confirmación del responsable, el KPI de bono se presenta como «Familias · Bono de Contingencia», 1.171, «Habilitadas al pago». Se mantienen las cifras y los nombres técnicos de la base para preservar compatibilidad.
