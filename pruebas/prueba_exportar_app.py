# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del dialogo "Exportar…" con la ventana REAL.

Uso:  python -I pruebas/prueba_exportar_app.py

Se maneja el dialogo como lo haria una persona (clics, teclas) y se comprueba el archivo que sale.
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-exportar-app-"), "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []
API = None
DESTINO = os.path.join(ex.TMP, "destino")
LLAMADOS_EXPLORADOR = []


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
    time.sleep(0.25)


def tecla_en_foco(w, codigo, ctrl=False):
    """Como una persona: la tecla le llega al elemento que tiene el foco."""
    w.evaluate_js("(document.activeElement || window).dispatchEvent(new KeyboardEvent('keydown', {code: '%s', ctrlKey: %s, bubbles: true, cancelable: true}))"
                  % (codigo, "true" if ctrl else "false"))
    time.sleep(0.5)


def pasos(w):
    return js(w, """({armar: !document.getElementById('exp-armar').hidden, progreso: !document.getElementById('exp-progreso').hidden,
                      resultado: !document.getElementById('exp-resultado').hidden, abierto: document.getElementById('dlg-exportar').open})""")


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
    os.makedirs(DESTINO, exist_ok=True)
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"))
    largo = ex.crear_fuente(os.path.join(ex.TMP, "largo.mp4"), dur=60, w=1280, h=720)
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 700)

    print("=== 1. el boton y el atajo ===")
    ok(js(w, "document.getElementById('btn-exportar').disabled") is True, "sin nada abierto, el boton Exportar esta desactivado")
    ok(abrir(w, src), "abre el video")
    ok(js(w, "document.getElementById('btn-exportar').disabled") is False, "con el video abierto se activa")
    ok(js(w, "document.getElementById('dlg-exportar').open") is False, "y el dialogo esta cerrado")
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyE', ctrlKey: true, bubbles: true, cancelable: true}))")
    ok(esperar(w, "document.getElementById('dlg-exportar').open", 5), "Ctrl+E abre el dialogo")
    ok(esperar(w, "document.getElementById('exp-archivo').textContent !== ''", 5), "propone el nombre del archivo")
    e = js(w, """({carpeta: document.getElementById('exp-carpeta').textContent, nombre: document.getElementById('exp-nombre').value,
                   archivo: document.getElementById('exp-archivo').textContent,
                   formato: [...document.querySelectorAll('[data-formato][aria-checked=true]')].map(b => b.dataset.formato),
                   video: !document.getElementById('exp-campo-video').hidden, encuadre: !document.getElementById('exp-encuadre').hidden,
                   norm: !document.getElementById('exp-campo-norm').hidden, gpu: !document.getElementById('exp-gpu').hidden,
                   foco: document.activeElement.id})""")
    ok(e["carpeta"] == os.path.dirname(src) and e["nombre"] == "src", "carpeta y nombre del archivo original", f"{e['carpeta']} / {e['nombre']}")
    ok(e["archivo"] == "Se guardará como: src-v1.mp4", "dice como se va a llamar el archivo", e["archivo"])
    ok(e["formato"] == ["original"] and e["video"] and not e["encuadre"] and e["norm"] and not e["gpu"],
       "por defecto: original, sin encuadre, con normalizar, sin aviso de GPU", str(e))
    ok(e["foco"] == "exp-iniciar", "el foco queda en el boton Exportar (se usa con el teclado)", e["foco"])

    print("=== 2. con el dialogo abierto, las teclas no llegan al editor ===")
    tecla_en_foco(w, "Space")
    tecla_en_foco(w, "KeyS")
    tecla_en_foco(w, "Delete")
    e = js(w, "({rep: S.reproduciendo, clips: document.querySelectorAll('#tira .clip').length, dur: S.duracion})")
    ok(e["rep"] is False and e["clips"] == 1 and abs(e["dur"] - 12.0) < 0.1, "Espacio, S y Supr no reproducen, ni cortan, ni borran", str(e))

    print("=== 3. elegir formato y destino ===")
    clic(w, '[data-formato="vertical"]')
    e = js(w, """({enc: !document.getElementById('exp-encuadre').hidden, foco: !document.getElementById('exp-foco').hidden,
                   archivo: document.getElementById('exp-archivo').textContent,
                   activo: [...document.querySelectorAll('[data-formato][aria-checked=true]')].map(b => b.dataset.formato)})""")
    ok(e["activo"] == ["vertical"] and e["enc"] and e["foco"], "Vertical: aparece el encuadre y las posiciones", str(e))
    clic(w, '[data-encuadre="barras"]')
    ok(js(w, "document.getElementById('exp-foco').hidden") is True, "con barras no hacen falta las posiciones")
    clic(w, '[data-encuadre="recortar"]')
    clic(w, '[data-formato="mp3"]')
    e = js(w, """({enc: !document.getElementById('exp-encuadre').hidden, archivo: document.getElementById('exp-archivo').textContent})""")
    ok(not e["enc"] and e["archivo"] == "Se guardará como: src-v1.mp3", "MP3: sin encuadre y con la extension de audio", str(e))
    clic(w, '[data-formato="vertical"]')
    clic(w, "#exp-cambiar")
    ok(esperar(w, "document.getElementById('exp-carpeta').textContent === " + json.dumps(DESTINO), 10), "Cambiar… pone la carpeta que elige la persona")
    w.evaluate_js("(() => { const n = document.getElementById('exp-nombre'); n.value = 'mi reel'; n.dispatchEvent(new Event('input', {bubbles: true})); })()")
    ok(esperar(w, "document.getElementById('exp-archivo').textContent === 'Se guardará como: mi reel-v1.mp4'", 5), "cambiar el nombre actualiza el archivo propuesto",
       js(w, "document.getElementById('exp-archivo').textContent"))
    w.evaluate_js("(() => { const x = document.getElementById('exp-foco-x'); x.value = 50; x.dispatchEvent(new Event('input', {bubbles: true})); })()")

    print("=== 4. exportar y ver el resultado ===")
    clic(w, "#exp-iniciar")
    ok(esperar(w, "!document.getElementById('exp-resultado').hidden", 90), "termina y muestra el resultado")
    e = js(w, """({titulo: document.getElementById('exp-resultado-titulo').textContent,
                   lineas: [...document.querySelectorAll('#exp-resultado-lineas li')].map(l => l.textContent),
                   aviso: !document.getElementById('exp-resultado-aviso').hidden, barra: document.getElementById('exp-barra').style.width,
                   foco: document.activeElement.id})""")
    salida = os.path.join(DESTINO, "mi reel-v1.mp4")
    ok(os.path.isfile(salida), "el archivo existe: mi reel-v1.mp4")
    ok(any("mi reel-v1.mp4" in l for l in e["lineas"]) and any("1080 × 1920" in l for l in e["lineas"]) and any("Duración" in l for l in e["lineas"]),
       "el resultado dice nombre, carpeta, duracion, tamano e imagen", " | ".join(e["lineas"]))
    ok(not e["aviso"], "y no muestra avisos (todo salio bien)")
    ok(any(l.endswith("a 30 cuadros por segundo") for l in e["lineas"]), "los cuadros por segundo salen como numero", " | ".join(e["lineas"]))
    ok(e["foco"] == "exp-cerrar", "el foco pasa a Listo", e["foco"])
    if os.path.isfile(salida):
        v, a, dur = ex.sondear(salida)
        ok((v["width"], v["height"]) == (1080, 1920) and a is not None and abs(dur - 12.0) < 0.15, "es de 1080x1920, con audio, de 12 s", f"{v['width']}x{v['height']} {dur:.2f}s")
        codigos = ex.leer_codigos(salida, lambda x, y: (x * 1920 / 360 - (640 * 1920 / 360 - 1080) / 2, y * 1920 / 360))
        ok(codigos == list(range(360)), "y tiene los 360 cuadros en orden", f"{len(codigos)} cuadros")
    LLAMADOS_EXPLORADOR.clear()
    clic(w, "#exp-mostrar")
    time.sleep(0.4)
    ok(len(LLAMADOS_EXPLORADOR) == 1 and LLAMADOS_EXPLORADOR[0][-1].endswith("mi reel-v1.mp4"), "Mostrar en la carpeta abre el explorador con ese archivo", str(LLAMADOS_EXPLORADOR))

    print("=== 5. Exportar otra: recuerda lo elegido y no pisa nada ===")
    clic(w, "#exp-otra")
    e = js(w, """({paso: !document.getElementById('exp-armar').hidden, carpeta: document.getElementById('exp-carpeta').textContent,
                   activo: [...document.querySelectorAll('[data-formato][aria-checked=true]')].map(b => b.dataset.formato),
                   archivo: document.getElementById('exp-archivo').textContent, nombre: document.getElementById('exp-nombre').value})""")
    ok(e["paso"] and e["carpeta"] == DESTINO and e["activo"] == ["vertical"], "vuelve al formulario con la carpeta y el formato de antes", str(e))
    w.evaluate_js("(() => { const n = document.getElementById('exp-nombre'); n.value = 'mi reel'; n.dispatchEvent(new Event('input', {bubbles: true})); })()")
    ok(esperar(w, "document.getElementById('exp-archivo').textContent === 'Se guardará como: mi reel-v2.mp4'", 5), "el nombre propuesto ya es la v2 (no pisa la primera)",
       js(w, "document.getElementById('exp-archivo').textContent"))

    print("=== 6. errores: se ven en el dialogo y no se pierde lo elegido ===")
    API_OVERRIDE["ruta"] = os.path.join(ex.TMP, "no_existe")
    clic(w, "#exp-cambiar")
    esperar(w, "document.getElementById('exp-carpeta').textContent === " + json.dumps(API_OVERRIDE["ruta"]), 10)
    clic(w, "#exp-iniciar")
    ok(esperar(w, "!document.getElementById('exp-error').hidden", 10), "una carpeta que no existe muestra el error")
    e = js(w, "({txt: document.getElementById('exp-error').textContent, rol: document.getElementById('exp-error').getAttribute('role')})")
    ok("no existe" in e["txt"] and e["rol"] == "alert", "con un texto claro, anunciado como alerta", e["txt"])
    ok(pasos(w)["armar"], "y se queda en el formulario")
    API_OVERRIDE["ruta"] = DESTINO
    clic(w, "#exp-cambiar")
    esperar(w, "document.getElementById('exp-carpeta').textContent === " + json.dumps(DESTINO), 10)

    print("=== 7. cancelar una exportacion larga ===")
    ok(abrir(w, largo), "se abre un video de 60 s con el dialogo abierto (como al soltar un archivo encima)")
    ok(esperar(w, "document.getElementById('dlg-exportar').open === false", 5), "y el dialogo se cierra solo: ya no habla del archivo anterior")
    clic(w, "#btn-exportar")
    ok(esperar(w, "document.getElementById('dlg-exportar').open && document.getElementById('exp-nombre').value === 'largo'", 5), "se vuelve a abrir con el nombre del archivo nuevo")
    clic(w, '[data-formato="vertical"]')
    w.evaluate_js("(() => { const n = document.getElementById('exp-nombre'); n.value = 'largo'; n.dispatchEvent(new Event('input', {bubbles: true})); })()")
    time.sleep(0.4)
    clic(w, "#exp-iniciar")
    ok(esperar(w, "!document.getElementById('exp-progreso').hidden", 10), "pasa a la pantalla de progreso")
    ok(esperar(w, "parseFloat(document.getElementById('exp-barra').style.width) > 0", 30), "la barra avanza")
    t = js(w, "document.getElementById('exp-progreso-texto').textContent")
    ok("%" in t, "y dice el porcentaje", t)
    e = js(w, "(() => { const ev = new Event('cancel', {cancelable: true}); document.getElementById('dlg-exportar').dispatchEvent(ev); return ev.defaultPrevented; })()")
    ok(e is True, "Esc no cierra el dialogo mientras se exporta")
    clic(w, "#exp-cancelar-export")
    ok(esperar(w, "!document.getElementById('exp-armar').hidden && !document.getElementById('exp-error').hidden", 30), "Cancelar exportacion vuelve al formulario con un aviso")
    ok("cancelada" in js(w, "document.getElementById('exp-error').textContent"), "que dice que se cancelo")
    ok(not [n for n in os.listdir(DESTINO) if n.startswith("largo") or n.startswith(".moviola") or "parcial" in n], "y no queda ningun archivo a medias", str(os.listdir(DESTINO)))

    print("=== 8. cerrar devuelve los atajos ===")
    clic(w, "#exp-cancelar-armar")
    ok(js(w, "document.getElementById('dlg-exportar').open") is False, "Cancelar cierra el dialogo")
    w.evaluate_js("irA(100, 540)")
    time.sleep(0.6)
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyS', bubbles: true, cancelable: true}))")
    time.sleep(0.8)
    ok(js(w, "document.querySelectorAll('#tira .clip').length") == 2, "y S vuelve a cortar")

    print("=== 9. un archivo de solo audio ===")
    ok(abrir(w, musica), "se abre un mp3")
    clic(w, "#btn-exportar")
    ok(esperar(w, "document.getElementById('dlg-exportar').open && document.getElementById('exp-archivo').textContent !== ''", 5), "se abre el dialogo")
    e = js(w, """({video: !document.getElementById('exp-campo-video').hidden, enc: !document.getElementById('exp-encuadre').hidden,
                   activo: [...document.querySelectorAll('[data-formato][aria-checked=true]')].map(b => b.dataset.formato),
                   rot: document.getElementById('exp-rotulo-audio').textContent, archivo: document.getElementById('exp-archivo').textContent})""")
    ok(not e["video"] and not e["enc"] and e["activo"] == ["wav"] and e["rot"] == "Formato del audio",
       "sin opciones de video; el formato por defecto es WAV", str(e))
    clic(w, "#exp-normalizar")
    clic(w, "#exp-iniciar")
    ok(esperar(w, "!document.getElementById('exp-resultado').hidden", 60), "exporta")
    e = js(w, "[...document.querySelectorAll('#exp-resultado-lineas li')].map(l => l.textContent)")
    wav = os.path.join(DESTINO, "musica-v1.wav")
    ok(os.path.isfile(wav) and any("normalizado" in l for l in e) and not any("Imagen" in l for l in e), "un WAV normalizado, sin datos de imagen", " | ".join(e))
    clic(w, "#exp-cerrar")
    ok(pasos(w)["abierto"] is False, "Listo cierra el dialogo")

    print("=== 10. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


API_OVERRIDE = {"ruta": DESTINO}


def main():
    global API
    API = app.API()
    API.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-exportar-app-cache-"), "cache")
    API.elegir_carpeta = lambda: {"ruta": API_OVERRIDE["ruta"]}          # el selector del sistema no se puede manejar desde aca
    popen_real = app.subprocess.Popen

    class PopenFalso(popen_real):                                           # solo el explorador es de mentira; ffmpeg anda
        def __new__(cls, cmd, *a, **k):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "explorer":
                LLAMADOS_EXPLORADOR.append(list(cmd))
                return object.__new__(cls)
            return popen_real(cmd, *a, **k)

        def __init__(self, *a, **k):
            pass
    app.subprocess.Popen = PopenFalso
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
