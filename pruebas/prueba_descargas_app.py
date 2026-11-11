# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Bajar de YouTube en la interfaz, con la ventana REAL y un yt-dlp de mentira (sin internet).

Uso:  python -I pruebas/prueba_descargas_app.py
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
TMP = tempfile.mkdtemp(prefix="prueba-descargas-app-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")
os.environ["MOVIOLA_YTDLP"] = os.path.join(AQUI, "falso_ytdlp.py")
os.environ["MOVIOLA_DESCARGAS"] = os.path.join(TMP, "bajados")

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


def clic(w, id_):
    w.evaluate_js("document.getElementById(%s).click()" % json.dumps(id_))
    time.sleep(0.6)


def escribir(w, url, derecho=True):
    w.evaluate_js("""(() => { const u = document.getElementById('yt-url'); u.value = %s; u.dispatchEvent(new Event('input', {bubbles: true}));
                       const c = document.getElementById('yt-derecho'); c.checked = %s; c.dispatchEvent(new Event('change', {bubbles: true})); })()""" % (json.dumps(url), "true" if derecho else "false"))
    time.sleep(0.3)


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
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=4)

    print("=== 1. el dialogo ===")
    ok(js(w, "!document.getElementById('btn-youtube').hidden") and js(w, "document.getElementById('btn-youtube-medios').hidden"), "en la pantalla de inicio esta «Bajar de YouTube» (y el del panel de medios, escondido hasta abrir algo)")
    clic(w, "btn-youtube")
    ok(esperar(w, "document.getElementById('dlg-youtube').open", 5), "se abre el dialogo")
    e = js(w, """({aviso: document.querySelector('#dlg-youtube .exp__nota').textContent, calidades: [...document.querySelectorAll('#yt-calidad option')].map(o => o.value), carpeta: document.getElementById('yt-carpeta').textContent,
                   bajar: document.getElementById('yt-bajar').disabled, herramienta: document.getElementById('yt-herramienta').hidden})""")
    ok("tuyos" in e["aviso"] and "libre difusión" in e["aviso"] and "no esquiva ninguna protección" in e["aviso"], "avisa que es para videos tuyos o de libre difusion y que Moviola no esquiva protecciones", e["aviso"][:80])
    ok(e["calidades"] == ["mejor", "1080", "720", "480"] and e["carpeta"] == os.environ["MOVIOLA_DESCARGAS"] and e["bajar"] and e["herramienta"], "ofrece las 4 calidades de video (el audio tiene su propio selector), dice donde se guarda, y «Bajar» esta apagado", str(e))
    escribir(w, "https://youtu.be/dQw4w9WgXcQ", derecho=False)
    ok(js(w, "document.getElementById('yt-bajar').disabled"), "con la direccion pero SIN confirmar el derecho, «Bajar» sigue apagado")
    escribir(w, "", derecho=True)
    ok(js(w, "document.getElementById('yt-bajar').disabled"), "con la confirmacion pero sin direccion, tambien")

    print("=== 2. errores claros ===")
    escribir(w, "https://vimeo.com/123456")
    clic(w, "yt-bajar")
    ok(esperar(w, "!document.getElementById('yt-error').hidden", 5) and "YouTube" in js(w, "document.getElementById('yt-error').textContent"), "una direccion de otro sitio: error claro y no empieza nada", js(w, "document.getElementById('yt-error').textContent"))
    escribir(w, "https://youtu.be/priv0000001")
    clic(w, "yt-bajar")
    ok(esperar(w, "!document.getElementById('yt-error').hidden && document.getElementById('yt-error').textContent.includes('privado')", 15), "un video privado: «Ese video es privado», y se puede probar otro", js(w, "document.getElementById('yt-error').textContent"))
    ok(not js(w, "document.getElementById('yt-formulario').hidden"), "(el formulario sigue ahi)")

    print("=== 3. bajar y editar ===")
    escribir(w, "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxx")
    w.evaluate_js("document.getElementById('yt-calidad').value = '720'")
    clic(w, "yt-bajar")
    ok(esperar(w, "!document.getElementById('yt-progreso').hidden && !document.getElementById('yt-cancelar').hidden", 5), "al bajar se ve el avance y el boton para cancelar")
    ok(esperar(w, "!document.getElementById('yt-resultado').hidden", 30), "termina")
    e = js(w, "({texto: document.getElementById('yt-resultado-texto').textContent, sumar: document.getElementById('yt-sumar').hidden})")
    ok(e["texto"].startswith("Listo: Video de prueba [dQw4w9WgXcQ]") and e["sumar"], "dice el nombre del archivo; sin proyecto abierto no ofrece «Agregarlo al proyecto»", str(e))
    clic(w, "yt-editar")
    ok(esperar(w, "S.ruta && S.ruta.includes('dQw4w9WgXcQ') && document.getElementById('cargando').hidden", 30) and not js(w, "document.getElementById('dlg-youtube').open"), "«Editarlo» cierra el dialogo y abre el video bajado")
    ok(js(w, "S.proy.pistas[0].clips.length") == 1 and abs(js(w, "S.proy.duracion") - 2.0) < 0.1, "como un video mas (2 s)")

    print("=== 4. sumarlo a un proyecto abierto ===")
    ok(js(w, "!document.getElementById('btn-youtube-medios').hidden"), "con un proyecto abierto aparece «Bajar de YouTube…» en el panel de medios")
    clic(w, "btn-youtube-medios")
    ok(esperar(w, "document.getElementById('dlg-youtube').open", 5), "se abre el mismo dialogo")
    escribir(w, "https://youtu.be/abcDEF12345")
    clic(w, "yt-bajar")
    ok(esperar(w, "!document.getElementById('yt-resultado').hidden", 30), "baja otro")
    ok(not js(w, "document.getElementById('yt-sumar').hidden") and js(w, "document.getElementById('yt-sumar').textContent") == "Agregarlo al proyecto", "ahora SI ofrece «Agregarlo al proyecto»")
    clic(w, "yt-sumar")
    ok(esperar(w, "Object.keys(S.proy.fuentes).length === 2", 15), "lo suma al panel de medios (todavia no a la linea de tiempo)")
    ok(js(w, "S.proy.pistas[0].clips.length") == 1, "y la linea de tiempo sigue igual")

    print("=== 5. audio y cancelar ===")
    clic(w, "btn-youtube-medios")
    esperar(w, "document.getElementById('dlg-youtube').open", 5)
    escribir(w, "https://youtu.be/ZZZZZZZZZZZ")
    ok(js(w, "!document.getElementById('yt-calidad-campo').hidden") and js(w, "document.getElementById('yt-bajar').textContent") == "Bajar el video", "por defecto se baja el VIDEO (con el selector de calidad)")
    w.evaluate_js("document.querySelector('[data-yt-tipo=audio]').click()")
    time.sleep(0.4)
    ok(js(w, "document.getElementById('yt-calidad-campo').hidden") and js(w, "document.getElementById('yt-bajar').textContent") == "Bajar el audio" and js(w, "document.querySelector('[data-yt-tipo=audio]').getAttribute('aria-checked')") == "true", "elegir «Solo el audio (MP3)»: se esconde la calidad y el boton dice «Bajar el audio»")
    clic(w, "yt-bajar")
    ok(esperar(w, "!document.getElementById('yt-resultado').hidden", 30) and js(w, "document.getElementById('yt-sumar').textContent") == "Ponerlo como audio en el cursor", "«Solo el audio»: baja un MP3 y ofrece ponerlo como audio")
    clic(w, "yt-sumar")
    ok(esperar(w, "S.proy.pistas.length >= 3", 15), "y lo pone en una pista de audio extra")
    clic(w, "btn-youtube-medios")
    esperar(w, "document.getElementById('dlg-youtube').open", 5)
    escribir(w, "https://youtu.be/cuelga00001")
    clic(w, "yt-bajar")
    ok(esperar(w, "!document.getElementById('yt-cancelar').hidden", 5), "una descarga lenta se puede cancelar")
    time.sleep(1.0)
    clic(w, "yt-cancelar")
    ok(esperar(w, "!document.getElementById('yt-formulario').hidden && document.getElementById('yt-error').textContent.includes('cancelada')", 15), "«Cancelar la descarga» vuelve al formulario y lo dice")
    clic(w, "yt-cerrar")
    ok(not js(w, "document.getElementById('dlg-youtube').open"), "Cerrar cierra el dialogo")

    print("=== 6. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1280, height=900)
        webview.start(correr, webview.windows[0])
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
