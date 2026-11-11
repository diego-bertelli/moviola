# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del proxy de reproduccion (motor/proxy.py).

Uso:  python -I pruebas/prueba_proxy.py

Lo critico: el proxy conserva la tabla de tiempos del original (mismos cuadros, mismos
instantes), porque la interfaz calcula el cuadro de una pausa con la tabla del original.
Los videos del Escritorio de Diego son opcionales: si no estan, se saltean.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

from motor import proxy  # noqa: E402
from motor.video import Video  # noqa: E402

ESCRITORIO = os.environ.get("MOVIOLA_VIDEOS_REALES", "")   # carpeta con dos videos reales (uno VFR y un MPEG-PS); sin ella esas partes se saltean
VFR = os.path.join(ESCRITORIO, "real-vfr.mp4")
MPG = os.path.join(ESCRITORIO, "real-mpeg2.mpg")

TMP = tempfile.mkdtemp(prefix="prueba-proxy-")
CACHE = os.path.join(TMP, "cache")
fallos = []
V = ["-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=3"]
A = ["-f", "lavfi", "-i", "sine=f=440:d=3"]


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def generar_origen(nombre, args):
    destino = os.path.join(TMP, nombre)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args, destino], capture_output=True, text=True)
    return destino if r.returncode == 0 and os.path.getsize(destino) > 0 else None


