# Validación del corte de kits y suspensiones

- Fuente: Corte_procesado_Kobo_26oct2026_2226.xlsx, hoja Detalle de entregas; controles contrastados con Resumen provincial y Control y notas.
- 89 registros, con ID Kobo y UUID sin duplicados; 13.390 kits, 12.681 familias reportadas, 20 provincias y 42 cantones.
- Fechas de entrega: 31/08/2026–26/10/2026. Corte de exportación: 26/10/2026, 22:26:42. Familias reportadas no equivale a familias únicas. Los kits incluyen entregas anteriores al 14/09, fecha de inicio del seguimiento de alertas.
- El corte sustituye los 802 kits anteriores; no se suma a ellos. Se publican las 89 entregas con fecha, provincia/cantón, kits, familias e ID administrativo Kobo. Se excluyen UUID, domicilios, nombres personales y observaciones libres.
- Se verificaron los códigos cantonales con el catálogo territorial existente del proyecto.
- Suspensiones, reporte territorial 26/10 a las 16:00: 12 CDI de El Oro + 6 CDI de Santa Elena = 18 CDI; 63 CNH de Machala + 1 CNH de Santa Elena = 64 CNH. Total: 82 unidades con suspensión de atención, incluida la presencial.
- El consolidado recibido dice 19 CDI y 63 CNH; se usa el detalle territorial, que asigna correctamente el CNH Mis Primeras Enseñanzas a CNH.
- La última base contiene 99 filas: 82 suspendidas y 17 CDI de Guayas con modalidad por confirmar. Los 11 CDI virtuales y los 4 operativos no están en el detalle actualizado y no se presentan como registros de este corte. No se suma esta base a las 10 alertas con código UA.
- Guayaquil: la suma de las 17 coberturas individuales es 723; la frase “800 usuarios y familias afectadas” mezcla unidades y no se adopta como una cifra validada de personas.
- PDF ejecutivo: tres páginas con indicadores, alertas, continuidad y consolidado provincial. Excel: detalle completo autorizado de las 89 entregas y las 99 unidades del último archivo. El PDF incluye los nombres de las 19 unidades suspendidas identificadas y agrupa los 63 CNH sin nombre ni cantón.

- La base actualizada Base_afectaciones_lluvias_El_Oro_desagregada(1).xlsx contiene 99 filas en Base territorial y en su tabla dinámica Hoja1; Resumen aún indica 110 y se trata como desactualizado.

## Confirmación posterior de Guayas

Las 17 CDI de Guayas se reclasifican como suspendidas por instrucción expresa del usuario, posterior al corte de la base. Se conserva `estado_fuente` con el valor inicial y el motivo de validación. El resultado final es 99 UA suspendidas: 35 CDI y 64 CNH; El Oro 75, Guayas 17 y Santa Elena 7. El PDF y la presentación muestran los 36 nombres disponibles y agrupan los 63 CNH sin nombre/cantón. Los totales de kits permanecen en 13.390 y las alertas con código UA en 10.

## Confirmación oficial y unidad de presentación

Total oficial confirmado por el usuario: 13.390 kits entregados. Se presenta el campo original `familias` como núcleos familiares: 12.681 reportados por entrega, sin afirmar unicidad. Se actualiza la fecha visible en dashboard y exportables. Montos cotejados con la ayuda memoria fuente: USD 33.200,80 gestionados; USD 354.379,41 en articulación; USD 13.405.351,02 de planificación nacional. No se suman esas etapas.
