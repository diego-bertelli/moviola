# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Moviola desde la línea de comandos, sin ventana: para procesar videos de a muchos o desde un script.

    python moviola.py presets
    python moviola.py procesar carpeta\\ --preset reel --salida listos\\
    python moviola.py procesar *.mp4 --preset youtube --sin-subtitulos
    python moviola.py exportar proyecto.moviola --formato vertical --normalizar --subtitulos quemar
    python moviola.py silencios entrevista.mp4
    python moviola.py transcribir entrevista.mp4 --idioma es
    python moviola.py medir entrevista.mp4
    python moviola.py herramientas

Códigos de salida: 0 todo bien, 1 algo falló (en un lote: al menos un archivo), 2 pedido mal escrito, 130 cancelado con Ctrl+C.
Con --json se escribe en la salida estándar un resultado que otro programa puede leer; el avance va a la salida de error.
"""

import argparse
import json
import os
import shutil
import sys
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
_BIN = os.path.join(AQUI, "bin")
if os.path.isdir(_BIN):
    os.environ["PATH"] = _BIN + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, AQUI)

for _flujo in (sys.stdout, sys.stderr):
    if _flujo is not None:
        try:
            _flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from motor import exportar as ex  # noqa: E402
from motor import lotes  # noqa: E402
from motor import proxy  # noqa: E402
from motor import silencios as sil  # noqa: E402
from motor import subtitulos as sub  # noqa: E402
from motor.proyecto import ErrorEdicion  # noqa: E402

CANCELAR = threading.Event()


def _escribir(texto="", fin="\n"):
    if sys.stdout is not None:
        sys.stdout.write(texto + fin)
        sys.stdout.flush()


def _avisar(texto, fin="\n"):
    if sys.stderr is not None:
        sys.stderr.write(texto + fin)
        sys.stderr.flush()


class Avance:
    """Una línea de avance que se reescribe (solo si la salida de error es una consola)."""

    def __init__(self, activo):
        self.activo = activo and sys.stderr is not None and sys.stderr.isatty()
        self.ultimo = ""

    def poner(self, texto):
        if not self.activo:
            return
        _avisar("\r" + texto.ljust(max(len(self.ultimo), len(texto))), fin="")
        self.ultimo = texto

    def cerrar(self):
        if self.activo and self.ultimo:
            _avisar("")
        self.ultimo = ""


def _tiempo(s):
    s = int(round(s))
    return "%d:%02d" % divmod(s, 60) if s < 3600 else "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def _tam(b):
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024 or u == "GB":
            return ("%d %s" % (b, u)) if u == "B" else ("%.1f %s" % (b, u))
        b /= 1024.0


# ------------------------------------------------------------------------------------------- comandos

def cmd_presets(a):
    lista = lotes.lista_presets()
    if a.json:
        _escribir(json.dumps(lista, ensure_ascii=False, indent=1))
        return 0
    for p in lista:
        _escribir("  %-9s %s" % (p["clave"], p["nombre"]))
        _escribir("            " + p["nota"])
        _escribir("            hace: " + ", ".join(p["pasos"]))
    _escribir("\nUsá uno con:  moviola.py procesar ARCHIVOS --preset NOMBRE")
    return 0


def _cambios_de(a):
    c = {}
    if a.sin_silencios:
        c["silencios"] = False
    elif a.silencios:
        c["silencios"] = True
    if a.sin_subtitulos:
        c["subtitulos"] = False
    elif a.con_subtitulos:
        c["subtitulos"] = True
    if a.idioma:
        c["idioma"] = a.idioma
    if a.karaoke:
        c["karaoke"] = True
    if a.normalizar is not None:
        c["normalizar"] = a.normalizar
    for k in ("formato", "encuadre", "perfil", "calidad"):
        if getattr(a, k, None):
            c[k] = getattr(a, k)
    return c


def cmd_procesar(a):
    receta = lotes.preparar_preset(a.preset, _cambios_de(a))
    entradas = lotes.listar_entradas(a.entradas, a.recursivo)
    if not entradas:
        raise lotes.ErrorLote("No encontré ningún video, audio ni proyecto en lo que pasaste.")
    av = Avance(not a.json and not a.callado)
    n = len(entradas)
    _avisar("%s: %d archivo%s" % (receta["nombre"], n, "" if n == 1 else "s"))

    def progreso(i, total, fr, nombre):
        av.poner("[%d/%d] %s  %3d %%" % (i + 1, total, nombre, int(fr * 100)))

    def paso(i, total, p, texto):
        if a.detalle:
            av.cerrar()
            _avisar("[%d/%d] %s" % (i + 1, total, texto))

    r = lotes.procesar_lote(entradas, a.salida, receta, progreso, CANCELAR, paso, continuar=not a.parar_si_falla)
    av.cerrar()
    if a.json:
        _escribir(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    else:
        for x in r["resultados"]:
            if x["ok"]:
                _escribir("  OK     %s -> %s  (%s, %s)" % (os.path.basename(x["origen"]), x["archivo"], _tiempo(x["duracion"]), _tam(os.path.getsize(x["archivo"]))))
                for aviso in x.get("avisos", []):
                    _escribir("         aviso: " + aviso)
            else:
                _escribir("  FALLÓ  %s: %s" % (os.path.basename(x["origen"]), x["error"]))
        _escribir("\n%d bien, %d con error%s." % (r["ok"], r["fallaron"], (", %d cancelados" % r["canceladas"]) if r["canceladas"] else ""))
    if CANCELAR.is_set():
        return 130
    return 0 if r["fallaron"] == 0 and r["canceladas"] == 0 else 1


def cmd_exportar(a):
    p = lotes.proyecto_desde(a.entrada)
    carpeta = a.salida or os.path.join(os.path.dirname(os.path.abspath(a.entrada)), lotes.CARPETA_SALIDA)
    subs = None
    if a.subtitulos:
        subs = {"quemar": False, "srt": False, "vtt": False}
        for x in a.subtitulos.split(","):
            x = x.strip()
            if x not in subs:
                raise lotes.ErrorLote("Los subtítulos se piden como quemar, srt o vtt (separados por coma).")
            subs[x] = True
        if not p.subtitulos["frases"]:
            raise lotes.ErrorLote("Este proyecto no tiene frases de subtítulos: transcribí primero (moviola.py transcribir) o abrí un proyecto que las tenga.")
    av = Avance(not a.json and not a.callado)
    r = ex.exportar(p, carpeta, a.nombre, a.formato, a.encuadre, (0.5, 0.5), bool(a.normalizar), -14.0, None, None,
                    lambda f: av.poner("exportando  %3d %%" % int(f * 100)), CANCELAR, subtitulos=subs, perfil=a.perfil, calidad=a.calidad)
    av.cerrar()
    r["tamano_bytes"] = os.path.getsize(r["archivo"])
    if a.json:
        _escribir(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    else:
        _escribir("Listo: %s  (%s, %s)" % (r["archivo"], _tiempo(r["duracion"]), _tam(r["tamano_bytes"])))
        for s in r.get("subtitulos", []):
            _escribir("       y %s" % s)
    return 0


def cmd_silencios(a):
    p = lotes.proyecto_desde(a.entrada)
    r = sil.analizar(p, a.umbral, a.minimo, a.margen, CANCELAR)
    if a.json:
        _escribir(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    if not r["silencios"]:
        _escribir("No hay silencios de %s s o más por debajo de %s dB." % (a.minimo, a.umbral))
        return 0
    for s in r["silencios"]:
        _escribir("  %s -> %s   (%.1f s)" % (_tiempo(s["inicio"]), _tiempo(s["fin"]), s["fin"] - s["inicio"]))
    _escribir("\n%d silencios, %.1f s en total de %.1f s (%.0f %%)." % (len(r["silencios"]), r["total"], r["duracion"], 100.0 * r["total"] / max(r["duracion"], 0.001)))
    return 0


def cmd_transcribir(a):
    p = lotes.proyecto_desde(a.entrada)
    av = Avance(not a.json and not a.callado)
    frases = sub.transcribir(p, a.idioma, a.letras, CANCELAR, lambda f: av.poner("transcribiendo  %3d %%" % int(f * 100)))
    av.cerrar()
    base = os.path.splitext(os.path.abspath(a.entrada))[0]
    carpeta = a.salida
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
        base = os.path.join(carpeta, os.path.splitext(os.path.basename(a.entrada))[0])
    escritos = []
    if frases:
        dur = p.duracion()
        for ext, texto in ((".srt", sub.a_srt(frases, dur)), (".vtt", sub.a_vtt(frases, dur)), (".txt", "\n".join(f["texto"] for f in frases) + "\n")):
            destino = ex.siguiente_destino(os.path.dirname(base), os.path.basename(base), ext)
            with open(destino, "w", encoding="utf-8") as f:
                f.write(texto)
            escritos.append(destino)
    if a.json:
        _escribir(json.dumps({"frases": frases, "archivos": escritos}, ensure_ascii=False, indent=1))
    elif not frases:
        _escribir("No encontré voz para transcribir.")
    else:
        for f in frases[:6]:
            _escribir("  %s  %s" % (_tiempo(f["inicio"]), f["texto"]))
        if len(frases) > 6:
            _escribir("  … %d frases más" % (len(frases) - 6))
        for e in escritos:
            _escribir("Escribí " + e)
    return 0


def cmd_medir(a):
    p = lotes.proyecto_desde(a.entrada)
    m = ex._medir_volumen(p, -14.0, CANCELAR)
    if not m:
        raise lotes.ErrorLote("No hay sonido para medir (todo está en silencio o silenciado).")
    r = {"lufs": round(float(m["input_i"]), 1), "pico": round(float(m["input_tp"]), 1), "rango": round(float(m["input_lra"]), 1)}
    if a.json:
        _escribir(json.dumps(r))
    else:
        _escribir("Volumen: %s LUFS   pico: %s dB   rango: %s LU    (para redes se apunta a -14 LUFS)" % (r["lufs"], r["pico"], r["rango"]))
    return 0


def cmd_herramientas(a):
    ffm = shutil.which("ffmpeg")
    ffp = shutil.which("ffprobe")
    w, m = sub.buscar_whisper(), sub.buscar_modelo()
    try:
        from motor import descargas
        y = descargas.buscar_ytdlp()
    except Exception:
        y = None
    r = {"ffmpeg": ffm or "", "ffprobe": ffp or "", "whisper": w or "", "modelo_whisper": m or "", "yt_dlp": y or ""}
    if a.json:
        _escribir(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    for k, v, nota in (("ffmpeg", ffm, "hace falta para todo"), ("ffprobe", ffp, "hace falta para todo"),
                       ("whisper-cli", w, "para transcribir y subtitular"), ("modelo de whisper", m, "para transcribir y subtitular"),
                       ("yt-dlp", y, "solo para bajar de YouTube desde la ventana")):
        _escribir("  %-18s %s" % (k, ("sí: " + v) if v else "NO (" + nota + ")"))
    return 0 if (ffm and ffp) else 1


# ------------------------------------------------------------------------------------------- argumentos

def _si_no(p, nombre, ayuda_si, ayuda_no):
    g = p.add_mutually_exclusive_group()
    g.add_argument("--" + nombre, dest=nombre.replace("-", "_"), action="store_true", help=ayuda_si)
    g.add_argument("--sin-" + nombre, dest="sin_" + nombre.replace("-", "_"), action="store_true", help=ayuda_no)


def armar():
    ap = argparse.ArgumentParser(prog="moviola.py", description="Moviola sin ventana: procesar, exportar y analizar videos desde la línea de comandos.",
                                 epilog="Moviola corre todo en tu PC: no usa internet. Más en README.md.")
    sp = ap.add_subparsers(dest="comando", metavar="comando")
    sp.required = True

    def comun(p, salida=True):
        p.add_argument("--json", action="store_true", help="escribe el resultado como JSON en la salida estándar")
        p.add_argument("--callado", action="store_true", help="sin línea de avance")
        if salida:
            p.add_argument("-o", "--salida", help="carpeta donde se escribe (por defecto, «%s» al lado del original)" % lotes.CARPETA_SALIDA)

    p = sp.add_parser("presets", help="muestra las recetas disponibles")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_presets)

    p = sp.add_parser("procesar", help="aplica un preset a uno o muchos archivos (video, audio o .moviola; carpetas y *.mp4 también)")
    p.add_argument("entradas", nargs="+", help="archivos, carpetas o patrones como *.mp4")
    p.add_argument("-p", "--preset", default="reel", help="receta a usar (ver «presets»; por defecto reel)")
    p.add_argument("-r", "--recursivo", action="store_true", help="entrar también a las subcarpetas")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--silencios", action="store_true", help="cortar silencios aunque el preset no lo haga")
    g.add_argument("--sin-silencios", action="store_true", help="no cortar silencios")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--con-subtitulos", action="store_true", help="subtitular aunque el preset no lo haga")
    g.add_argument("--sin-subtitulos", action="store_true", help="no subtitular")
    p.add_argument("--idioma", help="idioma de la voz: es, en, pt, fr, it, de o auto")
    p.add_argument("--karaoke", action="store_true", help="subtítulos que resaltan la palabra que se dice")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--normalizar", dest="normalizar", action="store_const", const=True, default=None, help="nivelar el volumen a -14 LUFS")
    g.add_argument("--no-normalizar", dest="normalizar", action="store_const", const=False, help="dejar el volumen como está")
    p.add_argument("--formato", choices=list(ex.FORMATOS_VIDEO) + list(ex.FORMATOS_AUDIO))
    p.add_argument("--encuadre", choices=("recortar", "barras"))
    p.add_argument("--perfil", choices=list(ex.PERFILES))
    p.add_argument("--calidad", choices=list(ex.CALIDADES))
    p.add_argument("--parar-si-falla", action="store_true", help="en un lote, detenerse en el primer archivo que falle")
    p.add_argument("--detalle", action="store_true", help="contar cada paso (abrir, silencios, transcribir, exportar)")
    comun(p)
    p.set_defaults(f=cmd_procesar)

    p = sp.add_parser("exportar", help="exporta un video, audio o proyecto .moviola tal cual está (sin recetas)")
    p.add_argument("entrada")
    p.add_argument("--formato", default="original", choices=list(ex.FORMATOS_VIDEO) + list(ex.FORMATOS_AUDIO))
    p.add_argument("--encuadre", default="recortar", choices=("recortar", "barras"))
    p.add_argument("--perfil", default="mp4_h264", choices=list(ex.PERFILES))
    p.add_argument("--calidad", default="alta", choices=list(ex.CALIDADES))
    p.add_argument("--normalizar", action="store_true", help="nivelar el volumen a -14 LUFS")
    p.add_argument("--subtitulos", help="quemar, srt, vtt (separados por coma): usa las frases que ya tenga el proyecto")
    p.add_argument("--nombre", help="nombre del archivo (por defecto el del original)")
    comun(p)
    p.set_defaults(f=cmd_exportar)

    p = sp.add_parser("silencios", help="lista los silencios de un archivo (no cambia nada)")
    p.add_argument("entrada")
    p.add_argument("--umbral", type=float, default=-35.0, help="nivel en dB por debajo del cual es silencio (-35)")
    p.add_argument("--minimo", type=float, default=0.5, help="duración mínima en segundos (0.5)")
    p.add_argument("--margen", type=float, default=0.1, help="segundos que se dejan a cada lado (0.1)")
    comun(p, salida=False)
    p.set_defaults(f=cmd_silencios)

    p = sp.add_parser("transcribir", help="escribe .srt, .vtt y .txt con lo que se dice (necesita whisper instalado)")
    p.add_argument("entrada")
    p.add_argument("--idioma", default="es")
    p.add_argument("--letras", type=int, default=32, help="máximo de letras por frase (32)")
    comun(p)
    p.set_defaults(f=cmd_transcribir)

    p = sp.add_parser("medir", help="mide el volumen (LUFS, pico y rango)")
    p.add_argument("entrada")
    comun(p, salida=False)
    p.set_defaults(f=cmd_medir)

    p = sp.add_parser("herramientas", help="dice qué herramientas están instaladas")
    p.add_argument("--json", action="store_true")
    p.set_defaults(f=cmd_herramientas)
    return ap


def main(argv=None):
    ap = armar()
    a = ap.parse_args(argv)
    try:
        return a.f(a)
    except KeyboardInterrupt:
        CANCELAR.set()
        _avisar("\nCancelado.")
        return 130
    except proxy.Cancelado:
        _avisar("Cancelado.")
        return 130
    except (lotes.ErrorLote, ex.ExportError, ErrorEdicion, sub.ErrorSubtitulo, sil.ErrorSilencio) as e:
        if getattr(a, "json", False):
            _escribir(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            _avisar("Error: %s" % e)
        return 1
    except Exception as e:
        _avisar("Error inesperado: %s: %s" % (type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
