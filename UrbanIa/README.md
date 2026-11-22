# UrbanIA Córdoba

Plataforma web para analizar el crecimiento urbano y la pérdida de espacios verdes de 24 ciudades de la
Provincia de Córdoba con imágenes satelitales **reales** (Sentinel-2) e Inteligencia Artificial (Gemini).
Trabajo Final Integrador – Aplicaciones Informáticas (Opción 4: UrbanIA).

## Ejecutar en local
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # editar SECRET_KEY y GEMINI_API_KEY
python init_db.py                                     # crea tablas + datos de prueba (SQLite por defecto)
flask --app app run --debug                           # http://127.0.0.1:5000
```
> `rasterio` trae GDAL en su rueda para Windows/Linux/macOS con Python 3.9–3.12. Si falla la instalación, use Python 3.11.

## Novedades de la versión 2
- Resultados en **5 pestañas**: Antes y después · Cambios detectados · Estadísticas · Informe · Fuentes.
- **Cambios específicos**: zonas de nueva urbanización / pérdida / ganancia de vegetación con tamaño, dirección y distancia al centro, botón para ver un punto de referencia aproximado en el mapa, crecimiento por dirección y descarga CSV/PNG.
- **Mapa más fácil de leer**: guía de colores y años sobre el mapa, orientación sencilla (norte arriba), explicación de los filtros y superficies comparadas con canchas de fútbol.
- **Comparación y orientación**: separador deslizante para comparar ambos años, explicación del área comparable sin nubes ni sombras, guía rápida de uso y marcador que aclara que solo indica una ubicación aproximada (no un límite exacto).
- **Accesibilidad**: tamaño de texto, alto contraste, colores aptos para daltonismo, pestañas con teclado, tablas equivalentes a los gráficos, resumen en lenguaje simple y lectura en voz alta.
- **Resumen provincial** (`/resumen`): ranking de ciudades y totales por cluster.

> **Si ya había ejecutado la versión 1:** se agregó la columna `cambios_json`. Borre `instance/urbania.db` (o `urbania.db`) y
> ejecute de nuevo `python init_db.py`. En MySQL/PostgreSQL: `ALTER TABLE analisis_urbano ADD COLUMN cambios_json TEXT;`.
> También ejecute `pip install -r requirements.txt` (se agregó `scipy`).

## Usuarios de prueba (cambiar en producción con las variables *_PASSWORD)
| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | admin@urbania.local | Admin1234! |
| Planificador Urbano | planificador@urbania.local | Plan1234! |
| Consultor | consultor@urbania.local | Cons1234! |

## Estructura
```
app.py          rutas, autenticación, roles, CSRF, CRUD, API
models.py       8 tablas (SQLAlchemy)
analisis.py     núcleo numérico: índices, clasificación, comparación, zonas de cambio, PNG (sin red)
satelite.py     búsqueda STAC + lectura de Sentinel-2 (rasterio)
ia.py           informe con Gemini (multimodal) + plan B sin IA
init_db.py      crea tablas y carga datos
schema.sql      esquema MySQL equivalente
templates/ static/   frontend (HTML5, CSS3, JavaScript: visor.js, accesibilidad.js, resumen.js...)
```

## Despliegue (Render + base remota)
La aplicación Flask no se puede alojar en GitHub Pages; GitHub guarda el código y Render ejecuta el servidor.

1. Confirma los cambios en GitHub y crea una base de datos PostgreSQL en Supabase u otro proveedor. Copia su URL de conexión.
2. Abre [desplegar UrbanIA en Render](https://render.com/deploy?repo=https://github.com/Kingolitaprime/UrbanIA) e inicia sesión en Render.
3. En el formulario de despliegue, proporciona `DATABASE_URL` y contraseñas propias para `ADMIN_PASSWORD`, `PLANIFICADOR_PASSWORD` y `CONSULTOR_PASSWORD`. Render genera `SECRET_KEY` automáticamente. No reutilices las contraseñas de prueba.
4. Render construye la aplicación, inicializa la base de datos y publica una URL `https://urbania.onrender.com` (o el nombre que elijas). Esa URL es el enlace público para compartir. El primer inicio puede tardar unos minutos.

La base de datos debe ser PostgreSQL y estar disponible desde Render. `GEMINI_API_KEY` es opcional; sin ella se utiliza el modo de informe alternativo. El plan gratuito de Render puede suspender el servicio cuando no recibe tráfico; al volver a abrirlo, el inicio puede demorar.

## Aviso
Las superficies son **estimaciones** por teledetección (umbrales de índices espectrales), no mediciones confirmadas.
Los registros marcados "[PRUEBA]" son ilustrativos y no provienen de imágenes reales.
