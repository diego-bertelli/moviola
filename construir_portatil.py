# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Arma la version PORTATIL del editor: una carpeta que anda en otra PC con Windows sin instalar nada,
sin permisos de administrador y sin internet.

Uso (con el Python con el que se desarrolla el editor):

    python construir_portatil.py                 crea dist\\Moviola-portatil\\
    python construir_portatil.py --destino X     otra carpeta (tiene que estar DENTRO de esta)
    python construir_portatil.py --sin-ffmpeg    sin ffmpeg.exe (si la otra PC ya lo tiene en el PATH)

Que hace:  COPIA (no descarga nada)
  python\\    el Python con el que corre esto, sin pruebas ni documentacion, mas solo las bibliotecas que la app usa
  bin\\       ffmpeg.exe y ffprobe.exe (los que estan en el PATH de esta PC)
  app.py, motor\\, web\\
  licencias\\ las licencias de todo lo que se incluye, y un texto que explica que implican
  Moviola.bat, Moviola-consola.bat, Moviola-navegador.bat, LEEME.txt

El Python copiado queda AISLADO (python313._pth): no mira PYTHONPATH, ni el Python de la otra PC, ni sus paquetes.
"""

import argparse
import importlib.metadata as md
import os
import re
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
MARCA = ".moviola-portatil"           # dentro de lo que arma este script: solo se borra una carpeta que tenga esta marca
PAQUETES_RAIZ = ("av", "pillow", "pywebview")

# Que NO se copia de la biblioteca estandar (pesan y la app no los usa)
SIN_COPIAR_LIB = {"test", "idlelib", "turtledemo", "lib2to3", "ensurepip", "site-packages", "__pycache__", "venv", "pydoc_data"}


try:
    from packaging.markers import Marker
except ImportError:                                  # pip trae su propia copia
    from pip._vendor.packaging.markers import Marker


def marker_texto(m):
    return m


def nombre_normal(n):
    return re.sub(r"[-_.]+", "-", n).lower()


def cierre_de_paquetes():
    """Los paquetes instalados que hacen falta para PAQUETES_RAIZ (con lo que ellos piden, y lo que piden esos...)."""
    por_nombre = {nombre_normal(d.metadata["Name"]): d for d in md.distributions() if d.metadata["Name"]}
    pendientes = list(PAQUETES_RAIZ)
    listos = {}
    while pendientes:
        n = nombre_normal(pendientes.pop())
        if n in listos:
            continue
        d = por_nombre.get(n)
        if d is None:
            raise SystemExit("Falta el paquete '%s' en este Python: no puedo armar la version portatil." % n)
        listos[n] = d
        for req in d.requires or []:
            m = re.match(r"\s*([A-Za-z0-9_.-]+)", req)
            if not m:
                continue
            if ";" in req:                      # marcadores (version de Python, plataforma, extras): se evaluan de verdad
                marcador = req.split(";", 1)[1].strip()
                try:
                    if not Marker(marker_texto(marcador)).evaluate({"extra": ""}):
                        continue
                except Exception:
                    if "extra" in marcador:
                        continue
            pendientes.append(m.group(1))
    return listos


def copiar_arbol(origen, destino, excluir_nombres=(), excluir_extensiones=()):
    cantidad = 0
    for raiz, carpetas, archivos in os.walk(origen):
        carpetas[:] = [c for c in carpetas if c not in excluir_nombres and c != "__pycache__"]
        rel = os.path.relpath(raiz, origen)
        os.makedirs(os.path.join(destino, rel), exist_ok=True)
        for a in archivos:
            if os.path.splitext(a)[1].lower() in excluir_extensiones:
                continue
            shutil.copy2(os.path.join(raiz, a), os.path.join(destino, rel, a))
            cantidad += 1
    return cantidad


def copiar_python(dest_python, dest_lic):
    base = sys.base_prefix
    os.makedirs(dest_python, exist_ok=True)
    # el ejecutable, sus DLL y el runtime de C
    for f in os.listdir(base):
        ruta = os.path.join(base, f)
        if os.path.isfile(ruta) and f.lower().endswith((".exe", ".dll")) and f.lower() not in ("uninstall.exe",):
            if f.lower() in ("pythonw.exe", "python.exe") or f.lower().startswith(("python3", "vcruntime", "msvcp", "concrt", "ucrtbase")):
                shutil.copy2(ruta, os.path.join(dest_python, f))
    copiar_arbol(os.path.join(base, "DLLs"), os.path.join(dest_python, "DLLs"), excluir_extensiones=(".lib", ".pdb"))
    copiar_arbol(os.path.join(base, "Lib"), os.path.join(dest_python, "Lib"), excluir_nombres=SIN_COPIAR_LIB)
    if os.path.isdir(os.path.join(base, "tcl")):                       # tkinter: el selector de carpetas del modo navegador
        copiar_arbol(os.path.join(base, "tcl"), os.path.join(dest_python, "tcl"))
    if os.path.isfile(os.path.join(base, "LICENSE.txt")):
        shutil.copy2(os.path.join(base, "LICENSE.txt"), os.path.join(dest_lic, "Python-LICENSE.txt"))

    # paquetes: solo los archivos que declara cada paquete en su RECORD
    sp_origen = None
    for p in sys.path:
        if p.endswith("site-packages") and os.path.isdir(p):
            sp_origen = p
            break
    sp_destino = os.path.join(dest_python, "Lib", "site-packages")
    os.makedirs(sp_destino, exist_ok=True)
    paquetes = cierre_de_paquetes()
    for n, d in sorted(paquetes.items()):
        copiados = 0
        for f in d.files or []:
            rel = str(f)
            if rel.startswith("..") or "__pycache__" in rel or rel.endswith((".pyc", ".pdb", ".lib")):
                continue
            origen = d.locate_file(f)
            if not os.path.isfile(origen):
                continue
            destino = os.path.join(sp_destino, rel)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy2(origen, destino)
            copiados += 1
            # licencias de cada paquete (estan dentro de su .dist-info)
            partes = rel.replace("\\", "/").split("/")
            if len(partes) >= 2 and partes[0].endswith(".dist-info") and re.search(r"(licen[sc]e|copying|notice|authors)", partes[-1], re.I):
                nombre_lic = "%s-%s" % (n, partes[-1])
                os.makedirs(dest_lic, exist_ok=True)
                shutil.copy2(origen, os.path.join(dest_lic, nombre_lic))
        print("  paquete %-14s %-10s %5d archivos" % (n, d.version, copiados))

    # aislado: ni PYTHONPATH ni el Python de la otra PC ni sus paquetes; el programa esta en la carpeta de arriba
    version = "%d%d" % sys.version_info[:2]
    with open(os.path.join(dest_python, "python%s._pth" % version), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("python%s.zip\nDLLs\nLib\nLib\\site-packages\n..\nimport site\n" % version)


LEEME = """MOVIOLA - editor de video y audio, local
=========================================

