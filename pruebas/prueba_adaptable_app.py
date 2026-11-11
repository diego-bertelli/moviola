# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""La interfaz se adapta a distintas resoluciones y proporciones, con la ventana REAL redimensionada (de 390 x 844, un celular, a 2560 x 1080,
un monitor ultra ancho): nada se pasa del ancho de la ventana (la pagina no se desplaza hacia los costados), los botones principales se ven
completos, y en las pantallas normales el visor y la linea de tiempo tienen lugar de verdad. Tambien la cuenta que decide el tamano con que se
abre la ventana segun la pantalla (app._tamano_ventana).

Uso:  python -I pruebas/prueba_adaptable_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-adaptable-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []

# (ancho, alto, nombre, modo): modo 'columnas' = herramientas | visor | propiedades; 'apilado' = una sola columna que se desplaza
TAMANOS = [
    (1920, 1080, "Full HD", "columnas"), (2560, 1080, "ultra ancho 21:9", "columnas"), (1360, 768, "el TV de 1360x768", "columnas"),
    (1280, 720, "HD", "columnas"), (1024, 600, "netbook 1024x600", "columnas"), (900, 700, "ventana chica", "columnas"),
    (768, 1024, "tablet vertical", "apilado"), (390, 844, "celular vertical", "apilado"), (844, 390, "celular apaisado", "apilado"),
    (1366, 500, "ancha pero baja", "columnas"),
]


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


MEDIR = """(() => {
  const r = (id) => { const n = document.getElementById(id); if (!n) return null; const b = n.getBoundingClientRect(); return {l: Math.round(b.left), r: Math.round(b.right), t: Math.round(b.top), b: Math.round(b.bottom), w: Math.round(b.width), h: Math.round(b.height)}; };
  return {iw: window.innerWidth, ih: window.innerHeight, sw: document.documentElement.scrollWidth, bsw: document.body.scrollWidth,
          barra: r('barra'), exportar: r('btn-exportar'), visor: r('visor'), escena: r('escena'), tiempo: r('zona-tiempo'), carriles: r('carriles'), props: r('props'), edicion: r('edicion'), play: r('btn-play'), transporte: r('transporte')};
})()"""


