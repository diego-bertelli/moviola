# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Los efectos por clip en la interfaz, con la ventana REAL.

Uso:  python -I pruebas/prueba_efectos_app.py

Se maneja el panel como una persona (clics en Agregar, mover controles, apagar, subir, quitar, deshacer)
y se comprueba tanto el proyecto que guarda el motor como lo que se ve: la vista previa del visor y las
insignias "fx" en la linea de tiempo.
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-efectos-app-"), "ajustes.json")

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


def elegir_clip(w, pista):
    w.evaluate_js("""(() => { const p = S.proy.pistas.find(x => x.id === %s); const c = p.clips[0];
                       S.sel = {grupo: c.grupo, clip: c.id}; actualizarSeleccion(); })()""" % json.dumps(pista))
    time.sleep(0.4)


def agregar(w, categoria, tipo):
    w.evaluate_js("""(() => { const s = document.querySelector('#fx-%s .fx__agregar select'); s.value = %s;
                       document.querySelector('[data-fxk="%s:agregar"]').click(); })()""" % (categoria, json.dumps(tipo), categoria))
    time.sleep(0.8)


def efectos_de(w, pista):
    return js(w, "S.proy.pistas.find(x => x.id === %s).clips[0].efectos.map(e => ({tipo: e.tipo, activo: e.activo, params: e.params}))" % json.dumps(pista))


