# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Motor de cuadros de video.

Decodifica por software con PyAV (la GPU de esta maquina no tiene encoder y su
decode es mas lento que el CPU) y entrega cada cuadro como JPEG listo para el
frontend.

El cuadro "n" es el n-esimo cuadro REAL del archivo, en orden de presentacion,
no el que cae en el instante n/fps. Con video de framerate variable (capturas
de pantalla, WhatsApp, algunos celulares) las dos cosas no coinciden, asi que
al abrir se arma un indice con la marca de tiempo (pts) de cada cuadro.
"""

from __future__ import annotations

import os
import statistics
import threading
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from io import BytesIO

import av
from PIL import Image

# Un seek cuesta ~100 ms y un cuadro secuencial ~1 ms: hasta 60 cuadros de
# distancia conviene avanzar decodificando en vez de saltar.
SALTO_MAXIMO = 60
CUADROS_EN_CACHE = 120
CALIDAD_JPEG = 75
ANCHO_MAXIMO = 7680
# Si mas de esta fraccion de los paquetes no trae pts, el indice por paquetes
# no es confiable y se arma decodificando (lento, pero exacto).
MAX_SIN_PTS = 0.02

# Valores de AVColorTransferCharacteristic que ffprobe muestra como
# color_transfer y que implican HDR. En PyAV 19 color_trc es un int.
_TRC_HDR = {16: "smpte2084", 18: "arib-std-b67"}

# WebView2 reproduce nativo h264 con aac o mp3 en contenedor mp4/m4v/mov.
_CONTENEDORES_WEB = {".mp4", ".m4v", ".mov"}
_VIDEO_WEB = {"h264", "avc1"}
_AUDIO_WEB = {"aac", "mp3", "mp3float", "mp2", "mp1"}
# Chromium decodifica h264 solo en 4:2:0 de 8 bits: un High 10 o un 4:2:2 se
# ven negros en el WebView aunque el codec diga h264.
_PIXELES_WEB = {"yuv420p", "yuvj420p", "nv12"}

_OPCIONES_ABRIR = {"fflags": "+genpts", "protocol_whitelist": "file"}      # solo archivos: nada de direcciones de internet


# Formatos con los que el hardware entrega los cuadros. PyAV informa is_hwaccel=True aunque
# caiga a software (medido con MPEG-2), asi que se mira el formato del primer cuadro.
_FORMATOS_HW = {"nv12", "p010le", "p010be", "p016le", "p016be", "d3d11", "dxva2_vld", "cuda", "qsv"}


class SinVideo(ValueError):
    """El archivo no tiene una pista de video real (puede tener audio)."""


def _abrir(ruta, aceleracion):
    """(contenedor, acelerador pedido). Si el acelerador no se puede iniciar, se abre por software."""
    if aceleracion:
        try:
            from av.codec.hwaccel import HWAccel, hwdevices_available
            # PyAV acepta cualquier nombre sin quejarse y elige un acelerador por su cuenta
            # (medido con un nombre inventado): se valida antes para hacer lo que se pidio.
            if aceleracion in hwdevices_available():
                contenedor = av.open(ruta, options=_OPCIONES_ABRIR,
                                     hwaccel=HWAccel(device_type=aceleracion, allow_software_fallback=True))
                return contenedor, aceleracion
        except Exception:
            pass
    return av.open(ruta, options=_OPCIONES_ABRIR), None


def _par(valor: float) -> int:
    """Redondea a entero par >= 2 (swscale falla con altos impares)."""
    entero = int(round(valor))
    if entero < 2:
        return 2
    return entero - (entero % 2)


def _es_portada(flujo) -> bool:
    """Un mp3 con caratula trae un 'video' de un solo cuadro: no es video."""
    try:
        if flujo.disposition & av.stream.Disposition.attached_pic:
            return True
    except Exception:
        pass
    nombre = (flujo.codec_context.name or "").lower()
    return nombre in {"mjpeg", "png", "bmp"} and (flujo.frames or 0) <= 1 and not flujo.average_rate


def pista_de_video(contenedor):
    """Primera pista de video real, o None."""
    for flujo in contenedor.streams.video:
        if not _es_portada(flujo):
            return flujo
    return None


class Video:
    def __init__(self, ruta: str, aceleracion: str = None):
        """aceleracion: tipo de acelerador de decodificacion por GPU (d3d11va, dxva2, cuda...)
        o None para el procesador. Si no se puede iniciar, se decodifica por el procesador."""
        self.ruta = ruta
        self._cerrado = False
        self._formato_inicial = ""

        # El decoder de libav no es thread-safe y el bridge de pywebview llama
        # desde varios hilos.
        self._candado = threading.Lock()
        self._candado_cache = threading.Lock()
        self._cache: "OrderedDict[tuple, bytes]" = OrderedDict()

        self._contenedor, self._acel_pedida = _abrir(ruta, aceleracion)
        self._flujo = pista_de_video(self._contenedor)
        if self._flujo is None:
            self._contenedor.close()
            raise SinVideo("el archivo no tiene pista de video")

        self._flujo.thread_type = "AUTO"
        contexto = self._flujo.codec_context
        self._base = self._flujo.time_base

        try:
            self._pts = self._construir_indice()
            total = len(self._pts)
            base = float(self._base)
            inicio = self._pts[0]
            self._inicio = inicio
            self._tiempos = [(p - inicio) * base for p in self._pts]

            # Duracion de un cuadro tipico y velocidad media.
            difs = [b - a for a, b in zip(self._tiempos, self._tiempos[1:]) if b > a]
            paso = statistics.median(difs) if difs else 0.0
            if paso <= 0:
                tasa = self._flujo.average_rate or self._flujo.guessed_rate
                paso = 1.0 / float(tasa) if tasa else 1.0 / 30.0
            duracion = self._tiempos[-1] + paso
            fps_medio = (total / duracion) if duracion > 0 else 1.0 / paso
            nominal = self._flujo.average_rate or self._flujo.guessed_rate
            if nominal and abs(float(nominal) - fps_medio) <= 0.01 * fps_medio:
                fps = float(nominal)
            else:
                fps = fps_medio

            # Es cuadros-constantes si ninguno se aparta mas de un cuarto de cuadro
            # de la grilla ideal. Si no, es framerate variable.
            cuadro_ideal = 1.0 / fps
            desvio = max((abs(t - i * cuadro_ideal) for i, t in enumerate(self._tiempos)), default=0.0)
            self._vfr = total > 1 and desvio > 0.25 * cuadro_ideal

            # Geometria: el decoder entrega el cuadro sin girar; la rotacion se
            # aplica al armar la vista previa.
            alm_ancho = int(contexto.width)
            alm_alto = int(contexto.height)
            self._rotacion = self._leer_rotacion()
            girado = self._rotacion in (90, 270)
            ancho = alm_alto if girado else alm_ancho
            alto = alm_ancho if girado else alm_alto

            proporcion = contexto.sample_aspect_ratio
            self._proporcion_pixel = float(proporcion) if proporcion else 1.0
            if self._proporcion_pixel <= 0:
                self._proporcion_pixel = 1.0

            self._fps = fps
            self._info = {
                "ancho": ancho,
                "alto": alto,
                "fps": fps,
                "duracion": duracion,
                "total_cuadros": total,
                "codec": contexto.name,
                "hdr": int(getattr(contexto, "color_trc", 0) or 0) in _TRC_HDR,
                "web_compatible": self._calcular_web(contexto),
                "vfr": self._vfr,
                "entrelazado": int(getattr(contexto, "field_order", 0) or 0) in (2, 3, 4, 5),
                "rotacion": self._rotacion,
                "pistas_audio": len(self._contenedor.streams.audio),
                # Instante ABSOLUTO (en el archivo) del primer cuadro: el cero de la linea de tiempo. El
                # exportador lo necesita para recortar con ffmpeg, que cuenta desde el inicio del contenedor.
                "inicio": float(self._pts[0] * self._base),
                # Que se uso de verdad (aproximado: por el formato del primer cuadro).
                "decodifica_con": "gpu" if (self._acel_pedida and self._formato_inicial in _FORMATOS_HW) else "cpu",
            }

        except BaseException:
            # Sin esto un archivo danado dejaba el original abierto (y bloqueado en Windows) hasta cerrar la app.
            try:
                self._contenedor.close()
            except Exception:
                pass
            raise

        # Estado del decoder: generador vivo, indice del ultimo cuadro
        # decodificado y ese mismo cuadro sin convertir (sirve para pedir el
        # mismo cuadro en otro ancho sin volver a decodificar).
        self._generador = None
        self._ultimo = None
        self._cuadro_crudo = None

    # --------------------------------------------------------------- publico

    def info(self) -> dict:
        return dict(self._info)

    def tabla_tiempos(self) -> list:
        """Segundo de cada cuadro. Solo hace falta pedirla si info()['vfr']."""
        return list(self._tiempos)

    def tiempo(self, n: int) -> float:
        """Segundo (desde el primer cuadro) en que se muestra el cuadro n."""
        return self._tiempos[self._acotar(n)]

    def cuadro_de_tiempo(self, t: float) -> int:
        """Cuadro que esta en pantalla en el segundo t."""
        # Un poco de tolerancia: currentTime del <video> puede quedar apenas
        # antes del pts exacto del cuadro.
        i = bisect_right(self._tiempos, float(t) + 1e-4) - 1
        return self._acotar(i)

    def cuadro(self, n: int, ancho: int = 540) -> bytes:
        n = self._acotar(n)
        ancho = _par(min(max(int(ancho), 2), ANCHO_MAXIMO))
        clave = (n, ancho)

        jpg = self._mirar_cache(clave)
        if jpg is not None:
            return jpg

        with self._candado:
            if self._cerrado:
                raise RuntimeError("el video ya fue cerrado")
            # Otro hilo pudo haberlo decodificado mientras esperabamos.
            jpg = self._mirar_cache(clave)
            if jpg is not None:
                return jpg
            crudo = self._decodificar(n)
            jpg = self._a_jpeg(crudo, ancho)
            self._guardar_cache(clave, jpg)
            return jpg

    def cerrar(self) -> None:
        with self._candado:
            if self._cerrado:
                return
            self._cerrado = True
            self._generador = None
            self._cuadro_crudo = None
            self._ultimo = None
            try:
                self._contenedor.close()
            except Exception:
                pass
        with self._candado_cache:
            self._cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cerrar()

    # ----------------------------------------------------------------- indice

    def _acotar(self, n) -> int:
        n = int(n)
        total = len(self._pts)
        if n < 0:
            return 0
        if n >= total:
            return total - 1
        return n

    def _construir_indice(self) -> list:
        """pts de cada cuadro, en orden de presentacion.

        Primero por paquetes (solo demux: 0,2 s para 15 min de video). Se
        verifico contra el decode completo que los pts coinciden uno a uno.
        """
        pts = []
        sin_pts = 0
        paquetes = 0
        lector = av.open(self.ruta, options=_OPCIONES_ABRIR)
        try:
            flujo = next(f for f in lector.streams if f.index == self._flujo.index)
            for paquete in lector.demux(flujo):
                if paquete.size == 0:
                    continue
                paquetes += 1
                if paquete.pts is None:
                    sin_pts += 1
                else:
                    pts.append(paquete.pts)
        finally:
            lector.close()

        if paquetes > 0 and sin_pts / paquetes <= MAX_SIN_PTS and pts:
            pts.sort()
            return pts
        return self._indice_decodificando()

    def _indice_decodificando(self) -> list:
        """Respaldo para contenedores sin pts por paquete: decodifica todo."""
        lector = av.open(self.ruta, options=_OPCIONES_ABRIR)
        pts = []
        try:
            flujo = next(f for f in lector.streams if f.index == self._flujo.index)
            flujo.thread_type = "AUTO"
            ultimo = None
            paso = None
            tasa = flujo.average_rate or flujo.guessed_rate
            if tasa and flujo.time_base:
                paso = int(round(1.0 / (float(tasa) * float(flujo.time_base))))
            for cuadro in lector.decode(flujo):
                if cuadro.pts is not None:
                    ultimo = cuadro.pts
                elif ultimo is not None and paso:
                    ultimo += paso
                else:
                    ultimo = 0
                pts.append(ultimo)
        finally:
            lector.close()
        if not pts:
            raise RuntimeError("no se pudo leer ningun cuadro del video")
        pts.sort()
        return pts

    def _leer_rotacion(self) -> int:
        """Grados que hay que girar el cuadro para mostrarlo derecho (0/90/180/270)."""
        try:
            return self._rotacion_de_primer_cuadro()
        except Exception:
            if not self._acel_pedida:
                return 0
        # La GPU no pudo con este archivo: se vuelve a abrir por el procesador.
        try:
            self._contenedor.close()
        except Exception:
            pass
        self._contenedor, self._acel_pedida = _abrir(self.ruta, None)
        self._flujo = pista_de_video(self._contenedor)
        self._flujo.thread_type = "AUTO"
        try:
            return self._rotacion_de_primer_cuadro()
        except Exception:
            return 0

    def _rotacion_de_primer_cuadro(self) -> int:
        try:
            for cuadro in self._contenedor.decode(self._flujo):
                self._formato_inicial = cuadro.format.name
                grados = getattr(cuadro, "rotation", 0) or 0
                self._contenedor.seek(0, stream=self._flujo, backward=True)
                self._flujo.codec_context.flush_buffers()
                return (int(round(grados / 90.0)) * 90) % 360
        except Exception:
            if self._acel_pedida:
                raise           # que _leer_rotacion reabra el archivo por el procesador
        return 0

    # ----------------------------------------------------------------- cache

    def _mirar_cache(self, clave):
        with self._candado_cache:
            jpg = self._cache.get(clave)
            if jpg is not None:
                self._cache.move_to_end(clave)
            return jpg

    def _guardar_cache(self, clave, jpg: bytes) -> None:
        with self._candado_cache:
            self._cache[clave] = jpg
            self._cache.move_to_end(clave)
            while len(self._cache) > CUADROS_EN_CACHE:
                self._cache.popitem(last=False)

    # --------------------------------------------------------------- decoder

    def _calcular_web(self, contexto) -> bool:
        extension = os.path.splitext(self.ruta)[1].lower()
        if extension not in _CONTENEDORES_WEB:
            return False
        # mp4/m4v/mov comparten el mismo demuxer en ffmpeg; la extension ya
        # descarto 3gp y companhia.
        if "mp4" not in (self._contenedor.format.name or ""):
            return False
        if (contexto.name or "").lower() not in _VIDEO_WEB:
            return False
        formato = getattr(contexto, "format", None)
        if formato is not None and formato.name not in _PIXELES_WEB:
            return False
        for pista in self._contenedor.streams.audio:
            if (pista.codec_context.name or "").lower() not in _AUDIO_WEB:
                return False
        return True

    def _posicionar(self, n: int, margen: float = 0.0) -> None:
        """Salta al keyframe anterior al cuadro n (menos un margen en segundos)."""
        objetivo = self._pts[n] - int(round(margen / float(self._base)))
        if objetivo <= self._pts[0]:
            self._contenedor.seek(0, stream=self._flujo, backward=True)
        else:
            self._contenedor.seek(objetivo, stream=self._flujo, backward=True)
        self._flujo.codec_context.flush_buffers()
        self._generador = self._contenedor.decode(self._flujo)
        self._ultimo = None
        self._cuadro_crudo = None

    def _numerar(self, cuadro) -> int:
        """Indice del cuadro recien decodificado, segun su pts."""
        if self._ultimo is not None:
            siguiente = self._ultimo + 1
            if siguiente < len(self._pts) and cuadro.pts == self._pts[siguiente]:
                return siguiente
        if cuadro.pts is None:
            return 0 if self._ultimo is None else min(self._ultimo + 1, len(self._pts) - 1)
        return min(bisect_left(self._pts, cuadro.pts), len(self._pts) - 1)

    def _decodificar(self, n: int):
        if self._ultimo == n and self._cuadro_crudo is not None:
            return self._cuadro_crudo

        secuencial = (
            self._generador is not None
            and self._ultimo is not None
            and self._ultimo < n <= self._ultimo + SALTO_MAXIMO
        )
        margen = 0.0
        # Algunos contenedores (MPEG-PS) caen despues del keyframe pedido: o el
        # primer cuadro que sale ya pasa de n, o (cerca del final del archivo)
        # no sale ninguno. En los dos casos se reintenta un poco antes.
        for _ in range(8):
            viene_de_seek = not secuencial
            if viene_de_seek:
                self._posicionar(n, margen)
            reintentar = False
            salio_alguno = False
            for cuadro in self._generador:
                salio_alguno = True
                indice = self._numerar(cuadro)
                if self._ultimo is None and indice > n and self._pts[0] < self._pts[n]:
                    reintentar = True
                    break
                self._ultimo = indice
                self._cuadro_crudo = cuadro
                if indice >= n:
                    return cuadro
            if viene_de_seek and not salio_alguno:
                reintentar = True
            if not reintentar:
                break
            secuencial = False
            margen = 1.0 if margen == 0 else margen * 4

        # Se acabo el archivo antes de llegar: devolvemos el ultimo cuadro real.
        self._generador = None
        if self._cuadro_crudo is not None:
            return self._cuadro_crudo

        # Ni un cuadro desde el seek: reintentamos desde el arranque.
        self._posicionar(0)
        for cuadro in self._generador:
            self._ultimo = self._numerar(cuadro)
            self._cuadro_crudo = cuadro
            return cuadro
        raise RuntimeError("no se pudo decodificar ningun cuadro del video")

    def _a_jpeg(self, crudo, ancho: int) -> bytes:
        giro = self._rotacion
        ancho_real = crudo.width or self._info["ancho"]
        alto_real = crudo.height or self._info["alto"]
        # Dimensiones del cuadro YA girado, tal como se va a mostrar.
        if giro in (90, 270):
            vis_ancho, vis_alto = alto_real, ancho_real
        else:
            vis_ancho, vis_alto = ancho_real, alto_real
        alto = _par(ancho * vis_alto / (vis_ancho * self._proporcion_pixel))

        # Regla de oro: reformat primero (swscale en C, ~1 ms); to_image sobre
        # el cuadro a resolucion completa cuesta ~22 ms.
        if giro in (90, 270):
            rgb = crudo.reformat(width=alto, height=ancho, format="rgb24")
        else:
            rgb = crudo.reformat(width=ancho, height=alto, format="rgb24")
        imagen = rgb.to_image()
        # frame.rotation viene en grados antihorarios (matriz de display);
        # verificado contra el autogiro de ffmpeg.
        if giro == 90:
            imagen = imagen.transpose(Image.Transpose.ROTATE_90)
        elif giro == 180:
            imagen = imagen.transpose(Image.Transpose.ROTATE_180)
        elif giro == 270:
            imagen = imagen.transpose(Image.Transpose.ROTATE_270)
        buffer = BytesIO()
        imagen.save(buffer, format="JPEG", quality=CALIDAD_JPEG)
        return buffer.getvalue()
