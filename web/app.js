/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — mesa de corte
   Frontend del editor. Sin frameworks, sin librerías, sin red.
   Habla con el motor de Python por HTTP local (ver "conexion con el motor"):
     elegir_archivo()      -> {ruta} | {cancelado}
     abrir(ruta)           -> info + picos + tira + url | {error}
     cuadro(n, ancho)      -> {jpg: URL de la imagen}
   ============================================================ */
'use strict';

/* ---------- referencias al DOM ---------- */
const $ = (id) => document.getElementById(id);

const el = {
  nombreArchivo:    $('nombre-archivo'),
  metaArchivo:      $('meta-archivo'),
  btnAbrirBarra:    $('btn-abrir-barra'),

  bienvenida:       $('bienvenida'),
  btnAbrir:         $('btn-abrir'),
  visor:            $('visor'),
  capaCuadro:       $('capa-cuadro'),
  capaVideo:        $('capa-video'),
  panelAudio:       $('panel-audio'),
  preparando:       $('preparando'),
  btnAcel:          $('btn-acel'),
  acelModo:         $('acel-modo'),
  panelAcel:        $('panel-acel'),
  acelTitulo:       $('acel-titulo'),
  acelLineas:       $('acel-lineas'),
  acelEfecto:       $('acel-efecto'),
  btnAcelRecomprobar: $('btn-acel-recomprobar'),
  preparandoTexto:  $('preparando-texto'),
  preparandoBarra:  $('preparando-barra'),
  panelAudioDatos:  $('panel-audio-datos'),
  cargando:         $('cargando'),
  cargandoTexto:    $('cargando-texto'),

  avisos:           $('avisos'),

  transporte:       $('transporte'),
  cuadroActual:     $('cuadro-actual'),
  cuadroTotal:      $('cuadro-total'),
  tiempoActual:     $('tiempo-actual'),
  tiempoTotal:      $('tiempo-total'),
  btnInicio:        $('btn-inicio'),
  btnSegAtras:      $('btn-seg-atras'),
  btnCuadroAtras:   $('btn-cuadro-atras'),
  btnPlay:          $('btn-play'),
  iconoReproducir:  $('icono-reproducir'),
  iconoPausar:      $('icono-pausar'),
  btnCuadroAdelante:$('btn-cuadro-adelante'),
  btnSegAdelante:   $('btn-seg-adelante'),
  btnFin:           $('btn-fin'),

  zonaTiempo:       $('zona-tiempo'),
  carriles:         $('carriles'),
  tira:             $('tira'),
  onda:             $('onda'),
  sinAudio:         $('sin-audio'),

  zonaSuelta:       $('zona-suelta')
};

/* ---------- estado ---------- */
const S = {
  ruta: null,
  info: null,          // lo que devolvió abrir()
  fps: 25,
  tiempos: null,       // segundo de cada cuadro; solo si el video es de framerate variable
  soloAudio: false,
  epocaProxy: 0,       // cambia al abrir otro archivo: corta la vigilancia del proxy anterior
  totalCuadros: 1,
  duracion: 0,
  cuadro: 0,
  reproduciendo: false,
  arrastrando: false,
  raf: 0,

  picos: [],
  sinAudio: true,

  tira: null,          // data URI de la tira completa
  tiraCantidad: 0,
  tiraAnchoMini: 0,
  tiraAltoMini: 0,

  // cola de pedidos de cuadro: uno solo en vuelo
  trabajo: null,
  pendiente: null,
  ultimoPintado: null,  // {n, ancho} del último cuadro que llegó a pantalla (n = cuadro de la LINEA DE TIEMPO)

  // --- edicion (ver edicion.js) ---
  proy: null,           // el proyecto que manda el motor: pistas, clips, fundidos...
  srcTotal: 1,          // cuadros de la fuente (el archivo original)
  srcDuracion: 0,       // duracion de la fuente
  segs: [],             // tramos que se reproducen, en orden: [{inicio, fin, desde, hasta}]
  segIdx: 0,            // tramo que se esta reproduciendo
  saltando: false,      // saltando de un tramo al siguiente (esperando el 'seeked')
  sel: null,            // clip elegido: {grupo, clip}
  marcaIn: null,        // marcas de entrada y salida, en segundos de la linea de tiempo
  marcaOut: null,
  picosFuente: {},      // picos del espectro de las fuentes extra (audios agregados)

  // --- varios videos (ver medios.js) ---
  fidPrincipal: null,   // el archivo abierto en el visor: el que describen fps, tiempos, srcTotal... (los demas, en S.medios)
  medios: {},           // id de archivo -> lo que devolvio abrir() (el principal) o medio_info() (los otros videos del proyecto)
  fuenteVideo: null,    // de que archivo es lo que tiene cargado el <video> ahora
  urlPrincipal: ''      // direccion para reproducir el principal
};

// Linea de tiempo EDITADA: para cada cuadro, de que cuadro de la fuente sale (tN) y en que segundo de
// la linea cae (tT). Sin ediciones es null y vale la identidad: todo funciona como antes.
const L = { tN: null, tT: null, tF: null, fids: [] };       // tF: de que archivo sale cada cuadro (indice en fids); null = siempre el principal

const ANCHO_NITIDO = 540;   // al soltar: cuadro nítido (~3,5 ms en el backend)
const ANCHO_LIVIANO = 270;  // mientras se arrastra: cuadro liviano (~1,1 ms)

/* ============================================================
   conexion con el motor: HTTP local con token en la ruta
   La pagina se sirve en  http://127.0.0.1:<puerto>/<token>/index.html  y todo se
   pide relativo a esa carpeta, asi el token nunca se escribe en el codigo. La misma
   interfaz corre en la ventana nativa o en cualquier navegador.
   ============================================================ */
const BASE = location.pathname.replace(/[^/]*$/, '');

async function llamar(metodo, args) {
  const r = await fetch(BASE + 'api/' + metodo, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(args || [])
  });
  if (!r.ok) throw new Error('El motor respondió ' + r.status);
  return r.json();
}

const puenteLocal = {
  elegir_archivo: () => llamar('elegir_archivo'),
  abrir: (ruta) => llamar('abrir', [ruta]),
  inicial: () => llamar('inicial'),
  // El cuadro llega como imagen directa (sin base64); se pide con fetch para
  // enterarse de los errores y se entrega como URL de objeto.
  cuadro: async (n, ancho, fid) => {
    const r = await fetch(BASE + 'frame?n=' + n + '&w=' + ancho + (fid ? '&f=' + encodeURIComponent(fid) : ''));
    if (!r.ok) return { error: 'No se pudo traer el cuadro ' + n + '.' };
    return { jpg: URL.createObjectURL(await r.blob()) };
  }
};

function api() {
  return Promise.resolve(puenteLocal);
}

/* ============================================================
   utilidades
   ============================================================ */
function acotar(n) {
  if (!isFinite(n)) return 0;
  n = Math.round(n);
  if (n < 0) return 0;
  const tope = S.totalCuadros - 1;
  return n > tope ? tope : n;
}

function dos(n) { return String(n).padStart(2, '0'); }

