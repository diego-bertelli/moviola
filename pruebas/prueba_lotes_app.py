# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Presets y lotes en la interfaz, con la ventana REAL: el dialogo «Reel en un clic», procesar el proyecto abierto sin tocarlo, varios archivos,
cancelar, y que lo que sale se pueda medir.

Uso:  python -I pruebas/prueba_lotes_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-lotes-app-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
import prueba_lotes as pl  # noqa: E402

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


def correr(w, api, fuentes):
    try:
        _correr(w, api, fuentes)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w, api, fuentes):
    time.sleep(3)
    silencios, corto, largo = fuentes
    salida = os.path.join(TMP, "salida")
    os.makedirs(salida, exist_ok=True)

    print("=== 1. la API (sin ventana) ===")
    c = api.presets_catalogo()
    ok(len(c["presets"]) == 5 and c["hay_proyecto"] is False and c["carpeta"] == "" and c["maximo"] == 500 and c["idiomas"], "el catalogo trae los presets, los idiomas y dice que no hay proyecto")
    for opciones, esperado in (({"preset": "no_existe"}, "no existe"), ({"preset": "reel", "cambios": 5}, "no son válidas"), ({"preset": "reel", "origenes": [1, 2]}, "no son válidas"),
                               ({"preset": "reel", "origenes": []}, "no son válidas"), ({"preset": "reel"}, "nada abierto"),
                               ({"preset": "reel", "origenes": [corto], "carpeta": os.path.join(TMP, "no_existe_carpeta")}, "no existe"),
                               ({"preset": "reel", "origenes": [os.path.join(TMP, "no_hay.mp4")]}, "No encontré"), ({"preset": "reel", "cambios": {"formato": "x"}, "origenes": [corto]}, "formato")):
        r = api.lote_iniciar(opciones)
        ok(r.get("error") and esperado in r["error"], "lote_iniciar(%s) -> error claro" % json.dumps(opciones)[:70], r.get("error", "")[:80])
    ok(api.lote_estado()["estado"] == "ninguno" and api.lote_cancelar() == {"ok": True}, "sin nada en marcha: estado «ninguno» y cancelar no rompe")

    print("=== 2. el dialogo desde la pantalla de inicio ===")
    ok(js(w, "!document.getElementById('btn-lote').hidden") and js(w, "document.getElementById('btn-presets').disabled"), "«Procesar varios» esta en la pantalla de inicio; el boton del riel (proyecto) esta apagado")
    clic(w, "btn-lote")
    ok(esperar(w, "document.getElementById('dlg-presets').open", 5), "se abre el dialogo")
    e = js(w, """({tarjetas: [...document.querySelectorAll('.pre__tarjeta')].map(b => b.dataset.clave), activa: document.querySelector('.pre__tarjeta--activa')?.dataset.clave,
                   origen: [...document.querySelectorAll('[data-origen]')].map(b => [b.dataset.origen, b.disabled, b.getAttribute('aria-checked')]),
                   empezar: document.getElementById('pre-empezar').disabled, archivos: !document.getElementById('pre-archivos').hidden,
                   carpeta: document.getElementById('pre-carpeta').textContent, pasos: document.getElementById('pre-pasos').textContent})""")
    ok(e["tarjetas"] == ["reel", "youtube", "podcast", "whatsapp", "clase"] and e["activa"] == "reel", "5 tarjetas, «reel» elegida", str(e["tarjetas"]))
    ok(e["origen"] == [["proyecto", True, "false"], ["archivos", False, "true"]] and e["archivos"] and e["empezar"], "sin proyecto: solo «Varios archivos», y «Empezar» apagado hasta elegir archivos", str(e["origen"]))
    ok("moviola-salida" in e["carpeta"] and "corta silencios" in e["pasos"], "dice donde se guarda y lo que hace la receta", e["pasos"])
    w.evaluate_js("document.querySelector('.pre__tarjeta[data-clave=\"clase\"]').click()")
    time.sleep(0.3)
    e = js(w, "({sil: document.getElementById('pre-silencios').checked, sub: document.getElementById('pre-subtitulos').checked, norm: document.getElementById('pre-normalizar').checked, kar: document.getElementById('pre-karaoke-campo').hidden})")
    ok(e["sil"] and e["norm"] and (e["sub"] or True), "al elegir «Clase» se marcan sus ajustes (silencios, volumen)", str(e))
    w.evaluate_js("document.querySelector('.pre__tarjeta[data-clave=\"podcast\"]').click()")
    time.sleep(0.3)
    e = js(w, "({sub: document.getElementById('pre-subtitulos').checked, idioma: document.getElementById('pre-idioma-campo').hidden})")
    ok(not e["sub"] and e["idioma"], "«Podcast» no subtitula: se esconden idioma y karaoke")

    print("=== 3. varios archivos ===")
    w.evaluate_js("pst.rutas = %s; pintarArchivos(); pintarEleccion();" % json.dumps([silencios, corto]))
    time.sleep(0.3)
    e = js(w, "({n: document.getElementById('pre-archivos-n').textContent, empezar: document.getElementById('pre-empezar').textContent, dis: document.getElementById('pre-empezar').disabled, lista: [...document.querySelectorAll('#pre-archivos-lista li')].map(l => l.textContent)})")
    ok(e["n"] == "2 archivos elegidos" and e["empezar"] == "Procesar 2 archivos" and not e["dis"] and e["lista"] == ["silencios.mp4", "corto.mp4"], "dice cuantos hay, los nombra y «Procesar 2 archivos» se enciende", str(e))
    w.evaluate_js("pst.carpetaElegida = %s; pintarEleccion();" % json.dumps(salida))
    clic(w, "pre-empezar")
    ok(esperar(w, "!document.getElementById('pre-progreso').hidden || !document.getElementById('pre-resultado').hidden", 10), "al empezar se ve el avance")
    ok(esperar(w, "!document.getElementById('pre-resultado').hidden", 90), "termina")
    e = js(w, "({titulo: document.getElementById('pre-resultado-titulo').textContent, filas: [...document.querySelectorAll('#pre-resultado-lista li')].map(l => l.textContent)})")
    ok(e["titulo"] == "Listo: 2 archivos guardados." and len(e["filas"]) == 2 and e["filas"][0].startswith("silencios-v1.mp3"), "lista los dos archivos con lo que se hizo", str(e))
    mp3 = os.path.join(salida, "silencios-v1.mp3")
    _, au, dur = ex.sondear(mp3)
    ok(os.path.isfile(mp3) and au is not None and abs(dur - 7.2) < 0.4, "el MP3 del primero existe y tiene los silencios cortados (7,2 s)", "%.2f s" % dur)
    clic(w, "pre-otra")
    ok(not js(w, "document.getElementById('pre-armar').hidden"), "«Otra vez» vuelve al formulario")
    clic(w, "pre-cerrar")
    ok(not js(w, "document.getElementById('dlg-presets').open"), "«Cerrar» cierra")

    print("=== 4. el proyecto abierto: se procesa una copia y no cambia nada ===")
    w.evaluate_js("pedirAbrir(%s)" % json.dumps(silencios))
    ok(esperar(w, "S.proy && S.ruta && document.getElementById('cargando').hidden", 30), "se abre el video")
    w.evaluate_js("irA(150)")
    time.sleep(0.5)
    clic(w, "btn-dividir")           # un cambio sin guardar, para ver que el preset no lo toca ni lo guarda
    esperar(w, "S.proy.pistas[0].clips.length === 2", 5)
    antes = js(w, "({clips: S.proy.pistas[0].clips.length, dur: S.proy.duracion, sin: S.proy.sin_guardar, rehacer: S.proy.puede_rehacer})")
    ok(not js(w, "document.getElementById('btn-presets').disabled"), "con un proyecto, el boton «Con un preset…» del riel se enciende")
    clic(w, "btn-presets")
    ok(esperar(w, "document.getElementById('dlg-presets').open", 5), "se abre")
    e = js(w, "({origen: document.querySelector('[data-origen=\"proyecto\"]').getAttribute('aria-checked'), carpeta: document.getElementById('pre-carpeta').textContent, dis: document.querySelector('[data-origen=\"proyecto\"]').disabled})")
    ok(e["origen"] == "true" and not e["dis"] and e["carpeta"].endswith("moviola-salida"), "queda elegido «Este proyecto» y la carpeta es «moviola-salida» al lado del video", str(e))
    w.evaluate_js("document.querySelector('.pre__tarjeta[data-clave=\"whatsapp\"]').click(); document.getElementById('pre-silencios').checked = true;")
    w.evaluate_js("pst.carpetaElegida = %s; pintarEleccion();" % json.dumps(salida))
    clic(w, "pre-empezar")
    ok(esperar(w, "!document.getElementById('pre-resultado').hidden", 90), "termina")
    e = js(w, "({titulo: document.getElementById('pre-resultado-titulo').textContent, fila: document.querySelector('#pre-resultado-lista li').textContent})")
    ok(e["titulo"] == "Listo: ya está guardado." and "de silencios" in e["fila"], "dice cuanto silencio saco", e["fila"])
    arch = [f for f in os.listdir(salida) if f.startswith("silencios-v") and f.endswith(".mp4")]
    ok(len(arch) == 1, "dejo un video", str(arch))
    if arch:
        v, au, dur = ex.sondear(os.path.join(salida, arch[0]))
        ok(abs(dur - 6.4) < 0.45 and pl.lufs(os.path.join(salida, arch[0])) is not None, "con los silencios cortados (~6,5 s) y sonido", "%.2f s" % dur)
    despues = js(w, "({clips: S.proy.pistas[0].clips.length, dur: S.proy.duracion, sin: S.proy.sin_guardar, rehacer: S.proy.puede_rehacer})")
    ok(despues == antes, "el proyecto abierto quedo EXACTAMENTE igual (mismos clips, duracion, sin tocar el historial)", "%s -> %s" % (antes, despues))
    clic(w, "pre-listo")

    print("=== 5. cancelar y convivir con exportar ===")
    clic(w, "btn-presets")
    esperar(w, "document.getElementById('dlg-presets').open", 5)
    w.evaluate_js("pst.origen = 'archivos'; pst.rutas = %s; pintarArchivos(); pintarEleccion(); document.querySelector('.pre__tarjeta[data-clave=\"whatsapp\"]').click(); document.getElementById('pre-silencios').checked = true; pst.carpetaElegida = %s; pintarEleccion();" % (json.dumps([largo]), json.dumps(os.path.join(TMP, "salida2"))))
    os.makedirs(os.path.join(TMP, "salida2"), exist_ok=True)
    clic(w, "pre-empezar")
    ok(esperar(w, "!document.getElementById('pre-progreso').hidden && !document.getElementById('pre-cancelar').disabled", 10), "mientras procesa se ve el avance y «Cancelar»")
    r = api.exportar_iniciar({"formato": "original", "carpeta": salida, "nombre": "x"})
    ok(r.get("error") and "preset" in r["error"], "exportar a mano mientras corre un preset: se rechaza con un mensaje claro", r.get("error", ""))
    time.sleep(1.0)
    clic(w, "pre-cancelar")
    ok(esperar(w, "!document.getElementById('pre-armar').hidden && document.getElementById('pre-error').textContent.includes('Cancelado')", 30), "«Cancelar» vuelve al formulario y lo dice")
    ok(not [f for f in os.listdir(os.path.join(TMP, "salida2")) if f.endswith(".mp4")], "sin archivos a medias")
    clic(w, "pre-cerrar")
    ok(api.lote_estado()["estado"] in ("cancelado", "listo"), "el motor quedo libre")

    print("=== 6. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    for f in ("ultimo-error.log",):
        try:
            os.remove(os.path.join(RAIZ, f))
        except OSError:
            pass
    silencios = pl.fuente_con_silencios(os.path.join(ex.TMP, "silencios.mp4"))
    corto = ex.crear_fuente(os.path.join(ex.TMP, "corto.mp4"), dur=3)
    largo = pl.fuente_con_silencios(os.path.join(ex.TMP, "largo.mp4"), dur=60)
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1280, height=900)
        webview.start(correr, (webview.windows[0], api, (silencios, corto, largo)))
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
