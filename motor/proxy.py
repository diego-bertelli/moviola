# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Proxy de reproduccion.

El <video> del WebView solo reproduce h264 + aac/mp3 en mp4 (y 4:2:0 de 8 bits). Para
todo lo demas (hevc, mpeg2, prores, vp9, av1, 10 bits, mkv, ac3, opus...) se genera un
proxy: un mp4 h264/aac liviano que SOLO sirve para escuchar y ver correr el video.
El cuadro por cuadro, las miniaturas y el espectro siguen saliendo del archivo original.

Lo importante: el proxy conserva EXACTAMENTE la tabla de tiempos del original (mismos
cuadros, mismos instantes, sin duplicar ni descartar). La interfaz calcula el cuadro de
una pausa con la tabla del original; si el proxy convirtiera un video de framerate
variable a fijo, la pausa mostraria el cuadro equivocado.

  - se desentrelaza (yadif, un cuadro de salida por cada cuadro de entrada);
  - el HDR se pasa a SDR (tonemap), si no sale lavado y gris;
  - la rotacion de celular queda aplicada (ffmpeg la aplica al transcodificar);
  - el audio se mezcla a estereo AAC;
  - se escribe a un .parcial y se renombra al terminar: un proceso interrumpido nunca
    deja un proxy corrupto que despues se reuse.
