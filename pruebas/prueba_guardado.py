# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Fase 7 (proyectos): guardar y abrir un proyecto .moviola, los recientes y los errores, sin ventana.

Uso:  python -I pruebas/prueba_guardado.py

La prueba mas fuerte es la de ida y vuelta: un proyecto editado (cortes, velocidad, efectos, subtitulos, musica) se guarda, se abre
en OTRA instancia del programa y se EXPORTA; el archivo tiene que ser el mismo, cuadro por cuadro.
"""

import json
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-guardado-"), "ajustes.json")

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
import prueba_imagen as im  # noqa: E402
from motor import exportar  # noqa: E402

ok = ex.ok


def nueva_api():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-guardado-cache-"), "cache")
    app.crear_servidor(api)
    return api


def foto(p):
    """El proyecto sin lo que cambia de una sesion a otra (direcciones locales, historial)."""
    d = p.a_dict()
    for f in d["fuentes"].values():
        f.pop("url", None)
    d.pop("puede_deshacer", None)
    d.pop("puede_rehacer", None)
    return json.dumps(d, sort_keys=True)


def main():
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=6)
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 8, 700)
    carpeta = tempfile.mkdtemp(prefix="prueba-guardado-carpeta-")
    api = nueva_api()

    print("=== 1. guardar ===")
    r = api.abrir(src)
    ok(not r.get("error") and r["proyecto"]["archivo_proyecto"] == "" and r["proyecto"]["sin_guardar"] is False, "un video recien abierto no tiene proyecto ni cambios", str(r.get("error")))
    r = api._editar("dividir", 3.0)
    ok(r["proyecto"]["sin_guardar"] is True, "despues de editar, el proyecto figura sin guardar")
    api._editar("agregar_efecto", api.proyecto.pista("V1")["clips"][0]["id"], "color_basico", {"brillo": 0.2})
    api._editar("velocidad", api.proyecto.pista("V1")["clips"][1]["grupo"], 1.5)
    api.agregar_audio(musica, 0.0)
    api.proyecto.subtitulo_agregar(0.5, 1.5, "Hola guardado")
    api.proyecto.subtitulos_estilo({"color": "coral"})
    api._editar("ducking", "A2", True, 9)
    ruta_p = os.path.join(carpeta, "mi montaje.moviola")
    r = api._guardar_en(ruta_p)
    ok(not r.get("error") and r["ruta"] == ruta_p and os.path.isfile(ruta_p) and r["proyecto"]["sin_guardar"] is False and r["proyecto"]["archivo_proyecto"] == "mi montaje.moviola",
       "Guardar escribe el archivo, queda al dia y el proyecto sabe como se llama", str(r.get("error")))
    ok(not os.path.exists(ruta_p + ".tmp"), "no queda un .tmp a medias")
    crudo = json.load(open(ruta_p, encoding="utf-8"))
    ok(all("url" not in f for f in crudo["fuentes"].values()) and "subtitulos_desactualizados" not in crudo and "tiempos" not in next(iter(crudo["fuentes"].values())),
       "el archivo no guarda las direcciones locales ni las tablas enormes de cuadros")
    r = api._guardar_en(os.path.join(carpeta, "otro"))
    ok(r["ruta"].endswith(".moviola") and os.path.isfile(r["ruta"]), "si el nombre no trae la extension, se la pone")
    api._guardar_en(ruta_p)
    r = api.guardar_proyecto()
    ok(r.get("ruta") == ruta_p and not r.get("error"), "Guardar (sin elegir) vuelve a escribir en el mismo archivo")
    api._editar("deshacer")
    ok(api._proyecto_dict()["sin_guardar"] is True, "y deshacer tambien cuenta como cambio")
    api._editar("rehacer")
    r = api._guardar_en(os.path.join(carpeta, "no_existe", "x.moviola"))
    ok("no existe" in r.get("error", ""), "guardar en una carpeta que no existe: error claro", r.get("error"))
    r = nueva_api().guardar_proyecto()
    ok("nada abierto" in r.get("error", ""), "guardar sin nada abierto: error claro", r.get("error"))
    antes = foto(api.proyecto)

    print("=== 2. abrir en otra sesion y comparar ===")
    api2 = nueva_api()
    r = api2.abrir(ruta_p)                       # abrir() reconoce la extension
    ok(not r.get("error"), "abrir() con un .moviola abre el proyecto", str(r.get("error")))
    ok(r["proyecto"]["archivo_proyecto"] == "mi montaje.moviola" and r["proyecto"]["sin_guardar"] is False and r["nombre"] == "src.mp4" and r.get("tira"),
       "arma el visor con el video principal y marca el proyecto como al dia")
    da, db = json.loads(antes), json.loads(foto(api2.proyecto))
    difs = [(k, json.dumps(da[k])[:160], json.dumps(db.get(k))[:160]) for k in da if da[k] != db.get(k)]
    ok(not difs, "el proyecto abierto es IDENTICO al que se guardo (clips, efectos, velocidad, subtitulos, musica, ducking)", str(difs))
    ok(api2.proyecto.puede_deshacer() is False and api2.proyecto.validar() == [], "empieza sin historial de deshacer y valido")
    f2 = [f for f in api2.proyecto.fuentes.values() if f["tipo"] == "audio"]
    ok(len(f2) == 1 and f2[0].get("url", "").startswith("http://127.0.0.1:"), "el audio extra vuelve a tener una direccion local de ESTA sesion", str(f2[0].get("url") if f2 else None))
    ok(api2.picos_fuentes.get(next(k for k, f in api2.proyecto.fuentes.items() if f["tipo"] == "audio")), "y su espectro")
    api2._editar("dividir", 1.0)
    ok(api2._proyecto_dict()["sin_guardar"] is True, "seguir editando lo vuelve a marcar sin guardar")

    print("=== 3. ida y vuelta exportando ===")
    a1, _ = im.exportar(api.proyecto, "g_original", subtitulos={"quemar": True})
    api3 = nueva_api()
    api3.abrir(ruta_p)
    a2, _ = im.exportar(api3.proyecto, "g_abierto", subtitulos={"quemar": True})
    c1, c2 = im.todos_los_cuadros(a1), im.todos_los_cuadros(a2)
    ok(len(c1) == len(c2) and len(c1) > 100 and max(im.dif_media(x, y) for x, y in zip(c1[::7], c2[::7])) < 0.01, "el video exportado del proyecto abierto es el mismo, cuadro por cuadro", f"{len(c1)} / {len(c2)} cuadros")
    m1, m2 = ex.muestras(a1), ex.muestras(a2)
    ok(len(m1) == len(m2) and abs(ex.rms(m1, 0, 3) - ex.rms(m2, 0, 3)) < 1e-4, "y el audio (con la musica y el ducking)")

    print("=== 4. archivos que faltan, movidos y errores ===")
    antes_api2 = foto(api2.proyecto)

    def con_rutas_en(destino, ruta_json):
        """Una copia del proyecto cuyas fuentes apuntan a `destino` (una carpeta donde NO estan)."""
        d = json.load(open(ruta_p, encoding="utf-8"))
        for f in d["fuentes"].values():
            f["ruta"] = os.path.join(destino, os.path.basename(f["ruta"]))
        json.dump(d, open(ruta_json, "w", encoding="utf-8"))
        return ruta_json

    p_falta = con_rutas_en(os.path.join(carpeta, "ya_no_estan"), os.path.join(carpeta, "faltan.moviola"))
    r = nueva_api().abrir(p_falta)
    ok("src.mp4" in r.get("error", "") and "musica.mp3" in r.get("error", "") and "Faltan" in r["error"], "si faltan archivos del proyecto: dice cuales", r.get("error"))
    r = api2.abrir(p_falta)
    ok(r.get("error") and foto(api2.proyecto) == antes_api2, "y no toca el proyecto que ya estaba abierto")
    movida = os.path.join(carpeta, "carpeta_movida")
    os.makedirs(movida)
    shutil.copy(src, os.path.join(movida, "src.mp4"))
    shutil.copy(musica, os.path.join(movida, "musica.mp3"))
    p_mov = con_rutas_en(os.path.join(carpeta, "ya_no_estan"), os.path.join(movida, "mi montaje.moviola"))
    r = nueva_api().abrir(p_mov)
    ok(not r.get("error") and os.path.dirname(r["ruta"]) == movida, "si los archivos estan JUNTO al proyecto (se movio la carpeta entera), los encuentra ahi", str(r.get("error")))
    for malo, contenido in (("un archivo que no es JSON", "esto no es un proyecto"), ("un JSON de otra cosa", json.dumps({"hola": 1})),
                            ("un proyecto de otra version", json.dumps({"version": 99, "fuentes": {}, "pistas": []})),
                            ("un proyecto sin fuentes", json.dumps({"version": 1, "fuentes": {}, "pistas": [], "n": {}}))):
        ruta_malo = os.path.join(carpeta, "malo.moviola")
        open(ruta_malo, "w", encoding="utf-8").write(contenido)
        r = nueva_api().abrir(ruta_malo)
        ok(r.get("error") and "Traceback" not in r["error"], "abrir " + malo + ": error claro", r.get("error"))
    dañado = json.load(open(ruta_p, encoding="utf-8"))
    dañado["pistas"][0]["clips"][0]["hasta"] = 9999.0          # un clip que se pasa de la fuente
    ruta_d = os.path.join(carpeta, "danado.moviola")
    json.dump(dañado, open(ruta_d, "w", encoding="utf-8"))
    r = nueva_api().abrir(ruta_d)
    ok(r.get("error") and "dañado" in r["error"], "un proyecto con clips imposibles: «está dañado»", r.get("error"))
    ok("no encontré" in nueva_api().abrir(os.path.join(carpeta, "no_hay.moviola"))["error"].lower(), "un proyecto que no existe: error claro")

    print("=== 5. recientes ===")
    api4 = nueva_api()
    api4.abrir(src)
    api4.abrir(ruta_p)
    rec = api4.recientes()["recientes"]
    ok([x["ruta"] for x in rec][:2] == [ruta_p, src] and rec[0]["tipo"] == "proyecto" and rec[1]["tipo"] == "video" and rec[0]["nombre"] == "mi montaje.moviola",
       "los recientes: el ultimo primero, con su tipo y su nombre", str([x["nombre"] for x in rec]))
    api4.abrir(src)
    ok(api4.recientes()["recientes"][0]["ruta"] == src and len([x for x in api4.recientes()["recientes"] if x["ruta"] == src]) == 1, "abrir uno repetido lo sube al primer lugar sin duplicarlo")
    for i in range(14):
        api4._recordar(os.path.join(carpeta, "x%d.moviola" % i), "proyecto")
    ok(len(json.load(open(os.environ["EDITOR_AJUSTES"], encoding="utf-8"))["recientes"]) <= 12 and len(api4.recientes()["recientes"]) <= 8, "se guardan hasta 12 y se muestran 8")
    api4.olvidar_reciente(src)
    ok(all(x["ruta"] != src for x in api4.recientes()["recientes"]), "olvidar uno lo saca de la lista")
    os.replace(ruta_p, ruta_p + ".x")
    ok(all(x["ruta"] != ruta_p for x in api4.recientes()["recientes"]), "un proyecto que ya no existe no aparece en los recientes")
    os.replace(ruta_p + ".x", ruta_p)

    print("=== 6. un audio como principal ===")
    pa = nueva_api()
    ra = pa.abrir(musica)
    pa._editar("dividir", 3.0)
    ruta_a = os.path.join(carpeta, "solo audio.moviola")
    pa._guardar_en(ruta_a)
    pb = nueva_api()
    rb = pb.abrir(ruta_a)
    ok(not rb.get("error") and rb.get("solo_audio") and foto(pb.proyecto) == foto(pa.proyecto), "un proyecto de solo audio se guarda y se abre igual", str(rb.get("error")))

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
