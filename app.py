# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
# Editor de video local. Arranca la ventana nativa (o el navegador) y expone el motor.
# Uso:  python app.py [archivo]          ventana nativa (WebView2)
#       python app.py --navegador [archivo]   en el navegador, si falta WebView2
import base64, copy, json, math, os, shutil, subprocess, sys, tempfile, threading, time, traceback

# Con pythonw lanzado por `start`, sys.stdout y sys.stderr son None: sin esta
# guarda, la app muere en esta linea y no queda ni rastro, porque no hay consola.
for _flujo in (sys.stdout, sys.stderr):
    if _flujo is not None:
        try:
            _flujo.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

AQUI = os.path.dirname(os.path.abspath(__file__))

# Las herramientas que vienen con el programa (binfmpeg.exe en la version portatil) van primero en el PATH:
# asi anda en una PC donde ffmpeg no esta instalado.
_BIN = os.path.join(AQUI, 'bin')
if os.path.isdir(_BIN):
    os.environ['PATH'] = _BIN + os.pathsep + os.environ.get('PATH', '')


def _carpeta_de_datos():
    """Donde se escriben el registro, los ajustes y el cache: al lado del programa si se puede escribir ahi
    (carpeta propia, pendrive); si no (Archivos de programa, carpeta de red de solo lectura), en el perfil."""
    en_perfil = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'Moviola')
    if os.path.isfile(os.path.join(AQUI, '.moviola-instalado')):
        # Instalada con el instalador: los ajustes, el registro y la cache (hasta 5 GB) no van dentro de la carpeta del programa
        # (desinstalar o actualizar no tiene que llevarselos).
        try:
            os.makedirs(en_perfil, exist_ok=True)
            return en_perfil
        except OSError:
            pass
    try:
        marca = os.path.join(AQUI, '.escritura-%d' % os.getpid())
        with open(marca, 'w') as f:
            f.write('x')
        os.remove(marca)
        return AQUI
    except OSError:
        try:
            carpeta = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'Moviola')
            os.makedirs(carpeta, exist_ok=True)
            return carpeta
        except OSError:
            return tempfile.gettempdir()


DATOS = _carpeta_de_datos()
AQUI_LOG = os.path.join(DATOS, 'ultimo-error.log')


def _anotar_falla(tipo, valor, rastro):
    # pythonw no tiene donde escribir: si algo explota, queda en un archivo al lado del .py.
    try:
        with open(AQUI_LOG, 'w', encoding='utf-8') as f:
            f.write('El editor no pudo arrancar.' + os.linesep * 2)
            traceback.print_exception(tipo, valor, rastro, file=f)
    except Exception:
        pass
    if sys.stderr is not None:
        traceback.print_exception(tipo, valor, rastro, file=sys.stderr)


sys.excepthook = _anotar_falla

AQUI_REGISTRO = os.path.join(DATOS, 'editor.log')


def _registrar(texto):
    """Deja una nota en editor.log (se recorta solo). Sirve para soporte."""
    try:
        if os.path.exists(AQUI_REGISTRO) and os.path.getsize(AQUI_REGISTRO) > 256 * 1024:
            os.remove(AQUI_REGISTRO)
        with open(AQUI_REGISTRO, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + texto + os.linesep)
    except Exception:
        pass


def _fps_numero(valor):
    """Los cuadros por segundo del exportador pueden venir como '30000/1001': a numero (o None)."""
    try:
        if valor is None:
            return None
        if isinstance(valor, str) and '/' in valor:
            a, b = valor.split('/', 1)
            return round(float(a) / float(b), 3)
        return round(float(valor), 3)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _explicar(e):
    """Mensaje para una persona, no para un programador."""
    nombre = type(e).__name__
    if nombre == 'InvalidDataError':
        return 'No lo reconozco como video ni como audio. Puede estar dañado o ser de otro tipo.'
    if nombre in ('FileNotFoundError', 'PermissionError'):
        return 'No pude leer el archivo. Revisá que exista y que no esté abierto en otro programa.'
    if isinstance(e, ValueError):
        return str(e)
    return 'Motivo: ' + str(e)


import av
from motor.video import Video, SinVideo
from motor.audio import picos
from motor.tiras import tira
from motor.servidor import ServidorLocal

from motor.proyecto import Proyecto, ErrorEdicion
from motor import efectos as efectos_mod
try:
    from motor import silencios as silencios_mod
except Exception as _e:        # sin esto se puede editar y exportar igual
    silencios_mod = None
    _registrar('no pude cargar motor.silencios: ' + repr(_e))

try:
    from motor import descargas as descargas_mod
except Exception as _e:
    descargas_mod = None
    _registrar('no pude cargar motor.descargas: ' + repr(_e))
try:
    from motor import escenas as escenas_mod
except Exception as _e:
    escenas_mod = None
    _registrar('no pude cargar motor.escenas: ' + repr(_e))
try:
    from motor import subtitulos as subtitulos_mod
except Exception as _e:
    subtitulos_mod = None
    _registrar('no pude cargar motor.subtitulos: ' + repr(_e))
try:
    from motor import lotes as lotes_mod
except Exception as _e:
    lotes_mod = None
    _registrar('no pude cargar motor.lotes: ' + repr(_e))

try:
    from motor import proxy as proxy_mod
except Exception as _e:        # sin el proxy la app anda igual: solo no suena lo que el WebView no reproduce
    proxy_mod = None
    _registrar('no pude cargar motor.proxy: ' + repr(_e))

try:
    from motor import exportar as exportar_mod
except Exception as _e:        # sin el exportador se puede editar, pero no exportar
    exportar_mod = None
    _registrar('no pude cargar motor.exportar: ' + repr(_e))

try:
    from motor import gpu as gpu_mod
except Exception as _e:        # sin esto la app anda igual, solo por el procesador
    gpu_mod = None
    _registrar('no pude cargar motor.gpu: ' + repr(_e))

try:
    from motor.proxy import Cancelado as _Cancelado
except Exception:
    class _Cancelado(Exception):
        pass


def _no_constante(nombre):
    raise ValueError('numero no valido en el archivo: ' + nombre)       # NaN e Infinity no entran al modelo


# El dialogo ofrece todo por defecto: ffmpeg lee muchisimos formatos mas de los
# que conviene listar, y si no se puede abrir la app lo explica.
_EXT_VIDEO = 'mp4;mov;m4v;mkv;avi;webm;mpg;mpeg;ts;mts;m2ts;wmv;flv;3gp;mxf;ogv;vob;asf;divx'
_EXT_AUDIO = 'mp3;wav;flac;m4a;aac;ogg;oga;opus;wma;aiff;aif;ac3;amr;mka'
_TODAS = (_EXT_VIDEO + ';' + _EXT_AUDIO).split(';')
EXT_PROYECTO = '.moviola'
TIPOS = (
    'Video audio y proyectos (' + ';'.join('*.' + e for e in _TODAS + ['moviola']) + ')',
    'Video y audio (' + ';'.join('*.' + e for e in _TODAS) + ')',
    'Todos los archivos (*.*)',
)

# Lo que la interfaz puede pedirle al modelo de edicion (motor/proyecto.py).
OPERACIONES_EDICION = ('dividir', 'borrar_rango', 'borrar_rangos', 'borrar_grupo', 'recortar_a', 'fade', 'fade_grupo', 'volumen',
                       'silenciar', 'mover_clip', 'eliminar_clip', 'desenlazar', 'cambiar_pista_audio',
                       'agregar_efecto', 'quitar_efecto', 'cambiar_efecto', 'activar_efecto', 'mover_efecto',
                       'poner_transicion', 'quitar_transicion', 'velocidad', 'reversa', 'repetir_grupo', 'ducking',
                       'insertar_fuente', 'mover_grupo', 'subtitulos_poner', 'subtitulo_agregar', 'subtitulo_cambiar', 'subtitulo_quitar', 'subtitulos_borrar',
                       'subtitulos_estilo', 'subtitulos_al_dia', 'dividir_varios', 'palabras_borrar', 'palabras_acortar_pausas', 'palabra_cambiar', 'recortar_borde',
                       'deshacer', 'rehacer')

# Lo que el elemento <audio>/<video> del WebView puede reproducir sin convertir.
_AUDIO_WEB_EXT = {'.mp3', '.m4a', '.aac', '.wav', '.ogg', '.oga', '.opus', '.flac'}
_AUDIO_WEB_CODEC = {'mp3', 'mp3float', 'aac', 'vorbis', 'opus', 'flac',
                    'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_u8', 'pcm_f32le'}


def _hay_webview2():
    """True si el runtime de WebView2 esta instalado (Windows 11 lo trae)."""
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        guid = r'{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
        sitios = (
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients' + '\\' + guid),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\EdgeUpdate\Clients' + '\\' + guid),
            (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\EdgeUpdate\Clients' + '\\' + guid),
        )
        for raiz, sub in sitios:
            try:
                with winreg.OpenKey(raiz, sub) as clave:
                    version = winreg.QueryValueEx(clave, 'pv')[0]
                    if version and version != '0.0.0.0':
                        return True
            except OSError:
                continue
    except Exception:
        pass
    return False


_COLA_PRINCIPAL = None            # en modo navegador: los dialogos se piden por aca y los atiende el hilo principal
_LOCK_TK = threading.Lock()


def _con_tk(dialogo):
    """Corre `dialogo(filedialog)` con una ventana raiz de tkinter oculta. Tk no es seguro fuera del hilo principal: en modo navegador
    (donde el hilo principal solo espera) el pedido se le pasa a el; si no, por lo menos va de a uno."""
    def correr():
        import tkinter
        from tkinter import filedialog
        raiz = tkinter.Tk()
        raiz.withdraw()
        try:
            raiz.attributes('-topmost', True)
            return dialogo(filedialog)
        finally:
            raiz.destroy()

    cola = _COLA_PRINCIPAL
    if cola is None or threading.current_thread() is threading.main_thread():
        with _LOCK_TK:
            return correr()
    caja, listo = {}, threading.Event()
    cola.put((correr, caja, listo))
    listo.wait()
    if 'error' in caja:
        raise caja['error']
    return caja.get('valor')


def _dialogo_tkinter():
    """Dialogo de archivos del sistema para el modo navegador (tkinter viene con Python)."""
    return _con_tk(lambda filedialog: filedialog.askopenfilename(
        title='Abrir video o audio',
        filetypes=[('Video y audio', ' '.join('*.' + e for e in _TODAS)), ('Todos los archivos', '*.*')]))


VERSION = '1.1.0'
_FFMPEG_VERSION = []


