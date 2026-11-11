# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Auditoria automatica de la API local: le tira BASURA a cada operacion y mira que nada se rompa.

Uso:  python -I pruebas/prueba_fuzz_api.py

Para cada metodo que la interfaz puede llamar (editar_*, agregar_*, subtitulos, escenas, descargas, proyectos...) se mandan argumentos
absurdos (None, textos enormes, listas, diccionarios anidados, numeros gigantes, negativos, booleanos, caracteres raros) y se exige:
  1. que el metodo DEVUELVA algo (un diccionario) en vez de explotar con una excepcion;
  2. que el proyecto siga VALIDO (`validar() == []`) despues de cada llamada;
  3. que una llamada que dio error NO haya cambiado el proyecto;
  4. que no quede ningun archivo temporal ni un hilo colgado.
Lo que NO se prueba aca (abre dialogos del sistema): elegir_*, guardar_proyecto_como, mostrar en carpeta.
"""

import copy
import json
import os
import random
import sys
import tempfile
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ["EDITOR_SIN_GPU"] = "1"
TMPA = tempfile.mkdtemp(prefix="prueba-fuzz-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMPA, "ajustes.json")
os.environ["MOVIOLA_YTDLP"] = os.path.join(AQUI, "falso_ytdlp.py")
os.environ["MOVIOLA_DESCARGAS"] = os.path.join(TMPA, "bajados")

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402

ok = ex.ok

# metodos que abren dialogos del sistema o arrancan trabajos largos de verdad: no se fuzzean con basura
SALTEAR = {"elegir_archivo", "elegir_lut", "elegir_carpeta", "elegir_proyecto", "elegir_videos", "guardar_proyecto_como", "mostrar_en_carpeta",
           "descarga_mostrar", "latido", "exportar_iniciar", "transcribir_iniciar", "descargar_iniciar", "gpu_comprobar", "gpu_modo",
           "abrir", "abrir_proyecto", "abrir_recuperacion", "agregar_audio", "agregar_medio", "inicial"}


def basura(azar):
    candidatos = [None, True, False, 0, 1, -1, 2 ** 31, 2 ** 63, -2 ** 63, 1e308, -1e308, 1e-300, 0.5, 3.0, "", "x", "s1", "s2", "c1", "g1", "A1", "V1", "A9",
                  "a" * 5000, "\x00", "ñandú ¿?", "<script>alert(1)</script>", "../../etc/passwd", "C:\\Windows\\System32", "%s%s%s", "{}", "null", [], [1, 2], ["a"], [[1, 2]],
                  [None], {"a": 1}, {"inicio": 1, "fin": 2, "texto": "x"}, {"color": "rojo"}, {"texto": "x" * 500}, {"brillo": 9}, {"brillo": "alto"}, [{"inicio": "a"}],
                  [[0, 1], [2, 3]], [[3, 1]], [[-1, 5]], list(range(300)), {"a": {"b": {"c": [1, 2, 3]}}}, "color_basico", "texto", "superponer", "zoom_lento"]
    return azar.choice(candidatos)


def tiene_dialogo(nombre):
    return nombre in SALTEAR


def main():
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=6)
    otro = ex.crear_fuente(os.path.join(ex.TMP, "otro.mp4"), dur=3, w=320, h=180, fps=25)
    musica = ex.crear_musica(os.path.join(ex.TMP, "musica.mp3"), 4, 700)
    api = app.API()
    api.cache = os.path.join(TMPA, "cache")
    app.crear_servidor(api)
    api.abrir(src)
    api.agregar_medio(otro)
    api.agregar_audio(musica, 0.0)
    api.proyecto.subtitulo_agregar(0.5, 1.5, "hola")
    api._guardar_en(os.path.join(TMPA, "fuzz.moviola"))        # con archivo de proyecto, guardar_proyecto() no abre ningun dialogo
    metodos = api.metodos()
    nombres = sorted(n for n in metodos if n not in SALTEAR)
    print("      metodos que se fuzzean:", len(nombres), flush=True)
    hilos_antes = {t.ident for t in threading.enumerate()}

    # ------------------------------------------------------------------ 1. basura a todo
    print("=== 1. argumentos absurdos a cada metodo ===")
    malos = []
    llamadas = 0
    for semilla in range(6):
        azar = random.Random(semilla)
        print("      vuelta", semilla, flush=True)
        for nombre in nombres:
            lentos = nombre in ("analizar_silencios", "analizar_escenas", "medir_volumen", "medio_info", "picos_fuente", "cuadro", "transcribir_estado")
            for _ in range(2 if lentos else 14):
                args = [basura(azar) for _ in range(azar.randint(0, 4))]
                try:
                    json.dumps(args, allow_nan=False)
                except (ValueError, TypeError):
                    continue
                if os.environ.get("FUZZ_VERBOSO"):
                    print("        ->", nombre, str(args)[:70], flush=True)
                antes = copy.deepcopy(api.proyecto.a_dict()["pistas"]) if api.proyecto else None
                try:
                    r = metodos[nombre](*args)
                except TypeError as e:
                    # la cantidad de argumentos que no coincide es un error del que llama (el servidor lo responde 400/500): no cuenta
                    if "positional argument" in str(e) or "required" in str(e) or "takes" in str(e):
                        continue
                    malos.append((nombre, args, "TypeError " + str(e)[:80]))
                    continue
                except Exception as e:
                    malos.append((nombre, str(args)[:60], type(e).__name__ + ": " + str(e)[:80]))
                    continue
                llamadas += 1
                if not (r is None or isinstance(r, (dict, list))):
                    malos.append((nombre, str(args)[:60], "devolvio " + type(r).__name__))
                if api.proyecto is not None:
                    problemas = api.proyecto.validar()
                    if problemas:
                        malos.append((nombre, str(args)[:60], "proyecto invalido: " + problemas[0]))
                        api.proyecto.deshacer() if api.proyecto.puede_deshacer() else None
                    if isinstance(r, dict) and r.get("error") and nombre.startswith("editar_"):
                        despues = api.proyecto.a_dict()["pistas"]
                        if despues != antes:
                            malos.append((nombre, str(args)[:60], "un error dejo el proyecto cambiado"))
    ok(not malos, "%d llamadas con basura: ninguna explota, el proyecto queda valido y un error no lo cambia" % llamadas, str(malos[:4]))
    if malos:
        for m in malos[:12]:
            print("      ", m)

    # ------------------------------------------------------------------ 2. el servidor, de verdad, con JSON basura
    print("=== 2. por HTTP, con cuerpos raros ===")
    import http.client
    srv = api.servidor
    base_ruta = "/%s/api/" % srv.token

    def pedir(metodo, cuerpo, tipo="application/json", host=None):
        c = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=20)
        c.putrequest("POST", base_ruta + metodo, skip_host=True)
        c.putheader("Host", host or "127.0.0.1:%d" % srv.puerto)
        c.putheader("Content-Type", tipo)
        c.putheader("Content-Length", str(len(cuerpo)))
        c.endheaders(cuerpo)
        r = c.getresponse()
        r.read()
        s = r.status
        c.close()
        return s

    for etiqueta, cuerpo, esperado in (("un JSON que no es lista", b'{"a":1}', 400), ("JSON roto", b"[1,2", 400), ("NaN", b"[NaN]", 400), ("Infinity", b"[Infinity]", 400),
                                       ("vacio (sin argumentos)", b"", None), ("anidado hasta el infinito", b"[" * 3000 + b"]" * 3000, None), ("no UTF-8", b"\xff\xfe\x00", 400)):
        try:
            s = pedir("proyecto_estado", cuerpo)
        except Exception as e:
            s = "excepcion " + type(e).__name__
        bien = (s == esperado) if esperado else (isinstance(s, int) and s < 600 and s != 500 or s == 400 or s == 200)
        ok(bien, "cuerpo " + etiqueta + " -> " + str(s))
    ok(pedir("proyecto_estado", b"[]", "text/plain") == 415, "un Content-Type que no es JSON se rechaza (415)")
    ok(pedir("proyecto_estado", b"[]", host="evil.com") == 421, "un Host raro se rechaza (421: DNS rebinding)")
    ok(pedir("no_existe_este_metodo", b"[]") == 404, "un metodo que no existe da 404")
    ok(pedir("__init__", b"[]") == 404 and pedir("metodos", b"[]") == 404 and pedir("_editar", b"[]") == 404, "los metodos internos no estan publicados")
    estado_http = api.proyecto.a_dict()["pistas"]
    ok(api.proyecto.validar() == [], "despues de todo eso el proyecto sigue valido")

    # ------------------------------------------------------------------ 3. basura a las operaciones del modelo, mezclada, sin dialogos
    print("=== 3. secuencias mezcladas de operaciones validas y absurdas ===")
    azar = random.Random(99)
    operaciones = [n for n in nombres if n.startswith("editar_")]
    validos = {"editar_dividir": lambda: [azar.uniform(0, 6)], "editar_deshacer": lambda: [], "editar_rehacer": lambda: [],
               "editar_insertar_fuente": lambda: ["s2", azar.choice([None, azar.uniform(0, 8)])], "editar_borrar_rango": lambda: sorted([azar.uniform(0, 5), azar.uniform(0, 5)])}
    malos = []
    for paso in range(400):
        nombre = azar.choice(operaciones)
        args = validos[nombre]() if (nombre in validos and azar.random() < 0.6) else [basura(azar) for _ in range(azar.randint(0, 3))]
        try:
            json.dumps(args, allow_nan=False)
        except (ValueError, TypeError):
            continue
        try:
            r = metodos[nombre](*args)
        except TypeError as e:
            if "positional argument" in str(e) or "required" in str(e):
                continue
            malos.append((nombre, str(args)[:50], "TypeError"))
            continue
        except Exception as e:
            malos.append((nombre, str(args)[:50], type(e).__name__ + str(e)[:60]))
            continue
        if api.proyecto.validar():
            malos.append((nombre, str(args)[:50], api.proyecto.validar()[0]))
            break
    ok(not malos, "400 operaciones mezcladas (validas y absurdas): nada explota y el proyecto siempre es valido", str(malos[:4]))

    # ------------------------------------------------------------------ 3b. archivos de proyecto danados
    print("=== 3b. proyectos guardados con partes rotas ===")
    ruta_buena = os.path.join(TMPA, "bueno.moviola")
    api._guardar_en(ruta_buena)
    crudo = json.load(open(ruta_buena, encoding="utf-8"))
    azar = random.Random(7)

    def rutas_de(o, base=()):
        if isinstance(o, dict):
            for k, v in o.items():
                yield base + (k,)
                yield from rutas_de(v, base + (k,))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield base + (i,)
                yield from rutas_de(v, base + (i,))

    todas = list(rutas_de(crudo))
    malos, abiertos, rechazados = [], 0, 0
    for i in range(120):
        d = copy.deepcopy(crudo)
        for _ in range(azar.randint(1, 3)):
            ruta = azar.choice(todas)
            try:
                padre = d
                for k in ruta[:-1]:
                    padre = padre[k]
                modo = azar.choice(["borrar", "nulo", "texto", "lista", "numero", "negativo"])
                if modo == "borrar":
                    del padre[ruta[-1]]
                else:
                    padre[ruta[-1]] = {"nulo": None, "texto": "x", "lista": [1], "numero": 1e9, "negativo": -5}[modo]
            except (KeyError, IndexError, TypeError):
                continue
        malo = os.path.join(TMPA, "roto%d.moviola" % i)
        json.dump(d, open(malo, "w", encoding="utf-8"))
        antes_video, antes_ruta, antes_proy = api.video, api.ruta, api.proyecto
        try:
            r = api.abrir(malo)
        except Exception as e:
            malos.append((i, "excepcion " + type(e).__name__ + ": " + str(e)[:80]))
            continue
        if not isinstance(r, dict):
            malos.append((i, "no devolvio un diccionario"))
        elif r.get("error"):
            rechazados += 1
            if api.video is not antes_video or api.ruta != antes_ruta or api.proyecto is not antes_proy:
                malos.append((i, "un proyecto roto cambio lo que estaba abierto: " + r["error"][:60]))
        else:
            abiertos += 1
            if api.proyecto.validar():
                malos.append((i, "abrio un proyecto invalido: " + api.proyecto.validar()[0]))
            api.abrir(src)                                 # se vuelve a lo conocido
            api.agregar_medio(otro)
            api.agregar_audio(musica, 0.0)
    ok(not malos, "120 proyectos con partes borradas o cambiadas: nunca explotan, un rechazo no toca lo abierto y uno aceptado es valido (%d abiertos, %d rechazados)" % (abiertos, rechazados), str(malos[:4]))

    # ------------------------------------------------------------------ 4. limpieza
    print("=== 4. sin restos ===")
    api.cerrar()
    import glob
    restos = glob.glob(os.path.join(tempfile.gettempdir(), "moviola-export-*")) + glob.glob(os.path.join(tempfile.gettempdir(), "moviola-voz-*"))
    ok(not restos, "no quedan carpetas temporales de exportar ni de transcribir", str(restos[:3]))
    colgados = [t for t in threading.enumerate() if t.ident not in hilos_antes and t.is_alive() and not t.daemon]
    ok(not colgados, "no queda ningun hilo no-daemon colgado", str([t.name for t in colgados]))

    print()
    print("TODO BIEN" if not ex.fallos else f"FALLARON {len(ex.fallos)}: " + ", ".join(ex.fallos))
    return 1 if ex.fallos else 0


if __name__ == "__main__":
    sys.exit(main())
