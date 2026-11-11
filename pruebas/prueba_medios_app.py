# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""El panel de medios y VARIOS videos en la interfaz, con la ventana REAL.

Uso:  python -I pruebas/prueba_medios_app.py

Se suman tres videos distintos, se ponen en la linea de tiempo y se comprueba que el VISOR muestra el cuadro que corresponde de cada
archivo (leyendo el codigo de barras de lo que esta en pantalla), que la reproduccion salta de un archivo a otro, que las miniaturas son
las de cada uno, que se puede reordenar, y que un proyecto con varios videos se guarda y se abre.
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-medios-app-"), "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []
api_ref = {}


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
    time.sleep(0.7)


def codigo_en_pantalla(w, ancho_src, alto_src):
    """El numero de cuadro del codigo de barras de LA IMAGEN QUE SE VE en el visor (nada de lo que dice el motor: lo que esta pintado)."""
    return js(w, """(() => { const im = document.getElementById('capa-cuadro'); const W = im.naturalWidth, H = im.naturalHeight;
        const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d'); g.drawImage(im, 0, 0);
        const esc = W / %d; const cx0 = (%d - 192) / 2, cy0 = (%d - 16) / 2; let n = 0;
        for (let k = 0; k < 12; k++) { const x = Math.round((cx0 + 16 * k + 8) * esc), y = Math.round((cy0 + 8) * esc);
          const d = g.getImageData(x, y, 1, 1).data; if (0.299 * d[0] + 0.587 * d[1] + 0.114 * d[2] > 128) n |= 1 << k; }
        return n; })()""" % (ancho_src, ancho_src, alto_src))


