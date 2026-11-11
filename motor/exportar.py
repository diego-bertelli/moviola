# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Exportador: convierte un Proyecto (motor/proyecto.py) en un archivo, con ffmpeg.

Formatos de video: 'original', 'vertical' 9:16 (1080x1920), 'horizontal' 16:9 (1920x1080),
'cuadrado' 1:1 (1080x1080). Si la proporcion no coincide: 'recortar' (llena el cuadro, centrado o
en el punto de foco) o 'barras' (entra entero, con barras negras). Formatos de audio: wav, mp3,
flac, m4a. Opcional: normalizar el volumen a -14 LUFS (dos pasadas).

Decisiones que importan para que el resultado sea exacto, no solo plausible:
  - Cada clip es una entrada propia con `-ss`/`-t`: cortar 10 s de un video de una hora no
    decodifica la hora entera. Se afina con `trim` y media milesima de tolerancia, para que
    ningun cuadro se pierda ni sobre por redondeo.
  - `-fflags +igndts` en cada entrada: sin eso ffmpeg puede cambiar de criterio de tiempos a
    mitad del archivo (en un video real el proxy quedaba 1,26 s desfasado; ver motor/proxy.py).
  - El cero de la linea de tiempo es el PRIMER CUADRO de la fuente, no el inicio del contenedor:
    se compensa la diferencia al recortar.
  - El filtro se pasa por archivo (`-/filter_complex`): con cientos de cortes no entra en la
    linea de comandos de Windows (32.767 caracteres).
  - Salida siempre a framerate constante (un VFR se lleva a 24/25/30 segun su promedio).
  - Nunca se pisa un archivo: se numeran -v1, -v2... y se escribe a un .parcial que se renombra
    al terminar.
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile

from motor import efectos as _fx
from motor import gpu as _gpu
from motor import proxy as _proxy
from motor import subtitulos as _sub
from motor.proyecto import TOL

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

FORMATOS_VIDEO = {"original": None, "vertical": (1080, 1920), "horizontal": (1920, 1080), "cuadrado": (1080, 1080)}
FORMATOS_AUDIO = {
    "wav": (".wav", ["-c:a", "pcm_s16le"]),
    "mp3": (".mp3", ["-c:a", "libmp3lame", "-q:a", "2"]),
    "flac": (".flac", ["-c:a", "flac"]),
    "m4a": (".m4a", ["-c:a", "aac", "-b:a", "192k"]),
    "opus": (".opus", ["-c:a", "libopus", "-b:a", "128k"]),
    "ogg": (".ogg", ["-c:a", "libvorbis", "-q:a", "5"]),
}

CALIDADES = ("alta", "equilibrada", "liviana")


def _crf(a, b, c_):
    return {"alta": str(a), "equilibrada": str(b), "liviana": str(c_)}