/** Tiempo como mm:ss,mmm (o h:mm:ss,mmm si pasa la hora). Coma decimal. */
function formatoTiempo(seg) {
  if (!isFinite(seg) || seg < 0) seg = 0;
  const ms = Math.round(seg * 1000);
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const mil = ms % 1000;
  const base = dos(m) + ':' + dos(s) + ',' + String(mil).padStart(3, '0');
  return h > 0 ? h + ':' + base : base;
}

function rellenarCuadro(n) {
  return String(n).padStart(String(Math.max(0, S.totalCuadros - 1)).length, '0');
}

function nombreDe(ruta) {
  const partes = String(ruta).split(/[\\/]/);
  return partes[partes.length - 1] || String(ruta);
}

function mensajeDe(e) {
  if (!e) return 'error desconocido';
  if (typeof e === 'string') return e;
  return e.message ? e.message : String(e);
}

function colorCss(nombre, alternativa) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
  return v || alternativa;
}

function esperarEvento(objetivo, nombre, limiteMs) {
  return new Promise((listo) => {
    let temporizador = 0;
    const mano = () => {
      clearTimeout(temporizador);
      objetivo.removeEventListener(nombre, mano);
      listo(true);
    };
    objetivo.addEventListener(nombre, mano, { once: true });
    temporizador = setTimeout(() => {
      objetivo.removeEventListener(nombre, mano);
      listo(false);
    }, limiteMs || 2000);
  });
}

/* ============================================================
   avisos (nada de alert())
   ============================================================ */
function avisar(texto, tipo) {
  const caja = document.createElement('div');
  caja.className = 'aviso aviso--' + (tipo === 'ojo' ? 'ojo' : (tipo === 'info' ? 'info' : 'error'));

  const p = document.createElement('p');
  p.className = 'aviso__texto';
  p.textContent = String(texto);

  const cerrar = document.createElement('button');
  cerrar.type = 'button';
  cerrar.className = 'aviso__cerrar';
  cerrar.textContent = 'Cerrar';
  cerrar.addEventListener('click', () => caja.remove());

  caja.appendChild(p);
  caja.appendChild(cerrar);
  el.avisos.appendChild(caja);
}

function limpiarAvisos() {
  el.avisos.textContent = '';
}

function mostrarCargando(texto) {
  el.cargandoTexto.textContent = texto;
  el.cargando.hidden = false;
}

function ocultarCargando() {
  el.cargando.hidden = true;
}

/* ============================================================
   abrir un video
   ============================================================ */
async function elegirYAbrir() {
  let puente;
  try {
    puente = await api();
  } catch (e) {
    avisar('No hay puente con el backend: ' + mensajeDe(e));
    return;
  }
  try {
    const r = await puente.elegir_archivo();
    if (!r || r.cancelado) return;
    if (r.error) { avisar(r.error); return; }
    if (!r.ruta) { avisar('El selector no devolvió ninguna ruta.'); return; }
    await abrir(r.ruta);
  } catch (e) {
    avisar('No se pudo abrir el selector de archivos: ' + mensajeDe(e));
  }
}

async function abrir(ruta) {
  limpiarAvisos();
  mostrarCargando('Leyendo ' + nombreDe(ruta) + '…');
  try {
    const puente = await api();
    const d = await puente.abrir(ruta);
    if (!d) { avisar('El backend no devolvió nada al abrir el archivo.'); return; }
    if (d.error) { avisar(d.error); return; }
    // si se abrio un proyecto (.moviola), el medio principal es el video del que habla, no el archivo del proyecto
    const medio = d.ruta || ruta;
    if (d.solo_audio) aplicarAudio(medio, d);
    else aplicarVideo(medio, d);
  } catch (e) {
    avisar('Falló abrir el archivo: ' + mensajeDe(e));
  } finally {
    ocultarCargando();
  }
}

/* ---------- tiempo <-> cuadro ----------
   Con framerate constante alcanza la cuenta n / fps. Con framerate variable el
   cuadro n no esta en n / fps (en un video real llegaba a correrse 49 s), asi
   que el backend manda el segundo de cada cuadro y se busca en esa tabla. */
/* Hay DOS numeraciones. El cuadro de la FUENTE es el del archivo original (lo numera el motor). El cuadro
   de la LINEA DE TIEMPO es el de lo que se ve despues de cortar. Sin ediciones coinciden. */
/* Con varios videos en el proyecto, cada archivo tiene SUS cuadros por segundo, SU tabla de cuadros y SU cantidad de cuadros:
   F = {fps, tiempos, total, dur}. Sin F se usa el archivo principal (lo de siempre). */
function ctxPrincipal() {
  return { fps: S.fps, tiempos: S.tiempos, total: S.srcTotal, dur: S.srcDuracion };
}

/** El contexto de tiempo del archivo `fid`. Si todavia no llegaron sus datos, se usa el principal de aproximacion (se corrige solo al llegar). */
function ctxFuente(fid) {
  if (!fid || fid === S.fidPrincipal) return ctxPrincipal();
  const m = S.medios[fid];
  if (!m) return ctxPrincipal();
  if (!m._ctx) {
    m._ctx = {
      fps: (typeof m.fps === 'number' && m.fps > 0) ? m.fps : 25,
      tiempos: (m.vfr && Array.isArray(m.tiempos)) ? Float64Array.from(m.tiempos) : null,
      total: Math.max(1, Math.floor(m.total_cuadros || 1)),
      dur: m.duracion || 0
    };
  }
  return m._ctx;
}

function acotarFuente(i, F) {
  F = F || ctxPrincipal();
  if (!isFinite(i)) return 0;
  i = Math.round(i);
  return i < 0 ? 0 : (i > F.total - 1 ? F.total - 1 : i);
}

/** Segundo (de la fuente) en que se muestra el cuadro i de la fuente. */
function tiempoFuente(i, F) {
  F = F || ctxPrincipal();
  i = acotarFuente(i, F);
  return F.tiempos ? F.tiempos[i] : i / F.fps;
}

/** Cuadro de la fuente que esta en pantalla en el segundo ts de la fuente. */
function cuadroFuente(ts, F) {
  F = F || ctxPrincipal();
  if (!F.tiempos) return acotarFuente(Math.round(ts * F.fps), F);
  const x = ts + 1e-4;
  let lo = 0;
  let hi = F.tiempos.length - 1;
  while (lo < hi) {
    const m = (lo + hi + 1) >> 1;
    if (F.tiempos[m] <= x) lo = m; else hi = m - 1;
  }
  return lo;
}

/** Primer cuadro de la fuente que empieza en ts o despues (los bordes de un clip son inicios de cuadro). */
function primerCuadroDesde(ts, F) {
  F = F || ctxPrincipal();
  if (!F.tiempos) return Math.max(0, Math.min(F.total, Math.round(ts * F.fps)));
  let lo = 0;
  let hi = F.tiempos.length;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (F.tiempos[m] < ts - 1e-6) lo = m + 1; else hi = m;
  }
  return lo;
}

/** Segundo de la linea de tiempo en que se muestra el cuadro k. */
function tiempoDe(k) {
  k = acotar(k);
  return L.tT ? L.tT[k] : tiempoFuente(k);
}

