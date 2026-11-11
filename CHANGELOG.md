# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado: [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [1.1.0] - 2026-11-09

### Seguridad
- Los programas externos (FFmpeg, ffprobe, yt-dlp, whisper) ya **no se buscan en la carpeta actual**: abrir un proyecto desde una carpeta
  que traía un `ffmpeg.exe` plantado podía ejecutarlo.
- Un proyecto `.moviola` dañado o armado a propósito (con `NaN`, `Infinity`, textos donde va un número, volúmenes absurdos) ya no pasa la
  validación; el archivo se lee rechazando `NaN` e `Infinity`.
- FFmpeg solo puede abrir archivos (`-protocol_whitelist file`): un «video» que en realidad es una lista de reproducción no puede hacerle
  pedir direcciones de internet.
- yt-dlp corre con `--ignore-config` (la configuración del usuario no cambia lo que hace Moviola).
- Instalador: los instaladores de WebView2 y de Visual C++ solo se ejecutan si traen una firma válida de Microsoft; al desinstalar no se
  borra una carpeta de whisper que ya existía con otras cosas.

### Corregido
- Cerrar la ventana durante una exportación, un preset, una transcripción o una descarga dejaba el programa externo trabajando solo y un
  archivo `.parcial`: ahora se cancela y se limpia antes de salir.
- En modo navegador, Moviola se apagaba sola si la pestaña quedaba oculta más de 30 segundos (el navegador frena los temporizadores) aunque
  estuviera exportando: ahora tolera 90 segundos y nunca se apaga con un trabajo en curso.
- Las transcripciones de más de una hora no se podían aplicar (el pedido pasaba de 1 MB): el tope es 16 MB.
- La detección de GPU del primer arranque pisaba los archivos recientes y el modo elegido que se hubieran guardado mientras tanto.
- Si al abrir un proyecto fallaba la lectura de uno de sus videos, el visor quedaba con el video nuevo y el proyecto viejo.
- Un archivo del proyecto reemplazado por otro mucho más corto se avisa en vez de abrir clips que se salen del archivo.
- Los diálogos de archivos del modo navegador (tkinter) corren en el hilo principal y de a uno.
- Al cancelar una descarga no quedan pedazos (`.part`) en la carpeta.

### Cambiado
- Instalada con el instalador, Moviola guarda ajustes, registro y caché en `%LOCALAPPDATA%\Moviola` (no dentro de la carpeta del programa).
- Los lanzadores se llaman `Moviola.bat`, `Moviola-consola.bat` y `Moviola-navegador.bat` (antes `Editor*.bat`).

### Agregado
- Instalador (`python construir_instalador.py`): `Instalar-Moviola.bat` instala Moviola sin administrador y, por consola, whisper.cpp, un modelo de
  whisper a elegir, yt-dlp y WebView2 (si falta), con accesos directos, «Aplicaciones instaladas» y doble clic en `.moviola`; verifica cada descarga con
  SHA-256, no baja lo que ya hay, actualiza sin perder ajustes y se desinstala limpio.
- Visor cuadro por cuadro exacto, también con framerate variable, con espectro de audio alineado.
- Abre casi cualquier formato de video y audio; reproducción con una copia liviana (proxy) cuando el navegador no puede.
- Aceleración por GPU con detección real, modos CPU / GPU / Automático y respaldo al procesador.
- Edición: cortar, marcar tramo, borrar cerrando el hueco, recortar, deshacer/rehacer, fundidos de entrada y salida,
  volumen, silenciar, separar audio, audios extra.
- Exportar: original, 9:16, 16:9, 1:1 o solo audio (WAV, MP3, FLAC, M4A), normalización a −14 LUFS, progreso y cancelar.
- Versión portátil (`python construir_portatil.py`): trae su propio Python y FFmpeg; no instala nada ni usa internet.
- Efectos por clip (brillo/contraste/saturación, voltear, quitar graves), apilables, reordenables, con deshacer, vista previa y exportación exacta.
- Audio: 12 efectos (ruido, compresor, puerta, limitador, eco, tono, al revés, ecualización...), cortar silencios en un paso y medir el volumen del proyecto.
- Imagen: 10 efectos nuevos (color, curvas, LUT, ruido, enfoque, estabilizar en dos pasadas, rotar, recortar bordes, lente, enderezar) y 10 transiciones entre clips que no cambian la duración.
- Tiempo: velocidad de ¼× a 4× (audio con o sin conservar el tono, cámara lenta suave), al revés, repetir clips y ducking de la música.
- Composición: logo o marca de agua, quitar fondo verde/azul (con color o imagen detrás), texto o títulos con 8 letras y zoom lento.
- Arreglo: un clip con velocidad seguido de otro con transición salía más corto de lo debido.
- Subtítulos: transcribir con el whisper instalado, editar las frases, estilo, vista sobre el visor, quemarlos y/o guardar .srt/.vtt. Escenas: cambios de escena, negros y congelados.
- Salida: MP4 H.265 y AV1, WebM VP9, MOV ProRes, MKV y GIF animado; calidad alta/equilibrada/liviana; audio Opus y OGG.
- Proyectos y medios: guardar/abrir proyectos `.moviola`, pantalla de inicio con recientes, recuperación del trabajo sin guardar, panel de Medios con varios videos (distinto tamaño y velocidad), Mover antes/después.
- Bajar un video de YouTube (con el yt-dlp instalado, con confirmación de derecho de uso y sin esquivar protecciones). Logo nuevo (la moviola).
- Interfaz nueva: riel de herramientas, panel de Propiedades, línea de tiempo sobre lienzo.
- Presets y lotes («Reel en un clic»): cortar silencios, subtitular, nivelar el volumen y exportar de una vez, sobre el proyecto abierto o sobre muchos archivos; 5 recetas (reel, youtube, podcast, whatsapp, clase). Línea de comandos `moviola.py` (`procesar`, `exportar`, `silencios`, `transcribir`, `medir`, `presets`, `herramientas`, con `--json`) y `Moviola-comandos.bat` en la versión portátil.
- Arreglo: un error de «Cortar silencios» se mostraba en el diálogo de Exportar (dos funciones globales con el mismo nombre).
- Editar por texto: transcribir con el tiempo de cada palabra, borrar palabras (corta video y audio juntos), marcar muletillas, acortar pausas largas y corregir palabras desde un panel lateral. Subtítulos karaoke (la palabra que se dice va resaltada, en el visor y al exportar) y también en el preset «reel».
- Línea de tiempo con el mouse: zoom y regla de tiempo (Ctrl + rueda, + / − / 0), arrastrar clips para reordenarlos, tirar de los bordes para recortar o estirar (con ripple), mover la música, imán a cursor, marcas y cortes. El logo de la moviola en la barra superior.
- «Crear un proyecto»: elegir varios videos y armar un proyecto con todos uno detrás de otro, y guardarlo.
- Arreglo: «Editar un video» no abría el selector de archivos (un nombre de filtro con comas que pywebview rechaza).
- Interfaz adaptable: se acomoda a pantallas de 390 a 2560 px de ancho (celular y tablet en vertical, apaisado, 1360x768, ultra ancho); la ventana se abre del tamaño de la pantalla. Pantalla de inicio en tres columnas y con texto nuevo.
- Bajar de YouTube: elegir entre video (MP4, con calidad) o solo el audio en MP3.
- «Acerca de Moviola» (botón «i», enlace en el inicio o F1): versión, autores, licencia y qué herramientas hay instaladas.
- Licencia GPL-3.0-or-later.
