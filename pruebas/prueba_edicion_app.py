# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la edicion en la interfaz, con la ventana REAL.

Uso:  python -I pruebas/prueba_edicion_app.py

Lo importante: se lee el codigo de barras de la imagen que esta en pantalla, asi que se comprueba que
tras cortar y borrar se VE el cuadro de la fuente que corresponde, no solo que los numeros internos coincidan.
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-edicion-app-"), "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402  (fuentes con codigo de barras y tono)

fallos = []
API = None

LEER_CODIGO = """
window.codigoDeCuadro = function () {
  const img = document.getElementById('capa-cuadro');
  const c = document.createElement('canvas');
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  const g = c.getContext('2d'); g.drawImage(img, 0, 0);
  const sx = img.naturalWidth / 640, sy = img.naturalHeight / 360;
  let n = 0;
  for (let k = 0; k < 12; k++) {
    const d = g.getImageData(Math.round((224 + 16 * k + 8) * sx), Math.round((172 + 8) * sy), 1, 1).data;
    if (d[0] > 128) n |= (1 << k);
  }
  return n;
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


def tecla(w, codigo, ctrl=False, shift=False):
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: '%s', ctrlKey: %s, shiftKey: %s, bubbles: true, cancelable: true}))"
                  % (codigo, "true" if ctrl else "false", "true" if shift else "false"))
    time.sleep(0.6)


def ir_a(w, k):
    w.evaluate_js("irA(%d, 540)" % k)
    esperar(w, "S.ultimoPintado && S.ultimoPintado.n === %d" % k, 10)


def codigo_en_pantalla(w, k):
    ir_a(w, k)
    time.sleep(0.15)
    return js(w, "codigoDeCuadro()")


def clic_en_carril(w, carril, fraccion):
    w.evaluate_js("""(() => {
        const lane = document.querySelector('[data-carril="%s"]').getBoundingClientRect();
        const c = document.getElementById('carriles').getBoundingClientRect();
        const x = c.left + c.width * %s, y = lane.top + lane.height / 2;
        const el = document.elementFromPoint(x, y);
        const op = {clientX: x, clientY: y, pointerId: 1, bubbles: true, buttons: 1};
        el.dispatchEvent(new PointerEvent('pointerdown', op));
        el.dispatchEvent(new PointerEvent('pointerup', op));
    })()""" % (carril, fraccion))
    time.sleep(0.6)


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
    w.evaluate_js(LEER_CODIGO)
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"))            # 640x360, 12 s, 30 fps, 360 cuadros
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 2000)

    print("=== 1. abrir: aparecen la barra de edicion y los clips ===")
    ok(abrir(w, src), "abre el video")
    ok(js(w, "document.getElementById('edicion').hidden") is False, "la barra de edicion se muestra")
    e = js(w, """({clips: document.querySelectorAll('#tira .clip').length, minis: document.querySelectorAll('#tira .mini').length,
                   dur: S.duracion, total: S.totalCuadros, identidad: L.tT === null,
                   herr: ['btn-dividir','btn-borrar','btn-recortar','btn-deshacer','btn-rehacer'].map(i => document.getElementById(i).disabled)})""")
    ok(e["clips"] == 1 and e["minis"] > 0, "un clip en V1, con sus miniaturas", f"{e['clips']} clip, {e['minis']} miniaturas")
    ok(abs(e["dur"] - 12.0) < 0.1 and e["total"] == 360 and e["identidad"], "sin ediciones la linea de tiempo es la identidad", f"{e['total']} cuadros")
    ok(e["herr"] == [False, True, True, True, True], "dividir habilitado; borrar, recortar, deshacer y rehacer no (todavia no hay que borrar ni deshacer)", str(e["herr"]))
    ok(codigo_en_pantalla(w, 100) == 100, "el cuadro 100 muestra el codigo 100 (el lector de codigos funciona)")
    # Regresion: una clase nueva (.marca) piso la del logo y tapaba el borde izquierdo de toda la pagina.
    e = js(w, """(() => { const l = document.querySelector('#barra .marca'); const r = l.getBoundingClientRect(); const cs = getComputedStyle(l);
                   return {pos: cs.position, ancho: Math.round(r.width), alto: Math.round(r.height), fondo: cs.backgroundColor}; })()""")
    ok(e["pos"] != "absolute" and e["ancho"] > 40 and e["alto"] < 40, "el logo de la barra no heredo estilos de las clases nuevas", str(e))
    e = js(w, """(() => { const t = [...document.querySelectorAll('body *')].filter(x => { const r = x.getBoundingClientRect(); const cs = getComputedStyle(x);
                   return cs.position === 'absolute' && r.width > 0 && r.width < 4 && r.height > 300 && x.id !== 'cursor'; }).map(x => x.className || x.id); return t; })()""")
    ok(e == [], "y no hay barras finas de alto casi completo sueltas por la pagina", str(e))

    print("=== 2. dividir en el cursor ===")
    ir_a(w, 90)
    tecla(w, "KeyS")
    e = js(w, """({clips: document.querySelectorAll('#tira .clip').length, v1: S.proy.pistas[0].clips.map(c => [c.desde, c.hasta]),
                   undo: !document.getElementById('btn-deshacer').disabled})""")
    ok(e["clips"] == 2 and abs(e["v1"][0][1] - 3.0) < 0.04 and abs(e["v1"][1][0] - 3.0) < 0.04, "la tecla S corta en el segundo 3: dos clips pegados", str(e["v1"]))
    ok(e["undo"], "y deshacer se habilita")
    ok(js(w, "S.totalCuadros") == 360 and js(w, "L.tT !== null") is True, "la duracion no cambia (360 cuadros)")
    tecla(w, "KeyS")
    ok(js(w, "document.querySelectorAll('.aviso--ojo').length") >= 1, "cortar donde ya hay un corte avisa con un mensaje claro",
       js(w, "[...document.querySelectorAll('.aviso__texto')].map(a => a.textContent).join(' | ')"))
    w.evaluate_js("document.querySelectorAll('.aviso__cerrar').forEach(b => b.click())")
    w.evaluate_js("document.getElementById('btn-deshacer').click()")
    time.sleep(0.6)
    ok(js(w, "document.querySelectorAll('#tira .clip').length") == 1, "el boton Deshacer vuelve a un solo clip")

    print("=== 3. marcar un tramo y borrarlo: se VE el cuadro correcto ===")
    ir_a(w, 30)
    tecla(w, "KeyI")
    ok(js(w, "S.marcaIn") is not None and abs(js(w, "S.marcaIn") - 1.0) < 0.04, "I marca la entrada en el segundo 1")
    ir_a(w, 60)
    tecla(w, "KeyO")
    e = js(w, "({r: document.querySelectorAll('#marcas .rango').length, izq: parseFloat(document.querySelector('#marcas .rango').style.left), ancho: parseFloat(document.querySelector('#marcas .rango').style.width)})")
    ok(e["r"] == 1 and abs(e["izq"] - 100 / 12) < 0.3 and abs(e["ancho"] - 100 / 12) < 0.3, "O marca la salida: se ve el tramo sobre la linea de tiempo", f"{e['izq']:.1f}% + {e['ancho']:.1f}%")
    ok(js(w, "document.getElementById('btn-borrar').disabled") is False and js(w, "document.getElementById('btn-recortar').disabled") is False,
       "con un tramo marcado, Borrar y Recortar se habilitan")
    tecla(w, "Delete")
    e = js(w, "({dur: S.duracion, total: S.totalCuadros, marcas: S.marcaIn === null && S.marcaOut === null, clips: document.querySelectorAll('#tira .clip').length})")
    ok(abs(e["dur"] - 11.0) < 0.1 and e["total"] == 330 and e["clips"] == 2 and e["marcas"], "Supr borra el tramo, cierra el hueco y limpia las marcas", str(e))
    ok(js(w, "[fuenteDe(29), fuenteDe(30), fuenteDe(31), fuenteDe(329)]") == [29, 60, 61, 359], "el cuadro 30 de la linea sale ahora del cuadro 60 de la fuente")
    for k, esperado in ((29, 29), (30, 60), (31, 61), (150, 180), (329, 359)):
        ok(codigo_en_pantalla(w, k) == esperado, f"en pantalla, el cuadro {k} de la linea ES el cuadro {esperado} de la fuente")
    ok(abs(js(w, "tiempoDe(30)") - 1.0) < 0.04, "y el tiempo de la linea sigue siendo continuo (el cuadro 30 esta en el segundo 1)")

    print("=== 4. deshacer y rehacer con el teclado ===")
    tecla(w, "KeyZ", ctrl=True)
    ok(js(w, "S.totalCuadros") == 360 and abs(js(w, "S.duracion") - 12.0) < 0.1, "Ctrl+Z recupera el tramo borrado")
    ok(codigo_en_pantalla(w, 30) == 30, "y el cuadro 30 vuelve a ser el 30")
    tecla(w, "KeyY", ctrl=True)
    ok(js(w, "S.totalCuadros") == 330, "Ctrl+Y lo vuelve a borrar")
    ok(codigo_en_pantalla(w, 30) == 60, "y se vuelve a ver el cuadro 60")
    tecla(w, "KeyZ", ctrl=True)
    tecla(w, "KeyZ", ctrl=True)

    print("=== 5. elegir un clip con el mouse ===")
    ir_a(w, 90)
    tecla(w, "KeyS")
    clic_en_carril(w, "V1", 0.75)
    e = js(w, """({sel: S.sel, marcado: document.querySelectorAll('#tira .clip--sel').length,
                   insp: !document.getElementById('inspector').hidden, titulo: document.getElementById('inspector-titulo').textContent})""")
    ok(e["sel"] is not None and e["marcado"] == 1 and e["insp"], "un clic en el carril elige el clip y muestra el inspector", e["titulo"])
    ok("video y su audio" in e["titulo"], "dice que es el clip de video con su audio")
    ok(js(w, "S.sel.grupo === S.proy.pistas[0].clips[1].grupo"), "elige el clip donde se hizo clic (el de la derecha)")
    tecla(w, "Delete")
    e = js(w, "({total: S.totalCuadros, clips: document.querySelectorAll('#tira .clip').length, sel: S.sel})")
    ok(e["total"] == 90 and e["clips"] == 1 and e["sel"] is None, "Supr borra el clip elegido (y su audio) y cierra el hueco", str(e))
    clic_en_carril(w, "V1", 0.5)
    ok(js(w, "S.sel") is not None, "se puede elegir de nuevo")
    clic_en_carril(w, "V1", 0.5)
    tecla(w, "Escape")
    ok(js(w, "S.sel") is None and js(w, "document.getElementById('inspector').hidden") is True, "Escape saca la seleccion")
    tecla(w, "KeyZ", ctrl=True)
    tecla(w, "KeyZ", ctrl=True)

    print("=== 6. fundidos y volumen desde el inspector ===")
    ir_a(w, 0)
    clic_en_carril(w, "V1", 0.5)
    w.evaluate_js("""(() => { const c = document.getElementById('fade-in'); c.value = '1'; c.dispatchEvent(new Event('input')); c.dispatchEvent(new Event('change')); })()""")
    time.sleep(0.9)
    ir_a(w, 0)                  # el clic en el carril movio el cursor al medio: se vuelve al primer cuadro
    time.sleep(0.2)
    e = js(w, """({fi: S.proy.pistas[0].clips[0].fade_in, fa: S.proy.pistas[1].clips[0].fade_in, grad: document.querySelectorAll('.clip__fundido--in').length,
                   op0: parseFloat(document.getElementById('fundido-visor').style.opacity)})""")
    ok(e["fi"] == 1.0 and e["fa"] == 1.0, "el fundido de entrada se aplica al video Y a su audio", f"{e['fi']} / {e['fa']}")
    ok(e["grad"] == 1, "y se ve en el clip como un degradado")
    ok(e["op0"] > 0.95, "en el cuadro 0 la imagen esta en negro (vista previa del fundido)", f"opacidad {e['op0']}")
    ir_a(w, 45)
    time.sleep(0.2)
    ok(js(w, "parseFloat(document.getElementById('fundido-visor').style.opacity)") < 0.02, "y en el cuadro 45 ya no hay fundido")
    ir_a(w, 15)
    ok(0.2 < js(w, "parseFloat(document.getElementById('fundido-visor').style.opacity)") < 0.8, "en la mitad del fundido esta a medias")
    w.evaluate_js("""(() => { const c = document.getElementById('volumen'); c.value = '50'; c.dispatchEvent(new Event('input')); c.dispatchEvent(new Event('change')); })()""")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[1].clips[0].volumen") == 0.5, "el volumen se aplica al audio")
    w.evaluate_js("document.getElementById('btn-silenciar').click()")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[1].silenciada") is True and "Activar" in js(w, "document.getElementById('btn-silenciar').textContent"), "Silenciar el audio")
    w.evaluate_js("document.getElementById('btn-silenciar').click()")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[1].silenciada") is False, "y se vuelve a activar")
    w.evaluate_js("document.getElementById('btn-separar').click()")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[0].clips[0].grupo !== S.proy.pistas[1].clips[0].grupo"), "Separar audio desenlaza video y audio")
    for _ in range(6):
        tecla(w, "KeyZ", ctrl=True)

    print("=== 7. reproducir saltando lo borrado ===")
    ir_a(w, 0)
    ir_a(w, 75)
    tecla(w, "KeyI")
    ir_a(w, 135)
    tecla(w, "KeyO")
    tecla(w, "Delete")                                  # se borra del segundo 2,5 al 4,5 (cuadros 75-135)
    ok(js(w, "S.totalCuadros") == 300, "se borraron 2 s (quedan 300 cuadros)")
    ir_a(w, 60)                                         # segundo 2,0: 0,5 s antes del corte
    t0 = js(w, "document.getElementById('capa-video').currentTime")
    w.evaluate_js("reproducir()")
    time.sleep(2.3)
    e = js(w, """({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime, k: S.cuadro,
                   seg: S.segIdx, err: !!document.getElementById('capa-video').error})""")
    ok(e["rep"] and not e["err"], "reproduce sin errores")
    ok(e["seg"] == 1, "paso al segundo tramo (salto el borrado)", f"tramo {e['seg']}")
    ok(e["ct"] > 4.5, "el video avanzo mas alla de lo borrado: segundo %.2f de la fuente" % e["ct"], "no se quedo en el tramo viejo")
    # 2,3 s despues de t=2,0 de la linea => ~4,3 s de la linea => ~6,3 s de la fuente
    ok(abs(e["ct"] - 6.3) < 0.7, "y la posicion es la esperada (4,3 s de la linea = 6,3 s de la fuente)", f"{e['ct']:.2f} s")
    ok(abs(js(w, "tiempoDe(S.cuadro)") - 4.3) < 0.5, "el contador va por el tiempo de la linea de tiempo, no de la fuente", f"{js(w, 'tiempoDe(S.cuadro)'):.2f} s")
    w.evaluate_js("pausar()")
    time.sleep(1.6)
    k = js(w, "S.cuadro")
    ok(js(w, "S.ultimoPintado && S.ultimoPintado.n") == k, "al pausar se pinta el cuadro de la pausa")
    ok(codigo_en_pantalla(w, k) == js(w, "fuenteDe(%d)" % k), "y se ve el cuadro de la fuente que corresponde", f"k={k}")
    ir_a(w, 280)
    w.evaluate_js("reproducir()")
    ok(esperar(w, "S.reproduciendo", 10), "empieza a reproducir cerca del final")
    ok(esperar(w, "!S.reproduciendo", 15), "reproducir hasta el final termina solo")
    ok(js(w, "S.cuadro") >= 298, "y deja el cursor en el ultimo cuadro", f"cuadro {js(w, 'S.cuadro')}")
    tecla(w, "KeyZ", ctrl=True)

    print("=== 8. audio extra ===")
    w.evaluate_js("llamar('agregar_audio', [%s, 2.0]).then(r => { aplicarProyecto(r.proyecto); window.__rx = r; })" % json.dumps(musica))
    ok(esperar(w, "window.__rx && window.__rx.proyecto", 20), "se agrega un mp3 en el segundo 2")
    ok(esperar(w, "document.querySelectorAll('.pista-extra').length === 1", 10), "aparece el carril del audio extra (A2)")
    time.sleep(0.8)
    px = js(w, """(() => { const c = document.querySelector('.pista-extra canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
                    let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n; })()""")
    ok(px > 2000, "con su onda dibujada", f"{px} pixeles")
    ok(js(w, "document.querySelector('.pista-extra .carril__rotulo').textContent") == "A2", "rotulado A2")
    ir_a(w, 80)                                          # segundo 2,67: la musica esta sonando
    w.evaluate_js("reproducir()")
    time.sleep(1.5)
    e = js(w, """(() => { const m = previa.extras; const id = [...m.keys()][0]; const a = m.get(id);
                   return a ? {n: m.size, pausado: a.paused, t: a.currentTime} : null; })()""")
    ok(e is not None and e["pausado"] is False, "durante la reproduccion el audio extra suena", str(e))
    ok(e and 0.5 < e["t"] < 3.0, "desde el punto correcto de la musica", f"{e and e['t']:.2f} s")
    w.evaluate_js("pausar()")
    time.sleep(0.7)
    ok(js(w, "[...previa.extras.values()].every(a => a.paused)"), "al pausar se detiene")
    w.evaluate_js("llamar('editar_deshacer').then(r => aplicarProyecto(r.proyecto))")
    time.sleep(0.8)
    ok(js(w, "document.querySelectorAll('.pista-extra').length") == 0, "al deshacer el audio extra desaparece el carril")
    w.evaluate_js("llamar('editar_rehacer').then(r => aplicarProyecto(r.proyecto))")
    time.sleep(0.8)
    clic_en_carril(w, "A2", 0.4)
    ok(js(w, "S.sel !== null && document.getElementById('inspector-titulo').textContent.includes('A2')"), "se puede elegir el clip de audio extra")
    ok(js(w, "document.getElementById('btn-silenciar').hidden") is True, "(sin el boton de silenciar el audio del video)")
    tecla(w, "Delete")
    ok(js(w, "document.querySelectorAll('.pista-extra').length") == 0 and abs(js(w, "S.duracion") - 12.0) < 0.1, "Supr saca el audio extra SIN cerrar ningun hueco")

    print("=== 9. archivos de solo audio ===")
    solo = ex.crear_musica(os.path.join(ex.TMP, "voz.mp3"), 10, 600)
    ok(abrir(w, solo), "abre un mp3")
    ok(js(w, "document.getElementById('edicion').hidden") is False, "la barra de edicion tambien aparece")
    ir_a(w, 300)                                         # segundo 3 (en audio, un cuadro son 10 ms)
    tecla(w, "KeyS")
    ok(js(w, "S.proy.pistas[0].clips.length") == 2, "se puede cortar un audio")
    ir_a(w, 200)
    tecla(w, "KeyI")
    ir_a(w, 400)
    tecla(w, "KeyO")
    tecla(w, "Delete")
    ok(abs(js(w, "S.duracion") - 8.0) < 0.05, "y borrar un tramo: queda de 8 s", js(w, "S.duracion"))
    ir_a(w, 100)
    w.evaluate_js("reproducir()")
    time.sleep(1.8)
    # si la maquina esta ocupada el salto puede demorar: se espera hasta 6 s mas antes de dar por mala la reproduccion
    esperar(w, "S.reproduciendo && S.segIdx === 1 && document.getElementById('capa-video').currentTime > 4.0", 6)
    e = js(w, "({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime, seg: S.segIdx})")
    ok(e["rep"] and e["seg"] == 1 and e["ct"] > 4.0, "reproduce el audio saltando lo borrado", str(e))
    w.evaluate_js("pausar()")

    print("=== 10. cambiar de archivo limpia todo ===")
    ok(abrir(w, src), "se abre otro archivo")
    e = js(w, """({sel: S.sel, marcas: [S.marcaIn, S.marcaOut], extras: document.querySelectorAll('.pista-extra').length,
                   clips: document.querySelectorAll('#tira .clip').length, undo: document.getElementById('btn-deshacer').disabled,
                   insp: document.getElementById('inspector').hidden, total: S.totalCuadros})""")
    ok(e["sel"] is None and e["marcas"] == [None, None] and e["extras"] == 0 and e["clips"] == 1 and e["undo"] and e["insp"] and e["total"] == 360,
       "sin seleccion, marcas, audios extra ni historial del archivo anterior", str(e))

    print("=== 11. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    global API
    API = app.API()
    API.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-edicion-app-cache-"), "cache")
    srv = app.crear_servidor(API)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1280, height=860)
        webview.start(correr, webview.windows[0])
    finally:
        API.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
