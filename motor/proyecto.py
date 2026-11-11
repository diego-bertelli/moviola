# Moviola
# Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
# SPDX-License-Identifier: GPL-3.0-or-later
# Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
"""Modelo de edicion: pistas con clips, cortes, borrado con cierre, fundidos, volumen,
audio extra y deshacer/rehacer. Python puro, sin ffmpeg ni interfaz: se prueba a fondo solo.

Conceptos
  fuente   un archivo (video o audio) ya leido: duracion y, si es video, el segundo de cada cuadro.
  pista    'V1' video, 'A1' audio del video, 'A2'... audio extra (musica, locucion).
  clip     un tramo de una fuente puesto en la linea de tiempo:
           desde/hasta = segundos DE LA FUENTE, inicio = segundo de la LINEA DE TIEMPO.
  grupo    clips enlazados (el video y su audio): se cortan y se borran juntos.

Garantias que se verifican en pruebas/prueba_proyecto.py (incluye pruebas de propiedades al azar):
  - un corte cae siempre en un limite de CUADRO real de la fuente (tambien en video de framerate variable);
  - borrar un tramo lo saca de TODAS las pistas y cierra el hueco en todas a la vez: la sincronia
    entre video y audio no se pierde;
  - una operacion que falla no deja el proyecto a medias;
  - deshacer y rehacer devuelven exactamente el estado anterior;
  - despues de cualquier secuencia de operaciones, validar() no encuentra problemas.
"""

import copy
import hashlib
import math
import json
import os
from bisect import bisect_left

from motor import efectos as _fx
from motor import subtitulos as _sub

TOL = 1e-4            # dos tiempos que difieren menos que esto son "el mismo"
HISTORIAL_MAX = 200
DURACION_TRANSICION_MAX = 3.0
VELOCIDAD = (0.25, 4.0)            # de un cuarto a cuatro veces la velocidad original
VECES_REPETIR = (2, 20)
REDUCCION_DUCKING = (3, 24)        # dB que baja una pista de musica cuando habla el audio del video
CURVAS = ("tri", "qsin", "hsin", "log", "exp", "par", "cub", "squ")
COLORES_FUNDIDO = ("negro", "blanco")


class ErrorEdicion(ValueError):
    """Algo que la persona hizo no se puede; el mensaje se le muestra tal cual."""


def _r(t):
    return round(float(t), 6)


