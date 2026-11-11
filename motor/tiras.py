# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Tira de miniaturas de la timeline: una sola imagen, un solo ffmpeg."""

from __future__ import annotations

import os
import re
import subprocess
import sys

_BANDERAS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_CUADRO = re.compile(r"showinfo.* n:\s*(\d+)")


def tira(ruta: str, destino: str, duracion: float, cantidad: int = 120,
         alto: int = 90) -> dict:
    """Genera UNA imagen con las miniaturas en fila y devuelve sus medidas.

    {"archivo": destino, "cantidad": int, "ancho_mini": int, "alto_mini": int}

    `cantidad` es la cantidad REAL de miniaturas útiles que quedaron en la
    imagen, y `ancho_mini` el ancho exacto de cada una (medido con ffprobe
    sobre el archivo generado, no estimado).
    """
    if cantidad <= 0:
        raise ValueError("cantidad tiene que ser mayor que cero")
    if alto <= 0:
        raise ValueError("alto tiene que ser mayor que cero")
    if not os.path.isfile(ruta):
        raise FileNotFoundError(ruta)

    destino = os.path.abspath(destino)
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    duracion = float(duracion)
    if duracion <= 0:
        duracion = _duracion(ruta)
    if duracion <= 0:
        raise RuntimeError("no pude determinar la duración de %s" % ruta)

    fps = cantidad / duracion
    emitidos = _generar(ruta, destino, fps, alto, cantidad)
    reales = min(emitidos, cantidad)
    if reales <= 0:
        raise RuntimeError("ffmpeg no generó ninguna miniatura de %s" % ruta)

    if reales < cantidad:
        # El filtro fps no llegó a la cantidad pedida y `tile` habría dejado
        # celdas negras al final: rehacemos la grilla con los cuadros que hay
        # para que ancho_mini * cantidad sea exactamente el ancho de la imagen.
        _generar(ruta, destino, fps, alto, reales)

    ancho_total, alto_total = _medidas(destino)
    if ancho_total % reales:
        # No debería pasar (tile hace celdas iguales); si pasa, lo cantamos.
        raise RuntimeError(
            "el ancho %d no es múltiplo de %d miniaturas" % (ancho_total, reales))

    return {
        "archivo": destino,
        "cantidad": reales,
        "ancho_mini": ancho_total // reales,
        "alto_mini": alto_total,
    }


def _generar(ruta: str, destino: str, fps: float, alto: int, celdas: int) -> int:
    """Corre el único ffmpeg y devuelve cuántos cuadros entraron a `tile`."""
    filtros = "fps=%.9f,scale=-2:%d,showinfo,tile=%dx1" % (fps, alto, celdas)
    orden = [
        "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-v", "info", "-y",
        "-protocol_whitelist", "file", "-i", ruta,
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", filtros,
        "-frames:v", "1",
        destino,
    ]
    proceso = subprocess.run(
        orden,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=_BANDERAS,
    )
    registro = proceso.stderr.decode("utf-8", "replace")
    if proceso.returncode != 0 or not os.path.isfile(destino):
        raise RuntimeError("ffmpeg falló con %s: %s" % (ruta, registro.strip()[-400:]))
    # showinfo imprime una línea por cuadro: así sabemos qué salió de verdad
    # del filtro fps en vez de confiar en cantidad/duracion.
    return len(_CUADRO.findall(registro))


def _medidas(imagen: str) -> tuple:
    orden = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", imagen,
    ]
    proceso = subprocess.run(
        orden,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_BANDERAS,
    )
    texto = proceso.stdout.decode("utf-8", "replace").strip().split("\n")[0]
    partes = texto.split("x")
    if proceso.returncode != 0 or len(partes) < 2:
        raise RuntimeError("no pude medir %s" % imagen)
    return int(partes[0]), int(partes[1])


def _duracion(ruta: str) -> float:
    orden = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", ruta,
    ]
    proceso = subprocess.run(
        orden,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_BANDERAS,
    )
    try:
        return float(proceso.stdout.decode("utf-8", "replace").strip())
    except ValueError:
        return 0.0
