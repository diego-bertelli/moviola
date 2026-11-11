# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""La linea de tiempo con el mouse, con la ventana REAL: zoom y desplazamiento, regla, mover un clip entre los demas, tirar de los bordes
(recortar y estirar), iman, un audio suelto, cancelar con Esc, y que un clic comun siga eligiendo y llevando el cursor.
Los arrastres se hacen con eventos de puntero (pointerdown / pointermove / pointerup) sobre las coordenadas reales de cada clip.

Uso:  python -I pruebas/prueba_linea_tiempo_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-linea-app-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")

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


AYUDAS = """
window.__ev = (tipo, x, y, extra) => {
  const o = document.elementFromPoint(x, y) || document.body;
  o.dispatchEvent(new PointerEvent(tipo, Object.assign({bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 9, pointerType: 'mouse', button: 0, buttons: tipo === 'pointerup' ? 0 : 1}, extra || {})));
};
window.__px = (t) => { const r = el.carriles.getBoundingClientRect(); return r.left + t / S.duracion * r.width; };
window.__y = (id) => { const n = id === 'V1' ? el.tira : (id === 'A1' ? document.getElementById('pista-audio') : document.querySelector('[data-carril="' + id + '"]')); const r = n.getBoundingClientRect(); return r.top + r.height / 2; };
window.__clips = (id) => S.proy.pistas.find(p => p.id === id).clips.map(c => [Math.round(c.inicio * 1000) / 1000, Math.round(c.desde * 1000) / 1000, Math.round(c.hasta * 1000) / 1000]);
"""


def punto(w, tipo, t, pista="V1", extra=None, dx=0):
    w.evaluate_js("__ev(%s, __px(%s) + %s, __y(%s), %s)" % (json.dumps(tipo), repr(float(t)), repr(float(dx)), json.dumps(pista), json.dumps(extra or {})))
    time.sleep(0.12)


def arrastrar(w, desde, hasta, pista="V1", dx0=0, extra=None, soltar=True, pasos=4):
    """Un arrastre: apretar en `desde` (segundos), pasar por varios puntos y soltar en `hasta`."""
    punto(w, "pointerdown", desde, pista, extra, dx0)
    for k in range(1, pasos + 1):
        punto(w, "pointermove", desde + (hasta - desde) * k / pasos, pista, extra, dx0)
    if soltar:
        punto(w, "pointerup", hasta, pista, extra, dx0)
        time.sleep(0.9)


def clips(w, id_="V1"):
    return js(w, "__clips(%s)" % json.dumps(id_))


