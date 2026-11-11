# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Regresiones de la auditoria del codigo: cosas que se encontraron leyendo y sondeando, y que ya no tienen que volver.

Uso:  python -I pruebas/prueba_auditoria.py
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-auditoria-"), "ajustes.json")

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
from motor.video import Video  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def post(srv, nombre, cuerpo_bytes):
    c = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=60)
    c.putrequest("POST", "/%s/api/%s" % (srv.token, nombre), skip_host=True)
    for k, v in {"Host": "127.0.0.1:%d" % srv.puerto, "Content-Type": "application/json", "Content-Length": str(len(cuerpo_bytes))}.items():
        c.putheader(k, v)
    c.endheaders(cuerpo_bytes)
    r = c.getresponse()
    d = r.read()
    c.close()
    return r.status, d


def main():
    src = ex.crear_fuente(os.path.join(ex.TMP, "s.mp4"), dur=6)
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(), "cache")
    srv = app.crear_servidor(api)
    api.abrir(src)

    print("=== 1. NaN e Infinity no entran (antes borraban 5 de 6 segundos y rompian el JSON) ===")
    antes = json.dumps(api.proyecto_estado(), sort_keys=True)
    for etiqueta, cuerpo in (("NaN en un tramo", b"[NaN, 1.0]"), ("Infinity", b"[1.0, Infinity]"), ("-Infinity", b"[-Infinity, 1.0]")):
        s, _ = post(srv, "editar_borrar_rango", cuerpo)
        ok(s == 400, f"{etiqueta}: el servidor responde 400", s)
    s, _ = post(srv, "editar_volumen", b'["c2", NaN]')
    ok(s == 400, "tambien en el volumen")
    s, _ = post(srv, "agregar_audio", json.dumps([src, 0]).encode().replace(b"0]", b"NaN]"))
    ok(s == 400, "y al agregar audio")
    ok(json.dumps(api.proyecto_estado(), sort_keys=True) == antes, "el proyecto quedo exactamente igual")
    r = api._editar("borrar_rango", float("nan"), 1.0)
    ok("error" in r and abs(api.proyecto.duracion() - 6.0) < 0.05, "y aunque algo llamara directo al motor, un NaN se rechaza", r.get("error"))
    s, d = post(srv, "editar_borrar_rango", b"[1.0, 2.0]")
    ok(s == 200 and abs(json.loads(d)["proyecto"]["duracion"] - 5.0) < 0.05, "un pedido normal sigue andando")
    api._editar("deshacer")

    print("=== 2. dos exportaciones a la vez: entra una sola ===")
    carpeta = os.path.join(ex.TMP, "salida")
    os.makedirs(carpeta)
    resultados = []

    def lanzar():
        resultados.append(api.exportar_iniciar({"formato": "horizontal", "carpeta": carpeta, "nombre": "x"}))

    hilos = [threading.Thread(target=lanzar) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    ok(sum(1 for r in resultados if r.get("ok")) == 1 and sum(1 for r in resultados if "en curso" in r.get("error", "")) == 7,
       "8 pedidos simultaneos: 1 arranca y 7 reciben 'ya hay una en curso'", str([r.get("ok") or r.get("error") for r in resultados]))
    api.exportar_cancelar()
    for _ in range(150):
        if api.exportar_estado()["estado"] != "exportando":
            break
        time.sleep(0.2)
    ok(api.exportar_estado()["estado"] in ("cancelado", "listo"), "y termina", api.exportar_estado()["estado"])
    r = api.exportar_iniciar({"formato": "vertical", "carpeta": carpeta, "foco": [float("nan"), 0.5]})
    ok("error" in r, "un foco NaN se rechaza", r.get("error"))

    print("=== 3. un archivo danado no queda abierto ===")
    malo = os.path.join(ex.TMP, "malo.mp4")
    con_video = open(src, "rb").read()
    with open(malo, "wb") as f:
        f.write(con_video[:40000])               # cortado: el indice (moov) se perdio
    try:
        Video(malo).cerrar()
        abrio = True
    except Exception:
        abrio = False
    try:
        os.remove(malo)
        liberado = True
    except OSError:
        liberado = False
    ok(liberado, "tras fallar al abrirlo se puede borrar el archivo (no queda bloqueado)", "abrio igual" if abrio else "")

    print("=== 4. cerrar limpia lo temporal ===")
    temporal = api.temp
    ok(os.path.isdir(temporal), "hay una carpeta temporal de la sesion")
    api.cerrar()
    ok(not os.path.exists(temporal), "y se borra al cerrar")

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
