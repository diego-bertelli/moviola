# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la aceleracion por GPU (motor/gpu.py + su uso en video.py, proxy.py y app.py).

Uso:  python -I pruebas/prueba_gpu.py

Que SE verifica de verdad en esta PC: la deteccion, la politica CPU/GPU/Auto, la decodificacion
por GPU (d3d11va), y el RESPALDO cuando un codificador por hardware falla (se usa NVENC, que
en esta PC no existe y falla de verdad).
Que NO se puede verificar sin el hardware: un codificador de GPU que SI funcione. Ese camino
se ejercita con un codificador real distinto de x264 (Media Foundation por software) puesto
en su lugar; prueba el codigo, no el rendimiento de ninguna GPU.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from io import BytesIO

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

TMP = tempfile.mkdtemp(prefix="prueba-gpu-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")
os.environ["EDITOR_SIN_GPU"] = "1"

from PIL import Image, ImageChops, ImageStat  # noqa: E402

import app  # noqa: E402
from motor import gpu, proxy  # noqa: E402
from motor.video import Video  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def parecido(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def jpg(datos):
    return Image.open(BytesIO(datos)).convert("L")


# -- detecciones inventadas para probar la politica sin depender del hardware de esta PC
def _dec(h264_conviene, hevc_conviene=None, tipo="d3d11va"):
    def d(conviene):
        return {"ok": True, "segundos": 0.5, "segundos_cpu": 0.5 * (0.5 if conviene else 4),
                "veces_mas_lento": 0.5 if conviene else 4.0, "conviene": conviene}
    return {tipo: {"h264": d(h264_conviene), "hevc": d(h264_conviene if hevc_conviene is None else hevc_conviene)}}


def _det(gpus, codificadores_ok=(), conviene=False, decodifica=True, pista=""):
    nombres = [("h264_nvenc", "NVIDIA", "NVIDIA NVENC"), ("h264_qsv", "Intel", "Intel Quick Sync"),
               ("h264_amf", "AMD", "AMD AMF"), ("h264_mf", None, "Media Foundation por hardware")]
    cod = {}
    for n, fab, etiqueta in nombres:
        if n in codificadores_ok:
            cod[n] = {"ok": True, "etiqueta": etiqueta, "motivo": ""}
        elif fab and not any(g["fabricante"] == fab for g in gpus):
            cod[n] = {"ok": False, "etiqueta": etiqueta, "motivo": "No hay una placa %s en esta PC." % fab}
        elif fab:
            cod[n] = {"ok": False, "etiqueta": etiqueta, "motivo": "La placa no ofrece codificación por hardware."}
        else:
            cod[n] = {"ok": False, "etiqueta": etiqueta, "motivo": "Windows no tiene un codificador por hardware."}
    return {"version": gpu.VERSION, "fecha": "2026-01-01 00:00:00", "huella": "inventada", "gpus": gpus,
            "procesador": "CPU", "codificadores": cod, "decodificadores": _dec(conviene) if decodifica else {},
            "nota": "", "pista": pista}


AMD = [{"nombre": "AMD Radeon RX 6500 XT", "fabricante": "AMD", "controlador": "1"}]
NVIDIA = [{"nombre": "NVIDIA GeForce RTX 3060", "fabricante": "NVIDIA", "controlador": "1"}]


def main():
    print("=== 1. deteccion real en esta PC ===")
    t0 = time.time()
    det = gpu.detectar()
    dt = time.time() - t0
    ok(dt < 60, "detectar() termina en un tiempo razonable", f"{dt:.1f} s")
    ok(det["procesador"] != "" and len(det["gpus"]) >= 1, "reconoce el procesador y la placa de video",
       f"{det['procesador']} / {[g['nombre'] for g in det['gpus']]}")
    ok(set(det["codificadores"]) >= {"h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"}, "prueba los codificadores principales")
    todos_explicados = all(c["ok"] or c["motivo"] for c in det["codificadores"].values())
    ok(todos_explicados, "cada codificador que no anda trae su motivo en castellano")
    ok(all("Task finished" not in c["motivo"] and "vost#" not in c["motivo"] for c in det["codificadores"].values()),
       "y ningun motivo es un volcado tecnico de ffmpeg")
    for n in ("h264_nvenc", "h264_qsv"):
        fab = {"h264_nvenc": "NVIDIA", "h264_qsv": "Intel"}[n]
        if not any(g["fabricante"] == fab for g in det["gpus"]):
            ok(det["codificadores"][n]["ok"] is False, f"{n} no se da por disponible sin una placa {fab}")
    mf = det["codificadores"]["h264_mf"]
    ok(not mf["ok"] or "hardware" in mf["etiqueta"].lower(),
       "Media Foundation solo cuenta como GPU si se obliga a usar hardware (el de Microsoft es por software)", mf["motivo"][:60])
    for tipo, por_codec in det["decodificadores"].items():
        for codec, d in por_codec.items():
            if d["ok"]:
                ok(d["veces_mas_lento"] > 0 and isinstance(d["conviene"], bool), f"{tipo}/{codec}: mide la velocidad contra el procesador",
                   f"{d['veces_mas_lento']}x")
    h1 = gpu._huella(gpu.listar_equipo())
    h2 = gpu._huella(gpu.listar_equipo())
    ok(h1 == h2 == det["huella"], "la huella del equipo es estable (sirve para saber si cambio)", h1)

    print("=== 2. politica CPU / GPU / Automatico (con casos inventados) ===")
    # PC como la de Diego: AMD sin motor de video, la GPU decodifica mas lento
    nada = _det(AMD, conviene=False)
    r = gpu.resolver(nada, "cpu")
    ok(r["codificar"]["usa"] == "cpu" and r["decodificar"]["usa"] == "cpu", "CPU: todo por el procesador")
    r = gpu.resolver(nada, "gpu")
    ok(r["codificar"]["usa"] == "cpu" and "no puede codificar" in r["codificar"]["motivo"], "GPU sin codificador: cae al procesador y lo explica",
       r["codificar"]["motivo"])
    ok(r["decodificar"]["usa"] == "gpu" and r["decodificar"]["tipo"] == "d3d11va", "GPU: decodifica por GPU aunque sea mas lento (lo pidio)")
    r = gpu.resolver(nada, "auto")
    ok(r["codificar"]["usa"] == "cpu" and r["decodificar"]["usa"] == "cpu", "Auto: no usa la GPU donde pierde")
    ok("más rápido que la GPU" in r["decodificar"]["motivo"], "y dice por que", r["decodificar"]["motivo"])
    # PC con NVIDIA que si gana
    rapida = _det(NVIDIA, codificadores_ok=["h264_nvenc"], conviene=True)
    r = gpu.resolver(rapida, "auto")
    ok(r["codificar"]["usa"] == "gpu" and r["codificar"]["codificador"] == "h264_nvenc", "Auto con NVIDIA: codifica con NVENC")
    ok(r["decodificar"]["usa"] == "gpu", "Auto con NVIDIA que gana decodificando: decodifica por GPU")
    r = gpu.resolver(rapida, "cpu")
    ok(r["codificar"]["codificador"] is None, "CPU con NVIDIA: igual usa el procesador (lo eligio)")
    ok(gpu.resolver(None, "gpu")["codificar"]["usa"] == "cpu", "sin deteccion todavia: procesador")
    ok(gpu.resolver(rapida, "cualquier cosa")["modo"] == "cpu", "un modo desconocido se trata como CPU")
    # preferencia entre codificadores
    varios = _det(NVIDIA, codificadores_ok=["h264_amf", "h264_qsv", "h264_nvenc"])
    ok(gpu.codificador_disponible(varios) == "h264_nvenc", "con varios, prefiere NVENC > Quick Sync > AMF")

    print("=== 3. lo que se le cuenta a la persona ===")
    res = gpu.resumen(nada)
    ok(res["nivel"] == "ojo" and not res["util"], "AMD sin motor de video: aviso 'ojo' y GPU no util", res["titulo"])
    texto = " ".join(res["lineas"])
    ok("NVIDIA" not in texto and "AMD Radeon RX 6500 XT" in texto, "explica la placa que SI hay, no una NVIDIA inexistente", texto[:140])
    ok("4.0 veces más lento" in texto, "dice cuanto mas lenta es la GPU para decodificar")
    res = gpu.resumen(rapida)
    ok(res["nivel"] == "ok" and res["util"] and res["puede_codificar"], "NVIDIA que anda: nivel ok", res["titulo"])
    ok("disponible" in " ".join(res["lineas"]), "y lo dice")
    ok(gpu.resumen(None)["titulo"].startswith("Comprobando"), "sin deteccion: 'comprobando'")
    pista = gpu.resumen(_det(AMD, pista="Tu procesador trae gráficos integrados que Windows no muestra."))
    ok(any("integrados" in l for l in pista["lineas"]), "incluye la pista de los graficos integrados apagados")

    print("=== 4. ajustes guardados ===")
    ruta = os.path.join(TMP, "a.json")
    gpu.guardar_ajustes(ruta, {"aceleracion": "auto", "n": "ñandú"})
    ok(gpu.leer_ajustes(ruta) == {"aceleracion": "auto", "n": "ñandú"}, "guarda y lee (con tildes)")
    ok(not os.path.exists(ruta + ".tmp"), "la escritura es atomica (no deja .tmp)")
    with open(ruta, "w") as f:
        f.write("{roto")
    ok(gpu.leer_ajustes(ruta) == {}, "un archivo roto se ignora sin romper nada")
    ok(gpu.leer_ajustes(os.path.join(TMP, "no_existe.json")) == {}, "uno que no existe tambien")

    print("=== 5. decodificar por GPU (d3d11va, de verdad) ===")
    h264 = os.path.join(TMP, "h264.mp4")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", h264)
    with Video(h264) as cpu, Video(h264, aceleracion="d3d11va") as hw:
        ok(cpu.info()["decodifica_con"] == "cpu", "sin pedir nada decodifica con el procesador")
        ok(hw.info()["decodifica_con"] == "gpu", "pidiendo d3d11va decodifica con la GPU", hw.info()["decodifica_con"])
        ok(cpu.tabla_tiempos() == hw.tabla_tiempos(), "misma tabla de tiempos")
        for n in (0, 30, 77, 119):
            d = parecido(jpg(cpu.cuadro(n, 320)), jpg(hw.cuadro(n, 320)))
            ok(d < 5, f"cuadro {n}: la GPU da la misma imagen que el procesador", f"diferencia {d:.2f}")
        hw.cuadro(10, 160)
        t0 = time.perf_counter()
        for n in range(11, 41):
            hw.cuadro(n, 160)
        ms_hw = (time.perf_counter() - t0) / 30 * 1000
        cpu.cuadro(10, 160)
        t0 = time.perf_counter()
        for n in range(11, 41):
            cpu.cuadro(n, 160)
        ms_cpu = (time.perf_counter() - t0) / 30 * 1000
        print(f"  (cuadro por cuadro 720p: GPU {ms_hw:.1f} ms, procesador {ms_cpu:.1f} ms; acceso aleatorio abajo)")
        for n in (3, 90, 45, 118, 1):
            hw._ultimo = None
            hw._generador = None
            cuadro = hw._decodificar(n)
            ok(cuadro.pts == hw._pts[n], f"acceso aleatorio por GPU al cuadro {n}")
    mpeg2 = os.path.join(TMP, "m.mpg")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=2", "-c:v", "mpeg2video", mpeg2)
    with Video(mpeg2, aceleracion="d3d11va") as v:
        ok(v.info()["decodifica_con"] == "cpu", "si la GPU no puede con ese codec, cae al procesador y lo informa (MPEG-2)",
           v.info()["decodifica_con"])
        ok(len(v.cuadro(5, 160)) > 100, "y los cuadros salen igual")
    with Video(h264, aceleracion="acelerador_inventado") as v:
        ok(v.info()["decodifica_con"] == "cpu" and len(v.cuadro(5, 160)) > 100, "un acelerador que no existe: procesador, sin romper")

    print("=== 6. proxy con codificador por hardware: el RESPALDO ===")
    fuente = os.path.join(TMP, "fuente.mkv")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=4", "-f", "lavfi", "-i", "sine=f=440:d=4",
           "-c:v", "libx265", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-shortest", fuente)

    def tabla_igual(a, b):
        with Video(a) as x, Video(b) as y:
            ta, tb = x.tabla_tiempos(), y.tabla_tiempos()
        return len(ta) == len(tb) and max(abs(p - q) for p, q in zip(ta, tb)) < 0.040

    # NVENC no existe en esta PC: falla de verdad, y el proxy se hace igual con el procesador
    avance = []
    r = proxy.generar(fuente, os.path.join(TMP, "c1"), avance.append, codificador="h264_nvenc")
    ok(r["usado"] == "cpu" and r["respaldo"] is True, "si NVENC falla se repite con el procesador y se avisa", f"{r['usado']}, respaldo={r['respaldo']}")
    ok(bool(r["motivo_respaldo"]), "con el motivo", r["motivo_respaldo"][:80])
    ok(tabla_igual(fuente, r["archivo"]), "y el proxy resultante es correcto (misma tabla de tiempos)")
    ok(all(b >= a for a, b in zip(avance, avance[1:])) and avance[-1] == 1.0, "el progreso no retrocede aunque se haya repetido el trabajo",
       f"{len(avance)} avisos")
    # un codificador "de hardware" que funciona (simulado con Media Foundation por software)
    original = dict(gpu._ARGS_CODIFICADOR)
    gpu._ARGS_CODIFICADOR["h264_mf"] = ["-c:v", "h264_mf", "-b:v", "2M"]
    try:
        r = proxy.generar(fuente, os.path.join(TMP, "c2"), codificador="h264_mf")
        ok(tabla_igual(fuente, r["archivo"]), "con un codificador alternativo el proxy sigue teniendo la misma tabla de tiempos",
           f"usado={r['usado']}")
        ok((r["usado"] == "gpu") == (not r["respaldo"]), "'usado' y 'respaldo' son coherentes", f"{r['usado']}/{r['respaldo']}")
        v = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,pix_fmt",
                            "-of", "csv=p=0", r["archivo"]], capture_output=True, text=True).stdout.strip()
        ok(v.startswith("h264"), "y sale h264 reproducible", v)
        # se fuerza que la verificacion de tiempos rechace lo que produjo el codificador
        real = proxy._comprobar_tabla
        proxy._comprobar_tabla = lambda *a, **k: (_ for _ in ()).throw(proxy.ProxyError("La GPU generó tiempos distintos a los del original."))
        try:
            r = proxy.generar(fuente, os.path.join(TMP, "c3"), codificador="h264_mf")
        finally:
            proxy._comprobar_tabla = real
        ok(r["usado"] == "cpu" and r["respaldo"] and "tiempos distintos" in r["motivo_respaldo"],
           "si la GPU produce tiempos que no coinciden, se descarta y se usa el procesador")
        ok(tabla_igual(fuente, r["archivo"]), "y el resultado final es correcto")
    finally:
        gpu._ARGS_CODIFICADOR.clear()
        gpu._ARGS_CODIFICADOR.update(original)
    # un audio no usa codificador de video
    ac3 = os.path.join(TMP, "t.ac3")
    ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=2", "-c:a", "ac3", ac3)
    r = proxy.generar(ac3, os.path.join(TMP, "c4"), codificador="h264_nvenc")
    ok(r["archivo"].endswith(".m4a") and r["respaldo"] is False, "un audio ignora el codificador de video")

    print("=== 7. la API: modo guardado, aviso, deteccion reutilizada ===")
    for f in os.listdir(TMP):
        if f == "ajustes.json":
            os.remove(os.path.join(TMP, f))
    api = app.API()
    api.deteccion = nada
    st = api.gpu_estado()
    ok(st["modo"] == "cpu" and st["listo"] and st["efectivo"]["codificar"]["usa"] == "cpu", "arranca en CPU")
    ok(st["avisar"] is True, "primera vez que ve este equipo: avisa")
    api.gpu_visto()
    ok(api.gpu_estado()["avisar"] is False, "ya visto en un equipo sin GPU util: no vuelve a molestar")
    api.deteccion = rapida
    ok(api.gpu_estado()["avisar"] is True, "si hay GPU util y se usa el procesador: avisa siempre (hay algo que decidir)")
    st = api.gpu_modo("gpu")
    ok(st["modo"] == "gpu" and st["efectivo"]["codificar"]["codificador"] == "h264_nvenc", "elegir GPU lo aplica")
    ok(api.gpu_modo("inventado").get("error"), "un modo invalido da error")
    api.cerrar()
    api2 = app.API()
    ok(api2.modo_acel == "gpu", "el modo elegido se recuerda al reabrir", api2.modo_acel)
    api2.cerrar()
    # la deteccion guardada se reutiliza si el equipo es el mismo
    real_detectar = gpu.detectar
    llamadas = []
    gpu.detectar = lambda: llamadas.append(1) or real_detectar()
    try:
        api3 = app.API()
        api3._detectar_gpu()
        n1 = len(llamadas)
        api3._detectar_gpu()
        ok(n1 == 1 and len(llamadas) == 1, "la deteccion se hace una vez y despues se reutiliza (huella igual)", f"{len(llamadas)} llamada(s)")
        t0 = time.time()
        api3._detectar_gpu()
        ok(time.time() - t0 < 5, "y reutilizarla es rapido", f"{time.time() - t0:.1f} s")
        api3.gpu_comprobar()
        time.sleep(0.3)
        t0 = time.time()
        while api3.detectando and time.time() - t0 < 60:
            time.sleep(0.5)
        ok(len(llamadas) == 2, "'Volver a comprobar' fuerza una deteccion nueva", f"{len(llamadas)} llamadas")
        api3.cerrar()
    finally:
        gpu.detectar = real_detectar

    print("=== 8. abrir un video usa la politica elegida ===")
    api = app.API()
    app.crear_servidor(api)
    api.deteccion = nada
    api.modo_acel = "gpu"
    info = api.abrir(h264)
    ok("error" not in info and info["decodifica_con"] in ("gpu", "cpu"), "abrir() informa con que decodifica", info.get("decodifica_con"))
    ok(info["decodifica_con"] == "gpu", "con modo GPU y d3d11va disponible, decodifica por GPU")
    api.modo_acel = "auto"
    info = api.abrir(h264)
    ok(info["decodifica_con"] == "cpu", "con modo Auto en una PC donde la GPU pierde, decodifica por el procesador")
    api.cerrar()

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
