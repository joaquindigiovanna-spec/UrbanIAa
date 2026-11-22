"""
Módulo de Inteligencia Artificial.

Usa la API de Gemini (SDK oficial google-genai) de forma MULTIMODAL: recibe las
estadísticas calculadas, los metadatos de las escenas y las imágenes (antes y
cambios detectados), e interpreta los resultados para generar un informe técnico
estructurado (diagnóstico, impacto ambiental, recomendaciones, limitaciones).

La IA NO calcula las hectáreas: eso lo hace analisis.py. La IA interpreta.
Si la clave no está configurada o la API falla, se genera un informe por reglas
marcado explícitamente como "sin IA" para que el sistema no se caiga.
"""
import json
import os

CONTEXTO_CLUSTER = {
    "Gran Córdoba": "área metropolitana con presión inmobiliaria sobre la franja serrana y periurbana; "
                    "riesgos de impermeabilización, escorrentía y crecidas repentinas en cuencas de sierra.",
    "Valle de Punilla": "valle serrano turístico; riesgos de crecidas de ríos y arroyos serranos, "
                        "incendios de interfase urbano-forestal y presión sobre el bosque nativo.",
    "Valle de Calamuchita": "valle serrano turístico; riesgos de incendios de interfase, crecidas y "
                            "presión sobre cuencas de abastecimiento.",
    "Valle de Traslasierra": "valle semiárido al oeste de las sierras; escasez hídrica, erosión y "
                             "avance de loteos sobre monte nativo.",
    "Nodos Agroindustriales": "región pampeana de llanura; pérdida de suelo agrícola de alta productividad, "
                              "anegamiento y ascenso de napas.",
    "Nodos Regionales Norte": "región norte, más árida; erosión, pérdida de monte nativo y vulnerabilidad hídrica.",
}

LIMITACIONES_BASE = (
    "Las cifras son estimaciones obtenidas por clasificación de imágenes Sentinel-2 (10 m) mediante índices "
    "espectrales y umbrales; no son mediciones confirmadas en terreno. Puede haber confusión entre suelo "
    "desnudo/agrícola y superficies construidas, diferencias por estacionalidad y fecha de la escena, y "
    "píxeles excluidos por nubes. Se recomienda validar con relevamiento de campo o cartografía oficial "
    "(por ejemplo IDECOR) antes de tomar decisiones."
)


def _detalle_para_prompt(cambios):
    if not cambios:
        return ""
    zonas = sorted(cambios.get("parcelas", []), key=lambda p: -p["ha"])[:6]
    lineas = [f"  - {p['tipo']}: {p['ha']} ha, a {p['dist_km']} km hacia el {p['dir_nombre']} del centro"
              f" (aprox. {int(p['pct_ex_verde'])} % antes era vegetación)" for p in zonas]
    dirs = [f"{d['nombre']}: {d['ha_urbanizadas']} ha" for d in cambios.get("direcciones", []) if d["ha_urbanizadas"] > 0]
    return ("\n- Zonas de cambio más grandes (detectadas individualmente):\n" + "\n".join(lineas)
            + "\n- Nueva superficie urbanizada por dirección desde el centro: " + ("; ".join(dirs) or "sin datos"))


def _prompt(ciudad, anos, stats, anillos, escenas, hay_imagenes, cambios=None):
    ctx = CONTEXTO_CLUSTER.get(ciudad["cluster"], "")
    ea, eb = escenas
    return f"""Actúa como un especialista en planificación urbana y teledetección de la Provincia de Córdoba, Argentina.
Redacta un informe técnico en español, claro y prudente, sobre el cambio territorial detectado.

DATOS DE LA CIUDAD
- Ciudad: {ciudad['nombre']} (cluster: {ciudad['cluster']}; población aprox.: {ciudad.get('poblacion') or 's/d'} hab.)
- Contexto territorial del cluster (úsalo solo si aplica): {ctx}

DATOS DEL ANÁLISIS (estimados por teledetección, NO medidos en terreno)
- Período: {anos[0]} a {anos[1]}
- Escena inicial: {ea.get('satelite')} del {ea.get('fecha')} (nubosidad {ea.get('nubes')} %)
- Escena final: {eb.get('satelite')} del {eb.get('fecha')} (nubosidad {eb.get('nubes')} %)
- Área analizada válida: {stats['ha_analizadas']} ha ({stats['pct_pixeles_validos']} % del recuadro sin nubes)
- Superficie urbana/construida inicial: {stats['ha_urbanas_inicio']} ha; final: {stats['ha_urbanas_fin']} ha
- Nueva superficie urbanizada estimada: {stats['ha_urbanizadas']} ha
- Vegetación perdida: {stats['ha_verdes_perdidas']} ha; vegetación ganada: {stats['ha_verdes_ganadas']} ha
- Vegetación convertida directamente a urbano: {stats['ha_verde_a_urbano']} ha
- Cobertura vegetal: {stats['pct_verde_inicio']} % -> {stats['pct_verde_fin']} %
- Vegetación y urbano por anillos de 1 km desde el centro: {json.dumps(anillos, ensure_ascii=False)}{_detalle_para_prompt(cambios)}
{"- Se adjuntan 2 imágenes: (1) color natural de la fecha inicial, (2) color natural de la fecha final con los cambios superpuestos (bermellón = nueva superficie urbanizada, púrpura oscuro = vegetación convertida a urbano, amarillo = vegetación perdida, azul = vegetación ganada). Úsalas para describir DÓNDE ocurre el cambio (centro, periferia, hacia qué sector)." if hay_imagenes else ""}

REGLAS
- Usa únicamente los números provistos; no inventes datos ni cifras.
- Habla siempre de valores "estimados" o "posibles"; nunca los presentes como mediciones confirmadas.
- Si la nubosidad o el % de píxeles válidos es alto, adviértelo.
- No des consejos legales ni nombres de normas que no estés seguro que existan.

Responde SOLO con un objeto JSON con exactamente estas claves (texto plano, sin markdown):
{{
  "diagnostico": "Diagnóstico técnico breve del crecimiento y de la pérdida de vegetación (3-5 oraciones).",
  "impacto_ambiental": "Impacto ambiental y territorial probable para este tipo de territorio (riesgo hídrico, impermeabilización, suelo productivo, islas de calor, según corresponda).",
  "recomendaciones": ["Recomendación 1 de planificación", "Recomendación 2", "Recomendación 3"],
  "limitaciones": "Limitaciones específicas de este análisis y qué verificar en terreno."
}}"""


