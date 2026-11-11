# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del control de aceleracion (CPU / GPU / Automatico) con la ventana real.

Uso:  python -I pruebas/prueba_gpu_app.py

Cubre el aviso al abrir, el panel, el cambio de modo (que se guarda), "Volver a comprobar"
y, de punta a punta, el aviso cuando se pide GPU y el codificador falla de verdad.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

TMP = tempfile.mkdtemp(prefix="prueba-gpu-app-")
os.environ["EDITOR_AJUSTES"] = os.path.join(TMP, "ajustes.json")
os.environ["EDITOR_SIN_GPU"] = "1"

import webview  # noqa: E402

import app  # noqa: E402
from motor import gpu  # noqa: E402

fallos = []
API = None


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


def js(w, expresion):
    r = w.evaluate_js("JSON.stringify((() => { return " + expresion + "; })())")
    return json.loads(r) if r else None


def esperar(w, condicion, tiempo=30.0, paso=0.2):
    t0 = time.time()
    while time.time() - t0 < tiempo:
        try:
            if js(w, condicion):
                return True
        except Exception:
            pass
        time.sleep(paso)
    return False


def clic(w, selector):
    w.evaluate_js("document.querySelector(%s).click()" % json.dumps(selector))
    time.sleep(0.5)


def amd_sin_motor():
    return {"version": gpu.VERSION, "fecha": "2026-01-01 10:00:00", "huella": "h-amd", "procesador": "CPU",
            "gpus": [{"nombre": "AMD Radeon RX 6500 XT", "fabricante": "AMD", "controlador": "1"}],
            "codificadores": {
                "h264_nvenc": {"ok": False, "etiqueta": "NVIDIA NVENC", "motivo": "No hay una placa NVIDIA en esta PC."},
                "h264_qsv": {"ok": False, "etiqueta": "Intel Quick Sync", "motivo": "No hay una placa Intel en esta PC."},
                "h264_amf": {"ok": False, "etiqueta": "AMD AMF", "motivo": "La AMD Radeon RX 6500 XT no ofrece codificación de video por hardware con este controlador."},
                "h264_mf": {"ok": False, "etiqueta": "Media Foundation por hardware", "motivo": "Windows no tiene un codificador de video por hardware."}},
            "decodificadores": {"d3d11va": {"h264": {"ok": True, "segundos": 1.0, "segundos_cpu": 0.25, "veces_mas_lento": 4.0, "conviene": False},
                                            "hevc": {"ok": True, "segundos": 1.0, "segundos_cpu": 0.3, "veces_mas_lento": 3.0, "conviene": False}}},
            "nota": "", "pista": ""}


def nvidia_que_anda():
    d = amd_sin_motor()
    d["huella"] = "h-nv"
    d["gpus"] = [{"nombre": "NVIDIA GeForce RTX 3060", "fabricante": "NVIDIA", "controlador": "1"}]
    d["codificadores"]["h264_nvenc"] = {"ok": True, "etiqueta": "NVIDIA NVENC", "motivo": ""}
    for v in d["decodificadores"]["d3d11va"].values():
        v.update(veces_mas_lento=0.5, conviene=True)
    return d


def correr(w):
    try:
        _correr(w)
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok(False, "la prueba termino sin excepciones", repr(e))
    finally:
        w.destroy()


