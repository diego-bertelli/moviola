# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 10: editar por texto (palabras con su tiempo) y subtitulos karaoke.

1. El modelo (sin whisper): palabras guardadas con las frases, borrar palabras = cortar el montaje (MEDIDO en los cuadros que salen),
   acortar pausas, corregir una palabra, deshacer, guardar y abrir, secuencias al azar.
2. Karaoke: el .ass y la palabra resaltada MEDIDA en la imagen quemada (se corre de una palabra a la siguiente).
3. Con whisper y una voz de Windows (si estan; si no, se saltea y lo dice): los tiempos por palabra contra una verdad conocida (cada palabra
   sintetizada por separado), las tildes, y borrar una muletilla del texto -> volver a transcribir lo exportado y comprobar que ya no esta.

Uso:  python -I pruebas/prueba_texto.py
"""

import json
import os
import random
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

from PIL import ImageChops  # noqa: E402

import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402
import voz  # noqa: E402
from motor import subtitulos as sub  # noqa: E402
from motor.proyecto import ErrorEdicion, Proyecto  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def da_error(f, *a, **k):
    try:
        f(*a, **k)
    except ErrorEdicion as e:
        return str(e)
    return None


def con_palabras(p, n=12, paso=0.9, desde=0.4):
    """n palabras seguidas (w0, w1...), cada una de `paso` segundos, en frases de 3. Los tiempos caen justo en cuadros de 30 por segundo."""
    palabras = []
    for i in range(n):
        a = round(desde + paso * i, 3)
        palabras.append({"texto": "w%d" % i, "inicio": a, "fin": round(a + paso, 3), "voz": round(a + 0.05, 3), "habla": round(a + 0.75, 3)})
    frases = []
    for k in range(0, n, 3):
        frases.append({"inicio": palabras[k]["inicio"], "fin": palabras[min(k + 2, n - 1)]["fin"], "texto": " ".join(w["texto"] for w in palabras[k:k + 3]),
                       "palabras": [k, k + 1, k + 2][: n - k]})
    p.subtitulos_poner(frases, palabras)
    return p


def ids(p):
    return [w["id"] for w in p.subtitulos["palabras"]]


def caja_azul(a, b, umbral=100):
    """Donde cambia el canal AZUL entre dos cuadros (blanco -> amarillo lo apaga): la palabra que se resalto."""
    return ImageChops.difference(a, b).split()[2].point(lambda v: 255 if v > umbral else 0).getbbox()


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if c.isalnum())


def main():
    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=12)

    # ------------------------------------------------------------------ 1. el modelo
    print("=== 1. palabras en el proyecto ===")
    p, _, _ = ex.armar(src)
    con_palabras(p)
    ok(len(p.subtitulos["palabras"]) == 12 and len(p.subtitulos["frases"]) == 4 and p.validar() == [], "12 palabras y 4 frases con sus palabras; el proyecto es valido")
    f0 = p.subtitulos["frases"][0]
    ok(f0["palabras"] == ["w1", "w2", "w3"] and f0["texto"] == "w0 w1 w2", "cada frase conoce las suyas (por id)", str(f0))
    ok(p.a_dict()["subtitulos_desactualizados"] is False, "recien puestas, estan al dia con el montaje")
    for malo, ps in (("sin texto", [{"texto": " ", "inicio": 0, "fin": 1}]), ("con dos palabras", [{"texto": "hola mundo", "inicio": 0, "fin": 1}]),
                     ("con el tiempo roto", [{"texto": "a", "inicio": "0", "fin": 1}]), ("con el final antes del inicio", [{"texto": "a", "inicio": 2, "fin": 1}]),
                     ("desordenadas", [{"texto": "a", "inicio": 2, "fin": 3}, {"texto": "b", "inicio": 1, "fin": 2}]), ("despues del final del video", [{"texto": "a", "inicio": 99, "fin": 100}]),
                     ("una frase que apunta a una palabra que no hay", None)):
        antes = json.dumps(p.subtitulos, sort_keys=True)
        if ps is None:
            e = da_error(p.subtitulos_poner, [{"inicio": 0, "fin": 1, "texto": "x", "palabras": [5]}], [{"texto": "a", "inicio": 0, "fin": 1}])
        else:
            e = da_error(p.subtitulos_poner, [], ps)
        ok(e is not None and json.dumps(p.subtitulos, sort_keys=True) == antes, "palabras " + malo + ": error claro y no cambia nada", e)

    print("=== 1b. borrar palabras = cortar el montaje ===")
    q, _, _ = ex.armar(src)
    con_palabras(q)
    w = ids(q)
    r = q.palabras_borrar([w[4]])           # w4 va de 4.0 a 4.9
    ok(r["palabras"] == 1 and abs(r["duracion"] - 0.9) < 1e-6 and abs(q.duracion() - 11.1) < 1e-6, "borrar la palabra 5 saca 0,9 s del montaje (12 -> 11,1 s)", str(r))
    ok(len(q.subtitulos["palabras"]) == 11 and "w4" not in [x["texto"] for x in q.subtitulos["palabras"]], "la palabra ya no esta en el texto")
    sig = next(x for x in q.subtitulos["palabras"] if x["texto"] == "w5")
    ok(abs(sig["inicio"] - 4.0) < 1e-6 and abs(sig["fin"] - 4.9) < 1e-6, "y la siguiente se corrio hacia adelante (de 4,9 a 4,0)", str(sig))
    fr = q.subtitulos["frases"][1]
    ok(fr["texto"] == "w3 w5" and abs(fr["inicio"] - 3.1) < 1e-6 and abs(fr["fin"] - 4.9) < 1e-6 and len(fr["palabras"]) == 2, "la frase se rearma con las palabras que le quedan", str(fr))
    ok(q.a_dict()["subtitulos_desactualizados"] is False and q.validar() == [], "los subtitulos siguen al dia (el modelo sabe que se corrieron) y el proyecto es valido")
    ok(len(q._deshacer) >= 1 and len(q.pista("V1")["clips"]) == 2 and len(q.pista("A1")["clips"]) == 2, "video y audio quedaron cortados juntos")
    q.deshacer()
    ok(len(q.subtitulos["palabras"]) == 12 and abs(q.duracion() - 12.0) < 1e-6 and q.subtitulos["frases"][1]["texto"] == "w3 w4 w5", "Deshacer devuelve el montaje, las palabras y las frases de una vez")
    q.rehacer()
    ok(len(q.subtitulos["palabras"]) == 11, "y Rehacer lo vuelve a sacar")
    # varias palabras, juntas y sueltas: un solo paso del historial
    q2, _, _ = ex.armar(src)
    con_palabras(q2)
    w2 = ids(q2)
    n_antes = len(q2._deshacer)
    r = q2.palabras_borrar([w2[1], w2[2], w2[3], w2[8]])
    ok(r["palabras"] == 4 and r["tramos"] == 2 and abs(r["duracion"] - 3.6) < 1e-6 and len(q2._deshacer) == n_antes + 1, "borrar 3 seguidas y 1 suelta: 2 tramos, 3,6 s, UN paso de deshacer", str(r))
    ok(q2.validar() == [] and [x["texto"] for x in q2.subtitulos["frases"]] == ["w0", "w4 w5", "w6 w7", "w9 w10 w11"], "las frases se rearman con las palabras que les quedan (sin juntarse entre ellas)", str([x["texto"] for x in q2.subtitulos["frases"]]))
    q3, _, _ = ex.armar(src)
    con_palabras(q3)
    q3.palabras_borrar(ids(q3)[3:6])
    ok([x["texto"] for x in q3.subtitulos["frases"]] == ["w0 w1 w2", "w6 w7 w8", "w9 w10 w11"], "si se borran TODAS las palabras de una frase, la frase desaparece", str([x["texto"] for x in q3.subtitulos["frases"]]))
    for malo, f, args in (("sin elegir nada", q3.palabras_borrar, ([],)), ("una que no existe", q3.palabras_borrar, (["w999"],)), ("ids que no son texto", q3.palabras_borrar, ([1, 2],)),
                          ("que no es una lista", q3.palabras_borrar, ("w1",))):
        antes = (json.dumps(q3.subtitulos, sort_keys=True), q3.duracion())
        e = da_error(f, *args)
        ok(e is not None and (json.dumps(q3.subtitulos, sort_keys=True), q3.duracion()) == antes, "borrar " + malo + ": error claro y no cambia nada", e)
    # desactualizadas: si el montaje cambio por otro lado, no se corta a ciegas
    q4, _, _ = ex.armar(src)
    con_palabras(q4)
    q4.velocidad(q4.pista("V1")["clips"][0]["grupo"], 2.0)
    e = da_error(q4.palabras_borrar, [ids(q4)[0]])
    ok(e is not None and "Volvé a transcribir" in e and abs(q4.duracion() - 6.0) < 1e-6, "con el montaje cambiado despues de transcribir (velocidad), no corta: pide volver a transcribir", e)

    print("=== 1c. el montaje que sale: se mide cuadro por cuadro ===")
    q5, _, _ = ex.armar(src)
    con_palabras(q5)
    q5.palabras_borrar([ids(q5)[4], ids(q5)[5]])        # 4,0 -> 5,8
    arch, _ = im.exportar(q5, "texto_borrado")
    cod = ex.leer_codigos(arch)
    ok(len(cod) == 12 * 30 - 54 and cod[119] == 119 and cod[120] == 174, "el video exportado salta del cuadro 119 al 174 (se sacaron 4,0 s a 5,8 s): quedan %d cuadros" % len(cod), "%s -> %s" % (cod[119], cod[120]))
    ok(not any(120 <= c < 174 for c in cod) and cod == sorted(cod), "ningun cuadro de lo borrado, y en orden")
    m = ex.muestras(arch)
    ok(abs(len(m) / 48000.0 - (12 - 1.8)) < 0.1, "el audio dura lo mismo que el video (10,2 s)")

    print("=== 1d. pausas ===")
    qp, _, _ = ex.armar(src)
    con_palabras(qp)                          # cada palabra suena 0,05..0,75 de su 0,9 s: pausas de 0,2 s entre una y otra
    pa = qp.pausas()
    ok(len(pa) == 11 and all(abs((x["fin"] - x["inicio"]) - 0.2) < 1e-6 for x in pa), "11 pausas de 0,2 s entre las 12 palabras", str(pa[:2]))
    ok(da_error(qp.palabras_acortar_pausas, 0.5, 0.2) is not None and len(qp._deshacer) == 1, "sin pausas de medio segundo: error claro")
    # una pausa larga entre w5 y w6
    ql, _, _ = ex.armar(src)
    con_palabras(ql)
    ql.subtitulos["palabras"][5]["habla"] = 5.0         # w5 va de 4,9 a 5,8 y w6 de 5,8 a 6,7: entre una y otra, de 5,0 a 6,2 no suena nada
    ql.subtitulos["palabras"][6]["voz"] = 6.2
    ql.subtitulos["huella"] = ql.huella_linea()
    ok(abs(ql.pausas(1.0)[0]["fin"] - ql.pausas(1.0)[0]["inicio"] - 1.2) < 1e-6 and len(ql.pausas(1.0)) == 1, "una pausa larga de 1,2 s")
    r = ql.palabras_acortar_pausas(1.0, 0.4)
    ok(abs(r["duracion"] - 0.8) < 1e-6 and abs(ql.duracion() - 11.2) < 1e-6 and r["pausas"] == 1, "acortarla a 0,4 s saca 0,8 s", str(r))
    ok(ql.validar() == [] and ql.a_dict()["subtitulos_desactualizados"] is False and len(ql.subtitulos["palabras"]) == 12, "no se pierde ninguna palabra y todo sigue al dia")
    w6 = ql.subtitulos["palabras"][6]
    ok(abs((w6["voz"] - ql.subtitulos["palabras"][5]["habla"]) - 0.4) < 1e-6, "la pausa que queda es de 0,4 s", "%.3f" % (w6["voz"] - ql.subtitulos["palabras"][5]["habla"]))
    ok(da_error(ql.palabras_acortar_pausas, 0.5, 0.6) is not None and da_error(ql.palabras_acortar_pausas, "x", 0.2) is not None, "valores raros: error claro")

    print("=== 1e. corregir una palabra ===")
    qc, _, _ = ex.armar(src)
    con_palabras(qc)
    qc.palabra_cambiar(ids(qc)[1], "Mundo")
    ok(qc.subtitulos["palabras"][1]["texto"] == "Mundo" and qc.subtitulos["frases"][0]["texto"] == "w0 Mundo w2", "cambia la palabra y la frase que la tiene")
    for malo, args in (("con espacios", (ids(qc)[0], "dos palabras")), ("vacia", (ids(qc)[0], "  ")), ("que no existe", ("w99", "x")), ("que no es texto", (ids(qc)[0], 5))):
        e = da_error(qc.palabra_cambiar, *args)
        ok(e is not None, "palabra " + malo + ": error claro", e)
    qc.deshacer()
    ok(qc.subtitulos["frases"][0]["texto"] == "w0 w1 w2", "Deshacer")
    # si se cambia a mano el texto de una frase, deja de coincidir con las palabras medidas: se desengancha
    qc.subtitulo_cambiar(qc.subtitulos["frases"][0]["id"], {"texto": "otra cosa distinta"})
    ok("palabras" not in qc.subtitulos["frases"][0], "si se escribe a mano el texto de una frase, deja de estar atada a las palabras medidas")
    qc.subtitulo_cambiar(qc.subtitulos["frases"][1]["id"], {"fin": 5.9})
    ok("palabras" in qc.subtitulos["frases"][1], "(cambiar solo un tiempo no la desengancha)")

    print("=== 1f. guardar, abrir y dividir ===")
    qg, _, _ = ex.armar(src)
    con_palabras(qg)
    qg.palabras_borrar([ids(qg)[2]])
    ruta = os.path.join(TMP, "con_palabras.moviola")
    qg.guardar(ruta)
    qa = Proyecto.cargar(ruta, lambda f: ex.armar(src)[2])
    ok(qa.subtitulos["palabras"] == qg.subtitulos["palabras"] and qa.subtitulos["frases"] == qg.subtitulos["frases"] and qa.validar() == [] and qa.a_dict()["subtitulos_desactualizados"] is False,
       "guardar y abrir conserva las palabras, las frases y que estan al dia")
    qa.palabras_borrar([ids(qa)[0]])
    ok(qa.validar() == [] and len(qa.subtitulos["palabras"]) == 10, "y se puede seguir editando por texto")
    # cortar con la herramienta de dividir NO marca los subtitulos como desactualizados (el montaje es el mismo)
    qd, _, _ = ex.armar(src)
    con_palabras(qd)
    qd.dividir(5.0)
    ok(qd.a_dict()["subtitulos_desactualizados"] is False, "dividir un clip no cambia el montaje: los subtitulos siguen al dia")
    qd.palabras_borrar([ids(qd)[8], ids(qd)[9]])
    ok(qd.validar() == [] and abs(qd.duracion() - 10.2) < 1e-6, "y se puede borrar por texto despues de dividir")
    # un borrado comun (la herramienta Borrar) tambien corre las palabras si estaban al dia
    qb, _, _ = ex.armar(src)
    con_palabras(qb)
    qb.borrar_rango(2.0, 3.0)
    w3 = next(x for x in qb.subtitulos["palabras"] if x["texto"] == "w3")
    ok("w2" not in [x["texto"] for x in qb.subtitulos["palabras"]] and abs(w3["inicio"] - 2.1) < 1e-6 and abs(w3["fin"] - 3.0) < 1e-6,
       "borrar un tramo (2 s a 3 s) con la herramienta de siempre saca la palabra que caia adentro y corre las demas (w3: de 3,1 a 2,1)", str(w3))
    ok(qb.a_dict()["subtitulos_desactualizados"] is False and qb.validar() == [], "y los subtitulos siguen al dia")

    print("=== 1g. al azar ===")
    malos = []
    for semilla in range(150):
        azar = random.Random(semilla)
        z, _, _ = ex.armar(src)
        con_palabras(z, n=azar.choice([6, 9, 12]))
        for paso in range(25):
            op = azar.choice(["borrar_p", "borrar_p", "pausas", "cambiar", "borrar_r", "dividir", "deshacer", "rehacer", "poner", "velocidad", "al_dia", "mala"])
            antes = (json.dumps(z.subtitulos, sort_keys=True), z.huella_linea(), z.duracion())
            try:
                if op == "borrar_p" and z.subtitulos["palabras"]:
                    z.palabras_borrar(azar.sample(ids(z), azar.randint(1, min(3, len(ids(z))))))
                elif op == "pausas":
                    z.palabras_acortar_pausas(azar.choice([0.2, 0.5]), azar.choice([0.0, 0.1]))
                elif op == "cambiar" and z.subtitulos["palabras"]:
                    z.palabra_cambiar(azar.choice(ids(z)), azar.choice(["hola", "ñandú", "x" * 70, "dos palabras"]))
                elif op == "borrar_r" and z.duracion() > 2:
                    t0 = azar.uniform(0, z.duracion() - 1)
                    z.borrar_rango(t0, t0 + azar.uniform(0.1, 1.5))
                elif op == "dividir":
                    z.dividir(azar.uniform(0, z.duracion()))
                elif op == "deshacer":
                    z.deshacer()
                elif op == "rehacer":
                    z.rehacer()
                elif op == "poner":
                    con_palabras(z, n=azar.choice([3, 6]))
                elif op == "velocidad":
                    z.velocidad(z.pista("V1")["clips"][0]["grupo"], azar.choice([0.5, 1.0, 2.0]))
                elif op == "al_dia":
                    z.subtitulos_al_dia()
                elif op == "mala":
                    z.palabras_borrar(azar.choice([["nada"], [], [3], "x"]))
            except ErrorEdicion:
                if (json.dumps(z.subtitulos, sort_keys=True), z.huella_linea(), z.duracion()) != antes:
                    malos.append((semilla, paso, op, "un error dejo el estado cambiado"))
                    break
                continue
            m = z.validar()
            if m:
                malos.append((semilla, paso, op, m[:2]))
                break
    ok(not malos, "150 secuencias al azar (borrar palabras, pausas, corregir, cortar, deshacer, velocidad): siempre valido y un error nunca deja nada a medias", str(malos[:3]))

    # ------------------------------------------------------------------ 2. karaoke
    print("=== 2. karaoke ===")
    frase = [{"id": "s1", "inicio": 1.0, "fin": 5.0, "texto": "uno dos tres cuatro", "palabras": ["a", "b", "c", "d"]}]
    pal = [{"id": "a", "texto": "uno", "inicio": 1.0, "fin": 2.0}, {"id": "b", "texto": "dos", "inicio": 2.0, "fin": 3.0},
           {"id": "c", "texto": "tres", "inicio": 3.0, "fin": 4.0}, {"id": "d", "texto": "cuatro", "inicio": 4.0, "fin": 5.0}]
    ass = sub.a_ass(frase, {"karaoke": True, "resaltado": "coral", "mayusculas": True}, 1080, 1920, None, pal)
    eventos = [l for l in ass.split("\n") if l.startswith("Dialogue:")]
    ok(len(eventos) == 4 and eventos[0].startswith("Dialogue: 0,0:00:01.00,0:00:02.00,") and eventos[3].startswith("Dialogue: 0,0:00:04.00,0:00:05.00,"), "un renglon por palabra, uno detras de otro, sin huecos", eventos[0][:60])
    ok("{\\1c&H5A6DFF&}UNO{\\1c&HFFFFFF&} DOS TRES CUATRO" in eventos[0] and "UNO {\\1c&H5A6DFF&}DOS{\\1c&HFFFFFF&} TRES" in eventos[1], "la palabra que se dice va en el color elegido (coral en BGR), el resto en el de siempre", eventos[1][-70:])
    ass0 = sub.a_ass(frase, {}, 1080, 1920, None, pal)
    ok(len([l for l in ass0.split("\n") if l.startswith("Dialogue:")]) == 1, "sin karaoke: un solo renglon (como siempre)")
    sin_pal = sub.a_ass([{"id": "s1", "inicio": 0.0, "fin": 4.0, "texto": "aa bbbbbb cc"}], {"karaoke": True}, 640, 360)
    ev = [l for l in sin_pal.split("\n") if l.startswith("Dialogue:")]
    ok(len(ev) == 3 and ev[1].startswith("Dialogue: 0,0:00:00.80,0:00:03.20,") and ev[2].startswith("Dialogue: 0,0:00:03.20,0:00:04.00,"), "una frase sin palabras medidas reparte el tiempo segun las letras de cada palabra (0,8 / 2,4 / 0,8 s)", ev[1][:50])
    cambiada = sub.a_ass([dict(frase[0], texto="uno dos tres CINCO")], {"karaoke": True}, 640, 360, None, pal)
    ok(len([l for l in cambiada.split("\n") if l.startswith("Dialogue:")]) == 4 and "CINCO" in cambiada.split("Dialogue:")[-1], "si el texto ya no coincide con las palabras medidas, se reparte por letras (no se rompe)")
    raro = sub.a_ass([{"id": "s1", "inicio": 0.0, "fin": 2.0, "texto": "{\\an9}hola\\n mundo"}], {"karaoke": True}, 640, 360)
    ok("\\an9" not in raro.split("Dialogue:")[1], "las llaves y barras no se interpretan como codigos")
    ok(sub.limpiar_estilo({"karaoke": True, "resaltado": "verde"})["resaltado"] == "verde", "el estilo acepta karaoke y un color de resalte")
    try:
        sub.limpiar_estilo({"resaltado": "fucsia"})
        ok(False, "un color de resalte que no existe")
    except sub.ErrorSubtitulo as e:
        ok("opción" in str(e), "un color de resalte que no existe: error claro", str(e))

    print("=== 2b. karaoke quemado: la palabra resaltada se corre (medido en la imagen) ===")
    pk, _, _ = ex.armar(src)
    pk.subtitulos_poner([{"inicio": 1.0, "fin": 5.0, "texto": "uno dos tres cuatro", "palabras": [0, 1, 2, 3]}],
                        [{"texto": "uno", "inicio": 1.0, "fin": 2.0}, {"texto": "dos", "inicio": 2.0, "fin": 3.0}, {"texto": "tres", "inicio": 3.0, "fin": 4.0}, {"texto": "cuatro", "inicio": 4.0, "fin": 5.0}])
    pk.subtitulos_estilo({"tamano": 9.0})
    normal = im.todos_los_cuadros(im.exportar(pk, "k_normal", subtitulos={"quemar": True})[0])
    pk.subtitulos_estilo({"karaoke": True, "resaltado": "amarillo"})
    kara = im.todos_los_cuadros(im.exportar(pk, "k_karaoke", subtitulos={"quemar": True})[0])
    centros = []
    for n in (45, 75, 105, 135):
        c = caja_azul(kara[n], normal[n])
        centros.append(None if c is None else (c[0] + c[2]) / 2.0)
    ok(all(c is not None for c in centros) and centros == sorted(centros) and centros[-1] - centros[0] > 120, "la parte amarilla pasa de izquierda a derecha, una palabra por segundo", str([None if c is None else round(c) for c in centros]))
    c_fuera = caja_azul(kara[15], normal[15])
    c_antes = caja_azul(kara[160], normal[160])
    ok(c_fuera is None and c_antes is None, "antes y despues de la frase no hay nada")
    sin_resalte = im.dif_media(kara[45], normal[45])
    ok(sin_resalte > 0.05, "y el cuadro es distinto del normal (hay resalte)")

    # ------------------------------------------------------------------ 3. con whisper
    print("=== 3. con whisper (tiempos por palabra reales) ===")
    est = sub.estado_transcripcion()
    palabras_base = ["Hola", "esto", "es", "una", "prueba", "de", "subtítulos", "además", "tengo", "que", "decir", "canción", "niño", "pingüino", "ahora", "hablamos", "otra", "cosa", "muy", "distinta"]
    if not est["disponible"]:
        print("  SALTEADA  la parte con whisper (falta whisper o su modelo)")
        return cierre()
    verdad, recortes, t = [], [], 0.0
    ok_voz = True
    for i, pal_ in enumerate(palabras_base):
        r = os.path.join(TMP, "p%d.wav" % i)
        if not voz.sintetizar(r, pal_):
            ok_voz = False
            break
        ex.ffmpeg("-i", r, "-ar", "16000", "-ac", "1", os.path.join(TMP, "p%d_16.wav" % i))
        env = sub.envolvente(os.path.join(TMP, "p%d_16.wav" % i))
        activo = [k for k, e in enumerate(env) if e > -45]
        ini, fin = (activo[0] * 0.01, (activo[-1] + 1) * 0.01) if activo else (0, len(env) * 0.01)
        ini0, fin0 = max(0.0, ini - 0.03), fin + 0.03
        rec = os.path.join(TMP, "p%d_rec.wav" % i)
        ex.ffmpeg("-i", r, "-ss", "%.3f" % ini0, "-t", "%.3f" % (fin0 - ini0), "-ar", "48000", "-ac", "1", rec)
        recortes.append(rec)
        verdad.append((pal_, t + (ini - ini0), t + (fin - ini0)))
        t += (fin0 - ini0) + 0.08
    if not ok_voz:
        print("  SALTEADA  la parte con whisper (falta una voz de Windows para el audio de prueba)")
        return cierre()
    entradas, filtro, partes = [], [], []
    for i, r in enumerate(recortes):
        entradas += ["-i", r]
        filtro.append("[%d:a]apad=pad_dur=0.08[v%d]" % (i + 1, i))
        partes.append("[v%d]" % i)
    mp4 = os.path.join(TMP, "verdad.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=%.2f,format=yuv420p" % (t + 0.5), *entradas, "-filter_complex", ";".join(filtro) + ";" + "".join(partes) + "concat=n=%d:v=0:a=1[o]" % len(partes),
          "-map", "0:v", "-map", "[o]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mp4)
    pv, _, _ = ex.armar(mp4)
    res = sub.transcribir_completo(pv, "es", 32)
    ws = res["palabras"]
    ok(res["dtw"], "whisper midio con DTW (tiempo de cada palabra)")
    ok([norm(w["texto"]) for w in ws] == [norm(x[0]) for x in verdad], "reconoce las 20 palabras, en orden y con sus tildes y eñes", " ".join(w["texto"] for w in ws))
    ok(any("ñ" in w["texto"] for w in ws) and any("ü" in w["texto"] for w in ws) and any("í" in w["texto"] for w in ws), "(ñ, ü e í quedan bien: los tokens partidos se unen por bytes)")
    errores = [abs(w["voz"] - v[1]) for w, v in zip(ws, verdad)]
    fin_err = [abs(w["habla"] - v[2]) for w, v in zip(ws, verdad)]
    ok(max(errores) < 0.08 and sum(errores) / len(errores) < 0.04, "cuando empieza a sonar cada palabra: error maximo %.0f ms, medio %.0f ms (tope 80 / 40)" % (max(errores) * 1000, sum(errores) / len(errores) * 1000))
    ok(max(fin_err) < 0.1, "y cuando deja de sonar: error maximo %.0f ms (tope 100)" % (max(fin_err) * 1000))
    ok(all(ws[i]["fin"] == ws[i + 1]["inicio"] for i in range(len(ws) - 1)) and all(w["inicio"] <= w["voz"] <= w["habla"] <= w["fin"] for w in ws), "cada palabra llega hasta que empieza la siguiente, y inicio <= voz <= habla <= fin")
    ok(all(v[1] - 0.05 <= w["fin"] <= verdad[i + 1][1] + 0.05 for i, (w, v) in enumerate(zip(ws[:-1], verdad[:-1]))), "los cortes caen en el silencio ENTRE palabras (nunca adentro de una)")
    ok(sum(len(f.get("palabras", [])) for f in res["frases"]) == len(ws), "cada palabra pertenece a una frase")
    # ponerlas en el proyecto
    pv.subtitulos_poner(res["frases"], res["palabras"])
    ok(pv.validar() == [] and len(pv.subtitulos["palabras"]) == 20, "entran al proyecto (valido)")

    print("=== 3b. borrar una muletilla del texto y volver a transcribir lo exportado ===")
    textos = ["Hola, esto es una prueba de subtítulos.", "Ahora hablamos de otra cosa muy distinta, eh, bueno, creo que sí."]
    hablado, tramos = voz.video_hablado(os.path.join(TMP, "hablado.mp4"), textos, pausa=3.0)
    if not hablado:
        print("  SALTEADA  borrar por texto con voz real (falta una voz de Windows)")
        return cierre()
    ph, _, _ = ex.armar(hablado)
    r = sub.transcribir_completo(ph, "es", 32)
    ph.subtitulos_poner(r["frases"], r["palabras"])
    pal = ph.subtitulos["palabras"]
    print("      palabras:", " ".join("%s(%.2f)" % (w["texto"], w["inicio"]) for w in pal))
    eh = next((w for w in pal if norm(w["texto"]).startswith("eh")), None)
    ok(eh is not None, "whisper reconoce la muletilla «eh»", str([w["texto"] for w in pal]))
    if eh is None:
        return cierre()
    dur_antes = ph.duracion()
    cant = len(pal)
    ph.palabras_borrar([eh["id"]])
    ok(abs((dur_antes - ph.duracion()) - (eh["fin"] - eh["inicio"])) < 0.04 and len(ph.subtitulos["palabras"]) == cant - 1, "el montaje se acorta lo que duraba la palabra (%.2f s)" % (eh["fin"] - eh["inicio"]))
    arch, rr = im.exportar(ph, "sin_eh", formato="original")
    pf, _, _ = ex.armar(arch)
    r2 = sub.transcribir_completo(pf, "es", 32)
    despues = [norm(w["texto"]) for w in r2["palabras"]]
    ok(not any(x.startswith("eh") for x in despues), "volver a transcribir el video exportado: la muletilla ya no esta", " ".join(despues))
    esperadas = [norm(w["texto"]) for w in pal if w["id"] != eh["id"]]
    comunes = sum(1 for x in esperadas if x in despues)
    ok(comunes >= len(esperadas) - 2, "y las demas palabras siguen estando enteras (%d de %d: nada comido por el corte)" % (comunes, len(esperadas)))
    # los subtitulos del modelo coinciden con lo que se transcribe del video final
    from collections import Counter
    unica = lambda lista: {k for k, n in Counter(lista).items() if n == 1}
    en_modelo = [norm(w["texto"]) for w in ph.subtitulos["palabras"]]
    unicas = unica(en_modelo) & unica(despues)
    modelo = {norm(w["texto"]): w["voz"] for w in ph.subtitulos["palabras"] if norm(w["texto"]) in unicas}
    desfases = [abs(w["voz"] - modelo[norm(w["texto"])]) for w in r2["palabras"] if norm(w["texto"]) in unicas]
    ok(len(desfases) >= 8 and max(desfases) < 0.2, "los tiempos de las palabras en el proyecto coinciden con los del video exportado, al transcribirlo de nuevo (%d palabras comparadas; maximo %.0f ms)" % (len(desfases), max(desfases) * 1000 if desfases else -1))

    print("=== 3c. pausas largas ===")
    pl = ph.pausas(1.0)
    ok(len(pl) >= 1 and any(3.0 < (x["fin"] - x["inicio"]) < 4.2 for x in pl), "la pausa de 3 s entre las dos frases (mas el aire de la voz) se detecta como pausa larga", str([round(x["fin"] - x["inicio"], 2) for x in pl]))
    d0 = ph.duracion()
    ph.palabras_acortar_pausas(1.0, 0.5)
    ok(d0 - ph.duracion() > 2.0, "acortarla a 0,5 s saca mas de 2 s", "%.2f s" % (d0 - ph.duracion()))
    arch2, _ = im.exportar(ph, "sin_pausa", formato="original")
    r3 = sub.transcribir_completo(ex.armar(arch2)[0], "es", 32)
    ok(len(r3["palabras"]) >= len(ph.subtitulos["palabras"]) - 2, "y las palabras siguen enteras despues de acortar (%d de %d)" % (len(r3["palabras"]), len(ph.subtitulos["palabras"])))
    ok(ph.validar() == [], "proyecto valido")
    return cierre()


def cierre():
    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
