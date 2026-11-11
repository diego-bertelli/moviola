# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Cortar silencios y medir el volumen, con la ventana REAL.

Uso:  python -I pruebas/prueba_silencios_app.py

Se maneja el dialogo como una persona (Buscar, mover un control, Cortar, Deshacer) y se comprueba el proyecto
que guarda el motor Y lo que se ve: el resumen, el mapa y los clips de la linea de tiempo.
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-silencios-app-"), "ajustes.json")

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


def clic(w, selector):
    w.evaluate_js("document.querySelector(%s).click()" % json.dumps(selector))
    time.sleep(0.3)


def poner(w, id_, valor):
    w.evaluate_js("(() => { const r = document.getElementById(%s); r.value = %s; r.dispatchEvent(new Event('input', {bubbles: true})); })()" % (json.dumps(id_), valor))
    time.sleep(0.2)


def tecla_en_foco(w, codigo, ctrl=False):
    w.evaluate_js("(document.activeElement || window).dispatchEvent(new KeyboardEvent('keydown', {code: '%s', ctrlKey: %s, bubbles: true, cancelable: true}))"
                  % (codigo, "true" if ctrl else "false"))
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
    mudo = ex.crear_fuente(os.path.join(ex.TMP, "mudo12.mp4"), dur=12, tono=False)
    hablado = os.path.join(ex.TMP, "hablado.mp4")
    ex.ffmpeg("-i", mudo, "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*440*t)*(1-between(t,3,5)-between(t,8,9.5))':s=48000:d=12:c=mono",
              "-c:v", "copy", "-c:a", "aac", "-shortest", hablado)
    sin_audio = ex.crear_fuente(os.path.join(ex.TMP, "sin_audio.mp4"), dur=4, tono=False)

    print("=== 1. el boton ===")
    ok(js(w, "document.getElementById('btn-silencios').disabled") is True, "sin nada abierto, 'Cortar silencios' esta desactivado")
    ok(abrir(w, sin_audio), "se abre un video sin audio")
    ok(js(w, "document.getElementById('btn-silencios').disabled") is True, "y sigue desactivado (no hay audio que analizar)")
    ok(abrir(w, hablado), "se abre un video con audio")
    ok(js(w, "document.getElementById('btn-silencios').disabled") is False, "ahora se activa")

    print("=== 2. buscar ===")
    clic(w, "#btn-silencios")
    ok(js(w, "document.getElementById('dlg-silencios').open"), "se abre el dialogo")
    e = js(w, "({umbral: document.getElementById('sil-umbral-valor').textContent, dur: document.getElementById('sil-duracion-valor').textContent, m: document.getElementById('sil-margen-valor').textContent, res: !document.getElementById('sil-resultado').hidden, cortar: !document.getElementById('sil-cortar').hidden})")
    ok(e["umbral"] == "−35 dB" and e["dur"] == "0,5 s" and e["m"] == "0,10 s" and not e["res"] and not e["cortar"], "con valores por defecto razonables y sin resultados todavia", str(e))
    tecla_en_foco(w, "Space")
    tecla_en_foco(w, "KeyS")
    ok(js(w, "S.reproduciendo") is False and js(w, "document.querySelectorAll('#tira .clip').length") == 1, "con el dialogo abierto, Espacio y S no llegan al editor")
    clic(w, "#sil-analizar")
    ok(esperar(w, "!document.getElementById('sil-resultado').hidden", 30), "Buscar silencios muestra el resultado")
    e = js(w, "({resumen: document.getElementById('sil-resumen').textContent, lista: [...document.querySelectorAll('#sil-lista li')].map(l => l.textContent), cortar: document.getElementById('sil-cortar').textContent, visible: !document.getElementById('sil-cortar').hidden})")
    ok("2 silencios" in e["resumen"] and "3,1 s" in e["resumen"] and "8,9 s" in e["resumen"], "el resumen dice cuantos, cuanto suman y como quedaria", e["resumen"])
    ok(len(e["lista"]) == 2 and "00:03,10" in e["lista"][0] and "00:04,90" in e["lista"][0], "la lista dice donde estan", str(e["lista"]))
    ok(e["visible"] and e["cortar"] == "Cortar los 2 silencios", "y el boton dice exactamente que va a hacer", e["cortar"])
    ok(js(w, "S.proy.pistas[0].clips.length") == 1, "buscar NO cambia el proyecto")
    poner(w, "sil-umbral", -40)
    ok(js(w, "document.getElementById('sil-resultado').hidden") is True and js(w, "document.getElementById('sil-cortar').hidden") is True,
       "mover un control descarta el resultado (ya no valdria para los valores nuevos)")
    poner(w, "sil-umbral", -35)
    poner(w, "sil-duracion", 3.0)
    clic(w, "#sil-analizar")
    ok(esperar(w, "!document.getElementById('sil-resultado').hidden", 30), "con 'dura al menos 3 s'...")
    e = js(w, "({resumen: document.getElementById('sil-resumen').textContent, cortar: document.getElementById('sil-cortar').hidden})")
    ok("No se encontraron" in e["resumen"] and e["cortar"], "...no hay nada para cortar y lo dice (sin boton de cortar)", e["resumen"])
    poner(w, "sil-duracion", 0.5)
    clic(w, "#sil-analizar")
    ok(esperar(w, "!document.getElementById('sil-cortar').hidden", 30), "con los valores de antes vuelve a encontrarlos")

    print("=== 3. cortar ===")
    clic(w, "#sil-cortar")
    ok(esperar(w, "document.getElementById('dlg-silencios').open === false", 15), "Cortar cierra el dialogo")
    e = js(w, "({dur: S.proy.duracion, clips: S.proy.pistas[0].clips.length, audio: S.proy.pistas[1].clips.length, dibujados: document.querySelectorAll('#tira .clip').length, rep: S.reproduciendo})")
    ok(abs(e["dur"] - 8.9) < 0.1 and e["clips"] == 3 and e["audio"] == 3 and e["dibujados"] == 3, "el proyecto queda de 8,9 s con 3 clips de video y 3 de audio", str(e))
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5), "y avisa lo que hizo")
    ok("2 silencios" in js(w, "document.querySelector('#avisos .aviso__texto').textContent") and "Deshacer" in js(w, "document.querySelector('#avisos .aviso__texto').textContent"),
       "diciendo como volver atras", js(w, "document.querySelector('#avisos .aviso__texto').textContent"))
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(0.9)
    e = js(w, "({dur: S.proy.duracion, clips: S.proy.pistas[0].clips.length})")
    ok(abs(e["dur"] - 12.0) < 0.05 and e["clips"] == 1, "UN solo Ctrl+Z devuelve los dos silencios", str(e))

    print("=== 4. medir el volumen ===")
    w.evaluate_js("(() => { const c = S.proy.pistas.find(p => p.id === 'A1').clips[0]; S.sel = {grupo: c.grupo, clip: c.id}; actualizarSeleccion(); })()")
    time.sleep(0.5)
    ok(js(w, "!document.getElementById('btn-medir-volumen').closest('details').hidden"), "con el clip de audio elegido aparece 'Medir el volumen del proyecto'")
    clic(w, "#btn-medir-volumen")
    ok(esperar(w, "document.getElementById('medida-volumen').textContent.includes('LUFS')", 30), "mide y muestra LUFS, pico y rango")
    txt = js(w, "document.getElementById('medida-volumen').textContent")
    import re
    m = re.search(r"([−-]?\d+,\d) LUFS · pico ([−-]?\d+,\d) dB · rango (\d+,\d) LU", txt)
    ok(m is not None and -20 < float(m.group(1).replace("−", "-").replace(",", ".")) < -5, "con numeros razonables para un tono de 0,5", txt)
    w.evaluate_js("operar('dividir', [tiempoDe(100)])")
    time.sleep(0.9)
    ok(js(w, "document.getElementById('medida-volumen').hidden") is True, "una medicion vieja se borra al editar")

    print("=== 5. un archivo de solo audio ===")
    solo = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 700)
    ok(abrir(w, solo), "se abre un mp3 (sin silencios: es un tono continuo)")
    clic(w, "#btn-silencios")
    clic(w, "#sil-analizar")
    ok(esperar(w, "!document.getElementById('sil-resultado').hidden", 30), "se puede buscar")
    ok("No se encontraron" in js(w, "document.getElementById('sil-resumen').textContent"), "y no inventa silencios donde no hay", js(w, "document.getElementById('sil-resumen').textContent"))
    clic(w, "#sil-cerrar")
    ok(js(w, "document.getElementById('dlg-silencios').open") is False, "Cerrar cierra el dialogo")

    print("=== 6. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-silencios-app-cache-"), "cache")
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
