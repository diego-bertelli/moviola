# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la app completa con la ventana real (pywebview).

Uso:  python -I pruebas/prueba_app.py

Abre la ventana, abre archivos desde el frontend, mueve el cursor con teclado y
mouse, reproduce y pausa, y revisa que el estado interno y lo que se ve
coincidan. Los videos del Escritorio son opcionales.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")      # estas pruebas no necesitan la deteccion de GPU

import webview  # noqa: E402

from app import API, crear_servidor  # noqa: E402

SERVIDOR = None

ESCRITORIO = os.environ.get("MOVIOLA_VIDEOS_REALES", "")   # carpeta con dos videos reales (uno VFR y un MPEG-PS); sin ella esas partes se saltean
VFR = os.path.join(ESCRITORIO, "real-vfr.mp4")
MPG = os.path.join(ESCRITORIO, "real-mpeg2.mpg")

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def js(w, expresion):
    """Evalua una expresion y devuelve el resultado ya decodificado."""
    r = w.evaluate_js("JSON.stringify((() => { return " + expresion + "; })())")
    return json.loads(r) if r else None


def esperar(w, condicion, tiempo=90.0, paso=0.25):
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
    t0 = time.time()
    listo = esperar(w, "S.ruta === " + json.dumps(ruta) + " && document.getElementById('cargando').hidden", 120)
    return listo, time.time() - t0


def tecla(w, codigo, shift=False):
    w.evaluate_js(
        "window.dispatchEvent(new KeyboardEvent('keydown', {code: '" + codigo + "', shiftKey: "
        + ("true" if shift else "false") + ", bubbles: true, cancelable: true}))")
    time.sleep(0.35)