/** Cuadro de la linea de tiempo que esta en pantalla en el segundo t de la linea. */
function cuadroDe(t) {
  if (!L.tT) return acotar(cuadroFuente(t));
  const x = t + 1e-4;
  let lo = 0;
  let hi = L.tT.length - 1;
  while (lo < hi) {
    const m = (lo + hi + 1) >> 1;
    if (L.tT[m] <= x) lo = m; else hi = m - 1;
  }
  return lo;
}

/** Cuadro de la FUENTE que corresponde al cuadro k de la linea de tiempo (es lo que se le pide al motor). */
function fuenteDe(k) {
  k = acotar(k);
  return L.tN ? L.tN[k] : k;
}

/** De que ARCHIVO del proyecto sale el cuadro k de la linea de tiempo (null = el principal, que es lo de siempre). */
function fidDe(k) {
  if (!L.tF) return null;
  const f = L.fids[L.tF[acotar(k)]];
  return f && f !== S.fidPrincipal ? f : null;
}

/** Arma la linea de tiempo editada a partir del proyecto (clips de V1, o de A1 si es solo audio). */
function reconstruirLinea() {
  L.tN = L.tT = L.tF = null;
  L.fids = [];
  S.totalCuadros = S.srcTotal;
  S.duracion = S.srcDuracion;
  S.segs = [{ inicio: 0, fin: S.srcDuracion, desde: 0, hasta: S.srcDuracion }];
  const p = S.proy;
  if (!p) return;
  const v1 = p.pistas.find((x) => x.id === 'V1');
  const guia = (S.soloAudio || !v1) ? p.pistas.find((x) => x.id === 'A1') : v1;
  S.duracion = Math.max(p.duracion, 1e-3);
  const clips = guia ? guia.clips : [];
  S.segs = clips.map((c) => ({ inicio: c.inicio, fin: c.inicio + (c.hasta - c.desde) / (c.velocidad || 1), desde: c.desde, hasta: c.hasta, clip: c.id,
                              v: c.velocidad || 1, rev: !!c.reversa, mt: c.mantener_tono !== false, fuente: c.fuente }));
  if (!S.segs.length) S.segs = [{ inicio: 0, fin: S.duracion, desde: 0, hasta: S.duracion }];
  if (S.soloAudio || !v1) {
    S.totalCuadros = Math.max(1, Math.ceil(S.duracion * S.fps));
    return;
  }
  const sinTiempo = clips.every((c) => (c.velocidad || 1) === 1 && !c.reversa);
  // un solo clip que cubre toda la fuente desde cero: no hay ediciones, vale la identidad
  if (clips.length === 1 && sinTiempo && Math.abs(clips[0].desde) < 1e-6 && Math.abs(clips[0].inicio) < 1e-6 &&
      Math.abs(clips[0].hasta - S.srcDuracion) < 1e-6 && (!clips[0].fuente || clips[0].fuente === S.fidPrincipal)) {
    S.totalCuadros = S.srcTotal;
    return;
  }
  // Cuantos cuadros de la linea de tiempo tiene cada clip: a velocidad normal son los de la fuente; con otra velocidad (o al revés)
  // la linea de tiempo es un reloj de S.fps cuadros por segundo y cada cuadro toma el de la fuente que le toca.
  let total = 0;
  const fids = [];
  const rangos = clips.map((c) => {
    const F = ctxFuente(c.fuente);
    let ix = fids.indexOf(c.fuente);
    if (ix < 0) { fids.push(c.fuente); ix = fids.length - 1; }
    const normal = (c.velocidad || 1) === 1 && !c.reversa;
    if (normal) {
      const i0 = primerCuadroDesde(c.desde, F);
      const i1 = primerCuadroDesde(c.hasta, F);
      total += Math.max(0, i1 - i0);
      return { c, normal, i0, i1, F, ix };
    }
    const n = Math.max(1, Math.round((c.hasta - c.desde) / (c.velocidad || 1) * S.fps));
    total += n;
    return { c, normal, n, F, ix };
  });
  const tN = new Int32Array(total);
  const tT = new Float64Array(total);
  const tF = new Uint16Array(total);
  let k = 0;
  rangos.forEach((r) => {
    if (r.normal) {
      for (let i = r.i0; i < r.i1; i++) {
        tN[k] = i;
        tT[k] = r.c.inicio + (tiempoFuente(i, r.F) - r.c.desde);
        tF[k] = r.ix;
        k++;
      }
      return;
    }
    const v = r.c.velocidad || 1;
    for (let j = 0; j < r.n; j++) {
      const tl = j / S.fps;
      // al revés, el primer cuadro de la linea de tiempo es el ULTIMO de la fuente
      const ts = r.c.reversa ? Math.max(r.c.desde, r.c.hasta - (tl + 1 / S.fps) * v) : Math.min(r.c.hasta - 1e-6, r.c.desde + tl * v + 1e-6);
      tN[k] = cuadroFuente(ts, r.F);
      tT[k] = r.c.inicio + tl;
      tF[k] = r.ix;
      k++;
    }
  });
  L.tN = tN;
  L.tT = tT;
  L.tF = tF;
  L.fids = fids;
  S.totalCuadros = Math.max(1, total);
}

/** Pone el proyecto que mando el motor. Conserva la posicion en el tiempo (acotada a lo que queda). */
function aplicarProyecto(p, dibujar) {
  const t = (S.proy && S.info) ? tiempoDe(S.cuadro) : 0;
  S.proy = p || null;
  reconstruirLinea();
  S.ultimoPintado = null;
  S.cuadro = S.info ? acotar(cuadroDe(t)) : 0;
  if (S.info) {
    el.cuadroTotal.textContent = rellenarCuadro(Math.max(0, S.totalCuadros - 1));
    el.tiempoTotal.textContent = formatoTiempo(S.duracion);
  }
  if (dibujar === false) return;
  construirTira();
  dibujarOnda();
  pintarPosicion();
  if (!S.reproduciendo) pedirCuadro(S.cuadro, ANCHO_NITIDO);
  if (typeof alActualizarProyecto === 'function') alActualizarProyecto();
  if (typeof asegurarMedios === 'function') asegurarMedios();         // medios.js: pide los datos de los videos nuevos del proyecto
}

/** Cuadro a `delta` segundos del actual; siempre se mueve al menos uno. */
function cuadroEnSegundos(delta) {
  const destino = cuadroDe(tiempoDe(S.cuadro) + delta);
  if (delta > 0 && destino <= S.cuadro) return acotar(S.cuadro + 1);
  if (delta < 0 && destino >= S.cuadro) return acotar(S.cuadro - 1);
  return destino;
}

/* ---------- proxy de reproduccion ----------
   El <video> del navegador solo reproduce h264/aac en mp4. Para el resto, el motor
   prepara en segundo plano una copia liviana (proxy) con los mismos cuadros y los mismos
   tiempos que el original: se ve el progreso y, cuando esta lista, se cambia la fuente. */
