# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 2 (audio): los efectos de audio, detectar y cortar silencios, y medir el volumen.

Uso:  python -I pruebas/prueba_audio.py

Todo se comprueba MIDIENDO el archivo que sale (nivel, frecuencia, picos, duracion), con sonidos de
laboratorio: tonos de frecuencia conocida, ruido, silencios en lugares conocidos.
"""

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

import prueba_exportar as ex  # noqa: E402
from motor import efectos, silencios  # noqa: E402
from motor.proyecto import Proyecto, ErrorEdicion  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def audio(nombre, expresion, dur):
    """Un wav mono de 48 kHz hecho con una expresion de ffmpeg (t es el tiempo)."""
    ruta = os.path.join(TMP, nombre)
    ex.ffmpeg("-f", "lavfi", "-i", "aevalsrc='%s':s=48000:d=%s:c=mono" % (expresion, dur), "-c:a", "pcm_s16le", ruta)
    return ruta


def ruido(nombre, nivel, dur):
    ruta = os.path.join(TMP, nombre)
    ex.ffmpeg("-f", "lavfi", "-i", "anoisesrc=a=%s:c=white:r=48000:d=%s" % (nivel, dur), "-ac", "1", "-c:a", "pcm_s16le", ruta)
    return ruta


def proyecto_de_audio(ruta):
    import av
    c = av.open(ruta)
    dur = float(c.duration) / av.time_base
    c.close()
    p = Proyecto()
    fid = p.agregar_fuente(ruta, "audio", dur, None, 1)
    p.nuevo_desde_fuente(fid)
    return p


def exportado(p, nombre, formato="wav"):
    r = ex.exportar_a(p, nombre, formato=formato)
    return ex.muestras(r["archivo"]), r


def pico(m, t0, t1, sr=48000):
    t = m[int(t0 * sr):int(t1 * sr)]
    return max((abs(x) for x in t), default=0) / 32768.0


def con_efecto(ruta, tipo, params=None):
    """Un proyecto de ese audio con un efecto en su clip de audio; devuelve (proyecto, id del clip)."""
    p = proyecto_de_audio(ruta)
    cid = p.pista("A1")["clips"][0]["id"]
    p.agregar_efecto(cid, tipo, params or {})
    return p, cid


def main():
    # ------------------------------------------------------------------ 1. el catalogo
    print("=== 1. el catalogo de efectos de audio ===")
    cat = efectos.catalogo()
    nuevos = ["pasa_bajos", "graves_agudos", "quitar_ruido", "quitar_clics", "nivelar_voz", "compresor", "puerta", "limitador", "eco", "tono", "invertir_audio"]
    ok(all(n in cat and cat[n]["categoria"] == "audio" for n in nuevos), "los 11 efectos nuevos estan y son de audio")
    ok(all(efectos.limpiar_params(t, {}) == efectos.defectos(t) for t in cat), "todos aceptan sus valores por defecto")
    ok(efectos.filtro_audio("pasa_altos", efectos.defectos("pasa_altos")) == "highpass=f=80",
       "un efecto con sus valores por defecto SI actua (Quitar graves en 80 Hz no es 'neutro')")
    ok(efectos.filtro_audio("graves_agudos", efectos.defectos("graves_agudos")) is None and efectos.filtro_audio("tono", efectos.defectos("tono")) is None,
       "los que en su valor inicial no hacen nada (graves y agudos en 0, tono en 0) no entran al grafo")
    ok(efectos.filtro_audio("graves_agudos", {"graves": 6.0, "agudos": 0.0}) == "bass=g=6.00", "graves y agudos arma solo lo que cambia")
    for t, malo in (("compresor", {"razon": 99}), ("tono", {"semitonos": 13}), ("quitar_ruido", {"reduccion": 0}), ("eco", {"nivel": 1.5})):
        try:
            efectos.limpiar_params(t, malo)
            ok(False, "fuera de rango en %s se rechaza" % t)
        except efectos.ErrorEfecto as e:
            ok("va de" in str(e), "fuera de rango en %s: mensaje con el rango" % t, str(e))

    # ------------------------------------------------------------------ 2. efectos medidos en el archivo exportado
    print("=== 2. cada efecto, medido en el audio que sale ===")
    tono3k = audio("t3k.wav", "0.5*sin(2*PI*3000*t)", 5)
    base = ex.rms(ex.muestras(ex.exportar_a(proyecto_de_audio(tono3k), "a_base3k", formato="wav")["archivo"]), 1, 4)
    p, _ = con_efecto(tono3k, "pasa_bajos", {"frecuencia": 1000})
    m, r = exportado(p, "a_pasa_bajos")
    ok(ex.rms(m, 1, 4) < 0.15 * base, "Quitar agudos (1000 Hz): un tono de 3000 Hz casi desaparece", f"{ex.rms(m, 1, 4):.4f} vs {base:.4f}")
    ok(abs(r["duracion"] - 5.0) < 0.03, "y la duracion es exacta", r["duracion"])

    tono100 = audio("t100.wav", "0.2*sin(2*PI*100*t)", 5)
    b100 = ex.rms(ex.muestras(ex.exportar_a(proyecto_de_audio(tono100), "a_base100", formato="wav")["archivo"]), 1, 4)
    p, _ = con_efecto(tono100, "graves_agudos", {"graves": 12.0})
    m, _ = exportado(p, "a_graves")
    ok(ex.rms(m, 1, 4) > 1.7 * b100, "Graves +12 dB: un tono de 100 Hz suena bastante mas fuerte", f"{ex.rms(m, 1, 4):.4f} vs {b100:.4f}")
    tono6k = audio("t6k.wav", "0.4*sin(2*PI*6000*t)", 5)
    b6k = ex.rms(ex.muestras(ex.exportar_a(proyecto_de_audio(tono6k), "a_base6k", formato="wav")["archivo"]), 1, 4)
    p, _ = con_efecto(tono6k, "graves_agudos", {"agudos": -12.0})
    m, _ = exportado(p, "a_agudos")
    ok(ex.rms(m, 1, 4) < 0.5 * b6k, "Agudos -12 dB: un tono de 6000 Hz suena bastante mas bajo", f"{ex.rms(m, 1, 4):.4f} vs {b6k:.4f}")

    rui = ruido("ruido.wav", 0.1, 6)
    b = ex.rms(ex.muestras(ex.exportar_a(proyecto_de_audio(rui), "a_base_ruido", formato="wav")["archivo"]), 2, 5)
    p, _ = con_efecto(rui, "quitar_ruido", {"reduccion": 30, "piso": -30})
    m, r = exportado(p, "a_quitar_ruido")
    ok(ex.rms(m, 2, 5) < 0.6 * b, "Quitar ruido: un ruido parejo baja de nivel", f"{ex.rms(m, 2, 5):.4f} vs {b:.4f}")
    ok(abs(r["duracion"] - 6.0) < 0.03, "y la duracion es exacta", r["duracion"])

    # fuerte y suave: 0,8 durante 3 s, 0,05 durante 3 s
    fs = audio("fuerte_suave.wav", "sin(2*PI*440*t)*if(lt(t,3),0.8,0.05)", 6)
    bm = ex.muestras(ex.exportar_a(proyecto_de_audio(fs), "a_base_fs", formato="wav")["archivo"])
    p, _ = con_efecto(fs, "compresor", {"umbral": -30, "razon": 10.0, "ganancia": 12})
    m, _ = exportado(p, "a_compresor")
    antes = ex.rms(bm, 0.5, 2.5) / ex.rms(bm, 3.5, 5.5)
    despues = ex.rms(m, 0.5, 2.5) / ex.rms(m, 3.5, 5.5)
    ok(despues < 0.6 * antes, "Compresor: la diferencia entre lo fuerte y lo suave se achica", f"de {antes:.1f}x a {despues:.1f}x")
    p, _ = con_efecto(fs, "nivelar_voz", {"fuerza": 20})
    m, _ = exportado(p, "a_nivelar")
    ok(ex.rms(m, 3.5, 5.5) > 2.0 * ex.rms(bm, 3.5, 5.5), "Nivelar la voz: lo suave sube", f"{ex.rms(m, 3.5, 5.5):.4f} vs {ex.rms(bm, 3.5, 5.5):.4f}")

    flojo = audio("flojo.wav", "0.01*sin(2*PI*440*t)", 5)
    fuerte = audio("fuerte.wav", "0.8*sin(2*PI*440*t)", 5)
    p, _ = con_efecto(flojo, "puerta", {"umbral": -30})
    m, _ = exportado(p, "a_puerta")
    ok(ex.rms(m, 1, 4) < 0.1 * ex.rms(ex.muestras(ex.exportar_a(proyecto_de_audio(flojo), "a_base_flojo", formato="wav")["archivo"]), 1, 4),
       "Puerta de ruido: lo que esta por debajo del umbral se silencia")
    p, _ = con_efecto(fuerte, "puerta", {"umbral": -30})
    m, _ = exportado(p, "a_puerta_fuerte")
    ok(ex.rms(m, 1, 4) > 0.85 * ex.rms(ex.muestras(ex.exportar_a(proyecto_de_audio(fuerte), "a_base_fuerte", formato="wav")["archivo"]), 1, 4), "y lo que esta por encima pasa", f"{ex.rms(m, 1, 4):.3f}")

    p, _ = con_efecto(fuerte, "limitador", {"tope": -12})
    m, _ = exportado(p, "a_limitador")
    ok(0.2 < pico(m, 1, 4) < 0.27, "Limitador (-12 dB = 0,25): el pico no pasa del tope ni se apaga", f"pico {pico(m, 1, 4):.3f}")

    # un pulso en el segundo 1: con eco de 300 ms aparece otro a los 1,3 s
    pulso = audio("pulso.wav", "0.8*sin(2*PI*600*t)*between(t,1,1.1)", 3)
    m0 = ex.muestras(ex.exportar_a(proyecto_de_audio(pulso), "a_base_pulso", formato="wav")["archivo"])
    p, _ = con_efecto(pulso, "eco", {"retardo": 300, "nivel": 0.6})
    m, r = exportado(p, "a_eco")
    ok(pico(m0, 1.32, 1.4) < 0.01 and pico(m, 1.32, 1.4) > 0.2, "Eco: aparece una repeticion 300 ms despues", f"sin {pico(m0, 1.32, 1.4):.3f}, con {pico(m, 1.32, 1.4):.3f}")
    ok(abs(r["duracion"] - 3.0) < 0.03, "y el eco no alarga el clip (termina con el)", r["duracion"])

    a440 = audio("a440.wav", "0.5*sin(2*PI*440*t)", 5)
    p, _ = con_efecto(a440, "tono", {"semitonos": 12.0})
    m, r = exportado(p, "a_tono")
    f = ex.frecuencia(m, 1.5, 3.5)
    ok(abs(f - 880) < 40, "Cambiar el tono +12 semitonos: 440 Hz pasa a ~880 Hz", f"{f:.0f} Hz")
    ok(abs(r["duracion"] - 5.0) < 0.03, "sin cambiar la duracion", r["duracion"])

    barrido = audio("barrido.wav", "0.5*sin(2*PI*(400*t+50*t*t))", 5)         # sube de 400 a 900 Hz
    mb = ex.muestras(ex.exportar_a(proyecto_de_audio(barrido), "a_base_barrido", formato="wav")["archivo"])
    p, _ = con_efecto(barrido, "invertir_audio")
    m, r = exportado(p, "a_reves")
    ok(ex.frecuencia(mb, 0.3, 1.0) < ex.frecuencia(mb, 4.0, 4.7) and ex.frecuencia(m, 0.3, 1.0) > ex.frecuencia(m, 4.0, 4.7) + 200,
       "Al reves: un barrido que subia ahora baja", f"antes {ex.frecuencia(mb, 0.3, 1.0):.0f}->{ex.frecuencia(mb, 4.0, 4.7):.0f}, ahora {ex.frecuencia(m, 0.3, 1.0):.0f}->{ex.frecuencia(m, 4.0, 4.7):.0f}")
    ok(abs(r["duracion"] - 5.0) < 0.03, "y dura lo mismo", r["duracion"])

    p, _ = con_efecto(a440, "quitar_clics")
    m, r = exportado(p, "a_clics")
    ok(abs(r["duracion"] - 5.0) < 0.03 and ex.rms(m, 1, 4) > 0.2, "Quitar clics: no daña un tono limpio y la duracion es exacta", f"{ex.rms(m, 1, 4):.3f}")

    # -------------------- varios efectos: en orden, y en un clip cortado (cada mitad con lo suyo)
    print("=== 3. efectos apilados, en orden, y en clips cortados ===")
    p = proyecto_de_audio(tono3k)
    cid = p.pista("A1")["clips"][0]["id"]
    p.agregar_efecto(cid, "pasa_bajos", {"frecuencia": 1000})
    p.agregar_efecto(cid, "graves_agudos", {"agudos": 6.0})
    m, _ = exportado(p, "a_apilados")
    ok(ex.rms(m, 1, 4) < 0.3 * base, "dos efectos a la vez: los dos actuan")
    p = proyecto_de_audio(tono3k)
    p.dividir(2.5)
    izq = p.pista("A1")["clips"][0]
    p.agregar_efecto(izq["id"], "pasa_bajos", {"frecuencia": 1000})
    m, r = exportado(p, "a_mitad")
    ok(ex.rms(m, 0.5, 2.0) < 0.15 * base and ex.rms(m, 3.0, 4.5) > 0.8 * base, "un efecto en la primera mitad no toca la segunda", f"{ex.rms(m, 0.5, 2.0):.3f} / {ex.rms(m, 3.0, 4.5):.3f}")
    ok(abs(r["duracion"] - 5.0) < 0.03, "y la duracion total es exacta (el corte no se desfasa)", r["duracion"])

    # --- con video: el audio con efecto sigue SINCRONIZADO con la imagen
    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"))
    pv, fid, tiempos = ex.armar(src)
    pv.agregar_efecto(pv.pista("A1")["clips"][0]["id"], "eco", {"retardo": 200, "nivel": 0.5})
    pv.agregar_efecto(pv.pista("A1")["clips"][0]["id"], "tono", {"semitonos": 3.0})
    pv.dividir(5.0)
    r = ex.exportar_a(pv, "a_con_video")
    v_, a_, dur = ex.sondear(r["archivo"])
    ok(abs(float(a_["duration"]) - float(v_["duration"])) < 0.05 and abs(dur - 12.0) < 0.1, "con video: el audio y la imagen duran lo mismo (nada se desfasa)",
       f"video {v_['duration']}, audio {a_['duration']}")
    ok(ex.leer_codigos(r["archivo"]) == ex.esperados(pv, tiempos), "y los cuadros siguen exactos")

    # ------------------------------------------------------------------ 4. silencios
    print("=== 4. detectar silencios ===")
    # 12 s: tono, silencio de 3 a 5, tono, silencio de 8 a 9,5, tono
    hablado = os.path.join(TMP, "hablado.mp4")
    mudo = ex.crear_fuente(os.path.join(TMP, "mudo12.mp4"), dur=12, tono=False)           # con el codigo de barras por cuadro
    ex.ffmpeg("-i", mudo, "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*440*t)*(1-between(t,3,5)-between(t,8,9.5))':s=48000:d=12:c=mono",
              "-c:v", "copy", "-c:a", "aac", "-shortest", hablado)
    p, fid, tiempos = ex.armar(hablado)
    r = silencios.analizar(p, -35.0, 0.5, 0.1)
    s = r["silencios"]
    ok(len(s) == 2 and abs(s[0]["inicio"] - 3.1) < 0.12 and abs(s[0]["fin"] - 4.9) < 0.12 and abs(s[1]["inicio"] - 8.1) < 0.12 and abs(s[1]["fin"] - 9.4) < 0.12,
       "encuentra los dos silencios (3-5 s y 8-9,5 s) y deja 0,1 s de margen", str(s))
    ok(abs(r["total"] - 3.0) < 0.2 and abs(r["duracion"] - 12.0) < 0.1, "suma lo que se sacaria", r["total"])
    r0 = silencios.analizar(p, -35.0, 0.5, 0.0)["silencios"]
    ok(abs(r0[0]["inicio"] - 3.0) < 0.12 and abs(r0[0]["fin"] - 5.0) < 0.12, "con margen 0 coincide con el silencio entero", str(r0[0]))
    ok(len(silencios.analizar(p, -35.0, 2.5, 0.0)["silencios"]) == 0, "un silencio mas corto que la duracion minima no cuenta (el de 1,5 s con minimo 2,5 s; el de 2 s tampoco)")
    ok(len(silencios.analizar(p, -35.0, 1.8, 0.0)["silencios"]) == 1, "y con minimo 1,8 s solo cuenta el de 2 s")
    for malo, kw in (("un nivel imposible", {"umbral_db": 5.0}), ("una duracion de 0", {"duracion_min": 0.0}), ("un margen negativo", {"margen": -1.0})):
        try:
            silencios.analizar(p, **{"umbral_db": -35.0, "duracion_min": 0.5, "margen": 0.1, **kw})
            ok(False, malo + " se rechaza")
        except silencios.ErrorSilencio as e:
            ok("va de" in str(e), malo + ": error claro", str(e))
    # despues de un corte, los silencios se mueven con el: se borra el primer segundo y todo se corre 1 s
    p2, _, _ = ex.armar(hablado)
    p2.borrar_rango(0.0, 1.0)
    s2 = silencios.analizar(p2, -35.0, 0.5, 0.1)["silencios"]
    ok(abs(s2[0]["inicio"] - 2.1) < 0.12 and abs(s2[1]["inicio"] - 7.1) < 0.12, "tras borrar el primer segundo, los silencios se corren 1 s", str(s2))
    # un silencio que cruza un corte es UNO solo
    p3, _, _ = ex.armar(hablado)
    p3.dividir(4.0)
    s3 = silencios.analizar(p3, -35.0, 0.5, 0.1)["silencios"]
    ok(len(s3) == 2 and abs(s3[0]["fin"] - 4.9) < 0.12, "un silencio que cruza un corte sigue siendo uno solo", str(s3))
    sin_audio = ex.crear_fuente(os.path.join(TMP, "mudo.mp4"), dur=3, tono=False)
    pm, _, _ = ex.armar(sin_audio)
    try:
        silencios.analizar(pm)
        ok(False, "un video sin audio da error")
    except silencios.ErrorSilencio as e:
        ok("audio" in str(e), "un video sin audio: error claro", str(e))

    print("=== 5. cortar los silencios (borrar varios tramos de una vez) ===")
    p, fid, tiempos = ex.armar(hablado)
    tramos = [(x["inicio"], x["fin"]) for x in silencios.analizar(p, -35.0, 0.5, 0.1)["silencios"]]
    res = p.borrar_rangos(tramos)
    ok(res["tramos"] == 2 and abs(res["duracion"] - 3.0) < 0.2, "borra los dos tramos de una vez", str(res))
    ok(abs(p.duracion() - (12.0 - res["duracion"])) < 0.02 and p.validar() == [], "la duracion es la esperada y el proyecto es valido", p.duracion())
    ok(len(p.pista("V1")["clips"]) == len(p.pista("A1")["clips"]) == 3, "queda en 3 clips de video y de audio, enlazados")
    p.deshacer()
    ok(abs(p.duracion() - 12.0) < 0.02 and len(p.pista("V1")["clips"]) == 1, "UN solo deshacer devuelve todo")
    p.rehacer()
    ok(abs(p.duracion() - (12.0 - res["duracion"])) < 0.02, "y rehacer lo vuelve")
    r = ex.exportar_a(p, "sin_silencios")
    ok(abs(r["duracion"] - p.duracion()) < 0.1 and ex.leer_codigos(r["archivo"]) == ex.esperados(p, tiempos), "exportado: los cuadros salen exactos y en orden", f"{r['duracion']:.2f} s")
    m = ex.muestras(r["archivo"])
    ok(ex.rms(m, 0.3, 2.5) > 0.2 and ex.rms(m, 3.5, p.duracion() - 0.5) > 0.2, "y el audio suena parejo, sin los huecos")
    despues = silencios.analizar(p, -35.0, 0.5, 0.0)["silencios"]
    ok(len(despues) == 0, "volver a buscar silencios en el resultado: no queda ninguno", str(despues))
    # casos raros
    p, _, _ = ex.armar(hablado)
    try:
        p.borrar_rangos([])
        ok(False, "una lista vacia se rechaza")
    except ErrorEdicion as e:
        ok("tramos" in str(e), "una lista vacia: error claro", str(e))
    antes = p.duracion()
    try:
        p.borrar_rangos([(1.0, 1.0001)])
        ok(False, "un tramo de menos de un cuadro se rechaza")
    except ErrorEdicion as e:
        ok(p.duracion() == antes, "un tramo mas corto que un cuadro: error claro y no cambia nada", str(e))
    res = p.borrar_rangos([(2.0, 3.0), (2.5, 4.0), (4.0, 4.5)])
    ok(res["tramos"] == 1 and abs(res["duracion"] - 2.5) < 0.05, "tramos que se tocan o se pisan se unen en uno", str(res))
    res = p.borrar_rangos([(0.0, 0.5), (p.duracion() - 0.5, p.duracion() + 50.0)])
    ok(res["tramos"] == 2 and p.validar() == [], "los extremos tambien (y un fin pasado de largo se acota)", str(res))

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
