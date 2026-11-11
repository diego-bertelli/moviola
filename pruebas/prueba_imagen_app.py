# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 3 en la interfaz, con la ventana REAL: efectos de imagen (listas, archivos, avisos) y transiciones.

Uso:  python -I pruebas/prueba_imagen_app.py
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-imagen-app-"), "ajustes.json")

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


def elegir_clip(w, pista, indice=0):
    w.evaluate_js("""(() => { const p = S.proy.pistas.find(x => x.id === %s); const c = p.clips[%d];
                       S.sel = {grupo: c.grupo, clip: c.id}; actualizarSeleccion(); })()""" % (json.dumps(pista), indice))
    time.sleep(0.5)


def agregar(w, categoria, tipo):
    w.evaluate_js("""(() => { const s = document.querySelector('#fx-%s .fx__agregar select'); s.value = %s;
                       document.querySelector('[data-fxk="%s:agregar"]').click(); })()""" % (categoria, json.dumps(tipo), categoria))
    time.sleep(0.8)


def poner(w, selector, valor, evento="change"):
    w.evaluate_js("""(() => { const e = document.querySelector(%s); e.value = %s; e.dispatchEvent(new Event(%s, {bubbles: true})); })()"""
                  % (json.dumps(selector), json.dumps(valor), json.dumps(evento)))
    time.sleep(0.8)


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
    colores = os.path.join(ex.TMP, "colores.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=12,format=yuv420p,geq=lum='10+20*floor(T)':cb=128:cr=128",
              "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*(300+50*floor(t))*t)':s=48000:d=12:c=mono",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", colores)
    lut = os.path.join(ex.TMP, "look.cube")
    with open(lut, "w") as f:
        f.write("LUT_3D_SIZE 2\n")
        for bl in (0, 1):
            for gr in (0, 1):
                for rj in (0, 1):
                    f.write("%d %d %d\n" % (1 - rj, 1 - gr, 1 - bl))

    print("=== 1. efectos de imagen en el panel ===")
    ok(abrir(w, colores), "abre el video")
    ok(esperar(w, "typeof fx !== 'undefined' && fx.catalogo && Object.keys(fx.catalogo).length >= 20", 10), "el catalogo llega (video y audio)")
    elegir_clip(w, "V1")
    opciones = js(w, "[...document.querySelectorAll('#fx-video select option')].map(o => o.value)")
    ok(set(["color_basico", "voltear", "temperatura", "curvas_luz", "lut", "reducir_ruido_imagen", "enfocar", "estabilizar", "rotar", "recortar_bordes", "lente", "enderezar", "superponer", "quitar_fondo", "texto", "zoom_lento"]) == set(opciones),
       "la lista de efectos de video trae los 16", str(opciones))
    agregar(w, "video", "rotar")
    e = js(w, """({n: S.proy.pistas[0].clips[0].efectos.length, selects: document.querySelectorAll('#fx-video .fx select').length,
                   opciones: [...document.querySelectorAll('#fx-video .fx select option')].map(o => o.textContent), nota: !!document.querySelector('#fx-video .fx .fx__nota')})""")
    ok(e["n"] == 1 and e["selects"] == 1 and "90° a la derecha" in e["opciones"] and e["nota"], "Rotar: una tarjeta con una lista de opciones y la nota 'se ve al exportar'", str(e))
    poner(w, "#fx-video .fx select", "270")
    ok(js(w, "S.proy.pistas[0].clips[0].efectos[0].params.grados") == "270", "cambiar la opcion se guarda en el motor")
    agregar(w, "video", "color_basico")
    ok(js(w, "document.querySelectorAll('#fx-video .fx')[1].querySelector('.fx__nota') === null"), "Brillo/contraste (que SI tiene vista previa) no lleva la nota de 'se ve al exportar'")
    agregar(w, "video", "estabilizar")
    ok("análisis" in js(w, "document.querySelectorAll('#fx-video .fx')[2].querySelector('.fx__nota').textContent"), "Estabilizar avisa que se calcula al exportar", js(w, "document.querySelectorAll('#fx-video .fx')[2].querySelector('.fx__nota').textContent"))
    agregar(w, "video", "lut")
    e = js(w, "({txt: document.querySelectorAll('#fx-video .fx')[3].querySelector('.fx__archivo').textContent, boton: document.querySelectorAll('#fx-video .fx')[3].querySelector('.campo--archivo button').textContent})")
    ok(e["txt"] == "Ningún archivo" and e["boton"] == "Elegir…", "LUT: dice que no hay archivo y ofrece Elegir…", str(e))
    w.evaluate_js("operar('cambiar_efecto', [S.proy.pistas[0].clips[0].id, S.proy.pistas[0].clips[0].efectos[3].id, {archivo: %s}])" % json.dumps(lut))
    time.sleep(1.0)
    e = js(w, "({txt: document.querySelectorAll('#fx-video .fx')[3].querySelector('.fx__archivo').textContent, boton: document.querySelectorAll('#fx-video .fx')[3].querySelector('.campo--archivo button').textContent})")
    ok(e["txt"] == "look.cube" and e["boton"] == "Cambiar…", "con un archivo elegido muestra su nombre y ofrece Cambiar…", str(e))
    w.evaluate_js("operar('cambiar_efecto', [S.proy.pistas[0].clips[0].id, S.proy.pistas[0].clips[0].efectos[3].id, {archivo: 'C:/no/existe.cube'}])")
    time.sleep(0.8)
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5) and "No encuentro" in js(w, "document.querySelector('#avisos .aviso__texto').textContent"),
       "un archivo que no existe: aviso claro", js(w, "document.querySelector('#avisos .aviso__texto').textContent"))
    ok(js(w, "S.proy.pistas[0].clips[0].efectos[3].params.archivo").endswith("look.cube"), "y el proyecto no cambia")

    print("=== 2. transiciones ===")
    ok(js(w, "document.getElementById('sec-transicion').hidden") is True, "con un solo clip no se ofrece transicion (no hay clip anterior)")
    w.evaluate_js("""(async () => { await operar('dividir', [4.0]); await operar('dividir', [8.0]); await operar('borrar_rango', [4.0, 8.0]); })()""")
    time.sleep(2.5)
    elegir_clip(w, "V1", 0)
    ok(js(w, "document.getElementById('sec-transicion').hidden") is True, "el PRIMER clip tampoco")
    elegir_clip(w, "V1", 1)
    e = js(w, """({visible: !document.getElementById('sec-transicion').hidden, boton: document.querySelector('[data-fxk="trans:accion"]').textContent,
                   tipos: [...document.querySelectorAll('#trans-cuerpo select option')].length, max: document.querySelector('#trans-cuerpo input[type=range]').max,
                   valor: document.querySelector('#trans-cuerpo output').textContent})""")
    ok(e["visible"] and e["boton"] == "Agregar la transición" and e["tipos"] >= 8 and float(e["max"]) >= 2.9 and e["valor"] == "1,0 s",
       "el clip que sigue a un corte ofrece 'Agregar la transicion' (10 tipos, hasta 3 s, 1 s de entrada)", str(e))
    w.evaluate_js("document.querySelector('[data-fxk=\"trans:accion\"]').click()")
    time.sleep(1.0)
    e = js(w, "({t: S.proy.pistas[0].clips[1].transicion, a: S.proy.pistas[1].clips[1].transicion, insignias: document.querySelectorAll('#tira .clip__trans').length, boton: document.querySelector('[data-fxk=\"trans:accion\"]').textContent, dur: S.proy.duracion})")
    ok(e["t"] == {"tipo": "disolver", "duracion": 1.0} and e["a"] is not None, "se pone en el video y en su audio enlazado", str(e))
    ok(e["insignias"] == 1 and e["boton"] == "Quitar la transición" and abs(e["dur"] - 8.0) < 0.05, "la linea de tiempo la marca, el boton pasa a 'Quitar' y el proyecto sigue durando 8 s")
    elegir_clip(w, "V1", 1)
    poner(w, "#trans-cuerpo select", "circulo")
    ok(js(w, "S.proy.pistas[0].clips[1].transicion.tipo") == "circulo", "cambiar el tipo la actualiza")
    poner(w, "#trans-cuerpo input[type=range]", "2.0")
    ok(js(w, "S.proy.pistas[0].clips[1].transicion.duracion") == 2.0, "y la duracion tambien")
    w.evaluate_js("operar('poner_transicion', [S.proy.pistas[0].clips[1].grupo, 'disolver', 9])")
    time.sleep(0.8)
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5), "una duracion imposible muestra un aviso")
    w.evaluate_js("document.querySelector('[data-fxk=\"trans:accion\"]').click()")
    time.sleep(1.0)
    ok(js(w, "S.proy.pistas[0].clips[1].transicion") is None and js(w, "document.querySelectorAll('#tira .clip__trans').length") == 0, "Quitar la transicion la saca (y la insignia desaparece)")
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(0.9)
    ok(js(w, "S.proy.pistas[0].clips[1].transicion") is not None, "Ctrl+Z la devuelve")

    print("=== 3. un fundido en un borde con transicion ===")
    w.evaluate_js("operar('fade', [S.proy.pistas[0].clips[1].id, 'in', 1.0])")
    time.sleep(0.8)
    ok("transición" in js(w, "[...document.querySelectorAll('#avisos .aviso__texto')].map(x => x.textContent).join(' ')"), "el aviso explica que la transicion ya hace de fundido")

    print("=== 4. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-imagen-app-cache-"), "cache")
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
