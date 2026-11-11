# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la reproduccion por proxy con la ventana real.

Uso:  python -I pruebas/prueba_proxy_app.py

Abre formatos que el WebView no reproduce y comprueba el flujo completo: progreso,
aviso si se da play antes de tiempo, reproduccion con el proxy, pausa, y que el cuadro
mostrado (que sale del ORIGINAL) coincida visualmente con el del PROXY en ese instante.
Tambien cubre cancelar al abrir otro archivo, errores y el cache.
"""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")      # estas pruebas no necesitan la deteccion de GPU

import webview  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402

import app  # noqa: E402

TMP = tempfile.mkdtemp(prefix="prueba-proxy-app-")
SERVIDOR = None
API = None
fallos = []
real_generar = app.proxy_mod.generar


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def js(w, expresion):
    r = w.evaluate_js("JSON.stringify((() => { return " + expresion + "; })())")
    return json.loads(r) if r else None


def esperar(w, condicion, tiempo=60.0, paso=0.2):
    t0 = time.time()
    while time.time() - t0 < tiempo:
        try:
            if js(w, condicion):
                return True
        except Exception:
            pass
        time.sleep(paso)
    return False


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def abrir(w, ruta):
    w.evaluate_js("abrir(" + json.dumps(ruta) + ")")
    return esperar(w, "S.ruta === " + json.dumps(ruta) + " && document.getElementById('cargando').hidden", 60)


def lento(segundos=4.0):
    """Reemplaza proxy.generar por uno lento (progreso visible) que respeta cancelar."""
    def generar(ruta, carpeta, al_progresar=None, alto_max=720, pista_audio=0, cancelar=None, codificador=None):
        pasos = 16
        for i in range(pasos):
            if cancelar is not None and cancelar.is_set():
                raise app.proxy_mod.Cancelado()
            if al_progresar:
                al_progresar(i / pasos * 0.9)
            time.sleep(segundos / pasos)
        return real_generar(ruta, carpeta, al_progresar, alto_max, pista_audio, cancelar, codificador)
    app.proxy_mod.generar = generar


def jpeg_del_motor(n, ancho):
    """El cuadro n tal como lo sirve el motor (sale del ORIGINAL)."""
    c = http.client.HTTPConnection("127.0.0.1", SERVIDOR.puerto, timeout=10)
    c.putrequest("GET", f"/{SERVIDOR.token}/frame?n={n}&w={ancho}", skip_host=True)
    c.putheader("Host", f"127.0.0.1:{SERVIDOR.puerto}")
    c.endheaders()
    r = c.getresponse()
    datos = r.read()
    c.close()
    return Image.open(BytesIO(datos)).convert("L")


def cuadro_del_proxy(ruta_proxy, segundo, ancho, alto):
    """El cuadro que muestra el PROXY en ese segundo."""
    salida = os.path.join(TMP, "del_proxy.png")
    ffmpeg("-ss", f"{segundo:.4f}", "-i", ruta_proxy, "-frames:v", "1", "-vf", f"scale={ancho}:{alto}", salida)
    return Image.open(salida).convert("L")


def parecido(a, b):
    if a.size != b.size:
        b = b.resize(a.size)
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def correr(w):
    try:
        _correr(w)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w):
    time.sleep(3)

    print("=== 1. formato que el WebView no reproduce: progreso y cambio de fuente ===")
    hevc = os.path.join(TMP, "contador.mkv")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=12", "-f", "lavfi", "-i", "sine=f=440:d=12",
           "-c:v", "libx265", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-shortest", hevc)
    lento(4.0)
    ok(abrir(w, hevc), "abre el mkv hevc/opus")
    e = js(w, """({proxy: S.info.proxy, repro: S.info.reproducible, url: S.info.url,
                   barra: !document.getElementById('preparando').hidden,
                   avisos: document.getElementById('avisos').textContent.trim(),
                   src: document.getElementById('capa-video').getAttribute('src')})""")
    ok(e["proxy"] == "generando" and e["repro"] is False, "queda 'generando' y no reproducible todavia", f"{e['proxy']}, {e['repro']}")
    ok(e["barra"], "muestra la barra de preparacion")
    ok(e["avisos"] == "", "y NO avisa que 'no se puede reproducir'", repr(e["avisos"]))
    ok(not e["src"], "el <video> todavia no tiene fuente")

    w.evaluate_js("reproducir()")
    time.sleep(0.5)
    aviso = js(w, "document.getElementById('avisos').textContent.trim()")
    ok("preparando" in aviso.lower(), "dar play antes de tiempo explica que falta poco", aviso[:80])
    w.evaluate_js("document.querySelectorAll('.aviso__cerrar').forEach(b => b.click())")

    time.sleep(1.5)
    txt = js(w, "document.getElementById('preparando-texto').textContent")
    ok("%" in txt, "el progreso se muestra con porcentaje", txt)
    pct = js(w, "parseFloat(document.getElementById('preparando-barra').style.width)")
    ok(pct > 0, "y la barra avanza", f"{pct}%")

    ok(esperar(w, "S.info.proxy === 'listo'", 60), "termina y pasa a 'listo'")
    e = js(w, """({repro: S.info.reproducible, barra: document.getElementById('preparando').hidden,
                   src: document.getElementById('capa-video').getAttribute('src') || ''})""")
    ok(e["repro"] and e["barra"], "reproducible y la barra se oculta")
    ok("/media/" in e["src"] and e["src"].endswith(".mp4"), "el <video> apunta al proxy (.mp4)", e["src"][-40:])
    estado = API.proxy_estado()
    ok(estado["estado"] == "listo" and estado["ruta"] == hevc, "el estado del motor coincide")

    print("=== 2. reproducir con el proxy y pausar: el cuadro coincide ===")
    w.evaluate_js("irA(100, 540)")
    time.sleep(0.8)
    w.evaluate_js("reproducir()")
    time.sleep(2.5)
    e = js(w, """({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime,
                   err: document.getElementById('capa-video').error ? document.getElementById('capa-video').error.message : null})""")
    ok(e["rep"] and e["err"] is None, "reproduce el proxy sin errores", e["err"])
    ok(e["ct"] > 100 / 30 + 1.5, "avanza desde donde estaba", f"{e['ct']:.2f} s")
    w.evaluate_js("pausar()")
    time.sleep(1.8)
    e = js(w, "({n: S.cuadro, ct: document.getElementById('capa-video').currentTime, pintado: S.ultimoPintado, t: tiempoDe(S.cuadro)})")
    ok(e["pintado"] and e["pintado"]["n"] == e["n"], "pinta el cuadro de la pausa", str(e["pintado"]))
    # el chequeo que importa: lo que se ve (ORIGINAL) == lo que muestra el proxy en ese segundo
    n = e["n"]
    mio = jpeg_del_motor(n, 270)
    proxy_ruta = os.path.join(API.cache, [f for f in os.listdir(API.cache) if f.startswith("contador") and f.endswith(".mp4")][0])
    del_proxy = cuadro_del_proxy(proxy_ruta, e["t"] + 0.001, mio.size[0], mio.size[1])
    d_mismo = parecido(mio, del_proxy)
    vecino = jpeg_del_motor(min(n + 12, 359), 270)
    d_vecino = parecido(vecino, del_proxy)
    ok(d_mismo < 14, "el cuadro mostrado se parece al que muestra el proxy en ese instante", f"diferencia {d_mismo:.1f}")
    ok(d_mismo * 2 < d_vecino, "y mucho mas que a un cuadro 12 lugares mas adelante", f"{d_mismo:.1f} contra {d_vecino:.1f}")

    print("=== 3. abrir otro archivo cancela el proxy que estaba en marcha ===")
    lento(30.0)                                   # tan lento que tiene que cancelarse
    otro = os.path.join(TMP, "contador2.mkv")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=6", "-f", "lavfi", "-i", "sine=f=330:d=6",
           "-c:v", "libx265", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-shortest", otro)
    ok(abrir(w, otro), "abre un segundo mkv (arranca otro proxy lento)")
    epoca1 = API._epoca_proxy
    time.sleep(1.0)
    lento(0.5)
    reproducible = os.path.join(TMP, "normal.mp4")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=4", "-f", "lavfi", "-i", "sine=f=220:d=4",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", reproducible)
    ok(abrir(w, reproducible), "y enseguida abre un mp4 normal")
    e = js(w, "({proxy: S.info.proxy, repro: S.info.reproducible, barra: document.getElementById('preparando').hidden})")
    ok(API._epoca_proxy > epoca1, "el motor cancelo el proxy anterior")
    ok(e["proxy"] == "nada" and e["repro"] and e["barra"], "el mp4 normal no usa proxy y no queda barra colgada", str(e))
    time.sleep(1.0)
    ok(API.proxy_estado()["ruta"] == reproducible and API.proxy_estado()["estado"] == "nada", "el estado del motor es el del archivo vigente")
    restos = [n for n in os.listdir(API.cache) if ".parcial." in n]
    ok(not restos, "no quedan archivos .parcial", str(restos))

    print("=== 4. si el proxy falla, se explica y el resto sigue andando ===")
    def roto(ruta, carpeta, al_progresar=None, alto_max=720, pista_audio=0, cancelar=None, codificador=None):
        time.sleep(0.8)
        raise app.proxy_mod.ProxyError("No pude preparar la reproducción de este archivo. Prueba de error.")
    app.proxy_mod.generar = roto
    ok(abrir(w, otro), "abre el mkv con el proxy roto")
    ok(esperar(w, "document.getElementById('avisos').textContent.includes('Prueba de error')", 15), "muestra el mensaje del error")
    e = js(w, "({barra: document.getElementById('preparando').hidden, repro: S.info.reproducible})")
    ok(e["barra"] and e["repro"] is False, "la barra se oculta y no queda como reproducible")
    w.evaluate_js("irA(40, 540)")
    time.sleep(0.8)
    ok(js(w, "S.ultimoPintado && S.ultimoPintado.n") == 40, "cuadro por cuadro sigue andando")
    w.evaluate_js("document.querySelectorAll('.aviso__cerrar').forEach(b => b.click())")

    print("=== 5. cache: abrir de nuevo el mismo archivo ya esta listo ===")
    app.proxy_mod.generar = real_generar
    ok(abrir(w, hevc), "reabre el mkv del principio")
    e = js(w, """({proxy: S.info.proxy, repro: S.info.reproducible, barra: document.getElementById('preparando').hidden,
                   src: document.getElementById('capa-video').getAttribute('src') || ''})""")
    ok(e["proxy"] == "listo" and e["repro"] and e["barra"], "sale 'listo' de entrada, sin esperar", e["proxy"])
    ok("/media/" in e["src"], "y el <video> ya tiene el proxy")

    print("=== 6. solo audio que el navegador no reproduce (ac3) ===")
    ac3 = os.path.join(TMP, "tono.ac3")
    ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=8", "-c:a", "ac3", ac3)
    ok(abrir(w, ac3), "abre un .ac3")
    ok(esperar(w, "S.info.proxy === 'listo'", 30), "se prepara el proxy de audio (.m4a)")
    w.evaluate_js("reproducir()")
    time.sleep(2.0)
    e = js(w, """({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime,
                   err: document.getElementById('capa-video').error ? document.getElementById('capa-video').error.message : null,
                   src: document.getElementById('capa-video').getAttribute('src') || ''})""")
    ok(e["rep"] and e["err"] is None and e["ct"] > 1.0, "el audio suena con el proxy", f"{e['ct']:.2f} s, {e['err']}")
    ok(e["src"].endswith(".m4a"), "y es un .m4a", e["src"][-30:])
    w.evaluate_js("pausar()")

    print("=== 7. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    global SERVIDOR, API
    API = app.API()
    API.cache = os.path.join(TMP, "cache")         # cache propio: la prueba no depende del real
    SERVIDOR = app.crear_servidor(API)
    try:
        webview.create_window("prueba", SERVIDOR.url_inicio(), width=1200, height=820)
        webview.start(correr, webview.windows[0])
    finally:
        app.proxy_mod.generar = real_generar
        API.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
