# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
# Servidor local de la app. Escucha SOLO en 127.0.0.1 (puerto efimero) y sirve tres cosas:
#   - la interfaz (los archivos de web/),
#   - la API (POST /<token>/api/<metodo>, JSON) y los cuadros (GET /<token>/frame),
#   - el video o audio abierto, con soporte de Range (GET /<token>/media/...).
#
# Por que HTTP y no el puente de pywebview: asi la misma interfaz corre en una
# ventana nativa o en cualquier navegador (si en la otra PC falta WebView2), los
# cuadros viajan como imagen directa y no como base64, y el <video> tiene una URL
# http (el WebView rechaza file://: "Media load rejected by URL safety check").
#
# Seguridad (esto escucha en la maquina de una persona):
#   - el token aleatorio va en la ruta: sin el no se obtiene nada (404);
#   - se valida Host (contra DNS rebinding) y, en POST, Origin y Content-Type;
#   - solo se sirven archivos de web/ con extension permitida, sin salirse de la carpeta;
#   - la politica CSP de la pagina prohibe cargar o enviar cualquier cosa fuera de este
#     servidor: la garantia de "100% offline" la hace cumplir el navegador.
import json, mimetypes, os, re, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

TROZO = 64 * 1024
MAX_CUERPO = 16 * 1024 * 1024      # las palabras de una transcripcion de mas de una hora pasan de 1 MB

_TIPOS_MEDIO = {
    '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime',
    '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.ogv': 'video/ogg',
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac',
    '.wav': 'audio/wav', '.flac': 'audio/flac', '.ogg': 'audio/ogg',
    '.oga': 'audio/ogg', '.opus': 'audio/ogg', '.weba': 'audio/webm',
}

_TIPOS_ESTATICOS = {
    '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml',
    '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json; charset=utf-8',
    '.woff2': 'font/woff2', '.woff': 'font/woff',
}

CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
       "font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _rechazar_constante(nombre):
    raise ValueError('constante no valida: ' + nombre)


