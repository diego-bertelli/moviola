# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Proyectos en la interfaz, con la ventana REAL: guardar, abrir, pantalla de inicio con recientes, recuperacion y el aviso de
cambios sin guardar.

Uso:  python -I pruebas/prueba_proyectos_app.py

Los cuadros de elegir archivo del sistema no se pueden manejar: se prueban con los metodos del motor y con la interfaz abriendo por ruta.
"""

import json
import os
import shutil
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")
CARPETA_AJUSTES = tempfile.mkdtemp(prefix="prueba-proyectos-app-")
os.environ["EDITOR_AJUSTES"] = os.path.join(CARPETA_AJUSTES, "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []
api_ref = {}


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


def clic(w, id_):
    w.evaluate_js("document.getElementById(%s).click()" % json.dumps(id_))
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
    api = api_ref["api"]
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=6)
    carpeta = tempfile.mkdtemp(prefix="prueba-proyectos-ui-")

    print("=== 1. pantalla de inicio ===")
    e = js(w, """({editar: document.getElementById('btn-abrir').textContent, proyecto: document.getElementById('btn-abrir-proyecto').textContent,
                   recientes: document.getElementById('recientes').hidden, recuperar: document.getElementById('recuperar').hidden,
                   guardar: document.getElementById('btn-guardar').hidden, marca: document.getElementById('marca-proyecto').hidden})""")
    ok(e["editar"] == "Editar un video" and e["proyecto"] == "Abrir un proyecto", "dos caminos: «Editar un video» y «Abrir un proyecto»", str(e))
    ok(e["recientes"] and e["recuperar"] and e["guardar"] and e["marca"], "sin historial: sin recientes, sin recuperacion y sin botones de guardar")

    print("=== 2. guardar ===")
    ok(abrir(w, src), "abre un video")
    e = js(w, "({guardar: !document.getElementById('btn-guardar').hidden, como: !document.getElementById('btn-guardar-como').hidden, marca: document.getElementById('marca-proyecto').textContent})")
    ok(e["guardar"] and e["como"] and e["marca"] == "Proyecto sin guardar", "aparecen Guardar y Guardar como, y la marca dice «Proyecto sin guardar»", str(e))
    w.evaluate_js("operar('dividir', [3.0])")
    time.sleep(0.9)
    ok(js(w, "S.proy.sin_guardar") is True and "•" in js(w, "document.getElementById('btn-guardar').textContent"), "al editar, el boton Guardar muestra un punto")
    ruta_p = os.path.join(carpeta, "uno.moviola")
    api._guardar_en(ruta_p)                         # el cuadro de guardar del sistema no se maneja: se guarda por el motor
    w.evaluate_js("llamar('proyecto_estado').then(r => aplicarProyecto(r.proyecto))")
    time.sleep(0.9)
    e = js(w, "({marca: document.getElementById('marca-proyecto').textContent, sin: S.proy.sin_guardar, btn: document.getElementById('btn-guardar').textContent})")
    ok(e["marca"] == "uno.moviola" and e["sin"] is False and e["btn"] == "Guardar", "tras guardar, la marca dice el nombre y el boton vuelve a la normalidad", str(e))
    clic(w, "btn-guardar")
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5) and "uno.moviola" in js(w, "document.querySelector('#avisos .aviso__texto').textContent"), "«Guardar» vuelve a escribir y avisa «Proyecto guardado: uno.moviola»")
    w.evaluate_js("operar('dividir', [1.0])")
    time.sleep(0.9)
    ok("•" in js(w, "document.getElementById('marca-proyecto').textContent") and js(w, "document.getElementById('marca-proyecto').classList.contains('marca-proyecto--sin')"), "otro cambio: la marca muestra el punto y se resalta")
    w.evaluate_js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'KeyS', ctrlKey: true, bubbles: true, cancelable: true}))")
    ok(esperar(w, "S.proy.sin_guardar === false", 10), "Ctrl+S guarda")
    ok(json.load(open(ruta_p, encoding="utf-8"))["pistas"][0]["clips"].__len__() == 3, "y el archivo tiene los 3 clips (2 cortes)")

    print("=== 3. cambios sin guardar: el aviso ===")
    w.evaluate_js("operar('dividir', [5.0])")
    time.sleep(0.9)
    clic(w, "btn-abrir-barra")
    ok(esperar(w, "document.getElementById('dlg-confirmar').open", 5), "con cambios sin guardar, «Abrir…» pregunta antes")
    clic(w, "conf-cancelar")
    ok(not js(w, "document.getElementById('dlg-confirmar').open") and js(w, "S.proy.sin_guardar") is True and js(w, "S.ruta") == src, "«Volver» no hace nada: sigue todo como estaba")
    # el cuadro de elegir archivo del sistema no se puede manejar: se reemplaza por uno de mentira que dice «cancelar»
    w.evaluate_js("(() => { const orig = window.llamar; window.llamar = async (m, a) => (m === 'elegir_proyecto' ? { cancelado: true } : orig(m, a)); })()")
    clic(w, "btn-abrir-proyecto")
    ok(esperar(w, "document.getElementById('dlg-confirmar').open", 5), "«Abrir un proyecto» tambien pregunta")
    clic(w, "conf-guardar")
    ok(esperar(w, "!document.getElementById('dlg-confirmar').open", 10) and js(w, "S.proy.sin_guardar") is False, "«Guardar y seguir» guarda y cierra el aviso")
    # (el cuadro del sistema de elegir proyecto queda abierto: se lo cierra desde el motor no se puede; se sigue por ruta)
    w.evaluate_js("operar('dividir', [4.0])")
    time.sleep(0.9)
    w.evaluate_js("pedirAbrir(%s)" % json.dumps(ruta_p))
    ok(esperar(w, "document.getElementById('dlg-confirmar').open", 5), "pedirAbrir (recientes, arrastrar) tambien pregunta")
    clic(w, "conf-descartar")
    ok(esperar(w, "S.proy && S.proy.archivo_proyecto === 'uno.moviola' && document.getElementById('cargando').hidden", 30), "«Seguir sin guardar» descarta lo nuevo y abre el proyecto")
    ok(js(w, "S.proy.pistas[0].clips.length") == 4 or js(w, "S.proy.pistas[0].clips.length") == 4, "(con lo que estaba guardado: 4 clips, con el corte de 5 s del «Guardar y seguir»)")
    ok(js(w, "S.proy.sin_guardar") is False and js(w, "document.getElementById('marca-proyecto').textContent") == "uno.moviola", "queda al dia y con su nombre")
    ok(not js(w, "document.getElementById('dlg-confirmar').open"), "sin cambios, abrir no pregunta nada")

    print("=== 4. abrir un proyecto por ruta (arrastrar, recientes) ===")
    w.evaluate_js("pedirAbrir(%s)" % json.dumps(src))
    ok(esperar(w, "S.ruta === %s && !document.getElementById('dlg-confirmar').open && document.getElementById('cargando').hidden" % json.dumps(src), 30), "sin cambios, un video se abre directo")
    ok(js(w, "S.proy.archivo_proyecto") == "", "y un video recien abierto no es un proyecto guardado")
    w.evaluate_js("pedirAbrir(%s)" % json.dumps(ruta_p))
    ok(esperar(w, "S.proy && S.proy.archivo_proyecto === 'uno.moviola'", 30), "un .moviola se abre como proyecto (la misma funcion de siempre reconoce la extension)")
    ok(js(w, "S.proy.pistas[0].clips.length") == 4 and js(w, "document.getElementById('nombre-archivo').textContent") == "src.mp4", "con sus cortes y el video principal en la cabecera")

    print("=== 5. recuperar el trabajo sin guardar ===")
    w.evaluate_js("operar('dividir', [2.0])")
    time.sleep(3.2)                                  # la copia de recuperacion se escribe 1,5 s despues del ultimo cambio
    recup = os.path.join(CARPETA_AJUSTES, "recuperacion.moviola")
    ok(os.path.isfile(recup), "tras editar se escribe sola una copia de recuperacion", recup)
    n_clips = js(w, "S.proy.pistas[0].clips.length")
    clic(w, "btn-guardar")
    time.sleep(1.2)
    ok(not os.path.isfile(recup), "al guardar, la copia de recuperacion se borra")
    w.evaluate_js("operar('dividir', [1.5])")
    time.sleep(3.2)
    ok(os.path.isfile(recup), "otro cambio sin guardar: vuelve a escribirse")
    n_sin = js(w, "S.proy.pistas[0].clips.length")
    # "se cierra la ventana sin guardar": otra sesion del motor ve la copia
    api2 = app.API()
    api2.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-proyectos-cache-"), "cache")
    app.crear_servidor(api2)
    r = api2.recientes()
    ok(r["recuperacion"] and r["recuperacion"]["nombre"] == "src.mp4", "al arrancar de nuevo, el motor ofrece recuperar el trabajo", str(r["recuperacion"]))
    d = api2.abrir_recuperacion()
    ok(not d.get("error") and d["proyecto"]["sin_guardar"] is True and d["proyecto"]["archivo_proyecto"] == "" and len(api2.proyecto.pista("V1")["clips"]) == n_sin,
       "recuperar abre exactamente lo ultimo, como proyecto sin nombre y sin guardar", str(d.get("error")))
    api2.cerrar()
    ok(os.path.isfile(recup), "cerrar el programa con cambios sin guardar deja la copia para la proxima vez")
    api2b = app.API()
    app.crear_servidor(api2b)
    api2b.descartar_recuperacion()
    ok(not os.path.isfile(recup) and api2b.recientes()["recuperacion"] is None, "descartar la borra")
    api2b.cerrar()
    os.makedirs(os.path.join(carpeta, "mov"), exist_ok=True)

    print("=== 6. recientes en la pantalla de inicio ===")
    r = api.recientes()
    ok([x["nombre"] for x in r["recientes"]][:2] == ["uno.moviola", "src.mp4"] or "uno.moviola" in [x["nombre"] for x in r["recientes"]], "el motor tiene los recientes", str([x["nombre"] for x in r["recientes"]]))
    w.evaluate_js("cargarRecientes()")
    time.sleep(1.0)
    e = js(w, "({visible: !document.getElementById('recientes').hidden, items: [...document.querySelectorAll('#recientes-lista .reciente__nombre')].map(x => x.textContent)})")
    ok(e["visible"] and any("uno.moviola" in x for x in e["items"]) and any(x.startswith("Proyecto") for x in e["items"]) and any(x.startswith("Video") for x in e["items"]), "la pantalla de inicio los lista con su tipo", str(e))
    w.evaluate_js("document.querySelector('#recientes-lista .reciente__olvidar').click()")
    time.sleep(1.0)
    ok(js(w, "document.querySelectorAll('#recientes-lista .reciente').length") == len(e["items"]) - 1, "la ✕ saca uno de la lista (sin borrar el archivo)")

    print("=== 7. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api_ref["api"] = api
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-proyectos-app-cache-"), "cache")
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
