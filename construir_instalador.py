# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Arma el INSTALADOR de Moviola: una carpeta (y un .zip) que se lleva a otra PC con Windows y se ejecuta con doble clic.

Uso (con el Python con el que se desarrolla el editor):

    python construir_instalador.py                 usa dist\\Moviola-portatil (si no esta o quedo viejo, o con --portatil, lo arma)
    python construir_instalador.py --portatil      vuelve a armar antes el paquete portatil
    python construir_instalador.py --sin-zip       no arma el .zip

Resultado:  dist\\Moviola-instalador\\
    Instalar-Moviola.bat      doble clic: instala Moviola y, por consola, todo lo que necesita (ver instalador\\instalar.ps1)
    instalador\\              instalar.ps1 y desinstalar.ps1 (PowerShell 5, el que trae Windows; sin permisos de administrador)
    paquete\\                 Moviola ya armada: su Python, sus bibliotecas y FFmpeg (no se baja nada de esto)
    LEEME-INSTALADOR.txt
y  dist\\Moviola-instalador.zip

Lo que el instalador baja de internet (y verifica con SHA-256): whisper.cpp, un modelo de whisper a eleccion, yt-dlp y, si Windows
no lo trae, WebView2.
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(AQUI, "dist")
PORTATIL = os.path.join(DIST, "Moviola-portatil")
DESTINO = os.path.join(DIST, "Moviola-instalador")

LEEME = """MOVIOLA - instalador
====================

PARA INSTALAR
  1. Descomprimi TODO el .zip en una carpeta (no ejecutes nada desde adentro del .zip).
  2. Doble clic en  Instalar-Moviola.bat
  3. Segui lo que va diciendo la consola. No hace falta ser administrador.

QUE INSTALA
  Moviola                     en  %LOCALAPPDATA%\\Programs\\Moviola  (con su propio Python, sus bibliotecas y FFmpeg: viene
                              dentro de este paquete, no baja nada para esto)
  whisper.cpp (whisper-cli)   para transcribir subtitulos      -> %LOCALAPPDATA%\\Programs\\whisper.cpp
  un modelo de whisper        a eleccion (de 141 MB a 1,5 GB)   -> %USERPROFILE%\\whisper-modelos
  yt-dlp                      para bajar de YouTube            -> carpeta de Moviola, bin\\
  WebView2                    la ventana de Moviola, solo si Windows no lo trae (Windows 11 lo trae)
  accesos directos (Inicio y Escritorio), «Aplicaciones instaladas» y doble clic en los archivos .moviola

  Lo que ya tengas instalado en la PC no se vuelve a bajar. Todo lo que se baja se verifica con su suma SHA-256: si no coincide, no
  se instala. Si no hay internet se instala solo Moviola (con FFmpeg) y se puede repetir despues: el instalador se puede ejecutar
  cuantas veces haga falta (actualiza, no duplica).

SIN PREGUNTAS (para varias PC o para un script)
  Instalar-Moviola.bat -Silencioso                      instala todo con las opciones recomendadas
  Instalar-Moviola.bat -Silencioso -Modelo small        otro modelo: turbo, turbo-q5, small, base o ninguno
  Otras opciones:  -SinWhisper  -SinYtdlp  -SinWebView2  -SinAccesos  -SinEscritorio  -SinAsociar
                   -Destino "D:\\Programas\\Moviola"  -Whisper "carpeta"  -Modelos "carpeta"  -Forzar (vuelve a bajar todo)

PARA DESINSTALAR
  Configuracion de Windows > Aplicaciones > Moviola > Desinstalar, o el acceso «Desinstalar Moviola» del menu Inicio, o
  Desinstalar-Moviola.bat en la carpeta de Moviola. Tus videos y tus proyectos no se tocan. Lo que se bajo aparte (whisper y el modelo)
  se pregunta uno por uno, porque otros programas pueden usarlo.

SI ALGO FALLA
  El registro de la instalacion queda en  %TEMP%\\moviola-instalacion.log
  Windows puede mostrar un aviso de «SmartScreen» o de «archivo bajado de internet» porque el instalador no esta firmado
  (es un script de texto: se puede leer entero en instalador\\instalar.ps1).

LICENCIA
  Moviola es software libre (GNU GPL v3 o posterior), sin ninguna garantia. Mira paquete\\LICENSE, paquete\\LICENCIA.md y
  paquete\\licencias\\. Autores: Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5).
"""