Todo corre en tu PC: no usa internet, no pide cuenta, no sube nada.

PARA ARRANCAR
  Doble clic en  Moviola.bat
  No hace falta instalar nada ni ser administrador.

  Si algo no arranca: Moviola-consola.bat muestra el error en una consola.
  Para procesar muchos videos sin ventana (por ejemplo, un reel con subtitulos de toda una carpeta):
  Moviola-comandos.bat procesar "C:\\mis videos" --preset reel   (ver "moviola.py presets" y README.md).
  Si la ventana no abre (Windows sin WebView2): Moviola-navegador.bat lo abre en tu navegador;
  al cerrar la pestana, el programa se apaga.

REQUISITOS
  Windows 10 u 11 de 64 bits. Windows 11 ya trae lo necesario (WebView2); en algunos Windows 10 el
  programa se abre solo en el navegador.

QUE HACE
  Abrir casi cualquier video o audio (o varios videos en un mismo proyecto), avanzar cuadro por cuadro, cortar,
  borrar tramos, fundidos, volumen, velocidad (de 1/4x a 4x), al reves, transiciones, efectos de color, imagen y
  audio, logo o texto encima, quitar fondo verde, zoom lento, musica que baja sola cuando alguien habla,
  cortar silencios, buscar escenas y tramos negros, y subtitulos (transcribir, corregir, quemar o guardar .srt).
  Un preset («Reel en un clic») corta silencios, subtitula, nivela el volumen y exporta de una vez, a un video o a muchos.
  Editar por texto: borrar palabras, muletillas y pausas desde la transcripcion (subtitulos karaoke incluidos). En la linea de
  tiempo se arrastran clips, se tira de los bordes para recortar y se hace zoom con Ctrl + rueda.
  Se guarda como proyecto (.moviola) y exporta: MP4 (H.264, H.265, AV1), WebM, MOV ProRes, MKV, GIF, en video
  original, vertical 9:16, horizontal 16:9 o cuadrado 1:1; o solo audio (WAV, MP3, FLAC, M4A, Opus, OGG).

  Para transcribir subtitulos hace falta tener instalado whisper (whisper-cli y un modelo ggml-*.bin); Moviola no
  descarga nada. Para bajar un video de YouTube hace falta tener instalado yt-dlp (winget install yt-dlp.yt-dlp).
  Sin ellos todo lo demas anda igual.