class Proyecto:
    def __init__(self):
        self.fuentes = {}
        self.pistas = []
        self.salida = {"formato": "original"}
        self._n = {"clip": 0, "grupo": 0, "fuente": 0, "efecto": 0, "sub": 0, "pal": 0}
        self.subtitulos = {"frases": [], "estilo": _sub.estilo_por_defecto(), "huella": "", "palabras": []}
        self._deshacer = []
        self._rehacer = []

    # ------------------------------------------------------------ historial

    def _estado(self):
        return {"pistas": copy.deepcopy(self.pistas), "n": dict(self._n), "salida": dict(self.salida), "subtitulos": copy.deepcopy(self.subtitulos)}

    def _restaurar(self, e):
        self.pistas = copy.deepcopy(e["pistas"])
        self._n = dict(e["n"])
        self.salida = dict(e["salida"])
        self.subtitulos = copy.deepcopy(e["subtitulos"])

    def _transaccion(self):
        return _Transaccion(self)

    def puede_deshacer(self):
        return bool(self._deshacer)

    def puede_rehacer(self):
        return bool(self._rehacer)

    def deshacer(self):
        if not self._deshacer:
            raise ErrorEdicion("No hay nada para deshacer.")
        self._rehacer.append(self._estado())
        self._restaurar(self._deshacer.pop())

    def rehacer(self):
        if not self._rehacer:
            raise ErrorEdicion("No hay nada para rehacer.")
        self._deshacer.append(self._estado())
        self._restaurar(self._rehacer.pop())

    # -------------------------------------------------------------- fuentes

    def agregar_fuente(self, ruta, tipo, duracion, tiempos=None, pistas_audio=0, **extra):
        """tipo: 'video' o 'audio'. tiempos: segundo de cada cuadro (solo video).
        pistas_audio: cuantas pistas de audio tiene el archivo."""
        if tipo not in ("video", "audio"):
            raise ErrorEdicion("Tipo de fuente desconocido.")
        if duracion <= 0:
            raise ErrorEdicion("El archivo no tiene duración.")
        self._n["fuente"] += 1
        fid = "s%d" % self._n["fuente"]
        self.fuentes[fid] = dict(extra, id=fid, ruta=ruta, tipo=tipo, duracion=_r(duracion),
                                 tiempos=list(tiempos) if tiempos else None, pistas_audio=int(pistas_audio))
        return fid

    def nuevo_desde_fuente(self, fid):
        """Arma el proyecto con una fuente entera: V1 (si es video) y A1 (si tiene audio), enlazados."""
        f = self.fuentes[fid]
        self.pistas = []
        self._deshacer, self._rehacer = [], []
        grupo = self._nuevo_grupo()
        if f["tipo"] == "video":
            self.pistas.append({"id": "V1", "tipo": "video", "nombre": "Video", "silenciada": False,
                                "clips": [self._clip(fid, 0.0, f["duracion"], 0.0, grupo)]})
        if f["pistas_audio"] > 0 or f["tipo"] == "audio":
            self.pistas.append({"id": "A1", "tipo": "audio", "nombre": "Audio", "silenciada": False,
                                "clips": [self._clip(fid, 0.0, f["duracion"], 0.0, grupo, pista_audio=0)]})

    # ---------------------------------------------------------------- ids

    def _nuevo_grupo(self):
        self._n["grupo"] += 1
        return "g%d" % self._n["grupo"]

    def _clip(self, fuente, desde, hasta, inicio, grupo, pista_audio=None):
        self._n["clip"] += 1
        c = {"id": "c%d" % self._n["clip"], "fuente": fuente, "desde": _r(desde), "hasta": _r(hasta),
             "inicio": _r(inicio), "grupo": grupo, "volumen": 1.0,
             "fade_in": 0.0, "fade_out": 0.0, "curva_in": "tri", "curva_out": "tri", "color_fundido": "negro",
             "efectos": [], "transicion": None,
             # tiempo: velocidad (1 = normal), si el audio mantiene el tono, interpolar cuadros en camara lenta, reversa
             "velocidad": 1.0, "mantener_tono": True, "interpolar": False, "reversa": False}
        if pista_audio is not None:
            c["pista_audio"] = int(pista_audio)
        return c

    # ------------------------------------------------------------ consultas

    @staticmethod
    def largo(c):
        """Lo que DURA en la linea de tiempo: el tramo de la fuente dividido por la velocidad."""
        return _r((c["hasta"] - c["desde"]) / c.get("velocidad", 1.0))

    @staticmethod
    def fin(c):
        return _r(c["inicio"] + (c["hasta"] - c["desde"]) / c.get("velocidad", 1.0))

    def duracion(self):
        return max((self.fin(c) for p in self.pistas for c in p["clips"]), default=0.0)

    def pista(self, pid):
        for p in self.pistas:
            if p["id"] == pid:
                return p
        raise ErrorEdicion("No existe la pista %s." % pid)

    def clip(self, cid):
        for p in self.pistas:
            for c in p["clips"]:
                if c["id"] == cid:
                    return p, c
        raise ErrorEdicion("Ese clip ya no existe.")

    def clips_del_grupo(self, grupo):
        return [(p, c) for p in self.pistas for c in p["clips"] if c["grupo"] == grupo]

    def clip_en(self, pid, t):
        """Clip de la pista pid que esta en pantalla en el segundo t de la linea de tiempo (None si hay un hueco).
        En el instante final exacto de la pista se devuelve el ultimo clip."""
        clips = self.pista(pid)["clips"]
        for c in clips:
            if c["inicio"] - TOL <= t < self.fin(c) - TOL:
                return c
        if clips and abs(t - self.fin(clips[-1])) < TOL:
            return clips[-1]
        return None

    def a_fuente(self, c, t):
        """Segundo de la FUENTE que corresponde al segundo t de la linea de tiempo, dentro del clip c."""
        v = c.get("velocidad", 1.0)
        if c.get("reversa"):
            return _r(c["hasta"] - (t - c["inicio"]) * v)
        return _r(c["desde"] + (t - c["inicio"]) * v)

    def a_linea(self, c, ts):
        """Segundo de la LINEA DE TIEMPO que corresponde al segundo ts de la fuente, dentro del clip c."""
        v = c.get("velocidad", 1.0)
        if c.get("reversa"):
            return _r(c["inicio"] + (c["hasta"] - ts) / v)
        return _r(c["inicio"] + (ts - c["desde"]) / v)

    def segmentos_video(self):
        """Lo que se ve, en orden: [{inicio, fin, fuente, desde, hasta, clip}]. Para reproducir saltando lo borrado."""
        out = []
        for p in self.pistas:
            if p["tipo"] == "video":
                for c in p["clips"]:
                    out.append({"inicio": c["inicio"], "fin": self.fin(c), "fuente": c["fuente"],
                                "desde": c["desde"], "hasta": c["hasta"], "clip": c["id"],
                                "velocidad": c.get("velocidad", 1.0), "reversa": bool(c.get("reversa"))})
        return sorted(out, key=lambda s: s["inicio"])

    # --------------------------------------------------- limites de cuadro

    def _limite_cuadro(self, fid, t):
        """Lleva t (segundos de la fuente) al limite de cuadro MAS CERCANO: el inicio de un cuadro o el final."""
        f = self.fuentes[fid]
        tiempos = f.get("tiempos")
        t = min(max(t, 0.0), f["duracion"])
        if not tiempos:
            return _r(t)
        i = bisect_left(tiempos, t)
        cand = [f["duracion"]]
        if i < len(tiempos):
            cand.append(tiempos[i])
        if i > 0:
            cand.append(tiempos[i - 1])
        return _r(min(cand, key=lambda c: abs(c - t)))

    def _video_en(self, t, grupo=None):
        for p in self.pistas:
            if p["tipo"] != "video":
                continue
            for c in p["clips"]:
                if (grupo is None or c["grupo"] == grupo) and c["inicio"] + TOL < t < self.fin(c) - TOL:
                    return c
        return None

    def ajustar(self, t, grupo=None):
        """El segundo de la linea de tiempo mas cercano a t que cae justo en un limite de cuadro."""
        t = _r(t)
        c = self._video_en(t, grupo)
        if c is None:
            # en el borde exacto de un clip de video ya es un limite de cuadro
            return t
        ts = self._limite_cuadro(c["fuente"], self.a_fuente(c, t))
        return self.a_linea(c, ts)

    # --------------------------------------------------------------- cortes

    def _partir(self, pista, c, t, mapa):
        # ajustar() ya llevo t a un limite de cuadro, pero ida y vuelta por la linea de tiempo (con velocidad) el segundo de la
        # fuente puede quedar 1e-7 corrido: se vuelve a llevar al limite EXACTO (validar() lo exige igual)
        corte = self._limite_cuadro(c["fuente"], self.a_fuente(c, t)) if self.fuentes[c["fuente"]].get("tiempos") else self.a_fuente(c, t)
        nuevo_g = mapa.setdefault(c["grupo"], self._nuevo_grupo())
        self._n["clip"] += 1
        der = dict(c, id="c%d" % self._n["clip"], inicio=_r(t), grupo=nuevo_g,
                   fade_in=0.0, efectos=self._copiar_efectos(c.get("efectos", [])), transicion=None)
        if c.get("reversa"):
            # al reves, lo que pasa PRIMERO en la linea de tiempo es el final de la fuente: la mitad izquierda se queda
            # con el tramo de adelante (corte..hasta) y la derecha con el de atras (desde..corte)
            der["hasta"] = corte
            c["desde"] = corte
        else:
            der["desde"] = corte
            c["hasta"] = corte
        c["fade_out"] = 0.0
        # Cada mitad es mas corta que el clip original: sus fundidos no pueden pasar de su largo nuevo.
        self._acotar_fundidos(c)
        self._acotar_fundidos(der)
        pista["clips"].insert(pista["clips"].index(c) + 1, der)

    def _copiar_efectos(self, lista):
        out = copy.deepcopy(lista)
        for e in out:
            e["id"] = self._nuevo_efecto_id()
        return out

    def _nuevo_efecto_id(self):
        self._n["efecto"] = self._n.get("efecto", 0) + 1
        return "e%d" % self._n["efecto"]

    def _acotar_fundidos(self, c):
        largo = self.largo(c)
        c["fade_in"] = _r(min(c["fade_in"], largo))
        c["fade_out"] = _r(min(c["fade_out"], max(0.0, largo - c["fade_in"])))

    def _dividir_en(self, t, grupo=None):
        """Parte en t todo clip que lo cruce. Devuelve True si partio algo."""
        t = self.ajustar(t, grupo)
        mapa, partio = {}, False
        for p in self.pistas:
            for c in list(p["clips"]):
                if grupo is not None and c["grupo"] != grupo:
                    continue
                if c["inicio"] + TOL < t < self.fin(c) - TOL:
                    self._partir(p, c, t, mapa)
                    partio = True
        return partio

    def dividir(self, t, grupo=None):
        """Corta en el segundo t (ajustado al cuadro mas cercano). Corta todas las pistas, o solo el grupo dado."""
        with self._transaccion():
            t = self.ajustar(t, grupo)
            if not (0 + TOL < t < self.duracion() - TOL):
                raise ErrorEdicion("Ahí no hay nada para cortar: está en el borde del video.")
            if not self._dividir_en(t, grupo):
                raise ErrorEdicion("Ahí ya hay un corte.")
            return t

    def borrar_rango(self, t0, t1):
        """Saca el tramo [t0, t1) de TODAS las pistas y cierra el hueco en todas a la vez."""
        with self._transaccion():
            a, b = sorted((float(t0), float(t1)))
            dur = self.duracion()
            a, b = max(a, 0.0), min(b, dur)
            a, b = self.ajustar(a), self.ajustar(b)
            if b - a < TOL:
                raise ErrorEdicion("Elegí un tramo con duración.")
            al_dia = bool(self.subtitulos["palabras"]) and self.subtitulos["huella"] == self.huella_linea()
            self._dividir_en(a)
            self._dividir_en(b)
            delta = _r(b - a)
            for p in self.pistas:
                restantes = []
                for c in p["clips"]:
                    if c["inicio"] >= a - TOL and self.fin(c) <= b + TOL:
                        continue                      # estaba adentro del tramo
                    if c["inicio"] >= b - TOL:
                        c["inicio"] = _r(c["inicio"] - delta)
                    restantes.append(c)
                p["clips"] = restantes
            self._podar_pistas()
            if al_dia:
                # las frases se transcribieron con palabras medidas y el montaje no habia cambiado: se corren con el corte y siguen al dia
                self._correr_palabras(a, b)
                self.subtitulos["huella"] = self.huella_linea()
            return {"desde": a, "hasta": b, "duracion": delta}

    def borrar_rangos(self, rangos):
        """Borra VARIOS tramos de una vez (por ejemplo, todos los silencios), cerrando cada hueco, en un solo paso de
        deshacer. Los tramos se dan en segundos de la linea de tiempo de ANTES de empezar; los que se tocan se unen y los
        que quedan en menos de un cuadro se saltean. Devuelve {"tramos", "duracion"} (lo realmente sacado)."""
        with self._transaccion():
            lista = []
            for r in rangos:
                a, b = sorted((float(r[0]), float(r[1])))
                lista.append((a, b))
            if not lista:
                raise ErrorEdicion("No hay tramos para borrar.")
            unidos = []
            for a, b in sorted(lista):
                if unidos and a <= unidos[-1][1] + TOL:
                    unidos[-1] = (unidos[-1][0], max(unidos[-1][1], b))
                else:
                    unidos.append((a, b))
            total, hechos = 0.0, 0
            # de atras para adelante: borrar uno no mueve los que vienen ANTES
            for a, b in reversed(unidos):
                dur = self.duracion()
                a2, b2 = self.ajustar(max(a, 0.0)), self.ajustar(min(b, dur))
                if b2 - a2 < TOL:
                    continue
                total += self.borrar_rango(a, b)["duracion"]
                hechos += 1
            if not hechos:
                raise ErrorEdicion("Esos tramos son más cortos que un cuadro: no hay nada para borrar.")
            return {"tramos": hechos, "duracion": _r(total)}

    def borrar_grupo(self, grupo):
        """Borra un clip con su audio y cierra el hueco."""
        clips = self.clips_del_grupo(grupo)
        if not clips:
            raise ErrorEdicion("Ese clip ya no existe.")
        c = clips[0][1]
        return self.borrar_rango(c["inicio"], self.fin(c))

    def recortar_a(self, t0, t1):
        """Se queda solo con [t0, t1) y borra el resto."""
        with self._transaccion():
            a, b = sorted((float(t0), float(t1)))
            dur = self.duracion()
            if b - a < TOL:
                raise ErrorEdicion("Elegí un tramo con duración.")
            if b < dur - TOL:
                self.borrar_rango(b, dur)
            if a > TOL:
                self.borrar_rango(0.0, a)

    # ------------------------------------------------------- fundidos, volumen

    def _largo_max(self, c):
        return self.largo(c)

    def fade(self, cid, lado, segundos, curva=None, color=None):
        """Fundido de entrada ('in') o de salida ('out') de un clip. 0 lo quita."""
        with self._transaccion():
            if lado not in ("in", "out"):
                raise ErrorEdicion("El fundido es de entrada o de salida.")
            pista_c, c = self.clip(cid)
            segundos = max(0.0, float(segundos))
            if segundos > 0.0:
                i = pista_c["clips"].index(c)
                sig = pista_c["clips"][i + 1] if i + 1 < len(pista_c["clips"]) else None
                if (lado == "in" and c.get("transicion")) or (lado == "out" and sig is not None and sig.get("transicion")
                                                              and abs(self.fin(c) - sig["inicio"]) < TOL):
                    raise ErrorEdicion("Ese borde tiene una transición: ya hace de fundido. Quitala si querés un fundido.")
            otro = c["fade_out"] if lado == "in" else c["fade_in"]
            if segundos + otro > self.largo(c) + TOL:
                segundos = max(0.0, self.largo(c) - otro)
            c["fade_" + lado] = _r(segundos)
            if curva:
                if curva not in CURVAS:
                    raise ErrorEdicion("Curva de fundido desconocida.")
                c["curva_" + lado] = curva
            if color:
                if color not in COLORES_FUNDIDO:
                    raise ErrorEdicion("El fundido es a negro o a blanco.")
                c["color_fundido"] = color
            return c["fade_" + lado]

    def fade_grupo(self, grupo, lado, segundos, curva=None, color=None):
        """El mismo fundido en el video y en su audio."""
        with self._transaccion():
            clips = self.clips_del_grupo(grupo)
            if not clips:
                raise ErrorEdicion("Ese clip ya no existe.")
            return [self.fade(c["id"], lado, segundos, curva, color) for _, c in clips][0]

    def volumen(self, cid, valor):
        with self._transaccion():
            p, c = self.clip(cid)
            if p["tipo"] != "audio":
                raise ErrorEdicion("El volumen es de los clips de audio.")
            valor = float(valor)
            if not 0.0 <= valor <= 4.0:
                raise ErrorEdicion("El volumen va de 0 a 400 %.")
            c["volumen"] = round(valor, 4)

    def silenciar(self, pid, si=True):
        with self._transaccion():
            p = self.pista(pid)
            if p["tipo"] != "audio":
                raise ErrorEdicion("Solo se silencian las pistas de audio.")
            p["silenciada"] = bool(si)

    def cambiar_pista_audio(self, cid, n):
        """Elegir cual de las pistas de audio del archivo suena (por si trae varias)."""
        with self._transaccion():
            p, c = self.clip(cid)
            if p["tipo"] != "audio":
                raise ErrorEdicion("Eso no es un clip de audio.")
            if not 0 <= int(n) < max(1, self.fuentes[c["fuente"]]["pistas_audio"]):
                raise ErrorEdicion("Ese archivo no tiene esa pista de audio.")
            c["pista_audio"] = int(n)

    # ------------------------------------------------------------- efectos

    def _clip_con_efectos(self, cid):
        p, c = self.clip(cid)
        c.setdefault("efectos", [])
        return p, c

    def _efecto(self, c, eid):
        for e in c["efectos"]:
            if e["id"] == eid:
                return e
        raise ErrorEdicion("Ese efecto ya no está.")

    def agregar_efecto(self, cid, tipo, params=None):
        """Agrega un efecto al final de la lista del clip. Un efecto de video solo va en un clip de video, y uno de
        audio en un clip de audio. Devuelve el id del efecto."""
        with self._transaccion():
            p, c = self._clip_con_efectos(cid)
            try:
                if _fx.categoria(tipo) != p["tipo"]:
                    raise ErrorEdicion("Un efecto de %s no se puede poner en un clip de %s."
                                       % (_fx.categoria(tipo), p["tipo"]))
                valores = _fx.limpiar_params(tipo, params or {}, comprobar_archivos=True)
            except _fx.ErrorEfecto as e:
                raise ErrorEdicion(str(e))
            e = {"id": self._nuevo_efecto_id(), "tipo": tipo, "activo": True, "params": valores}
            c["efectos"].append(e)
            return e["id"]

    def quitar_efecto(self, cid, eid):
        with self._transaccion():
            _, c = self._clip_con_efectos(cid)
            c["efectos"].remove(self._efecto(c, eid))

    def cambiar_efecto(self, cid, eid, params):
        """Cambia algunos valores de un efecto (un dict parcial: solo lo que cambia)."""
        with self._transaccion():
            _, c = self._clip_con_efectos(cid)
            e = self._efecto(c, eid)
            try:
                e["params"] = _fx.limpiar_params(e["tipo"], params, base=e["params"], comprobar_archivos=True)
            except _fx.ErrorEfecto as err:
                raise ErrorEdicion(str(err))

    def activar_efecto(self, cid, eid, si=True):
        """Prende o apaga un efecto sin perder sus valores."""
        with self._transaccion():
            _, c = self._clip_con_efectos(cid)
            self._efecto(c, eid)["activo"] = bool(si)

    def mover_efecto(self, cid, eid, desplazamiento):
        """Sube (-1) o baja (+1) un efecto en la lista: el orden cambia el resultado."""
        with self._transaccion():
            _, c = self._clip_con_efectos(cid)
            e = self._efecto(c, eid)
            i = c["efectos"].index(e)
            j = i + int(desplazamiento)
            if not 0 <= j < len(c["efectos"]):
                raise ErrorEdicion("Ya está en el extremo de la lista.")
            c["efectos"][i], c["efectos"][j] = c["efectos"][j], c["efectos"][i]

    # ------------------------------------------------------------ tiempo

    def _correr(self, desde_t, delta, excepto):
        """Corre `delta` segundos TODOS los clips (de todas las pistas) que empiezan en `desde_t` o despues, menos los de
        los grupos en `excepto`. Es lo que pasa en una linea de tiempo cuando un clip se hace mas largo o mas corto."""
        for p in self.pistas:
            for c in p["clips"]:
                if c["grupo"] not in excepto and c["inicio"] >= desde_t - TOL:
                    c["inicio"] = _r(max(0.0, c["inicio"] + delta))

    def _sin_pisarse(self):
        """Si despues de un cambio de tiempo dos clips de una misma pista se pisan, la operacion no se puede."""
        for p in self.pistas:
            p["clips"].sort(key=lambda x: x["inicio"])
            for a, b in zip(p["clips"], p["clips"][1:]):
                if b["inicio"] < self.fin(a) - TOL:
                    raise ErrorEdicion("Eso haría que dos clips de la pista %s se pisen (por ejemplo, la música): movelos antes." % p["id"])

    def velocidad(self, grupo, valor, mantener_tono=True, interpolar=False):
        """Cambia la velocidad de un clip y de su audio enlazado (0,25 a 4 veces). El clip dura mas o menos en la linea de
        tiempo y todo lo que viene despues se corre (en todas las pistas, para no perder la sincronia)."""
        with self._transaccion():
            valor = float(valor)
            lo, hi = VELOCIDAD
            if not lo - 1e-9 <= valor <= hi + 1e-9:
                raise ErrorEdicion("La velocidad va de %s a %s veces." % (str(lo).replace(".", ","), str(hi).replace(".", ",")))
            clips = self.clips_del_grupo(grupo)
            if not clips:
                raise ErrorEdicion("Ese clip ya no existe.")
            valor = _r(valor)
            fin_viejo = max(self.fin(c) for _, c in clips)
            largo_viejo = max(self.largo(c) for _, c in clips)
            for _, c in clips:
                c["velocidad"] = valor
                c["mantener_tono"] = bool(mantener_tono)
                c["interpolar"] = bool(interpolar)
            self._correr(fin_viejo, max(self.largo(c) for _, c in clips) - largo_viejo, {grupo})
            for _, c in clips:
                self._acotar_fundidos(c)
            self._sin_pisarse()
            return round(max(self.largo(c) for _, c in clips), 3)

    def reversa(self, grupo, si=True):
        """Pone o saca la reversa (el clip y su audio se reproducen de atras para adelante). No cambia lo que dura."""
        with self._transaccion():
            clips = self.clips_del_grupo(grupo)
            if not clips:
                raise ErrorEdicion("Ese clip ya no existe.")
            for pista, c in clips:
                i = pista["clips"].index(c)
                sig = pista["clips"][i + 1] if i + 1 < len(pista["clips"]) else None
                if si and (c.get("transicion") or (sig is not None and sig.get("transicion") and abs(self.fin(c) - sig["inicio"]) < TOL)):
                    raise ErrorEdicion("Un clip al revés no puede tener una transición en sus bordes: quitala primero.")
            for _, c in clips:
                c["reversa"] = bool(si)

    def repetir_grupo(self, grupo, veces):
        """Repite un clip (y su audio) `veces` veces seguidas: agrega las copias a continuacion y corre lo que sigue."""
        with self._transaccion():
            veces = int(veces)
            lo, hi = VECES_REPETIR
            if not lo <= veces <= hi:
                raise ErrorEdicion("Se puede repetir entre %d y %d veces." % (lo, hi))
            clips = self.clips_del_grupo(grupo)
            if not clips:
                raise ErrorEdicion("Ese clip ya no existe.")
            largo = max(self.largo(c) for _, c in clips)
            fin_viejo = max(self.fin(c) for _, c in clips)
            self._correr(fin_viejo, (veces - 1) * largo, {grupo})
            originales = [(p, c) for p, c in clips]
            for k in range(1, veces):
                nuevo_g = self._nuevo_grupo()
                for p, c in originales:
                    self._n["clip"] += 1
                    copia = dict(copy.deepcopy(c), id="c%d" % self._n["clip"], grupo=nuevo_g, inicio=_r(c["inicio"] + k * largo),
                                 transicion=None, efectos=self._copiar_efectos(c.get("efectos", [])))
                    if k < veces - 1:
                        copia["fade_out"] = 0.0          # un fundido de salida solo va al final de la ultima repeticion
                    copia["fade_in"] = 0.0               # y uno de entrada solo al principio de la primera
                    p["clips"].append(copia)
            for p, c in originales:
                if veces > 1:
                    c["fade_out"] = 0.0                  # la primera ya no es la ultima
            self._sin_pisarse()
            return {"veces": veces, "duracion": _r(veces * largo)}

    def ducking(self, pista_id, activo=True, reduccion=12):
        """En una pista de musica o locucion (no A1): que baje sola `reduccion` dB mientras suena el audio del video (A1)."""
        with self._transaccion():
            p = self.pista(pista_id)
            if p["tipo"] != "audio" or p["id"] == "A1":
                raise ErrorEdicion("Eso se pone en una pista de música o locución, no en el audio del video.")
            lo, hi = REDUCCION_DUCKING
            reduccion = float(reduccion)
            if not lo <= reduccion <= hi:
                raise ErrorEdicion("La música baja entre %d y %d dB." % (lo, hi))
            p["ducking"] = {"activo": bool(activo), "reduccion": int(round(reduccion))}

    # ------------------------------------------------------ varios videos

    def _fin_v1(self):
        v1 = next((p for p in self.pistas if p["id"] == "V1"), None)
        return max([self.fin(c) for c in v1["clips"]], default=0.0) if v1 else None

    def insertar_fuente(self, fid, t=None):
        """Pone un video del panel de medios en la linea de tiempo (con su audio, enlazado). Sin `t` (o con t al final) va despues del
        ultimo clip; en otro lugar, en el borde de clip MAS CERCANO, y todo lo que sigue se corre (en todas las pistas)."""
        f = self.fuentes.get(fid)
        if f is None:
            raise ErrorEdicion("Ese archivo no está en el proyecto.")
        if f["tipo"] != "video":
            raise ErrorEdicion("Un audio se pone con «Agregar audio».")
        if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or t != t or t < 0):
            raise ErrorEdicion("El lugar donde ponerlo no es válido.")
        with self._transaccion():
            fin_v = self._fin_v1()
            if fin_v is None:                                      # proyecto de solo audio: el video va despues de todo lo que hay (o en un borde)
                todos = {0.0, self.duracion()} | {c["inicio"] for p in self.pistas for c in p["clips"]}
                destino = self.duracion() if t is None else min(sorted(todos), key=lambda b: abs(b - t))
            elif t is None or t >= fin_v - TOL:
                destino = fin_v
            else:
                v1 = self.pista("V1")
                bordes = {0.0, fin_v} | {c["inicio"] for c in v1["clips"]}
                destino = min(sorted(bordes), key=lambda b: abs(b - t))
            dur = f["duracion"]
            if destino < (fin_v if fin_v is not None else self.duracion()) - TOL:
                self._correr(destino, dur, set())                  # se abre el lugar
            grupo = self._nuevo_grupo()
            if fin_v is None:
                self.pistas.insert(0, {"id": "V1", "tipo": "video", "nombre": "Video", "silenciada": False, "clips": []})
            cv = self._clip(fid, 0.0, dur, destino, grupo)
            self.pista("V1")["clips"].append(cv)
            self.pista("V1")["clips"].sort(key=lambda x: x["inicio"])
            if f["pistas_audio"] > 0:
                if not any(p["id"] == "A1" for p in self.pistas):
                    i = next(i for i, p in enumerate(self.pistas) if p["id"] == "V1") + 1
                    self.pistas.insert(i, {"id": "A1", "tipo": "audio", "nombre": "Audio", "silenciada": False, "clips": []})
                ca = self._clip(fid, 0.0, dur, destino, grupo, pista_audio=0)
                self.pista("A1")["clips"].append(ca)
                self.pista("A1")["clips"].sort(key=lambda x: x["inicio"])
            self._sin_pisarse()
            return {"clip": cv["id"], "grupo": grupo, "inicio": _r(destino), "fin": self.fin(cv)}

    def mover_grupo(self, grupo, t):
        """Cambia de lugar un clip de video (con su audio) a otro borde de clip: el hueco que deja se cierra y se abre uno donde cae."""
        clips = self.clips_del_grupo(grupo)
        if not clips:
            raise ErrorEdicion("Ese clip ya no existe.")
        if not any(p["id"] == "V1" for p, _ in clips):
            raise ErrorEdicion("Solo se pueden reordenar los clips de video.")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or t != t:
            raise ErrorEdicion("El lugar donde ponerlo no es válido.")
        with self._transaccion():
            base = next(c for p, c in clips if p["id"] == "V1")
            a, dur = base["inicio"], self.largo(base)
            for p, c in clips:
                p["clips"].remove(c)
            self._correr(a, -dur, set())                          # se cierra el hueco
            t = float(t) - (dur if t > a else 0.0)                # el destino se medía con el clip todavia adentro
            v1 = self.pista("V1")
            bordes = {0.0, max([self.fin(c) for c in v1["clips"]], default=0.0)} | {c["inicio"] for c in v1["clips"]}
            destino = min(sorted(bordes), key=lambda b: abs(b - t))
            if abs(destino - a) < TOL:
                raise ErrorEdicion("Ya está en ese lugar.")
            self._correr(destino, dur, set())                     # se abre el lugar
            for p, c in clips:
                c["inicio"] = _r(destino)
                p["clips"].append(c)
                p["clips"].sort(key=lambda x: x["inicio"])
            self._sin_pisarse()
            return _r(destino)

    def recortar_borde(self, grupo, lado, t):
        """Tira del borde de un clip (y del de su audio enlazado) hasta el segundo `t` de la linea de tiempo.

        lado: 'inicio' o 'fin'. Acortar saca material de ese borde; alargar usa material que SOBRA de la fuente (hasta donde alcance).
        - Un clip del bloque principal (video y su audio): el clip empieza donde empezaba y lo que sigue se corre (en todas las pistas,
          como al borrar un tramo): no quedan huecos ni se pisan clips.
        - Un audio suelto (musica, locucion, audio separado): el resto no se mueve; si se tira del inicio, el clip empieza mas tarde
          (o antes) y el sonido queda en el mismo lugar.
        El borde cae en un limite de cuadro. Devuelve {"inicio", "fin", "cambio"} (segundos que cambio el largo del clip)."""
        if lado not in ("inicio", "fin"):
            raise ErrorEdicion("El borde es el inicio o el final del clip.")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
            raise ErrorEdicion("El lugar donde poner el borde no es válido.")
        clips = self.clips_del_grupo(grupo)
        if not clips:
            raise ErrorEdicion("Ese clip ya no existe.")
        with self._transaccion():
            pista0, base = next(((p, c) for p, c in clips if p["tipo"] == "video"), clips[0])
            principal = len(clips) > 1 or pista0["id"] == "V1"
            f = self.fuentes[base["fuente"]]
            v = base.get("velocidad", 1.0)
            rev = bool(base.get("reversa"))
            a, b = base["inicio"], self.fin(base)
            dt = float(t) - (b if lado == "fin" else a)
            # que borde de la FUENTE se mueve, y para que lado: sin reversa el final de la fuente es el final del clip; al reves, el inicio
            if not rev:
                campo, signo = ("hasta", 1) if lado == "fin" else ("desde", 1)
            else:
                campo, signo = ("desde", -1) if lado == "fin" else ("hasta", -1)
            bruto = base[campo] + signo * dt * v
            if pista0["tipo"] == "video" and f.get("tiempos"):
                nuevo = self._limite_cuadro(base["fuente"], bruto)
            else:
                nuevo = _r(min(max(bruto, 0.0), f["duracion"]))
            if abs(nuevo - base[campo]) < TOL:
                raise ErrorEdicion("El borde ya está ahí (o no hay más material para estirarlo).")
            d, h = (nuevo, base["hasta"]) if campo == "desde" else (base["desde"], nuevo)
            if d < -TOL or h > f["duracion"] + TOL:
                raise ErrorEdicion("No sobra más material de ese lado.")
            if (h - d) / v < 0.05:
                raise ErrorEdicion("El clip quedaría casi sin duración: para sacarlo usá «Borrar».")
            largo_viejo = self.largo(base)
            corrimiento = signo * (nuevo - base[campo]) / v          # lo que se movio el borde en la linea de tiempo (hacia adelante, +)
            for _, c in clips:
                c[campo] = nuevo
            if principal:
                self._correr(b, self.largo(base) - largo_viejo, {grupo})
            elif lado == "inicio":
                _, c = clips[0]
                c["inicio"] = _r(a + corrimiento)
                if c["inicio"] < -TOL:
                    raise ErrorEdicion("No se puede empezar antes del principio.")
            for _, c in clips:
                self._acotar_fundidos(c)
            self._sin_pisarse()
            return {"inicio": base["inicio"], "fin": self.fin(base), "cambio": _r(self.largo(base) - largo_viejo)}

    def quitar_fuente(self, fid):
        """Saca un archivo del panel de medios. Solo si ningun clip lo usa."""
        if fid not in self.fuentes:
            raise ErrorEdicion("Ese archivo ya no está en el proyecto.")
        if any(c["fuente"] == fid for p in self.pistas for c in p["clips"]):
            raise ErrorEdicion("Ese archivo se usa en la línea de tiempo: borrá sus clips antes de sacarlo.")
        del self.fuentes[fid]                                      # no es una edicion de la linea de tiempo: no entra al historial

    # ----------------------------------------------------------- subtitulos

    def huella_linea(self):
        """Una firma de COMO esta armada la linea de tiempo (que clip, de donde a donde, a que velocidad y donde empieza).
        Si cambia despues de transcribir, las frases pueden haber quedado corridas."""
        datos = []
        for pista in self.pistas:
            tramos = []
            for c in pista["clips"]:
                t = [c["fuente"], round(c["desde"], 4), round(c["hasta"], 4), round(c["inicio"], 4), c.get("velocidad", 1.0), bool(c.get("reversa"))]
                previo = tramos[-1] if tramos else None
                # dos clips que siguen uno del otro (misma fuente, misma velocidad, sin hueco) son el mismo montaje que uno solo: cortar no lo cambia
                if (previo and not t[5] and not previo[5] and previo[0] == t[0] and previo[4] == t[4]
                        and abs(previo[2] - t[1]) < 2e-4 and abs(previo[3] + (previo[2] - previo[1]) / previo[4] - t[3]) < 2e-4):
                    previo[2] = t[2]
                else:
                    tramos.append(t)
            datos.append([pista["id"], tramos])
        return hashlib.md5(json.dumps(datos).encode("utf-8")).hexdigest()[:12]

    def subtitulos_desactualizados(self):
        return bool(self.subtitulos["frases"]) and self.subtitulos["huella"] != self.huella_linea()

    def _frase_id(self):
        self._n["sub"] += 1
        return "s%d" % self._n["sub"]

    def _frase(self, inicio, fin, texto):
        try:
            a, b, x = _sub.limpiar_frase(inicio, fin, texto, self.duracion())
        except _sub.ErrorSubtitulo as e:
            raise ErrorEdicion(str(e))
        b = min(b, round(self.duracion(), 3))
        if b - a < 0.1:
            raise ErrorEdicion("La frase queda fuera del video (o dura menos de una décima).")
        return {"id": self._frase_id(), "inicio": a, "fin": b, "texto": x}

    def _ordenar_frases(self):
        self.subtitulos["frases"].sort(key=lambda f: (f["inicio"], f["fin"]))

    def _palabras_limpias(self, palabras):
        """Valida las palabras medidas de una transcripcion y las devuelve con su id."""
        if not isinstance(palabras, list) or len(palabras) > _sub.PALABRAS_MAX:
            raise ErrorEdicion("Las palabras tienen que ser una lista de hasta %d." % _sub.PALABRAS_MAX)
        dur = round(self.duracion(), 3)
        out, ultimo = [], -1.0
        for w in palabras:
            if not isinstance(w, dict):
                raise ErrorEdicion("Cada palabra tiene texto, inicio y final.")
            t = w.get("texto")
            if not isinstance(t, str) or not t.strip() or len(t.strip()) > _sub.PALABRA_MAX_LETRAS or "\x00" in t or len(t.split()) != 1:
                raise ErrorEdicion("Cada palabra es un texto de hasta %d letras, sin espacios." % _sub.PALABRA_MAX_LETRAS)
            tiempos = []
            for k in ("inicio", "fin", "voz", "habla"):
                v = w.get(k, w.get("inicio") if k == "voz" else (w.get("fin") if k == "habla" else None))
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise ErrorEdicion("El tiempo de una palabra tiene que ser un número.")
                tiempos.append(round(float(v), 3))
            ini, fin, voz, habla = tiempos
            if ini < 0 or fin < ini or ini < ultimo - 1e-6 or ini > dur + 1e-3:
                raise ErrorEdicion("Los tiempos de las palabras tienen que ir en orden y dentro del video.")
            fin = min(fin, dur)
            voz, habla = min(max(voz, ini), fin), min(max(habla, ini), fin)
            ultimo = ini
            self._n["pal"] += 1
            out.append({"id": "w%d" % self._n["pal"], "texto": t.strip(), "inicio": ini, "fin": fin, "voz": voz, "habla": habla})
        return out

    def subtitulos_poner(self, frases, palabras=None):
        """Reemplaza TODAS las frases (lo que devuelve la transcripcion). Cada una: {inicio, fin, texto} y, si la transcripcion midio las
        palabras, `palabras` con los indices de las suyas dentro de `palabras` ([{texto, inicio, fin, voz, habla}]): eso permite
        editar por texto y resaltar la palabra que se dice."""
        if not isinstance(frases, list) or len(frases) > _sub.FRASES_MAX:
            raise ErrorEdicion("Las frases tienen que ser una lista de hasta %d." % _sub.FRASES_MAX)
        with self._transaccion():
            pals = self._palabras_limpias(palabras) if palabras else []
            nuevas = []
            for f in frases:
                if not isinstance(f, dict):
                    raise ErrorEdicion("Cada frase tiene inicio, final y texto.")
                nf = self._frase(f.get("inicio"), f.get("fin"), f.get("texto"))
                idx = f.get("palabras")
                if idx:
                    if (not isinstance(idx, list) or any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(pals) for i in idx)
                            or idx != sorted(set(idx))):
                        raise ErrorEdicion("Las palabras de una frase no son válidas.")
                    nf["palabras"] = [pals[i]["id"] for i in idx]
                nuevas.append(nf)
            self.subtitulos["frases"] = nuevas
            self.subtitulos["palabras"] = pals
            self._ordenar_frases()
            self.subtitulos["huella"] = self.huella_linea()
            return len(nuevas)

    def _correr_palabras(self, a, b):
        """El tramo [a, b] de la linea de tiempo ya se sacó: las palabras y las frases se corren con el corte. Una palabra cuyo centro caía
        adentro del tramo se va (se mira el medio de lo que suena, no el de sus pausas); las demás se acortan o se corren. Una frase con palabras medidas se rearma con las que le quedan."""
        sub = self.subtitulos
        delta = b - a

        def mapa(t):
            return t if t <= a else (a if t < b else t - delta)

        quitadas, quedan = set(), []
        for w in sub["palabras"]:
            if a <= (w.get("voz", w["inicio"]) + w.get("habla", w["fin"])) / 2.0 < b:       # el centro de lo que SUENA de la palabra
                quitadas.add(w["id"])
                continue
            w2 = dict(w)
            for k in ("inicio", "fin", "voz", "habla"):
                w2[k] = round(mapa(w[k]), 3)
            quedan.append(w2)
        por_id = {w["id"]: w for w in quedan}
        frases = []
        for f in sub["frases"]:
            g = dict(f)
            if f.get("palabras"):
                ids = [i for i in f["palabras"] if i in por_id]
                if not ids:
                    continue
                g["palabras"] = ids
                if len(ids) != len(f["palabras"]):
                    g["texto"] = " ".join(por_id[i]["texto"] for i in ids)
                    g["inicio"], g["fin"] = por_id[ids[0]]["inicio"], por_id[ids[-1]]["fin"]
                else:
                    g["inicio"], g["fin"] = round(mapa(f["inicio"]), 3), round(mapa(f["fin"]), 3)
            else:
                g["inicio"], g["fin"] = round(mapa(f["inicio"]), 3), round(mapa(f["fin"]), 3)
            if g["fin"] - g["inicio"] < 0.1:
                g["fin"] = round(g["inicio"] + 0.1, 3)
                if g["fin"] > round(self.duracion(), 3) + 1e-6:
                    continue
            frases.append(g)
        sub["palabras"], sub["frases"] = quedan, frases
        self._ordenar_frases()

    def palabras_borrar(self, ids):
        """Edicion por texto: saca del montaje las palabras elegidas (el video, el audio y todas las pistas, cerrando el hueco, en un solo
        paso del historial). Cada palabra va de un corte al siguiente: sale con la mitad de la pausa de cada lado, así lo que queda suena natural."""
        if not isinstance(ids, list) or not ids or len(ids) > _sub.PALABRAS_MAX or not all(isinstance(i, str) for i in ids):
            raise ErrorEdicion("Elegí las palabras que querés sacar.")
        with self._transaccion():
            por_id = {w["id"]: w for w in self.subtitulos["palabras"]}
            if any(i not in por_id for i in ids):
                raise ErrorEdicion("Alguna de esas palabras ya no existe.")
            if self.subtitulos_desactualizados():
                raise ErrorEdicion("El video cambió después de transcribir: los tiempos de las palabras ya no coinciden. Volvé a transcribir.")
            rangos = sorted((por_id[i]["inicio"], por_id[i]["fin"]) for i in set(ids))
            r = self.borrar_rangos(rangos)
            return {"palabras": len(set(ids)), "tramos": r["tramos"], "duracion": r["duracion"]}

    def pausas(self, minimo=0.0):
        """Las pausas entre palabras: [{palabra, inicio, fin}] donde `inicio` es cuando deja de sonar la palabra y `fin` cuando empieza la siguiente.
        `minimo`: solo las que duran al menos eso (segundos)."""
        ws = self.subtitulos["palabras"]
        out = []
        for i in range(len(ws) - 1):
            a, b = ws[i]["habla"], ws[i + 1]["voz"]
            if b - a >= minimo - 1e-9 and b - a > 0.0:
                out.append({"palabra": ws[i]["id"], "inicio": a, "fin": b})
        return out

    def palabras_acortar_pausas(self, minimo=0.8, dejar=0.3, ids=None):
        """Acorta las pausas de al menos `minimo` segundos hasta que queden en `dejar` segundos (la mitad a cada lado del corte). Con `ids`,
        solo las que siguen a esas palabras. En un solo paso del historial."""
        for nombre, v, lo, hi in (("La pausa mínima", minimo, 0.2, 30.0), ("La pausa que queda", dejar, 0.0, 5.0)):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
                raise ErrorEdicion("%s va de %s a %s segundos." % (nombre, lo, hi))
        if dejar >= minimo:
            raise ErrorEdicion("La pausa que queda tiene que ser más corta que la mínima.")
        if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)):
            raise ErrorEdicion("Esas palabras no son válidas.")
        with self._transaccion():
            if self.subtitulos_desactualizados():
                raise ErrorEdicion("El video cambió después de transcribir: los tiempos de las palabras ya no coinciden. Volvé a transcribir.")
            rangos = [(x["inicio"] + dejar / 2.0, x["fin"] - dejar / 2.0) for x in self.pausas(minimo) if ids is None or x["palabra"] in ids]
            if not rangos:
                raise ErrorEdicion("No hay pausas de %s segundos o más." % str(minimo).replace(".", ","))
            r = self.borrar_rangos(rangos)
            return {"pausas": r["tramos"], "duracion": r["duracion"]}

    def palabra_cambiar(self, wid, texto):
        """Corrige el texto de UNA palabra transcripta (sin cambiarle el tiempo). La frase que la tiene se rearma con el texto nuevo."""
        if not isinstance(texto, str):
            raise ErrorEdicion("La palabra tiene que ser un texto.")
        texto = texto.strip()
        if not texto or len(texto.split()) != 1 or len(texto) > _sub.PALABRA_MAX_LETRAS or "\x00" in texto:
            raise ErrorEdicion("Una palabra son hasta %d letras, sin espacios." % _sub.PALABRA_MAX_LETRAS)
        with self._transaccion():
            w = next((x for x in self.subtitulos["palabras"] if x["id"] == wid), None)
            if w is None:
                raise ErrorEdicion("Esa palabra ya no existe.")
            w["texto"] = texto
            por_id = {x["id"]: x for x in self.subtitulos["palabras"]}
            for f in self.subtitulos["frases"]:
                if wid in (f.get("palabras") or []):
                    f["texto"] = " ".join(por_id[i]["texto"] for i in f["palabras"])[: _sub.TEXTO_MAX]

    def subtitulo_agregar(self, inicio, fin, texto):
        with self._transaccion():
            if len(self.subtitulos["frases"]) >= _sub.FRASES_MAX:
                raise ErrorEdicion("Hay demasiadas frases (el máximo es %d)." % _sub.FRASES_MAX)
            f = self._frase(inicio, fin, texto)
            self.subtitulos["frases"].append(f)
            self._ordenar_frases()
            if not self.subtitulos["huella"]:
                self.subtitulos["huella"] = self.huella_linea()
            return f["id"]

    def subtitulo_cambiar(self, sid, campos):
        """campos: cualquiera de inicio, fin, texto."""
        if not isinstance(campos, dict) or not campos or any(k not in ("inicio", "fin", "texto") for k in campos):
            raise ErrorEdicion("Se puede cambiar el inicio, el final o el texto.")
        with self._transaccion():
            f = next((x for x in self.subtitulos["frases"] if x["id"] == sid), None)
            if f is None:
                raise ErrorEdicion("Esa frase ya no existe.")
            n = self._frase(campos.get("inicio", f["inicio"]), campos.get("fin", f["fin"]), campos.get("texto", f["texto"]))
            if n["texto"].split() != f["texto"].split():
                f.pop("palabras", None)               # le cambiaron el texto a mano: ya no coincide con las palabras medidas
            f["inicio"], f["fin"], f["texto"] = n["inicio"], n["fin"], n["texto"]
            self._ordenar_frases()

    def subtitulo_quitar(self, sid):
        with self._transaccion():
            antes = len(self.subtitulos["frases"])
            self.subtitulos["frases"] = [x for x in self.subtitulos["frases"] if x["id"] != sid]
            if len(self.subtitulos["frases"]) == antes:
                raise ErrorEdicion("Esa frase ya no existe.")

    def subtitulos_borrar(self):
        with self._transaccion():
            self.subtitulos["frases"] = []
            self.subtitulos["palabras"] = []
            self.subtitulos["huella"] = ""

    def subtitulos_estilo(self, params):
        with self._transaccion():
            try:
                self.subtitulos["estilo"] = _sub.limpiar_estilo(params, self.subtitulos["estilo"])
            except _sub.ErrorSubtitulo as e:
                raise ErrorEdicion(str(e))

    def subtitulos_al_dia(self):
        """La persona confirma que las frases estan bien aunque el montaje haya cambiado."""
        with self._transaccion():
            self.subtitulos["huella"] = self.huella_linea()

    def dividir_varios(self, tiempos):
        """Corta en todos los segundos dados (por ejemplo, en los cambios de escena), en UN solo paso del historial."""
        if not isinstance(tiempos, list) or not tiempos or len(tiempos) > 2000 or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in tiempos):
            raise ErrorEdicion("Los cortes tienen que ser una lista de segundos.")
        with self._transaccion():
            hechos = 0
            for x in sorted(set(round(float(v), 3) for v in tiempos)):
                if not (0 + TOL < x < self.duracion() - TOL):
                    continue
                if self._dividir_en(x, None):
                    hechos += 1
            if not hechos:
                raise ErrorEdicion("En esos lugares no había nada para cortar.")
            return hechos

    # ---------------------------------------------------------- transiciones

    def _vecinos(self, pista, i):
        """(clip anterior pegado al i, o None)."""
        if i <= 0:
            return None
        a, c = pista["clips"][i - 1], pista["clips"][i]
        return a if abs(self.fin(a) - c["inicio"]) < TOL else None

    def _limite_transicion(self, pista, i):
        """Duracion maxima de la transicion de entrada del clip i de la pista (0 si no se puede), SIN contar la que ya tenga.
        Esta centrada en el corte: usa la mitad de la duracion de imagen/sonido que SOBRA a cada lado (fuera del tramo usado)
        y esa mitad tambien tiene que caber dentro de cada clip, junto con la mitad de las otras transiciones del clip."""
        a = self._vecinos(pista, i)
        if a is None:
            return 0.0
        c = pista["clips"][i]
        if a.get("reversa") or c.get("reversa"):
            return 0.0                              # una transicion sobre material al reves no tiene sentido (y confunde los bordes)
        sobra_a = (self.fuentes[a["fuente"]]["duracion"] - a["hasta"]) / a.get("velocidad", 1.0)
        sobra_b = c["desde"] / c.get("velocidad", 1.0)
        previa_a = (a.get("transicion") or {}).get("duracion", 0.0) / 2 if i - 1 > 0 else 0.0       # su propia entrada
        sig = pista["clips"][i + 1] if i + 1 < len(pista["clips"]) else None
        salida_c = ((sig.get("transicion") or {}).get("duracion", 0.0) / 2
                    if sig is not None and abs(self.fin(c) - sig["inicio"]) < TOL else 0.0)
        mitad = min(sobra_a, sobra_b, self.largo(a) - previa_a, self.largo(c) - salida_c)
        return max(0.0, min(DURACION_TRANSICION_MAX, _r(2 * mitad - 1e-6)))

    def transicion_maxima(self, cid):
        """Lo que la interfaz necesita saber para ofrecer (o no) una transicion en la entrada de este clip."""
        p, c = self.clip(cid)
        return round(self._limite_transicion(p, p["clips"].index(c)), 3)

    def poner_transicion(self, grupo, tipo, duracion):
        """Pone (o cambia) la transicion de ENTRADA de un clip (y de su audio enlazado) desde el clip pegado que le precede.
        No cambia la duracion del proyecto. Los fundidos de los dos bordes que se unen se sacan (la transicion ya los reemplaza)."""
        with self._transaccion():
            if tipo not in _fx.TRANSICIONES:
                raise ErrorEdicion("Esa transición no existe.")
            duracion = float(duracion)
            lo, hi = _fx.DURACION_TRANSICION
            if not lo <= duracion <= hi:
                raise ErrorEdicion("La transición dura entre %s y %s s." % (str(lo).replace(".", ","), str(hi).replace(".", ",")))
            clips = self.clips_del_grupo(grupo)
            if not clips:
                raise ErrorEdicion("Ese clip ya no existe.")
            puesta, maximo = False, 0.0
            for pista, c in clips:
                i = pista["clips"].index(c)
                tope = self._limite_transicion(pista, i)
                maximo = max(maximo, tope)
                if tope <= 0.0:
                    continue
                if duracion > tope + 1e-6:
                    raise ErrorEdicion("Ahí solo entra una transición de hasta %s s: no sobra más imagen o sonido a los lados del corte."
                                       % str(round(tope, 1)).replace(".", ","))
                a = self._vecinos(pista, i)
                c["transicion"] = {"tipo": tipo, "duracion": _r(duracion)}
                c["fade_in"] = 0.0
                a["fade_out"] = 0.0
                puesta = True
            if not puesta:
                raise ErrorEdicion("Para una transición hace falta otro clip pegado antes y que sobre imagen o sonido a los lados del corte.")

    def quitar_transicion(self, grupo):
        with self._transaccion():
            clips = self.clips_del_grupo(grupo)
            if not clips:
                raise ErrorEdicion("Ese clip ya no existe.")
            if not any(c.get("transicion") for _, c in clips):
                raise ErrorEdicion("Ese clip no tiene transición de entrada.")
            for _, c in clips:
                c["transicion"] = None

    def _normalizar_transiciones(self):
        """Saca las transiciones que dejaron de tener sentido (se borro el clip anterior, ya no estan pegados, o no sobra
        material). Se llama al terminar cada operacion, dentro de su mismo paso de deshacer."""
        for pista in self.pistas:
            for i, c in enumerate(pista["clips"]):
                t = c.get("transicion")
                if t and (self._vecinos(pista, i) is None or t["duracion"] > self._limite_transicion(pista, i) + 1e-4):
                    c["transicion"] = None

    def _podar_pistas(self):
        """Una pista de audio EXTRA que se quedo sin clips desaparece (V1 y A1 son fijas). Deshacer la devuelve."""
        self.pistas = [p for p in self.pistas if p["clips"] or p["id"] in ("V1", "A1")]

    # ---------------------------------------------------------- audio extra

    def agregar_audio(self, fid, inicio=0.0, desde=0.0, hasta=None):
        """Pone un audio (otro archivo, o las pistas de uno) en la linea de tiempo, en una pista extra."""
        with self._transaccion():
            f = self.fuentes[fid]
            if f["pistas_audio"] < 1 and f["tipo"] != "audio":
                raise ErrorEdicion("Ese archivo no tiene audio.")
            hasta = f["duracion"] if hasta is None else min(float(hasta), f["duracion"])
            desde = max(0.0, float(desde))
            if hasta - desde < TOL:
                raise ErrorEdicion("Ese tramo de audio no tiene duración.")
            inicio = max(0.0, float(inicio))
            fin = inicio + (hasta - desde)
            destino = None
            for p in self.pistas:
                if p["tipo"] == "audio" and p["id"] != "A1" and not any(
                        c["inicio"] < fin - TOL and inicio < self.fin(c) - TOL for c in p["clips"]):
                    destino = p
                    break
            if destino is None:
                usados = {p["id"] for p in self.pistas}
                n = 2
                while "A%d" % n in usados:
                    n += 1
                destino = {"id": "A%d" % n, "tipo": "audio", "nombre": "Audio %d" % n, "silenciada": False, "clips": []}
                self.pistas.append(destino)
            c = self._clip(fid, desde, hasta, inicio, self._nuevo_grupo(), pista_audio=0)
            destino["clips"].append(c)
            destino["clips"].sort(key=lambda x: x["inicio"])
            return c["id"]

    def mover_clip(self, cid, inicio):
        """Mueve un audio extra (solo los que no estan enlazados a video)."""
        with self._transaccion():
            p, c = self.clip(cid)
            if p["tipo"] != "audio" or len(self.clips_del_grupo(c["grupo"])) > 1:
                raise ErrorEdicion("Ese clip está enlazado al video: cortalo o borralo con el video.")
            inicio = max(0.0, float(inicio))
            fin = inicio + self.largo(c)
            for o in p["clips"]:
                if o is not c and o["inicio"] < fin - TOL and inicio < self.fin(o) - TOL:
                    raise ErrorEdicion("Se superpone con otro audio de la misma pista.")
            c["inicio"] = _r(inicio)
            p["clips"].sort(key=lambda x: x["inicio"])

    def eliminar_clip(self, cid):
        """Saca un audio extra SIN cerrar el hueco (no mueve nada mas)."""
        with self._transaccion():
            p, c = self.clip(cid)
            if p["tipo"] != "audio" or len(self.clips_del_grupo(c["grupo"])) > 1:
                raise ErrorEdicion("Ese clip está enlazado al video: borralo con el video.")
            p["clips"].remove(c)
            self._podar_pistas()

    def desenlazar(self, grupo):
        with self._transaccion():
            clips = self.clips_del_grupo(grupo)
            if len(clips) < 2:
                raise ErrorEdicion("Ese clip no está enlazado a nada.")
            for _, c in clips[1:]:
                c["grupo"] = self._nuevo_grupo()

    # ----------------------------------------------------------- validacion

    def validar(self):
        """Lista de problemas (vacia si todo esta bien). Las pruebas la llaman despues de cada operacion."""
        malos = []

        def numero(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

        # Primero los tipos: un proyecto guardado puede venir dañado (o armado a proposito) con NaN, textos donde va un numero o valores
        # absurdos; las comparaciones de abajo los dejarian pasar (toda comparacion con NaN da falso).
        for fid, f in self.fuentes.items():
            if (not isinstance(f, dict) or f.get("tipo") not in ("video", "audio") or not isinstance(f.get("ruta"), str)
                    or not numero(f.get("duracion")) or not 0 <= f["duracion"] <= 1e6):
                malos.append("fuente %s: datos invalidos" % fid)
        for p in self.pistas:
            if not isinstance(p, dict) or p.get("tipo") not in ("video", "audio") or not isinstance(p.get("clips"), list):
                malos.append("pista invalida")
                continue
            for c in p["clips"]:
                if not isinstance(c, dict) or not isinstance(c.get("id"), str):
                    malos.append("clip invalido")
                    continue
                for campo in ("inicio", "desde", "hasta", "fade_in", "fade_out", "volumen"):
                    if not numero(c.get(campo)):
                        malos.append("%s: «%s» no es un numero" % (c["id"], campo))
                if numero(c.get("volumen")) and not 0.0 <= c["volumen"] <= 4.0:
                    malos.append("%s: volumen fuera de rango" % c["id"])
                if numero(c.get("fade_in")) and numero(c.get("fade_out")) and (c["fade_in"] < 0 or c["fade_out"] < 0):
                    malos.append("%s: fundido negativo" % c["id"])
                if "pista_audio" in c and (isinstance(c["pista_audio"], bool) or not isinstance(c["pista_audio"], int) or not 0 <= c["pista_audio"] < 64):
                    malos.append("%s: pista de audio invalida" % c["id"])
        if malos:
            return malos
        ids = set()
        ids_pista = [p["id"] for p in self.pistas]
        if len(ids_pista) != len(set(ids_pista)):
            malos.append("ids de pista repetidos: %s" % ids_pista)
        for p in self.pistas:
            previo = None
            for c in p["clips"]:
                if c["id"] in ids:
                    malos.append("id repetido %s" % c["id"])
                ids.add(c["id"])
                f = self.fuentes.get(c["fuente"])
                if f is None:
                    malos.append("%s: fuente inexistente" % c["id"])
                    continue
                if c["hasta"] - c["desde"] < TOL:
                    malos.append("%s: clip sin duracion" % c["id"])
                v = c.get("velocidad", 1.0)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not VELOCIDAD[0] - 1e-6 <= v <= VELOCIDAD[1] + 1e-6:
                    malos.append("%s: velocidad fuera de rango (%s)" % (c["id"], v))
                if c.get("reversa") and c.get("transicion"):
                    malos.append("%s: un clip al reves con transicion" % c["id"])
                if c["desde"] < -TOL or c["hasta"] > f["duracion"] + TOL:
                    malos.append("%s: se sale de la fuente (%s-%s de %s)" % (c["id"], c["desde"], c["hasta"], f["duracion"]))
                if c["inicio"] < -TOL:
                    malos.append("%s: empieza antes de cero" % c["id"])
                if previo is not None and c["inicio"] < self.fin(previo) - TOL:
                    malos.append("%s: se superpone con %s" % (c["id"], previo["id"]))
                if c["fade_in"] + c["fade_out"] > self.largo(c) + TOL:
                    malos.append("%s: los fundidos pasan del largo del clip" % c["id"])
                if p["tipo"] == "video" and f["tipo"] == "video" and f.get("tiempos"):
                    for borde in (c["desde"], c["hasta"]):
                        if self._limite_cuadro(c["fuente"], borde) != _r(borde):
                            malos.append("%s: el borde %s no cae en un limite de cuadro" % (c["id"], borde))
                previo = c
        ids_efecto = set()
        for p in self.pistas:
            for c in p["clips"]:
                for e in c.get("efectos", []):
                    if e["id"] in ids_efecto:
                        malos.append("id de efecto repetido %s" % e["id"])
                    ids_efecto.add(e["id"])
                    try:
                        if _fx.categoria(e["tipo"]) != p["tipo"]:
                            malos.append("%s: el efecto %s no es de %s" % (c["id"], e["tipo"], p["tipo"]))
                        _fx.limpiar_params(e["tipo"], e["params"], base=_fx.defectos(e["tipo"]))
                    except _fx.ErrorEfecto as err:
                        malos.append("%s: efecto %s invalido (%s)" % (c["id"], e.get("tipo"), err))
        for p in self.pistas:
            for i, c in enumerate(p["clips"]):
                t = c.get("transicion")
                if not t:
                    continue
                if t.get("tipo") not in _fx.TRANSICIONES or not isinstance(t.get("duracion"), (int, float)):
                    malos.append("%s: transicion invalida" % c["id"])
                elif self._vecinos(p, i) is None:
                    malos.append("%s: transicion sin clip pegado antes" % c["id"])
                elif t["duracion"] > self._limite_transicion(p, i) + 1e-3:
                    malos.append("%s: la transicion dura mas de lo que sobra a los lados del corte" % c["id"])
        # los clips enlazados tienen que coincidir
        grupos = {}
        for p in self.pistas:
            for c in p["clips"]:
                grupos.setdefault(c["grupo"], []).append(c)
        for g, cs in grupos.items():
            if len(cs) > 1:
                base = cs[0]
                for o in cs[1:]:
                    if abs(o["inicio"] - base["inicio"]) > TOL or abs(self.largo(o) - self.largo(base)) > TOL:
                        malos.append("grupo %s: los clips enlazados no coinciden" % g)
                    if o["fuente"] == base["fuente"] and abs(o["desde"] - base["desde"]) > TOL:
                        malos.append("grupo %s: el video y el audio salen de instantes distintos de la fuente" % g)
        vistas = set()
        for f in self.subtitulos["frases"]:
            if f["id"] in vistas:
                malos.append("frase repetida: %s" % f["id"])
            vistas.add(f["id"])
            if not (isinstance(f["inicio"], (int, float)) and isinstance(f["fin"], (int, float)) and 0 <= f["inicio"] < f["fin"]):
                malos.append("frase %s con tiempos malos" % f["id"])
            if not isinstance(f["texto"], str) or not f["texto"].strip():
                malos.append("frase %s sin texto" % f["id"])
        if [f["inicio"] for f in self.subtitulos["frases"]] != sorted(f["inicio"] for f in self.subtitulos["frases"]):
            malos.append("las frases no estan en orden")
        pals = self.subtitulos.get("palabras", [])
        ids_p = [w["id"] for w in pals]
        if len(set(ids_p)) != len(ids_p):
            malos.append("palabras repetidas")
        for w in pals:
            if not (isinstance(w["texto"], str) and w["texto"].strip() and 0 <= w["inicio"] <= w["fin"]
                    and w["inicio"] - 1e-6 <= w["voz"] <= w["habla"] <= w["fin"] + 1e-6):
                malos.append("palabra %s con datos malos" % w["id"])
        if [w["inicio"] for w in pals] != sorted(w["inicio"] for w in pals):
            malos.append("las palabras no estan en orden")
        for f in self.subtitulos["frases"]:
            for i in f.get("palabras") or []:
                if i not in ids_p:
                    malos.append("la frase %s usa una palabra que no existe (%s)" % (f["id"], i))
        return malos

    # ------------------------------------------------------------ guardado

    def a_dict(self):
        """Todo el proyecto como datos simples (sin la tabla de tiempos de cada fuente, que es enorme)."""
        return {"version": 1,
                "fuentes": {k: {a: b for a, b in v.items() if a != "tiempos"} for k, v in self.fuentes.items()},
                "pistas": copy.deepcopy(self.pistas), "duracion": self.duracion(), "salida": dict(self.salida),
                "n": dict(self._n), "subtitulos": copy.deepcopy(self.subtitulos), "subtitulos_desactualizados": self.subtitulos_desactualizados(),
                "puede_deshacer": self.puede_deshacer(), "puede_rehacer": self.puede_rehacer()}

    def guardar(self, ruta):
        d = self.a_dict()
        for f in d["fuentes"].values():
            f.pop("url", None)                      # la direccion local de un audio cambia en cada sesion: no se guarda
        d.pop("subtitulos_desactualizados", None)
        d.pop("puede_deshacer", None)
        d.pop("puede_rehacer", None)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ruta)

    @classmethod
    def cargar(cls, ruta, tiempos_de=None):
        """tiempos_de(fuente_dict) -> lista de segundos de cada cuadro (se vuelve a leer del archivo)."""
        try:
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            raise ErrorEdicion("No pude leer el archivo del proyecto: %s" % e)
        return cls.cargar_dict(d, tiempos_de)

    @classmethod
    def cargar_dict(cls, d, tiempos_de=None):
        """Igual que `cargar`, con los datos ya leidos (el programa puede cambiar de lugar un archivo antes de abrir el proyecto)."""
        if not isinstance(d, dict) or d.get("version") != 1 or not isinstance(d.get("fuentes"), dict) or not isinstance(d.get("pistas"), list):
            raise ErrorEdicion("Este archivo no es un proyecto de Moviola (o es de otra versión del programa).")
        p = cls()
        for k, v in d["fuentes"].items():
            v = dict(v)
            v["tiempos"] = tiempos_de(v) if (tiempos_de and v["tipo"] == "video") else None
            p.fuentes[k] = v
        p.pistas = d["pistas"]
        for pista in p.pistas:
            for clip in pista["clips"]:
                clip.setdefault("efectos", [])
                clip.setdefault("transicion", None)
                clip.setdefault("velocidad", 1.0)
                clip.setdefault("mantener_tono", True)
                clip.setdefault("interpolar", False)
                clip.setdefault("reversa", False)
        p.salida = d.get("salida", {"formato": "original"})
        p._n = d["n"]
        p._n.setdefault("efecto", 0)
        p._n.setdefault("sub", 0)
        p._n.setdefault("pal", 0)
        sub = d.get("subtitulos")
        if sub:
            p.subtitulos = {"frases": list(sub.get("frases", [])), "estilo": _sub.limpiar_estilo(sub.get("estilo", {})), "huella": sub.get("huella", ""),
                            "palabras": list(sub.get("palabras", []))}
        return p


class _Transaccion:
    """Guarda el estado antes de una operacion: si falla, se restaura; si sale bien, queda en el historial.
    Las operaciones pueden llamarse unas a otras: solo la mas externa escribe el historial."""

    def __init__(self, proyecto):
        self.p = proyecto

    def __enter__(self):
        self.externa = not getattr(self.p, "_en_transaccion", False)
        if self.externa:
            self.p._en_transaccion = True
            self.previo = self.p._estado()
        return self

    def __exit__(self, tipo, valor, rastro):
        if not self.externa:
            return False
        self.p._en_transaccion = False
        if tipo is not None:
            self.p._restaurar(self.previo)       # la operacion fallo: nada queda a medias
            return False
        self.p._normalizar_transiciones()          # un corte o un borrado puede dejar una transicion sin clip pegado: se quita
        self.p._deshacer.append(self.previo)
        if len(self.p._deshacer) > HISTORIAL_MAX:
            self.p._deshacer.pop(0)
        self.p._rehacer = []
        return False
