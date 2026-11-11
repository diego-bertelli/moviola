# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Bajar un video de YouTube para editarlo (con `yt-dlp`).

Lo que hace y lo que NO hace:
- Usa el `yt-dlp` que YA esté instalado en la computadora (en el PATH, en la carpeta `bin` del programa o donde lo deja WinGet).
  Moviola no lo descarga ni lo instala: si falta, lo dice y explica cómo conseguirlo.
- Solo acepta direcciones de YouTube (youtube.com y youtu.be), de UN video (no listas), y siempre pide confirmar que se tiene derecho a usarlo.
- NO saltea nada: no usa cookies, no cambia de país, no esquiva bloqueos ni protecciones. Si YouTube no deja bajar un video, el error se muestra tal cual
  (en palabras de una persona) y listo.
- Se baja SIEMPRE a una carpeta propia y nunca se pisa un archivo: el video bajado es un archivo más, que se abre como cualquier otro.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
CALIDADES = {
    "mejor": ("Lo mejor disponible", "bv*+ba/b"),
    "1080": ("Hasta 1080p", "bv*[height<=1080]+ba/b[height<=1080]/b"),
    "720": ("Hasta 720p", "bv*[height<=720]+ba/b[height<=720]/b"),
    "480": ("Hasta 480p", "bv*[height<=480]+ba/b[height<=480]/b"),
    "audio": ("Solo el audio (MP3)", "ba/b"),
}
_PROGRESO = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class ErrorDescarga(ValueError):
    """Algo que no se puede bajar; el mensaje se le muestra a la persona."""


