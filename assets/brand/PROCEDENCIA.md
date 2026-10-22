# Identidad visual

`mtdh_logo.png` reproduce sin modificación la imagen incrustada en el PDF proporcionado por el usuario, `Resumen_Ejecutivo_MTDH_2026_09.pdf` (imagen de 1184 × 282 píxeles con canal alfa original). Conserva las proporciones y el escudo. La tipografía del logotipo es blanca y requiere un fondo oscuro.

`escudo.png` es el escudo recortado de ese mismo logo, sin redibujarlo. `favicon.png` lo coloca sobre una placa morada redondeada para la pestaña del navegador.

## Paleta

Los anclajes provienen del boletín y del logo oficial. Los demás tonos se generan en OKLCH con el mismo tono del morado institucional, para que interfaz, gráficos y documentos hablen el mismo idioma. Todos viven en `src/theme.py`: cambiar un valor ahí actualiza la aplicación y los cuatro formatos de reporte.

| Rol | Color | Origen |
| --- | --- | --- |
| Morado institucional | `#512F8D` | Placa del logo y cabeceras del boletín |
| Lavanda | `#EBE5F3` | Superficies de tablas del boletín |
| Niebla | `#F7F5FA` | Fondo claro del boletín |
| Tinta | `#20202B` | Texto principal del boletín |
| Oro | `#F8C018` | Oro del escudo nacional en el logo; marca el territorio elegido y la línea ecuatorial |
| Fucsia | `#C33F8D` | Acento secundario derivado en OKLCH; distingue los servicios de protección integral de los bonos y pensiones |
| Rampa morada | `#F7F6FD` → `#3D216D` | Diez pasos de un solo tono para magnitudes (mapas y mapas de calor) |

El par morado–fucsia de los gráficos se validó con el método de la guía de visualización: banda de luminosidad, separación entre ambos colores con visión normal y con daltonismo, y contraste mínimo de 3:1 sobre blanco.

## Tipografías

- **Montserrat** (títulos y cifras) y **Public Sans** (texto) en la aplicación y en los gráficos de los reportes. Ambas tienen licencia SIL Open Font License 1.1; las licencias están en `assets/fonts/` y `static/fonts/`. Public Sans fue diseñada para servicios públicos; Montserrat acompaña la rotulación geométrica del logotipo.
- **Century Gothic** (títulos) y **Calibri** (texto) en Excel, Word y PowerPoint, porque vienen instaladas con Microsoft Office y el archivo se ve igual en cualquier equipo de la institución sin incrustar fuentes.

Esta implementación toma el boletín y el logo como referencia visual; no sustituye la revisión del manual de identidad institucional ni la aprobación de Comunicación.
