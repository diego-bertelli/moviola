# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Los cuadros de «elegir archivo» del sistema, SIN abrirlos: se les pasa una ventana de mentira que valida los filtros con el MISMO
validador que usa pywebview (webview.util.parse_file_type). Un filtro mal escrito (por ejemplo, con comas en el nombre) hace que el cuadro
real no abra nunca y la persona vea «No pude abrir el selector de archivos»: esta prueba lo atrapa.

Uso:  python -I pruebas/prueba_dialogos.py
"""

import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-dialogos-"), "ajustes.json")

import webview  # noqa: E402
from webview.util import parse_file_type  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

ok = ex.ok


class VentanaDeMentira:
    def __init__(self):
        self.pedidos = []

    def create_file_dialog(self, dialog_type=webview.FileDialog.OPEN, directory="", allow_multiple=False, save_filename="", file_types=()):
        for t in file_types:
            parse_file_type(t)                       # levanta ValueError si el filtro no es valido, como el cuadro real
        self.pedidos.append((dialog_type, file_types))
        if dialog_type == webview.FileDialog.FOLDER:
            return [tempfile.gettempdir()]
        if dialog_type == webview.FileDialog.SAVE:
            return [os.path.join(tempfile.gettempdir(), "dialogo-prueba.moviola")]
        return ["C:\\x\\a.mp4", "C:\\x\\b.mp4"] if allow_multiple else ["C:\\x\\a.mp4"]


def main():
    print("=== los filtros, uno por uno ===")
    for t in app.TIPOS:
        try:
            parse_file_type(t)
            ok(True, "filtro valido: " + t[:44] + "…")
        except ValueError as e:
            ok(False, "filtro valido: " + t[:44] + "…", str(e)[:80])

    print("=== cada cuadro de la API, con la ventana de mentira ===")
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=2)
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-dialogos-cache-"), "cache")
    app.crear_servidor(api)
    v = VentanaDeMentira()
    api.ventana = v
    r = api.elegir_archivo()
    ok(r.get("ruta") and not r.get("error"), "«Editar un video» (elegir_archivo) abre el cuadro", str(r))
    r = api.elegir_proyecto()
    ok(r.get("ruta") and not r.get("error"), "«Abrir un proyecto» (elegir_proyecto) abre el cuadro", str(r))
    r = api.elegir_videos()
    ok(r.get("rutas") and len(r["rutas"]) == 2 and not r.get("error"), "«Agregar videos» / «Crear un proyecto» / «Procesar varios» (elegir_videos): varios archivos", str(r))
    r = api.elegir_lut()
    ok(r.get("ruta") and not r.get("error"), "elegir un archivo de color (LUT)", str(r))
    r = api.elegir_lut([".png", ".jpg"])
    ok(r.get("ruta") and not r.get("error"), "elegir una imagen (logo o fondo)", str(r))
    r = api.elegir_carpeta()
    ok(r.get("ruta") and not r.get("error"), "elegir una carpeta", str(r))
    api.abrir(src)
    r = api.guardar_proyecto_como()
    ok(r.get("ruta") and not r.get("error"), "«Guardar como…» abre el cuadro y guarda", str(r))
    try:
        os.remove(r["ruta"])
    except OSError:
        pass
    ok(len(v.pedidos) == 7, "se abrieron los 7 cuadros", str(len(v.pedidos)))
    api.cerrar()
    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
