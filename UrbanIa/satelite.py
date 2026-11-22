"""
Acceso a imágenes satelitales REALES.

Fuente: Sentinel-2 nivel L2A (reflectancia de superficie, ESA/Copernicus), consultado
mediante el catálogo STAC público "Earth Search" (Element 84) sobre Cloud-Optimized
GeoTIFFs en AWS. No requiere clave ni registro. Solo se descarga la ventana de
la imagen que cubre la ciudad (no la escena completa), por eso es rápido.

Por qué no CONAE como fuente principal: los productos de CONAE (SAOCOM, SAC-D, etc.)
se obtienen desde su catálogo con registro y descarga manual; no hay una API abierta
para consumirlos automáticamente desde un servidor. La estrategia del proyecto es usar
Sentinel-2 para el procesamiento automático y documentar a CONAE como fuente
complementaria (ver sección "Fuentes y limitaciones" de la documentación).
"""
import calendar
import os
from datetime import datetime

import numpy as np
import requests

import analisis as an

STAC_URL = os.getenv("STAC_URL", "https://earth-search.aws.element84.com/v1/search")
COLECCION = "sentinel-2-l2a"
BANDAS = {"blue": "blue", "green": "green", "red": "red", "nir": "nir", "swir": "swir16"}
SCL_INVALIDOS = [0, 1, 3, 8, 9, 10, 11]   # sin dato, saturado, sombra, nubes, cirros, nieve
FECHA_CAMBIO_BASELINE = datetime(2022, 1, 25)  # desde aquí Sentinel-2 L2A usa offset -1000 DN
MIN_PIXELES_VALIDOS = 0.60
OBJETIVO_PIXELES_VALIDOS = 0.85


class ErrorSatelital(Exception):
    """Error esperable (sin escenas, demasiadas nubes, servicio caído...). El mensaje es para el usuario."""


# ------------------------------------------------------------------ búsqueda
def buscar_escenas(lon, lat, anio, mes_desde, mes_hasta, max_nubes=20, limite=20):
    ultimo_dia = calendar.monthrange(anio, mes_hasta)[1]
    cuerpo = {
        "collections": [COLECCION],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{anio}-{mes_desde:02d}-01T00:00:00Z/{anio}-{mes_hasta:02d}-{ultimo_dia}T23:59:59Z",
        "limit": limite,
        "query": {"eo:cloud_cover": {"lt": max_nubes}},
    }
    try:
        r = requests.post(STAC_URL, json=cuerpo, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        raise ErrorSatelital(
            "No se pudo consultar el catálogo satelital (Earth Search). Intente nuevamente en unos minutos."
        ) from e
    items = r.json().get("features", [])
    items.sort(key=lambda f: f["properties"].get("eo:cloud_cover", 100))
    return items


def metadatos(item):
    """Datos de trazabilidad exigidos por la consigna: fecha, ubicación (tile) y fuente."""
    p = item["properties"]
    enlace = next((l["href"] for l in item.get("links", []) if l.get("rel") == "self"), "")
    return {
        "satelite": str(p.get("platform", "sentinel-2")).upper(),
        "producto": "Sentinel-2 L2A (reflectancia de superficie) - catálogo Earth Search",
        "id_escena": item["id"],
        "fecha_adquisicion": datetime.strptime(p["datetime"][:19], "%Y-%m-%dT%H:%M:%S"),
        "cobertura_nubes": float(p.get("eo:cloud_cover", 0.0)),
        "tile": str(p.get("grid:code", "")),
        "url_fuente": enlace,
    }


# ------------------------------------------------------------------- lectura
def _leer_banda(href, grilla, nearest):
    """Lee una banda remota recortada y remuestreada a la grilla común (EPSG:3857, 10 m)."""
    import rasterio
    from rasterio.crs import CRS
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    transform = from_origin(grilla["x0"], grilla["y1"], grilla["res"], grilla["res"])
    metodo = Resampling.nearest if nearest else Resampling.bilinear
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=CRS.from_epsg(3857), transform=transform,
                       width=grilla["n"], height=grilla["n"],
                       resampling=metodo, nodata=0) as vrt:
            return vrt.read(1)


def _reflectancia(dn, asset, fecha):
    rb = (asset.get("raster:bands") or [{}])[0]
    escala = rb.get("scale", 0.0001)
    offset = rb.get("offset", -0.1 if fecha >= FECHA_CAMBIO_BASELINE else 0.0)
    return np.clip(dn.astype(np.float32) * escala + offset, 0.0, 1.0)


