# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Los tipos de archivo de salida en el dialogo Exportar, con la ventana REAL.

Uso:  python -I pruebas/prueba_salida_app.py

Se maneja el dialogo como una persona (elegir el tipo de archivo, la calidad, el ancho del GIF, un audio Opus) y se abren
los archivos que salen con ffprobe.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-salida-app-"), "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def js(w, expresion):
    r = w.evaluate_js("JSON.stringify((() => { return " + expresion + "; })())")
    return json.loads(r) if r else None


def esperar(w, condicion, tiempo=30.0, paso=0.2):
    t0 = time.time()
    while time.time() - t0 < tiempo:
        try:
            if js(w, condicion):
                return True
        except Exception:
            pass
        time.sleep(paso)
    return False


def abrir(w, ruta):
    w.evaluate_js("abrir(" + json.dumps(ruta) + ")")
    return esperar(w, "S.ruta === " + json.dumps(ruta) + " && document.getElementById('cargando').hidden", 60)


def clic(w, id_):
    w.evaluate_js("document.getElementById(%s).click()" % json.dumps(id_))
    time.sleep(0.5)


def elegir(w, perfil):
    w.evaluate_js("(() => { const s = document.getElementById('exp-perfil'); s.value = %s; s.dispatchEvent(new Event('change', {bubbles: true})); })()" % json.dumps(perfil))
    time.sleep(0.5)


def sonda(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries", "format=format_name,duration:stream=codec_type,codec_name,width,height,nb_read_frames",
                        "-of", "json", ruta], capture_output=True, text=True)
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return d["format"], v, a


def correr(w):
    try:
        _correr(w)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def exportar_y_esperar(w, carpeta):
    w.evaluate_js("X.carpeta = %s" % json.dumps(carpeta))
    clic(w, "exp-iniciar")
    return esperar(w, "!document.getElementById('exp-resultado').hidden", 120)


