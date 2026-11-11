# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la API de edicion por HTTP (lo que usa la interfaz), sin ventana.

Uso:  python -I pruebas/prueba_edicion_api.py
"""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-edicion-"), "ajustes.json")

import app  # noqa: E402

TMP = tempfile.mkdtemp(prefix="prueba-edicion-api-")
fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


class Cliente:
    def __init__(self, srv):
        self.srv = srv

    def _pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.puerto, timeout=30)
        h = {"Host": "127.0.0.1:%d" % self.srv.puerto}
        h.update(cabeceras or {})
        c.putrequest(metodo, ruta, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        if cuerpo is not None:
            c.putheader("Content-Length", str(len(cuerpo)))
        c.endheaders(cuerpo)
        r = c.getresponse()
        datos = r.read()
        cab = {k.lower(): v for k, v in r.getheaders()}
        c.close()
        return r.status, cab, datos

    def llamar(self, nombre, *args):
        s, _, d = self._pedir("POST", "/%s/api/%s" % (self.srv.token, nombre), json.dumps(list(args)).encode(),
                              {"Content-Type": "application/json"})
        return s, (json.loads(d) if d and d[:1] in b"{[" else d)

    def get(self, ruta, cabeceras=None):
        return self._pedir("GET", ruta, None, cabeceras)


def main():
    video = os.path.join(TMP, "v.mp4")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=10", "-f", "lavfi", "-i", "sine=f=440:d=10",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", video)
    musica = os.path.join(TMP, "musica.mp3")
    ffmpeg("-f", "lavfi", "-i", "sine=f=2000:d=8", "-c:a", "libmp3lame", musica)
    solo_audio = os.path.join(TMP, "voz.wav")
    ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=5", solo_audio)

    api = app.API()
    srv = app.crear_servidor(api)
    c = Cliente(srv)

    print("=== 1. abrir arma el proyecto ===")
    s, r = c.llamar("proyecto_estado")
    ok(s == 200 and "error" in r, "sin nada abierto: error claro, no un 500", r)
    s, info = c.llamar("abrir", video)
    ok("error" not in info, "abre el video")
    s, r = c.llamar("proyecto_estado")
    p = r["proyecto"]
    ok([x["id"] for x in p["pistas"]] == ["V1", "A1"], "el proyecto tiene V1 y A1")
    ok(abs(p["duracion"] - 10.0) < 0.1 and p["fuentes"]["s1"]["nombre"] == "v.mp4", "dura 10 s y conoce el nombre del archivo")
    ok("tiempos" not in p["fuentes"]["s1"], "no manda la tabla de tiempos de cada cuadro (es enorme)")
    ok(p["puede_deshacer"] is False and p["puede_rehacer"] is False, "sin historial")

    print("=== 2. operaciones por HTTP ===")
    s, r = c.llamar("editar_dividir", 4.0)
    ok(s == 200 and "error" not in r and abs(r["resultado"] - 4.0) < 0.04, "dividir devuelve el instante ajustado a cuadro", r.get("resultado"))
    ok(len(r["proyecto"]["pistas"][0]["clips"]) == 2 and r["proyecto"]["puede_deshacer"], "y el proyecto completo, ya con 2 clips")
    s, r = c.llamar("editar_borrar_rango", 1.0, 2.0)
    ok(abs(r["proyecto"]["duracion"] - 9.0) < 0.05, "borrar un tramo: la duracion baja", r["proyecto"]["duracion"])
    s, r = c.llamar("editar_borrar_rango", 3.0, 3.0)
    ok("error" in r and "duración" in r["error"] and "proyecto" in r, "un error trae su mensaje Y el proyecto actual (para que la interfaz se resincronice)", r["error"])
    clip = r["proyecto"]["pistas"][0]["clips"][0]
    s, r = c.llamar("editar_fade", clip["id"], "in", 1.0, "qsin", "blanco")
    ok(r["proyecto"]["pistas"][0]["clips"][0]["fade_in"] == 1.0 and r["proyecto"]["pistas"][0]["clips"][0]["color_fundido"] == "blanco", "fade con curva y color")
    a1 = r["proyecto"]["pistas"][1]["clips"][0]
    s, r = c.llamar("editar_volumen", a1["id"], 0.5)
    ok(r["proyecto"]["pistas"][1]["clips"][0]["volumen"] == 0.5, "volumen")
    s, r = c.llamar("editar_silenciar", "A1", True)
    ok(r["proyecto"]["pistas"][1]["silenciada"] is True, "silenciar")
    s, r = c.llamar("editar_volumen", "c999", 1.0)
    ok("error" in r, "un clip que no existe da error claro", r["error"])
    s, r = c.llamar("editar_volumen", "c1")
    ok("error" in r and "proyecto" in r, "argumentos que faltan: error claro, no un 500", r.get("error"))
    s, r = c.llamar("editar_dividir", "esto no es un numero")
    ok(s == 200 and "error" in r, "argumentos de tipo equivocado: error claro", r.get("error"))
    s, r = c.llamar("editar_borrar_todo")
    ok(s == 404, "una operacion que no existe: 404")
    s, r = c.llamar("editar___class__")
    ok(s == 404, "ni se puede llamar a cualquier atributo del objeto")

    print("=== 3. deshacer y rehacer ===")
    antes = c.llamar("proyecto_estado")[1]["proyecto"]
    c.llamar("editar_deshacer")
    c.llamar("editar_deshacer")
    s, r = c.llamar("editar_rehacer")
    ok(r["proyecto"]["puede_rehacer"] and r["proyecto"]["puede_deshacer"], "deshacer y rehacer funcionan por HTTP")
    c.llamar("editar_rehacer")
    despues = c.llamar("proyecto_estado")[1]["proyecto"]
    ok(despues["pistas"] == antes["pistas"], "rehacer deja el proyecto exactamente como estaba")
    s, r = c.llamar("editar_rehacer")
    ok("error" in r and "rehacer" in r["error"], "no hay mas para rehacer: error claro", r["error"])

    print("=== 4. audio extra ===")
    s, r = c.llamar("agregar_audio", musica, 2.0)
    ok("error" not in r and [x["id"] for x in r["proyecto"]["pistas"]][-1] == "A2", "agregar un mp3 crea la pista A2", r.get("error"))
    fid = r["fuente"]
    f = r["proyecto"]["fuentes"][fid]
    ok(f["tipo"] == "audio" and f["url"].startswith("http://127.0.0.1:") and "/extra/" in f["url"] and f["web_compatible"], "con su URL para la vista previa")
    s, cab, datos = c.get(f["url"].split("%d" % srv.puerto)[1], {"Range": "bytes=0-1023"})
    ok(s == 206 and len(datos) == 1024 and cab["content-type"] == "audio/mpeg", "esa URL sirve el audio con Range", f"{s} {cab.get('content-type')}")
    s, cab, datos = c.get(f["url"].split("%d" % srv.puerto)[1].replace("/extra/", "/extra/XXXX"))
    ok(s == 404, "un token de audio inventado da 404")
    s, cab, datos = c._pedir("GET", f["url"].split("%d" % srv.puerto)[1], None, {"Host": "evil.example.com"})
    ok(s == 421, "y exige Host valido")
    s, r2 = c.llamar("picos_fuente", fid)
    ok(len(r2["picos"]) == 2000 and all(-1 <= x <= 1 for par in r2["picos"] for x in par), "los picos de la onda del audio extra (2000 pares)")
    s, r2 = c.llamar("picos_fuente", "s1")
    ok(len(r2["picos"]) == 2000, "y los de la fuente principal")
    s, r3 = c.llamar("agregar_audio", musica, 3.0)
    ok(r3["fuente"] == fid and [x["id"] for x in r3["proyecto"]["pistas"]][-1] == "A3", "el mismo archivo no se vuelve a leer, y si se superpone va a otra pista")
    s, r3 = c.llamar("agregar_audio", os.path.join(TMP, "no_existe.mp3"), 0)
    ok("error" in r3 and "No encontré" in r3["error"], "un archivo que no existe: error claro", r3["error"])
    basura = os.path.join(TMP, "basura.mp3")
    with open(basura, "wb") as fh:
        fh.write(b"no es audio" * 100)
    s, r3 = c.llamar("agregar_audio", basura, 0)
    ok("error" in r3 and "proyecto" in r3, "un archivo que no es audio: error claro y el proyecto intacto", r3["error"][:70])
    # borrar un tramo del video recorta y corre el audio extra
    n_antes = len(c.llamar("proyecto_estado")[1]["proyecto"]["pistas"][2]["clips"])
    s, r = c.llamar("editar_borrar_rango", 3.0, 5.0)
    ok("error" not in r, "borrar un tramo con audio extra encima")

    print("=== 5. concurrencia: 8 hilos editando a la vez ===")
    c.llamar("abrir", video)
    errores = []

    def trabajar(n):
        import random
        azar = random.Random(n)
        for _ in range(25):
            nombre = azar.choice(["editar_dividir", "editar_borrar_rango", "editar_deshacer", "editar_rehacer"])
            args = {"editar_dividir": [azar.uniform(0.5, 8)], "editar_borrar_rango": [azar.uniform(0, 4), azar.uniform(4, 9)]}.get(nombre, [])
            s, r = c.llamar(nombre, *args)
            if s != 200 or ("proyecto" not in r and "error" not in r):
                errores.append((nombre, s, r))

    hilos = [threading.Thread(target=trabajar, args=(i,)) for i in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    ok(not errores, "200 pedidos concurrentes, todos con respuesta valida", str(errores[:2]))
    problemas = api.proyecto.validar()
    ok(problemas == [] and not api.proyecto._en_transaccion, "y el proyecto queda valido y sin transaccion abierta", str(problemas[:2]))

    print("=== 6. abrir otro archivo reemplaza el proyecto ===")
    s, info = c.llamar("abrir", solo_audio)
    r = c.llamar("proyecto_estado")[1]["proyecto"]
    ok([x["id"] for x in r["pistas"]] == ["A1"] and r["fuentes"]["s1"]["tipo"] == "audio" and not r["puede_deshacer"],
       "un archivo de solo audio arma solo A1 y el historial vuelve a cero")
    s, r = c.llamar("editar_dividir", 2.0)
    ok("error" not in r and len(r["proyecto"]["pistas"][0]["clips"]) == 2, "se puede cortar un audio")
    s, info = c.llamar("abrir", os.path.join(TMP, "basura.mp3"))
    ok("error" in info, "un archivo que falla al abrir...")
    r = c.llamar("proyecto_estado")[1]["proyecto"]
    ok(len(r["pistas"][0]["clips"]) == 2, "...no pierde el proyecto que estaba en edicion")

    print("=== 7. efectos por HTTP ===")
    s, cat = c.llamar("efectos_catalogo")
    ok(s == 200 and {"color_basico", "voltear", "pasa_altos", "eco", "tono"} <= set(cat["efectos"]), "el catalogo de efectos llega completo", str(list(cat.get("efectos", {})))[:80])
    ok(all(d["categoria"] in ("video", "audio") and "params" in d for d in cat["efectos"].values()), "con su categoria y sus ajustes")
    c.llamar("abrir", video)
    pv = c.llamar("proyecto_estado")[1]["proyecto"]
    cid = pv["pistas"][0]["clips"][0]["id"]
    aid = pv["pistas"][1]["clips"][0]["id"]
    s, r = c.llamar("editar_agregar_efecto", cid, "color_basico", {"brillo": 0.2})
    ok(s == 200 and "error" not in r and r["resultado"].startswith("e"), "agregar un efecto devuelve su id", str(r.get("resultado")))
    eid = r["resultado"]
    ok(r["proyecto"]["pistas"][0]["clips"][0]["efectos"][0]["params"]["brillo"] == 0.2, "y el proyecto vuelve con el efecto")
    s, r = c.llamar("editar_agregar_efecto", cid, "pasa_altos")
    ok("error" in r and "proyecto" in r, "un efecto de audio en un clip de video: error claro Y el proyecto completo", r.get("error"))
    s, r = c.llamar("editar_cambiar_efecto", cid, eid, {"brillo": 5})
    ok("error" in r and "rango" not in r["error"] and "va de" in r["error"], "un valor fuera de rango: error que dice el rango", r.get("error"))
    s, r = c.llamar("editar_cambiar_efecto", cid, eid, {"brillo": "mucho"})
    ok("error" in r, "un texto donde va un numero")
    s, r = c.llamar("editar_cambiar_efecto", cid, eid, {"inventado": 1})
    ok("error" in r, "un ajuste que no existe")
    s, r = c.llamar("editar_cambiar_efecto", cid, eid, [1, 2])
    ok("error" in r, "valores que no son un objeto")
    s, r = c.llamar("editar_cambiar_efecto", cid, eid, {"contraste": 1.4})
    ok("error" not in r and r["proyecto"]["pistas"][0]["clips"][0]["efectos"][0]["params"] == {"brillo": 0.2, "contraste": 1.4, "saturacion": 1.0},
       "cambiar un ajuste deja los demas como estaban")
    s, r = c.llamar("editar_agregar_efecto", aid, "pasa_altos", {"frecuencia": 150})
    ok("error" not in r and r["proyecto"]["pistas"][1]["clips"][0]["efectos"][0]["params"]["frecuencia"] == 150, "un efecto de audio en el clip de audio")
    s, r = c.llamar("editar_mover_efecto", cid, eid, -1)
    ok("error" in r, "mover el primero hacia arriba: error claro")
    s, r = c.llamar("editar_activar_efecto", cid, eid, False)
    ok(r["proyecto"]["pistas"][0]["clips"][0]["efectos"][0]["activo"] is False, "apagar")
    s, r = c.llamar("editar_quitar_efecto", cid, eid)
    ok(r["proyecto"]["pistas"][0]["clips"][0]["efectos"] == [], "quitar")
    s, r = c.llamar("editar_deshacer")
    ok(len(r["proyecto"]["pistas"][0]["clips"][0]["efectos"]) == 1, "y deshacer lo devuelve")

    api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
