# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la API de exportacion por HTTP (lo que usa el dialogo de la interfaz), sin ventana.

Uso:  python -I pruebas/prueba_exportar_api.py
"""

import http.client
import json
import os
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-exportar-api-"), "ajustes.json")

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


class Cliente:
    def __init__(self, srv):
        self.srv = srv

    def llamar(self, nombre, *args):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.puerto, timeout=60)
        c.putrequest("POST", "/%s/api/%s" % (self.srv.token, nombre), skip_host=True)
        cuerpo = json.dumps(list(args)).encode()
        for k, v in {"Host": "127.0.0.1:%d" % self.srv.puerto, "Content-Type": "application/json",
                     "Content-Length": str(len(cuerpo))}.items():
            c.putheader(k, v)
        c.endheaders(cuerpo)
        r = c.getresponse()
        d = r.read()
        c.close()
        return r.status, (json.loads(d) if d[:1] in b"{[" else d)

    def esperar(self, estados, tiempo=120):
        t0 = time.time()
        vistos = []
        while time.time() - t0 < tiempo:
            _, e = self.llamar("exportar_estado")
            vistos.append(e.get("progreso", 0))
            if e["estado"] in estados:
                return e, vistos
            time.sleep(0.15)
        return e, vistos


def main():
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"))
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(), "cache")
    srv = app.crear_servidor(api)
    c = Cliente(srv)
    carpeta = os.path.join(ex.TMP, "destino")
    os.makedirs(carpeta)

    print("=== 1. opciones y nombres ===")
    s, r = c.llamar("exportar_opciones")
    ok(s == 200 and "error" in r, "sin nada abierto: error claro", r)
    c.llamar("abrir", src)
    c.llamar("editar_borrar_rango", 3.0, 5.0)
    s, o = c.llamar("exportar_opciones")
    ok(o["tiene_video"] and o["tiene_audio"] and abs(o["duracion"] - 10.0) < 0.1, "el proyecto editado: dura 10 s, con video y audio", str(o))
    ok(o["nombre"] == "src" and o["carpeta"] == os.path.dirname(src), "propone la carpeta y el nombre del archivo original")
    s, d = c.llamar("exportar_destino", carpeta, "mi video", "vertical")
    ok(os.path.basename(d["archivo"]) == "mi video-v1.mp4", "el nombre propuesto: nombre-v1.mp4", d["archivo"])
    s, d = c.llamar("exportar_destino", carpeta, "x", "flac")
    ok(d["archivo"].endswith("x-v1.flac"), "y con la extension del formato de audio")
    s, d = c.llamar("exportar_destino", carpeta, "x", "avi")
    ok("error" in d, "un formato desconocido da error")

    print("=== 2. exportar un video vertical ===")
    s, r = c.llamar("exportar_iniciar", {"formato": "vertical", "encuadre": "recortar", "foco": [0.5, 0.5], "normalizar": False,
                                         "carpeta": carpeta, "nombre": "reel"})
    ok(r == {"ok": True}, "arranca")
    e, vistos = c.esperar({"listo", "error", "cancelado"})
    ok(e["estado"] == "listo", "termina bien", e.get("error"))
    ok(all(b >= a for a, b in zip(vistos, vistos[1:])) and e["progreso"] == 1.0, "el progreso sube sin retroceder", f"{len(vistos)} lecturas")
    ok(os.path.isfile(e["archivo"]) and e["nombre"] == "reel-v1.mp4", "el archivo existe y se llama reel-v1.mp4", e.get("nombre"))
    ok(e["dimensiones"] == [1080, 1920] and abs(e["duracion"] - 10.0) < 0.15, "1080x1920 y 10 s", f"{e['dimensiones']} {e['duracion']}")
    ok(e["tamano_bytes"] > 10000 and e["respaldo"] is False, "con su tamano y sin respaldo de GPU")
    with ex.Video(src) as v_:
        tiempos = v_.tabla_tiempos()
    codigos = ex.leer_codigos(e["archivo"], lambda x, y: (x * 1920 / 360 - (640 * 1920 / 360 - 1080) / 2, y * 1920 / 360))
    ok(codigos == ex.esperados(api.proyecto, tiempos), "y los cuadros son exactamente los del proyecto editado", f"{len(codigos)} cuadros")
    s, r = c.llamar("exportar_iniciar", {"formato": "vertical", "carpeta": carpeta, "nombre": "reel"})
    e2, _ = c.esperar({"listo", "error"})
    ok(e2["nombre"] == "reel-v2.mp4", "exportar de nuevo no pisa nada: reel-v2.mp4", e2.get("nombre"))

    print("=== 3. solo audio y normalizar ===")
    c.llamar("exportar_iniciar", {"formato": "wav", "normalizar": True, "carpeta": carpeta, "nombre": "voz"})
    e, _ = c.esperar({"listo", "error"})
    ok(e["estado"] == "listo" and e["nombre"] == "voz-v1.wav" and e["normalizado"] is True and e["dimensiones"] is None,
       "un WAV normalizado a -14 LUFS", str(e.get("error") or e.get("nombre")))

    print("=== 4. opciones invalidas: errores claros, nada arranca ===")
    for etiqueta, op in (("formato desconocido", {"formato": "avi", "carpeta": carpeta}),
                         ("carpeta que no existe", {"formato": "wav", "carpeta": os.path.join(ex.TMP, "no_existe")}),
                         ("una carpeta que es un archivo", {"formato": "wav", "carpeta": src}),
                         ("foco que no es un numero", {"formato": "vertical", "carpeta": carpeta, "foco": ["a", "b"]}),
                         ("opciones que no son un objeto", "esto no es un objeto")):
        s, r = c.llamar("exportar_iniciar", op)
        ok(s == 200 and "error" in r, f"{etiqueta}: error claro", r.get("error"))
    ok(c.llamar("exportar_estado")[1]["estado"] == "listo", "y el estado no cambio (sigue el de la ultima exportacion)")
    original = app.tempfile.NamedTemporaryFile
    app.tempfile.NamedTemporaryFile = lambda *a, **k: (_ for _ in ()).throw(PermissionError("sin permiso"))
    try:
        s, r = c.llamar("exportar_iniciar", {"formato": "wav", "carpeta": carpeta})
    finally:
        app.tempfile.NamedTemporaryFile = original
    ok("error" in r and "escribir" in r["error"], "una carpeta donde no se puede escribir: error claro", r.get("error"))

    print("=== 5. un trabajo a la vez, cancelar, y editar mientras exporta ===")
    largo = ex.crear_fuente(os.path.join(ex.TMP, "largo.mp4"), dur=60, w=1280, h=720)
    c.llamar("abrir", largo)
    s, r = c.llamar("exportar_iniciar", {"formato": "vertical", "carpeta": carpeta, "nombre": "largo"})
    ok(r == {"ok": True}, "arranca una exportacion larga")
    time.sleep(0.8)
    s, r2 = c.llamar("exportar_iniciar", {"formato": "wav", "carpeta": carpeta, "nombre": "otra"})
    ok("error" in r2 and "en curso" in r2["error"], "una segunda mientras tanto se rechaza", r2.get("error"))
    s, _ = c.llamar("exportar_cancelar")
    e, _ = c.esperar({"cancelado", "listo", "error"}, 60)
    ok(e["estado"] == "cancelado", "cancelar la corta", e["estado"])
    ok(not [n for n in os.listdir(carpeta) if "largo" in n or "parcial" in n or n.startswith(".moviola")], "y no deja archivos a medias", str(os.listdir(carpeta)))
    s, r = c.llamar("exportar_iniciar", {"formato": "vertical", "carpeta": carpeta, "nombre": "largo"})
    time.sleep(0.8)
    c.llamar("editar_borrar_rango", 0.0, 30.0)                 # se edita MIENTRAS se exporta
    e, _ = c.esperar({"listo", "error"}, 120)
    ok(e["estado"] == "listo" and abs(e["duracion"] - 60.0) < 0.3, "editar mientras se exporta NO cambia lo exportado (copia del proyecto del momento)", f"{e.get('duracion')} s")
    ok(abs(api.proyecto.duracion() - 30.0) < 0.1, "y el proyecto en pantalla si quedo editado", api.proyecto.duracion())

    print("=== 6. mostrar en la carpeta ===")
    llamados = []
    real = app.subprocess.Popen
    app.subprocess.Popen = lambda cmd, *a, **k: llamados.append(cmd) or None
    try:
        s, r = c.llamar("mostrar_en_carpeta")
        s2, r2 = c.llamar("mostrar_en_carpeta", "C:\\Windows\\System32\\cmd.exe")
    finally:
        app.subprocess.Popen = real
    ok(r == {"ok": True} and llamados and llamados[0][0] == "explorer" and llamados[0][1] == "/select," and llamados[0][2].endswith("largo-v1.mp4"),
       "abre el explorador con el ultimo archivo exportado seleccionado", str(llamados[:1]))
    ok(len(llamados) == 1, "y si la interfaz le pasa una ruta cualquiera NO la abre (no acepta rutas)", f"{len(llamados)} llamada(s), estado {s2}")

    print("=== 7. GPU: solo si se eligio de forma explicita ===")
    import prueba_gpu_app as pg
    api.deteccion = pg.nvidia_que_anda()
    api.modo_acel = "auto"
    api.proyecto.recortar_a(0.0, 2.0)
    c.llamar("exportar_iniciar", {"formato": "horizontal", "carpeta": carpeta, "nombre": "auto"})
    e, _ = c.esperar({"listo", "error"})
    ok(e["estado"] == "listo" and e["respaldo"] is False, "en modo Automatico se exporta con el procesador (calidad): no intenta la GPU")
    api.modo_acel = "gpu"
    c.llamar("exportar_iniciar", {"formato": "horizontal", "carpeta": carpeta, "nombre": "gpu"})
    e, _ = c.esperar({"listo", "error"})
    ok(e["estado"] == "listo" and e["respaldo"] is True and "no funcionó" in e["motivo_respaldo"],
       "en modo GPU intenta NVENC (que aca falla de verdad), exporta con el procesador y avisa", e.get("motivo_respaldo"))

    print("=== 8. un proyecto sin audio ===")
    sin = ex.crear_fuente(os.path.join(ex.TMP, "sin.mp4"), dur=3, tono=False)
    c.llamar("abrir", sin)
    s, o = c.llamar("exportar_opciones")
    ok(o["tiene_video"] and not o["tiene_audio"], "se sabe que no tiene audio (para no ofrecer formatos de audio)")
    c.llamar("exportar_iniciar", {"formato": "wav", "carpeta": carpeta, "nombre": "mudo"})
    e, _ = c.esperar({"listo", "error"})
    ok(e["estado"] == "error" and "audio" in e["error"].lower(), "pedir audio de algo mudo da un error claro", e.get("error"))

    api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