def escribir_con_bom(origen, destino):
    """PowerShell 5 lee un .ps1 sin BOM como ANSI y rompe las tildes: se guarda como UTF-8 con BOM y fin de linea de Windows."""
    with open(origen, encoding="utf-8-sig", newline="") as f:
        texto = f.read().replace("\r\n", "\n")
    with open(destino, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(texto)


def hacer_icono(destino):
    from PIL import Image
    im = Image.open(os.path.join(AQUI, "web", "logo.png")).convert("RGBA")
    im.save(destino, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def portatil_al_dia():
    """True si el paquete portatil que ya esta armado tiene EXACTAMENTE el programa de ahora (app.py, moviola.py, motor/ y web/). Si se
    cambio algo despues de armarlo, el instalador llevaria una version vieja."""
    if not os.path.isfile(os.path.join(PORTATIL, ".moviola-portatil")):
        return False
    pares = [("app.py", "app.py"), ("moviola.py", "moviola.py")]
    for carpeta in ("motor", "web"):
        for raiz, carpetas, nombres in os.walk(os.path.join(AQUI, carpeta)):
            carpetas[:] = [c for c in carpetas if c != "__pycache__"]
            for n in nombres:
                if not n.endswith(".pyc"):
                    rel = os.path.relpath(os.path.join(raiz, n), AQUI)
                    pares.append((rel, rel))
    for origen, copia in pares:
        a, b = os.path.join(AQUI, origen), os.path.join(PORTATIL, copia)
        if not os.path.isfile(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            if fa.read() != fb.read():
                return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portatil", action="store_true", help="vuelve a armar antes el paquete portatil")
    ap.add_argument("--sin-zip", action="store_true")
    a = ap.parse_args()

    if a.portatil or not portatil_al_dia():
        print("Armando el paquete portatil (no esta o es de una version anterior del programa)...")
        subprocess.run([sys.executable, "-I", os.path.join(AQUI, "construir_portatil.py")], check=True, cwd=AQUI)
    if not os.path.isfile(os.path.join(PORTATIL, "python", "pythonw.exe")):
        raise SystemExit("El paquete portatil esta incompleto: corre  python construir_portatil.py")

    if os.path.exists(DESTINO):
        if not os.path.isfile(os.path.join(DESTINO, ".moviola-instalador")):
            raise SystemExit("%s ya existe y no lo armo este script: no lo toco." % DESTINO)
        shutil.rmtree(DESTINO)
    os.makedirs(os.path.join(DESTINO, "instalador"))
    with open(os.path.join(DESTINO, ".moviola-instalador"), "w") as f:
        f.write("marca: solo se borra una carpeta que tenga este archivo\n")

    print("Paquete...")
    paquete = os.path.join(DESTINO, "paquete")
    shutil.copytree(PORTATIL, paquete, ignore=shutil.ignore_patterns(".moviola-portatil", "__pycache__"))
    hacer_icono(os.path.join(paquete, "moviola.ico"))

    print("Scripts...")
    for nombre in ("instalar.ps1", "desinstalar.ps1"):
        escribir_con_bom(os.path.join(AQUI, "instalador", nombre), os.path.join(DESTINO, "instalador", nombre))
    with open(os.path.join(AQUI, "instalador", "Instalar-Moviola.bat"), encoding="utf-8") as f:
        bat = f.read().replace("\r\n", "\n")
    with open(os.path.join(DESTINO, "Instalar-Moviola.bat"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(bat)
    with open(os.path.join(DESTINO, "LEEME-INSTALADOR.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(LEEME)

    total = sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(DESTINO) for x in fs)
    print("Carpeta lista: %s  (%.0f MB)" % (DESTINO, total / 1048576))

    if not a.sin_zip:
        print("Comprimiendo...")
        zip_ruta = DESTINO + ".zip"
        if os.path.exists(zip_ruta):
            os.remove(zip_ruta)
        with zipfile.ZipFile(zip_ruta, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for r, ds, fs in os.walk(DESTINO):
                for x in fs:
                    ruta = os.path.join(r, x)
                    z.write(ruta, os.path.join("Moviola-instalador", os.path.relpath(ruta, DESTINO)))
        print("Zip listo: %s  (%.0f MB)" % (zip_ruta, os.path.getsize(zip_ruta) / 1048576))


if __name__ == "__main__":
    main()
