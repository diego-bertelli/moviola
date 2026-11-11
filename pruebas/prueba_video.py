# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del motor de cuadros (motor/video.py).

Uso:  python -I pruebas/prueba_video.py

Cubre: indice de cuadros real (VFR), acceso aleatorio contra secuencial, MPEG-PS
entrelazado, rotacion de celular comparada contra el autogiro de ffmpeg y
concurrencia. Los videos del Escritorio son opcionales: si no estan, esos casos
se saltean. Nunca modifica los archivos de entrada.
"""

import os
import random
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from PIL import Image, ImageChops, ImageStat  # noqa: E402

from motor.video import Video, SinVideo  # noqa: E402

ESCRITORIO = os.environ.get("MOVIOLA_VIDEOS_REALES", "")   # carpeta con dos videos reales (uno VFR y un MPEG-PS); sin ella esas partes se saltean
VFR = os.path.join(ESCRITORIO, "real-vfr.mp4")
MPG = os.path.join(ESCRITORIO, "real-mpeg2.mpg")

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def jpeg_a_imagen(datos):
    return Image.open(BytesIO(datos)).convert("L")


def diferencia(a, b):
    if a.size != b.size:
        return 999.0
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def acceso_aleatorio(v, cuantos, semilla):
    """Cada cuadro pedido al azar tiene que salir con el pts que le corresponde."""
    azar = random.Random(semilla)
    total = v.info()["total_cuadros"]
    malos = 0
    # los extremos son los casos delicados (el seek puede caer pasado el final)
    pedidos = [0, 1, total - 1, total - 2, total - 3, total - 20] + [azar.randrange(total) for _ in range(cuantos)]
    for n in pedidos:
        # Se saltea la cache y el decoder en curso: acceso aleatorio de verdad.
        v._ultimo = None
        v._generador = None
        cuadro = v._decodificar(n)
        # con pts duplicados el indice puede caer en el gemelo
        if cuadro.pts != v._pts[n] or abs((v._ultimo or 0) - n) > 1:
            malos += 1
    return malos


def secuencial_igual_a_salto(v, desde, largo):
    """Avanzar de a uno tiene que dar los mismos cuadros que saltar directo."""
    malos = 0
    for n in range(desde, desde + largo):
        a = v.cuadro(n, 160)
        otro = type(v)(v.ruta)
        try:
            b = otro.cuadro(n, 160)
        finally:
            otro.cerrar()
        if a != b:
            malos += 1
    return malos


def medir(v, etiqueta):
    total = v.info()["total_cuadros"]
    v.cuadro(total // 3, 540)
    t0 = time.perf_counter()
    for n in range(total // 3 + 1, total // 3 + 41):
        v.cuadro(n, 540)
    seq = (time.perf_counter() - t0) / 40 * 1000
    azar = random.Random(7)
    saltos = []
    for _ in range(12):
        n = azar.randrange(total)
        t0 = time.perf_counter()
        v.cuadro(n, 540)
        saltos.append((time.perf_counter() - t0) * 1000)
    saltos.sort()
    print(f"  [{etiqueta}] secuencial {seq:.1f} ms/cuadro | salto mediana {saltos[6]:.0f} ms, peor {saltos[-1]:.0f} ms", flush=True)
    return seq, saltos[6]


def main():
    tmp = tempfile.mkdtemp(prefix="prueba-video-")

    print("=== 1. clip sintetico de cuadros constantes ===")
    cfr = os.path.join(tmp, "cfr.mp4")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=10", "-f", "lavfi", "-i", "sine=f=220:d=10",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", cfr)
    with Video(cfr) as v:
        i = v.info()
        ok(i["total_cuadros"] == 300, "300 cuadros", i["total_cuadros"])
        ok(abs(i["fps"] - 30) < 0.01, "30 fps", i["fps"])
        ok(i["vfr"] is False, "no es VFR")
        ok(i["rotacion"] == 0 and i["entrelazado"] is False, "sin rotacion ni entrelazado")
        ok(i["pistas_audio"] == 1, "una pista de audio")
        ok(i["web_compatible"] is True, "reproducible en el WebView")
        ok(abs(v.tiempo(30) - 1.0) < 1e-6, "tiempo(30) = 1,000 s", v.tiempo(30))
        ok(v.cuadro_de_tiempo(1.0) == 30 and v.cuadro_de_tiempo(0.9999) in (29, 30), "cuadro_de_tiempo(1,0) = 30")
        ok(acceso_aleatorio(v, 40, 1) == 0, "acceso aleatorio exacto (40 cuadros)")
        ok(secuencial_igual_a_salto(v, 100, 6) == 0, "secuencial == salto directo")

    print("=== 2. video de framerate variable (real-vfr.mp4) ===")
    if os.path.isfile(VFR):
        with Video(VFR) as v:
            i = v.info()
            ok(i["vfr"] is True, "detectado como VFR")
            ok(i["total_cuadros"] == 20247, "20247 cuadros reales", i["total_cuadros"])
            ok(21 < i["fps"] < 24, "fps medio ~22,4", round(i["fps"], 3))
            ok(abs(i["duracion"] - 904.53) < 2, "duracion ~904,5 s", round(i["duracion"], 2))
            tabla = v.tabla_tiempos()
            ok(len(tabla) == 20247 and all(b >= a for a, b in zip(tabla, tabla[1:])), "tabla de tiempos creciente")
            # el cuadro n+1 no esta en n/fps: con VFR la grilla ideal se corre
            corrido = max(abs(t - n / i["fps"]) for n, t in enumerate(tabla))
            ok(corrido > 0.5, "la grilla n/fps se corre del tiempo real (justifica el indice)", f"hasta {corrido:.1f} s")
            ok(acceso_aleatorio(v, 60, 2) == 0, "acceso aleatorio exacto (60 cuadros)")
            for n in (0, 5000, 12345, 20246):
                ok(v.cuadro_de_tiempo(v.tiempo(n)) in (n, n + 1, n - 1), f"ida y vuelta tiempo/cuadro en {n}")
            medir(v, "VFR 360x640")
    else:
        print("  (sin el video, se saltea)")

    print("=== 3. MPEG-2 entrelazado en MPEG-PS, audio AC3 5.1 ===")
    if os.path.isfile(MPG):
        with Video(MPG) as v:
            i = v.info()
            ok(i["codec"] == "mpeg2video", "codec mpeg2video", i["codec"])
            ok(i["entrelazado"] is True, "detectado como entrelazado")
            ok(i["vfr"] is False, "cuadros constantes")
            ok(abs(i["fps"] - 29.97) < 0.01, "29,97 fps", round(i["fps"], 4))
            ok(i["total_cuadros"] == 9750, "9750 cuadros", i["total_cuadros"])
            ok(i["web_compatible"] is False, "no reproducible directo (va por proxy)")
            ok(i["pistas_audio"] == 1, "una pista de audio")
            ok(acceso_aleatorio(v, 60, 3) == 0, "acceso aleatorio exacto (60 cuadros)")
            ok(secuencial_igual_a_salto(v, 4000, 4) == 0, "secuencial == salto directo")
            seq, salto = medir(v, "MPEG-PS 1080i")
    else:
        print("  (sin el video, se saltea)")

    print("=== 4. rotacion de celular (matriz de display 90 grados) ===")
    rot = os.path.join(tmp, "rot90.mp4")
    ffmpeg("-display_rotation", "90", "-i", cfr, "-c", "copy", rot)
    with Video(rot) as v:
        i = v.info()
        ok(i["rotacion"] == 90, "lee rotacion 90", i["rotacion"])
        ok((i["ancho"], i["alto"]) == (360, 640), "ancho y alto ya girados", f"{i['ancho']}x{i['alto']}")
        img = jpeg_a_imagen(v.cuadro(10, 270))
        ok(img.size == (270, 480), "el JPEG sale derecho", img.size)
        # referencia: ffmpeg gira solo al decodificar
        ref = os.path.join(tmp, "ref.png")
        ffmpeg("-i", rot, "-vf", "select=eq(n\\,10),scale=270:480", "-frames:v", "1", ref)
        referencia = Image.open(ref).convert("L")
        d_bien = diferencia(img, referencia)
        d_mal = diferencia(img.transpose(Image.Transpose.ROTATE_180), referencia)
        ok(d_bien < 18, "coincide con el autogiro de ffmpeg", f"diferencia {d_bien:.1f}")
        ok(d_bien < d_mal / 2, "y es mucho mas parecido que girado al reves", f"{d_bien:.1f} contra {d_mal:.1f}")

    print("=== 5. solo audio y archivos que no son video ===")
    mp3 = os.path.join(tmp, "solo.mp3")
    ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=3", mp3)
    try:
        Video(mp3)
        ok(False, "un mp3 sin video levanta SinVideo")
    except SinVideo:
        ok(True, "un mp3 sin video levanta SinVideo")
    caratula = os.path.join(tmp, "caratula.png")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=200x200:d=1", "-frames:v", "1", caratula)
    mp3c = os.path.join(tmp, "con_caratula.mp3")
    ffmpeg("-i", mp3, "-i", caratula, "-map", "0", "-map", "1", "-c", "copy", "-id3v2_version", "3", mp3c)
    try:
        Video(mp3c)
        ok(False, "un mp3 con caratula tampoco cuenta como video")
    except SinVideo:
        ok(True, "un mp3 con caratula tampoco cuenta como video")
    basura = os.path.join(tmp, "no_es_video.mp4")
    with open(basura, "wb") as f:
        f.write(b"esto no es un video" * 50)
    try:
        Video(basura)
        ok(False, "un archivo basura levanta error")
    except Exception as e:
        ok(True, "un archivo basura levanta error", type(e).__name__)

    print("=== 6. concurrencia: 8 hilos pidiendo cuadros a la vez ===")
    with Video(cfr) as v:
        esperado = {n: v.cuadro(n, 160) for n in range(0, 300, 15)}
        errores = []

        def trabajar(sem):
            azar = random.Random(sem)
            for _ in range(25):
                n = azar.choice(list(esperado))
                if v.cuadro(n, 160) != esperado[n]:
                    errores.append(n)

        hilos = [threading.Thread(target=trabajar, args=(s,)) for s in range(8)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        ok(not errores, "200 pedidos concurrentes, ninguno mezclado", f"{len(errores)} mezclados")

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
