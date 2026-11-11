# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba de la version PORTATIL: se arma con construir_portatil.py y se la hace trabajar en el peor entorno posible.

Uso:  python -I pruebas/prueba_portatil.py        (arma el paquete: tarda un rato y ocupa ~550 MB en dist\\prueba-portatil)

El paquete corre con SU Python, con el PATH reducido a lo de Windows (sin Python, sin ffmpeg ni ffprobe del sistema) y con
PYTHONPATH apuntando a un lugar que no existe. Adentro se abre un video, se mira que haya miniaturas, se pide un video que
necesita proxy (MPEG-2) y se exporta. Esta prueba existe porque la primera version del paquete llevaba ffmpeg.exe pero no
ffprobe.exe y las miniaturas fallaban en silencio.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


CLIENTE = r'''
import http.client, json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
import shutil
import app

res = {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"), "python": sys.executable,
       "sys_path": sys.path, "datos": app.DATOS}
api = app.API()
srv = app.crear_servidor(api)


def llamar(nombre, *args):
    c = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=120)
    cuerpo = json.dumps(list(args)).encode()
    c.putrequest("POST", "/%s/api/%s" % (srv.token, nombre), skip_host=True)
    for k, v in {"Host": "127.0.0.1:%d" % srv.puerto, "Content-Type": "application/json", "Content-Length": str(len(cuerpo))}.items():
        c.putheader(k, v)
    c.endheaders(cuerpo)
    r = c.getresponse()
    d = json.loads(r.read())
    c.close()
    return d


def esperar(f, tiempo=180):
    t0 = time.time()
    while time.time() - t0 < tiempo:
        v = f()
        if v:
            return v
        time.sleep(0.3)
    return None


mp4, mpg, destino = sys.argv[1:4]
i = llamar("abrir", mp4)
res["abrir_mp4"] = {"error": i.get("error"), "tira": str(i.get("tira", ""))[:22], "cantidad": i.get("tira_cantidad"), "cuadros": i.get("total_cuadros") or i.get("cuadros")}
j = llamar("abrir", mpg)
res["abrir_mpg"] = {"error": j.get("error"), "proxy": j.get("proxy"), "tira": str(j.get("tira", ""))[:22]}
res["proxy_final"] = esperar(lambda: (lambda e: e if e.get("estado") in ("listo", "error") else None)(llamar("proxy_estado")))
llamar("abrir", mp4)
llamar("editar_borrar_rango", 1.0, 2.0)
llamar("exportar_iniciar", {"formato": "vertical", "carpeta": destino, "nombre": "salida"})
res["export"] = esperar(lambda: (lambda e: e if e.get("estado") in ("listo", "error", "cancelado") else None)(llamar("exportar_estado")))
res["archivos_destino"] = sorted(os.listdir(destino))
res["ultimo_error"] = os.path.exists(os.path.join(app.DATOS, "ultimo-error.log"))
api.cerrar()
print("RESULTADO " + json.dumps(res, default=str))
'''


