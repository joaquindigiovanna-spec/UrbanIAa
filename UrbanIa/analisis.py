"""
Núcleo de análisis territorial de UrbanIA Córdoba.

Solo depende de numpy y Pillow (no toca la red ni rasterio), de modo que puede
probarse de forma aislada. La lectura de imágenes satelitales está en satelite.py.

Método (resumen):
  1. Reflectancia de superficie (Sentinel-2 L2A) -> índices NDVI, NDBI y MNDWI.
  2. Clasificación por umbrales: agua / vegetación / urbano-construido / suelo.
  3. Se comparan dos fechas sobre la MISMA grilla y solo en píxeles válidos
     (sin nubes ni sombras) en ambas imágenes.
  4. Resultado: hectáreas estimadas de cambio, estadísticas por anillos y mapas PNG.

IMPORTANTE: son ESTIMACIONES por teledetección, no mediciones confirmadas en terreno.
"""
import io
import math

import numpy as np
from PIL import Image

RES_M = 10.0                      # resolución espacial de trabajo (m)
HA_PIXEL = (RES_M ** 2) / 10000.0  # hectáreas por píxel (0,01 ha)
R_MERC = 6378137.0                # radio terrestre de Web Mercator

CL_INVALIDO, CL_AGUA, CL_VEG, CL_URBANO, CL_SUELO = 0, 1, 2, 3, 4

# Umbrales iniciales. Son valores típicos de la bibliografía y DEBEN calibrarse
# contra puntos de verificación (ver sección de limitaciones de la documentación).
UMBRALES = {
    "ndvi_veg": 0.35,      # NDVI >= -> vegetación
    "ndvi_urb_max": 0.20,  # NDVI < -> candidato a construido
    "ndbi_urb_min": 0.00,  # NDBI >= -> candidato a construido
    "bui_min": 0.05,       # (NDBI - NDVI) >= -> construido
    "mndwi_agua": 0.20,    # MNDWI > -> agua
}


# ---------------------------------------------------------------- geometría
def mercator(lon, lat):
    x = R_MERC * math.radians(lon)
    y = R_MERC * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def mercator_inv(x, y):
    lon = math.degrees(x / R_MERC)
    lat = math.degrees(2 * math.atan(math.exp(y / R_MERC)) - math.pi / 2)
    return lon, lat


def definir_grilla(lon, lat, radio_km):
    """
    Grilla cuadrada en EPSG:3857 centrada en (lon, lat). Se usa 3857 porque Leaflet
    dibuja en ese sistema: la imagen queda exactamente alineada con el mapa base.
    El tamaño de píxel se corrige por 1/cos(lat) para que cada píxel represente
    RES_M x RES_M metros REALES (si no, las áreas quedarían infladas ~37 %).
    """
    k = math.cos(math.radians(lat))
    res = RES_M / k
    n = int(round(2 * radio_km * 1000 / RES_M))
    cx, cy = mercator(lon, lat)
    x0 = cx - n * res / 2
    y1 = cy + n * res / 2
    oeste, sur = mercator_inv(x0, y1 - n * res)
    este, norte = mercator_inv(x0 + n * res, y1)
    return {
        "n": n, "res": res, "x0": x0, "y1": y1,
        "bounds": [[sur, oeste], [norte, este]],  # formato Leaflet [[S,O],[N,E]]
    }


# ---------------------------------------------------------- clasificación
def _nd(a, b):
    return (a - b) / (a + b + 1e-6)


def _mayoria(mask):
    """Filtro de mayoría 3x3: elimina píxeles aislados (ruido) en una máscara booleana."""
    h, w = mask.shape
    p = np.pad(mask.astype(np.uint8), 1)
    suma = np.zeros((h, w), dtype=np.uint8)
    for i in range(3):
        for j in range(3):
            suma += p[i:i + h, j:j + w]
    return suma >= 5


