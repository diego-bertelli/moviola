# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Procesar videos SIN ventana: presets («Reel en un clic») y lotes de archivos.

Un preset es una receta: cortar silencios, transcribir y subtitular, normalizar el volumen y exportar en un formato.
`procesar()` la aplica a UN archivo (video, audio o proyecto .moviola) y `procesar_lote()` a muchos, uno atrás de otro,
sin que un archivo con problemas detenga a los demás. Lo usan la interfaz (diálogo «Preparar con un preset») y la línea
de comandos (`moviola.py`). Nada de acá abre ventanas ni usa internet.

Si falta una herramienta que una receta pide (whisper para transcribir), el paso se SALTEA y queda dicho en `avisos`:
un preset con subtítulos no tiene que fallar entero en una PC sin whisper.
"""

import copy
import glob
import json
import os
import threading

from motor import exportar as _ex
from motor import proxy as _proxy
from motor import silencios as _sil
from motor import subtitulos as _sub
from motor.proyecto import ErrorEdicion, Proyecto
from motor.video import SinVideo, Video

EXT_VIDEO = "mp4 mov m4v mkv avi webm mpg mpeg ts mts m2ts wmv flv 3gp mxf ogv vob asf divx".split()
EXT_AUDIO = "mp3 wav flac m4a aac ogg oga opus wma aiff aif ac3 amr mka".split()
EXT_MEDIOS = tuple("." + e for e in EXT_VIDEO + EXT_AUDIO)
EXT_PROYECTO = ".moviola"
CARPETA_SALIDA = "moviola-salida"
ENTRADAS_MAX = 500


class ErrorLote(ValueError):
    """Algo que no se puede procesar; el mensaje se le muestra a la persona."""


# --------------------------------------------------------------------------------------------- recetas

SILENCIOS = {"umbral_db": -35.0, "duracion_min": 0.5, "margen": 0.1}

PRESETS = {
    "reel": {
        "nombre": "Reel vertical",
        "nota": "9:16 para Instagram, TikTok y Shorts: corta los silencios, pone subtítulos grandes, nivela el volumen (-14 LUFS).",
        "silencios": {"umbral_db": -35.0, "duracion_min": 0.4, "margen": 0.08},
        "subtitulos": {"idioma": "es", "letras": 24, "quemar": True, "srt": False, "vtt": False, "karaoke": False,
                       "estilo": {"tamano": 7.0, "posicion": "centro", "mayusculas": True, "contorno": True, "caja": False}},
        "normalizar": True, "formato": "vertical", "encuadre": "recortar", "perfil": "mp4_h264", "calidad": "alta"},
    "youtube": {
        "nombre": "YouTube horizontal",
        "nota": "16:9 con el volumen nivelado y un archivo .srt al lado (sin quemar), para subirlo como subtítulos de YouTube.",
        "silencios": None,
        "subtitulos": {"idioma": "es", "letras": 42, "quemar": False, "srt": True, "vtt": False, "karaoke": False, "estilo": {}},
        "normalizar": True, "formato": "horizontal", "encuadre": "recortar", "perfil": "mp4_h264", "calidad": "alta"},
    "podcast": {
        "nombre": "Podcast (solo audio)",
        "nota": "Un MP3 con los silencios largos cortados y el volumen nivelado.",
        "silencios": {"umbral_db": -38.0, "duracion_min": 0.8, "margen": 0.2},
        "subtitulos": None,
        "normalizar": True, "formato": "mp3", "encuadre": "recortar", "perfil": "mp4_h264", "calidad": "alta"},
    "whatsapp": {
        "nombre": "WhatsApp liviano",
        "nota": "Mismo tamaño que el original pero liviano, con el volumen nivelado: para mandar por mensaje.",
        "silencios": None, "subtitulos": None,
        "normalizar": True, "formato": "original", "encuadre": "recortar", "perfil": "mp4_h264", "calidad": "liviana"},
    "clase": {
        "nombre": "Clase o charla",
        "nota": "Horizontal, sin silencios largos y con subtítulos quemados abajo: para material de formación.",
        "silencios": {"umbral_db": -38.0, "duracion_min": 1.0, "margen": 0.25},
        "subtitulos": {"idioma": "es", "letras": 42, "quemar": True, "srt": True, "vtt": False, "karaoke": False,
                       "estilo": {"tamano": 5.0, "posicion": "abajo", "caja": True}},
        "normalizar": True, "formato": "horizontal", "encuadre": "recortar", "perfil": "mp4_h264", "calidad": "equilibrada"},
}

# Lo que se puede cambiar de un preset (desde la línea de comandos o la interfaz) sin escribir uno nuevo.
CAMBIOS = ("silencios", "subtitulos", "normalizar", "formato", "encuadre", "perfil", "calidad", "idioma", "karaoke")


def lista_presets():
    """Los presets para mostrar en pantalla: clave, nombre, nota y los pasos que hacen."""
    out = []
    for k, v in PRESETS.items():
        pasos = []
        if v["silencios"]:
            pasos.append("corta silencios")
        if v["subtitulos"]:
            s = v["subtitulos"]
            pasos.append("subtítulos " + "+".join(x for x, y in (("quemados", s["quemar"]), ("srt", s["srt"]), ("vtt", s["vtt"])) if y))
        if v["normalizar"]:
            pasos.append("nivela el volumen")
        pasos.append("exporta " + (v["formato"] if v["formato"] in _ex.FORMATOS_AUDIO else v["formato"] + " " + _ex.PERFILES[v["perfil"]]["nombre"]))
        s = v["subtitulos"]
        out.append({"clave": k, "nombre": v["nombre"], "nota": v["nota"], "pasos": pasos, "solo_audio": v["formato"] in _ex.FORMATOS_AUDIO,
                    "ajustes": {"silencios": bool(v["silencios"]), "subtitulos": bool(s), "karaoke": bool(s and s.get("karaoke")),
                                "normalizar": bool(v["normalizar"]), "idioma": s["idioma"] if s else "es"}})
    return out


def preparar_preset(clave, cambios=None):
    """La receta `clave` con los `cambios` encima, ya validada. Devuelve un dict nuevo (los presets de fábrica no se tocan)."""
    if clave not in PRESETS:
        raise ErrorLote("Ese preset no existe. Los hay: %s." % ", ".join(PRESETS))
    r = copy.deepcopy(PRESETS[clave])
    r["clave"] = clave
    cambios = dict(cambios or {})
    desconocidos = [k for k in cambios if k not in CAMBIOS]
    if desconocidos:
        raise ErrorLote("No se puede cambiar eso del preset: %s." % ", ".join(desconocidos))
    if "silencios" in cambios:
        v = cambios["silencios"]
        if v is False or v is None:
            r["silencios"] = None
        elif v is True:
            r["silencios"] = r["silencios"] or dict(SILENCIOS)
        elif isinstance(v, dict):
            r["silencios"] = dict(r["silencios"] or SILENCIOS, **v)
        else:
            raise ErrorLote("«silencios» es sí, no o un conjunto de ajustes.")
    if "subtitulos" in cambios:
        v = cambios["subtitulos"]
        if v is False or v is None:
            r["subtitulos"] = None
        elif v is True:
            r["subtitulos"] = r["subtitulos"] or {"idioma": "es", "letras": 32, "quemar": True, "srt": False, "vtt": False, "karaoke": False, "estilo": {}}
        elif isinstance(v, dict):
            base = r["subtitulos"] or {"idioma": "es", "letras": 32, "quemar": True, "srt": False, "vtt": False, "karaoke": False, "estilo": {}}
            r["subtitulos"] = dict(base, **v)
        else:
            raise ErrorLote("«subtitulos» es sí, no o un conjunto de ajustes.")
    if "idioma" in cambios and r["subtitulos"]:
        r["subtitulos"]["idioma"] = cambios["idioma"]
    if "karaoke" in cambios and r["subtitulos"]:
        r["subtitulos"]["karaoke"] = bool(cambios["karaoke"])
    for k in ("normalizar",):
        if k in cambios:
            if not isinstance(cambios[k], bool):
                raise ErrorLote("«%s» es sí o no." % k)
            r[k] = cambios[k]
    for k in ("formato", "encuadre", "perfil", "calidad"):
        if k in cambios:
            r[k] = cambios[k]
    _validar_receta(r)
    return r


def _validar_receta(r):
    if r["formato"] not in _ex.FORMATOS_VIDEO and r["formato"] not in _ex.FORMATOS_AUDIO:
        raise ErrorLote("Ese formato no existe: %s." % r["formato"])
    if r["encuadre"] not in ("recortar", "barras"):
        raise ErrorLote("El encuadre es «recortar» o «barras».")
    if r["perfil"] not in _ex.PERFILES:
        raise ErrorLote("Ese tipo de archivo no existe: %s." % r["perfil"])
    if r["calidad"] not in _ex.CALIDADES:
        raise ErrorLote("La calidad es alta, equilibrada o liviana.")
    if r["silencios"] is not None:
        s = r["silencios"]
        for k, (lo, hi) in (("umbral_db", _sil.UMBRAL_DB), ("duracion_min", _sil.DURACION_MIN), ("margen", _sil.MARGEN)):
            v = s.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ErrorLote("En los silencios, «%s» va de %s a %s." % (k, lo, hi))
    if r["subtitulos"] is not None:
        s = r["subtitulos"]
        if s.get("idioma") not in [k for k, _ in _sub.IDIOMAS]:
            raise ErrorLote("Ese idioma no está en la lista: %s." % s.get("idioma"))
        lo, hi = _sub.LETRAS
        if isinstance(s.get("letras"), bool) or not isinstance(s.get("letras"), (int, float)) or not lo <= s["letras"] <= hi:
            raise ErrorLote("Las letras por frase van de %d a %d." % (lo, hi))
        if not isinstance(s.get("estilo"), dict):
            raise ErrorLote("El estilo de los subtítulos es un conjunto de ajustes.")
        try:
            _sub.limpiar_estilo(s["estilo"])
        except _sub.ErrorSubtitulo as e:
            raise ErrorLote(str(e))
        if not (s.get("quemar") or s.get("srt") or s.get("vtt")):
            raise ErrorLote("Los subtítulos tienen que quemarse o escribirse en un archivo .srt o .vtt.")
    if r["formato"] in _ex.FORMATOS_AUDIO and r["subtitulos"] and r["subtitulos"].get("quemar") and not (r["subtitulos"].get("srt") or r["subtitulos"].get("vtt")):
        r["subtitulos"] = None          # no hay imagen donde quemarlos: en audio no se pide


# --------------------------------------------------------------------------------------------- abrir sin ventana

def _datos_audio(ruta):
    import av
    with av.open(ruta, options={"protocol_whitelist": "file"}) as c:
        pistas = list(c.streams.audio)
        if not pistas:
            raise ErrorLote("El archivo no tiene ni video ni audio que se pueda leer.")
        p = pistas[0]
        dur = float(c.duration) / av.time_base if c.duration else (float(p.duration * p.time_base) if p.duration is not None and p.time_base else 0.0)
        if dur <= 0:
            raise ErrorLote("El archivo no tiene duración.")
        return {"duracion": dur, "pistas": len(pistas), "codec": (p.codec_context.name or "").lower()}


def proyecto_desde(origen):
    """Un Proyecto listo para trabajar, hecho de un video, un audio o un archivo .moviola. Levanta ErrorLote si no se puede."""
    origen = os.path.abspath(str(origen))
    if not os.path.isfile(origen):
        raise ErrorLote("No encontré el archivo: %s" % origen)
    if origen.lower().endswith(EXT_PROYECTO):
        return _abrir_moviola(origen)
    try:
        with Video(origen) as v:
            info = dict(v.info())
            tabla = v.tabla_tiempos()
        p = Proyecto()
        fid = p.agregar_fuente(origen, "video", info["duracion"], tabla, info.get("pistas_audio", 0), inicio=info["inicio"], ancho=info["ancho"],
                               alto=info["alto"], fps=info["fps"], vfr=bool(info.get("vfr")), rotacion=info.get("rotacion", 0))
    except SinVideo:
        d = _datos_audio(origen)
        p = Proyecto()
        fid = p.agregar_fuente(origen, "audio", d["duracion"], None, d["pistas"], codec=d["codec"], web_compatible=False)
    except ErrorLote:
        raise
    except Exception as e:
        raise ErrorLote("No pude abrir %s: %s" % (os.path.basename(origen), _mensaje(e)))
    p.nuevo_desde_fuente(fid)
    return p


def _abrir_moviola(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError) as e:
        raise ErrorLote("No pude leer el proyecto: %s" % _mensaje(e))
    if not isinstance(datos, dict) or datos.get("version") != 1 or not isinstance(datos.get("fuentes"), dict) or not datos["fuentes"]:
        raise ErrorLote("Ese archivo no es un proyecto de Moviola (o es de otra versión del programa).")
    faltan = []
    for f in datos["fuentes"].values():
        if not isinstance(f, dict) or not isinstance(f.get("ruta"), str):
            raise ErrorLote("El proyecto está dañado y no se puede abrir.")
        if not os.path.isfile(f["ruta"]):
            al_lado = os.path.join(os.path.dirname(ruta), os.path.basename(f["ruta"]))
            if os.path.isfile(al_lado):
                f["ruta"] = al_lado
            else:
                faltan.append(os.path.basename(f["ruta"]))
        f["ruta"] = os.path.abspath(f["ruta"])
    if faltan:
        raise ErrorLote("Faltan estos archivos del proyecto: %s." % ", ".join(faltan[:6]))

    def tiempos_de(f):
        with Video(f["ruta"]) as v:
            return v.tabla_tiempos()
    try:
        p = Proyecto.cargar_dict(datos, tiempos_de)
        if p.validar():
            raise ErrorLote("El proyecto guardado está dañado y no se puede abrir.")
    except ErrorLote:
        raise
    except Exception as e:
        raise ErrorLote("El proyecto guardado está dañado y no se puede abrir. %s" % _mensaje(e))
    return p


def _mensaje(e):
    return str(e) if isinstance(e, (ValueError, ErrorEdicion)) else "%s: %s" % (type(e).__name__, e)


# --------------------------------------------------------------------------------------------- procesar

def _aviso_paso(avisar, paso, texto):
    if avisar:
        avisar(paso, texto)


def procesar(origen, carpeta, receta, nombre=None, al_progresar=None, cancelar=None, avisar=None, codificador=None, proyecto=None):
    """Aplica la receta `receta` (de `preparar_preset`) a `origen` y exporta a `carpeta`.

    Devuelve {archivo, duracion, pasos: [{paso, detalle}], avisos: [...], silencios_quitados, frases, origen, ...resultado de exportar}.
    al_progresar(fraccion) va de 0 a 1 sobre todo el trabajo; avisar(paso, texto) cuenta en qué paso va.
    `proyecto`: un Proyecto ya armado (en vez de abrir `origen`; lo usa la interfaz). Se modifica: pasá una copia.
    """
    if cancelar is None:
        cancelar = threading.Event()
    es_audio = receta["formato"] in _ex.FORMATOS_AUDIO
    quiere_silencios = receta["silencios"] is not None
    quiere_subs = receta["subtitulos"] is not None
    pesos = {"abrir": 4, "silencios": 12 if quiere_silencios else 0, "transcribir": 50 if quiere_subs else 0, "exportar": 34}
    total = float(sum(pesos.values()))
    hecho = [0.0]

    def tramo(paso):
        base = hecho[0]
        peso = pesos[paso] / total

        def f(x):
            if al_progresar:
                al_progresar(min(1.0, base + peso * max(0.0, min(1.0, x))))
        return f, peso

    pasos = []

    def cerrar(paso, detalle=""):
        hecho[0] += pesos[paso] / total
        pasos.append({"paso": paso, "detalle": detalle})
        if al_progresar:
            al_progresar(min(1.0, hecho[0]))

    def revisar():
        if cancelar.is_set():
            raise _proxy.Cancelado()

    _aviso_paso(avisar, "abrir", "Abriendo %s" % os.path.basename(str(origen)))
    p = proyecto if proyecto is not None else proyecto_desde(origen)
    revisar()
    avisos = []
    if not es_audio and not any(t["tipo"] == "video" and t["clips"] for t in p.pistas):
        # un audio (o un proyecto sin video) con una receta de video: no hay imagen que exportar, se hace el audio
        receta = dict(receta, formato="mp3")
        es_audio = True
        pesos["exportar"] = 34
        avisos.append("Es solo audio: se exportó como MP3 en vez de video.")
        if receta["subtitulos"] and receta["subtitulos"].get("quemar") and not (receta["subtitulos"].get("srt") or receta["subtitulos"].get("vtt")):
            receta["subtitulos"] = dict(receta["subtitulos"], srt=True)
    cerrar("abrir", "%.1f s" % p.duracion())

    quitados = 0.0
    if quiere_silencios:
        _aviso_paso(avisar, "silencios", "Buscando silencios")
        f, _ = tramo("silencios")
        s = receta["silencios"]
        try:
            r = _sil.analizar(p, s["umbral_db"], s["duracion_min"], s["margen"], cancelar)
            f(0.8)
            if r["silencios"]:
                p.borrar_rangos([(x["inicio"], x["fin"]) for x in r["silencios"]])
                quitados = r["total"]
            cerrar("silencios", "%d tramos, %.1f s" % (len(r["silencios"]), quitados))
        except _sil.ErrorSilencio as e:
            avisos.append("No se cortaron silencios: %s" % e)
            cerrar("silencios", "salteado")
        except ErrorEdicion as e:
            avisos.append("No se cortaron silencios: %s" % e)
            cerrar("silencios", "salteado")
        revisar()

    frases = 0
    subs = None
    if quiere_subs:
        s = receta["subtitulos"]
        _aviso_paso(avisar, "transcribir", "Transcribiendo el audio")
        f, _ = tramo("transcribir")
        est = _sub.estado_transcripcion()
        if not est["disponible"]:
            avisos.append("No se pusieron subtítulos: " + est["motivo"])
            cerrar("transcribir", "salteado")
        else:
            try:
                r = _sub.transcribir_completo(p, s["idioma"], s["letras"], cancelar, f)
                lista = r["frases"]
                if lista:
                    p.subtitulos_poner(lista, r["palabras"])
                    p.subtitulos_estilo(dict(s["estilo"], karaoke=bool(s.get("karaoke"))))
                    frases = len(lista)
                    subs = {"quemar": bool(s["quemar"]) and not es_audio, "srt": bool(s["srt"]), "vtt": bool(s["vtt"])}
                else:
                    avisos.append("No se pusieron subtítulos: no encontré voz para transcribir.")
                cerrar("transcribir", "%d frases" % frases)
            except _sub.ErrorSubtitulo as e:
                avisos.append("No se pusieron subtítulos: %s" % e)
                cerrar("transcribir", "salteado")
        revisar()

    _aviso_paso(avisar, "exportar", "Exportando")
    f, _ = tramo("exportar")
    r = _ex.exportar(p, carpeta, nombre, receta["formato"], receta["encuadre"], (0.5, 0.5), receta["normalizar"], -14.0, None, codificador, f, cancelar,
                     subtitulos=subs, perfil=receta["perfil"], calidad=receta["calidad"])
    cerrar("exportar", os.path.basename(r["archivo"]))
    salida = dict(r)
    salida.update({"origen": str(origen), "pasos": pasos, "avisos": avisos, "silencios_quitados": round(quitados, 3), "frases": frases, "preset": receta.get("clave", "")})
    return salida


# --------------------------------------------------------------------------------------------- lotes

def listar_entradas(rutas, recursivo=False):
    """Expande lo que escribió la persona (archivos, carpetas, patrones como *.mp4) en una lista de archivos de verdad, sin repetir.
    Una carpeta aporta los videos, audios y proyectos que tiene adentro (con `recursivo`, también los de sus subcarpetas)."""
    if isinstance(rutas, (str, os.PathLike)):
        rutas = [rutas]
    vistos, out = set(), []

    def poner(r):
        k = os.path.normcase(os.path.abspath(r))
        if k not in vistos:
            vistos.add(k)
            out.append(os.path.abspath(r))

    for r in rutas:
        r = str(r)
        if any(c in r for c in "*?[") and not os.path.exists(r):
            for x in sorted(glob.glob(r, recursive=recursivo)):
                if os.path.isfile(x) and x.lower().endswith(EXT_MEDIOS + (EXT_PROYECTO,)):
                    poner(x)
        elif os.path.isdir(r):
            if recursivo:
                for raiz, carpetas, nombres in os.walk(r):
                    carpetas[:] = sorted(c for c in carpetas if c != CARPETA_SALIDA)
                    for n in sorted(nombres):
                        if n.lower().endswith(EXT_MEDIOS + (EXT_PROYECTO,)):
                            poner(os.path.join(raiz, n))
            else:
                for n in sorted(os.listdir(r)):
                    x = os.path.join(r, n)
                    if os.path.isfile(x) and n.lower().endswith(EXT_MEDIOS + (EXT_PROYECTO,)):
                        poner(x)
        elif os.path.isfile(r):
            poner(r)
        else:
            raise ErrorLote("No encontré: %s" % r)
        if len(out) > ENTRADAS_MAX:
            raise ErrorLote("Son demasiados archivos (el máximo es %d por vez)." % ENTRADAS_MAX)
    return out


def procesar_lote(origenes, carpeta, receta, al_progresar=None, cancelar=None, avisar=None, codificador=None, continuar=True):
    """Procesa varios archivos, uno atrás de otro. Un archivo que falla no detiene a los demás (salvo `continuar=False`).

    carpeta: dónde se escribe todo; si es None, cada uno va a una subcarpeta «moviola-salida» al lado del original.
    al_progresar(i, n, fraccion_del_archivo, nombre) y avisar(i, n, paso, texto) cuentan el avance.
    Devuelve {resultados: [{origen, ok, archivo | error, ...}], ok, fallaron, canceladas}."""
    if cancelar is None:
        cancelar = threading.Event()
    n = len(origenes)
    if not n:
        raise ErrorLote("No hay ningún archivo para procesar.")
    resultados = []
    for i, o in enumerate(origenes):
        nombre = os.path.basename(o)
        if cancelar.is_set():
            resultados.append({"origen": o, "ok": False, "cancelado": True, "error": "Cancelado."})
            continue
        destino = carpeta or os.path.join(os.path.dirname(os.path.abspath(o)), CARPETA_SALIDA)
        try:
            r = procesar(o, destino, receta, None,
                         (lambda fr, i=i, nombre=nombre: al_progresar(i, n, fr, nombre)) if al_progresar else None, cancelar,
                         (lambda paso, texto, i=i: avisar(i, n, paso, texto)) if avisar else None, codificador)
            r["ok"] = True
            resultados.append(r)
        except _proxy.Cancelado:
            resultados.append({"origen": o, "ok": False, "cancelado": True, "error": "Cancelado."})
        except (ErrorLote, _ex.ExportError, ErrorEdicion, _sub.ErrorSubtitulo, _sil.ErrorSilencio) as e:
            resultados.append({"origen": o, "ok": False, "error": str(e)})
            if al_progresar:
                al_progresar(i, n, 1.0, nombre)        # que la barra avance igual
            if not continuar:
                break
        except Exception as e:                      # un archivo raro no puede tirar abajo a todo el lote
            resultados.append({"origen": o, "ok": False, "error": "No pude procesarlo. %s" % _mensaje(e), "interno": True})
            if al_progresar:
                al_progresar(i, n, 1.0, nombre)
            if not continuar:
                break
    bien = sum(1 for r in resultados if r["ok"])
    return {"resultados": resultados, "ok": bien, "fallaron": sum(1 for r in resultados if not r["ok"] and not r.get("cancelado")),
            "canceladas": sum(1 for r in resultados if r.get("cancelado"))}