class _Pedido(BaseHTTPRequestHandler):
    # HTTP/1.1 para que el <video> pueda pedir rangos y reutilizar la conexion.
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass  # sin ruido en la consola

    def handle(self):
        # El <video> abre y corta conexiones todo el tiempo, sobre todo en cada seek.
        # Sin esto, cada corte imprime un WinError 10053 y tapa los errores de verdad.
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError):
            pass

    # ------------------------------------------------------------ respuestas

    def _enviar(self, codigo, tipo, cuerpo=b'', extra=None, con_cuerpo=True):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(cuerpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if self.close_connection:
            self.send_header('Connection', 'close')
        if tipo.startswith('text/html'):
            self.send_header('Content-Security-Policy', CSP)
        for clave, valor in (extra or {}).items():
            self.send_header(clave, valor)
        self.end_headers()
        if con_cuerpo and cuerpo:
            self.wfile.write(cuerpo)

    def _json(self, codigo, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False, allow_nan=False).encode('utf-8')      # NaN no es JSON: la pagina no podria leerlo
        self._enviar(codigo, 'application/json; charset=utf-8', cuerpo)

    def _error(self, codigo, texto=''):
        self._enviar(codigo, 'text/plain; charset=utf-8', texto.encode('utf-8'))

    # ----------------------------------------------------------- autorizacion

    def _resto_autorizado(self, es_post):
        """Devuelve la ruta sin el token, o None (y ya respondio el error)."""
        ctx = self.server.ctx
        host = (self.headers.get('Host') or '').lower()
        if host not in ctx.hosts_validos:
            self._error(421, 'host no valido')   # DNS rebinding
            return None
        ruta = unquote(urlsplit(self.path).path)
        segmento = ruta[1:].split('/', 1)[0] if ruta.startswith('/') else ''
        if not segmento or not secrets.compare_digest(segmento.encode(), ctx.token.encode()):
            self._error(404)
            return None
        if es_post:
            origen = self.headers.get('Origin')
            if origen and origen.lower() not in ctx.origenes_validos:
                self._error(403, 'origen no valido')
                return None
            tipo = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if tipo != 'application/json':
                self._error(415, 'se espera application/json')
                return None
        return ruta[len(segmento) + 2:]

    # ----------------------------------------------------------------- verbos

    def do_HEAD(self):
        self._atender(False, False)

    def do_GET(self):
        self._atender(True, False)

    def do_POST(self):
        self._atender(True, True)

    def _atender(self, con_cuerpo, es_post):
        # La conexion HTTP/1.1 se reutiliza: si un POST responde sin leer su cuerpo,
        # esos bytes se pegan al pedido siguiente ("[]GET /...") y lo rompen con un
        # 501. Por eso el cuerpo se consume SIEMPRE, antes de cualquier decision.
        self._cuerpo = b''
        if es_post:
            try:
                largo = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                largo = -1
            if largo < 0 or largo > MAX_CUERPO:
                self.close_connection = True      # no se lee: se corta la conexion
                return self._error(413 if largo > MAX_CUERPO else 400)
            self._cuerpo = self.rfile.read(largo) if largo else b''
        resto = self._resto_autorizado(es_post)
        if resto is None:
            return
        ctx = self.server.ctx
        try:
            if resto.startswith('api/'):
                if not es_post:
                    return self._error(405)
                return self._api(resto[4:])
            if es_post:
                return self._error(405)
            if resto == 'frame':
                return self._cuadro(con_cuerpo)
            if resto.startswith(('media/', 'extra/')):
                return self._medio(resto, con_cuerpo)
            return self._estatico(resto or 'index.html', con_cuerpo)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            raise
        except Exception as e:
            ctx.registrar('servidor ' + self.path[:60] + ' -> ' + repr(e))
            self._error(500, 'error interno')

    # ------------------------------------------------------------------- API

    def _api(self, nombre):
        ctx = self.server.ctx
        if nombre == 'latido':
            ctx.ultimo_latido = time.time()
            ctx.hubo_latido = True
            return self._json(200, {'ok': True})
        funcion = ctx.metodos.get(nombre)
        if funcion is None:
            return self._error(404)
        try:
            # NaN e Infinity no son JSON valido (Python los acepta igual): un NaN que entrara al modelo de
            # edicion lo corrompe en silencio y despues la pagina no puede leer ni la respuesta.
            args = json.loads(self._cuerpo.decode('utf-8') or '[]', parse_constant=_rechazar_constante)
        except (ValueError, RecursionError):          # (un cuerpo anidado miles de veces desborda la pila del analizador)
            return self._error(400, 'JSON invalido')
        if not isinstance(args, list):
            return self._error(400, 'se espera una lista de argumentos')
        resultado = funcion(*args)
        self._json(200, resultado if resultado is not None else {})

    def _cuadro(self, con_cuerpo):
        ctx = self.server.ctx
        consulta = parse_qs(urlsplit(self.path).query)
        try:
            n = int(consulta.get('n', ['0'])[0])
            ancho = int(consulta.get('w', ['540'])[0])
        except ValueError:
            return self._error(400, 'parametros invalidos')
        fid = consulta.get('f', [''])[0]
        if fid and not re.fullmatch(r's\d{1,6}', fid):
            return self._error(400, 'parametros invalidos')
        jpg = ctx.cuadro(n, ancho, fid) if fid else ctx.cuadro(n, ancho)       # f = de que archivo del proyecto (por defecto, el principal)
        if not jpg:
            return self._error(404, 'no hay cuadro')
        self._enviar(200, 'image/jpeg', jpg, con_cuerpo=con_cuerpo)

    # --------------------------------------------------------------- estaticos

    def _estatico(self, relativa, con_cuerpo):
        ctx = self.server.ctx
        extension = os.path.splitext(relativa)[1].lower()
        tipo = _TIPOS_ESTATICOS.get(extension)
        if tipo is None:
            return self._error(404)
        raiz = ctx.raiz_web
        candidato = os.path.normpath(os.path.join(raiz, relativa))
        # Sin salirse de web/ (../ , rutas absolutas, ADS de Windows).
        if os.path.commonpath([candidato, raiz]) != raiz or not os.path.isfile(candidato):
            return self._error(404)
        with open(candidato, 'rb') as f:
            self._enviar(200, tipo, f.read(), con_cuerpo=con_cuerpo)

    # ------------------------------------------------------------------ medio

    def _medio(self, resto, con_cuerpo):
        ctx = self.server.ctx
        partes = resto.split('/', 2)       # media/<token>/<nombre>  o  extra/<token>/<nombre>
        ruta = None
        if len(partes) >= 3:
            if partes[0] == 'media':
                if ctx.medio_ruta and secrets.compare_digest(partes[1].encode(), (ctx.medio_token or '').encode()):
                    ruta = ctx.medio_ruta
            else:
                ruta = ctx.extras.get(partes[1])      # audio extra: cada archivo con su propio token
        if not ruta or not os.path.isfile(ruta):
            return self._error(404)

        tam = os.path.getsize(ruta)
        extension = os.path.splitext(ruta)[1].lower()
        # Tabla propia: el registro de Windows no conoce flac, opus o m4a, y un
        # audio servido como video/mp4 puede ser rechazado por el reproductor.
        tipo = _TIPOS_MEDIO.get(extension) or mimetypes.guess_type(ruta)[0] or 'application/octet-stream'
        desde, hasta, codigo = 0, tam - 1, 200

        # El <video> pide rangos para arrancar y para cada seek. Sin esto no busca.
        cab = self.headers.get('Range')
        if cab:
            m = re.match(r'bytes=(\d*)-(\d*)\s*$', cab.strip())
            if m:
                a, b = m.group(1), m.group(2)
                if a:
                    desde = int(a)
                    hasta = min(int(b), tam - 1) if b else tam - 1
                elif b:
                    desde = max(0, tam - int(b))  # bytes=-N: los ultimos N
                codigo = 206

        if desde >= tam or desde > hasta:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{tam}')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        largo = hasta - desde + 1
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(largo))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if codigo == 206:
            self.send_header('Content-Range', f'bytes {desde}-{hasta}/{tam}')
        self.end_headers()
        if not con_cuerpo:
            return

        with open(ruta, 'rb') as f:
            f.seek(desde)
            resta = largo
            while resta > 0:
                datos = f.read(min(TROZO, resta))
                if not datos:
                    break
                try:
                    self.wfile.write(datos)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    return  # el <video> corta la conexion en cada seek: es normal
                resta -= len(datos)


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # una conexion cortada por el reproductor no es un error


