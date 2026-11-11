# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Matriz de compatibilidad: genera archivos en muchos formatos y comprueba que
cada uno abra por el camino completo de la app (API.abrir), sin ventana.

Uso:  python -I pruebas/prueba_formatos.py

Para cada archivo revisa: que abra sin error, que la info sea coherente, que el
primer y el ultimo cuadro se puedan pedir, y que haya espectro de audio. Lo que
no se puede generar con este ffmpeg se informa como "saltado", nunca como OK.
"""

import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")      # estas pruebas no necesitan la deteccion de GPU

from app import API, crear_servidor  # noqa: E402

TMP = tempfile.mkdtemp(prefix="prueba-formatos-")
fallos = []
saltados = []

# Fuentes cortas. 320x240 para que generar cada formato sea rapido.
V = ["-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=2"]
V4K = ["-f", "lavfi", "-i", "testsrc2=s=3840x2160:r=30:d=2"]
A = ["-f", "lavfi", "-i", "sine=f=440:d=2"]


def generar(nombre, args):
    destino = os.path.join(TMP, nombre)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args, destino], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(destino) or os.path.getsize(destino) == 0:
        return None, (r.stderr or "").strip().splitlines()[-1:] or ["no se pudo generar"]
    return destino, None


# (nombre, argumentos de ffmpeg, esperado: web_compatible, notas)
VIDEOS = [
    ("h264_aac.mp4", V + A + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"], True),
    ("h264_high10.mp4", V + A + ["-c:v", "libx264", "-profile:v", "high10", "-pix_fmt", "yuv420p10le", "-c:a", "aac", "-shortest"], False),
    ("h264_444.mp4", V + A + ["-c:v", "libx264", "-pix_fmt", "yuv444p", "-c:a", "aac", "-shortest"], False),
    ("hevc_8bit.mp4", V + A + ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"], False),
    ("hevc_10bit_4k.mkv", V4K + A + ["-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le", "-c:a", "aac", "-shortest"], False),
    ("vp9_opus.webm", V + A + ["-c:v", "libvpx-vp9", "-b:v", "300k", "-deadline", "realtime", "-c:a", "libopus", "-shortest"], False),
    ("av1_flac.mkv", V + A + ["-c:v", "libsvtav1", "-preset", "12", "-c:a", "flac", "-shortest"], False),
    ("prores.mov", V + A + ["-c:v", "prores_ks", "-profile:v", "1", "-c:a", "pcm_s16le", "-shortest"], False),
    ("mpeg4_mp3.avi", V + A + ["-c:v", "mpeg4", "-c:a", "libmp3lame", "-shortest"], False),
    ("mjpeg.avi", V + A + ["-c:v", "mjpeg", "-c:a", "pcm_s16le", "-shortest"], False),
    ("wmv2_wma.wmv", V + A + ["-c:v", "wmv2", "-c:a", "wmav2", "-shortest"], False),
    ("flv_h264_mp3.flv", V + A + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "libmp3lame", "-shortest"], False),
    ("theora_vorbis.ogv", V + A + ["-c:v", "libtheora", "-c:a", "libvorbis", "-shortest"], False),
    ("mpeg2_ac3.mpg", V + A + ["-c:v", "mpeg2video", "-c:a", "ac3", "-shortest"], False),
    ("mpegts_h264.ts", V + A + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-f", "mpegts"], False),
    ("sin_audio.mp4", V + ["-c:v", "libx264", "-pix_fmt", "yuv420p"], True),
    ("dos_audios.mkv", V + A + ["-f", "lavfi", "-i", "sine=f=880:d=2", "-map", "0:v", "-map", "1:a", "-map", "2:a",
                                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"], False),
    ("gif_animado.gif", V + ["-vf", "fps=10"], False),
    ("rotado_90.mp4", V + A + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"], True),
]

AUDIOS = [
    ("tono.wav", A + ["-c:a", "pcm_s16le"], True),
    ("tono.flac", A + ["-c:a", "flac"], True),
    ("tono.mp3", A + ["-c:a", "libmp3lame"], True),
    ("tono.m4a", A + ["-c:a", "aac"], True),
    ("tono.ogg", A + ["-c:a", "libvorbis"], True),
    ("tono.opus", A + ["-c:a", "libopus"], True),
    ("tono.ac3", A + ["-c:a", "ac3"], False),
    ("tono.wma", A + ["-c:a", "wmav2"], False),
    ("tono_5_1.wav", ["-f", "lavfi", "-i", "sine=f=440:d=2", "-af", "pan=5.1|FL=c0|FR=c0|FC=c0|LFE=c0|BL=c0|BR=c0", "-c:a", "pcm_s16le"], True),
]


def comprobar(api, ruta, esperado_web, es_audio):
    nombre = os.path.basename(ruta)
    t0 = time.time()
    r = api.abrir(ruta)
    dt = time.time() - t0
    if "error" in r:
        print(f"  FALLA {nombre:22} no abrio: {r['error'][:110]}", flush=True)
        fallos.append(nombre)
        return
    problemas = []
    if es_audio:
        if not r.get("solo_audio"):
            problemas.append("no lo detecto como solo audio")
        if len(r.get("picos", [])) != 2000:
            problemas.append(f"picos={len(r.get('picos', []))}")
        if not (1.5 < r.get("duracion", 0) < 2.6):
            problemas.append(f"duracion={r.get('duracion')}")
        detalle = f"{r.get('codec')}, {r.get('canales')} can, {r.get('duracion', 0):.2f} s"
    else:
        if r.get("solo_audio"):
            problemas.append("lo tomo por solo audio")
        total = r.get("total_cuadros", 0)
        if total < 2:
            problemas.append(f"total_cuadros={total}")
        else:
            for n in (0, total - 1):
                c = api.cuadro(n, 160)
                if "jpg" not in c:
                    problemas.append(f"cuadro({n}): {c.get('error', '?')[:50]}")
        if nombre != "sin_audio.mp4" and nombre != "gif_animado.gif" and r.get("sin_audio"):
            problemas.append("dice que no tiene audio")
        if nombre == "sin_audio.mp4" and not r.get("sin_audio"):
            problemas.append("deberia decir sin audio")
        if nombre == "dos_audios.mkv" and r.get("pistas_audio") != 2:
            problemas.append(f"pistas_audio={r.get('pistas_audio')}")
        if nombre == "rotado_90.mp4" and r.get("rotacion") != 90:
            problemas.append(f"rotacion={r.get('rotacion')}")
        if r.get("tira_cantidad", 0) < 1:
            problemas.append("sin miniaturas")
        detalle = f"{r.get('codec')} {r.get('ancho')}x{r.get('alto')} {r.get('total_cuadros')}cu"
    if bool(r.get("web_compatible")) != esperado_web:
        problemas.append(f"web_compatible={r.get('web_compatible')} (esperado {esperado_web})")
    marca = "OK   " if not problemas else "FALLA"
    print(f"  {marca} {nombre:22} {detalle:34} {dt:5.1f} s" + ("   " + "; ".join(problemas) if problemas else ""), flush=True)
    if problemas:
        fallos.append(nombre)


def main():
    api = API()
    api.cache = os.path.join(TMP, "cache")      # los proxies de prueba no ensucian el cache real
    crear_servidor(api)
    print("=== VIDEO ===")
    for nombre, args, web in VIDEOS:
        a = list(args)
        if nombre == "rotado_90.mp4":
            base, _ = generar("_base_rot.mp4", args)
            if not base:
                saltados.append(nombre)
                print(f"  salto {nombre:22} no se pudo generar la base")
                continue
            destino = os.path.join(TMP, nombre)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-display_rotation", "90", "-i", base, "-c", "copy", destino], check=True)
            ruta = destino
        else:
            ruta, motivo = generar(nombre, a)
        if not ruta:
            saltados.append(nombre)
            print(f"  salto {nombre:22} este ffmpeg no lo genera: {motivo[0][:70]}")
            continue
        comprobar(api, ruta, web, False)

    print("=== SOLO AUDIO ===")
    for nombre, args, web in AUDIOS:
        ruta, motivo = generar(nombre, args)
        if not ruta:
            saltados.append(nombre)
            print(f"  salto {nombre:22} este ffmpeg no lo genera: {motivo[0][:70]}")
            continue
        comprobar(api, ruta, web, True)

    print("=== MP3 CON CARATULA (no es video) ===")
    mp3, _ = generar("base.mp3", A + ["-c:a", "libmp3lame"])
    png, _ = generar("caratula.png", ["-f", "lavfi", "-i", "testsrc2=s=200x200:d=1", "-frames:v", "1"])
    destino = os.path.join(TMP, "con_caratula.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-i", png, "-map", "0", "-map", "1", "-c", "copy",
                    "-id3v2_version", "3", destino], check=True)
    comprobar(api, destino, True, True)

    print("=== ARCHIVO TRUNCADO (la mitad de un .mpg) ===")
    mpg, _ = generar("completo.mpg", V + A + ["-c:v", "mpeg2video", "-c:a", "mp2", "-t", "2", "-shortest"])
    corto = os.path.join(TMP, "cortado.mpg")
    with open(mpg, "rb") as f, open(corto, "wb") as g:
        g.write(f.read(os.path.getsize(mpg) // 2))
    r = api.abrir(corto)
    if "error" in r:
        print(f"  OK    el truncado no se abre y lo explica: {r['error'][:100]}")
    else:
        c = api.cuadro(r["total_cuadros"] - 1, 160)
        bien = "jpg" in c
        print(f"  {'OK   ' if bien else 'FALLA'} abre lo que se puede leer ({r['total_cuadros']} cuadros) y sirve el ultimo")
        if not bien:
            fallos.append("truncado")

    api.cerrar()
    print()
    if saltados:
        print("Saltados (este ffmpeg no puede generarlos, NO se probaron):", ", ".join(saltados))
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