function vigilarProxy(ruta) {
  const epoca = ++S.epocaProxy;
  el.preparando.hidden = false;
  el.preparandoTexto.textContent = 'Preparando la reproducción…';
  el.preparandoBarra.style.width = '0%';
  const paso = async () => {
    if (epoca !== S.epocaProxy) return;
    let r = null;
    try { r = await llamar('proxy_estado'); } catch (e) { r = null; }
    if (epoca !== S.epocaProxy) return;
    if (r && r.ruta === ruta) {
      if (r.estado === 'listo') {
        if (r.respaldo) {
          avisar('La GPU no pudo preparar la reproducción, así que se usó el procesador. ' + (r.motivo_respaldo || ''), 'ojo');
        }
        proxyListo(r.url);
        return;
      }
      if (r.estado === 'error') {
        el.preparando.hidden = true;
        avisar((r.error || 'No pude preparar la reproducción.') +
               ' El resto sigue andando: cuadro por cuadro, miniaturas y espectro.', 'ojo');
        return;
      }
      const pct = Math.round((r.progreso || 0) * 100);
      el.preparandoTexto.textContent = 'Preparando la reproducción… ' + pct + ' %';
      el.preparandoBarra.style.width = pct + '%';
    }
    setTimeout(paso, 600);
  };
  paso();
}

function proxyListo(url) {
  el.preparando.hidden = true;
  if (!S.info) return;
  S.info.url = url;
  S.info.reproducible = true;
  S.info.proxy = 'listo';
  S.urlPrincipal = url;
  const video = el.capaVideo;
  if (S.fuenteVideo && S.fuenteVideo !== S.fidPrincipal) return;      // el <video> tiene otro archivo: se usa la copia cuando vuelva el principal
  video.src = url;
  video.load();
}

/* ---------- aceleracion por GPU ----------
   El motor prueba de verdad que puede la PC (no se fia de la lista de ffmpeg) y la interfaz
   lo cuenta en castellano. Modos: CPU, GPU (usa la GPU donde pueda) y Automatico (la usa
   solo donde gana). Se avisa al abrir si hay algo que decidir. */
const NOMBRES_ACEL = { cpu: 'CPU', gpu: 'GPU', auto: 'Auto' };
let sondeoAcel = 0;
let avisoAcelMostrado = false;

function pintarAcel(r) {
  el.acelModo.textContent = NOMBRES_ACEL[r.modo] || 'CPU';
  document.querySelectorAll('.acel__op').forEach((b) => {
    const activo = b.dataset.modo === r.modo;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('acel__op--activo', activo);
  });
  const res = r.resumen;
  el.acelTitulo.textContent = res ? res.titulo
    : (r.detectando ? 'Comprobando la aceleración por GPU…' : (r.error || 'Sin información de la GPU.'));
  el.acelLineas.textContent = '';
  (res ? res.lineas : []).forEach((linea) => {
    const li = document.createElement('li');
    li.textContent = linea;
    el.acelLineas.appendChild(li);
  });
  const ef = r.efectivo;
  el.acelEfecto.textContent = ef
    ? 'Ahora: codifica con ' + (ef.codificar.usa === 'gpu' ? 'la GPU' : 'el procesador') + ' y decodifica con ' +
      (ef.decodificar.usa === 'gpu' ? 'la GPU' : 'el procesador') + '. ' + ef.codificar.motivo
    : '';
  el.btnAcelRecomprobar.disabled = !!r.detectando;
}

async function actualizarAcel() {
  try {
    const r = await llamar('gpu_estado');
    pintarAcel(r);
    return r;
  } catch (e) {
    return null;
  }
}

function mostrarAvisoAcel(r, forzar) {
  if (!r.resumen || (!forzar && (!r.avisar || avisoAcelMostrado))) return;
  avisoAcelMostrado = true;
  const res = r.resumen;
  const partes = [res.titulo + '.'].concat(res.lineas.slice(1, 3));
  if (res.util && r.modo === 'cpu') partes.push('Podés activarla en «Aceleración», arriba a la derecha.');
  avisar(partes.join(' '), res.nivel === 'ok' ? 'info' : 'ojo');
  llamar('gpu_visto').catch(() => {});
}

async function vigilarAcel(forzarAviso) {
  const epoca = ++sondeoAcel;
  for (let i = 0; i < 180 && epoca === sondeoAcel; i++) {
    const r = await actualizarAcel();
    if (r && r.listo && !r.detectando) { mostrarAvisoAcel(r, forzarAviso); return; }
    if (r && !r.disponible) return;
    await new Promise((resolver) => setTimeout(resolver, 1000));
  }
}

function abrirPanelAcel(abrir) {
  el.panelAcel.hidden = !abrir;
  el.btnAcel.setAttribute('aria-expanded', abrir ? 'true' : 'false');
  if (abrir) actualizarAcel();
}

el.btnAcel.addEventListener('click', (e) => { e.stopPropagation(); abrirPanelAcel(el.panelAcel.hidden); });
el.panelAcel.addEventListener('click', (e) => e.stopPropagation());
document.addEventListener('click', () => abrirPanelAcel(false));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !el.panelAcel.hidden) abrirPanelAcel(false); });
document.querySelectorAll('.acel__op').forEach((b) => {
  b.addEventListener('click', async () => {
    try { pintarAcel(await llamar('gpu_modo', [b.dataset.modo])); } catch (e) { avisar('No pude cambiar el modo de aceleración.'); }
  });
});
el.btnAcelRecomprobar.addEventListener('click', async () => {
  try { await llamar('gpu_comprobar'); } catch (e) { return; }
  avisoAcelMostrado = false;
  vigilarAcel(true);
});

/** Solo audio: sin visor, sin cuadros, sin miniaturas. */
function modoSoloAudio(si) {
  S.soloAudio = si;
  const campoCuadro = el.cuadroActual.closest('.contador__campo');
  if (campoCuadro) campoCuadro.hidden = si;
  el.tira.hidden = si;
  el.capaCuadro.hidden = si;
  el.panelAudio.hidden = !si;
  el.btnCuadroAtras.hidden = si;
  el.btnCuadroAdelante.hidden = si;
}

