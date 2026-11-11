# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Corre TODAS las pruebas, una por una (cada una en su proceso, aislada), y resume.

Uso:  python -I pruebas/correr_todas.py [--sin-portatil] [--solo nombre1,nombre2]

Una prueba pasa si termina con la linea "TODO BIEN". Las pruebas con ventana real abren la interfaz y la manejan solas:
mientras corren conviene no tocar el mouse ni el teclado. Cualquier archivo nuevo "prueba_*.py" se suma solo.
"""

import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
LENTAS = {"prueba_portatil", "prueba_instalador"}      # arman el paquete entero: ~550 MB


def main():
    sin_portatil = "--sin-portatil" in sys.argv
    solo = None
    for a in sys.argv[1:]:
        if a.startswith("--solo"):
            solo = (a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]).split(",")
    pruebas = sorted(f[:-3] for f in os.listdir(AQUI) if f.startswith("prueba_") and f.endswith(".py"))
    # prueba_exportar_api antes que las de ventana, y el paquete al final
    pruebas = [p for p in pruebas if p not in LENTAS] + ([] if sin_portatil else sorted(LENTAS & set(pruebas)))
    if solo:
        pruebas = [p for p in pruebas if p in solo]
    fallaron = []
    t_total = time.time()
    for nombre in pruebas:
        t0 = time.time()
        try:
            # cada prueba con sus propios ajustes, recientes y copia de recuperacion: no tocan los del programa de verdad
            entorno = dict(os.environ)
            entorno.setdefault("EDITOR_AJUSTES", os.path.join(tempfile.mkdtemp(prefix="correr-todas-"), "ajustes.json"))
            r = subprocess.run([sys.executable, "-I", os.path.join(AQUI, nombre + ".py")], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=1800, cwd=RAIZ, env=entorno)
            salida = (r.stdout or "") + (r.stderr or "")
            bien = "TODO BIEN" in salida and r.returncode == 0
            malas = [l.strip() for l in salida.splitlines() if "FALLA" in l or l.startswith("Traceback")][:6]
        except subprocess.TimeoutExpired:
            bien, malas = False, ["se colgo (mas de 30 minutos)"]
        print("%-28s %s  (%d s)" % (nombre, "OK" if bien else "FALLA", time.time() - t0), flush=True)
        if not bien:
            fallaron.append(nombre)
            for m in malas:
                print("      " + m[:200], flush=True)
    print()
    print("%d pruebas en %d s: %s" % (len(pruebas), time.time() - t_total, "TODAS EN VERDE" if not fallaron else "FALLARON " + ", ".join(fallaron)))
    return 1 if fallaron else 0


if __name__ == "__main__":
    sys.exit(main())