def clasificar(b):
    """
    b: dict con arrays float32 de reflectancia (blue, green, red, nir, swir) y
    'valido' (bool). Devuelve array uint8 de clases.
    """
    u = UMBRALES
    ndvi = _nd(b["nir"], b["red"])
    ndbi = _nd(b["swir"], b["nir"])
    mndwi = _nd(b["green"], b["swir"])

    cls = np.full(ndvi.shape, CL_SUELO, dtype=np.uint8)
    urbano = (ndbi >= u["ndbi_urb_min"]) & (ndvi < u["ndvi_urb_max"]) & ((ndbi - ndvi) >= u["bui_min"])
    cls[urbano] = CL_URBANO
    cls[ndvi >= u["ndvi_veg"]] = CL_VEG
    cls[mndwi > u["mndwi_agua"]] = CL_AGUA
    cls[~b["valido"]] = CL_INVALIDO
    return cls


# ------------------------------------------------------------- comparación
def comparar(cls_a, cls_b, radio_km):
    """
    Compara dos clasificaciones de la misma grilla. Devuelve (stats, anillos, mascaras).
    Solo se cuentan píxeles válidos en AMBAS fechas.
    """
    valido = (cls_a != CL_INVALIDO) & (cls_b != CL_INVALIDO)
    n_valido = int(valido.sum())
    if n_valido == 0:
        raise ValueError("No hay píxeles válidos comunes entre ambas fechas.")

    urb_a = _mayoria(cls_a == CL_URBANO) & valido
    urb_b = _mayoria(cls_b == CL_URBANO) & valido
    veg_a = _mayoria(cls_a == CL_VEG) & valido
    veg_b = _mayoria(cls_b == CL_VEG) & valido

    nuevas = urb_b & ~urb_a
    verde_perdido = veg_a & ~veg_b
    verde_ganado = veg_b & ~veg_a
    verde_a_urbano = nuevas & veg_a

    def ha(m):
        return round(float(m.sum()) * HA_PIXEL, 2)

    stats = {
        "ha_analizadas": ha(valido),
        "pct_pixeles_validos": round(100.0 * n_valido / valido.size, 1),
        "ha_urbanas_inicio": ha(urb_a),
        "ha_urbanas_fin": ha(urb_b),
        "ha_urbanizadas": ha(nuevas),
        "ha_verdes_perdidas": ha(verde_perdido),
        "ha_verdes_ganadas": ha(verde_ganado),
        "ha_verde_a_urbano": ha(verde_a_urbano),
        "pct_verde_inicio": round(100.0 * float(veg_a.sum()) / n_valido, 1),
        "pct_verde_fin": round(100.0 * float(veg_b.sum()) / n_valido, 1),
    }

    # Distribución de áreas verdes: % de vegetación por anillo de 1 km desde el centro
    n = cls_a.shape[0]
    yy, xx = np.indices(cls_a.shape)
    dist_km = np.hypot(yy - (n - 1) / 2, xx - (n - 1) / 2) * RES_M / 1000.0
    def pct(m, total):
        return round(100.0 * float(m.sum()) / total, 1) if total else None

    anillos = []
    for k in range(int(math.ceil(radio_km))):
        en_anillo = valido & (dist_km >= k) & (dist_km < k + 1)
        t = int(en_anillo.sum())
        anillos.append({
            "desde_km": k, "hasta_km": k + 1,
            "pct_verde_inicio": pct(veg_a & en_anillo, t),
            "pct_verde_fin": pct(veg_b & en_anillo, t),
            "pct_urbano_inicio": pct(urb_a & en_anillo, t),
            "pct_urbano_fin": pct(urb_b & en_anillo, t),
        })

    mascaras = {"nuevas": nuevas, "verde_perdido": verde_perdido,
                "verde_ganado": verde_ganado, "verde_a_urbano": verde_a_urbano,
                "valido": valido, "veg_a": veg_a, "urb_a": urb_a}
    return stats, anillos, mascaras