function aplicarVideo(ruta, d) {
  detenerBucle();
  S.epocaProxy++;
  el.preparando.hidden = true;
  modoSoloAudio(false);

  S.ruta = ruta;
  S.info = d;
  S.fidPrincipal = d.fid || null;
  S.medios = d.fid ? { [d.fid]: d } : {};
  S.fuenteVideo = S.fidPrincipal;
  S.urlPrincipal = (d.reproducible && d.url) ? d.url : '';
  S.fps = (typeof d.fps === 'number' && d.fps > 0) ? d.fps : 25;
  S.totalCuadros = (typeof d.total_cuadros === 'number' && d.total_cuadros > 0) ? Math.floor(d.total_cuadros) : 1;
  S.duracion = (typeof d.duracion === 'number' && d.duracion > 0) ? d.duracion : (S.totalCuadros / S.fps);
  S.tiempos = (d.vfr && Array.isArray(d.tiempos)) ? Float64Array.from(d.tiempos) : null;
  S.srcTotal = S.totalCuadros;
  S.srcDuracion = S.duracion;
  S.proy = null;
  L.tN = L.tT = null;
  S.sel = null;
  S.marcaIn = S.marcaOut = null;
  S.picosFuente = {};
  S.cuadro = 0;
  S.reproduciendo = false;
  S.pendiente = null;
  S.ultimoPintado = null;

  S.picos = Array.isArray(d.picos) ? d.picos : [];
  S.sinAudio = (d.sin_audio === true) || S.picos.length === 0;

  S.tira = d.tira || null;
  S.tiraCantidad = Math.max(0, parseInt(d.tira_cantidad, 10) || 0);
  S.tiraAnchoMini = Math.max(0, parseInt(d.tira_ancho_mini, 10) || 0);
  S.tiraAltoMini = Math.max(1, parseInt(d.tira_alto_mini, 10) || 1);

  // --- cabecera ---
  el.nombreArchivo.textContent = nombreDe(ruta);
  el.nombreArchivo.title = ruta;
  el.metaArchivo.textContent = '';
  const trozos = [];
  if (d.ancho && d.alto) trozos.push(d.ancho + '×' + d.alto);
  trozos.push(S.fps.toFixed(2).replace('.', ',') + (d.vfr ? ' fps (variable)' : ' fps'));
  if (d.rotacion) trozos.push('girado ' + d.rotacion + '°');
  if (d.entrelazado) trozos.push('entrelazado');
  if (d.decodifica_con === 'gpu') trozos.push('decodifica con GPU');
  if (d.codec) trozos.push(String(d.codec));
  trozos.push(S.srcTotal + ' cuadros');
  el.metaArchivo.textContent = trozos.join('  ·  ');
  if (d.hdr) {
    const b = document.createElement('span');
    b.className = 'hdr';
    b.textContent = 'HDR';
    el.metaArchivo.appendChild(b);
  }

  aplicarProyecto(d.proyecto || null, false);

  // --- reproducción nativa: la URL la arma el backend, se usa tal cual ---
  const video = el.capaVideo;
  video.pause();
  video.hidden = true;
  if (d.reproducible && d.url) {
    video.src = d.url;
    video.load();
  } else {
    video.removeAttribute('src');
    video.load();
  }

  // --- mostrar la mesa ---
  el.bienvenida.hidden = true;
  el.visor.hidden = false;
  el.transporte.hidden = false;
  el.zonaTiempo.hidden = false;

  el.cuadroTotal.textContent = rellenarCuadro(Math.max(0, S.totalCuadros - 1));
  el.tiempoTotal.textContent = formatoTiempo(S.duracion);
  pintarPlay();
  pintarPosicion();

  // --- carriles ---
  el.sinAudio.hidden = !S.sinAudio;
  el.onda.hidden = S.sinAudio;
  construirTira();
  dibujarOnda();

  // --- primer cuadro ---
  pedirCuadro(0, ANCHO_NITIDO);
  if (typeof alActualizarProyecto === 'function') alActualizarProyecto();
  if (typeof asegurarMedios === 'function') asegurarMedios();          // un proyecto guardado puede traer varios videos

  if (d.proxy === 'generando') {
    vigilarProxy(ruta);
  } else if (!d.reproducible) {
    avisar('Este formato (' + (d.codec || 'codec desconocido') + ') no se puede reproducir con audio en esta ventana. ' +
           'El resto anda igual: cuadro por cuadro, miniaturas y espectro.', 'ojo');
  } else if (!d.url) {
    avisar('El backend no mandó la URL del video, así que la reproducción no está disponible. ' +
           'Cuadro por cuadro, miniaturas y espectro siguen funcionando.', 'ojo');
  }
}

function aplicarAudio(ruta, d) {
  detenerBucle();
  S.epocaProxy++;
  el.preparando.hidden = true;
  modoSoloAudio(true);

  S.ruta = ruta;
  S.info = d;
  S.fidPrincipal = d.fid || null;
  S.medios = {};
  S.fuenteVideo = null;
  S.urlPrincipal = (d.reproducible && d.url) ? d.url : '';
  S.fps = 100;                        // en solo audio un "cuadro" son 10 ms
  S.duracion = (typeof d.duracion === 'number' && d.duracion > 0) ? d.duracion : 1;
  S.totalCuadros = Math.max(1, Math.ceil(S.duracion * S.fps));
  S.tiempos = null;
  S.srcTotal = S.totalCuadros;
  S.srcDuracion = S.duracion;
  S.proy = null;
  L.tN = L.tT = null;
  S.sel = null;
  S.marcaIn = S.marcaOut = null;
  S.picosFuente = {};
  S.cuadro = 0;
  S.reproduciendo = false;
  S.pendiente = null;
  S.ultimoPintado = null;

  S.picos = Array.isArray(d.picos) ? d.picos : [];
  S.sinAudio = S.picos.length === 0;
  S.tira = null;
  S.tiraCantidad = 0;
  S.tiraAnchoMini = 0;
  S.tiraAltoMini = 1;

  el.nombreArchivo.textContent = nombreDe(ruta);
  el.nombreArchivo.title = ruta;
  const trozos = ['solo audio'];
  if (d.codec) trozos.push(String(d.codec));
  if (d.canales) trozos.push(d.canales + (d.canales === 1 ? ' canal' : ' canales'));
  if (d.frecuencia) trozos.push((d.frecuencia / 1000).toFixed(1).replace('.', ',') + ' kHz');
  el.metaArchivo.textContent = trozos.join('  ·  ');
  el.panelAudioDatos.textContent = formatoTiempo(S.duracion);
  aplicarProyecto(d.proyecto || null, false);

  const video = el.capaVideo;
  video.pause();
  video.hidden = true;
  if (d.reproducible && d.url) {
    video.src = d.url;
    video.load();
  } else {
    video.removeAttribute('src');
    video.load();
  }

  el.bienvenida.hidden = true;
  el.visor.hidden = false;
  el.transporte.hidden = false;
  el.zonaTiempo.hidden = false;
  el.tiempoTotal.textContent = formatoTiempo(S.duracion);
  pintarPlay();
  pintarPosicion();
  el.sinAudio.hidden = !S.sinAudio;
  el.onda.hidden = S.sinAudio;
  dibujarOnda();
  if (typeof alActualizarProyecto === 'function') alActualizarProyecto();

  if (d.proxy === 'generando') {
    vigilarProxy(ruta);
  } else if (!d.reproducible) {
    avisar('Este audio (' + (d.codec || 'codec desconocido') + ') no se puede escuchar desde esta ventana todavía. ' +
           'El espectro y la navegación sí funcionan.', 'ojo');
  }
}

/* ============================================================
   pedidos de cuadro: uno solo en vuelo, se descarta el viejo
   ============================================================ */
function pedirCuadro(n, ancho) {
  if (S.soloAudio) return Promise.resolve();   // no hay cuadros que pedir
  n = acotar(n);
  ancho = ancho || ANCHO_NITIDO;
  // Si ese mismo cuadro, a ese mismo ancho, ya está en pantalla y no hay
  // nada en vuelo, no se vuelve a pedir: arrastrar repite mucho la posición.
  if (!S.trabajo && S.ultimoPintado && S.ultimoPintado.n === n && S.ultimoPintado.ancho === ancho) {
    return Promise.resolve();
  }
  S.pendiente = { n: n, ancho: ancho };
  if (!S.trabajo) {
    S.trabajo = correrCola().then(terminarCola, terminarCola);
  }
  return S.trabajo;
}

