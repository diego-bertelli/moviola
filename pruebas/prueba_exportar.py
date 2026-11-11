# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del exportador (motor/exportar.py), verificada con DATOS: nada de "se ve bien".

Uso:  python -I pruebas/prueba_exportar.py

Las fuentes sinteticas llevan el numero de cada cuadro escrito como un codigo de barras de 12 bits
en el centro, y un tono de audio que sube 50 Hz cada segundo. Asi se puede comprobar, cuadro por
cuadro y segundo por segundo, que lo exportado es EXACTAMENTE lo que el proyecto dice.
Los videos del Escritorio de Diego son opcionales.
"""

import hashlib
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from array import array

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")

import av  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402

from motor import exportar  # noqa: E402
from motor.proyecto import Proyecto  # noqa: E402
from motor.video import Video  # noqa: E402

TMP = tempfile.mkdtemp(prefix="prueba-exportar-")
ESCRITORIO = os.environ.get("MOVIOLA_VIDEOS_REALES", "")   # carpeta con dos videos reales (uno VFR y un MPEG-PS); sin ella esas partes se saltean
VFR = os.path.join(ESCRITORIO, "real-vfr.mp4")
MPG = os.path.join(ESCRITORIO, "real-mpeg2.mpg")
fallos = []

BLOQUE = 16                                      # cada bit del codigo de barras es un cuadrado de 16x16


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


# ----------------------------------------------------------------- fuentes

def crear_fuente(ruta, dur=12, w=640, h=360, fps=30, tono=True):
    # el codigo se dibuja siempre en el centro de la imagen
    cx0, cy0 = (w - 12 * BLOQUE) // 2, (h - BLOQUE) // 2
    barra = "if(between(X,%d,%d)*between(Y,%d,%d),255*mod(floor(N/pow(2,floor((X-%d)/%d))),2),%%s(X,Y))" % (
        cx0, cx0 + 12 * BLOQUE - 1, cy0, cy0 + BLOQUE - 1, cx0, BLOQUE)
    vf = "testsrc2=s=%dx%d:r=%d:d=%d,format=gbrp,geq=r='%s':g='%s':b='%s',format=yuv420p" % (
        w, h, fps, dur, barra % "r", barra % "g", barra % "b")
    args = ["-f", "lavfi", "-i", vf]
    if tono:
        args += ["-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*(400+50*floor(t))*t)':s=48000:d=%d:c=mono" % dur]
    args += ["-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p"]
    args += (["-c:a", "aac", "-shortest"] if tono else ["-an"])
    ffmpeg(*args, ruta)
    return ruta


def crear_musica(ruta, dur=8, freq=2000):
    ffmpeg("-f", "lavfi", "-i", "sine=f=%d:d=%d" % (freq, dur), "-c:a", "libmp3lame", ruta)
    return ruta


def armar(ruta):
    with Video(ruta) as v:
        info, tiempos = v.info(), v.tabla_tiempos()
    p = Proyecto()
    fid = p.agregar_fuente(ruta, "video", info["duracion"], tiempos, info["pistas_audio"], inicio=info["inicio"])
    p.nuevo_desde_fuente(fid)
    return p, fid, tiempos


def agregar_audio_archivo(p, ruta, **kw):
    c = av.open(ruta)
    dur = float(c.duration) / av.time_base
    c.close()
    fid = p.agregar_fuente(ruta, "audio", dur, None, 1)
    return p.agregar_audio(fid, **kw)


# ---------------------------------------------------------------- lectura

def leer_codigos(ruta, mapa=None, ancho_fuente=640, alto_fuente=360):
    """Numero de cuadro de cada cuadro del archivo. mapa(x, y) lleva una coordenada de la fuente a la salida."""
    cx0, cy0 = (ancho_fuente - 12 * BLOQUE) // 2, (alto_fuente - BLOQUE) // 2
    c = av.open(ruta)
    s = c.streams.video[0]
    out = []
    for f in c.decode(s):
        img = f.to_image().convert("L")
        n = 0
        for k in range(12):
            x, y = cx0 + BLOQUE * k + BLOQUE // 2, cy0 + BLOQUE // 2
            if mapa:
                x, y = mapa(x, y)
            if img.getpixel((int(round(x)), int(round(y)))) > 128:
                n |= 1 << k
        out.append(n)
    c.close()
    return out


def luminancia_cuadros(ruta, indices):
    c = av.open(ruta)
    s = c.streams.video[0]
    out = {}
    for i, f in enumerate(c.decode(s)):
        if i in indices:
            out[i] = ImageStat.Stat(f.to_image().convert("L").resize((32, 18))).mean[0]
        if i > max(indices):
            break
    c.close()
    return out


def muestras(ruta):
    """Audio completo como enteros de 16 bits, mono, 48 kHz."""
    c = av.open(ruta)
    s = c.streams.audio[0]
    r = av.AudioResampler(format="s16", layout="mono", rate=48000)
    m = array("h")
    for f in c.decode(s):
        for g in r.resample(f):
            m.frombytes(bytes(g.planes[0])[: g.samples * 2])
    for g in r.resample(None):
        m.frombytes(bytes(g.planes[0])[: g.samples * 2])
    c.close()
    return m


def rms(m, t0, t1, sr=48000):
    t = m[int(t0 * sr):int(t1 * sr)]
    return math.sqrt(sum(x * x for x in t) / max(1, len(t))) / 32768.0 if len(t) else 0.0


def frecuencia(m, t0, t1, sr=48000):
    """Frecuencia dominante por cruces por cero (sirve para un tono)."""
    t = m[int(t0 * sr):int(t1 * sr)]
    cruces = sum(1 for a, b in zip(t, t[1:]) if (a < 0) != (b < 0))
    return cruces / 2.0 / ((t1 - t0))


def goertzel(m, t0, t1, f, sr=48000):
    t = m[int(t0 * sr):int(t1 * sr)]
    if not len(t):
        return 0.0
    k = 2 * math.cos(2 * math.pi * f / sr)
    s1 = s2 = 0.0
    for x in t:
        s0 = x / 32768.0 + k * s1 - s2
        s2, s1 = s1, s0
    return (s1 * s1 + s2 * s2 - k * s1 * s2) / (len(t) ** 2)


def sondear(ruta):
    import json
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", ruta], capture_output=True, text=True)
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return v, a, float(d["format"]["duration"])


def esperados(p, tiempos):
    """Cuadros que tiene que tener la salida segun el proyecto: por cada clip de V1, los de la fuente en [desde, hasta)."""
    out = []
    for c in p.pista("V1")["clips"]:
        out += [i for i, t in enumerate(tiempos) if c["desde"] - 1e-6 <= t < c["hasta"] - 1e-6]
    return out


def exportar_a(p, nombre="t", **kw):
    carpeta = os.path.join(TMP, "salida-" + nombre)
    return exportar.exportar(p, carpeta, nombre, **kw)


def main():
    src = crear_fuente(os.path.join(TMP, "src.mp4"))
    musica = crear_musica(os.path.join(TMP, "musica.mp3"))

    print("=== 1. un corte: los cuadros salen EXACTOS y el audio acompana ===")
    p, fid, tiempos = armar(src)
    p.borrar_rango(3.0, 5.0)
    avance = []
    r = exportar_a(p, "corte", al_progresar=avance.append)
    codigos = leer_codigos(r["archivo"])
    ok(codigos == esperados(p, tiempos), "los 300 cuadros son exactamente los esperados ([0-89] + [150-359])",
       f"{len(codigos)} cuadros; {len(esperados(p, tiempos))} esperados")
    ok(abs(r["duracion"] - 10.0) < 0.1, "dura 10 s", r["duracion"])
    ok(r["tamano"] == (640, 360) and r["fps"] == "30/1", "mismo tamano y fps que la fuente", f"{r['tamano']} {r['fps']}")
    ok(all(b >= a for a, b in zip(avance, avance[1:])) and avance[-1] == 1.0, "el progreso sube hasta 1")
    m = muestras(r["archivo"])
    for t_sal, t_src in ((0.5, 0.5), (2.5, 2.5), (3.5, 5.5), (6.5, 8.5), (9.5, 11.5)):
        f = frecuencia(m, t_sal - 0.1, t_sal + 0.1)
        esperado = 400 + 50 * int(t_src)
        ok(abs(f - esperado) < 15, f"audio en {t_sal} s sale del segundo {t_src} de la fuente", f"{f:.0f} Hz, esperaba {esperado}")
    ok(abs(len(m) / 48000 - 10.0) < 0.1, "el audio dura lo mismo que el video", f"{len(m) / 48000:.2f} s")

    print("=== 2. varios cortes, recortes y piezas pegadas ===")
    p, fid, tiempos = armar(src)
    p.dividir(2.0)
    p.dividir(7.0)
    p.borrar_rango(4.0, 5.5)
    p.borrar_rango(0.0, 1.0)
    p.dividir(2.5)
    r = exportar_a(p, "varios")
    codigos = leer_codigos(r["archivo"])
    esp = esperados(p, tiempos)
    ok(codigos == esp, "con varios cortes, todos los cuadros coinciden con el proyecto", f"{len(codigos)} contra {len(esp)}")
    ok(abs(r["duracion"] - p.duracion()) < 0.1, "y la duracion es la del proyecto", f"{r['duracion']:.2f} contra {p.duracion():.2f}")

    print("=== 3. fundidos ===")
    p, fid, tiempos = armar(src)
    cv, ca = p.pista("V1")["clips"][0], p.pista("A1")["clips"][0]
    p.fade_grupo(cv["grupo"], "in", 1.0)
    p.fade_grupo(cv["grupo"], "out", 1.0)
    r = exportar_a(p, "fundido")
    lum = luminancia_cuadros(r["archivo"], {0, 15, 45, 330, 345, 359})
    ok(lum[0] < 0.25 * lum[45], "fundido de entrada: el primer cuadro es casi negro", f"{lum[0]:.0f} contra {lum[45]:.0f}")
    ok(lum[15] < 0.75 * lum[45], "y va subiendo", f"{lum[15]:.0f}")
    ok(lum[359] < 0.25 * lum[330], "fundido de salida: el ultimo cuadro es casi negro", f"{lum[359]:.0f} contra {lum[330]:.0f}")
    m = muestras(r["archivo"])
    ok(rms(m, 0.0, 0.08) < 0.35 * rms(m, 1.2, 1.4), "audio con fundido de entrada", f"{rms(m, 0, .08):.3f} contra {rms(m, 1.2, 1.4):.3f}")
    ok(rms(m, 11.92, 12.0) < 0.35 * rms(m, 10.6, 10.8), "audio con fundido de salida")
    ok(abs(r["duracion"] - 12.0) < 0.1, "los fundidos no cambian la duracion", r["duracion"])
    p, fid, tiempos = armar(src)
    p.fade(p.pista("V1")["clips"][0]["id"], "in", 1.0, color="blanco")
    r = exportar_a(p, "fundido_blanco")
    lum = luminancia_cuadros(r["archivo"], {0, 45})
    ok(lum[0] > 1.3 * lum[45] or lum[0] > 200, "fundido desde blanco: el primer cuadro es casi blanco", f"{lum[0]:.0f}")
    ok(leer_codigos(r["archivo"])[45:] == list(range(45, 360)), "y el resto sigue exacto")

    print("=== 4. volumen y silenciar ===")
    p, fid, tiempos = armar(src)
    base = exportar_a(p, "vol1")
    p.volumen(p.pista("A1")["clips"][0]["id"], 0.5)
    medio = exportar_a(p, "vol05")
    a = rms(muestras(base["archivo"]), 2.0, 4.0)
    b = rms(muestras(medio["archivo"]), 2.0, 4.0)
    ok(abs(b / a - 0.5) < 0.06, "volumen 50 %: la mitad de amplitud", f"{b / a:.2f}")
    p.silenciar("A1", True)
    r = exportar_a(p, "mudo")
    v, a_, _ = sondear(r["archivo"])
    ok(a_ is None and v is not None, "con el audio silenciado el archivo no trae pista de audio")

    print("=== 4b. efectos por clip ===")
    from PIL import Image, ImageChops, ImageStat

    def cuadro_n(ruta, n):
        cont = av.open(ruta)
        for i, f in enumerate(cont.decode(cont.streams.video[0])):
            if i == n:
                img = f.to_image().convert("RGB")
                cont.close()
                return img
        cont.close()
        return None

    def dif_media(a, b):
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3.0

    p, fid, tiempos = armar(src)
    base = exportar_a(p, "fx_base")["archivo"]
    cid = p.pista("V1")["clips"][0]["id"]
    # --- color: la imagen cambia, los cuadros NO
    p.agregar_efecto(cid, "color_basico", {"brillo": 0.1})
    r = exportar_a(p, "fx_brillo")
    ok(leer_codigos(r["archivo"]) == esperados(p, tiempos), "con un efecto de color los 360 cuadros siguen siendo los mismos y en orden")
    lb, le = luminancia_cuadros(base, {10, 100, 200}), luminancia_cuadros(r["archivo"], {10, 100, 200})
    ok(all(le[i] - lb[i] > 12 for i in lb), "brillo +0,1: la imagen sale mas clara", f"base {lb}, con efecto {le}")
    p2, _, _ = armar(src)
    p2.agregar_efecto(p2.pista("V1")["clips"][0]["id"], "color_basico", {"saturacion": 0.0})
    gris = cuadro_n(exportar_a(p2, "fx_gris")["archivo"], 100)
    sat_con = ImageStat.Stat(gris.convert("HSV").split()[1]).mean[0]          # saturacion media de la imagen (0-255)
    sat_base = ImageStat.Stat(cuadro_n(base, 100).convert("HSV").split()[1]).mean[0]
    ok(sat_con < 0.15 * sat_base and sat_base > 80, "saturacion 0: la imagen sale en grises", f"saturacion con efecto {sat_con:.0f}, base {sat_base:.0f}")
    # --- apagado: es como no tenerlo
    p.activar_efecto(cid, p.pista("V1")["clips"][0]["efectos"][0]["id"], False)
    apagado = exportar_a(p, "fx_apagado")["archivo"]
    la = luminancia_cuadros(apagado, {10, 100, 200})
    ok(all(abs(la[i] - lb[i]) < 1.5 for i in lb), "un efecto apagado no cambia la imagen", f"{la} vs {lb}")
    # --- voltear
    p3, _, _ = armar(src)
    p3.agregar_efecto(p3.pista("V1")["clips"][0]["id"], "voltear", {"horizontal": True, "vertical": False})
    rv = exportar_a(p3, "fx_espejo")["archivo"]
    espejo = cuadro_n(rv, 50)
    base50 = cuadro_n(base, 50)
    ok(dif_media(espejo, base50.transpose(Image.Transpose.FLIP_LEFT_RIGHT)) < 8 and dif_media(espejo, base50) > 15,
       "voltear (izquierda con derecha): sale como en un espejo", f"{dif_media(espejo, base50.transpose(Image.Transpose.FLIP_LEFT_RIGHT)):.1f} vs {dif_media(espejo, base50):.1f}")
    ok(leer_codigos(rv, lambda x, y: (640 - x, y)) == esperados(p3, tiempos), "y los cuadros siguen en orden (el codigo de barras se lee del otro lado)")
    p3.cambiar_efecto(p3.pista("V1")["clips"][0]["id"], p3.pista("V1")["clips"][0]["efectos"][0]["id"], {"horizontal": False, "vertical": True})
    vert = cuadro_n(exportar_a(p3, "fx_vertical")["archivo"], 50)
    ok(dif_media(vert, base50.transpose(Image.Transpose.FLIP_TOP_BOTTOM)) < 8 and dif_media(vert, base50) > 15, "voltear (arriba con abajo)")
    # --- un efecto solo en una mitad
    p4, _, _ = armar(src)
    p4.dividir(6.0)
    izq4 = p4.pista("V1")["clips"][0]
    p4.agregar_efecto(izq4["id"], "color_basico", {"brillo": 0.2})
    r4 = exportar_a(p4, "fx_mitad")
    l4 = luminancia_cuadros(r4["archivo"], {50, 300})
    lbase = luminancia_cuadros(base, {50, 300})
    ok(l4[50] - lbase[50] > 25 and abs(l4[300] - lbase[300]) < 1.5, "un efecto en la primera mitad no toca la segunda", f"{l4} vs {lbase}")
    ok(leer_codigos(r4["archivo"]) == esperados(p4, tiempos), "y el corte sigue exacto")
    # --- las dos mitades con el mismo efecto se exportan como un solo tramo (mismo resultado)
    p5, _, _ = armar(src)
    id5 = p5.pista("V1")["clips"][0]["id"]
    p5.agregar_efecto(id5, "color_basico", {"brillo": 0.1})
    p5.dividir(6.0)
    r5 = exportar_a(p5, "fx_dos_mitades")
    l5 = luminancia_cuadros(r5["archivo"], {50, 300})
    ok(all(l5[i] - lbase[i] > 12 for i in l5), "al cortar, las dos mitades llevan el efecto", f"{l5} vs {lbase}")
    ok(leer_codigos(r5["archivo"]) == esperados(p5, tiempos), "y salen los mismos cuadros")
    # --- audio: quitar graves
    grave = crear_musica(os.path.join(TMP, "grave.mp3"), 8, 100)
    pa, _, _ = armar(src)
    pa.silenciar("A1", True)
    cm = agregar_audio_archivo(pa, grave, inicio=0.0, hasta=8.0)
    sin = muestras(exportar_a(pa, "fx_sin_filtro")["archivo"])
    pa.agregar_efecto(cm, "pasa_altos", {"frecuencia": 500})
    con = muestras(exportar_a(pa, "fx_pasa_altos")["archivo"])
    ok(rms(sin, 1.0, 5.0) > 0.05 and rms(con, 1.0, 5.0) < 0.1 * rms(sin, 1.0, 5.0),
       "quitar graves (500 Hz): un tono de 100 Hz casi desaparece", f"sin {rms(sin, 1.0, 5.0):.4f}, con {rms(con, 1.0, 5.0):.4f}")
    pa.cambiar_efecto(cm, pa.pista("A2")["clips"][0]["efectos"][0]["id"], {"frecuencia": 20})
    suave = muestras(exportar_a(pa, "fx_pasa_altos_20")["archivo"])
    ok(rms(suave, 1.0, 5.0) > 0.7 * rms(sin, 1.0, 5.0), "y con 20 Hz el mismo tono casi no cambia", f"{rms(suave, 1.0, 5.0):.4f}")

    print("=== 5. audio extra mezclado, y reemplazo del audio ===")
    p, fid, tiempos = armar(src)
    agregar_audio_archivo(p, musica, inicio=2.0, hasta=4.0)           # 4 s de un tono de 2000 Hz desde el segundo 2
    r = exportar_a(p, "mezcla")
    m = muestras(r["archivo"])
    antes = goertzel(m, 0.5, 1.5, 2000)
    durante = goertzel(m, 3.0, 4.0, 2000)
    despues = goertzel(m, 7.0, 8.0, 2000)
    ok(durante > 50 * max(antes, 1e-12) and durante > 50 * max(despues, 1e-12), "la musica suena solo entre el segundo 2 y el 6",
       f"antes {antes:.2e}, durante {durante:.2e}, despues {despues:.2e}")
    ok(goertzel(m, 3.0, 4.0, 450 if int(3.5) == 3 else 400) > 1e-5 or goertzel(m, 1.0, 1.9, 450) > 1e-5, "y el audio original sigue sonando debajo")
    ok(abs(r["duracion"] - 12.0) < 0.1, "la musica no cambia la duracion (se recorta al video)", r["duracion"])
    p.silenciar("A1", True)
    r = exportar_a(p, "reemplazo")
    m = muestras(r["archivo"])
    ok(goertzel(m, 3.0, 4.0, 2000) > 1e-5 and goertzel(m, 0.2, 0.9, 400) < 1e-6, "reemplazo: solo se oye la musica, no el audio original")
    ok(rms(m, 0.2, 1.5) < 0.001 and rms(m, 3.0, 5.0) > 0.05, "y hay silencio donde la musica no suena")

    print("=== 6. formatos de video y encuadres ===")
    casos = [("vertical", "recortar", (1080, 1920)), ("vertical", "barras", (1080, 1920)),
             ("horizontal", "recortar", (1920, 1080)), ("cuadrado", "recortar", (1080, 1080)), ("cuadrado", "barras", (1080, 1080))]
    for formato, encuadre, (W, H) in casos:
        p, fid, tiempos = armar(src)
        p.recortar_a(1.0, 2.0)                       # 30 cuadros alcanzan para comprobar el mapeo
        r = exportar_a(p, "f-%s-%s" % (formato, encuadre), formato=formato, encuadre=encuadre)
        ok(r["tamano"] == (W, H), f"{formato}/{encuadre}: sale de {W}x{H}", r["tamano"])
        if encuadre == "recortar":
            s = max(W / 640, H / 360)
            ox, oy = (640 * s - W) / 2, (360 * s - H) / 2
            mapa = lambda x, y, s=s, ox=ox, oy=oy: (x * s - ox, y * s - oy)
        else:
            s = min(W / 640, H / 360)
            ox, oy = (W - 640 * s) / 2, (H - 360 * s) / 2
            mapa = lambda x, y, s=s, ox=ox, oy=oy: (x * s + ox, y * s + oy)
        codigos = leer_codigos(r["archivo"], mapa)
        ok(codigos == list(range(30, 60)), f"{formato}/{encuadre}: el recuadro es el esperado (se lee el codigo de cada cuadro)",
           f"{codigos[:4]}...")
    # el foco mueve el recorte: se compara con el recorte calculado aparte (PIL) a partir del cuadro original
    from io import BytesIO
    imagenes = {}
    for fx in (0.0, 1.0):
        p, fid, tiempos = armar(src)
        p.recortar_a(1.0, 1.5)
        r = exportar_a(p, "foco-%s" % fx, formato="vertical", encuadre="recortar", foco=(fx, 0.5))
        c = av.open(r["archivo"])
        salida = next(c.decode(c.streams.video[0])).to_image().convert("L").resize((90, 160))
        c.close()
        with Video(src) as v:
            ref = Image.open(BytesIO(v.cuadro(30, 640))).convert("L")
        s_ = 1920 / 360
        ref = ref.resize((round(640 * s_), 1920))
        x0 = (ref.width - 1080) * fx
        ref = ref.crop((int(round(x0)), 0, int(round(x0)) + 1080, 1920)).resize((90, 160))
        d = ImageStat.Stat(ImageChops.difference(salida, ref)).mean[0]
        ok(d < 12, "foco %.1f: el recorte coincide con el calculado aparte" % fx, f"diferencia {d:.1f}")
        imagenes[fx] = salida
    ok(ImageStat.Stat(ImageChops.difference(imagenes[0.0], imagenes[1.0])).mean[0] > 15,
       "y foco a la izquierda y a la derecha dan recortes bien distintos")

    print("=== 7. solo audio ===")
    p, fid, tiempos = armar(src)
    p.borrar_rango(3.0, 5.0)
    for formato, codec in (("wav", "pcm_s16le"), ("mp3", "mp3"), ("flac", "flac"), ("m4a", "aac")):
        r = exportar_a(p, "a-" + formato, formato=formato)
        v, a_, dur = sondear(r["archivo"])
        ok(v is None and a_ and a_["codec_name"] == codec, f"{formato}: sin video, codec {codec}", a_ and a_["codec_name"])
        ok(a_["sample_rate"] == "48000" and a_["channels"] == 2 and abs(dur - 10.0) < 0.15, f"{formato}: 48 kHz estereo y 10 s", f"{a_['sample_rate']}, {a_['channels']}, {dur:.2f}")
    m = muestras(r["archivo"])
    ok(abs(frecuencia(m, 3.4, 3.6) - 650) < 20, "el corte esta aplicado en el audio exportado (3,5 s sale del segundo 5,5)",
       f"{frecuencia(m, 3.4, 3.6):.0f} Hz")
    pa = Proyecto()
    solo = crear_musica(os.path.join(TMP, "solo.mp3"), 6, 880)
    c = av.open(solo)
    dur = float(c.duration) / av.time_base
    c.close()
    fa = pa.agregar_fuente(solo, "audio", dur, None, 1)
    pa.nuevo_desde_fuente(fa)
    ra = exportar_a(pa, "solo-audio", formato="wav")
    ok(abs(ra["duracion"] - dur) < 0.1, "un proyecto de solo audio se exporta", ra["duracion"])
    err = None
    try:
        exportar_a(pa, "mal", formato="vertical")
    except exportar.ExportError as e:
        err = str(e)
    ok(err and "no tiene video" in err, "pedirle video a un proyecto de solo audio da un error claro", err)

    print("=== 8. normalizar a -14 LUFS ===")
    p, fid, tiempos = armar(src)
    p.volumen(p.pista("A1")["clips"][0]["id"], 0.08)           # muy bajo
    sin = exportar_a(p, "sin-norm", formato="wav")
    con = exportar_a(p, "con-norm", formato="wav", normalizar=True, lufs=-14.0)

    def lufs(ruta):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", ruta, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        import json
        return float(json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])["input_i"])

    a, b = lufs(sin["archivo"]), lufs(con["archivo"])
    ok(a < -24, "sin normalizar queda bajo", f"{a:.1f} LUFS")
    ok(abs(b - (-14.0)) < 1.0, "normalizado queda en -14 LUFS (+-1)", f"{b:.1f} LUFS")
    ok(con["normalizacion"] is not None and con["normalizacion"]["objetivo"] == -14.0, "informa la medicion que hizo")
    p.silenciar("A1", True)
    err = None
    try:
        exportar_a(p, "norm-mudo", formato="wav", normalizar=True)
    except exportar.ExportError as e:
        err = str(e)
    ok(err is not None, "normalizar sin audio da un error claro, no revienta", err)

    print("=== 9. nunca se pisa nada: versiones ===")
    carpeta = os.path.join(TMP, "versiones")
    os.makedirs(carpeta)
    ajeno = os.path.join(carpeta, "mi-v1.mp4")
    with open(ajeno, "wb") as f:
        f.write(b"un archivo que ya estaba ahi")
    huella = hashlib.sha1(open(ajeno, "rb").read()).hexdigest()
    p, fid, tiempos = armar(src)
    p.recortar_a(0.0, 1.0)
    nombres = [os.path.basename(exportar.exportar(p, carpeta, "mi")["archivo"]) for _ in range(3)]
    ok(nombres == ["mi-v2.mp4", "mi-v3.mp4", "mi-v4.mp4"], "va numerando y saltea el que ya existia", str(nombres))
    ok(hashlib.sha1(open(ajeno, "rb").read()).hexdigest() == huella, "y el archivo que ya estaba queda intacto")
    ok(not [n for n in os.listdir(carpeta) if "parcial" in n], "no quedan archivos .parcial")

    print("=== 10. cancelar ===")
    largo = crear_fuente(os.path.join(TMP, "largo.mp4"), dur=60, w=1280, h=720)
    p, fid, tiempos = armar(largo)
    evento = threading.Event()
    resultado = {}

    def trabajar():
        try:
            exportar.exportar(p, os.path.join(TMP, "cancel"), "c", formato="vertical", cancelar=evento)
            resultado["fin"] = "completo"
        except exportar.Cancelado:
            resultado["fin"] = "cancelado"
        except Exception as e:
            resultado["fin"] = repr(e)

    h = threading.Thread(target=trabajar)
    h.start()
    time.sleep(1.5)
    evento.set()
    h.join(60)
    ok(resultado.get("fin") == "cancelado", "cancelar corta la exportacion", resultado.get("fin"))
    ok(not os.listdir(os.path.join(TMP, "cancel")), "y no deja archivos a medias", str(os.listdir(os.path.join(TMP, "cancel"))))

    print("=== 11. codificador de GPU que falla: respaldo al procesador ===")
    p, fid, tiempos = armar(src)
    p.borrar_rango(3.0, 5.0)
    r = exportar_a(p, "gpu", codificador="h264_nvenc")
    ok(r["usado"] == "cpu" and r["respaldo"] is True and "no funcionó" in r["motivo_respaldo"] and "out#" not in r["motivo_respaldo"],
       "si NVENC falla se exporta con el procesador y se avisa con una frase clara", r["motivo_respaldo"])
    ok(leer_codigos(r["archivo"]) == esperados(p, tiempos), "y el resultado es exacto igual")

    print("=== 12. muchisimos cortes (el filtro no entra en la linea de comandos) ===")
    p, fid, tiempos = armar(src)
    t = 0.0
    while t < 11.95:
        t += 1 / 30            # un corte por cuadro: cientos de clips
        try:
            p.dividir(t)
        except Exception:
            pass
    grupos = [c["grupo"] for c in p.pista("V1")["clips"]]
    for g in grupos[1::2]:
        try:
            p.borrar_grupo(g)
        except Exception:
            pass
    plan = exportar._Plan(p, "original", "recortar", (0.5, 0.5), None, True, True)
    n_clips = len(p.pista("V1")["clips"])
    ok(len(plan.grafo()) > 33000, f"el filtro de {n_clips} clips pasa el limite de la linea de comandos de Windows (32.767)", f"{len(plan.grafo())} caracteres, {len(plan.entradas)} entradas")
    r = exportar_a(p, "muchos")
    ok(leer_codigos(r["archivo"]) == esperados(p, tiempos), "y se exporta igual, cuadro por cuadro", f"{n_clips} clips")

    print("=== 13. hueco en la linea de tiempo (queda negro y en silencio) ===")
    p, fid, tiempos = armar(src)
    p.dividir(6.0)
    for pista in p.pistas:
        pista["clips"][1]["inicio"] = round(pista["clips"][1]["inicio"] + 1.0, 6)
    ok(p.validar() == [], "el proyecto con hueco es valido")
    r = exportar_a(p, "hueco")
    ok(abs(r["duracion"] - 13.0) < 0.1, "dura 1 s mas", r["duracion"])
    lum = luminancia_cuadros(r["archivo"], {100, 185, 230})
    ok(lum[185] < 20 and lum[100] > 40 and lum[230] > 40, "durante el hueco la imagen es negra", f"{lum}")
    ok(rms(muestras(r["archivo"]), 6.2, 6.8) < 0.002, "y el audio, silencio")

    print("=== 14. varias fuentes de video distintas (montaje) ===")
    otra = crear_fuente(os.path.join(TMP, "otra.mp4"), dur=4, w=320, h=240, fps=25)
    p, fid, tiempos = armar(src)
    p.recortar_a(0.0, 3.0)
    with Video(otra) as v:
        i2, t2 = v.info(), v.tabla_tiempos()
    f2 = p.agregar_fuente(otra, "video", i2["duracion"], t2, i2["pistas_audio"], inicio=i2["inicio"])
    g = p._nuevo_grupo()
    p.pista("V1")["clips"].append(p._clip(f2, 0.0, i2["duracion"], 3.0, g))
    p.pista("A1")["clips"].append(p._clip(f2, 0.0, i2["duracion"], 3.0, g, pista_audio=0))
    ok(p.validar() == [], "el proyecto con dos fuentes es valido", p.validar())
    r = exportar_a(p, "montaje", formato="horizontal", encuadre="barras")
    v, a_, dur = sondear(r["archivo"])
    ok((int(v["width"]), int(v["height"])) == (1920, 1080) and abs(dur - 7.0) < 0.15, "dos fuentes de distinto tamano y fps: 1920x1080 y 7 s", f"{v['width']}x{v['height']} {dur:.2f}")
    ok(v["r_frame_rate"] == "30/1", "con el fps de la primera fuente", v["r_frame_rate"])
    s = min(1920 / 640, 1080 / 360)
    c1 = leer_codigos(r["archivo"], lambda x, y: (x * s + (1920 - 640 * s) / 2, y * s + (1080 - 360 * s) / 2))
    ok(c1[:90] == list(range(90)), "la primera parte es exacta")
    ok(rms(muestras(r["archivo"]), 4.0, 6.0) > 0.05, "y el audio de la segunda parte suena")

    print("=== 15. errores claros ===")
    p, fid, tiempos = armar(src)
    for etiqueta, kw in (("formato desconocido", {"formato": "avi"}), ("encuadre desconocido", {"encuadre": "estirar"})):
        err = None
        try:
            exportar_a(p, "e", **kw)
        except exportar.ExportError as e:
            err = str(e)
        ok(err is not None, f"{etiqueta}: error claro", err)
    p2 = Proyecto()
    f = p2.agregar_fuente(os.path.join(TMP, "no_existe.mp4"), "video", 5.0, [i / 30 for i in range(150)], 1)
    p2.nuevo_desde_fuente(f)
    err = None
    try:
        exportar_a(p2, "e2")
    except exportar.ExportError as e:
        err = str(e)
    ok(err and "No encuentro" in err, "un archivo original que ya no esta: error claro", err)
    err = None
    try:
        exportar_a(Proyecto(), "vacio")
    except exportar.ExportError as e:
        err = str(e)
    ok(err is not None, "un proyecto vacio: error claro", err)

    print("=== 16. video girado de celular ===")
    base = crear_fuente(os.path.join(TMP, "base_rot.mp4"), dur=3)
    rot = os.path.join(TMP, "rotado.mp4")
    ffmpeg("-display_rotation", "90", "-i", base, "-c", "copy", rot)
    p, fid, tiempos = armar(rot)
    r = exportar_a(p, "rotado")
    ok(r["tamano"] == (360, 640), "la salida sale derecha (360x640) y no de costado", r["tamano"])
    img_sal = av.open(r["archivo"])
    f10 = None
    for i, f in enumerate(img_sal.decode(img_sal.streams.video[0])):
        if i == 10:
            f10 = f.to_image().convert("L").resize((90, 160))
            break
    img_sal.close()
    from io import BytesIO
    with Video(rot) as v:
        ref = Image.open(BytesIO(v.cuadro(10, 90))).convert("L").resize((90, 160))
    d = ImageStat.Stat(ImageChops.difference(f10, ref)).mean[0]
    ok(d < 12, "y se parece al cuadro que muestra el editor (que ya se verifico contra el autogiro de ffmpeg)", f"diferencia {d:.1f}")

    print("=== 17. el video real de framerate variable (el de Diego) ===")
    if os.path.isfile(VFR):
        p, fid, tiempos = armar(VFR)
        p.recortar_a(100.0, 120.0)
        t0 = time.time()
        r = exportar_a(p, "vfr")
        v, a_, dur = sondear(r["archivo"])
        n = int(round(dur * 24))
        ok(r["fps"] == "24", "un VFR de 22,4 fps promedio sale a 24 fps constantes", r["fps"])
        ok(abs(dur - p.duracion()) < 0.15, "dura lo que dice el proyecto", f"{dur:.2f} contra {p.duracion():.2f}")
        ok(a_ is not None, "con su audio")
        c = av.open(r["archivo"])
        cuadros = sum(1 for _ in c.decode(c.streams.video[0]))
        c.close()
        ok(abs(cuadros - 24 * p.duracion()) <= 2, "con la cantidad de cuadros que corresponde", f"{cuadros} contra {24 * p.duracion():.0f}")
        with Video(VFR) as vv:
            n0 = vv.cuadro_de_tiempo(100.0 + 0.0)
            ref = Image.open(BytesIO(vv.cuadro(n0, 180))).convert("L")
        c = av.open(r["archivo"])
        primero = next(c.decode(c.streams.video[0])).to_image().convert("L").resize(ref.size)
        c.close()
        d = ImageStat.Stat(ImageChops.difference(primero, ref)).mean[0]
        ok(d < 12, "el primer cuadro exportado es el del segundo 100 del original (alineado a pesar de los timestamps raros)", f"diferencia {d:.1f}")
        print(f"  (exportar 20 s de un video de 15 min tardo {time.time() - t0:.1f} s)")
    else:
        print("  (sin el video del Escritorio, se saltea)")

    print("=== 18. el video real entrelazado con audio 5.1 (el de Diego) ===")
    if os.path.isfile(MPG):
        p, fid, tiempos = armar(MPG)
        p.recortar_a(60.0, 75.0)
        t0 = time.time()
        r = exportar_a(p, "mpg", formato="vertical", encuadre="recortar")
        v, a_, dur = sondear(r["archivo"])
        ok((int(v["width"]), int(v["height"])) == (1080, 1920) and abs(dur - 15.0) < 0.2, "sale vertical 1080x1920 y dura 15 s", f"{v['width']}x{v['height']} {dur:.2f}")
        ok(a_ and a_["channels"] == 2, "el 5.1 queda mezclado a estereo", a_ and a_["channels"])
        c = av.open(r["archivo"])
        cuadros = sum(1 for _ in c.decode(c.streams.video[0]))
        c.close()
        ok(abs(cuadros - 15 * 30000 / 1001) <= 2, "con los cuadros que corresponden (29,97 fps)", f"{cuadros}")
        pr = subprocess.run(["ffmpeg", "-v", "info", "-i", r["archivo"], "-vf", "idet", "-frames:v", "300", "-an", "-f", "null", "-"], capture_output=True, text=True)
        ms = re.findall(r"Multi frame detection: TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)", pr.stderr)
        tff, bff, prog = map(int, ms[-1])
        ok(prog > 8 * max(1, tff + bff), "se desentrelazo", f"progresivos {prog}, entrelazados {tff + bff}")
        with Video(MPG) as vv:
            n7 = vv.cuadro_de_tiempo(67.5)
            ref = Image.open(BytesIO(vv.cuadro(n7, 1920))).convert("L")
        w0, h0 = ref.size
        ancho_recorte = h0 * 9 / 16
        ref = ref.crop((int((w0 - ancho_recorte) / 2), 0, int((w0 + ancho_recorte) / 2), h0)).resize((90, 160))
        c = av.open(r["archivo"])
        fx = None
        for i, f in enumerate(c.decode(c.streams.video[0])):
            if i == 225:
                fx = f.to_image().convert("L").resize((90, 160))
                break
        c.close()
        d = ImageStat.Stat(ImageChops.difference(fx, ref)).mean[0]
        ok(d < 14, "el cuadro del segundo 7,5 exportado coincide con el del original recortado al centro", f"diferencia {d:.1f}")
        print(f"  (exportar 15 s de un MPEG-2 1080i a vertical tardo {time.time() - t0:.1f} s)")
    else:
        print("  (sin el video del Escritorio, se saltea)")

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
