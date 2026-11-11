# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 4a en la interfaz, con la ventana REAL: velocidad, al reves, repetir y ducking.

Uso:  python -I pruebas/prueba_tiempo_app.py
"""

import json
import os
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-tiempo-app-"), "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []

LEER_GRIS = """
window.grisDeCuadro = function () {
  const img = document.getElementById('capa-cuadro');
  const c = document.createElement('canvas');
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  const g = c.getContext('2d'); g.drawImage(img, 0, 0);
  return g.getImageData(Math.round(img.naturalWidth / 2), Math.round(img.naturalHeight / 2), 1, 1).data[0];
};
"""


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


def elegir_clip(w, pista, indice=0):
    w.evaluate_js("""(() => { const p = S.proy.pistas.find(x => x.id === %s); const c = p.clips[%d];
                       S.sel = {grupo: c.grupo, clip: c.id}; actualizarSeleccion(); })()""" % (json.dumps(pista), indice))
    time.sleep(0.5)


def clic(w, selector):
    w.evaluate_js("document.querySelector(%s).click()" % json.dumps(selector))
    time.sleep(0.9)


def ir_a(w, k):
    w.evaluate_js("irA(%d, 540)" % k)
    esperar(w, "S.ultimoPintado && S.ultimoPintado.n === %d" % k, 10)
    time.sleep(0.2)


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
    w.evaluate_js(LEER_GRIS)
    colores = os.path.join(ex.TMP, "colores.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=12,format=yuv420p,geq=lum='10+20*floor(T)':cb=128:cr=128",
              "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*(300+50*floor(t))*t)':s=48000:d=12:c=mono",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", colores)
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 700)

    def gris_esperado(t_):                       # el gris que se VE para el segundo t_ de la fuente (rango limitado)
        return max(0.0, min(255.0, (10 + 20 * int(t_) - 16) * 255 / 219))

    print("=== 1. velocidad ===")
    ok(abrir(w, colores), "abre el video")
    ok(js(w, "document.getElementById('sec-velocidad').hidden") is True, "sin elegir un clip no se muestra la seccion Velocidad")
    elegir_clip(w, "V1")
    e = js(w, """({visible: !document.getElementById('sec-velocidad').hidden, salida: document.querySelector('#vel-cuerpo output').textContent,
                   pasos: [...document.querySelectorAll('#vel-cuerpo .vel__pasos button')].map(b => b.textContent),
                   marcado: [...document.querySelectorAll('#vel-cuerpo .boton--marcado')].map(b => b.textContent),
                   tono: !document.querySelector('[data-fxk=\"vel:tono\"]').closest('label').hidden, suave: !document.querySelector('[data-fxk=\"vel:suave\"]').closest('label').hidden})""")
    ok(e["visible"] and e["salida"] == "1×" and e["pasos"] == ["0,25×", "0,5×", "1×", "2×", "4×"] and e["marcado"] == ["1×"], "con un clip elegido: velocidad 1×, con los pasos 0,25× a 4× y el actual marcado", str(e))
    ok(not e["tono"] and not e["suave"], "a 1× no ofrece 'mantener el tono' ni 'camara lenta suave'")
    clic(w, '[data-fxk="vel:2"]')
    e = js(w, "({v: S.proy.pistas[0].clips[0].velocidad, a: S.proy.pistas[1].clips[0].velocidad, dur: S.proy.duracion, total: S.totalCuadros, badge: [...document.querySelectorAll('#tira .clip__vel')].map(b => b.textContent), salida: document.querySelector('#vel-cuerpo output').textContent})")
    ok(e["v"] == 2 and e["a"] == 2 and abs(e["dur"] - 6.0) < 0.05 and e["total"] == 180 and e["badge"] == ["2×"] and e["salida"] == "2×", "2×: video y audio enlazado, el proyecto pasa a 6 s y 180 cuadros, con la insignia 2× en la linea de tiempo", str(e))
    ok(js(w, "!document.querySelector('[data-fxk=\"vel:tono\"]').closest('label').hidden") and js(w, "document.querySelector('[data-fxk=\"vel:suave\"]').closest('label').hidden"), "ahora ofrece 'mantener el tono' (y la camara lenta suave solo por debajo de 1×)")
    # cuadro por cuadro con la linea de tiempo nueva: el cuadro 30 (segundo 1,0 de la linea) es el segundo 2,0 de la fuente
    ir_a(w, 30)
    e = js(w, "({fuente: fuenteDe(30), gris: grisDeCuadro(), t: tiempoDe(30)})")
    ok(abs(e["fuente"] - 60) <= 1 and abs(e["t"] - 1.0) < 0.04 and abs(e["gris"] - gris_esperado(2.0)) < 8, "el cuadro 30 de la linea de tiempo es el cuadro 60 de la fuente (y se VE el gris del segundo 2)", str(e))
    ir_a(w, 120)
    ok(abs(js(w, "grisDeCuadro()") - gris_esperado(8.0)) < 8 and abs(js(w, "fuenteDe(120)") - 240) <= 1, "y el 120 es el 240 (segundo 8)")
    # reproducir: el video corre a 2×
    w.evaluate_js("irA(0, 540)")
    time.sleep(0.5)
    w.evaluate_js("reproducir()")
    ok(esperar(w, "S.reproduciendo === true && document.getElementById('capa-video').playbackRate === 2", 10), "al reproducir, el <video> corre al doble de velocidad")
    time.sleep(1.2)
    e = js(w, "({cuadro: S.cuadro, ct: document.getElementById('capa-video').currentTime})")
    ok(30 < e["cuadro"] < 70 and e["ct"] > 1.8, "y el cursor avanza al ritmo de la linea de tiempo (no al de la fuente)", str(e))
    w.evaluate_js("pausar()")
    time.sleep(0.8)
    ok(js(w, "document.getElementById('capa-video').playbackRate") == 1, "al pausar vuelve a 1")
    # el control logaritmico
    elegir_clip(w, "V1")
    w.evaluate_js("(() => { const r = document.querySelector('[data-fxk=\"vel:rango\"]'); r.value = -1; r.dispatchEvent(new Event('change', {bubbles: true})); })()")
    time.sleep(1.0)
    e = js(w, "({v: S.proy.pistas[0].clips[0].velocidad, dur: S.proy.duracion, suave: !document.querySelector('[data-fxk=\"vel:suave\"]').closest('label').hidden})")
    ok(abs(e["v"] - 0.5) < 1e-6 and abs(e["dur"] - 24.0) < 0.1 and e["suave"], "el control (escala logaritmica) en -1 es 0,5×: el proyecto dura 24 s y ofrece la camara lenta suave", str(e))
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[0].clips[0].velocidad") == 2, "un Ctrl+Z vuelve a 2×")
    clic(w, '[data-fxk="vel:1"]')
    ok(js(w, "S.proy.pistas[0].clips[0].velocidad") == 1 and js(w, "document.querySelectorAll('#tira .clip__vel').length") == 0 and js(w, "L.tT === null"), "1× vuelve a lo normal (sin insignia y con la linea de tiempo 'identidad' de siempre)")

    print("=== 2. al reves ===")
    clic(w, '[data-fxk="vel:reves"]')
    e = js(w, "({r: S.proy.pistas[0].clips[0].reversa, a: S.proy.pistas[1].clips[0].reversa, f0: fuenteDe(0), f10: fuenteDe(10), badge: [...document.querySelectorAll('#tira .clip__vel')].map(b => b.textContent), total: S.totalCuadros})")
    ok(e["r"] and e["a"] and e["total"] == 360 and e["f0"] >= 358 and e["f10"] == e["f0"] - 10 and e["badge"] and "reversa" in e["badge"][0], "al reves: el primer cuadro de la linea es el ULTIMO de la fuente, y los siguientes retroceden", str(e))
    ir_a(w, 0)
    ok(abs(js(w, "grisDeCuadro()") - gris_esperado(11.5)) < 8, "y se ve el gris del ultimo segundo")
    w.evaluate_js("reproducir()")
    time.sleep(1.0)
    ok(js(w, "S.reproduciendo") is False and esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5) and "al revés" in js(w, "document.querySelector('#avisos .aviso__texto').textContent"),
       "un tramo al reves no se reproduce: avisa que se ve bien al exportar", js(w, "document.querySelector('#avisos .aviso__texto').textContent"))
    clic(w, '[data-fxk="vel:reves"]')
    ok(js(w, "S.proy.pistas[0].clips[0].reversa") is False, "y se saca")

    print("=== 3. repetir ===")
    w.evaluate_js("(async () => { await operar('dividir', [2.0]); await operar('dividir', [3.0]); })()")
    time.sleep(1.8)
    elegir_clip(w, "V1", 1)
    w.evaluate_js("document.querySelector('.vel__veces').value = 3")
    clic(w, '[data-fxk="vel:repetir"]')
    e = js(w, "({n: S.proy.pistas[0].clips.length, dur: S.proy.duracion})")
    ok(e["n"] == 5 and abs(e["dur"] - 14.0) < 0.05, "repetir 3 veces un clip de 1 s: 5 clips y 14 s", str(e))
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[0].clips.length") == 3 and abs(js(w, "S.proy.duracion") - 12.0) < 0.05, "un Ctrl+Z deshace toda la repeticion")

    print("=== 4. musica y voz (ducking) ===")
    w.evaluate_js("llamar('agregar_audio', [%s, 1.0]).then(r => aplicarProyecto(r.proyecto))" % json.dumps(musica))
    time.sleep(1.6)
    elegir_clip(w, "V1", 0)
    ok(js(w, "document.getElementById('sec-ducking').hidden") is True, "con un clip de video elegido no se ofrece el ducking")
    elegir_clip(w, "A2", 0)
    ok(js(w, "!document.getElementById('sec-ducking').hidden"), "con la musica elegida si")
    clic(w, '[data-fxk="duck:activo"]')
    ok(js(w, "S.proy.pistas.find(p => p.id === 'A2').ducking") == {"activo": True, "reduccion": 12}, "activarlo guarda 12 dB por defecto en la pista")
    w.evaluate_js("(() => { const r = document.querySelector('[data-fxk=\"duck:rango\"]'); r.value = 18; r.dispatchEvent(new Event('change', {bubbles: true})); })()")
    time.sleep(1.0)
    ok(js(w, "S.proy.pistas.find(p => p.id === 'A2').ducking.reduccion") == 18 and js(w, "document.querySelector('#duck-cuerpo output').textContent") == "18 dB", "y se puede ajustar")

    print("=== 5. errores ===")
    w.evaluate_js("operar('velocidad', [S.proy.pistas[0].clips[0].grupo, 9, true, false])")
    time.sleep(0.8)
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5), "una velocidad imposible muestra un aviso")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-tiempo-app-cache-"), "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1280, height=860)
        webview.start(correr, webview.windows[0])
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
