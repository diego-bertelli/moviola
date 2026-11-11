# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 3 (video - imagen): color, limpieza, estabilizar, geometria y transiciones.

Uso:  python -I pruebas/prueba_imagen.py

Todo se comprueba MIDIENDO la imagen del archivo que sale (colores, bordes, posicion de un marcador, tamano),
comparando siempre contra la misma fuente exportada sin el efecto.
"""

import glob
import math
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

import av  # noqa: E402
from PIL import Image, ImageChops, ImageFilter, ImageStat  # noqa: E402

import prueba_exportar as ex  # noqa: E402
from motor import efectos  # noqa: E402
from motor.proyecto import ErrorEdicion  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def cuadro_n(ruta, n):
    cont = av.open(ruta)
    for i, f in enumerate(cont.decode(cont.streams.video[0])):
        if i == n:
            img = f.to_image().convert("RGB")
            cont.close()
            return img
    cont.close()
    return None


def todos_los_cuadros(ruta):
    cont = av.open(ruta)
    out = [f.to_image().convert("RGB") for f in cont.decode(cont.streams.video[0])]
    cont.close()
    return out


def dif_media(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3.0


def bordes(img):
    """Cuanto detalle fino hay: el promedio del filtro de bordes (sube con el grano y con el enfoque)."""
    return ImageStat.Stat(img.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]


def medias(img):
    return [ImageStat.Stat(x).mean[0] for x in img.split()]


def exportar(p, nombre, **kw):
    r = ex.exportar_a(p, nombre, **kw)
    return r["archivo"], r


def con_efecto(src, tipo, params=None, nombre="x"):
    p, fid, tiempos = ex.armar(src)
    cid = p.pista("V1")["clips"][0]["id"]
    eid = p.agregar_efecto(cid, tipo, params or {})
    return p, cid, eid, tiempos


def main():
    # ------------------------------------------------------------------ 1. catalogo
    print("=== 1. el catalogo de efectos de video ===")
    cat = efectos.catalogo()
    nuevos = ["temperatura", "curvas_luz", "lut", "reducir_ruido_imagen", "enfocar", "estabilizar", "rotar", "recortar_bordes", "lente", "enderezar"]
    ok(all(n in cat and cat[n]["categoria"] == "video" for n in nuevos), "los 10 efectos nuevos de video estan")
    ok(cat["rotar"]["etapa"] == "antes" and cat["recortar_bordes"]["etapa"] == "antes" and cat["enfocar"]["etapa"] == "despues",
       "los que cambian el tamano van 'antes' de encuadrar; el resto 'despues'")
    ok(cat["estabilizar"]["aviso"] and cat["color_basico"]["vista_previa"] and not cat["enfocar"]["vista_previa"], "con aviso y con marca de vista previa donde corresponde")
    ok(efectos.dims_tras("rotar", {"grados": "90"}, 640, 360) == (360, 640) and efectos.dims_tras("rotar", {"grados": "180"}, 640, 360) == (640, 360),
       "rotar 90 cambia el tamano; 180 no")
    ok(efectos.dims_tras("recortar_bordes", {"izquierda": 10.0, "derecha": 10.0, "arriba": 0.0, "abajo": 25.0}, 640, 360) == (512, 270), "recortar bordes calcula el tamano nuevo (par)")

    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=6)
    base, _ = exportar(ex.armar(src)[0], "i_base")
    base50 = cuadro_n(base, 50)

    # ------------------------------------------------------------------ 2. color
    print("=== 2. color ===")
    p, *_ = con_efecto(src, "temperatura", {"kelvin": 3000})
    c = medias(cuadro_n(exportar(p, "i_calido")[0], 50))
    p, *_ = con_efecto(src, "temperatura", {"kelvin": 11000})
    f = medias(cuadro_n(exportar(p, "i_frio")[0], 50))
    b = medias(base50)
    ok(c[0] - c[2] > b[0] - b[2] + 20 and f[2] - f[0] > b[2] - b[0] + 15, "temperatura: 3000 K da una imagen mas calida (mas rojo) y 11000 K una mas fria (mas azul)",
       f"base R-B {b[0] - b[2]:.0f}; 3000 K {c[0] - c[2]:.0f}; 11000 K {f[2] - f[0]:.0f} (azul-rojo)")

    def tonos(img):
        """Promedio de los oscuros medios (20-100) y de los muy claros (>215): lo que mueven las sombras y las luces."""
        px = list(img.convert("L").get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.convert("L").getdata())
        osc = [x for x in px if 20 <= x <= 100]
        cla = [x for x in px if x > 215]
        return sum(osc) / len(osc), sum(cla) / len(cla)

    # las curvas se miden sobre bandas de GRIS PLANO (50, 90, 130, 170, 230): en las barras de color saturadas (255,0,0...)
    # el recorte a 0 y 255 deja el resultado igual aunque la curva funcione
    bandas = os.path.join(TMP, "bandas.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=640x360:r=25:d=2,format=yuv420p,geq=lum='if(lt(X,128),50,if(lt(X,256),90,if(lt(X,384),130,if(lt(X,512),170,230))))':cb=128:cr=128",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", bandas)

    def niveles(img):
        g = img.convert("L")
        return [g.getpixel((x, 180)) for x in (64, 192, 320, 448, 576)]

    nb = niveles(cuadro_n(exportar(ex.armar(bandas)[0], "i_bandas_base")[0], 10))
    p, *_ = con_efecto(bandas, "curvas_luz", {"sombras": 0.15, "luces": 0.0})
    ns = niveles(cuadro_n(exportar(p, "i_sombras")[0], 10))
    ok(ns[0] > nb[0] + 15 and ns[1] > nb[1] + 15 and abs(ns[4] - nb[4]) <= 3, "curvas de luz: aclarar las sombras sube los grises oscuros y no toca el mas claro", f"{nb} -> {ns}")
    p, *_ = con_efecto(bandas, "curvas_luz", {"sombras": 0.0, "luces": -0.15})
    nl = niveles(cuadro_n(exportar(p, "i_luces")[0], 10))
    ok(nl[3] < nb[3] - 25 and nl[2] < nb[2] - 15 and abs(nl[0] - nb[0]) <= 3, "y bajar las luces oscurece los grises claros sin tocar el mas oscuro", f"{nb} -> {nl}")

    # una LUT que invierte los colores, en una carpeta con espacios y un nombre con espacios (a proposito: sin escapes raros)
    carpeta_lut = os.path.join(TMP, "mi carpeta con espacios")
    os.makedirs(carpeta_lut, exist_ok=True)
    lut = os.path.join(carpeta_lut, "look invertido.cube")
    with open(lut, "w") as f_:
        f_.write("TITLE \"invertir\"\nLUT_3D_SIZE 2\n")
        for bl in (0, 1):
            for gr in (0, 1):
                for rj in (0, 1):
                    f_.write("%d %d %d\n" % (1 - rj, 1 - gr, 1 - bl))
    p, cid, eid, tiempos = con_efecto(src, "lut", {"archivo": lut})
    inv = cuadro_n(exportar(p, "i_lut")[0], 50)
    ok(dif_media(inv, ImageChops.invert(base50)) < 12 and dif_media(inv, base50) > 60, "LUT (.cube) en una ruta con espacios: aplica el look (aqui, invertir colores)",
       f"contra el negativo {dif_media(inv, ImageChops.invert(base50)):.1f}, contra el original {dif_media(inv, base50):.1f}")
    ok(not glob.glob(os.path.join(tempfile.gettempdir(), "moviola-export-*")), "y la carpeta de trabajo temporal se borra al terminar")
    for malo, ruta in (("un archivo que no existe", os.path.join(TMP, "no_hay.cube")), ("un archivo de otro tipo", src)):
        p2, cid2, _, _ = con_efecto(src, "lut", {"archivo": lut})
        try:
            p2.cambiar_efecto(cid2, p2.pista("V1")["clips"][0]["efectos"][0]["id"], {"archivo": ruta})
            ok(False, "LUT: " + malo + " se rechaza")
        except ErrorEdicion as e:
            ok(True, "LUT: " + malo + ": error claro", str(e))
    # la LUT se borro despues de agregarla: al exportar, un error que se entiende
    efimera = os.path.join(carpeta_lut, "efimera.cube")
    open(efimera, "w").write(open(lut).read())
    p3, *_ = con_efecto(src, "lut", {"archivo": efimera})
    os.remove(efimera)
    try:
        exportar(p3, "i_lut_perdida")
        ok(False, "exportar con la LUT borrada da un error")
    except ex.exportar.ExportError as e:
        ok("No encuentro el archivo" in str(e), "si la LUT desaparece antes de exportar: error claro", str(e))

    # ------------------------------------------------------------------ 3. limpieza
    print("=== 3. limpieza de la imagen ===")
    ruidoso = os.path.join(TMP, "ruidoso.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2,noise=alls=30:allf=t+u,format=yuv420p", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", ruidoso)
    b_r, _ = exportar(ex.armar(ruidoso)[0], "i_ruidoso_base")
    ruido_base = bordes(cuadro_n(b_r, 20))
    p, *_ = con_efecto(ruidoso, "reducir_ruido_imagen", {"metodo": "rapido", "fuerza": 8})
    rapido = bordes(cuadro_n(exportar(p, "i_denoise_rapido")[0], 20))
    ok(rapido < 0.85 * ruido_base, "reducir ruido (rapido): baja el grano", f"{ruido_base:.1f} -> {rapido:.1f}")
    p, *_ = con_efecto(ruidoso, "reducir_ruido_imagen", {"metodo": "fino", "fuerza": 6})
    fino = bordes(cuadro_n(exportar(p, "i_denoise_fino")[0], 20))
    ok(fino < 0.85 * ruido_base, "reducir ruido (fino, nlmeans): tambien", f"{ruido_base:.1f} -> {fino:.1f}")
    nitido = bordes(base50)
    p, *_ = con_efecto(src, "enfocar", {"cantidad": 2.0})
    enf = bordes(cuadro_n(exportar(p, "i_enfocar")[0], 50))
    p, *_ = con_efecto(src, "enfocar", {"cantidad": -1.5})
    sua = bordes(cuadro_n(exportar(p, "i_suavizar")[0], 50))
    ok(enf > 1.1 * nitido and sua < 0.9 * nitido, "enfocar sube los detalles y suavizar (cantidad negativa) los baja", f"suave {sua:.1f} < normal {nitido:.1f} < enfocado {enf:.1f}")

    # ------------------------------------------------------------------ 4. estabilizar
    print("=== 4. estabilizar ===")
    # una escena ESTATICA con textura y un marcador fijo, vista por una camara que tiembla (un recorte que se mueve)
    from PIL import ImageDraw
    import random
    azar = random.Random(5)
    escena = Image.new("RGB", (800, 500))
    px_ = escena.load()
    for y_ in range(500):
        for x_ in range(800):
            v_ = azar.randint(40, 215)
            px_[x_, y_] = (v_, v_, v_)
    escena = escena.filter(ImageFilter.GaussianBlur(2.5))
    ImageDraw.Draw(escena).rectangle((380, 230, 419, 269), fill=(0, 255, 127))
    escena_png = os.path.join(TMP, "escena.png")
    escena.save(escena_png)
    tembloroso = os.path.join(TMP, "tembloroso.mp4")
    ex.ffmpeg("-loop", "1", "-framerate", "25", "-i", escena_png, "-t", "5", "-vf",
              "crop=w=640:h=360:x='80+30*sin(n/4)':y='70+20*sin(n/3.3)',format=yuv420p",
              "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", tembloroso)

    def posiciones(ruta):
        out = []
        for im in todos_los_cuadros(ruta):
            px = im.load()
            xs, ys = [], []
            for y in range(0, im.height, 2):
                for x in range(0, im.width, 2):
                    r_, g_, b_ = px[x, y]
                    if r_ < 60 and g_ > 220 and 80 < b_ < 180:
                        xs.append(x)
                        ys.append(y)
            if len(xs) > 30:                  # la mediana: unos pocos pixeles sueltos del fondo no la mueven
                xs.sort()
                ys.sort()
                out.append((xs[len(xs) // 2], ys[len(ys) // 2]))
            else:
                out.append(None)
        return out

    def temblor(pos):
        pos = [q for q in pos[2:-2] if q]
        mx = sum(q[0] for q in pos) / len(pos)
        my = sum(q[1] for q in pos) / len(pos)
        return math.sqrt(sum((q[0] - mx) ** 2 + (q[1] - my) ** 2 for q in pos) / len(pos)), len(pos)

    t_base = temblor(posiciones(exportar(ex.armar(tembloroso)[0], "i_tembloroso_base")[0]))
    ok(t_base[1] > 90 and t_base[0] > 10, "la toma de prueba tiembla de verdad (se rastrea el marcador en cada cuadro)", f"temblor {t_base[0]:.1f} px en {t_base[1]} cuadros")
    p, *_ = con_efecto(tembloroso, "estabilizar", {"fuerza": 20})
    arch, r = exportar(p, "i_estab")
    t_b = temblor(posiciones(arch))
    ok(t_b[0] < 0.25 * t_base[0], "estabilizar: el marcador casi deja de temblar", f"{t_base[0]:.1f} -> {t_b[0]:.1f} px")
    ok(len(todos_los_cuadros(arch)) == len(todos_los_cuadros(exportar(ex.armar(tembloroso)[0], "i_tembloroso_base2")[0])), "y sigue teniendo los mismos cuadros")
    ok(not glob.glob(os.path.join(tempfile.gettempdir(), "moviola-export-*")), "los archivos del analisis no quedan en ningun lado")
    # el analisis ve el clip YA cortado: cortar y estabilizar solo una parte
    p, fid, tiempos = ex.armar(tembloroso)
    p.dividir(2.0)
    p.agregar_efecto(p.pista("V1")["clips"][1]["id"], "estabilizar", {"fuerza": 20})
    pos = posiciones(exportar(p, "i_estab_mitad")[0])
    t1 = temblor(pos[:48])
    t2 = temblor(pos[52:])
    ok(t2[0] < 0.3 * t1[0], "estabilizar solo la segunda parte de un clip cortado: la primera sigue temblando y la segunda no", f"primera {t1[0]:.1f} px, segunda {t2[0]:.1f} px")

    # ------------------------------------------------------------------ 5. geometria
    print("=== 5. geometria ===")
    p, *_ = con_efecto(src, "rotar", {"grados": "90"})
    arch, r = exportar(p, "i_rotar90")
    rot = cuadro_n(arch, 50)
    ok(rot.size == (360, 640) and r["tamano"] == (360, 640), "rotar 90 (formato original): sale 360x640", str(rot.size))
    ok(dif_media(rot, base50.transpose(Image.Transpose.ROTATE_270)) < 6 and dif_media(rot, base50.resize((360, 640))) > 20, "y es un giro a la derecha (como las agujas del reloj)")
    p, *_ = con_efecto(src, "rotar", {"grados": "270"})
    ok(dif_media(cuadro_n(exportar(p, "i_rotar270")[0], 50), base50.transpose(Image.Transpose.ROTATE_90)) < 6, "rotar 270: giro a la izquierda")
    p, *_ = con_efecto(src, "rotar", {"grados": "180"})
    ok(dif_media(cuadro_n(exportar(p, "i_rotar180")[0], 50), base50.transpose(Image.Transpose.ROTATE_180)) < 6, "rotar 180")
    p, cid, eid, tiempos = con_efecto(src, "rotar", {"grados": "90"})
    arch, r = exportar(p, "i_rotar_vertical", formato="vertical")
    ok(r["tamano"] == (1080, 1920) and len(todos_los_cuadros(arch)) == 180, "rotar y exportar en vertical: el encuadre trabaja con la imagen ya girada (1080x1920, 180 cuadros)", str(r["tamano"]))
    # dos clips con distinta rotacion: todos salen del mismo tamano
    p, fid, tiempos = ex.armar(src)
    p.dividir(3.0)
    p.agregar_efecto(p.pista("V1")["clips"][1]["id"], "rotar", {"grados": "90"})
    arch, r = exportar(p, "i_rotar_mitad", formato="horizontal")
    ok(r["tamano"] == (1920, 1080) and len(todos_los_cuadros(arch)) == 180, "un clip girado y otro no, en 16:9: los dos entran en el mismo tamano", str(r["tamano"]))

    p, *_ = con_efecto(src, "recortar_bordes", {"izquierda": 25.0, "derecha": 0.0, "arriba": 10.0, "abajo": 0.0})
    arch, r = exportar(p, "i_recorte")
    rec = cuadro_n(arch, 50)
    esperado = base50.crop((160, 36, 640, 360))
    ok(rec.size == (480, 324) and dif_media(rec, esperado) < 6, "recortar bordes: 25% a la izquierda y 10% arriba -> 480x324, y es la parte correcta de la imagen", f"{rec.size}, dif {dif_media(rec, esperado):.1f}")
    p, *_ = con_efecto(src, "recortar_bordes", {"izquierda": 25.0, "derecha": 25.0})
    arch, r = exportar(p, "i_recorte_cuadrado", formato="cuadrado")
    ok(r["tamano"] == (1080, 1080), "y despues se encuadra al formato de salida (1:1)")

    p, *_ = con_efecto(src, "lente", {"k1": 0.3, "k2": 0.0})
    lente = cuadro_n(exportar(p, "i_lente")[0], 50)
    ok(lente.size == base50.size and dif_media(lente, base50) > 3, "corregir lente: cambia la imagen sin cambiar el tamano", f"dif {dif_media(lente, base50):.1f}")
    p, *_ = con_efecto(src, "enderezar", {"angulo": 5.0, "ampliar": 1.2})
    end = cuadro_n(exportar(p, "i_enderezar")[0], 50)
    esquinas = [end.getpixel(q) for q in ((2, 2), (end.width - 3, 2), (2, end.height - 3), (end.width - 3, end.height - 3))]
    ok(end.size == base50.size and dif_media(end, base50) > 8 and all(sum(q) > 60 for q in esquinas), "enderezar: gira, mantiene el tamano y no deja esquinas negras", f"esquinas {esquinas}")

    # ------------------------------------------------------------------ 6. varios, y los cuadros siguen exactos
    print("=== 6. efectos apilados y cuadros exactos ===")
    p, fid, tiempos = ex.armar(src)
    cid = p.pista("V1")["clips"][0]["id"]
    for tipo, params in (("temperatura", {"kelvin": 4000}), ("enfocar", {}), ("curvas_luz", {"sombras": 0.05}), ("reducir_ruido_imagen", {})):
        p.agregar_efecto(cid, tipo, params)
    p.dividir(3.0)
    arch, r = exportar(p, "i_apilados")
    ok(ex.leer_codigos(arch) == ex.esperados(p, tiempos), "cuatro efectos juntos y un corte: los 180 cuadros siguen exactos y en orden")

    # ------------------------------------------------------------------ 7. transiciones
    print("=== 7. transiciones entre clips ===")
    # 12 s: el gris sube 20 niveles por segundo (10, 30, 50...) y el tono sube 50 Hz por segundo (300, 350...): cada instante se reconoce
    colores = os.path.join(TMP, "colores.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=12,format=yuv420p,geq=lum='10+20*floor(T)':cb=128:cr=128",
              "-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*(300+50*floor(t))*t)':s=48000:d=12:c=mono",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", colores)

    def gris(img, x=160, y=90):
        return img.convert("L").getpixel((x, y))

    def nivel(t_):
        """El gris (0-255) que se VE para la fuente en el segundo t_: el video guarda el nivel Y en rango limitado (16-235)."""
        y = 10 + 20 * int(t_)
        return max(0.0, min(255.0, (y - 16) * 255 / 219))

    def salto():
        """A = fuente 0-4 s, B = fuente 8-12 s, pegados (se borro 4-8): el corte cae en el segundo 4, y a cada lado sobra material."""
        q, fid_, tiempos_ = ex.armar(colores)
        q.dividir(4.0)
        q.dividir(8.0)
        q.borrar_rango(4.0, 8.0)
        return q, tiempos_

    q, tiempos = salto()
    b = q.pista("V1")["clips"][1]
    ok(abs(q.duracion() - 8.0) < 0.05 and q.transicion_maxima(b["id"]) >= 2.9, "se puede hacer una transicion donde hay un corte con material a los lados", f"maximo {q.transicion_maxima(b['id'])} s")
    ok(q.transicion_maxima(q.pista("V1")["clips"][0]["id"]) == 0.0, "el primer clip no tiene transicion de entrada")
    q.poner_transicion(b["grupo"], "disolver", 1.0)
    ok(q.pista("V1")["clips"][1]["transicion"] == {"tipo": "disolver", "duracion": 1.0} and q.pista("A1")["clips"][1]["transicion"] is not None and q.validar() == [],
       "la transicion se pone en el video y en su audio enlazado")
    arch, r = exportar(q, "t_disolver")
    cuadros = todos_los_cuadros(arch)
    ok(len(cuadros) == 240 and abs(r["duracion"] - 8.0) < 0.1, "la duracion NO cambia: 240 cuadros, 8 s", f"{len(cuadros)} cuadros, {r['duracion']:.2f} s")
    g = [gris(cuadros[int(x * 30)]) for x in (1.0, 3.2, 3.5, 4.0, 4.5, 4.8, 7.0)]
    esp = [nivel(1.0), nivel(3.2), None, (nivel(4.0) + nivel(8.0)) / 2, None, nivel(8.8), nivel(11.0)]       # nivel(4.0)=79, nivel(8.0)=179
    ok(abs(g[0] - esp[0]) < 4 and abs(g[1] - esp[1]) < 4 and abs(g[5] - esp[5]) < 4 and abs(g[6] - esp[6]) < 4, "fuera de la transicion la imagen es la de siempre", f"{g}")
    ok(abs(g[3] - esp[3]) < 6, "en el medio del corte es la mezcla justa de las dos tomas", f"{g[3]} (esperado {esp[3]:.0f})")
    ok(g[1] < g[2] + 1 and g[2] <= g[3] + 1 and g[3] <= g[4] + 1 and g[4] <= g[5] + 1, "y entre los dos extremos pasa de a poco de una a otra", f"{g[1:6]}")
    m = ex.muestras(arch)
    a_antes = ex.goertzel(m, 3.0, 3.3, 450)            # fuente 3-4 s: 450 Hz
    b_despues = ex.goertzel(m, 4.7, 4.95, 700)         # fuente 8.7-8.95 s: 700 Hz
    medio_a = ex.goertzel(m, 3.9, 4.1, 500)            # material de A que sobra (fuente 4.x: 500 Hz)
    medio_b = ex.goertzel(m, 3.9, 4.1, 700)            # material de B que sobra (fuente 7.x: 650 Hz / 8: 700 Hz)
    ok(a_antes > 1e-4 and b_despues > 1e-4, "el audio: antes suena la primera toma y despues la segunda", f"{a_antes:.2e}, {b_despues:.2e}")
    ok(medio_a > 1e-5 and medio_b > 1e-5, "y en el medio suenan las dos a la vez (fundido cruzado)", f"{medio_a:.2e}, {medio_b:.2e}")
    ok(abs(float(ex.sondear(arch)[1]["duration"]) - float(ex.sondear(arch)[0]["duration"])) < 0.05, "y el audio y el video duran lo mismo")

    for tipo, esperado in (("fundido_negro", "negro"), ("fundido_blanco", "blanco")):
        q2, _ = salto()
        q2.poner_transicion(q2.pista("V1")["clips"][1]["grupo"], tipo, 1.0)
        c2 = todos_los_cuadros(exportar(q2, "t_" + tipo)[0])
        zona = [gris(c2[k]) for k in range(105, 136)]
        ok((min(zona) < 25) if esperado == "negro" else (max(zona) > 225), "%s: durante la transicion la imagen pasa por %s" % (tipo, esperado), f"gris minimo {min(zona)}, maximo {max(zona)}")
    q3, _ = salto()
    q3.poner_transicion(q3.pista("V1")["clips"][1]["grupo"], "deslizar_izquierda", 1.0)
    c3 = todos_los_cuadros(exportar(q3, "t_desliza")[0])
    izq, der = gris(c3[120], 20, 90), gris(c3[120], 300, 90)
    ok(abs(izq - nivel(4.0)) < 8 and abs(der - nivel(8.0)) < 8, "deslizar a la izquierda: a mitad de camino se ven las dos tomas lado a lado", f"izquierda {izq} ({nivel(4.0):.0f}), derecha {der} ({nivel(8.0):.0f})")
    q4, _ = salto()
    q4.poner_transicion(q4.pista("V1")["clips"][1]["grupo"], "circulo", 1.0)
    c4 = todos_los_cuadros(exportar(q4, "t_circulo")[0])
    ok(len(c4) == 240 and abs(gris(c4[120], 160, 90) - nivel(8.0)) < 10 and abs(gris(c4[120], 5, 5) - nivel(4.0)) < 10, "circulo: el centro ya es la segunda toma y las esquinas todavia la primera", f"centro {gris(c4[120], 160, 90)}, esquina {gris(c4[120], 5, 5)}")

    # con el codigo de barras: fuera de la transicion los cuadros son EXACTAMENTE los de la fuente, uno por uno
    qb, fidb, tiemposb = ex.armar(src)
    qb.dividir(2.0)
    qb.dividir(4.0)
    qb.borrar_rango(2.0, 4.0)                                                   # A = fuente 0-2, B = fuente 4-6 (src dura 6 s)
    qb.poner_transicion(qb.pista("V1")["clips"][1]["grupo"], "disolver", 1.0)
    archb, rb_ = exportar(qb, "t_codigos")
    cod = ex.leer_codigos(archb)
    esp_b = ex.esperados(qb, tiemposb)
    ok(len(cod) == len(esp_b) == 120 and cod[:45] == esp_b[:45] and cod[75:] == esp_b[75:], "con codigo de barras: fuera de la transicion (1,5-2,5 s) los cuadros son exactos y en orden", f"{len(cod)} cuadros")
    ok(cod[45:75] != esp_b[45:75], "y durante la transicion la imagen es otra cosa (la mezcla)")

    print("    --- limites y errores")
    q5, _ = salto()
    g5 = q5.pista("V1")["clips"][1]["grupo"]
    for malo, args in (("una transicion que no existe", ("no_existe", 1.0)), ("de 0 s", ("disolver", 0.0)), ("de 10 s", ("disolver", 10.0))):
        try:
            q5.poner_transicion(g5, *args)
            ok(False, "se rechaza " + malo)
        except ErrorEdicion as e:
            ok(True, "se rechaza " + malo, str(e))
    qp, _, _ = ex.armar(colores)
    try:
        qp.poner_transicion(qp.pista("V1")["clips"][0]["grupo"], "disolver", 1.0)
        ok(False, "sin clip anterior se rechaza")
    except ErrorEdicion as e:
        ok("pegado" in str(e), "sin otro clip pegado antes: error claro", str(e))
    qc, _, _ = ex.armar(colores)
    qc.dividir(6.0)
    ok(qc.transicion_maxima(qc.pista("V1")["clips"][1]["id"]) >= 2.9, "un corte simple (sin borrar nada) tambien admite transicion")
    # el borde de un archivo no tiene material sobrante: un clip que empieza en 0 de otra fuente no admite transicion
    qd, _, _ = ex.armar(colores)
    qd.dividir(3.0)
    qd.borrar_rango(0.0, 3.0)                                      # B ahora empieza en el segundo 0 de la linea, pero en la fuente en 3
    ok(qd.transicion_maxima(qd.pista("V1")["clips"][0]["id"]) == 0.0, "el primer clip de la linea de tiempo no tiene transicion")
    # fundido + transicion: el motor no deja que se pisen
    q6, _ = salto()
    g6 = q6.pista("V1")["clips"][1]["grupo"]
    q6.poner_transicion(g6, "disolver", 1.0)
    try:
        q6.fade(q6.pista("V1")["clips"][1]["id"], "in", 1.0)
        ok(False, "un fundido de entrada sobre una transicion se rechaza")
    except ErrorEdicion as e:
        ok("transición" in str(e), "un fundido de entrada sobre una transicion: error claro", str(e))
    try:
        q6.fade(q6.pista("V1")["clips"][0]["id"], "out", 1.0)
        ok(False, "tampoco un fundido de salida del clip anterior")
    except ErrorEdicion as e:
        ok(True, "ni un fundido de salida en el clip de antes")
    # se quita, se deshace, y desaparece cuando deja de tener sentido
    q6.quitar_transicion(g6)
    ok(q6.pista("V1")["clips"][1]["transicion"] is None, "se puede quitar")
    q6.deshacer()
    ok(q6.pista("V1")["clips"][1]["transicion"] is not None, "y deshacer la devuelve")
    q6.borrar_grupo(q6.pista("V1")["clips"][0]["grupo"])
    ok(all(c["transicion"] is None for pp in q6.pistas for c in pp["clips"]) and q6.validar() == [], "si se borra el clip anterior la transicion se va sola (y el proyecto sigue valido)")
    q6.deshacer()
    ok(q6.pista("V1")["clips"][1]["transicion"] is not None, "y un solo deshacer devuelve el borrado Y la transicion")

    print("    --- dos transiciones seguidas, con efectos y un corte en el medio")
    q7, fid7, tiempos7 = ex.armar(colores)
    q7.dividir(3.0)
    q7.dividir(5.0)
    q7.dividir(8.0)
    q7.dividir(9.0)
    q7.borrar_rango(3.0, 5.0)
    q7.borrar_rango(6.0, 7.0)                                      # quedan [0-3] [5-8] [9-12]: 9 s
    cl = q7.pista("V1")["clips"]
    q7.poner_transicion(cl[1]["grupo"], "disolver", 0.8)
    q7.poner_transicion(q7.pista("V1")["clips"][2]["grupo"], "granulado", 0.6)
    q7.agregar_efecto(q7.pista("V1")["clips"][1]["id"], "color_basico", {"brillo": 0.1})
    arch, r = exportar(q7, "t_dos")
    c7 = todos_los_cuadros(arch)
    ok(len(c7) == 270 and abs(r["duracion"] - 9.0) < 0.1 and q7.validar() == [], "tres clips con dos transiciones: 9 s y 270 cuadros", f"{len(c7)} cuadros, {r['duracion']:.2f} s")
    ok(abs(gris(c7[int(1.5 * 30)]) - nivel(1.5)) < 5 and nivel(6.5) + 15 < gris(c7[int(4.5 * 30)]) < nivel(6.5) + 45 and abs(gris(c7[int(8 * 30)]) - nivel(11.0)) < 5,
       "lejos de las transiciones cada clip muestra su propio tramo de la fuente (el del medio, ademas, mas claro por su efecto de brillo)", f"{gris(c7[45])}, {gris(c7[135])}, {gris(c7[240])}")
    m7 = ex.muestras(arch)
    ok(abs(float(ex.sondear(arch)[1]["duration"]) - float(ex.sondear(arch)[0]["duration"])) < 0.05, "audio y video duran lo mismo")
    # solo audio de un proyecto con transiciones: dura lo mismo y suena
    ra = ex.exportar_a(q7, "t_dos_audio", formato="wav")
    ok(abs(ra["duracion"] - 9.0) < 0.05, "exportar solo el audio de un proyecto con transiciones: tambien 9 s", f"{ra['duracion']:.2f}")

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
