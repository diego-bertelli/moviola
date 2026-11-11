# Contrato entre módulos — Editor de video

> **Documento histórico.** Es el contrato de la primera etapa (cuando varios agentes escribían módulos en paralelo) y describe la PC donde se
> midió. Lo de «todo por CPU» vale para ESA placa: hoy el programa detecta la GPU de cada equipo y ofrece los modos CPU / GPU / Automático
> (ver README.md y DECISIONES.md).

Hardware medido (Ryzen 5 5600GT 6c/12t, 32 GB, RX 6500 XT, NVMe).
**La GPU NO sirve: no tiene encoder (h264_amf falla con -22) y su decode es más lento que el software. TODO POR CPU.**

Números verificados en esta máquina con un clip 1080x1920 h264 de 60 s:

| Operación | Medido |
|---|---|
| decode secuencial con PyAV (decoder abierto) | 0,84 ms/cuadro |
| `frame.reformat(540,960,'rgb24')` + JPEG por PIL | 3,5 ms (32 KB) |
| `frame.reformat(270,480,'rgb24')` + JPEG q70 | 1,1 ms (11 KB) |
| `v.seek()` a punto arbitrario + cuadro exacto | 103 ms mediana / 184 ms peor |
| waveform (ffmpeg a PCM 8 kHz mono) | 108 ms |
| tira de 120 miniaturas | 1,4 s |
| export 1 min 1080x1920 libx264 veryfast | 7,8 s |
| arrancar un proceso ffmpeg | 70 ms |

**Regla de oro: NUNCA lanzar un proceso ffmpeg por cuadro (70 ms de puro arranque).
Para cuadros se usa PyAV con el decoder abierto. ffmpeg CLI solo para waveform, miniaturas y export.**

**Regla de oro 2: NUNCA usar `frame.to_image()` sin reformatear antes.** Convierte a RGB a
resolución completa en Python y cuesta 22 ms en vez de 3,5 ms. Siempre
`frame.reformat(width=W, height=H, format='rgb24')` primero: eso corre en C (swscale).

## Reparto de archivos

| Archivo | Responsable | Nadie más lo toca |
|---|---|---|
| `motor/video.py` | agente 1 | sí |
| `motor/audio.py`, `motor/tiras.py` | agente 2 | sí |
| `web/index.html`, `web/estilo.css`, `web/app.js` | agente 3 | sí |
| `app.py` | Claude (pegamento) | sí |

## motor/video.py — contrato exacto

```python
class Video:
    def __init__(self, ruta: str): ...
    def info(self) -> dict:
        # {"ancho":int, "alto":int, "fps":float, "duracion":float,
        #  "total_cuadros":int, "codec":str, "hdr":bool, "web_compatible":bool}
        # web_compatible: True si el codec lo puede reproducir WebView2 (h264/aac en mp4).
    def cuadro(self, n: int, ancho: int = 540) -> bytes:
        # JPEG del cuadro n (0-indexado). Alto proporcional, PAR (swscale lo exige).
        # Si n está fuera de rango, lo recorta al rango válido. Nunca tira excepción por eso.
    def cerrar(self) -> None: ...
```

Requisitos de `cuadro()`:
1. **Seek inteligente.** Guardá el índice del último cuadro entregado. Si el pedido está
   adelante y a 60 cuadros o menos, decodificá secuencial (0,84 ms/cuadro) en vez de
   hacer seek (103 ms). Si está atrás o más lejos, seek al keyframe y avanzá hasta el exacto.
2. **Caché LRU** de 120 cuadros, con clave `(n, ancho)`.
3. `thread_type = "AUTO"` en el stream de video (usa los 12 hilos).
4. Un `threading.Lock` alrededor del decoder: el bridge de pywebview llama desde varios hilos
   y un decoder de libav NO es thread-safe.
5. Nunca uses `to_image()` sin `reformat()` antes (ver Regla de oro 2).

## motor/audio.py — contrato exacto

```python
def picos(ruta: str, n: int = 2000) -> dict:
    # {"picos": [[min,max], ...]} con n pares, cada valor float en -1.0..1.0
    # Si el archivo no tiene pista de audio: {"picos": [], "sin_audio": True}
```
Implementación: un solo `ffmpeg -i ruta -ac 1 -ar 8000 -f s16le -` leyendo el PCM de stdout,
y agrupás en n tramos calculando min y max de cada uno. Un solo proceso, nunca n procesos.

## motor/tiras.py — contrato exacto

```python
def tira(ruta: str, destino: str, duracion: float, cantidad: int = 120, alto: int = 90) -> dict:
    # Genera UNA imagen con las miniaturas en fila horizontal (filtro `tile`).
    # {"archivo": destino, "cantidad": int, "ancho_mini": int, "alto_mini": int}
```
Usá `-vf "fps=<cantidad/duracion>,scale=-2:<alto>,tile=<cantidad>x1"`. Un solo proceso ffmpeg.
Devolvé el ancho real de cada miniatura: el JS necesita ese número para posicionar el recorte.

## app.py — API que el frontend ve como `window.pywebview.api`

Todos los métodos devuelven dicts JSON-serializables. Los que pueden fallar devuelven
`{"error": "mensaje para mostrarle a la persona"}`.

```
abrir(ruta: str)            -> info() + {"picos":[...], "tira":"file:///...", ...}
cuadro(n: int, ancho: int)  -> {"jpg": "data:image/jpeg;base64,..."}
elegir_archivo()            -> {"ruta": str} | {"cancelado": True}
```
