# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""«Acerca de Moviola»: los datos del motor (version, autoria, licencia, herramientas) y el dialogo en la ventana REAL (boton «i», enlace de la
pantalla de inicio, F1, cerrar, «Ver la licencia»), tambien en un celular.

Uso:  python -I pruebas/prueba_acerca_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-acerca-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []
abiertos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def js(w, expresion):
    r = w.evaluate_js("JSON.stringify((() => { return " + expresion + "; })())")
    return json.loads(r) if r else None


def esperar(w, condicion, tiempo=20.0, paso=0.2):
    t0 = time.time()
    while time.time() - t0 < tiempo:
        try:
            if js(w, condicion):
                return True
        except Exception:
            pass
        time.sleep(paso)
    return False


def correr(w, api):
    try:
        _correr(w, api)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w, api):
    time.sleep(3)
    print("=== 1. los datos del motor ===")
    d = api.acerca_de()
    ok(d["nombre"] == "Moviola" and d["version"] == app.VERSION and d["licencia"].startswith("GNU GPL v3") and "Diego Bertelli" in d["autores"] and "Claude" in d["autores"],
       "nombre, version, licencia y autores", "%s %s" % (d["nombre"], d["version"]))
    ok([h["nombre"] for h in d["herramientas"]] == ["FFmpeg", "Transcribir (whisper)", "Bajar de YouTube (yt-dlp)"] and all(isinstance(h["hay"], bool) and h["detalle"] for h in d["herramientas"]),
       "dice si estan FFmpeg, whisper y yt-dlp (y por que no, si faltan)", str([(h["nombre"], h["hay"]) for h in d["herramientas"]]))
    ok(d["herramientas"][0]["hay"], "FFmpeg esta (si no, nada de esto andaria)", d["herramientas"][0]["detalle"])
    ok(any("PyAV" in c["nombre"] for c in d["componentes"]) and any("pywebview" in c["nombre"] for c in d["componentes"]) and all(c["licencia"] for c in d["componentes"]), "lista los componentes libres con su licencia")
    ok(os.path.isfile(os.path.join(app.AQUI, "LICENSE")), "el archivo LICENSE esta junto al programa")

    print("=== 2. el dialogo ===")
    ok(js(w, "!document.getElementById('btn-acerca').hidden") and js(w, "!document.getElementById('btn-acerca-inicio').hidden"), "hay un boton «i» en el encabezado y un enlace en la pantalla de inicio")
    w.evaluate_js("document.getElementById('btn-acerca').click()")
    ok(esperar(w, "document.getElementById('dlg-acerca').open"), "el boton «i» abre «Acerca de»")
    e = js(w, "({v: document.getElementById('ac-version').textContent, a: document.getElementById('ac-autores').textContent, l: document.getElementById('ac-licencia').textContent, g: document.getElementById('ac-garantia').textContent, items: [...document.querySelectorAll('#ac-herramientas li')].map(x => [x.className.includes('--si'), x.querySelector('b').textContent]), comp: document.getElementById('ac-componentes').textContent})")
    ok(e["v"].startswith("Versión " + app.VERSION) and "Diego Bertelli" in e["a"] and "GPL" in e["l"] and "SIN NINGUNA GARANTÍA" in e["g"], "muestra la version, quien lo hizo, la licencia y que no tiene garantia", str(e["v"]))
    ok([x[1] for x in e["items"]] == ["FFmpeg", "Transcribir (whisper)", "Bajar de YouTube (yt-dlp)"] and [x[0] for x in e["items"]] == [h["hay"] for h in d["herramientas"]], "y que herramientas hay en esta PC, igual que dice el motor", str(e["items"]))
    ok("PyAV" in e["comp"] and "(BSD)" in e["comp"], "con los componentes que usa", e["comp"][:60])
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'F1', bubbles: true, cancelable: true}))")
    time.sleep(0.5)
    ok(not js(w, "document.getElementById('dlg-acerca').open"), "F1 con el dialogo abierto lo cierra")
    w.evaluate_js("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'F1', bubbles: true, cancelable: true}))")
    ok(esperar(w, "document.getElementById('dlg-acerca').open"), "y F1 lo abre")

    print("=== 3. ver la licencia ===")
    real = getattr(os, "startfile", None)
    os.startfile = lambda ruta: abiertos.append(ruta)
    try:
        w.evaluate_js("document.getElementById('ac-licencia-ver').click()")
        time.sleep(0.8)
    finally:
        if real is not None:
            os.startfile = real
    ok(abiertos == [os.path.join(app.AQUI, "LICENSE")], "«Ver la licencia» abre el archivo LICENSE del programa (y solo ese)", str(abiertos))
    ok(js(w, "document.getElementById('ac-error').hidden"), "(sin error)")
    w.evaluate_js("document.getElementById('ac-cerrar').click()")
    time.sleep(0.4)
    ok(not js(w, "document.getElementById('dlg-acerca').open"), "«Cerrar» cierra")
    w.evaluate_js("document.getElementById('btn-acerca-inicio').click()")
    ok(esperar(w, "document.getElementById('dlg-acerca').open"), "el enlace de la pantalla de inicio tambien lo abre")
    w.evaluate_js("document.getElementById('ac-cerrar').click()")
    time.sleep(0.4)

    print("=== 4. en un celular ===")
    w.resize(390, 844)
    time.sleep(1.0)
    b = js(w, "(() => { const r = document.getElementById('btn-acerca').getBoundingClientRect(); return {l: Math.round(r.left), r: Math.round(r.right), iw: window.innerWidth}; })()")
    ok(b["l"] >= 0 and b["r"] <= b["iw"] + 1, "el boton «i» se ve en un celular", str(b))
    w.evaluate_js("document.getElementById('btn-acerca').click()")
    time.sleep(1.0)
    d2 = js(w, "(() => { const r = document.getElementById('dlg-acerca').getBoundingClientRect(); return {l: Math.round(r.left), r: Math.round(r.right), t: Math.round(r.top), b: Math.round(r.bottom), iw: window.innerWidth, ih: window.innerHeight, abierto: document.getElementById('dlg-acerca').open}; })()")
    ok(d2["abierto"] and d2["l"] >= 0 and d2["r"] <= d2["iw"] + 1 and d2["b"] <= d2["ih"] + 1, "y el dialogo entra entero", str(d2))
    w.evaluate_js("document.getElementById('ac-cerrar').click()")
    w.resize(1400, 900)

    print("=== 5. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    try:
        os.remove(os.path.join(RAIZ, "ultimo-error.log"))
    except OSError:
        pass
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1400, height=900)
        webview.start(correr, (webview.windows[0], api))
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
