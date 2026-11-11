# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 11 (motor): tirar de los bordes de un clip (`recortar_borde`) y reordenar, MEDIDO en el video que sale (codigo de barras por cuadro).

La parte de la interfaz (arrastrar con el mouse, zoom, iman) se prueba con la ventana real en prueba_linea_tiempo_app.py.

Uso:  python -I pruebas/prueba_linea_tiempo.py
"""

import json
import os
import random
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402
from motor.proyecto import ErrorEdicion  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def da_error(f, *a, **k):
    try:
        f(*a, **k)
    except ErrorEdicion as e:
        return str(e)
    return None


def grupos(p):
    return [c["grupo"] for c in p.pista("V1")["clips"]]


def dos_clips(src):
    p, _, _ = ex.armar(src)
    p.dividir(6.0)
    return p, grupos(p)


def codigos(p, nombre):
    arch, _ = im.exportar(p, nombre)
    return ex.leer_codigos(arch), arch


def main():
    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=12)

    print("=== 1. acortar el final: lo que sigue se corre ===")
    p, (g1, g2) = dos_clips(src)
    r = p.recortar_borde(g1, "fin", 4.0)
    c1, c2 = p.pista("V1")["clips"]
    a1 = p.pista("A1")["clips"]
    ok(abs(c1["hasta"] - 4.0) < 1e-6 and abs(c2["inicio"] - 4.0) < 1e-6 and abs(p.duracion() - 10.0) < 1e-6 and r["cambio"] == -2.0, "el primer clip pasa a 0-4 s y el segundo se corre de 6 a 4 s (10 s en total)", str(r))
    ok(abs(a1[0]["hasta"] - 4.0) < 1e-6 and abs(a1[1]["inicio"] - 4.0) < 1e-6, "y el audio enlazado hace lo mismo")
    ok(p.validar() == [], "proyecto valido")
    cod, arch = codigos(p, "t_fin_corto")
    ok(len(cod) == 300 and cod[119] == 119 and cod[120] == 180 and not any(120 <= c < 180 for c in cod), "se ve: cuadro 119 -> 180 (se salteo 4 s a 6 s), 300 cuadros", "%s -> %s" % (cod[119], cod[120]))
    ok(abs(len(ex.muestras(arch)) / 48000.0 - 10.0) < 0.1, "y el audio dura lo mismo (10 s)")
    p.deshacer()
    ok(abs(p.duracion() - 12.0) < 1e-6 and p.validar() == [], "Deshacer lo devuelve en un paso")

    print("=== 2. alargar el final: usa el material que sobra ===")
    p, (g1, g2) = dos_clips(src)
    p.recortar_borde(g1, "fin", 4.0)
    p.recortar_borde(g1, "fin", 5.0)
    c1, c2 = p.pista("V1")["clips"]
    ok(abs(c1["hasta"] - 5.0) < 1e-6 and abs(c2["inicio"] - 5.0) < 1e-6 and abs(p.duracion() - 11.0) < 1e-6, "estirarlo de 4 a 5 s trae el segundo 4-5 de la fuente y vuelve a correr lo que sigue")
    cod, _ = codigos(p, "t_fin_largo")
    ok(len(cod) == 330 and cod[149] == 149 and cod[150] == 180, "cuadro 149 -> 180: el cuadro 120-149 volvio a aparecer")
    ok(da_error(p.recortar_borde, g2, "fin", 99.0) is not None, "mas alla de lo que tiene la fuente: error claro (no hay mas material)", da_error(p.recortar_borde, g2, "fin", 99.0))
    p.recortar_borde(g1, "fin", 11.0)
    ok(abs(p.pista("V1")["clips"][0]["hasta"] - 12.0) < 1e-6 or abs(p.pista("V1")["clips"][0]["hasta"] - 11.0) < 1e-6, "se puede estirar hasta el final de la fuente (el borde pedido se ajusta)")
    ok(p.validar() == [], "proyecto valido")

    print("=== 3. el inicio ===")
    p, (g1, g2) = dos_clips(src)
    p.recortar_borde(g2, "inicio", 8.0)
    c1, c2 = p.pista("V1")["clips"]
    ok(abs(c2["desde"] - 8.0) < 1e-6 and abs(c2["inicio"] - 6.0) < 1e-6 and abs(p.duracion() - 10.0) < 1e-6, "acortar el inicio del segundo clip: sigue empezando en 6 s pero ahora muestra desde el segundo 8 (dura 10 s en total)")
    cod, _ = codigos(p, "t_ini_corto")
    ok(len(cod) == 300 and cod[179] == 179 and cod[180] == 240, "cuadro 179 -> 240")
    p.recortar_borde(g2, "inicio", 3.0)          # el borde estaba en 6 s: tirar 3 s hacia atras = 3 s mas de material (desde 8 -> 5)
    c2 = p.pista("V1")["clips"][1]
    ok(abs(c2["desde"] - 5.0) < 1e-6 and abs(p.duracion() - 13.0) < 1e-6, "estirar el inicio hacia atras trae material de antes (desde 5 s): 13 s en total")
    cod, _ = codigos(p, "t_ini_largo")
    ok(len(cod) == 390 and cod[180] == 150, "cuadro 180 -> 150")
    ok(da_error(p.recortar_borde, g1, "inicio", -3.0) is not None or p.pista("V1")["clips"][0]["desde"] == 0.0, "no se puede estirar el inicio del primero mas alla del principio de la fuente")
    ok(p.validar() == [], "proyecto valido")

    print("=== 4. velocidad y reversa ===")
    p, (g1, g2) = dos_clips(src)
    p.velocidad(g1, 2.0)                       # el primero dura 3 s en la linea de tiempo
    p.recortar_borde(g1, "fin", 2.0)           # dejarlo en 2 s de linea = 4 s de fuente
    c1 = p.pista("V1")["clips"][0]
    ok(abs(c1["hasta"] - 4.0) < 1e-6 and abs(p.largo(c1) - 2.0) < 1e-6 and abs(p.pista("V1")["clips"][1]["inicio"] - 2.0) < 1e-6, "con velocidad 2x: 2 s de linea de tiempo son 4 s de fuente", str((c1["hasta"], p.largo(c1))))
    p, (g1, g2) = dos_clips(src)
    p.reversa(g1, True)
    p.recortar_borde(g1, "fin", 4.0)           # al reves, el FINAL de la linea de tiempo es el INICIO de la fuente
    c1 = p.pista("V1")["clips"][0]
    ok(abs(c1["desde"] - 2.0) < 1e-6 and abs(c1["hasta"] - 6.0) < 1e-6, "al reves: acortar el final saca material del inicio de la fuente (desde 2 s)", str((c1["desde"], c1["hasta"])))
    p.recortar_borde(g1, "inicio", 1.0)
    c1 = p.pista("V1")["clips"][0]
    ok(abs(c1["hasta"] - 5.0) < 1e-6 and p.validar() == [], "y acortar el inicio saca del final de la fuente (hasta 5 s)", str((c1["desde"], c1["hasta"])))
    cod, _ = codigos(p, "t_reversa")
    ok(cod[0] == 149 and cod[-1] == 359, "se ve el primer clip al reves (empieza en el cuadro 149) y el segundo normal hasta el 359", "%s ... %s" % (cod[0], cod[-1]))

    print("=== 5. un audio suelto (musica): nada mas se mueve ===")
    p, (g1, g2) = dos_clips(src)
    musica = ex.crear_musica(os.path.join(TMP, "m.mp3"), 8, 2000)
    cid = ex.agregar_audio_archivo(p, musica, inicio=2.0)
    g_m = p.clip(cid)[1]["grupo"]
    antes = [(c["id"], c["inicio"]) for pp in p.pistas for c in pp["clips"] if c["id"] != cid]
    p.recortar_borde(g_m, "inicio", 3.0)
    m = p.clip(cid)[1]
    ok(abs(m["inicio"] - 3.0) < 1e-6 and abs(m["desde"] - 1.0) < 1e-6, "acortar el inicio de la musica: empieza 1 s mas tarde y el sonido queda en el mismo lugar (desde 1 s)", str((m["inicio"], m["desde"])))
    p.recortar_borde(g_m, "fin", 6.0)
    m = p.clip(cid)[1]
    ok(abs(p.fin(m) - 6.0) < 1e-6 and abs(m["hasta"] - 4.0) < 1e-6, "acortar el final: termina a los 6 s")
    ok([(c["id"], c["inicio"]) for pp in p.pistas for c in pp["clips"] if c["id"] != cid] == antes and p.validar() == [], "el video y su audio no se movieron")
    p.recortar_borde(g_m, "inicio", 1.0)
    ok(abs(p.clip(cid)[1]["inicio"] - 2.0) < 1e-6 and abs(p.clip(cid)[1]["desde"] - 0.0) < 1e-6, "estirar el inicio hacia atras la hace empezar antes, hasta donde llega el material (solo sobraba 1 s)")
    e = da_error(p.recortar_borde, g_m, "inicio", -5.0)
    ok(p.validar() == [], "no empezar antes del principio: no rompe nada", e)

    print("=== 6. errores ===")
    p, (g1, g2) = dos_clips(src)
    for malo, args in (("un borde que no existe", (g1, "medio", 3.0)), ("un tiempo que no es numero", (g1, "fin", "3")), ("NaN", (g1, "fin", float("nan"))), ("infinito", (g1, "fin", float("inf"))),
                       ("un clip que no existe", ("g999", "fin", 3.0)), ("dejarlo casi sin duracion", (g1, "fin", 0.01)), ("sin cambiar nada", (g1, "fin", 6.0)), ("un booleano", (g1, "fin", True))):
        antes = (json.dumps(p.pistas, sort_keys=True), p.duracion())
        e = da_error(p.recortar_borde, *args)
        ok(e is not None and (json.dumps(p.pistas, sort_keys=True), p.duracion()) == antes, "recortar_borde con " + malo + ": error claro y no cambia nada", e)

    print("=== 7. transiciones y fundidos ===")
    p, (g1, g2) = dos_clips(src)
    # que el primero deje material sobrante para poder poner una transicion
    p.recortar_borde(g1, "fin", 5.0)
    p.recortar_borde(g2, "inicio", 7.0)
    g2 = grupos(p)[1]
    p.poner_transicion(g2, "disolver", 0.8)
    ok(p.pista("V1")["clips"][1]["transicion"] is not None and p.validar() == [], "(con material de sobra a los lados se pone una transicion)")
    p.recortar_borde(g2, "inicio", p.pista("V1")["clips"][1]["inicio"] - 7.7)       # se estira hasta casi el principio de la fuente: ya no sobra material y la transicion no cabe
    ok(p.pista("V1")["clips"][1]["transicion"] is None and p.validar() == [], "si al estirar la transicion ya no cabe, se saca sola (y el proyecto sigue valido)")
    p, (g1, g2) = dos_clips(src)
    p.fade(p.pista("V1")["clips"][0]["id"], "out", 2.0)
    p.recortar_borde(g1, "fin", 1.0)
    ok(p.pista("V1")["clips"][0]["fade_out"] <= 1.0 + 1e-6 and p.validar() == [], "un fundido mas largo que el clip nuevo se acota")

    print("=== 8. historial y subtitulos ===")
    p, (g1, g2) = dos_clips(src)
    p.subtitulo_agregar(1.0, 2.0, "uno")
    n = len(p._deshacer)
    p.recortar_borde(g1, "fin", 4.0)
    ok(len(p._deshacer) == n + 1 and p.a_dict()["subtitulos_desactualizados"] is True, "un solo paso de deshacer, y los subtitulos quedan marcados como desactualizados (el montaje cambio)")
    p.deshacer()
    ok(p.a_dict()["subtitulos_desactualizados"] is False and p.validar() == [], "deshacer los deja al dia")

    print("=== 9. al azar ===")
    malos = []
    musica2 = ex.crear_musica(os.path.join(TMP, "m2.mp3"), 5, 1500)
    for semilla in range(200):
        azar = random.Random(semilla)
        z, _, _ = ex.armar(src)
        for paso in range(30):
            op = azar.choice(["borde", "borde", "borde", "dividir", "velocidad", "reversa", "borrar", "mover", "musica", "deshacer", "rehacer", "transicion"])
            antes = (json.dumps(z.pistas, sort_keys=True), json.dumps(z._n, sort_keys=True))
            try:
                gs = sorted({c["grupo"] for pp in z.pistas for c in pp["clips"]})
                if op == "borde" and gs:
                    z.recortar_borde(azar.choice(gs), azar.choice(["inicio", "fin"]), azar.uniform(-1, z.duracion() + 3))
                elif op == "dividir" and z.duracion() > 1:
                    z.dividir(azar.uniform(0, z.duracion()))
                elif op == "velocidad" and grupos(z):
                    z.velocidad(azar.choice(grupos(z)), azar.choice([0.5, 1.0, 2.0]))
                elif op == "reversa" and grupos(z):
                    z.reversa(azar.choice(grupos(z)), azar.choice([True, False]))
                elif op == "borrar" and z.duracion() > 2:
                    t0 = azar.uniform(0, z.duracion() - 1)
                    z.borrar_rango(t0, t0 + azar.uniform(0.2, 1.5))
                elif op == "mover" and len(grupos(z)) > 1:
                    z.mover_grupo(azar.choice(grupos(z)), azar.uniform(0, z.duracion()))
                elif op == "musica":
                    ex.agregar_audio_archivo(z, musica2, inicio=azar.uniform(0, 8))
                elif op == "deshacer":
                    z.deshacer()
                elif op == "rehacer":
                    z.rehacer()
                elif op == "transicion" and len(grupos(z)) > 1:
                    z.poner_transicion(azar.choice(grupos(z)[1:]), "disolver", azar.uniform(0.2, 1.0))
            except ErrorEdicion:
                if (json.dumps(z.pistas, sort_keys=True), json.dumps(z._n, sort_keys=True)) != antes:
                    malos.append((semilla, paso, op, "un error dejo el estado cambiado"))
                    break
                continue
            m = z.validar()
            if m:
                malos.append((semilla, paso, op, m[:2]))
                break
    ok(not malos, "200 secuencias al azar con bordes, cortes, velocidad, reversa, musica, transiciones y deshacer: siempre valido y un error no deja nada a medias", str(malos[:3]))

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
