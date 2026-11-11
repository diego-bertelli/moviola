# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del modo navegador (sin abrir ninguna ventana ni navegador de verdad).

Uso:  python -I pruebas/prueba_navegador.py

Cubre: deteccion de WebView2, el apagado automatico cuando se cierra la pestana
(latido que deja de llegar), el apagado si la pagina nunca carga, el archivo inicial
por linea de comandos y que el dialogo de archivos de tkinter se pueda crear en un hilo.
"""

import json
import os
import sys
import threading
import time
import http.client

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")      # estas pruebas no necesitan la deteccion de GPU

import app  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def latido(servidor):
    c = http.client.HTTPConnection("127.0.0.1", servidor.puerto, timeout=5)
    c.request("POST", f"/{servidor.token}/api/latido", b"[]",
              {"Content-Type": "application/json", "Host": f"127.0.0.1:{servidor.puerto}"})
    r = c.getresponse()
    r.read()
    c.close()
    return r.status


def llamar(servidor, metodo, args=None):
    c = http.client.HTTPConnection("127.0.0.1", servidor.puerto, timeout=5)
    c.request("POST", f"/{servidor.token}/api/{metodo}", json.dumps(args or []).encode(),
              {"Content-Type": "application/json", "Host": f"127.0.0.1:{servidor.puerto}"})
    r = c.getresponse()
    datos = json.loads(r.read())
    c.close()
    return datos


def main():
    print("=== 1. WebView2 ===")
    ok(isinstance(app._hay_webview2(), bool), "la deteccion devuelve un booleano", app._hay_webview2())

    # el navegador no se abre de verdad
    import webbrowser
    abiertos = []
    webbrowser.open = lambda url, *a, **k: abiertos.append(url) or True

    print("=== 2. se cierra la pestaña: el motor se apaga solo ===")
    app.LIMITE_SIN_LATIDO = 2.5
    api = app.API()
    srv = app.crear_servidor(api)
    pulsos = threading.Thread(target=lambda: [(latido(srv), time.sleep(0.5)) for _ in range(6)], daemon=True)
    pulsos.start()
    t0 = time.time()
    app._navegador(api, srv)
    dt = time.time() - t0
    ok(len(abiertos) == 1 and abiertos[0] == srv.url_inicio(), "abre el navegador en la direccion con token")
    ok(3.0 < dt < 9.0, "termina unos segundos despues del ultimo latido", f"{dt:.1f} s (latidos durante ~3 s + 2,5 s de espera)")
    api.cerrar()

    print("=== 3. la pagina nunca carga ===")
    app.LIMITE_CARGA = 2.0
    api = app.API()
    srv = app.crear_servidor(api)
    t0 = time.time()
    app._navegador(api, srv)
    dt = time.time() - t0
    ok(1.5 < dt < 5.0, "se rinde si no llega ningun latido", f"{dt:.1f} s")
    api.cerrar()

    print("=== 4. archivo inicial por linea de comandos ===")
    api = app.API()
    srv = app.crear_servidor(api)
    api.archivo_inicial = r"C:\ruta\video.mp4"
    r1 = llamar(srv, "inicial")
    r2 = llamar(srv, "inicial")
    ok(r1 == {"ruta": r"C:\ruta\video.mp4"} and r2 == {"ruta": None}, "se entrega una sola vez", f"{r1} luego {r2}")
    api.cerrar()

    print("=== 5. dialogo de archivos del modo navegador (tkinter) ===")
    resultado = {}

    def crear():
        try:
            import tkinter
            raiz = tkinter.Tk()
            raiz.withdraw()
            raiz.attributes("-topmost", True)
            raiz.update()
            raiz.destroy()
            resultado["ok"] = True
        except Exception as e:
            resultado["error"] = repr(e)

    h = threading.Thread(target=crear)
    h.start()
    h.join(15)
    ok(resultado.get("ok") is True, "tkinter se puede crear y destruir desde un hilo (sin mostrar el dialogo)",
       resultado.get("error", ""))

    print("=== 6. el dialogo no revienta si falla ===")
    api = app.API()
    srv = app.crear_servidor(api)
    original = app._dialogo_tkinter
    app._dialogo_tkinter = lambda: (_ for _ in ()).throw(RuntimeError("sin pantalla"))
    r = llamar(srv, "elegir_archivo")
    app._dialogo_tkinter = lambda: ""
    r_cancelado = llamar(srv, "elegir_archivo")
    app._dialogo_tkinter = lambda: r"C:\video.mp4"
    r_ruta = llamar(srv, "elegir_archivo")
    app._dialogo_tkinter = original
    ok("error" in r and "selector" in r["error"], "si el dialogo falla devuelve un mensaje que se entiende", r)
    ok(r_cancelado == {"cancelado": True}, "cancelar devuelve cancelado")
    ok(r_ruta == {"ruta": r"C:\video.mp4"}, "elegir devuelve la ruta")
    api.cerrar()

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