# Perfiles de salida de VIDEO: contenedor + codec. `video(calidad)` son los argumentos del codec; `crf` solo existe en los que
# comprimen con perdida (ProRes y GIF no tienen «calidad» para elegir).
PERFILES = {
    "mp4_h264": {"nombre": "MP4 · H.264", "ext": ".mp4", "audio": ["-c:a", "aac", "-b:a", "192k"], "gpu": "h264", "mov": True,
                 "nota": "El más compatible: sirve para redes y casi cualquier equipo.",
                 "video": lambda q: ["-c:v", "libx264", "-preset", "medium", "-crf", _crf(18, 23, 28)[q], "-profile:v", "high", "-pix_fmt", "yuv420p"]},
    "mp4_h265": {"nombre": "MP4 · H.265 (HEVC)", "ext": ".mp4", "audio": ["-c:a", "aac", "-b:a", "192k"], "gpu": "hevc", "mov": True,
                 "nota": "Archivos más chicos con la misma calidad. No lo abre todo (equipos y navegadores viejos).",
                 "video": lambda q: ["-c:v", "libx265", "-preset", "medium", "-crf", _crf(22, 26, 31)[q], "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]},
    "mp4_av1": {"nombre": "MP4 · AV1", "ext": ".mp4", "audio": ["-c:a", "aac", "-b:a", "192k"], "gpu": None, "mov": True,
                "nota": "El más chico de todos; tarda más en exportar y lo abren solo los equipos recientes.",
                "video": lambda q: ["-c:v", "libsvtav1", "-preset", "8", "-crf", _crf(28, 35, 42)[q], "-pix_fmt", "yuv420p"]},
    "webm_vp9": {"nombre": "WebM · VP9", "ext": ".webm", "audio": ["-c:a", "libopus", "-b:a", "128k"], "gpu": None, "mov": False,
                 "nota": "Para la web (sitios y navegadores). Con sonido Opus.",
                 "video": lambda q: ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", _crf(28, 34, 41)[q], "-row-mt", "1", "-cpu-used", "4", "-pix_fmt", "yuv420p"]},
    "mov_prores": {"nombre": "MOV · ProRes 422", "ext": ".mov", "audio": ["-c:a", "pcm_s16le"], "gpu": None, "mov": True, "calidad": False,
                   "nota": "Para seguir editando en otro programa. Casi sin pérdida, pero los archivos son enormes.",
                   "video": lambda q: ["-c:v", "prores_ks", "-profile:v", "3", "-vendor", "apl0", "-pix_fmt", "yuv422p10le"]},
    "mkv_h264": {"nombre": "MKV · H.264", "ext": ".mkv", "audio": ["-c:a", "aac", "-b:a", "192k"], "gpu": "h264", "mov": False,
                 "nota": "H.264 en un contenedor Matroska (lo abren VLC y la mayoría de los reproductores; las redes, no).",
                 "video": lambda q: ["-c:v", "libx264", "-preset", "medium", "-crf", _crf(18, 23, 28)[q], "-profile:v", "high", "-pix_fmt", "yuv420p"]},
    "gif": {"nombre": "GIF animado", "ext": ".gif", "audio": None, "gpu": None, "mov": False, "calidad": False,
            "nota": "Sin sonido, hasta 2 minutos. Pesa mucho: conviene chico y corto.",
            "video": lambda q: ["-loop", "0"]},
}
GIF_ANCHO = (120, 1920)
GIF_FPS = (10, 15, 20, 25)
GIF_DURACION_MAX = 120.0
FPS_PARA_VFR = (24, 25, 30)

Cancelado = _proxy.Cancelado


class ExportError(RuntimeError):
    """No se pudo exportar; el mensaje se le muestra a la persona."""


# ----------------------------------------------------------------- utilidades

def _fraccion(texto):
    try:
        a, b = str(texto).split("/")
        return float(a) / float(b) if float(b) else 0.0
    except (ValueError, ZeroDivisionError):
        try:
            return float(texto)
        except (TypeError, ValueError):
            return 0.0


def fps_de_salida(video):
    """Framerate constante de la salida, como cadena que ffmpeg entiende."""
    avg = _fraccion(video.get("avg_frame_rate"))
    r = _fraccion(video.get("r_frame_rate"))
    if avg <= 0:
        avg = r if r > 0 else 30.0
    # r_frame_rate es el maximo: si es muy distinto del promedio, el video es de framerate variable.
    if r > 0 and abs(r - avg) / avg > 0.05:
        return str(min(FPS_PARA_VFR, key=lambda c: abs(c - avg)))
    texto = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30"
    return texto if "/" in str(texto) and _fraccion(texto) > 0 else str(round(avg, 3))


def _dims_visibles(video):
    """Ancho y alto con que se ve el video (con la rotacion de celular y los pixeles no cuadrados aplicados)."""
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    rot = 0
    for dato in video.get("side_data_list") or []:
        if "rotation" in dato:
            try:
                rot = abs(int(round(float(dato["rotation"])))) % 360
            except (TypeError, ValueError):
                rot = 0
    if rot in (90, 270):
        w, h = h, w
    sar = _sar(video)
    if sar != 1.0 and rot not in (90, 270):
        w = int(round(w * sar))
    return w - w % 2, h - h % 2


def _sar(video):
    txt = video.get("sample_aspect_ratio") or "1:1"
    try:
        a, b = txt.split(":")
        v = float(a) / float(b)
        return v if v > 0 else 1.0
    except (ValueError, ZeroDivisionError):
        return 1.0


def _fusionar(clips, audio=False):
    """Une clips seguidos que salen de la misma fuente sin interrupcion y sin fundido en la union:
    se exportan como uno solo (menos entradas, mismo resultado)."""
    out = []
    for c in clips:
        if out:
            a = out[-1]
            if (not c.get("transicion") and a["fuente"] == c["fuente"] and abs(a["hasta"] - c["desde"]) < 1e-6
                    and a.get("velocidad", 1.0) == c.get("velocidad", 1.0) and not a.get("reversa") and not c.get("reversa")
                    and a.get("mantener_tono", True) == c.get("mantener_tono", True) and a.get("interpolar") == c.get("interpolar")
                    and abs((a["inicio"] + (a["hasta"] - a["desde"]) / a.get("velocidad", 1.0)) - c["inicio"]) < TOL
                    and a["fade_out"] == 0 and c["fade_in"] == 0
                    and _fx.firma(a.get("efectos", [])) == _fx.firma(c.get("efectos", []))
                    and (not audio or (a["volumen"] == c["volumen"] and a.get("pista_audio") == c.get("pista_audio")))
                    and (audio or a.get("color_fundido") == c.get("color_fundido"))):
                a = dict(a, hasta=c["hasta"], fade_out=c["fade_out"], curva_out=c["curva_out"])
                out[-1] = a
                continue
        out.append(dict(c))
    return out


def _cadena_atempo(v):
    """Filtros que cambian la velocidad del audio a `v` veces SIN cambiar el tono (cada atempo va de 0,5 a 100)."""
    out = []
    while v < 0.5 - 1e-9:
        out.append("atempo=0.5")
        v /= 0.5
    out.append("atempo=%.6f" % v)
    return out


def desfase_de_fuente(f, info):
    """Segundos entre el inicio del contenedor y el cero de la linea de tiempo de esa fuente (el primer cuadro).
    Un tiempo de ffmpeg es el tiempo de la fuente MAS este desfase."""
    inicio = f.get("inicio")
    if inicio is not None:
        return float(inicio) - info["inicio_contenedor"]
    if info["video"] is not None:
        return _proxy._numero(info["video"].get("start_time")) - info["inicio_contenedor"]
    return 0.0


def siguiente_destino(carpeta, base, extension):
    """Primer nombre libre: base-v1.ext, base-v2.ext... Nunca pisa un archivo existente."""
    n = 1
    while os.path.exists(os.path.join(carpeta, "%s-v%d%s" % (base, n, extension))):
        n += 1
    return os.path.join(carpeta, "%s-v%d%s" % (base, n, extension))


def _nombre_seguro(texto):
    return re.sub(r"[^\w\-. ]+", "_", texto).strip(" ._")[:60] or "montaje"


# ------------------------------------------------------------- el grafo

class _Plan:
    """Todo lo que hace falta para armar el comando: entradas, grafo, duracion."""

    def __init__(self, p, formato, encuadre, foco, fps, con_video, con_audio, medir=None, normalizar=None, trabajo=None, subtitulos=None, gif=None):
        self.p = p
        self.subs = subtitulos            # {'frases', 'estilo'} para quemar sobre el video, o None
        self.gif = gif                    # {'ancho', 'fps'} si la salida es un GIF (la paleta se arma dentro del grafo)
        self.trabajo = trabajo            # carpeta temporal: ahi viven las copias de archivos externos (LUT) y los analisis
        self.preparaciones = []           # pasadas de analisis que hay que correr ANTES de exportar (estabilizar bien)
        self._copias = {}
        self.formato = formato
        self.encuadre = encuadre
        self.foco = foco
        self.con_video = con_video
        self.con_audio = con_audio
        self.entradas = []
        self._clave = {}
        self.lineas = []
        self.fuentes = {}
        self.fps = fps
        self.ancho = self.alto = 0
        self.duracion = 0.0
        self.tiene_audio = False
        self.medir = medir
        self.normalizar = normalizar
        self._n = 0
        try:
            self._construir()
        except _fx.ErrorEfecto as e:               # un ajuste que no se puede armar (por ejemplo, falta elegir la imagen de fondo)
            raise ExportError(str(e))

    # -- fuentes
    def _fuente(self, fid):
        if fid not in self.fuentes:
            f = self.p.fuentes[fid]
            if not os.path.isfile(f["ruta"]):
                raise ExportError("No encuentro el archivo original: %s" % f["ruta"])
            info = _proxy.sondear(f["ruta"])
            self.fuentes[fid] = {"ruta": f["ruta"], "info": info, "off": desfase_de_fuente(f, info)}
        return self.fuentes[fid]

    def _entrada(self, ruta, a, b):
        """(indice de entrada, x). a y b son tiempos de ffmpeg; x es donde se hace el -ss."""
        x = max(0.0, a - 0.5)
        clave = (ruta, round(x, 6), round(b, 6))
        if clave not in self._clave:
            self._clave[clave] = len(self.entradas)
            self.entradas.append({"ruta": ruta, "ss": x, "t": (b - x) + 0.1})
        return self._clave[clave], x

    def _trans_con(self, clips, i):
        """Transicion REAL (tipo, duracion) en la entrada del clip i de una lista de clips (None si no hay o no se puede).
        La duracion se redondea para abajo a una cantidad PAR de cuadros cuando se conoce el framerate: asi cada mitad es
        de cuadros enteros, y el video, el audio y la cuenta de cuadros siguen exactos."""
        if i <= 0:
            return None
        a, b = clips[i - 1], clips[i]
        t = b.get("transicion")
        if not t or abs(self.p.fin(a) - b["inicio"]) > 1e-3:
            return None
        d = float(t["duracion"])
        if self.fps is not None:
            dt = 1.0 / _fraccion(self.fps)
            d = 2 * dt * int(d / (2 * dt) + 1e-9)
        return (t["tipo"], d) if d >= 0.04 else None

    def _extensiones(self, clips, i):
        """(segundos que se agregan antes, y despues) del clip i para las transiciones de sus dos bordes."""
        ent = self._trans_con(clips, i)
        sal = self._trans_con(clips, i + 1) if i + 1 < len(clips) else None
        return (ent[1] / 2 if ent else 0.0), (sal[1] / 2 if sal else 0.0)

    def _etiqueta(self, prefijo):
        self._n += 1
        return "%s%d" % (prefijo, self._n)

    # -- armado
    def _construir(self):
        p = self.p
        pistas_v = [t for t in p.pistas if t["tipo"] == "video" and t["clips"]]
        if self.con_video:
            if not pistas_v:
                raise ExportError("Este proyecto no tiene video: elegí un formato de audio.")
            self.duracion = max(p.fin(c) for c in pistas_v[0]["clips"])
        else:
            self.duracion = p.duracion()
        if self.duracion < TOL:
            raise ExportError("No hay nada para exportar.")
        if self.con_video:
            self._video(pistas_v[0])
        if self.con_audio:
            self._audio()

    def _destino_dims(self, primer_clip):
        meta = FORMATOS_VIDEO[self.formato]
        if meta:
            return meta
        v = self._fuente(primer_clip["fuente"])["info"]["video"]
        w, h = _dims_visibles(v)
        # "original" es el tamano del primer clip YA con sus efectos que cambian el tamano (rotar, recortar bordes)
        for e in primer_clip.get("efectos", []):
            if e.get("activo", True) and _fx.categoria(e["tipo"]) == "video" and _fx.etapa(e["tipo"]) == "antes":
                w, h = _fx.dims_tras(e["tipo"], e["params"], w, h)
        return w, h

    def _copiar_externo(self, ruta):
        """Lleva un archivo externo (una LUT) a la carpeta de trabajo y devuelve un nombre SIN carpetas: asi no hay que
        escapar rutas de Windows dentro del filtro."""
        if ruta in self._copias:
            return self._copias[ruta]
        if not os.path.isfile(ruta):
            raise ExportError("No encuentro el archivo: %s" % ruta)
        if self.trabajo is None:
            raise ExportError("No se pueden usar archivos externos en este tipo de exportacion.")
        nombre = "externo%d%s" % (len(self._copias) + 1, os.path.splitext(ruta)[1].lower())
        shutil.copyfile(ruta, os.path.join(self.trabajo, nombre))
        self._copias[ruta] = nombre
        return nombre

    def _escribir_texto(self, texto):
        """El texto de un titulo va en un archivo de la carpeta de trabajo (UTF-8): asi no hay que escapar nada en el filtro."""
        if self.trabajo is None:
            raise ExportError("No se puede escribir texto en este tipo de exportacion.")
        nombre = "texto%d.txt" % (len(self._copias) + 1)
        self._copias["#" + nombre] = nombre
        with io.open(os.path.join(self.trabajo, nombre), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        return nombre

    def _fuente_letra(self, clave):
        """Copia la letra elegida desde las fuentes de Windows a la carpeta de trabajo y devuelve su nombre."""
        if "@" + clave in self._copias:
            return self._copias["@" + clave]
        archivo = _fx.FUENTES[clave][1]
        ruta = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Fonts", archivo)
        if not os.path.isfile(ruta):
            raise ExportError("Esta computadora no tiene la letra «%s»: elegí otra." % _fx.FUENTES[clave][0])
        if self.trabajo is None:
            raise ExportError("No se puede escribir texto en este tipo de exportacion.")
        nombre = "letra%d.ttf" % (len(self._copias) + 1)
        shutil.copyfile(ruta, os.path.join(self.trabajo, nombre))
        self._copias["@" + clave] = nombre
        return nombre

    def _video(self, pista):
        clips = _fusionar(pista["clips"])
        primera = self._fuente(clips[0]["fuente"])["info"]["video"]
        if self.fps is None:
            self.fps = fps_de_salida(primera)
        self.ancho, self.alto = self._destino_dims(clips[0])
        piezas, t = [], 0.0
        cadena = None                       # (etiqueta, duracion) del tramo que se va armando: los clips pegados con transicion se encadenan

        def cerrar():
            nonlocal cadena
            if cadena is not None:
                piezas.append(cadena[0])
                cadena = None

        for i, c in enumerate(clips):
            hueco = c["inicio"] - t
            if hueco > 1e-3:
                cerrar()
                e = self._etiqueta("vh")
                self.lineas.append("color=c=black:s=%dx%d:r=%s:d=%.6f,format=yuv420p,setsar=1[%s]"
                                   % (self.ancho, self.alto, self.fps, hueco, e))
                piezas.append(e)
            ext_ini, ext_fin = self._extensiones(clips, i)
            seg = self._clip_video(c, ext_ini, ext_fin)
            largo_seg = (c["hasta"] - c["desde"]) / c.get("velocidad", 1.0) + ext_ini + ext_fin
            tr = self._trans_con(clips, i)
            if tr is not None and cadena is not None and hueco <= 1e-3:
                x = self._etiqueta("vx")
                self.lineas.append("[%s][%s]xfade=transition=%s:duration=%.6f:offset=%.6f[%s]"
                                   % (cadena[0], seg, _fx.TRANSICIONES[tr[0]]["xfade"], tr[1], cadena[1] - tr[1], x))
                cadena = (x, cadena[1] + largo_seg - tr[1])
            else:
                cerrar()
                cadena = (seg, largo_seg)
            t = self.p.fin(c)
        cerrar()
        quemar = bool(self.subs and self.subs["frases"] and self.trabajo is not None)
        self.lineas.append("%sconcat=n=%d:v=1:a=0[%s]" % ("".join("[%s]" % s for s in piezas), len(piezas), "vcat" if (quemar or self.gif) else "vout"))
        ultimo = "vcat"
        if quemar:
            # los subtitulos se quemaban sobre el video YA armado: sus tiempos son los de la linea de tiempo
            est = self.subs["estilo"]
            letra = self._fuente_letra(est["fuente"])          # la letra viaja a la carpeta de trabajo: libass la busca ahi (fontsdir)
            with io.open(os.path.join(self.trabajo, "subs.ass"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(_sub.a_ass(self.subs["frases"], est, self.ancho, self.alto, self.duracion, self.subs.get("palabras")))
            self.lineas.append("[vcat]ass=filename=subs.ass:fontsdir=.[%s]" % ("vsub" if self.gif else "vout"))
            ultimo = "vsub"
        if self.gif:
            # GIF: se baja a los cuadros por segundo y al ancho pedidos y se arma la MEJOR paleta de 256 colores de ESTE video
            self.lineas.append("[%s]fps=%d,scale=%d:-2:flags=lanczos,split[g1][g2];[g1]palettegen=stats_mode=diff[gp];[g2][gp]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle[vout]"
                               % (ultimo, self.gif["fps"], self.gif["ancho"]))

    def _clip_video(self, c, ext_ini=0.0, ext_fin=0.0):
        f = self._fuente(c["fuente"])
        v = f["info"]["video"]
        vel = c.get("velocidad", 1.0)
        # las extensiones de las transiciones estan en segundos de la LINEA DE TIEMPO: en la fuente son `vel` veces mas
        a, b = c["desde"] + f["off"] - ext_ini * vel, c["hasta"] + f["off"] + ext_fin * vel
        k, x = self._entrada(f["ruta"], a, b)
        largo = (c["hasta"] - c["desde"]) / vel + ext_ini + ext_fin
        cad = ["trim=start=%.6f:end=%.6f" % (a - x - 0.0005, b - x - 0.0005), "setpts=PTS-STARTPTS"]
        if abs(vel - 1.0) > 1e-9:
            cad.append("setpts=PTS/%.6f" % vel)
        if f["info"]["entrelazado"]:
            cad.append("yadif=mode=0:parity=-1:deint=1")
        sar = _sar(v)
        if abs(sar - 1.0) > 1e-3:
            cad.append("scale=w='trunc(iw*sar/2)*2':h=ih,setsar=1")
        vw, vh = _dims_visibles(v)
        efectos_activos = [e for e in c.get("efectos", []) if e.get("activo", True) and _fx.categoria(e["tipo"]) == "video"]

        def ctx(ancho, alto):
            def preparacion(tipo, params):
                # el analisis ve la imagen EXACTAMENTE como llega a este efecto (todo lo que va antes en la cadena)
                nombre = "estab%d.trf" % (len(self.preparaciones) + 1)
                self.preparaciones.append({"ruta": f["ruta"], "ss": self.entradas[k]["ss"], "t": self.entradas[k]["t"],
                                           "indice": v["index"], "prefijo": ",".join(cad), "trf": nombre})
                return nombre
            return {"ancho": ancho, "alto": alto, "copiar": self._copiar_externo, "preparacion": preparacion,
                    "fuente": self._fuente_letra, "escribir_texto": self._escribir_texto, "fps": self.fps,
                    "fps_n": _fraccion(self.fps), "largo": largo, "t0": ext_ini}

        entrada = "%d:%d" % (k, v["index"])

        # 1) los que cambian el tamano de la imagen, ANTES de encuadrar
        for e in efectos_activos:
            if _fx.etapa(e["tipo"]) == "antes":
                fx = _fx.filtro_video(e["tipo"], e["params"], ctx(vw, vh))
                if fx:
                    cad.append(fx)
                    vw, vh = _fx.dims_tras(e["tipo"], e["params"], vw, vh)
        if (vw, vh) != (self.ancho, self.alto):
            if self.encuadre == "barras":
                cad.append("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=black"
                           % (self.ancho, self.alto, self.ancho, self.alto))
            else:
                cad.append("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d:x='(iw-ow)*%.4f':y='(ih-oh)*%.4f'"
                           % (self.ancho, self.alto, self.ancho, self.alto, self.foco[0], self.foco[1]))
        if f["info"]["hdr"]:
            cad.append(_proxy._TONEMAP)
        if c.get("interpolar") and vel < 1.0:
            # camara lenta suave: se inventan los cuadros que faltan entre los de la fuente (lento, pero se ve mucho mejor)
            cad.append("minterpolate=fps=%s:mi_mode=mci:mc_mode=aobmc:vsbmc=1" % self.fps)
        cad += ["fps=%s" % self.fps, "setsar=1", "format=yuv420p"]
        # 2) el resto de los efectos del clip, en orden, despues de encuadrar y antes de los fundidos
        for e in efectos_activos:
            if _fx.etapa(e["tipo"]) == "despues":
                if _fx.es_complejo(e["tipo"]):
                    # trae una entrada extra (una imagen, un fondo): se cierra la cadena que va y se arma un subgrafo aparte
                    if not _fx.es_neutro(e["tipo"], e["params"]):
                        sig = self._etiqueta("vc")
                        self.lineas.append("[%s]%s[%s]" % (entrada, ",".join(cad) or "null", sig))
                        lineas, entrada = _fx.subgrafo(e["tipo"], e["params"], ctx(self.ancho, self.alto), sig, self._etiqueta)
                        self.lineas += lineas
                        cad = []
                    continue
                fx = _fx.filtro_video(e["tipo"], e["params"], ctx(self.ancho, self.alto))
                if fx:
                    cad.append(fx)
        if c.get("reversa"):
            # `reverse` guarda TODOS los cuadros del clip en memoria: se avisa antes de que ffmpeg se quede sin ella
            if largo * _fraccion(self.fps) * self.ancho * self.alto * 1.5 > 3.0e9:
                raise ExportError("Un clip al revés tan largo y pesado usa demasiada memoria: cortalo en tramos más cortos.")
            cad.append("reverse")
        if (abs(vel - 1.0) > 1e-9 or c.get("reversa")) and ext_ini == 0.0 and ext_fin == 0.0:
            # cantidad EXACTA de cuadros: con otra velocidad el largo del clip no es un multiplo del cuadro de salida y el
            # redondeo de cada clip se acumularia (el video terminaria corrido del audio). Se cuenta sobre el tiempo acumulado.
            fps_n = _fraccion(self.fps)
            n = int(round(self.p.fin(c) * fps_n)) - int(round(c["inicio"] * fps_n))
            cad.append("tpad=stop=3:stop_mode=clone,trim=end_frame=%d" % max(1, n))
        color = "white" if c.get("color_fundido") == "blanco" else "black"
        if c["fade_in"] > TOL:
            cad.append("fade=t=in:st=0:d=%.6f:color=%s" % (c["fade_in"], color))
        if c["fade_out"] > TOL:
            cad.append("fade=t=out:st=%.6f:d=%.6f:color=%s" % (largo - c["fade_out"], c["fade_out"], color))
        e = self._etiqueta("v")
        self.lineas.append("[%s]%s[%s]" % (entrada, ",".join(cad) or "null", e))
        return e

    def _audio(self):
        p = self.p
        pistas = [t for t in p.pistas if t["tipo"] == "audio" and not t["silenciada"] and t["clips"]]
        salidas = []
        for t in pistas:
            piezas, fin = [], 0.0
            cadena = None
            clips = _fusionar(t["clips"], audio=True)

            def cerrar():
                nonlocal cadena
                if cadena is not None:
                    piezas.append(cadena)
                    cadena = None

            for i, c in enumerate(clips):
                hueco = c["inicio"] - fin
                if hueco > 1e-3:
                    cerrar()
                    e = self._etiqueta("ah")
                    self.lineas.append("anullsrc=r=48000:cl=stereo:d=%.6f,aformat=sample_rates=48000:channel_layouts=stereo[%s]" % (hueco, e))
                    piezas.append(e)
                ext_ini, ext_fin = self._extensiones(clips, i)
                seg = self._clip_audio(c, ext_ini, ext_fin)
                tr = self._trans_con(clips, i)
                if tr is not None and cadena is not None and hueco <= 1e-3:
                    x = self._etiqueta("ax")
                    self.lineas.append("[%s][%s]acrossfade=d=%.6f:c1=tri:c2=tri[%s]" % (cadena, seg, tr[1], x))
                    cadena = x
                else:
                    cerrar()
                    cadena = seg
                fin = p.fin(c)
            cerrar()
            e = self._etiqueta("at")
            self.lineas.append("%sconcat=n=%d:v=0:a=1[%s]" % ("".join("[%s]" % s for s in piezas), len(piezas), e))
            salidas.append(e)
        # ducking: las pistas de musica con "bajar cuando habla el audio del video" se comprimen con A1 como disparador
        if salidas:
            etiquetas = {pistas[i]["id"]: salidas[i] for i in range(len(salidas))}
            voz = etiquetas.get("A1")
            duck = [pid for pid in etiquetas if pid != "A1" and (self.p.pista(pid).get("ducking") or {}).get("activo")]
            if voz and duck:
                disparos = [self._etiqueta("ak") for _ in duck]
                voz_m = self._etiqueta("am")
                self.lineas.append("[%s]asplit=%d[%s]%s" % (voz, len(duck) + 1, voz_m, "".join("[%s]" % d for d in disparos)))
                etiquetas["A1"] = voz_m
                for pid, disparo in zip(duck, disparos):
                    red = float(self.p.pista(pid)["ducking"]["reduccion"])
                    razon = 1.0 / (1.0 - min(red, 19.0) / 20.0)          # con una voz ~20 dB sobre el umbral, la razon da la reduccion pedida
                    x = self._etiqueta("ad")
                    self.lineas.append("[%s][%s]sidechaincompress=threshold=0.05:ratio=%.2f:attack=20:release=300:makeup=1[%s]"
                                       % (etiquetas[pid], disparo, razon, x))
                    etiquetas[pid] = x
                salidas = [etiquetas[pistas[i]["id"]] for i in range(len(salidas))]
        if not salidas:
            return
        self.tiene_audio = True
        d = self.duracion
        if len(salidas) == 1:
            mezcla = "[%s]atrim=end=%.6f,apad=whole_dur=%.6f" % (salidas[0], d, d)
        else:
            mezcla = "%samix=inputs=%d:duration=longest:normalize=0,alimiter=limit=0.95,atrim=end=%.6f,apad=whole_dur=%.6f" % (
                "".join("[%s]" % s for s in salidas), len(salidas), d, d)
        if self.medir is not None:
            mezcla += ",loudnorm=I=%.1f:TP=-1.5:LRA=11:print_format=json" % self.medir
        elif self.normalizar:
            m = self.normalizar
            mezcla += (",loudnorm=I=%.1f:TP=-1.5:LRA=11:measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:"
                       "offset=%s:linear=true") % (m["objetivo"], m["input_i"], m["input_tp"], m["input_lra"],
                                                   m["input_thresh"], m["target_offset"])
        self.lineas.append(mezcla + "[aout]")

    def _clip_audio(self, c, ext_ini=0.0, ext_fin=0.0):
        f = self._fuente(c["fuente"])
        vel = c.get("velocidad", 1.0)
        a, b = c["desde"] + f["off"] - ext_ini * vel, c["hasta"] + f["off"] + ext_fin * vel
        k, x = self._entrada(f["ruta"], a, b)
        largo = (c["hasta"] - c["desde"]) / vel + ext_ini + ext_fin
        cad = ["atrim=start=%.6f:end=%.6f" % (a - x, b - x), "asetpts=PTS-STARTPTS",
               "aformat=sample_rates=48000:channel_layouts=stereo"]
        con_efecto = False
        if abs(vel - 1.0) > 1e-9:
            con_efecto = True                                   # la velocidad tambien agrega o quita milisegundos
            if c.get("mantener_tono", True):
                cad += _cadena_atempo(vel)                      # cambia la velocidad SIN cambiar el tono
            else:
                cad += ["asetrate=%d" % int(round(48000 * vel)), "aresample=48000"]     # como una cinta: el tono sube o baja
        if c.get("reversa"):
            cad.append("areverse")
            con_efecto = True
        # efectos del clip, en orden, antes del volumen y los fundidos
        for e in c.get("efectos", []):
            if e.get("activo", True):
                fx = _fx.filtro_audio(e["tipo"], e["params"])
                if fx:
                    cad.append(fx)
                    con_efecto = True
        if con_efecto:
            # Algunos efectos agregan o quitan unos milisegundos (eco, tono): el clip tiene que durar EXACTAMENTE
            # lo mismo, o todo lo que viene despues se corre y el audio se desfasa del video.
            cad.append("apad=whole_dur=%.6f,atrim=end=%.6f" % (largo, largo))
        if abs(c["volumen"] - 1.0) > 1e-4:
            cad.append("volume=%.4f" % c["volumen"])
        if c["fade_in"] > TOL:
            cad.append("afade=t=in:st=0:d=%.6f:curve=%s" % (c["fade_in"], c["curva_in"]))
        if c["fade_out"] > TOL:
            cad.append("afade=t=out:st=%.6f:d=%.6f:curve=%s" % (largo - c["fade_out"], c["fade_out"], c["curva_out"]))
        e = self._etiqueta("a")
        self.lineas.append("[%d:a:%d]%s[%s]" % (k, c.get("pista_audio") or 0, ",".join(cad), e))
        return e

    def grafo(self):
        return ";\n".join(self.lineas)


# --------------------------------------------------------------- ejecucion

def _escribir_grafo(texto):
    fd, ruta = tempfile.mkstemp(prefix="grafo-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta


def _comando_base(plan, grafo_ruta):
    cmd = [_proxy._ffmpeg(), "-v", "error", "-y", "-nostdin"]
    for e in plan.entradas:
        cmd += ["-fflags", "+igndts", "-ss", "%.6f" % e["ss"], "-t", "%.6f" % e["t"], "-protocol_whitelist", "file", "-i", e["ruta"]]
    cmd += ["-/filter_complex", grafo_ruta]
    return cmd


def _medir_volumen(p, objetivo, cancelar):
    """Primera pasada de loudnorm: mide la mezcla final sin escribir nada."""
    plan = _Plan(p, "original", "recortar", (0.5, 0.5), None, False, True, medir=objetivo)
    if not plan.tiene_audio:
        return None
    grafo = _escribir_grafo(plan.grafo())
    try:
        cmd = _comando_base(plan, grafo)
        cmd[1:3] = ["-hide_banner", "-loglevel", "info"]
        cmd += ["-map", "[aout]", "-f", "null", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
        salida = []
        for linea in proc.stdout:
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                proc.wait()
                raise Cancelado()
            salida.append(linea)
        proc.wait()
    finally:
        _proxy._borrar(grafo)
    bloques = re.findall(r"\{[^{}]*\}", "".join(salida))
    if proc.returncode != 0 or not bloques:
        return None
    try:
        datos = json.loads(bloques[-1])
        if float(datos["input_i"]) < -70:           # silencio: no hay nada que normalizar
            return None
        datos["objetivo"] = objetivo
        return datos
    except (ValueError, KeyError):
        return None


def _correr(cmd, total_us, avisar, cancelar, parcial, cwd=None):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA, cwd=cwd)
    errores = []
    try:
        for linea in proc.stdout:
            linea = linea.strip()
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                raise Cancelado()
            if linea.startswith("out_time_us="):
                valor = linea.split("=", 1)[1]
                if avisar is not None and valor.lstrip("-").isdigit():
                    avisar(min(0.999, max(0.0, int(valor) / total_us)))
            elif linea and not _proxy._RUIDO.match(linea):
                errores.append(linea)
        proc.wait()
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if parcial:
            _proxy._borrar(parcial)
        raise
    if proc.returncode != 0:
        if parcial:
            _proxy._borrar(parcial)
        detalle = (errores[-1] if errores else "ffmpeg terminó con error %s" % proc.returncode)
        detalle = re.sub(r"\[[^\]]*\]\s*", "", detalle)[:200]      # sin los prefijos tecnicos de ffmpeg
        raise ExportError("No pude exportar. %s" % detalle)


def _correr_preparaciones(plan, cancelar):
    """Las pasadas de analisis que algunos efectos piden antes de exportar (estabilizar bien: detectar el movimiento de
    camara). Cada una ve la imagen exactamente como llega al efecto."""
    for prep in plan.preparaciones:
        grafo = _escribir_grafo("[0:%d]%s,vidstabdetect=shakiness=5:accuracy=9:mincontrast=0.1:result=%s[o]" % (prep["indice"], prep["prefijo"], prep["trf"]))
        try:
            cmd = [_proxy._ffmpeg(), "-v", "error", "-y", "-nostdin", "-fflags", "+igndts", "-ss", "%.6f" % prep["ss"], "-t", "%.6f" % prep["t"],
                   "-protocol_whitelist", "file", "-i", prep["ruta"], "-/filter_complex", grafo, "-map", "[o]", "-f", "null", "-"]
            _correr(cmd, None, None, cancelar, None, cwd=plan.trabajo)
        finally:
            _proxy._borrar(grafo)
        if not os.path.isfile(os.path.join(plan.trabajo, prep["trf"])):
            raise ExportError("No pude analizar el movimiento de la camara para estabilizar.")


def _duracion_de(ruta):
    d, tipos = _proxy._duracion_de(ruta)
    return d, tipos


def exportar(p, carpeta, nombre_base=None, formato="original", encuadre="recortar", foco=(0.5, 0.5),
             normalizar=False, lufs=-14.0, fps=None, codificador=None, al_progresar=None, cancelar=None, subtitulos=None,
             perfil="mp4_h264", calidad="alta", gif=None):
    """Exporta el proyecto. Devuelve un dict con archivo, duracion, formato, tamano, fps, usado, respaldo,
    motivo_respaldo y normalizacion.

    formato: 'original' | 'vertical' | 'horizontal' | 'cuadrado' | 'wav' | 'mp3' | 'flac' | 'm4a'.
    encuadre: 'recortar' | 'barras' (solo cuando la proporcion no coincide).
    foco: (x, y) de 0 a 1, centro del recorte cuando se recorta.
    codificador: codificador H.264 por hardware (motor/gpu.py) o None para el procesador; si falla, se repite
      con el procesador y se avisa en 'respaldo'.
    perfil: contenedor + codec del video (ver PERFILES: 'mp4_h264', 'mp4_h265', 'mp4_av1', 'webm_vp9', 'mov_prores', 'mkv_h264', 'gif').
      Los formatos de solo audio ignoran el perfil. calidad: 'alta' | 'equilibrada' | 'liviana' (no cuenta en ProRes ni en GIF).
      gif: {'ancho', 'fps'} (por defecto 480 de ancho y 10 cuadros por segundo). `codificador` (GPU) solo se usa con H.264 y H.265.
    subtitulos: {'quemar': bool, 'srt': bool, 'vtt': bool} sobre las frases del proyecto (p.subtitulos): 'quemar' las dibuja
      sobre el video; 'srt' y 'vtt' escriben un archivo al lado con el mismo nombre. Se devuelven en 'subtitulos'.
    """
    if formato not in FORMATOS_VIDEO and formato not in FORMATOS_AUDIO:
        raise ExportError("Formato de exportación desconocido.")
    if encuadre not in ("recortar", "barras"):
        raise ExportError("El encuadre es 'recortar' o 'barras'.")
    es_audio = formato in FORMATOS_AUDIO
    if perfil not in PERFILES:
        raise ExportError("Ese tipo de archivo de video no existe.")
    if calidad not in CALIDADES:
        raise ExportError("La calidad es alta, equilibrada o liviana.")
    if perfil == "gif" and not es_audio:
        gif = dict(gif or {})
        gif.setdefault("ancho", 480)
        gif.setdefault("fps", 10)
        if isinstance(gif["ancho"], bool) or not isinstance(gif["ancho"], (int, float)) or not GIF_ANCHO[0] <= gif["ancho"] <= GIF_ANCHO[1]:
            raise ExportError("El ancho del GIF va de %d a %d." % GIF_ANCHO)
        if gif["fps"] not in GIF_FPS:
            raise ExportError("Los cuadros por segundo del GIF son %s." % ", ".join(str(x) for x in GIF_FPS))
        gif["ancho"] = int(gif["ancho"]) // 2 * 2
        if p.duracion() > GIF_DURACION_MAX:
            raise ExportError("Un GIF de más de %d minutos pesaría muchísimo: exportá un tramo más corto o elegí otro tipo de archivo." % (GIF_DURACION_MAX // 60))
    else:
        gif = None
    if perfil == "gif" and not es_audio and codificador:
        codificador = None
    if not es_audio and codificador and PERFILES[perfil]["gpu"] is None:
        codificador = None
    os.makedirs(carpeta, exist_ok=True)
    if nombre_base is None:
        primera = next(iter(p.fuentes.values()), None)
        nombre_base = os.path.splitext(os.path.basename(primera["ruta"]))[0] if primera else "montaje"
    nombre_base = _nombre_seguro(nombre_base)
    extension = FORMATOS_AUDIO[formato][0] if es_audio else PERFILES[perfil]["ext"]
    destino = siguiente_destino(carpeta, nombre_base, extension)
    parcial = destino[:-len(extension)] + ".parcial" + extension
    _proxy._borrar(parcial)

    avance = [0.0]

    def avisar(fraccion):
        if al_progresar and fraccion >= avance[0]:
            avance[0] = fraccion
            al_progresar(fraccion)

    medicion = None
    if normalizar:
        medicion = _medir_volumen(p, float(lufs), cancelar)
    trabajo = tempfile.mkdtemp(prefix="moviola-export-")
    try:
        return _exportar(p, carpeta, nombre_base, formato, encuadre, foco, es_audio, extension, destino, parcial, medicion,
                         fps, codificador, avisar, cancelar, trabajo, subtitulos, perfil, calidad, gif)
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)


def _exportar(p, carpeta, nombre_base, formato, encuadre, foco, es_audio, extension, destino, parcial, medicion,
              fps, codificador, avisar, cancelar, trabajo, subtitulos=None, perfil="mp4_h264", calidad="alta", gif=None):
    subtitulos = subtitulos or {}
    pf = PERFILES[perfil]
    frases = p.subtitulos["frases"] if hasattr(p, "subtitulos") else []
    if (subtitulos.get("quemar") or subtitulos.get("srt") or subtitulos.get("vtt")) and not frases:
        raise ExportError("Pediste subtítulos pero no hay ninguna frase: transcribí o escribí alguna primero.")
    plan = _Plan(p, formato, encuadre, (float(foco[0]), float(foco[1])), fps, not es_audio, not gif,
                 normalizar=medicion, trabajo=trabajo, gif=gif,
                 subtitulos=({"frases": frases, "estilo": p.subtitulos["estilo"], "palabras": p.subtitulos.get("palabras", [])} if (subtitulos.get("quemar") and not es_audio) else None))
    if es_audio and not plan.tiene_audio:
        raise ExportError("No hay audio para exportar (todas las pistas están silenciadas o no hay ninguna).")
    total_us = plan.duracion * 1_000_000
    grafo = _escribir_grafo(plan.grafo())

    def lanzar(cod):
        cmd = _comando_base(plan, grafo)
        if not es_audio:
            cmd += ["-map", "[vout]"]
            if cod:
                cmd += _gpu.args_codificador(cod, "final")
                if perfil == "mp4_h265":
                    cmd += ["-tag:v", "hvc1"]
            else:
                cmd += pf["video"](calidad)
            cmd += ["-fps_mode", "passthrough"] + (["-movflags", "+faststart"] if pf["mov"] else [])
        else:
            cmd += ["-vn"]
        if plan.tiene_audio:
            cmd += ["-map", "[aout]"]
            cmd += (pf["audio"] if not es_audio else FORMATOS_AUDIO[formato][1])
            cmd += ["-ar", "48000", "-ac", "2"]
        else:
            cmd += ["-an"]
        cmd += ["-progress", "pipe:1", "-nostats", parcial]
        _correr(cmd, total_us, avisar, cancelar, parcial, cwd=trabajo)

    usado, respaldo, motivo = "cpu", False, ""
    try:
        _correr_preparaciones(plan, cancelar)          # los analisis previos (estabilizar bien); una sola vez aunque haya respaldo de GPU
        if codificador and not es_audio:
            try:
                lanzar(codificador)
                usado = "gpu"
            except ExportError:
                # El detalle de ffmpeg no le sirve a la persona: se le dice lo que paso.
                respaldo, motivo = True, "El codificador por hardware (%s) no funcionó en esta PC." % codificador
                _proxy._borrar(parcial)
        if usado == "cpu":
            lanzar(None)
        duracion, tipos = _duracion_de(parcial)
        if duracion <= 0 or not tipos:
            raise ExportError("El archivo exportado salió vacío.")
        if abs(duracion - plan.duracion) > (0.25 if not gif else max(0.25, 0.04 * plan.duracion)):
            raise ExportError("El archivo exportado dura %.2f s y tenía que durar %.2f s." % (duracion, plan.duracion))
        # nunca se pisa nada: si mientras tanto aparecio el nombre, se usa el siguiente
        final = destino
        if os.path.exists(final):
            final = siguiente_destino(carpeta, nombre_base, extension)
        os.replace(parcial, final)
        escritos = []
        for clave, ext, hacer in (("srt", ".srt", _sub.a_srt), ("vtt", ".vtt", _sub.a_vtt)):
            if subtitulos.get(clave):
                ruta_sub = os.path.splitext(final)[0] + ext
                with io.open(ruta_sub, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(hacer(frases, plan.duracion))
                escritos.append(ruta_sub)
    finally:
        _proxy._borrar(grafo)
        if os.path.exists(parcial):
            _proxy._borrar(parcial)
    avisar(1.0)
    return {"archivo": final, "duracion": duracion, "formato": formato, "tamano": (plan.ancho, plan.alto) if not es_audio else None,
            "fps": plan.fps if not es_audio else None, "usado": usado, "respaldo": respaldo, "motivo_respaldo": motivo,
            "normalizacion": medicion, "subtitulos": escritos}
