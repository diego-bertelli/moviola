# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Un yt-dlp DE MENTIRA para las pruebas: no toca internet. Habla como el verdadero (opciones, lineas de progreso, --print after_move:filepath).

El id del video decide que pasa:  priv0000001 -> video privado, edad0000001 -> pide iniciar sesion, caido000001 -> sin conexion,
cuelga00001 -> tarda mucho (para probar Cancelar), cualquier otro -> baja un video de prueba de 2 s.
Guarda los argumentos que recibio en el archivo que diga la variable FALSO_YTDLP_REGISTRO.
"""

import json
import os
import subprocess
import sys
import time


def main():
    args = sys.argv[1:]
    reg = os.environ.get("FALSO_YTDLP_REGISTRO")
    if reg:
        with open(reg, "a", encoding="utf-8") as f:
            f.write(json.dumps(args) + "\n")
    url = args[-1]
    vid = url.rsplit("=", 1)[-1]
    if vid == "priv0000001":
        print("ERROR: [youtube] priv0000001: Private video. Sign in if you've been granted access to this video")
        return 1
    if vid == "edad0000001":
        print("ERROR: [youtube] edad0000001: Sign in to confirm your age. This video may be inappropriate for some users.")
        return 1
    if vid == "caido000001":
        print("ERROR: [youtube] caido000001: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>")
        return 1
    plantilla = args[args.index("-o") + 1]
    audio = "-x" in args
    carpeta = os.path.dirname(plantilla)
    destino = plantilla.replace("%(title).120B", "Video de prueba").replace("%(id)s", vid).replace("%(ext)s", "mp3" if audio else "mp4")
    for i in range(0, 101, 20):
        print("[download]  %5.1f%% of 1.00MiB at 1.00MiB/s ETA 00:00" % i, flush=True)
        time.sleep(0.15)
        if vid == "cuelga00001":
            time.sleep(60)
    if os.path.exists(destino):
        base, ext = os.path.splitext(destino)
        destino = base + " (2)" + ext
    if audio:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=2", destino], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", destino], check=True)
    print(destino)
    return 0


if __name__ == "__main__":
    sys.exit(main())
