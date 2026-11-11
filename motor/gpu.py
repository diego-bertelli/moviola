# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Deteccion REAL de aceleracion por GPU y la politica CPU / GPU / Automatico.

La lista de ffmpeg (`-hwaccels`, `-encoders`) dice lo que la BUILD soporta, no lo que
tiene la PC: en una maquina sin NVIDIA ni Intel igual lista nvenc y qsv. Por eso aca cada
capacidad se prueba de verdad: se codifica un segundo de video con cada codificador y se
decodifica un clip con cada acelerador, y recien ahi se dice "disponible".

Dos cuidados que salieron de medir en la PC de desarrollo:
  - `h264_mf` (Media Foundation) funciona siempre, pero por defecto usa el codificador por
    SOFTWARE de Microsoft. Solo cuenta como GPU si se lo obliga a usar hardware
    (`-hw_encoding 1`).
  - Que un acelerador de decodificacion ande no quiere decir que convenga: en esa PC
    la GPU decodificaba 1080p entre 2,5 y 6 veces mas lento que el procesador. Por eso se mide
    la velocidad y "Automatico" solo usa la GPU donde gana.
"""

from motor import herramienta as _herramienta
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

VERSION = 1
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# (codificador, nombre para mostrar, fabricante que lo trae, argumentos extra del sondeo)
CODIFICADORES = [
    ("h264_nvenc", "NVIDIA NVENC", "NVIDIA", []),
    ("h264_qsv", "Intel Quick Sync", "Intel", []),
    ("h264_amf", "AMD AMF", "AMD", []),
    ("h264_mf", "Media Foundation por hardware", None, ["-hw_encoding", "1"]),
    ("hevc_nvenc", "NVIDIA NVENC (HEVC)", "NVIDIA", []),
    ("hevc_qsv", "Intel Quick Sync (HEVC)", "Intel", []),
    ("hevc_amf", "AMD AMF (HEVC)", "AMD", []),
]
# Para el proxy (H.264), en este orden de preferencia.
PREFERENCIA_H264 = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"]
PREFERENCIA_HEVC = ["hevc_nvenc", "hevc_qsv", "hevc_amf"]

# Aceleradores de decodificacion que se prueban a traves de PyAV (es quien decodifica).
ACELERADORES = ["d3d11va", "dxva2", "cuda", "qsv", "d3d12va"]

_ARGS_CODIFICADOR = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "24", "-b:v", "0", "-profile:v", "high"],
    "h264_qsv": ["-c:v", "h264_qsv", "-global_quality", "24", "-preset", "veryfast", "-profile:v", "high"],
    "h264_amf": ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "24", "-qp_p", "26", "-profile:v", "high"],
    "h264_mf": ["-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "4M"],
}


_ARGS_FINAL = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-profile:v", "high"],
    "h264_qsv": ["-c:v", "h264_qsv", "-global_quality", "19", "-preset", "medium", "-profile:v", "high"],
    "h264_amf": ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21", "-profile:v", "high"],
    "h264_mf": ["-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "12M"],
    # H.265 por hardware (solo para exportar un archivo final en MP4 H.265). Mismos criterios que el H.264.
    "hevc_nvenc": ["-c:v", "hevc_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0"],
    "hevc_qsv": ["-c:v", "hevc_qsv", "-global_quality", "23", "-preset", "medium"],
    "hevc_amf": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "23", "-qp_p", "25"],
}


def args_codificador(nombre, calidad="proxy"):
    """Argumentos de ffmpeg para codificar H.264 con ese codificador por hardware.
    calidad 'proxy' (copia de reproduccion, prioriza velocidad) o 'final' (exportar, prioriza calidad).
    Sin verificar en hardware real: salen de la documentacion de ffmpeg (ver README)."""
    return list((_ARGS_FINAL if calidad == "final" else _ARGS_CODIFICADOR)[nombre])


def _ffmpeg():
    return _herramienta("ffmpeg")


def _correr(args, timeout=30):
    """Devuelve (codigo, lineas_de_error, segundos). Nunca levanta: un controlador roto
    puede colgar ffmpeg, y eso se informa como fallo."""
    t0 = time.time()
    try:
        r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=timeout, creationflags=_SIN_VENTANA)
        return r.returncode, (r.stderr or "").strip().splitlines(), time.time() - t0
    except subprocess.TimeoutExpired:
        return -999, ["se colgó (más de %d s)" % timeout], time.time() - t0
    except OSError as e:
        return -998, [str(e)], time.time() - t0


# ------------------------------------------------------------------ el equipo

def listar_equipo():
    """Placas de video y procesador, tal como los ve Windows."""
    gpus, cpu = [], ""
    try:
        orden = ("$g = Get-CimInstance Win32_VideoController | Select-Object Name,AdapterCompatibility,DriverVersion;"
                 "$c = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name;"
                 "@{gpus=@($g); cpu=$c} | ConvertTo-Json -Compress -Depth 3")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", orden], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=30, creationflags=_SIN_VENTANA)
        datos = json.loads(r.stdout or "{}")
        for g in datos.get("gpus") or []:
            nombre = (g.get("Name") or "").strip()
            if nombre:
                gpus.append({"nombre": nombre, "fabricante": _fabricante(nombre, g.get("AdapterCompatibility") or ""),
                             "controlador": g.get("DriverVersion") or ""})
        cpu = (datos.get("cpu") or "").strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return {"gpus": gpus, "procesador": cpu}


def _fabricante(nombre, compat):
    t = (nombre + " " + compat).lower()
    if "nvidia" in t or "geforce" in t or "quadro" in t:
        return "NVIDIA"
    if "amd" in t or "radeon" in t or "advanced micro" in t:
        return "AMD"
    if "intel" in t:
        return "Intel"
    return compat.strip() or "otro"


def _huella(equipo):
    try:
        v = subprocess.run([_ffmpeg(), "-version"], capture_output=True, encoding="utf-8", errors="replace",
                           timeout=15, creationflags=_SIN_VENTANA).stdout.splitlines()[0]
    except (OSError, IndexError, subprocess.SubprocessError):
        v = "?"
    try:
        import av
        pyav = av.__version__
    except Exception:
        pyav = "?"
    base = "|".join([str(VERSION), v, pyav, equipo["procesador"]] +
                    ["%s:%s" % (g["nombre"], g["controlador"]) for g in equipo["gpus"]])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------- codificacion

def _motivo_codificador(nombre, fabricante, equipo, codigo, lineas):
    """Por que no anduvo, en castellano y sin inventar: se apoya en las placas que hay."""
    if codigo == -999:
        return "El controlador se colgó al probarlo."
    if nombre.endswith("_mf"):
        return "Windows no tiene un codificador de video por hardware (el que trae es solo por software)."
    hay = [g for g in equipo["gpus"] if g["fabricante"] == fabricante]
    if fabricante and not hay:
        return "No hay una placa %s en esta PC." % fabricante
    if hay:
        return ("La %s no ofrece codificación de video por hardware con este controlador. "
                "Hay modelos sin ese bloque, como la RX 6500 XT, y a veces falta el controlador completo." % hay[0]["nombre"]
                if fabricante == "AMD" else
                "La %s no ofrece codificación de video por hardware con este controlador." % hay[0]["nombre"])
    ultima = lineas[-1] if lineas else ""
    return "No se pudo iniciar (%s)." % (re.sub(r"\[[^\]]*\]\s*", "", ultima)[:90] or "sin detalle")


def _sondear_codificadores(equipo, disponibles):
    resultado = {}
    for nombre, etiqueta, fabricante, extra in CODIFICADORES:
        if nombre not in disponibles:
            resultado[nombre] = {"ok": False, "etiqueta": etiqueta, "motivo": "Este ffmpeg no trae ese codificador."}
            continue
        codigo, lineas, seg = _correr(["-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=1", "-frames:v", "10",
                                       "-c:v", nombre, *extra, "-f", "null", "-"], timeout=20)
        if codigo == 0:
            resultado[nombre] = {"ok": True, "etiqueta": etiqueta, "motivo": "", "segundos": round(seg, 2)}
        else:
            resultado[nombre] = {"ok": False, "etiqueta": etiqueta,
                                 "motivo": _motivo_codificador(nombre, fabricante, equipo, codigo, lineas)}
    return resultado


def _nombres_de_codificadores():
    try:
        r = subprocess.run([_ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=20, creationflags=_SIN_VENTANA)
        return set(re.findall(r"^\s*V\S*\s+(\S+)", r.stdout, flags=re.M))
    except (OSError, subprocess.SubprocessError):
        return set()


# ------------------------------------------------------------ decodificacion

def _sondear_decodificacion(tmp):
    """Prueba cada acelerador a traves de PyAV (quien decodifica) y mide si conviene."""
    try:
        import av
        from av.codec.hwaccel import HWAccel, hwdevices_available
        vistos = set(hwdevices_available())
    except Exception as e:
        return {}, "PyAV no pudo consultar los aceleradores: %s" % e

    clips = {}
    for codec, lib in (("h264", "libx264"), ("hevc", "libx265")):
        ruta = os.path.join(tmp, codec + ".mp4")
        c, _, _ = _correr(["-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=5", "-c:v", lib, "-preset", "ultrafast",
                           "-pix_fmt", "yuv420p", ruta], timeout=90)
        if c == 0 and os.path.isfile(ruta):
            clips[codec] = ruta

    def decodificar(ruta, tipo):
        t0 = time.perf_counter()
        if tipo is None:
            cont = av.open(ruta)
        else:
            cont = av.open(ruta, hwaccel=HWAccel(device_type=tipo, allow_software_fallback=False))
        flujo = cont.streams.video[0]
        flujo.thread_type = "AUTO"
        n = sum(1 for _ in cont.decode(flujo))
        cont.close()
        return n, time.perf_counter() - t0

    # Referencia por software, lo mejor de dos corridas.
    base = {}
    for codec, ruta in clips.items():
        base[codec] = min(decodificar(ruta, None)[1] for _ in range(2))

    resultado = {}
    for tipo in ACELERADORES:
        if tipo not in vistos:
            continue
        por_codec = {}
        for codec, ruta in clips.items():
            try:
                n, seg = min((decodificar(ruta, tipo) for _ in range(2)), key=lambda x: x[1])
                if n < 50:
                    raise RuntimeError("solo decodificó %d cuadros" % n)
                razon = seg / base[codec] if base[codec] > 0 else 99.0
                por_codec[codec] = {"ok": True, "segundos": round(seg, 3), "segundos_cpu": round(base[codec], 3),
                                    "veces_mas_lento": round(razon, 2), "conviene": razon < 0.85}
            except Exception as e:
                por_codec[codec] = {"ok": False, "motivo": str(e)[:100]}
        resultado[tipo] = por_codec
    return resultado, ""


# ------------------------------------------------------------------ publico

def detectar():
    """Prueba todo de verdad. Tarda unos segundos: se hace una vez y se guarda."""
    equipo = listar_equipo()
    disponibles = _nombres_de_codificadores()
    tmp = tempfile.mkdtemp(prefix="gpu-")
    try:
        codificadores = _sondear_codificadores(equipo, disponibles)
        decodificadores, nota = _sondear_decodificacion(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    det = {
        "version": VERSION,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "huella": _huella(equipo),
        "gpus": equipo["gpus"],
        "procesador": equipo["procesador"],
        "codificadores": codificadores,
        "decodificadores": decodificadores,
        "nota": nota,
    }
    det["pista"] = _pista_grafico_integrado(equipo)
    return det


def _pista_grafico_integrado(equipo):
    """Un procesador con graficos integrados que Windows no muestra: suele estar apagado en la BIOS."""
    cpu = equipo["procesador"].lower()
    nombres = " ".join(g["nombre"].lower() for g in equipo["gpus"])
    if "radeon graphics" in cpu and "radeon(tm) graphics" not in nombres and "radeon graphics" not in nombres:
        return ("Tu procesador trae gráficos AMD integrados que Windows no está mostrando. Si están desactivados en la "
                "BIOS, activarlos podría habilitar la codificación por hardware. No lo puedo comprobar desde acá.")
    if re.search(r"intel.*(core|pentium|celeron)", cpu) and not any(g["fabricante"] == "Intel" for g in equipo["gpus"]):
        return ("Tu procesador Intel suele traer gráficos integrados (Quick Sync) que Windows no está mostrando. Si están "
                "desactivados en la BIOS, activarlos podría habilitar la codificación por hardware. No lo puedo comprobar desde acá.")
    return ""


def codificador_disponible(det):
    """Primer codificador H.264 por hardware que paso la prueba, o None."""
    if not det:
        return None
    for nombre in PREFERENCIA_H264:
        c = det["codificadores"].get(nombre)
        if c and c["ok"]:
            return nombre
    return None


def codificador_hevc_disponible(det, h264=None):
    """Primer codificador H.265 por hardware que paso la prueba, o None. Con `h264` (el H.264 que se va a usar) se prefiere el
    mismo fabricante."""
    if not det:
        return None
    ok = [n for n in PREFERENCIA_HEVC if (det["codificadores"].get(n) or {}).get("ok")]
    if h264:
        pareja = "hevc_" + h264.split("_", 1)[1] if "_" in h264 else None
        if pareja in ok:
            return pareja
    return ok[0] if ok else None


def acelerador_decodificacion(det, codec=None, solo_si_conviene=False):
    """Mejor acelerador de decodificacion. Con solo_si_conviene, solo si le gana al procesador."""
    if not det:
        return None
    mejor, mejor_ms = None, None
    for tipo, por_codec in det["decodificadores"].items():
        datos = por_codec.get(codec) if codec in por_codec else None
        if datos is None:
            # codecs que no se midieron (mpeg2, vp9...): sin datos, solo en modo GPU explicito
            if solo_si_conviene:
                continue
            datos = next((d for d in por_codec.values() if d.get("ok")), None)
        if not datos or not datos.get("ok"):
            continue
        if solo_si_conviene and not datos.get("conviene"):
            continue
        ms = datos.get("segundos", 0)
        if mejor is None or ms < mejor_ms:
            mejor, mejor_ms = tipo, ms
    return mejor


def resolver(det, modo):
    """Que se usa de verdad para cada tarea, y por que (para mostrarselo a la persona)."""
    modo = modo if modo in ("cpu", "gpu", "auto") else "cpu"
    cod = codificador_disponible(det)
    dec = acelerador_decodificacion(det)
    dec_conviene = acelerador_decodificacion(det, "h264", solo_si_conviene=True) or \
        acelerador_decodificacion(det, "hevc", solo_si_conviene=True)

    if modo == "cpu":
        return {"modo": modo,
                "codificar": {"usa": "cpu", "codificador": None, "motivo": "Elegiste el procesador."},
                "decodificar": {"usa": "cpu", "tipo": None, "motivo": "Elegiste el procesador."}}

    if modo == "gpu":
        codificar = ({"usa": "gpu", "codificador": cod, "motivo": "Elegiste la GPU."} if cod else
                     {"usa": "cpu", "codificador": None, "motivo": "Pediste la GPU, pero esta PC no puede codificar por hardware."})
        decodificar = ({"usa": "gpu", "tipo": dec, "motivo": "Elegiste la GPU."} if dec else
                       {"usa": "cpu", "tipo": None, "motivo": "Pediste la GPU, pero esta PC no puede decodificar por hardware."})
        return {"modo": modo, "codificar": codificar, "decodificar": decodificar}

    codificar = ({"usa": "gpu", "codificador": cod, "motivo": "Automático: la GPU codifica más rápido y para una copia de reproducción no importa la calidad."}
                 if cod else {"usa": "cpu", "codificador": None, "motivo": "Automático: no hay codificación por hardware."})
    if dec_conviene:
        decodificar = {"usa": "gpu", "tipo": dec_conviene, "motivo": "Automático: en esta PC la GPU decodifica más rápido."}
    else:
        decodificar = {"usa": "cpu", "tipo": None,
                       "motivo": "Automático: el procesador decodifica más rápido que la GPU en esta PC." if dec
                       else "Automático: no hay decodificación por hardware."}
    return {"modo": modo, "codificar": codificar, "decodificar": decodificar}


def resumen(det):
    """Lo que se le muestra a la persona: un titulo, lineas y si hay GPU util."""
    if not det:
        return {"titulo": "Comprobando la aceleración por GPU…", "lineas": [], "util": False,
                "puede_codificar": False, "puede_decodificar": False, "nivel": "info"}
    cod = codificador_disponible(det)
    dec = acelerador_decodificacion(det)
    gpus = ", ".join(g["nombre"] for g in det["gpus"]) or "ninguna placa de video detectada"
    lineas = ["Placa de video: %s." % gpus]

    if cod:
        lineas.append("Codificar con GPU: disponible (%s)." % det["codificadores"][cod]["etiqueta"])
    else:
        # Se explica el motivo de la placa que SI hay (no el de una NVIDIA que no existe).
        presentes = {g["fabricante"] for g in det["gpus"]}
        fabricante_de = {n: f for n, _, f, _ in CODIFICADORES}
        motivos = []
        for nombre in PREFERENCIA_H264:
            c = det["codificadores"].get(nombre)
            if c and c["motivo"] and fabricante_de.get(nombre) in presentes:
                motivos.append(c["motivo"])
        for nombre in PREFERENCIA_H264:
            c = det["codificadores"].get(nombre)
            if c and c["motivo"]:
                motivos.append(c["motivo"])
        lineas.append("Codificar con GPU: no disponible. " + (motivos[0] if motivos else ""))

    if dec:
        mas_rapido = acelerador_decodificacion(det, "h264", solo_si_conviene=True) or \
            acelerador_decodificacion(det, "hevc", solo_si_conviene=True)
        if mas_rapido:
            lineas.append("Decodificar con GPU: disponible y más rápido que el procesador.")
        else:
            razones = [d["veces_mas_lento"] for t in det["decodificadores"].values() for d in t.values() if d.get("ok")]
            lineas.append("Decodificar con GPU: disponible, pero en esta PC es %.1f veces más lento que el procesador en 1080p."
                          % (min(razones) if razones else 1.0))
    else:
        lineas.append("Decodificar con GPU: no disponible.")
    if det.get("pista"):
        lineas.append(det["pista"])

    util = bool(cod) or bool(acelerador_decodificacion(det, "h264", True) or acelerador_decodificacion(det, "hevc", True))
    if cod:
        titulo, nivel = "Aceleración por GPU disponible", "ok"
    elif dec:
        titulo, nivel = "La GPU no puede codificar en esta PC", "ojo"
    else:
        titulo, nivel = "Aceleración por GPU no disponible en esta PC", "ojo"
    return {"titulo": titulo, "lineas": lineas, "util": util, "nivel": nivel,
            "puede_codificar": bool(cod), "puede_decodificar": bool(dec)}


# ------------------------------------------------------------------ ajustes

def leer_ajustes(ruta):
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_ajustes(ruta, datos):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)