def correr(w, src):
    try:
        _correr(w, src)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w, src):
    time.sleep(3)

    print("=== 1. la pantalla de inicio en todos los tamanos ===")
    for an, al, nombre, modo in TAMANOS:
        w.resize(an, al)
        time.sleep(0.9)
        m = js(w, MEDIR)
        boton = js(w, "(() => { const b = document.getElementById('btn-crear-proyecto').getBoundingClientRect(); return [Math.round(b.left), Math.round(b.right)]; })()")
        ok(m["sw"] <= m["iw"] + 1 and boton[0] >= 0 and boton[1] <= m["iw"] + 1, "inicio %dx%d (%s): sin desbordar y con los botones a la vista" % (an, al, nombre), "pagina %s de %s px" % (m["sw"], m["iw"]))

    print("=== 2. con un video abierto ===")
    w.resize(1400, 900)
    time.sleep(0.8)
    w.evaluate_js("abrir(%s)" % json.dumps(src))
    ok(esperar(w, "S.proy && S.ruta && document.getElementById('cargando').hidden", 30), "se abre el video")
    time.sleep(1.0)
    for an, al, nombre, modo in TAMANOS:
        w.resize(an, al)
        time.sleep(1.1)
        m = js(w, MEDIR)
        etiqueta = "%dx%d (%s)" % (an, al, nombre)
        ok(m["sw"] <= m["iw"] + 1 and m["bsw"] <= m["iw"] + 1, etiqueta + ": la pagina no se desplaza hacia los costados", "pagina %s de %s px" % (m["sw"], m["iw"]))
        ok(m["exportar"]["r"] <= m["iw"] + 1 and m["exportar"]["l"] >= 0, etiqueta + ": «Exportar» se ve entero", str(m["exportar"]))
        ok(m["carriles"]["r"] <= m["iw"] + 1 and m["carriles"]["l"] >= 0 and m["carriles"]["w"] > m["iw"] * 0.55, etiqueta + ": la linea de tiempo entra a lo ancho y es util", "%s de %s" % (m["carriles"]["w"], m["iw"]))
        ok(m["play"]["r"] <= m["iw"] + 1 and m["play"]["l"] >= 0, etiqueta + ": el boton de reproducir se ve")
        if modo == "columnas":
            ok(m["props"]["r"] <= m["iw"] + 1 and m["edicion"]["l"] >= 0, etiqueta + ": las herramientas y las propiedades entran en la ventana", "props hasta %s, ventana %s" % (m["props"]["r"], m["iw"]))
            ok(m["visor"]["h"] >= 90 and m["visor"]["w"] >= 160, etiqueta + ": el visor tiene lugar de verdad", "%sx%s" % (m["visor"]["w"], m["visor"]["h"]))
            ok(m["tiempo"]["b"] <= m["ih"] + 1, etiqueta + ": la linea de tiempo entra en la altura (no hay que desplazarse)", "hasta %s de %s" % (m["tiempo"]["b"], m["ih"]))
        else:
            ok(m["visor"]["h"] >= 120 and m["escena"]["w"] >= m["iw"] - 50, etiqueta + ": apilado: el visor ocupa el ancho y tiene altura", "%sx%s" % (m["escena"]["w"], m["visor"]["h"]))
            ok(m["props"]["l"] >= 0 and m["props"]["r"] <= m["iw"] + 1, etiqueta + ": las propiedades van abajo, a todo el ancho")
            ok(m["props"]["t"] > m["carriles"]["t"] and m["edicion"]["t"] > m["carriles"]["t"], etiqueta + ": en este orden: visor, linea de tiempo, herramientas, propiedades")
    w.resize(1400, 900)
    time.sleep(0.8)

    print("=== 3. un dialogo en un celular ===")
    w.resize(390, 844)
    time.sleep(0.9)
    w.evaluate_js("document.getElementById('btn-exportar').click()")
    time.sleep(1.0)
    d = js(w, "(() => { const b = document.getElementById('dlg-exportar').getBoundingClientRect(); return {abierto: document.getElementById('dlg-exportar').open, l: Math.round(b.left), r: Math.round(b.right), t: Math.round(b.top), b: Math.round(b.bottom), iw: window.innerWidth, ih: window.innerHeight}; })()")
    ok(d["abierto"] and d["l"] >= 0 and d["r"] <= d["iw"] + 1 and d["b"] <= d["ih"] + 1, "el dialogo Exportar entra entero en un celular", str(d))
    w.evaluate_js("document.getElementById('exp-cancelar-armar').click()")
    time.sleep(0.5)
    w.resize(1400, 900)

    print("=== 4. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


class P:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.width, self.height = x, y, w, h


def tamano_de_ventana():
    print("=== 0. el tamano con que se abre la ventana, segun la pantalla ===")
    tv = [P(-1280, 0, 1280, 1024), P(0, 0, 1360, 768)]          # el equipo de Diego: un monitor a la izquierda y el TV de 1360x768 de principal
    a, h = app._tamano_ventana(None, pantallas=tv)
    ok(a <= 1360 * 0.94 + 1 and h <= 768 - 80, "TV 1360x768 (con otro monitor a la izquierda): cabe en la pantalla principal", "%dx%d" % (a, h))
    ok(app._tamano_ventana(None, pantallas=[P(0, 0, 1920, 1080)]) == (1280, 860), "en Full HD sigue siendo 1280x860")
    ok(app._tamano_ventana(None, pantallas=[P(0, 0, 1366, 768)])[1] <= 678, "portatil 1366x768: no pasa de 678 de alto")
    a, h = app._tamano_ventana(None, pantallas=[P(0, 0, 1024, 600)])
    ok(a <= 1024 and h <= 600 - 80, "pantalla de 1024x600: cabe", "%dx%d" % (a, h))
    ok(app._tamano_ventana(None, pantallas=[]) == (1280, 860), "sin datos de la pantalla: el de siempre")

    class Rota:
        @property
        def screens(self):
            raise RuntimeError("sin pantallas")
    ok(app._tamano_ventana(Rota()) == (1280, 860), "si pywebview falla al medir: el de siempre (no rompe el arranque)")


def main():
    try:
        os.remove(os.path.join(RAIZ, "ultimo-error.log"))
    except OSError:
        pass
    tamano_de_ventana()
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=6)
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1400, height=900)
        webview.start(correr, (webview.windows[0], src))
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