def _correr(w):
    time.sleep(3)
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=3)
    ok(abrir(w, src), "abre el video")
    clic(w, "btn-exportar")
    ok(esperar(w, "document.getElementById('dlg-exportar').open && !document.getElementById('exp-armar').hidden", 10), "se abre Exportar")

    print("=== 1. el formulario ===")
    e = js(w, """({opciones: [...document.querySelectorAll('#exp-perfil option')].map(o => o.value), campo: !document.getElementById('exp-perfil-campo').hidden,
                   calidad: !document.getElementById('exp-calidad-campo').hidden, gif: !document.getElementById('exp-gif-campo').hidden,
                   nota: document.getElementById('exp-perfil-nota').textContent, valor: document.getElementById('exp-perfil').value,
                   audio: [...document.querySelectorAll('[data-formato]')].map(b => b.dataset.formato).filter(f => ['wav','mp3','flac','m4a','opus','ogg'].includes(f))})""")
    ok(e["opciones"] == ["mp4_h264", "mp4_h265", "mp4_av1", "webm_vp9", "mov_prores", "mkv_h264", "gif"] and e["campo"] and e["calidad"] and not e["gif"] and e["valor"] == "mp4_h264",
       "la lista trae los 7 tipos, empieza en MP4 H.264, con calidad y sin opciones de GIF", str(e))
    ok("compatible" in e["nota"], "y cada tipo muestra su nota (aqui: el mas compatible)", e["nota"])
    ok(e["audio"] == ["wav", "mp3", "flac", "m4a", "opus", "ogg"], "el audio ofrece los 6 formatos (con Opus y OGG)", str(e["audio"]))
    elegir(w, "mov_prores")
    e = js(w, "({calidad: !document.getElementById('exp-calidad-campo').hidden, gif: !document.getElementById('exp-gif-campo').hidden, nota: document.getElementById('exp-perfil-nota').textContent, archivo: document.getElementById('exp-archivo').textContent})")
    ok(not e["calidad"] and not e["gif"] and "ProRes" not in "" and e["archivo"].endswith(".mov"), "ProRes: sin calidad para elegir y el nombre propuesto termina en .mov", str(e))
    elegir(w, "gif")
    e = js(w, "({calidad: !document.getElementById('exp-calidad-campo').hidden, gif: !document.getElementById('exp-gif-campo').hidden, archivo: document.getElementById('exp-archivo').textContent})")
    ok(not e["calidad"] and e["gif"] and e["archivo"].endswith(".gif"), "GIF: aparecen el ancho y los cuadros por segundo (y no la calidad), y el nombre termina en .gif", str(e))
    elegir(w, "webm_vp9")
    ok(js(w, "document.getElementById('exp-archivo').textContent").endswith(".webm") and js(w, "!document.getElementById('exp-calidad-campo').hidden"), "WebM: vuelve la calidad y el nombre termina en .webm")
    w.evaluate_js("document.querySelector('[data-formato=\"wav\"]').click()")
    time.sleep(0.5)
    ok(js(w, "document.getElementById('exp-perfil-campo').hidden"), "si se elige un formato de solo audio, el tipo de video se esconde")
    w.evaluate_js("document.querySelector('[data-formato=\"original\"]').click()")
    time.sleep(0.5)
    ok(not js(w, "document.getElementById('exp-perfil-campo').hidden") and js(w, "document.getElementById('exp-perfil').value") == "webm_vp9", "y al volver al video se recuerda el tipo elegido")

    print("=== 2. exportar un WebM con calidad liviana ===")
    w.evaluate_js("document.querySelector('[data-calidad=\"liviana\"]').click()")
    time.sleep(0.4)
    ok(js(w, "document.querySelector('[data-calidad=\"liviana\"]').getAttribute('aria-checked')") == "true", "la calidad Liviana queda marcada")
    carpeta = tempfile.mkdtemp(prefix="prueba-salida-ui-")
    ok(exportar_y_esperar(w, carpeta), "exporta")
    arch = os.listdir(carpeta)
    fmt, v, a = sonda(os.path.join(carpeta, arch[0])) if arch else (None, None, None)
    ok(len(arch) == 1 and arch[0].endswith(".webm") and v["codec_name"] == "vp9" and a["codec_name"] == "opus" and int(v["nb_read_frames"]) == 90, "sale un .webm VP9 con sonido Opus y los 90 cuadros", str(arch))
    res = js(w, "[...document.querySelectorAll('#exp-resultado-lineas li')].map(l => l.textContent)")
    ok(any(x.startswith("Tipo: WebM · VP9") and "liviana" in x for x in res), "el resultado dice el tipo y la calidad", str(res))
    clic(w, "exp-otra")

    print("=== 3. exportar un GIF chico ===")
    elegir(w, "gif")
    w.evaluate_js("(() => { const r = document.getElementById('exp-gif-ancho'); r.value = 240; r.dispatchEvent(new Event('input', {bubbles: true})); const s = document.getElementById('exp-gif-fps'); s.value = '15'; })()")
    time.sleep(0.3)
    ok(js(w, "document.getElementById('exp-gif-ancho-valor').textContent") == "240 px", "el ancho se muestra con su unidad")
    carpeta = tempfile.mkdtemp(prefix="prueba-salida-ui-")
    ok(exportar_y_esperar(w, carpeta), "exporta")
    arch = os.listdir(carpeta)
    fmt, v, a = sonda(os.path.join(carpeta, arch[0])) if arch else (None, None, None)
    ok(len(arch) == 1 and arch[0].endswith(".gif") and v["codec_name"] == "gif" and v["width"] == 240 and a is None and abs(int(v["nb_read_frames"]) - 45) <= 1,
       "sale un .gif de 240 px, a 15 cuadros por segundo (45 cuadros) y sin sonido", str(arch) + " " + str(v and (v["width"], v["nb_read_frames"])))
    clic(w, "exp-otra")

    print("=== 4. audio Opus ===")
    w.evaluate_js("document.querySelector('[data-formato=\"opus\"]').click()")
    time.sleep(0.5)
    ok(js(w, "document.getElementById('exp-archivo').textContent").endswith(".opus"), "el nombre propuesto termina en .opus")
    carpeta = tempfile.mkdtemp(prefix="prueba-salida-ui-")
    ok(exportar_y_esperar(w, carpeta), "exporta")
    arch = os.listdir(carpeta)
    fmt, v, a = sonda(os.path.join(carpeta, arch[0])) if arch else (None, None, None)
    ok(len(arch) == 1 and arch[0].endswith(".opus") and v is None and a["codec_name"] == "opus", "sale un .opus", str(arch))

    print("=== 5. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-salida-app-cache-"), "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1280, height=900)
        webview.start(correr, webview.windows[0])
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
