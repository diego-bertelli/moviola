# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""El instalador (Instalar-Moviola.bat / instalar.ps1 / desinstalar.ps1), ejecutado de verdad pero SIN internet y SIN tocar el perfil del usuario
(sin accesos directos ni registro de Windows: eso se prueba a mano porque pisaria una instalacion real).

Cubre: los scripts se leen bien en PowerShell 5 (sintaxis, UTF-8 con BOM, el .bat en ASCII); una instalacion deja el programa andando (su Python
importa av, pywebview y Pillow, FFmpeg incluido, la marca con la version); sin conexion avisa y sigue; instalar de nuevo ACTUALIZA sin perder los
ajustes; no toca una carpeta ajena; reconoce lo que ya hay (whisper, modelo); las sumas de verificacion fijadas en el script tienen forma de SHA-256;
el desinstalador borra solo lo que tiene la marca y respeta lo ajeno.

Uso:  python -I pruebas/prueba_instalador.py        (arma el instalador: ~1-2 minutos)
"""

import os
import re
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
os.chdir(RAIZ)
INST = os.path.join(RAIZ, "dist", "Moviola-instalador")
TMP = tempfile.mkdtemp(prefix="prueba-instalador-")
fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def ps(argumentos, entorno_extra=None, timeout=900):
    entorno = dict(os.environ, MOVIOLA_SIN_PAUSA="1", MOVIOLA_SIN_INTERNET="1")
    entorno.update(entorno_extra or {})
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"] + argumentos, capture_output=True, timeout=timeout, env=entorno)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def instalar(destino, *extra):
    return ps(["-File", os.path.join(INST, "instalador", "instalar.ps1"), "-Silencioso", "-SinAccesos", "-SinWebView2", "-Destino", destino,
               "-Whisper", os.path.join(TMP, "whisper"), "-Modelos", os.path.join(TMP, "modelos")] + list(extra))


def main():
    print("=== armando el instalador ===")
    r = subprocess.run([sys.executable, "-I", os.path.join(RAIZ, "construir_instalador.py"), "--sin-zip"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok(r.returncode == 0 and os.path.isfile(os.path.join(INST, "Instalar-Moviola.bat")), "construir_instalador.py arma la carpeta", (r.stdout or r.stderr)[-120:].strip())
    if r.returncode != 0:
        return 1

    print("=== 1. los scripts ===")
    for nombre in ("instalar.ps1", "desinstalar.ps1"):
        ruta = os.path.join(INST, "instalador", nombre)
        crudo = open(ruta, "rb").read()
        ok(crudo.startswith(b"\xef\xbb\xbf"), nombre + ": UTF-8 con BOM (sin BOM PowerShell 5 rompe las tildes)")
        ok(b"\r\n" in crudo and b"\n" not in crudo.replace(b"\r\n", b""), nombre + ": fin de linea de Windows")
        c, s = ps(["-Command", "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); $e.Count" % ruta])
        ok(s.strip().endswith("0"), nombre + ": PowerShell lo lee sin errores de sintaxis", s.strip()[-80:])
    bat = open(os.path.join(INST, "Instalar-Moviola.bat"), "rb").read()
    ok(all(b < 128 for b in bat) and b"%*" in bat and b"instalar.ps1" in bat, "Instalar-Moviola.bat: ASCII y pasa los argumentos (%*) al script")
    ok(os.path.isfile(os.path.join(INST, "paquete", "moviola.ico")) and os.path.isfile(os.path.join(INST, "LEEME-INSTALADOR.txt")), "trae el icono y el LEEME")
    texto = open(os.path.join(INST, "instalador", "instalar.ps1"), encoding="utf-8-sig").read()
    shas = re.findall(r"sha\s*=\s*'([0-9a-f]+)'", texto)
    ok(len(shas) == 5 and all(re.fullmatch(r"[0-9a-f]{64}", s) for s in shas), "las 5 sumas SHA-256 fijadas (4 modelos y whisper) tienen forma de SHA-256", str(len(shas)))
    leeme = open(os.path.join(INST, "LEEME-INSTALADOR.txt"), encoding="utf-8-sig").read()
    documentadas = set(re.findall(r"(?<![\w-])-(Silencioso|SinWhisper|SinYtdlp|SinWebView2|SinAccesos|SinEscritorio|SinAsociar|Forzar|Destino|Whisper|Modelos|Modelo)", leeme))
    declaradas = set(re.findall(r"\[(?:switch|string|ValidateSet[^\]]*\]\[string)\]\$(\w+)", texto))
    ok(len(documentadas) == 12 and documentadas <= declaradas, "todas las opciones que explica el LEEME existen en instalar.ps1", str(sorted(documentadas - declaradas)))

    print("=== 2. instalar (sin internet) ===")
    destino = os.path.join(TMP, "Moviola")
    c, s = instalar(destino)
    ok(c == 0, "termina bien aunque no haya conexion", "codigo %s" % c)
    ok("No hay conexión" in s and "falta whisper-cli" in s, "avisa que sin conexion no pudo bajar whisper, el modelo ni yt-dlp y lo deja dicho")
    ok(all(os.path.exists(os.path.join(destino, x)) for x in ("app.py", "moviola.py", "motor", "web", "python/pythonw.exe", "bin/ffmpeg.exe", "bin/ffprobe.exe", "LICENSE", "licencias", "Desinstalar-Moviola.bat", "instalador/desinstalar.ps1", ".moviola-instalado")),
       "quedan el programa, su Python, FFmpeg, las licencias y el desinstalador")
    import json
    man = json.load(open(os.path.join(destino, ".moviola-instalado"), encoding="utf-8"))
    version = re.search(r"^VERSION\s*=\s*'([^']+)'", open(os.path.join(RAIZ, "app.py"), encoding="utf-8").read(), re.M).group(1)
    ok(man["version"] == version, "la marca anota la version instalada", man["version"])
    r = subprocess.run([os.path.join(destino, "python", "python.exe"), "-I", "-c", "import av, webview, PIL; print('importa')"], capture_output=True, text=True)
    ok("importa" in r.stdout, "el Python instalado importa av, pywebview y Pillow", (r.stderr or r.stdout)[-100:])
    r = subprocess.run([os.path.join(destino, "python", "python.exe"), os.path.join(destino, "moviola.py"), "herramientas"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=destino)
    ok(destino.lower() in r.stdout.lower() and "ffmpeg" in r.stdout.lower(), "moviola.py herramientas encuentra el FFmpeg incluido", r.stdout.strip().splitlines()[0][:100] if r.stdout.strip() else r.stderr[-100:])

    print("=== 3. instalar de nuevo = actualizar ===")
    with open(os.path.join(destino, "ajustes.json"), "w", encoding="utf-8") as f:
        f.write('{"mio": true}')
    huerfano = os.path.join(destino, "motor", "viejo_que_ya_no_existe.py")
    open(huerfano, "w").write("x = 1\n")
    c, s = instalar(destino)
    ok(c == 0 and "se actualiza" in s, "el segundo pase actualiza", "codigo %s" % c)
    ok(open(os.path.join(destino, "ajustes.json"), encoding="utf-8").read() == '{"mio": true}', "los ajustes del usuario se conservan")
    ok(not os.path.exists(huerfano), "y no quedan archivos viejos del programa")

    print("=== 4. lo ajeno no se toca ===")
    ajena = os.path.join(TMP, "ajena")
    os.makedirs(ajena)
    open(os.path.join(ajena, "mis-cosas.txt"), "w").write("importante")
    c, s = instalar(ajena)
    ok(c == 1 and "no la toco" in s and os.path.isfile(os.path.join(ajena, "mis-cosas.txt")) and not os.path.exists(os.path.join(ajena, "app.py")),
       "una carpeta con archivos que no armo el instalador se rechaza y queda intacta")

    print("=== 5. reconoce lo que ya hay ===")
    os.makedirs(os.path.join(TMP, "whisper"))
    os.makedirs(os.path.join(TMP, "modelos"))
    open(os.path.join(TMP, "whisper", "whisper-cli.exe"), "wb").write(b"no es un programa de verdad")
    open(os.path.join(TMP, "modelos", "ggml-base.bin"), "wb").write(b"x")
    c, s = instalar(os.path.join(TMP, "Moviola2"))
    ok("whisper-cli ya está" in s and "Ya hay un modelo de whisper: ggml-base.bin" in s, "si whisper y un modelo ya estan, no los baja")

    print("=== 6. desinstalar ===")
    c, s = ps(["-File", os.path.join(INST, "instalador", "desinstalar.ps1"), "-Destino", ajena, "-Silencioso"])      # el del instalador (no el instalado: ese siempre quita su propia carpeta)
    ok(c == 1 and os.path.isfile(os.path.join(ajena, "mis-cosas.txt")), "no borra una carpeta que no tiene la marca del instalador")
    c, s = ps(["-File", os.path.join(destino, "instalador", "desinstalar.ps1"), "-Silencioso"])
    ok(c == 0 and not os.path.exists(destino), "desinstalar desde la carpeta instalada la borra entera (aunque el script viva adentro)", "codigo %s" % c)
    ok(os.path.isdir(os.path.join(TMP, "Moviola2")) and os.path.isfile(os.path.join(TMP, "modelos", "ggml-base.bin")), "y no toca otra instalacion ni los modelos")

    print("=== 7. basura ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)

    print()
    print("TODO BIEN" if not fallos else "FALLARON %d: %s" % (len(fallos), ", ".join(fallos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