function terminarCola() {
  S.trabajo = null;
  // Carrera: si entró un pedido justo cuando la cola se vaciaba, se relanza.
  if (S.pendiente) {
    const p = S.pendiente;
    pedirCuadro(p.n, p.ancho);
  }
}

async function correrCola() {
  const puente = await api();
  while (S.pendiente) {
    const p = S.pendiente;
    S.pendiente = null;
    let r;
    try {
      r = await puente.cuadro(fuenteDe(p.n), p.ancho, fidDe(p.n));     // p.n es de la linea de tiempo; el motor numera la fuente de ESE archivo
    } catch (e) {
      avisar('No se pudo traer el cuadro ' + p.n + ': ' + mensajeDe(e));
      return;
    }
    if (!r) continue;
    if (r.error) { avisar(r.error); continue; }
    if (!r.jpg) continue;
    if (S.pendiente) continue;   // ya hay uno más nuevo: este cuadro se tira
    await pintarCuadro(r.jpg);
    S.ultimoPintado = { n: p.n, ancho: p.ancho };
  }
}

let urlObjetoPintada = null;

async function pintarCuadro(datos) {
  const img = el.capaCuadro;
  const anterior = urlObjetoPintada;
  urlObjetoPintada = String(datos).startsWith('blob:') ? datos : null;
  img.src = datos;
  if (typeof img.decode === 'function') {
    try { await img.decode(); } catch (e) { /* el src cambió mientras decodificaba */ }
  } else {
    await esperarEvento(img, 'load', 1500);
  }
  // Soltar la imagen anterior de la memoria (cada cuadro es una URL de objeto).
  if (anterior && anterior !== urlObjetoPintada) URL.revokeObjectURL(anterior);
}

/* ============================================================
   posición
   ============================================================ */
function pintarPosicion() {
  if (!S.info) return;
  el.cuadroActual.textContent = rellenarCuadro(S.cuadro);
  el.tiempoActual.textContent = formatoTiempo(tiempoDe(S.cuadro));
  // El cursor sigue al tiempo, igual que el espectro y la tira.
  const fraccion = Math.min(1, tiempoDe(S.cuadro) / Math.max(S.duracion, 1e-6));
  el.carriles.style.setProperty('--pos', String(fraccion));
  if (typeof alMoverCursor === 'function') alMoverCursor();
}

/** Mueve el cursor al cuadro n. `ancho` elige la calidad del cuadro pedido. */
function irA(n, ancho) {
  if (!S.info) return;
  n = acotar(n);
  S.cuadro = n;
  pintarPosicion();
  if (S.reproduciendo) {
    // Reproduciendo manda el <video>: se mueve el tiempo nativo, no se piden cuadros.
    saltarVideoA(tiempoDe(n));
    return;
  }
  pedirCuadro(n, ancho || ANCHO_NITIDO);
}

function fraccionDeEvento(e) {
  const caja = el.carriles.getBoundingClientRect();
  if (caja.width <= 0) return 0;
  let f = (e.clientX - caja.left) / caja.width;
  if (f < 0) f = 0;
  if (f > 1) f = 1;
  return f;
}

function cuadroDeEvento(e) {
  return cuadroDe(fraccionDeEvento(e) * S.duracion);
}

/* ============================================================
   reproducción: la hace el <video> nativo (audio sincronizado solo)
   ============================================================ */
function puedeReproducir() {
  return !!(S.info && S.info.reproducible && S.info.url);
}

/** Direccion para reproducir el archivo `fid` ('' si todavia no se puede: su copia se esta preparando o no hay). */
function urlDeFuente(fid) {
  if (!fid || fid === S.fidPrincipal) return S.urlPrincipal;
  const m = S.medios[fid];
  return (m && m.reproducible && m.url) ? m.url : '';
}

/** Carga en el <video> el archivo `fid` si no es el que tiene. Devuelve true si el <video> queda con ese archivo. */
async function ponerFuenteEnVideo(fid) {
  fid = fid || S.fidPrincipal;
  if (S.fuenteVideo === fid) return true;
  const url = urlDeFuente(fid);
  if (!url) return false;
  const video = el.capaVideo;
  video.src = url;
  video.load();
  S.fuenteVideo = fid;
  try { await esperarEvento(video, 'loadedmetadata', 6000); } catch (e) { /* se sigue: el seek reintenta */ }
  return true;
}

function avisarSinReproduccion(fid) {
  const m = S.medios[fid];
  avisar(m && m.proxy === 'generando'
    ? 'Todavía estoy preparando la reproducción de «' + (m.nombre || 'ese video') + '». En unos segundos vas a poder darle play.'
    : 'Ese tramo es de un archivo que no se puede reproducir acá. Recorrelo con las flechas: se ve bien al exportar.', 'ojo');
}

function pintarPlay() {
  const sonando = S.reproduciendo;
  el.iconoReproducir.hidden = sonando;
  el.iconoPausar.hidden = !sonando;
  el.btnPlay.setAttribute('aria-label', sonando ? 'Pausar' : 'Reproducir');
  el.btnPlay.title = sonando ? 'Pausar (Espacio)' : 'Reproducir (Espacio)';
}

function detenerBucle() {
  if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0; }
}

/* Reproduccion con cortes: el <video> reproduce el ARCHIVO ORIGINAL; la linea de tiempo editada es una
   lista de tramos (S.segs). Al llegar al final de un tramo se salta al principio del siguiente. */
function indiceSegmento(t) {
  let r = 0;
  for (let i = 0; i < S.segs.length; i++) {
    if (S.segs[i].inicio <= t + 1e-6) r = i; else break;
  }
  return r;
}

/** Segundo de la linea de tiempo que corresponde al segundo ct del <video> (dentro del tramo actual). */
function tiempoLineaDeVideo(ct) {
  const s = S.segs[S.segIdx] || { inicio: 0, desde: 0, hasta: Infinity, v: 1 };
  return s.inicio + Math.min(Math.max(ct - s.desde, 0), s.hasta - s.desde) / (s.v || 1);
}

/** Ajusta el <video> a lo que pide el tramo: velocidad (y si conserva el tono). Un tramo al revés no se puede reproducir. */
function aplicarVelocidadTramo(s) {
  const video = el.capaVideo;
  video.playbackRate = s.v || 1;
  try { video.preservesPitch = s.mt !== false; } catch (e) { /* sin soporte */ }
}

/** Lleva el <video> al segundo t de la linea de tiempo (elige el tramo que corresponde). */
function saltarVideoA(t) {
  S.segIdx = indiceSegmento(t);
  const s = S.segs[S.segIdx];
  const llevar = () => {
    el.capaVideo.currentTime = s.desde + (t - s.inicio) * (s.v || 1);
    aplicarVelocidadTramo(s);
    if (typeof previaInicio === 'function') previaInicio(t);
  };
  if (!s.fuente || s.fuente === S.fuenteVideo) { llevar(); return; }
  // el tramo es de OTRO archivo: se carga en el <video> y recien ahi se mueve
  S.saltando = true;
  ponerFuenteEnVideo(s.fuente).then((bien) => {
    S.saltando = false;
    if (!bien) { avisarSinReproduccion(s.fuente); pausar(); return; }
    llevar();
    if (S.reproduciendo) el.capaVideo.play().catch(() => {});
  });
}

