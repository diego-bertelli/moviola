# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Detectar silencios en el audio de un proyecto, para poder cortarlos.

Se analiza el audio ORIGINAL de cada archivo que usa la pista A1 (una sola pasada de ffmpeg por archivo) y
los silencios se llevan a la línea de tiempo EDITADA, clip por clip: así el resultado cae en el lugar correcto
aunque ya se hayan hecho cortes. No se analiza el efecto del volumen ni de los efectos de audio: es el sonido
de la fuente. Cortar los silencios es borrar esos tramos cerrando el hueco (Proyecto.borrar_rangos), o sea que
video, audio y todas las pistas quedan sincronizados.
"""

import re
import subprocess

from motor import exportar as _ex
from motor import proxy as _proxy
from motor.proyecto import TOL

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_INICIO = re.compile(r"silence_start:\s*(-?[\d.]+)")
_FIN = re.compile(r"silence_end:\s*(-?[\d.]+)")

UMBRAL_DB = (-80.0, -5.0)
DURACION_MIN = (0.1, 10.0)
MARGEN = (0.0, 2.0)


class ErrorSilencio(ValueError):
    """Algo que no se puede analizar; el mensaje se le muestra a la persona."""


def detectar(ruta, pista_audio, umbral_db, duracion_min, cancelar=None):
    """Silencios de UN archivo: lista de (inicio, fin) en segundos de ffmpeg (desde el inicio del contenedor).
    `fin` es None si el archivo termina en silencio."""
    cmd = [_proxy._ffmpeg(), "-nostdin", "-hide_banner", "-nostats", "-v", "info", "-protocol_whitelist", "file", "-i", ruta,
           "-map", "0:a:%d" % int(pista_audio), "-vn", "-sn", "-dn",
           "-af", "silencedetect=noise=%.1fdB:d=%.3f" % (umbral_db, duracion_min), "-f", "null", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", creationflags=_SIN_VENTANA)
    tramos, abierto = [], None
    try:
        for linea in proc.stdout:
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                raise _proxy.Cancelado()
            m = _INICIO.search(linea)
            if m:
                abierto = float(m.group(1))
                continue
            m = _FIN.search(linea)
            if m and abierto is not None:
                tramos.append((abierto, float(m.group(1))))
                abierto = None
        proc.wait()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    if proc.returncode != 0:
        raise ErrorSilencio("No pude analizar el audio de ese archivo.")
    if abierto is not None:
        tramos.append((abierto, None))
    return tramos


def _a_linea(p, clips, tramos_fuente):
    """Lleva tramos de la FUENTE (segundos de la fuente) a la línea de tiempo, clip por clip."""
    out = []
    for c in clips:
        for a, b in tramos_fuente:
            lo, hi = max(a, c["desde"]), min(b, c["hasta"])
            if hi - lo > 1e-3:
                # con velocidad distinta de 1 o en reversa, la fuente se recorre a otro ritmo (o al reves)
                x, y = p.a_linea(c, lo), p.a_linea(c, hi)
                out.append((min(x, y), max(x, y)))
    return out


def _unir(tramos):
    """Ordena y junta los tramos que se tocan (un silencio que cruza un corte es uno solo)."""
    out = []
    for a, b in sorted(tramos):
        if out and a <= out[-1][1] + TOL:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def analizar(p, umbral_db=-35.0, duracion_min=0.5, margen=0.1, cancelar=None):
    """Silencios de la línea de tiempo del proyecto `p`.

    umbral_db: por debajo de este nivel es silencio. duracion_min: un silencio más corto no cuenta.
    margen: segundos de silencio que se DEJAN a cada lado (para no comer el principio ni el final de una palabra).
    Devuelve {"silencios": [{"inicio", "fin"}], "total": segundos que se sacarían, "duracion": de la línea de tiempo}.
    """
    for nombre, valor, (lo, hi) in (("El nivel", umbral_db, UMBRAL_DB), ("La duración mínima", duracion_min, DURACION_MIN),
                                    ("El margen", margen, MARGEN)):
        if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not lo <= valor <= hi:
            raise ErrorSilencio("%s va de %s a %s." % (nombre, str(lo).replace(".", ","), str(hi).replace(".", ",")))
    a1 = next((t for t in p.pistas if t["id"] == "A1"), None)
    if a1 is None or not a1["clips"]:
        raise ErrorSilencio("Este proyecto no tiene audio que analizar.")

    # un archivo (y una pista de audio) por vez, aunque tenga muchos clips
    grupos = {}
    for c in a1["clips"]:
        grupos.setdefault((c["fuente"], c.get("pista_audio") or 0), []).append(c)
    todos = []
    for (fid, pista), clips in grupos.items():
        f = p.fuentes[fid]
        crudo = detectar(f["ruta"], pista, umbral_db, duracion_min, cancelar)
        off = _ex.desfase_de_fuente(f, _proxy.sondear(f["ruta"]))
        en_fuente = [(a - off, (f["duracion"] if b is None else b - off)) for a, b in crudo]
        todos += _a_linea(p, clips, en_fuente)

    final = []
    for a, b in _unir(todos):
        if b - a < duracion_min - 1e-3:        # recortado por un corte, ya no llega a la duracion minima
            continue
        a, b = a + margen, b - margen
        if b - a > 0.05:
            final.append((round(a, 3), round(b, 3)))
    return {"silencios": [{"inicio": a, "fin": b} for a, b in final],
            "total": round(sum(b - a for a, b in final), 3), "duracion": p.duracion()}
