# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Presets, lotes y linea de comandos (motor/lotes.py y moviola.py), SIN ventana.

Se mide el archivo que sale: un video con codigo de barras por cuadro y audio con tono y silencios conocidos; se corta los silencios
con un preset y se comprueba cuadro por cuadro que quedo lo que tenia que quedar, y cuanto suena (LUFS). Los subtitulos reales usan
whisper y una voz de Windows (si no estan, esa parte se saltea y lo dice).

Uso:  python -I pruebas/prueba_lotes.py
"""

import json
import os
import re
import subprocess
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"

import prueba_exportar as ex  # noqa: E402
import voz  # noqa: E402

from motor import lotes, proxy  # noqa: E402
from motor import subtitulos as sub  # noqa: E402

ok = ex.ok
TMP = ex.TMP


def fuente_con_silencios(ruta, dur=12):
    """Codigo de barras por cuadro + audio: 2 s de tono de 600 Hz y 2 s de silencio, en ese orden, durante `dur` segundos."""
    video = os.path.join(TMP, "sinaudio-%s" % os.path.basename(ruta))
    ex.crear_fuente(video, dur=dur, tono=False)
    ex.ffmpeg("-i", video, "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*600*t)*lt(mod(t,4),2)':s=48000:d=%d:c=mono" % dur,
              "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", ruta)
    return ruta


def lufs(ruta):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", ruta, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.findall(r"^\s*I:\s*(-?[\d.]+) LUFS", r.stderr, re.M)
    return float(m[-1]) if m else None


def cli(*args):
    r = subprocess.run([sys.executable, "-I", os.path.join(RAIZ, "moviola.py")] + [str(a) for a in args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def main():
    src = fuente_con_silencios(os.path.join(TMP, "silencios.mp4"))

    # --------------------------------------------------------------- 1. recetas
    print("=== 1. las recetas ===")
    lista = lotes.lista_presets()
    ok([p["clave"] for p in lista] == ["reel", "youtube", "podcast", "whatsapp", "clase"] and all(p["nota"] and p["pasos"] for p in lista), "hay 5 presets con nota y pasos", str([p["clave"] for p in lista]))
    r = lotes.preparar_preset("reel")
    ok(r["formato"] == "vertical" and r["silencios"] and r["subtitulos"]["quemar"] and r["normalizar"], "«reel» es vertical, corta silencios, subtitula quemado y normaliza")
    r2 = lotes.preparar_preset("reel", {"silencios": False, "subtitulos": False, "normalizar": False, "formato": "cuadrado", "calidad": "liviana"})
    ok(r2["silencios"] is None and r2["subtitulos"] is None and not r2["normalizar"] and r2["formato"] == "cuadrado", "los cambios se aplican encima")
    ok(lotes.PRESETS["reel"]["silencios"] is not None and lotes.PRESETS["reel"]["formato"] == "vertical", "y no tocan los de fabrica")
    r3 = lotes.preparar_preset("youtube", {"silencios": True, "subtitulos": {"letras": 30}})
    ok(r3["silencios"] == lotes.SILENCIOS and r3["subtitulos"]["letras"] == 30 and r3["subtitulos"]["srt"], "«silencios: True» usa los valores por defecto; un conjunto de ajustes se mezcla con los del preset")
    for cambios, esperado in (({"formato": "ocho_por_siete"}, "formato"), ({"encuadre": "x"}, "encuadre"), ({"calidad": "ultra"}, "calidad"), ({"perfil": "x"}, "tipo"),
                              ({"silencios": {"umbral_db": 5}}, "silencios"), ({"subtitulos": {"letras": 3}}, "letras"), ({"idioma": "klingon"}, "idioma"),
                              ({"normalizar": "si"}, "sí o no"), ({"inventado": 1}, "cambiar"), ({"subtitulos": {"quemar": False, "srt": False, "vtt": False}}, "quemarse")):
        try:
            lotes.preparar_preset("reel", cambios)
            ok(False, "se rechaza %s" % cambios)
        except lotes.ErrorLote as e:
            ok(esperado in str(e), "se rechaza %s: %s" % (cambios, e))
    try:
        lotes.preparar_preset("no_existe")
        ok(False, "preset inexistente")
    except lotes.ErrorLote as e:
        ok("reel" in str(e), "un preset que no existe lista los que hay", str(e))

    # --------------------------------------------------------------- 2. procesar y medir
    print("=== 2. procesar un video (silencios + vertical + volumen) y medir lo que sale ===")
    salida = os.path.join(TMP, "salida")
    avances, pasos = [], []
    receta = lotes.preparar_preset("reel", {"subtitulos": False})
    res = lotes.procesar(src, salida, receta, None, avances.append, None, lambda p, t: pasos.append(p))
    v, au, dur = ex.sondear(res["archivo"])
    ok(os.path.dirname(res["archivo"]) == salida and res["archivo"].endswith("silencios-v1.mp4"), "escribe en la carpeta pedida, sin pisar nada (-v1)", res["archivo"])
    ok((v["width"], v["height"]) == (1080, 1920), "vertical 1080x1920", "%sx%s" % (v["width"], v["height"]))
    ok([p["paso"] for p in res["pasos"]] == ["abrir", "silencios", "exportar"] and pasos == ["abrir", "silencios", "exportar"], "paso a paso: abrir, silencios, exportar", str(pasos))
    ok(abs(res["silencios_quitados"] - 5.52) < 0.4 and abs(dur - (12 - res["silencios_quitados"])) < 0.35, "saca ~5,5 s de silencio y el video dura lo que corresponde (~6,5 s)", "quitado %s, dura %.2f" % (res["silencios_quitados"], dur))
    ok(avances and avances == sorted(avances) and avances[-1] > 0.99 and avances[0] < 0.2, "el avance va de 0 a 1 sin retroceder", "%d avisos, de %.2f a %.2f" % (len(avances), avances[0], avances[-1]))
    nivel = lufs(res["archivo"])
    ok(nivel is not None and abs(nivel + 14.0) < 1.2, "el volumen quedo en -14 LUFS", str(nivel))

    print("=== 2b. cuadro por cuadro: queda lo que tiene que quedar ===")
    r_orig = lotes.preparar_preset("whatsapp", {"silencios": True, "calidad": "alta"})
    res2 = lotes.procesar(src, salida, r_orig)
    codigos = ex.leer_codigos(res2["archivo"])
    tiempos = [c / 30.0 for c in codigos]
    conservados = [(0, 2.08), (3.92, 6.08), (7.92, 10.08), (11.92, 12.0)]
    dentro = all(any(a - 0.13 <= t <= b + 0.13 for a, b in conservados) for t in tiempos)
    ok(dentro, "todos los cuadros que quedan son de un tramo con sonido", "fuera: %s" % [round(t, 2) for t in tiempos if not any(a - 0.13 <= t <= b + 0.13 for a, b in conservados)][:6])
    ok(not any(2.3 <= t <= 3.7 or 6.3 <= t <= 7.7 or 10.3 <= t <= 11.7 for t in tiempos), "y ninguno de adentro de un silencio")
    ok(codigos == sorted(codigos) and len(set(codigos)) == len(codigos), "en orden y sin repetidos")
    ok(abs(len(codigos) / 30.0 - (12 - res2["silencios_quitados"])) < 0.3, "la cantidad de cuadros es la esperada", "%d cuadros" % len(codigos))

    print("=== 2c. otros destinos ===")
    r_pod = lotes.preparar_preset("podcast")
    res3 = lotes.procesar(src, salida, r_pod)
    _, au3, dur3 = ex.sondear(res3["archivo"])
    ok(res3["archivo"].endswith(".mp3") and au3 is not None and abs(dur3 - 7.2) < 0.4, "«podcast» da un MP3 con los silencios largos cortados (12 s - 3 x 1,6 s)", "%.2f s" % dur3)
    ok(abs(lufs(res3["archivo"]) + 14.0) < 1.2, "y nivelado")
    # sin audio: el paso de silencios se saltea y lo dice
    mudo = os.path.join(TMP, "mudo.mp4")
    ex.crear_fuente(mudo, dur=3, tono=False)
    res4 = lotes.procesar(mudo, salida, lotes.preparar_preset("reel", {"subtitulos": False, "normalizar": False}))
    ok(res4["silencios_quitados"] == 0 and any("silencios" in a for a in res4["avisos"]) and os.path.isfile(res4["archivo"]), "un video sin audio: no corta silencios, avisa, y exporta igual", str(res4["avisos"]))

    # --------------------------------------------------------------- 3. subtitulos
    print("=== 3. subtitulos dentro del preset ===")
    real = sub.estado_transcripcion
    sub.estado_transcripcion = lambda: {"disponible": False, "whisper": "", "modelo": "", "motivo": "Para transcribir hace falta tener instalado whisper-cli."}
    try:
        res5 = lotes.procesar(src, salida, lotes.preparar_preset("youtube"))
    finally:
        sub.estado_transcripcion = real
    ok(os.path.isfile(res5["archivo"]) and res5["frases"] == 0 and any("subtítulos" in a and "whisper" in a for a in res5["avisos"]), "sin whisper el preset NO falla: exporta todo lo demas y avisa por que no hay subtitulos", str(res5["avisos"]))
    estado = sub.estado_transcripcion()
    hablado, tramos = (None, None)
    if estado["disponible"]:
        hablado, tramos = voz.video_hablado(os.path.join(TMP, "hablado.mp4"), ["Hola, esto es una prueba de subtítulos.", "Ahora hablamos de otra cosa muy distinta."], pausa=3.0)
    if not hablado:
        print("  SALTEADA  la prueba con voz real (falta %s)" % ("whisper o su modelo" if not estado["disponible"] else "una voz de Windows"))
    else:
        res6 = lotes.procesar(hablado, salida, lotes.preparar_preset("youtube", {"silencios": True, "normalizar": False}))
        srt = os.path.splitext(res6["archivo"])[0] + ".srt"
        texto = open(srt, encoding="utf-8").read().lower() if os.path.isfile(srt) else ""
        ok(os.path.isfile(srt) and "hola" in texto and "distinta" in texto, "con whisper: escribe el .srt con lo que se dijo, al lado del video", texto.replace("\n", "|")[:100])
        _, _, d6 = ex.sondear(res6["archivo"])
        ok(res6["frases"] >= 2 and res6["silencios_quitados"] > 1.5 and d6 < voz.duracion(hablado) - 1.0, "y cortó los 3 s de silencio entre las dos frases antes de transcribir (los tiempos son los del montaje cortado)", "%.1f s de %.1f" % (d6, voz.duracion(hablado)))
        res7 = lotes.procesar(hablado, salida, lotes.preparar_preset("reel", {"silencios": False, "normalizar": False}))
        ok(os.path.isfile(res7["archivo"]) and res7["frases"] >= 2, "«reel» con subtitulos quemados exporta (frases: %d)" % res7["frases"])

    # --------------------------------------------------------------- 4. proyecto .moviola
    print("=== 4. un proyecto .moviola como origen ===")
    p, _, _ = ex.armar(src)
    p.borrar_rango(2.0, 5.0)
    carpeta_p = os.path.join(TMP, "proyectos")
    os.makedirs(carpeta_p, exist_ok=True)
    pm = os.path.join(carpeta_p, "editado.moviola")
    p.guardar(pm)
    res8 = lotes.procesar(pm, salida, lotes.preparar_preset("whatsapp"))
    _, _, d8 = ex.sondear(res8["archivo"])
    ok(abs(d8 - 9.0) < 0.15, "se procesa el montaje editado (12 s - 3 s = 9 s)", "%.2f s" % d8)
    # sin su video
    roto = os.path.join(carpeta_p, "sin_video.moviola")
    datos = json.load(open(pm, encoding="utf-8"))
    for f in datos["fuentes"].values():
        f["ruta"] = os.path.join(TMP, "no-existe", "x.mp4")
    json.dump(datos, open(roto, "w", encoding="utf-8"))
    try:
        lotes.procesar(roto, salida, lotes.preparar_preset("whatsapp"))
        ok(False, "proyecto sin sus archivos")
    except lotes.ErrorLote as e:
        ok("Faltan" in str(e) and "x.mp4" in str(e), "un proyecto al que le faltan archivos: dice cuales", str(e))
    open(os.path.join(carpeta_p, "basura.moviola"), "w").write("{ no es json")
    try:
        lotes.proyecto_desde(os.path.join(carpeta_p, "basura.moviola"))
        ok(False, "proyecto roto")
    except lotes.ErrorLote as e:
        ok("No pude leer" in str(e), "un .moviola roto: error claro", str(e))

    # --------------------------------------------------------------- 5. lotes
    print("=== 5. varios archivos ===")
    carpeta_l = os.path.join(TMP, "lote")
    os.makedirs(os.path.join(carpeta_l, "sub"), exist_ok=True)
    a = fuente_con_silencios(os.path.join(carpeta_l, "a.mp4"), dur=6)
    b = os.path.join(carpeta_l, "b.mp3")
    ex.ffmpeg("-f", "lavfi", "-i", "sine=f=500:d=3", "-c:a", "libmp3lame", b)
    mal = os.path.join(carpeta_l, "roto.mp4")
    open(mal, "wb").write(os.urandom(4000))
    c = fuente_con_silencios(os.path.join(carpeta_l, "sub", "c.mp4"), dur=4)
    open(os.path.join(carpeta_l, "notas.txt"), "w").write("nada")
    lista = lotes.listar_entradas(carpeta_l)
    ok([os.path.basename(x) for x in lista] == ["a.mp4", "b.mp3", "roto.mp4"], "una carpeta aporta sus videos y audios (no las notas ni las subcarpetas)", str([os.path.basename(x) for x in lista]))
    ok([os.path.basename(x) for x in lotes.listar_entradas(carpeta_l, recursivo=True)] == ["a.mp4", "b.mp3", "roto.mp4", "c.mp4"], "con «recursivo» entra a las subcarpetas")
    ok(len(lotes.listar_entradas([os.path.join(carpeta_l, "*.mp4"), a, carpeta_l])) == 3, "los patrones (*.mp4) se expanden y lo repetido se cuenta una sola vez")
    try:
        lotes.listar_entradas([os.path.join(carpeta_l, "no_existe.mp4")])
        ok(False, "entrada inexistente")
    except lotes.ErrorLote as e:
        ok("No encontré" in str(e), "algo que no existe: error claro", str(e))
    os.makedirs(os.path.join(carpeta_l, lotes.CARPETA_SALIDA), exist_ok=True)
    ex.crear_fuente(os.path.join(carpeta_l, lotes.CARPETA_SALIDA, "viejo.mp4"), dur=1)
    ok("viejo.mp4" not in [os.path.basename(x) for x in lotes.listar_entradas(carpeta_l, recursivo=True)], "la carpeta de salida no se vuelve a procesar")

    avisos = []
    lote = lotes.procesar_lote(lista, os.path.join(TMP, "lote-sal"), lotes.preparar_preset("podcast", {"silencios": False}),
                               lambda i, n, f, nom: avisos.append((i, n, round(f, 2), nom)))
    ok(lote["ok"] == 2 and lote["fallaron"] == 1 and len(lote["resultados"]) == 3, "3 archivos con uno roto: 2 bien, 1 con error, y el lote sigue", "%s bien, %s mal" % (lote["ok"], lote["fallaron"]))
    rr = {os.path.basename(r["origen"]): r for r in lote["resultados"]}
    ok(rr["a.mp4"]["ok"] and rr["b.mp3"]["ok"] and not rr["roto.mp4"]["ok"] and "roto.mp4" in rr["roto.mp4"]["error"] and not rr["roto.mp4"].get("interno"), "el roto dice cual es y por que, sin explotar", rr["roto.mp4"]["error"][:90])
    ok(all(os.path.isfile(rr[k]["archivo"]) for k in ("a.mp4", "b.mp3")), "los otros dos tienen su archivo")
    ok({i for i, n, f, nom in avisos} == {0, 1, 2} and {n for i, n, f, nom in avisos} == {3}, "el avance cuenta archivo por archivo (i de n)")
    sobran = [f for f in os.listdir(os.path.join(TMP, "lote-sal")) if ".parcial" in f]
    ok(not sobran, "no queda nada a medias en la carpeta", str(sobran))
    lote2 = lotes.procesar_lote(lista[:2], os.path.join(TMP, "lote-sal"), lotes.preparar_preset("podcast", {"silencios": False}))
    ok(all("-v2" in r["archivo"] for r in lote2["resultados"] if r["ok"]), "volver a procesar no pisa lo anterior (-v2)")
    lote3 = lotes.procesar_lote([mal, a], os.path.join(TMP, "lote-sal3"), lotes.preparar_preset("podcast"), continuar=False)
    ok(len(lote3["resultados"]) == 1 and lote3["fallaron"] == 1, "con continuar=False se detiene en el primer error")
    lote4 = lotes.procesar_lote([a], None, lotes.preparar_preset("whatsapp", {"normalizar": False}))
    ok(lote4["ok"] == 1 and os.path.dirname(lote4["resultados"][0]["archivo"]) == os.path.join(carpeta_l, lotes.CARPETA_SALIDA), "sin carpeta: «moviola-salida» al lado del original")

    audio_con_video = lotes.procesar(b, os.path.join(TMP, "lote-sal"), lotes.preparar_preset("reel"))
    ok(audio_con_video["archivo"].endswith(".mp3") and any("solo audio" in a for a in audio_con_video["avisos"]), "un audio con una receta de video: se exporta como MP3 y lo avisa", str(audio_con_video["avisos"]))

    print("=== 5b. cancelar ===")
    ya = threading.Event()
    ya.set()
    lote5 = lotes.procesar_lote(lista[:2], os.path.join(TMP, "lote-cancel"), lotes.preparar_preset("whatsapp"), cancelar=ya)
    ok(lote5["canceladas"] == 2 and lote5["ok"] == 0 and not os.path.isdir(os.path.join(TMP, "lote-cancel")), "cancelado de antemano: no se hace nada ni se crea la carpeta")
    ev = threading.Event()
    largo = fuente_con_silencios(os.path.join(TMP, "largo.mp4"), dur=40)
    sal6 = os.path.join(TMP, "lote-cancel2")
    lote6 = lotes.procesar_lote([largo], sal6, lotes.preparar_preset("whatsapp", {"silencios": True}), lambda i, n, f, nom: ev.set() if f > 0.3 else None, ev)
    ok(lote6["canceladas"] == 1 and lote6["ok"] == 0, "cancelado a la mitad: se reporta como cancelado, no como error", str(lote6["resultados"][0].get("error")))
    ok(not [f for f in os.listdir(sal6) if f.endswith(".mp4")] if os.path.isdir(sal6) else True, "y no deja ningun archivo a medias")
    try:
        lotes.procesar_lote([], None, lotes.preparar_preset("reel"))
        ok(False, "lote vacio")
    except lotes.ErrorLote as e:
        ok("ningún archivo" in str(e), "un lote vacio: error claro")

    # --------------------------------------------------------------- 6. linea de comandos
    print("=== 6. la linea de comandos (moviola.py) ===")
    rc, out, err = cli("presets", "--json")
    ok(rc == 0 and [p["clave"] for p in json.loads(out)] == ["reel", "youtube", "podcast", "whatsapp", "clase"], "«presets --json» lista las recetas", str(rc))
    rc, out, err = cli("herramientas", "--json")
    h = json.loads(out)
    ok(rc == 0 and h["ffmpeg"] and h["ffprobe"] and "whisper" in h, "«herramientas --json» dice que hay instalado")
    rc, out, err = cli("silencios", src, "--json")
    s = json.loads(out)
    ok(rc == 0 and len(s["silencios"]) == 3 and abs(s["silencios"][0]["inicio"] - 2.1) < 0.15, "«silencios --json» encuentra los 3 silencios", str([x["inicio"] for x in s["silencios"]]))
    rc, out, err = cli("silencios", src)
    ok(rc == 0 and "3 silencios" in out, "y sin --json los cuenta en palabras", out.strip().splitlines()[-1] if out.strip() else err)
    rc, out, err = cli("medir", src, "--json")
    ok(rc == 0 and -20 < json.loads(out)["lufs"] < -5, "«medir --json» da el volumen", out.strip())
    salida_cli = os.path.join(TMP, "salida-cli")
    rc, out, err = cli("procesar", src, "--preset", "podcast", "-o", salida_cli, "--json", "--callado")
    r_cli = json.loads(out)
    ok(rc == 0 and r_cli["ok"] == 1 and os.path.isfile(r_cli["resultados"][0]["archivo"]), "«procesar --json» procesa y cuenta lo que hizo", str(rc))
    rc, out, err = cli("procesar", carpeta_l, "--preset", "whatsapp", "-o", salida_cli, "--sin-silencios")
    ok(rc == 1 and "FALLÓ  roto.mp4" in out and "OK     a.mp4" in out and "2 bien, 1 con error" in out, "con un archivo roto en la carpeta: sale con codigo 1, cuenta 2 bien y 1 mal", out.strip().splitlines()[-1] if out.strip() else err)
    rc, out, err = cli("procesar", os.path.join(TMP, "no_existe.mp4"))
    ok(rc == 1 and "No encontré" in err, "un archivo que no existe: codigo 1 y el motivo en la salida de error", err.strip())
    rc, out, err = cli("procesar", src, "--preset", "inventado")
    ok(rc == 1 and "reel" in err, "un preset que no existe: lista los que hay")
    rc, out, err = cli("procesar", src, "--formato", "nueve")
    ok(rc == 2, "un valor fuera de la lista: codigo 2 (pedido mal escrito)")
    rc, out, err = cli("procesar", src, "--silencios", "--sin-silencios")
    ok(rc == 2, "dos opciones contradictorias: codigo 2")
    rc, out, err = cli("exportar", src, "--formato", "cuadrado", "--normalizar", "-o", salida_cli, "--json", "--callado")
    r_e = json.loads(out)
    v_e, _, _ = ex.sondear(r_e["archivo"])
    ok(rc == 0 and (v_e["width"], v_e["height"]) == (1080, 1080), "«exportar» sin recetas: cuadrado 1080x1080")
    rc, out, err = cli("exportar", src, "--subtitulos", "quemar", "-o", salida_cli)
    ok(rc == 1 and "subtítulos" in err, "pedir subtitulos de un proyecto que no tiene frases: error claro")
    rc, out, err = cli("exportar", pm, "--subtitulos", "gif", "-o", salida_cli)
    ok(rc == 1 and "quemar, srt o vtt" in err, "subtitulos mal pedidos: dice como se piden")
    rc, out, err = cli("exportar", pm, "--formato", "wav", "-o", salida_cli, "--callado")
    ok(rc == 0 and "Listo" in out, "«exportar» desde un .moviola")
    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
