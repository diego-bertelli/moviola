# Cómo colaborar

¡Gracias por querer aportar a Moviola! Es un editor de video y audio **local** (sin internet, sin cuentas) para Windows.

## Antes de empezar

- Leé `README.md` (qué hace y cómo está armado) y `DECISIONES.md` (por qué se hizo cada cosa así).
- Todo aporte se licencia bajo **GPL-3.0-or-later**, igual que el resto del proyecto (ver `LICENCIA.md`).
  Al abrir un pull request aceptás eso.
- Los archivos nuevos de código llevan el encabezado de copyright y el `SPDX-License-Identifier: GPL-3.0-or-later`
  (copiá el de cualquier archivo existente).

## Reglas del producto (por favor, respetalas)

1. **Nunca se modifica un archivo del usuario.** Exportar siempre crea un archivo nuevo (`nombre-v1`, `nombre-v2`...).
2. **Local primero.** La interfaz no se conecta a ningún lado (hay una CSP que lo impide). Cualquier función que use internet
   tiene que ser opcional, explícita y estar claramente avisada.
3. **La interfaz no recibe poder de más.** La API solo expone lo necesario; por ejemplo, "Mostrar en la carpeta" no acepta
   rutas de afuera.
4. **Los cortes caen en límites de cuadro reales**, también en video de framerate variable.

## Cómo probar

Las pruebas están en `pruebas/` y se corren de a una, con Python 3.13 y las dependencias de `README.md`:

```
python -I pruebas/prueba_proyecto.py
python -I pruebas/prueba_exportar_api.py
python -I pruebas/prueba_auditoria.py
```

Cada una termina con `TODO BIEN`. Hay pruebas de ventana real (`*_app.py`) que abren la interfaz y la manejan solas.
Algunas usan videos reales que no están en el repositorio; si no los encuentran, esa parte se saltea.
Cambios en el exportador o en el modelo de edición: agregá un caso a la prueba correspondiente.

## Estilo

- Código y comentarios en castellano rioplatense, claros y sin jerga innecesaria; los mensajes que ve la persona
  se escriben para una persona, no para un programador.
- JavaScript sin frameworks ni dependencias (`web/`); Python con la biblioteca estándar más PyAV, pywebview y Pillow.
- Un bug encontrado merece una prueba que lo cubra.

## Reportar un problema

Abrí un *issue* con: qué hiciste, qué esperabas, qué pasó, la versión de Windows, y el contenido de `editor.log`
(está junto al programa o en `%LOCALAPPDATA%\Moviola`). **No subas videos personales.**
