# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Editar por texto en la interfaz, con la ventana REAL: el panel, elegir palabras (clic, Mayus + clic), Supr, Ctrl+Z, corregir una palabra,
muletillas, pausas, el aviso de «el video cambio», karaoke sobre el visor y (si hay whisper y una voz de Windows) transcribir de verdad.

Uso:  python -I pruebas/prueba_texto_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-texto-app-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
import voz  # noqa: E402
from motor import subtitulos as sub  # noqa: E402

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


def clic(w, id_):
    w.evaluate_js("document.getElementById(%s).click()" % json.dumps(id_))
    time.sleep(0.5)


def tecla(w, clave, ctrl=False):
    codigo = ("Key" + clave.upper()) if len(clave) == 1 else clave
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: %s, code: %s, ctrlKey: %s, bubbles: true, cancelable: true}))" % (json.dumps(clave), json.dumps(codigo), "true" if ctrl else "false"))
    time.sleep(0.9)


def raton(w, indice, tipo="mousedown", mayus=False):
    w.evaluate_js("""(() => { const s = document.querySelectorAll('.tx__pal')[%d]; s.dispatchEvent(new MouseEvent(%s, {bubbles: true, cancelable: true, button: 0, buttons: 1, shiftKey: %s})); })()""" % (indice, json.dumps(tipo), "true" if mayus else "false"))
    time.sleep(0.4)


def palabras_js(n=12, pausa_larga=None):
    """El texto de 12 palabras (w0..w11) de 0,9 s, en 4 frases. Con pausa_larga=(indice, segundos): una pausa grande despues de esa palabra."""
    ps = []
    t = 0.4
    for i in range(n):
        extra = pausa_larga[1] if pausa_larga and i == pausa_larga[0] + 1 else 0.0
        t += 0.0
        a = round(t, 3)
        habla = round(a + 0.75, 3)
        fin = round(a + 0.9, 3)
        ps.append({"texto": "w%d" % i, "inicio": a, "fin": fin, "voz": round(a + 0.05, 3), "habla": habla})
        t = fin
    if pausa_larga:
        # la pausa larga se cuela en el audio entre la palabra k y la k+1: la voz de k+1 se atrasa y el montaje sigue siendo el mismo
        k, largo = pausa_larga
        for j in range(k + 1, n):
            ps[j] = dict(ps[j], inicio=round(ps[j]["inicio"] + largo, 3), fin=round(ps[j]["fin"] + largo, 3), voz=round(ps[j]["voz"] + largo, 3), habla=round(ps[j]["habla"] + largo, 3))
        ps[k]["fin"] = ps[k + 1]["inicio"] = round(ps[k]["habla"] + largo / 2.0, 3)
    frases = []
    for k in range(0, n, 3):
        frases.append({"inicio": ps[k]["inicio"], "fin": ps[min(k + 2, n - 1)]["fin"], "texto": " ".join(x["texto"] for x in ps[k:k + 3]), "palabras": list(range(k, min(k + 3, n)))})
    return frases, ps


