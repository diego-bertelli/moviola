# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Subtitulos y escenas en la interfaz, con la ventana REAL.

Uso:  python -I pruebas/prueba_subtitulos_app.py

Se manejan los dialogos como una persona: transcribir (con whisper de verdad si esta instalado), corregir frases, cambiar el estilo,
ver la frase sobre el visor, exportar con subtitulos, y buscar y cortar escenas / negros / congelados.
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
sys.path.insert(0, AQUI)
os.chdir(RAIZ)
os.environ.setdefault("EDITOR_SIN_GPU", "1")
os.environ["EDITOR_AJUSTES"] = os.path.join(tempfile.mkdtemp(prefix="prueba-subtitulos-app-"), "ajustes.json")

import webview  # noqa: E402

import app  # noqa: E402
import prueba_exportar as ex  # noqa: E402
from motor import subtitulos as sub  # noqa: E402

fallos = []


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


def abrir(w, ruta):
    w.evaluate_js("abrir(" + json.dumps(ruta) + ")")
    return esperar(w, "S.ruta === " + json.dumps(ruta) + " && document.getElementById('cargando').hidden", 60)


def clic(w, id_):
    w.evaluate_js("document.getElementById(%s).click()" % json.dumps(id_))
    time.sleep(0.6)


def frases(w):
    return js(w, "S.proy.subtitulos.frases.map(f => ({id: f.id, inicio: f.inicio, fin: f.fin, texto: f.texto}))")