ATAJOS
  Espacio reproducir/pausar   Flechas cuadro a cuadro   Shift+Flechas un segundo   Inicio/Fin extremos
  I / O marcar entrada/salida   S cortar   Supr borrar   Ctrl+Z deshacer   Ctrl+Y rehacer
  Ctrl+S guardar el proyecto   Ctrl+E exportar

TUS ARCHIVOS
  El programa nunca modifica tus videos: exporta siempre un archivo nuevo (nombre-v1, nombre-v2...).
  Guarda sus ajustes, un registro (editor.log) y copias livianas para reproducir en esta carpeta; si no
  se puede escribir aca, usa %LOCALAPPDATA%\\Moviola. Se puede borrar la carpeta "cache" cuando quieras.

LICENCIAS
  Moviola es software libre (GNU GPL v3 o posterior): archivos LICENSE, LICENCIA.md y AUTHORS. Se puede usar y
  compartir libremente, pero quien lo reparta tiene que mantener esas licencias y la carpeta "licencias", y ofrecer
  el codigo fuente de FFmpeg (ver licencias\\LEEME-LICENCIAS.txt y LICENCIA.md).
"""

LEEME_LICENCIAS = """LICENCIAS DE LO QUE VIENE EN ESTA CARPETA
=========================================

Esta carpeta junta programas de terceros. Cada uno conserva su licencia, copiada en esta misma carpeta.

  FFmpeg (bin\\ffmpeg.exe, ffprobe.exe)  GPL v3 (compilacion "full" de gyan.dev, con x264 y x265). Texto: FFmpeg-LICENSE.
                               Codigo fuente: https://ffmpeg.org/download.html y https://www.gyan.dev/ffmpeg/builds/
  PyAV (paquete "av")          BSD (el codigo de PyAV). Su paquete trae ademas bibliotecas de FFmpeg 9 (carpeta
                               python\\Lib\\site-packages\\av.libs) con libx264 y libx265 (GPL), libvpx, libopus, libwebp,
                               dav1d y SVT-AV1 (BSD). Fuentes: https://github.com/PyAV-Org/PyAV y
                               https://github.com/PyAV-Org/pyav-ffmpeg
  Python                       PSF License. Texto: Python-LICENSE.txt
  pywebview                    BSD
  Pillow                       MIT-CMU (HPND)
  pythonnet, clr_loader        MIT
  bottle, proxy_tools, cffi, pycparser   MIT / BSD

QUE SIGNIFICA PARA VOS
  * Usar el programa en tu trabajo o en tu casa: sin restricciones.
  * Copiarlo y compartirlo gratis con otras personas: permitido, siempre que la carpeta "licencias" viaje con el
    programa.
  * La GPL de FFmpeg pide que quien reparta el programa tambien ofrezca el codigo fuente de esa version de
    FFmpeg. Alcanza con dejar escrito, junto al programa, el enlace de arriba y el numero de version
    (se ve ejecutando  bin\\ffmpeg.exe -version).
  * El codigo de Moviola (app.py, motor\\, web\\) es software libre: GNU GPL version 3 o posterior
    (archivo LICENSE en la carpeta de arriba). Autores: Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5). Las
    aclaraciones (autoria, marca, patentes, que hacer si lo repartis) estan en LICENCIA.md.
  * "Moviola" es tambien el nombre historico de una marca de mesas de montaje de cine. Para uso interno y para
    compartirlo gratis no suele haber problema; antes de venderlo o publicarlo con ese nombre conviene una busqueda
    formal de marcas.
  * Algunos codecs (H.264, H.265, AAC) tienen patentes en algunos paises; para uso interno suele no importar,
    para vender un producto si.
