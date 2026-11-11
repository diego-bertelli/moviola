# Auditoría profunda del código — fase final (2026-11-09)

Pedido por Diego: «cuando termines todo, hacé una auditoría profunda del código». Se hizo con **pruebas que rompen cosas a propósito** (no solo leyendo) y con
revisión de lo que no se puede probar así. Todo lo hallado se arregló con una prueba que lo cubre; lo que no se pudo verificar queda dicho al final.

## Qué se revisó y cómo

| Tema | Cómo | Resultado |
|---|---|---|
| La API local (≈62 métodos) con **argumentos absurdos** (nulos, textos de 5 000 letras, listas, diccionarios anidados, números gigantes, ids que no existen, `<script>`, rutas con `..`) | `pruebas/prueba_fuzz_api.py`: ~4 800 llamadas; exige que nada explote, que el proyecto siga válido y que un error no deje cambios a medias | **2 hallazgos reales** (abajo), arreglados |
| El servidor HTTP con cuerpos raros (JSON roto, `NaN`, no UTF-8, anidado 3 000 niveles, `Host` ajeno, `Content-Type` ajeno, métodos internos) | misma prueba, parte 2 | **1 hallazgo** (abajo) |
| Archivos de proyecto **dañados** (120 mutaciones al azar de un proyecto guardado: campos borrados, tipos cambiados, números absurdos) | misma prueba, parte 3b | **1 hallazgo** por revisión (abajo); 37 abiertos válidos, 83 rechazados sin tocar nada |
| 400 operaciones mezcladas (válidas y absurdas) sobre el modelo | misma prueba, parte 3 | sin hallazgos |
| Nombres de carpeta y de archivo difíciles: `Ñandú ¿qué (final) [v2]`, `100% real & más`, `l'été à São Paulo`, espacios dobles, japonés | `pruebas/prueba_rutas_raras.py`: abrir, sumar un segundo video, guardar, abrir, logo + texto + subtítulos quemados, exportar, `.srt` | sin hallazgos |
| **Hilos**: editar, pedir cuadros, consultar medios, guardar y EXPORTAR a la vez (6 hilos + una exportación en medio) | `pruebas/prueba_concurrencia.py` | sin hallazgos: ninguna excepción, proyecto válido, el video exportado es completo y coherente (se exporta una copia) |
| **Fugas**: 40 vueltas de abrir / sumar / quitar / guardar / abrir / exportar | script de handles de Windows y de hilos (no se dejó como prueba permanente: depende de `ctypes`) | +1 handle y 0 hilos de diferencia: sin fugas |
| Archivos temporales | la prueba de basura comprueba que no queden `moviola-export-*` ni `moviola-voz-*` | sin restos |
| **XSS** en la interfaz | búsqueda de `innerHTML`, `insertAdjacentHTML`, `eval`, `new Function`, `document.write` en `web/*.js` | **no hay ninguno**: todo texto de archivos, frases, nombres y errores entra con `textContent`; la CSP además prohíbe scripts que no sean del propio servidor |
| Seguridad del servidor local | lectura de `motor/servidor.py` | token en la ruta (comparación en tiempo constante), `Host` verificado (DNS rebinding), `Origin` y `Content-Type` exigidos en POST, tamaño máximo del cuerpo, `NaN`/`Infinity` rechazados, id de archivo de `/frame` validado con expresión regular. Sin hallazgos |
| Excepciones tragadas en silencio (`except …: pass`) | script de revisión estática (no hay pyflakes) | 20 casos: todos son limpieza (cerrar un archivo, borrar un temporal) o el registro mismo; ninguno esconde un error de verdad |
| Sintaxis | `node --check` en los 17 `.js`, `compileall` en Python | limpio (y se quitó una advertencia de escape inválido en una prueba) |
| Yt-dlp / whisper: argumentos y ejecución | `prueba_descargas.py` revisa los argumentos REALES que se le pasan | no se usa nada para esquivar protecciones; la dirección va después de `--` |

## Hallazgos y arreglos

1. **Argumentos de un tipo que no es → error 500** (`exportar_destino`, `medio_estado`, `quitar_medio`… con una lista o un diccionario donde va un id: `TypeError: unhashable type`).
   No corrompía nada, pero la interfaz recibía «error interno». **Arreglo:** `API._blindar` envuelve cada método publicado; un pedido imposible devuelve `{"error": "Ese pedido no es válido."}` y se anota en el registro.
2. **Un cuerpo JSON anidado miles de veces desbordaba la pila del analizador → 500.** **Arreglo:** el servidor atrapa `RecursionError` y contesta 400.
3. **Abrir un proyecto dañado podía dejar el programa a medias.** El orden era: abrir el video principal nuevo → cambiar lo que estaba abierto → recién entonces armar el proyecto. Si el proyecto resultaba inválido, el visor quedaba
   mostrando el video del proyecto roto mientras seguía abierto el proyecto viejo. **Arreglo:** el proyecto se valida entero **antes** de tocar nada (`cargar_dict` + `validar`); la prueba 3b comprueba que un rechazo no cambia el video, la ruta ni el proyecto abiertos.
   (Hallado leyendo el código; la prueba actual lo cubre, no se vio fallar antes del arreglo.)

Errores encontrados al construir las últimas fases (ya arreglados y cubiertos por pruebas, para que queden anotados):
- clip con velocidad seguido de otro con transición: el video salía más corto (el `offset` del `xfade` usaba el largo de la fuente) — `prueba_tiempo.py`;
- `blackdetect` escribe inicio, final y duración en una sola línea y se leía solo el inicio — `prueba_escenas.py`;
- al terminar un archivo el `<video>` dispara `ended` antes de que el bucle vea el fin del tramo: con varios videos eso frenaba la reproducción — `prueba_medios_app.py`;
- el espectro de un video recién sumado al panel salía vacío para siempre — `prueba_medios.py`;
- cancelar una descarga esperaba a la próxima línea de salida de yt-dlp (con la red muda eran 60 s) — ahora un vigilante mata el proceso — `prueba_descargas.py`;
- trampa de las pruebas (no del programa): un `ultimo-error.log` viejo hace fallar las pruebas de ventana (exigen que no exista); el programa lo borra al arrancar pero las pruebas no. Queda avisado en `ESTADO.md`.

## Lo que NO se pudo verificar (dicho con franqueza)

- **Bajar de YouTube de verdad**: Claude no usa internet en este trabajo; todo se probó con un yt-dlp de mentira. Falta la primera prueba real en la PC de Diego.
- **H.265 por GPU**: en esta PC (AMD RX 6500 XT) ningún codificador HEVC de hardware pasó la prueba de ffmpeg, así que ese camino (y su regreso al procesador) quedó escrito pero sin ejecutar en hardware.
- **Transcripción con otros idiomas, modelos o PCs**: probada con la voz de Windows en español y el modelo `large-v3-turbo` de esta PC.
- **Windows 10 sin WebView2** (modo navegador): lo cubre `prueba_navegador.py` en parte, pero no se probó en una instalación limpia.
- **Videos muy largos** (horas) y proyectos con cientos de clips: el modelo se probó con secuencias al azar, no con volumen; la interfaz dibuja un bloque por clip.

## Para la próxima auditoría

Correr `python -I pruebas/correr_todas.py --sin-portatil` (son 39 pruebas, ~20 minutos), y para subir la dureza: `PROPIEDADES_N=2000 python -I pruebas/prueba_proyecto.py` (secuencias al azar del modelo) y más vueltas en `prueba_fuzz_api.py`.
