# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 4a (tiempo): velocidad, camara lenta, reversa, repetir y ducking.

Uso:  python -I pruebas/prueba_tiempo.py

La velocidad cambia lo que DURA un clip: es la regla de tiempo del modelo. Se verifica con el modelo (duraciones, cortes,
transiciones, silencios) y MIDIENDO el archivo exportado: la duracion, el numero de cada cuadro (codigo de barras), el gris de cada
instante y la frecuencia del tono de cada segundo.
"""

import os
import random
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

import av  # noqa: E402

import prueba_exportar as ex  # noqa: E402
from motor import efectos, silencios  # noqa: E402
from motor.exportar import ExportError  # noqa: E402
from motor.proyecto import Proyecto, ErrorEdicion  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def da_error(f, *a, **k):
    try:
        f(*a, **k)
    except ErrorEdicion as e:
        return str(e)
    return None


def cuadros(ruta):
    c = av.open(ruta)
    out = [f.to_image().convert("L") for f in c.decode(c.streams.video[0])]
    c.close()
    return out


def exportar(p, nombre, **kw):
    r = ex.exportar_a(p, nombre, **kw)
    return r["archivo"], r


def durs(ruta):
    v, a, d = ex.sondear(ruta)
    return float(v["duration"]), float(a["duration"]) if a else None


def main():
    # ----------------------------------------------------------------- fuentes de laboratorio
    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=12)                       # codigo de barras por cuadro + tono que sube 50 Hz/s
    colores = os.path.join(TMP, "colores.mp4")                                         # gris Y=10+20*s y tono 300+50*s Hz en el segundo s
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=12,format=yuv420p,geq=lum='10+20*floor(T)':cb=128:cr=128",
              "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*(300+50*floor(t))*t)':s=48000:d=12:c=mono",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", colores)

    def nivel(t_):
        return max(0.0, min(255.0, (10 + 20 * int(t_) - 16) * 255 / 219))

    # ----------------------------------------------------------------- 1. el modelo
    print("=== 1. la regla de tiempo del modelo ===")
    p, fid, tiempos = ex.armar(src)
    g = p.pista("V1")["clips"][0]["grupo"]
    ok(abs(p.velocidad(g, 2.0) - 6.0) < 1e-6 and abs(p.duracion() - 6.0) < 1e-6, "a 2x un clip de 12 s dura 6 s", p.duracion())
    ok(all(abs(p.largo(c) - 6.0) < 1e-6 for pp in p.pistas for c in pp["clips"]), "el video y su audio enlazado cambian juntos")
    ok(p.validar() == [], "el proyecto sigue valido", p.validar())
    p.dividir(3.0)
    izq, der = p.pista("V1")["clips"]
    ok(abs(izq["hasta"] - 6.0) < 0.04 and abs(der["desde"] - 6.0) < 0.04 and abs(p.fin(izq) - 3.0) < 0.04, "cortar a los 3 s de la linea de tiempo corta la FUENTE a los 6 s", f"{izq['hasta']}")
    ok(p.validar() == [], "y todo sigue valido (los cortes caen en limites de cuadro de la fuente)")
    ok(da_error(p.velocidad, izq["grupo"], 0.1) is not None and da_error(p.velocidad, izq["grupo"], 5.0) is not None, "fuera de 0,25-4 veces se rechaza con un mensaje que lo dice", da_error(p.velocidad, izq["grupo"], 5.0))
    # cambiar la velocidad de un clip del medio corre todo lo que sigue, en todas las pistas
    q, fid2, _ = ex.armar(src)
    q.dividir(4.0)
    q.dividir(8.0)
    musica = os.path.join(TMP, "musica.mp3")
    ex.crear_musica(musica, 8, 700)
    mid = q.pista("V1")["clips"][1]
    ex.agregar_audio_archivo(q, musica, inicio=9.0, hasta=3.0)
    q.velocidad(mid["grupo"], 0.5)
    cv = q.pista("V1")["clips"]
    ok(abs(q.fin(cv[1]) - 12.0) < 1e-6 and abs(cv[2]["inicio"] - 12.0) < 1e-6 and abs(q.duracion() - 16.0) < 1e-6, "a 0,5x el clip del medio dura el doble y lo que sigue se corre", f"{[round(c['inicio'], 2) for c in cv]}")
    ok(abs(q.pista("A1")["clips"][2]["inicio"] - 12.0) < 1e-6 and abs(q.pista("A2")["clips"][0]["inicio"] - 13.0) < 1e-6, "tambien en el audio enlazado y en la musica que empezaba despues (queda igual de lejos del final)", f"A2 {q.pista('A2')['clips'][0]['inicio']}")
    q.deshacer()
    ok(abs(q.duracion() - 12.0) < 1e-6 and q.pista("A2")["clips"][0]["inicio"] == 9.0, "un solo deshacer lo devuelve todo")
    # la musica que se pisaria: error limpio y no cambia nada
    q2, _, _ = ex.armar(src)
    q2.dividir(4.0)
    q2.dividir(8.0)
    ex.agregar_audio_archivo(q2, musica, inicio=0.0, hasta=8.0)
    ex.agregar_audio_archivo(q2, musica, inicio=8.0, hasta=3.0)
    ok(da_error(q2.velocidad, q2.pista("V1")["clips"][0]["grupo"], 2.0) is not None and abs(q2.duracion() - 12.0) < 1e-6,
       "si cambiar la velocidad haria que dos musicas se pisen (a 2x lo que sigue se corre 2 s para atras): error claro y no cambia nada", da_error(q2.velocidad, q2.pista("V1")["clips"][0]["grupo"], 2.0))
    # reversa
    r_, _, _ = ex.armar(src)
    r_.dividir(6.0)
    primero = r_.pista("V1")["clips"][0]
    r_.reversa(primero["grupo"])
    r_.dividir(2.0)
    a_, b_ = r_.pista("V1")["clips"][0], r_.pista("V1")["clips"][1]
    ok(a_["desde"] > 3.9 and abs(a_["hasta"] - 6.0) < 1e-6 and abs(b_["desde"]) < 1e-6 and abs(b_["hasta"] - 4.0) < 0.04 and r_.validar() == [],
       "cortar un clip al reves: la mitad de la izquierda se queda con el FINAL de la fuente", f"[{a_['desde']},{a_['hasta']}] [{b_['desde']},{b_['hasta']}]")
    r2, _, _ = ex.armar(src)
    r2.dividir(4.0)
    r2.dividir(8.0)
    r2.borrar_rango(4.0, 8.0)
    r2.poner_transicion(r2.pista("V1")["clips"][1]["grupo"], "disolver", 1.0)
    ok(da_error(r2.reversa, r2.pista("V1")["clips"][1]["grupo"]) is not None, "un clip con transicion no se puede poner al reves (y viceversa)", da_error(r2.reversa, r2.pista("V1")["clips"][1]["grupo"]))
    r2.quitar_transicion(r2.pista("V1")["clips"][1]["grupo"])
    r2.reversa(r2.pista("V1")["clips"][1]["grupo"])
    ok(r2.transicion_maxima(r2.pista("V1")["clips"][1]["id"]) == 0.0, "y un clip al reves no admite transicion")
    # velocidad + transicion: el material sobrante se cuenta en segundos de la linea de tiempo
    t1, _, _ = ex.armar(src)
    t1.dividir(4.0)
    t1.dividir(8.0)
    t1.borrar_rango(4.0, 8.0)
    gb = t1.pista("V1")["clips"][1]["grupo"]
    t1.velocidad(gb, 4.0)
    ok(abs(t1.transicion_maxima(t1.pista("V1")["clips"][1]["id"]) - 2.0) < 1e-6 and t1.validar() == [], "a 4x el clip de 4 s dura 1 s: la mitad de la transicion (1 s) tiene que caber en el, o sea hasta 2 s", t1.transicion_maxima(t1.pista("V1")["clips"][1]["id"]))
    t1.poner_transicion(gb, "disolver", 1.5)
    ok(t1.validar() == [] and abs(t1.duracion() - 5.0) < 1e-6, "y se puede poner: el proyecto sigue valido y durando 5 s", t1.duracion())
    # repetir
    s_, _, tiemposs = ex.armar(src)
    s_.dividir(2.0)
    s_.dividir(3.0)
    uno = s_.pista("V1")["clips"][1]
    res = s_.repetir_grupo(uno["grupo"], 3)
    ok(res == {"veces": 3, "duracion": 3.0} and abs(s_.duracion() - 14.0) < 1e-6 and len(s_.pista("V1")["clips"]) == 5 and s_.validar() == [],
       "repetir 3 veces un clip de 1 s: +2 s, 5 clips y todo valido", str(res))
    ok(da_error(s_.repetir_grupo, uno["grupo"], 1) is not None and da_error(s_.repetir_grupo, uno["grupo"], 99) is not None, "fuera de 2-20 veces se rechaza")
    s_.deshacer()
    ok(abs(s_.duracion() - 12.0) < 1e-6, "y un deshacer devuelve el original")
    # ducking
    d_, _, _ = ex.armar(src)
    ex.agregar_audio_archivo(d_, musica, inicio=0.0, hasta=8.0)
    d_.ducking("A2", True, 12)
    ok(d_.pista("A2")["ducking"] == {"activo": True, "reduccion": 12} and d_.validar() == [], "ducking en la pista de musica")
    ok(da_error(d_.ducking, "A1") is not None and da_error(d_.ducking, "V1") is not None and da_error(d_.ducking, "A2", True, 99) is not None, "no en el audio del video, ni en el video, ni con un valor fuera de rango")
    d_.deshacer()
    ok("ducking" not in d_.pista("A2"), "y se deshace")

    # propiedades al azar con velocidad, reversa y repetir
    print("=== 2. secuencias al azar con velocidad, reversa y repetir ===")
    malos, total = [], 0
    for semilla in range(250):
        azar = random.Random(900 + semilla)
        pp, _, _ = ex.armar(src)
        inicial = pp.a_dict()["pistas"]
        for paso in range(16):
            op = azar.choice(["velocidad", "velocidad", "reversa", "repetir", "dividir", "dividir", "borrar", "deshacer", "rehacer", "transicion"])
            clips = pp.pista("V1")["clips"]
            if not clips:
                break
            antes = pp.a_dict()["pistas"]
            try:
                if op == "velocidad":
                    pp.velocidad(azar.choice(clips)["grupo"], azar.choice([0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, azar.uniform(0.25, 4.0)]), azar.random() < 0.5, azar.random() < 0.3)
                elif op == "reversa":
                    pp.reversa(azar.choice(clips)["grupo"], azar.random() < 0.6)
                elif op == "repetir":
                    pp.repetir_grupo(azar.choice(clips)["grupo"], azar.randint(2, 4))
                elif op == "dividir":
                    pp.dividir(azar.uniform(0, pp.duracion()))
                elif op == "borrar":
                    a, b = sorted((azar.uniform(0, pp.duracion()), azar.uniform(0, pp.duracion())))
                    pp.borrar_rango(a, b)
                elif op == "transicion":
                    pp.poner_transicion(azar.choice(clips)["grupo"], "disolver", azar.uniform(0.1, 2.0))
                elif op == "deshacer":
                    pp.deshacer()
                else:
                    pp.rehacer()
            except ErrorEdicion:
                if pp.a_dict()["pistas"] != antes:
                    malos.append((semilla, paso, op, "un error dejo el estado cambiado"))
                    break
                continue
            total += 1
            prob = pp.validar()
            v1, a1 = pp.pista("V1")["clips"], pp.pista("A1")["clips"]
            if prob or len(v1) != len(a1) or any(abs(pp.largo(x) - pp.largo(y)) > 1e-4 or abs(x["inicio"] - y["inicio"]) > 1e-4 for x, y in zip(v1, a1)):
                malos.append((semilla, paso, op, prob[:2] or "video y audio se desincronizaron"))
                break
            t_ = 0.0
            for x in v1:
                if abs(x["inicio"] - t_) > 1e-4:
                    malos.append((semilla, paso, op, "hueco en V1 en %s" % t_))
                    break
                t_ = pp.fin(x)
            else:
                continue
            break
        else:
            while pp.puede_deshacer():
                pp.deshacer()
            if pp.a_dict()["pistas"] != inicial:
                malos.append((semilla, "fin", "deshacer todo", "no volvio al estado inicial"))
    ok(not malos, "250 secuencias (%d operaciones): siempre valido, video y audio sincronizados, sin huecos, y deshacer todo vuelve al principio" % total, str(malos[:2]))

    # ----------------------------------------------------------------- 3. exportado, medido
    print("=== 3. velocidad medida en el archivo exportado ===")
    p, fid, tiempos = ex.armar(src)
    p.velocidad(p.pista("V1")["clips"][0]["grupo"], 2.0)
    arch, r = exportar(p, "tm_x2")
    c2 = ex.leer_codigos(arch)
    dv, da_ = durs(arch)
    ok(abs(r["duracion"] - 6.0) < 0.08 and len(c2) == 180 and abs(dv - da_) < 0.05, "2x: dura 6 s, 180 cuadros, y el audio dura lo mismo que el video", f"{r['duracion']:.2f} s, {len(c2)} cuadros, video {dv:.2f} audio {da_:.2f}")
    ok(all(abs(c2[k] - 2 * k) <= 1 for k in range(len(c2))), "y cada cuadro es el que toca de la fuente (0, 2, 4, 6...)", str([(k, c2[k]) for k in range(0, 180, 45)]))
    p, fid, tiempos = ex.armar(src)
    p.recortar_a(0.0, 4.0)
    p.velocidad(p.pista("V1")["clips"][0]["grupo"], 0.5)
    arch, r = exportar(p, "tm_x05")
    c05 = ex.leer_codigos(arch)
    ok(abs(r["duracion"] - 8.0) < 0.08 and len(c05) == 240 and all(abs(c05[k] - k // 2) <= 1 for k in range(240)), "0,5x: 4 s pasan a 8 s, 240 cuadros, cada uno repetido (camara lenta)", f"{r['duracion']:.2f} s, {len(c05)} cuadros")
    ok(abs(durs(arch)[0] - durs(arch)[1]) < 0.05, "con el audio de la misma duracion")
    # camara lenta suave: los cuadros intermedios se inventan (no se repite el anterior)
    p.velocidad(p.pista("V1")["clips"][0]["grupo"], 0.5, True, True)
    arch_i, r_i = exportar(p, "tm_x05_suave")
    cs, ci = cuadros(arch), cuadros(arch_i)

    def iguales(lista):
        """Que fraccion de los cuadros seguidos son repetidos (el video comprimido no los deja identicos al bit: se mide la diferencia)."""
        from PIL import ImageChops, ImageStat
        return sum(1 for a, b in zip(lista, lista[1:]) if ImageStat.Stat(ImageChops.difference(a, b)).mean[0] < 0.4) / max(1, len(lista) - 1)

    ok(len(ci) == 240 and iguales(cs) > 0.4 and iguales(ci) < 0.1, "camara lenta suave (minterpolate): sin cuadros repetidos y la misma cantidad de cuadros", f"repetidos: {iguales(cs):.0%} -> {iguales(ci):.0%}")
    # el gris de cada instante (colores) y el tono, a otra velocidad
    pc, _, _ = ex.armar(colores)
    pc.velocidad(pc.pista("V1")["clips"][0]["grupo"], 2.0)
    archc, rc = exportar(pc, "tm_colores_x2")
    cc = cuadros(archc)
    ok(abs(cc[int(1.0 * 30)].getpixel((160, 90)) - nivel(2.0)) < 6 and abs(cc[int(4.0 * 30)].getpixel((160, 90)) - nivel(8.0)) < 6, "a 2x, en el segundo 1 de la linea se ve el segundo 2 de la fuente, y en el 4 el 8", f"{cc[30].getpixel((160, 90))} / {cc[120].getpixel((160, 90))}")
    m = ex.muestras(archc)
    f1 = ex.frecuencia(m, 0.55, 0.95)           # linea 0,5-1 s = fuente 1-2 s = 350 Hz (con el tono conservado)
    ok(abs(f1 - 350) < 25, "el audio a 2x CONSERVA el tono (350 Hz siguen siendo 350 Hz)", f"{f1:.0f} Hz")
    pc.velocidad(pc.pista("V1")["clips"][0]["grupo"], 2.0, False)
    archt, _ = exportar(pc, "tm_colores_x2_cinta")
    f2 = ex.frecuencia(ex.muestras(archt), 0.55, 0.95)
    ok(abs(f2 - 700) < 50, "y 'como una cinta' (sin conservar el tono) suena una octava mas arriba (700 Hz)", f"{f2:.0f} Hz")

    print("=== 4. reversa, repetir y mezcla de velocidades ===")
    p, fid, tiempos = ex.armar(src)
    p.recortar_a(0.0, 4.0)
    p.reversa(p.pista("V1")["clips"][0]["grupo"])
    arch, r = exportar(p, "tm_reves")
    cr = ex.leer_codigos(arch)
    ok(len(cr) == 120 and cr == list(range(119, -1, -1)), "reversa: los 120 cuadros salen exactamente al reves (119, 118 ... 0)", f"{cr[:3]}...{cr[-3:]}")
    mr = ex.muestras(arch)
    ok(ex.frecuencia(mr, 0.25, 0.75) > ex.frecuencia(mr, 3.25, 3.75) + 100, "y el audio tambien: el tono que subia ahora baja", f"{ex.frecuencia(mr, 0.25, 0.75):.0f} -> {ex.frecuencia(mr, 3.25, 3.75):.0f} Hz")
    ok(abs(durs(arch)[0] - durs(arch)[1]) < 0.05, "con la misma duracion en imagen y sonido")
    p, fid, tiempos = ex.armar(src)
    p.dividir(2.0)
    p.dividir(3.0)
    p.repetir_grupo(p.pista("V1")["clips"][1]["grupo"], 3)
    arch, r = exportar(p, "tm_repetir")
    crp = ex.leer_codigos(arch)
    esp = ex.esperados(p, tiempos)
    ok(len(crp) == len(esp) == 420 and crp == esp and crp[60:150] == list(range(60, 90)) * 3, "repetir x3: el tramo de 1 s se ve tres veces seguidas y los cuadros siguen exactos", f"{len(crp)} cuadros")
    # tres clips con velocidades distintas: ni el video ni el audio se corren
    p, fid, tiempos = ex.armar(src)
    p.dividir(4.0)
    p.dividir(8.0)
    cl = p.pista("V1")["clips"]
    p.velocidad(cl[0]["grupo"], 0.5)
    p.velocidad(p.pista("V1")["clips"][2]["grupo"], 2.0)
    arch, r = exportar(p, "tm_mezcla")
    dv, da_ = durs(arch)
    ok(abs(p.duracion() - (8 + 4 + 2)) < 0.01 and abs(r["duracion"] - 14.0) < 0.1 and abs(dv - da_) < 0.05, "0,5x + 1x + 2x: 8 + 4 + 2 = 14 s, imagen y sonido de la misma duracion", f"{r['duracion']:.2f} s, video {dv:.2f}, audio {da_:.2f}")
    cm = ex.leer_codigos(arch)
    esp = ex.esperados(p, tiempos)
    ok(len(cm) == 14 * 30 and all(abs(cm[k] - esp[min(k, len(esp) - 1)]) <= 120 for k in range(0, len(cm), 30)) and abs(cm[8 * 30 + 15] - (120 + 15)) <= 1 and abs(cm[12 * 30 + 15] - (240 + 2 * 15)) <= 2,
       "y cada tramo muestra lo que corresponde (el 1x arranca en el cuadro 120; el 2x salta de a dos)", f"{len(cm)} cuadros; {cm[8 * 30 + 15]} y {cm[12 * 30 + 15]}")
    # el limite de memoria de la reversa
    largo = ex.crear_fuente(os.path.join(TMP, "largo.mp4"), dur=60)
    pl, _, _ = ex.armar(largo)
    pl.reversa(pl.pista("V1")["clips"][0]["grupo"])
    try:
        exportar(pl, "tm_reves_largo", formato="vertical")
        ok(False, "un clip al reves de 60 s en 1080x1920 se rechaza")
    except ExportError as e:
        ok("memoria" in str(e), "un clip al reves de 60 s en 1080x1920 (5,6 GB de cuadros): error claro ANTES de empezar", str(e))

    # velocidad + transicion en el mismo proyecto (un clip a 1,5x seguido de otro con transicion): el largo de cada tramo se cuenta en la linea de tiempo
    p, fid, tiempos = ex.armar(src)
    p.recortar_a(0.0, 6.0)
    p.dividir(3.0)
    va, vb = p.pista("V1")["clips"]
    p.poner_transicion(vb["grupo"], "disolver", 1.0)
    p.velocidad(va["grupo"], 1.5)
    arch, r = exportar(p, "tm_vel_trans")
    cc = ex.leer_codigos(arch)
    dv, da = durs(arch)
    ok(len(cc) == 150 and abs(dv - 5.0) < 0.05 and abs(da - 5.0) < 0.05 and p.validar() == [], "un clip a 1,5x seguido de otro con transicion: 150 cuadros y 5 s en imagen y en sonido", f"{len(cc)} cuadros, {dv:.2f} s / {da:.2f} s")
    ok(cc[0] == 0 and abs(cc[10] - 15) <= 1 and abs(cc[40] - 60) <= 1 and cc[-1] >= 176, "y cada cuadro sale de donde corresponde de la fuente (0, 15 a los 10, 60 a los 40, y el final)", f"{cc[0]}, {cc[10]}, {cc[40]}, {cc[-1]}")

    print("=== 5. ducking medido ===")
    voz = os.path.join(TMP, "voz.mp4")
    mudo = ex.crear_fuente(os.path.join(TMP, "mudo12.mp4"), dur=12, tono=False)
    ex.ffmpeg("-i", mudo, "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*440*t)*lt(t,6)':s=48000:d=12:c=mono", "-c:v", "copy", "-c:a", "aac", "-shortest", voz)
    tono1k = os.path.join(TMP, "mil.mp3")
    ex.ffmpeg("-f", "lavfi", "-i", "sine=f=1000:d=12", "-c:a", "libmp3lame", tono1k)
    pd, _, _ = ex.armar(voz)
    ex.agregar_audio_archivo(pd, tono1k, inicio=0.0, hasta=12.0)
    base_m = ex.muestras(exportar(pd, "tm_duck_sin")[0])
    pd.ducking("A2", True, 12)
    duck_m = ex.muestras(exportar(pd, "tm_duck_con")[0])
    nivel_sin = ex.rms(base_m, 2.0, 5.0)
    nivel_con = ex.rms(duck_m, 2.0, 5.0)
    libre_con = ex.rms(duck_m, 8.0, 11.0)
    libre_sin = ex.rms(base_m, 8.0, 11.0)
    import math
    bajada = 20 * math.log10(max(1e-9, ex.goertzel(duck_m, 2.0, 5.0, 1000)) / max(1e-9, ex.goertzel(base_m, 2.0, 5.0, 1000))) / 2   # goertzel es potencia
    ok(-18 < bajada < -6, "ducking de 12 dB: mientras habla la voz, la musica baja unos 12 dB", f"{bajada:.1f} dB")
    ok(abs(libre_con - libre_sin) / libre_sin < 0.1, "y cuando la voz calla, la musica vuelve a su nivel", f"{libre_sin:.3f} -> {libre_con:.3f}")
    ok(ex.goertzel(duck_m, 2.0, 5.0, 440) > 0.8 * ex.goertzel(base_m, 2.0, 5.0, 440), "la voz NO se toca", f"{ex.goertzel(duck_m, 2.0, 5.0, 440):.2e} vs {ex.goertzel(base_m, 2.0, 5.0, 440):.2e}")

    print("=== 6. silencios con velocidad ===")
    hablado = os.path.join(TMP, "hablado.mp4")
    ex.ffmpeg("-i", mudo, "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*440*t)*(1-between(t,3,5)-between(t,8,9.5))':s=48000:d=12:c=mono",
              "-c:v", "copy", "-c:a", "aac", "-shortest", hablado)
    ph, _, _ = ex.armar(hablado)
    ph.velocidad(ph.pista("V1")["clips"][0]["grupo"], 2.0)
    s = silencios.analizar(ph, -35.0, 0.5, 0.0)["silencios"]
    ok(len(s) == 2 and abs(s[0]["inicio"] - 1.5) < 0.1 and abs(s[0]["fin"] - 2.5) < 0.1 and abs(s[1]["inicio"] - 4.0) < 0.1, "a 2x los silencios (3-5 s y 8-9,5 s de la fuente) caen en 1,5-2,5 s y 4-4,75 s de la linea de tiempo", str(s))
    ph.borrar_rangos([(x["inicio"], x["fin"]) for x in s])
    ok(abs(ph.duracion() - (6.0 - 1.0 - 0.75)) < 0.1 and ph.validar() == [], "y cortarlos funciona", ph.duracion())
    pr, _, _ = ex.armar(hablado)
    pr.reversa(pr.pista("V1")["clips"][0]["grupo"])
    s = silencios.analizar(pr, -35.0, 0.5, 0.0)["silencios"]
    ok(len(s) == 2 and abs(s[0]["inicio"] - 2.5) < 0.1 and abs(s[0]["fin"] - 4.0) < 0.1 and abs(s[1]["inicio"] - 7.0) < 0.1 and abs(s[1]["fin"] - 9.0) < 0.1, "y en reversa se leen al reves (12 - 9,5 = 2,5 ... 12 - 8 = 4 y 12 - 5 = 7 ... 12 - 3 = 9)", str(s))

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