"""

BAT = {
    "Moviola.bat": '@echo off\r\ncd /d "%~dp0"\r\nif exist ultimo-error.log del ultimo-error.log\r\nstart "" "%~dp0python\\pythonw.exe" "%~dp0app.py" %*\r\n',
    "Moviola-navegador.bat": '@echo off\r\ncd /d "%~dp0"\r\nif exist ultimo-error.log del ultimo-error.log\r\nstart "" "%~dp0python\\pythonw.exe" "%~dp0app.py" --navegador %*\r\n',
    "Moviola-comandos.bat": ('@echo off\r\ncd /d "%~dp0"\r\nif "%~1"=="" (\r\n  "%~dp0python\\python.exe" "%~dp0moviola.py" --help\r\n  echo.\r\n'
                             '  echo Ejemplo:  Moviola-comandos.bat procesar "C:\\mis videos" --preset reel\r\n  pause\r\n) else (\r\n'
                             '  "%~dp0python\\python.exe" "%~dp0moviola.py" %*\r\n)\r\n'),
    "Moviola-consola.bat": '@echo off\r\ncd /d "%~dp0"\r\necho Arrancando con consola. Cerra esta ventana para cortar la app.\r\n"%~dp0python\\python.exe" "%~dp0app.py" --debug %*\r\necho.\r\necho La app termino con codigo %errorlevel%.\r\npause\r\n',
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default=os.path.join(AQUI, "dist", "Moviola-portatil"))
    ap.add_argument("--sin-ffmpeg", action="store_true")
    a = ap.parse_args()

    destino = os.path.abspath(a.destino)
    if os.path.commonpath([destino, AQUI]) != AQUI or destino == AQUI:
        raise SystemExit("El destino tiene que estar DENTRO de %s (y no ser esa carpeta)." % AQUI)
    if os.path.exists(destino):
        if not os.path.isfile(os.path.join(destino, MARCA)):
            raise SystemExit("%s ya existe y no lo armo este script: no lo toco." % destino)
        shutil.rmtree(destino)
    os.makedirs(destino)
    with open(os.path.join(destino, MARCA), "w") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    lic = os.path.join(destino, "licencias")
    os.makedirs(lic)

    print("Programa...")
    shutil.copy2(os.path.join(AQUI, "app.py"), os.path.join(destino, "app.py"))
    shutil.copy2(os.path.join(AQUI, "moviola.py"), os.path.join(destino, "moviola.py"))
    copiar_arbol(os.path.join(AQUI, "motor"), os.path.join(destino, "motor"))
    copiar_arbol(os.path.join(AQUI, "web"), os.path.join(destino, "web"))

    print("Python y bibliotecas...")
    copiar_python(os.path.join(destino, "python"), lic)

    if not a.sin_ffmpeg:
        print("ffmpeg...")
        ff = shutil.which("ffmpeg")
        if not ff:
            raise SystemExit("No encuentro ffmpeg en el PATH (usa --sin-ffmpeg si la otra PC ya lo tiene).")
        sonda = shutil.which("ffprobe")
        if not sonda:
            raise SystemExit("No encuentro ffprobe en el PATH: la app lo usa (proxy, miniaturas, audio).")
        os.makedirs(os.path.join(destino, "bin"))
        shutil.copy2(ff, os.path.join(destino, "bin", "ffmpeg.exe"))
        shutil.copy2(sonda, os.path.join(destino, "bin", "ffprobe.exe"))
        carpeta_ff = os.path.dirname(os.path.dirname(ff))
        for nombre in ("LICENSE", "README.txt"):
            if os.path.isfile(os.path.join(carpeta_ff, nombre)):
                shutil.copy2(os.path.join(carpeta_ff, nombre), os.path.join(lic, "FFmpeg-" + nombre))

    print("Textos y lanzadores...")
    for nombre in ("LICENSE", "LICENCIA.md", "AUTHORS"):       # la licencia propia viaja con el programa
        origen = os.path.join(AQUI, nombre)
        if not os.path.isfile(origen):
            raise SystemExit("Falta %s: sin la licencia no se arma el paquete." % nombre)
        shutil.copy2(origen, os.path.join(destino, nombre))
    with open(os.path.join(destino, "LEEME.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(LEEME)
    with open(os.path.join(lic, "LEEME-LICENCIAS.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(LEEME_LICENCIAS)
    for nombre, texto in BAT.items():
        with open(os.path.join(destino, nombre), "w", encoding="ascii", newline="") as f:
            f.write(texto)

    total = sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(destino) for x in fs)
    print("Listo: %s  (%.0f MB)" % (destino, total / 1048576))


if __name__ == "__main__":
    main()