def correr(w, hablado):
    try:
        _correr(w, hablado)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w, hablado):
    time.sleep(3)
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=14)
    w.evaluate_js("pedirAbrir(%s)" % json.dumps(src))
    ok(esperar(w, "S.proy && S.ruta && document.getElementById('cargando').hidden", 30), "se abre el video")

    print("=== 1. el panel ===")
    ok(not js(w, "document.getElementById('btn-texto').disabled"), "con un proyecto abierto, «Editar por texto…» se enciende")
    clic(w, "btn-texto")
    ok(esperar(w, "!document.getElementById('panel-texto').hidden", 5), "se abre el panel (al costado: el video sigue a la vista)")
    e = js(w, "({vacio: !document.getElementById('tx-vacio').hidden, texto: document.getElementById('tx-vacio-texto').textContent, herr: document.getElementById('tx-herr').hidden, area: document.getElementById('tx-texto').hidden, visor: document.getElementById('visor').getBoundingClientRect().width > 100})")
    ok(e["vacio"] and e["herr"] and e["area"] and "Todavía no hay texto" in e["texto"] and e["visor"], "sin transcripcion: explica que hay que transcribir y no muestra herramientas", e["texto"][:60])
    frases, ps = palabras_js()
    w.evaluate_js("operar('subtitulos_poner', [%s, %s])" % (json.dumps(frases), json.dumps(ps)))
    ok(esperar(w, "document.querySelectorAll('.tx__pal').length === 12", 10), "al ponerse las palabras, el panel las muestra (12)")
    e = js(w, "({vacio: document.getElementById('tx-vacio').hidden, parrafos: document.querySelectorAll('.tx__parrafo').length, texto: document.getElementById('tx-texto').innerText.replace(/\\s+/g, ' ')})")
    ok(e["vacio"] and e["parrafos"] == 1 and "w0 w1 w2" in e["texto"], "un parrafo (las pausas son cortas)", e["texto"][:60])

    print("=== 2. elegir y borrar ===")
    raton(w, 4)
    ok(js(w, "tx.sel.size") == 1 and js(w, "document.querySelectorAll('.tx__pal--sel').length") == 1, "un clic elige una palabra")
    w.evaluate_js("window.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}))")
    time.sleep(0.8)
    t_cursor = js(w, "tiempoDe(S.cuadro)")
    ok(abs(t_cursor - 4.05) < 0.1, "y el cursor va a donde suena (4,05 s)", str(t_cursor))
    raton(w, 6, mayus=True)
    ok(js(w, "tx.sel.size") == 3 and js(w, "document.getElementById('tx-sel').textContent") == "3 palabras · 2,7 s", "Mayus + clic elige el rango (3 palabras, 2,7 s)", js(w, "document.getElementById('tx-sel').textContent"))
    ok(js(w, "document.getElementById('tx-borrar').textContent") == "Borrar 3" and not js(w, "document.getElementById('tx-borrar').disabled"), "el boton dice «Borrar 3»")
    tecla(w, "Delete")
    ok(esperar(w, "Math.abs(S.proy.duracion - 11.3) < 0.01", 10), "Supr saca las 3 palabras del montaje (14 s -> 11,3 s)", str(js(w, "S.proy.duracion")))
    e = js(w, "({n: palabrasDe().length, spans: document.querySelectorAll('.tx__pal').length, sel: tx.sel.size, clips: S.proy.pistas[0].clips.length, desact: S.proy.subtitulos_desactualizados, frases: S.proy.subtitulos.frases.map(f => f.texto)})")
    ok(e["n"] == 9 and e["spans"] == 9 and e["sel"] == 0 and e["desact"] is False, "el texto ya no tiene esas palabras, no queda nada elegido y los subtitulos siguen al dia", str(e))
    ok(e["frases"] == ["w0 w1 w2", "w3", "w7 w8", "w9 w10 w11"], "las frases se rearmaron", str(e["frases"]))
    tecla(w, "z", ctrl=True)
    ok(esperar(w, "Math.abs(S.proy.duracion - 14.0) < 0.01 && palabrasDe().length === 12", 10), "Ctrl+Z devuelve las palabras y el video entero", str(js(w, "S.proy.duracion")))
    ok(js(w, "S.proy.pistas[0].clips.length") == 1, "(un solo clip otra vez)")
    tecla(w, "Delete")
    ok(js(w, "S.proy.duracion") == 14.0, "Supr sin elegir nada no borra ningun clip (el panel se queda con la tecla)")

    print("=== 3. corregir una palabra ===")
    w.evaluate_js("""(() => { const s = document.querySelectorAll('.tx__pal')[2]; s.dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true})); })()""")
    time.sleep(0.4)
    ok(js(w, "!!document.querySelector('.tx__editar')"), "doble clic abre un campo para corregirla")
    w.evaluate_js("""(() => { const c = document.querySelector('.tx__editar'); c.value = 'Hola'; c.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })()""")
    ok(esperar(w, "palabrasDe()[2].texto === 'Hola' && S.proy.subtitulos.frases[0].texto === 'w0 w1 Hola'", 10), "Enter la cambia (y la frase que la tiene)")
    tecla(w, "z", ctrl=True)
    ok(esperar(w, "palabrasDe()[2].texto === 'w2'", 10), "Ctrl+Z la deshace")

    print("=== 4. muletillas ===")
    for i, t in ((3, "eh"), (6, "o"), (7, "sea")):
        w.evaluate_js("operar('palabra_cambiar', [palabrasDe()[%d].id, %s])" % (i, json.dumps(t)))
        time.sleep(0.5)
    w.evaluate_js("document.querySelector('#tx-mule summary').click()")
    ok(js(w, "document.getElementById('tx-mule-n').textContent") == "3 palabras en el texto", "cuenta las muletillas del texto (eh, o sea)", js(w, "document.getElementById('tx-mule-n').textContent"))
    clic(w, "tx-mule-marcar")
    e = js(w, "[...document.querySelectorAll('.tx__pal--sel')].map(s => s.textContent)")
    ok(e == ["eh", "o", "sea"], "«Marcarlas» las elige para revisarlas", str(e))
    w.evaluate_js("document.querySelector('[data-mule=\"ehm\"]').checked = false; document.querySelector('[data-mule=\"ehm\"]').dispatchEvent(new Event('change'))")
    ok(js(w, "document.getElementById('tx-mule-n').textContent") == "2 palabras en el texto", "desmarcar un tipo cambia la cuenta")
    clic(w, "tx-borrar")
    ok(esperar(w, "palabrasDe().length === 9", 10), "Borrar las saca (los dos «o sea» juntos y el «eh»)")
    tecla(w, "z", ctrl=True)
    esperar(w, "palabrasDe().length === 12", 10)

    print("=== 5. pausas largas ===")
    frases2, ps2 = palabras_js(pausa_larga=(5, 2.0))
    w.evaluate_js("operar('subtitulos_poner', [%s, %s])" % (json.dumps(frases2), json.dumps(ps2)))
    time.sleep(0.8)
    e = js(w, "({parrafos: document.querySelectorAll('.tx__parrafo').length, tiempos: [...document.querySelectorAll('.tx__tiempo')].map(b => b.textContent)})")
    ok(e["parrafos"] == 2, "una pausa de 2 s parte el texto en dos parrafos con su minuto", str(e))
    w.evaluate_js("document.querySelector('#tx-pausas summary').click()")
    ok("1 pausa" in js(w, "document.getElementById('tx-pausa-n').textContent") and "se ahorran 1,9 s" in js(w, "document.getElementById('tx-pausa-n').textContent"), "«Pausas largas» cuenta 1 pausa y lo que se ahorra (2,2 - 0,3 = 1,9 s)", js(w, "document.getElementById('tx-pausa-n').textContent"))
    dur0 = js(w, "S.proy.duracion")
    clic(w, "tx-pausa-acortar")
    ok(esperar(w, "Math.abs(%s - S.proy.duracion - 1.9) < 0.05" % dur0, 10), "Acortarlas saca 1,9 s del video", "%s -> %s" % (dur0, js(w, "S.proy.duracion")))
    ok(js(w, "palabrasDe().length") == 12 and js(w, "S.proy.subtitulos_desactualizados") is False, "sin perder palabras y al dia")
    tecla(w, "z", ctrl=True)
    esperar(w, "Math.abs(S.proy.duracion - %s) < 0.01" % dur0, 10)

    print("=== 6. si el video cambia por otro lado ===")
    w.evaluate_js("operar('velocidad', [S.proy.pistas[0].clips[0].grupo, 2.0, true, false])")
    ok(esperar(w, "S.proy.subtitulos_desactualizados === true", 10), "cambiar la velocidad deja las palabras desactualizadas")
    e = js(w, "({aviso: !document.getElementById('tx-desact').hidden, borrar: document.getElementById('tx-borrar').disabled, pausa: document.getElementById('tx-pausa-acortar').disabled})")
    ok(e["aviso"] and e["borrar"] and e["pausa"], "el panel avisa y apaga Borrar y Acortar (no se corta a ciegas)", str(e))
    clic(w, "tx-al-dia")
    ok(esperar(w, "S.proy.subtitulos_desactualizados === false && document.getElementById('tx-desact').hidden", 10), "«Están bien así» lo confirma")
    tecla(w, "z", ctrl=True)
    tecla(w, "z", ctrl=True)

    print("=== 7. karaoke sobre el visor y la palabra que suena ===")
    w.evaluate_js("operar('subtitulos_poner', [%s, %s])" % (json.dumps(frases), json.dumps(ps)))
    time.sleep(0.8)
    w.evaluate_js("operar('subtitulos_estilo', [{karaoke: true, resaltado: 'amarillo'}])")
    time.sleep(0.8)
    w.evaluate_js("irA(cuadroDe(1.4))")
    time.sleep(1.0)
    e = js(w, "({oculto: document.getElementById('subtitulo-visor').hidden, hijos: [...document.getElementById('subtitulo-visor').children].map(c => [c.textContent, c.style.color]), ahora: document.querySelector('.tx__pal--ahora')?.textContent})")
    ok(not e["oculto"] and [h[0] for h in e["hijos"]] == ["w0", "w1", "w2"] and [bool(h[1]) for h in e["hijos"]] == [False, True, False], "en el visor la palabra que se dice va resaltada (la 2.a a 1,4 s)", str(e["hijos"]))
    ok(e["ahora"] == "w1", "y en el panel esta marcada la palabra que suena", str(e["ahora"]))
    w.evaluate_js("irA(cuadroDe(2.9))")
    time.sleep(0.8)
    e = js(w, "[...document.getElementById('subtitulo-visor').children].map(c => !!c.style.color)")
    ok(e == [False, False, True], "al avanzar, el resalte pasa a la siguiente (3.a a 2,9 s)", str(e))
    clic(w, "tx-cerrar")
    ok(js(w, "document.getElementById('panel-texto').hidden") and not js(w, "document.body.classList.contains('con-texto')"), "la ✕ cierra el panel")

    print("=== 8. transcribir de verdad (whisper + voz de Windows) ===")
    est = sub.estado_transcripcion()
    if not (est["disponible"] and hablado):
        print("  SALTEADA  (falta %s)" % ("whisper o su modelo" if not est["disponible"] else "una voz de Windows"))
    else:
        w.evaluate_js("abrir(%s)" % json.dumps(hablado))
        esperar(w, "S.proy && S.ruta && S.ruta.includes('hablado') && document.getElementById('cargando').hidden", 30)
        clic(w, "btn-texto")
        esperar(w, "!document.getElementById('panel-texto').hidden", 5)
        ok(js(w, "!document.getElementById('tx-vacio-campos').hidden"), "ofrece «Transcribir» con el idioma")
        clic(w, "tx-transcribir")
        ok(esperar(w, "!document.getElementById('tx-prog').hidden", 10), "mientras transcribe muestra el avance")
        ok(esperar(w, "palabrasDe().length > 10", 120), "termina: las palabras aparecen en el panel")
        t = js(w, "document.getElementById('tx-texto').innerText.toLowerCase()")
        ok("hola" in t and "subtítulos" in t and "distinta" in t, "con sus tildes", t.replace("\n", " ")[:80])
        w.evaluate_js("document.querySelector('#tx-mule').open = true; const c = document.querySelector('[data-mule=ehm]'); c.checked = true; c.dispatchEvent(new Event('change'))")
        time.sleep(0.3)
        clic(w, "tx-mule-marcar")
        marc = js(w, "[...document.querySelectorAll('.tx__pal--sel')].map(s => s.textContent)")
        print("      palabras:", js(w, "palabrasDe().map(x => x.texto).join(' ')"))
        ok(any(x.lower().startswith("eh") for x in marc), "marca la muletilla «eh» que dijo la voz", str(marc))
        dur0 = js(w, "S.proy.duracion")
        clic(w, "tx-borrar")
        ok(esperar(w, "S.proy.duracion < %s - 0.1" % dur0, 10), "y al borrarla el video se acorta", "%s -> %s" % (dur0, js(w, "S.proy.duracion")))
        ok(js(w, "S.proy.subtitulos_desactualizados") is False, "los subtitulos siguen al dia")

    print("=== 9. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    try:
        os.remove(os.path.join(RAIZ, "ultimo-error.log"))
    except OSError:
        pass
    hablado = None
    if sub.estado_transcripcion()["disponible"]:
        hablado, _ = voz.video_hablado(os.path.join(ex.TMP, "hablado.mp4"), ["Hola, esto es una prueba de subtítulos.", "Ahora hablamos de otra cosa muy distinta, eh, bueno, creo que sí."], pausa=1.0)
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1400, height=900)
        webview.start(correr, (webview.windows[0], hablado))
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