def historial(w):
    return js(w, "S.proy.puede_deshacer")


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
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"))
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 700)

    print("=== 1. el panel aparece con el clip elegido ===")
    ok(abrir(w, src), "abre el video")
    ok(esperar(w, "typeof fx !== 'undefined' && fx.catalogo && Object.keys(fx.catalogo).length >= 3", 10), "el catalogo de efectos llego del motor")
    e = js(w, "({v: !document.getElementById('sec-fx-video').hidden, a: !document.getElementById('sec-fx-audio').hidden, insp: !document.getElementById('inspector').hidden})")
    ok(not e["v"] and not e["a"] and not e["insp"], "sin elegir un clip no se muestran secciones de efectos", str(e))
    elegir_clip(w, "V1")
    e = js(w, """({v: !document.getElementById('sec-fx-video').hidden, a: !document.getElementById('sec-fx-audio').hidden,
                   opcionesV: [...document.querySelectorAll('#fx-video select option')].map(o => o.value),
                   opcionesA: [...document.querySelectorAll('#fx-audio select option')].map(o => o.value),
                   vacioV: !!document.querySelector('#fx-video .fx__vacio')})""")
    ok(e["v"] and e["a"], "con el clip de video elegido hay efectos de video y de audio (el audio va enlazado)")
    ok(e["opcionesV"][:2] == ["color_basico", "voltear"] and "pasa_altos" not in e["opcionesV"] and e["opcionesA"][0] == "pasa_altos" and "eco" in e["opcionesA"] and "voltear" not in e["opcionesA"] and len(e["opcionesA"]) >= 10, "cada lista ofrece solo los efectos de su categoria", str(e))
    ok(e["vacioV"], "y avisa que todavia no hay ninguno")

    print("=== 2. agregar y ajustar ===")
    agregar(w, "video", "color_basico")
    ok([x["tipo"] for x in efectos_de(w, "V1")] == ["color_basico"], "Agregar pone el efecto en el clip de video")
    ok(js(w, "document.querySelectorAll('#fx-video .fx').length") == 1 and js(w, "document.querySelectorAll('#fx-video input[type=range]').length") == 3,
       "y aparece su tarjeta con sus 3 controles (armados solos con el catalogo)")
    ok(js(w, "document.querySelectorAll('#tira .clip__fx').length") == 1, "el clip lleva la insignia fx en la linea de tiempo")
    antes = js(w, "S.proy.puede_deshacer")
    # arrastrar el control: solo vista previa, NADA se guarda hasta soltar
    w.evaluate_js("""(() => { const r = document.querySelector('#fx-video input[type=range]'); r.value = 0.3; r.dispatchEvent(new Event('input', {bubbles: true})); })()""")
    time.sleep(0.4)
    e = js(w, """({brillo: S.proy.pistas[0].clips[0].efectos[0].params.brillo, filtro: getComputedStyle(document.getElementById('capa-cuadro')).filter,
                   salida: document.querySelector('#fx-video output').textContent})""")
    ok(e["brillo"] == 0.0 and "brightness" in e["filtro"], "mientras se arrastra: se ve en el visor, pero el proyecto no cambia", str(e))
    ok(e["salida"].startswith("0,30"), "y el numero acompana (con coma decimal)", e["salida"])
    w.evaluate_js("document.querySelector('#fx-video input[type=range]').dispatchEvent(new Event('change', {bubbles: true}))")
    time.sleep(0.8)
    ok(efectos_de(w, "V1")[0]["params"]["brillo"] == 0.3, "al soltar se guarda en el motor")
    pasos = 0
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(0.7)
    ok(efectos_de(w, "V1")[0]["params"]["brillo"] == 0.0, "Ctrl+Z deshace SOLO ese ajuste (un cambio por vez, no uno por pixel)")
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyY', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(0.7)
    ok(efectos_de(w, "V1")[0]["params"]["brillo"] == 0.3, "y Ctrl+Y lo vuelve")

    print("=== 3. voltear, apagar, ordenar, quitar ===")
    agregar(w, "video", "voltear")
    e = js(w, "getComputedStyle(document.getElementById('capa-cuadro')).transform")
    ok(e not in (None, "none") and e.startswith("matrix(-1"), "voltear: el visor muestra la imagen en espejo", e)
    w.evaluate_js("document.querySelectorAll('#fx-video .fx__activo')[1].click()")
    time.sleep(0.8)
    ok(efectos_de(w, "V1")[1]["activo"] is False, "apagar un efecto lo deja en la lista, sin perder sus valores")
    ok(js(w, "getComputedStyle(document.getElementById('capa-cuadro')).transform") == "none", "y el visor deja de mostrarlo")
    ok(js(w, "document.querySelectorAll('#fx-video .fx--apagado').length") == 1, "la tarjeta se ve apagada")
    w.evaluate_js("document.querySelectorAll('#fx-video .fx')[1].querySelector('[data-fxk$=\":mover-1\"]').click()")
    time.sleep(0.8)
    ok([x["tipo"] for x in efectos_de(w, "V1")] == ["voltear", "color_basico"], "subir un efecto cambia el orden")
    w.evaluate_js("document.querySelectorAll('#fx-video .fx')[0].querySelector('.fx__btn--quitar').click()")
    time.sleep(0.8)
    ok([x["tipo"] for x in efectos_de(w, "V1")] == ["color_basico"], "quitar saca ese efecto")

    print("=== 4. audio ===")
    agregar(w, "audio", "pasa_altos")
    ok([x["tipo"] for x in efectos_de(w, "A1")] == ["pasa_altos"] and efectos_de(w, "A1")[0]["params"]["frecuencia"] == 80, "el efecto de audio va al clip de audio, con su valor por defecto")
    ok(js(w, "document.querySelector('#fx-audio output').textContent") == "80 Hz", "y se muestra con su unidad")
    ok("exportar" in js(w, "document.querySelector('#fx-audio .fx__nota').textContent"), "la nota avisa que se oye al exportar")
    w.evaluate_js("""(() => { const r = document.querySelector('#fx-audio input[type=range]'); r.value = 200; r.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.8)
    ok(efectos_de(w, "A1")[0]["params"]["frecuencia"] == 200, "se puede ajustar")
    ok(js(w, "document.querySelectorAll('#pista-audio').length") == 1, "(la insignia del audio se dibuja en el espectro)")

    # un efecto sin ajustes (Al reves) es una tarjeta sin controles
    agregar(w, "audio", "invertir_audio")
    e = js(w, "({n: S.proy.pistas[1].clips[0].efectos.length, tarjetas: document.querySelectorAll('#fx-audio .fx').length, rangos: document.querySelectorAll('#fx-audio .fx')[1].querySelectorAll('input[type=range]').length, nombre: document.querySelectorAll('#fx-audio .fx')[1].querySelector('.fx__nombre').textContent})")
    ok(e["n"] == 2 and e["tarjetas"] == 2 and e["rangos"] == 0 and e["nombre"] == "Al revés", "un efecto sin ajustes (Al reves) es una tarjeta sin controles", str(e))
    # agregar cada efecto de audio del catalogo: ninguno rompe el panel ni el proyecto
    for tipo in js(w, "Object.keys(fx.catalogo).filter(k => fx.catalogo[k].categoria === 'audio')"):
        agregar(w, "audio", tipo)
    ok(js(w, "S.proy.pistas[1].clips[0].efectos.length") >= 12 and js(w, "document.querySelectorAll('#fx-audio .fx').length") == js(w, "S.proy.pistas[1].clips[0].efectos.length"),
       "se pueden poner todos los efectos de audio del catalogo a la vez (una tarjeta por cada uno)")

    print("=== 5. un audio extra solo muestra efectos de audio ===")
    w.evaluate_js("llamar('agregar_audio', [%s, 1.0]).then(r => aplicarProyecto(r.proyecto))" % json.dumps(musica))
    time.sleep(1.5)
    elegir_clip(w, "A2")
    e = js(w, "({v: !document.getElementById('sec-fx-video').hidden, a: !document.getElementById('sec-fx-audio').hidden, titulo: document.getElementById('inspector-titulo').textContent})")
    ok(not e["v"] and e["a"], "para un audio extra: sin efectos de video, con los de audio", str(e))

    print("=== 6. errores claros ===")
    w.evaluate_js("operar('cambiar_efecto', ['c1', 'e999', {brillo: 0}])")
    time.sleep(0.8)
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5), "un pedido imposible muestra un aviso (no un error mudo)")
    ok(js(w, "document.querySelector('#avisos .aviso__texto').textContent.length > 5"), "con un texto que se entiende", js(w, "document.querySelector('#avisos .aviso__texto').textContent"))

    print("=== 7. al abrir otro archivo no queda nada del anterior ===")
    ok(abrir(w, src), "se abre otro archivo")
    e = js(w, "({v: !document.getElementById('sec-fx-video').hidden, filtro: document.getElementById('visor').style.getPropertyValue('--filtro'), n: document.querySelectorAll('#tira .clip__fx').length})")
    ok(not e["v"] and e["n"] == 0 and e["filtro"] in ("none", ""), "sin secciones, sin insignias y el visor sin filtro", str(e))

    print("=== 8. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-efectos-app-cache-"), "cache")
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
