# Propuestas para mejorar Moviola

Escrito por Claude el 2026-11-09, después de terminar las fases 0 a 8, la auditoría y el cierre. **Actualización (2026-11-09): Diego pidió «aplicá tus 3 propuestas» y las tres de arriba (1, 2 y 3) ya están HECHAS** (línea de tiempo con el mouse, edición por texto con karaoke, y presets/lotes con línea de comandos; ver CHANGELOG.md y DECISIONES.md). El resto sigue sin implementar: es para que Diego elija.
Esfuerzo: **S** = una sesión corta, **M** = una fase de trabajo (como las de este plan), **L** = varias fases o algo que cambia la arquitectura.

## Las 5 que más valdrían la pena (en este orden)

1. **Línea de tiempo con el mouse: arrastrar para reordenar, recortar tirando de los bordes, zoom y imán (L).**
   Hoy se corta con «S», se borra con «Supr» y se reordena con «Mover antes/después». Es lo primero que se extraña al usar cualquier editor, y el modelo ya lo soporta (`mover_grupo`, `dividir`, `recortar_a`): falta la capa de interfaz
   (arrastre con pointer events, bordes con `ajustar` a cuadro, zoom horizontal de `#tira` y del espectro). Riesgo: el tamaño de `web/edicion.js`; conviene partirlo en `linea-tiempo.js` antes.
2. **[HECHA] Editar por texto + subtítulos «karaoke» (L).** Ya se transcribe con whisper por frase; con tiempos **por palabra** (`-ml 1` rompía las tildes, hay que usar la salida `-ojf` con `tokens` o `--dtw`) se puede: borrar palabras del texto y que se corte el video,
   quitar muletillas con un clic, y subtítulos que resaltan la palabra que se dice (el estilo de los reels que ya hace el skill `editar-mis-reels`). Es la función que más diferencia a Moviola de un editor común. Depende de la calidad de los tiempos por palabra.
3. **[HECHA] Lotes y presets de exportación: «Reel en un clic» y línea de comandos (M).** Un preset = vertical + normalizar a −14 LUFS + subtítulos quemados + cortar silencios; y un `moviola exportar proyecto.moviola --preset reel` sin ventana, para procesar carpetas enteras.
   Casi todo existe (silencios, normalizado, subtítulos, exportar, `.moviola`): es pegarlo. Muy buena relación esfuerzo/valor para el trabajo y para los reels. Riesgo bajo.
4. **Vista previa real de la composición y animación con keyframes (L).** Logo, texto, zoom lento y quitar fondo hoy «se ven al exportar». Con un canvas en el visor (o una vista previa renderizada por ffmpeg de pocos segundos) se vería al editar, y con
   **keyframes** (posición, tamaño, opacidad en el tiempo) el logo entra y sale, el texto se anima, el zoom se programa. Es lo que separa un editor «de cortes» de uno «de motion básico».
5. **Robustez de proyectos: reencontrar archivos faltantes, caché persistente, versiones y diagnóstico (M).** Un diálogo «no encuentro `video.mp4`: ubicalo» en vez de rechazar el proyecto; guardar miniaturas, espectro y tablas de cuadros junto a los ajustes para
   abrir un proyecto de 40 clips al instante; historial de versiones del proyecto (`proyecto.moviola.v1…`); y «Copiar informe de diagnóstico» (versiones, GPU, errores del registro) para soporte.

## Backend

