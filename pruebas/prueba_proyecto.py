# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del modelo de edicion (motor/proyecto.py). Sin ffmpeg ni interfaz.

Uso:  python -I pruebas/prueba_proyecto.py

Casos concretos, y pruebas de PROPIEDADES: miles de secuencias al azar de operaciones donde, despues
de cada una, el proyecto tiene que seguir siendo valido y la sincronia entre video y audio intacta.
"""

import copy
import json
import os
import random
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from motor.proyecto import Proyecto, ErrorEdicion  # noqa: E402
from motor import efectos  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def da_error(f, *a, **k):
    try:
        f(*a, **k)
    except ErrorEdicion as e:
        return str(e)
    return None


def cfr(n=300, fps=30.0):
    return [i / fps for i in range(n)]


def vfr():
    """Tiempos irregulares, como un video de pantalla: pasos de 28 a 96 ms y una pausa de 2,4 s."""
    azar = random.Random(11)
    t, out = 0.0, []
    for i in range(400):
        out.append(round(t, 6))
        t += azar.choice([0.028, 0.033, 0.036, 0.045, 0.057, 0.096])
        if i == 200:
            t += 2.4
    return out, round(t, 6)


def nuevo(tiempos=None, dur=None, pistas_audio=1, tipo="video"):
    p = Proyecto()
    tiempos = cfr() if tiempos is None else tiempos
    dur = dur if dur is not None else round(tiempos[-1] + (tiempos[1] - tiempos[0]), 6)
    fid = p.agregar_fuente("x.mp4", tipo, dur, tiempos if tipo == "video" else None, pistas_audio)
    p.nuevo_desde_fuente(fid)
    return p, fid


def estado(p):
    d = p.a_dict()
    return {k: d[k] for k in ("pistas", "duracion", "salida")}


def main():
    print("=== 1. arranque desde una fuente ===")
    p, fid = nuevo()
    ok([x["id"] for x in p.pistas] == ["V1", "A1"], "V1 (video) y A1 (audio)")
    v, a = p.pistas[0]["clips"][0], p.pistas[1]["clips"][0]
    ok(v["grupo"] == a["grupo"], "video y audio quedan enlazados")
    ok(p.duracion() == 10.0 and p.validar() == [], "dura 10 s y es valido", p.validar())
    ok(not p.puede_deshacer(), "sin historial todavia")
    pa, fa = nuevo(None, 6.0, 1, "audio")
    ok([x["id"] for x in pa.pistas] == ["A1"], "un archivo de audio arma solo A1")
    sin_audio = Proyecto()
    f = sin_audio.agregar_fuente("m.mp4", "video", 3.0, cfr(90), 0)
    sin_audio.nuevo_desde_fuente(f)
    ok([x["id"] for x in sin_audio.pistas] == ["V1"], "un video sin audio arma solo V1")

    print("=== 2. dividir ===")
    p, fid = nuevo()
    t = p.dividir(3.0123)
    ok(abs(t - 3.0) < 1e-6 or abs(t - 3.033333) < 1e-5, "el corte cae en un limite de cuadro", t)
    ok(len(p.pistas[0]["clips"]) == 2 and len(p.pistas[1]["clips"]) == 2, "cada pista queda con 2 clips")
    v0, v1 = p.pistas[0]["clips"]
    a0, a1 = p.pistas[1]["clips"]
    ok(v0["grupo"] == a0["grupo"] and v1["grupo"] == a1["grupo"] and v0["grupo"] != v1["grupo"],
       "video y audio siguen enlazados de cada lado del corte")
    ok(v0["hasta"] == v1["desde"] == a0["hasta"] == a1["desde"], "el corte es el mismo instante de la fuente en las dos pistas")
    ok(p.validar() == [], "valido", p.validar())
    ok(da_error(p.dividir, t) is not None, "cortar donde ya hay un corte da un error claro", da_error(p.dividir, t))
    ok(da_error(p.dividir, 0.0) is not None and da_error(p.dividir, 10.0) is not None, "cortar en los bordes tambien")
    ok(da_error(p.dividir, 1.0, v0["grupo"]) is None, "se puede cortar solo un grupo")

    print("=== 3. borrar un tramo cierra el hueco en todas las pistas ===")
    p, fid = nuevo()
    r = p.borrar_rango(2.0, 4.0)
    ok(abs(p.duracion() - 8.0) < 1e-6, "el proyecto dura 2 s menos", p.duracion())
    for pid in ("V1", "A1"):
        cs = p.pista(pid)["clips"]
        ok(len(cs) == 2 and abs(cs[0]["hasta"] - 2.0) < 1e-6 and abs(cs[1]["desde"] - 4.0) < 1e-6 and abs(cs[1]["inicio"] - 2.0) < 1e-6,
           f"{pid}: queda [0-2] y [4-10] pegados", [(c["desde"], c["hasta"], c["inicio"]) for c in cs])
    ok(p.validar() == [], "valido", p.validar())
    ok(abs(r["duracion"] - 2.0) < 1e-6, "informa cuanto saco", r)
    # un tramo con valores que no caen en cuadro
    p, fid = nuevo()
    p.borrar_rango(1.0049, 2.0211)
    cs = p.pista("V1")["clips"]
    ok(p.validar() == [], "con valores sueltos tambien queda valido (se ajusta a cuadros)", p.validar())
    ok(abs(p.duracion() - (10.0 - (cs[1]["desde"] - cs[0]["hasta"]))) < 1e-5, "la duracion cierra con lo borrado")
    p, fid = nuevo()
    ok(da_error(p.borrar_rango, 3.0, 3.0) is not None, "un tramo vacio da error")
    ok(da_error(p.borrar_rango, 3.0, 3.00001) is not None, "uno de menos de un cuadro tambien")
    p.borrar_rango(8.0, 99.0)
    ok(abs(p.duracion() - 8.0) < 1e-6, "pasarse del final se recorta al final")
    p.borrar_rango(-5.0, 1.0)
    ok(abs(p.duracion() - 7.0) < 1e-6 and p.validar() == [], "pasarse del principio tambien")
    p, fid = nuevo()
    p.dividir(5.0)
    g = p.pista("V1")["clips"][1]["grupo"]
    p.borrar_grupo(g)
    ok(abs(p.duracion() - 5.0) < 1e-6 and len(p.pista("V1")["clips"]) == 1 and len(p.pista("A1")["clips"]) == 1,
       "borrar un clip se lleva tambien su audio")
    p, fid = nuevo()
    p.recortar_a(2.0, 6.0)
    ok(abs(p.duracion() - 4.0) < 1e-6 and abs(p.pista("V1")["clips"][0]["desde"] - 2.0) < 1e-6 and p.validar() == [],
       "recortar_a se queda solo con el tramo elegido")

    print("=== 4. deshacer y rehacer ===")
    p, fid = nuevo()
    s0 = estado(p)
    p.dividir(3.0)
    s1 = estado(p)
    p.borrar_rango(1.0, 2.0)
    s2 = estado(p)
    p.fade(p.pista("V1")["clips"][0]["id"], "in", 0.5)
    s3 = estado(p)
    p.deshacer()
    ok(estado(p) == s2, "deshacer el fundido vuelve al estado exacto anterior")
    p.deshacer()
    ok(estado(p) == s1, "deshacer el borrado")
    p.deshacer()
    ok(estado(p) == s0 and not p.puede_deshacer(), "deshacer el corte: queda como al principio")
    ok(da_error(p.deshacer) is not None, "no hay mas para deshacer: error claro")
    p.rehacer()
    p.rehacer()
    p.rehacer()
    ok(estado(p) == s3 and not p.puede_rehacer(), "rehacer 3 veces recupera todo")
    ok(da_error(p.rehacer) is not None, "y no hay mas para rehacer")
    p.deshacer()
    p.dividir(8.0)
    ok(not p.puede_rehacer(), "una operacion nueva borra lo que se podia rehacer")

    print("=== 5. una operacion que falla no deja nada a medias ===")
    p, fid = nuevo()
    p.dividir(4.0)
    antes, nh = estado(p), len(p._deshacer)
    for etiqueta, f, args in (("borrar un tramo vacio", p.borrar_rango, (3.0, 3.0)),
                              ("volumen de video", p.volumen, (p.pista("V1")["clips"][0]["id"], 1.0)),
                              ("clip inexistente", p.fade, ("c999", "in", 1.0)),
                              ("volumen fuera de rango", p.volumen, (p.pista("A1")["clips"][0]["id"], 9.0)),
                              ("lado de fundido invalido", p.fade, (p.pista("V1")["clips"][0]["id"], "medio", 1.0))):
        ok(da_error(f, *args) is not None, f"{etiqueta}: da error")
    ok(estado(p) == antes and len(p._deshacer) == nh, "y el proyecto y su historial quedan exactamente como estaban")
    # una operacion compuesta que falla a la mitad
    p2, _ = nuevo()
    antes = estado(p2)
    original = p2._dividir_en

    def roto(*a, **k):
        original(*a, **k)
        raise RuntimeError("falla a mitad")
    p2._dividir_en = roto
    try:
        p2.borrar_rango(2.0, 4.0)
    except RuntimeError:
        pass
    p2._dividir_en = original
    ok(estado(p2) == antes, "si algo explota a mitad de un borrado, se restaura todo")
    ok(p2.validar() == [] and not p2._en_transaccion, "y la transaccion queda cerrada")

    print("=== 6. fundidos y volumen ===")
    p, fid = nuevo()
    cv = p.pista("V1")["clips"][0]
    ca = p.pista("A1")["clips"][0]
    ok(p.fade(cv["id"], "in", 1.5) == 1.5 and cv["fade_in"] == 1.5, "fundido de entrada")
    ok(p.fade(cv["id"], "out", 9.0) == 8.5, "el de salida se recorta para que no pasen del largo del clip", cv["fade_out"])
    ok(p.validar() == [], "sigue valido")
    p.fade(cv["id"], "out", 0.0)
    p.fade_grupo(cv["grupo"], "out", 2.0, curva="qsin")
    ok(cv["fade_out"] == 2.0 and ca["fade_out"] == 2.0 and ca["curva_out"] == "qsin", "fade_grupo pone el mismo fundido en video y audio")
    p.fade(cv["id"], "in", 1.0, color="blanco")
    ok(cv["color_fundido"] == "blanco", "el fundido de video puede ser a blanco")
    ok(da_error(p.fade, cv["id"], "in", 1.0, "curva_rara") is not None, "una curva desconocida da error")
    # (tras el error de la curva el modelo restauro el estado con una copia: se vuelve a buscar el clip)
    ca = p.pista("A1")["clips"][0]
    p.volumen(ca["id"], 0.5)
    ok(p.pista("A1")["clips"][0]["volumen"] == 0.5, "volumen")
    # al cortar, el fundido de entrada se queda en la primera mitad y el de salida en la segunda
    p, fid = nuevo()
    c0 = p.pista("V1")["clips"][0]
    p.fade(c0["id"], "in", 1.0)
    p.fade(c0["id"], "out", 1.0)
    p.dividir(5.0)
    izq, der = p.pista("V1")["clips"]
    ok(izq["fade_in"] == 1.0 and izq["fade_out"] == 0.0 and der["fade_in"] == 0.0 and der["fade_out"] == 1.0,
       "al cortar, cada fundido queda en el borde de afuera (no aparecen fundidos en el corte)")
    p.silenciar("A1", True)
    ok(p.pista("A1")["silenciada"] is True and da_error(p.silenciar, "V1", True) is not None, "silenciar una pista de audio (no de video)")

    print("=== 7. audio extra (musica, locucion) ===")
    p, fid = nuevo()
    musica = p.agregar_fuente("m.mp3", "audio", 30.0, None, 1)
    c1 = p.agregar_audio(musica, inicio=1.0, hasta=6.0)
    ok([x["id"] for x in p.pistas] == ["V1", "A1", "A2"], "crea la pista A2")
    c2 = p.agregar_audio(musica, inicio=2.0, hasta=4.0)
    ok([x["id"] for x in p.pistas][-1] == "A3", "si se superpone con lo que hay, va a otra pista (A3)")
    c3 = p.agregar_audio(musica, inicio=7.0, desde=10.0, hasta=12.0)
    ok(len(p.pista("A2")["clips"]) == 2, "si no se superpone, comparte la pista A2")
    ok(p.validar() == [], "valido", p.validar())
    ok(da_error(p.mover_clip, p.pista("A1")["clips"][0]["id"], 1.0) is not None, "no se mueve el audio enlazado al video")
    ok(da_error(p.mover_clip, c3, 3.0) is not None, "no se mueve encima de otro audio de su pista")
    p.mover_clip(c3, 9.0)
    ok(p.clip(c3)[1]["inicio"] == 9.0, "se mueve a un lugar libre")
    # borrar un tramo del video tambien recorta y corre el audio extra
    p.borrar_rango(2.0, 4.0)
    ok(p.validar() == [], "borrar un tramo con musica de fondo deja todo valido", p.validar())
    ok(abs(p.clip(c3)[1]["inicio"] - 7.0) < 1e-5, "y el audio que estaba despues se corre igual (sigue la sincronia)", p.clip(c3)[1]["inicio"])
    p.eliminar_clip(c3)
    ok(da_error(p.eliminar_clip, p.pista("A1")["clips"][0]["id"]) is not None, "no se saca suelto un audio enlazado")
    ok(da_error(p.agregar_audio, fid, 0, 5.0, 1.0) is not None, "un tramo sin duracion da error")
    p.desenlazar(p.pista("V1")["clips"][0]["grupo"])
    ok(p.pista("V1")["clips"][0]["grupo"] != p.pista("A1")["clips"][0]["grupo"], "desenlazar separa video y audio")
    ok(da_error(p.desenlazar, p.pista("V1")["clips"][0]["grupo"]) is not None, "y no se puede desenlazar lo que no esta enlazado")

    print("=== 7b. las pistas extra vacias desaparecen y los ids no se repiten ===")
    p, fid = nuevo()
    musica = p.agregar_fuente("m.mp3", "audio", 30.0, None, 1)
    c1 = p.agregar_audio(musica, inicio=1.0, hasta=5.0)
    p.eliminar_clip(c1)
    ok([x["id"] for x in p.pistas] == ["V1", "A1"], "al sacar el unico audio de A2, la pista A2 desaparece")
    p.deshacer()
    ok([x["id"] for x in p.pistas] == ["V1", "A1", "A2"] and p.validar() == [], "deshacer la devuelve")
    p, fid = nuevo()
    musica = p.agregar_fuente("m.mp3", "audio", 30.0, None, 1)
    a = p.agregar_audio(musica, inicio=0.0, hasta=6.0)          # A2
    b = p.agregar_audio(musica, inicio=1.0, hasta=3.0)          # se superpone: A3
    ok([x["id"] for x in p.pistas] == ["V1", "A1", "A2", "A3"], "A2 y A3")
    p.eliminar_clip(a)
    ok([x["id"] for x in p.pistas] == ["V1", "A1", "A3"], "sacar el de A2 deja A3 sola")
    c = p.agregar_audio(musica, inicio=0.5, hasta=1.5)          # no se superpone con A3
    ids = [x["id"] for x in p.pistas]
    ok(len(ids) == len(set(ids)) and p.validar() == [], "el siguiente audio no repite el id de ninguna pista", str(ids))
    p, fid = nuevo()
    musica = p.agregar_fuente("m.mp3", "audio", 30.0, None, 1)
    p.agregar_audio(musica, inicio=2.0, hasta=2.0)              # dura 2 s: ocupa de la linea 2 a la 4
    p.borrar_rango(1.0, 5.0)
    ok([x["id"] for x in p.pistas] == ["V1", "A1"] and p.validar() == [], "borrar un tramo que cubre todo un audio extra tambien saca su pista")
    p.deshacer()
    ok([x["id"] for x in p.pistas] == ["V1", "A1", "A2"], "y deshacer la devuelve")

    print("=== 8. video de framerate variable: los cortes caen en cuadros REALES ===")
    tiempos, dur = vfr()
    p, fid = nuevo(tiempos, dur)
    ok(p.validar() == [], "arranca valido")
    azar = random.Random(3)
    for _ in range(25):
        try:
            p.dividir(azar.uniform(0.2, p.duracion() - 0.2))
        except ErrorEdicion:
            pass
    conjunto = set(round(x, 6) for x in tiempos) | {round(dur, 6)}
    bordes = {round(c["desde"], 6) for c in p.pista("V1")["clips"]} | {round(c["hasta"], 6) for c in p.pista("V1")["clips"]}
    ok(bordes <= conjunto, "todos los bordes de clip son el inicio de un cuadro real (o el final)", f"{len(bordes)} bordes")
    ok(p.validar() == [], "y es valido", p.validar()[:2])
    cerca_pausa = [t for t in tiempos if 5.0 < t < 5.5]
    p, fid = nuevo(tiempos, dur)
    t = p.dividir(5.2)
    ok(any(abs(t - x) < 1e-5 for x in tiempos), "un corte cerca de la pausa de 2,4 s cae en un cuadro", t)

    print("=== 9. consultas para reproducir ===")
    p, fid = nuevo()
    p.borrar_rango(2.0, 4.0)
    seg = p.segmentos_video()
    ok(len(seg) == 2 and abs(seg[0]["fin"] - seg[1]["inicio"]) < 1e-6 and abs(seg[1]["desde"] - 4.0) < 1e-6,
       "segmentos_video: dos tramos pegados, el segundo sale del segundo 4 de la fuente")
    c = p.clip_en("V1", 2.5)
    ok(abs(p.a_fuente(c, 2.5) - 4.5) < 1e-6 and abs(p.a_linea(c, 4.5) - 2.5) < 1e-6, "linea de tiempo <-> fuente, ida y vuelta")
    ok(p.clip_en("V1", 0.0)["desde"] == 0.0 and p.clip_en("V1", p.duracion())["hasta"] == 10.0, "clip_en en los extremos")
    ok(p.clip_en("V1", 99.0) is None, "fuera del proyecto: ninguno")

    print("=== 10. guardar y cargar ===")
    p, fid = nuevo()
    p.dividir(3.0)
    p.fade(p.pista("V1")["clips"][0]["id"], "in", 1.0)
    musica = p.agregar_fuente("m.mp3", "audio", 20.0, None, 1)
    p.agregar_audio(musica, 0.0, 0.0, 5.0)
    ruta = os.path.join(tempfile.mkdtemp(), "p.moviola.json")
    p.guardar(ruta)
    ok(not os.path.exists(ruta + ".tmp"), "se guarda de forma atomica")
    q = Proyecto.cargar(ruta, tiempos_de=lambda f: cfr() if f["tipo"] == "video" else None)
    ok(estado(q) == estado(p), "al cargar queda igual")
    ok(q.validar() == [], "y valido")
    ok("tiempos" not in p.a_dict()["fuentes"]["s1"], "el archivo guardado no arrastra la tabla de tiempos de cada cuadro")
    q.dividir(7.0)
    ok(q.validar() == [] and q.pista("V1")["clips"][-1]["id"] not in [c["id"] for c in p.pista("V1")["clips"]],
       "y sigue editando sin repetir ids")
    with open(ruta, "w") as f:
        f.write('{"version": 99}')
    ok(da_error(Proyecto.cargar, ruta) is not None, "una version desconocida da un error claro")

    print("=== 10b. efectos por clip ===")
    p, fid = nuevo()
    # un pedido rechazado restaura una COPIA del estado: nunca se guardan referencias a clips, se vuelven a buscar
    v1c = {"id": p.pista("V1")["clips"][0]["id"]}
    a1c = {"id": p.pista("A1")["clips"][0]["id"]}
    ok(p.pista("V1")["clips"][0]["efectos"] == [] and p.pista("A1")["clips"][0]["efectos"] == [], "un clip nuevo no tiene efectos")
    e1 = p.agregar_efecto(v1c["id"], "color_basico", {"brillo": 0.2})
    ok(p.pista("V1")["clips"][0]["efectos"][0]["params"] == {"brillo": 0.2, "contraste": 1.0, "saturacion": 1.0} and p.pista("V1")["clips"][0]["efectos"][0]["activo"],
       "agregar: los ajustes que no se piden quedan en su valor por defecto", p.pista("V1")["clips"][0]["efectos"][0])
    ok(p.validar() == [], "y el proyecto sigue valido", p.validar())
    ok(da_error(p.agregar_efecto, v1c["id"], "pasa_altos") is not None, "un efecto de audio no entra en un clip de video", da_error(p.agregar_efecto, v1c["id"], "pasa_altos"))
    ok(da_error(p.agregar_efecto, a1c["id"], "voltear") is not None, "ni uno de video en un clip de audio")
    ok(da_error(p.agregar_efecto, v1c["id"], "no_existe") is not None, "un efecto desconocido da un error claro")
    ok(da_error(p.agregar_efecto, v1c["id"], "color_basico", {"brillo": 9}) is not None, "un valor fuera de rango se rechaza (no se recorta en silencio)")
    ok(da_error(p.agregar_efecto, v1c["id"], "color_basico", {"inventado": 1}) is not None, "un ajuste que no existe tambien")
    ok(da_error(p.agregar_efecto, v1c["id"], "color_basico", {"brillo": float("nan")}) is not None, "y un NaN")
    ok(da_error(p.agregar_efecto, v1c["id"], "color_basico", {"brillo": True}) is not None, "y un si/no donde va un numero")
    ok(len(p.pista("V1")["clips"][0]["efectos"]) == 1, "los pedidos rechazados no dejan nada a medias")
    e2 = p.agregar_efecto(v1c["id"], "voltear")
    ok([e["tipo"] for e in p.pista("V1")["clips"][0]["efectos"]] == ["color_basico", "voltear"] and e1 != e2, "se apilan en orden, cada uno con su id")
    p.cambiar_efecto(v1c["id"], e1, {"contraste": 1.5})
    ok(p.pista("V1")["clips"][0]["efectos"][0]["params"] == {"brillo": 0.2, "contraste": 1.5, "saturacion": 1.0}, "cambiar toca solo lo pedido")
    ok(da_error(p.cambiar_efecto, v1c["id"], "e999", {"brillo": 0}) is not None, "cambiar un efecto que no esta da un error claro")
    p.activar_efecto(v1c["id"], e1, False)
    ok(p.pista("V1")["clips"][0]["efectos"][0]["activo"] is False and p.pista("V1")["clips"][0]["efectos"][0]["params"]["contraste"] == 1.5, "apagar un efecto conserva sus valores")
    p.mover_efecto(v1c["id"], e2, -1)
    ok([e["id"] for e in p.pista("V1")["clips"][0]["efectos"]] == [e2, e1], "mover cambia el orden")
    ok(da_error(p.mover_efecto, v1c["id"], e2, -1) is not None, "mover mas alla del extremo da un error claro")
    p.deshacer()
    ok([e["id"] for e in p.pista("V1")["clips"][0]["efectos"]] == [e1, e2], "deshacer devuelve el orden")
    while p.puede_deshacer():
        p.deshacer()
    ok(p.pista("V1")["clips"][0]["efectos"] == [], "deshacer todo deja el clip sin efectos")
    while p.puede_rehacer():
        p.rehacer()
    ok(len(p.pista("V1")["clips"][0]["efectos"]) == 2, "y rehacer los vuelve")
    p.quitar_efecto(p.pista("V1")["clips"][0]["id"], e1)
    ok([e["tipo"] for e in p.pista("V1")["clips"][0]["efectos"]] == ["voltear"], "quitar saca uno solo")
    # cortar un clip: cada mitad lleva SUS efectos (copias, con ids nuevos)
    p2, _ = nuevo()
    cv = p2.pista("V1")["clips"][0]
    ca = p2.pista("A1")["clips"][0]
    p2.agregar_efecto(cv["id"], "color_basico", {"saturacion": 0.0})
    p2.agregar_efecto(ca["id"], "pasa_altos", {"frecuencia": 200})
    p2.dividir(4.0)
    izq, der = p2.pista("V1")["clips"]
    ok(efectos.firma(izq["efectos"]) == efectos.firma(der["efectos"]) and len(izq["efectos"]) == 1, "al cortar, las dos mitades conservan el efecto")
    ok(izq["efectos"][0]["id"] != der["efectos"][0]["id"], "con ids distintos (si no, tocar uno tocaria el otro)")
    p2.cambiar_efecto(der["id"], der["efectos"][0]["id"], {"saturacion": 1.5})
    ok(izq["efectos"][0]["params"]["saturacion"] == 0.0, "y son independientes: cambiar uno no cambia el otro")
    ok(len(p2.pista("A1")["clips"][1]["efectos"]) == 1 and p2.validar() == [], "lo mismo en el audio, y valido", p2.validar())
    # borrar un tramo: los clips que quedan conservan sus efectos
    p2.borrar_rango(1.0, 2.0)
    ok(all(len(c["efectos"]) == 1 for c in p2.pista("V1")["clips"]) and p2.validar() == [], "borrar un tramo no pierde efectos de lo que queda")
    # guardar y cargar
    ruta = os.path.join(tempfile.mkdtemp(), "fx.moviola.json")
    p2.guardar(ruta)
    q = Proyecto.cargar(ruta, tiempos_de=lambda f: cfr() if f["tipo"] == "video" else None)
    ok(estado(q) == estado(p2) and q.validar() == [], "los efectos se guardan y se cargan")
    q.agregar_efecto(q.pista("V1")["clips"][0]["id"], "voltear")
    ids = [e["id"] for pp in q.pistas for c in pp["clips"] for e in c["efectos"]]
    ok(len(ids) == len(set(ids)), "y un efecto nuevo despues de cargar no repite ids")
    # un proyecto guardado antes de existir los efectos
    d = json.load(open(ruta, encoding="utf-8"))
    for pp in d["pistas"]:
        for c in pp["clips"]:
            c.pop("efectos", None)
    d["n"].pop("efecto", None)
    json.dump(d, open(ruta, "w", encoding="utf-8"))
    viejo = Proyecto.cargar(ruta, tiempos_de=lambda f: cfr() if f["tipo"] == "video" else None)
    ok(viejo.validar() == [] and viejo.pista("V1")["clips"][0]["efectos"] == [], "un proyecto de antes de los efectos se abre sin efectos")
    viejo.agregar_efecto(viejo.pista("V1")["clips"][0]["id"], "voltear")
    ok(viejo.validar() == [], "y se le pueden agregar")
    # validar() detecta un efecto roto
    rota = Proyecto()
    rota.fuentes = dict(p2.fuentes)
    rota.pistas = json.loads(json.dumps(p2.pistas))
    rota.pistas[0]["clips"][0]["efectos"][0]["params"]["saturacion"] = 99
    ok(any("invalido" in m for m in rota.validar()), "validar encuentra un efecto con un valor fuera de rango")
    rota.pistas[0]["clips"][0]["efectos"][0] = {"id": "e1", "tipo": "pasa_altos", "activo": True, "params": {"frecuencia": 80}}
    ok(any("no es de" in m for m in rota.validar()), "y un efecto en la pista que no le corresponde")
    # traduccion a ffmpeg
    ok(efectos.filtro_video("color_basico", efectos.defectos("color_basico")) is None, "un efecto sin cambios no genera filtro")
    ok(efectos.filtro_video("voltear", {"horizontal": False, "vertical": False}) is None, "voltear sin nada tampoco")
    ok(efectos.filtro_video("voltear", {"horizontal": True, "vertical": True}) == "hflip,vflip", "voltear en los dos sentidos")
    ok(efectos.filtro_video("color_basico", {"brillo": 0.1, "contraste": 1.2, "saturacion": 0.5}) == "eq=brightness=0.1000:contrast=1.2000:saturation=0.5000",
       "color basico -> eq")
    ok(efectos.filtro_audio("pasa_altos", {"frecuencia": 120}) == "highpass=f=120", "quitar graves -> highpass")
    ok(efectos.filtro_audio("color_basico", {"brillo": 0.1, "contraste": 1.0, "saturacion": 1.0}) is None, "un efecto de video no genera filtro de audio")
    cat = efectos.catalogo()
    ok(set(cat) == set(efectos.EFECTOS) and all("nombre" in v and "params" in v for v in cat.values()), "el catalogo para la interfaz esta completo")
    ok(json.dumps(cat) and all(efectos.limpiar_params(tp, {}) == efectos.defectos(tp) for tp in cat), "y cada efecto acepta sus valores por defecto")

    print("=== 11. PROPIEDADES: secuencias al azar ===")
    malos = []
    total_ops = 0
    n_secuencias = int(os.environ.get("PROPIEDADES_N", "300"))      # subir para una corrida de estres
    for semilla in range(n_secuencias):
        azar = random.Random(semilla)
        usar_vfr = semilla % 3 == 0
        tiempos, dur = vfr() if usar_vfr else (cfr(), 10.0)
        p, fid = nuevo(tiempos, dur)
        musica = p.agregar_fuente("m.mp3", "audio", 60.0, None, 1)
        otro = p.agregar_fuente("v2.mp4", "video", 5.0, cfr(150, 30.0), 1)         # un segundo video (con audio)
        mudo = p.agregar_fuente("v3.mp4", "video", 3.0, cfr(75, 25.0), 0)          # y un tercero sin audio
        inicial = estado(p)
        historial = []
        for paso in range(18):
            dur_ahora = p.duracion()
            if not p.pista("V1")["clips"]:
                # se borro todo (una persona tambien puede): lo unico que tiene sentido es deshacer
                if p.puede_deshacer():
                    p.deshacer()
                    if p.validar():
                        malos.append((semilla, paso, "deshacer", p.validar()[:2]))
                        break
                continue
            op = azar.choice(["dividir", "dividir", "borrar", "borrar", "grupo", "recortar", "fade", "volumen",
                              "audio", "mover", "deshacer", "rehacer", "silenciar", "pista",
                              "fx_agregar", "fx_agregar", "fx_cambiar", "fx_quitar", "fx_mover", "fx_activar",
                              "trans_poner", "trans_poner", "trans_poner", "trans_quitar",
                              "insertar", "insertar", "mover_grupo", "mover_grupo"])
            antes = estado(p)
            esperado = None
            try:
                if op == "dividir":
                    p.dividir(azar.uniform(0, dur_ahora))
                elif op == "borrar":
                    a, b = sorted((azar.uniform(0, dur_ahora), azar.uniform(0, dur_ahora)))
                    r = p.borrar_rango(a, b)
                    esperado = dur_ahora - r["duracion"]
                elif op == "grupo":
                    p.borrar_grupo(azar.choice(p.pista("V1")["clips"])["grupo"])
                elif op == "recortar":
                    a, b = sorted((azar.uniform(0, dur_ahora), azar.uniform(0, dur_ahora)))
                    p.recortar_a(a, b)
                elif op == "fade":
                    todos = [c for pp in p.pistas for c in pp["clips"]]
                    p.fade(azar.choice(todos)["id"], azar.choice(["in", "out"]), azar.uniform(0, 4))
                elif op == "volumen":
                    if any(pp["id"] == "A1" and pp["clips"] for pp in p.pistas):
                        p.volumen(azar.choice(p.pista("A1")["clips"])["id"], azar.uniform(0, 4))
                elif op == "audio":
                    p.agregar_audio(musica, azar.uniform(0, dur_ahora), azar.uniform(0, 20), azar.uniform(20, 40))
                elif op == "mover":
                    extras = [c for pp in p.pistas if pp["id"] not in ("V1", "A1") for c in pp["clips"]]
                    if extras:
                        p.mover_clip(azar.choice(extras)["id"], azar.uniform(0, dur_ahora))
                elif op == "insertar":
                    p.insertar_fuente(azar.choice([otro, mudo, fid]), azar.choice([None, azar.uniform(0, dur_ahora)]))
                elif op == "mover_grupo":
                    p.mover_grupo(azar.choice(p.pista("V1")["clips"])["grupo"], azar.uniform(0, dur_ahora))
                elif op == "deshacer":
                    p.deshacer()
                elif op == "rehacer":
                    p.rehacer()
                elif op == "silenciar":
                    p.silenciar("A1", azar.random() < 0.5)
                elif op == "pista":
                    if any(pp["id"] == "A1" and pp["clips"] for pp in p.pistas):
                        p.cambiar_pista_audio(azar.choice(p.pista("A1")["clips"])["id"], 0)
                elif op == "trans_poner":
                    g = azar.choice(p.pista("V1")["clips"])["grupo"]
                    p.poner_transicion(g, azar.choice(list(efectos.TRANSICIONES)), azar.uniform(0.05, 3.2))
                elif op == "trans_quitar":
                    p.quitar_transicion(azar.choice(p.pista("V1")["clips"])["grupo"])
                elif op.startswith("fx_"):
                    pp = azar.choice([x for x in p.pistas if x["clips"]])
                    cl = azar.choice(pp["clips"])
                    tipos = [k for k, d in efectos.EFECTOS.items() if d["categoria"] == pp["tipo"]]
                    if op == "fx_agregar":
                        tp = azar.choice(tipos)
                        valores = {}
                        for s in efectos.EFECTOS[tp]["params"]:
                            if s["tipo"] == "bool":
                                valores[s["id"]] = azar.random() < 0.5
                            elif s["tipo"] == "opcion":
                                valores[s["id"]] = azar.choice(s["opciones"])["valor"]
                            elif s["tipo"] == "archivo":
                                pass                                              # sin archivo (no hay archivos reales en esta prueba)
                            elif s["tipo"] == "texto":
                                valores[s["id"]] = azar.choice(["", "Hola", "Ñandú ¿qué? %{n} \\ ' :"])
                            elif azar.random() < 0.7:
                                valores[s["id"]] = azar.uniform(s["min"], s["max"])
                        p.agregar_efecto(cl["id"], tp, valores)
                    elif cl["efectos"]:
                        ef = azar.choice(cl["efectos"])
                        if op == "fx_cambiar" and not efectos.EFECTOS[ef["tipo"]]["params"]:
                            p.activar_efecto(cl["id"], ef["id"], True)           # un efecto sin ajustes (Al reves) no tiene nada para cambiar
                        elif op == "fx_cambiar":
                            s = azar.choice(efectos.EFECTOS[ef["tipo"]]["params"])
                            if s["tipo"] == "bool":
                                v = azar.random() < 0.5
                            elif s["tipo"] == "opcion":
                                v = azar.choice(s["opciones"] + [{"valor": "no_existe"}])["valor"]    # a veces una opcion que no hay: error limpio
                            elif s["tipo"] == "archivo":
                                v = ""
                            elif s["tipo"] == "texto":
                                v = azar.choice(["Título", "x" * (s["max"] + 1), "", 7])     # a veces demasiado largo o que no es texto: error limpio
                            else:
                                v = azar.uniform(s["min"] - 0.1, s["max"] + 0.1)
                            p.cambiar_efecto(cl["id"], ef["id"], {s["id"]: v})     # a veces fuera de rango: tiene que dar error limpio
                        elif op == "fx_quitar":
                            p.quitar_efecto(cl["id"], ef["id"])
                        elif op == "fx_mover":
                            p.mover_efecto(cl["id"], ef["id"], azar.choice([-1, 1]))
                        else:
                            p.activar_efecto(cl["id"], ef["id"], azar.random() < 0.5)
            except ErrorEdicion:
                if estado(p) != antes:
                    malos.append((semilla, paso, op, "un error dejo el estado cambiado"))
                    break
                continue
            total_ops += 1
            problemas = p.validar()
            if problemas:
                malos.append((semilla, paso, op, problemas[:2]))
                break
            if esperado is not None and abs(p.duracion() - esperado) > 1e-4:
                malos.append((semilla, paso, op, "duracion %s, esperaba %s" % (p.duracion(), esperado)))
                break
            # video y audio siguen sincronizados: en cada instante, el audio enlazado sale del mismo punto de la fuente
            v1, a1 = p.pista("V1")["clips"], p.pista("A1")["clips"]
            por_grupo = {c["grupo"]: c for c in a1}
            falta = [cv for cv in v1 if (p.fuentes[cv["fuente"]]["pistas_audio"] > 0) != (cv["grupo"] in por_grupo)]
            if falta or len(a1) != len([cv for cv in v1 if p.fuentes[cv["fuente"]]["pistas_audio"] > 0]):
                malos.append((semilla, paso, op, "cada clip de V1 tiene su audio en A1 (si la fuente tiene) y A1 no tiene clips de mas"))
                break
            for cv in [c for c in v1 if c["grupo"] in por_grupo]:
                ca = por_grupo[cv["grupo"]]
                if (abs(cv["inicio"] - ca["inicio"]) > 1e-4 or abs(cv["desde"] - ca["desde"]) > 1e-4
                        or abs(cv["hasta"] - ca["hasta"]) > 1e-4 or cv["fuente"] != ca["fuente"]):
                    malos.append((semilla, paso, op, "video y audio se desincronizaron"))
                    break
            else:
                # V1 sin huecos: empieza en cero y cada clip arranca donde termino el anterior
                t = 0.0
                for cv in v1:
                    if abs(cv["inicio"] - t) > 1e-4:
                        malos.append((semilla, paso, op, "hueco en V1 en %s" % t))
                        break
                    t = p.fin(cv)
                else:
                    continue
                break
            break
        else:
            # se deshace todo lo deshacible: tiene que volver exactamente al principio
            while p.puede_deshacer():
                p.deshacer()
            if estado(p) != inicial:
                malos.append((semilla, "fin", "deshacer todo", "no volvio al estado inicial"))
    ok(not malos, f"{n_secuencias} secuencias al azar ({total_ops} operaciones): todo valido, sincronizado, sin huecos y deshacible",
       str(malos[:2]))

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
