# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Ayudas de las pruebas que necesitan voz: una voz de Windows (SAPI) dice un texto y se arma un video con ese audio.
Si falta la voz o whisper, las pruebas que la usan se saltean y lo dicen."""

import os
import subprocess

import prueba_exportar as ex


def sintetizar(ruta, texto):
    """Escribe `ruta` (.wav) con la voz de Windows diciendo `texto`. True si salio."""
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "try { $s.SelectVoice('Microsoft Pablo') } catch { }; $s.SetOutputToWaveFile('%s'); $s.Speak('%s'); $s.Dispose()" % (ruta, texto.replace("'", "''")))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0 and os.path.isfile(ruta)


def duracion(ruta):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta], capture_output=True, text=True).stdout)


def video_hablado(destino, textos, pausa=1.0, ancho=320, alto=180, fps=25):
    """Un video (testsrc2) cuyo audio es la voz diciendo cada texto, con `pausa` segundos de silencio entre uno y otro.
    Devuelve (ruta, [(inicio, fin) de cada texto en segundos]) o (None, None) si no hay voz."""
    voces, duraciones = [], []
    for i, t in enumerate(textos):
        r = os.path.join(ex.TMP, "voz-%s-%d.wav" % (os.path.basename(destino), i))
        if not sintetizar(r, t):
            return None, None
        voces.append(r)
        duraciones.append(duracion(r))
    n = len(voces)
    entradas, filtros, partes, tramos, t = [], [], [], [], 0.0
    for r in voces:                                        # entradas 1..n: las voces
        entradas += ["-i", r]
    for i in range(n - 1):                                 # entradas n+1..2n-1: los silencios
        entradas += ["-f", "lavfi", "-t", "%.2f" % pausa, "-i", "anullsrc=r=48000:cl=mono"]
    for i in range(n):
        filtros.append("[%d:a]aresample=48000,aformat=channel_layouts=mono[v%d]" % (i + 1, i))
        partes.append("[v%d]" % i)
        tramos.append((round(t, 2), round(t + duraciones[i], 2)))
        t += duraciones[i]
        if i < n - 1:
            filtros.append("[%d:a]aformat=channel_layouts=mono[p%d]" % (n + 1 + i, i))
            partes.append("[p%d]" % i)
            t += pausa
    total = t + 0.5
    filtro = ";".join(filtros) + ";" + "".join(partes) + "concat=n=%d:v=0:a=1[o]" % len(partes)
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=%dx%d:r=%d:d=%.2f,format=yuv420p" % (ancho, alto, fps, total), *entradas,
              "-filter_complex", filtro, "-map", "0:v", "-map", "[o]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", destino)
    return destino, tramos