# ------------------------------------------------------------------ imágenes
def _png(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def rgb_png(b):
    """Color natural con estiramiento simple. Píxeles inválidos (nubes) en gris."""
    rgb = np.stack([b["red"], b["green"], b["blue"]], axis=-1)
    img = (np.clip(rgb / 0.30, 0, 1) ** 0.8 * 255).astype(np.uint8)
    img[~b["valido"]] = (128, 128, 128)
    return _png(img)


# Paleta apta para daltonismo (basada en Okabe-Ito). La leyenda de la interfaz usa los mismos valores.
COLORES_CAMBIO = {
    "nueva_urbanizacion": (213, 94, 0),     # bermellón  #D55E00
    "verde_a_urbano": (122, 31, 92),        # púrpura    #7A1F5C
    "verde_perdido": (240, 228, 66),        # amarillo   #F0E442
    "verde_ganado": (0, 114, 178),          # azul       #0072B2
}


def overlay_png(m):
    """Capa RGBA transparente con los cambios (para superponer sobre el mapa)."""
    h, w = m["nuevas"].shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    c = COLORES_CAMBIO
    out[m["verde_ganado"]] = (*c["verde_ganado"], 170)
    out[m["verde_perdido"]] = (*c["verde_perdido"], 200)
    out[m["nuevas"]] = (*c["nueva_urbanizacion"], 215)
    out[m["verde_a_urbano"]] = (*c["verde_a_urbano"], 240)
    return _png(out)


def compuesto_png(rgb_bytes, overlay_bytes, lado=512):
    """Imagen RGB + cambios, reducida: se envía a la IA como contexto visual."""
    base = Image.open(io.BytesIO(rgb_bytes)).convert("RGBA")
    capa = Image.open(io.BytesIO(overlay_bytes)).convert("RGBA")
    base.alpha_composite(capa)
    base.thumbnail((lado, lado))
    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def miniatura_png(png_bytes, lado=512):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img.thumbnail((lado, lado))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------- detalle de los cambios
DIRS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
DIRS_NOMBRE = ["norte", "noreste", "este", "sudeste", "sur", "sudoeste", "oeste", "noroeste"]
MIN_HA_ZONA = 0.5  # zonas menores se consideran ruido y no se listan


def _octante(dx, dy):
    """Índice de octante (0=N, 1=NE...) desde el centro; dx hacia el este, dy hacia el norte."""
    rumbo = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0
    return (np.floor((rumbo + 22.5) / 45.0).astype(int)) % 8


def _lonlat_de_pixel(grilla, fila, col):
    x = grilla["x0"] + (col + 0.5) * grilla["res"]
    y = grilla["y1"] - (fila + 0.5) * grilla["res"]
    return mercator_inv(x, y)


def _zonas(mask, tipo, grilla, veg_a, top):
    from scipy import ndimage
    etiquetas, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return 0, []
    tam = np.bincount(etiquetas.ravel())[1:]
    min_px = int(round(MIN_HA_ZONA / HA_PIXEL))
    ids = np.where(tam >= min_px)[0] + 1
    if len(ids) == 0:
        return 0, []
    orden = ids[np.argsort(-tam[ids - 1])][:top]
    centros = ndimage.center_of_mass(mask, etiquetas, orden)
    ex_verde = np.atleast_1d(ndimage.sum(veg_a, etiquetas, orden))
    c0 = (mask.shape[0] - 1) / 2.0
    zonas = []
    for i, lid in enumerate(orden):
        fila, col = centros[i]
        dx, dy = col - c0, c0 - fila
        oct_i = int(_octante(np.array([dx]), np.array([dy]))[0])
        lon, lat = _lonlat_de_pixel(grilla, fila, col)
        px = int(tam[lid - 1])
        zonas.append({
            "tipo": tipo, "ha": round(px * HA_PIXEL, 2),
            "lat": round(float(lat), 6), "lng": round(float(lon), 6),
            "dir": DIRS[oct_i], "dir_nombre": DIRS_NOMBRE[oct_i],
            "dist_km": round(float(np.hypot(dx, dy)) * RES_M / 1000.0, 2),
            "pct_ex_verde": round(100.0 * float(ex_verde[i]) / px, 0),
        })
    return int(len(ids)), zonas


def detalle_cambios(m, grilla, top=8):
    """
    Zonas de cambio individuales (las mayores de cada tipo) con ubicación respecto del centro,
    más la distribución del cambio por dirección (8 octantes).
    """
    n_zonas, parcelas = {}, []
    for clave, mascara, tipo in (("urbanizacion", m["nuevas"], "Nueva urbanización"),
                                 ("perdida_verde", m["verde_perdido"], "Pérdida de vegetación"),
                                 ("ganancia_verde", m["verde_ganado"], "Ganancia de vegetación")):
        total, zs = _zonas(mascara, tipo, grilla, m["veg_a"], top)
        n_zonas[clave] = total
        parcelas.extend(zs)

    n = m["nuevas"].shape[0]
    c0 = (n - 1) / 2.0
    direcciones = []
    por_dir = {}
    for clave, mascara in (("ha_urbanizadas", m["nuevas"]), ("ha_verde_perdido", m["verde_perdido"])):
        filas, cols = np.nonzero(mascara)
        octs = _octante(cols - c0, c0 - filas) if len(filas) else np.array([], dtype=int)
        por_dir[clave] = np.bincount(octs, minlength=8) * HA_PIXEL
    for i in range(8):
        direcciones.append({"dir": DIRS[i], "nombre": DIRS_NOMBRE[i],
                            "ha_urbanizadas": round(float(por_dir["ha_urbanizadas"][i]), 2),
                            "ha_verde_perdido": round(float(por_dir["ha_verde_perdido"][i]), 2)})
    return {"min_ha": MIN_HA_ZONA, "n_zonas": n_zonas, "parcelas": parcelas, "direcciones": direcciones}


# ----------------------------------------------------- indicadores y resumen
def indicadores(stats, ai, af):
    """Indicadores derivados de las estadísticas (None cuando no se pueden calcular)."""
    anos = max(af - ai, 1)
    ini, fin = stats.get("ha_urbanas_inicio"), stats.get("ha_urbanas_fin")
    nuevas, perd = stats.get("ha_urbanizadas"), stats.get("ha_verdes_perdidas")
    a_urb = stats.get("ha_verde_a_urbano")
    return {
        "crecimiento_pct": round(100.0 * (fin - ini) / ini, 1) if ini and fin is not None else None,
        "ha_por_ano": round(nuevas / anos, 1) if nuevas is not None else None,
        "pct_urbanizado_era_verde": round(100.0 * a_urb / nuevas, 0) if nuevas and a_urb is not None else None,
        "verde_perdido_por_ha_urbanizada": round(perd / nuevas, 2) if nuevas and perd is not None else None,
        "variacion_verde_pp": round(stats["pct_verde_fin"] - stats["pct_verde_inicio"], 1)
        if stats.get("pct_verde_fin") is not None and stats.get("pct_verde_inicio") is not None else None,
    }


def _num(x):
    return f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".").replace(",0", "", 1) \
        if x is not None else "s/d"