def ir_a_tiempo(w, t):
    """Lleva el cursor al segundo t de la linea de tiempo y espera a que el visor pinte ese cuadro."""
    w.evaluate_js("(() => { const k = cuadroDe(%f); window.__k = k; irA(k, ANCHO_NITIDO); })()" % t)
    esperar(w, "S.ultimoPintado && S.ultimoPintado.n === window.__k && !S.trabajo", 10)
    time.sleep(0.25)


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
    api = api_ref["api"]
    a = ex.crear_fuente(os.path.join(ex.TMP, "A.mp4"), dur=6, w=640, h=360, fps=30)
    b = ex.crear_fuente(os.path.join(ex.TMP, "B.mp4"), dur=4, w=320, h=180, fps=25)
    c = ex.crear_fuente(os.path.join(ex.TMP, "C.mp4"), dur=3, w=480, h=270, fps=24, tono=False)

    print("=== 1. el panel ===")
    ok(abrir(w, a), "abre el video A")
    e = js(w, """({visible: !document.getElementById('sec-medios').hidden, items: document.querySelectorAll('#medios-lista .medio').length,
                   nombre: (document.querySelector('#medios-lista .medio__nombre') || {}).textContent, marca: (document.querySelector('#medios-lista .medio__marca') || {}).textContent,
                   meta: (document.querySelector('#medios-lista .medio__meta') || {}).textContent, agregar: document.getElementById('btn-agregar-videos').disabled})""")
    ok(e["visible"] and e["items"] == 1 and e["nombre"] == "A.mp4" and e["marca"] == "Principal" and "640×360" in e["meta"] and "30 fps" in e["meta"] and not e["agregar"],
       "el panel Medios lista el video abierto como «Principal», con su tamano, sus cuadros por segundo y su duracion", str(e))
    ok(js(w, "document.querySelector('#medios-lista .medio__btn[data-accion=quitar]').disabled"), "y el principal no se puede sacar")

    print("=== 2. sumar videos ===")
    w.evaluate_js("sumarRutas(%s)" % json.dumps([b, c]))
    ok(esperar(w, "document.querySelectorAll('#medios-lista .medio').length === 3", 20), "sumar dos videos: aparecen en la lista")
    ok(esperar(w, "S.medios.s2 && S.medios.s3 && !S.medios.s2.error", 30), "el motor manda los datos de cada uno (cuadros por segundo, miniaturas...)")
    time.sleep(0.8)
    e = js(w, """({items: [...document.querySelectorAll('#medios-lista .medio')].map(x => ({n: x.querySelector('.medio__nombre').textContent, meta: x.querySelector('.medio__meta').textContent,
                    mini: x.querySelector('.medio__mini').style.backgroundImage.length > 20, btns: [...x.querySelectorAll('.medio__btn')].map(b => b.dataset.accion + (b.disabled ? '!' : ''))}))})""")
    ok([x["n"] for x in e["items"]] == ["A.mp4", "B.mp4", "C.mp4"] and "320×180" in e["items"][1]["meta"] and "25 fps" in e["items"][1]["meta"] and "24 fps" in e["items"][2]["meta"], "con sus datos propios", str(e["items"]))
    ok(e["items"][1]["mini"] and e["items"][2]["mini"] and e["items"][1]["btns"] == ["final", "cursor", "quitar"], "con miniatura y los botones para ponerlos en la linea de tiempo", str(e["items"][1]))
    ok(js(w, "S.proy.pistas[0].clips.length") == 1 and js(w, "S.proy.sin_guardar") is True, "todavia no estan en la linea de tiempo")
    w.evaluate_js("sumarRutas(%s)" % json.dumps([b]))
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5) and js(w, "document.querySelectorAll('#medios-lista .medio').length") == 3, "sumar uno repetido: avisa y no lo duplica")

    print("=== 3. ponerlos en la linea de tiempo ===")
    w.evaluate_js("document.querySelector('#medios-lista .medio[data-fid=\"s2\"] .medio__btn[data-accion=final]').click()")
    ok(esperar(w, "S.proy.pistas[0].clips.length === 2", 10), "«Al final» pone B despues de A")
    time.sleep(1.0)
    e = js(w, "({dur: S.proy.duracion, total: S.totalCuadros, fids: L.fids, uso: document.querySelector('#medios-lista .medio[data-fid=\"s2\"] .medio__meta').textContent})")
    ok(abs(e["dur"] - 10.0) < 1e-6 and e["fids"] == ["s1", "s2"] and "en uso" in e["uso"], "la linea de tiempo dura 10 s, sabe de que archivo es cada tramo y el panel marca «en uso»", str(e))
    ok(js(w, "S.totalCuadros") == 180 + 100, "y tiene los cuadros de cada archivo: 180 de A (30/s) y 100 de B (25/s)", str(js(w, "S.totalCuadros")))
    ok(js(w, "fidDe(0)") is None and js(w, "fidDe(S.totalCuadros - 1)") == "s2" and js(w, "fuenteDe(S.totalCuadros - 1)") == 99, "el ultimo cuadro es el 99 de B, y el primero es de A (el principal)")
    ok(js(w, "document.querySelector('#medios-lista .medio[data-fid=\"s2\"] .medio__btn[data-accion=quitar]').disabled"), "un video que se usa no se puede sacar del panel")

    print("=== 4. el visor muestra el cuadro de cada archivo ===")
    ir_a_tiempo(w, 2.0)
    cod_a = codigo_en_pantalla(w, 640, 360)
    ir_a_tiempo(w, 7.0)
    cod_b = codigo_en_pantalla(w, 320, 180)
    ir_a_tiempo(w, 9.0)
    cod_b2 = codigo_en_pantalla(w, 320, 180)
    ir_a_tiempo(w, 5.0)
    cod_a2 = codigo_en_pantalla(w, 640, 360)
    ok(cod_a == 60 and cod_a2 == 150, "a los 2 s y a los 5 s el visor muestra los cuadros 60 y 150 de A", f"{cod_a} / {cod_a2}")
    ok(cod_b == 25 and cod_b2 == 75, "a los 7 s y a los 9 s muestra los cuadros 25 y 75 de B (a 25 cuadros por segundo)", f"{cod_b} / {cod_b2}")
    ok(js(w, "S.ultimoPintado.n === window.__k"), "(el cuadro de pantalla es el que se pidio)")

    print("=== 5. miniaturas de cada archivo ===")
    e = js(w, """(() => { const bl = [...document.querySelectorAll('#tira .clip--video')]; const fondo = (b) => b.querySelector('.mini').style.backgroundImage;
        return {n: bl.length, distintos: fondo(bl[0]) !== fondo(bl[1]), a: fondo(bl[0]) === 'url("' + S.tira + '")', b: fondo(bl[1]) === 'url("' + S.medios.s2.tira + '")'}; })()""")
    ok(e["n"] == 2 and e["distintos"] and e["a"] and e["b"], "cada clip de la linea de tiempo usa las miniaturas de SU archivo", str(e))

    print("=== 6. reproducir saltando de un archivo a otro ===")
    ir_a_tiempo(w, 5.0)
    w.evaluate_js("reproducir()")
    ok(esperar(w, "S.reproduciendo", 10), "empieza a reproducir en A")
    ok(esperar(w, "S.fuenteVideo === 's2' && S.segIdx === 1", 15), "al llegar al final de A, el <video> pasa a B (cambia de archivo)")
    time.sleep(1.2)
    e = js(w, "({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime, url: document.getElementById('capa-video').src, esperada: S.medios.s2.url, cuadro: S.cuadro, t: tiempoDe(S.cuadro)})")
    ok(e["rep"] and e["url"] == e["esperada"] and 0.2 < e["ct"] < 3.0 and e["t"] > 6.0, "y sigue reproduciendo B desde su principio", str(e))
    w.evaluate_js("pausar()")
    time.sleep(0.8)
    ok(not js(w, "S.reproduciendo"), "pausa")
    ir_a_tiempo(w, 1.0)
    w.evaluate_js("reproducir()")
    ok(esperar(w, "S.reproduciendo && S.fuenteVideo === 's1'", 15), "y volver a reproducir en A recarga el archivo de A")
    w.evaluate_js("pausar()")
    time.sleep(0.8)

    print("=== 7. insertar en el cursor y reordenar ===")
    ir_a_tiempo(w, 4.5)
    w.evaluate_js("document.querySelector('#medios-lista .medio[data-fid=\"s3\"] .medio__btn[data-accion=cursor]').click()")
    ok(esperar(w, "S.proy.pistas[0].clips.length === 3", 10), "«En el cursor» pone C en el borde de clip mas cercano")
    time.sleep(0.8)
    ok(js(w, "S.proy.pistas[0].clips.map(c => c.fuente)") == ["s1", "s3", "s2"] and abs(js(w, "S.proy.duracion") - 13.0) < 1e-6, "queda A | C | B, de 13 s", str(js(w, "S.proy.pistas[0].clips.map(c => c.fuente)")))
    ir_a_tiempo(w, 7.5)
    cod_c = codigo_en_pantalla(w, 480, 270)
    ok(cod_c == 36, "a los 7,5 s el visor muestra el cuadro 36 de C (a 24 por segundo: 1,5 s)", str(cod_c))
    w.evaluate_js("(() => { const c = S.proy.pistas[0].clips[1]; S.sel = {grupo: c.grupo, clip: c.id}; actualizarSeleccion(); })()")
    time.sleep(0.5)
    ok(js(w, "!document.getElementById('sec-orden').hidden") and not js(w, "document.getElementById('btn-mover-antes').disabled") and not js(w, "document.getElementById('btn-mover-despues').disabled"),
       "con C elegido aparece «Orden» con Mover antes y Mover despues")
    clic(w, "btn-mover-despues")
    ok(esperar(w, "S.proy.pistas[0].clips.map(c => c.fuente).join() === 's1,s2,s3'", 10), "«Mover después» lo pasa detras de B: A | B | C")
    clic(w, "btn-mover-antes")
    ok(esperar(w, "S.proy.pistas[0].clips.map(c => c.fuente).join() === 's1,s3,s2'", 10), "y «Mover antes» lo devuelve: A | C | B")
    w.evaluate_js("(() => { const c = S.proy.pistas[0].clips[0]; S.sel = {grupo: c.grupo, clip: c.id}; actualizarSeleccion(); })()")
    time.sleep(0.5)
    ok(js(w, "document.getElementById('btn-mover-antes').disabled") and not js(w, "document.getElementById('btn-mover-despues').disabled"), "el primero no se puede mover antes")
    w.evaluate_js("operar('deshacer', []); operar('deshacer', []); operar('deshacer', [])")
    time.sleep(2.0)
    ok(js(w, "S.proy.pistas[0].clips.map(c => c.fuente).join()") == "s1,s2", "Deshacer devuelve todo, paso por paso (queda A | B)")
    ok(js(w, "document.querySelector('#medios-lista .medio[data-fid=\"s3\"] .medio__btn[data-accion=quitar]').disabled") is False, "con C sin usar, ya se puede sacar del panel")
    w.evaluate_js("document.querySelector('#medios-lista .medio[data-fid=\"s3\"] .medio__btn[data-accion=quitar]').click()")
    ok(esperar(w, "document.querySelectorAll('#medios-lista .medio').length === 2", 10) and js(w, "!S.medios.s3"), "la ✕ saca C del panel")

    print("=== 8. guardar y abrir un proyecto con varios videos ===")
    api._guardar_en(os.path.join(ex.TMP, "varios_ui.moviola"))
    ruta_p = os.path.join(ex.TMP, "varios_ui.moviola")
    w.evaluate_js("abrir(%s)" % json.dumps(ruta_p))
    ok(esperar(w, "S.proy && S.proy.archivo_proyecto === 'varios_ui.moviola' && document.getElementById('cargando').hidden", 60), "abre el proyecto guardado")
    ok(esperar(w, "S.medios.s2 && !S.medios.s2.error && L.fids.length === 2", 30), "los datos del segundo video se piden solos y la linea de tiempo se arma con ambos")
    time.sleep(0.8)
    ir_a_tiempo(w, 8.0)
    ok(codigo_en_pantalla(w, 320, 180) == 50, "y el visor muestra el cuadro 50 de B a los 8 s")
    ok(js(w, "document.querySelectorAll('#medios-lista .medio').length") == 2 and js(w, "S.proy.archivo_proyecto") == "varios_ui.moviola", "el panel lista los dos y el proyecto tiene su nombre")

    print("=== 9. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api_ref["api"] = api
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-medios-app-cache-"), "cache")
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
