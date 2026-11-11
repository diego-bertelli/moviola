# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""«Crear un proyecto» desde la pantalla de inicio, con la ventana REAL: se eligen varios videos, quedan uno detras de otro en la linea de
tiempo (con su audio) y se ofrece guardar el proyecto. Los cuadros del sistema se reemplazan por respuestas fijas.

Uso:  python -I pruebas/prueba_crear_proyecto_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-crear-proyecto-")
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


def correr(w, api, rutas, destino):
    try:
        _correr(w, api, rutas, destino)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w, api, rutas, destino):
    time.sleep(3)
    print("=== 1. el boton ===")
    e = js(w, "({hay: !!document.getElementById('btn-crear-proyecto'), visible: !document.getElementById('btn-crear-proyecto').hidden, texto: document.getElementById('btn-crear-proyecto').textContent, orden: [...document.querySelectorAll('.bienvenida__botones button')].map(b => b.textContent)})")
    ok(e["hay"] and e["visible"] and e["texto"] == "Crear un proyecto", "la pantalla de inicio tiene «Crear un proyecto»", str(e["orden"]))
    ok(e["orden"] == ["Crear un proyecto", "Abrir un proyecto", "Editar un video", "Procesar varios", "Bajar de YouTube"], "tres columnas: Proyectos (crear, abrir), Editar (video, varios) y YouTube", str(e["orden"]))
    cols = js(w, "[...document.querySelectorAll('.bienvenida__columna')].map(c => [c.querySelector('.bienvenida__rotulo').textContent, Math.round(c.getBoundingClientRect().left), [...c.querySelectorAll('button')].length])")
    ok([c[0] for c in cols] == ["Proyectos", "Editar", "YouTube"] and cols[0][1] < cols[1][1] < cols[2][1] and [c[2] for c in cols] == [2, 2, 1], "con su titulo y una al lado de la otra (de izquierda a derecha)", str(cols))

    print("=== 2. crear el proyecto con 3 videos ===")
    w.evaluate_js("document.getElementById('btn-crear-proyecto').click()")
    ok(esperar(w, "S.proy && Object.keys(S.proy.fuentes).length === 3 && S.proy.pistas[0].clips.length === 3", 60), "se arma el proyecto: 3 archivos y 3 clips en V1")
    e = js(w, "({v1: S.proy.pistas.find(p => p.id === 'V1').clips.map(c => [S.proy.fuentes[c.fuente].nombre, c.inicio, c.hasta - c.desde]), a1: S.proy.pistas.find(p => p.id === 'A1').clips.length, dur: S.proy.duracion})")
    ok([x[0] for x in e["v1"]] == ["a.mp4", "b.mp4", "c.mp4"] and [x[1] for x in e["v1"]] == [0, 2, 4], "uno detras de otro, en el orden elegido (0 s, 2 s, 4 s)", str(e["v1"]))
    ok(e["a1"] == 3 and abs(e["dur"] - 6.0) < 0.01, "cada uno con su audio, y el proyecto dura 6 s", str(e))
    ok(esperar(w, "S.proy.archivo_proyecto === 'mi-proyecto.moviola' && S.proy.sin_guardar === false", 15), "al final ofrece guardarlo y queda guardado")
    ok(os.path.isfile(destino), "el archivo .moviola existe", destino)
    ok("mi-proyecto" in js(w, "document.getElementById('marca-proyecto').textContent"), "y la barra muestra su nombre", js(w, "document.getElementById('marca-proyecto').textContent"))

    print("=== 3. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    try:
        os.remove(os.path.join(RAIZ, "ultimo-error.log"))
    except OSError:
        pass
    rutas = []
    for nombre, dur in (("a.mp4", 2), ("b.mp4", 2), ("c.mp4", 2)):
        rutas.append(ex.crear_fuente(os.path.join(ex.TMP, nombre), dur=dur))
    destino = os.path.join(TMP, "mi-proyecto.moviola")
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    api.elegir_videos = lambda: {"rutas": rutas}
    api.guardar_proyecto_como = lambda: api._guardar_en(destino)
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1400, height=900)
        webview.start(correr, (webview.windows[0], api, rutas, destino))
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