def _version_ffmpeg():
    """La version del ffmpeg que usa el programa (se pregunta una sola vez)."""
    if not _FFMPEG_VERSION:
        texto = ''
        try:
            exe = shutil.which('ffmpeg')
            if exe:
                r = subprocess.run([exe, '-version'], capture_output=True, text=True, timeout=10,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                primera = (r.stdout or '').splitlines()[0] if r.stdout else ''
                texto = primera.replace('ffmpeg version ', '').split(' Copyright')[0].strip()
        except Exception:
            texto = ''
        _FFMPEG_VERSION.append(texto)
    return _FFMPEG_VERSION[0]


class API:
    def __init__(self):
        self.video = None
        self.ruta = None
        self.ruta_proyecto = None     # el archivo .moviola donde se guardo (o de donde se abrio) este proyecto
        self._cambios = 0             # cuantas veces cambio el proyecto desde que se abrio
        self._cambios_guardados = 0   # el valor de _cambios cuando se guardo por ultima vez
        self._temporizador_recup = None
        self.fid_principal = None     # el archivo que esta abierto en el visor (el primer video del proyecto)
        self.videos = {}              # fid -> Video ya abierto de los OTROS videos del proyecto (los cuadros del visor)
        self.medios = {}              # fid -> lo que la interfaz necesita saber de cada archivo del panel de medios
        self.proxies = {}             # fid -> estado de la copia de reproduccion de un video que no es el principal
        self.temp = tempfile.mkdtemp(prefix='editor-video-')
        self.servidor = None          # se asigna en main(): ServidorLocal
        self.ventana = None           # ventana de pywebview, si hay
        self.archivo_inicial = None
        self.lock = threading.Lock()
        self._lock_ajustes = threading.RLock()
        # Proyecto de edicion (motor/proyecto.py): se arma al abrir un archivo.
        self.proyecto = None
        self.picos_fuentes = {}
        self._lock_proyecto = threading.Lock()
        # Exportacion (motor/exportar.py): un trabajo a la vez, en segundo plano.
        self.exportacion = {'estado': 'ninguna', 'progreso': 0.0}
        self._lock_export = threading.Lock()
        self._cancelar_export = None
        self.descarga = {'estado': 'ninguna', 'progreso': 0.0}
        self._lock_descarga = threading.Lock()
        self._cancelar_descarga = None
        self._ultima_descarga = None
        self.transcripcion = {'estado': 'ninguna', 'progreso': 0.0}
        self._lock_transcripcion = threading.Lock()
        self._cancelar_transcripcion = None
        self._ultimo_export = None
        self.lote = {'estado': 'ninguno', 'progreso': 0.0}
        self._lock_lote = threading.Lock()
        self._cancelar_lote = None
        # Proxy de reproduccion (formatos que el WebView no puede reproducir).
        self.cache = os.path.join(DATOS, 'cache')
        self.estado_proxy = {'ruta': None, 'estado': 'nada', 'progreso': 0.0, 'url': '', 'error': ''}
        self._epoca_proxy = 0
        self._cancelar_proxy = None
        self._lock_proxy = threading.Lock()
        if proxy_mod is not None:
            # Mantiene el cache acotado (5 GB) sin hacer esperar el arranque.
            threading.Thread(target=self._limpiar_cache, daemon=True).start()
        # Aceleracion por GPU: modo elegido (se guarda) y lo que la PC puede de verdad.
        # EDITOR_AJUSTES / EDITOR_SIN_GPU: solo para las pruebas (aislar el archivo y evitar la deteccion).
        self.ajustes_ruta = os.environ.get('EDITOR_AJUSTES') or os.path.join(DATOS, 'ajustes.json')
        ajustes = gpu_mod.leer_ajustes(self.ajustes_ruta) if gpu_mod else {}
        self.modo_acel = ajustes.get('aceleracion') if ajustes.get('aceleracion') in ('cpu', 'gpu', 'auto') else 'cpu'
        self.deteccion = None
        self.detectando = False
        self.error_gpu = ''
        self._lock_gpu = threading.Lock()
        if gpu_mod is not None and not os.environ.get('EDITOR_SIN_GPU'):
            threading.Thread(target=self._detectar_gpu, daemon=True).start()

    def _cambiar_ajustes(self, cambio):
        """Lee ajustes.json, le aplica `cambio(ajustes)` y lo guarda, todo con un candado y releyendo el archivo en el momento: asi dos
        cosas que escriben a la vez (la deteccion de GPU, que tarda 10 s, y abrir un archivo) no se pisan."""
        if gpu_mod is None:
            return {}
        with self._lock_ajustes:
            ajustes = gpu_mod.leer_ajustes(self.ajustes_ruta)
            cambio(ajustes)
            gpu_mod.guardar_ajustes(self.ajustes_ruta, ajustes)
            return ajustes

    def ocupada(self):
        """True si hay un trabajo largo en curso (exportar, preset, transcribir, bajar): no es momento de apagarse."""
        with self._lock_export:
            if self.exportacion.get('estado') == 'exportando':
                return True
        with self._lock_lote:
            if self.lote.get('estado') == 'procesando':
                return True
        with self._lock_transcripcion:
            if self.transcripcion.get('estado') == 'transcribiendo':
                return True
        with self._lock_descarga:
            return self.descarga.get('estado') == 'bajando'

    def _cancelar_todo(self, espera=6.0):
        """Al cerrar: se cancela lo que este corriendo y se espera un poco a que cada trabajo mate su programa (ffmpeg, whisper, yt-dlp) y
        borre su archivo a medias. Sin esto quedaba un ffmpeg trabajando solo y un «.parcial» en la carpeta de la persona."""
        for candado, evento in ((self._lock_export, '_cancelar_export'), (self._lock_lote, '_cancelar_lote'),
                                (self._lock_transcripcion, '_cancelar_transcripcion'), (self._lock_descarga, '_cancelar_descarga')):
            with candado:
                e = getattr(self, evento)
            if e is not None:
                e.set()
        with self._lock_proxy:
            for est in self.proxies.values():
                if est.get('evento') is not None:
                    est['evento'].set()
        limite = time.time() + espera
        while self.ocupada() and time.time() < limite:
            time.sleep(0.1)

    def metodos(self):
        """Lo que la interfaz puede llamar por HTTP (POST /api/<nombre>)."""
        m = {'abrir': self.abrir, 'elegir_archivo': self.elegir_archivo, 'inicial': self.inicial,
             'acerca_de': self.acerca_de, 'acerca_licencia': self.acerca_licencia, 'proxy_estado': self.proxy_estado, 'gpu_estado': self.gpu_estado, 'gpu_modo': self.gpu_modo,
             'gpu_comprobar': self.gpu_comprobar, 'gpu_visto': self.gpu_visto,
             'proyecto_estado': self.proyecto_estado, 'agregar_audio': self.agregar_audio,
             'picos_fuente': self.picos_fuente, 'efectos_catalogo': self.efectos_catalogo,
             'analizar_silencios': self.analizar_silencios, 'medir_volumen': self.medir_volumen,
             'elegir_lut': self.elegir_lut,
             'guardar_proyecto': self.guardar_proyecto, 'guardar_proyecto_como': self.guardar_proyecto_como,
             'agregar_medio': self.agregar_medio, 'medio_info': self.medio_info, 'medio_estado': self.medio_estado, 'quitar_medio': self.quitar_medio,
             'elegir_videos': self.elegir_videos,
             'abrir_proyecto': self.abrir_proyecto, 'recientes': self.recientes, 'abrir_recuperacion': self.abrir_recuperacion,
             'descartar_recuperacion': self.descartar_recuperacion, 'elegir_proyecto': self.elegir_proyecto, 'olvidar_reciente': self.olvidar_reciente,
             'descarga_herramienta': self.descarga_herramienta, 'descargar_iniciar': self.descargar_iniciar, 'descargar_estado': self.descargar_estado,
             'descargar_cancelar': self.descargar_cancelar, 'descarga_mostrar': self.descarga_mostrar,
             'analizar_escenas': self.analizar_escenas, 'subtitulos_catalogo': self.subtitulos_catalogo,
             'transcribir_iniciar': self.transcribir_iniciar, 'transcribir_estado': self.transcribir_estado,
             'transcribir_cancelar': self.transcribir_cancelar,
             'exportar_opciones': self.exportar_opciones,
             'exportar_destino': self.exportar_destino, 'exportar_iniciar': self.exportar_iniciar,
             'exportar_estado': self.exportar_estado, 'exportar_cancelar': self.exportar_cancelar,
             'presets_catalogo': self.presets_catalogo, 'lote_iniciar': self.lote_iniciar, 'lote_estado': self.lote_estado,
             'lote_cancelar': self.lote_cancelar,
             'elegir_carpeta': self.elegir_carpeta, 'mostrar_en_carpeta': self.mostrar_en_carpeta}
        # Operaciones de edicion: editar_dividir, editar_borrar_rango, editar_fade...
        for nombre in OPERACIONES_EDICION:
            m['editar_' + nombre] = (lambda *a, _n=nombre: self._editar(_n, *a))
        return {k: self._blindar(k, f) for k, f in m.items()}

    def _blindar(self, nombre, funcion):
        """Lo que llega por la API viene de afuera: un argumento de un tipo que no es (una lista donde va un id, un texto donde va un numero)
        no puede terminar en un error 500 ni en una excepcion; se contesta con un error claro y se anota para encontrarlo."""
        def seguro(*args):
            try:
                return funcion(*args)
            except (TypeError, ValueError, KeyError, AttributeError, IndexError, OverflowError, RecursionError) as e:
                _registrar('API %s%r: %r' % (nombre, tuple(str(a)[:40] for a in args), e))
                return {'error': 'Ese pedido no es válido.'}
        seguro.__name__ = getattr(funcion, '__name__', nombre)
        return seguro

    # --- interno ---

    def _tira_data_uri(self, archivo):
        with open(archivo, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        return 'data:image/jpeg;base64,' + b64

    def _soltar_video(self):
        if self.video is not None:
            self.video.cerrar()
            self.video = None
        for v in self.videos.values():
            try:
                v.cerrar()
            except Exception:
                pass
        self.videos = {}

    def _agregar_espectro(self, ruta, info):
        # Waveform: una sola pasada de ffmpeg.
        try:
            a = picos(ruta, 2000)
            info['picos'] = a.get('picos', [])
            info['sin_audio'] = bool(a.get('sin_audio', False))
        except Exception as e:
            _registrar('waveform fallo: ' + repr(e))
            info['picos'], info['sin_audio'] = [], True

    def _datos_solo_audio(self, ruta):
        """Info de un archivo que no tiene video (mp3, wav, flac, m4a...)."""
        with av.open(ruta, options={'protocol_whitelist': 'file'}) as contenedor:
            pistas = list(contenedor.streams.audio)
            if not pistas:
                raise ValueError('El archivo no tiene ni video ni audio que se pueda leer.')
            pista = pistas[0]
            contexto = pista.codec_context
            duracion = 0.0
            if contenedor.duration:
                duracion = float(contenedor.duration) / av.time_base
            elif pista.duration is not None and pista.time_base:
                duracion = float(pista.duration * pista.time_base)
            try:
                canales = len(contexto.layout.channels)
            except Exception:
                canales = getattr(contexto, 'channels', 0) or 0
            codec = (contexto.name or '').lower()
            ext = os.path.splitext(ruta)[1].lower()
            return {
                'solo_audio': True,
                'codec': codec,
                'canales': canales,
                'frecuencia': int(contexto.sample_rate or 0),
                'duracion': duracion,
                'pistas_audio': len(pistas),
                'web_compatible': ext in _AUDIO_WEB_EXT and codec in _AUDIO_WEB_CODEC,
            }

    # --- proyecto de edicion ---

    def _armar_proyecto(self, ruta, info, tabla):
        """Un proyecto nuevo con el archivo entero: V1 (video) y A1 (audio) enlazados."""
        p = Proyecto()
        if info.get('solo_audio'):
            fid = p.agregar_fuente(ruta, 'audio', info['duracion'], None, info.get('pistas_audio', 1),
                                   codec=info.get('codec', ''), web_compatible=bool(info.get('web_compatible')))
        else:
            fid = p.agregar_fuente(ruta, 'video', info['duracion'], tabla, info.get('pistas_audio', 0),
                                   inicio=info['inicio'], ancho=info['ancho'], alto=info['alto'], fps=info['fps'],
                                   vfr=bool(info.get('vfr')), rotacion=info.get('rotacion', 0))
        p.nuevo_desde_fuente(fid)
        with self._lock_proyecto:
            self.proyecto = p
            self.picos_fuentes = {fid: info.get('picos', [])}
            self.fid_principal = fid
            self.medios = {}
            self.proxies = {}

    # --- recuperacion: una copia del trabajo sin guardar, por si se cierra la ventana o se corta la luz ---

    def _ruta_recuperacion(self):
        return os.path.join(os.path.dirname(self.ajustes_ruta), 'recuperacion.moviola')

    def _marcar_cambio(self):
        self._cambios += 1
        if self._temporizador_recup is not None:
            self._temporizador_recup.cancel()
        t = threading.Timer(1.5, self._escribir_recuperacion)      # se junta una racha de cambios en una sola escritura
        t.daemon = True
        self._temporizador_recup = t
        t.start()

    def _escribir_recuperacion(self):
        try:
            with self._lock_proyecto:
                if self.proyecto is None or self._cambios == self._cambios_guardados:
                    return
                self._guardar_copia(self._ruta_recuperacion())
        except Exception as e:
            _registrar('no pude escribir la recuperacion: ' + repr(e))

    def _guardar_copia(self, ruta):
        self.proyecto.guardar(ruta)

    def _borrar_recuperacion(self):
        if self._temporizador_recup is not None:
            self._temporizador_recup.cancel()
            self._temporizador_recup = None
        try:
            os.remove(self._ruta_recuperacion())
        except OSError:
            pass

    def _proyecto_dict(self):
        d = self.proyecto.a_dict()
        d['archivo_proyecto'] = os.path.basename(self.ruta_proyecto) if self.ruta_proyecto else ''
        d['ruta_proyecto'] = self.ruta_proyecto or ''
        d['sin_guardar'] = self._cambios != self._cambios_guardados
        for f in d['fuentes'].values():
            f['nombre'] = os.path.basename(f['ruta'])
        # cuanto admite una transicion en la entrada de cada clip (0 = no se puede): la interfaz lo usa para ofrecerla o no
        for p in d['pistas']:
            for c in p['clips']:
                c['transicion_max'] = self.proyecto.transicion_maxima(c['id'])
        return d

    def proyecto_estado(self):
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto.'}
            return {'proyecto': self._proyecto_dict()}

    def _editar(self, nombre, *args):
        """Una operacion de edicion. Siempre devuelve el proyecto COMPLETO: tras un error el modelo restaura
        una copia del estado, asi que la interfaz no tiene que guardar referencias a clips."""
        if any(isinstance(a, float) and not math.isfinite(a) for a in args):      # defensa: el servidor ya los rechaza
            return {'error': 'Ese valor no es válido.'}
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para editar.'}
            try:
                resultado = getattr(self.proyecto, nombre)(*args)
            except ErrorEdicion as e:
                return {'error': str(e), 'proyecto': self._proyecto_dict()}
            except (TypeError, ValueError, KeyError) as e:
                _registrar('edicion %s%r: %r' % (nombre, args, e))
                return {'error': 'No pude hacer ese cambio.', 'proyecto': self._proyecto_dict()}
            self._marcar_cambio()
            return {'proyecto': self._proyecto_dict(), 'resultado': resultado}

    def agregar_audio(self, ruta, inicio=0.0):
        """Pone un audio (otro archivo, musica, locucion) en la linea de tiempo, en una pista extra."""
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para editar.'}
            try:
                ruta = os.path.abspath(ruta)
                if not os.path.isfile(ruta):
                    return {'error': 'No encontré el archivo: ' + ruta, 'proyecto': self._proyecto_dict()}
                fid = next((k for k, f in self.proyecto.fuentes.items() if f['ruta'] == ruta), None)
                if fid is None:
                    datos = self._datos_solo_audio(ruta)
                    fid = self.proyecto.agregar_fuente(
                        ruta, 'audio', datos['duracion'], None, datos['pistas_audio'], codec=datos['codec'],
                        web_compatible=datos['web_compatible'], url=self.servidor.publicar_extra(ruta))
                    try:
                        self.picos_fuentes[fid] = picos(ruta, 2000).get('picos', [])
                    except Exception as e:
                        _registrar('picos del audio extra fallaron: ' + repr(e))
                        self.picos_fuentes[fid] = []
                cid = self.proyecto.agregar_audio(fid, float(inicio))
            except ErrorEdicion as e:
                return {'error': str(e), 'proyecto': self._proyecto_dict()}
            except Exception as e:
                _registrar('agregar audio ' + ruta + ': ' + repr(e))
                return {'error': 'No pude usar ese archivo como audio. ' + _explicar(e), 'proyecto': self._proyecto_dict()}
            self._marcar_cambio()
            return {'proyecto': self._proyecto_dict(), 'clip': cid, 'fuente': fid}

    def efectos_catalogo(self):
        """Los efectos que se pueden poner en un clip, con sus ajustes: la interfaz arma los controles con esto."""
        return {'efectos': efectos_mod.catalogo(), 'transiciones': efectos_mod.catalogo_transiciones()}

    def elegir_lut(self, extensiones=None):
        """Dialogo del sistema para elegir un archivo para un efecto: una LUT (.cube / .3dl, por defecto) o una imagen."""
        permitidas = set(efectos_mod.EXTENSIONES_LUT) | set(efectos_mod.EXTENSIONES_IMAGEN)
        if not (isinstance(extensiones, list) and extensiones and all(isinstance(e, str) and e in permitidas for e in extensiones)):
            extensiones = list(efectos_mod.EXTENSIONES_LUT)
        es_imagen = extensiones[0] in efectos_mod.EXTENSIONES_IMAGEN
        nombre_tipo = 'Imágenes' if es_imagen else 'Archivos de color'
        exts = ';'.join('*' + e for e in extensiones)
        try:
            if self.ventana is not None:
                import webview
                v = self.ventana.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                    file_types=(nombre_tipo + ' (' + exts + ')', 'Todos los archivos (*.*)'))
                ruta = v[0] if isinstance(v, (list, tuple)) and v else (v or '')
            else:
                ruta = _con_tk(lambda filedialog: filedialog.askopenfilename(title=nombre_tipo,
                                                      filetypes=[(nombre_tipo, ' '.join('*' + e for e in extensiones)),
                                                                 ('Todos los archivos', '*.*')]))
            return {'ruta': ruta} if ruta else {'cancelado': True}
        except Exception as e:
            _registrar('elegir lut fallo: ' + repr(e))
            return {'error': 'No pude abrir el selector de archivos.'}

    def _copia_del_proyecto(self):
        """Una copia liviana (sin el historial de deshacer) para trabajar sin tener tomado el candado del proyecto."""
        with self._lock_proyecto:
            if self.proyecto is None:
                return None
            copia = Proyecto()
            copia.fuentes = dict(self.proyecto.fuentes)
            copia.pistas = copy.deepcopy(self.proyecto.pistas)
            copia.subtitulos = copy.deepcopy(self.proyecto.subtitulos)
            return copia

    def analizar_escenas(self, que=None, umbral_escena=10.0, negro_min=0.3, congelado_min=1.0):
        """Busca cambios de escena, tramos negros y tramos congelados en V1, en tiempos de la linea de tiempo actual. No cambia nada:
        para cortar o sacar la interfaz llama a editar_dividir_varios / editar_borrar_rangos."""
        if escenas_mod is None:
            return {'error': 'La detección de escenas no está disponible.'}
        copia = self._copia_del_proyecto()
        if copia is None:
            return {'error': 'No hay nada abierto para analizar.'}
        try:
            return escenas_mod.analizar(copia, que or list(escenas_mod.QUE), umbral_escena, negro_min, congelado_min)
        except escenas_mod.ErrorEscena as e:
            return {'error': str(e)}
        except (OSError, KeyError) as e:
            _registrar('analizar escenas fallo: ' + repr(e))
            return {'error': 'No pude analizar el video. ' + _explicar(e)}

    # --- bajar un video de YouTube (con el yt-dlp que ya este instalado: ver motor/descargas.py) ---

    def _carpeta_descargas(self):
        return os.environ.get('MOVIOLA_DESCARGAS') or descargas_mod.carpeta_por_defecto()

    def descarga_herramienta(self):
        """Si esta PC puede bajar videos (yt-dlp instalado), con el motivo si no, las calidades y la carpeta donde se guardan."""
        if descargas_mod is None:
            return {'error': 'La descarga de videos no está disponible.'}
        e = descargas_mod.estado()
        e['calidades'] = [{'valor': k, 'nombre': v[0]} for k, v in descargas_mod.CALIDADES.items()]
        e['carpeta'] = self._carpeta_descargas()
        return e

    def descargar_iniciar(self, url, calidad='1080', tengo_derecho=False):
        """Baja UN video de YouTube en segundo plano. Exige que la persona haya confirmado que tiene derecho a usarlo."""
        if descargas_mod is None:
            return {'error': 'La descarga de videos no está disponible.'}
        if tengo_derecho is not True:
            return {'error': 'Antes de bajarlo tenés que confirmar que tenés derecho a usar ese video.'}
        if not descargas_mod.estado()['disponible']:
            return {'error': descargas_mod.estado()['motivo']}
        try:
            limpia = descargas_mod.validar_url(url)
        except descargas_mod.ErrorDescarga as e:
            return {'error': str(e)}
        if calidad not in descargas_mod.CALIDADES:
            return {'error': 'Esa calidad no está en la lista.'}
        evento = threading.Event()
        with self._lock_descarga:
            if self.descarga.get('estado') == 'bajando':
                return {'error': 'Ya hay una descarga en curso.'}
            self._cancelar_descarga = evento
            self.descarga = {'estado': 'bajando', 'progreso': 0.0}
        threading.Thread(target=self._descargar, daemon=True, args=(limpia, calidad, evento)).start()
        return {'ok': True}

    def _descargar(self, url, calidad, evento):
        def avance(f):
            with self._lock_descarga:
                if self.descarga.get('estado') == 'bajando':
                    self.descarga['progreso'] = round(float(f), 3)

        try:
            r = descargas_mod.descargar(url, self._carpeta_descargas(), calidad, evento, avance)
            with self._lock_descarga:
                self._ultima_descarga = r['archivo']
                self.descarga = {'estado': 'listo', 'progreso': 1.0, 'archivo': r['archivo'], 'nombre': r['nombre'], 'es_audio': calidad == 'audio'}
        except _Cancelado:
            with self._lock_descarga:
                self.descarga = {'estado': 'cancelado', 'progreso': 0.0}
        except descargas_mod.ErrorDescarga as e:
            with self._lock_descarga:
                self.descarga = {'estado': 'error', 'progreso': 0.0, 'error': str(e)}
        except Exception as e:
            _registrar('descargar fallo: ' + traceback.format_exc())
            with self._lock_descarga:
                self.descarga = {'estado': 'error', 'progreso': 0.0, 'error': 'No pude bajar el video. ' + _explicar(e)}

    def descargar_estado(self):
        with self._lock_descarga:
            return dict(self.descarga)

    def descargar_cancelar(self):
        with self._lock_descarga:
            evento = self._cancelar_descarga
            activa = self.descarga.get('estado') == 'bajando'
        if evento is not None and activa:
            evento.set()
        return {'ok': True}

    def descarga_mostrar(self):
        """Abre el explorador con el ULTIMO video bajado seleccionado (no recibe ninguna ruta de la interfaz)."""
        with self._lock_descarga:
            ruta = self._ultima_descarga
        if not ruta or not os.path.isfile(ruta):
            return {'error': 'No encuentro el archivo bajado.'}
        try:
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', '/select,', os.path.normpath(ruta)])
            return {'ok': True}
        except Exception as e:
            _registrar('mostrar descarga fallo: ' + repr(e))
            return {'error': 'No pude abrir la carpeta.'}

    # --- subtitulos ---

    def subtitulos_catalogo(self):
        """Los ajustes de estilo, los idiomas y si esta PC puede transcribir (con el motivo si no)."""
        if subtitulos_mod is None:
            return {'error': 'Los subtítulos no están disponibles.'}
        return {'catalogo': subtitulos_mod.catalogo(), 'transcripcion': subtitulos_mod.estado_transcripcion()}

    def transcribir_iniciar(self, idioma='es', max_letras=32):
        """Transcribe el audio de A1 en segundo plano, sobre una COPIA del proyecto de este momento. Cuando termina, la interfaz
        pone las frases con editar_subtitulos_poner (si el montaje cambio mientras tanto, se avisa)."""
        if subtitulos_mod is None:
            return {'error': 'Los subtítulos no están disponibles.'}
        est = subtitulos_mod.estado_transcripcion()
        if not est['disponible']:
            return {'error': est['motivo']}
        copia = self._copia_del_proyecto()
        if copia is None:
            return {'error': 'No hay nada abierto para transcribir.'}
        with self._lock_proyecto:
            huella = self.proyecto.huella_linea() if self.proyecto is not None else ''
        evento = threading.Event()
        with self._lock_transcripcion:
            if self.transcripcion.get('estado') == 'transcribiendo':
                return {'error': 'Ya hay una transcripción en curso.'}
            self._cancelar_transcripcion = evento
            self.transcripcion = {'estado': 'transcribiendo', 'progreso': 0.0}
        threading.Thread(target=self._transcribir, daemon=True, args=(copia, idioma, max_letras, evento, huella)).start()
        return {'ok': True}

    def _transcribir(self, copia, idioma, max_letras, evento, huella):
        def avance(f):
            with self._lock_transcripcion:
                if self.transcripcion.get('estado') == 'transcribiendo':
                    self.transcripcion['progreso'] = round(float(f), 3)

        try:
            r = subtitulos_mod.transcribir_completo(copia, idioma, max_letras, evento, avance)
            with self._lock_transcripcion:
                self.transcripcion = {'estado': 'listo', 'progreso': 1.0, 'frases': r['frases'], 'palabras': r['palabras'], 'huella': huella}
        except _Cancelado:
            with self._lock_transcripcion:
                self.transcripcion = {'estado': 'cancelado', 'progreso': 0.0}
        except (subtitulos_mod.ErrorSubtitulo, exportar_mod.ExportError) as e:
            with self._lock_transcripcion:
                self.transcripcion = {'estado': 'error', 'progreso': 0.0, 'error': str(e)}
        except Exception as e:
            _registrar('transcribir fallo: ' + traceback.format_exc())
            with self._lock_transcripcion:
                self.transcripcion = {'estado': 'error', 'progreso': 0.0, 'error': 'No pude transcribir. ' + _explicar(e)}

    def transcribir_estado(self):
        with self._lock_transcripcion:
            d = dict(self.transcripcion)
        with self._lock_proyecto:
            actual = self.proyecto.huella_linea() if self.proyecto is not None else ''
        if d.get('estado') == 'listo':
            d['montaje_cambio'] = d.get('huella') != actual
        return d

    def transcribir_cancelar(self):
        with self._lock_transcripcion:
            evento = self._cancelar_transcripcion
            activa = self.transcripcion.get('estado') == 'transcribiendo'
        if evento is not None and activa:
            evento.set()
        return {'ok': True}

    def analizar_silencios(self, umbral_db=-35.0, duracion_min=0.5, margen=0.1):
        """Busca los silencios del audio (A1) y los devuelve en tiempos de la linea de tiempo actual. No cambia nada:
        para cortarlos la interfaz llama a editar_borrar_rangos con lo que se vea bien."""
        if silencios_mod is None:
            return {'error': 'La detección de silencios no está disponible.'}
        copia = self._copia_del_proyecto()
        if copia is None:
            return {'error': 'No hay nada abierto para analizar.'}
        try:
            return silencios_mod.analizar(copia, umbral_db, duracion_min, margen)
        except silencios_mod.ErrorSilencio as e:
            return {'error': str(e)}
        except (OSError, KeyError) as e:
            _registrar('analizar silencios fallo: ' + repr(e))
            return {'error': 'No pude analizar el audio. ' + _explicar(e)}

    def medir_volumen(self):
        """Volumen de TODO el proyecto como queda al exportar (con efectos, volumen y fundidos): LUFS, pico y rango."""
        if exportar_mod is None:
            return {'error': 'El exportador no está disponible.'}
        copia = self._copia_del_proyecto()
        if copia is None:
            return {'error': 'No hay nada abierto para medir.'}
        try:
            m = exportar_mod._medir_volumen(copia, -14.0, None)
        except exportar_mod.ExportError as e:
            return {'error': str(e)}
        except Exception as e:
            _registrar('medir volumen fallo: ' + traceback.format_exc())
            return {'error': 'No pude medir el volumen. ' + _explicar(e)}
        if not m:
            return {'error': 'No hay sonido para medir (todo está en silencio o silenciado).'}
        return {'lufs': round(float(m['input_i']), 1), 'pico': round(float(m['input_tp']), 1),
                'rango': round(float(m['input_lra']), 1)}

    def picos_fuente(self, fid):
        """Picos del espectro de una fuente (para dibujar la onda de cada clip). Si todavia no se calcularon (un video recien sumado
        al panel), se calculan ahora."""
        with self._lock_proyecto:
            if fid in self.picos_fuentes:
                return {'picos': self.picos_fuentes[fid]}
            f = self.proyecto.fuentes.get(fid) if self.proyecto is not None else None
            ruta = f['ruta'] if f else None
        if ruta is None:
            return {'picos': []}
        try:
            calculados = picos(ruta, 2000).get('picos', [])
        except Exception as e:
            _registrar('picos de %s fallaron: %r' % (fid, e))
            calculados = []
        with self._lock_proyecto:
            self.picos_fuentes[fid] = calculados
        return {'picos': calculados}

    # --- exportar ---

    def exportar_opciones(self):
        """Lo que el dialogo de exportar necesita saber del proyecto actual."""
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para exportar.'}
            p = self.proyecto
            principal = next(iter(p.fuentes.values()))
            tiene_video = any(t['tipo'] == 'video' and t['clips'] for t in p.pistas)
            tiene_audio = any(t['tipo'] == 'audio' and not t['silenciada'] and t['clips'] for t in p.pistas)
            if tiene_video:
                duracion = max(p.fin(c) for t in p.pistas if t['tipo'] == 'video' for c in t['clips'])
            else:
                duracion = p.duracion()
            return {
                'carpeta': os.path.dirname(principal['ruta']),
                'nombre': os.path.splitext(os.path.basename(principal['ruta']))[0],
                'tiene_video': tiene_video, 'tiene_audio': tiene_audio, 'duracion': duracion,
                'disponible': exportar_mod is not None,
                'perfiles': [{'clave': k, 'nombre': v['nombre'], 'nota': v['nota'], 'ext': v['ext'], 'calidad': v.get('calidad', True), 'gif': k == 'gif', 'gpu': v['gpu']}
                             for k, v in exportar_mod.PERFILES.items()] if exportar_mod else [],
                'gif': {'ancho': list(exportar_mod.GIF_ANCHO), 'fps': list(exportar_mod.GIF_FPS), 'duracion_max': exportar_mod.GIF_DURACION_MAX} if exportar_mod else None,
                'gpu': bool(self.modo_acel == 'gpu' and self._acel_efectiva()
                            and self._acel_efectiva()['codificar']['usa'] == 'gpu'),
            }

    def exportar_destino(self, carpeta, nombre, formato, perfil='mp4_h264'):
        """El nombre libre que tendria el archivo (base-v1.ext, base-v2.ext...): no crea nada."""
        if exportar_mod is None:
            return {'error': 'El exportador no está disponible.'}
        if formato in exportar_mod.FORMATOS_AUDIO:
            ext = exportar_mod.FORMATOS_AUDIO[formato][0]
        elif formato in exportar_mod.FORMATOS_VIDEO:
            ext = exportar_mod.PERFILES.get(perfil, exportar_mod.PERFILES['mp4_h264'])['ext']
        else:
            return {'error': 'Formato desconocido.'}
        return {'archivo': exportar_mod.siguiente_destino(
            str(carpeta), exportar_mod._nombre_seguro(str(nombre)), ext)}

    def exportar_iniciar(self, opciones):
        """Arranca la exportacion en segundo plano, sobre una COPIA del proyecto de este momento:
        si la persona sigue editando mientras tanto, el archivo no cambia."""
        if exportar_mod is None:
            return {'error': 'El exportador no está disponible.'}
        try:
            formato = str(opciones.get('formato'))
            carpeta = str(opciones.get('carpeta') or '')
            nombre = str(opciones.get('nombre') or '')
            encuadre = str(opciones.get('encuadre') or 'recortar')
            foco = opciones.get('foco') or [0.5, 0.5]
            foco = (min(max(float(foco[0]), 0.0), 1.0), min(max(float(foco[1]), 0.0), 1.0))
            if not all(math.isfinite(x) for x in foco):
                raise ValueError('foco')
            normalizar = bool(opciones.get('normalizar'))
            subs = opciones.get('subtitulos') or {}
            subs = {k: bool(subs.get(k)) for k in ('quemar', 'srt', 'vtt')}
            perfil = str(opciones.get('perfil') or 'mp4_h264')
            calidad = str(opciones.get('calidad') or 'alta')
            gif = opciones.get('gif')
            if gif is not None:
                gif = {'ancho': int(gif.get('ancho', 480)), 'fps': int(gif.get('fps', 10))}
        except (AttributeError, TypeError, ValueError, IndexError):
            return {'error': 'Las opciones de exportación no son válidas.'}
        if formato not in exportar_mod.FORMATOS_VIDEO and formato not in exportar_mod.FORMATOS_AUDIO:
            return {'error': 'Formato desconocido.'}
        if perfil not in exportar_mod.PERFILES or calidad not in exportar_mod.CALIDADES:
            return {'error': 'El tipo de archivo o la calidad no son válidos.'}
        if not os.path.isdir(carpeta):
            return {'error': 'La carpeta de destino no existe: ' + carpeta}
        try:
            prueba = tempfile.NamedTemporaryFile(dir=carpeta, prefix='.moviola-', delete=True)
            prueba.close()
        except OSError:
            return {'error': 'No puedo escribir en esa carpeta. Elegí otra.'}
        with self._lock_export:
            if self.exportacion.get('estado') == 'exportando':
                return {'error': 'Ya hay una exportación en curso.'}
        with self._lock_lote:
            if self.lote.get('estado') == 'procesando':
                return {'error': 'Hay un preset procesando archivos: esperá a que termine o cancelalo.'}
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para exportar.'}
            # Solo hacen falta las pistas (las fuentes no se modifican); copiar tambien el historial de
            # deshacer seria copiar hasta 200 estados para nada.
            copia = Proyecto()
            copia.fuentes = dict(self.proyecto.fuentes)
            copia.pistas = copy.deepcopy(self.proyecto.pistas)
            copia.subtitulos = copy.deepcopy(self.proyecto.subtitulos)
        if any(subs.values()) and not copia.subtitulos['frases']:
            return {'error': 'Pediste subtítulos pero no hay ninguna frase: transcribí o escribí alguna primero.'}
        acel = self._acel_efectiva()
        # Para el archivo FINAL la calidad importa mas que la velocidad: Automatico usa el procesador;
        # solo se usa la GPU si la persona la eligio de forma explicita.
        codificador = (acel['codificar']['codificador']
                       if (self.modo_acel == 'gpu' and acel and acel['codificar']['usa'] == 'gpu') else None)
        if codificador and exportar_mod.PERFILES[perfil]['gpu'] == 'hevc':
            codificador = gpu_mod.codificador_hevc_disponible(self.deteccion, codificador)   # puede ser None: se usa el procesador
        evento = threading.Event()
        with self._lock_export:
            # Se vuelve a mirar ADENTRO del mismo candado que lo marca: dos pedidos a la vez no pasan los dos.
            if self.exportacion.get('estado') == 'exportando':
                return {'error': 'Ya hay una exportación en curso.'}
            self._cancelar_export = evento
            self.exportacion = {'estado': 'exportando', 'progreso': 0.0, 'formato': formato}
        threading.Thread(target=self._exportar, daemon=True, args=(
            copia, carpeta, nombre or None, formato, encuadre, foco, normalizar, codificador, evento, subs, perfil, calidad, gif)).start()
        return {'ok': True}

    def _exportar(self, copia, carpeta, nombre, formato, encuadre, foco, normalizar, codificador, evento, subs=None,
                  perfil='mp4_h264', calidad='alta', gif=None):
        def avance(fraccion):
            with self._lock_export:
                if self.exportacion.get('estado') == 'exportando':
                    self.exportacion['progreso'] = round(float(fraccion), 3)

        try:
            r = exportar_mod.exportar(copia, carpeta, nombre, formato, encuadre, foco, normalizar, -14.0, None,
                                      codificador, avance, evento, subtitulos=subs, perfil=perfil, calidad=calidad, gif=gif)
            tam = os.path.getsize(r['archivo'])
            with self._lock_export:
                self._ultimo_export = r['archivo']
                self.exportacion = {
                    'estado': 'listo', 'progreso': 1.0, 'formato': formato, 'archivo': r['archivo'],
                    'nombre': os.path.basename(r['archivo']), 'carpeta': os.path.dirname(r['archivo']),
                    'duracion': round(r['duracion'], 2), 'tamano_bytes': tam, 'dimensiones': r.get('tamano'),
                    'fps': _fps_numero(r.get('fps')), 'respaldo': bool(r.get('respaldo')), 'motivo_respaldo': r.get('motivo_respaldo', ''),
                    'normalizado': bool(r.get('normalizacion')), 'pidio_normalizar': normalizar,
                    'subtitulos': [os.path.basename(x) for x in r.get('subtitulos', [])],
                    'perfil': exportar_mod.PERFILES[perfil]['nombre'] if formato in exportar_mod.FORMATOS_VIDEO else '', 'calidad': calidad}
        except _Cancelado:
            with self._lock_export:
                self.exportacion = {'estado': 'cancelado', 'progreso': 0.0}
        except exportar_mod.ExportError as e:
            _registrar('exportar fallo: ' + str(e))
            with self._lock_export:
                self.exportacion = {'estado': 'error', 'progreso': 0.0, 'error': str(e)}
        except Exception as e:
            _registrar('exportar fallo: ' + traceback.format_exc())
            with self._lock_export:
                self.exportacion = {'estado': 'error', 'progreso': 0.0,
                                    'error': 'No pude exportar. ' + _explicar(e)}

    def exportar_estado(self):
        with self._lock_export:
            return dict(self.exportacion)

    def exportar_cancelar(self):
        with self._lock_export:
            evento = self._cancelar_export
            exportando = self.exportacion.get('estado') == 'exportando'
        if evento is not None and exportando:
            evento.set()
        return {'ok': True}

    # --- presets y lotes (motor/lotes.py) ---

    def presets_catalogo(self):
        """Los presets («Reel en un clic») y lo que esta PC puede hacer con ellos (transcribir necesita whisper)."""
        if lotes_mod is None:
            return {'error': 'Los presets no están disponibles.'}
        with self._lock_proyecto:
            principal = next(iter(self.proyecto.fuentes.values()), None) if self.proyecto is not None else None
        return {'presets': lotes_mod.lista_presets(),
                'transcripcion': subtitulos_mod.estado_transcripcion() if subtitulos_mod else {'disponible': False, 'motivo': 'Los subtítulos no están disponibles.'},
                'idiomas': [{'valor': k, 'nombre': n} for k, n in subtitulos_mod.IDIOMAS] if subtitulos_mod else [],
                'hay_proyecto': self.proyecto is not None,
                'carpeta': os.path.join(os.path.dirname(principal['ruta']), lotes_mod.CARPETA_SALIDA) if principal else '',
                'maximo': lotes_mod.ENTRADAS_MAX}

    def lote_iniciar(self, opciones):
        """Procesa con un preset, en segundo plano: el PROYECTO ABIERTO (una copia de este momento; lo que se ve no cambia) o una lista de archivos.
        opciones: {preset, cambios, origenes: [rutas] o None, carpeta}. Un archivo con problemas no detiene a los demas."""
        if lotes_mod is None or exportar_mod is None:
            return {'error': 'Los presets no están disponibles.'}
        try:
            clave = str(opciones.get('preset'))
            cambios = opciones.get('cambios') or {}
            origenes = opciones.get('origenes')
            carpeta = str(opciones.get('carpeta') or '')
            if not isinstance(cambios, dict):
                raise TypeError('cambios')
            receta = lotes_mod.preparar_preset(clave, cambios)
            if origenes is not None:
                if not isinstance(origenes, list) or not origenes or not all(isinstance(o, str) for o in origenes):
                    raise TypeError('origenes')
                origenes = lotes_mod.listar_entradas(origenes)
        except lotes_mod.ErrorLote as e:
            return {'error': str(e)}
        except (AttributeError, TypeError, ValueError):
            return {'error': 'Las opciones del preset no son válidas.'}
        copia = None
        if origenes is None:
            copia = self._copia_del_proyecto()
            if copia is None:
                return {'error': 'No hay nada abierto: elegí los archivos que querés procesar.'}
            principal = next(iter(copia.fuentes.values()))
            if not carpeta:
                carpeta = os.path.join(os.path.dirname(principal['ruta']), lotes_mod.CARPETA_SALIDA)
        elif carpeta and not os.path.isdir(carpeta):
            return {'error': 'La carpeta de destino no existe: ' + carpeta}
        if carpeta:
            try:
                os.makedirs(carpeta, exist_ok=True)
                tempfile.NamedTemporaryFile(dir=carpeta, prefix='.moviola-', delete=True).close()
            except OSError:
                return {'error': 'No puedo escribir en esa carpeta. Elegí otra.'}
        with self._lock_export:
            if self.exportacion.get('estado') == 'exportando':
                return {'error': 'Hay una exportación en curso: esperá a que termine.'}
        evento = threading.Event()
        with self._lock_lote:
            if self.lote.get('estado') == 'procesando':
                return {'error': 'Ya hay un preset procesando archivos.'}
            self._cancelar_lote = evento
            n = 1 if copia is not None else len(origenes)
            self.lote = {'estado': 'procesando', 'progreso': 0.0, 'i': 0, 'n': n, 'nombre': '', 'paso': 'Empezando…', 'resultados': [],
                         'preset': receta['nombre']}
        threading.Thread(target=self._lote, daemon=True, args=(receta, copia, origenes, carpeta or None, evento)).start()
        return {'ok': True, 'n': n}

    def _lote(self, receta, copia, origenes, carpeta, evento):
        def progreso(i, n, fr, nombre):
            with self._lock_lote:
                if self.lote.get('estado') == 'procesando':
                    self.lote.update(i=i, n=n, nombre=nombre, progreso=round(min(1.0, (i + fr) / float(n)), 3))

        def paso(i, n, p, texto):
            with self._lock_lote:
                if self.lote.get('estado') == 'procesando':
                    self.lote.update(i=i, n=n, paso=texto)

        def compacto(r):
            if not r.get('ok'):
                return {'origen': r.get('origen', ''), 'nombre': os.path.basename(r.get('origen', '')), 'ok': False,
                        'cancelado': bool(r.get('cancelado')), 'error': r.get('error', '')}
            return {'origen': r['origen'], 'nombre': os.path.basename(r['archivo']), 'ok': True, 'archivo': r['archivo'], 'carpeta': os.path.dirname(r['archivo']),
                    'duracion': round(r['duracion'], 2), 'tamano_bytes': os.path.getsize(r['archivo']), 'avisos': r.get('avisos', []),
                    'silencios_quitados': r.get('silencios_quitados', 0), 'frases': r.get('frases', 0), 'subtitulos': [os.path.basename(x) for x in r.get('subtitulos', [])]}

        try:
            if copia is not None:
                principal = next(iter(copia.fuentes.values()))
                nombre_proyecto = os.path.basename(principal['ruta'])
                try:
                    r = lotes_mod.procesar(nombre_proyecto, carpeta, receta, None, lambda fr: progreso(0, 1, fr, nombre_proyecto), evento,
                                           lambda p, t: paso(0, 1, p, t), None, copia)
                    r['ok'] = True
                except _Cancelado:
                    r = {'origen': principal['ruta'], 'ok': False, 'cancelado': True, 'error': 'Cancelado.'}
                except (lotes_mod.ErrorLote, exportar_mod.ExportError, ErrorEdicion) as e:
                    r = {'origen': principal['ruta'], 'ok': False, 'error': str(e)}
                resultado = {'resultados': [r], 'ok': 1 if r['ok'] else 0, 'fallaron': 0 if (r['ok'] or r.get('cancelado')) else 1,
                             'canceladas': 1 if r.get('cancelado') else 0}
            else:
                resultado = lotes_mod.procesar_lote(origenes, carpeta, receta, progreso, evento, paso)
            filas = [compacto(r) for r in resultado['resultados']]
            ultimo = next((f['archivo'] for f in reversed(filas) if f.get('ok')), None)
            with self._lock_export:
                if ultimo:
                    self._ultimo_export = ultimo
            estado = 'cancelado' if (evento.is_set() and not any(f['ok'] for f in filas) or resultado['canceladas'] and not resultado['ok']) else 'listo'
            with self._lock_lote:
                self.lote = {'estado': estado, 'progreso': 1.0 if estado == 'listo' else 0.0, 'n': len(filas), 'resultados': filas, 'ok': resultado['ok'],
                             'fallaron': resultado['fallaron'], 'canceladas': resultado['canceladas'], 'preset': receta['nombre']}
        except Exception as e:
            _registrar('lote fallo: ' + traceback.format_exc())
            with self._lock_lote:
                self.lote = {'estado': 'error', 'progreso': 0.0, 'error': 'No pude procesar. ' + _explicar(e), 'resultados': []}

    def lote_estado(self):
        with self._lock_lote:
            return copy.deepcopy(self.lote)

    def lote_cancelar(self):
        with self._lock_lote:
            evento = self._cancelar_lote
            activo = self.lote.get('estado') == 'procesando'
        if evento is not None and activo:
            evento.set()
        return {'ok': True}

    def elegir_carpeta(self):
        """Dialogo del sistema para elegir la carpeta de destino."""
        try:
            if self.ventana is not None:
                import webview
                v = self.ventana.create_file_dialog(webview.FileDialog.FOLDER)
                ruta = v[0] if isinstance(v, (list, tuple)) and v else (v or '')
            else:
                ruta = _con_tk(lambda filedialog: filedialog.askdirectory(title='Carpeta de destino'))
            return {'ruta': ruta} if ruta else {'cancelado': True}
        except Exception as e:
            _registrar('elegir carpeta fallo: ' + repr(e))
            return {'error': 'No pude abrir el selector de carpetas.'}

    def mostrar_en_carpeta(self):
        """Abre el explorador de archivos con el ULTIMO archivo exportado seleccionado.
        No recibe ninguna ruta de la interfaz: solo abre lo que la app misma exporto."""
        with self._lock_export:
            ruta = self._ultimo_export
        if not ruta or not os.path.isfile(ruta):
            return {'error': 'No encuentro el archivo exportado.'}
        try:
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', '/select,', os.path.normpath(ruta)])
            else:
                import webbrowser
                webbrowser.open('file://' + os.path.dirname(ruta))
            return {'ok': True}
        except Exception as e:
            _registrar('mostrar en carpeta fallo: ' + repr(e))
            return {'error': 'No pude abrir la carpeta.'}

    # --- aceleracion por GPU ---

    def _detectar_gpu(self, forzar=False):
        """Prueba de verdad que puede la PC. Tarda ~10 s, asi que se guarda: solo se repite
        si cambia el equipo, el controlador o el ffmpeg, o si la persona lo pide."""
        with self._lock_gpu:
            if self.detectando:
                return
            self.detectando = True
            if forzar:
                self.deteccion = None
        try:
            ajustes = gpu_mod.leer_ajustes(self.ajustes_ruta)
            guardada = ajustes.get('deteccion')
            if guardada and not forzar and guardada.get('version') == gpu_mod.VERSION:
                if guardada.get('huella') == gpu_mod._huella(gpu_mod.listar_equipo()):
                    self.deteccion = guardada
                    return
            det = gpu_mod.detectar()
            self.deteccion = det
            self._cambiar_ajustes(lambda a: a.__setitem__('deteccion', det))      # se relee: en estos 10 s pudo cambiar otra cosa
            self.error_gpu = ''
        except Exception as e:
            _registrar('deteccion de GPU fallo: ' + traceback.format_exc())
            self.error_gpu = 'No pude comprobar la aceleración por GPU.'
        finally:
            self.detectando = False

    def _acel_efectiva(self):
        """Que se usa de verdad (con el motivo), o None si todavia no se sabe."""
        if gpu_mod is None or self.deteccion is None:
            return None
        return gpu_mod.resolver(self.deteccion, self.modo_acel)

    def gpu_estado(self):
        det = self.deteccion
        ajustes = gpu_mod.leer_ajustes(self.ajustes_ruta) if gpu_mod else {}
        resumen = gpu_mod.resumen(det) if (gpu_mod and det) else None
        # Se avisa al abrir cuando hay algo que decidir (GPU util y se esta usando el procesador)
        # o la primera vez que se ve este equipo. Si no, no se molesta en cada arranque.
        avisar = bool(det and resumen and (
            ajustes.get('aviso_huella') != det.get('huella') or (resumen['util'] and self.modo_acel == 'cpu')))
        return {'disponible': gpu_mod is not None, 'listo': det is not None, 'detectando': self.detectando,
                'modo': self.modo_acel, 'resumen': resumen,
                'efectivo': gpu_mod.resolver(det, self.modo_acel) if (gpu_mod and det) else None,
                'fecha': det['fecha'] if det else '', 'error': self.error_gpu, 'avisar': avisar}

    def gpu_modo(self, modo):
        if modo not in ('cpu', 'gpu', 'auto'):
            return {'error': 'Modo de aceleración desconocido.'}
        self.modo_acel = modo
        if gpu_mod is not None:
            try:
                self._cambiar_ajustes(lambda a: a.__setitem__('aceleracion', modo))
            except OSError as e:
                _registrar('no pude guardar ajustes: ' + repr(e))
        return self.gpu_estado()

    def gpu_comprobar(self):
        if gpu_mod is not None:
            threading.Thread(target=self._detectar_gpu, args=(True,), daemon=True).start()
            time.sleep(0.05)
        return self.gpu_estado()

    def gpu_visto(self):
        """La interfaz ya mostro el aviso para este equipo."""
        if gpu_mod is not None and self.deteccion is not None:
            huella = self.deteccion.get('huella')
            try:
                self._cambiar_ajustes(lambda a: a.__setitem__('aviso_huella', huella))
            except OSError:
                pass
        return {'ok': True}

    # --- proxy de reproduccion ---

    def _limpiar_cache(self):
        try:
            proxy_mod.limpiar(self.cache)
        except Exception as e:
            _registrar('limpiar cache fallo: ' + repr(e))

    def _cancelar_proxy_actual(self):
        with self._lock_proxy:
            self._epoca_proxy += 1        # los hilos viejos dejan de ser vigentes
            if self._cancelar_proxy is not None:
                self._cancelar_proxy.set()
                self._cancelar_proxy = None

    def _preparar_reproduccion(self, ruta, info):
        """Decide como se va a escuchar este archivo y completa info:
        url, reproducible y proxy ('nada' | 'listo' | 'generando')."""
        self._cancelar_proxy_actual()
        with self._lock_proxy:
            self.estado_proxy = {'ruta': ruta, 'estado': 'nada', 'progreso': 0.0, 'url': '', 'error': ''}
        if info.get('web_compatible'):
            info.update(reproducible=True, proxy='nada', url=self.servidor.publicar(ruta))
            return
        info.update(reproducible=False, proxy='nada', url='')
        if proxy_mod is None:
            return
        try:
            existente = proxy_mod.hay_proxy(ruta, self.cache)
        except Exception as e:
            _registrar('hay_proxy fallo: ' + repr(e))
            existente = None
        if existente:
            url = self.servidor.publicar(existente)
            with self._lock_proxy:
                self.estado_proxy.update(estado='listo', progreso=1.0, url=url)
            info.update(reproducible=True, proxy='listo', url=url)
            return
        with self._lock_proxy:
            epoca = self._epoca_proxy
            evento = threading.Event()
            self._cancelar_proxy = evento
            self.estado_proxy['estado'] = 'generando'
        info.update(proxy='generando')
        threading.Thread(target=self._generar_proxy, args=(ruta, epoca, evento), daemon=True).start()

    def _generar_proxy(self, ruta, epoca, evento):
        def vigente():
            return epoca == self._epoca_proxy

        def avance(fraccion):
            with self._lock_proxy:
                if vigente():
                    self.estado_proxy['progreso'] = round(float(fraccion), 3)

        try:
            acel = self._acel_efectiva()
            codificador = acel['codificar']['codificador'] if (acel and acel['codificar']['usa'] == 'gpu') else None
            r = proxy_mod.generar(ruta, self.cache, al_progresar=avance, cancelar=evento, codificador=codificador)
            with self._lock_proxy:
                if not vigente():
                    return                      # mientras tanto se abrio otro archivo
                url = self.servidor.publicar(r['archivo'])
                self.estado_proxy.update(estado='listo', progreso=1.0, url=url,
                                         usado=r.get('usado', 'cpu'), respaldo=bool(r.get('respaldo')),
                                         motivo_respaldo=r.get('motivo_respaldo', ''))
            if r.get('respaldo'):
                _registrar('el codificador de GPU fallo y se uso el procesador: ' + r.get('motivo_respaldo', ''))
        except proxy_mod.Cancelado:
            return
        except Exception as e:
            _registrar('proxy de ' + ruta + os.linesep + traceback.format_exc())
            mensaje = str(e) if isinstance(e, proxy_mod.ProxyError) else 'No pude preparar la reproducción de este archivo.'
            with self._lock_proxy:
                if vigente():
                    self.estado_proxy.update(estado='error', error=mensaje)

    def proxy_estado(self):
        """Lo consulta la interfaz mientras se prepara la reproduccion."""
        with self._lock_proxy:
            return dict(self.estado_proxy)

    def cerrar(self):
        if self._temporizador_recup is not None:
            self._temporizador_recup.cancel()
        self._escribir_recuperacion()               # lo ultimo que se hizo no se pierde aunque se haya cerrado enseguida
        self._cancelar_todo()
        self._cancelar_proxy_actual()
        with self.lock:
            self._soltar_video()
        if self.servidor is not None:
            self.servidor.cerrar()
        shutil.rmtree(self.temp, ignore_errors=True)      # la miniatura temporal de esta sesion

    # --- API que ve la interfaz ---

    def acerca_de(self):
        """Lo que muestra «Acerca de Moviola»: version, autoria, licencia y que herramientas hay en esta computadora."""
        import importlib.metadata as md

        def v(paquete):
            try:
                return md.version(paquete)
            except Exception:
                return ''
        w = subtitulos_mod.buscar_whisper() if subtitulos_mod else None
        m = subtitulos_mod.buscar_modelo() if subtitulos_mod else None
        y = descargas_mod.buscar_ytdlp() if descargas_mod else None
        ff = _version_ffmpeg()
        return {
            'nombre': 'Moviola', 'version': VERSION,
            'descripcion': 'Editor de video y audio que corre en tu computadora: no sube nada.',
            'autores': 'Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)',
            'anio': '2026',
            'licencia': 'GNU GPL v3 o posterior',
            'garantia': 'Se distribuye SIN NINGUNA GARANTÍA.',
            'herramientas': [
                {'nombre': 'FFmpeg', 'hay': bool(ff), 'detalle': ff or 'No encontrado: hace falta para exportar.'},
                {'nombre': 'Transcribir (whisper)', 'hay': bool(w and m), 'detalle': (os.path.basename(m) if (w and m) else 'No está instalado: sin él no se transcribe.')},
                {'nombre': 'Bajar de YouTube (yt-dlp)', 'hay': bool(y), 'detalle': os.path.basename(y) if y else 'No está instalado: winget install yt-dlp.yt-dlp'},
            ],
            'componentes': [
                {'nombre': 'FFmpeg', 'licencia': 'GPL v3'}, {'nombre': 'PyAV ' + v('av'), 'licencia': 'BSD'},
                {'nombre': 'pywebview ' + v('pywebview'), 'licencia': 'BSD'}, {'nombre': 'Pillow ' + v('pillow'), 'licencia': 'MIT-CMU'},
                {'nombre': 'Python ' + sys.version.split()[0], 'licencia': 'PSF'}],
            'carpeta_datos': DATOS,
        }

    def acerca_licencia(self):
        """Abre el archivo LICENSE del programa con el visor del sistema. No recibe ninguna ruta: solo abre el suyo."""
        ruta = os.path.join(AQUI, 'LICENSE')
        if not os.path.isfile(ruta):
            return {'error': 'No encuentro el archivo LICENSE junto al programa.'}
        try:
            if sys.platform == 'win32':
                os.startfile(ruta)
            else:
                import webbrowser
                webbrowser.open('file://' + ruta)
            return {'ok': True}
        except Exception as e:
            _registrar('abrir licencia fallo: ' + repr(e))
            return {'error': 'No pude abrir el archivo de la licencia.'}

    def inicial(self):
        """Archivo pasado por linea de comandos; se entrega una sola vez."""
        ruta, self.archivo_inicial = self.archivo_inicial, None
        return {'ruta': ruta}

    def elegir_archivo(self):
        try:
            if self.ventana is not None:
                import webview
                v = self.ventana.create_file_dialog(
                    webview.FileDialog.OPEN, allow_multiple=False, file_types=TIPOS)
                ruta = v[0] if isinstance(v, (list, tuple)) and v else (v or '')
            else:
                ruta = _dialogo_tkinter()
            if not ruta:
                return {'cancelado': True}
            return {'ruta': ruta}
        except Exception as e:
            _registrar('dialogo fallo: ' + repr(e))
            return {'error': 'No pude abrir el selector de archivos. Probá arrastrar el archivo a la ventana.'}

    def elegir_proyecto(self):
        """Dialogo del sistema para elegir un proyecto guardado (.moviola)."""
        try:
            if self.ventana is not None:
                import webview
                v = self.ventana.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                    file_types=('Proyectos de Moviola (*' + EXT_PROYECTO + ')', 'Todos los archivos (*.*)'))
                ruta = v[0] if isinstance(v, (list, tuple)) and v else (v or '')
            else:
                ruta = _con_tk(lambda filedialog: filedialog.askopenfilename(title='Abrir un proyecto', filetypes=[('Proyectos de Moviola', '*' + EXT_PROYECTO), ('Todos los archivos', '*.*')]))
            return {'ruta': ruta} if ruta else {'cancelado': True}
        except Exception as e:
            _registrar('elegir proyecto fallo: ' + repr(e))
            return {'error': 'No pude abrir el selector de archivos.'}

    def abrir(self, ruta):
        """Abre un video o un audio como proyecto nuevo (o, si es un archivo .moviola, abre ese proyecto)."""
        if str(ruta).lower().endswith(EXT_PROYECTO):
            return self.abrir_proyecto(ruta)
        return self._abrir(ruta)

    def _abrir(self, ruta, _datos_proyecto=None, _ruta_proyecto=None, _recuperando=False):
        """Con `_datos_proyecto` (uso interno de abrir_proyecto) abre ESE archivo como el principal y arma el proyecto guardado en vez de uno nuevo."""
        try:
            ruta = os.path.abspath(ruta)
            if not os.path.isfile(ruta):
                return {'error': 'No encontré el archivo: ' + ruta}

            with self.lock:
                # Se abre el nuevo ANTES de soltar el anterior: si falla, la
                # pantalla sigue mostrando el video viejo y el motor tambien lo
                # tiene. Antes se cerraba primero y quedaban desincronizados.
                acel = self._acel_efectiva()
                tipo = acel['decodificar']['tipo'] if (acel and acel['decodificar']['usa'] == 'gpu') else None
                try:
                    nuevo = Video(ruta, aceleracion=tipo)
                    info = dict(nuevo.info())
                    tabla = nuevo.tabla_tiempos()
                    if info.get('vfr'):
                        # Con framerate variable el cuadro n no esta en n/fps:
                        # el frontend necesita el segundo real de cada cuadro.
                        info['tiempos'] = tabla
                except SinVideo:
                    nuevo = None
                    tabla = None
                    info = self._datos_solo_audio(ruta)

            # El proyecto guardado se arma ENTERO antes de cambiar el video del visor: si falla (otro de sus videos no se puede leer), el
            # visor y el proyecto abierto siguen siendo los de antes, no una mezcla.
            try:
                self._agregar_espectro(ruta, info)
                preparado = self._preparar_proyecto(_datos_proyecto, ruta, info, tabla) if _datos_proyecto is not None else None
            except BaseException:
                if nuevo is not None:
                    nuevo.cerrar()
                raise
            with self.lock:
                self._soltar_video()
                self.video = nuevo
                self.ruta = ruta
            if preparado is not None:
                self._instalar_proyecto(*preparado)
            else:
                self._armar_proyecto(ruta, info, tabla)
            self.ruta_proyecto = _ruta_proyecto
            self._cambios = self._cambios_guardados = 0
            if not _recuperando:
                self._borrar_recuperacion()
            if not _recuperando:
                self._recordar(_ruta_proyecto or ruta, 'proyecto' if _ruta_proyecto else 'video')
            with self._lock_proyecto:
                info['proyecto'] = self._proyecto_dict()      # la interfaz lo necesita desde el primer cuadro

            info['tira'] = ''
            info['tira_cantidad'] = 0
            info['tira_ancho_mini'] = 0
            info['tira_alto_mini'] = 0
            if not info.get('solo_audio'):
                try:
                    destino = os.path.join(self.temp, 'tira.jpg')
                    t = tira(ruta, destino, info['duracion'], 120, 90)
                    info['tira'] = self._tira_data_uri(t['archivo'])
                    info['tira_cantidad'] = t['cantidad']
                    info['tira_ancho_mini'] = t['ancho_mini']
                    info['tira_alto_mini'] = t['alto_mini']
                except Exception as e:
                    # Sin miniaturas la app sigue siendo usable: el carril queda vacio.
                    _registrar('tira fallo: ' + repr(e))

            info['ruta'] = ruta
            info['fid'] = self.fid_principal
            info['nombre'] = os.path.basename(ruta)
            # El WebView rechaza file://, asi que el medio va por el servidor local. Si el
            # navegador no puede reproducir este formato se prepara un proxy en segundo plano.
            self._preparar_reproduccion(ruta, info)
            return info
        except ErrorEdicion as e:
            return {'error': str(e)}
        except Exception as e:
            _registrar('abrir ' + ruta + os.linesep + traceback.format_exc())
            return {'error': 'No pude abrir el archivo. ' + _explicar(e)}

    # --- panel de medios: varios videos en el proyecto ---

    def elegir_videos(self):
        """Dialogo del sistema para elegir uno o varios videos para el panel de medios."""
        try:
            if self.ventana is not None:
                import webview
                v = self.ventana.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=TIPOS[1:])
                rutas = list(v) if isinstance(v, (list, tuple)) else ([v] if v else [])
            else:
                rutas = _con_tk(lambda filedialog: list(filedialog.askopenfilenames(title='Agregar videos al proyecto',
                                                             filetypes=[('Video', ' '.join('*.' + e for e in _EXT_VIDEO.split(';'))), ('Todos los archivos', '*.*')])))
            return {'rutas': rutas} if rutas else {'cancelado': True}
        except Exception as e:
            _registrar('elegir videos fallo: ' + repr(e))
            return {'error': 'No pude abrir el selector de archivos.'}

    def agregar_medio(self, ruta):
        """Suma un video al panel de medios (no lo pone en la linea de tiempo: eso lo hace editar_insertar_fuente). Si ya esta, devuelve el que hay."""
        try:
            ruta = os.path.abspath(ruta)
            if not os.path.isfile(ruta):
                return {'error': 'No encontré el archivo: ' + ruta}
            with self._lock_proyecto:
                if self.proyecto is None:
                    return {'error': 'Primero abrí un video o un proyecto.'}
                fid = next((k for k, f in self.proyecto.fuentes.items() if os.path.abspath(f['ruta']) == ruta), None)
                if fid is not None:
                    return {'fuente': fid, 'repetido': True, 'proyecto': self._proyecto_dict()}
            try:
                v = Video(ruta)
            except SinVideo:
                return {'error': 'Ese archivo no tiene imagen. Para sumar música o una voz usá «Agregar audio».'}
            try:
                info = dict(v.info())
                tabla = v.tabla_tiempos()
            finally:
                v.cerrar()
            with self._lock_proyecto:
                fid = self.proyecto.agregar_fuente(ruta, 'video', info['duracion'], tabla, info.get('pistas_audio', 0), inicio=info['inicio'],
                                                   ancho=info['ancho'], alto=info['alto'], fps=info['fps'], vfr=bool(info.get('vfr')),
                                                   rotacion=info.get('rotacion', 0))
                self._marcar_cambio()
                d = self._proyecto_dict()
            return {'fuente': fid, 'repetido': False, 'proyecto': d}
        except Exception as e:
            _registrar('agregar medio ' + str(ruta) + os.linesep + traceback.format_exc())
            return {'error': 'No pude agregar ese archivo. ' + _explicar(e)}

    def medio_info(self, fid):
        """Lo que la interfaz necesita de un video que NO es el principal (y del principal, lo mismo): cuadros por segundo, tabla de
        cuadros si el video es de velocidad variable, espectro, tira de miniaturas y como reproducirlo."""
        with self._lock_proyecto:
            f = self.proyecto.fuentes.get(fid) if self.proyecto is not None else None
            if f is None or f['tipo'] != 'video':
                return {'error': 'Ese video no está en el proyecto.'}
            ruta = f['ruta']
            hecho = self.medios.get(fid)
        if hecho is not None:
            return self._con_estado_de_reproduccion(fid, dict(hecho))
        try:
            with self.lock:
                v = self._video_de(fid) if fid != self.fid_principal else self.video
                info = dict(v.info())
                tabla = v.tabla_tiempos()
            if info.get('vfr'):
                info['tiempos'] = tabla
            self._agregar_espectro(ruta, info)
            with self._lock_proyecto:
                self.picos_fuentes[fid] = info.get('picos', [])
            info['tira'] = ''
            info['tira_cantidad'] = info['tira_ancho_mini'] = info['tira_alto_mini'] = 0
            try:
                t = tira(ruta, os.path.join(self.temp, 'tira-%s.jpg' % fid), info['duracion'], 120, 90)
                info['tira'] = self._tira_data_uri(t['archivo'])
                info['tira_cantidad'] = t['cantidad']
                info['tira_ancho_mini'] = t['ancho_mini']
                info['tira_alto_mini'] = t['alto_mini']
            except Exception as e:
                _registrar('tira de %s fallo: %r' % (fid, e))
            info['ruta'] = ruta
            info['fid'] = fid
            info['nombre'] = os.path.basename(ruta)
            self._preparar_medio(fid, ruta, info)
            with self._lock_proyecto:
                self.medios[fid] = info
            return self._con_estado_de_reproduccion(fid, dict(info))
        except Exception as e:
            _registrar('medio_info ' + str(fid) + os.linesep + traceback.format_exc())
            return {'error': 'No pude leer ese video. ' + _explicar(e)}

    def _preparar_medio(self, fid, ruta, info):
        """Como se va a escuchar un video que no es el principal: directo si el navegador puede, o con una copia de reproduccion."""
        if info.get('web_compatible'):
            info.update(reproducible=True, proxy='nada', url=self.servidor.publicar_extra(ruta))
            return
        info.update(reproducible=False, proxy='nada', url='')
        if proxy_mod is None:
            return
        try:
            existente = proxy_mod.hay_proxy(ruta, self.cache)
        except Exception as e:
            _registrar('hay_proxy fallo: ' + repr(e))
            existente = None
        if existente:
            info.update(reproducible=True, proxy='listo', url=self.servidor.publicar_extra(existente))
            return
        evento = threading.Event()
        with self._lock_proxy:
            self.proxies[fid] = {'estado': 'generando', 'progreso': 0.0, 'url': '', 'error': '', 'evento': evento}
        info.update(proxy='generando')
        threading.Thread(target=self._generar_proxy_medio, args=(fid, ruta, evento), daemon=True).start()

    def _generar_proxy_medio(self, fid, ruta, evento):
        def avance(f):
            with self._lock_proxy:
                est = self.proxies.get(fid)
                if est is not None:
                    est['progreso'] = round(float(f), 3)

        try:
            acel = self._acel_efectiva()
            cod = acel['codificar']['codificador'] if (acel and acel['codificar']['usa'] == 'gpu') else None
            r = proxy_mod.generar(ruta, self.cache, al_progresar=avance, cancelar=evento, codificador=cod)
            url = self.servidor.publicar_extra(r['archivo'])
            with self._lock_proxy:
                est = self.proxies.get(fid)
                if est is not None:
                    est.update(estado='listo', progreso=1.0, url=url)
        except proxy_mod.Cancelado:
            return
        except Exception as e:
            _registrar('proxy de ' + ruta + os.linesep + traceback.format_exc())
            with self._lock_proxy:
                est = self.proxies.get(fid)
                if est is not None:
                    est.update(estado='error', error=str(e) if isinstance(e, proxy_mod.ProxyError) else 'No pude preparar la reproducción de este archivo.')

    def _con_estado_de_reproduccion(self, fid, info):
        with self._lock_proxy:
            est = self.proxies.get(fid)
            if est is not None:
                info['proxy'] = est['estado']
                info['proxy_progreso'] = est['progreso']
                info['proxy_error'] = est['error']
                if est['estado'] == 'listo':
                    info.update(reproducible=True, url=est['url'])
        return info

    def medio_estado(self, fid):
        """Lo consulta la interfaz mientras se prepara la reproduccion de uno de los otros videos."""
        with self._lock_proxy:
            est = self.proxies.get(fid)
            if est is None:
                return {'estado': 'nada', 'progreso': 0.0, 'url': '', 'error': ''}
            return {k: v for k, v in est.items() if k != 'evento'}

    def quitar_medio(self, fid):
        """Saca un video del panel de medios. Solo si ningun clip lo usa, y nunca el principal."""
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto.'}
            if fid == self.fid_principal:
                return {'error': 'Ese es el video principal del proyecto: no se puede sacar.'}
            try:
                self.proyecto.quitar_fuente(fid)
            except ErrorEdicion as e:
                return {'error': str(e), 'proyecto': self._proyecto_dict()}
            self.medios.pop(fid, None)
            self.picos_fuentes.pop(fid, None)
            self._marcar_cambio()
            d = self._proyecto_dict()
        with self._lock_proxy:
            est = self.proxies.pop(fid, None)
        if est and est.get('evento') is not None and est['estado'] == 'generando':
            est['evento'].set()
        with self.lock:
            v = self.videos.pop(fid, None)
            if v is not None:
                v.cerrar()
        return {'proyecto': d}

    # --- proyectos guardados (.moviola) ---

    def _preparar_proyecto(self, datos, ruta_principal, info, tabla):
        """Arma (sin instalarlo) el proyecto GUARDADO. `ruta_principal` es el archivo que va a quedar en el visor (info y tabla son suyos).
        Devuelve lo que necesita `_instalar_proyecto`; si algo falla, no cambio nada."""
        def tiempos_de(f):
            if os.path.abspath(f['ruta']) == ruta_principal:
                return tabla
            with Video(f['ruta']) as v:                       # otro video del proyecto: se lee su tabla de cuadros
                return v.tabla_tiempos()

        p = Proyecto.cargar_dict(datos, tiempos_de)
        picos_f = {}
        for fid, f in p.fuentes.items():
            if os.path.abspath(f['ruta']) == ruta_principal:
                picos_f[fid] = info.get('picos', [])
            elif f['tipo'] == 'audio':
                f['url'] = self.servidor.publicar_extra(f['ruta'])
                try:
                    picos_f[fid] = picos(f['ruta'], 2000).get('picos', [])
                except Exception as e:
                    _registrar('picos del audio extra fallaron: ' + repr(e))
                    picos_f[fid] = []
        problemas = p.validar()
        if problemas:
            _registrar('proyecto guardado invalido: ' + '; '.join(problemas[:5]))
            raise ErrorEdicion('El proyecto guardado está dañado y no se puede abrir.')
        return p, picos_f, ruta_principal

    def _instalar_proyecto(self, p, picos_f, ruta_principal):
        with self._lock_proyecto:
            self.proyecto = p
            self.picos_fuentes = picos_f
            self.fid_principal = next((k for k, f in p.fuentes.items() if os.path.abspath(f['ruta']) == ruta_principal), None)
            self.medios = {}
            self.proxies = {}

    def _recordar(self, ruta, tipo):
        """Los ultimos archivos abiertos (para la pantalla de inicio): se guardan junto con los demas ajustes."""
        if gpu_mod is None:
            return
        try:
            def poner(ajustes):
                lista = [x for x in ajustes.get('recientes', []) if isinstance(x, dict) and x.get('ruta') != ruta]
                lista.insert(0, {'ruta': ruta, 'tipo': tipo, 'fecha': time.strftime('%Y-%m-%d %H:%M')})
                ajustes['recientes'] = lista[:12]
            self._cambiar_ajustes(poner)
        except (OSError, ValueError, TypeError) as e:
            _registrar('no pude guardar los recientes: ' + repr(e))

    def recientes(self):
        """Los ultimos proyectos y videos abiertos que todavia existen, el mas nuevo primero."""
        if gpu_mod is None:
            return {'recientes': []}
        ajustes = gpu_mod.leer_ajustes(self.ajustes_ruta)
        out = []
        for x in ajustes.get('recientes', []):
            if isinstance(x, dict) and isinstance(x.get('ruta'), str) and os.path.isfile(x['ruta']):
                out.append({'ruta': x['ruta'], 'nombre': os.path.basename(x['ruta']), 'carpeta': os.path.dirname(x['ruta']),
                            'tipo': 'proyecto' if x['ruta'].lower().endswith(EXT_PROYECTO) else 'video', 'fecha': x.get('fecha', '')})
        recup = None
        ruta_r = self._ruta_recuperacion()
        if os.path.isfile(ruta_r):
            try:
                with open(ruta_r, encoding='utf-8') as f:
                    d = json.load(f)
                rutas = [x.get('ruta') for x in d['fuentes'].values()]
                if rutas and all(isinstance(x, str) and os.path.isfile(x) for x in rutas):       # si los archivos ya no estan, no hay nada que recuperar
                    recup = {'nombre': os.path.basename(rutas[0]), 'fecha': time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(ruta_r)))}
            except (OSError, ValueError, KeyError, AttributeError):
                recup = None
        return {'recientes': out[:8], 'recuperacion': recup}

    def abrir_recuperacion(self):
        """Abre la copia del trabajo que quedo sin guardar. Queda como proyecto SIN nombre y sin guardar."""
        ruta = self._ruta_recuperacion()
        if not os.path.isfile(ruta):
            return {'error': 'No hay ningún trabajo para recuperar.'}
        r = self.abrir_proyecto(ruta, True)
        if not r.get('error'):
            with self._lock_proyecto:
                self.ruta_proyecto = None
                self._cambios_guardados = self._cambios - 1          # distinto de _cambios: figura sin guardar
                r['proyecto'] = self._proyecto_dict()
        return r

    def descartar_recuperacion(self):
        self._borrar_recuperacion()
        return {'ok': True}

    def olvidar_reciente(self, ruta):
        if gpu_mod is None:
            return {'ok': True}
        def sacar(ajustes):
            ajustes['recientes'] = [x for x in ajustes.get('recientes', []) if not (isinstance(x, dict) and x.get('ruta') == ruta)]
        try:
            self._cambiar_ajustes(sacar)
        except OSError as e:
            _registrar('no pude guardar los recientes: ' + repr(e))
        return {'ok': True}

    def abrir_proyecto(self, ruta, _recuperando=False):
        """Abre un proyecto guardado: el primer video (o audio) es el principal y el resto de los archivos se buscan donde estaban o
        junto al proyecto. Si falta alguno, no se abre nada y se dice cuales faltan."""
        try:
            ruta = os.path.abspath(ruta)
            if not os.path.isfile(ruta):
                return {'error': 'No encontré el proyecto: ' + ruta}
            try:
                with open(ruta, encoding='utf-8') as f:
                    datos = json.load(f, parse_constant=_no_constante)
            except (OSError, ValueError, RecursionError):
                return {'error': 'No pude leer el proyecto: el archivo está dañado.'}
            if not isinstance(datos, dict) or datos.get('version') != 1 or not isinstance(datos.get('fuentes'), dict) or not datos['fuentes']:
                return {'error': 'Ese archivo no es un proyecto de Moviola (o es de otra versión del programa).'}
            faltan = []
            for f in datos['fuentes'].values():
                if not isinstance(f, dict) or not isinstance(f.get('ruta'), str):
                    return {'error': 'El proyecto está dañado y no se puede abrir.'}
                if not os.path.isfile(f['ruta']):
                    al_lado = os.path.join(os.path.dirname(ruta), os.path.basename(f['ruta']))      # por si se movio la carpeta entera
                    if os.path.isfile(al_lado):
                        f['ruta'] = al_lado
                    else:
                        faltan.append(os.path.basename(f['ruta']))
            if faltan:
                return {'error': 'Faltan estos archivos del proyecto: ' + ', '.join(faltan[:6]) + (' y %d más' % (len(faltan) - 6) if len(faltan) > 6 else '') +
                                 '. Ponelos donde estaban (o junto al proyecto) y volvé a abrirlo.'}
            # Se comprueba el proyecto ENTERO antes de tocar nada: si se descubriera que esta dañado cuando el video ya se cambio, el visor
            # quedaria mostrando un video que no es el del proyecto que sigue abierto.
            try:
                prueba = Proyecto.cargar_dict(copy.deepcopy(datos), None)
                if prueba.validar():
                    return {'error': 'El proyecto guardado está dañado y no se puede abrir.'}
            except Exception as e:
                _registrar('proyecto invalido: ' + repr(e))
                return {'error': 'El proyecto guardado está dañado y no se puede abrir.'}
            cambiado = self._fuente_cambiada(datos)
            if cambiado:
                return {'error': '«%s» no es el mismo archivo que cuando se guardó el proyecto (ahora dura mucho menos). Poné el original '
                                 'en su lugar y volvé a abrirlo.' % cambiado}
            fuentes = list(datos['fuentes'].values())
            principal = next((f for f in fuentes if f.get('tipo') == 'video'), fuentes[0])
            for f in fuentes:
                f['ruta'] = os.path.abspath(f['ruta'])
            return self._abrir(os.path.abspath(principal['ruta']), datos, None if _recuperando else ruta, _recuperando)
        except ErrorEdicion as e:
            return {'error': str(e)}
        except Exception as e:
            _registrar('abrir proyecto ' + str(ruta) + os.linesep + traceback.format_exc())
            return {'error': 'No pude abrir el proyecto. ' + _explicar(e)}

    def _fuente_cambiada(self, datos):
        """El nombre de un archivo del proyecto que hoy dura MUCHO menos de lo que usan sus clips (lo reemplazaron por otro con el mismo
        nombre), o None. Los datos de cada archivo salen del proyecto guardado, no se vuelven a medir: esto ataja el caso grosero. El margen
        es amplio a proposito: la duracion que informa el contenedor de algunos formatos (MPEG-PS) es aproximada."""
        if proxy_mod is None:
            return None
        usado = {}
        for pista in datos.get('pistas') or []:
            for c in (pista.get('clips') or []) if isinstance(pista, dict) else []:
                if isinstance(c, dict) and isinstance(c.get('hasta'), (int, float)) and not isinstance(c.get('hasta'), bool):
                    usado[c.get('fuente')] = max(usado.get(c.get('fuente'), 0.0), float(c['hasta']))
        for fid, f in datos['fuentes'].items():
            if usado.get(fid, 0.0) <= 0:
                continue
            try:
                real, _tipos = proxy_mod._duracion_de(f['ruta'])
            except Exception:
                continue
            if real and real > 0 and usado[fid] > real * 1.25 + 2.0:
                return os.path.basename(f['ruta'])
        return None

    def _guardar_en(self, ruta):
        ruta = os.path.abspath(ruta)
        if not ruta.lower().endswith(EXT_PROYECTO):
            ruta += EXT_PROYECTO
        carpeta = os.path.dirname(ruta)
        if not os.path.isdir(carpeta):
            return {'error': 'La carpeta no existe: ' + carpeta}
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para guardar.'}
            try:
                self.proyecto.guardar(ruta)
            except OSError as e:
                return {'error': 'No pude guardar el proyecto. ' + _explicar(e)}
            self.ruta_proyecto = ruta
            self._cambios_guardados = self._cambios
            d = self._proyecto_dict()
        self._borrar_recuperacion()
        self._recordar(ruta, 'proyecto')
        return {'ruta': ruta, 'nombre': os.path.basename(ruta), 'proyecto': d}

    def guardar_proyecto(self):
        """Guarda en el archivo del proyecto; si todavia no tiene, pregunta donde."""
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para guardar.'}
            ruta = self.ruta_proyecto
        if not ruta:
            return self.guardar_proyecto_como()
        return self._guardar_en(ruta)

    def guardar_proyecto_como(self):
        with self._lock_proyecto:
            if self.proyecto is None:
                return {'error': 'No hay nada abierto para guardar.'}
            base = os.path.splitext(os.path.basename(self.ruta_proyecto or self.ruta or 'proyecto'))[0]
            carpeta = os.path.dirname(self.ruta_proyecto or self.ruta or '') or os.path.expanduser('~')
        try:
            if self.ventana is not None:
                import webview
                v = self.ventana.create_file_dialog(webview.FileDialog.SAVE, directory=carpeta, save_filename=base + EXT_PROYECTO,
                                                    file_types=('Proyectos de Moviola (*' + EXT_PROYECTO + ')',))
                ruta = v[0] if isinstance(v, (list, tuple)) and v else (v or '')
            else:
                ruta = _con_tk(lambda filedialog: filedialog.asksaveasfilename(title='Guardar el proyecto', initialdir=carpeta, initialfile=base + EXT_PROYECTO,
                                                        defaultextension=EXT_PROYECTO, filetypes=[('Proyectos de Moviola', '*' + EXT_PROYECTO)]))
        except Exception as e:
            _registrar('guardar como fallo: ' + repr(e))
            return {'error': 'No pude abrir el cuadro para guardar.'}
        if not ruta:
            return {'cancelado': True}
        return self._guardar_en(ruta)

    def _video_de(self, fid):
        """El Video abierto de un archivo del proyecto (el principal, o uno de los otros, que se abre la primera vez que se pide).
        Se llama con `self.lock` tomado. Se guardan hasta 3 de los otros: mas gastaria memoria de decodificadores."""
        if fid is None or fid == self.fid_principal:
            return self.video
        v = self.videos.pop(fid, None)
        if v is None:
            with self._lock_proyecto:
                f = self.proyecto.fuentes.get(fid) if self.proyecto is not None else None
                ruta = f['ruta'] if f and f['tipo'] == 'video' else None
            if ruta is None:
                return None
            v = Video(ruta)
        self.videos[fid] = v                                   # (re)entra como el mas reciente
        while len(self.videos) > 3:
            viejo = self.videos.pop(next(iter(self.videos)))
            viejo.cerrar()
        return v

    def cuadro_jpeg(self, n, ancho=540, fid=None):
        """JPEG del cuadro n (bytes) del archivo `fid` (por defecto el principal) o None. Lo usa el servidor para GET /frame."""
        try:
            with self.lock:
                v = self._video_de(fid)
                if v is None:
                    return None
                return v.cuadro(int(n), int(ancho))
        except Exception as e:
            _registrar('cuadro %s fallo: %r' % (n, e))
            return None

    def cuadro(self, n, ancho=540):
        """Version con base64, solo para pruebas internas (la interfaz usa /frame)."""
        jpg = self.cuadro_jpeg(n, ancho)
        if jpg is None:
            return {'error': 'No pude leer el cuadro %s.' % n}
        return {'jpg': 'data:image/jpeg;base64,' + base64.b64encode(jpg).decode('ascii')}