def estilo(w):
    return js(w, "S.proy.subtitulos.estilo")


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
    src = ex.crear_fuente(os.path.join(ex.TMP, "src.mp4"), dur=6)

    print("=== 1. el boton y el dialogo ===")
    e = js(w, "({sub: document.getElementById('btn-subtitulos').disabled, esc: document.getElementById('btn-escenas').disabled})")
    ok(e["sub"] and e["esc"], "sin proyecto, los botones de subtitulos y escenas estan apagados", str(e))
    ok(abrir(w, src), "abre el video")
    e = js(w, "({sub: document.getElementById('btn-subtitulos').disabled, esc: document.getElementById('btn-escenas').disabled})")
    ok(not e["sub"] and not e["esc"], "con un proyecto se prenden")
    clic(w, "btn-subtitulos")
    ok(js(w, "document.getElementById('dlg-subtitulos').open"), "el dialogo se abre")
    e = js(w, """({idiomas: [...document.querySelectorAll('#sub-idioma option')].map(o => o.value), estilo: document.querySelectorAll('#sub-estilo [data-sbk]').length,
                   vacio: !document.getElementById('sub-vacio').hidden, desact: !document.getElementById('sub-desactualizado').hidden,
                   motivo: document.getElementById('sub-motivo').hidden})""")
    ok(e["idiomas"][:2] == ["es", "en"] and "auto" in e["idiomas"] and e["estilo"] == 10 and e["vacio"] and not e["desact"], "trae los idiomas, los 10 ajustes de estilo armados con el catalogo y el aviso de que no hay frases", str(e))
    puede = sub.estado_transcripcion()["disponible"]
    ok(js(w, "document.getElementById('sub-transcribir-ya').disabled") == (not puede), "Transcribir esta prendido solo si hay whisper y modelo", f"disponible={puede}")
    ok(js(w, "document.getElementById('sub-motivo').hidden") == puede, "y si no se puede, explica que falta")

    print("=== 2. frases a mano ===")
    w.evaluate_js("irA(cuadroDe(1.0))")
    time.sleep(0.5)
    clic(w, "sub-agregar")
    f = frases(w)
    ok(len(f) == 1 and abs(f[0]["inicio"] - 1.0) < 0.05 and abs(f[0]["fin"] - 3.0) < 0.05 and f[0]["texto"] == "Escribí acá", "«Agregar una frase acá» la pone en el cursor, de 2 s", str(f))
    ok(js(w, "document.querySelectorAll('#sub-lista .sub__frase').length") == 1 and not js(w, "!document.getElementById('sub-vacio').hidden"), "aparece en la lista y desaparece el cartel de vacio")
    w.evaluate_js("""(() => { const t = document.querySelector('#sub-lista [data-sbf="texto"]'); t.value = 'Hola, esto es una prueba'; t.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.7)
    ok(frases(w)[0]["texto"] == "Hola, esto es una prueba", "cambiar el texto en la lista lo guarda en el proyecto")
    w.evaluate_js("""(() => { const t = document.querySelector('#sub-lista [data-sbf="fin"]'); t.value = '2.5'; t.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.7)
    ok(frases(w)[0]["fin"] == 2.5, "y el tiempo")
    w.evaluate_js("""(() => { const t = document.querySelector('#sub-lista [data-sbf="fin"]'); t.value = '0.5'; t.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.8)
    ok(frases(w)[0]["fin"] == 2.5 and esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5), "un tiempo imposible (final antes del inicio) se rechaza con un aviso y no cambia nada")
    ok(js(w, "document.querySelector('#sub-lista [data-sbf=\"fin\"]').value") == "2.5", "(y la lista vuelve a mostrar el valor bueno)")

    print("=== 3. estilo y vista sobre el visor ===")
    w.evaluate_js("""(() => { const s = document.querySelector('#sub-estilo select[data-sbk="color"]'); s.value = 'coral'; s.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.7)
    w.evaluate_js("""(() => { const c = document.querySelector('#sub-estilo input[data-sbk="mayusculas"]'); c.checked = true; c.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.7)
    w.evaluate_js("""(() => { const r = document.querySelector('#sub-estilo input[data-sbk="tamano"]'); r.value = 9; r.dispatchEvent(new Event('change', {bubbles: true})); })()""")
    time.sleep(0.7)
    est = estilo(w)
    ok(est["color"] == "coral" and est["mayusculas"] is True and est["tamano"] == 9.0, "los ajustes de estilo llegan al proyecto", str(est))
    clic(w, "sub-cerrar")
    ok(not js(w, "document.getElementById('dlg-subtitulos').open"), "Listo cierra el dialogo")
    w.evaluate_js("irA(cuadroDe(1.5))")
    time.sleep(1.0)
    v = js(w, """(() => { const e = document.getElementById('subtitulo-visor'); const m = document.getElementById('capa-cuadro').getBoundingClientRect(); const r = e.getBoundingClientRect();
                         return {oculto: e.hidden, texto: e.textContent, color: getComputedStyle(e).color, tam: parseFloat(getComputedStyle(e).fontSize),
                                 dentro: r.left >= m.left - 2 && r.right <= m.right + 2 && r.bottom <= m.bottom + 2 && r.top >= m.top - 2, abajo: r.bottom > m.top + m.height * 0.7, altoImagen: m.height}; })()""")
    ok(not v["oculto"] and v["texto"] == "HOLA, ESTO ES UNA PRUEBA" and v["color"] == "rgb(255, 109, 90)", "dentro de la frase el visor muestra el texto (en mayusculas y coral)", str(v))
    ok(v["dentro"] and v["abajo"] and abs(v["tam"] - v["altoImagen"] * 0.09) < 2, "sobre la imagen, abajo, y con el tamano pedido (9 % del alto)", str(v))
    w.evaluate_js("irA(cuadroDe(4.0))")
    time.sleep(0.7)
    ok(js(w, "document.getElementById('subtitulo-visor').hidden"), "fuera de la frase se oculta")
    w.evaluate_js("""(() => { S.proy.subtitulos.estilo.posicion = 'arriba'; irA(cuadroDe(1.5)); })()""")
    time.sleep(0.8)
    v = js(w, """(() => { const e = document.getElementById('subtitulo-visor'); const m = document.getElementById('capa-cuadro').getBoundingClientRect(); const r = e.getBoundingClientRect(); return {arriba: r.top < m.top + m.height * 0.3, oculto: e.hidden}; })()""")
    ok(v["arriba"] and not v["oculto"], "con la posicion «Arriba» se dibuja arriba (probado sobre el estado local)")
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(0.8)

    print("=== 4. historial y aviso de «desactualizado» ===")
    w.evaluate_js("operar('subtitulos_poner', [[{inicio: 1, fin: 2, texto: 'uno'}, {inicio: 4, fin: 5, texto: 'dos'}]])")
    time.sleep(0.8)
    ok(len(frases(w)) == 2 and js(w, "S.proy.subtitulos_desactualizados") is False, "poner las frases de una transcripcion (dos): quedan al dia")
    w.evaluate_js("operar('borrar_rango', [2.0, 3.0])")
    time.sleep(0.8)
    ok(js(w, "S.proy.subtitulos_desactualizados") is True, "si se corta el video despues, el proyecto avisa que quedaron corridas")
    clic(w, "btn-subtitulos")
    ok(not js(w, "document.getElementById('sub-desactualizado').hidden"), "y el dialogo muestra el aviso")
    clic(w, "sub-al-dia")
    ok(js(w, "S.proy.subtitulos_desactualizados") is False and js(w, "document.getElementById('sub-desactualizado').hidden"), "«Están bien así» lo apaga")
    w.evaluate_js("""(() => { document.querySelector('#sub-lista [data-sbf="quitar"]').click(); })()""")
    time.sleep(0.8)
    ok(len(frases(w)) == 1, "la ✕ quita una frase")
    clic(w, "sub-borrar-todas")
    ok(frases(w) == [] and js(w, "document.getElementById('sub-borrar-todas').disabled"), "«Borrar todas» las saca (y se apaga solo)")
    clic(w, "sub-cerrar")

    print("=== 5. exportar con subtitulos ===")
    w.evaluate_js("operar('subtitulo_agregar', [1.0, 2.5, 'Hola exportado'])")
    time.sleep(0.8)
    clic(w, "btn-exportar")
    ok(esperar(w, "document.getElementById('dlg-exportar').open && !document.getElementById('exp-armar').hidden", 10), "se abre Exportar")
    e = js(w, "({campo: !document.getElementById('exp-campo-subs').hidden, quemar: !document.getElementById('exp-subs-quemar-campo').hidden})")
    ok(e["campo"] and e["quemar"], "con frases, Exportar ofrece los subtitulos (quemar, .srt y .vtt)", str(e))
    w.evaluate_js("document.querySelector('[data-formato=\"wav\"]').click()")
    time.sleep(0.4)
    ok(js(w, "document.getElementById('exp-subs-quemar-campo').hidden"), "pero «quemar» se esconde si el formato es solo audio")
    w.evaluate_js("document.querySelector('[data-formato=\"original\"]').click()")
    time.sleep(0.4)
    carpeta = tempfile.mkdtemp(prefix="prueba-subs-salida-")
    w.evaluate_js("X.carpeta = %s" % json.dumps(carpeta))
    w.evaluate_js("document.getElementById('exp-subs-quemar').checked = true; document.getElementById('exp-subs-srt').checked = true")
    clic(w, "exp-iniciar")
    ok(esperar(w, "!document.getElementById('exp-resultado').hidden", 120), "exporta")
    res = js(w, "[...document.querySelectorAll('#exp-resultado-lineas li')].map(l => l.textContent)")
    ok(any(x.startswith("Subtítulos: ") and x.endswith(".srt") for x in res), "el resultado lista el .srt que se guardo", str(res))
    arch = [x for x in os.listdir(carpeta) if x.endswith(".mp4")]
    srt = [x for x in os.listdir(carpeta) if x.endswith(".srt")]
    ok(len(arch) == 1 and len(srt) == 1 and "Hola exportado" in open(os.path.join(carpeta, srt[0]), encoding="utf-8").read(), "el .srt esta junto al video y tiene la frase")
    clic(w, "exp-cerrar")

    print("=== 6. transcribir de verdad desde la ventana ===")
    voz = os.path.join(ex.TMP, "voz_ui.wav")
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; try { $s.SelectVoice('Microsoft Pablo') } catch { }; "
          "$s.SetOutputToWaveFile('%s'); $s.Speak('Hola, esto es una prueba de subtítulos.'); $s.Dispose()" % voz)
    r_ = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if not (puede and r_.returncode == 0 and os.path.isfile(voz)):
        print("  SALTEADA  (falta whisper, su modelo o una voz de Windows)")
    else:
        hablado = os.path.join(ex.TMP, "hablado_ui.mp4")
        ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=4,format=yuv420p", "-i", voz, "-filter_complex", "[1:a]aresample=48000,aformat=channel_layouts=mono[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", hablado)
        ok(abrir(w, hablado), "abre un video con una voz")
        clic(w, "btn-subtitulos")
        w.evaluate_js("document.getElementById('sub-idioma').value = 'es'")
        clic(w, "sub-transcribir-ya")
        vio_avance = esperar(w, "!document.getElementById('sub-progreso-texto').hidden && !document.getElementById('sub-cancelar-trans').hidden && document.getElementById('sub-transcribir-ya').hidden", 20)
        ok(vio_avance, "mientras transcribe se ve el avance y el boton Cancelar (y se esconde Transcribir)")
        ok(esperar(w, "S.proy.subtitulos.frases.length > 0", 150), "al terminar las frases entran al proyecto")
        f = frases(w)
        print("      frases:", [(x["inicio"], x["fin"], x["texto"]) for x in f])
        ok(" ".join(x["texto"].lower() for x in f).count("hola") >= 1 and "prueba" in " ".join(x["texto"].lower() for x in f), "con lo que se dijo")
        ok(js(w, "document.getElementById('sub-progreso-texto').hidden") and not js(w, "document.getElementById('sub-transcribir-ya').hidden"), "y el dialogo vuelve a su estado normal")
        ok(js(w, "document.querySelectorAll('#sub-lista .sub__frase').length") == len(f), "la lista las muestra")
        # cancelar una transcripcion
        clic(w, "sub-transcribir-ya")
        esperar(w, "!document.getElementById('sub-cancelar-trans').hidden", 20)
        clic(w, "sub-cancelar-trans")
        ok(esperar(w, "document.getElementById('sub-transcribir-ya').hidden === false && document.getElementById('sub-progreso-texto').hidden", 30), "Cancelar corta la transcripcion y vuelve a Transcribir")
        time.sleep(1.0)
        ok(len(frases(w)) == len(f), "(y no toca las frases que ya habia)")
        clic(w, "sub-cerrar")

    print("=== 7. escenas ===")
    video = os.path.join(ex.TMP, "escenas_ui.mp4")
    ex.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25:d=1.5",
              "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2,hue=h=120,negate", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=0.04,loop=loop=49:size=1",
              "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0,format=yuv420p[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", video)
    ok(abrir(w, video), "abre un video con escenas, un negro y un tramo quieto")
    clic(w, "btn-escenas")
    ok(js(w, "document.getElementById('dlg-escenas').open") and js(w, "document.getElementById('esc-resultado').hidden"), "el dialogo se abre sin resultados")
    clic(w, "esc-analizar")
    ok(esperar(w, "!document.getElementById('esc-resultado').hidden", 60), "Buscar muestra los resultados")
    e = js(w, """({resumen: document.getElementById('esc-resumen').textContent, cortar: document.getElementById('esc-cortar').textContent, negros: !document.getElementById('esc-sacar-negros').hidden,
                   cong: !document.getElementById('esc-sacar-congelados').hidden, mapa: !document.getElementById('esc-mapa').hidden})""")
    ok("3 cambios de escena" in e["resumen"] and "1 tramo negro" in e["resumen"] and "congelado" in e["resumen"] and e["negros"] and e["cong"] and e["mapa"], "dice que encontro 3 cambios, 1 negro y los congelados, y ofrece los tres botones", str(e))
    w.evaluate_js("document.getElementById('esc-umbral').value = 12; document.getElementById('esc-umbral').dispatchEvent(new Event('input', {bubbles: true}))")
    ok(js(w, "document.getElementById('esc-resultado').hidden"), "mover un valor descarta el resultado viejo")
    clic(w, "esc-analizar")
    esperar(w, "!document.getElementById('esc-resultado').hidden", 60)
    n0 = js(w, "S.proy.pistas[0].clips.length")
    clic(w, "esc-sacar-negros")
    ok(esperar(w, "!document.getElementById('dlg-escenas').open", 10) and abs(js(w, "S.proy.duracion") - 6.0) < 0.15, "«Sacar los negros» acorta el video 1,5 s y cierra", str(js(w, "S.proy.duracion")))
    ok(esperar(w, "document.querySelectorAll('#avisos .aviso').length >= 1", 5), "y avisa que Deshacer lo devuelve")
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(1.0)
    clic(w, "btn-escenas")
    clic(w, "esc-analizar")
    esperar(w, "!document.getElementById('esc-resultado').hidden", 60)
    clic(w, "esc-cortar")
    ok(esperar(w, "!document.getElementById('dlg-escenas').open", 10) and js(w, "S.proy.pistas[0].clips.length") == n0 + 3, "«Cortar en los cambios» deja un clip mas por cada cambio (3)", str(js(w, "S.proy.pistas[0].clips.length")))
    w.evaluate_js("operar('deshacer', [])")
    time.sleep(1.0)
    ok(js(w, "S.proy.pistas[0].clips.length") == n0, "y un solo Deshacer los saca todos")

    print("=== 8. errores ===")
    ok(not os.path.exists(os.path.join(RAIZ, "ultimo-error.log")), "no se escribio ultimo-error.log")


def main():
    api = app.API()
    api.cache = os.path.join(tempfile.mkdtemp(prefix="prueba-subtitulos-app-cache-"), "cache")
    srv = app.crear_servidor(api)
    try:
        webview.create_window("prueba", srv.url_inicio(), width=1280, height=860)
        webview.start(correr, webview.windows[0])
    finally:
        api.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
