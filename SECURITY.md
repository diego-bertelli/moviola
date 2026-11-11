# Seguridad

## Cómo avisar de un problema

Si encontrás una vulnerabilidad, **no abras un *issue* público**. Usá «Report a vulnerability» en la pestaña *Security* del repositorio
(aviso privado de GitHub). Contá qué versión usás (está en «Acerca de Moviola»), los pasos para reproducirlo y qué puede hacer alguien con eso.
Moviola es un proyecto personal sin garantía: se responde cuando se puede.

## Qué promete el diseño

- **Todo local.** La interfaz es una página servida por un servidor HTTP que escucha solo en `127.0.0.1`, en un puerto al azar, con un
  token aleatorio en la ruta. Se validan `Host` (DNS rebinding), `Origin` y `Content-Type`; la página lleva una CSP que le impide conectarse
  a otro lado o cargar código ajeno. La interfaz nunca usa `innerHTML` ni `eval`.
- **Nunca se modifica un archivo del usuario.** Exportar crea siempre un archivo nuevo.
- **Programas externos** (FFmpeg, ffprobe, whisper-cli, yt-dlp): se ejecutan con lista de argumentos (sin `shell`), con ruta completa y
  nunca desde la carpeta actual. FFmpeg solo puede abrir archivos (`-protocol_whitelist file`). Los textos y archivos del usuario no se
  escriben dentro del filtro de FFmpeg: van a una carpeta de trabajo con nombres fijos.
- **Proyectos `.moviola`**: son JSON; se validan enteros (tipos y rangos) antes de abrir y un archivo dañado no cambia nada de lo abierto.
- **Red**: el programa no usa internet salvo «Bajar de YouTube» (yt-dlp, pedido explícito de la persona). El **instalador** sí baja cosas
  (whisper.cpp, un modelo, yt-dlp, WebView2) y verifica cada una con SHA-256 o con la firma de Microsoft.

## Límites conocidos

- La suma de verificación de yt-dlp se baja del mismo sitio que el programa: detecta una descarga rota, no una versión comprometida.
- Abrir archivos de video de origen dudoso expone a los errores que tenga FFmpeg, como en cualquier reproductor.
- Quien ya puede ejecutar programas con tu usuario puede leer el token del servidor local: Moviola no protege contra eso.
- El instalador y los `.bat` no están firmados.

Lo que se revisó y cómo está en `AUDITORIA-F8.md` y en `DECISIONES.md`; las pruebas de regresión, en `pruebas/prueba_auditoria.py`,
`pruebas/prueba_fuzz_api.py`, `pruebas/prueba_servidor.py` y `pruebas/prueba_revision.py`.
