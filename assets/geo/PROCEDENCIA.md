# Cartografía de los mapas

`ecuador_dpa.json` contiene la geometría de todos los mapas de InfoReport (tablero y reportes): 1.040 parroquias,
224 cantones, 24 provincias, las 9 zonas de planificación y el contorno del país.

## Origen

- **Límites:** cartografía censal del Instituto Nacional de Estadística y Censos (INEC), edición 2015,
  publicada en el [Geoportal del INEC](https://www.ecuadorencifras.gob.ec/documentos/web-inec/Geografia_Estadistica/Micrositio_geoportal/index.html).
- **Redistribución utilizada:** paquete npm [`ec-atlas`](https://npmjs.org/package/ec-atlas) 0.0.7
  ([repositorio](https://github.com/ccalobeto/ec-atlas)), archivo `ecuador-transverse_mercator-50k.json`,
  un TopoJSON con país, provincias, cantones y parroquias.
- **Generación:** `scripts/build_geo.py` lee ese archivo y escribe `ecuador_dpa.json`; la huella SHA-256 del archivo
  de origen queda registrada dentro del propio JSON (`fuente.sha256`).

```bash
npm pack ec-atlas@0.0.7 && tar -xzf ec-atlas-0.0.7.tgz
python scripts/build_geo.py package/ecuador-transverse_mercator-50k.json
```

## Tratamiento

- **Topología compartida:** los polígonos vecinos usan exactamente los mismos arcos, por lo que no aparecen huecos
  ni superposiciones al cambiar de escala.
- **Tres niveles de detalle:** cada vértice lleva un nivel de simplificación (Visvalingam–Whyatt). El mapa nacional
  usa el nivel más liviano y los acercamientos a una provincia usan el detalle completo.
- **División vigente de las bases:** los códigos parroquiales de los datos se relacionan con los polígonos y se
  adopta la división político-administrativa que usan las bases (por ejemplo, La Concordia en Santo Domingo de los
  Tsáchilas). Las parroquias urbanas sin polígono propio se dibujan en la cabecera cantonal.
- **Zonas de planificación:** se forman disolviendo cantones y provincias (Zona 8: Guayaquil, Durán y Samborondón;
  Zona 9: Distrito Metropolitano de Quito).
- **Galápagos:** se dibuja en un recuadro desplazado 7,5° de longitud hacia el continente, una convención
  cartográfica para ver el país en un solo mapa.
- **Zona no delimitada (código 90):** no tiene polígono; su valor se incluye en totales, tablas y rankings.
- **Línea ecuatorial:** la línea punteada dorada marca la latitud 0°.

Son mapas estadísticos de referencia, no cartografía oficial de límites. Para límites oficiales consulte la
cartografía del Instituto Geográfico Militar (IGM) y del INEC.

## Licencia de la redistribución `ec-atlas`

```
MIT License

Copyright (c) 2023, Carlos León
All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
