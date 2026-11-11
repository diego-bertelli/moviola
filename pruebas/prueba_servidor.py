# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Prueba del servidor local (motor/servidor.py): rutas, seguridad y Range.

Uso:  python -I pruebas/prueba_servidor.py

No abre ventana. Cada defensa se prueba atacandola: token falso, Host falso (DNS
rebinding), Origin ajeno, Content-Type de formulario, rutas que se escapan de web/,
cuerpos enormes, JSON roto y rangos fuera de lugar.
"""

import http.client
import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

from motor.servidor import ServidorLocal  # noqa: E402

fallos = []


def ok(cond, etiqueta, extra=""):
    print(("  OK    " if cond else "  FALLA ") + etiqueta + (f"   {extra}" if extra else ""), flush=True)
    if not cond:
        fallos.append(etiqueta)


JPEG_FALSO = b"\xff\xd8\xff\xe0" + b"fakejpeg" * 20 + b"\xff\xd9"


def cuadro(n, ancho):
    if n < 0:
        return None
    return JPEG_FALSO + str(n).encode() + b"/" + str(ancho).encode()


def pedir(servidor, metodo, ruta, cuerpo=None, cabeceras=None, host=None):
    """Hace un pedido crudo (sin que urllib normalice la ruta)."""
    c = http.client.HTTPConnection("127.0.0.1", servidor.puerto, timeout=10)
    h = dict(cabeceras or {})
    c.putrequest(metodo, ruta, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", host or f"127.0.0.1:{servidor.puerto}")
    for k, v in h.items():
        c.putheader(k, v)
    if cuerpo is not None:
        c.putheader("Content-Length", str(len(cuerpo)))
    c.endheaders(cuerpo)
    r = c.getresponse()
    datos = r.read()
    cab = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, cab, datos


def main():
    tmp = tempfile.mkdtemp(prefix="prueba-servidor-")
    web = os.path.join(tmp, "web")
    os.makedirs(web)
    with open(os.path.join(web, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><title>hola</title>")
    with open(os.path.join(web, "app.js"), "w", encoding="utf-8") as f:
        f.write("console.log(1)")
    with open(os.path.join(web, "estilo.css"), "w", encoding="utf-8") as f:
        f.write("body{}")
    with open(os.path.join(web, "secreto.py"), "w", encoding="utf-8") as f:
        f.write("TOKEN = 1")
    with open(os.path.join(tmp, "fuera.js"), "w", encoding="utf-8") as f:
        f.write("// fuera de web/")

    medio = os.path.join(tmp, "pista.flac")
    contenido = bytes(range(256)) * 400            # 102400 bytes
    with open(medio, "wb") as f:
        f.write(contenido)

    registro = []
    srv = ServidorLocal(web, {"ping": lambda x=None: {"eco": x}}, cuadro, registro.append)
    T = srv.token
    print(f"puerto {srv.puerto}")

    print("=== 1. solo escucha en loopback ===")
    ok(srv.srv.server_address[0] == "127.0.0.1", "direccion 127.0.0.1 (no 0.0.0.0)", srv.srv.server_address[0])

    print("=== 2. la interfaz y su politica CSP ===")
    s, cab, cuerpo = pedir(srv, "GET", f"/{T}/index.html")
    ok(s == 200 and b"hola" in cuerpo, "GET index.html")
    ok("default-src 'none'" in cab.get("content-security-policy", "") and "connect-src 'self'" in cab.get("content-security-policy", ""),
       "lleva CSP que prohibe cargar cosas de afuera")
    ok(cab.get("x-content-type-options") == "nosniff" and cab.get("cache-control") == "no-store", "nosniff y no-store")
    s, _, _ = pedir(srv, "GET", f"/{T}/")
    ok(s == 200, "la raiz del token sirve el index")
    s, cab, _ = pedir(srv, "GET", f"/{T}/app.js")
    ok(s == 200 and cab["content-type"].startswith("text/javascript"), "app.js con su tipo")
    s, cab, _ = pedir(srv, "GET", f"/{T}/estilo.css")
    ok(s == 200 and cab["content-type"].startswith("text/css"), "estilo.css con su tipo")
    s, _, cuerpo = pedir(srv, "HEAD", f"/{T}/index.html")
    ok(s == 200 and cuerpo == b"", "HEAD no manda cuerpo")

    print("=== 3. token ===")
    for etiqueta, ruta in (("sin token", "/index.html"), ("token falso", "/falso/index.html"),
                           ("token parcial", f"/{T[:-3]}/index.html"), ("raiz sola", "/")):
        s, _, _ = pedir(srv, "GET", ruta)
        ok(s == 404, f"{etiqueta} -> 404", s)

    print("=== 4. Host (DNS rebinding) ===")
    s, _, _ = pedir(srv, "GET", f"/{T}/index.html", host="evil.example.com")
    ok(s == 421, "Host ajeno -> 421", s)
    s, _, _ = pedir(srv, "GET", f"/{T}/index.html", host=f"evil.example.com:{srv.puerto}")
    ok(s == 421, "Host ajeno con nuestro puerto -> 421", s)
    s, _, _ = pedir(srv, "GET", f"/{T}/index.html", host=f"localhost:{srv.puerto}")
    ok(s == 200, "localhost:puerto si se acepta", s)

    print("=== 5. rutas que intentan salirse de web/ ===")
    ataques = {
        "../ crudo": f"/{T}/../fuera.js",
        "..%2f": f"/{T}/..%2ffuera.js",
        "%2e%2e/": f"/{T}/%2e%2e/fuera.js",
        "doble ..": f"/{T}/../../fuera.js",
        "contrabarra": f"/{T}/..\\fuera.js",
        "ruta absoluta": f"/{T}//Windows/win.ini",
        "unidad": f"/{T}/C:/Windows/win.ini",
        "extension no permitida (.py)": f"/{T}/secreto.py",
        "subcarpeta inexistente": f"/{T}/otra/app.js",
    }
    for etiqueta, ruta in ataques.items():
        s, _, cuerpo = pedir(srv, "GET", ruta)
        ok(s == 404 and b"fuera de web" not in cuerpo and b"TOKEN" not in cuerpo and b"[fonts]" not in cuerpo,
           f"{etiqueta} -> 404", s)

    print("=== 6. API ===")
    cab_json = {"Content-Type": "application/json"}
    s, cab, cuerpo = pedir(srv, "POST", f"/{T}/api/ping", json.dumps(["hola ñ"]).encode(), cab_json)
    ok(s == 200 and json.loads(cuerpo) == {"eco": "hola ñ"}, "POST /api/ping devuelve JSON (con tildes)", cuerpo[:40])
    s, _, _ = pedir(srv, "POST", f"/{T}/api/ping", b"[1]", {**cab_json, "Origin": "http://evil.example.com"})
    ok(s == 403, "Origin ajeno -> 403", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/ping", b"[1]", {**cab_json, "Origin": f"http://127.0.0.1:{srv.puerto}"})
    ok(s == 200, "Origin propio -> 200", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/ping", b"x=1", {"Content-Type": "application/x-www-form-urlencoded"})
    ok(s == 415, "formulario (CSRF clasico) -> 415", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/ping", b"[1]", {"Content-Type": "text/plain"})
    ok(s == 415, "text/plain (peticion 'simple' cross-site) -> 415", s)
    s, _, _ = pedir(srv, "GET", f"/{T}/api/ping")
    ok(s == 405, "GET a la API -> 405", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/no_existe", b"[]", cab_json)
    ok(s == 404, "metodo que no esta en la lista -> 404", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/__class__", b"[]", cab_json)
    ok(s == 404, "metodo magico -> 404", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/ping", b"{no es json", cab_json)
    ok(s == 400, "JSON roto -> 400", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/api/ping", b'{"a": 1}', cab_json)
    ok(s == 400, "JSON que no es lista -> 400", s)
    s, _, _ = pedir(srv, "POST", "/falso/api/ping", b"[]", cab_json)
    ok(s == 404, "API con token falso -> 404", s)
    c = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=10)
    c.putrequest("POST", f"/{T}/api/ping", skip_host=True)
    c.putheader("Host", f"127.0.0.1:{srv.puerto}")
    c.putheader("Content-Type", "application/json")
    c.putheader("Content-Length", "50000000")
    c.endheaders()
    r = c.getresponse()
    ok(r.status == 413, "cuerpo declarado de 50 MB -> 413 (no lo lee)", r.status)
    c.close()
    s, _, cuerpo = pedir(srv, "POST", f"/{T}/api/latido", b"[]", cab_json)
    ok(s == 200 and srv.segundos_sin_latido() is not None and srv.segundos_sin_latido() < 2, "latido registrado")

    print("=== 7. cuadros ===")
    s, cab, cuerpo = pedir(srv, "GET", f"/{T}/frame?n=7&w=320")
    ok(s == 200 and cab["content-type"] == "image/jpeg" and cuerpo.endswith(b"7/320"), "GET /frame devuelve la imagen pedida")
    s, _, _ = pedir(srv, "GET", f"/{T}/frame?n=abc&w=320")
    ok(s == 400, "parametro que no es numero -> 400", s)
    s, _, _ = pedir(srv, "GET", f"/{T}/frame?n=-1&w=320")
    ok(s == 404, "cuadro inexistente -> 404", s)
    s, _, _ = pedir(srv, "POST", f"/{T}/frame?n=1&w=1", b"[]", cab_json)
    ok(s == 405, "POST a /frame -> 405", s)

    print("=== 8. medio con Range ===")
    url = srv.publicar(medio)
    ruta_medio = url.split(f":{srv.puerto}", 1)[1]
    s, cab, cuerpo = pedir(srv, "GET", ruta_medio)
    ok(s == 200 and cuerpo == contenido and cab["accept-ranges"] == "bytes", "archivo completo")
    ok(cab["content-type"] == "audio/flac", "un .flac sale como audio/flac", cab["content-type"])
    s, cab, cuerpo = pedir(srv, "GET", ruta_medio, cabeceras={"Range": "bytes=1000-1999"})
    ok(s == 206 and cuerpo == contenido[1000:2000] and cab["content-range"] == "bytes 1000-1999/102400", "rango del medio")
    s, _, cuerpo = pedir(srv, "GET", ruta_medio, cabeceras={"Range": "bytes=102300-"})
    ok(s == 206 and cuerpo == contenido[102300:], "rango abierto (bytes=N-)")
    s, _, cuerpo = pedir(srv, "GET", ruta_medio, cabeceras={"Range": "bytes=-500"})
    ok(s == 206 and cuerpo == contenido[-500:], "ultimos N bytes (bytes=-N)")
    s, _, _ = pedir(srv, "GET", ruta_medio, cabeceras={"Range": "bytes=999999-"})
    ok(s == 416, "rango fuera del archivo -> 416", s)
    s, _, cuerpo = pedir(srv, "HEAD", ruta_medio)
    ok(s == 200 and cuerpo == b"", "HEAD del medio")
    falsa = ruta_medio.replace(srv.medio_token, "tokenfalso")
    s, _, _ = pedir(srv, "GET", falsa)
    ok(s == 404, "token del medio falso -> 404", s)
    url2 = srv.publicar(medio)
    s, _, _ = pedir(srv, "GET", ruta_medio)
    ok(s == 404 and url2 != url, "al publicar otro archivo la URL anterior deja de servir", s)
    s, _, _ = pedir(srv, "GET", url2.split(f":{srv.puerto}", 1)[1], host="evil.example.com")
    ok(s == 421, "el medio tambien exige Host valido", s)

    print("=== 8b. una misma conexion con pedidos mezclados (como un navegador) ===")
    # Regresion: un POST respondido SIN leer su cuerpo dejaba bytes sobrantes en la
    # conexion, y el pedido siguiente llegaba como "[]GET ..." y volvia con 501. Las
    # pruebas anteriores abrian una conexion nueva por pedido y no lo veian.
    conexion = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=10)
    secuencia = [
        ("POST", f"/{T}/api/latido", b"[]", cab_json, 200),
        ("GET", f"/{T}/frame?n=1&w=10", None, {}, 200),
        ("POST", f"/{T}/api/no_existe", b"[1,2,3]", cab_json, 404),
        ("GET", f"/{T}/frame?n=2&w=10", None, {}, 200),
        ("POST", f"/{T}/api/ping", b"abc", {"Content-Type": "text/plain"}, 415),
        ("GET", f"/{T}/frame?n=3&w=10", None, {}, 200),
        ("POST", f"/{T}/api/ping", b"[1]", {**cab_json, "Origin": "http://evil.example.com"}, 403),
        ("GET", url2.split(f":{srv.puerto}", 1)[1], None, {"Range": "bytes=0-99"}, 206),
        ("POST", f"/{T}/api/ping", b"{roto", cab_json, 400),
        ("POST", "/falso/api/ping", b"[1,2,3,4,5]", cab_json, 404),
        ("POST", f"/{T}/frame?n=1&w=1", b"[1,2]", cab_json, 405),
        ("GET", f"/{T}/index.html", None, {}, 200),
        ("POST", f"/{T}/api/ping", b'["ok"]', cab_json, 200),
    ]
    mal = []
    for i, (metodo, ruta, cuerpo, cabeceras, esperado) in enumerate(secuencia, 1):
        conexion.putrequest(metodo, ruta, skip_host=True, skip_accept_encoding=True)
        conexion.putheader("Host", f"127.0.0.1:{srv.puerto}")
        for k, v in cabeceras.items():
            conexion.putheader(k, v)
        if cuerpo is not None:
            conexion.putheader("Content-Length", str(len(cuerpo)))
        conexion.endheaders(cuerpo)
        r = conexion.getresponse()
        r.read()
        if r.status != esperado:
            mal.append(f"#{i} {metodo} esperaba {esperado}, dio {r.status}")
    conexion.close()
    ok(not mal, f"{len(secuencia)} pedidos seguidos en UNA conexion, todos con su codigo", "; ".join(mal))

    print("=== 9. errores internos no filtran detalles ===")
    srv.cuadro = lambda n, w: 1 / 0
    s, _, cuerpo = pedir(srv, "GET", f"/{T}/frame?n=1&w=1")
    ok(s == 500 and b"ZeroDivision" not in cuerpo and b"Traceback" not in cuerpo, "500 sin detalles tecnicos", cuerpo)
    ok(any("ZeroDivision" in r for r in registro), "el detalle quedo en el registro")

    srv.cerrar()
    print()
    print("TODO BIEN" if not fallos else f"FALLARON {len(fallos)}: " + ", ".join(fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