/** Se acabo el tramo actual y hay otro: se salta a el (de otro archivo, si hace falta). false si se freno ahi (un tramo que no se puede reproducir). */
function pasarAlSiguienteTramo() {
  const video = el.capaVideo;
  S.segIdx++;
  const sig = S.segs[S.segIdx];
  if (sig.rev) {                      // un tramo al revés no se puede reproducir: se frena ahí
    S.raf = 0;
    avisar('El siguiente tramo está al revés y la vista previa no lo reproduce: recorrelo con las flechas. Se ve bien al exportar.', 'ojo');
    pausar().then(() => { irA(cuadroDe(sig.inicio), ANCHO_NITIDO); });
    return false;
  }
  S.saltando = true;
  if (sig.fuente && sig.fuente !== S.fuenteVideo) {
    // el siguiente tramo es de OTRO archivo: se cambia lo que tiene el <video> (hay un instante de carga; es la vista previa)
    ponerFuenteEnVideo(sig.fuente).then((bien) => {
      if (!bien) { S.saltando = false; avisarSinReproduccion(sig.fuente); pausar().then(() => { irA(cuadroDe(sig.inicio), ANCHO_NITIDO); }); return; }
      aplicarVelocidadTramo(sig);
      video.currentTime = sig.desde;
      esperarEvento(video, 'seeked', 3000).then(() => { S.saltando = false; if (S.reproduciendo) video.play().catch(() => {}); });
    });
  } else {
    aplicarVelocidadTramo(sig);
    video.currentTime = sig.desde;
    esperarEvento(video, 'seeked', 1500).then(() => {
      S.saltando = false;
      if (S.reproduciendo && video.paused) video.play().catch(() => {});       // si el tramo anterior llego al final del archivo, el <video> se habia frenado solo
    });
  }
  if (typeof previaInicio === 'function') previaInicio(sig.inicio);
  return true;
}

function bucle() {
  if (!S.reproduciendo) { S.raf = 0; return; }
  if (!S.saltando) {
    const video = el.capaVideo;
    const s = S.segs[S.segIdx];
    const ct = video.currentTime;
    if (s && ct >= s.hasta - 0.004) {
      if (S.segIdx + 1 < S.segs.length) {
        // se acabo este tramo: se salta al siguiente (hay un instante de busqueda; es la vista previa)
        if (!pasarAlSiguienteTramo()) return;
      } else if (S.segs.length > 1 || ct >= s.hasta) {
        // fin del proyecto
        S.raf = 0;
        pausar().then(() => { irA(S.totalCuadros - 1, ANCHO_NITIDO); });
        return;
      }
    }
    const tl = tiempoLineaDeVideo(video.currentTime);
    const k = cuadroDe(tl);
    if (k !== S.cuadro) {
      S.cuadro = k;
      pintarPosicion();
    }
    if (typeof previaTick === 'function') previaTick(tl);
  }
  S.raf = requestAnimationFrame(bucle);
}

async function reproducir() {
  if (!S.info || S.reproduciendo) return;
  const segInicial = S.segs[indiceSegmento(tiempoDe(S.cuadro))];
  if (segInicial && segInicial.fuente && segInicial.fuente !== S.fidPrincipal) {
    // el cursor esta sobre un tramo de otro archivo: se carga ese en el <video>
    if (!(await ponerFuenteEnVideo(segInicial.fuente))) { avisarSinReproduccion(segInicial.fuente); return; }
  } else if (S.fuenteVideo !== S.fidPrincipal && !S.soloAudio) {
    if (!(await ponerFuenteEnVideo(S.fidPrincipal))) { avisarSinReproduccion(S.fidPrincipal); return; }
  }
  if (!(segInicial && segInicial.fuente && segInicial.fuente !== S.fidPrincipal) && !puedeReproducir()) {
    if (S.info.proxy === 'generando') {
      avisar('Todavía estoy preparando la reproducción de este formato. En unos segundos vas a poder darle play.', 'ojo');
    } else {
      avisar('No se puede reproducir con audio este formato (' + (S.info.codec || 'codec desconocido') + '). ' +
             'Movete con las flechas, el espectro y la tira: eso sí funciona.', 'ojo');
    }
    return;
  }
  const video = el.capaVideo;
  try {
    if (video.readyState < 1) {
      await esperarEvento(video, 'loadedmetadata', 4000);
    }
    // Si el cursor esta al final, se vuelve a empezar.
    if (S.cuadro >= S.totalCuadros - 1 && S.totalCuadros > 1) S.cuadro = 0;
    const t = tiempoDe(S.cuadro);
    S.segIdx = indiceSegmento(t);
    const s = S.segs[S.segIdx];
    if (s.rev) {
      avisar('Este tramo está al revés y la vista previa no lo reproduce: recorrelo con las flechas. Se ve bien al exportar.', 'ojo');
      return;
    }
    aplicarVelocidadTramo(s);
    const ts = s.desde + (t - s.inicio) * (s.v || 1);
    if (Math.abs(video.currentTime - ts) > (0.5 / ctxFuente(s.fuente).fps)) {
      video.currentTime = ts;
      await esperarEvento(video, 'seeked', 2000);
    }
    S.saltando = false;
    // El <video> aparece recién cuando ya está en el tiempo correcto:
    // así no se ve el salto al cuadro cero.
    video.hidden = S.soloAudio;
    if (typeof previaInicio === 'function') previaInicio(t);
    await video.play();
    S.reproduciendo = true;
    pintarPlay();
    detenerBucle();
    S.raf = requestAnimationFrame(bucle);
  } catch (e) {
    video.hidden = true;
    S.reproduciendo = false;
    pintarPlay();
    if (typeof previaFin === 'function') previaFin();
    avisar('No se pudo reproducir: ' + mensajeDe(e));
  }
}

async function pausar() {
  if (!S.info) return;
  const video = el.capaVideo;
  video.pause();
  video.playbackRate = 1;
  const estaba = S.reproduciendo;
  S.reproduciendo = false;
  S.saltando = false;
  detenerBucle();
  pintarPlay();
  if (typeof previaFin === 'function') previaFin();
  if (!estaba) { video.hidden = true; return; }

  // Cuadro exacto donde quedó el video. El <video> pausado sigue a la
  // vista mostrando ese mismo fotograma, así que se cambia de capa recién
  // cuando la imagen exacta ya está decodificada: cero parpadeo.
  S.cuadro = cuadroDe(tiempoLineaDeVideo(video.currentTime));
  pintarPosicion();
  await pedirCuadro(S.cuadro, ANCHO_NITIDO);
  if (S.trabajo) { try { await S.trabajo; } catch (e) { /* ya se avisó */ } }
  video.hidden = true;
}

function alternarReproduccion() {
  if (S.reproduciendo) pausar();
  else reproducir();
}

/* ============================================================
   carriles: las miniaturas y el espectro los dibuja edicion.js (por clip, con los cortes aplicados)
   ============================================================ */
function construirTira() {
  if (typeof renderizarVideo === 'function') renderizarVideo();
}