def resumen_simple(ciudad, ai, af, stats, cambios=None):
    """Resumen en lenguaje llano (sirve para lectura en voz alta y para personas no técnicas)."""
    nuevas, perd = stats["ha_urbanizadas"], stats["ha_verdes_perdidas"]
    ind = indicadores(stats, ai, af)
    canchas = int(round(nuevas * 1.4))  # una cancha de fútbol reglamentaria ocupa unos 0,7 ha
    f = [f"Entre {ai} y {af}, en {ciudad}, se estima que se urbanizó una superficie de {_num(nuevas)} hectáreas, "
         f"equivalente a unas {canchas} canchas de fútbol."]
    if ind["variacion_verde_pp"] is not None:
        verbo = "bajó" if ind["variacion_verde_pp"] < 0 else "subió"
        f.append(f"La vegetación {verbo} de {_num(stats['pct_verde_inicio'])} % a {_num(stats['pct_verde_fin'])} % "
                 f"del área analizada, con {_num(perd)} hectáreas de vegetación perdida.")
    if ind["pct_urbanizado_era_verde"] is not None and nuevas:
        f.append(f"Se calcula que alrededor de {int(ind['pct_urbanizado_era_verde'])} % de lo urbanizado era vegetación.")
    if cambios and cambios.get("direcciones"):
        mayor = max(cambios["direcciones"], key=lambda d: d["ha_urbanizadas"])
        if mayor["ha_urbanizadas"] > 0 and nuevas:
            pct = int(round(100.0 * mayor["ha_urbanizadas"] / nuevas))
            f.append(f"El mayor crecimiento se dio hacia el {mayor['nombre']} del centro ({pct} % de lo urbanizado).")
    zonas = [p for p in (cambios or {}).get("parcelas", []) if p["tipo"] == "Nueva urbanización"]
    if zonas:
        z = zonas[0]
        f.append(f"La zona nueva más grande ocupa {_num(z['ha'])} hectáreas y está a {_num(z['dist_km'])} km "
                 f"al {z['dir_nombre']} del centro.")
    f.append("Son estimaciones obtenidas de imágenes satelitales, no mediciones confirmadas en terreno.")
    return " ".join(f)