def _correr(w):
    time.sleep(3)

    print("=== 1. aviso al abrir (PC como la de Diego: AMD sin motor de video) ===")
    ok(esperar(w, "document.querySelectorAll('.aviso').length > 0", 15), "aparece un aviso al abrir")
    aviso = js(w, "(() => { const a = document.querySelector('.aviso'); return {clase: a.className, texto: a.textContent}; })()")
    ok("aviso--ojo" in aviso["clase"], "es un aviso de 'ojo' (no un error)", aviso["clase"])
    ok("no puede codificar" in aviso["texto"].lower(), "dice que la GPU no puede codificar", aviso["texto"][:70])
    ok("AMD Radeon RX 6500 XT" in aviso["texto"], "nombra la placa que hay")
    ok("más lento" in aviso["texto"], "y que decodificar por GPU es mas lento")
    ok(js(w, "document.getElementById('acel-modo').textContent") == "CPU", "el boton arranca en CPU")
    cfg = gpu.leer_ajustes(os.environ["EDITOR_AJUSTES"])
    ok(cfg.get("aviso_huella") == "h-amd", "queda registrado que ya se aviso para este equipo")
    clic(w, ".aviso__cerrar")

    print("=== 2. el panel ===")
    ok(js(w, "document.getElementById('panel-acel').hidden") is True, "el panel arranca cerrado")
    clic(w, "#btn-acel")
    ok(js(w, "document.getElementById('panel-acel').hidden") is False, "se abre con el boton")
    ok(js(w, "document.getElementById('btn-acel').getAttribute('aria-expanded')") == "true", "y lo informa (aria-expanded)")
    e = js(w, """({titulo: document.getElementById('acel-titulo').textContent,
                   lineas: [...document.querySelectorAll('#acel-lineas li')].map(l => l.textContent),
                   efecto: document.getElementById('acel-efecto').textContent,
                   activo: document.querySelector('.acel__op--activo').dataset.modo,
                   opciones: [...document.querySelectorAll('.acel__op')].map(b => b.textContent)})""")
    ok(e["titulo"] == "La GPU no puede codificar en esta PC", "titulo claro", e["titulo"])
    ok(len(e["lineas"]) >= 3, "con el detalle: placa, codificar, decodificar", str(len(e["lineas"])) + " lineas")
    ok("procesador" in e["efecto"], "y que se usa ahora", e["efecto"][:80])
    ok(e["activo"] == "cpu" and e["opciones"] == ["CPU", "GPU", "Automático"], "tres opciones, CPU marcada", str(e["opciones"]))
    w.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
    time.sleep(0.4)
    ok(js(w, "document.getElementById('panel-acel').hidden") is True, "Escape lo cierra")
    clic(w, "#btn-acel")
    w.evaluate_js("document.getElementById('visor').click()")
    time.sleep(0.4)
    ok(js(w, "document.getElementById('panel-acel').hidden") is True, "un clic afuera lo cierra")

    print("=== 3. cambiar de modo ===")
    clic(w, "#btn-acel")
    clic(w, '.acel__op[data-modo="gpu"]')
    ok(js(w, "document.getElementById('acel-modo').textContent") == "GPU", "elegir GPU actualiza el boton")
    ok(API.modo_acel == "gpu", "y el motor")
    ok(gpu.leer_ajustes(os.environ["EDITOR_AJUSTES"]).get("aceleracion") == "gpu", "y queda guardado en disco")
    ok(js(w, "document.querySelector('.acel__op--activo').dataset.modo") == "gpu"
       and js(w, "document.querySelector('.acel__op[data-modo=\"gpu\"]').getAttribute('aria-checked')") == "true", "la opcion queda marcada")
    ok("no puede codificar" in js(w, "document.getElementById('acel-efecto').textContent").lower()
       or "procesador" in js(w, "document.getElementById('acel-efecto').textContent"),
       "y explica que pedir GPU aca igual codifica con el procesador", js(w, "document.getElementById('acel-efecto').textContent")[:90])
    clic(w, '.acel__op[data-modo="auto"]')
    ok(js(w, "document.getElementById('acel-modo').textContent") == "Auto", "Automatico se muestra como 'Auto'")
    clic(w, '.acel__op[data-modo="cpu"]')

    print("=== 4. 'Volver a comprobar' con una PC distinta (NVIDIA que si anda) ===")
    original = app.gpu_mod.detectar
    app.gpu_mod.detectar = lambda: (time.sleep(1.5), nvidia_que_anda())[1]
    try:
        w.evaluate_js("document.querySelectorAll('.aviso__cerrar').forEach(b => b.click())")
        clic(w, "#btn-acel-recomprobar")
        ok(js(w, "document.getElementById('btn-acel-recomprobar').disabled") is True
           or js(w, "document.getElementById('acel-titulo').textContent").startswith("Comprobando"), "mientras comprueba se nota")
        ok(esperar(w, "document.getElementById('acel-titulo').textContent === 'Aceleración por GPU disponible'", 20),
           "al terminar muestra 'Aceleración por GPU disponible'")
        ok(esperar(w, "document.querySelectorAll('.aviso--info').length > 0", 10), "y avisa con un mensaje informativo (no de error)")
        texto = js(w, "document.querySelector('.aviso--info').textContent")
        ok("NVIDIA NVENC" in texto or "disponible" in texto, "que dice que si hay", texto[:100])
        ok("Podés activarla" in texto, "y como activarla (esta en modo CPU)")
        ok(js(w, "document.getElementById('btn-acel-recomprobar').disabled") is False, "el boton vuelve a habilitarse")
    finally:
        app.gpu_mod.detectar = original
    w.evaluate_js("document.querySelectorAll('.aviso__cerrar').forEach(b => b.click())")
    clic(w, "#btn-acel")

    print("=== 5. de punta a punta: se pide GPU, NVENC 'esta disponible' pero falla de verdad ===")
    API.deteccion = nvidia_que_anda()          # el motor cree que hay NVENC; en esta PC no existe
    clic(w, '.acel__op[data-modo="gpu"]')
    w.evaluate_js("document.getElementById('btn-acel').click()")
    time.sleep(0.3)
    ok(API.gpu_estado()["efectivo"]["codificar"]["codificador"] == "h264_nvenc", "el motor intentaria usar NVENC")
    fuente = os.path.join(TMP, "fuente.mkv")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=5", "-f", "lavfi", "-i",
                    "sine=f=440:d=5", "-c:v", "libx265", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-shortest", fuente], check=True)
    API.cache = os.path.join(TMP, "cache")
    w.evaluate_js("abrir(%s)" % json.dumps(fuente))
    ok(esperar(w, "S.ruta === %s && S.info && S.info.proxy === 'listo'" % json.dumps(fuente), 60), "igual termina de preparar la reproduccion")
    ok(esperar(w, "[...document.querySelectorAll('.aviso')].some(a => a.textContent.includes('se usó el procesador'))", 10),
       "y le dice a la persona que se uso el procesador")
    est = API.proxy_estado()
    ok(est["respaldo"] is True and est["usado"] == "cpu", "el estado del motor lo registra", f"{est['usado']}, respaldo={est['respaldo']}")
    w.evaluate_js("reproducir()")
    time.sleep(2.0)
    e = js(w, """({rep: S.reproduciendo, ct: document.getElementById('capa-video').currentTime,
                   err: document.getElementById('capa-video').error ? document.getElementById('capa-video').error.message : null})""")
    ok(e["rep"] and e["err"] is None and e["ct"] > 1, "y la reproduccion anda igual", f"{e['ct']:.2f} s")
    w.evaluate_js("pausar()")

    print("=== 6. con decodificacion por GPU el video abre y se ve ===")
    API.deteccion = amd_sin_motor()
    h264 = os.path.join(TMP, "h264.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", h264], check=True)
    w.evaluate_js("abrir(%s)" % json.dumps(h264))
    ok(esperar(w, "S.ruta === %s && document.getElementById('cargando').hidden" % json.dumps(h264), 30), "abre con modo GPU")
    ok("decodifica con GPU" in js(w, "document.getElementById('meta-archivo').textContent"), "la cabecera lo indica",
       js(w, "document.getElementById('meta-archivo').textContent"))
    w.evaluate_js("irA(40, 540)")
    time.sleep(0.8)
    ok(js(w, "S.ultimoPintado && S.ultimoPintado.n") == 40, "y el cuadro por cuadro anda")

    print("=== 7. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    global API
    API = app.API()
    API.deteccion = amd_sin_motor()
    API.cache = os.path.join(TMP, "cache0")
    srv = app.crear_servidor(API)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1200, height=820)
        webview.start(correr, webview.windows[0])
    finally:
        API.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