def correr(w, fuentes):
    try:
        _correr(w, fuentes)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w, fuentes):
    src, musica = fuentes
    time.sleep(3)
    w.evaluate_js("pedirAbrir(%s)" % json.dumps(src))
    ok(esperar(w, "S.proy && S.ruta && document.getElementById('cargando').hidden", 30), "se abre el video (12 s)")
    w.evaluate_js(AYUDAS)
    w.evaluate_js("operar('dividir', [4.0])")
    time.sleep(0.8)
    w.evaluate_js("operar('dividir', [8.0])")
    time.sleep(0.8)
    ok(clips(w) == [[0, 0, 4], [4, 4, 8], [8, 8, 12]], "tres clips de 4 s", str(clips(w)))

    print("=== 1. zoom, regla y desplazamiento ===")
    e = js(w, "({zoom: lt.zoom, txt: document.getElementById('lt-zoom').textContent, menos: document.getElementById('lt-menos').disabled, ancho: el.carriles.clientWidth, visible: lt.desp.clientWidth})")
    ok(e["zoom"] == 1 and e["txt"] == "Ajustado" and e["menos"] and e["ancho"] <= e["visible"] + 1, "al empezar se ve todo (zoom «Ajustado», «−» apagado)", str(e))
    n_regla = js(w, "(() => { const c = document.getElementById('regla'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n; })()")
    ok(n_regla > 200, "la regla de tiempo esta dibujada", str(n_regla))
    w.evaluate_js("document.getElementById('lt-mas').click()")
    time.sleep(0.5)
    e = js(w, "({zoom: lt.zoom, ancho: el.carriles.clientWidth, visible: lt.desp.clientWidth, txt: document.getElementById('lt-zoom').textContent})")
    ok(abs(e["zoom"] - 1.5) < 1e-6 and e["ancho"] > e["visible"] * 1.4 and e["txt"] == "1,5×", "«+» acerca 1,5 veces y el lienzo se hace mas ancho que la ventana", str(e))
    for _ in range(5):
        w.evaluate_js("document.getElementById('lt-mas').click()")
        time.sleep(0.25)
    e = js(w, "({zoom: lt.zoom, ancho: el.carriles.clientWidth, visible: lt.desp.clientWidth, mas: document.getElementById('lt-mas').disabled})")
    ok(e["ancho"] <= 14000 + 5 and e["zoom"] > 5, "con mucho zoom, el lienzo no pasa del tope de ancho (14000 px)", str(e))
    n_min = js(w, "document.querySelectorAll('#tira .mini').length")
    ok(n_min > 20, "las miniaturas se redibujan para el ancho nuevo", str(n_min))
    w.evaluate_js("document.getElementById('lt-ajustar').click()")
    time.sleep(0.5)
    ok(js(w, "lt.zoom") == 1 and js(w, "el.carriles.style.width") == "", "«Ajustar» vuelve a ver todo")
    # Ctrl + rueda: el instante bajo el puntero queda quieto
    w.evaluate_js("(() => { const x = __px(6); const o = document.elementFromPoint(x, __y('V1')); o.dispatchEvent(new WheelEvent('wheel', {bubbles: true, cancelable: true, ctrlKey: true, deltaY: -100, clientX: x, clientY: __y('V1')})); })()")
    time.sleep(0.5)
    e = js(w, "({zoom: lt.zoom, scroll: lt.desp.scrollLeft})")
    ok(abs(e["zoom"] - 1.25) < 1e-6, "Ctrl + rueda hacia arriba acerca (1,25x)", str(e))
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: '+', bubbles: true}))")
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: '+', bubbles: true}))")
    time.sleep(0.4)
    ok(js(w, "lt.zoom") > 2.5, "la tecla + tambien acerca", str(js(w, "lt.zoom")))
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: '0', bubbles: true}))")
    time.sleep(0.4)
    ok(js(w, "lt.zoom") == 1, "y la tecla 0 vuelve a ver todo")
    # el cursor no se pierde de vista
    w.evaluate_js("document.getElementById('lt-mas').click(); document.getElementById('lt-mas').click(); document.getElementById('lt-mas').click()")
    time.sleep(0.4)
    w.evaluate_js("irA(0)")
    time.sleep(0.5)
    w.evaluate_js("irA(S.totalCuadros - 1)")
    time.sleep(0.9)
    e = js(w, "(() => { const x = pxDe(tiempoDe(S.cuadro)); return {x, a: lt.desp.scrollLeft, w: lt.desp.clientWidth}; })()")
    ok(e["a"] <= e["x"] <= e["a"] + e["w"], "al ir al final con zoom, la linea de tiempo se desplaza para mostrar el cursor", str(e))
    w.evaluate_js("document.getElementById('lt-ajustar').click()")
    time.sleep(0.4)

    print("=== 2. un clic comun sigue siendo un clic ===")
    antes = clips(w)
    punto(w, "pointerdown", 6.0)
    punto(w, "pointerup", 6.0)
    time.sleep(0.6)
    e = js(w, "({sel: S.sel && S.sel.grupo, t: tiempoDe(S.cuadro), clips: S.proy.pistas[0].clips.map(c => c.grupo)})")
    ok(e["sel"] == e["clips"][1] and abs(e["t"] - 6.0) < 0.1 and clips(w) == antes, "un clic en el medio de un clip lo elige y lleva el cursor ahi, sin mover nada", str(e))
    ok(js(w, "S.arrastrando") is False, "(y no queda un arrastre colgado)")

    print("=== 3. recortar tirando del borde ===")
    # el final del primer clip (4 s) hacia 3 s
    arrastrar(w, 3.97, 3.0)
    ok(clips(w) == [[0, 0, 3], [3, 4, 8], [7, 8, 12]], "tirar del final del primer clip de 4 s a 3 s lo acorta y corre lo que sigue", str(clips(w)))
    ok(abs(js(w, "S.proy.duracion") - 11.0) < 0.01 and clips(w, "A1") == [[0, 0, 3], [3, 4, 8], [7, 8, 12]], "el audio enlazado hace lo mismo, y el proyecto dura 11 s")
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    ok(clips(w) == [[0, 0, 4], [4, 4, 8], [8, 8, 12]], "Ctrl+Z lo devuelve en un paso")
    # estirar: el final del primer clip hacia 5 s usa material que sobra de la fuente
    arrastrar(w, 3.97, 5.0)
    ok(clips(w)[0] == [0, 0, 5] and clips(w)[1][0] == 5, "estirar el final de 4 s a 5 s usa el material que sobra (hasta 5 s)", str(clips(w)))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    # el inicio del segundo clip hacia adelante
    arrastrar(w, 4.03, 5.0)
    ok(clips(w)[1] == [4, 5, 8], "tirar del inicio del segundo clip hacia la derecha le saca el principio (muestra desde 5 s)", str(clips(w)))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    # topes: no se puede estirar mas de lo que hay
    antes = clips(w)
    arrastrar(w, 3.97, 0.0)
    c1 = clips(w)[0]
    ok(c1[2] - c1[1] >= 0.09 and c1[2] - c1[1] < 0.2, "tirar del borde mas alla del principio deja el clip con el minimo (0,1 s), no lo borra", str(c1))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    ok(clips(w) == antes, "(Ctrl+Z)")

    print("=== 4. mover un clip entre los demas ===")
    arrastrar(w, 10.0, 0.4)
    ok(clips(w) == [[0, 8, 12], [4, 0, 4], [8, 4, 8]], "arrastrar el tercer clip al principio lo pone primero (los otros se corren)", str(clips(w)))
    ok(js(w, "S.proy.pistas.find(p => p.id === 'A1').clips.map(c => c.desde)") == [8, 0, 4], "con su audio")
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    arrastrar(w, 2.0, 11.5)
    ok(clips(w) == [[0, 4, 8], [4, 8, 12], [8, 0, 4]], "arrastrar el primero hacia el final lo manda al final", str(clips(w)))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    antes = clips(w)
    arrastrar(w, 6.0, 6.2)
    ok(clips(w) == antes, "un arrastre de menos de unos pixeles hacia el mismo lugar no cambia nada")
    arrastrar(w, 6.0, 5.0, soltar=True)
    ok(clips(w) == antes, "soltar en el mismo lugar (entre los bordes de su propio clip) tampoco")
    # mientras se arrastra se ve el fantasma y el destino
    punto(w, "pointerdown", 6.0)
    punto(w, "pointermove", 3.0)
    punto(w, "pointermove", 1.0)
    e = js(w, "({tipo: lt.drag && lt.drag.tipo, cajas: [...lt.fantasma.children].map(c => c.className), clase: document.body.classList.contains('lt-arrastrando')})")
    ok(e["tipo"] == "mover-bloque" and "lt__fantasma" in e["cajas"] and "lt__destino" in e["cajas"] and e["clase"], "mientras se arrastra se ve el clip fantasma y la raya verde donde caeria", str(e))
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
    time.sleep(0.4)
    punto(w, "pointerup", 1.0)
    time.sleep(0.6)
    ok(clips(w) == antes and js(w, "lt.drag") is None and js(w, "lt.fantasma.children.length") == 0, "Esc cancela el arrastre: no cambia nada y desaparece el fantasma")

    print("=== 5. iman ===")
    w.evaluate_js("irA(cuadroDe(2.5))")
    time.sleep(0.7)
    # el cursor esta en 2,5 s: tirar del final del primer clip (4 s) hasta cerca de 2,5 s se pega al cursor
    px = js(w, "pxPorSeg()")
    umbral = 8.0 / px
    arrastrar(w, 3.97, 2.5 + umbral * 0.5, soltar=False)
    n = js(w, "lt.drag && lt.drag.nuevo")
    ok(n is not None and abs(n - 2.5) < 0.04, "a menos de 8 px del cursor, el borde se pega EXACTO al cursor (2,5 s)", str(n))
    ok(not js(w, "document.getElementById('lt-guia').hidden"), "y aparece la guia verde")
    punto(w, "pointerup", 2.5)
    time.sleep(0.9)
    ok(abs(clips(w)[0][2] - 2.5) < 0.04 and abs(clips(w)[1][0] - 2.5) < 0.04, "al soltar queda en 2,5 s y el siguiente se corre ahi", str(clips(w)))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    arrastrar(w, 3.97, 2.5 + umbral * 0.5, extra={"altKey": True}, soltar=False)
    n = js(w, "lt.drag && lt.drag.nuevo")
    ok(n is not None and abs(n - 2.5) > 0.01 and abs(n - (2.5 + umbral * 0.5)) < 0.05, "con Alt apretado el iman se apaga (queda donde esta el puntero)", str(n))
    punto(w, "pointerup", 2.5, extra={"altKey": True})
    time.sleep(0.9)
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    w.evaluate_js("document.getElementById('lt-iman').click()")
    time.sleep(0.3)
    ok(js(w, "lt.imanOn") is False and js(w, "document.getElementById('lt-iman').getAttribute('aria-pressed')") == "false", "el boton «Imán» lo apaga")
    arrastrar(w, 3.97, 2.5 + umbral * 0.5, soltar=False)
    n = js(w, "lt.drag && lt.drag.nuevo")
    ok(n is not None and abs(n - 2.5) > 0.01, "apagado, no se pega", str(n))
    punto(w, "pointerup", 2.5)
    time.sleep(0.9)
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    w.evaluate_js("document.getElementById('lt-iman').click()")
    time.sleep(0.3)
    ok(js(w, "lt.imanOn") is True, "y se vuelve a prender")

    print("=== 6. un audio suelto (musica) ===")
    w.evaluate_js("llamar('agregar_audio', [%s, 1.0]).then(r => aplicarProyecto(r.proyecto))" % json.dumps(musica))
    ok(esperar(w, "S.proy.pistas.some(p => p.id === 'A2')", 15), "se agrega la musica en la pista A2 (1 s a 9 s)")
    time.sleep(0.8)
    base = clips(w)
    m0 = clips(w, "A2")[0]
    arrastrar(w, 4.0, 5.0, pista="A2")
    m1 = clips(w, "A2")[0]
    ok(abs(m1[0] - (m0[0] + 1.0)) < 0.2 and clips(w) == base, "arrastrar la musica la mueve (no mueve el video)", "%s -> %s" % (m0, m1))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    # que se pegue al borde de un corte de video: el inicio de la musica cerca de 4 s
    arrastrar(w, 3.0, 3.0 + (4.0 - m0[0]) + umbral * 0.4, pista="A2")
    m2 = clips(w, "A2")[0]
    ok(abs(m2[0] - 4.0) < 0.04, "la musica se pega a un corte del video (empieza en 4,0 s)", str(m2))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)
    antes_v = clips(w)
    arrastrar(w, m0[0] + 8.0 - 0.03, m0[0] + 6.0, pista="A2")
    m3 = clips(w, "A2")[0]
    ok(abs(m3[2] - 6.0) < 0.3 and clips(w) == antes_v, "tirar del final de la musica la acorta SIN correr el resto", str(m3))
    ok(js(w, "S.proy.duracion") >= 11.9, "(y la duracion no cambio)")
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.9)

    print("=== 7. el puntero avisa lo que hay debajo ===")
    punto(w, "pointermove", 4.0, extra={"buttons": 0}, dx=-3)
    ok(js(w, "lt.desp.dataset.lt") == "borde", "sobre un borde: «borde» (cursor de redimensionar)")
    punto(w, "pointermove", 2.0, extra={"buttons": 0})
    ok(js(w, "lt.desp.dataset.lt") == "cuerpo", "sobre el cuerpo de un clip: «cuerpo» (la manito)")

    print("=== 8. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    try:
        os.remove(os.path.join(RAIZ, "ultimo-error.log"))
    except OSError:
        pass
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=12)
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 700)
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1400, height=950)
        webview.start(correr, (webview.windows[0], (src, musica)))
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