"""

from motor import herramienta as _herramienta
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time

from motor import gpu as _gpu

# Sube cuando cambia COMO se genera: invalida los proxies viejos del cache.
VERSION = 3

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_HDR = {"smpte2084", "arib-std-b67"}
_ENTRELAZADO = {"tt", "bb", "tb", "bt"}
_RUIDO = re.compile(r"^(frame|fps|stream_\d+_\d+_q|bitrate|total_size|out_time_us|out_time_ms|out_time|"
                    r"dup_frames|drop_frames|speed|progress)=")

# La cadena de tonemap de HDR a SDR que ya usa el proyecto.
_TONEMAP = ("zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=mobius:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def _borrar(ruta, intentos=30):
    """Borra con reintentos: en Windows el archivo sigue bloqueado un instante despues de
    matar ffmpeg, y un os.remove inmediato falla."""
    for _ in range(intentos):
        try:
            os.remove(ruta)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(0.1)
    return False


def _marca(destino):
    return destino + ".ok"


class ProxyError(RuntimeError):
    """No se pudo generar el proxy; el mensaje se puede mostrar a la persona."""


class Cancelado(Exception):
    """La generacion se cancelo (por ejemplo, se abrio otro archivo)."""


_candados = {}
_guardia = threading.Lock()
_memo_info = {}


def _candado(clave):
    with _guardia:
        return _candados.setdefault(clave, threading.Lock())


def _ffmpeg():
    return _herramienta("ffmpeg")


def _ffprobe():
    return _herramienta("ffprobe")


def _numero(texto, defecto=0.0):
    try:
        return float(texto)
    except (TypeError, ValueError):
        return defecto


def sondear(ruta):
    """Lo que hace falta saber del original para decidir como armar el proxy."""
    estado = os.stat(ruta)
    clave = (os.path.abspath(ruta), estado.st_mtime_ns, estado.st_size)
    if clave in _memo_info:
        return _memo_info[clave]
    try:
        r = subprocess.run([_ffprobe(), "-v", "error", "-protocol_whitelist", "file", "-show_format", "-show_streams", "-of", "json", ruta],
                           capture_output=True, encoding="utf-8", errors="replace",
                           creationflags=_SIN_VENTANA, timeout=60)
        datos = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        raise ProxyError("No pude leer el archivo para preparar la reproducción: %s" % e)
    if r.returncode != 0 or "streams" not in datos:
        raise ProxyError("No pude leer el archivo para preparar la reproducción.")

    video = None
    audios = []
    for s in datos["streams"]:
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic"):
            if video is None:
                video = s
        elif s.get("codec_type") == "audio":
            audios.append(s)

    formato = datos.get("format") or {}
    duracion = _numero(formato.get("duration"))
    if duracion <= 0 and video is not None:
        duracion = _numero(video.get("duration"))
    info = {
        "duracion": duracion,
        "inicio_contenedor": _numero(formato.get("start_time")),
        "video": video,
        "audios": audios,
        "hdr": bool(video and video.get("color_transfer") in _HDR),
        "entrelazado": bool(video and video.get("field_order") in _ENTRELAZADO),
    }
    if len(_memo_info) > 64:          # no crece sin limite en una sesion larga
        _memo_info.clear()
    _memo_info[clave] = info
    return info


def _extension(info):
    return ".mp4" if info["video"] is not None else ".m4a"


def ruta_proxy(ruta_original, carpeta_cache, alto_max=720, pista_audio=0):
    """Ruta deterministica del proxy. Si el original cambia, la ruta cambia."""
    estado = os.stat(ruta_original)
    huella = "%d|%s|%d|%d|%d|%d" % (VERSION, os.path.abspath(ruta_original), estado.st_mtime_ns,
                                    estado.st_size, alto_max, pista_audio)
    nombre = hashlib.sha1(huella.encode("utf-8")).hexdigest()[:12]
    base = re.sub(r"[^\w\-]+", "_", os.path.splitext(os.path.basename(ruta_original))[0])[:40] or "medio"
    return os.path.join(carpeta_cache, "%s-%s%s" % (base, nombre, _extension(sondear(ruta_original))))


def _duracion_de(ruta):
    try:
        r = subprocess.run([_ffprobe(), "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration:stream=codec_type",
                            "-of", "json", ruta], capture_output=True, encoding="utf-8", errors="replace",
                           creationflags=_SIN_VENTANA, timeout=30)
        datos = json.loads(r.stdout or "{}")
        tipos = {s.get("codec_type") for s in datos.get("streams", [])}
        return _numero((datos.get("format") or {}).get("duration")), tipos
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0, set()


def hay_proxy(ruta_original, carpeta_cache, alto_max=720, pista_audio=0):
    """Ruta del proxy si existe y esta completo y es de este original; si no, None."""
    destino = ruta_proxy(ruta_original, carpeta_cache, alto_max, pista_audio)
    if not os.path.isfile(destino) or os.path.getsize(destino) == 0:
        return None
    # La marca guarda el tamano con que se termino de escribir. ffprobe NO alcanza para
    # detectar un archivo truncado: con faststart el indice esta al principio, asi que
    # un proxy cortado a la mitad igual informa la duracion completa.
    try:
        with open(_marca(destino), encoding="utf-8") as f:
            marca = json.load(f)
    except (OSError, ValueError):
        return None
    if marca.get("version") != VERSION or marca.get("size") != os.path.getsize(destino):
        return None
    info = sondear(ruta_original)
    duracion, tipos = _duracion_de(destino)
    esperado = "video" if info["video"] is not None else "audio"
    if esperado not in tipos or duracion <= 0:
        return None
    if info["duracion"] > 0 and abs(duracion - info["duracion"]) > max(0.5, 0.02 * info["duracion"]):
        return None
    os.utime(destino, None)          # lo usado hace poco se queda en el cache
    return destino


def _tabla_de(ruta, indice=None):
    """Segundo de cada cuadro de un archivo (solo demux, sin decodificar)."""
    import av
    with av.open(ruta, options={"fflags": "+genpts", "protocol_whitelist": "file"}) as contenedor:
        flujo = next(f for f in contenedor.streams
                     if (f.index == indice if indice is not None else f.type == "video"))
        pts = sorted(p.pts for p in contenedor.demux(flujo) if p.size and p.pts is not None)
        base = float(flujo.time_base)
    if not pts:
        return []
    return [(x - pts[0]) * base for x in pts]


def _comprobar_tabla(ruta_original, info, ruta_proxy):
    """El proxy tiene que tener los mismos cuadros en los mismos instantes. Un codificador por
    hardware puede reordenar o re-estampar distinto: si no coincide, no sirve."""
    a = _tabla_de(ruta_original, info["video"]["index"])
    b = _tabla_de(ruta_proxy)
    if len(a) != len(b):
        raise ProxyError("La GPU generó %d cuadros en lugar de %d." % (len(b), len(a)))
    difs = [abs(x - y) for x, y in zip(a, b)]
    if difs and (max(difs) > 0.040 or sum(1 for d in difs if d > 0.002) > max(3, len(difs) // 1000)):
        raise ProxyError("La GPU generó tiempos distintos a los del original.")


def _filtro_video(info, alto_max):
    pasos = []
    if info["entrelazado"]:
        # mode=0: un cuadro de salida por cada cuadro de entrada (no duplica los fps).
        pasos.append("yadif=mode=0:parity=-1:deint=1")
    # El lado CORTO queda en alto_max como mucho, sin agrandar; ancho y alto pares.
    pasos.append("scale=w='if(gt(iw,ih),-2,min(%d,iw))':h='if(gt(iw,ih),min(%d,ih),-2)'" % (alto_max, alto_max))
    if info["hdr"]:
        pasos.append(_TONEMAP)
    pasos.append("format=yuv420p")
    # El tiempo del primer cuadro pasa a ser 0 y los tiempos se obligan a ser
    # ESTRICTAMENTE crecientes. Hay videos reales (capturas de pantalla, WhatsApp) cuyo
    # decoder entrega algun cuadro con el tiempo 13 ms hacia atras: sin esto el
    # codificador se atasca (dts +1 tick por cuadro) y arrastra un atraso de mas de un
    # segundo hasta el final. Con esto el desvio queda en esos pocos milisegundos.
    pasos.append("setpts='if(isnan(PREV_OUTPTS),PTS-STARTPTS,max(PTS-STARTPTS,PREV_OUTPTS+1))'")
    return ",".join(pasos)


def _armar_comando(ruta, parcial, info, alto_max, pista_audio, codificador=None):
    cmd = [_ffmpeg(), "-v", "error", "-y", "-nostdin"]
    video = info["video"]
    # La tabla de tiempos de la interfaz arranca en el PRIMER CUADRO. Si el contenedor
    # arranca antes, se salta esa diferencia en la entrada (tambien recorta el audio).
    if video is not None:
        corrimiento = _numero(video.get("start_time")) - info["inicio_contenedor"]
        if corrimiento > 0.001:
            cmd += ["-ss", "%.6f" % corrimiento]
    # +igndts: sin esto, apenas un cuadro trae el pts 13 ms hacia atras, ffmpeg desconfia
    # de TODOS los pts y pasa a usar el dts del paquete. En capturas de pantalla y videos
    # de WhatsApp el pts va ~1,25 s adelantado del dts, y el proxy quedaba con ese atraso
    # hasta el final (medido en un video real de 15 min). Ignorando el dts, usa siempre el pts.
    cmd += ["-fflags", "+igndts", "-protocol_whitelist", "file", "-i", ruta]
    audios = info["audios"]
    audio = audios[pista_audio] if 0 <= pista_audio < len(audios) else (audios[0] if audios else None)
    if video is not None:
        if codificador:
            # Codificador por hardware (nvenc, qsv, amf...). No se fuerza el formato de pixel: cada
            # uno acepta el suyo y ffmpeg inserta la conversion.
            codec = _gpu.args_codificador(codificador)
        else:
            codec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high",
                     "-pix_fmt", "yuv420p"]
        cmd += ["-map", "0:%d" % video["index"], "-vf", _filtro_video(info, alto_max)] + codec + [
                # Sin duplicar ni descartar cuadros: la tabla de tiempos queda igual a la original.
                # Base de tiempo fina (1/90000) para no redondear los instantes de un VFR.
                "-fps_mode", "passthrough", "-enc_time_base", "1/90000",
                "-video_track_timescale", "90000", "-movflags", "+faststart"]
    else:
        cmd += ["-vn"]
    if audio is not None:
        cmd += ["-map", "0:%d" % audio["index"], "-c:a", "aac",
                "-b:a", "160k" if video is not None else "192k", "-ac", "2", "-ar", "48000"]
    else:
        cmd += ["-an"]
    cmd += ["-sn", "-dn", "-progress", "pipe:1", "-nostats", parcial]
    return cmd


def generar(ruta_original, carpeta_cache, al_progresar=None, alto_max=720, pista_audio=0, cancelar=None,
            codificador=None):
    """Genera (o reutiliza) el proxy. Devuelve
    {"archivo", "duracion", "reusado", "usado": "cpu"|"gpu", "respaldo": bool, "motivo_respaldo": str}.

    al_progresar(fraccion): se llama con valores crecientes de 0.0 a 1.0.
    cancelar: threading.Event; si se activa, se corta ffmpeg y se levanta Cancelado.
    codificador: nombre de un codificador H.264 por hardware (motor/gpu.py), o None para el
      procesador. Si el codificador por hardware falla, o produce tiempos que no coinciden
      con el original, se REPITE con el procesador y se avisa en "respaldo": nunca se deja a la
      persona sin reproduccion por culpa de la GPU.
    Es seguro llamarlo desde un hilo. Dos llamadas a la vez para el mismo archivo no
    transcodifican dos veces: la segunda espera y reutiliza el resultado de la primera.
    """
    if not os.path.isfile(ruta_original):
        raise ProxyError("No encontré el archivo.")
    os.makedirs(carpeta_cache, exist_ok=True)
    destino = ruta_proxy(ruta_original, carpeta_cache, alto_max, pista_audio)

    with _candado(destino):
        existente = hay_proxy(ruta_original, carpeta_cache, alto_max, pista_audio)
        if existente:
            if al_progresar:
                al_progresar(1.0)
            return {"archivo": existente, "duracion": _duracion_de(existente)[0], "reusado": True,
                    "usado": "cpu", "respaldo": False, "motivo_respaldo": ""}

        info = sondear(ruta_original)
        if info["video"] is None and not info["audios"]:
            raise ProxyError("El archivo no tiene video ni audio que se pueda reproducir.")
        parcial = destino[:-4] + ".parcial" + destino[-4:]
        _borrar(parcial)
        _borrar(_marca(destino))
        total_us = max(info["duracion"], 0.001) * 1_000_000
        emitido = [0.0]

        def avisar(fraccion):
            # El progreso nunca retrocede, aunque haya que repetir el trabajo con el procesador.
            if al_progresar and fraccion >= emitido[0]:
                emitido[0] = fraccion
                al_progresar(fraccion)

        def ejecutar(cod):
            cmd = _armar_comando(ruta_original, parcial, info, alto_max, pista_audio, cod)
            proceso = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
            errores = []
            try:
                for linea in proceso.stdout:
                    linea = linea.strip()
                    if cancelar is not None and cancelar.is_set():
                        proceso.kill()
                        raise Cancelado()
                    if linea.startswith("out_time_us="):
                        valor = linea.split("=", 1)[1]
                        if valor.lstrip("-").isdigit():
                            avisar(min(0.999, max(0.0, int(valor) / total_us)))
                    elif linea and not _RUIDO.match(linea):
                        errores.append(linea)
                proceso.wait()
            except BaseException:
                if proceso.poll() is None:
                    proceso.kill()
                    proceso.wait()
                _borrar(parcial)
                raise
            if proceso.returncode != 0:
                _borrar(parcial)
                detalle = (errores[-1] if errores else "ffmpeg terminó con error %s" % proceso.returncode)[:160]
                raise ProxyError("No pude preparar la reproducción de este archivo. %s" % detalle)

        usado, respaldo, motivo = "cpu", False, ""
        if codificador and info["video"] is not None:
            try:
                ejecutar(codificador)
                _comprobar_tabla(ruta_original, info, parcial)
                usado = "gpu"
            except Cancelado:
                raise
            except ProxyError as e:
                # Los mensajes propios ("La GPU genero tiempos distintos...") se muestran tal cual; el volcado
                # tecnico de ffmpeg no: se reemplaza por una frase clara.
                respaldo = True
                motivo = (str(e) if str(e).startswith("La GPU")
                          else "El codificador por hardware (%s) no funcionó en esta PC." % codificador)
                _borrar(parcial)
        if usado == "cpu":
            ejecutar(None)

        duracion, tipos = _duracion_de(parcial)
        if duracion <= 0 or not tipos:
            _borrar(parcial)
            raise ProxyError("La reproducción preparada salió vacía.")
        os.replace(parcial, destino)
        with open(_marca(destino) + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"version": VERSION, "size": os.path.getsize(destino), "duracion": duracion}, f)
        os.replace(_marca(destino) + ".tmp", _marca(destino))
        if al_progresar:
            al_progresar(1.0)
        return {"archivo": destino, "duracion": duracion, "reusado": False,
                "usado": usado, "respaldo": respaldo, "motivo_respaldo": motivo}


def limpiar(carpeta_cache, max_bytes=5 * 1024 ** 3):
    """Borra .parcial viejos y, si el cache pasa de max_bytes, los proxies menos usados."""
    if not os.path.isdir(carpeta_cache):
        return 0
    borrados = 0
    archivos = []
    ahora = time.time()
    for nombre in os.listdir(carpeta_cache):
        ruta = os.path.join(carpeta_cache, nombre)
        if not os.path.isfile(ruta):
            continue
        if ".parcial." in nombre and ahora - os.path.getmtime(ruta) > 3600:
            _borrar(ruta)
            borrados += 1
        elif nombre.endswith((".mp4", ".m4a")) and ".parcial." not in nombre:
            archivos.append((os.path.getmtime(ruta), os.path.getsize(ruta), ruta))
    total = sum(a[1] for a in archivos)
    for _, tam, ruta in sorted(archivos):
        if total <= max_bytes:
            break
        _borrar(ruta)
        _borrar(_marca(ruta))
        total -= tam
        borrados += 1
    return borrados