class ServidorLocal:
    """metodos: {nombre: funcion} que la interfaz puede llamar por POST /api/<nombre>.
    cuadro: funcion (n, ancho) -> bytes JPEG (o None)."""

    def __init__(self, raiz_web, metodos, cuadro, registrar=None):
        self.raiz_web = os.path.normpath(os.path.abspath(raiz_web))
        self.metodos = dict(metodos)
        self.cuadro = cuadro
        self.registrar = registrar or (lambda texto: None)
        self.token = secrets.token_urlsafe(24)
        self.medio_ruta = None
        self.medio_token = None
        self.extras = {}            # token -> ruta: audios extra para escuchar en la vista previa
        self.ultimo_latido = time.time()
        self.hubo_latido = False

        self.srv = _Servidor(('127.0.0.1', 0), _Pedido)
        self.srv.ctx = self
        self.puerto = self.srv.server_address[1]
        self.hosts_validos = {f'127.0.0.1:{self.puerto}', f'localhost:{self.puerto}'}
        self.origenes_validos = {f'http://127.0.0.1:{self.puerto}', f'http://localhost:{self.puerto}'}
        self.hilo = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.hilo.start()

    def url_inicio(self):
        return f'http://127.0.0.1:{self.puerto}/{self.token}/index.html'

    def publicar(self, ruta):
        # Token nuevo por archivo: una URL vieja deja de servir.
        self.medio_ruta = os.path.abspath(ruta)
        self.medio_token = secrets.token_urlsafe(16)
        nombre = os.path.basename(ruta).replace(' ', '_')
        return f'http://127.0.0.1:{self.puerto}/{self.token}/media/{self.medio_token}/{nombre}'

    def publicar_extra(self, ruta):
        """URL para un audio extra (musica, locucion). A diferencia de publicar(), no invalida las anteriores:
        la vista previa puede necesitar varios a la vez. Mismo archivo, misma URL. Tope de 32."""
        ruta = os.path.abspath(ruta)
        token = next((t for t, r in self.extras.items() if r == ruta), None)
        if token is None:
            token = secrets.token_urlsafe(16)
            self.extras[token] = ruta
            while len(self.extras) > 32:
                self.extras.pop(next(iter(self.extras)))
        nombre = os.path.basename(ruta).replace(' ', '_')
        return f'http://127.0.0.1:{self.puerto}/{self.token}/extra/{token}/{nombre}'

    def segundos_sin_latido(self):
        """None si la pagina nunca mando un latido (todavia no cargo)."""
        return (time.time() - self.ultimo_latido) if self.hubo_latido else None

    def cerrar(self):
        try:
            self.srv.shutdown()
            self.srv.server_close()
        except Exception:
            pass
