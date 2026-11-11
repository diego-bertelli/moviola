# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Datos del espectro de audio para dibujar abajo de la timeline.

Un solo proceso ffmpeg por llamada: escupe PCM crudo por stdout y el
agrupado en tramos lo hace Python (arrancar ffmpeg cuesta 70 ms).
"""

from __future__ import annotations

import array
import os
import subprocess
import sys

FRECUENCIA = 8000  # Hz mono: alcanza para dibujar picos y deja el PCM chico
ESCALA = 32768.0  # s16 con signo -> -1,0..1,0

# En Windows evita que cada subproceso abra una consola negra.
_BANDERAS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def picos(ruta: str, n: int = 2000) -> dict:
    """Devuelve {"picos": [[min, max], ...], "sin_audio": bool}.

    `n` es la cantidad de tramos pedidos. Si el audio tiene menos muestras
    que `n`, devuelve un tramo por muestra en vez de fallar.
    Si el archivo no tiene pista de audio: {"picos": [], "sin_audio": True}.
    """
    if n <= 0:
        raise ValueError("n tiene que ser mayor que cero")
    if not os.path.isfile(ruta):
        raise FileNotFoundError(ruta)

    orden = [
        "ffmpeg", "-nostdin", "-hide_banner", "-v", "error",
        "-protocol_whitelist", "file", "-i", ruta,
        "-vn", "-sn", "-dn",
        "-ac", "1", "-ar", str(FRECUENCIA),
        "-f", "s16le", "-",
    ]
    proceso = subprocess.run(
        orden,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_BANDERAS,
    )
    crudo = proceso.stdout

    if not crudo:
        # Un video mudo hace fallar la salida s16le (no hay stream que mapear).
        # Recién acá gastamos un ffprobe para distinguir "mudo" de "roto".
        if _sin_pista_audio(ruta):
            return {"picos": [], "sin_audio": True}
        detalle = proceso.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError("ffmpeg no devolvió audio de %s: %s" % (ruta, detalle[-400:]))

    muestras = array.array("h")  # s16 nativo: 2 bytes con signo
    muestras.frombytes(crudo[: len(crudo) - len(crudo) % 2])
    if sys.byteorder == "big":
        muestras.byteswap()  # el PCM de ffmpeg viene little-endian

    total = len(muestras)
    tramos = min(n, total)
    salida = []
    for i in range(tramos):
        # Bordes con enteros: reparte el resto sin acumular error de redondeo.
        ini = total * i // tramos
        fin = total * (i + 1) // tramos
        trozo = muestras[ini:fin]
        salida.append([min(trozo) / ESCALA, max(trozo) / ESCALA])

    return {"picos": salida, "sin_audio": False}


def _sin_pista_audio(ruta: str) -> bool:
    orden = [
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", ruta,
    ]
    proceso = subprocess.run(
        orden,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_BANDERAS,
    )
    return proceso.returncode == 0 and not proceso.stdout.strip()
