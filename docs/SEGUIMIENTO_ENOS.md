# Seguimiento y respuesta en Riesgos

Acceso: **Riesgos**. La exposición territorial se conserva como análisis interno y no se muestra en el dashboard ni en sus reportes. Los exportables completos incluyen indicadores, evolución, gráficas por provincia y servicio, las diez alertas con código y nombre UA, acciones provinciales, kits, planificación y nota metodológica. El seguimiento inicia el **14/09/2026**. En el corte actual: PDF de tres páginas, PowerPoint de diez diapositivas y Excel de nueve hojas.

## Corte del 26 de octubre de 2026

- Se revisaron las **31 alertas** desde el 14/09. El criterio vigente solicitado por el responsable incluye **solo registros con código UA**: **10 alertas y 10 códigos UA distintos**, en 3 provincias y 4 cantones. Ocho registros corresponden a Desarrollo Infantil y dos a CNH. El primer registro con código es del 16/10. Los 21 registros sin código quedan fuera de este alcance.
- **Ocho alertas tienen afectación documentada y dos están por confirmar**. En ALT-2026-000315 / UA 58336 y ALT-2026-000316 / UA 58337 (Tenguel), la fuente vincula una UA pero solo describe inundación territorial. Se muestran con esa salvedad, sin atribuir un daño o interrupción no confirmados.
- El campo Afectados mezcla personas, familias y usuarios. No se presenta una suma como personas únicas. Una alerta no equivale necesariamente a un evento independiente y no acredita causalidad ENOS. Se conservan los códigos y nombres de UA existentes, sin inferir códigos faltantes.
- Kits en provincias priorizadas: siete entregas documentadas del 24–25/10, corte 25/10 a las 19:00; 802 kits en cuatro provincias priorizadas (Azuay, Esmeraldas, Guayas y Manabí) y cinco cantones. Las entregas repetidas en un cantón tienen cantidades distintas y no se eliminan. No es el acumulado desde el 14/09.
- Bono: la ayuda memoria contiene planificación explícita para El Niño 2026–2027: 145.523 personas potenciales, 44.098 núcleos familiares y USD 13.405.351,02 estimados. Es una proyección nacional y permanece nacional al aplicar filtros provinciales.
- Referencia por inundaciones: 113 núcleos familiares / USD 33.200,80 en pagos gestionados desde el 29/08, y 1.169 personas / USD 354.379,41 en articulación al 23/10. Se excluyen otros tipos de evento y la ejecución anual general. La fuente no permite atribuir exclusivamente esos pagos a ENOS ni recortarlos desde el 14/09; se explicita en pantalla y en los documentos. Se requiere un detalle individual fechado y una clasificación oficial de vinculación ENOS para publicar esa ejecución específica.
- La Gasca (ALT-2026-000346) se excluye: la fuente describe familias usuarias afectadas y ayuda, pero no acredita impacto en la prestación del servicio. Las dos alertas de Tenguel se distinguen como afectación por confirmar, según el criterio actualizado de código UA. Los kits y bonos se mantienen como acciones institucionales solicitadas, con sus propios alcances; no se presentan como prueba de afectación a las UA.

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

### Visibilidad y unidades de medida

Por instrucción del responsable, la exposición territorial se conserva como análisis interno y deja de mostrarse en el tablero, los mapas, los indicadores, las tablas y los exportables públicos de Riesgos, incluido el resumen de todas las secciones. Los exportables completos usan únicamente la respuesta institucional visible y sus filtros.

El indicador de bonos gestionados se presenta como **113 núcleos familiares**, con **USD 33.200,80**, por aclaración del responsable. La columna original de la ayuda memoria se titula PERSONAS; se conserva su nombre técnico `personas` en el dato de origen para mantener la trazabilidad. No se cambia el conteo, no se estima el tamaño de los núcleos y no se reinterpreta la columna de casos en articulación (personas).

### Criterio vigente confirmado con la captura del responsable

Se muestran **solo registros revisados con código UA**: **10 alertas y 10 códigos UA distintos**, ocho en Desarrollo Infantil y dos en CNH. Se verificó el filtro de la columna Código SIIMDH del Excel original, descartando guiones y valores vacíos. El seguimiento sigue desde el 14/09/2026; la primera alerta con código es del 16/10/2026. La ausencia de registros con código en septiembre no acredita ausencia de eventos.

De estas diez, **ocho tienen afectación documentada y dos están por confirmar**: ALT-2026-000315 / UA 58336 y ALT-2026-000316 / UA 58337, en Tenguel. El código las vincula a una UA, pero sus relatos solo documentan inundación territorial. Se incorporan por el criterio expresamente confirmado por el responsable y se muestran como afectación por confirmar, sin afirmar daño ni interrupción del servicio. Las cinco alertas anteriormente incluidas sin código quedan fuera del alcance público. La Gasca permanece excluida.

La revisión CSV registra inclusión y confirmación de afectación por separado. El snapshot de esquema 3 declara `criterio_alertas=codigo_ua`: 31 registros originales, 10 incluidos, 21 excluidos, 8 con impacto documentado y 2 por confirmar. Tablero, gráficas y exportables usan ese mismo criterio.
