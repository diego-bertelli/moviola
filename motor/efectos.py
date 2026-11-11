# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Catálogo de efectos por clip. Python puro: no usa ffmpeg ni la interfaz.

Un efecto es una entrada de la lista `efectos` de un clip: {"id", "tipo", "activo", "params"}.
Este módulo sabe DOS cosas de cada tipo:
  - qué parámetros tiene (nombre, rango, valor por defecto): con eso se validan los pedidos y la
    interfaz arma sola los controles, sin código nuevo por efecto;
  - cómo se traduce a un filtro de ffmpeg (`filtro_video` / `filtro_audio`).

Para agregar un efecto hay que sumar UNA entrada a EFECTOS y, si hace falta, su traducción acá abajo.
Los efectos se aplican en el orden de la lista, DESPUÉS de encuadrar/escalar y ANTES de los fundidos
(un fundido a negro tiene que oscurecer también el color ya corregido).

Efectos que cambian la duración o el tiempo (velocidad, reversa...) NO van por acá: rompen la cuenta
de cuadros exacta y necesitan su propio diseño (fase 4 del plan).

Etapa de un efecto de video (clave "etapa"): los que cambian el TAMAÑO de la imagen (rotar 90°, recortar bordes)
van "antes" de encuadrar: así el encuadre final (recortar o dejar barras, 9:16, 16:9...) trabaja ya con la imagen
nueva y todos los clips salen del mismo tamaño. El resto va "despues" (es el valor por defecto).
Un efecto puede declarar "vista_previa": True si el visor sabe mostrarlo (si no, la interfaz avisa que se ve al
exportar) y "aviso" con una nota para la persona (por ejemplo, que es lento).
"""

import math
import os

CATEGORIAS = ("video", "audio")
ETAPAS = ("antes", "despues")      # antes o despues de ENCUADRAR (llevar la imagen al tamano de salida)
EXTENSIONES_LUT = (".cube", ".3dl")
EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
# Efectos que arman un subgrafo con una entrada extra (una imagen, un color de fondo): no son un filtro mas de la cadena.
COMPLEJOS = ("superponer", "quitar_fondo")
POSICIONES = [{"valor": v, "nombre": n} for v, n in (
    ("arriba_izquierda", "Arriba a la izquierda"), ("arriba_centro", "Arriba al centro"), ("arriba_derecha", "Arriba a la derecha"),
    ("centro_izquierda", "Al centro a la izquierda"), ("centro", "En el centro"), ("centro_derecha", "Al centro a la derecha"),
    ("abajo_izquierda", "Abajo a la izquierda"), ("abajo_centro", "Abajo al centro"), ("abajo_derecha", "Abajo a la derecha"))]
FUENTES = {"segoeui": ("Segoe UI", "segoeui.ttf"), "segoeuib": ("Segoe UI negrita", "segoeuib.ttf"), "arial": ("Arial", "arial.ttf"),
           "arialbd": ("Arial negrita", "arialbd.ttf"), "georgia": ("Georgia", "georgia.ttf"), "impact": ("Impact", "impact.ttf"),
           "times": ("Times New Roman", "times.ttf"), "verdana": ("Verdana", "verdana.ttf")}
COLORES_TEXTO = {"blanco": "white", "amarillo": "yellow", "negro": "black", "coral": "0xFF6D5A", "celeste": "0x7FD8FF", "verde": "0x5FD6A6"}

# tipo: {nombre, categoria, descripcion, params: [{id, nombre, tipo, ...}]}
# tipo de parámetro: "num" (min, max, paso, defecto, unidad) o "bool" (defecto)
EFECTOS = {
    # ------------------------------------------------------------------ video
    "color_basico": {
        "nombre": "Brillo, contraste y saturación",
        "categoria": "video",
        "descripcion": "Corrige la luz y el color del clip.",
        "vista_previa": True,
        "neutro": {"brillo": 0.0, "contraste": 1.0, "saturacion": 1.0},
        "params": [
            {"id": "brillo", "nombre": "Brillo", "tipo": "num", "min": -0.5, "max": 0.5, "paso": 0.01, "defecto": 0.0, "unidad": ""},
            {"id": "contraste", "nombre": "Contraste", "tipo": "num", "min": 0.5, "max": 2.0, "paso": 0.01, "defecto": 1.0, "unidad": "×"},
            {"id": "saturacion", "nombre": "Saturación", "tipo": "num", "min": 0.0, "max": 2.0, "paso": 0.01, "defecto": 1.0, "unidad": "×"},
        ],
    },
    "voltear": {
        "nombre": "Voltear",
        "categoria": "video",
        "descripcion": "Da vuelta la imagen como en un espejo.",
        "vista_previa": True,
        "neutro": {"horizontal": False, "vertical": False},
        "params": [
            {"id": "horizontal", "nombre": "Izquierda con derecha", "tipo": "bool", "defecto": True},
            {"id": "vertical", "nombre": "Arriba con abajo", "tipo": "bool", "defecto": False},
        ],
    },
    "temperatura": {
        "nombre": "Temperatura de color",
        "categoria": "video",
        "descripcion": "Más baja = imagen más cálida (anaranjada); más alta = más fría (azulada).",
        "neutro": {"kelvin": 6500},
        "params": [
            {"id": "kelvin", "nombre": "Temperatura", "tipo": "num", "min": 2000, "max": 12000, "paso": 100, "defecto": 6500, "unidad": "K"},
        ],
    },
    "curvas_luz": {
        "nombre": "Curvas de luz",
        "categoria": "video",
        "descripcion": "Aclara u oscurece las sombras y las luces por separado (una curva en S da más contraste).",
        "neutro": {"sombras": 0.0, "luces": 0.0},
        "params": [
            {"id": "sombras", "nombre": "Sombras", "tipo": "num", "min": -0.2, "max": 0.2, "paso": 0.01, "defecto": 0.0, "unidad": ""},
            {"id": "luces", "nombre": "Luces", "tipo": "num", "min": -0.2, "max": 0.2, "paso": 0.01, "defecto": 0.0, "unidad": ""},
        ],
    },
    "lut": {
        "nombre": "LUT de color (.cube)",
        "categoria": "video",
        "descripcion": "Aplica un look de color guardado en un archivo .cube o .3dl (los traen muchos paquetes de color).",
        "neutro": {"archivo": ""},
        "params": [
            {"id": "archivo", "nombre": "Archivo", "tipo": "archivo", "extensiones": list(EXTENSIONES_LUT), "defecto": ""},
        ],
    },
    "reducir_ruido_imagen": {
        "nombre": "Reducir ruido de imagen",
        "categoria": "video",
        "descripcion": "Limpia el grano de las tomas con poca luz.",
        "aviso": "El método fino (nlmeans) es mucho más lento al exportar.",
        "params": [
            {"id": "metodo", "nombre": "Método", "tipo": "opcion", "defecto": "rapido",
             "opciones": [{"valor": "rapido", "nombre": "Rápido"}, {"valor": "fino", "nombre": "Fino (lento)"}]},
            {"id": "fuerza", "nombre": "Fuerza", "tipo": "num", "min": 1, "max": 10, "paso": 1, "defecto": 4, "unidad": ""},
        ],
    },
    "enfocar": {
        "nombre": "Enfocar o suavizar",
        "categoria": "video",
        "descripcion": "Más de 0 enfoca los detalles; menos de 0 suaviza la imagen.",
        "neutro": {"cantidad": 0.0},
        "params": [
            {"id": "cantidad", "nombre": "Cantidad", "tipo": "num", "min": -1.5, "max": 3.0, "paso": 0.1, "defecto": 1.0, "unidad": ""},
        ],
    },
    "estabilizar": {
        "nombre": "Estabilizar",
        "categoria": "video",
        "descripcion": "Calma las sacudidas de una toma hecha a mano. Una fuerza mayor suaviza movimientos más lentos, pero acerca un poco la imagen.",
        "aviso": "Se calcula al exportar, en una pasada de análisis aparte (por eso tarda más), y la vista previa no lo muestra.",
        "params": [
            {"id": "fuerza", "nombre": "Fuerza", "tipo": "num", "min": 1, "max": 30, "paso": 1, "defecto": 10, "unidad": ""},
        ],
    },
    "rotar": {
        "nombre": "Rotar",
        "categoria": "video",
        "etapa": "antes",
        "descripcion": "Gira la imagen de a 90 grados (un video grabado de costado, por ejemplo).",
        "params": [
            {"id": "grados", "nombre": "Girar", "tipo": "opcion", "defecto": "90",
             "opciones": [{"valor": "90", "nombre": "90° a la derecha"}, {"valor": "180", "nombre": "180°"}, {"valor": "270", "nombre": "90° a la izquierda"}]},
        ],
    },
    "recortar_bordes": {
        "nombre": "Recortar bordes",
        "categoria": "video",
        "etapa": "antes",
        "descripcion": "Saca una franja de cada lado (barras negras, un micrófono que se coló en el cuadro). Después se encuadra al formato de salida.",
        "neutro": {"izquierda": 0.0, "derecha": 0.0, "arriba": 0.0, "abajo": 0.0},
        "params": [
            {"id": "izquierda", "nombre": "Izquierda", "tipo": "num", "min": 0.0, "max": 45.0, "paso": 0.5, "defecto": 0.0, "unidad": "%"},
            {"id": "derecha", "nombre": "Derecha", "tipo": "num", "min": 0.0, "max": 45.0, "paso": 0.5, "defecto": 0.0, "unidad": "%"},
            {"id": "arriba", "nombre": "Arriba", "tipo": "num", "min": 0.0, "max": 45.0, "paso": 0.5, "defecto": 0.0, "unidad": "%"},
            {"id": "abajo", "nombre": "Abajo", "tipo": "num", "min": 0.0, "max": 45.0, "paso": 0.5, "defecto": 0.0, "unidad": "%"},
        ],
    },
    "lente": {
        "nombre": "Corregir distorsión de lente",
        "categoria": "video",
        "descripcion": "Endereza las líneas curvas de un gran angular (positivo) o de un teleobjetivo (negativo).",
        "neutro": {"k1": 0.0, "k2": 0.0},
        "params": [
            {"id": "k1", "nombre": "Distorsión principal", "tipo": "num", "min": -0.5, "max": 0.5, "paso": 0.01, "defecto": 0.0, "unidad": ""},
            {"id": "k2", "nombre": "Distorsión en los bordes", "tipo": "num", "min": -0.5, "max": 0.5, "paso": 0.01, "defecto": 0.0, "unidad": ""},
        ],
    },
    "enderezar": {
        "nombre": "Enderezar el horizonte",
        "categoria": "video",
        "descripcion": "Gira un poco la imagen y la amplía lo justo para que no queden esquinas negras.",
        "neutro": {"angulo": 0.0},
        "params": [
            {"id": "angulo", "nombre": "Ángulo", "tipo": "num", "min": -15.0, "max": 15.0, "paso": 0.1, "defecto": 0.0, "unidad": "°"},
            {"id": "ampliar", "nombre": "Ampliar", "tipo": "num", "min": 1.0, "max": 1.6, "paso": 0.01, "defecto": 1.1, "unidad": "×"},
        ],
    },
    "superponer": {
        "nombre": "Logo o imagen encima",
        "categoria": "video",
        "descripcion": "Pone una imagen (un logo, una marca de agua) encima del video, en la posición, el tamaño y la transparencia que elijas. Sirve .png con fondo transparente.",
        "neutro": {"archivo": ""},
        "params": [
            {"id": "archivo", "nombre": "Imagen", "tipo": "archivo", "extensiones": list(EXTENSIONES_IMAGEN), "defecto": ""},
            {"id": "posicion", "nombre": "Posición", "tipo": "opcion", "defecto": "abajo_derecha", "opciones": POSICIONES},
            {"id": "tamano", "nombre": "Tamaño (del ancho)", "tipo": "num", "min": 3, "max": 100, "paso": 1, "defecto": 20, "unidad": "%"},
            {"id": "opacidad", "nombre": "Opacidad", "tipo": "num", "min": 0.05, "max": 1.0, "paso": 0.05, "defecto": 1.0, "unidad": ""},
            {"id": "margen", "nombre": "Margen", "tipo": "num", "min": 0, "max": 20, "paso": 1, "defecto": 3, "unidad": "%"},
        ],
    },
    "quitar_fondo": {
        "nombre": "Quitar el fondo verde o azul",
        "categoria": "video",
        "descripcion": "Vuelve transparente un fondo de color liso (pantalla verde) y pone otro fondo atrás: un color o una imagen.",
        "params": [
            {"id": "color", "nombre": "Color a quitar", "tipo": "opcion", "defecto": "verde",
             "opciones": [{"valor": "verde", "nombre": "Verde"}, {"valor": "azul", "nombre": "Azul"}]},
            {"id": "similitud", "nombre": "Cuánto se parece", "tipo": "num", "min": 0.01, "max": 0.5, "paso": 0.01, "defecto": 0.15, "unidad": ""},
            {"id": "mezcla", "nombre": "Suavizar el borde", "tipo": "num", "min": 0.0, "max": 0.5, "paso": 0.01, "defecto": 0.05, "unidad": ""},
            {"id": "fondo", "nombre": "Poner atrás", "tipo": "opcion", "defecto": "negro",
             "opciones": [{"valor": "negro", "nombre": "Negro"}, {"valor": "blanco", "nombre": "Blanco"}, {"valor": "gris", "nombre": "Gris"},
                          {"valor": "imagen", "nombre": "Una imagen"}]},
            {"id": "imagen", "nombre": "Imagen de fondo", "tipo": "archivo", "extensiones": list(EXTENSIONES_IMAGEN), "defecto": ""},
        ],
    },
    "texto": {
        "nombre": "Texto o título",
        "categoria": "video",
        "descripcion": "Escribe un texto sobre la imagen (un título, un nombre, una frase). Se puede hacer aparecer solo en un tramo del clip.",
        "neutro": {"texto": ""},
        "params": [
            {"id": "texto", "nombre": "Texto", "tipo": "texto", "max": 300, "defecto": ""},
            {"id": "fuente", "nombre": "Letra", "tipo": "opcion", "defecto": "segoeuib",
             "opciones": [{"valor": k, "nombre": v[0]} for k, v in FUENTES.items()]},
            {"id": "tamano", "nombre": "Tamaño (del alto)", "tipo": "num", "min": 2, "max": 30, "paso": 1, "defecto": 8, "unidad": "%"},
            {"id": "color", "nombre": "Color", "tipo": "opcion", "defecto": "blanco",
             "opciones": [{"valor": k, "nombre": k.capitalize()} for k in COLORES_TEXTO]},
            {"id": "contorno", "nombre": "Con contorno negro", "tipo": "bool", "defecto": True},
            {"id": "caja", "nombre": "Con fondo oscuro", "tipo": "bool", "defecto": False},
            {"id": "posicion", "nombre": "Posición", "tipo": "opcion", "defecto": "abajo_centro", "opciones": POSICIONES},
            {"id": "margen", "nombre": "Margen", "tipo": "num", "min": 0, "max": 20, "paso": 1, "defecto": 5, "unidad": "%"},
            {"id": "desde", "nombre": "Aparece a los", "tipo": "num", "min": 0.0, "max": 3600.0, "paso": 0.1, "defecto": 0.0, "unidad": "s"},
            {"id": "hasta", "nombre": "Desaparece a los (0 = al final)", "tipo": "num", "min": 0.0, "max": 3600.0, "paso": 0.1, "defecto": 0.0, "unidad": "s"},
        ],
    },
    "zoom_lento": {
        "nombre": "Zoom lento",
        "categoria": "video",
        "descripcion": "Acerca o aleja la imagen poco a poco durante el clip (el efecto de las fotos animadas de los documentales).",
        "neutro": {"zoom": 1.0},
        "params": [
            {"id": "direccion", "nombre": "Dirección", "tipo": "opcion", "defecto": "acercar",
             "opciones": [{"valor": "acercar", "nombre": "Acercar"}, {"valor": "alejar", "nombre": "Alejar"}]},
            {"id": "zoom", "nombre": "Cuánto", "tipo": "num", "min": 1.0, "max": 2.5, "paso": 0.05, "defecto": 1.3, "unidad": "×"},
            {"id": "centro_x", "nombre": "Centro: horizontal", "tipo": "num", "min": 0.0, "max": 1.0, "paso": 0.05, "defecto": 0.5, "unidad": ""},
            {"id": "centro_y", "nombre": "Centro: vertical", "tipo": "num", "min": 0.0, "max": 1.0, "paso": 0.05, "defecto": 0.5, "unidad": ""},
        ],
    },
    # ------------------------------------------------------------------ audio
    "pasa_altos": {
        "nombre": "Quitar graves",
        "categoria": "audio",
        "descripcion": "Corta los sonidos más graves que la frecuencia elegida (golpes de micrófono, rumor de fondo).",
        "params": [
            {"id": "frecuencia", "nombre": "Cortar por debajo de", "tipo": "num", "min": 20, "max": 500, "paso": 1, "defecto": 80, "unidad": "Hz"},
        ],
    },
    "pasa_bajos": {
        "nombre": "Quitar agudos",
        "categoria": "audio",
        "descripcion": "Corta los sonidos más agudos que la frecuencia elegida (silbidos, siseo).",
        "params": [
            {"id": "frecuencia", "nombre": "Cortar por encima de", "tipo": "num", "min": 1000, "max": 20000, "paso": 100, "defecto": 8000, "unidad": "Hz"},
        ],
    },
    "graves_agudos": {
        "nombre": "Graves y agudos",
        "categoria": "audio",
        "descripcion": "Sube o baja los graves y los agudos, como el control de tono de un equipo de música.",
        "neutro": {"graves": 0.0, "agudos": 0.0},
        "params": [
            {"id": "graves", "nombre": "Graves", "tipo": "num", "min": -15.0, "max": 15.0, "paso": 0.5, "defecto": 0.0, "unidad": "dB"},
            {"id": "agudos", "nombre": "Agudos", "tipo": "num", "min": -15.0, "max": 15.0, "paso": 0.5, "defecto": 0.0, "unidad": "dB"},
        ],
    },
    "quitar_ruido": {
        "nombre": "Quitar ruido de fondo",
        "categoria": "audio",
        "descripcion": "Baja el ruido parejo de fondo (soplido, ventilador, zumbido). Si se exagera, la voz suena metálica.",
        "params": [
            {"id": "reduccion", "nombre": "Cuánto bajarlo", "tipo": "num", "min": 1, "max": 40, "paso": 1, "defecto": 12, "unidad": "dB"},
            {"id": "piso", "nombre": "Nivel del ruido", "tipo": "num", "min": -80, "max": -20, "paso": 1, "defecto": -50, "unidad": "dB"},
        ],
    },
    "quitar_clics": {
        "nombre": "Quitar clics",
        "categoria": "audio",
        "descripcion": "Repara los chasquidos cortos (clics de grabación, golpecitos). Un valor más bajo detecta más.",
        "params": [
            {"id": "umbral", "nombre": "Umbral de detección", "tipo": "num", "min": 1.0, "max": 10.0, "paso": 0.5, "defecto": 2.0, "unidad": ""},
        ],
    },
    "nivelar_voz": {
        "nombre": "Nivelar la voz",
        "categoria": "audio",
        "descripcion": "Sube las partes bajas de una voz hasta emparejarlas con las fuertes.",
        "params": [
            {"id": "fuerza", "nombre": "Fuerza", "tipo": "num", "min": 1, "max": 30, "paso": 1, "defecto": 6, "unidad": ""},
        ],
    },
    "compresor": {
        "nombre": "Compresor",
        "categoria": "audio",
        "descripcion": "Achica la diferencia entre lo fuerte y lo suave. Con «Ganancia» se recupera el volumen perdido.",
        "params": [
            {"id": "umbral", "nombre": "Desde qué nivel actúa", "tipo": "num", "min": -60, "max": 0, "paso": 1, "defecto": -20, "unidad": "dB"},
            {"id": "razon", "nombre": "Fuerza (razón)", "tipo": "num", "min": 1.0, "max": 20.0, "paso": 0.5, "defecto": 3.0, "unidad": ": 1"},
            {"id": "ataque", "nombre": "Ataque", "tipo": "num", "min": 1, "max": 500, "paso": 1, "defecto": 20, "unidad": "ms"},
            {"id": "liberacion", "nombre": "Liberación", "tipo": "num", "min": 10, "max": 2000, "paso": 10, "defecto": 250, "unidad": "ms"},
            {"id": "ganancia", "nombre": "Ganancia", "tipo": "num", "min": 0, "max": 24, "paso": 1, "defecto": 0, "unidad": "dB"},
        ],
    },
    "puerta": {
        "nombre": "Puerta de ruido",
        "categoria": "audio",
        "descripcion": "Silencia lo que suena por debajo del umbral (el ruido entre frases).",
        "params": [
            {"id": "umbral", "nombre": "Silenciar por debajo de", "tipo": "num", "min": -80, "max": -10, "paso": 1, "defecto": -45, "unidad": "dB"},
            {"id": "liberacion", "nombre": "Liberación", "tipo": "num", "min": 10, "max": 2000, "paso": 10, "defecto": 250, "unidad": "ms"},
        ],
    },
    "limitador": {
        "nombre": "Limitador",
        "categoria": "audio",
        "descripcion": "Impide que el sonido pase de un tope (evita que sature).",
        "params": [
            {"id": "tope", "nombre": "Tope", "tipo": "num", "min": -24, "max": 0, "paso": 1, "defecto": -1, "unidad": "dB"},
        ],
    },
    "eco": {
        "nombre": "Eco",
        "categoria": "audio",
        "descripcion": "Repite el sonido con un retraso. El eco termina con el clip.",
        "params": [
            {"id": "retardo", "nombre": "Retraso", "tipo": "num", "min": 20, "max": 1500, "paso": 10, "defecto": 300, "unidad": "ms"},
            {"id": "nivel", "nombre": "Nivel del eco", "tipo": "num", "min": 0.05, "max": 0.9, "paso": 0.05, "defecto": 0.4, "unidad": ""},
        ],
    },
    "tono": {
        "nombre": "Cambiar el tono",
        "categoria": "audio",
        "descripcion": "Sube o baja el tono sin cambiar la velocidad ni la duración (12 semitonos = una octava).",
        "neutro": {"semitonos": 0.0},
        "params": [
            {"id": "semitonos", "nombre": "Semitonos", "tipo": "num", "min": -12.0, "max": 12.0, "paso": 0.5, "defecto": 0.0, "unidad": "st"},
        ],
    },
    "invertir_audio": {
        "nombre": "Al revés",
        "categoria": "audio",
        "descripcion": "Reproduce el audio de este clip de atrás para adelante. No cambia la duración.",
        "params": [],
    },
}


# Transiciones entre dos clips pegados: id -> nombre para la persona y nombre del filtro xfade de ffmpeg.
# Una transicion esta CENTRADA en el corte: usa un poco de imagen y sonido que sobran a cada lado, asi que la
# duracion total del proyecto no cambia (ver motor/proyecto.py: transicion_maxima).
TRANSICIONES = {
    "disolver": {"nombre": "Disolvencia", "xfade": "fade"},
    "fundido_negro": {"nombre": "Fundido por negro", "xfade": "fadeblack"},
    "fundido_blanco": {"nombre": "Fundido por blanco", "xfade": "fadewhite"},
    "granulado": {"nombre": "Disolvencia granulada", "xfade": "dissolve"},
    "deslizar_izquierda": {"nombre": "Deslizar a la izquierda", "xfade": "slideleft"},
    "deslizar_derecha": {"nombre": "Deslizar a la derecha", "xfade": "slideright"},
    "cortina_izquierda": {"nombre": "Cortina hacia la izquierda", "xfade": "wipeleft"},
    "circulo": {"nombre": "Círculo que se abre", "xfade": "circleopen"},
    "pixelar": {"nombre": "Pixelar", "xfade": "pixelize"},
    "zoom": {"nombre": "Acercarse", "xfade": "zoomin"},
}
DURACION_TRANSICION = (0.1, 3.0)


def catalogo_transiciones():
    return {k: {"nombre": v["nombre"]} for k, v in TRANSICIONES.items()}


class ErrorEfecto(ValueError):
    """Un pedido de efecto que no se puede cumplir; el mensaje se le muestra a la persona."""


def _coma(n):
    """Un numero como se escribe en castellano: coma decimal."""
    return str(n).replace(".", ",")


def catalogo():
    """El catálogo completo, listo para mandar a la interfaz (JSON)."""
    return {tipo: {"nombre": d["nombre"], "categoria": d["categoria"], "descripcion": d["descripcion"],
                   "aviso": d.get("aviso", ""), "vista_previa": bool(d.get("vista_previa")),
                   "etapa": d.get("etapa", "despues"),
                   "params": [dict(p) for p in d["params"]]} for tipo, d in EFECTOS.items()}


def definicion(tipo):
    d = EFECTOS.get(tipo)
    if d is None:
        raise ErrorEfecto("Ese efecto no existe.")
    return d


def categoria(tipo):
    return definicion(tipo)["categoria"]


def defectos(tipo):
    """Los parámetros con sus valores por defecto."""
    return {p["id"]: p["defecto"] for p in definicion(tipo)["params"]}


def limpiar_params(tipo, nuevos, base=None, comprobar_archivos=False):
    """Valida `nuevos` (un dict parcial) y los mezcla sobre `base` (o sobre los valores por defecto).
    Devuelve el dict completo. Un parámetro desconocido, de otro tipo o fuera de rango es un error:
    no se recorta en silencio, porque entonces lo que se ve y lo que se exporta pueden no coincidir.
    comprobar_archivos: además, un parámetro de tipo archivo tiene que existir (se pide al ELEGIR el archivo; al
    abrir un proyecto no, porque el archivo pudo haberse movido: eso lo avisa el exportador)."""
    if not isinstance(nuevos, dict):
        raise ErrorEfecto("Los valores del efecto no son válidos.")
    specs = {p["id"]: p for p in definicion(tipo)["params"]}
    out = dict(defectos(tipo) if base is None else base)
    for k, v in nuevos.items():
        s = specs.get(k)
        if s is None:
            raise ErrorEfecto("Ese efecto no tiene el ajuste «%s»." % k)
        if s["tipo"] == "bool":
            if not isinstance(v, bool):
                raise ErrorEfecto("«%s» es de sí o no." % s["nombre"])
            out[k] = v
        elif s["tipo"] == "opcion":
            if not isinstance(v, str) or v not in [o["valor"] for o in s["opciones"]]:
                raise ErrorEfecto("«%s» no tiene esa opción." % s["nombre"])
            out[k] = v
        elif s["tipo"] == "texto":
            if not isinstance(v, str) or len(v) > s["max"] or "\x00" in v:
                raise ErrorEfecto("«%s» tiene que ser un texto de hasta %d letras." % (s["nombre"], s["max"]))
            out[k] = v
        elif s["tipo"] == "archivo":
            if not isinstance(v, str):
                raise ErrorEfecto("«%s» tiene que ser un archivo." % s["nombre"])
            if v:
                if os.path.splitext(v)[1].lower() not in s["extensiones"]:
                    raise ErrorEfecto("«%s» tiene que ser un archivo %s." % (s["nombre"], " o ".join(s["extensiones"])))
                if comprobar_archivos and not os.path.isfile(v):
                    raise ErrorEfecto("No encuentro el archivo: %s" % v)
            out[k] = v
        else:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ErrorEfecto("«%s» tiene que ser un número." % s["nombre"])
            if not s["min"] <= v <= s["max"]:
                raise ErrorEfecto("«%s» va de %s a %s." % (s["nombre"], _coma(s["min"]), _coma(s["max"])))
            out[k] = round(float(v), 4) if isinstance(s["defecto"], float) else int(round(v))
    return out


def etapa(tipo):
    """'antes' si el efecto cambia el tamaño de la imagen (va antes de encuadrar), 'despues' si no."""
    return definicion(tipo).get("etapa", "despues")


def es_complejo(tipo):
    return tipo in COMPLEJOS


def _x(pos, margen):
    return {"izquierda": "%d" % margen, "centro": "(W-w)/2", "derecha": "W-w-%d" % margen}[pos.rsplit("_", 1)[-1] if "_" in pos else "centro"]


def _xy(posicion, margen, ancho_txt, alto_txt):
    """Expresiones x, y de ffmpeg para un ancla de las 9 posiciones. Con (W,w,H,h) del overlay o (w,text_w,h,text_h) del texto."""
    vert, _, horiz = posicion.partition("_")
    if posicion == "centro":
        vert, horiz = "centro", "centro"
    x = {"izquierda": "%d" % margen, "centro": "(%s-%s)/2" % ancho_txt, "derecha": "%s-%s-%d" % (ancho_txt[0], ancho_txt[1], margen)}[horiz]
    y = {"arriba": "%d" % margen, "centro": "(%s-%s)/2" % alto_txt, "abajo": "%s-%s-%d" % (alto_txt[0], alto_txt[1], margen)}[vert]
    return x, y


def subgrafo(tipo, params, ctx, entrada, etiqueta):
    """Para los efectos COMPLEJOS: (lineas del grafo, etiqueta de la salida). `entrada` es la etiqueta de la imagen que llega;
    `etiqueta(prefijo)` da etiquetas nuevas. Las capas externas (imagen, fondo) se leen con `movie=` desde la carpeta de trabajo."""
    ancho, alto = ctx["ancho"], ctx["alto"]
    if tipo == "superponer":
        mx = int(round(ancho * params["margen"] / 100.0))
        w = max(2, int(ancho * params["tamano"] / 100.0 / 2) * 2)
        logo, salida = etiqueta("lg"), etiqueta("vo")
        x, y = _xy(params["posicion"], mx, ("W", "w"), ("H", "h"))
        alfa = ",colorchannelmixer=aa=%.3f" % params["opacidad"] if params["opacidad"] < 0.999 else ""
        return ["movie=%s,scale=%d:-2,format=rgba%s[%s]" % (ctx["copiar"](params["archivo"]), w, alfa, logo),
                "[%s][%s]overlay=x='%s':y='%s':format=auto[%s]" % (entrada, logo, x, y, salida)], salida
    if tipo == "quitar_fondo":
        fg, bg, salida = etiqueta("fg"), etiqueta("bg"), etiqueta("vq")
        color = {"verde": "0x00FF00", "azul": "0x0000FF"}[params["color"]]
        lineas = ["[%s]chromakey=color=%s:similarity=%.3f:blend=%.3f,format=yuva420p[%s]" % (entrada, color, params["similitud"], params["mezcla"], fg)]
        if params["fondo"] == "imagen":
            if not params["imagen"]:
                raise ErrorEfecto("Elegí la imagen de fondo.")
            # un lienzo del largo del clip con la imagen encima (la imagen es un solo cuadro: el overlay lo repite hasta el final)
            lienzo, img = etiqueta("lz"), etiqueta("im")
            lineas.append("color=c=black:s=%dx%d:r=%s:d=%.6f,format=yuv420p[%s]" % (ancho, alto, ctx["fps"], ctx["largo"] + 1.0, lienzo))
            lineas.append("movie=%s,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,format=rgba[%s]"
                          % (ctx["copiar"](params["imagen"]), ancho, alto, ancho, alto, img))
            lineas.append("[%s][%s]overlay=format=auto[%s]" % (lienzo, img, bg))
        else:
            lineas.append("color=c=%s:s=%dx%d:r=%s:d=%.6f,format=yuv420p[%s]"
                          % ({"negro": "black", "blanco": "white", "gris": "gray"}[params["fondo"]], ancho, alto, ctx["fps"], ctx["largo"] + 1.0, bg))
        lineas.append("[%s][%s]overlay=format=auto:shortest=1[%s]" % (bg, fg, salida))
        return lineas, salida
    raise ErrorEfecto("Ese efecto no arma un subgrafo.")


def necesita_preparacion(tipo, params):
    """True si, con estos valores, el efecto necesita una pasada de análisis ANTES de exportar (estabilizar bien)."""
    return tipo == "estabilizar"


def _par(n):
    return max(2, int(n / 2) * 2)


def dims_tras(tipo, params, ancho, alto):
    """Tamaño de la imagen después de un efecto 'antes' (los demás no la cambian)."""
    if es_neutro(tipo, params):
        return ancho, alto
    if tipo == "rotar" and params.get("grados") in ("90", "270"):
        return alto, ancho
    if tipo == "recortar_bordes":
        return (_par(ancho * (1 - (params["izquierda"] + params["derecha"]) / 100.0)),
                _par(alto * (1 - (params["arriba"] + params["abajo"]) / 100.0)))
    return ancho, alto


def es_neutro(tipo, params):
    """True si con estos valores el efecto no cambia nada (no hace falta ponerlo en el grafo). Cada efecto declara
    en su entrada de EFECTOS los valores que lo vuelven neutro («neutro»); sin esa clave, siempre actúa."""
    neutro = definicion(tipo).get("neutro")
    if not neutro:
        return False
    def igual(k, v):
        x = params.get(k, v)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(x, (int, float)) and not isinstance(x, bool):
            return abs(float(x) - float(v)) < 1e-9
        return x == v
    return all(igual(k, v) for k, v in neutro.items())


# ----------------------------------------------------------- traducción a ffmpeg

def filtro_video(tipo, params, ctx=None):
    """Filtro de ffmpeg (texto) o None si el efecto no cambia nada o no es de video.

    ctx: lo que algunos efectos necesitan saber del grafo: {"ancho", "alto"} (el tamaño de la imagen en ese punto)
    y {"copiar": f(ruta) -> nombre} (lleva un archivo externo, como una LUT, a la carpeta de trabajo y devuelve un nombre
    sin carpetas, para no tener que escapar rutas dentro del filtro) y {"preparacion": f(tipo, params) -> nombre}
    (registra una pasada de análisis previa y devuelve el nombre del archivo que produce)."""
    ctx = ctx or {}
    if categoria(tipo) != "video" or es_neutro(tipo, params):
        return None
    if tipo == "color_basico":
        return "eq=brightness=%.4f:contrast=%.4f:saturation=%.4f" % (params["brillo"], params["contraste"], params["saturacion"])
    if tipo == "voltear":
        partes = (["hflip"] if params.get("horizontal") else []) + (["vflip"] if params.get("vertical") else [])
        return ",".join(partes)
    if tipo == "temperatura":
        return "colortemperature=temperature=%d" % int(params["kelvin"])
    if tipo == "curvas_luz":
        return "curves=master='0/0 0.25/%.4f 0.75/%.4f 1/1'" % (0.25 + params["sombras"], 0.75 + params["luces"])
    if tipo == "lut":
        return "lut3d=file=%s" % ctx["copiar"](params["archivo"])
    if tipo == "reducir_ruido_imagen":
        f = float(params["fuerza"])
        if params["metodo"] == "fino":
            return "nlmeans=s=%.2f:p=5:r=9" % f
        return "hqdn3d=luma_spatial=%.2f:chroma_spatial=%.2f:luma_tmp=%.2f:chroma_tmp=%.2f" % (f, f * 0.75, f * 1.5, f * 1.1)
    if tipo == "enfocar":
        return "unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=%.2f" % params["cantidad"]
    if tipo == "estabilizar":
        return "vidstabtransform=input=%s:smoothing=%d:zoom=0:optzoom=1:interpol=bilinear" % (
            ctx["preparacion"](tipo, params), int(params["fuerza"]))
    if tipo == "rotar":
        return {"90": "transpose=1", "270": "transpose=2", "180": "hflip,vflip"}[params["grados"]]
    if tipo == "recortar_bordes":
        w = "trunc(iw*(1-%.4f)/2)*2" % ((params["izquierda"] + params["derecha"]) / 100.0)
        h = "trunc(ih*(1-%.4f)/2)*2" % ((params["arriba"] + params["abajo"]) / 100.0)
        return "crop=w='%s':h='%s':x='iw*%.4f':y='ih*%.4f'" % (w, h, params["izquierda"] / 100.0, params["arriba"] / 100.0)
    if tipo == "lente":
        return "lenscorrection=k1=%.3f:k2=%.3f" % (params["k1"], params["k2"])
    if tipo == "texto":
        alto = ctx["alto"]
        tam = max(8, int(round(alto * params["tamano"] / 100.0)))
        mx = int(round(ctx["ancho"] * params["margen"] / 100.0))
        x, y = _xy(params["posicion"], mx, ("w", "text_w"), ("h", "text_h"))
        op = ["fontfile=%s" % ctx["fuente"](params["fuente"]), "textfile=%s" % ctx["escribir_texto"](params["texto"]),
              "fontsize=%d" % tam, "fontcolor=%s" % COLORES_TEXTO[params["color"]], "x='%s'" % x, "y='%s'" % y, "text_shaping=1", "expansion=none"]
        if params["contorno"]:
            op += ["borderw=%d" % max(1, tam // 14), "bordercolor=black"]
        if params["caja"]:
            op += ["box=1", "boxcolor=black@0.55", "boxborderw=%d" % max(2, tam // 3)]
        t0 = ctx.get("t0", 0.0)          # segundos que la transicion agrega antes del clip
        if params["hasta"] > 0:
            op.append("enable='between(t,%.3f,%.3f)'" % (params["desde"] + t0, max(params["hasta"], params["desde"] + 0.1) + t0))
        elif params["desde"] > 0:
            op.append("enable='gte(t,%.3f)'" % (params["desde"] + t0))
        return "drawtext=" + ":".join(op)
    if tipo == "zoom_lento":
        z, n = float(params["zoom"]), max(1, int(round(ctx["largo"] * ctx["fps_n"])))
        expr = ("1+(%.4f-1)*on/%d" if params["direccion"] == "acercar" else "%.4f-(%.4f-1)*on/%d")
        expr = (expr % (z, n)) if params["direccion"] == "acercar" else (expr % (z, z, n))
        # se agranda al doble antes de recortar: el recorte de zoompan es de pixeles enteros y asi no "tiembla"
        return ("scale=iw*2:ih*2,zoompan=z='%s':x='(iw-iw/zoom)*%.3f':y='(ih-ih/zoom)*%.3f':d=1:s=%dx%d:fps=%s,setsar=1"
                % (expr, params["centro_x"], params["centro_y"], ctx["ancho"], ctx["alto"], ctx["fps"]))
    if tipo == "enderezar":
        z = float(params["ampliar"])
        return ("rotate=%.6f:ow=iw:oh=ih:c=black,scale=w='trunc(iw*%.4f/2)*2':h='trunc(ih*%.4f/2)*2',crop=%d:%d"
                % (math.radians(params["angulo"]), z, z, ctx["ancho"], ctx["alto"]))
    return None


def _db_a_lineal(db):
    return 10.0 ** (float(db) / 20.0)


def filtro_audio(tipo, params):
    """Filtro de ffmpeg (texto) o None si el efecto no cambia nada o no es de audio."""
    if categoria(tipo) != "audio" or es_neutro(tipo, params):
        return None
    if tipo == "pasa_altos":
        return "highpass=f=%d" % int(params["frecuencia"])
    if tipo == "pasa_bajos":
        return "lowpass=f=%d" % int(params["frecuencia"])
    if tipo == "graves_agudos":
        partes = []
        if abs(params["graves"]) > 1e-9:
            partes.append("bass=g=%.2f" % params["graves"])
        if abs(params["agudos"]) > 1e-9:
            partes.append("treble=g=%.2f" % params["agudos"])
        return ",".join(partes) or None
    if tipo == "quitar_ruido":
        return "afftdn=nr=%d:nf=%d" % (int(params["reduccion"]), int(params["piso"]))
    if tipo == "quitar_clics":
        return "adeclick=threshold=%.2f" % params["umbral"]
    if tipo == "nivelar_voz":
        return "speechnorm=e=%d" % int(params["fuerza"])
    if tipo == "compresor":
        # el umbral de acompressor es lineal (0,001 a 1) y la ganancia tambien (1 a 64)
        return "acompressor=threshold=%.5f:ratio=%.2f:attack=%d:release=%d:makeup=%.3f" % (
            max(0.001, _db_a_lineal(params["umbral"])), params["razon"], int(params["ataque"]),
            int(params["liberacion"]), _db_a_lineal(params["ganancia"]))
    if tipo == "puerta":
        return "agate=threshold=%.5f:ratio=8:attack=10:release=%d" % (_db_a_lineal(params["umbral"]), int(params["liberacion"]))
    if tipo == "limitador":
        # level=0: sin el "auto nivel" de alimiter, que subiria todo el audio hasta el tope
        return "alimiter=limit=%.4f:level=0" % max(0.0625, _db_a_lineal(params["tope"]))
    if tipo == "eco":
        return "aecho=0.8:0.6:%d:%.3f" % (int(params["retardo"]), params["nivel"])
    if tipo == "tono":
        return "rubberband=pitch=%.6f" % (2.0 ** (float(params["semitonos"]) / 12.0))
    if tipo == "invertir_audio":
        return "areverse"
    return None


def firma(efectos):
    """Lo que hace un grupo de efectos, sin los ids: dos clips con la misma firma se ven y suenan igual
    (el exportador la usa para unir clips contiguos)."""
    return tuple((e["tipo"], bool(e["activo"]), tuple(sorted(e["params"].items()))) for e in efectos)
