# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Auditoria de hilos: el servidor atiende cada pedido en su propio hilo, asi que la interfaz puede pedir cuadros, editar, guardar,
consultar medios y exportar AL MISMO TIEMPO. Se lanzan muchos hilos a la vez contra la misma API y se exige: ninguna excepcion, el proyecto
valido al final, y que una exportacion hecha en medio de las ediciones sea un video completo y coherente (se exporta una COPIA).

Uso:  python -I pruebas/prueba_concurrencia.py
"""

import os
import random
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-concurrencia-"), "ajustes.json")

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

ok = ex.ok


def main():
    a = ex.crear_fuente(os.path.join(ex.TMP, "A.mp4"), dur=6)
    b = ex.crear_fuente(os.path.join(ex.TMP, "B.mp4"), dur=3, w=320, h=180, fps=25)
    carpeta = tempfile.mkdtemp(prefix="prueba-concurrencia-salida-")
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-concurrencia-cache-"), "cache")
    app.crear_servidor(api)
    api.abrir(a)
    rb = api.agregar_medio(b)
    fid_b = rb["fuente"]
    api._guardar_en(os.path.join(carpeta, "c.moviola"))
    errores = []
    parar = threading.Event()

    def trabajador(nombre, f):
        azar = random.Random(nombre)
        while not parar.is_set():
            try:
                f(azar)
            except Exception as e:
                errores.append((nombre, type(e).__name__ + ": " + str(e)[:100]))
                return
            time.sleep(0.005)

    def editar(azar):
        op = azar.choice(["dividir", "dividir", "deshacer", "rehacer", "insertar", "borrar"])
        if op == "dividir":
            api._editar("dividir", azar.uniform(0, 6))
        elif op == "insertar":
            api._editar("insertar_fuente", fid_b)
        elif op == "borrar":
            t0 = azar.uniform(0, 4)
            api._editar("borrar_rango", t0, t0 + azar.uniform(0.2, 1.0))
        else:
            api._editar(op)

    def pedir_cuadros(azar):
        api.cuadro_jpeg(azar.randint(0, 150), 120)
        api.cuadro_jpeg(azar.randint(0, 70), 120, fid_b)

    def consultar(azar):
        api.medio_info(fid_b)
        api.picos_fuente(fid_b)
        api.proyecto_estado()
        api.recientes()
        api.exportar_estado()

    def guardar(azar):
        api.guardar_proyecto()
        time.sleep(0.05)

    hilos = [threading.Thread(target=trabajador, args=(n, f), daemon=True) for n, f in
             (("editar-1", editar), ("editar-2", editar), ("cuadros-1", pedir_cuadros), ("cuadros-2", pedir_cuadros), ("consultas", consultar), ("guardar", guardar))]
    for h in hilos:
        h.start()
    time.sleep(1.0)
    # una exportacion EN MEDIO de todo ese trabajo
    inicio = time.time()
    r = api.exportar_iniciar({"formato": "original", "carpeta": carpeta, "nombre": "en_medio", "encuadre": "recortar", "foco": [0.5, 0.5]})
    ok(r.get("ok") is True, "arranca una exportacion mientras otros hilos editan, piden cuadros y guardan", str(r))
    estado = {}
    while time.time() - inicio < 120:
        estado = api.exportar_estado()
        if estado.get("estado") in ("listo", "error", "cancelado"):
            break
        time.sleep(0.3)
    time.sleep(1.0)
    parar.set()
    for h in hilos:
        h.join(10)
    ok(estado.get("estado") == "listo" and os.path.isfile(estado.get("archivo", "")), "la exportacion termina bien", str(estado))
    if estado.get("estado") == "listo":
        v, au, d = ex.sondear(estado["archivo"])
        ok(abs(float(v["duration"]) - estado["duracion"]) < 0.2 and au is not None, "y es un video completo y coherente (la imagen y el sonido duran lo mismo)", "%s s vs %s s" % (v["duration"], estado["duracion"]))
    ok(not errores, "ningun hilo termino con una excepcion", str(errores[:3]))
    ok(api.proyecto.validar() == [], "el proyecto quedo valido despues de todo")
    guardado = api.guardar_proyecto()
    ok(not guardado.get("error"), "y se puede guardar", str(guardado.get("error")))
    api.cerrar()
    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