def _a_texto(valor):
    if isinstance(valor, list):
        return "\n".join(f"{i}. {str(x).strip()}" for i, x in enumerate(valor, 1))
    return str(valor).strip()


def _informe_por_reglas(ciudad, anos, stats):
    nuevas, perd = stats["ha_urbanizadas"], stats["ha_verdes_perdidas"]
    dv = round(stats["pct_verde_fin"] - stats["pct_verde_inicio"], 1)
    tendencia = "disminuyó" if dv < 0 else "aumentó"
    return {
        "diagnostico": (
            f"Entre {anos[0]} y {anos[1]} se estiman {nuevas} ha de nueva superficie urbanizada en {ciudad['nombre']} "
            f"y {perd} ha de vegetación perdida. La cobertura vegetal {tendencia} {abs(dv)} puntos porcentuales "
            f"({stats['pct_verde_inicio']} % a {stats['pct_verde_fin']} %)."),
        "impacto_ambiental": (
            "Informe generado SIN inteligencia artificial (plan B por reglas). En general, la pérdida de cobertura "
            "vegetal y el aumento de superficie impermeable incrementan la escorrentía y reducen la infiltración."),
        "recomendaciones": ("1. Verificar en terreno los sectores con mayor cambio.\n"
                            "2. Contrastar con cartografía oficial de uso del suelo.\n"
                            "3. Priorizar la conservación de espacios verdes en las zonas de mayor presión."),
        "limitaciones": LIMITACIONES_BASE,
        "modelo": "reglas (sin IA)",
        "es_fallback": True,
    }


def generar_informe(ciudad, anos, stats, anillos, escenas, imagenes=None, cambios=None):
    """
    ciudad: dict(nombre, cluster, poblacion) | anos: (inicio, fin)
    escenas: (dict(satelite, fecha, nubes), dict(...)) | imagenes: lista de bytes PNG (opcional)
    Siempre devuelve un dict con diagnostico, impacto_ambiental, recomendaciones,
    limitaciones, modelo y es_fallback.
    """
    clave = os.getenv("GEMINI_API_KEY", "")
    modelo = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if not clave:
        return _informe_por_reglas(ciudad, anos, stats)
    try:
        from google import genai
        from google.genai import types

        cliente = genai.Client(api_key=clave)
        contenido = []
        for png in (imagenes or []):
            contenido.append(types.Part.from_bytes(data=png, mime_type="image/png"))
        contenido.append(_prompt(ciudad, anos, stats, anillos, escenas, bool(imagenes), cambios))
        resp = cliente.models.generate_content(
            model=modelo,
            contents=contenido,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3),
        )
        texto = (resp.text or "").replace("```json", "").replace("```", "").strip()
        datos = json.loads(texto)
        return {
            "diagnostico": _a_texto(datos["diagnostico"]),
            "impacto_ambiental": _a_texto(datos["impacto_ambiental"]),
            "recomendaciones": _a_texto(datos["recomendaciones"]),
            "limitaciones": _a_texto(datos.get("limitaciones") or LIMITACIONES_BASE),
            "modelo": modelo,
            "es_fallback": False,
        }
    except Exception:  # clave inválida, cuota, JSON mal formado, red...
        return _informe_por_reglas(ciudad, anos, stats)
