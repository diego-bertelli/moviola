# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 5 (subtitulos): el modelo de frases, los archivos .srt/.vtt/.ass, quemarlos al exportar y transcribir con whisper.

Uso:  python -I pruebas/prueba_subtitulos.py

Quemar se comprueba MIDIENDO la imagen exportada (donde aparece el texto, en que momento, de que color). La transcripcion usa el
whisper y el modelo YA instalados en esta PC con una voz de Windows (SAPI) como audio de prueba: si falta algo de eso, esa parte se
saltea y lo dice (no falla: otra PC puede no tenerlos).
"""

import json
import os
import random
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

from PIL import ImageChops  # noqa: E402

import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402
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


def caja(a, b, umbral=60):
    return ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > umbral else 0).getbbox()


def pixeles(img, region, pred):
    return sum(1 for px in img.crop(region).getdata() if pred(px))


def main():
    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=6)

    # ------------------------------------------------------------------ 1. el modelo
    print("=== 1. frases y estilo en el proyecto ===")
    p, fid, _ = ex.armar(src)
    ok(p.subtitulos["frases"] == [] and p.a_dict()["subtitulos_desactualizados"] is False, "un proyecto nuevo no tiene frases")
    a = p.subtitulo_agregar(1.0, 2.0, "  Hola mundo  ")
    b = p.subtitulo_agregar(0.2, 0.9, "Primera")
    fr = p.subtitulos["frases"]
    ok([f["texto"] for f in fr] == ["Primera", "Hola mundo"] and fr[0]["id"] == b and fr[1]["id"] == a, "las frases se guardan ordenadas por tiempo y sin espacios de mas")
    p.subtitulo_cambiar(a, {"texto": "Hola de nuevo", "fin": 2.5})
    ok(p.subtitulos["frases"][1]["texto"] == "Hola de nuevo" and p.subtitulos["frases"][1]["fin"] == 2.5, "se puede cambiar el texto y el tiempo")
    p.subtitulo_cambiar(a, {"inicio": 0.0})
    ok([f["id"] for f in p.subtitulos["frases"]] == [a, b], "y si el cambio las desordena, se vuelven a ordenar")
    for malo, f, args in (("vacia", p.subtitulo_agregar, (1.0, 2.0, "   ")), ("de 5 letras por segundo cero", p.subtitulo_agregar, (1.0, 1.05, "x")),
                          ("con el final antes del inicio", p.subtitulo_agregar, (3.0, 2.0, "x")), ("despues del video", p.subtitulo_agregar, (99.0, 100.0, "x")),
                          ("con un texto que no es texto", p.subtitulo_agregar, (1.0, 2.0, 5)), ("de 401 letras", p.subtitulo_agregar, (1.0, 2.0, "x" * 401)),
                          ("de una frase que no existe", p.subtitulo_cambiar, ("s999", {"texto": "x"})), ("con un campo que no existe", p.subtitulo_cambiar, (a, {"color": "x"})),
                          ("quitar una frase que no existe", p.subtitulo_quitar, ("s999",))):
        antes = json.dumps(p.subtitulos, sort_keys=True)
        e = da_error(f, *args)
        ok(e is not None and json.dumps(p.subtitulos, sort_keys=True) == antes, "frase " + malo + ": error claro y no cambia nada", e)
    p.subtitulos_estilo({"color": "coral", "tamano": 9.5, "posicion": "arriba"})
    ok(p.subtitulos["estilo"]["color"] == "coral" and p.subtitulos["estilo"]["tamano"] == 9.5 and p.subtitulos["estilo"]["fuente"] == "segoeuib", "el estilo cambia solo lo que se pide")
    for malo, x in (("un color que no hay", {"color": "fucsia"}), ("un tamano de 40", {"tamano": 40}), ("un ajuste que no existe", {"brillo": 1}), ("un si/no que no es booleano", {"caja": 1})):
        e = da_error(p.subtitulos_estilo, x)
        ok(e is not None, "estilo con " + malo + ": error claro", e)
    ok(p.validar() == [], "el proyecto sigue valido")
    # historial
    n = len(p.subtitulos["frases"])
    p.subtitulo_quitar(b)
    ok(len(p.subtitulos["frases"]) == n - 1, "quitar una frase")
    p.deshacer()
    ok(len(p.subtitulos["frases"]) == n, "Deshacer la trae de vuelta")
    p.deshacer()
    ok(p.subtitulos["estilo"]["color"] == "blanco" and p.subtitulos["frases"][0]["texto"] == "Hola de nuevo", "y el estilo se deshace en su orden (vuelve al blanco de fabrica)")
    p.rehacer()
    p.rehacer()
    # guardar y abrir
    ruta = os.path.join(TMP, "con_subs.moviola")
    p.guardar(ruta)
    q = Proyecto.cargar(ruta, lambda f: ex.armar(src)[2])
    ok(q.subtitulos["frases"] == p.subtitulos["frases"] and q.subtitulos["estilo"] == p.subtitulos["estilo"], "guardar y abrir el proyecto conserva las frases y el estilo")
    ok("subtitulos_desactualizados" not in json.load(open(ruta, encoding="utf-8")), "(el archivo no guarda el aviso, que se calcula)")
    # desactualizados
    p2, _, _ = ex.armar(src)
    p2.subtitulos_poner([{"inicio": 1.0, "fin": 2.0, "texto": "uno"}, {"inicio": 4.0, "fin": 5.0, "texto": "dos"}])
    ok(p2.a_dict()["subtitulos_desactualizados"] is False and len(p2.subtitulos["frases"]) == 2, "poner las frases de una transcripcion las deja al dia con el montaje")
    p2.borrar_rango(2.0, 3.0)
    ok(p2.a_dict()["subtitulos_desactualizados"] is True, "si despues se corta el video, avisa que las frases pueden estar corridas")
    p2.subtitulos_al_dia()
    ok(p2.a_dict()["subtitulos_desactualizados"] is False, "y «están bien así» lo confirma")
    p2.deshacer()
    ok(p2.a_dict()["subtitulos_desactualizados"] is True, "(y deshacer el aviso vuelve a mostrarlo, porque el montaje es el de antes pero la huella no)")
    p2.deshacer()
    ok(p2.a_dict()["subtitulos_desactualizados"] is False, "deshacer hasta el estado original lo deja al dia")
    p2.subtitulos_borrar()
    ok(p2.subtitulos["frases"] == [] and p2.a_dict()["subtitulos_desactualizados"] is False, "borrar todas las frases")
    # dividir_varios
    p3, _, _ = ex.armar(src)
    n_hechos = p3.dividir_varios([1.0, 2.0, 2.0, 3.0, 99.0])
    ok(n_hechos == 3 and len(p3.pista("V1")["clips"]) == 4 and len(p3._deshacer) == 1 and p3.validar() == [], "dividir en varios lugares: 3 cortes en UN paso del historial (el repetido y el de afuera no cuentan)")
    p3.deshacer()
    ok(len(p3.pista("V1")["clips"]) == 1, "y un Deshacer los saca todos")
    ok(da_error(p3.dividir_varios, []) is not None and da_error(p3.dividir_varios, [99.0]) is not None, "sin lugares validos: error claro")

    # propiedades al azar
    malos = []
    for semilla in range(120):
        azar = random.Random(semilla)
        q, _, _ = ex.armar(src)
        q.recortar_a(0.0, 6.0)
        for paso in range(25):
            op = azar.choice(["agregar", "agregar", "cambiar", "quitar", "poner", "estilo", "dividir", "borrar", "deshacer", "rehacer", "al_dia"])
            antes = (json.dumps(q.subtitulos, sort_keys=True), q.huella_linea())
            try:
                if op == "agregar":
                    q.subtitulo_agregar(azar.uniform(-1, 7), azar.uniform(-1, 8), azar.choice(["a", "", "Hola ñandú", "x" * 500]))
                elif op == "cambiar" and q.subtitulos["frases"]:
                    f = azar.choice(q.subtitulos["frases"])
                    q.subtitulo_cambiar(f["id"], {azar.choice(["inicio", "fin", "texto"]): azar.choice([azar.uniform(0, 6), "nuevo", None])})
                elif op == "quitar" and q.subtitulos["frases"]:
                    q.subtitulo_quitar(azar.choice(q.subtitulos["frases"])["id"])
                elif op == "poner":
                    q.subtitulos_poner([{"inicio": azar.uniform(0, 5), "fin": azar.uniform(0, 7), "texto": "t"} for _ in range(azar.randint(0, 4))])
                elif op == "estilo":
                    q.subtitulos_estilo({azar.choice(["tamano", "margen"]): azar.uniform(-1, 40)})
                elif op == "dividir":
                    q.dividir(azar.uniform(0, q.duracion()))
                elif op == "borrar" and q.duracion() > 2:
                    t0 = azar.uniform(0, q.duracion() - 1)
                    q.borrar_rango(t0, t0 + azar.uniform(0.2, 1.0))
                elif op == "deshacer":
                    q.deshacer()
                elif op == "rehacer":
                    q.rehacer()
                elif op == "al_dia":
                    q.subtitulos_al_dia()
            except ErrorEdicion:
                if (json.dumps(q.subtitulos, sort_keys=True), q.huella_linea()) != antes:
                    malos.append((semilla, paso, op, "un error dejo el estado cambiado"))
                    break
                continue
            m = q.validar()
            if m:
                malos.append((semilla, paso, op, m[:2]))
                break
    ok(not malos, "120 secuencias al azar con frases, estilo, cortes y deshacer: siempre valido y un error nunca deja nada a medias", str(malos[:3]))

    # ------------------------------------------------------------------ 2. archivos de subtitulos
    print("=== 2. .srt, .vtt y .ass ===")
    frases = [{"inicio": 1.5, "fin": 3.25, "texto": "Hola\nmundo"}, {"inicio": 3661.007, "fin": 3662.0, "texto": "Una hora después"}, {"inicio": 9.0, "fin": 9.02, "texto": "muy corta"}]
    srt = sub.a_srt(frases)
    ok(srt.startswith("1\n00:00:01,500 --> 00:00:03,250\nHola\nmundo\n") and "2\n01:01:01,007 --> 01:01:02,000\nUna hora después" in srt and "muy corta" not in srt,
       "SRT: numeracion, coma en los milisegundos, horas, saltos de linea y sin frases de menos de 40 ms", srt[:90].replace("\n", "|"))
    vtt = sub.a_vtt(frases, 10.0)
    ok(vtt.startswith("WEBVTT") and "00:00:01.500 --> 00:00:03.250" in vtt and "Una hora" not in vtt, "VTT: cabecera, punto en los milisegundos, y lo que queda fuera del video no se escribe")
    ass = sub.a_ass(frases[:1], {"mayusculas": True, "posicion": "arriba", "color": "coral"}, 1080, 1920)
    ok("PlayResX: 1080" in ass and "PlayResY: 1920" in ass and ",&H005A6DFF," in ass and "Dialogue: 0,0:00:01.50,0:00:03.25,Default,,0,0,0,,HOLA\\NMUNDO" in ass and ",8," in ass.split("Style: Default,")[1].split("\n")[0],
       "ASS: en la resolucion de salida, color coral (en BGR), mayusculas, renglones con \\N y alineacion arriba")
    raro = sub.a_ass([{"inicio": 0, "fin": 1, "texto": "{\\an9}uno\\ndos"}], {}, 640, 360)
    ok("{" not in raro.split("Dialogue:")[1] and "\\an9" not in raro.split("Dialogue:")[1], "ASS: las llaves y barras que escriba la persona no se interpretan como codigos")

    # ------------------------------------------------------------------ 3. quemar al exportar
    print("=== 3. quemar al exportar (medido en la imagen) ===")
    base, _ = im.exportar(ex.armar(src)[0], "s_base")
    base = im.todos_los_cuadros(base)

    def con_frases(estilo=None, formato="original"):
        q, _, _ = ex.armar(src)
        q.subtitulo_agregar(1.0, 2.0, "HOLA MUNDO")
        if estilo:
            q.subtitulos_estilo(estilo)
        return q

    q = con_frases()
    arch, r = im.exportar(q, "s_quemado", subtitulos={"quemar": True})
    cu = im.todos_los_cuadros(arch)
    bb = caja(cu[45], base[45], 50)
    ok(len(cu) == 180 and bb is not None and bb[1] > 230 and abs((bb[0] + bb[2]) / 2 - 320) < 30,
       "el texto aparece abajo y centrado en el momento de la frase, y el video sigue durando 180 cuadros", f"caja {bb}")
    d_antes, d_durante, d_despues = (im.dif_media(cu[i], base[i]) for i in (15, 45, 75))
    ok(d_antes < 1.5 and d_durante > 3 * max(d_antes, 0.3) and d_despues < 1.5, "y solo entre 1 s y 2 s: no esta a los 0,5 s ni a los 2,5 s", f"{d_antes:.2f} / {d_durante:.2f} / {d_despues:.2f}")
    ok(r["subtitulos"] == [] and not [f for f in os.listdir(os.path.dirname(arch)) if f.endswith((".srt", ".vtt"))], "quemar solo no deja archivos de subtitulos al lado")
    for estilo, nombre in (({"posicion": "arriba"}, "arriba"), ({"posicion": "centro"}, "centro")):
        a_, _ = im.exportar(con_frases(estilo), "s_" + nombre, subtitulos={"quemar": True})
        c_ = im.todos_los_cuadros(a_)
        b_ = caja(c_[45], base[45], 50)
        esperado = (b_ is not None and b_[3] < 120) if nombre == "arriba" else (b_ is not None and 120 < (b_[1] + b_[3]) / 2 < 240)
        ok(esperado, "posicion " + nombre, f"caja {b_}")
    a_, _ = im.exportar(con_frases({"color": "coral", "contorno": False}), "s_coral", subtitulos={"quemar": True})
    c_ = im.todos_los_cuadros(a_)
    n_coral = pixeles(c_[45], (100, 250, 540, 360), lambda px: abs(px[0] - 255) < 30 and abs(px[1] - 109) < 30 and abs(px[2] - 90) < 30)
    n_coral_base = pixeles(base[45], (100, 250, 540, 360), lambda px: abs(px[0] - 255) < 30 and abs(px[1] - 109) < 30 and abs(px[2] - 90) < 30)
    ok(n_coral > n_coral_base + 150, "el color coral se ve en el texto", f"{n_coral} contra {n_coral_base} sin subtitulos")
    q_min = con_frases({"mayusculas": False})
    q_min.subtitulo_cambiar(q_min.subtitulos["frases"][0]["id"], {"texto": "hola mundo"})
    q_may = con_frases({"mayusculas": True})
    q_may.subtitulo_cambiar(q_may.subtitulos["frases"][0]["id"], {"texto": "hola mundo"})
    c_min = im.todos_los_cuadros(im.exportar(q_min, "s_min", subtitulos={"quemar": True})[0])
    c_may = im.todos_los_cuadros(im.exportar(q_may, "s_may", subtitulos={"quemar": True})[0])
    b_min, b_may = caja(c_min[45], base[45], 50), caja(c_may[45], base[45], 50)
    ok(b_min and b_may and (b_may[2] - b_may[0]) > (b_min[2] - b_min[0]) + 15, "«TODO EN MAYUSCULAS» ensancha el texto", f"{b_min} contra {b_may}")
    q_grande = con_frases({"tamano": 12})
    c_g = im.todos_los_cuadros(im.exportar(q_grande, "s_grande", subtitulos={"quemar": True})[0])
    b_g = caja(c_g[45], base[45], 50)
    ok(b_g and (b_g[3] - b_g[1]) > 1.5 * (bb[3] - bb[1]), "un tamano mayor da letras mas altas", f"{b_g[3] - b_g[1]} contra {bb[3] - bb[1]}")
    # una letra distinta (todas las del catalogo se pueden quemar: la letra viaja a la carpeta de trabajo)
    faltan = []
    for clave in sub.FAMILIAS:
        a_, _ = im.exportar(con_frases({"fuente": clave}), "s_f_" + clave, subtitulos={"quemar": True})
        c_ = im.todos_los_cuadros(a_)
        if caja(c_[45], base[45], 50) is None:
            faltan.append(clave)
    ok(not faltan, "las %d letras se pueden quemar" % len(sub.FAMILIAS), str(faltan))
    # vertical: el tamano se mide sobre el alto de la salida (1080x1920)
    a_, _ = im.exportar(con_frases(), "s_vertical", formato="vertical", subtitulos={"quemar": True})
    cv = im.todos_los_cuadros(a_)
    q_v, _, _ = ex.armar(src)
    bv = im.todos_los_cuadros(im.exportar(q_v, "s_vertical_base", formato="vertical")[0])
    b_v = caja(cv[45], bv[45], 50)
    ok(cv[0].size == (1080, 1920) and b_v is not None and b_v[1] > 1500 and (b_v[3] - b_v[1]) > 60, "en vertical (1080x1920) queda abajo y con el tamano proporcional", f"caja {b_v}")
    # sin frases no se puede pedir; .srt y .vtt aparte
    try:
        im.exportar(ex.armar(src)[0], "s_sin", subtitulos={"quemar": True})
        ok(False, "pedir subtitulos sin frases da un error")
    except ex.exportar.ExportError as e:
        ok("ninguna frase" in str(e), "pedir subtitulos sin ninguna frase: error claro", str(e))
    q = con_frases()
    q.subtitulo_agregar(5.5, 9.0, "Esta se corta en el final")
    arch, r = im.exportar(q, "s_archivos", subtitulos={"srt": True, "vtt": True})
    srt_path, vtt_path = os.path.splitext(arch)[0] + ".srt", os.path.splitext(arch)[0] + ".vtt"
    ok(sorted(r["subtitulos"]) == sorted([srt_path, vtt_path]) and os.path.isfile(srt_path) and os.path.isfile(vtt_path), "con .srt y .vtt: se escriben al lado, con el mismo nombre del video")
    txt = open(srt_path, encoding="utf-8").read()
    ok("HOLA MUNDO" in txt and "00:00:05,500 --> 00:00:06,000" in txt and txt.count("-->") == 2, "el .srt tiene las dos frases y la ultima recortada al final del video (6 s)", txt.replace("\n", "|")[:120])
    cu_sin = im.todos_los_cuadros(arch)
    ok(im.dif_media(cu_sin[45], base[45]) < 1.5, "y sin «quemar» la imagen no cambia")
    # con otro audio: formato de audio ignora quemar y escribe los archivos
    ra = ex.exportar_a(q, "s_audio", formato="wav", subtitulos={"quemar": True, "srt": True})
    ok(os.path.isfile(ra["archivo"]) and len(ra["subtitulos"]) == 1, "exportar solo audio con subtitulos: no intenta quemar y deja el .srt")

    # ------------------------------------------------------------------ 4. transcribir
    print("=== 4. transcribir con whisper ===")
    est = sub.estado_transcripcion()
    print("      estado:", est)
    ok(isinstance(est["disponible"], bool) and (est["disponible"] or est["motivo"]), "el estado dice si se puede transcribir y, si no, que falta")
    voz1, voz2 = os.path.join(TMP, "voz1.wav"), os.path.join(TMP, "voz2.wav")
    sapi_ok = True
    for ruta_v, texto in ((voz1, "Hola, esto es una prueba de subtítulos."), (voz2, "Ahora hablamos de otra cosa muy distinta.")):
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "try { $s.SelectVoice('Microsoft Pablo') } catch { }; $s.SetOutputToWaveFile('%s'); $s.Speak('%s'); $s.Dispose()" % (ruta_v, texto))
        r_ = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, encoding="utf-8", errors="replace")
        sapi_ok = sapi_ok and r_.returncode == 0 and os.path.isfile(ruta_v)
    if not (est["disponible"] and sapi_ok):
        print("  SALTEADA  la transcripcion real (falta %s)" % ("whisper o su modelo" if not est["disponible"] else "una voz de Windows para el audio de prueba"))
    else:
        d1 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", voz1], capture_output=True, text=True).stdout)
        hablado = os.path.join(TMP, "hablado.mp4")
        total = d1 + 3.0 + float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", voz2], capture_output=True, text=True).stdout) + 0.5
        ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=%.2f,format=yuv420p" % total, "-i", voz1, "-f", "lavfi", "-t", "3", "-i", "anullsrc=r=22050:cl=mono", "-i", voz2,
                  "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=mono[a];[2:a]aresample=48000,aformat=channel_layouts=mono[b];[3:a]aresample=48000,aformat=channel_layouts=mono[c];[a][b][c]concat=n=3:v=0:a=1[o]",
                  "-map", "0:v", "-map", "[o]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", hablado)
        ph, _, _ = ex.armar(hablado)
        estados = []
        frases = sub.transcribir(ph, "es", 32, avisar=lambda f: estados.append(f))
        textos = " ".join(f["texto"].lower() for f in frases)
        print("      frases:", [(f["inicio"], f["fin"], f["texto"]) for f in frases])
        ok(len(frases) >= 2 and "hola" in textos and "prueba" in textos and "distinta" in textos, "reconoce lo que se dijo (hola, prueba, distinta)", textos)
        primera = next((f for f in frases if "hola" in f["texto"].lower()), None)
        segunda = next((f for f in frases if "ahora" in f["texto"].lower() or "hablamos" in f["texto"].lower()), None)
        ok(primera is not None and primera["inicio"] < 1.0 and segunda is not None and abs(segunda["inicio"] - (d1 + 3.0)) < 0.9,
           "y cada frase cae en su momento de la linea de tiempo (la primera al comienzo, la segunda despues de los 3 s de silencio)",
           f"{primera and primera['inicio']} / {segunda and segunda['inicio']} (esperado ~{d1 + 3.0:.2f})")
        ok(all(0 <= f["inicio"] < f["fin"] <= ph.duracion() + 0.01 for f in frases) and all(len(f["texto"]) <= 40 for f in frases), "todas dentro del video y de 32 letras mas o menos")
        ok(estados and estados == sorted(estados) and estados[-1] > 0.9 and max(estados) < 1.0, "el avance sube de a poco y no llega a 1 antes de terminar", f"{len(estados)} avisos, ultimo {estados[-1] if estados else None}")
        ph.subtitulos_poner(frases)
        ok(ph.validar() == [] and len(ph.subtitulos["frases"]) == len(frases), "las frases entran al proyecto")
        # montaje EDITADO: se saca un tramo del silencio y las frases salen corridas, porque se transcribe el audio tal como queda
        ph2, _, _ = ex.armar(hablado)
        ph2.borrar_rango(d1 + 0.3, d1 + 2.8)
        fr2 = sub.transcribir(ph2, "es", 32)
        seg2 = next((f for f in fr2 if "ahora" in f["texto"].lower() or "hablamos" in f["texto"].lower()), None)
        ok(seg2 is not None and abs(seg2["inicio"] - (d1 + 0.5)) < 0.9, "con un tramo cortado, las frases salen en tiempos del montaje editado (2,5 s antes)", f"{seg2 and seg2['inicio']} (esperado ~{d1 + 0.5:.2f})")
        # sin audio de voz
        ph3, _, _ = ex.armar(hablado)
        ph3.silenciar("A1", True)
        try:
            sub.transcribir(ph3, "es", 32)
            ok(False, "con A1 silenciada se rechaza")
        except sub.ErrorSubtitulo as e:
            ok("silenciada" in str(e), "con la pista de voz silenciada: error claro", str(e))
        import threading
        ev = threading.Event()
        ev.set()
        try:
            sub.transcribir(ph, "es", 32, cancelar=ev)
            ok(False, "cancelar corta la transcripcion")
        except Exception as e:
            ok(type(e).__name__ == "Cancelado", "cancelar corta la transcripcion", type(e).__name__)
        for malo, kw in (("un idioma que no hay", {"idioma": "klingon"}), ("0 letras por frase", {"max_letras": 0})):
            try:
                sub.transcribir(ph, **{"idioma": "es", "max_letras": 32, **kw})
                ok(False, "transcribir con " + malo + " se rechaza")
            except sub.ErrorSubtitulo as e:
                ok(True, "transcribir con " + malo + ": error claro", str(e))

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