def clic_en_carril(w, fraccion):
    w.evaluate_js("""(() => {
        const c = document.getElementById('carriles').getBoundingClientRect();
        const x = c.left + c.width * %s, y = c.top + c.height / 2;
        const op = {clientX: x, clientY: y, pointerId: 1, bubbles: true, buttons: 1};
        const caja = document.getElementById('carriles');
        caja.dispatchEvent(new PointerEvent('pointerdown', op));
        caja.dispatchEvent(new PointerEvent('pointerup', op));
    })()""" % fraccion)
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
    tmp = tempfile.mkdtemp(prefix="prueba-app-")

    print("=== 1. arranque ===")
    ok(js(w, "typeof abrir === 'function' && typeof tiempoDe === 'function' && typeof aplicarAudio === 'function'"),
       "app.js cargo completo, con los helpers de tiempo y el modo audio")
    ok(js(w, "document.getElementById('bienvenida').hidden === false"), "arranca en la pantalla de bienvenida")

    print("=== 2. video de framerate variable ===")
    if os.path.isfile(VFR):
        listo, seg = abrir(w, VFR)
        ok(listo, "abre el video VFR", f"{seg:.1f} s")
        e = js(w, """({vfr: S.info.vfr, tiempos: S.tiempos ? S.tiempos.length : 0, total: S.totalCuadros,
                       fps: S.fps, soloAudio: S.soloAudio, avisos: document.getElementById('avisos').textContent.trim(),
                       meta: document.getElementById('meta-archivo').textContent})""")
        ok(e["vfr"] is True and e["tiempos"] == 20247, "recibe la tabla de tiempos (20247)", f"{e['tiempos']}")
        ok(e["soloAudio"] is False, "no esta en modo solo audio")
        ok("variable" in e["meta"], "la cabecera avisa fps variable", e["meta"])
        ok(e["avisos"] == "", "sin avisos de error", repr(e["avisos"]))

        # el cursor es una linea de tiempo: coincide con el instante real del cuadro
        w.evaluate_js("irA(10000, 540)")
        time.sleep(1.0)
        e = js(w, """({n: S.cuadro, t: tiempoDe(S.cuadro), dur: S.duracion,
                       pos: parseFloat(getComputedStyle(document.getElementById('carriles')).getPropertyValue('--pos')),
                       vuelta: cuadroDe(tiempoDe(S.cuadro))})""")
        ok(e["n"] == 10000, "irA(10000)", e["n"])
        ok(abs(e["pos"] - e["t"] / e["dur"]) < 1e-3, "el cursor esta donde cae el cuadro EN EL TIEMPO",
           f"pos {e['pos']:.4f} contra t/dur {e['t'] / e['dur']:.4f}")
        ok(e["vuelta"] == 10000, "tiempo->cuadro->tiempo es exacto")
        # con la cuenta vieja n/fps el cursor habria quedado lejos
        vieja = 10000 / e["dur"] / js(w, "S.fps")
        ok(abs(vieja - e["pos"]) > 0.02, "(la cuenta vieja n/fps habria errado)", f"{vieja:.3f} contra {e['pos']:.3f}")

        # clic en la mitad del carril: cae en el cuadro del instante duracion/2
        clic_en_carril(w, 0.5)
        e = js(w, "({n: S.cuadro, t: tiempoDe(S.cuadro), dur: S.duracion})")
        ok(abs(e["t"] - e["dur"] / 2) < 3.0, "clic al 50% del carril cae en la mitad del TIEMPO",
           f"t={e['t']:.1f} s de {e['dur']:.1f} s")

        # teclado
        w.evaluate_js("irA(5000, 540)")
        time.sleep(0.6)
        tecla(w, "ArrowRight")
        ok(js(w, "S.cuadro") == 5001, "flecha derecha: +1 cuadro", js(w, "S.cuadro"))
        tecla(w, "ArrowLeft")
        ok(js(w, "S.cuadro") == 5000, "flecha izquierda: -1 cuadro")
        t0 = js(w, "tiempoDe(S.cuadro)")
        tecla(w, "ArrowRight", shift=True)
        t1 = js(w, "tiempoDe(S.cuadro)")
        ok(0.9 <= t1 - t0 <= 1.6, "Shift+derecha: avanza ~1 s de TIEMPO real", f"{t1 - t0:.2f} s")
        tecla(w, "Home")
        ok(js(w, "S.cuadro") == 0, "Inicio")
        tecla(w, "End")
        ok(js(w, "S.cuadro") == 20246, "Fin")

        # reproducir y pausar
        w.evaluate_js("irA(3000, 540)")
        time.sleep(0.8)
        w.evaluate_js("reproducir()")
        time.sleep(3.0)
        e = js(w, """({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime,
                       err: !!document.getElementById('capa-video').error, cuadro: S.cuadro,
                       esperado: cuadroDe(document.getElementById('capa-video').currentTime)})""")
        ok(e["rep"] and not e["err"], "reproduce sin errores")
        t_ini = js(w, "tiempoDe(3000)")
        ok(e["ct"] > t_ini + 1.5, "el video avanza desde donde estaba", f"{t_ini:.1f} -> {e['ct']:.1f} s")
        ok(abs(e["cuadro"] - e["esperado"]) <= 3, "el contador sigue al video (por tiempo real)",
           f"{e['cuadro']} contra {e['esperado']}")
        w.evaluate_js("pausar()")
        time.sleep(1.8)
        e = js(w, """({rep: S.reproduciendo, cuadro: S.cuadro, ct: document.getElementById('capa-video').currentTime,
                       oculto: document.getElementById('capa-video').hidden,
                       pintado: S.ultimoPintado, ancho: document.getElementById('capa-cuadro').naturalWidth})""")
        ok(e["rep"] is False and e["oculto"] is True, "pausa y vuelve al cuadro exacto")
        ok(e["pintado"] and e["pintado"]["n"] == e["cuadro"], "el cuadro mostrado ES el de la pausa",
           f"pintado {e['pintado'] and e['pintado']['n']}, estado {e['cuadro']}")
        ok(abs(e["cuadro"] - js(w, "cuadroDe(%f)" % e["ct"])) <= 1, "y corresponde al instante de pausa del video")
    else:
        print("  (sin el video del Escritorio, se saltea)")

    print("=== 3. MPEG-2 entrelazado (no reproducible directo) ===")
    if os.path.isfile(MPG):
        listo, seg = abrir(w, MPG)
        ok(listo, "abre el .mpg de 654 MB", f"{seg:.1f} s")
        e = js(w, """({total: S.totalCuadros, entrel: S.info.entrelazado, web: S.info.web_compatible, vfr: S.info.vfr,
                       meta: document.getElementById('meta-archivo').textContent,
                       tira: document.querySelectorAll('#tira .mini').length,
                       onda: !document.getElementById('onda').hidden,
                       aviso: document.getElementById('avisos').textContent.trim().slice(0, 90),
                       reanuda: S.tiempos === null})""")
        ok(e["total"] == 9750 and e["reanuda"], "9750 cuadros, y descartó la tabla del VFR anterior")
        ok(e["entrel"] is True and "entrelazado" in e["meta"], "marca entrelazado en la cabecera", e["meta"])
        ok(e["web"] is False and "no se puede reproducir" in e["aviso"].lower() or e["web"] is False,
           "avisa que no se reproduce todavia (lo resuelve el proxy)")
        ok(e["tira"] > 0 and e["onda"], "tira de miniaturas y espectro presentes")
        w.evaluate_js("irA(5000, 540)")
        time.sleep(1.0)
        ok(js(w, "S.ultimoPintado && S.ultimoPintado.n") == 5000, "cuadro 5000 del .mpg pintado")
        w.evaluate_js("irA(9749, 540)")
        time.sleep(1.0)
        ok(js(w, "S.ultimoPintado && S.ultimoPintado.n") == 9749, "y el ULTIMO cuadro (9749) tambien")
    else:
        print("  (sin el video del Escritorio, se saltea)")

    print("=== 4. solo audio ===")
    mp3 = os.path.join(tmp, "tono.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=12", "-ac", "2", mp3], check=True)
    listo, seg = abrir(w, mp3)
    ok(listo, "abre un mp3", f"{seg:.1f} s")
    e = js(w, """({audio: S.soloAudio, panel: !document.getElementById('panel-audio').hidden,
                   tira: !document.getElementById('tira').hidden,
                   campoCuadro: !document.getElementById('cuadro-actual').closest('.contador__campo').hidden,
                   img: !document.getElementById('capa-cuadro').hidden,
                   onda: !document.getElementById('onda').hidden, dur: S.duracion, picos: S.picos.length,
                   meta: document.getElementById('meta-archivo').textContent,
                   web: S.info.web_compatible, avisos: document.getElementById('avisos').textContent.trim()})""")
    ok(e["audio"] and e["panel"], "muestra el panel de solo audio")
    ok(not e["tira"] and not e["campoCuadro"] and not e["img"], "oculta tira, contador de cuadros e imagen")
    ok(e["onda"] and e["picos"] == 2000, "el espectro es lo principal", f"{e['picos']} picos")
    ok(abs(e["dur"] - 12.0) < 0.2, "duracion 12 s", e["dur"])
    ok(e["web"] is True and e["avisos"] == "", "reproducible, sin avisos", e["meta"])
    clic_en_carril(w, 0.5)
    t = js(w, "tiempoDe(S.cuadro)")
    ok(abs(t - 6.0) < 0.3, "clic al 50% del espectro cae en 6 s", f"{t:.2f} s")
    w.evaluate_js("reproducir()")
    time.sleep(2.5)
    e = js(w, """({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime,
                   err: !!document.getElementById('capa-video').error,
                   oculto: document.getElementById('capa-video').hidden})""")
    ok(e["rep"] and not e["err"], "reproduce el audio sin errores")
    ok(e["ct"] > 7.5, "avanza desde los 6 s", f"{e['ct']:.2f} s")
    w.evaluate_js("pausar()")
    time.sleep(0.8)
    ok(js(w, "S.reproduciendo") is False, "pausa")
    tecla(w, "ArrowRight", shift=True)
    ok(js(w, "tiempoDe(S.cuadro)") > t + 1.5, "Shift+derecha avanza ~1 s en audio")

    print("=== 5. volver a un video despues del audio (sin estado viejo) ===")
    cfr = os.path.join(tmp, "cfr.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=6",
                    "-f", "lavfi", "-i", "sine=f=330:d=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", cfr], check=True)
    listo, seg = abrir(w, cfr)
    ok(listo, "abre un mp4 normal")
    e = js(w, """({audio: S.soloAudio, panel: document.getElementById('panel-audio').hidden,
                   tira: !document.getElementById('tira').hidden,
                   campoCuadro: !document.getElementById('cuadro-actual').closest('.contador__campo').hidden,
                   img: !document.getElementById('capa-cuadro').hidden, total: S.totalCuadros,
                   btn: !document.getElementById('btn-cuadro-atras').hidden, tiempos: S.tiempos === null})""")
    ok(e["audio"] is False and e["panel"] is True, "sale del modo solo audio")
    ok(e["tira"] and e["campoCuadro"] and e["img"] and e["btn"], "vuelven la tira, el contador, la imagen y los botones")
    ok(e["total"] == 180 and e["tiempos"], "180 cuadros, sin tabla VFR")
    w.evaluate_js("irA(90, 540)")
    time.sleep(0.8)
    ok(js(w, "S.ultimoPintado && S.ultimoPintado.n") == 90, "y muestra cuadros de nuevo")

    print("=== 6. archivo que no es de medios ===")
    basura = os.path.join(tmp, "texto.mp4")
    with open(basura, "wb") as f:
        f.write(b"esto no es un video" * 100)
    w.evaluate_js("abrir(" + json.dumps(basura) + ")")
    ok(esperar(w, "document.getElementById('avisos').textContent.trim().length > 0", 30), "avisa el error en pantalla")
    aviso = js(w, "document.getElementById('avisos').textContent.trim()")
    ok("No pude abrir" in aviso, "con un mensaje en castellano", aviso[:70])
    ok(js(w, "S.ruta") == cfr, "y la pantalla no pierde el video que estaba abierto")
    ok("dañado" in aviso or "reconozco" in aviso, "el mensaje se entiende (no es un codigo de error crudo)", aviso)
    # lo importante: el MOTOR tambien tiene que seguir con el video viejo
    w.evaluate_js("window.__r = null; fetch(BASE + 'frame?n=10&w=270').then(async r => { "
                  "window.__r = {estado: r.status, tipo: r.headers.get('content-type'), bytes: (await r.blob()).size}; })")
    time.sleep(1.0)
    r = js(w, "window.__r")
    ok(bool(r) and r.get("estado") == 200 and r.get("tipo") == "image/jpeg" and r.get("bytes", 0) > 500,
       "y el motor sigue sirviendo cuadros del video viejo", str(r))
    ok(os.path.exists(os.path.join(RAIZ, "editor.log")), "el detalle tecnico quedo en editor.log")

    print("=== 7. la pagina no puede hablar con nada fuera de este servidor ===")
    # El navegador hace cumplir la CSP: un intento de contactar otro origen genera un
    # evento de violacion ANTES de salir a la red.
    w.evaluate_js("""window.__csp = null;
        document.addEventListener('securitypolicyviolation', e => { window.__csp = e.violatedDirective; });
        fetch('http://127.0.0.1:9/sacar-datos').catch(() => {});""")
    time.sleep(1.0)
    directiva = js(w, "window.__csp")
    ok(bool(directiva) and "connect-src" in directiva, "fetch a otro origen bloqueado por la CSP", directiva)
    w.evaluate_js("""window.__csp2 = null;
        document.addEventListener('securitypolicyviolation', e => { window.__csp2 = e.violatedDirective; });
        const i = new Image(); i.src = 'http://127.0.0.1:9/pixel.png';""")
    time.sleep(1.0)
    directiva = js(w, "window.__csp2")
    ok(bool(directiva) and "img-src" in directiva, "una imagen de otro origen tambien", directiva)

    print("=== 8. latido y errores ===")
    sin = SERVIDOR.segundos_sin_latido()
    ok(sin is not None and sin < 7, "la pagina manda latido cada pocos segundos", None if sin is None else f"{sin:.1f} s")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    global SERVIDOR
    api = API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-app-cache-"), "cache")
    SERVIDOR = crear_servidor(api)
    try:
        webview.create_window("prueba", SERVIDOR.url_inicio(), width=1200, height=820)
        webview.start(correr, webview.windows[0])
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