def probe(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", ruta],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def flujos(ruta):
    d = probe(ruta)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return v, a, d["format"]


def comparar_tablas(original, copia):
    """Mismos cuadros, mismos instantes (tolerancia 2 ms por el cambio de base de tiempo)."""
    with Video(original) as a, Video(copia) as b:
        ta, tb = a.tabla_tiempos(), b.tabla_tiempos()
    if len(ta) != len(tb):
        return False, f"{len(ta)} cuadros contra {len(tb)}"
    difs = [abs(x - y) for x, y in zip(ta, tb)]
    peor = max(difs)
    fuera = sum(1 for d in difs if d > 0.002)
    # Un cuadro del VFR real llega con el tiempo 13 ms hacia atras desde el propio decoder
    # (el proxy lo obliga a ser creciente). Se tolera menos de un cuadro y muy pocos casos.
    bien = peor < 0.040 and fuera <= max(3, len(difs) // 1000)
    return bien, f"peor diferencia {peor * 1000:.2f} ms; {fuera} de {len(difs)} cuadros pasan de 2 ms"


def revisar(nombre, origen, esperar_video=True, esperar_audio=True, **opciones):
    """Genera el proxy y verifica todo lo que importa. Devuelve el resultado de generar()."""
    avance = []
    t0 = time.time()
    try:
        r = proxy.generar(origen, CACHE, avance.append, **opciones)
    except Exception as e:
        ok(False, f"{nombre}: se genera el proxy", repr(e)[:120])
        return None
    dt = time.time() - t0
    v, a, fmt = flujos(r["archivo"])
    ov, oa, ofmt = flujos(origen)
    problemas = []
    if esperar_video:
        if not v:
            problemas.append("sin video")
        else:
            if v["codec_name"] != "h264" or v["pix_fmt"] != "yuv420p":
                problemas.append(f"{v['codec_name']}/{v['pix_fmt']}")
            ancho, alto = int(v["width"]), int(v["height"])
            if ancho % 2 or alto % 2:
                problemas.append(f"dimensiones impares {ancho}x{alto}")
            if min(ancho, alto) > 720:
                problemas.append(f"lado corto {min(ancho, alto)} > 720")
            if v.get("color_transfer") in ("smpte2084", "arib-std-b67"):
                problemas.append("sigue siendo HDR")
            if ov and (ancho > int(ov["width"]) and alto > int(ov["height"])) and not opciones:
                problemas.append("agrando la imagen")
    elif v:
        problemas.append("un audio no deberia traer video")
    if esperar_audio:
        if not a:
            problemas.append("sin audio")
        elif a[0]["codec_name"] != "aac" or int(a[0]["channels"]) != 2:
            problemas.append(f"audio {a[0]['codec_name']} {a[0]['channels']}ch")
    elif a:
        problemas.append("tiene audio y el original no")
    ok(not problemas, f"{nombre}: formato del proxy", "; ".join(problemas) or f"{dt:.1f} s")
    if esperar_video and ov:
        igual, detalle = comparar_tablas(origen, r["archivo"])
        ok(igual, f"{nombre}: MISMA tabla de tiempos que el original", detalle)
    else:
        dur_o, dur_p = float(ofmt["duration"]), float(fmt["duration"])
        ok(abs(dur_o - dur_p) < 0.1, f"{nombre}: misma duracion", f"{dur_o:.2f} s contra {dur_p:.2f} s")
    creciente = all(b >= a2 for a2, b in zip(avance, avance[1:]))
    ok(bool(avance) and creciente and 0 <= avance[0] <= 1 and avance[-1] == 1.0,
       f"{nombre}: el progreso va de 0 a 1 sin retroceder", f"{len(avance)} avisos, ultimo {avance[-1] if avance else None}")
    return r


def main():
    print("=== 1. formatos que el WebView no reproduce ===")
    casos = [
        ("hevc 8 bits", "hevc.mp4", V + A + ["-c:v", "libx265", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"], {}),
        ("h264 10 bits", "h264_10b.mp4", V + A + ["-c:v", "libx264", "-profile:v", "high10", "-pix_fmt", "yuv420p10le", "-c:a", "aac", "-shortest"], {}),
        ("h264 4:4:4", "h264_444.mp4", V + A + ["-c:v", "libx264", "-pix_fmt", "yuv444p", "-c:a", "aac", "-shortest"], {}),
        ("vp9 + opus (webm)", "vp9.webm", V + A + ["-c:v", "libvpx-vp9", "-b:v", "300k", "-deadline", "realtime", "-c:a", "libopus", "-shortest"], {}),
        ("prores + pcm (mov)", "prores.mov", V + A + ["-c:v", "prores_ks", "-profile:v", "1", "-c:a", "pcm_s16le", "-shortest"], {}),
        ("mpeg2 + ac3", "mpeg2.mpg", V + A + ["-c:v", "mpeg2video", "-c:a", "ac3", "-shortest"], {}),
        ("avi mpeg4 + mp3", "viejo.avi", V + A + ["-c:v", "mpeg4", "-c:a", "libmp3lame", "-shortest"], {}),
    ]
    for etiqueta, nombre, args, opciones in casos:
        origen = generar_origen(nombre, args)
        if origen:
            revisar(etiqueta, origen, **opciones)
        else:
            print(f"  salto {etiqueta}: este ffmpeg no lo genera")

    print("=== 2. sin audio, dos audios, rotacion, 4K, HDR ===")
    sin_audio = generar_origen("sin_audio.mkv", V + ["-c:v", "libx265"])
    revisar("sin audio", sin_audio, esperar_audio=False)

    dos = generar_origen("dos_audios.mkv", V + A + ["-f", "lavfi", "-i", "sine=f=880:d=3", "-map", "0:v", "-map", "1:a", "-map", "2:a",
                                                    "-c:v", "libx264", "-c:a", "aac", "-shortest"])
    r0 = revisar("dos audios, la primera", dos)
    r1 = revisar("dos audios, la segunda", dos, pista_audio=1)
    ok(bool(r0) and bool(r1) and r0["archivo"] != r1["archivo"], "cada pista de audio tiene su propio proxy")

    base = generar_origen("base_rot.mp4", V + A + ["-c:v", "libx264", "-c:a", "aac", "-shortest"])
    rotado = os.path.join(TMP, "rotado.mkv")
    ffmpeg("-display_rotation", "90", "-i", base, "-c", "copy", rotado)
    r = revisar("rotado 90 (mkv)", rotado)
    if r:
        v, _, _ = flujos(r["archivo"])
        ok((int(v["width"]), int(v["height"])) == (240, 320), "la rotacion queda aplicada al proxy", f"{v['width']}x{v['height']}")

    grande = generar_origen("4k.mkv", ["-f", "lavfi", "-i", "testsrc2=s=3840x2160:r=30:d=2"] + A + ["-c:v", "libx265", "-preset", "ultrafast",
                                                                                                      "-pix_fmt", "yuv420p10le", "-c:a", "aac", "-shortest"])
    r = revisar("4K hevc 10 bits", grande)
    if r:
        v, _, _ = flujos(r["archivo"])
        ok((int(v["width"]), int(v["height"])) == (1280, 720), "4K baja a 1280x720", f"{v['width']}x{v['height']}")

    hdr = generar_origen("hdr.mkv", V + A + ["-c:v", "libx265", "-pix_fmt", "yuv420p10le",
                                              "-x265-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                                              "-c:a", "aac", "-shortest"])
    ov, _, _ = flujos(hdr)
    ok(ov.get("color_transfer") == "smpte2084", "el archivo de prueba es HDR de verdad", ov.get("color_transfer"))
    revisar("HDR a SDR", hdr)

    print("=== 3. solo audio ===")
    for nombre, args in (("tono.ac3", A + ["-c:a", "ac3"]), ("tono.wma", A + ["-c:a", "wmav2"]), ("tono.flac", A + ["-c:a", "flac"])):
        origen = generar_origen(nombre, args)
        r = revisar(nombre, origen, esperar_video=False)
        if r:
            ok(r["archivo"].endswith(".m4a"), f"{nombre}: sale como .m4a")

    print("=== 4. video de framerate variable (el de Diego) ===")
    if os.path.isfile(VFR):
        t0 = time.time()
        r = revisar("VFR 15 min", VFR)
        if r:
            print(f"  (proxy de 15 min en {time.time() - t0:.0f} s)")
    else:
        print("  (sin el video, se saltea)")

    print("=== 5. MPEG-2 entrelazado, 5.1 (el de Diego) ===")
    if os.path.isfile(MPG):
        t0 = time.time()
        r = revisar("1080i 5.1", MPG)
        if r:
            print(f"  (proxy de 5:25 en {time.time() - t0:.0f} s)")
            v, _, _ = flujos(r["archivo"])
            ok((int(v["width"]), int(v["height"])) == (1280, 720), "baja a 1280x720", f"{v['width']}x{v['height']}")
            # ya no tiene que estar entrelazado
            p = subprocess.run(["ffmpeg", "-v", "info", "-i", r["archivo"], "-vf", "idet", "-frames:v", "600", "-f", "null", "-"],
                               capture_output=True, text=True)
            # idet imprime un bloque por cada instancia del filtro: vale el ULTIMO
            patron = r"Multi frame detection: TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)"
            ms = re.findall(patron, p.stderr)
            po = subprocess.run(["ffmpeg", "-v", "info", "-ss", "0", "-i", MPG, "-vf", "idet", "-frames:v", "600", "-an", "-f", "null", "-"],
                                capture_output=True, text=True)
            mo = re.findall(patron, po.stderr)
            if ms and mo:
                otff, obff, oprog = map(int, mo[-1])
                ok(otff + obff > 5 * max(1, oprog), "el original se mide como entrelazado (la medida sirve)", f"TFF {otff}, progresivos {oprog}")
                tff, bff, prog = map(int, ms[-1])
                ok(prog > 8 * max(1, tff + bff), "el proxy ya no esta entrelazado", f"progresivos {prog}, entrelazados {tff + bff}")
            else:
                ok(False, "se pudo medir el entrelazado")
            # sincronia: el desfase audio-video del proxy sigue al del original
            ov, oa, _ = flujos(MPG)
            pv, pa, _ = flujos(r["archivo"])
            desfase_o = float(oa[0]["start_time"]) - float(ov["start_time"])
            desfase_p = float(pa[0]["start_time"]) - float(pv["start_time"])
            ok(abs(desfase_o - desfase_p) < 0.06, "el desfase entre audio y video se conserva",
               f"original {desfase_o * 1000:.0f} ms, proxy {desfase_p * 1000:.0f} ms")
            ok(abs(float(pv["start_time"])) < 0.05, "el proxy arranca en cero", f"{float(pv['start_time']):.3f} s")
    else:
        print("  (sin el video, se saltea)")

    print("=== 6. cache ===")
    origen = generar_origen("cache.mp4", V + A + ["-c:v", "libx265", "-c:a", "aac", "-shortest"])
    r1 = proxy.generar(origen, CACHE)
    t0 = time.time()
    r2 = proxy.generar(origen, CACHE)
    dt = time.time() - t0
    ok(r1["reusado"] is False and r2["reusado"] is True and r1["archivo"] == r2["archivo"], "la segunda vez reutiliza")
    ok(dt < 1.0, "y casi no tarda", f"{dt * 1000:.0f} ms")
    time.sleep(0.05)
    os.utime(origen, (time.time() + 5, time.time() + 5))
    ok(proxy.ruta_proxy(origen, CACHE) != r1["archivo"], "si el original cambia, la ruta del proxy cambia")

    print("=== 7. proxy corrupto o truncado ===")
    origen = generar_origen("trunc.mp4", V + A + ["-c:v", "libx265", "-c:a", "aac", "-shortest"])
    r = proxy.generar(origen, CACHE)
    tam = os.path.getsize(r["archivo"])
    ok(proxy.hay_proxy(origen, CACHE) == r["archivo"], "(control) el proxy entero SI se da por bueno")
    with open(r["archivo"], "r+b") as f:
        f.truncate(tam // 2)
    ok(proxy.hay_proxy(origen, CACHE) is None, "un proxy truncado a la mitad NO se da por bueno")
    r2 = proxy.generar(origen, CACHE)
    ok(r2["reusado"] is False and proxy.hay_proxy(origen, CACHE) == r2["archivo"], "se regenera bien")
    with open(r["archivo"], "wb") as f:
        f.write(b"basura")
    ok(proxy.hay_proxy(origen, CACHE) is None, "un archivo de basura tampoco")

    print("=== 8. archivos que no son medios ===")
    txt = os.path.join(TMP, "texto.mp4")
    with open(txt, "wb") as f:
        f.write(b"esto no es un video" * 100)
    try:
        proxy.generar(txt, CACHE)
        ok(False, "un archivo basura da ProxyError")
    except proxy.ProxyError as e:
        ok(True, "un archivo basura da ProxyError con un mensaje claro", str(e))
    except Exception as e:
        ok(False, "un archivo basura da ProxyError", repr(e))
    try:
        proxy.generar(os.path.join(TMP, "no_existe.mp4"), CACHE)
        ok(False, "un archivo inexistente da ProxyError")
    except proxy.ProxyError:
        ok(True, "un archivo inexistente da ProxyError")

    print("=== 9. cancelar a mitad ===")
    largo = os.path.join(TMP, "largo.mkv")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=120", "-f", "lavfi", "-i", "sine=f=300:d=120",
           "-c:v", "libx265", "-preset", "ultrafast", "-c:a", "aac", "-shortest", largo)
    evento = threading.Event()
    resultado = {}

    def trabajar():
        try:
            proxy.generar(largo, CACHE, cancelar=evento)
            resultado["fin"] = "completo"
        except proxy.Cancelado:
            resultado["fin"] = "cancelado"
        except Exception as e:
            resultado["fin"] = repr(e)

    h = threading.Thread(target=trabajar)
    h.start()
    time.sleep(1.5)
    evento.set()
    h.join(30)
    ok(resultado.get("fin") == "cancelado", "cancelar corta la transcodificacion", resultado.get("fin"))
    restos = [n for n in os.listdir(CACHE) if "largo" in n]
    ok(not restos, "y no deja archivos a medias", str(restos))

    print("=== 10. dos pedidos a la vez para el mismo archivo ===")
    origen = generar_origen("doble.mp4", V + A + ["-c:v", "libx265", "-c:a", "aac", "-shortest"])
    salidas = []

    def pedir():
        salidas.append(proxy.generar(origen, CACHE))

    hs = [threading.Thread(target=pedir) for _ in range(3)]
    for x in hs:
        x.start()
    for x in hs:
        x.join(60)
    ok(len(salidas) == 3 and sum(1 for s in salidas if not s["reusado"]) == 1,
       "se transcodifica una sola vez; los otros dos reutilizan", str([s["reusado"] for s in salidas]))
    ok(len({s["archivo"] for s in salidas}) == 1, "y los tres reciben el mismo archivo")

    print("=== 11. limpieza del cache ===")
    antes = len(os.listdir(CACHE))
    borrados = proxy.limpiar(CACHE, max_bytes=1)
    ok(borrados > 0 and len(os.listdir(CACHE)) < antes, "limpiar() borra los menos usados al pasar el limite", f"{borrados} borrados")

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
