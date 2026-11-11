# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""El motor de Moviola."""
import os
import shutil

# Seguridad: en Windows, buscar un programa por su nombre mira PRIMERO la carpeta actual. Si Moviola arranca parada en una carpeta ajena
# (doble clic en un proyecto que vino en un zip con un «ffmpeg.exe» al lado), ejecutaria ese programa. Con esta variable, Windows y
# shutil.which dejan de mirar la carpeta actual; ademas `herramienta` nunca devuelve un nombre suelto (CreateProcess tambien la miraria).
os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"

_AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def herramienta(nombre):
    """Ruta COMPLETA de un programa externo (ffmpeg, ffprobe...) buscado en el PATH, nunca en la carpeta actual. Si no esta, devuelve la
    ruta donde deberia estar dentro del programa (bin\\nombre.exe): al ejecutarla falla con «no encontrado» en vez de buscar en otro lado."""
    ruta = shutil.which(nombre)
    if ruta and os.path.isabs(ruta):
        return ruta
    return os.path.join(_AQUI, "bin", nombre + (".exe" if os.name == "nt" else ""))


# FFmpeg solo puede abrir ARCHIVOS: un «video» que en realidad es una lista de reproduccion no puede hacerle pedir direcciones de internet.
SOLO_ARCHIVOS = ["-protocol_whitelist", "file"]
