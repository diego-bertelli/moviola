# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Los efectos de composicion (logo, quitar fondo, texto, zoom lento) en la interfaz, con la ventana REAL.

Uso:  python -I pruebas/prueba_composicion_app.py

Se maneja el panel como una persona; el selector de archivos del sistema se reemplaza por uno de mentira (no se puede
manejar un cuadro nativo) y lo guardado se EXPORTA y se mide.
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-composicion-app-"), "ajustes.json")

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


def cuadros_de(ruta):
    import av
    cont = av.open(ruta)
    out = [f.to_image().convert("RGB") for f in cont.decode(cont.streams.video[0])]
    cont.close()
    return out


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
    from PIL import Image, ImageChops
    from motor import exportar as exportar_mod
    time.sleep(3)
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=4)
    logo = os.path.join(ex.TMP, "logo ui.png")
    Image.new("RGBA", (200, 100), (255, 0, 255, 255)).save(logo)

    print("=== 1. las listas ofrecen los efectos nuevos ===")
    ok(abrir(w, src), "abre el video")
    ok(esperar(w, "typeof fx !== 'undefined' && fx.catalogo && fx.catalogo.texto", 10), "el catalogo llego del motor con los efectos nuevos")
    elegir_clip(w, "V1")
    opciones = js(w, "[...document.querySelectorAll('#fx-video .fx__agregar select option')].map(o => o.value)")
    ok(all(k in opciones for k in ("superponer", "quitar_fondo", "texto", "zoom_lento")), "la lista de efectos de video los incluye", str(opciones))

    print("=== 2. texto: un cuadro para escribir ===")
    agregar(w, "video", "texto")
    ok([x["tipo"] for x in efectos_de(w, "V1")] == ["texto"], "Agregar pone el efecto")
    e = js(w, """({area: document.querySelectorAll('#fx-video textarea').length, selects: document.querySelectorAll('#fx-video .fx select').length,
                   rangos: document.querySelectorAll('#fx-video input[type=range]').length, casillas: document.querySelectorAll('#fx-video input[type=checkbox]').length,
                   nota: (document.querySelector('#fx-video .fx__nota') || {}).textContent})""")
    ok(e["area"] == 1 and e["selects"] >= 3 and e["rangos"] == 4 and e["casillas"] == 3, "la tarjeta se arma sola con el catalogo: un cuadro de texto, listas, controles y casillas (contorno, fondo oscuro y el de prender y apagar)", str(e))
    ok(e["nota"] and "exportar" in e["nota"], "y avisa que se ve al exportar", e["nota"])
    w.evaluate_js("""(() => { const a = document.querySelector('#fx-video textarea'); a.value = 'Hola desde la ventana'; a.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.8)
    ok(efectos_de(w, "V1")[0]["params"]["texto"] == "Hola desde la ventana", "al salir del cuadro el texto se guarda en el motor")
    ok(js(w, "document.querySelector('#fx-video textarea').value") == "Hola desde la ventana", "y el cuadro lo conserva al repintar")
    w.evaluate_js("""(() => { const s = document.querySelector('#fx-video .fx select[data-fxk$=":posicion"]'); s.value = 'arriba_centro'; s.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.8)
    ok(efectos_de(w, "V1")[0]["params"]["posicion"] == "arriba_centro", "la lista de posiciones cambia la posicion")

    print("=== 3. logo: el selector de archivos ===")
    agregar(w, "video", "superponer")
    ok(js(w, "document.querySelectorAll('#fx-video .fx').length") == 2, "aparece la tarjeta del logo")
    # el cuadro nativo no se puede manejar: se reemplaza llamar() y se comprueba que se piden SOLO imagenes
    w.evaluate_js("""(() => { window.__pedido = null; const orig = window.llamar;
                       window.llamar = async (m, a) => { if (m === 'elegir_lut') { window.__pedido = a; return {ruta: %s}; } return orig(m, a); }; })()""" % json.dumps(logo))
    w.evaluate_js("""document.querySelectorAll('#fx-video .fx')[1].querySelector('button[data-fxk$=":archivo"]').click()""")
    time.sleep(1.0)
    pedido = js(w, "window.__pedido")
    ok(pedido and ".png" in pedido[0] and ".cube" not in pedido[0], "el selector se abre pidiendo imagenes (no archivos de color)", str(pedido))
    ok(efectos_de(w, "V1")[1]["params"]["archivo"] == logo, "y la imagen elegida queda en el efecto")
    ok(js(w, "document.querySelectorAll('#fx-video .fx')[1].querySelector('.fx__archivo').textContent") == "logo ui.png", "con su nombre a la vista")

    print("=== 3b. el logo en el visor: se ve, se arrastra con el mouse y se elige el tramo ===")
    ok(esperar(w, "(() => { const i = document.querySelector('#logos-visor img'); return i && i.naturalWidth > 0 && i.style.visibility !== 'hidden'; })()", 10),
       "el logo se ve en el visor (la imagen la sirve el motor)")
    caja = js(w, """(() => { const i = document.querySelector('#logos-visor img').getBoundingClientRect();
                     const m = (document.getElementById('capa-video').hidden ? document.getElementById('capa-cuadro') : document.getElementById('capa-video')).getBoundingClientRect();
                     return {il: i.left, it: i.top, iw: i.width, ih: i.height, ml: m.left, mt: m.top, mw: m.width, mh: m.height}; })()""")
    ok(abs(caja["iw"] - caja["mw"] * 0.20) < 2 and abs((caja["il"] + caja["iw"]) - (caja["ml"] + caja["mw"] * 0.97)) < 3
       and abs((caja["it"] + caja["ih"]) - (caja["mt"] + caja["mh"] - caja["mw"] * 0.03)) < 3,
       "con la misma cuenta que al exportar: 20 % del ancho, abajo a la derecha, con su margen", str(caja))
    ok(js(w, "document.querySelectorAll('#fx-video .fx')[1].querySelector('input[data-fxk$=\":x\"]').closest('label').hidden") is True,
       "los controles del lugar libre se esconden mientras la posicion es una de las 9 fijas")
    ok(not js(w, "[...document.querySelectorAll('#fx-video .fx')].some(t => /exportar: la vista previa/.test(t.textContent) && t.querySelector('[data-fxk$=\":archivo\"]'))"),
       "la tarjeta del logo ya no dice que solo se ve al exportar")
    # arrastrarlo hasta la esquina de arriba a la izquierda (mas alla del borde: queda contra el borde)
    w.evaluate_js("""(() => { const i = document.querySelector('#logos-visor img'); const r = i.getBoundingClientRect();
        const ev = (t, x, y) => i.dispatchEvent(new PointerEvent(t, {clientX: x, clientY: y, button: 0, pointerId: 7, bubbles: true}));
        ev('pointerdown', r.left + 10, r.top + 10); ev('pointermove', r.left - 30, r.top - 30); ev('pointermove', -500, -500); ev('pointerup', -500, -500); })()""")
    ok(esperar(w, "S.proy.pistas.find(x => x.id === 'V1').clips[0].efectos[1].params.posicion === 'libre'", 5), "al soltarlo, la posicion pasa a «donde la deje con el mouse»")
    pr = efectos_de(w, "V1")[1]["params"]
    ok(pr["x"] == 0 and pr["y"] == 0, "y queda contra la esquina de arriba a la izquierda (x 0 %, y 0 %)", str(pr))
    caja = js(w, """(() => { const i = document.querySelector('#logos-visor img').getBoundingClientRect();
                     const m = (document.getElementById('capa-video').hidden ? document.getElementById('capa-cuadro') : document.getElementById('capa-video')).getBoundingClientRect();
                     return {dx: i.left - m.left, dy: i.top - m.top}; })()""")
    ok(abs(caja["dx"]) < 2 and abs(caja["dy"]) < 2, "el visor lo muestra ahi", str(caja))
    ok(js(w, "document.querySelectorAll('#fx-video .fx')[1].querySelector('input[data-fxk$=\":x\"]').closest('label').hidden") is False,
       "y aparecen los controles del lugar, para afinarlo con numeros")
    # «Aparece a los»: el boton toma el tiempo de la linea roja (a los 2 s del clip)
    w.evaluate_js("irA(cuadroDe(2.0))")
    time.sleep(0.8)
    w.evaluate_js("""document.querySelectorAll('#fx-video .fx')[1].querySelector('[data-fxk$=":desde:aca"]').click()""")
    ok(esperar(w, "Math.abs(S.proy.pistas.find(x => x.id === 'V1').clips[0].efectos[1].params.desde - 2.0) < 0.051", 5), "«Usar donde está la línea roja» pone el «aparece a los» en 2 s")
    w.evaluate_js("irA(cuadroDe(1.0))")
    ok(esperar(w, "!document.querySelector('#logos-visor img')", 5), "antes de los 2 s el visor no muestra el logo")
    w.evaluate_js("irA(cuadroDe(3.0))")
    ok(esperar(w, "!!document.querySelector('#logos-visor img')", 5), "y despues si")
    w.evaluate_js("""(() => { const r = document.querySelectorAll('#fx-video .fx')[1].querySelector('input[data-fxk$=":desde"]'); r.value = '0'; r.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    ok(esperar(w, "S.proy.pistas.find(x => x.id === 'V1').clips[0].efectos[1].params.desde === 0", 5), "y se vuelve a 0 con el deslizador")
    ajena = api_ref["api"].imagen_efecto(js(w, "S.proy.pistas.find(x => x.id === 'V1').clips[0].id"), js(w, "S.proy.pistas.find(x => x.id === 'V1').clips[0].efectos[0].id"))
    ok("error" in ajena and "url" not in ajena, "el motor solo sirve la imagen de un logo: otro efecto (el texto) no da ningun archivo", str(ajena))

    print("=== 4. lo guardado desde la interfaz se EXPORTA y se mide ===")
    p = api_ref["api"]._copia_del_proyecto()
    ef = {x["tipo"]: x["params"] for x in p.pista("V1")["clips"][0]["efectos"]}
    ok(ef["texto"]["texto"] == "Hola desde la ventana" and ef["superponer"]["archivo"] == logo, "el motor tiene el texto y la imagen que se eligieron")
    r = exportar_mod.exportar(p, os.path.join(ex.TMP, "salida-composicion-app"), "ui")
    cuadros = cuadros_de(r["archivo"])
    p0, _, _ = ex.armar(src)
    r0 = exportar_mod.exportar(p0, os.path.join(ex.TMP, "base-ui"), "base")
    cuadros0 = cuadros_de(r0["archivo"])
    d = ImageChops.difference(cuadros[30], cuadros0[30]).convert("L").point(lambda v: 255 if v > 60 else 0).getbbox()
    ok(len(cuadros) == 120 and d is not None and d[1] < 80, "el archivo exportado tiene el texto arriba (la posicion elegida) y el logo", f"{len(cuadros)} cuadros; cambios en {d}")

    print("=== 5. zoom y quitar fondo ===")
    agregar(w, "video", "zoom_lento")
    agregar(w, "video", "quitar_fondo")
    ok([x["tipo"] for x in efectos_de(w, "V1")] == ["texto", "superponer", "zoom_lento", "quitar_fondo"], "se agregan los otros dos")
    ok(js(w, "document.querySelectorAll('#fx-video .fx').length") == 4, "y hay una tarjeta por cada efecto")
    w.evaluate_js("""(() => { const s = document.querySelectorAll('#fx-video .fx')[3].querySelector('select[data-fxk$=":fondo"]'); s.value = 'blanco'; s.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.8)
    ok(efectos_de(w, "V1")[3]["params"]["fondo"] == "blanco", "se cambia el fondo de reemplazo")
    p = api_ref["api"]._copia_del_proyecto()
    r = exportar_mod.exportar(p, os.path.join(ex.TMP, "salida-composicion-app2"), "todos")
    ok(os.path.isfile(r["archivo"]) and abs(r["duracion"] - 4.0) < 0.1, "con los cuatro efectos puestos desde la interfaz, el video se exporta completo", f"{r['duracion']:.2f} s")

    print("=== 6. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api_ref["api"] = api
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-composicion-app-cache-"), "cache")
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
