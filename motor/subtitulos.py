# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Subtítulos: el modelo (frases con su tiempo y un estilo), los archivos .ass / .srt / .vtt y la transcripción.

- Las frases viven en la LÍNEA DE TIEMPO del proyecto (segundos desde el principio del montaje), no en la fuente:
  se quemaban sobre el video ya armado, así que no les importa cómo se llegó a él (cortes, velocidad, transiciones).
- La transcripción NO descarga nada: usa el `whisper-cli` y el modelo que ya haya instalados en la computadora (se
  buscan en lugares conocidos). Si no están, el mensaje dice qué falta y la edición a mano de las frases sigue andando.
- Se transcribe el audio de la pista A1 TAL COMO QUEDA en el montaje (con cortes, velocidad, efectos): los tiempos que
  devuelve whisper ya son los de la línea de tiempo.
- Este módulo no importa al exportador al cargarse (el modelo lo importa a él): la transcripción lo trae adentro.
"""

import glob
import json
import math
import os
import re
import shutil
import subprocess
import threading
import tempfile

from motor import efectos as _fx

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

TEXTO_MAX = 400
FRASES_MAX = 3000
IDIOMAS = [("es", "Español"), ("en", "Inglés"), ("pt", "Portugués"), ("fr", "Francés"), ("it", "Italiano"), ("de", "Alemán"), ("auto", "Detectar solo")]
LETRAS = (10, 80)                                  # máximo de letras por frase al transcribir

# nombre de la familia que usa el .ass y si va en negrita, por cada letra del catalogo de efectos
FAMILIAS = {"segoeui": ("Segoe UI", 0), "segoeuib": ("Segoe UI", 1), "arial": ("Arial", 0), "arialbd": ("Arial", 1), "georgia": ("Georgia", 0),
            "impact": ("Impact", 0), "times": ("Times New Roman", 0), "verdana": ("Verdana", 0)}

ESTILO = [
    {"id": "fuente", "nombre": "Letra", "tipo": "opcion", "defecto": "segoeuib", "opciones": [{"valor": k, "nombre": v[0]} for k, v in _fx.FUENTES.items()]},
    {"id": "tamano", "nombre": "Tamaño (del alto)", "tipo": "num", "min": 3, "max": 15, "paso": 0.5, "defecto": 6, "unidad": "%"},
    {"id": "color", "nombre": "Color", "tipo": "opcion", "defecto": "blanco", "opciones": [{"valor": k, "nombre": k.capitalize()} for k in _fx.COLORES_TEXTO]},
    {"id": "contorno", "nombre": "Con contorno negro", "tipo": "bool", "defecto": True},
    {"id": "caja", "nombre": "Con fondo oscuro", "tipo": "bool", "defecto": False},
    {"id": "mayusculas", "nombre": "TODO EN MAYÚSCULAS", "tipo": "bool", "defecto": False},
    {"id": "posicion", "nombre": "Posición", "tipo": "opcion", "defecto": "abajo",
     "opciones": [{"valor": "abajo", "nombre": "Abajo"}, {"valor": "centro", "nombre": "En el centro"}, {"valor": "arriba", "nombre": "Arriba"}]},
    {"id": "margen", "nombre": "Distancia al borde", "tipo": "num", "min": 0, "max": 30, "paso": 1, "defecto": 8, "unidad": "%"},
    {"id": "karaoke", "nombre": "Resaltar la palabra que se dice", "tipo": "bool", "defecto": False},
    {"id": "resaltado", "nombre": "Color de la palabra resaltada", "tipo": "opcion", "defecto": "amarillo",
     "opciones": [{"valor": k, "nombre": k.capitalize()} for k in _fx.COLORES_TEXTO]},
]

PALABRAS_MAX = 40000
PALABRA_MAX_LETRAS = 60


class ErrorSubtitulo(ValueError):
    """Algo que no se puede hacer con los subtítulos; el mensaje se le muestra a la persona."""


def catalogo():
    return {"estilo": ESTILO, "idiomas": [{"valor": k, "nombre": n} for k, n in IDIOMAS], "letras": {"min": LETRAS[0], "max": LETRAS[1], "defecto": 32}}


def estilo_por_defecto():
    return {s["id"]: (float(s["defecto"]) if s["tipo"] == "num" else s["defecto"]) for s in ESTILO}      # numeros siempre decimales: igual antes y despues de guardar


def _coma(x):
    return ("%g" % x).replace(".", ",")


def limpiar_estilo(nuevos, base=None):
    """Valida los valores nuevos del estilo y los mezcla con los de `base` (o los de fábrica). Devuelve el dict completo."""
    if not isinstance(nuevos, dict):
        raise ErrorSubtitulo("El estilo tiene que ser un conjunto de ajustes.")
    out = dict(base) if base else estilo_por_defecto()
    specs = {s["id"]: s for s in ESTILO}
    for k, v in nuevos.items():
        s = specs.get(k)
        if s is None:
            raise ErrorSubtitulo("Ese ajuste no existe: %s." % k)
        if s["tipo"] == "bool":
            if not isinstance(v, bool):
                raise ErrorSubtitulo("«%s» es sí o no." % s["nombre"])
            out[k] = v
        elif s["tipo"] == "opcion":
            if not isinstance(v, str) or v not in [o["valor"] for o in s["opciones"]]:
                raise ErrorSubtitulo("«%s» no tiene esa opción." % s["nombre"])
            out[k] = v
        else:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ErrorSubtitulo("«%s» tiene que ser un número." % s["nombre"])
            if not s["min"] <= v <= s["max"]:
                raise ErrorSubtitulo("«%s» va de %s a %s." % (s["nombre"], _coma(s["min"]), _coma(s["max"])))
            out[k] = float(v)
    return out


def limpiar_frase(inicio, fin, texto, duracion=None):
    """(inicio, fin, texto) validados y redondeados al milisegundo."""
    for nombre, v in (("El inicio", inicio), ("El final", fin)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ErrorSubtitulo("%s tiene que ser un número." % nombre)
    if not isinstance(texto, str):
        raise ErrorSubtitulo("El texto de la frase tiene que ser un texto.")
    texto = texto.strip()
    if not texto:
        raise ErrorSubtitulo("La frase no puede estar vacía.")
    if len(texto) > TEXTO_MAX or "\x00" in texto:
        raise ErrorSubtitulo("Una frase puede tener hasta %d letras." % TEXTO_MAX)
    inicio, fin = round(float(inicio), 3), round(float(fin), 3)
    if inicio < 0:
        raise ErrorSubtitulo("La frase no puede empezar antes del principio.")
    if fin - inicio < 0.1:
        raise ErrorSubtitulo("La frase tiene que durar al menos una décima de segundo.")
    if duracion is not None and inicio > duracion + 1e-3:
        raise ErrorSubtitulo("La frase empieza después del final del video.")
    return inicio, fin, texto


# ------------------------------------------------------------------ archivos de subtitulos

def _hms(t, sep, cs=False):
    t = max(0.0, float(t))
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    if cs:
        return "%d:%02d:%02d.%02d" % (h, m, s, ms // 10)
    return "%02d:%02d:%02d%s%03d" % (h, m, s, sep, ms)


def _visibles(frases, duracion):
    """Las frases recortadas al largo del video (una que queda fuera no se escribe)."""
    out = []
    for f in sorted(frases, key=lambda f: (f["inicio"], f["fin"])):
        a, b = f["inicio"], min(f["fin"], duracion) if duracion else f["fin"]
        if b - a >= 0.04:
            out.append((a, b, f["texto"]))
    return out


def a_srt(frases, duracion=None):
    bloques = []
    for i, (a, b, t) in enumerate(_visibles(frases, duracion), 1):
        bloques.append("%d\n%s --> %s\n%s\n" % (i, _hms(a, ","), _hms(b, ","), t.replace("\r", "")))
    return "\n".join(bloques)


def a_vtt(frases, duracion=None):
    bloques = ["WEBVTT\n"]
    for a, b, t in _visibles(frases, duracion):
        bloques.append("%s --> %s\n%s\n" % (_hms(a, "."), _hms(b, "."), t.replace("\r", "")))
    return "\n".join(bloques)


_NOMBRES_COLOR = {"white": (255, 255, 255), "yellow": (255, 255, 0), "black": (0, 0, 0)}


def _rgb(nombre):
    if nombre in _NOMBRES_COLOR:
        return _NOMBRES_COLOR[nombre]
    n = int(nombre, 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def _ass_color(rgb, alfa=0):
    return "&H%02X%02X%02X%02X" % (alfa, rgb[2], rgb[1], rgb[0])


def _ass_texto(t, mayusculas):
    t = t.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\r", "")
    t = "\\N".join(x.strip() for x in t.split("\n") if x.strip())
    return t.upper() if mayusculas else t


def _tiempos_de_palabras(f, por_id):
    """Las palabras de una frase con su tiempo, para resaltar la que se dice: [(texto, inicio, fin)], sin huecos entre una y otra
    (cada palabra dura hasta que empieza la siguiente; la primera arranca con la frase y la ultima termina con ella).
    Si la frase conserva sus palabras medidas (y no se le cambio el texto), se usan esos tiempos; si no, el tiempo de la frase se
    reparte entre sus palabras en proporcion a las letras de cada una."""
    ids = f.get("palabras") or []
    medidas = [por_id.get(i) for i in ids] if por_id else []
    if medidas and all(medidas) and " ".join(w["texto"] for w in medidas).split() == f["texto"].split():
        piezas = [(w["texto"], float(w["inicio"])) for w in medidas]
    else:
        palabras = f["texto"].split()
        if not palabras:
            return []
        pesos = [max(1, len(x)) for x in palabras]
        total, acumulado, piezas = float(sum(pesos)), 0.0, []
        for x, peso in zip(palabras, pesos):
            piezas.append((x, f["inicio"] + (f["fin"] - f["inicio"]) * acumulado / total))
            acumulado += peso
    out = []
    for i, (texto, ini) in enumerate(piezas):
        a = f["inicio"] if i == 0 else max(ini, out[-1][1] + 0.001)
        b = f["fin"] if i == len(piezas) - 1 else max(piezas[i + 1][1], a + 0.001)
        out.append((texto, min(a, f["fin"] - 0.001), min(b, f["fin"])))
    return out


def a_ass(frases, estilo, ancho, alto, duracion=None, palabras=None):
    """Un .ass listo para `ass=` de ffmpeg, en la resolución exacta de la salida (1 unidad = 1 píxel).

    Con el estilo «karaoke», cada frase se escribe una vez por palabra, con la que se dice del color de resaltado: el texto no se mueve
    y la palabra va cambiando de color a medida que se dice. `palabras` son las palabras medidas del proyecto (opcional)."""
    est = limpiar_estilo(estilo)
    por_id = {w["id"]: w for w in palabras} if palabras else {}
    familia, negrita = FAMILIAS[est["fuente"]]
    tam = max(8, int(round(alto * est["tamano"] / 100.0)))
    color = _rgb(_fx.COLORES_TEXTO[est["color"]])
    if est["caja"]:
        borde_estilo, borde, contorno_color, sombra = 3, max(2, tam // 4), _ass_color((0, 0, 0), 0x73), 0
    else:
        borde_estilo, borde, contorno_color, sombra = 1, (max(1, round(tam / 14.0)) if est["contorno"] else 0), _ass_color((0, 0, 0)), 0
    alinear = {"abajo": 2, "centro": 5, "arriba": 8}[est["posicion"]]
    margen_v = int(round(alto * est["margen"] / 100.0))
    margen_h = int(round(ancho * 0.05))
    lineas = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % ancho, "PlayResY: %d" % alto, "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
              "[V4+ Styles]",
              "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
              "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
              "Style: Default,%s,%d,%s,%s,%s,%s,%d,0,0,0,100,100,0,0,%d,%d,%d,%d,%d,%d,%d,1" % (
                  familia, tam, _ass_color(color), _ass_color(color), contorno_color, _ass_color((0, 0, 0), 0x80), -1 if negrita else 0,
                  borde_estilo, borde, sombra, alinear, margen_h, margen_h, margen_v),
              "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    if not est["karaoke"]:
        for a, b, t in _visibles(frases, duracion):
            lineas.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (_hms(a, ".", cs=True), _hms(b, ".", cs=True), _ass_texto(t, est["mayusculas"])))
        return "\n".join(lineas) + "\n"
    rgb_r = _rgb(_fx.COLORES_TEXTO[est["resaltado"]])
    resalte = "&H%02X%02X%02X" % (rgb_r[2], rgb_r[1], rgb_r[0])          # c lleva solo azul, verde y rojo (sin transparencia)
    base = "&H%02X%02X%02X" % (color[2], color[1], color[0])
    for f in sorted(frases, key=lambda f: (f["inicio"], f["fin"])):
        piezas = _tiempos_de_palabras(f, por_id)
        limpias = [_ass_texto(x[0], est["mayusculas"]).replace("\\N", " ") for x in piezas]
        for k, (_, a, b) in enumerate(piezas):
            b = min(b, duracion) if duracion else b
            if b - a < 0.02 or not limpias[k]:
                continue
            texto = " ".join(("{\\1c%s&}%s{\\1c%s&}" % (resalte, w, base)) if j == k else w for j, w in enumerate(limpias))
            lineas.append("Dialogue: 0,%s,%s,Default,,0,0,0,,%s" % (_hms(a, ".", cs=True), _hms(b, ".", cs=True), texto))
    return "\n".join(lineas) + "\n"


# ------------------------------------------------------------------ transcripcion (whisper)

_ALUCINACIONES = ("subtítulos realizados por", "subtitulos realizados por", "amara.org", "gracias por ver", "suscríbete", "suscribete",
                  "thanks for watching", "subtitles by", "sous-titres", "legendas pela comunidade")
_PROGRESO = re.compile(r"progress\s*=\s*(\d+)\s*%")


def buscar_whisper():
    """Ruta del whisper-cli instalado, o None."""
    ruta = shutil.which("whisper-cli")
    if ruta and os.path.isabs(ruta):
        return ruta
    local = os.environ.get("LOCALAPPDATA", "")
    for c in (os.path.join(local, "Programs", "whisper.cpp", "whisper-cli.exe"), os.path.expanduser(os.path.join("~", "whisper.cpp", "build", "bin", "whisper-cli.exe"))):
        if os.path.isfile(c):
            return c
    return None


def buscar_modelo():
    """Ruta de un modelo ggml de whisper ya instalado (el más grande y bueno primero), o None. Nunca descarga nada."""
    env = os.environ.get("WHISPER_MODEL")
    if env and os.path.isfile(os.path.expanduser(env)):
        return os.path.expanduser(env)
    carpetas = [os.path.expanduser(os.path.join("~", "whisper-modelos")), os.path.expanduser(os.path.join("~", "whisper.cpp", "models"))]
    orden = ("large-v3-turbo", "large-v3", "medium", "small", "base", "tiny")
    halladas = []
    for c in carpetas:
        halladas += glob.glob(os.path.join(c, "ggml-*.bin"))
    if not halladas:
        return None

    def puesto(r):
        n = os.path.basename(r).lower()
        for i, clave in enumerate(orden):
            if clave in n:
                return i
        return len(orden)
    return sorted(halladas, key=puesto)[0]


def estado_transcripcion():
    """Qué hace falta para transcribir, dicho para una persona."""
    w, m = buscar_whisper(), buscar_modelo()
    faltan = []
    if not w:
        faltan.append("el programa whisper-cli (whisper.cpp)")
    if not m:
        faltan.append("un modelo de whisper (un archivo ggml-*.bin)")
    return {"disponible": not faltan, "whisper": w or "", "modelo": os.path.basename(m) if m else "",
            "motivo": ("" if not faltan else "Para transcribir hace falta tener instalado " + " y ".join(faltan) + ". Moviola no descarga nada mientras se usa: lo instala su "
                       "instalador (Instalar-Moviola.bat). Mientras tanto podés escribir las frases a mano.")}


def _pistas_de_voz(p):
    a1 = next((t for t in p.pistas if t["id"] == "A1"), None)
    return a1 if a1 and a1["clips"] and not a1.get("silenciada") else None


def _filtrar(segmentos, p, a1, duracion):
    """Saca lo que whisper inventa sobre los silencios y lo que cae donde no hay voz. Cada segmento es (inicio, fin, texto) o
    (inicio, fin, texto, indice); las frases que quedan llevan el `indice` del segmento del que salieron (clave «seg»), si lo tenian."""
    voz = [(c["inicio"], p.fin(c)) for c in a1["clips"]]
    out = []
    for s in segmentos:
        a, b, t = s[0], s[1], s[2]
        t = t.strip()
        if not t or any(x in t.lower() for x in _ALUCINACIONES):
            continue
        if not any(min(b, y) - max(a, x) > 0.05 for x, y in voz):
            continue
        a, b = max(0.0, a), min(b, duracion)
        if b - a < 0.1:
            continue
        f = {"inicio": round(a, 3), "fin": round(b, 3), "texto": t[:TEXTO_MAX]}
        if len(s) > 3:
            f["seg"] = s[3]
        out.append(f)
    return out


# ------------------------------------------------------------------ palabras (tiempos por palabra)

_ESPECIAL = re.compile(r"^\[[A-Za-z_0-9 ]+\]$")
_PRESETS_DTW = ("tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large.v1", "large.v2", "large.v3", "large.v3.turbo")


def preset_dtw(ruta_modelo):
    """El nombre con que whisper.cpp conoce a este modelo para medir el tiempo de cada palabra (--dtw), o None si no se sabe cuál es.
    Sale del nombre del archivo: ggml-large-v3-turbo-q5_0.bin -> large.v3.turbo."""
    n = os.path.basename(ruta_modelo or "").lower()
    if n.startswith("ggml-"):
        n = n[5:]
    if n.endswith(".bin"):
        n = n[:-4]
    n = re.sub(r"-q\d(_\d)?(_k(_[sm])?)?$", "", n)
    n = n.replace("-", ".")
    n = n.replace("large.v3.turbo", "large.v3.turbo")
    return n if n in _PRESETS_DTW else None


def _a_texto(s):
    """El texto de un archivo de whisper que se leyó byte a byte (latin-1): vuelve a ser UTF-8 (una letra con tilde puede venir partida
    en dos tokens, y cada token por separado no es UTF-8 válido)."""
    try:
        return s.encode("latin-1").decode("utf-8", "replace")
    except UnicodeEncodeError:
        return s


def _es_puntuacion(texto):
    return not any(c.isalnum() for c in texto)


def palabras_de_segmento(seg):
    """Las palabras de un segmento del JSON completo de whisper: [{texto, inicio, fin, dtw}] (segundos del audio).
    Los tokens se unen a nivel de BYTES (una tilde puede quedar partida entre dos); la puntuación se pega a la palabra de adelante sin
    cambiarle el tiempo. Con DTW, `t_dtw` de un token es el instante en que TERMINA de decirse: `fin` es el de su último token e `inicio`
    el del token anterior (aproximado: el ajuste fino lo hace `afinar_palabras` con el sonido). Sin DTW se usan los tiempos aproximados
    de cada token."""
    palabras, actual, previo, abre = [], None, None, b""
    for t in seg.get("tokens", []):
        crudo = t["text"].encode("latin-1", "replace") if isinstance(t.get("text"), str) else b""
        visible = _a_texto(t["text"]) if isinstance(t.get("text"), str) else ""
        dtw = t.get("t_dtw", -1)
        hay_dtw = isinstance(dtw, (int, float)) and dtw >= 0
        if not visible.strip() or _ESPECIAL.match(visible.strip()):
            continue
        empieza = crudo.startswith(b" ")
        sola = _es_puntuacion(visible)
        ini = previo if (hay_dtw and previo is not None) else t["offsets"]["from"] / 1000.0
        fin = (dtw / 100.0) if hay_dtw else t["offsets"]["to"] / 1000.0
        if empieza and sola:
            abre += crudo.strip(b" ")                    # «¿» o «¡»: se pega a la palabra que viene
            continue
        if actual is None or (empieza and not sola) or (abre and not sola):
            if sola and actual is None:
                continue                                  # puntuacion suelta al principio: no es una palabra
            actual = {"bytes": abre + crudo.lstrip(b" "), "inicio": ini, "fin": max(ini, fin), "dtw": hay_dtw}
            abre = b""
            palabras.append(actual)
        else:
            actual["bytes"] += crudo
            if not sola:
                actual["fin"] = max(actual["fin"], fin)
        if hay_dtw:
            previo = dtw / 100.0
    out = []
    for w in palabras:
        texto = w["bytes"].decode("utf-8", "replace").strip()
        if not texto or not any(c.isalnum() for c in texto):
            continue
        partes = texto.split()                         # un token con espacios adentro serian dos palabras
        for k, parte in enumerate(partes):
            a = w["inicio"] + (w["fin"] - w["inicio"]) * k / len(partes)
            b = w["inicio"] + (w["fin"] - w["inicio"]) * (k + 1) / len(partes)
            out.append({"texto": parte[:PALABRA_MAX_LETRAS], "inicio": a, "fin": b, "dtw": w["dtw"]})
    return out


def reparar_tiempos(ws, desde, hasta, minimo=0.04):
    """Deja los finales de las palabras de UNA frase en orden creciente y dentro de la frase. Los tiempos de whisper a veces se
    amontonan (varias palabras con el mismo final) o salen de la frase: esa tanda se reparte entre el último final bueno y el siguiente
    en proporción a las letras de cada palabra. Devuelve cuántas palabras hubo que repartir."""
    m = len(ws)
    fin = [min(max(w["fin"], desde), hasta) for w in ws]
    for i in range(1, m):
        fin[i] = max(fin[i], fin[i - 1])
    reparadas, previo, i = 0, desde, 0
    while i < m:
        if fin[i] - previo >= minimo:
            previo = fin[i]
            i += 1
            continue
        j = i
        while j < m and fin[j] - (fin[j - 1] if j > i else previo) < minimo:
            j += 1
        tope = fin[j] if j < m else hasta
        tope = max(tope, previo + 0.06 * (j - i + (1 if j >= m else 0)))
        pesos = [max(1, len(ws[k]["texto"])) for k in range(i, j)]
        acumulado = 0.0
        for k, peso in zip(range(i, j), pesos):
            acumulado += peso
            fin[k] = previo + (tope - previo) * acumulado / sum(pesos)
        reparadas += j - i
        previo = fin[j - 1]
        i = j
    for w, f in zip(ws, fin):
        w["fin"] = f
        w["inicio"] = min(w["inicio"], f)
    return reparadas


def _repartir_aproximadas(palabras):
    """Sin DTW whisper deja varias palabras con el MISMO tiempo (el del principio de la frase). Cada tanda de palabras con el mismo
    inicio se reparte hasta que empieza la siguiente, en proporción a sus letras."""
    i = 0
    while i < len(palabras):
        j = i + 1
        while j < len(palabras) and palabras[j]["inicio"] <= palabras[i]["inicio"] + 0.005:
            j += 1
        if j - i > 1:
            tope = palabras[j]["inicio"] if j < len(palabras) else max(w["fin"] for w in palabras[i:j])
            tope = max(tope, palabras[i]["inicio"] + 0.1 * (j - i))
            pesos = [max(1, len(w["texto"])) for w in palabras[i:j]]
            acum = 0.0
            for w, peso in zip(palabras[i:j], pesos):
                w["inicio"] = palabras[i]["inicio"] + (tope - palabras[i]["inicio"]) * acum / sum(pesos)
                acum += peso
        i = j
    return palabras


def envolvente(wav, paso=0.01):
    """Cuánto suena cada centésima de segundo de un WAV de 16 bits mono: lista de decibeles (con piso en -90). Sirve para cortar entre
    palabras en el lugar donde menos suena."""
    import array
    import math
    import wave
    from operator import mul
    with wave.open(wav, "rb") as w:
        sr, ancho, canales = w.getframerate(), w.getsampwidth(), w.getnchannels()
        crudo = w.readframes(w.getnframes())
    if ancho != 2 or canales != 1:
        raise ErrorSubtitulo("El audio para medir las palabras tiene que ser de 16 bits y mono.")
    m = array.array("h")
    m.frombytes(crudo[: len(crudo) // 2 * 2])
    n = max(1, int(round(sr * paso)))
    out = []
    for i in range(0, len(m) - n + 1, n):
        c = m[i:i + n]
        e = sum(map(mul, c, c)) / float(n)
        out.append(10.0 * math.log10(e / (32768.0 ** 2) + 1e-9))
    return out


def _tramos_con_voz(env, umbral, paso):
    """Los tramos del audio donde suena algo: [(inicio, fin)] en segundos. Los huecos de menos de 40 ms no cuentan (una oclusiva)."""
    tramos, desde, ultimo = [], None, None
    for k, e in enumerate(env):
        if e >= umbral:
            if desde is None:
                desde = k
            ultimo = k
        elif desde is not None and k - ultimo > 4:
            tramos.append((desde * paso, (ultimo + 1) * paso))
            desde = None
    if desde is not None:
        tramos.append((desde * paso, (ultimo + 1) * paso))
    return tramos


def afinar_palabras(palabras, env, duracion, paso=0.01, ventana=0.35):
    """Deja a cada palabra con `inicio`, `fin`, `voz` y `habla`.

    Whisper dice DÓNDE TERMINA cada palabra (aproximado). Acá se busca en el sonido el silencio que hay cerca de ese final (entre dos
    tramos con voz) y se corta justo en el MEDIO: así, al sacar una palabra, la pausa natural queda partida a la mitad entre las vecinas, ni
    se le come nada a la de al lado ni queda un silencio doble. Sin silencio cerca (se habla de corrido) se corta donde menos suena.
    - `inicio` y `fin` son esos cortes: cada palabra va de un corte al siguiente (las palabras seguidas no dejan huecos entre sí).
    - `voz` es cuando empieza a sonar de verdad y `habla` cuando deja de sonar: lo que hay entre `habla` y la `voz` de la que sigue es
      una pausa, y se puede acortar sin tocar las palabras."""
    if not palabras:
        return []
    n = len(env)
    orden = sorted(env)
    piso = orden[int(len(orden) * 0.10)] if orden else -90.0
    pico = orden[int(len(orden) * 0.90)] if orden else -20.0
    umbral = piso + max(6.0, 0.25 * (pico - piso))
    tramos = _tramos_con_voz(env, umbral, paso) if n else []
    suave = [(env[max(0, k - 1)] + env[k] + env[min(n - 1, k + 1)]) / 3.0 for k in range(n)] if n else []
    m = len(palabras)
    corte, habla, voz = [0.0] * m, [0.0] * m, [0.0] * m
    # un corte antes de cada palabra menos la primera
    for i in range(1, m):
        e = palabras[i - 1]["fin"]
        mejor = None
        for g0, g1 in zip(tramos, tramos[1:]):
            h0, h1 = g0[1], g1[0]                        # el silencio entre dos tramos con voz
            if not (e - ventana <= h0 <= e + ventana or h0 <= e <= h1):
                continue                                 # su comienzo no esta cerca del final de la palabra
            puntaje = abs(h0 - e)
            if mejor is None or puntaje < mejor[0]:
                mejor = (puntaje, h0, h1)
        if mejor is not None:
            largo = mejor[2] - mejor[1]
            # una pausa corta se parte al medio; en una larga el corte queda cerca de la palabra que termina (la pausa es de la que sigue)
            corte[i], habla[i - 1], voz[i] = (mejor[1] + min(largo / 2.0, 0.35)), mejor[1], mejor[2]
        elif n:
            k0, k1 = max(0, int(round((e - 0.12) / paso))), min(n - 1, int(round((e + 0.12) / paso)))
            k = min(range(k0, max(k0, k1) + 1), key=lambda j: (round(suave[j], 1), abs(j * paso - e))) if k1 >= k0 else int(round(e / paso))
            corte[i] = habla[i - 1] = voz[i] = k * paso
        else:
            corte[i] = habla[i - 1] = voz[i] = e
    # la primera empieza donde empieza a sonar; la ultima, donde deja de sonar
    primero = palabras[0]["inicio"]
    arranque = next((a for a, b in tramos if b > primero - 0.1), None)
    voz[0] = arranque if arranque is not None else primero
    corte[0] = max(0.0, voz[0] - 0.03)
    ultimo = palabras[-1]["fin"]
    cierre = next((b for a, b in tramos if b >= ultimo - 0.05 and a <= ultimo + 0.3), None)
    habla[-1] = min(duracion or 1e9, cierre if cierre is not None else ultimo)
    # en orden y sin choques
    for i in range(m):
        if i and corte[i] < corte[i - 1] + 0.03:
            corte[i] = corte[i - 1] + 0.03
        if voz[i] < corte[i]:
            voz[i] = corte[i]
    out = []
    for i, w in enumerate(palabras):
        a = corte[i]
        f = corte[i + 1] if i + 1 < m else min(duracion or 1e9, habla[-1] + 0.03)
        f = max(f, a + 0.03)
        f = min(f, duracion) if duracion else f
        a = min(a, f - 0.02)
        h = min(max(habla[i], voz[i] + 0.02), f)
        out.append({"texto": w["texto"], "inicio": round(a, 3), "fin": round(f, 3), "voz": round(min(voz[i], h), 3), "habla": round(h, 3)})
    return out


def _leer_json(ruta):
    with open(ruta, "rb") as f:
        return json.loads(f.read().decode("latin-1"))


def _correr_whisper(cmd, cancelar, aviso, desde, hasta):
    """Corre whisper-cli y devuelve (código de salida, últimas líneas de error); avisa el avance entre `desde` y `hasta`."""
    from motor import proxy as _proxy
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
    ultimas = []
    terminado = threading.Event()

    def vigilar():
        # whisper puede pasar muchos segundos sin escribir nada: cancelar (o cerrar el programa) no puede esperar a la proxima linea
        while not terminado.is_set():
            if cancelar.wait(0.2):
                if proc.poll() is None:
                    proc.kill()
                return

    if cancelar is not None:
        threading.Thread(target=vigilar, daemon=True).start()
    try:
        for linea in proc.stderr:
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                raise _proxy.Cancelado()
            m = _PROGRESO.search(linea)
            if m:
                aviso(desde + (hasta - desde) * int(m.group(1)) / 100.0)
            else:
                ultimas.append(linea.strip())
        proc.wait()
        if cancelar is not None and cancelar.is_set():
            raise _proxy.Cancelado()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        terminado.set()
    return proc.returncode, ultimas


def transcribir_completo(p, idioma="es", max_letras=32, cancelar=None, avisar=None):
    """Transcribe el audio de A1 del montaje. Devuelve {"frases": [{inicio, fin, texto, palabras: [índices]}], "palabras": [{texto, inicio, fin,
    habla}]}: las frases son los renglones de subtítulo y las palabras tienen su propio tiempo (para editar por texto y resaltar la que se dice).
    Todo en tiempos de la línea de tiempo."""
    from motor import exportar as _ex
    from motor import proxy as _proxy
    from motor.proyecto import Proyecto

    if idioma not in [k for k, _ in IDIOMAS]:
        raise ErrorSubtitulo("Ese idioma no está en la lista.")
    if isinstance(max_letras, bool) or not isinstance(max_letras, (int, float)) or not LETRAS[0] <= max_letras <= LETRAS[1]:
        raise ErrorSubtitulo("Las letras por frase van de %d a %d." % LETRAS)
    est = estado_transcripcion()
    if not est["disponible"]:
        raise ErrorSubtitulo(est["motivo"])
    a1 = _pistas_de_voz(p)
    if a1 is None:
        raise ErrorSubtitulo("No hay audio para transcribir (la pista A1 está vacía o silenciada).")
    duracion = p.duracion()

    def aviso(f):
        if avisar:
            avisar(min(0.999, max(0.0, f)))

    carpeta = tempfile.mkdtemp(prefix="moviola-voz-")
    try:
        copia = Proyecto()
        copia.fuentes = dict(p.fuentes)
        import copy as _copy
        copia.pistas = [_copy.deepcopy(a1)]
        r = _ex.exportar(copia, carpeta, "voz", formato="wav", al_progresar=lambda f: aviso(f * 0.1), cancelar=cancelar)
        wav = os.path.join(carpeta, "voz16.wav")
        subprocess.run([_proxy._ffmpeg(), "-v", "error", "-y", "-nostdin", "-i", r["archivo"], "-ar", "16000", "-ac", "1", wav],
                       check=True, creationflags=_SIN_VENTANA)
        if cancelar is not None and cancelar.is_set():
            raise _proxy.Cancelado()
        modelo = buscar_modelo()
        hilos = max(2, min(8, (os.cpu_count() or 4) // 2))
        base = os.path.join(carpeta, "salida")
        comun = [buscar_whisper(), "-m", modelo, "-l", idioma, "-f", wav, "-ojf", "-ml", str(int(max_letras)), "-sow", "-np", "-pp", "-t", str(hilos), "-of", base]
        dtw = preset_dtw(modelo)
        codigo, ultimas = 1, []
        if dtw:
            # DTW mide el tiempo de cada palabra mucho mejor que lo normal, pero necesita apagar la atencion rapida (flash attention)
            codigo, ultimas = _correr_whisper(comun + ["-dtw", dtw, "-nfa"], cancelar, aviso, 0.1, 0.95)
            if codigo != 0 or not os.path.isfile(base + ".json"):
                dtw = None
        if not dtw:
            codigo, ultimas = _correr_whisper(comun, cancelar, aviso, 0.1, 0.95)
        if codigo != 0 or not os.path.isfile(base + ".json"):
            raise ErrorSubtitulo("No pude transcribir el audio (whisper terminó con error). %s" % (ultimas[-1][:120] if ultimas else ""))
        datos = _leer_json(base + ".json")
        segmentos, por_segmento = [], []
        for i, s in enumerate(datos.get("transcription", [])):
            segmentos.append((s["offsets"]["from"] / 1000.0, s["offsets"]["to"] / 1000.0, _a_texto(s["text"]), i))
            por_segmento.append(palabras_de_segmento(s))
        frases = _filtrar(segmentos, p, a1, duracion)
        # las palabras de las frases que quedaron, en orden, y a cada frase los indices de las suyas
        crudas, dueno, repartidas = [], [], 0
        for k, f in enumerate(frases):
            ws = por_segmento[f["seg"]]
            if not any(w["dtw"] for w in ws):
                ws = _repartir_aproximadas(ws)
            if ws:
                repartidas += reparar_tiempos(ws, ws[0]["inicio"], max(w["fin"] for w in ws) + 1.0)
            for w in ws:
                crudas.append(w)
                dueno.append(k)
        try:
            env = envolvente(wav)
        except (OSError, ErrorSubtitulo, EOFError):
            env = []
        for w in crudas:
            w["inicio"] = max(0.0, min(w["inicio"], max(0.0, duracion - 0.05)))
        palabras = afinar_palabras(crudas, env, duracion)
        # una palabra que quedo fuera del video (o sin duracion) no sirve
        validas = [i for i, w in enumerate(palabras) if w["fin"] - w["inicio"] >= 0.02 and w["inicio"] < duracion]
        palabras = [palabras[i] for i in validas]
        dueno = [dueno[i] for i in validas]
        for f in frases:
            f.pop("seg", None)
            f["palabras"] = []
        for i, k in enumerate(dueno):
            frases[k]["palabras"].append(i)
        for f in frases:
            if not f["palabras"]:
                f.pop("palabras")
        # los renglones se muestran cuando suenan sus palabras (los tiempos de whisper por segmento no siempre coinciden con los de cada palabra)
        previo_fin = 0.0
        for f in frases:
            if f.get("palabras"):
                ws = [palabras[i] for i in f["palabras"]]
                a = max(previo_fin, ws[0]["voz"] - 0.05)
                b = min(duracion, ws[-1]["habla"] + 0.15)
                if b - a >= 0.1:
                    f["inicio"], f["fin"] = round(a, 3), round(b, 3)
            previo_fin = f["fin"]
        for k in range(len(frases) - 1):
            frases[k]["fin"] = min(frases[k]["fin"], frases[k + 1]["inicio"]) if frases[k + 1]["inicio"] - frases[k]["inicio"] >= 0.1 else frases[k]["fin"]
        aviso(0.999)
        return {"frases": frases, "palabras": palabras, "dtw": bool(dtw), "repartidas": repartidas}
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def transcribir(p, idioma="es", max_letras=32, cancelar=None, avisar=None):
    """Transcribe el audio de A1 del montaje. Devuelve la lista de frases [{inicio, fin, texto}] en tiempos de la línea de tiempo."""
    frases = transcribir_completo(p, idioma, max_letras, cancelar, avisar)["frases"]
    for f in frases:
        f.pop("palabras", None)
    return frases
