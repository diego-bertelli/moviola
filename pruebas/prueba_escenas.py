# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 5 (deteccion): cambios de escena, tramos negros y tramos congelados.

Uso:  python -I pruebas/prueba_escenas.py

Se arma un video con tramos que se conocen al milisegundo (movimiento 0-2 s, negro 2-3,5 s, movimiento de otro color 3,5-5,5 s,
imagen congelada 5,5-7,5 s) y se comprueba lo que se encuentra, en la fuente y en una linea de tiempo ya editada (cortes, velocidad, reversa).
"""

import os
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

import prueba_exportar as ex  # noqa: E402
from motor import escenas  # noqa: E402
from motor.proyecto import ErrorEdicion  # noqa: E402

ok = ex.ok


def cerca(lista, valor, tol=0.15):
    return any(abs(x - valor) <= tol for x in lista)


def tramo(lista, a, b, tol=0.2):
    return any(abs(x["inicio"] - a) <= tol and abs(x["fin"] - b) <= tol for x in lista)


def main():
    video = os.path.join(ex.TMP, "escenas.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=1.5",
              "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2,hue=h=120,negate", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=0.04,loop=loop=49:size=1",
              "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0,format=yuv420p[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", video)
    p, fid, _ = ex.armar(video)
    print("=== 1. en el video entero ===")
    r = escenas.analizar(p)
    print("      ", r)
    ok(abs(r["duracion"] - 7.5) < 0.1, "la duracion es la de la linea de tiempo", str(r["duracion"]))
    ok(cerca(r["escenas"], 2.0) and cerca(r["escenas"], 3.5), "cambios de escena: al entrar y al salir del negro (2 s y 3,5 s)", str(r["escenas"]))
    ok(tramo(r["negros"], 2.0, 3.5), "tramo negro: 2 s a 3,5 s", str(r["negros"]))
    ok(tramo(r["congelados"], 5.5, 7.5, 0.3), "tramo congelado: la imagen quieta de 5,5 s al final (7,5 s)", str(r["congelados"]))
    ok(not any(x["fin"] < 1.9 for x in r["congelados"]) and not any(x["inicio"] > 7.0 and x["inicio"] < 5.0 for x in r["congelados"]),
       "y el tramo con movimiento (0 a 2 s) NO se marca como congelado")
    only = escenas.analizar(p, ["negros"])
    ok(only["escenas"] == [] and only["congelados"] == [] and tramo(only["negros"], 2.0, 3.5), "se puede pedir solo una cosa")
    alto = escenas.analizar(p, ["escenas"], 60.0)
    bajo = escenas.analizar(p, ["escenas"], 3.0)
    ok(len(alto["escenas"]) <= len(r["escenas"]) <= len(bajo["escenas"]), "mas sensibilidad (numero chico) encuentra mas o igual cantidad de cambios", f"{len(alto['escenas'])} <= {len(r['escenas'])} <= {len(bajo['escenas'])}")
    n = len(p.pista("V1")["clips"])
    cortes = r["escenas"]
    hechos = p.dividir_varios(cortes)
    ok(hechos == len(cortes) and len(p.pista("V1")["clips"]) == n + hechos and p.validar() == [], "cortar en los cambios de escena deja un clip por tramo, valido", f"{hechos} cortes")
    p.deshacer()
    # sacar el negro con borrar_rangos
    p.borrar_rangos([(x["inicio"], x["fin"]) for x in r["negros"]])
    ok(abs(p.duracion() - 6.0) < 0.1 and p.validar() == [], "sacar el tramo negro acorta el video 1,5 s", str(p.duracion()))
    p.deshacer()

    print("=== 2. en una linea de tiempo editada ===")
    q, _, _ = ex.armar(video)
    q.borrar_rango(0.0, 1.0)                       # todo se corre 1 s a la izquierda
    r2 = escenas.analizar(q)
    ok(tramo(r2["negros"], 1.0, 2.5) and cerca(r2["escenas"], 1.0) and cerca(r2["escenas"], 2.5), "con el principio cortado todo se corre 1 s", f"{r2['negros']} {r2['escenas']}")
    ok(not cerca(r2["escenas"], 2.0 - 1.0 + 5.0), "(sin resultados fantasma)")
    q, _, _ = ex.armar(video)
    q.velocidad(q.pista("V1")["clips"][0]["grupo"], 2.0)
    r3 = escenas.analizar(q, ["negros", "escenas"])
    ok(tramo(r3["negros"], 1.0, 1.75) and abs(r3["duracion"] - 3.75) < 0.1, "a 2x el negro (2 a 3,5 s de la fuente) cae en 1 a 1,75 s de la linea de tiempo", str(r3["negros"]))
    q, _, _ = ex.armar(video)
    q.reversa(q.pista("V1")["clips"][0]["grupo"])
    r4 = escenas.analizar(q, ["negros"])
    ok(tramo(r4["negros"], 7.5 - 3.5, 7.5 - 2.0), "al reves el negro se lee desde el otro lado (7,5 - 3,5 = 4 a 7,5 - 2 = 5,5)", str(r4["negros"]))
    q, _, _ = ex.armar(video)
    q.dividir(4.0)
    q.borrar_rango(2.0, 3.0)                       # sale 1 s del negro
    r5 = escenas.analizar(q, ["negros"])
    ok(tramo(r5["negros"], 2.0, 2.5), "con un pedazo del negro ya cortado queda el resto, unido a los dos lados del corte", str(r5["negros"]))

    print("=== 3. errores ===")
    for malo, kw in (("una cosa que no se busca", {"que": ["rostros"]}), ("nada para buscar", {"que": []}), ("sensibilidad 0", {"umbral_escena": 0}),
                     ("negro de 0 s", {"negro_min": 0}), ("congelado de 100 s", {"congelado_min": 100})):
        try:
            escenas.analizar(p, **kw)
            ok(False, malo + " se rechaza")
        except escenas.ErrorEscena as e:
            ok(True, malo + ": error claro", str(e))
    audio = os.path.join(ex.TMP, "solo_audio.mp3")
    ex.crear_musica(audio, 3)
    from motor.proyecto import Proyecto
    pa = Proyecto()
    try:
        escenas.analizar(pa)
        ok(False, "un proyecto vacio se rechaza")
    except escenas.ErrorEscena as e:
        ok("no tiene video" in str(e), "un proyecto sin video: error claro", str(e))
    ev = threading.Event()
    ev.set()
    try:
        escenas.analizar(p, cancelar=ev)
        ok(False, "cancelar corta el analisis")
    except Exception as e:
        ok(type(e).__name__ == "Cancelado", "cancelar corta el analisis", type(e).__name__)

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