def crear_servidor(api):
    """Arma el servidor local enganchado a la API."""
    servidor = ServidorLocal(os.path.join(AQUI, 'web'), api.metodos(), api.cuadro_jpeg, _registrar)
    api.servidor = servidor
    return servidor


def _tamano_ventana(webview, ancho=1280, alto=860, pantallas=None):
    """El tamaño con que se abre la ventana: el de siempre (1280 x 860), pero nunca mas grande que la pantalla principal (la del origen):
    en un monitor de 1366 x 768 una ventana de 860 de alto se pasa por arriba y por abajo y la interfaz queda cortada.
    Se deja margen para la barra de tareas y el marco. `pantallas` solo lo usan las pruebas."""
    try:
        lista = list(pantallas if pantallas is not None else webview.screens)
        principal = next((p for p in lista if p.x <= 0 < p.x + p.width and p.y <= 0 < p.y + p.height), lista[0] if lista else None)
        if principal is not None and principal.width > 0 and principal.height > 0:
            ancho = min(ancho, max(640, int(principal.width * 0.94)))
            alto = min(alto, max(480, int(principal.height) - 90))
    except Exception as e:
        _registrar('no pude medir la pantalla: ' + repr(e))
    return ancho, alto


def _ventana(api, servidor, depurar):
    import webview
    from webview.dom import DOMEventHandler

    ancho, alto = _tamano_ventana(webview)
    ventana = webview.create_window('Moviola', servidor.url_inicio(),
                                    width=ancho, height=alto, min_size=(min(480, ancho), min(360, alto)))
    api.ventana = ventana

    def al_iniciar(w):
        # Arrastrar un archivo a la ventana: el navegador no entrega la ruta, pero
        # pywebview si (pywebviewFullPath). Sin verificar a mano: si falla, avisa.
        def soltar(evento):
            try:
                archivos = evento['dataTransfer']['files']
                ruta = archivos[0].get('pywebviewFullPath') if archivos else None
            except Exception:
                ruta = None
            if ruta:
                w.evaluate_js('window.abrirDesdePython(' + json.dumps(ruta) + ')')
            else:
                w.evaluate_js("avisar('No pude leer la ruta del archivo soltado. Usá el botón Abrir.', 'ojo')")
        try:
            w.dom.document.events.drop += DOMEventHandler(soltar, True, True)
            w.evaluate_js('window.__soltarEnPython = true')
        except Exception as e:
            _registrar('no pude registrar el arrastre de archivos: ' + repr(e))

    webview.start(al_iniciar, ventana, debug=depurar)