| # | Propuesta | Por qué sirve | Esf. | Depende de / riesgo |
|---|---|---|---|---|
| B1 | **Cola de exportaciones y varias salidas a la vez** (vertical + horizontal + audio de un tirón) | Hoy es una por vez; para redes se suele necesitar 2 o 3 formatos | M | usa una sola lectura del proyecto; cuida la memoria con `reverse` |
| B2 | **Caché persistente por archivo** (miniaturas, picos, tabla de cuadros, huella) en `cache\` | Abrir un proyecto grande hoy recalcula todo | M | invalidar por tamaño+fecha del archivo |
| B3 | **Autoguardado ampliado con versiones** (ya hay una copia de recuperación) | Volver a «cómo estaba hace una hora» | S/M | espacio en disco; política de limpieza |
| B4 | **Verificar y ajustar H.265/AV1 por GPU en otras PC** y elegir el codificador por prueba real | Hoy el camino H.265 por GPU está escrito y sin verificar en hardware | S | necesita una PC con NVIDIA/Intel/AMD que lo soporte |
| B5 | **Decodificación por GPU también al exportar** | Exportar 4K más rápido | M | ffmpeg `-hwaccel` y filtros: hay que mantener los efectos en CPU |
| B6 | **API de línea de comandos** (`moviola exportar|medir|silencios|transcribir`) | Automatizar lotes; probar sin ventana | M | separar `app.py` de la interfaz (ya casi está) |
| B7 | **Importar y exportar EDL/XML** (CMX3600 / FCPXML) | Pasar el corte a DaVinci o Premiere | M | mapear velocidad, transiciones y efectos (solo cortes al principio) |
| B8 | **Mejor manejo de VFR y de audio desfasado** (`aresample=async`, tolerancia por archivo) | Videos de pantalla y celulares | S | pruebas con archivos reales (ya hay uno de el Escritorio del autor) |
| B9 | **Registro estructurado y rotación** (JSON por línea, con el id del pedido) | Diagnosticar fallas de otros usuarios | S | privacidad: no guardar rutas completas si se comparte |
| B10 | **Actualizador de herramientas** (avisar si `yt-dlp` o `whisper` están viejos) | YouTube cambia seguido; yt-dlp se rompe sin avisar | S | solo avisa, nunca baja solo |

## Frontend

| # | Propuesta | Por qué sirve | Esf. | Depende de / riesgo |
|---|---|---|---|---|
| F1 | **Pista de subtítulos en la línea de tiempo** (bloques arrastrables, dividir y unir frases con un clic) | Hoy se editan en una lista dentro de un diálogo | M | requiere la propuesta 1 (zoom y arrastre) |
| F2 | **Paleta de comandos (Ctrl+K) y atajos configurables** | Con ~60 funciones el riel ya es largo | M | guardar el mapa de atajos en `ajustes.json` |
| F3 | **Copiar y pegar efectos entre clips**, favoritos y «aplicar a todos» | Mismo ajuste de color en 12 clips | S/M | multi-selección de clips |
| F4 | **Vista previa de transiciones** al elegirlas (miniatura animada) | Hoy se elige por nombre | S | CSS/canvas, sin motor |
| F5 | **Tema claro y accesibilidad** (alto contraste, foco visible en todo, lector de pantalla, todo por teclado) | Uso en pantallas con sol / personas con otras necesidades | M | la paleta violeta/coral aprobada se mantiene como tema por defecto |
| F6 | **Recorrido de bienvenida con un video de ejemplo** y mensajes de error con «qué hacer» | Quien no sabe qué es una «moviola» | S | un video chico incluido en el paquete |
| F7 | **Zoom del espectro y de las miniaturas** + marcadores con nombre y color | Edición fina y por capítulos | S/M | marcadores se guardan en el proyecto |
| F8 | **Arrastrar archivos al panel Medios desde el Explorador** de forma confiable | Hoy depende de que WebView2 entregue la ruta | S | probar en Windows 10/11 |
| F9 | **Pantalla de «qué hay de nuevo»** y de licencias dentro de la app | Cumplir la GPL a la vista y ayudar a descubrir funciones | S | texto ya existe |

## Funciones nuevas

| # | Propuesta | Por qué sirve | Esf. | Depende de / riesgo |
|---|---|---|---|---|
| N1 | **Reencuadre inteligente 9:16** (seguir al sujeto al pasar de horizontal a vertical) | Hoy el foco es fijo (X, Y) | L | detección de rostro/sujeto: sin librerías nuevas es limitado; evaluar `cropdetect`/seguimiento por movimiento |
| N2 | **Mejora de voz con red neuronal** (`arnndn` de ffmpeg) y «voz de radio» en un clic | Audios de celular | S | necesita un modelo `.rnnn` (no se descarga solo) |
| N3 | **Títulos y gráficos de plantilla** (tercio inferior, créditos, cuenta regresiva) con tu logo | Se repiten en todos los videos | M | keyframes (propuesta 4) |
| N4 | **Biblioteca local de música y efectos** (carpeta que elegís, con vista previa y ducking automático) | Hoy se agrega audio de a uno | S/M | derechos: solo archivos tuyos |
| N5 | **Grabar pantalla, cámara y voz desde la app** | Tutoriales y clases (Diego es formador) | M | captura por ffmpeg `gdigrab`/`dshow`; permisos del micrófono |
| N6 | **Traducir subtítulos y doblar** (whisper `--translate` a inglés; traducción local opcional) | Llegar a otros públicos | M | el modelo de traducción sería otra herramienta instalada por la persona |
| N7 | **Efectos de audio más finos:** ecualizador gráfico, de-esser, reverb, compresor del master | El audio es el 50 % de un reel | S | filtros de ffmpeg ya presentes |
| N8 | **Máscaras y quitar fondo sin pantalla verde** (recorte por forma, o por movimiento) | Logos con forma, personas sobre fondos | L | segmentación de personas requiere un modelo |
| N9 | **Instalador, doble clic en `.moviola` y actualizaciones** | Que no haya que descomprimir una carpeta de 550 MB | M | asociar la extensión toca el registro de Windows (con permiso) |
| N10 | **Versión para macOS y Linux** | `pywebview`, `PyAV` y ffmpeg existen allá | M/L | rutas de whisper/yt-dlp, WebView distinto; sin GPU de Windows |

## Deuda técnica chica (conviene antes de seguir creciendo)

- `web/edicion.js` y `web/app.js` pasan las 1 200 líneas: partirlos por tema (línea de tiempo, reproducción, inspector, vista previa).
- `motor/efectos.py` mezcla el catálogo, la traducción a ffmpeg y los subgrafos: separar «catálogo» de «traductor».
- Las pruebas de ventana real tardan (≈15 min de los 20 de la corrida completa): paralelizarlas en carpetas de ajustes distintas.
- `efectos.necesita_preparacion` no la usa nadie (se puede borrar).
- Las funciones que dependen de herramientas externas (whisper, yt-dlp, GPU) merecen una pantalla de **«Estado de la instalación»** que diga qué está disponible y qué falta, con una línea de cómo conseguirlo.

## Mi recomendación

Si solo se hacen dos cosas: **(1)** la línea de tiempo con el mouse, porque es lo que más se nota a diario, y **(3)** lotes y presets, porque es poco trabajo y ya paga el esfuerzo de las últimas fases.
La **edición por texto (2)** es la apuesta grande: el equipo de whisper + silencios + subtítulos ya está armado y sería el rasgo propio de Moviola.

## Anotado para más adelante (pedido de Diego, 2026-11-09: «versión APK para Android, si es viable»; NO se empezó)

**¿Es viable? Sí, pero no es «empaquetar lo que hay»: es un proyecto grande (L+), y conviene decidirlo con calma.**
- **Lo que se reutiliza casi tal cual:** toda la interfaz (`web/`: HTML/CSS/JS sin frameworks, ya con eventos de puntero, así que sirve con el dedo) y el modelo de proyecto (`motor/proyecto.py` es Python puro). La interfaz ya habla con el motor por HTTP local (`/api/...`): un motor distinto que conteste lo mismo bastaría.
- **Lo que NO anda en Android:** `app.py` con pywebview/WebView2, PyAV y el `ffmpeg.exe` de Windows, whisper.cpp tal como está instalado, yt-dlp, la detección de GPU, las rutas de Windows y los diálogos de archivos.
- **Caminos posibles (de menos a más trabajo):**
  1. **Cliente del programa de la PC**: el celular abre la interfaz en el navegador contra Moviola corriendo en la PC de la misma red (casi sin código nuevo: hay que permitir otra dirección además de 127.0.0.1, con token y emparejado). No es una APK offline, pero sirve para editar desde el sofá. Riesgo: seguridad de red local.
  2. **APK con WebView + motor Python embebido (Chaquopy o BeeWare)**: reusa el motor, pero PyAV/FFmpeg para Android hay que compilarlos y mantenerlos (sin ruedas oficiales), y el rendimiento sin GPU sería flojo.
  3. **APK nativa (Kotlin) con la interfaz `web/` en un WebView y un motor nuevo** (Media3 Transformer / MediaCodec o una build propia de FFmpeg, y whisper.cpp compilado para ARM): lo más sólido y rápido, y también lo más caro (se reescribe el exportador y los efectos).
- **Preguntas para decidir:** ¿offline obligatorio? ¿para editar de verdad o solo cortes y subtítulos rápidos? ¿quién la va a usar (trabajo, grupos)? ¿Play Store o instalación directa (APK suelta)? Android 10+ pide acceso por SAF a los archivos.
- **Recomendación:** empezar por el camino 1 como prueba barata (una tarde), y solo si hace falta algo offline pensar en el 3. No empezar antes de usar un tiempo lo nuevo (presets, edición por texto, línea de tiempo con mouse) y ver qué se necesita en el celular.
