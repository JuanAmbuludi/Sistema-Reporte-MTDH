# Seguimiento y respuesta en Riesgos

Acceso: **Riesgos**, capítulo «Respuesta del Ministerio», en la misma página que la exposición de las UA y con el mismo peso. Los exportables de Riesgos (PDF de dos páginas, PowerPoint de siete diapositivas y Excel con la hoja Respuesta) incluyen la exposición y la respuesta con la misma selección. El seguimiento inicia el **14/09/2026**.

## Corte inicial del 26 de octubre de 2026

- Alertas: el seguimiento toma las alertas registradas desde el **14/09/2026** (`--start` del generador) hasta el 26/10. El corte publicado del 26/10 contiene las alertas revisadas desde el 29/09 (`control.alertas_revisadas_desde`); las del 14 al 28/09 se incorporan al regenerar el corte con el Excel fuente y su revisión documental en el CSV de revisión. Se publican **8 alertas con afectación documentada a servicios MTDH**: 6 pendientes y 2 en seguimiento, 8 códigos UA, 3 provincias y 3 cantones. De las 17 alertas del periodo, 9 se excluyen por no acreditar impacto en instalaciones, acceso, continuidad o modalidad de atención. Tener un código UA no basta. El daño a viviendas de usuarios tampoco acredita por sí solo afectación al servicio. La revisión reproducible consta en `data/reference/enos_revision_servicios_2026-10-26.csv`. Los casos nuevos sin revisión quedan fuera hasta contar con evidencia.
- El campo Afectados mezcla personas, familias y usuarios. No se presenta una suma como personas únicas. Una alerta no equivale necesariamente a un evento independiente y no acredita causalidad ENOS. Se conservan los códigos y nombres de UA existentes, sin inferir códigos faltantes.
- Kits: siete entregas documentadas del 24–25/10, corte 25/10 a las 19:00; 802 kits en cuatro provincias y cinco cantones. Las entregas repetidas en un cantón tienen cantidades distintas y no se eliminan. No es el acumulado desde el 14/09.
- Bono: la ayuda memoria contiene planificación explícita para El Niño 2026–2027: 145.523 personas potenciales, 44.098 núcleos familiares y USD 13.405.351,02 estimados. Es una proyección nacional y permanece nacional al aplicar filtros provinciales.
- Referencia por inundaciones: 113 personas / USD 33.200,80 en pagos gestionados desde el 29/08, y 1.169 personas / USD 354.379,41 en articulación al 23/10. Se excluyen otros tipos de evento y la ejecución anual general. Gestionado no acredita cobro. La fuente no permite atribuir exclusivamente esos pagos a ENOS ni recortarlos desde el 14/09; se explicita en pantalla y en los documentos. Se requiere un detalle individual fechado y una clasificación oficial de vinculación ENOS para publicar esa ejecución específica.
- La Gasca (ALT-2026-000346) se excluye: la fuente describe familias usuarias afectadas y ayuda, pero no acredita impacto en la prestación del servicio. También se excluyen las dos alertas de Tenguel con código UA cuyo relato solo describe el sector. Los kits y bonos se mantienen como acciones institucionales solicitadas, con sus propios alcances; no se presentan como prueba de afectación a las UA.

El boletín N.º 0044 de Educación (25/10) se emplea como referencia de estructura. No se suman sus 1.378 eventos ni sus cifras educativas a los datos MTDH, y su pronóstico hasta el 25/10 no se presenta como pronóstico vigente.

## Fuentes y actualización

El snapshot `data/processed/seguimiento_enos_2026-10-26.json` publica únicamente campos operativos necesarios. Omite relatos libres, domicilios, responsables, teléfonos y datos personales de familias. Conserva las huellas de las fuentes.

```bash
python scripts/build_enos.py \
  --alerts "analisis-alertas-2026-10-26 (2).xlsx" \
  --service-review data/reference/enos_revision_servicios_2026-10-26.csv \
  --bonos "Bono de Contingencia - Fenómeno del Niño.docx" \
  --kits data/reference/enos_kits_2026-10-25.csv \
  --start 2026-09-14 --cut 2026-10-26 --kits-cut 2026-10-25 --bonos-cut 2026-10-23
```

Cada corte se guarda en su propio JSON. La interfaz permite elegir los cortes recibidos. El CSV de kits es una transcripción revisada de `Reporte_ministerial_kits_provincias_priorizadas_rev.pdf`; para nuevos cortes se debe suministrar el archivo actualizado. El parser de bonos conserva la provincia de las celdas verticalmente combinadas del Word. Los alcances narrativos de cada fuente deben revisarse cuando cambien sus periodos o criterios.

## Estabilidad de la aplicación

Se eliminó la invalidación manual de `sys.modules` al arrancar cada sesión: podía borrar un módulo mientras otra sesión lo importaba y causar el KeyError observado. La recarga de código queda a cargo de Streamlit.