LIMITE_CARGA = 120        # segundos esperando que la pagina cargue por primera vez
LIMITE_SIN_LATIDO = 90    # segundos sin latido = se cerro la pestaña (una pestaña oculta late solo una vez por minuto: el navegador la frena)


def _navegador(api, servidor):
    import webbrowser
    url = servidor.url_inicio()
    if sys.stdout is not None:
        print('Moviola abierta en el navegador. Cerrá la pestaña para terminar.')
    if not webbrowser.open(url):
        _registrar('no pude abrir el navegador; la direccion es ' + url)
    import queue
    global _COLA_PRINCIPAL
    _COLA_PRINCIPAL = cola = queue.Queue()      # los dialogos de archivos (tkinter) se atienden en este hilo, el principal
    inicio = time.time()
    try:
        while True:
            try:
                correr, caja, listo = cola.get(timeout=0.5)
                try:
                    caja['valor'] = correr()
                except Exception as e:
                    caja['error'] = e
                listo.set()
                continue
            except queue.Empty:
                pass
            sin = servidor.segundos_sin_latido()
            if sin is None:
                if time.time() - inicio > LIMITE_CARGA:
                    break            # la pagina nunca cargo
            elif sin > LIMITE_SIN_LATIDO and not api.ocupada():
                break                # se cerro la pestaña (y no hay una exportacion ni nada largo a medias)
    finally:
        _COLA_PRINCIPAL = None


def main():
    try:
        os.remove(AQUI_LOG)          # un error viejo no tiene que parecer de esta vez
    except OSError:
        pass
    api = API()
    servidor = crear_servidor(api)
    argumentos = [a for a in sys.argv[1:] if not a.startswith('--')]
    api.archivo_inicial = os.path.abspath(argumentos[0]) if argumentos else None
    depurar = '--debug' in sys.argv
    usar_navegador = '--navegador' in sys.argv or not _hay_webview2()
    if usar_navegador and '--navegador' not in sys.argv:
        _registrar('WebView2 no encontrado: abro en el navegador')
    try:
        if not usar_navegador:
            try:
                _ventana(api, servidor, depurar)
            except Exception as e:
                _registrar('la ventana nativa fallo, abro en el navegador: ' + repr(e))
                api.ventana = None
                usar_navegador = True
        if usar_navegador:
            _navegador(api, servidor)
    finally:
        api.cerrar()


if __name__ == '__main__':
    main()
