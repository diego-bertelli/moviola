# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 4b (composicion): logo encima, quitar fondo de color, texto y zoom lento.

Uso:  python -I pruebas/prueba_composicion.py

Todo se comprueba MIDIENDO la imagen del archivo exportado: donde cae el logo, de que color queda el fondo que se quita,
en que region y en que momento aparece el texto, y hacia donde se acerca el zoom.
"""

import glob
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)

from PIL import Image, ImageChops  # noqa: E402

import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402
from motor import efectos  # noqa: E402
from motor.proyecto import ErrorEdicion  # noqa: E402

TMP = ex.TMP
ok = ex.ok


def caja_de_cambios(a, b, umbral=60):
    """Rectangulo (x0, y0, x1, y1) donde las dos imagenes difieren mucho; None si no difieren."""
    d = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > umbral else 0)
    return d.getbbox()


def cerca(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def main():
    # ------------------------------------------------------------------ 1. catalogo
    print("=== 1. el catalogo ===")
    cat = efectos.catalogo()
    ok(all(n in cat and cat[n]["categoria"] == "video" for n in ("superponer", "quitar_fondo", "texto", "zoom_lento")), "los 4 efectos de composicion estan")
    ok(efectos.es_complejo("superponer") and efectos.es_complejo("quitar_fondo") and not efectos.es_complejo("texto"), "superponer y quitar fondo arman un subgrafo; texto y zoom son filtros comunes")
    ok(any(s["tipo"] == "texto" for s in cat["texto"]["params"]), "hay un tipo de ajuste nuevo: texto")
    try:
        efectos.limpiar_params("texto", {"texto": "x" * 301})
        ok(False, "un texto de 301 letras se rechaza")
    except efectos.ErrorEfecto as e:
        ok(True, "un texto demasiado largo da un error claro", str(e))
    try:
        efectos.limpiar_params("texto", {"texto": 5})
        ok(False, "un texto que no es texto se rechaza")
    except efectos.ErrorEfecto:
        ok(True, "y algo que no es texto, tambien")
    ok(efectos.es_neutro("texto", {"texto": ""}) and efectos.es_neutro("superponer", {"archivo": ""}) and efectos.es_neutro("zoom_lento", {"zoom": 1.0})
       and not efectos.es_neutro("quitar_fondo", {}), "texto vacio, sin imagen y zoom 1x no hacen nada; quitar fondo siempre actua")

    src = ex.crear_fuente(os.path.join(TMP, "src.mp4"), dur=6)
    base_arch, _ = im.exportar(ex.armar(src)[0], "c_base")
    base = im.todos_los_cuadros(base_arch)
    ok(len(base) == 180, "la fuente de prueba: 180 cuadros", str(len(base)))

    # ------------------------------------------------------------------ 2. logo encima
    print("=== 2. logo o imagen encima ===")
    carpeta = os.path.join(TMP, "mis imagenes con espacios")
    os.makedirs(carpeta, exist_ok=True)
    macizo = os.path.join(carpeta, "logo macizo.png")
    Image.new("RGBA", (200, 100), (255, 0, 255, 255)).save(macizo)
    mitad = os.path.join(carpeta, "logo mitad.png")
    im_m = Image.new("RGBA", (200, 100), (255, 0, 255, 255))
    im_m.paste((0, 0, 0, 0), (100, 0, 200, 100))
    im_m.save(mitad)

    # 20% de 640 = 128 de ancho, 64 de alto; margen 3% de 640 = 19
    w_l, h_l, mg = 128, 64, 19
    esperado = {
        "arriba_izquierda": (mg + w_l / 2, mg + h_l / 2), "arriba_centro": (320, mg + h_l / 2), "arriba_derecha": (640 - mg - w_l / 2, mg + h_l / 2),
        "centro_izquierda": (mg + w_l / 2, 180), "centro": (320, 180), "centro_derecha": (640 - mg - w_l / 2, 180),
        "abajo_izquierda": (mg + w_l / 2, 360 - mg - h_l / 2), "abajo_centro": (320, 360 - mg - h_l / 2), "abajo_derecha": (640 - mg - w_l / 2, 360 - mg - h_l / 2)}
    otro = os.path.join(carpeta, "logo verde.png")
    Image.new("RGBA", (200, 100), (0, 200, 60, 255)).save(otro)
    malas = []
    for pos, (ex_, ey_) in esperado.items():
        # el logo se mide con DOS colores distintos y se une lo que cambio: sobre la imagen de prueba (muy colorida) un color solo puede perderse en parte
        cajas, largo_n = [], 0
        for logo in (macizo, otro):
            p, cid, eid, _ = im.con_efecto(src, "superponer", {"archivo": logo, "posicion": pos}, pos)
            cuadros = im.todos_los_cuadros(im.exportar(p, "c_pos_" + pos)[0])
            largo_n = len(cuadros)
            cajas.append(caja_de_cambios(cuadros[40], base[40]))
        if None in cajas or largo_n != 180:
            malas.append((pos, cajas, largo_n))
            continue
        bb = (min(c_[0] for c_ in cajas), min(c_[1] for c_ in cajas), max(c_[2] for c_ in cajas), max(c_[3] for c_ in cajas))
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        if abs(cx - ex_) > 5 or abs(cy - ey_) > 5 or abs((bb[2] - bb[0]) - w_l) > 4 or abs((bb[3] - bb[1]) - h_l) > 4:
            malas.append((pos, bb, (ex_, ey_)))
    ok(not malas, "las 9 posiciones: el logo (128x64) cae donde corresponde, con su margen, y el video sigue durando 180 cuadros", str(malas))

    p, cid, eid, _ = im.con_efecto(src, "superponer", {"archivo": mitad, "posicion": "arriba_izquierda", "tamano": 40, "margen": 0}, "mitad")
    cuadros = im.todos_los_cuadros(im.exportar(p, "c_mitad")[0])
    # 40% de 640 = 256 de ancho y 128 de alto; la mitad izquierda (0..127) es opaca, la derecha transparente
    ok(cerca(cuadros[40].getpixel((60, 60)), (255, 0, 255), 12), "el logo opaco se ve del color del logo", str(cuadros[40].getpixel((60, 60))))
    ok(cerca(cuadros[40].getpixel((200, 60)), base[40].getpixel((200, 60)), 12), "y donde el PNG es transparente se sigue viendo el video", f"{cuadros[40].getpixel((200, 60))} vs {base[40].getpixel((200, 60))}")

    p, cid, eid, _ = im.con_efecto(src, "superponer", {"archivo": macizo, "posicion": "arriba_izquierda", "tamano": 40, "margen": 0, "opacidad": 0.5}, "opaco")
    cuadros = im.todos_los_cuadros(im.exportar(p, "c_opacidad")[0])
    px, b0 = cuadros[40].getpixel((60, 60)), base[40].getpixel((60, 60))
    mezcla = tuple(0.5 * m + 0.5 * b for m, b in zip((255, 0, 255), b0))
    ok(cerca(px, mezcla, 22), "con opacidad 0,5 el logo se mezcla mitad y mitad con el video", f"{px} vs {tuple(int(x) for x in mezcla)}")

    # errores: sin archivo no hace nada; archivo de otro tipo se rechaza; archivo que desaparece antes de exportar: error claro
    p, cid, eid, _ = im.con_efecto(src, "superponer", {}, "vacio")
    a_vacio = im.todos_los_cuadros(im.exportar(p, "c_logo_vacio")[0])
    ok(len(a_vacio) == 180 and im.dif_media(a_vacio[40], base[40]) < 1.5, "un logo sin imagen elegida no cambia nada")
    p, cid, eid, _ = im.con_efecto(src, "superponer", {"archivo": macizo}, "e")
    try:
        p.cambiar_efecto(cid, eid, {"archivo": src})
        ok(False, "una imagen que es un video se rechaza")
    except ErrorEdicion as e:
        ok(True, "una imagen que en realidad es un video: error claro", str(e))
    efimera = os.path.join(carpeta, "efimera.png")
    Image.new("RGBA", (10, 10), (1, 2, 3, 255)).save(efimera)
    p, *_ = im.con_efecto(src, "superponer", {"archivo": efimera}, "ef")
    os.remove(efimera)
    try:
        im.exportar(p, "c_logo_perdido")
        ok(False, "exportar con el logo borrado da un error")
    except ex.exportar.ExportError as e:
        ok("archivo" in str(e).lower(), "si la imagen desaparece antes de exportar: error claro", str(e))

    # ------------------------------------------------------------------ 3. quitar el fondo
    print("=== 3. quitar el fondo verde o azul ===")
    verde = os.path.join(TMP, "verde.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=0x00FF00:s=640x360:r=30:d=3,drawbox=x=220:y=100:w=200:h=160:color=red:t=fill,format=yuv420p",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", verde)
    azul = os.path.join(TMP, "azul.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "color=c=0x0000FF:s=640x360:r=30:d=3,drawbox=x=220:y=100:w=200:h=160:color=yellow:t=fill,format=yuv420p",
              "-c:v", "libx264", "-crf", "8", "-pix_fmt", "yuv420p", azul)
    p, *_ = im.con_efecto(verde, "quitar_fondo", {"fondo": "gris"}, "g")
    cu = im.todos_los_cuadros(im.exportar(p, "c_chroma_gris")[0])
    ok(len(cu) == 90 and cerca(cu[10].getpixel((50, 50)), (128, 128, 128), 14) and cerca(cu[10].getpixel((320, 180)), (255, 0, 0), 40),
       "pantalla verde sobre gris: el verde pasa a gris y el cuadro rojo se queda", f"{cu[10].getpixel((50, 50))} / {cu[10].getpixel((320, 180))}")
    p, *_ = im.con_efecto(verde, "quitar_fondo", {"fondo": "negro"}, "n")
    cu = im.todos_los_cuadros(im.exportar(p, "c_chroma_negro")[0])
    ok(cerca(cu[10].getpixel((50, 50)), (0, 0, 0), 14) and cerca(cu[89].getpixel((600, 340)), (0, 0, 0), 14), "con fondo negro, tambien hasta el ultimo cuadro", f"{cu[10].getpixel((50, 50))}")
    p, *_ = im.con_efecto(azul, "quitar_fondo", {"color": "azul", "fondo": "blanco"}, "a")
    cu = im.todos_los_cuadros(im.exportar(p, "c_chroma_azul")[0])
    ok(cerca(cu[10].getpixel((50, 50)), (255, 255, 255), 14) and cerca(cu[10].getpixel((320, 180)), (255, 255, 0), 40), "pantalla azul sobre blanco: el azul pasa a blanco y el amarillo se queda", f"{cu[10].getpixel((50, 50))} / {cu[10].getpixel((320, 180))}")
    fondo = os.path.join(carpeta, "fondo naranja.png")
    Image.new("RGB", (300, 200), (255, 128, 0)).save(fondo)
    p, *_ = im.con_efecto(verde, "quitar_fondo", {"fondo": "imagen", "imagen": fondo}, "i")
    cu = im.todos_los_cuadros(im.exportar(p, "c_chroma_imagen")[0])
    ok(len(cu) == 90 and cerca(cu[10].getpixel((50, 50)), (255, 128, 0), 18) and cerca(cu[89].getpixel((600, 340)), (255, 128, 0), 18)
       and cerca(cu[10].getpixel((320, 180)), (255, 0, 0), 40), "con una IMAGEN de fondo (se repite durante todo el clip): el verde pasa a la imagen", f"{cu[10].getpixel((50, 50))}")
    p, cid, eid, _ = im.con_efecto(verde, "quitar_fondo", {"fondo": "imagen", "imagen": ""}, "sin")
    try:
        im.exportar(p, "c_chroma_sin_imagen")
        ok(False, "fondo 'una imagen' sin elegir la imagen da un error")
    except ex.exportar.ExportError as e:
        ok("fondo" in str(e).lower(), "fondo «una imagen» sin elegir la imagen: error claro", str(e))

    # ------------------------------------------------------------------ 4. texto
    print("=== 4. texto o titulo ===")
    p, *_ = im.con_efecto(src, "texto", {"texto": "HOLA MUNDO", "tamano": 14, "posicion": "abajo_centro", "caja": True, "contorno": True}, "t")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto")[0])
    bb = caja_de_cambios(cu[40], base[40], 40)
    ok(len(cu) == 180 and bb is not None and bb[1] > 250 and abs((bb[0] + bb[2]) / 2 - 320) < 25 and bb[3] <= 360,
       "el texto aparece abajo y centrado, sin tocar la parte de arriba", f"caja {bb}")
    p, *_ = im.con_efecto(src, "texto", {"texto": "ARRIBA", "tamano": 14, "posicion": "arriba_izquierda", "caja": False}, "t2")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto_arriba")[0])
    bb = caja_de_cambios(cu[40], base[40], 40)
    ok(bb is not None and bb[1] < 60 and bb[0] < 60 and bb[2] < 320, "arriba a la izquierda, tambien", f"caja {bb}")

    p, *_ = im.con_efecto(src, "texto", {"texto": "SOLO UN RATO", "tamano": 14, "posicion": "centro_izquierda", "desde": 1.0, "hasta": 2.0, "caja": True}, "ventana")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto_ventana")[0])
    antes, durante, despues = (im.dif_media(cu[i], base[i]) for i in (15, 45, 75))
    ok(antes < 1.5 and durante > 3 * max(antes, 0.3) and despues < 1.5, "con «aparece a 1 s, desaparece a 2 s»: no esta a los 0,5 s, esta a los 1,5 s y ya no a los 2,5 s",
       f"diferencia {antes:.2f} / {durante:.2f} / {despues:.2f}")
    p, *_ = im.con_efecto(src, "texto", {"texto": "DESDE EL 3", "tamano": 14, "desde": 3.0, "caja": True}, "desde")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto_desde")[0])
    ok(im.dif_media(cu[60], base[60]) < 1.5 and im.dif_media(cu[100], base[100]) > 1.0 and im.dif_media(cu[179], base[179]) > 1.0,
       "con solo «aparece a los 3 s» (sin final) se queda hasta el ultimo cuadro")

    p, *_ = im.con_efecto(src, "texto", {"texto": "Nandu ¿qué? 100% 'ok' : \\ \"hola\" {n} %{pts}", "tamano": 10, "caja": True}, "raro")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto_raro")[0])
    ok(len(cu) == 180 and caja_de_cambios(cu[40], base[40], 40) is not None, "un texto con acentos, comillas, dos puntos, barras y porcentajes se escribe tal cual (sin tratar nada como codigo)")
    p, *_ = im.con_efecto(src, "texto", {"texto": "linea uno\nlinea dos", "tamano": 10, "caja": True, "posicion": "centro"}, "dos")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto_dos_lineas")[0])
    bb = caja_de_cambios(cu[40], base[40], 40)
    ok(bb is not None and (bb[3] - bb[1]) > 40, "dos renglones: la caja del texto es mas alta que un solo renglon", f"alto {bb[3] - bb[1] if bb else None}")

    p, *_ = im.con_efecto(src, "texto", {"texto": "COLOR", "tamano": 20, "color": "coral", "contorno": False, "caja": False, "posicion": "centro"}, "col")
    cu = im.todos_los_cuadros(im.exportar(p, "c_texto_coral")[0])
    n_coral = sum(1 for px in cu[40].crop((150, 100, 490, 260)).getdata() if abs(px[0] - 255) < 30 and abs(px[1] - 109) < 30 and abs(px[2] - 90) < 30)
    p, *_ = im.con_efecto(src, "texto", {"texto": "COLOR", "tamano": 20, "color": "blanco", "contorno": False, "caja": False, "posicion": "centro"}, "col2")
    cu2 = im.todos_los_cuadros(im.exportar(p, "c_texto_blanco")[0])
    n_blanco = sum(1 for px in cu2[40].crop((150, 100, 490, 260)).getdata() if px[0] > 245 and px[1] > 245 and px[2] > 245)
    n_blanco_base = sum(1 for px in base[40].crop((150, 100, 490, 260)).getdata() if px[0] > 245 and px[1] > 245 and px[2] > 245)
    ok(n_coral > 300 and n_blanco > n_blanco_base + 300, "el color elegido se ve: coral (255,109,90) y blanco aparecen como pixeles del texto", f"coral {n_coral}; blanco {n_blanco} contra {n_blanco_base} sin texto")

    # cada letra elegida existe (se copia de las fuentes de Windows a la carpeta de trabajo)
    faltan = []
    for clave in efectos.FUENTES:
        p, *_ = im.con_efecto(src, "texto", {"texto": "Aa", "fuente": clave, "tamano": 12}, "f")
        try:
            cu = im.todos_los_cuadros(im.exportar(p, "c_letra_" + clave)[0])
            if caja_de_cambios(cu[10], base[10], 40) is None:
                faltan.append(clave)
        except ex.exportar.ExportError:
            faltan.append(clave)
    ok(not faltan, "las %d letras del catalogo se pueden usar" % len(efectos.FUENTES), str(faltan))

    # ------------------------------------------------------------------ 5. zoom lento
    print("=== 5. zoom lento ===")

    def recorte_ampliado(img, x0, y0, x1, y1):
        return img.crop((x0, y0, x1, y1)).resize((640, 360), Image.BILINEAR)

    p, *_ = im.con_efecto(src, "zoom_lento", {"direccion": "acercar", "zoom": 2.0}, "z")
    cu = im.todos_los_cuadros(im.exportar(p, "c_zoom_acercar")[0])
    ok(len(cu) == 180, "el zoom no cambia la cantidad de cuadros", str(len(cu)))
    d_ini = im.dif_media(cu[0], base[0])
    d_fin_zoom = im.dif_media(cu[179], recorte_ampliado(base[179], 160, 90, 480, 270))
    d_fin_base = im.dif_media(cu[179], base[179])
    ok(d_ini < 8 and d_fin_zoom < 14 and d_fin_base > 25, "acercar 2x: empieza igual que el video y termina mostrando solo la mitad central, ampliada",
       f"primer cuadro vs video {d_ini:.1f}; ultimo vs recorte {d_fin_zoom:.1f}, vs video {d_fin_base:.1f}")
    d_med = im.dif_media(cu[90], recorte_ampliado(base[90], 106, 60, 534, 300))        # a la mitad: zoom ~1,5 -> se ve 1/1,5 del ancho
    ok(d_med < 16, "y a la mitad del clip va por el medio (zoom 1,5x)", f"{d_med:.1f}")

    p, *_ = im.con_efecto(src, "zoom_lento", {"direccion": "alejar", "zoom": 2.0}, "za")
    cu = im.todos_los_cuadros(im.exportar(p, "c_zoom_alejar")[0])
    ok(im.dif_media(cu[0], recorte_ampliado(base[0], 160, 90, 480, 270)) < 14 and im.dif_media(cu[179], base[179]) < 12,
       "alejar: empieza ampliado y termina con la imagen completa")

    p, *_ = im.con_efecto(src, "zoom_lento", {"direccion": "acercar", "zoom": 2.0, "centro_x": 0.0, "centro_y": 0.0}, "zc")
    cu = im.todos_los_cuadros(im.exportar(p, "c_zoom_esquina")[0])
    d_izq = im.dif_media(cu[179], recorte_ampliado(base[179], 0, 0, 320, 180))
    d_der = im.dif_media(cu[179], recorte_ampliado(base[179], 320, 180, 640, 360))
    ok(d_izq < 14 and d_der > 25, "con el centro arriba a la izquierda se acerca hacia esa esquina", f"esquina {d_izq:.1f}; esquina opuesta {d_der:.1f}")

    # ------------------------------------------------------------------ 6. todo junto
    print("=== 6. todo junto: varios clips, transicion, velocidad y los cuatro efectos ===")
    p, fid, tiempos = ex.armar(src)
    p.dividir(3.0)
    a, b = p.pista("V1")["clips"]
    p.agregar_efecto(a["id"], "texto", {"texto": "PRIMERO", "tamano": 12, "caja": True})
    p.agregar_efecto(a["id"], "superponer", {"archivo": macizo, "posicion": "arriba_derecha"})
    p.agregar_efecto(b["id"], "zoom_lento", {"zoom": 1.6})
    p.agregar_efecto(b["id"], "color_basico", {"brillo": 0.1})
    p.agregar_efecto(b["id"], "texto", {"texto": "SEGUNDO", "tamano": 12, "posicion": "arriba_centro"})
    p.poner_transicion(b["grupo"], "disolver", 1.0)
    p.velocidad(a["grupo"], 1.5)
    arch, r = im.exportar(p, "c_todo")
    cu = im.todos_los_cuadros(arch)
    esperado_n = round(p.duracion() * 30)
    ok(p.validar() == [] and abs(len(cu) - esperado_n) <= 1 and abs(r["duracion"] - p.duracion()) < 0.1,
       "se exporta con la duracion del proyecto (el largo de cada clip incluye velocidad y transicion)", f"{len(cu)} cuadros (esperados {esperado_n}), {r['duracion']:.2f} s")
    bb_a = caja_de_cambios(cu[10], base[15], 40)       # el clip A va a 1,5x: el cuadro 10 de la salida es el 15 de la fuente
    ok(bb_a is not None, "el clip con texto y logo muestra algo encima", f"{bb_a}")
    ok(not glob.glob(os.path.join(tempfile.gettempdir(), "moviola-export-*")), "y la carpeta de trabajo temporal se borra al terminar")

    # un clip al reves con texto y con zoom
    p, fid, tiempos = ex.armar(src)
    p.dividir(2.0)
    c = p.pista("V1")["clips"][0]
    p.reversa(c["grupo"], True)
    p.agregar_efecto(c["id"], "zoom_lento", {"zoom": 1.5})
    p.agregar_efecto(c["id"], "texto", {"texto": "AL REVES", "tamano": 12})
    arch, r = im.exportar(p, "c_reves")
    ok(p.validar() == [] and len(im.todos_los_cuadros(arch)) == 180, "un clip al reves con zoom y texto tambien se exporta completo")

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
