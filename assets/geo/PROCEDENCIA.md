# Límites provinciales

`ecuador_provincias.geojson` contiene las 24 provincias del Ecuador que dibujan los mapas de la aplicación y de los reportes.

- **Origen:** Natural Earth, capa *Admin 1 – States, Provinces* a escala 1:10m, de dominio público: <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-1-states-provinces/>
- **Simplificación:** topológica con mapshaper, conservando el 25 % de los vértices. Las provincias vecinas siguen compartiendo bordes y el archivo pesa unos 34 KB, de modo que los mapas cargan sin conexión y sin servicios externos.
- **Códigos:** cada provincia lleva el código provincial de dos dígitos que usa la base de datos (`01` Azuay … `24` Santa Elena), su nombre oficial y su región natural.
- **Galápagos:** se dibuja en un recuadro desplazado 7,5° de longitud hacia el continente. Es una convención cartográfica para ver todo el país en un solo mapa; no representa su ubicación real.
- **Zona en estudio (código 90):** no tiene polígono. Su valor aparece como nota junto al mapa y se incluye en totales y rankings.
- **Línea ecuatorial:** la línea punteada dorada marca la latitud 0°.

`src/geo.py` lee este archivo y entrega los polígonos al mapa interactivo (Plotly), al mapa del encabezado (SVG) y a los mapas de los reportes (matplotlib).

Son mapas estadísticos de referencia, no cartografía oficial de límites. Para límites oficiales consulte la cartografía del Instituto Geográfico Militar (IGM).
