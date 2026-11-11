# Licencia de Moviola

**Moviola** es software libre, licenciado bajo la **GNU General Public License, versión 3 o posterior**
(identificador SPDX: `GPL-3.0-or-later`).

> Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)

El texto completo y legalmente válido de la licencia está en el archivo [`LICENSE`](LICENSE), en inglés. Es el
texto oficial de la Free Software Foundation; **las traducciones no oficiales no tienen valor legal**, así que este
documento es una explicación en castellano, no un reemplazo. Cada archivo de código lleva al principio una línea
`SPDX-License-Identifier: GPL-3.0-or-later` y el aviso de copyright.

## Resumen en lenguaje común

- Podés **usarlo** para lo que quieras, en tu casa o en tu trabajo, sin pedir permiso y sin pagar.
- Podés **copiarlo y compartirlo** con quien quieras, gratis o cobrando por la copia o el servicio.
- Podés **estudiarlo y modificarlo**: el código fuente viene con el programa (son archivos de texto: `app.py`,
  `motor\`, `web\`).
- Si lo **repartís** (con cambios o sin ellos), tenés que repartirlo **bajo esta misma licencia**, conservar los avisos de
  copyright, incluir la carpeta `licencias\` y el archivo `LICENSE`, y poner el código fuente a disposición de quien lo reciba
  (ver "Si lo compartís").
- Si lo **modificás y lo repartís**, tenés que marcar claramente que lo cambiaste y qué cambiaste.
- **No tiene garantía de ningún tipo** (ver más abajo).

## Autores

| Autor | Aporte |
|---|---|
| **Diego Bertelli** | Autor humano del proyecto: concibió el producto, definió qué hace y cómo se ve, tomó las decisiones y dirigió el trabajo. |
| **Claude** (Anthropic), modelo **Claude Sonnet 5.5** (`claude-sonnet-5-5`) | Escribió la mayor parte del código y la documentación, y lo probó, bajo la dirección de Diego. Otras versiones de Claude participaron en etapas anteriores del desarrollo. |

### Aclaración sobre la autoría (importante)

La ley de derecho de autor **no está resuelta** para obras hechas con inteligencia artificial, y varía según el país:

- En varios países (por ejemplo Estados Unidos, según su Oficina de Derecho de Autor) **solo una persona humana puede ser
  titular** de derechos de autor. En la Argentina, la ley 11.723 también atribuye la autoría a personas, y no hay
  jurisprudencia firme sobre obras hechas con IA.
- Por eso, **a efectos legales, quien otorga esta licencia es Diego Bertelli**, como persona responsable del proyecto.
  La mención de Claude como autor es un **reconocimiento de quién hizo el trabajo**, y se mantiene en los avisos de
  copyright por pedido expreso de Diego, pero no se puede asegurar que cree por sí sola un derecho de autor a favor de Claude
  ni de Anthropic.
- Las condiciones de uso de Anthropic vigentes al momento de escribir esto dicen, en general, que quien usa el servicio
  conserva los derechos sobre lo que genera. **Conviene verificarlas** y, si el proyecto se va a usar comercialmente o a
  publicar a gran escala, **consultar a una persona abogada** especializada en propiedad intelectual.

## Qué cubre esta licencia y qué no

**Cubre** el código y los documentos propios: `app.py`, `construir_portatil.py`, `motor\`, `web\`, `pruebas\`, los archivos
`.md` y los `.bat`.

**No cubre:**

- **El nombre "Moviola".** La GPL no concede derechos sobre nombres ni marcas (la GPLv3, sección 7, lo permite expresamente).
  "Moviola" es además el nombre histórico de las mesas de montaje de cine y consta como marca de EE. UU. en otro rubro
  (ver `DECISIONES.md`). Para compartirlo gratis o usarlo en una organización no suele haber problema; antes de **vender**
  el programa o publicarlo comercialmente con ese nombre conviene una **búsqueda formal de marcas** (INPI, USPTO).
  Quien haga una versión modificada puede tener que cambiarle el nombre.
- **El logo**, cuando exista: se decidirá su licencia por separado (puede ser la misma GPL o una de contenido, como
  Creative Commons BY-SA).
- **Tus videos y audios, ni los archivos que exportes.** El programa **nunca modifica los originales** y lo que exportás es
  tuyo: la GPL no impone nada sobre los archivos creados con un programa.
- **Los componentes de terceros** que vienen en la versión portátil: cada uno conserva su propia licencia (ver abajo).

## Por qué GPL y no otra

El paquete portátil incluye **FFmpeg compilado con codecs GPL** (la compilación "full" de gyan.dev, con
`--enable-gpl --enable-version3`, que incluye x264 y x265), y PyAV trae esas mismas bibliotecas en `av.libs`. Quien reparte
un conjunto que **enlaza o incluye** código GPL tiene que repartirlo bajo una licencia compatible con la GPL. La
**GPL versión 3 o posterior** es la opción coherente: es compatible con FFmpeg (GPLv3) y con todas las bibliotecas
permisivas que se usan (BSD, MIT, PSF, MIT-CMU). Una licencia permisiva (MIT, BSD) para el código propio sería posible,
pero el conjunto repartido igual quedaría sujeto a la GPL.

> "o posterior" significa que quien reciba el programa puede elegir aplicar la versión 3 o cualquier versión más nueva de la GPL
> que publique la Free Software Foundation.

## Componentes de terceros que vienen en la versión portátil

| Componente | Para qué se usa | Licencia |
|---|---|---|
| FFmpeg 9.0.2 (`bin\ffmpeg.exe`, `bin\ffprobe.exe`), compilación "full" de gyan.dev | proxy de reproducción, miniaturas, espectro, exportación | GPL v3 (incluye x264 y x265, GPL) |
| PyAV (`av`) 19.0.2 y las bibliotecas de `av.libs` | leer cuadros y tiempos de los videos | BSD-3-Clause (PyAV); libx264 y libx265 GPL; libvpx, libopus, libwebp, dav1d, SVT-AV1 BSD |
| Python 3.13 | el intérprete | PSF License |
| pywebview 6.2.1 | la ventana | BSD-3-Clause |
| Pillow 12.3.0 | imágenes JPEG | MIT-CMU (HPND) |
| pythonnet, clr_loader | puente con WebView2 | MIT |
| cffi, pycparser, bottle, proxy_tools, typing_extensions | dependencias | MIT-0, BSD, MIT, MIT, PSF-2.0 |

Los textos de cada licencia están en la carpeta `licencias\`. WebView2 (Microsoft Edge) **no se incluye**: lo trae
Windows 11 o se instala aparte, con su propia licencia de Microsoft.

## Si lo compartís

1. **Conservá** `LICENSE`, este archivo, `AUTHORS` y la carpeta `licencias\`.
2. **Código fuente de Moviola:** ya está en el paquete (`app.py`, `motor\`, `web\`, `construir_portatil.py`), como texto legible.
   Si repartís una versión modificada, ponela a disposición de quien la reciba bajo la misma licencia.
3. **Código fuente de los componentes GPL incluidos** (oferta escrita, GPLv3 sección 6): quien reciba este paquete puede
   obtener el código fuente correspondiente de FFmpeg 9.0.2, x264 y x265 en los sitios del proyecto de cada uno
   (<https://ffmpeg.org/download.html>, <https://www.gyan.dev/ffmpeg/builds/>, <https://www.videolan.org/developers/x264.html>,
   <https://www.x265.org/>; la compilación de las bibliotecas de PyAV: <https://github.com/PyAV-Org/pyav-ffmpeg>). El número
   de versión se ve con `bin\ffmpeg.exe -version`. Quien reparta el paquete debe mantener esta oferta durante al menos tres
   años. *(Estos enlaces apuntan a los sitios de cada proyecto; conviene comprobar que sigan vigentes cuando se reparta.)*
4. **No agregues restricciones** adicionales a lo que recibe la otra persona (por ejemplo, prohibirle compartirlo).

## Patentes

La GPLv3 (sección 11) hace que quienes contribuyen al programa den licencia sobre **sus propias** patentes. No cubre patentes
de **terceros**: los formatos H.264, H.265 (HEVC) y AAC están patentados en algunos países. Para uso personal o interno no
suele haber consecuencias; **repartir o vender un producto** que codifique esos formatos puede requerir licencias de los
consorcios de patentes. Es un tema para una persona abogada, no se resuelve con este documento.

## Sin garantía

Como dice la GPL (secciones 15 y 16), el programa se ofrece **"tal cual", sin garantía de ningún tipo**, ni de que sirva
para un fin particular. En la práctica: se probó mucho (hay pruebas automáticas) pero **no se verificó a oído** el audio ni con
una GPU real, y no hay garantía de que un archivo exportado sea idóneo para una entrega profesional. **Revisá siempre lo que
exportás** y guardá copias de lo importante. Quien creó el programa no responde por pérdidas de datos ni de trabajo.

## Contribuciones

Quien aporte código, documentación o cambios a este proyecto acepta que su aporte se licencie bajo
**GPL-3.0-or-later**, igual que el resto.

## Cómo se aplica a los archivos

Cada archivo de código empieza con:

```
Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
SPDX-License-Identifier: GPL-3.0-or-later
```

Esto sigue la recomendación de la FSF ("How to Apply These Terms to Your New Programs", al final de `LICENSE`) y la
especificación REUSE.
