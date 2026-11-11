# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 8 (bajar de YouTube): la validacion de direcciones, los argumentos que se le pasan a yt-dlp, los errores en palabras claras,
el avance, cancelar, y la API, SIN internet: se usa un yt-dlp de mentira (pruebas/falso_ytdlp.py) que habla como el verdadero.

Uso:  python -I pruebas/prueba_descargas.py
"""

import json
import os
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-descargas-"), "ajustes.json")
TMP = tempfile.mkdtemp(prefix="prueba-descargas-tmp-")
REGISTRO = os.path.join(TMP, "registro.jsonl")
os.environ["MOVIOLA_YTDLP"] = os.path.join(AQUI, "falso_ytdlp.py")
os.environ["FALSO_YTDLP_REGISTRO"] = REGISTRO
os.environ["MOVIOLA_DESCARGAS"] = os.path.join(TMP, "bajados")

import app  # noqa: E402
from motor import descargas  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def da_error(f, *a):
    try:
        f(*a)
    except descargas.ErrorDescarga as e:
        return str(e)
    return None


def argumentos():
    with open(REGISTRO, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def esperar_estado(api, fin, tiempo=60):
    t0 = time.time()
    while time.time() - t0 < tiempo:
        e = api.descargar_estado()
        if e["estado"] in fin:
            return e
        time.sleep(0.2)
    return api.descargar_estado()


def main():
    print("=== 1. direcciones ===")
    buenas = {
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&t=30s&si=abc": "dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=5": "dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/abcDEF12345": "abcDEF12345",
        "youtu.be/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "  https://www.youtube.com/watch?v=dQw4w9WgXcQ  ": "dQw4w9WgXcQ",
    }
    malas = []
    for url, vid in buenas.items():
        try:
            if descargas.validar_url(url) != "https://www.youtube.com/watch?v=" + vid:
                malas.append(url)
        except descargas.ErrorDescarga as e:
            malas.append((url, str(e)))
    ok(not malas, "las direcciones de YouTube se reconocen y se limpian (sin lista, tiempo ni rastreo)", str(malas))
    for malo, url in (("vacia", ""), ("de otro sitio", "https://vimeo.com/123456"), ("de un sitio que imita a YouTube", "https://youtube.com.malo.com/watch?v=dQw4w9WgXcQ"),
                      ("con usuario y clave", "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ"), ("sin https", "http://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                      ("una lista", "https://www.youtube.com/playlist?list=PLabc"), ("un canal", "https://www.youtube.com/@canal"), ("sin el video", "https://www.youtube.com/watch"),
                      ("con un id raro", "https://www.youtube.com/watch?v=--exec"), ("que parece una opcion", "--version"), ("con espacios", "https://www.youtube.com/watch?v=dQw4w9WgXcQ && calc"),
                      ("con saltos de linea", "https://www.youtube.com/watch?v=dQw4w9WgXcQ\\nhttps://x"), ("que no es texto", 5), ("enorme", "https://www.youtube.com/watch?v=" + "a" * 400)):
        e = da_error(descargas.validar_url, url.replace("\\n", "\n") if isinstance(url, str) else url)
        ok(e is not None, "direccion " + malo + ": se rechaza con una frase clara", e)

    print("=== 2. la herramienta ===")
    e = descargas.estado()
    ok(e["disponible"] is True and e["motivo"] == "", "con yt-dlp (el de mentira) el estado dice que se puede")
    os.environ["MOVIOLA_YTDLP"] = os.path.join(TMP, "no_esta.exe")
    e = descargas.estado()
    ok(e["disponible"] is False and "winget install yt-dlp.yt-dlp" in e["motivo"] and "no lo descarga" in e["motivo"], "sin yt-dlp: dice como conseguirlo y que Moviola no lo descarga por su cuenta", e["motivo"])
    ok(da_error(descargas.descargar, "https://youtu.be/dQw4w9WgXcQ", TMP) is not None, "y bajar sin la herramienta da ese mismo error")
    os.environ["MOVIOLA_YTDLP"] = os.path.join(AQUI, "falso_ytdlp.py")

    print("=== 3. bajar (con el yt-dlp de mentira) ===")
    carpeta = os.path.join(TMP, "directo")
    avances = []
    r = descargas.descargar("https://youtu.be/dQw4w9WgXcQ?t=9", carpeta, "720", None, avances.append)
    ok(os.path.isfile(r["archivo"]) and r["archivo"].startswith(carpeta) and r["nombre"].endswith("[dQw4w9WgXcQ].mp4"), "baja el video a la carpeta pedida, con su titulo y su id en el nombre", r["nombre"])
    ok(avances and avances == sorted(avances) and avances[-1] == 1.0 and 0 <= avances[0] < 0.5, "el avance sube de a poco hasta 1", str([round(x, 2) for x in avances]))
    args = argumentos()[-1]
    ok(args[-1] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ" and args[-2] == "--", "se le pasa SOLO la direccion limpia, despues de «--» (no se puede confundir con una opcion)", str(args[-3:]))
    ok("--no-playlist" in args and "--no-overwrites" in args and "-f" in args and "height<=720" in args[args.index("-f") + 1], "una sola pieza (--no-playlist), sin pisar nada y con la calidad pedida")
    prohibidas = ("--cookies", "--cookies-from-browser", "--geo-bypass", "--geo-verification-proxy", "--proxy", "--username", "--password", "--extractor-args", "--allow-unplayable-formats")
    ok(not any(any(a.startswith(p) for a in args) for p in prohibidas), "NO usa cookies, proxies, cambio de pais ni nada que esquive una proteccion", str(args))
    ok("--ffmpeg-location" in args, "usa el ffmpeg de Moviola")
    r2 = descargas.descargar("https://youtu.be/dQw4w9WgXcQ", carpeta, "mejor")
    ok(r2["archivo"] != r["archivo"] and os.path.isfile(r["archivo"]) and os.path.isfile(r2["archivo"]), "bajar de nuevo el mismo video NO pisa el anterior", os.path.basename(r2["archivo"]))
    ra = descargas.descargar("https://youtu.be/dQw4w9WgXcQ", carpeta, "audio")
    ok(ra["archivo"].endswith(".mp3") and "-x" in argumentos()[-1] and "--merge-output-format" not in argumentos()[-1], "«Solo el audio» baja un MP3 (sin juntar video)", ra["nombre"])
    for malo, kw in (("una calidad que no existe", {"calidad": "4k"}),):
        e = da_error(descargas.descargar, "https://youtu.be/dQw4w9WgXcQ", carpeta, kw["calidad"])
        ok(e is not None, malo + ": error claro", e)

    print("=== 4. los errores de YouTube, dichos para una persona ===")
    for vid, esperado in (("priv0000001", "privado"), ("edad0000001", "iniciar sesión"), ("caido000001", "conexión")):
        e = da_error(descargas.descargar, "https://youtu.be/" + vid, carpeta)
        ok(e is not None and esperado in e and "Traceback" not in e and "ERROR" not in e, "%s: «%s»" % (vid, e), e)
    ok(descargas.explicar("ERROR: [youtube] abcdefghijk: Something strange happened here").startswith("No se pudo bajar el video. Something strange"), "un error desconocido se muestra cortado y sin el prefijo tecnico")
    ok("Video unavailable" not in descargas.explicar("ERROR: Video unavailable"), "(y las frases conocidas no muestran el original en ingles)")

    print("=== 5. cancelar ===")
    ev = threading.Event()
    t = threading.Timer(1.0, ev.set)
    t.start()
    t0 = time.time()
    try:
        descargas.descargar("https://youtu.be/cuelga00001", carpeta, "1080", ev)
        ok(False, "cancelar corta la descarga")
    except Exception as e:
        ok(type(e).__name__ == "Cancelado" and time.time() - t0 < 15, "cancelar corta la descarga enseguida (sin esperar a que yt-dlp termine)", type(e).__name__ + " %.1f s" % (time.time() - t0))

    print("=== 6. la API ===")
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    app.crear_servidor(api)
    h = api.descarga_herramienta()
    ok(h["disponible"] and [c["valor"] for c in h["calidades"]] == ["mejor", "1080", "720", "480", "audio"] and h["carpeta"] == os.environ["MOVIOLA_DESCARGAS"], "descarga_herramienta: disponible, las 5 calidades y la carpeta", str(h))
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ok("derecho" in api.descargar_iniciar(url, "720").get("error", "") and "derecho" in api.descargar_iniciar(url, "720", "si").get("error", ""), "sin confirmar que se tiene derecho a usarlo: no baja (tiene que ser exactamente true)")
    ok(api.descargar_iniciar("https://vimeo.com/1", "720", True).get("error") and api.descargar_iniciar(url, "4k", True).get("error"), "direccion de otro sitio o calidad rara: error claro")
    ok(api.descargar_estado()["estado"] == "ninguna", "(y no empezo nada)")
    r = api.descargar_iniciar(url, "480", True)
    ok(r.get("ok") is True, "con la confirmacion, empieza")
    ok("en curso" in api.descargar_iniciar(url, "480", True).get("error", ""), "una segunda descarga a la vez: error claro")
    e = esperar_estado(api, ("listo", "error", "cancelado"))
    ok(e["estado"] == "listo" and os.path.isfile(e["archivo"]) and e["archivo"].startswith(os.environ["MOVIOLA_DESCARGAS"]) and e["es_audio"] is False, "termina: archivo en la carpeta de descargas", str(e))
    ok(api.descarga_mostrar().get("ok") is True or sys.platform != "win32", "mostrar en la carpeta usa solo lo que se bajo (no recibe ninguna ruta)")
    r = api.descargar_iniciar("https://youtu.be/priv0000001", "720", True)
    e = esperar_estado(api, ("listo", "error", "cancelado"))
    ok(e["estado"] == "error" and "privado" in e["error"], "un video privado: la API devuelve el error en palabras claras", e.get("error"))
    api.descargar_iniciar("https://youtu.be/cuelga00001", "720", True)
    time.sleep(1.0)
    api.descargar_cancelar()
    e = esperar_estado(api, ("listo", "error", "cancelado"), 20)
    ok(e["estado"] == "cancelado", "cancelar desde la API", e["estado"])
    ok(api.descargar_iniciar(url, "720", True).get("ok") is True, "y despues se puede volver a bajar")
    esperar_estado(api, ("listo", "error", "cancelado"))
    # el archivo bajado es un archivo mas: se abre como cualquier video
    ultimo = api.descargar_estado()["archivo"]
    a = api.abrir(ultimo)
    ok(not a.get("error") and a["duracion"] > 1.5 and a["ancho"] == 320, "el video bajado se abre en el editor como cualquier otro", str(a.get("error")))
    ok("descargar_iniciar" in api.metodos() and "descarga_mostrar" in api.metodos(), "los metodos estan publicados para la interfaz")
    api.cerrar()

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