function dibujarOnda() {
  if (typeof renderizarAudios === 'function') renderizarAudios();
}

/* ============================================================
   redibujo al cambiar el tamaño de la ventana
   ============================================================ */
let redibujoPedido = 0;
function programarRedibujo() {
  if (redibujoPedido) return;
  redibujoPedido = requestAnimationFrame(() => {
    redibujoPedido = 0;
    if (!S.info) return;
    construirTira();
    dibujarOnda();
  });
}

if (typeof ResizeObserver === 'function') {
  new ResizeObserver(programarRedibujo).observe(el.carriles);
}
window.addEventListener('resize', programarRedibujo);

/* ============================================================
   navegación por clic y arrastre sobre los dos carriles
   ============================================================ */
el.carriles.addEventListener('pointerdown', (e) => {
  if (!S.info || e.button !== 0) return;
  e.preventDefault();
  S.arrastrando = true;
  el.carriles.classList.add('arrastrando');
  try { el.carriles.setPointerCapture(e.pointerId); } catch (err) { /* sin captura, igual anda */ }
  if (typeof seleccionarEn === 'function') seleccionarEn(e);
  irA(cuadroDeEvento(e), ANCHO_LIVIANO);
});

el.carriles.addEventListener('pointermove', (e) => {
  if (!S.arrastrando) return;
  // Mientras se arrastra: cuadros livianos (270 px), uno solo en vuelo.
  irA(cuadroDeEvento(e), ANCHO_LIVIANO);
});

function soltarCarril(e) {
  if (!S.arrastrando) return;
  S.arrastrando = false;
  el.carriles.classList.remove('arrastrando');
  // Al soltar: el cuadro nítido.
  const n = cuadroDeEvento(e);
  S.cuadro = acotar(n);
  pintarPosicion();
  if (S.reproduciendo) saltarVideoA(tiempoDe(S.cuadro));
  else pedirCuadro(S.cuadro, ANCHO_NITIDO);
}

el.carriles.addEventListener('pointerup', soltarCarril);
el.carriles.addEventListener('pointercancel', soltarCarril);

/* ============================================================
   botones
   ============================================================ */

el.btnAbrir.addEventListener('click', elegirYAbrir);
el.btnAbrirBarra.addEventListener('click', elegirYAbrir);

el.btnInicio.addEventListener('click', () => irA(0, ANCHO_NITIDO));
el.btnFin.addEventListener('click', () => irA(S.totalCuadros - 1, ANCHO_NITIDO));
el.btnCuadroAtras.addEventListener('click', () => irA(S.cuadro - 1, ANCHO_NITIDO));
el.btnCuadroAdelante.addEventListener('click', () => irA(S.cuadro + 1, ANCHO_NITIDO));
el.btnSegAtras.addEventListener('click', () => irA(cuadroEnSegundos(-1), ANCHO_NITIDO));
el.btnSegAdelante.addEventListener('click', () => irA(cuadroEnSegundos(1), ANCHO_NITIDO));
el.btnPlay.addEventListener('click', alternarReproduccion);

el.capaVideo.addEventListener('ended', () => {
  // el archivo se acabo: si el tramo que sigue es de otro archivo (o de otro punto de este), se sigue; si no, fin
  if (S.reproduciendo && !S.saltando && S.segIdx + 1 < S.segs.length) { pasarAlSiguienteTramo(); return; }
  pausar();
});
el.capaVideo.addEventListener('error', () => {
  if (!S.info || !S.info.reproducible) return;
  el.capaVideo.hidden = true;
  S.reproduciendo = false;
  detenerBucle();
  pintarPlay();
  avisar('El reproductor no pudo cargar el video. Cuadro por cuadro, miniaturas y espectro siguen andando.', 'ojo');
});

/* ============================================================
   atajos de teclado
   ============================================================ */
window.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  const foco = e.target;
  if (foco && (foco.tagName === 'INPUT' || foco.tagName === 'TEXTAREA' || foco.tagName === 'SELECT' || foco.isContentEditable)) return;
  if (!S.info) return;

  switch (e.code) {
    case 'ArrowLeft':
      irA(e.shiftKey ? cuadroEnSegundos(-1) : S.cuadro - 1, ANCHO_NITIDO);
      break;
    case 'ArrowRight':
      irA(e.shiftKey ? cuadroEnSegundos(1) : S.cuadro + 1, ANCHO_NITIDO);
      break;
    case 'Space':
      alternarReproduccion();
      break;
    case 'Home':
      irA(0, ANCHO_NITIDO);
      break;
    case 'End':
      irA(S.totalCuadros - 1, ANCHO_NITIDO);
      break;
    case 'KeyJ':
      // Sin reproducción hacia atrás: J retrocede un segundo y pausa.
      if (S.reproduciendo) pausar().then(() => irA(cuadroEnSegundos(-1), ANCHO_NITIDO));
      else irA(cuadroEnSegundos(-1), ANCHO_NITIDO);
      break;
    case 'KeyK':
      pausar();
      break;
    case 'KeyL':
      if (!S.reproduciendo) reproducir();
      break;
    default:
      return;   // tecla que no manejamos: no se bloquea
  }
  e.preventDefault();
});

/* ============================================================
   arrastrar y soltar un archivo sobre la ventana
   ============================================================ */
function frenar(e) {
  e.preventDefault();
  e.stopPropagation();
}

['dragenter', 'dragover'].forEach((nombre) => {
  window.addEventListener(nombre, (e) => {
    frenar(e);
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    el.zonaSuelta.hidden = false;
  });
});

window.addEventListener('dragleave', (e) => {
  if (!e.relatedTarget) el.zonaSuelta.hidden = true;
});

window.addEventListener('drop', (e) => {
  frenar(e);
  el.zonaSuelta.hidden = true;
  const archivos = e.dataTransfer && e.dataTransfer.files;
  const archivo = archivos && archivos.length ? archivos[0] : null;
  const ruta = archivo && archivo.path ? archivo.path : '';
  if (ruta) { (typeof pedirAbrir === 'function' ? pedirAbrir : abrir)(ruta); return; }      // pedirAbrir pregunta por los cambios sin guardar
  // En la ventana nativa la ruta la lee Python y abre el archivo por su cuenta.
  if (window.__soltarEnPython) return;
  avisar('Desde el navegador no puedo leer la ruta de un archivo soltado. Usá el botón Abrir.', 'ojo');
});

/* ============================================================
   arranque
   ============================================================ */
pintarPlay();

// Latido: avisa al motor que la pagina sigue abierta. En el modo navegador, cuando
// se cierra la pestaña y deja de llegar, el motor se apaga solo.
vigilarAcel(false);
llamar('latido').catch(() => {});
setInterval(() => { llamar('latido').catch(() => {}); }, 5000);

// Archivo pasado por linea de comandos (python app.py video.mp4).
llamar('inicial').then((r) => { if (r && r.ruta) abrir(r.ruta); }).catch(() => {});

/* ============================================================
   gancho para app.py: abrir un archivo pasado por linea de comandos
   (python app.py "C:\ruta\video.mp4")
   ============================================================ */
window.abrirDesdePython = function (ruta) {
  if (typeof ruta === 'string' && ruta) abrir(ruta);
};
