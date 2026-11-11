# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 7 (panel de medios): VARIOS videos en un mismo proyecto, sin ventana.

Uso:  python -I pruebas/prueba_medios.py

Se juntan tres videos que no se parecen (640x360 a 30 cuadros/s con sonido, 320x180 a 25 con sonido, 480x270 a 24 SIN sonido) y se
comprueba, midiendo el archivo exportado, que cada uno sale en su lugar y en su orden; los cuadros que el visor le pide al motor
(cada uno de su archivo); reordenar; quitar; guardar y abrir; y la copia de reproduccion de un formato que el navegador no abre.
"""

import io
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
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-medios-"), "ajustes.json")

from PIL import Image  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402

ok = ex.ok


def nueva_api():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-medios-cache-"), "cache")
    app.crear_servidor(api)
    return api


def codigos_de(arch, ancho, alto, escala):
    """Los numeros de cuadro del archivo, leyendo el codigo de barras de una fuente de ancho x alto escalada `escala` veces."""
    return ex.leer_codigos(arch, mapa=lambda x, y: (x * escala, y * escala), ancho_fuente=ancho, alto_fuente=alto)


def main():
    a = ex.crear_fuente(os.path.join(ex.TMP, "A.mp4"), dur=6, w=640, h=360, fps=30)
    b = ex.crear_fuente(os.path.join(ex.TMP, "B.mp4"), dur=4, w=320, h=180, fps=25)
    c = ex.crear_fuente(os.path.join(ex.TMP, "C.mp4"), dur=3, w=480, h=270, fps=24, tono=False)
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 3, 800)
    api = nueva_api()

    print("=== 1. sumar videos al panel ===")
    r = api.abrir(a)
    ok(not r.get("error") and r["fid"] == "s1", "el video abierto es el principal (s1)", str(r.get("error")))
    rb = api.agregar_medio(b)
    rc = api.agregar_medio(c)
    ok(rb.get("fuente") == "s2" and rc.get("fuente") == "s3" and not rb["repetido"], "sumar B y C: reciben s2 y s3", str(rb.get("error") or rc.get("error")))
    fu = rc["proyecto"]["fuentes"]
    ok(sorted(fu) == ["s1", "s2", "s3"] and fu["s2"]["ancho"] == 320 and fu["s2"]["fps"] == 25 and fu["s3"]["pistas_audio"] == 0 and fu["s3"]["nombre"] == "C.mp4",
       "el proyecto trae los tres con su tamano, sus cuadros por segundo y si tienen audio", str({k: (v["ancho"], v["fps"], v["pistas_audio"]) for k, v in fu.items()}))
    ok(api.agregar_medio(b)["repetido"] is True and len(api.proyecto.fuentes) == 3, "sumar dos veces el mismo archivo no lo duplica")
    ok("imagen" in api.agregar_medio(musica).get("error", ""), "un audio no entra como video: error claro (se usa «Agregar audio»)", api.agregar_medio(musica).get("error"))
    ok("No encontré" in api.agregar_medio(os.path.join(ex.TMP, "no_hay.mp4")).get("error", ""), "un archivo que no existe: error claro")
    ok(nueva_api().agregar_medio(b).get("error", "").startswith("Primero"), "sin nada abierto: error claro")
    ok(api._proyecto_dict()["sin_guardar"] is True, "agregar archivos cuenta como cambio del proyecto")
    ok(len(api.proyecto.pista("V1")["clips"]) == 1, "todavia no estan en la linea de tiempo: solo estan en el panel")

    print("=== 2. lo que el visor le pide al motor ===")
    ib = api.medio_info("s2")
    ok(not ib.get("error") and ib["fps"] == 25 and ib["ancho"] == 320 and ib["fid"] == "s2" and ib["reproducible"] and ib["url"].startswith("http://127.0.0.1:") and ib["tira"].startswith("data:image/jpeg")
       and ib["tira_cantidad"] > 0 and ib["picos"], "medio_info(B): cuadros por segundo, tira de miniaturas, espectro y una direccion para reproducirlo", str(ib.get("error")))
    ic = api.medio_info("s3")
    ok(ic["sin_audio"] is True or not ic["picos"], "C no tiene audio: sin espectro")
    ok(api.medio_info("s9").get("error") and api.medio_info("s1").get("error") is None, "un video que no esta: error claro (y el principal tambien se puede consultar)")
    j1 = api.cuadro_jpeg(10, 160)
    j2 = api.cuadro_jpeg(10, 160, "s2")
    j3 = api.cuadro_jpeg(10, 160, "s3")
    im1, im2, im3 = (Image.open(io.BytesIO(x)) for x in (j1, j2, j3))
    ok(j1 and j2 and j3 and im1.size[0] == im2.size[0] == im3.size[0] == 160, "el visor pide cuadros de cada archivo (el principal sin decir cual, los otros por su id)", str((im1.size, im2.size, im3.size)))
    ok(im.dif_media(im1.convert("RGB"), im2.convert("RGB")) > 3 and im.dif_media(im2.convert("RGB"), im3.convert("RGB")) > 3, "y son cuadros distintos (cada uno de su video)")
    ok(api.cuadro_jpeg(10, 160, "s9") is None and api.cuadro_jpeg(10**6, 160, "s2") is not None, "un archivo que no existe: sin cuadro; un cuadro de mas: el ultimo")
    ok(len(api.videos) <= 3, "los videos abiertos de los otros archivos son pocos (se abren de a uno)", str(list(api.videos)))
    import urllib.request
    base = api.servidor.url_inicio().rsplit("/", 1)[0]
    cod = urllib.request.urlopen(base + "/frame?n=3&w=120&f=s2").getcode()
    ok(cod == 200, "por HTTP: /frame?n=3&w=120&f=s2")
    try:
        urllib.request.urlopen(base + "/frame?n=3&w=120&f=../s2")
        ok(False, "un id raro se rechaza")
    except Exception as e:
        ok("400" in str(e), "un id de archivo raro se rechaza (400)", str(e))

    print("=== 3. juntarlos en la linea de tiempo y exportar ===")
    r = api._editar("insertar_fuente", "s2")
    ok(not r.get("error") and r["resultado"]["inicio"] == 6.0 and abs(r["resultado"]["fin"] - 10.0) < 1e-6, "B va despues de A (de 6 s a 10 s)", str(r.get("error") or r["resultado"]))
    r = api._editar("insertar_fuente", "s3")
    ok(abs(api.proyecto.duracion() - 13.0) < 1e-6 and len(api.proyecto.pista("V1")["clips"]) == 3 and len(api.proyecto.pista("A1")["clips"]) == 2, "C (sin audio) va al final: 13 s, 3 clips de video y solo 2 de audio")
    ok(api.proyecto.validar() == [], "el proyecto es valido")
    arch, res = im.exportar(api.proyecto, "m_todo")
    cu = im.todos_los_cuadros(arch)
    ok(len(cu) == 390 and abs(res["duracion"] - 13.0) < 0.1 and cu[0].size == (640, 360), "se exporta de un tirón: 13 s, 390 cuadros, a 640x360 (el tamano del primero)", f"{len(cu)} cuadros {cu[0].size}")
    ca = codigos_de(arch, 640, 360, 1)[:180]
    ok(ca == list(range(180)), "los primeros 180 cuadros son los de A, en orden (codigo de barras)", str(ca[:3]) + "..." + str(ca[-3:]))
    cb = codigos_de(arch, 320, 180, 2)[180:300]
    ok(cb == sorted(cb) and cb[0] == 0 and cb[-1] >= 98 and len(set(cb)) >= 98, "los 120 siguientes son los de B (25 cuadros/s pasados a 30, escalados al doble), en orden", str(cb[:6]) + "..." + str(cb[-3:]))
    cc = codigos_de(arch, 480, 270, 640 / 480)[300:]
    ok(len(cc) == 90 and cc == sorted(cc) and cc[0] == 0 and cc[-1] >= 70, "y los 90 ultimos, los de C (24 cuadros/s a 30, escalados), en orden", str(cc[:4]) + "..." + str(cc[-3:]))
    m = ex.muestras(arch)
    ok(ex.rms(m, 0.5, 5.5) > 0.05 and ex.rms(m, 6.5, 9.5) > 0.05 and ex.rms(m, 10.5, 12.5) < 0.005, "el sonido: suena A, suena B y C es silencio", f"{ex.rms(m, 0.5, 5.5):.3f} / {ex.rms(m, 6.5, 9.5):.3f} / {ex.rms(m, 10.5, 12.5):.4f}")
    ok(abs(float(ex.sondear(arch)[1]["duration"]) - 13.0) < 0.1, "y dura lo mismo que el video")

    ok(len(api.picos_fuente("s2")["picos"]) > 100, "el espectro de un video sumado al panel se calcula cuando se pide (picos_fuente)")
    ok(api.picos_fuente("s9")["picos"] == [], "y de un archivo que no existe, vacio")

    print("=== 3b. silencios y escenas con varios videos ===")
    from motor import escenas, silencios
    negro = os.path.join(ex.TMP, "con_negro.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=1.5", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2,hue=h=120,negate",
              "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", negro)
    api.agregar_medio(negro)
    fid_n = [k for k, f in api.proyecto.fuentes.items() if f["ruta"] == negro][0]
    api._editar("insertar_fuente", fid_n, 6.0)                 # en el borde de 6 s: antes de B
    esc = escenas.analizar(api.proyecto, ["negros"])
    ok(any(abs(x["inicio"] - 8.0) < 0.2 and abs(x["fin"] - 9.5) < 0.2 for x in esc["negros"]), "el negro de un video que esta en el medio de la linea de tiempo cae en su lugar (6 + 2 = 8 s a 9,5 s)", str(esc["negros"]))
    api._editar("deshacer")
    api.quitar_medio(fid_n)
    sil = silencios.analizar(api.proyecto, -35.0, 0.5, 0.0)
    ok(len(sil["silencios"]) == 0 or all(0 <= x["inicio"] < x["fin"] <= api.proyecto.duracion() + 0.01 for x in sil["silencios"]), "los silencios se buscan en el audio de cada archivo y caen dentro de la linea de tiempo", str(sil["silencios"][:2]))

    print("=== 4. insertar en el medio y reordenar ===")
    q = nueva_api()
    q.abrir(a)
    q.agregar_medio(b)
    q.agregar_medio(c)
    q._editar("dividir", 3.0)
    r = q._editar("insertar_fuente", "s2", 2.8)
    ok(r["resultado"]["inicio"] == 3.0 and abs(q.proyecto.duracion() - 10.0) < 1e-6 and [x["fuente"] for x in q.proyecto.pista("V1")["clips"]] == ["s1", "s2", "s1"],
       "insertar en 2,8 s cae en el borde de clip mas cercano (3 s): A | B | A", str(r.get("error") or r["resultado"]))
    ok([round(x["inicio"], 2) for x in q.proyecto.pista("V1")["clips"]] == [0.0, 3.0, 7.0] and q.proyecto.validar() == [], "lo que sigue se corrio 4 s")
    g_b = q.proyecto.pista("V1")["clips"][1]["grupo"]
    r = q._editar("mover_grupo", g_b, 99.0)
    ok([x["fuente"] for x in q.proyecto.pista("V1")["clips"]] == ["s1", "s1", "s2"] and abs(q.proyecto.duracion() - 10.0) < 1e-6 and q.proyecto.validar() == [], "mover_grupo lleva B al final: A | A | B", str(r.get("error")))
    ok(all(abs(x["inicio"] - y) < 1e-6 for x, y in zip(q.proyecto.pista("V1")["clips"], [0.0, 3.0, 6.0])), "con los tiempos cerrados y abiertos: 0, 3 y 6 s")
    r = q._editar("mover_grupo", g_b, 99.0)
    ok("Ya está" in r.get("error", "") and [x["fuente"] for x in q.proyecto.pista("V1")["clips"]] == ["s1", "s1", "s2"], "moverlo a donde ya esta: error claro y no cambia nada", r.get("error"))
    r = q._editar("mover_grupo", g_b, 0.0)
    ok([x["fuente"] for x in q.proyecto.pista("V1")["clips"]] == ["s2", "s1", "s1"], "y moverlo al principio: B | A | A")
    arch2, _ = im.exportar(q.proyecto, "m_reorden")
    cu2 = im.todos_los_cuadros(arch2)
    # el primer clip manda: ahora es B (320x180, 25 cuadros/s), asi que TODO sale a ese tamano y a 25 cuadros por segundo (250 cuadros en 10 s)
    cb2 = codigos_de(arch2, 320, 180, 1)[:100]
    ca2 = codigos_de(arch2, 640, 360, 0.5)[100:]
    pasos = [y - x for x, y in zip(ca2, ca2[1:])]
    ok(len(cu2) == 250 and cb2 == list(range(100)) and len(ca2) == 150 and ca2[0] == 0 and ca2[-1] >= 172 and set(pasos) <= {1, 2},
       "exportado: primero B (100 cuadros a 25/s) y despues los dos tramos de A seguidos, sin saltos en el corte (30 a 25 cuadros/s: pasos de 1 o 2)", f"{len(cu2)} cuadros; {ca2[:4]}...{ca2[-3:]}")
    q._editar("deshacer")
    ok([x["fuente"] for x in q.proyecto.pista("V1")["clips"]] == ["s1", "s1", "s2"], "Deshacer devuelve el orden")
    ok(q._editar("mover_grupo", "g999", 1.0).get("error") and q._editar("insertar_fuente", "s99").get("error") and q._editar("insertar_fuente", "s1", -5.0).get("error"), "pedidos imposibles: errores claros")

    print("=== 5. quitar del panel ===")
    ok("se usa" in q.quitar_medio("s2").get("error", "") and "principal" in q.quitar_medio("s1").get("error", ""), "un archivo que se usa, o el principal, no se puede sacar", q.quitar_medio("s2").get("error"))
    r = q.quitar_medio("s3")
    ok(not r.get("error") and "s3" not in r["proyecto"]["fuentes"] and q.proyecto.validar() == [], "uno que no se usa, si")

    print("=== 6. guardar y abrir con varios videos ===")
    carpeta = tempfile.mkdtemp(prefix="prueba-medios-carpeta-")
    ruta_p = os.path.join(carpeta, "varios.moviola")
    api._guardar_en(ruta_p)
    api2 = nueva_api()
    r = api2.abrir(ruta_p)
    ok(not r.get("error") and sorted(r["proyecto"]["fuentes"]) == ["s1", "s2", "s3"] and r["fid"] == "s1", "se abre con los tres videos", str(r.get("error")))
    ok(api2.proyecto.fuentes["s2"]["tiempos"] and len(api2.proyecto.fuentes["s2"]["tiempos"]) == 100, "y con la tabla de cuadros de cada uno (para cortar justo en un cuadro)")
    ib2 = api2.medio_info("s2")
    ok(not ib2.get("error") and ib2["fps"] == 25 and api2.cuadro_jpeg(5, 120, "s2"), "los otros videos se consultan igual despues de abrir")
    arch3, _ = im.exportar(api2.proyecto, "m_abierto")
    cu3 = im.todos_los_cuadros(arch3)
    ok(len(cu3) == 390 and max(im.dif_media(x, y) for x, y in zip(cu[::13], cu3[::13])) < 0.01, "y el proyecto abierto se exporta igual que el original, cuadro por cuadro")

    print("=== 7. un formato que el navegador no abre (copia de reproduccion por archivo) ===")
    mpg = os.path.join(ex.TMP, "viejo.mpg")
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi", "-i", "sine=f=500:d=2", "-c:v", "mpeg2video", "-c:a", "mp2", "-shortest", mpg)
    q.agregar_medio(mpg)
    fid_mpg = [k for k, f in q.proyecto.fuentes.items() if f["ruta"].endswith("viejo.mpg")][0]
    im_ = q.medio_info(fid_mpg)
    ok(not im_.get("error") and im_["reproducible"] is False and im_["proxy"] == "generando", "MPEG-2: no se reproduce directo, y se empieza a preparar su copia", str(im_.get("error") or im_["proxy"]))
    t0 = time.time()
    while time.time() - t0 < 90 and q.medio_estado(fid_mpg)["estado"] == "generando":
        time.sleep(0.5)
    est = q.medio_estado(fid_mpg)
    ok(est["estado"] == "listo" and est["url"].startswith("http://127.0.0.1:"), "la copia de reproduccion queda lista, con su direccion", str(est))
    im2 = q.medio_info(fid_mpg)
    ok(im2["reproducible"] is True and im2["proxy"] == "listo" and im2["url"] == est["url"], "y medio_info la ofrece como reproducible", str(im2["proxy"]))
    r = q.quitar_medio(fid_mpg)
    ok(not r.get("error") and q.medio_estado(fid_mpg)["estado"] == "nada", "sacarlo del panel olvida su copia")

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
