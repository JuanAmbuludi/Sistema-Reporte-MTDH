# Seguimiento y respuesta en Riesgos

Acceso: **Riesgos → Seguimiento y respuesta**. Incluye centro de reportes PDF (2 páginas), PowerPoint (4 diapositivas) y Excel. La vista de exposición de UA, con 6.220 registros de multiamenaza, conserva su propio corte y sus exportables.

## Corte inicial del 26 de octubre de 2026

- Alertas: se utiliza exclusivamente `Detalle` del archivo de la Subsecretaría Territorial. Se filtra la fecha de registro desde el **29/09/2026**, inclusive, hasta el 26/10; 17 alertas (9 pendientes, 7 en seguimiento, 1 resuelta), 10 códigos UA, 7 provincias y 10 cantones. Las hojas resumen abarcan otras categorías y fechas; no se utilizan para calcular estas cifras.
- El campo Afectados mezcla personas, familias y usuarios. No se presenta una suma como personas únicas. Una alerta no equivale necesariamente a un evento independiente y no acredita causalidad ENOS. Se conservan los códigos y nombres de UA existentes, sin inferir códigos faltantes.
- Kits: siete entregas documentadas del 24–25/10, corte 25/10 a las 19:00; 802 kits en cuatro provincias y cinco cantones. Las entregas repetidas en un cantón tienen cantidades distintas y no se eliminan. No es el acumulado desde el 29/09.
- Bono: la ayuda memoria contiene planificación explícita para El Niño 2026–2027: 145.523 personas potenciales, 44.098 núcleos familiares y USD 13.405.351,02 estimados. Es una proyección nacional y permanece nacional al aplicar filtros provinciales.
- Referencia por inundaciones: 113 personas / USD 33.200,80 en pagos gestionados desde el 29/08, y 1.169 personas / USD 354.379,41 en articulación al 23/10. Se excluyen otros tipos de evento y la ejecución anual general. Gestionado no acredita cobro. La fuente no permite atribuir exclusivamente esos pagos a ENOS ni recortarlos desde el 29/09; se explicita en pantalla y en los documentos. Se requiere un detalle individual fechado y una clasificación oficial de vinculación ENOS para publicar esa ejecución específica.
- El registro ALT-2026-000301 consigna Nobol y describe Balao. Se conserva el cantón estructurado con una observación de validación pendiente.

El boletín N.º 0044 de Educación (25/10) se emplea como referencia de estructura. No se suman sus 1.378 eventos ni sus cifras educativas a los datos MTDH, y su pronóstico hasta el 25/10 no se presenta como pronóstico vigente.

## Fuentes y actualización

El snapshot `data/processed/seguimiento_enos_2026-10-26.json` publica únicamente campos operativos necesarios. Omite relatos libres, domicilios, responsables, teléfonos y datos personales de familias. Conserva las huellas de las fuentes.

```bash
python scripts/build_enos.py \
  --alerts "analisis-alertas-2026-10-26 (2).xlsx" \
  --bonos "Bono de Contingencia - Fenómeno del Niño.docx" \
  --kits data/reference/enos_kits_2026-10-25.csv \
  --cut 2026-10-26 --kits-cut 2026-10-25 --bonos-cut 2026-10-23
```

Cada corte se guarda en su propio JSON. La interfaz permite elegir los cortes recibidos. El CSV de kits es una transcripción revisada de `Reporte_ministerial_kits_provincias_priorizadas_rev.pdf`; para nuevos cortes se debe suministrar el archivo actualizado. El parser de bonos conserva la provincia de las celdas verticalmente combinadas del Word. Los alcances narrativos de cada fuente deben revisarse cuando cambien sus periodos o criterios.
