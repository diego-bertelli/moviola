# Decisiones tomadas en modo autónomo + reglas

Diego no está disponible. Estas son las reglas con las que Claude trabaja solo, y la bitácora
de cada decisión para que Diego pueda revisarla y revertirla.

## Reglas duras (no negociables aunque nadie las vea)

- Solo se escribe dentro de la carpeta del proyecto, su carpeta de respaldos
  la de respaldos y el scratchpad de la sesión.
- Los videos del Escritorio son de SOLO LECTURA. No se copian, mueven, renombran ni modifican.
- NO descargar archivos ni acceder a internet. NO instalar paquetes nuevos de pip salvo que una
  etapa sea imposible sin eso; si pasa, anotarlo acá con el motivo.
- NO tocar la BIOS, configuración del sistema, seguridad, otros proyectos de la carpeta de arriba
  (otros proyectos), ni borrar nada que no haya creado Claude.
- NO enviar mensajes, publicar, ni subir nada. La app es 100% local y offline.
- Sin git: los puntos de retorno son copias en `editor-video-respaldos\`.
- Notificar al celular (PushNotification) SOLO si: quedó bloqueado sin salida, ocurre algo
  inesperado que pueda afectar archivos del usuario, o terminó todo. Nada de avisos de rutina.

## Criterios por defecto para decidir

1. Lo que el usuario ya dijo manda: todo local, interfaz actual (le gusta), formatos máximos,
   switch CPU/GPU con aviso real, audio solo + audio de video, fundidos básicos, compartible.
2. Ante dos opciones: la más simple que funcione y se pueda verificar.
3. Una etapa no se da por terminada sin pruebas que la ejerciten de verdad (ventana real cuando
   toque la interfaz). Si una prueba falla, se arregla; no se tacha igual.
4. Si algo es imposible o demasiado riesgoso, se documenta en la bitácora y se sigue con lo
   siguiente. Nunca se deja el proyecto en un estado que no arranque.
5. Pocas defensas, buenos mensajes de error en castellano rioplatense, sin telemetría.
6. Cosas que no se pueden verificar acá (otra GPU, PC limpia, antivirus) se marcan como
   "no verificado" en el README, sin afirmar que funcionan.

## Bitácora de decisiones
(una entrada por decisión: fecha · decisión · por qué · cómo revertir)

- 2026-11-08 · **Aviso al celular no disponible.** PushNotification devolvió "Remote Control
  inactive". No se activa Remote Control desde acá: da acceso remoto a la sesión y es decisión
  de Diego. Las alertas quedan escritas en `ESTADO.md > ALERTAS` y como notificación de escritorio.
  Para activarlo: abrir la sesión en la app y encender Remote Control. · Revertir: nada que revertir.
- 2026-11-08 · **Orden de etapas.** Primero formatos/índice de cuadros (base de todo), después la
  API HTTP (antes de sumar más métodos al puente viejo, para no migrarlos dos veces), luego
  proxy, GPU, modelo de proyecto y exportar. Empaquetado al final. · Revertir: reordenar ESTADO.md.
- 2026-11-08 · **Descargas diferidas.** El paquete portable con Python embebido necesita bajar
  un zip de python.org. No se descarga sin permiso: E7 deja el script listo y documenta el paso.
- 2026-11-08 · **Reanudador programado** `editor-video-reanudar` (cada 30 min, solo actúa si el
  latido tiene más de 45 min y el estado no es TERMINADO). Pedido explícito de Diego.
  · Revertir: eliminar la tarea desde la sección "Programadas" de la app.
- 2026-11-08 · **El "cuadro n" pasa a ser el n-esimo cuadro real**, no el que cae en n/fps. Medido en
  el video VFR de Diego: la grilla n/fps se corre hasta 49 s del tiempo real. Cursor y saltos de 1 s
  van por tiempo. · Revertir: no conviene; es la base de cortar y exportar.
- 2026-11-08 · **Rotacion**: frame.rotation de PyAV viene en grados ANTIHORARIOS; se verifico contra el
  autogiro de ffmpeg (la primera version giraba al reves y la prueba lo atrapo).
- 2026-11-08 · **Entrelazado**: no se desentrelaza en la vista previa (a 540 px el escalado ya promedia
  las lineas); si en proxy y exportar. · Revertir: agregar yadif en Video._a_jpeg.
- 2026-11-08 · **Solo audio**: un "cuadro" son 10 ms; sin visor, tira ni contador de cuadros. Es una base
  minima para F1; la edicion de audio real viene en E5.
- 2026-11-08 · **Bug corregido**: abrir() cerraba el video viejo antes de abrir el nuevo; si el nuevo
  fallaba, pantalla y motor quedaban desincronizados. Ahora se abre primero el nuevo.
- 2026-11-08 · **HTTP local en lugar del puente de pywebview.** Permite el modo navegador de respaldo
  (si falta WebView2 en la PC del trabajo), cuadros como imagen directa y una sola superficie para probar.
  Costo: hay un servidor escuchando en loopback, mitigado con token/Host/Origin/CSP y probado atacandolo.
  · Revertir: respaldo en editor-video-respaldos/E2-previo (usa el puente viejo).
- 2026-11-08 · **Si no hay WebView2, la app abre sola en el navegador** en vez de fallar o caer al motor
  viejo de Internet Explorer que usa pywebview por defecto (no corre JS moderno).
- 2026-11-08 · **Remote Control activado** a pedido de Diego ("claude rc") para seguir la sesion desde el celular.
- 2026-11-08 · **Proxy limitado por el lado CORTO a 720** (no por el alto): un video vertical 1080x1920 queda
  720x1280, no 406x720. Nunca agranda. · Revertir: _filtro_video en motor/proxy.py.
- 2026-11-08 · **Cache de proxies dentro del proyecto** (editor-video/cache/, tope 5 GB), no en %LOCALAPPDATA%,
  para que la app sea portable y para no escribir fuera de la carpeta. Las pruebas usan un cache temporal.
- 2026-11-08 · **Tolerancia de tabla del proxy**: < 40 ms y pocos cuadros fuera de 2 ms. El VFR real trae un cuadro
  con el tiempo 13 ms hacia atras desde el propio decoder; forzarlo a crecer es inevitable.
- 2026-11-08 · **Por defecto el modo es CPU**, no Automatico: es lo que se midio mas rapido en la PC de desarrollo
  y no depende de hardware que no se pudo probar. · Revertir: valor por defecto en API.__init__ (modo_acel).
- 2026-11-08 · **"Automatico" codifica el proxy con GPU si hay, pero decodifica con GPU solo si se midio mas rapido.**
  Para un proxy la calidad no importa y los codificadores de hardware ganan en velocidad.
- 2026-11-08 · **El aviso de GPU al abrir NO se repite en cada arranque**: solo la primera vez por equipo (huella) o
  si hay GPU util y se esta usando el procesador (hay algo que decidir). Pedido de Diego: "avisar si esta disponible".
- 2026-11-08 · **Cambiar de modo no reabre el archivo actual**; se aplica al proximo. Evita cortar lo que se esta mirando.
- 2026-11-08 · **Etapas reordenadas: modelo y exportador primero (backend), interfaz despues.** Cortar y exportar son lo que mas
  riesgo tiene (si cortan mal, nada mas sirve) y se verifican a fondo sin interfaz. E5 modelo, E6 exportador, E7 interfaz de edicion,
  E8 exportar desde la interfaz, E9 paquete. · Revertir: no aplica (solo es un orden).
- 2026-11-08 · **Alcance de edicion de la primera entrega:** un archivo de video de origen (con todas sus pistas de audio) + audios
  extra, con cortes, borrado con cierre, fundidos, volumen y silenciar. El MODELO ya admite varias fuentes (montaje), pero la
  reproduccion en pantalla de varias fuentes de VIDEO queda para despues; el exportador si las soporta. Decision de alcance: Diego
  pidio "funciones basicas que funcionen bien".
- 2026-11-08 · **Borrar = borrar rango con cierre (ripple) sobre TODAS las pistas**, como los editores comunes: no deja huecos y
  mantiene la sincronia entre video y audio. No hay "borrar dejando hueco" todavia.
- 2026-11-08 · **Los cortes siempre caen en un limite de cuadro real de la fuente** (el inicio de un cuadro o el final del
  video), tambien en VFR: se ajusta al mas cercano. Asi nunca queda un cuadro partido ni un corte "entre cuadros".
- 2026-11-08 · **Un fundido de entrada queda en la mitad izquierda de un corte y el de salida en la derecha**: cortar no
  crea fundidos en el corte, y cada mitad acota los suyos a su largo.
- 2026-11-08 · **El historial guarda copias del estado (200 como maximo), no operaciones inversas**: mas simple y a prueba
  de errores; el costo (copias chicas de pistas) es despreciable. La tabla de tiempos de cada fuente NO se copia.
- 2026-11-08 · **Exportar con modo Auto usa el procesador** (x264, CRF 18): para el archivo final la calidad importa mas que
  la velocidad. Solo el modo GPU explicito usa el codificador de hardware (con respaldo al procesador). El proxy si usa GPU en Auto.
- 2026-11-08 · **Un VFR se exporta a 24/25/30 fps constantes** (el mas cercano a su promedio): los formatos de entrega
  (redes, reproductores, editores) esperan framerate fijo. Se puede forzar con el parametro fps.
- 2026-11-08 · **Encuadre por defecto: recortar** (llena el cuadro) para vertical/horizontal/cuadrado, que es lo que se quiere
  para reels; 'barras' deja el video entero con bandas negras. El punto de foco del recorte se puede mover (0..1).
- 2026-11-08 · **El motivo de un respaldo de GPU es una frase fija**, no el volcado de ffmpeg: el usuario no puede hacer nada con
  "[out#0/mp4 @ 000002...] Nothing was written". El detalle tecnico queda para el registro.
- 2026-11-08 · **En la interfaz, el "cuadro" es el de la LINEA DE TIEMPO editada** (el contador, las flechas, el cursor), no el de
  la fuente; para pedir una imagen se traduce con fuenteDe(k). Asi la edicion se siente natural (el cuadro 30 es el que esta en el
  segundo 1 de lo que se ve) y sin ediciones todo es identico a antes.
- 2026-11-08 · **Sin zoom ni arrastre en esta entrega.** Se prioriza que cortar, borrar, fundidos y exportar sean exactos y estén
  probados; zoom y arrastrar son comodidad y se pueden sumar sobre la misma base. Se edita con el cursor, las flechas y marcas.
- 2026-11-08 · **El inspector aplica un cambio por vez que se suelta el control** (evento change), no uno por cada pixel que se
  arrastra: si no, un fundido llenaria el historial de deshacer de decenas de pasos.
- 2026-11-08 · **Borrar un audio extra NO cierra el hueco** (solo borrar un tramo de video/audio del video lo cierra): una musica
  de fondo que se saca no tiene por que mover nada mas.
- 2026-11-08 · **El dialogo de exportar es modal y bloquea los atajos.** Mientras esta abierto, Espacio/S/Supr/flechas no llegan al
  visor (captura en window + stopImmediatePropagation): apretar Espacio sobre un boton del dialogo no tiene que reproducir el video.
- 2026-11-08 · **Exportar trabaja sobre una copia de las pistas** tomada al apretar el boton, sin el historial de deshacer (hasta 200
  copias para nada). Editar durante la exportacion no cambia el archivo. Un trabajo a la vez.
- 2026-11-08 · **Exportar con el modo Automatico usa el procesador** (calidad del archivo final); solo "GPU" elegido a mano usa el
  codificador de hardware, con respaldo a CPU y aviso si falla.
- 2026-11-08 · **mostrar_en_carpeta no acepta rutas de la interfaz**: abre solo el ultimo archivo que la app exporto (no se puede usar
  la API para abrir cualquier cosa en el explorador).
- 2026-11-08 · **Esc no cierra el dialogo durante la exportacion**; se cancela con el boton (cancel + preventDefault).
- 2026-11-08 · **Version portatil = copia del Python de desarrollo + las bibliotecas que la app usa + ffmpeg.exe del PATH** (script
  construir_portatil.py). No se descarga el Python "embebido" de python.org porque descargar esta prohibido en este trabajo; copiar un
  Python ya instalado anda igual (se verifico aislado, con PYTHONPATH envenenado y sin Python ni ffmpeg en el PATH). Las dependencias
  se calculan con importlib.metadata (evaluando marcadores), no a mano. El script solo borra una carpeta que el mismo armo (marca).
- 2026-11-08 · **Los datos de la app (ajustes, registro, cache) van junto al programa si se puede escribir ahi; si no, en
  %LOCALAPPDATA%\Moviola.** La version portatil puede quedar en una carpeta de solo lectura o en red. En desarrollo no cambia nada.
- 2026-11-08 · **C11 (contador "000 / 359")**: se deja. Los cuadros se cuentan desde 0 (como el timecode de los editores) y el total
  muestra el ULTIMO indice, asi al final el contador dice 359 / 359. Cambiar solo el total a "360" dejaria el final en "359 / 360".
  **C12** ("1 s" con 29,97 fps): se deja; el salto de un segundo cae en el cuadro mas cercano, que es lo esperable.
- 2026-11-08 · **El nombre "Moviola" queda.** Diego busco y no encontro nada a mano. Verificacion de Claude (busqueda web, sin acceso a las
  bases oficiales): no hay otro software con ese nombre salvo una app de edicion para Meta Quest (SideQuest, 2024); es el nombre historico
  de la mesa de montaje de cine (Moviola Company, 1924); aparece una marca de EE. UU. MOVIOLA (reg. 3507121, 2008, Filmtools Inc.,
  Burbank) en servicios de la clase 41 y una marca VIDEOLA ya inactiva de Magnasync/Moviola Corp. En Argentina no se pudo confirmar
  nada (la base del INPI no se puede consultar desde aca). Es un chequeo de internet, NO una busqueda marcaria formal.
- 2026-11-08 · **Licencia: GPL v3 o posterior** (GPL-3.0-or-later). Motivo: el paquete incluye FFmpeg "full" (--enable-gpl --enable-version3) y
  PyAV trae libx264/libx265 (GPL); todo lo repartido tiene que ser compatible con la GPL, y la v3+ es la coherente (FFmpeg es v3).
  Autores: Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5), a pedido de Diego. Aclaracion incluida en LICENCIA.md: la autoria de
  una IA no esta resuelta legalmente (EE. UU.: solo personas; Argentina: ley 11.723, sin jurisprudencia firme), asi que a efectos
  legales la licencia la otorga Diego. El texto de la licencia se copio del LICENSE que trae FFmpeg (GPLv3 completo, verificado), no se descargo.
- 2026-11-08 · **Preparado para GitHub, sin subir nada**: .gitignore, .gitattributes, CONTRIBUTING.md, CHANGELOG.md, GITHUB.md (checklist,
  textos y comandos). Antes de publicar hay que limpiar datos personales de los documentos de trabajo y de las rutas de las pruebas.
- 2026-11-08 · **Fase 0 (interfaz nueva), direccion:** punto medio entre la mesa de montaje y n8n. De n8n: lienzo con grilla de puntos, paneles
  redondeados, acento coral (#FF6D5A), botones primarios llenos. De Moviola: la pelicula perforada (solo en la tira de video), el contador
  en DIN (Bahnschrift) y los clips como "nodos" con puertos coral al elegirlos. Paleta violeta de noche (#12101C lienzo, #1B1829 panel).
  Sin fuentes web (la CSP lo impide y no se descarga nada): Segoe UI Variable del sistema. Texto sobre coral OSCURO a proposito: el blanco no llega a 3:1.
- 2026-11-08 · **Fase 0, estructura:** barra superior (marca, archivo, Abrir, Aceleracion, Exportar primario) / riel izquierdo de herramientas
  agrupadas (Marcar, Cortar, Historial, Audio) / centro con visor y transporte / panel derecho de Propiedades con secciones plegables
  (Fundidos, Audio, Clip) / linea de tiempo abajo sobre el lienzo. El riel es de FILAS (icono + etiqueta) y no de columna de iconos: la altura es
  lo escaso (la ventana minima es 900x620) y el ancho sobra. El panel de Propiedades queda como base para los efectos de las fases siguientes:
  cada funcion nueva suma una seccion. Los avisos pasan a tarjetas arriba al centro (antes empujaban el resto de la pantalla).
- 2026-11-08 · **Fase 0, lo que NO se toco:** ninguna funcion nueva; los IDs que usa el JS y las pruebas se conservaron. Se cambio solo lo minimo en
  edicion.js (la etiqueta de Borrar, mostrar/ocultar secciones del panel, colores del espectro). Las columnas del espacio de trabajo son explicitas
  (si un lado esta oculto, el centro no se corre).
- 2026-11-08 · **Paleta APROBADA por Diego** ("paleta como esta"): violeta de noche + acento coral. Valores definitivos: lienzo #12101C, panel #1B1829,
  panel alto #242038, borde #342F4E, texto #EFECFA / #AEA9C8 / #7A7599, coral #FF6D5A (hover #FF8A7A), rosa de error #FF5C80, menta de info #5FD6A6,
  espectro #B7ABFF -> #6F5FE0. Estos son los colores del logo (idea 3 de IDEAS.md) y de todo lo que se agregue en las fases siguientes.
- 2026-11-08 · **Fase 1: efectos por clip.** Cada clip tiene una lista `efectos` ({id, tipo, activo, params}). El catalogo vive en UN lugar
  (motor/efectos.py): ahi se declara cada efecto con sus ajustes (rango, valor por defecto, unidad) y su traduccion a un filtro de ffmpeg. De ese
  catalogo salen solas la validacion, los controles de la interfaz (efectos.js no conoce ningun efecto) y el grafo del exportador. Agregar un efecto
  nuevo = una entrada en EFECTOS + su traduccion.
- 2026-11-08 · **Orden de los efectos:** despues de encuadrar/escalar y antes de los fundidos (un fundido a negro tiene que oscurecer tambien el
  color ya corregido); en audio, antes del volumen y de los fundidos. El orden dentro de la lista cambia el resultado y se puede reordenar.
- 2026-11-08 · **Un valor fuera de rango se RECHAZA, no se recorta en silencio**: si no, lo que se ve y lo que se exporta pueden no coincidir.
  Un efecto de video solo entra en un clip de video y uno de audio en uno de audio. Apagar un efecto no pierde sus valores.
- 2026-11-08 · **Al cortar un clip, cada mitad lleva SU copia de los efectos (ids nuevos)**: tocar uno no toca el otro. El exportador une dos clips
  contiguos solo si tienen la misma "firma" de efectos (motor/efectos.firma), asi que un efecto en una sola mitad nunca se pierde ni se estira.
- 2026-11-08 · **Vista previa de efectos: solo los de video, y aproximada** (filtro CSS del navegador sobre el visor). Los de audio se oyen al
  exportar y el panel lo dice. Lo exportado es lo exacto. El control se mueve en vivo y se guarda UN cambio al soltarlo (no llena el historial).
- 2026-11-08 · **Efectos de ejemplo de esta fase:** Brillo/contraste/saturacion (eq), Voltear (hflip/vflip), Quitar graves (highpass). Ninguno cambia la
  duracion ni el tiempo: los que si (velocidad, reversa, cámara lenta) rompen la cuenta de cuadros exacta y van en la fase 4 con su propio diseño.
- 2026-11-08 · **Un proyecto guardado antes de los efectos se abre sin efectos** (cargar() completa `efectos` y el contador de ids).
- 2026-11-08 · **Fase 2 (audio): 11 efectos nuevos por clip** con el mismo mecanismo de la fase 1 (catalogo en motor/efectos.py): Quitar agudos, Graves y agudos,
  Quitar ruido de fondo (afftdn), Quitar clics (adeclick), Nivelar la voz (speechnorm), Compresor, Puerta de ruido (agate), Limitador, Eco, Cambiar el tono
  (rubberband, sin cambiar la duracion) y Al reves (areverse). La interfaz los muestra sin codigo nuevo.
- 2026-11-08 · **BUG de la fase 1, corregido:** el exportador trataba como "neutro" a un efecto con sus valores POR DEFECTO, asi que Quitar graves a 80 Hz
  (el valor inicial) no se aplicaba. Ahora cada efecto declara explicitamente que valores lo vuelven neutro (`neutro`); sin esa clave siempre actua.
- 2026-11-08 · **Un clip de audio con efectos se fuerza a durar EXACTAMENTE lo que dura** (apad + atrim al final de sus efectos): el eco y el cambio de tono
  agregan o quitan milisegundos y, sin esto, todo lo que viene despues se correria y el audio se desfasaria del video. El eco, por eso, termina con el clip.
- 2026-11-08 · **Se dejan para la fase 4 la velocidad (atempo) y el ducking**: la velocidad cambia la duracion del clip (necesita un modelo de tiempo
  propio, junto con la velocidad del video) y el ducking (bajar la musica cuando habla alguien) es de DOS pistas a la vez, no de un clip. "Al reves" y
  "Cambiar el tono" si entran porque no cambian la duracion. arnndn (RNNoise) no entra: necesita un archivo de modelo que no se puede descargar.
- 2026-11-08 · **Cortar silencios (motor/silencios.py):** una pasada de silencedetect por archivo sobre el audio ORIGINAL de A1 (no sobre el resultado de
  efectos), llevada a la linea de tiempo clip por clip; los silencios que se tocan o cruzan un corte se unen; se dejan 0,1 s de margen a cada lado (para no
  comerse el inicio de una palabra); un silencio que un corte dejo mas corto que la duracion minima ya no cuenta. Borrar = `borrar_rangos`: de atras para
  adelante, cerrando cada hueco en TODAS las pistas, en UN solo paso de deshacer. Buscar no cambia nada; los resultados se descartan si se mueve un control.
- 2026-11-08 · **Medir el volumen** usa la misma primera pasada de loudnorm que exportar: mide la mezcla COMO QUEDA (con efectos, volumen y fundidos).
- 2026-11-08 · Nota de medicion: pasar mono a estereo en ffmpeg baja 3 dB (ley de panorama); las pruebas comparan siempre contra la misma fuente sin efecto.
- 2026-11-08 · **Fase 3 (video-imagen): 10 efectos de video nuevos** con el mismo catalogo: Temperatura de color, Curvas de luz, LUT (.cube/.3dl), Reducir ruido de
  imagen (hqdn3d rapido / nlmeans fino), Enfocar o suavizar, Estabilizar, Rotar, Recortar bordes, Corregir distorsion de lente y Enderezar el horizonte. El catalogo ahora
  tiene parametros de tipo lista ("opcion") y archivo, y marca cuales se ven en la vista previa (`vista_previa`) y cuales llevan un aviso.
- 2026-11-08 · **Etapa de un efecto de video ("antes" / "despues" de encuadrar):** los que cambian el TAMANO de la imagen (rotar 90, recortar bordes) van antes de
  encuadrar, asi el formato de salida (9:16, 16:9, original...) trabaja con la imagen ya girada o recortada y todos los clips salen del mismo tamano; el tamano
  "original" tambien los tiene en cuenta. El resto va despues y antes de los fundidos.
- 2026-11-08 · **Archivos externos (LUT) y analisis previos van a una carpeta de trabajo temporal** y los filtros usan solo el NOMBRE del archivo (cwd = esa carpeta):
  nada de escapar rutas de Windows con espacios y dos puntos dentro del filtro. La carpeta se borra al terminar. Una LUT que ya no existe al exportar da un error claro.
- 2026-11-08 · **Estabilizar = vidstab en dos pasadas, y solo eso.** Se midio con una escena estatica con textura y un marcador, vista por una "camara" que tiembla: el temblor
  bajo de 25,8 a 0,0 px. Dos hallazgos: (1) `mincontrast` por defecto (0,25) descarta zonas de poco contraste y deja la estabilizacion en la mitad; con 0,1 funciona; (2) `deshake`
  EMPEORABA (de 27 a 29-85 px segun el rango) en esas pruebas, asi que NO se ofrece: no se vende un metodo que no se pudo demostrar. El analisis ve la imagen exactamente como llega
  al efecto (todo lo que va antes en la cadena, incluido un corte).
- 2026-11-08 · **Transiciones entre clips (xfade + acrossfade):** una transicion de ENTRADA de un clip, CENTRADA en el corte: toma la mitad de su duracion de la imagen y el sonido que
  SOBRAN a cada lado (fuera del tramo usado), asi que **la duracion del proyecto no cambia** y los cuadros fuera de la transicion siguen siendo exactos. La duracion maxima sale de lo que
  sobra a cada lado y de lo que dura cada clip (`transicion_maxima`); se redondea para abajo a cuadros PARES para que cada mitad sea de cuadros enteros. Una transicion entre dos mitades de la MISMA toma continua es invisible (muestran el mismo
  instante): sirve cuando se borro algo en el medio o son tomas distintas. Se pone en el grupo (video y audio enlazado). 10 tipos.
- 2026-11-08 · **Una transicion reemplaza a los fundidos de sus dos bordes** (el motor los pone en 0 y no deja crear uno nuevo ahi, con un aviso que lo explica). Si un corte o un borrado la deja sin
  clip pegado o sin material, el motor la saca sola (dentro del mismo paso de deshacer). Nunca se unen (en el exportador) dos clips a traves de una transicion.
- 2026-11-08 · **Lo que quedo afuera de la fase 3, y por que:** `cropdetect` (detectar barras negras solo) y `v360` (video 360): el primero necesita una accion de analisis dentro de la tarjeta
  del efecto (la arquitectura actual de tarjetas no la tiene; "Recortar bordes" se ajusta a mano) y el segundo es un caso muy de nicho (necesita fuentes equirectangulares). Sin vista previa
  en el visor: temperatura, curvas, LUT, ruido, enfoque, estabilizar, rotar, recorte, lente, enderezar y las transiciones (se ven al exportar; la interfaz lo dice en cada tarjeta).
- 2026-11-08 · Notas de medicion: el video guarda el gris en rango LIMITADO (Y 16-235), asi que lo que se VE no es el numero que se escribio; las barras de color saturadas (255,0,0...) no sirven para medir
  una curva (el recorte a 0 y 255 las deja iguales): se midieron grises planos.
- 2026-11-08 · **Orden de Diego: modo AUTONOMO otra vez** ("preparate para que se corte la sesion por tiempo y retoma de manera automatica cuando se restituya; segui sin consultarme, automatiza todo").
  Se reactivo la tarea programada `editor-video-reanudar` (cada 30 min; si .latido tiene menos de 45 min no toca nada) con un prompt que lee el "PLAN VIGENTE" de ESTADO.md y retoma desde la primera fase
  sin tachar. Quedan F4-F7 y el CIERRE. NO se hace sin Diego: el logo (gasta sus creditos de Higgsfield) ni la descarga de YouTube (riesgo legal). Reglas duras de siempre: sin internet/descargas/instalaciones,
  sin git ni publicar, escribir solo en editor-video, editor-video-respaldos y el scratchpad, paleta y nombre fijos.
- 2026-11-08 · **Fase 4a (tiempo): la REGLA DE TIEMPO del modelo cambia.** Un clip dura en la linea de tiempo `(hasta - desde) / velocidad` (0,25x a 4x). `largo`, `fin`, `a_fuente` y `a_linea`
  la incorporan, y con ellas todo lo que las usa: cortar (el corte en la linea cae en el segundo de la FUENTE que corresponde y se lleva al limite de cuadro EXACTO: ida y vuelta con la velocidad dejaba 1e-7 de error
  y `validar()` lo exige exacto), borrar tramos, fundidos, silencios (se llevan a la linea clip por clip), y las transiciones (el material sobrante se cuenta en segundos de la LINEA: a 4x una toma de 4 s dura 1 s).
- 2026-11-08 · **Cambiar la velocidad es un "ripple"**: todo lo que empieza despues del clip, en TODAS las pistas, se corre lo que el clip se acorta o se alarga (igual que borrar un tramo cierra el hueco en todas). Si eso hiciera
  que dos clips de una misma pista (por ejemplo dos musicas) se pisen, la operacion se rechaza con un mensaje que lo explica y no cambia nada. La velocidad es del GRUPO (video + su audio enlazado).
- 2026-11-08 · **Audio a otra velocidad:** por defecto conserva el tono (`atempo`, encadenado por debajo de 0,5); "como una cinta" (`asetrate`+`aresample`) lo deja subir o bajar. El clip se fuerza a durar exacto (como con los efectos).
  **Video a otra velocidad:** `setpts=PTS/v` y, ademas, la cantidad de cuadros del clip se fija EXACTA sobre el tiempo acumulado (`tpad`+`trim=end_frame`): el largo de un clip ya no es multiplo del cuadro de salida y el redondeo se acumularia,
  corriendo el video del audio. Camara lenta suave opcional (`minterpolate`, lento).
- 2026-11-08 · **Reversa (video `reverse` + audio `areverse`), solo del clip:** al reves el primer cuadro de la linea es el ultimo de la fuente; cortar un clip al reves deja a la IZQUIERDA el final de la fuente. `reverse` guarda todos los
  cuadros del clip en memoria: si eso pasa de unos 3 GB se rechaza ANTES de empezar con un mensaje claro (un clip al reves de 60 s en 1080x1920 serian 5,6 GB). Un clip al reves no admite transicion (ni se puede poner la reversa con una).
  La vista previa NO reproduce un tramo al reves (el navegador no puede): avisa y se recorre con las flechas; la velocidad si se reproduce (`playbackRate`, con o sin conservar el tono).
- 2026-11-08 · **Repetir un clip N veces (2 a 20)** es una operacion de copias con ripple (no una propiedad nueva del tiempo): el fundido de entrada queda solo en la primera y el de salida solo en la ultima.
- 2026-11-08 · **Ducking = ajuste de PISTA** (`pista.ducking = {activo, reduccion}`), no de clip, porque trabaja con dos pistas a la vez: la musica se comprime con A1 como disparador (`sidechaincompress`, A1 se duplica con `asplit`).
  Se midio: con 12 dB pedidos la musica bajo ~10 dB mientras habla la voz, volvio a su nivel al callar, y la voz no se toco. Si A1 esta silenciada no hay disparador y no se aplica.
- 2026-11-08 · **Fase 4b (composicion): efectos con ENTRADAS EXTRA.** Un logo o un fondo de reemplazo son archivos que se leen aparte, asi que no caben en la cadena lineal de filtros del clip. Esos efectos se marcan
  `COMPLEJOS` (`superponer`, `quitar_fondo`) y el exportador, al llegar a uno, cierra la cadena que lleva (`[entrada]cadena[vcN]`) y arma un SUBGRAFO (`movie=` + `scale` + `overlay`) cuya salida es la entrada de lo que siga.
  `efectos.subgrafo()` devuelve las lineas y la etiqueta de salida. Asi se pueden poner en cualquier orden con los demas efectos.
- 2026-11-08 · **Archivos externos siempre COPIADOS a la carpeta de trabajo** (la imagen del logo, la del fondo, la letra, y el texto en un `.txt` UTF-8): el filtro recibe un nombre sin carpetas ni espacios y nunca hay que escapar rutas de Windows
  ni comillas. El texto va con `textfile=` y `expansion=none`: un `%{pts}` o unas comillas escritas por la persona se dibujan tal cual, no se interpretan. Las 8 letras del catalogo son las que Windows trae seguras (`C:\Windows\Fonts`);
  si una falta, error claro que pide elegir otra.
- 2026-11-08 · **Imagen de fondo en «quitar fondo»**: un lienzo (`color=`) del largo del clip con la imagen encima por `overlay` (la imagen es UN cuadro y el overlay lo repite). Probe primero `movie=...:loop=0` y COLGO ffmpeg (los tiempos de
  la imagen en bucle no avanzan): descartado. Regla: nada de bucles infinitos de `movie`, siempre una fuente finita (`color=...:d=`).
- 2026-11-08 · **Tipo de ajuste nuevo `texto`** (hasta N letras, sin NUL) y el selector de archivos del sistema ahora acepta una lista de extensiones (solo las del catalogo: LUT e imagenes). El tiempo del texto («aparece a los / desaparece a los»)
  se cuenta desde el principio del CLIP (se le suma lo que la transicion agrega antes).
- 2026-11-08 · **Zoom lento (zoompan)**: se agranda el doble antes (`scale=iw*2`) para que el recorte de enteros no «tiemble», `d=1` y el avance por numero de cuadro de salida (`on`). Se mide: con 2x el ultimo cuadro es la mitad central ampliada
  (diferencia 3 contra 97 del video sin zoom).
- 2026-11-08 · **Estos efectos NO tienen vista previa en el visor** (como los de limpieza): la tarjeta avisa «Se ve al exportar». Es una decision de alcance, no un olvido: simular overlay/chroma/zoompan en el navegador seria otro motor para mantener.
- 2026-11-08 · **BUG de F4a hallado y arreglado al armar la prueba de 4b**: un clip con velocidad seguido de otro con transicion salia con el video de la mitad de largo (el `offset` del `xfade` usaba el largo en la fuente, no en la linea de tiempo).
  Ahora `prueba_tiempo.py` lo mide (150 cuadros, 5 s en imagen y sonido, cada cuadro de donde toca).
- 2026-11-09 · **Fase 5 (subtitulos): las frases viven en la LINEA DE TIEMPO, no en la fuente.** `proyecto.subtitulos = {frases: [{id, inicio, fin, texto}], estilo, huella}`. Se quemaban sobre el video ya armado (`[vcat]ass=...[vout]` al
  final del grafo), asi que no les importan los cortes, la velocidad ni las transiciones. Entran al historial (Deshacer) y se guardan con el proyecto.
- 2026-11-09 · **Si el montaje cambia DESPUES de transcribir, no se mueven solas**: `huella` es una firma de como esta armada la linea (clips, tramos, velocidad, reversa); si deja de coincidir el proyecto marca `subtitulos_desactualizados` y el
  dialogo avisa «pueden estar corridas» con un boton «Están bien así». Mover las frases automaticamente en cada operacion (borrar, velocidad, repetir...) era una fuente enorme de errores para poco; esto es honesto y simple.
- 2026-11-09 · **Transcripcion con el whisper que YA esta en la PC, sin descargar nada**: `whisper-cli` (en el PATH o en `%LOCALAPPDATA%\Programs\whisper.cpp`) y el mejor modelo `ggml-*.bin` que haya en `~/whisper-modelos` o `~/whisper.cpp/models`
  (o la variable `WHISPER_MODEL`). Si falta algo, el dialogo lo dice con palabras y deja escribir las frases a mano. El paquete portatil NO lo lleva (el modelo pesa 1,6 GB): usa el de la PC donde corre.
- 2026-11-09 · **Se transcribe el audio de A1 TAL COMO QUEDA en el montaje**: el exportador renderiza solo la pista A1 a un WAV (con cortes, velocidad, efectos y volumen) y whisper corre sobre ese archivo: los tiempos que devuelve ya son los de la
  linea de tiempo, sin mapear nada. Salida `-oj -ml N -sow` (frases de hasta N letras cortadas en palabra, JSON UTF-8: probe `-ml 1` y rompe las letras con tilde). Se descartan las frases que whisper inventa sobre el silencio
  (lista de muletillas conocidas) y las que caen donde no hay voz.
- 2026-11-09 · **Quemar con libass (`ass=`)**: se escribe un `.ass` en la resolucion exacta de la salida (1 unidad = 1 pixel, tamano = % del alto) y la letra elegida se copia a la carpeta de trabajo (`fontsdir=.`). Estilo: letra (las 8 del catalogo
  de efectos), tamano, color, contorno, fondo oscuro, mayusculas, posicion (abajo/centro/arriba) y distancia al borde. El texto de la persona se limpia (llaves y barras no son codigos .ass). Tambien `.srt` y `.vtt` al lado, con el mismo nombre.
- 2026-11-09 · **Vista previa en el visor**: la frase actual se dibuja sobre la IMAGEN (no sobre todo el visor, que deja bordes), con una aproximacion del estilo en CSS. Es una vista previa: el resultado exacto es el quemado.
- 2026-11-09 · **Deteccion de escenas/negros/congelados**: una sola pasada de ffmpeg por archivo con `scdet`, `blackdetect` y `freezedetect` juntos, llevada a la linea de tiempo clip por clip (igual que los silencios: con velocidad y reversa). Un cambio a menos
  de 0,12 s del borde de un clip no se ofrece (ya es un corte). Acciones: cortar en los cambios (`dividir_varios`, un solo paso de Deshacer) y sacar negros o congelados (`borrar_rangos`). Nota: `scdet` mira el brillo, asi que un cambio entre dos
  imagenes de brillo parecido (negro a azul oscuro) puede no aparecer; se baja la sensibilidad.
- 2026-11-09 · **Bug de F2 arreglado**: `blackdetect` escribe inicio, final y duracion en UNA sola linea; el analisis tomaba solo el inicio. Ahora la prueba (`prueba_escenas.py`) lo mide.
- 2026-11-09 · **Fase 6 (salida): el «formato» de video (original / vertical / horizontal / cuadrado) y el «tipo de archivo» son dos ejes distintos.** El formato dice la forma de la imagen; el tipo (`PERFILES`) dice contenedor + codec:
  MP4 H.264 (por defecto, el de siempre), MP4 H.265, MP4 AV1 (libsvtav1), WebM VP9 + Opus, MOV ProRes 422 (+ PCM), MKV H.264 y GIF. Todos aceptan cualquier formato de imagen, subtitulos quemados y los efectos.
- 2026-11-09 · **Calidad = alta / equilibrada / liviana**, traducida a CRF por codec (H.264 18/23/28, H.265 22/26/31, AV1 28/35/42, VP9 28/34/41). ProRes y GIF no tienen calidad para elegir. Se midio con VMAF (solo en pruebas, `libvmaf`): con «alta» todos pasan de 98
  sobre una fuente de prueba, y en H.264 el orden alta > equilibrada > liviana se cumple tanto en peso como en puntaje.
- 2026-11-09 · **GIF**: la paleta se arma DENTRO del grafo (`fps`, `scale` lanczos, `palettegen stats_mode=diff` + `paletteuse` con dither bayer): la mejor paleta de 256 colores de ESE video. Sin sonido (no se arma el audio). Ancho 120-1920 (par), cuadros 10/15/20/25,
  maximo 2 minutos (error claro: pesaria muchisimo). La duracion del GIF se mide en centesimas de segundo: se midio que 10, 15 y 25 cuadros/s dan 3,00 s en una fuente de 3 s (el chequeo de duracion del exportador acepta 4 % de desvio para GIF).
- 2026-11-09 · **VMAF mide mal los contenedores de tiempos en milisegundos (WebM, MKV)** si no se fija la cadencia: ahi los cuadros se emparejan corridos y el puntaje cae (80 en vez de 99). La medicion hace `fps=30` a los dos lados. No era un problema del archivo:
  el codigo de barras confirma que los 90 cuadros salen en orden.
- 2026-11-09 · **H.265 por GPU**: `gpu.py` ya probaba los codificadores HEVC; ahora `codificador_hevc_disponible` elige uno (el del mismo fabricante que el H.264) y `args_codificador` los trae. Solo se usa si la persona eligio GPU y el tipo es MP4 H.265; si falla, vuelve al procesador y lo dice,
  como con H.264. **NO se pudo verificar en hardware real**: en esta PC (AMD RX 6500 XT) ningun codificador HEVC paso la prueba de ffmpeg, asi que la prueba lo saltea y lo dice. Con GPU, la calidad es la fija del codificador (no cuenta la calidad elegida).
- 2026-11-09 · **Audio solo**: se suman Opus (`libopus` 128k, `.opus`) y OGG (`libvorbis` q5). El nombre propuesto para el archivo ahora depende del tipo (`exportar_destino` recibe el perfil).
- 2026-11-09 · **Fase 7 (medios y proyectos). Proyecto guardado = archivo `.moviola`** (el JSON de siempre: fuentes con su ruta, pistas, clips, efectos, subtitulos, contadores; sin las tablas de cuadros ni las direcciones locales, que se vuelven a armar).
  Al abrirlo, el PRIMER video es el principal (el del visor); si falta un archivo se dice cual (y se busca tambien junto al proyecto, por si se movio la carpeta entera); si un clip es imposible, «el proyecto esta dañado». Abrir algo que falla NO toca lo que ya estaba abierto.
- 2026-11-09 · **El motor lleva la cuenta de los cambios** (`_cambios` / `_cambios_guardados`): `sin_guardar` viaja en el proyecto y la interfaz marca el boton Guardar y la etiqueta del encabezado. Deshacer tambien cuenta como cambio. Los botones de abrir (y arrastrar un archivo, y los recientes)
  preguntan «guardar y seguir / seguir sin guardar / volver»; la funcion `abrir()` que usan las pruebas NO pregunta (solo lo hace la capa de botones: `pedirAbrir`).
- 2026-11-09 · **Recuperacion del trabajo sin guardar**: 1,5 s despues del ultimo cambio se escribe sola una copia (`recuperacion.moviola` junto a los ajustes); se borra al guardar o al abrir otra cosa; si se cierra con cambios sin guardar queda, y la pantalla de inicio ofrece «Recuperarlo»
  (solo si los archivos del proyecto siguen estando). Se abre como proyecto SIN nombre y sin guardar. El runner de pruebas le da a cada prueba sus propios ajustes para que ninguna toque los de verdad.
- 2026-11-09 · **Pantalla de inicio**: «Editar un video» y «Abrir un proyecto», la lista de abiertos hace poco (hasta 8; se guardan 12; un archivo que ya no existe no aparece) y el aviso de recuperacion. Recientes en `ajustes.json`.
- 2026-11-09 · **Varios videos: lo que se hizo y por que asi.** El modelo ya soportaba varias fuentes; lo nuevo es `insertar_fuente` (al final, o en el BORDE DE CLIP mas cercano al cursor, corriendo todo lo que sigue en todas las pistas), `mover_grupo` (cambia el orden: cierra el hueco y abre otro) y `quitar_fuente`
  (sin historial: no es una edicion de la linea de tiempo). Un video sin audio no deja huecos raros: solo no tiene clip en A1 (el exportador pone silencio). La salida toma el tamano y los cuadros por segundo del PRIMER clip, como ya hacia.
- 2026-11-09 · **El visor con varios archivos**: la linea de tiempo sigue siendo una lista de (cuadro de la fuente, segundo de la linea) pero ahora con UN contexto por archivo (`ctxFuente`: cuadros por segundo, tabla de cuadros si es VFR, cantidad) y una tabla paralela `L.tF` (de que archivo sale cada cuadro). `GET /frame` acepta `f=<id>`
  (validado con una expresion regular) y el motor abre cada video la primera vez que se lo piden (maximo 3 abiertos ademas del principal). Los datos de cada video nuevo se piden solos (`medio_info`: cuadros por segundo, tabla, espectro, miniaturas, como reproducirlo) y, al llegar, la linea de tiempo se rearma.
- 2026-11-09 · **Reproduccion de varios archivos**: un solo `<video>`; al pasar de un tramo a otro de OTRO archivo se le cambia el `src` (hay un instante de carga: es la vista previa, al exportar no existe). Si el archivo no se puede reproducir (su copia se esta preparando) se frena y se explica. Un formato que el navegador no abre
  recibe SU copia de reproduccion (por archivo, con avance). Bug encontrado al probarlo: cuando un tramo llega al final de SU archivo el `<video>` dispara `ended` antes de que el bucle vea el final del tramo: ahora `ended` tambien pasa al tramo siguiente.
- 2026-11-09 · **Limite conocido**: un proyecto que empezo con un AUDIO no puede sumar videos desde el panel (el visor esta en modo audio); el boton se apaga y lo explica. Reordenar con botones «Mover antes / Mover despues» (no arrastrando). No se agrego «reencontrar archivos faltantes» con un dialogo: se dice cuales faltan.
- 2026-11-09 · **Logo de Moviola (idea 3, pedido por Diego: «hacé el logo, gastá lo menos posible; una moviola estilizada con la paleta»).** Saldo en Higgsfield: 2 créditos (plan gratuito: no deja usar `gpt_image_2_6`, y Recraft vector costaba 2,5). Se gastaron **0,15 créditos** (una imagen `z_image`):
  `logo/moviola-higgsfield.png` (2048x2048, una moviola con dos carretes, visor y pantalla, en violeta y coral; el fondo salió algo mas claro que #12101C). Ademas se dibujo a mano, **gratis y con la paleta exacta**, `logo/moviola-icono.svg` (vectorial: carretes, cinta con perforaciones coral, pantalla con barras de espectro, sobre #12101C).
  El SVG es el que se usa en la app (icono de la pestaña/ventana); el PNG queda como alternativa de arte. Saldo que queda: ~1,85 créditos.
- 2026-11-09 · **Diego eligió el logo de Higgsfield** (la moviola generada, `logo/moviola-higgsfield.png`): es el que usa la app (`web/logo.png` de 512 px en la pantalla de inicio y `web/logo-256.png` como icono de la pestaña). El SVG dibujado a mano queda en `logo/` como alternativa vectorial.
- 2026-11-09 · **Fase 8: bajar de YouTube (idea 4), pedido por Diego** («no quiero hacer algo ilegal, solo voy a bajar videos de libre difusion; YouTube bloquea lo que no se puede bajar»). Claude lo implemento con estas salvaguardas, que son decision de diseño y no se sacan sin hablar con Diego:
  (1) **solo YouTube y de a UN video** (`validar_url`: https, youtube.com / youtu.be, sin usuario ni clave, se queda con el id y tira la lista, el tiempo y el rastreo; el id va despues de «--» para que nunca se tome por una opcion);
  (2) **confirmacion obligatoria** de que se tiene derecho a usar el video (casilla en la interfaz Y exigida por la API: tiene que llegar exactamente `true`); el dialogo dice «tuyos, de libre difusion o con licencia que lo permita»;
  (3) **no se saltea NADA**: ningun argumento de cookies, proxy, cambio de pais, credenciales ni formatos protegidos (la prueba lo comprueba sobre los argumentos reales); si YouTube lo bloquea, el motivo se muestra en palabras claras y termina ahi;
  (4) **Moviola no descarga ni instala yt-dlp**: usa el que ya haya en el equipo (PATH, `bin\` del programa o WinGet) y, si falta, explica como conseguirlo (`winget install yt-dlp.yt-dlp`); (5) nunca pisa archivos (`--no-overwrites`) y baja a una carpeta propia (`Videos\Moviola descargas`).
  Se prueba SIN internet con un yt-dlp de mentira (`pruebas/falso_ytdlp.py`) que habla como el verdadero. Importante: nadie probo todavia con el yt-dlp real ni contra YouTube (Claude no usa internet en este trabajo): la primera vez en la PC de Diego hay que mirar que ande; si YouTube cambia algo, se actualiza yt-dlp, no Moviola.
  Cancelar mata el proceso aunque yt-dlp este callado (un vigilante aparte; antes esperaba a la proxima linea de salida).
- 2026-11-09 · **Plan 2 (pedido de Diego: «Aplica tus 3 propuestas»): F9 = presets, lotes y linea de comandos.** `motor/lotes.py` hace TODO sin ventana (y sin tocar el proyecto abierto: trabaja sobre una copia): `proyecto_desde` (video, audio o `.moviola`, con la misma busqueda de archivos movidos), `preparar_preset` (5 recetas de fabrica: reel, youtube, podcast, whatsapp, clase; los cambios se validan y se mezclan ENCIMA, nunca se tocan las de fabrica), `procesar` (abrir → cortar silencios → transcribir y poner subtitulos → exportar, con el avance de 0 a 1 sobre todo el trabajo) y `procesar_lote` (de a un archivo; uno que falla NO detiene a los demas salvo `continuar=False`; cancelar se reporta como «cancelado», no como error). Decisiones: (1) **si falta una herramienta el paso se saltea y se avisa** (sin whisper el preset exporta igual y dice por que no hay subtitulos); (2) **un audio con una receta de video** se exporta como MP3 y lo avisa, en vez de fallar; (3) la salida por defecto es una carpeta `moviola-salida` AL LADO del original (y esa carpeta no se vuelve a procesar con «recursivo»); (4) los presets exportan siempre con el procesador (como el modo Automatico) y con la calidad de la receta.
  `moviola.py` es la misma funcion por linea de comandos (`presets`, `procesar`, `exportar`, `silencios`, `transcribir`, `medir`, `herramientas`; `--json` para otros programas; codigos de salida 0 / 1 / 2 / 130). Sin ventana, sin internet. La version portatil trae `Moviola-comandos.bat`.
  En la interfaz: «Reel en un clic» (boton del riel «Con un preset…» y «Procesar varios» en la pantalla de inicio): elegir receta, ajustar silencios / subtitulos / volumen / idioma, carpeta, avance con cancelar y lista de resultados por archivo. Mientras corre un preset no se puede exportar a mano (los dos usan ffmpeg a la vez) y el motor lo explica.
  Bug previo encontrado de paso: `silencios.js` y `exportar.js` definian la misma funcion global `mostrarError` (la ultima cargada pisaba a la otra, asi que un error de silencios se escribia en el dialogo de exportar). Ahora la de silencios es `errorSil`. REGLA: los scripts de `web/` comparten el espacio global; cada archivo nuevo usa nombres con su prefijo.
- 2026-11-09 · **F10: edicion por texto y karaoke.** (1) **Tiempos por palabra**: whisper `-ojf -dtw <modelo> -nfa` (DTW exige apagar flash attention; el nombre del preset sale del archivo del modelo, y si falla se repite sin DTW). Los tokens se unen por BYTES (se lee el JSON como latin-1 y se vuelve a UTF-8: una tilde queda partida entre dos tokens), «¿» y «¡» se pegan a la palabra que sigue. **`t_dtw` marca donde TERMINA el token** (medido: llegaba ~0,28 s tarde si se tomaba como inicio): es el ancla del final de cada palabra. (2) **Ajuste con el sonido** (`afinar_palabras`): cerca del final de cada palabra se busca el silencio entre dos tramos con voz y se corta en el MEDIO (en una pausa larga, cerca de la palabra que termina); cada palabra guarda `inicio`/`fin` (cortes, sin huecos entre palabras), `voz` (empieza a sonar) y `habla` (deja de sonar). Contra palabras sintetizadas por separado: error al empezar ≤ 20 ms. El orden del texto SIEMPRE se respeta (primer intento: ordenar por tiempo desordenaba el texto); tiempos amontonados se reparten por letras (`reparar_tiempos`). (3) **Modelo**: `subtitulos.palabras` + `frases[].palabras` (ids). `palabras_borrar` = `borrar_rangos` de lo que ocupan; `borrar_rango` corre palabras y frases SOLO si habia palabras y los subtitulos estaban al dia (sin palabras, el comportamiento viejo: queda «desactualizado»); una palabra se va si el centro de LO QUE SUENA cae en el tramo. `huella_linea` ya no cambia al dividir un clip en dos. Si el texto de una frase se edita a mano, se desengancha de las palabras. (4) **Karaoke**: estilo `karaoke` + `resaltado`; el .ass escribe la frase una vez por palabra con `{\1c&H..&}` (el texto no se mueve); sin palabras medidas, el tiempo se reparte por letras. Tambien se dibuja sobre el visor. (5) **Panel** `web/texto.js`: lateral y no modal (el video sigue a la vista), Supr borra las palabras elegidas (no el clip), muletillas (eh/em/mm, «o sea», bueno, digamos, tipo) que se MARCAN para revisar y no se borran solas, pausas largas (chip ⏸ y acortar todas), doble clic corrige, la palabra que suena se marca. Limite conocido: palabras de habla muy corrida (sin silencio entre ellas) tienen cortes menos exactos que con pausas.
- 2026-11-09 · **F11: la linea de tiempo con el mouse.** (1) **Zoom**: el lienzo `#carriles` se ensancha dentro de `#lt-desplazador` (overflow-x); como todo se dibujaba «como fraccion del ancho» (miniaturas, espectro, cursor, marcas) no hubo que tocar `edicion.js`. Tope de 14000 px de ancho (los canvas del espectro tienen limite) y 600 px por segundo; regla de tiempo con marcas adaptativas; Ctrl+rueda (el instante bajo el puntero queda quieto), + / − / 0, y el cursor se sigue solo (al reproducir pasa de «pagina»). Un archivo nuevo vuelve a «Ajustado». (2) **Nueva operacion del modelo `recortar_borde(grupo, lado, t)`**: acorta o estira un borde usando el material que sobra de la fuente (respeta velocidad y reversa, y el borde cae en un limite de cuadro); en el bloque principal (video + su audio) es un «ripple»: el clip empieza donde empezaba y lo que sigue se corre en todas las pistas, como al borrar un tramo; en un audio suelto no se mueve nada mas. Un clip nunca baja de 0,05 s (para sacarlo esta Borrar). Las transiciones que dejan de caber se sacan solas. (3) **Mover**: arrastrar un clip de video usa `mover_grupo` (el destino es el borde mas cercano al puntero; si lo mas cercano es uno de sus propios bordes no se mueve); un audio suelto, `mover_clip`. (4) **Iman**: cursor, marcas, principio, final y bordes de los demas clips, a 8 px; Alt lo apaga mientras se arrastra, el boton lo apaga del todo (se recuerda en el navegador). (5) Un clic comun sigue eligiendo y llevando el cursor: un clic sobre el cuerpo de un clip es un arrastre solo despues de 5 px; sobre un borde (8 px) empieza el recorte enseguida. Esc cancela. Todo en `web/linea-tiempo.js` (nuevo): `edicion.js` y `app.js` casi no cambiaron. Limite conocido: no se mueven clips entre pistas (arriba/abajo) ni se estira un clip de video alargando mas alla del material de la fuente. Tambien: el logo de la barra superior es ahora la moviola (antes dos puntos y una linea).
- 2026-11-09 · **Encabezado**: a pedido de Diego, el logo de la moviola (`web/logo-256.png`) reemplaza los dos puntos y la linea, y la palabra «Moviola» es una imagen generada en Higgsfield (`gpt_image_2`, 0,5 creditos: **quedan ~1,35**) con letra cursiva de movimiento y degradado lavanda → coral, sin fondo (`web/marca.png`, hecha con `logo/moviola-palabra-higgsfield.png`; el original queda en `logo/`). Se probo antes con texto CSS (Segoe UI Black cursiva) y Diego pidio una letra mejor.
- 2026-11-09 · **La palabra «Moviola» del encabezado, segunda version**: Diego dijo que la primera seguia con «lineas rectas» y pidio algo mas curvo: se genero otra en Higgsfield (`gpt_image_2`, 0,5 creditos: **quedan ~0,85**), letra manuscrita fluida con cola, degradado lavanda → coral (`logo/moviola-palabra-curva-higgsfield.png` → `web/marca.png`). La anterior queda en `logo/`.
- 2026-11-09 · **Bug real encontrado por Diego: «No pude abrir el selector de archivos»** al apretar «Editar un video». Causa: pywebview valida el NOMBRE de cada filtro de archivos y solo acepta letras, numeros y espacios; el filtro «Video, audio y proyectos» (agregado en la fase 7 al sumar los .moviola) tenia comas, asi que el cuadro real nunca abria (las pruebas reemplazan el cuadro y no lo veian; quedo anotado en `editor.log`: «is not a valid file filter»). Arreglo: «Video audio y proyectos». Nueva `pruebas/prueba_dialogos.py`: pasa cada cuadro de la API (editar, proyecto, varios videos, LUT, imagen, carpeta, guardar como) por una ventana de mentira que usa el MISMO validador de pywebview. REGLA: los nombres de filtro, sin comas ni signos.
- 2026-11-09 · **«Crear un proyecto»** (pedido de Diego): boton en la pantalla de inicio, despues de «Editar un video». Se eligen varios videos; el primero se abre, los demas se suman al panel de medios y se ponen en la linea de tiempo uno detras de otro (con su audio), y al final se abre «Guardar como…» para crear el archivo .moviola (si se cancela, el proyecto queda abierto sin guardar). Prueba: `prueba_crear_proyecto_app.py`.
- 2026-11-09 · **La ventana nativa se cortaba en la pantalla de Diego (TV de 1360x768)**: se abria siempre a 1280x860 (mas alto que el area util de 720 px) y la interfaz quedaba corrida y cortada. `app._tamano_ventana` ahora la ajusta a la pantalla principal (la que contiene el origen; 94 % del ancho y alto menos 90 px de barra y marco; en Full HD sigue 1280x860) y el minimo bajo a 480x360.
- 2026-11-09 · **Interfaz adaptable (pedido de Diego: «que sea web responsive y se adapte a las varias resoluciones y proporciones»)**. Causa raiz de los cortes: el encabezado forzaba un ancho minimo a toda la pagina (`body` era una grilla de una columna `auto`). Reglas nuevas al final de `estilo.css`: la pagina nunca se ensancha (columna `minmax(0,1fr)`, el encabezado se achica o pasa a dos filas), altura en `dvh`. Puntos de corte: ≥1700 px paneles anchos; ≤1250 se saca el detalle del archivo; ≤1000 riel de herramientas solo con iconos, atajos ocultos y encabezado en dos filas; ≤760 px (celular y tablet en vertical) y apaisado bajo (alto ≤560 y ancho ≤1000): UNA columna que se desplaza (visor, linea de tiempo, herramientas en una tira horizontal, propiedades); ventana ancha pero baja: todo mas compacto. Con el dedo (`pointer: coarse`) los blancos son mas grandes (y los bordes de recorte de la linea de tiempo, 18 px). Prueba: `pruebas/prueba_adaptable_app.py` redimensiona la ventana real por 10 tamanos (de 390x844 a 2560x1080) y verifica que nada se desborde.
- 2026-11-09 · **Pantalla de inicio**: los botones pasaron a tres columnas (Proyectos / Editar / YouTube) y el texto se reescribio («Editor de video y audio · Tu mesa de montaje.» y una descripcion de lo que hace hoy): el anterior («Abrí un video y recorrelo cuadro a cuadro…») era de cuando solo abria un video.
- 2026-11-09 · **Bajar de YouTube: «Video» o «Solo el audio (MP3)» como eleccion explicita** (pedido de Diego). Antes «solo audio» era una opcion perdida al final de la lista de calidades. Ahora el dialogo tiene un selector «Qué querés bajar» (Video MP4 / Solo el audio MP3); la lista de calidades queda solo para video y se esconde al elegir audio; el boton dice «Bajar el video» o «Bajar el audio». El motor no cambio (`calidad='audio'` = `-x --audio-format mp3 --audio-quality 0`). Un MP3 bajado se puede poner como audio en el cursor o abrir para editar.
- 2026-11-09 · **«Acerca de Moviola»** (pedido de Diego): dialogo con el logo, la **version (`app.VERSION`, hoy 1.0.0)**, quien lo hizo (Diego Bertelli y Claude, Anthropic, Claude Sonnet 5.5), la licencia (GPL v3 o posterior, sin garantia), que herramientas hay en ESA computadora (FFmpeg con su version, whisper con su modelo, yt-dlp; si falta una dice como conseguirla) y los componentes libres que usa. Se abre con el boton «i» del encabezado, con el enlace de la pantalla de inicio o con F1. «Ver la licencia» abre el LICENSE del programa con el visor del sistema (`acerca_licencia` no recibe ninguna ruta: solo abre el suyo). Prueba: `prueba_acerca_app.py`. Al subir de version hay que cambiar `VERSION` en `app.py`.
- 2026-11-09 · **Instalador de consola** (pedido de Diego: «un instalador que también instale por consola todo lo que necesita Moviola»). Son scripts de
  PowerShell 5 (el que trae Windows; no hace falta instalar nada para instalar) + un `.bat` de doble clic, y `construir_instalador.py` los arma junto al paquete
  portátil en `dist\Moviola-instalador\` (+ `.zip`). Decisiones: (1) **sin administrador**: todo va a `%LOCALAPPDATA%` y `HKCU` (WebView2 y el runtime de
  Visual C++, solo si faltan, piden su propio permiso). (2) **Las rutas son las que la app ya busca** (`%LOCALAPPDATA%\Programs\whisper.cpp`, `~\whisper-modelos`,
  `<Moviola>\bin\yt-dlp.exe`): el instalador no toca el código de la app. (3) **Moviola y FFmpeg salen del paquete** (no se baja nada para lo esencial: sin internet
  igual queda andando); lo opcional (whisper, modelo, yt-dlp, WebView2) se baja y **se verifica**: los modelos con el SHA-256 que publica Hugging Face (fijado en el
  script: un modelo no cambia), whisper.cpp en una **versión fija probada** (`b5454`; la última «etiquetada» no trae programas para Windows) con su SHA-256, y
  yt-dlp la última con el `SHA2-256SUMS` de la misma versión. Si no coincide, no se instala. (4) Descarga con `curl.exe` (viene con Windows 10/11, muestra el
  avance y retoma con `-C -`) y BITS como respaldo; siempre a `.part` y se renombra recién tras verificar. (5) **No se vuelve a bajar lo que ya hay**
  (`-Forzar` lo obliga). (6) **Volver a ejecutarlo actualiza** sin tocar `ajustes.json` ni la caché; una carpeta que existe, tiene archivos y no tiene la marca
  `.moviola-instalado` **no se toca**. (7) **El desinstalador solo borra una carpeta con esa marca**, se copia a `TEMP` para poder borrar la carpeta en la que
  vive, y lo bajado aparte (whisper, modelo) se pregunta con «No» por defecto porque otros programas pueden usarlo. (8) Modelo recomendado con `-Silencioso`:
  el turbo comprimido (q5_0, 574 MB, mismo nombre de preset DTW que el completo). (9) Los `.ps1` van **UTF-8 con BOM** (sin BOM, PowerShell 5 rompe las tildes).
  (10) Una trampa encontrada al probar: en PowerShell las variables no distinguen mayúsculas, y `$MODELOS` (la tabla) pisaba al parámetro `$Modelos` (la carpeta).
- 2026-11-09 · **Revisión completa del código y versión 1.1.0** (pedido de Diego: «revisá el código completo» y después «arreglá todo»). Decisiones:
  (1) **Programas externos**: `motor/__init__.py` pone `NoDefaultCurrentDirectoryInExePath=1` (Windows y `shutil.which` dejan de mirar la carpeta actual) y
  `motor.herramienta()` nunca devuelve un nombre suelto (`CreateProcess` también miraría la carpeta actual): si el programa no está, devuelve `bin\nombre.exe`
  y falla con «no encontrado». Se eligió esto y no `os.chdir` porque la línea de comandos recibe rutas relativas. (2) **`validar` revisa primero los tipos**
  (número finito, no booleano) porque toda comparación con `NaN` da falso y lo dejaba pasar; el volumen va de 0 a 4 como en la interfaz. (3) **Los datos de cada
  archivo siguen saliendo del proyecto guardado** (volver a medir todo al abrir es lento y la duración del contenedor es aproximada en MPEG-PS): solo se ataja
  el caso grosero, un archivo que hoy dura mucho menos de lo que usan sus clips (margen: 25 % + 2 s). Una huella por archivo queda como mejora.
  (4) **Al cerrar se cancela todo y se espera hasta 6 s**; no se usó un «Job Object» de Windows porque también mataría al navegador que se abrió en modo
  navegador y al visor de la licencia. A whisper se le agregó un vigilante (puede pasar muchos segundos sin escribir). (5) **Modo navegador**: 90 s sin latido
  (una pestaña oculta late una vez por minuto) y nunca con un trabajo en curso; los diálogos de tkinter los atiende el hilo principal, que ahí solo espera.
  (6) **`ajustes.json`** se cambia con `API._cambiar_ajustes`: candado + releer en el momento de escribir. (7) **Tope del cuerpo 16 MB** (sigue acotado; una
  hora de palabras pesa ~1 MB) y las respuestas se arman con `allow_nan=False`. (8) **Instalada, los datos van al perfil** (`.moviola-instalado` junto al
  programa lo indica); la portátil sigue escribiendo al lado. (9) **`-protocol_whitelist file`** en cada entrada de FFmpeg/ffprobe y en PyAV. (10) Queda
  sabido y sin resolver: la suma de yt-dlp viene del mismo sitio que el programa (detecta una descarga rota, no una versión comprometida) y dos ventanas de
  Moviola comparten la copia de recuperación. Pruebas: `pruebas/prueba_revision.py`.
