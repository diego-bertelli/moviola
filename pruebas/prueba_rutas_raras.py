# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Auditoria: nombres de carpetas y archivos «dificiles» (acentos, eñes, espacios, corchetes, apostrofes, signos de porcentaje) en TODO el recorrido:
abrir un video, sumar otro, guardar y abrir el proyecto, imagenes y letras de los efectos, subtitulos quemados y exportar.

Uso:  python -I pruebas/prueba_rutas_raras.py
"""

import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-rutas-"), "ajustes.json")

from PIL import Image  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402

ok = ex.ok

NOMBRES = ["Ñandú ¿qué (final) [v2]", "100% real & más", "l'été à São Paulo", "con   espacios   dobles", "日本語のフォルダ"]


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-rutas-cache-"), "cache")
    app.crear_servidor(api)
    base = tempfile.mkdtemp(prefix="prueba-rutas-base-")
    for nombre in NOMBRES:
        print("=== carpeta: %s ===" % nombre)
        carpeta = os.path.join(base, nombre)
        os.makedirs(carpeta)
        a = ex.crear_fuente(os.path.join(carpeta, "vídeo ñ A.mp4"), dur=3)
        b = ex.crear_fuente(os.path.join(carpeta, "otro [B] 50%.mp4"), dur=2, w=320, h=180, fps=25)
        logo = os.path.join(carpeta, "logo ñ.png")
        Image.new("RGBA", (64, 32), (255, 0, 255, 255)).save(logo)
        r = api.abrir(a)
        ok(not r.get("error") and r["nombre"] == "vídeo ñ A.mp4", "abrir el video", str(r.get("error")))
        rb = api.agregar_medio(b)
        ok(not rb.get("error"), "sumar el segundo video", str(rb.get("error")))
        api._editar("insertar_fuente", rb["fuente"])
        cid = api.proyecto.pista("V1")["clips"][0]["id"]
        api.proyecto.agregar_efecto(cid, "superponer", {"archivo": logo, "posicion": "arriba_izquierda"})
        api.proyecto.agregar_efecto(cid, "texto", {"texto": nombre + " — ¡hola!", "tamano": 10})
        api.proyecto.subtitulo_agregar(0.5, 2.0, "Ñandú: «%s» 100%% & <b>")
        ruta_p = os.path.join(carpeta, "proyecto " + nombre + ".moviola")
        g = api._guardar_en(ruta_p)
        ok(not g.get("error") and os.path.isfile(ruta_p), "guardar el proyecto con ese nombre", str(g.get("error")))
        api2 = app.API()
        api2.cache = api.cache
        app.crear_servidor(api2)
        r2 = api2.abrir(ruta_p)
        ok(not r2.get("error") and len(api2.proyecto.pista("V1")["clips"]) == 2 and api2.proyecto.subtitulos["frases"][0]["texto"].startswith("Ñandú"),
           "abrir el proyecto guardado (con sus dos videos, los efectos y los subtitulos)", str(r2.get("error")))
        arch, res = im.exportar(api2.proyecto, "r_" + str(abs(hash(nombre)) % 9999), subtitulos={"quemar": True, "srt": True})
        cu = im.todos_los_cuadros(arch)
        ok(len(cu) == 150 and abs(res["duracion"] - 5.0) < 0.1 and len(res["subtitulos"]) == 1, "exportar con el logo, el texto y los subtitulos quemados", "%d cuadros" % len(cu))
        srt = open(res["subtitulos"][0], encoding="utf-8").read()
        ok("Ñandú" in srt and "100%" in srt, "el .srt conserva los acentos y el signo de porcentaje")
        api2.cerrar()

    print()
    api.cerrar()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
