# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Regresiones de la revision de la version 1.1.0 (seguridad, bugs y diseño): cada cosa que se encontro tiene aca la prueba que la ataja.

Uso:  python -I pruebas/prueba_revision.py
"""

import copy
import http.client
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
TMP = tempfile.mkdtemp(prefix="prueba-revision-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")

import app  # noqa: E402
import motor  # noqa: E402
import prueba_exportar as ex  # noqa: E402
from motor import descargas, gpu, proxy, servidor  # noqa: E402
from motor.proyecto import Proyecto  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def post(srv, nombre, cuerpo_bytes):
    c = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=60)
    c.putrequest("POST", "/%s/api/%s" % (srv.token, nombre), skip_host=True)
    for k, v in {"Host": "127.0.0.1:%d" % srv.puerto, "Content-Type": "application/json", "Content-Length": str(len(cuerpo_bytes))}.items():
        c.putheader(k, v)
    c.endheaders(cuerpo_bytes)
    r = c.getresponse()
    d = r.read()
    c.close()
    return r.status, d


def main():
    print("=== 1. un programa plantado en la carpeta actual no se ejecuta ===")
    trampa = os.path.join(TMP, "carpeta-ajena")
    os.makedirs(trampa)
    falso = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "whoami.exe")
    for nombre in ("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe", "whisper-cli.exe"):
        shutil.copyfile(falso, os.path.join(trampa, nombre))
    codigo = ("import sys, os; sys.path.insert(0, %r); import shutil\n"
              "antes = shutil.which('ffmpeg')\n"
              "from motor import proxy, gpu, descargas, subtitulos, herramienta\n"
              "r = [proxy._ffmpeg(), proxy._ffprobe(), gpu._ffmpeg(), descargas.buscar_ytdlp() or '', subtitulos.buscar_whisper() or '', herramienta('no-existe')]\n"
              "print(repr(antes)); print('|'.join(r))\n") % RAIZ
    entorno = {k: v for k, v in os.environ.items() if k.lower() != "nodefaultcurrentdirectoryinexepath"}
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True, cwd=trampa, env=entorno)
    lineas = (r.stdout or "").strip().splitlines()
    ok(len(lineas) == 2, "el sondeo corrio", (r.stderr or "")[-200:])
    if len(lineas) == 2:
        ok(lineas[0].lower().startswith(("'.\\\\", "'.\\", "'./")) or "carpeta-ajena" in lineas[0].lower(),
           "(sin la defensa, Windows SI elige el ffmpeg.exe de la carpeta actual)", lineas[0])
        rutas = lineas[1].split("|")
        ok(all(os.path.isabs(x) for x in rutas if x) and not any("carpeta-ajena" in x.lower() for x in rutas),
           "con el motor cargado, ffmpeg, ffprobe, yt-dlp y whisper salen del PATH con ruta completa, nunca de la carpeta actual", lineas[1][:160])
        ok(os.path.isabs(rutas[-1]) and rutas[-1].lower().endswith(os.path.join("bin", "no-existe.exe")), "y un programa que no esta devuelve una ruta completa (no un nombre suelto)", rutas[-1])
    ok(os.environ.get("NoDefaultCurrentDirectoryInExePath") == "1", "la variable que le dice a Windows que no mire la carpeta actual queda puesta")

    print("=== 2. un proyecto con numeros que no son numeros no pasa ===")
    src = ex.crear_fuente(os.path.join(ex.TMP, "rev.mp4"), dur=6)
    api = app.API()
    api.cache = os.path.join(TMP, "cache")
    srv = app.crear_servidor(api)
    api.abrir(src)
    base = json.loads(json.dumps(api.proyecto.a_dict()))
    for f in base["fuentes"].values():
        f.pop("url", None)
    casos = (("inicio", float("nan"), 0), ("desde", float("nan"), 0), ("fade_in", float("inf"), 0), ("volumen", "alto", 1), ("volumen", -5, 1),
             ("volumen", 1e9, 1), ("hasta", True, 0), ("pista_audio", 2.5, 1))
    for campo, valor, pista in casos:
        d = copy.deepcopy(base)
        d["pistas"][pista]["clips"][0][campo] = valor
        try:
            malos = Proyecto.cargar_dict(d, None).validar()
        except Exception as e:
            malos = [repr(e)]
        ok(bool(malos), "validar rechaza %s = %r" % (campo, valor), (malos[0] if malos else "")[:70])
    d = copy.deepcopy(base)
    next(iter(d["fuentes"].values()))["duracion"] = float("nan")
    ok(bool(Proyecto.cargar_dict(d, None).validar()), "y una fuente con duracion NaN")
    ok(not Proyecto.cargar_dict(copy.deepcopy(base), None).validar(), "(el proyecto sano sigue pasando)")
    malo = os.path.join(TMP, "con-nan.moviola")
    with open(malo, "w", encoding="utf-8") as f:
        f.write(json.dumps(base).replace('"inicio": 0.0', '"inicio": NaN', 1))
    antes = json.dumps(api.proyecto_estado(), sort_keys=True)
    r = api.abrir_proyecto(malo)
    ok("error" in r and json.dumps(api.proyecto_estado(), sort_keys=True) == antes, "un .moviola con NaN no se abre y no cambia nada", r.get("error", "")[:70])

    print("=== 3. un archivo del proyecto reemplazado por otro mucho mas corto ===")
    d = copy.deepcopy(base)
    for f in d["fuentes"].values():
        f["duracion"] = 600.0
    for p in d["pistas"]:
        p["clips"][0]["hasta"] = 600.0
    cambiado = os.path.join(TMP, "cambiado.moviola")
    with open(cambiado, "w", encoding="utf-8") as f:
        json.dump(d, f)
    r = api.abrir_proyecto(cambiado)
    ok("error" in r and "no es el mismo archivo" in r["error"] and json.dumps(api.proyecto_estado(), sort_keys=True) == antes,
       "se avisa y no se abre (antes se abria con clips que se salian del archivo)", r.get("error", "")[:80])

    print("=== 4. si otro video del proyecto no se puede leer, el visor no cambia ===")
    otro = ex.crear_fuente(os.path.join(ex.TMP, "rev-otro.mp4"), dur=3)
    api2 = app.API()
    api2.cache = os.path.join(TMP, "cache2")
    app.crear_servidor(api2)
    api2.abrir(otro)
    video_antes, ruta_antes = api2.video, api2.ruta
    original = api2._preparar_proyecto
    api2._preparar_proyecto = lambda *a: (_ for _ in ()).throw(OSError("no se pudo leer otro video"))
    guardado = os.path.join(TMP, "bueno.moviola")
    api.proyecto.guardar(guardado)
    r = api2.abrir_proyecto(guardado)
    api2._preparar_proyecto = original
    ok("error" in r and api2.video is video_antes and api2.ruta == ruta_antes and os.path.basename(next(iter(api2.proyecto.fuentes.values()))["ruta"]) == "rev-otro.mp4",
       "falla al armar el proyecto: sigue el video y el proyecto de antes (no una mezcla)", r.get("error", "")[:60])
    ok(api2.cuadro_jpeg(0) is not None, "y el visor sigue entregando cuadros")
    r = api2.abrir_proyecto(guardado)
    ok(not r.get("error") and os.path.basename(api2.ruta) == "rev.mp4", "sin la falla, el proyecto se abre normalmente")
    api2.cerrar()

    print("=== 5. el servidor: una transcripcion larga entra, y no se responde NaN ===")
    ok(servidor.MAX_CUERPO >= 8 * 1024 * 1024, "el tope del cuerpo alcanza para varias horas de palabras", str(servidor.MAX_CUERPO))
    palabras = [{"texto": "palabra", "inicio": 1234.567, "fin": 1234.89, "voz": 1234.6, "habla": 1234.8} for _ in range(30000)]
    cuerpo = json.dumps([[], palabras]).encode()
    s, _ = post(srv, "editar_subtitulos_poner", cuerpo)
    ok(len(cuerpo) > 2 * 1024 * 1024 and s == 200, "un pedido de %.1f MB (palabras de mas de 3 horas) se atiende (antes: 413)" % (len(cuerpo) / 1048576.0), s)
    srv2 = servidor.ServidorLocal(os.path.join(RAIZ, "web"), {"nan": lambda: {"x": float("nan")}}, lambda *a: None)
    s, _ = post(srv2, "nan", b"[]")
    srv2.cerrar()
    ok(s == 500, "una respuesta con NaN no sale como JSON invalido (la pagina no podria leerla)", s)

    print("=== 6. ajustes.json: dos cosas que escriben a la vez no se pisan ===")
    real = gpu.detectar
    def lenta():
        api._recordar(src, "video")                        # mientras se detecta la GPU (10 s) la persona abre un archivo
        api.gpu_modo("auto")
        return {"version": gpu.VERSION, "huella": "h", "fecha": "hoy"}
    gpu.detectar = lenta
    try:
        api._detectar_gpu(True)
    finally:
        gpu.detectar = real
    a = gpu.leer_ajustes(api.ajustes_ruta)
    ok(a.get("deteccion", {}).get("huella") == "h" and a.get("aceleracion") == "auto" and any(x.get("ruta") == src for x in a.get("recientes", [])),
       "quedan la deteccion, el modo elegido y el archivo reciente (antes la deteccion pisaba a los otros dos)", str(sorted(a.keys())))

    print("=== 7. cerrar cancela lo que este corriendo ===")
    evento = threading.Event()
    with api._lock_export:
        api._cancelar_export = evento
        api.exportacion = {"estado": "exportando", "progreso": 0.2}
    def trabajo():
        evento.wait(20)
        time.sleep(0.3)                                    # lo que tarda en matar a ffmpeg y borrar el archivo a medias
        with api._lock_export:
            api.exportacion = {"estado": "cancelado", "progreso": 0.0}
    threading.Thread(target=trabajo, daemon=True).start()
    ok(api.ocupada(), "con una exportacion en curso el programa figura ocupado (en modo navegador no se apaga solo)")
    t0 = time.time()
    api.cerrar()
    ok(evento.is_set() and not api.ocupada() and time.time() - t0 < 5, "cerrar avisa a la exportacion y espera a que termine de limpiar", "%.1f s" % (time.time() - t0))
    ok(app.LIMITE_SIN_LATIDO >= 75, "en modo navegador se toleran mas de 60 s sin latido (una pestaña oculta late una vez por minuto)", str(app.LIMITE_SIN_LATIDO))

    print("=== 8. yt-dlp y FFmpeg ===")
    fuente = inspect.getsource(descargas.descargar)
    ok('"--ignore-config"' in fuente, "yt-dlp corre sin la configuracion del usuario (--ignore-config)")
    cmd = [proxy._ffprobe(), "-v", "warning"] + motor.SOLO_ARCHIVOS + ["-show_format", "-of", "json", "http://127.0.0.1:9/no-existe.mp4"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    ok("whitelist" in (r.stderr or "").lower(), "con SOLO_ARCHIVOS, FFmpeg se niega a pedir una direccion de internet (lo que haria una lista de reproduccion disfrazada de video)",
       (r.stderr or "").strip()[-90:])
    for modulo, texto in (("exportar", '"-protocol_whitelist", "file", "-i", e["ruta"]'), ("proxy", '"-protocol_whitelist", "file", "-i", ruta'),
                          ("audio", '"-protocol_whitelist", "file", "-i", ruta'), ("tiras", '"-protocol_whitelist", "file", "-i", ruta'),
                          ("video", '"protocol_whitelist": "file"')):
        with open(os.path.join(RAIZ, "motor", modulo + ".py"), encoding="utf-8") as f:
            ok(texto in f.read(), "motor/%s.py abre solo archivos" % modulo)

    print("=== 9. instalada con el instalador, los datos van al perfil ===")
    marca = os.path.join(RAIZ, ".moviola-instalado")
    ya = os.path.exists(marca)
    if not ya:
        open(marca, "w").close()
    try:
        carpeta = app._carpeta_de_datos()
    finally:
        if not ya:
            os.remove(marca)
    ok(os.path.normcase(carpeta) != os.path.normcase(RAIZ) and os.path.basename(carpeta) == "Moviola", "con la marca del instalador: %LOCALAPPDATA%\\Moviola", carpeta)
    ok(os.path.normcase(app._carpeta_de_datos()) == os.path.normcase(RAIZ), "sin la marca (portatil, desarrollo): al lado del programa")

    print("=== 10. los subtitulos dependen solo de la pista de voz ===")
    q = Proyecto.cargar_dict(copy.deepcopy(base), None)
    q.subtitulos_poner([{"inicio": 0.5, "fin": 2.0, "texto": "hola"}])
    musica = q.agregar_fuente(src, "audio", 6.0, None, 1)
    q.agregar_audio(musica, 0.0)
    ok(not q.subtitulos_desactualizados(), "sumar musica en otra pista no marca los subtitulos como desactualizados (antes si)")
    q.borrar_rango(1.0, 2.0)
    ok(q.subtitulos_desactualizados(), "cortar la voz si los marca")
    vieja = Proyecto.cargar_dict(copy.deepcopy(base), None)
    vieja.subtitulos_poner([{"inicio": 0.5, "fin": 2.0, "texto": "hola"}])
    d = vieja.a_dict()
    d["subtitulos"]["huella"] = vieja.huella_linea(todas=True)          # como lo guardaba la 1.0
    ok(not Proyecto.cargar_dict(d, None).subtitulos_desactualizados(), "un proyecto guardado con la 1.0 abre con los subtitulos al dia")

    print("=== 11. version ===")
    with open(os.path.join(RAIZ, "CHANGELOG.md"), encoding="utf-8") as f:
        ok("## [%s]" % app.VERSION in f.read(), "CHANGELOG.md tiene la seccion de la version %s" % app.VERSION)

    print()
    print("TODO BIEN" if not fallos else "FALLARON %d: %s" % (len(fallos), ", ".join(fallos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
