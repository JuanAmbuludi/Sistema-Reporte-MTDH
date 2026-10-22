# Validación de la entrega

Entrega revisada el 22 de octubre de 2026 con Python 3.12 y Streamlit 1.66.1.

## Fuente y cifras

Se procesó el Excel original incluido en `data/source/`. Los 296 agregados vigentes se conciliaron por provincia y programa. Los controles verifican 1.578.019 beneficiarios reportados de bonos y pensiones, 456.239 usuarios de servicios y 11.158 unidades. Se conservaron los saldos históricos de las dos pensiones con cobertura actual cero.

El presupuesto ejecutado permanece nulo porque el insumo no certifica esa fase presupuestaria. Los datos agregados no permiten verificar personas únicas. Estas condiciones se mantienen en pantalla y en las exportaciones.

## Aplicación y exportaciones

- Pruebas automáticas de depuración, claves, filtros, acumulados, nulos, ejecución parcial, autenticación y contenido de las tres exportaciones.
- Inicio de sesión real en navegador, consulta de dashboard, referencias anuales/cantonales y descarga efectiva de un PDF.
- Verificación en escritorio de 1.512 px y pantalla móvil de 390 px, sin desbordamiento horizontal del documento.
- Word y PDF de ejemplo: tres páginas; presentación: nueve diapositivas. Todas las páginas y diapositivas se renderizaron e inspeccionaron.
- Se revisó la correspondencia de los gráficos PowerPoint con los libros de datos incrustados y la selección exportada.

Los tests que contienen cifras esperadas corresponden al insumo de septiembre de 2026. Al sustituir ese corte por datos nuevos, actualiza esas referencias de regresión con cifras previamente conciliadas.

## Publicación

La aplicación queda lista para desplegar desde `app.py`, con dependencias, datos y cuenta inicial incluidos. El acceso `admin` / `admin12345678` se lee de `config/access.toml`, que contiene el hash de la contraseña. No requiere ejecutar el asistente ni configurar Secrets para el primer despliegue. Una sección `[auth]` configurada posteriormente en Secrets sustituye por completo ese acceso inicial.

El paquete para GitHub no incluye el archivo privado `.streamlit/secrets.toml` ni la cuenta personal del usuario. No se realizó un despliegue en Streamlit ni se creó un repositorio nuevo durante esta entrega: el paquete se entrega para que el usuario suba su contenido al repositorio y seleccione `app.py` en Streamlit.