def main():
    from prueba_exportar import crear_fuente, ffmpeg   # fuentes sinteticas (con el ffmpeg del sistema)
    tmp = tempfile.mkdtemp(prefix="prueba-portatil-")
    mp4 = crear_fuente(os.path.join(tmp, "a.mp4"), dur=4)
    mpg = os.path.join(tmp, "b.mpg")
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3", "-c:v", "mpeg2video", "-c:a", "mp2", mpg)
    destino = os.path.join(tmp, "salida")
    os.makedirs(destino)

    paquete = os.path.join(RAIZ, "dist", "prueba-portatil")
    print("=== 1. armar el paquete ===")
    r = subprocess.run([sys.executable, "-I", os.path.join(RAIZ, "construir_portatil.py"), "--destino", paquete], capture_output=True, text=True)
    ok(r.returncode == 0, "construir_portatil.py termina bien", (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else "")
    for rel in ("python/python.exe", "python/pythonw.exe", "bin/ffmpeg.exe", "bin/ffprobe.exe", "app.py", "motor/exportar.py", "web/exportar.js",
                "Moviola.bat", "LEEME.txt", "LICENSE", "LICENCIA.md", "AUTHORS", "licencias/LEEME-LICENCIAS.txt", "licencias/FFmpeg-LICENSE", "licencias/Python-LICENSE.txt"):
        ok(os.path.isfile(os.path.join(paquete, rel)), "trae " + rel)
    ok(not os.path.exists(os.path.join(paquete, "pruebas")) and not os.path.exists(os.path.join(paquete, "ESTADO.md")), "y no trae pruebas ni documentos de trabajo")
    # una segunda vez no pisa lo ajeno: una carpeta que no armo el script se respeta
    ajena = os.path.join(RAIZ, "dist", "ajena-prueba")
    os.makedirs(ajena, exist_ok=True)
    open(os.path.join(ajena, "x.txt"), "w").write("x")
    r2 = subprocess.run([sys.executable, "-I", os.path.join(RAIZ, "construir_portatil.py"), "--destino", ajena], capture_output=True, text=True)
    ok(r2.returncode != 0 and os.path.isfile(os.path.join(ajena, "x.txt")), "no borra una carpeta que no armo el")
    shutil.rmtree(ajena)
    r3 = subprocess.run([sys.executable, "-I", os.path.join(RAIZ, "construir_portatil.py"), "--destino", os.path.join(tmp, "afuera")], capture_output=True, text=True)
    ok(r3.returncode != 0, "y se niega a armar algo fuera de la carpeta del proyecto")

    print("=== 2. correr adentro, en un entorno hostil ===")
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    entorno = {"PATH": os.pathsep.join([os.path.join(windir, "System32"), windir]), "PYTHONPATH": os.path.join(tmp, "no_existe"),
               "SystemRoot": windir, "TEMP": tmp, "TMP": tmp, "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""), "USERPROFILE": os.environ.get("USERPROFILE", "")}
    cliente = os.path.join(tmp, "cliente.py")
    open(cliente, "w", encoding="utf-8").write(CLIENTE)
    p = subprocess.run([os.path.join(paquete, "python", "python.exe"), "-I", cliente, mp4, mpg, destino], capture_output=True, text=True, env=entorno,
                       cwd=tmp, timeout=900)
    linea = next((l for l in p.stdout.splitlines() if l.startswith("RESULTADO ")), None)
    ok(linea is not None, "el programa del paquete corre de punta a punta", (p.stdout + p.stderr)[-600:] if linea is None else "")
    if linea:
        res = json.loads(linea[len("RESULTADO "):])
        pq = paquete.lower()
        ok(res["python"].lower().startswith(pq), "usa el Python del paquete", res["python"])
        ok(all(x.lower().startswith(pq) for x in res["sys_path"] if x), "y no mira ningun otro lugar para importar", str(res["sys_path"]))
        ok(res["ffmpeg"] and res["ffmpeg"].lower().startswith(pq) and res["ffprobe"] and res["ffprobe"].lower().startswith(pq),
           "encuentra el ffmpeg y el ffprobe del paquete (no hay otros en el PATH)", f"{res['ffmpeg']} / {res['ffprobe']}")
        ok(res["datos"].lower() == pq, "escribe sus datos junto al programa", res["datos"])
        ok(not res["abrir_mp4"]["error"] and res["abrir_mp4"]["tira"].startswith("data:image/jpeg") and (res["abrir_mp4"]["cantidad"] or 0) > 0,
           "abre un mp4 y arma la tira de miniaturas (necesita ffmpeg y ffprobe)", str(res["abrir_mp4"]))
        ok(not res["abrir_mpg"]["error"] and res["abrir_mpg"]["proxy"] in ("generando", "listo") and res["proxy_final"] and res["proxy_final"].get("estado") == "listo",
           "abre un MPEG-2 y prepara la copia de reproduccion (proxy)", str(res["abrir_mpg"]) + " " + str(res["proxy_final"]))
        ok(res["export"] and res["export"].get("estado") == "listo" and res["archivos_destino"] == ["salida-v1.mp4"] and res["export"].get("dimensiones") == [1080, 1920],
           "exporta un vertical editado", str(res["export"])[:300])
        ok(not res["ultimo_error"], "y no deja ultimo-error.log")
    shutil.rmtree(paquete, ignore_errors=True)

    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
