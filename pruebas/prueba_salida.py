# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 6 (salida): los tipos de archivo de video (H.264, H.265, AV1, VP9, ProRes, MKV, GIF), las calidades y el audio Opus / OGG.

Uso:  python -I pruebas/prueba_salida.py

Cada archivo se abre con ffprobe (contenedor, codec, formato de pixel, sonido, cuadros, duracion) y se MIDE contra la fuente:
los cuadros salen en orden (codigo de barras), la calidad con VMAF (solo aca: libvmaf no hace falta para usar el programa),
el tono del audio, el tamano del GIF y su duracion.
"""

import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

import av  # noqa: E402
from PIL import ImageChops  # noqa: E402

import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402
from motor import exportar  # noqa: E402
from motor import gpu  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def sonda(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries", "format=format_name,duration,size:stream=codec_type,codec_name,pix_fmt,width,height,nb_read_frames,r_frame_rate",
                        "-of", "json", ruta], capture_output=True, text=True)
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return d["format"], v, a


def codigos(ruta):
    """El numero de cada cuadro (codigo de barras). Si PyAV no sabe decodificar ese codec se pasa por ffmpeg a un MP4 sin perdida."""
    try:
        c = ex.leer_codigos(ruta)
        if c:
            return c
    except Exception:
        pass
    llano = os.path.join(TMP, "llano.mp4")
    ex.ffmpeg("-i", ruta, "-an", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p", llano)
    return ex.leer_codigos(llano)


def vmaf(salida, referencia):
    log = "vmaf.json"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", salida, "-i", referencia, "-lavfi",
                    "[0:v]setpts=PTS-STARTPTS,fps=30,format=yuv420p[a];[1:v]setpts=PTS-STARTPTS,fps=30,format=yuv420p[b];[a][b]libvmaf=log_fmt=json:log_path=%s:n_threads=4" % log,
                    "-f", "null", "-"], check=True, cwd=TMP)
    with open(os.path.join(TMP, log), encoding="utf-8") as f:
        return float(json.load(f)["pooled_metrics"]["vmaf"]["mean"])


def exportar_perfil(p, nombre, **kw):
    r = ex.exportar_a(p, nombre, **kw)
    return r["archivo"], r


def main():
    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=3)
    ref = os.path.join(TMP, "ref.mp4")                       # la fuente decodificada como referencia de calidad (mismo tamano y cuadros)
    ex.ffmpeg("-i", src, "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", "-an", ref)

    print("=== 1. el catalogo ===")
    ok(set(exportar.PERFILES) == {"mp4_h264", "mp4_h265", "mp4_av1", "webm_vp9", "mov_prores", "mkv_h264", "gif"}, "los 7 tipos de archivo de video", str(list(exportar.PERFILES)))
    ok(all(PF["nombre"] and PF["nota"] and PF["ext"].startswith(".") for PF in exportar.PERFILES.values()), "cada uno con su nombre, su nota y su extension")
    ok({"opus", "ogg"} <= set(exportar.FORMATOS_AUDIO), "y el audio suma Opus y OGG")

    print("=== 2. cada tipo de archivo, abierto con ffprobe y medido ===")
    esperados = {  # perfil: (contenedor contiene, codec de video, formato de pixel, codec de audio, extension)
        "mp4_h264": ("mp4", "h264", "yuv420p", "aac", ".mp4"),
        "mp4_h265": ("mp4", "hevc", "yuv420p", "aac", ".mp4"),
        "mp4_av1": ("mp4", "av1", "yuv420p", "aac", ".mp4"),
        "webm_vp9": ("webm", "vp9", "yuv420p", "opus", ".webm"),
        "mov_prores": ("mov", "prores", "yuv422p10le", "pcm_s16le", ".mov"),
        "mkv_h264": ("matroska", "h264", "yuv420p", "aac", ".mkv"),
    }
    puntajes = {}
    for perfil, (cont, codec, pix, acodec, ext) in esperados.items():
        p, _, _ = ex.armar(src)
        arch, r = exportar_perfil(p, "o_" + perfil, perfil=perfil)
        fmt, v, a = sonda(arch)
        malo = []
        if not arch.endswith(ext): malo.append("extension " + arch)
        if cont not in fmt["format_name"]: malo.append("contenedor " + fmt["format_name"])
        if v["codec_name"] != codec: malo.append("codec " + v["codec_name"])
        if v["pix_fmt"] != pix: malo.append("pixel " + v["pix_fmt"])
        if a is None or a["codec_name"] != acodec: malo.append("audio " + str(a and a["codec_name"]))
        if (v["width"], v["height"]) != (640, 360): malo.append("tamano %sx%s" % (v["width"], v["height"]))
        if int(v["nb_read_frames"]) != 90: malo.append("cuadros " + v["nb_read_frames"])
        if abs(float(fmt["duration"]) - 3.0) > 0.1: malo.append("duracion " + fmt["duration"])
        ok(not malo, "%s: %s / %s / %s, 640x360, 90 cuadros, 3 s" % (perfil, cont, codec, acodec), "; ".join(malo) + "  (%d KB)" % (int(fmt["size"]) // 1024))
        cu = codigos(arch)
        ok(cu == list(range(90)), "%s: los 90 cuadros salen en orden (codigo de barras)" % perfil, str(cu[:4]) + "..." + str(cu[-3:]))
        puntajes[perfil] = vmaf(arch, ref)
        ok(puntajes[perfil] > (95 if perfil == "mov_prores" else 80), "%s: calidad VMAF %.1f" % (perfil, puntajes[perfil]))
        m = ex.muestras(arch)
        ok(abs(ex.frecuencia(m, 0.25, 0.75) - 400) < 15 and abs(ex.frecuencia(m, 2.25, 2.75) - 500) < 15, "%s: el sonido es el de la fuente (400 Hz y despues 500 Hz)" % perfil,
           "%.0f / %.0f Hz" % (ex.frecuencia(m, 0.25, 0.75), ex.frecuencia(m, 2.25, 2.75)))
    print("      VMAF:", {k: round(v, 1) for k, v in puntajes.items()})

    print("=== 3. calidades ===")
    pesos, calid = {}, {}
    for q in exportar.CALIDADES:
        p, _, _ = ex.armar(src)
        arch, _ = exportar_perfil(p, "q_h264_" + q, calidad=q)
        pesos[q] = os.path.getsize(arch)
        calid[q] = vmaf(arch, ref)
    ok(pesos["alta"] > pesos["equilibrada"] > pesos["liviana"], "H.264: mas calidad, archivo mas grande (alta > equilibrada > liviana)", str(pesos))
    ok(calid["alta"] > calid["equilibrada"] > calid["liviana"] - 0.01 and calid["alta"] > calid["liviana"], "y la calidad medida baja en el mismo orden", str({k: round(v, 1) for k, v in calid.items()}))
    for perfil in ("mp4_h265", "webm_vp9", "mp4_av1"):
        p, _, _ = ex.armar(src)
        a_, _ = exportar_perfil(p, "q_%s_alta" % perfil, perfil=perfil, calidad="alta")
        p, _, _ = ex.armar(src)
        l_, _ = exportar_perfil(p, "q_%s_liviana" % perfil, perfil=perfil, calidad="liviana")
        ok(os.path.getsize(a_) > os.path.getsize(l_), "%s: alta pesa mas que liviana" % perfil, "%d KB contra %d KB" % (os.path.getsize(a_) // 1024, os.path.getsize(l_) // 1024))
    p, _, _ = ex.armar(src)
    a_, _ = exportar_perfil(p, "q_prores_a", perfil="mov_prores", calidad="alta")
    p, _, _ = ex.armar(src)
    l_, _ = exportar_perfil(p, "q_prores_l", perfil="mov_prores", calidad="liviana")
    ok(os.path.getsize(a_) == os.path.getsize(l_), "ProRes no tiene calidad para elegir: sale igual", "%d contra %d" % (os.path.getsize(a_), os.path.getsize(l_)))

    print("=== 4. con otro formato de imagen y con subtitulos ===")
    p, _, _ = ex.armar(src)
    arch, r = exportar_perfil(p, "o_vertical_webm", perfil="webm_vp9", formato="vertical")
    fmt, v, a = sonda(arch)
    ok((v["width"], v["height"]) == (1080, 1920) and v["codec_name"] == "vp9", "WebM vertical: 1080x1920", "%sx%s" % (v["width"], v["height"]))
    p, _, _ = ex.armar(src)
    p.subtitulo_agregar(1.0, 2.0, "HOLA MUNDO")
    base = im.todos_los_cuadros(exportar_perfil(ex.armar(src)[0], "o_base_mkv", perfil="mkv_h264")[0])
    con, r = exportar_perfil(p, "o_subs_mkv", perfil="mkv_h264", subtitulos={"quemar": True, "srt": True})
    cu = im.todos_los_cuadros(con)
    d1, d2 = im.dif_media(cu[45], base[45]), im.dif_media(cu[15], base[15])
    ok(d1 > 1.0 and d1 > 4 * d2 and len(r["subtitulos"]) == 1 and r["subtitulos"][0].endswith(".srt") and "o_subs_mkv" in r["subtitulos"][0], "MKV con subtitulos quemados y .srt al lado", f"{d1:.1f} / {d2:.1f}")

    print("=== 5. GIF ===")
    for ancho, fps, nombre in ((480, 10, "g1"), (240, 15, "g2"), (320, 25, "g3")):
        p, _, _ = ex.armar(src)
        arch, r = exportar_perfil(p, "gif_" + nombre, perfil="gif", gif={"ancho": ancho, "fps": fps})
        fmt, v, a = sonda(arch)
        esp_alto = round(360 * ancho / 640 / 2) * 2
        ok(arch.endswith(".gif") and v["codec_name"] == "gif" and a is None and v["width"] == ancho and abs(v["height"] - esp_alto) <= 2,
           "GIF %d px a %d cuadros/s: codec gif, sin sonido, %dx%d" % (ancho, fps, v["width"], v["height"]), "esperado alto %d" % esp_alto)
        ok(abs(int(v["nb_read_frames"]) - 3 * fps) <= 1, "con %d cuadros (3 s a %d por segundo)" % (3 * fps, fps), v["nb_read_frames"])
        ok(abs(float(fmt["duration"]) - 3.0) < 0.15, "y dura 3 s (los GIF miden el cuadro en centesimas: la duracion no se corre)", fmt["duration"])
    cu = im.todos_los_cuadros(arch)
    base_g = im.todos_los_cuadros(exportar_perfil(ex.armar(src)[0], "gif_ref", formato="original")[0])
    mitad = cu[len(cu) // 2].convert("RGB")
    ref_img = base_g[len(base_g) // 2].resize(mitad.size)
    ok(im.dif_media(mitad, ref_img) < 22, "la imagen del GIF se parece al video (paleta de 256 colores)", f"{im.dif_media(mitad, ref_img):.1f}")
    p, _, _ = ex.armar(src)
    p.subtitulo_agregar(1.0, 2.0, "HOLA MUNDO")
    gcon, _ = exportar_perfil(p, "gif_subs", perfil="gif", gif={"ancho": 320, "fps": 10}, subtitulos={"quemar": True})
    gsin, _ = exportar_perfil(ex.armar(src)[0], "gif_sinsubs", perfil="gif", gif={"ancho": 320, "fps": 10})
    c1, c2 = im.todos_los_cuadros(gcon), im.todos_los_cuadros(gsin)
    ok(im.dif_media(c1[15], c2[15]) > 2 * max(im.dif_media(c1[5], c2[5]), 0.5), "un GIF con subtitulos quemados los muestra en su momento")
    largo = exportar.GIF_DURACION_MAX
    exportar.GIF_DURACION_MAX = 1.0
    try:
        p, _, _ = ex.armar(src)
        exportar_perfil(p, "gif_largo", perfil="gif")
        ok(False, "un GIF demasiado largo se rechaza")
    except exportar.ExportError as e:
        ok("pesaría" in str(e), "un GIF demasiado largo: error claro", str(e))
    finally:
        exportar.GIF_DURACION_MAX = largo
    for malo, kw in (("ancho 10", {"ancho": 10}), ("ancho 5000", {"ancho": 5000}), ("7 cuadros por segundo", {"fps": 7})):
        try:
            exportar_perfil(ex.armar(src)[0], "gif_malo", perfil="gif", gif=kw)
            ok(False, "GIF con " + malo + " se rechaza")
        except exportar.ExportError as e:
            ok(True, "GIF con " + malo + ": error claro", str(e))

    print("=== 6. audio Opus y OGG ===")
    for formato, codec, ext in (("opus", "opus", ".opus"), ("ogg", "vorbis", ".ogg")):
        p, _, _ = ex.armar(src)
        arch, r = exportar_perfil(p, "a_" + formato, formato=formato)
        fmt, v, a = sonda(arch)
        m = ex.muestras(arch)
        ok(arch.endswith(ext) and v is None and a["codec_name"] == codec and abs(float(fmt["duration"]) - 3.0) < 0.1 and abs(ex.frecuencia(m, 0.25, 0.75) - 400) < 15,
           "%s: archivo %s, codec %s, 3 s y el tono de 400 Hz" % (formato.upper(), ext, codec), "%s %s %s" % (fmt["format_name"], a["codec_name"], fmt["duration"]))

    print("=== 7. errores ===")
    for malo, kw in (("un tipo de archivo que no existe", {"perfil": "avi"}), ("una calidad que no existe", {"calidad": "perfecta"})):
        try:
            exportar_perfil(ex.armar(src)[0], "e_malo", **kw)
            ok(False, malo + " se rechaza")
        except exportar.ExportError as e:
            ok(True, malo + ": error claro", str(e))
    ok(not [f for f in os.listdir(os.path.join(TMP, "salida-e_malo")) if f.endswith(".parcial.mp4")] if os.path.isdir(os.path.join(TMP, "salida-e_malo")) else True, "un error no deja archivos a medias")

    print("=== 8. H.265 por hardware (si esta PC puede) ===")
    det = gpu.detectar()
    hev = gpu.codificador_hevc_disponible(det)
    print("      codificadores HEVC que pasaron la prueba:", [n for n in gpu.PREFERENCIA_HEVC if (det["codificadores"].get(n) or {}).get("ok")])
    ok(gpu.codificador_hevc_disponible(None) is None, "sin deteccion no hay codificador de H.265")
    if not hev:
        print("  SALTEADA  esta PC no tiene codificador H.265 por hardware que pase la prueba")
    else:
        p, _, _ = ex.armar(src)
        arch, r = exportar_perfil(p, "gpu_h265", perfil="mp4_h265", codificador=hev)
        fmt, v, a = sonda(arch)
        ok(v["codec_name"] == "hevc" and int(v["nb_read_frames"]) == 90 and codigos(arch) == list(range(90)) and (r["usado"] == "gpu" or r["respaldo"]),
           "H.265 con %s: sale H.265 completo (%s%s)" % (hev, r["usado"], ", con respaldo al procesador" if r["respaldo"] else ""), r["motivo_respaldo"])
    p, _, _ = ex.armar(src)
    arch, r = exportar_perfil(p, "gpu_ignorado", perfil="webm_vp9", codificador="h264_amf")
    ok(r["usado"] == "cpu" and not r["respaldo"] and sonda(arch)[1]["codec_name"] == "vp9", "un tipo de archivo sin codificador por hardware (VP9) ignora el pedido de GPU y usa el procesador")

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
