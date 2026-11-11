# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Detectar en el video cambios de escena, tramos negros y tramos congelados, para poder cortar o sacar.

Igual que con los silencios: se analiza el video ORIGINAL de cada archivo que usa V1 (una pasada de ffmpeg por archivo, con
los tres detectores juntos) y lo hallado se lleva a la línea de tiempo EDITADA, clip por clip (con velocidad y reversa).
Analizar no cambia nada; cortar es Proyecto.dividir_varios y sacar tramos es Proyecto.borrar_rangos.
"""

import re
import subprocess

from motor import exportar as _ex
from motor import proxy as _proxy
from motor.proyecto import TOL
from motor.silencios import _a_linea, _unir

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ESCENA = re.compile(r"lavfi\.scd\.time:\s*(-?[\d.]+)")
_NEGRO_I = re.compile(r"black_start:\s*(-?[\d.]+)")
_NEGRO_F = re.compile(r"black_end:\s*(-?[\d.]+)")
_CONG_I = re.compile(r"lavfi\.freezedetect\.freeze_start:\s*(-?[\d.]+)")
_CONG_F = re.compile(r"lavfi\.freezedetect\.freeze_end:\s*(-?[\d.]+)")

QUE = ("escenas", "negros", "congelados")
UMBRAL_ESCENA = (1.0, 60.0)
NEGRO_MIN = (0.1, 10.0)
CONGELADO_MIN = (0.3, 30.0)
BORDE = 0.12           # un cambio a menos de esto del borde de un clip ya es un corte: no se repite


class ErrorEscena(ValueError):
    """Algo que no se puede analizar; el mensaje se le muestra a la persona."""


def _detectar(ruta, indice, que, umbral, negro_min, congelado_min, cancelar):
    """Un archivo: {'escenas': [t], 'negros': [(a, b|None)], 'congelados': [(a, b|None)]} en segundos de ffmpeg."""
    filtros = []
    if "escenas" in que:
        filtros.append("scdet=t=%.2f" % umbral)
    if "negros" in que:
        filtros.append("blackdetect=d=%.3f:pic_th=0.98:pix_th=0.10" % negro_min)
    if "congelados" in que:
        filtros.append("freezedetect=n=-60dB:d=%.3f" % congelado_min)
    cmd = [_proxy._ffmpeg(), "-nostdin", "-hide_banner", "-nostats", "-v", "info", "-protocol_whitelist", "file", "-i", ruta, "-map", "0:%d" % int(indice), "-an", "-sn", "-dn",
           "-vf", ",".join(filtros), "-f", "null", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
    out = {"escenas": [], "negros": [], "congelados": []}
    abierto = {"negros": None, "congelados": None}
    try:
        for linea in proc.stdout:
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                raise _proxy.Cancelado()
            m = _ESCENA.search(linea)
            if m:
                out["escenas"].append(float(m.group(1)))
                continue
            for clave, ini, fin in (("negros", _NEGRO_I, _NEGRO_F), ("congelados", _CONG_I, _CONG_F)):
                m = ini.search(linea)
                if m:
                    abierto[clave] = float(m.group(1))
                m = fin.search(linea)          # blackdetect escribe inicio, final y duracion en la MISMA linea
                if m and abierto[clave] is not None:
                    out[clave].append((abierto[clave], float(m.group(1))))
                    abierto[clave] = None
        proc.wait()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    if proc.returncode != 0:
        raise ErrorEscena("No pude analizar el video de ese archivo.")
    for clave, a in abierto.items():
        if a is not None:
            out[clave].append((a, None))
    return out


def analizar(p, que=QUE, umbral_escena=10.0, negro_min=0.3, congelado_min=1.0, cancelar=None):
    """Lo que hay en la línea de tiempo de V1. Devuelve {'escenas': [t], 'negros': [{inicio, fin}], 'congelados': [{inicio, fin}],
    'duracion'}, con los tiempos de la línea de tiempo EDITADA."""
    if not isinstance(que, (list, tuple)) or not que or any(x not in QUE for x in que):
        raise ErrorEscena("Se puede buscar: cambios de escena, tramos negros y tramos congelados.")
    for nombre, valor, (lo, hi) in (("La sensibilidad de escena", umbral_escena, UMBRAL_ESCENA), ("La duración mínima del negro", negro_min, NEGRO_MIN),
                                    ("La duración mínima de lo congelado", congelado_min, CONGELADO_MIN)):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not lo <= valor <= hi:
            raise ErrorEscena("%s va de %s a %s." % (nombre, str(lo).replace(".", ","), str(hi).replace(".", ",")))
    v1 = next((t for t in p.pistas if t["id"] == "V1"), None)
    if v1 is None or not v1["clips"]:
        raise ErrorEscena("Este proyecto no tiene video que analizar.")
    grupos = {}
    for c in v1["clips"]:
        grupos.setdefault(c["fuente"], []).append(c)
    puntos, negros, congelados = [], [], []
    for fid, clips in grupos.items():
        f = p.fuentes[fid]
        info = _proxy.sondear(f["ruta"])
        indice = (info.get("video") or {}).get("index", 0)
        crudo = _detectar(f["ruta"], indice, que, float(umbral_escena), float(negro_min), float(congelado_min), cancelar)
        off = _ex.desfase_de_fuente(f, info)
        for t in crudo["escenas"]:
            t -= off
            for c in clips:
                if c["desde"] + BORDE < t < c["hasta"] - BORDE:
                    puntos.append(p.a_linea(c, t))
        for clave, destino in (("negros", negros), ("congelados", congelados)):
            tramos = [(a - off, (f["duracion"] if b is None else b - off)) for a, b in crudo[clave]]
            destino += _a_linea(p, clips, tramos)
    cortes = []
    for t in sorted(puntos):
        if not cortes or t - cortes[-1] > 0.05:
            cortes.append(t)
    duracion = p.duracion()
    return {"escenas": [round(t, 3) for t in cortes if TOL < t < duracion - TOL],
            "negros": [{"inicio": round(a, 3), "fin": round(b, 3)} for a, b in _unir(negros) if b - a > 0.04],
            "congelados": [{"inicio": round(a, 3), "fin": round(b, 3)} for a, b in _unir(congelados) if b - a > 0.04],
            "duracion": duracion}