def _leer_escena(item, grilla):
    fecha = datetime.strptime(item["properties"]["datetime"][:19], "%Y-%m-%dT%H:%M:%S")
    assets = item["assets"]
    faltan = [k for k in list(BANDAS.values()) + ["scl"] if k not in assets]
    if faltan:
        raise ErrorSatelital(f"La escena {item['id']} no tiene las bandas necesarias ({', '.join(faltan)}).")

    bandas, dn_rojo = {}, None
    for clave, asset_key in BANDAS.items():
        dn = _leer_banda(assets[asset_key]["href"], grilla, nearest=False)
        if clave == "red":
            dn_rojo = dn
        bandas[clave] = _reflectancia(dn, assets[asset_key], fecha)
    scl = _leer_banda(assets["scl"]["href"], grilla, nearest=True)
    bandas["valido"] = (dn_rojo > 0) & (~np.isin(scl, SCL_INVALIDOS))
    return bandas


def _mejor_escena(lon, lat, anio, mes_desde, mes_hasta, max_nubes, grilla):
    candidatas = buscar_escenas(lon, lat, anio, mes_desde, mes_hasta, max_nubes)
    if not candidatas:
        raise ErrorSatelital(
            f"No hay escenas Sentinel-2 con menos de {max_nubes} % de nubes para {anio} en el período "
            f"elegido. Pruebe otro año u otra estación."
        )
    mejor = None
    for item in candidatas[:4]:
        try:
            bandas = _leer_escena(item, grilla)
        except ErrorSatelital:
            raise
        except Exception:
            continue  # escena corrupta o inaccesible: probar la siguiente
        frac = float(bandas["valido"].mean())
        if mejor is None or frac > mejor[0]:
            mejor = (frac, item, bandas)
        if frac >= OBJETIVO_PIXELES_VALIDOS:
            break
    if mejor is None:
        raise ErrorSatelital(f"No se pudieron leer las imágenes de {anio}. Intente nuevamente más tarde.")
    if mejor[0] < MIN_PIXELES_VALIDOS:
        raise ErrorSatelital(
            f"Las mejores escenas de {anio} cubren solo el {mejor[0] * 100:.0f} % del área sin nubes "
            f"(mínimo {MIN_PIXELES_VALIDOS * 100:.0f} %). Pruebe otro año, otra estación o un radio menor."
        )
    return mejor[1], mejor[2]


# --------------------------------------------------------------- orquestación
def procesar(lon, lat, radio_km, anio_a, anio_b, mes_desde, mes_hasta, max_nubes=20):
    """
    Descarga las dos escenas, las clasifica y las compara.
    Devuelve un dict con metadatos de escenas, estadísticas, anillos y PNG.
    """
    try:
        import rasterio
    except ImportError as e:  # pragma: no cover
        raise ErrorSatelital("El servidor no tiene instalada la librería rasterio.") from e

    grilla = an.definir_grilla(lon, lat, radio_km)
    entorno = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "AWS_NO_SIGN_REQUEST": "YES",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF",
        "GDAL_HTTP_TIMEOUT": "30",
        "GDAL_HTTP_MAX_RETRY": "3",
    }
    with rasterio.Env(**entorno):
        item_a, bandas_a = _mejor_escena(lon, lat, anio_a, mes_desde, mes_hasta, max_nubes, grilla)
        item_b, bandas_b = _mejor_escena(lon, lat, anio_b, mes_desde, mes_hasta, max_nubes, grilla)

    cls_a, cls_b = an.clasificar(bandas_a), an.clasificar(bandas_b)
    try:
        stats, anillos, mascaras = an.comparar(cls_a, cls_b, radio_km)
    except ValueError as e:
        raise ErrorSatelital(str(e)) from e

    rgb_a, rgb_b = an.rgb_png(bandas_a), an.rgb_png(bandas_b)
    cambio = an.overlay_png(mascaras)
    return {
        "cambios": an.detalle_cambios(mascaras, grilla),
        "escena_inicio": metadatos(item_a),
        "escena_fin": metadatos(item_b),
        "stats": stats,
        "anillos": anillos,
        "bounds": grilla["bounds"],
        "imagenes": {"rgb_inicio": rgb_a, "rgb_fin": rgb_b, "cambio": cambio},
        "para_ia": [an.miniatura_png(rgb_a), an.compuesto_png(rgb_b, cambio)],
    }