def buscar_ytdlp():
    """Ruta del yt-dlp instalado, o None. MOVIOLA_YTDLP (solo para las pruebas) manda sobre todo lo demás."""
    env = os.environ.get("MOVIOLA_YTDLP")
    if env:
        return env if os.path.isfile(env) else None
    ruta = shutil.which("yt-dlp")
    if ruta and os.path.isabs(ruta):
        return ruta
    aqui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidatos = [os.path.join(aqui, "bin", "yt-dlp.exe")]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        base = os.path.join(local, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                if d.lower().startswith("yt-dlp.yt-dlp"):
                    candidatos.append(os.path.join(base, d, "yt-dlp.exe"))
    return next((c for c in candidatos if os.path.isfile(c)), None)


def estado():
    r = buscar_ytdlp()
    return {"disponible": bool(r), "motivo": "" if r else
            "Para bajar videos de YouTube hace falta tener instalado yt-dlp. Moviola no lo descarga por su cuenta: lo instala su instalador (Instalar-Moviola.bat) o, en PowerShell, "
            "«winget install yt-dlp.yt-dlp», cerrá y volvé a abrir Moviola."}


def validar_url(url):
    """La dirección limpia de UN video de YouTube, o ErrorDescarga con una frase clara."""
    if not isinstance(url, str) or not url.strip():
        raise ErrorDescarga("Pegá la dirección del video de YouTube.")
    url = url.strip()
    if len(url) > 300 or any(ord(c) < 32 for c in url) or " " in url:
        raise ErrorDescarga("Esa dirección no es válida.")
    if "://" not in url:
        url = "https://" + url
    p = urlsplit(url)
    if p.scheme != "https" or (p.hostname or "").lower() not in HOSTS or p.username or p.password:
        raise ErrorDescarga("Solo se pueden bajar videos de YouTube (youtube.com o youtu.be), con una dirección que empiece con https.")
    host = p.hostname.lower()
    q = parse_qs(p.query)
    if host.endswith("youtu.be"):
        vid = p.path.strip("/").split("/")[0]
    elif p.path == "/watch":
        vid = (q.get("v") or [""])[0]
    elif p.path.startswith(("/shorts/", "/live/", "/embed/")):
        vid = p.path.split("/")[2] if len(p.path.split("/")) > 2 else ""
    elif p.path == "/playlist":
        raise ErrorDescarga("Esa dirección es una lista de reproducción. Pegá la de un video en particular.")
    else:
        raise ErrorDescarga("No reconozco esa dirección como la de un video de YouTube.")
    if not _ID.match(vid or ""):
        raise ErrorDescarga("No encuentro el video en esa dirección.")
    return "https://www.youtube.com/watch?v=" + vid           # sin lista, sin tiempos ni rastreo: solo el video


def carpeta_por_defecto():
    base = os.path.join(os.path.expanduser("~"), "Videos")
    if not os.path.isdir(base):
        base = os.path.expanduser("~")
    return os.path.join(base, "Moviola descargas")


# lo que dice yt-dlp, dicho para una persona (lo desconocido se muestra cortado y sin rastros tecnicos)
_EXPLICACIONES = (
    ("private video", "Ese video es privado: no se puede bajar."),
    ("sign in to confirm your age", "Ese video exige iniciar sesión (restricción de edad): no se puede bajar desde acá."),
    ("members-only", "Ese video es solo para miembros del canal: no se puede bajar."),
    ("video unavailable", "Ese video no está disponible."),
    ("this video is not available", "Ese video no está disponible (puede estar bloqueado en tu país)."),
    ("not available in your country", "Ese video está bloqueado en tu país."),
    ("copyright", "YouTube no permite bajar ese video por derechos de autor."),
    ("drm", "Ese video está protegido (DRM): no se puede bajar."),
    ("http error 429", "YouTube pidió esperar un rato (demasiados pedidos). Probá de nuevo en unos minutos."),
    ("unable to download webpage", "No pude conectarme a YouTube. Revisá tu conexión a internet."),
    ("getaddrinfo failed", "No pude conectarme a YouTube. Revisá tu conexión a internet."),
    ("live event will begin", "Esa transmisión en vivo todavía no empezó."),
    ("is live", "Esa transmisión está en vivo: esperá a que termine."),
)


def explicar(texto):
    bajo = (texto or "").lower()
    for clave, frase in _EXPLICACIONES:
        if clave in bajo:
            return frase
    linea = next((x for x in reversed((texto or "").splitlines()) if x.strip()), "")
    linea = re.sub(r"^ERROR:\s*(\[[^\]]*\]\s*)?([\w-]{11}:\s*)?", "", linea.strip())
    return "No se pudo bajar el video. " + (linea[:160] if linea else "YouTube no lo permitió.")


def _borrar_restos(carpeta, url):
    """Los pedazos (.part, .ytdl) que deja yt-dlp cuando se corta una descarga de ESTE video."""
    import glob
    vid = url.rsplit("=", 1)[-1]
    for ruta in glob.glob(os.path.join(glob.escape(carpeta), "*[[]%s[]]*" % glob.escape(vid))):
        if ruta.endswith((".part", ".ytdl")) or ".part-" in os.path.basename(ruta):
            try:
                os.remove(ruta)
            except OSError:
                pass


def descargar(url, carpeta, calidad="1080", cancelar=None, avisar=None):
    """Baja el video y devuelve {'archivo', 'nombre'}. Corre yt-dlp; el progreso (0 a 1) llega a `avisar`; `cancelar` es un threading.Event."""
    from motor import proxy as _proxy

    exe = buscar_ytdlp()
    if not exe:
        raise ErrorDescarga(estado()["motivo"])
    limpia = validar_url(url)
    if calidad not in CALIDADES:
        raise ErrorDescarga("Esa calidad no está en la lista.")
    if not carpeta or not os.path.isdir(carpeta):
        try:
            os.makedirs(carpeta, exist_ok=True)
        except (OSError, TypeError):
            raise ErrorDescarga("No pude crear la carpeta de descargas.")
    ffmpeg = _proxy._ffmpeg()
    plantilla = os.path.join(carpeta, "%(title).120B [%(id)s].%(ext)s")
    cmd = ([sys.executable, exe] if exe.lower().endswith(".py") else [exe]) + [
        "--ignore-config", "--no-playlist", "--no-mtime", "--no-overwrites", "--windows-filenames", "--newline", "--no-colors",
        "--ffmpeg-location", os.path.dirname(ffmpeg) if os.path.dirname(ffmpeg) else ffmpeg,
        "-f", CALIDADES[calidad][1], "-o", plantilla, "--print", "after_move:filepath", "--no-simulate"]
    cmd += (["-x", "--audio-format", "mp3", "--audio-quality", "0"] if calidad == "audio" else ["--merge-output-format", "mp4"])
    cmd += ["--", limpia]                                       # el "--" evita que una direccion se tome por una opcion
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
    cola, archivo = [], None
    terminado = threading.Event()

    def vigilar():
        # yt-dlp puede quedarse un rato sin escribir nada (red lenta): cancelar no puede esperar a la proxima linea
        while not terminado.is_set():
            if cancelar is not None and cancelar.wait(0.2):
                if proc.poll() is None:
                    proc.kill()
                return

    if cancelar is not None:
        threading.Thread(target=vigilar, daemon=True).start()
    try:
        for linea in proc.stdout:
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                raise _proxy.Cancelado()
            linea = linea.rstrip()
            m = _PROGRESO.search(linea)
            if m:
                if avisar:
                    avisar(min(0.99, float(m.group(1)) / 100.0))
                continue
            if linea and os.path.isabs(linea) and os.path.isfile(linea):
                archivo = linea                                  # la linea que imprime --print after_move:filepath
                continue
            if linea:
                cola.append(linea)
                cola = cola[-12:]
        proc.wait()
        if cancelar is not None and cancelar.is_set():
            raise _proxy.Cancelado()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        _borrar_restos(carpeta, limpia)
        raise
    finally:
        terminado.set()
    if proc.returncode != 0 or not archivo:
        raise ErrorDescarga(explicar("\n".join(cola)))
    if avisar:
        avisar(1.0)
    return {"archivo": archivo, "nombre": os.path.basename(archivo)}
