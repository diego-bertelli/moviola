/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — edicion
   La linea de tiempo con clips, las herramientas (dividir, borrar, marcas, deshacer), el inspector
   (fundidos, volumen) y la vista previa de los fundidos y del audio extra.
   Se carga despues de app.js y usa su estado (S, L, el, llamar, avisar...).
   El modelo de edicion vive en el motor (motor/proyecto.py): aca solo se piden operaciones y se
   dibuja el proyecto que vuelve. NUNCA se guardan referencias a clips: despues de cada operacion
   (y de cada error) el motor manda el proyecto completo.
   ============================================================ */
'use strict';

const ed = {
  barra:       $('edicion'),
  btnEntrada:  $('btn-entrada'),
  btnSalida:   $('btn-salida'),
  btnLimpiar:  $('btn-limpiar-marcas'),
  btnDividir:  $('btn-dividir'),
  btnBorrar:   $('btn-borrar'),
  btnRecortar: $('btn-recortar'),
  btnDeshacer: $('btn-deshacer'),
  btnRehacer:  $('btn-rehacer'),
  btnAudio:    $('btn-agregar-audio'),
  inspector:   $('inspector'),
  titulo:      $('inspector-titulo'),
  fadeIn:      $('fade-in'),
  fadeInVal:   $('fade-in-valor'),
  fadeOut:     $('fade-out'),
  fadeOutVal:  $('fade-out-valor'),
  curva:       $('fade-curva'),
  campoColor:  $('campo-color'),
  color:       $('fade-color'),
  campoVol:    $('campo-volumen'),
  volumen:     $('volumen'),
  volumenVal:  $('volumen-valor'),
  btnSilenciar: $('btn-silenciar'),
  btnSeparar:  $('btn-separar'),
  btnMoverAntes: $('btn-mover-antes'),
  btnMoverDespues: $('btn-mover-despues'),
  marcas:      $('marcas'),
  extras:      $('extras'),
  fundido:     $('fundido-visor'),
  pistaA1:     $('pista-audio')
};

/* ============================================================
   consultas sobre el proyecto
   ============================================================ */
function pistaDe(id) {
  return S.proy ? S.proy.pistas.find((p) => p.id === id) : null;
}

// Un clip dura en la linea de tiempo el tramo de la fuente dividido por la velocidad.
function finClip(c) { return c.inicio + (c.hasta - c.desde) / (c.velocidad || 1); }
function largoClip(c) { return (c.hasta - c.desde) / (c.velocidad || 1); }
function largoFuente(c) { return c.hasta - c.desde; }          // lo que usa de la fuente (para las miniaturas y el espectro)
function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

/** Clip de una pista en el segundo t de la linea de tiempo (o null si hay un hueco). */
function clipEn(pista, t) {
  if (!pista) return null;
  for (const c of pista.clips) {
    if (t >= c.inicio - 1e-6 && t < finClip(c) - 1e-6) return c;
  }
  const u = pista.clips[pista.clips.length - 1];
  return (u && Math.abs(t - finClip(u)) < 1e-6) ? u : null;
}

function buscarClip(id) {
  if (!S.proy) return null;
  for (const p of S.proy.pistas) {
    for (const c of p.clips) if (c.id === id) return { pista: p, clip: c };
  }
  return null;
}

function clipsDelGrupo(grupo) {
  const out = [];
  if (!S.proy) return out;
  for (const p of S.proy.pistas) {
    for (const c of p.clips) if (c.grupo === grupo) out.push({ pista: p, clip: c });
  }
  return out;
}

/** Los clips que estan elegidos (el video y su audio, o un audio extra). */
function elegidos() {
  if (!S.sel) return [];
  const g = clipsDelGrupo(S.sel.grupo);
  return g.length ? g : (buscarClip(S.sel.clip) ? [buscarClip(S.sel.clip)] : []);
}

/* ============================================================
   fundidos: la misma cuenta para dibujar la onda y para la vista previa
   (aproximada: el resultado exportado usa las curvas de ffmpeg)
   ============================================================ */
function curva(x, nombre) {
  x = clamp01(x);
  switch (nombre) {
    case 'qsin': return Math.sin(x * Math.PI / 2);
    case 'hsin': return (1 - Math.cos(x * Math.PI)) / 2;
    case 'log': return Math.log10(1 + 9 * x);
    case 'exp': return (Math.pow(10, x) - 1) / 9;
    case 'par': return x * x;
    case 'cub': return x * x * x;
    case 'squ': return Math.sqrt(x);
    default: return x;
  }
}

/** Ganancia (0 a 1) que le aplican los fundidos al clip c en el segundo t de la linea de tiempo. */
function gananciaFundido(c, t) {
  const largo = largoClip(c);
  const pos = Math.min(Math.max(t - c.inicio, 0), largo);
  let g = 1;
  if (c.fade_in > 1e-6 && pos < c.fade_in) g *= curva(pos / c.fade_in, c.curva_in);
  if (c.fade_out > 1e-6 && pos > largo - c.fade_out) g *= curva((largo - pos) / c.fade_out, c.curva_out);
  return g;
}

/* ============================================================
   carril de video: un bloque por clip, con sus miniaturas
   ============================================================ */
/** Las miniaturas del archivo `fid` (el principal, o uno de los otros videos del proyecto), o null si no hay. */
function tiraDe(fid) {
  if (!fid || fid === S.fidPrincipal) {
    return (S.tira && S.tiraCantidad && S.tiraAnchoMini)
      ? { img: S.tira, cant: S.tiraCantidad, ancho: S.tiraAnchoMini, alto: S.tiraAltoMini, dur: S.srcDuracion } : null;
  }
  const m = S.medios[fid];
  return (m && m.tira && m.tira_cantidad && m.tira_ancho_mini)
    ? { img: m.tira, cant: m.tira_cantidad, ancho: m.tira_ancho_mini, alto: Math.max(1, m.tira_alto_mini), dur: m.duracion } : null;
}

function renderizarVideo() {
  const caja = el.tira;
  caja.textContent = '';
  const v1 = pistaDe('V1');
  if (!v1 || !v1.clips.length) return;

  const ancho = caja.clientWidth;
  const alto = caja.clientHeight;
  if (ancho < 8 || alto < 4) return;
  const dur = Math.max(S.duracion, 1e-6);

  const rotulo = document.createElement('span');
  rotulo.className = 'carril__rotulo';
  rotulo.textContent = 'V1';

  const fragmento = document.createDocumentFragment();
  v1.clips.forEach((c) => {
    const x0 = Math.round(c.inicio / dur * ancho);
    const x1 = Math.round(finClip(c) / dur * ancho);
    const w = Math.max(1, x1 - x0);
    const bloque = document.createElement('div');
    bloque.className = 'clip clip--video';
    bloque.dataset.clip = c.id;
    bloque.dataset.grupo = c.grupo;
    bloque.style.left = x0 + 'px';
    bloque.style.width = w + 'px';
    if (S.sel && S.sel.grupo === c.grupo) bloque.classList.add('clip--sel');

    const T = tiraDe(c.fuente);            // cada clip usa las miniaturas de SU archivo
    if (T) {
      const fondo = 'url("' + T.img + '")';
      const ideal = Math.max(8, T.ancho * (alto / T.alto));
      const celdas = Math.max(1, Math.round(w / ideal));
      const anchoCelda = w / celdas;
      const tam = (T.cant * anchoCelda).toFixed(2) + 'px 100%';
      for (let k = 0; k < celdas; k++) {
        // el cuadro de la fuente que esta en el centro de esta celda
        const frac = (k + 0.5) / celdas;
        const ts = c.desde + (c.reversa ? 1 - frac : frac) * largoFuente(c);
        const indice = Math.min(T.cant - 1, Math.max(0, Math.floor(ts / Math.max(T.dur, 1e-6) * T.cant)));
        const d = document.createElement('div');
        d.className = 'mini';
        d.style.width = (Math.round((k + 1) * anchoCelda) - Math.round(k * anchoCelda)) + 'px';
        d.style.backgroundImage = fondo;
        d.style.backgroundSize = tam;
        d.style.backgroundPosition = (-indice * anchoCelda).toFixed(2) + 'px 0';
        bloque.appendChild(d);
      }
    } else if (!caja.querySelector('.tira__vacia')) {
      const p = document.createElement('p');
      p.className = 'tira__vacia';
      p.textContent = 'Sin miniaturas';
      caja.appendChild(p);
    }
    if ((c.velocidad || 1) !== 1 || c.reversa) {
      const ve = document.createElement('span');
      ve.className = 'clip__vel';
      ve.textContent = (c.reversa ? '◀ ' : '') + ((c.velocidad || 1) !== 1 ? String(Number((c.velocidad).toFixed(2))).replace('.', ',') + '×' : 'reversa');
      ve.title = 'Velocidad ' + String(Number((c.velocidad || 1).toFixed(2))).replace('.', ',') + '×' + (c.reversa ? ', al revés' : '');
      bloque.appendChild(ve);
    }
    if (c.transicion) {
      const tr = document.createElement('span');
      tr.className = 'clip__trans';
      tr.textContent = '⇄';
      tr.title = 'Transición de entrada: ' + String(c.transicion.tipo).replace(/_/g, ' ') + ', ' + c.transicion.duracion.toFixed(1).replace('.', ',') + ' s';
      bloque.appendChild(tr);
    }
    if (c.efectos && c.efectos.length) {
      const fx = document.createElement('span');
      fx.className = 'clip__fx';
      fx.textContent = 'fx';
      fx.title = c.efectos.length + (c.efectos.length === 1 ? ' efecto' : ' efectos');
      bloque.appendChild(fx);
    }
    // los fundidos se ven como un degradado en el borde del clip
    const largo = Math.max(largoClip(c), 1e-6);
    ['in', 'out'].forEach((lado) => {
      const seg = lado === 'in' ? c.fade_in : c.fade_out;
      if (seg > 1e-6) {
        const f = document.createElement('div');
        f.className = 'clip__fundido clip__fundido--' + lado + (c.color_fundido === 'blanco' ? ' clip__fundido--blanco' : '');
        f.style.width = (seg / largo * 100).toFixed(2) + '%';
        bloque.appendChild(f);
      }
    });
    fragmento.appendChild(bloque);
  });
  caja.appendChild(fragmento);
  caja.appendChild(rotulo);
}

/* ============================================================
   carriles de audio: el espectro de cada clip, con volumen y fundidos
   ============================================================ */
function picosDe(fid) {
  if (S.proy && S.proy.fuentes[fid] && fid === primeraFuente()) return S.picos;
  return S.picosFuente[fid] || null;
}

function primeraFuente() {
  return S.proy ? Object.keys(S.proy.fuentes)[0] : null;
}

async function cargarPicos(fid) {
  if (S.picosFuente[fid] !== undefined) return;
  S.picosFuente[fid] = null;
  try {
    const r = await llamar('picos_fuente', [fid]);
    S.picosFuente[fid] = Array.isArray(r.picos) ? r.picos : [];
  } catch (e) {
    S.picosFuente[fid] = [];
  }
  renderizarAudios();
}

function dibujarPistaAudio(lienzo, pista) {
  const caja = lienzo.getBoundingClientRect();
  const w = Math.max(1, Math.floor(caja.width));
  const h = Math.max(1, Math.floor(caja.height));
  const dpr = window.devicePixelRatio || 1;
  lienzo.width = Math.round(w * dpr);
  lienzo.height = Math.round(h * dpr);
  const ctx = lienzo.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const medio = Math.round(h / 2) + 0.5;
  ctx.fillStyle = colorCss('--onda-cero', '#3E463A');
  ctx.fillRect(0, Math.round(h / 2), w, 1);

  const dur = Math.max(S.duracion, 1e-6);
  const amp = (h / 2) - 2;
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  const alta = colorCss('--onda-alta', '#AABDA2');
  const baja = colorCss('--onda-baja', '#67775F');
  grad.addColorStop(0, alta);
  grad.addColorStop(0.5, baja);
  grad.addColorStop(1, alta);
  const filo = colorCss('--filo', '#14170F');
  const lampara = colorCss('--coral', '#FF6D5A');

  pista.clips.forEach((c) => {
    const picos = picosDe(c.fuente);
    const f = S.proy.fuentes[c.fuente];
    const x0 = c.inicio / dur * w;
    const x1 = finClip(c) / dur * w;
    const sel = !!(S.sel && (S.sel.grupo === c.grupo || S.sel.clip === c.id));

    if (picos && picos.length && f) {
      const P = picos.length;
      const durF = Math.max(f.duracion, 1e-6);
      const largo = largoFuente(c);
      const ancho = Math.max(x1 - x0, 1e-6);
      ctx.globalAlpha = pista.silenciada ? 0.25 : 1;
      ctx.fillStyle = grad;
      for (let x = Math.floor(x0); x < Math.ceil(x1) && x < w; x++) {
        let f0 = clamp01((x - x0) / ancho);
        let f1 = clamp01((x + 1 - x0) / ancho);
        if (c.reversa) { const g0 = 1 - f1; f1 = 1 - f0; f0 = g0; }        // al revés, el espectro se lee de atras para adelante
        let i0 = Math.floor((c.desde + f0 * largo) / durF * P);
        let i1 = Math.ceil((c.desde + f1 * largo) / durF * P);
        if (i1 <= i0) i1 = i0 + 1;
        if (i0 < 0) i0 = 0;
        if (i1 > P) i1 = P;
        let mx = 0;
        let mn = 0;
        for (let i = i0; i < i1; i++) {
          const par = picos[i];
          if (!par) continue;
          if (par[1] > mx) mx = par[1];
          if (par[0] < mn) mn = par[0];
        }
        // la altura refleja el volumen y los fundidos del clip
        const g = Math.min(c.volumen, 1.6) * gananciaFundido(c, c.inicio + ((c.reversa ? 1 - (f0 + f1) / 2 : (f0 + f1) / 2)) * largoClip(c));
        const arriba = Math.min(1, mx * g) * amp;
        const abajo = Math.min(1, -mn * g) * amp;
        ctx.fillRect(x, medio - arriba, 1, Math.max(1, arriba + abajo));
      }
      ctx.globalAlpha = 1;
    }
    // borde del clip
    ctx.fillStyle = filo;
    ctx.fillRect(Math.round(x0), 0, 1, h);
    if (c.efectos && c.efectos.length && x1 - x0 > 26) {
      ctx.font = '700 10px "Segoe UI Variable Text", "Segoe UI", sans-serif';
      ctx.fillStyle = lampara;
      ctx.fillText('fx', x1 - 18, 14);
    }
    if (sel) {
      ctx.fillStyle = 'rgba(255, 109, 90, 0.16)';
      ctx.fillRect(x0, 0, x1 - x0, h);
      ctx.strokeStyle = lampara;
      ctx.lineWidth = 2;
      ctx.strokeRect(x0 + 1, 1, Math.max(0, x1 - x0 - 2), h - 2);
    }
  });
}

function renderizarAudios() {
  if (!S.proy) return;
  // A1: el carril de siempre
  const a1 = pistaDe('A1');
  el.sinAudio.hidden = !!(a1 && a1.clips.length && S.picos.length);
  el.onda.hidden = !(a1 && a1.clips.length && S.picos.length);
  if (a1 && a1.clips.length && S.picos.length) dibujarPistaAudio(el.onda, a1);

  // audios extra: un carril por pista
  const extras = S.proy.pistas.filter((p) => p.tipo === 'audio' && p.id !== 'A1');
  const existentes = new Map();
  ed.extras.querySelectorAll('.pista-extra').forEach((d) => existentes.set(d.dataset.carril, d));
  existentes.forEach((d, id) => { if (!extras.find((p) => p.id === id)) d.remove(); });
  extras.forEach((p) => {
    let d = existentes.get(p.id);
    if (!d) {
      d = document.createElement('div');
      d.className = 'pista-extra';
      d.dataset.carril = p.id;
      const lienzo = document.createElement('canvas');
      const r = document.createElement('span');
      r.className = 'carril__rotulo';
      d.appendChild(lienzo);
      d.appendChild(r);
      ed.extras.appendChild(d);
    }
    d.querySelector('.carril__rotulo').textContent = p.id + (p.silenciada ? ' · silenciada' : '');
    p.clips.forEach((c) => cargarPicos(c.fuente));
    dibujarPistaAudio(d.querySelector('canvas'), p);
  });
}

/* ============================================================
   seleccion de clips (clic en la linea de tiempo)
   ============================================================ */
function seleccionarEn(e) {
  if (!S.proy) return;
  const t = fraccionDeEvento(e) * S.duracion;
  const carril = e.target && e.target.closest ? e.target.closest('[data-carril]') : null;
  let c = null;
  if (carril) c = clipEn(pistaDe(carril.dataset.carril), t);
  S.sel = c ? { grupo: c.grupo, clip: c.id } : null;
  actualizarSeleccion();
}

function actualizarSeleccion() {
  el.tira.querySelectorAll('.clip').forEach((b) => {
    b.classList.toggle('clip--sel', !!(S.sel && b.dataset.grupo === S.sel.grupo));
  });
  renderizarAudios();
  pintarInspector();
  actualizarHerramientas();
}

/* ============================================================
   marcas de entrada y salida
   ============================================================ */
function pintarMarcas() {
  ed.marcas.textContent = '';
  const dur = Math.max(S.duracion, 1e-6);
  const a = S.marcaIn;
  const b = S.marcaOut;
  if (a != null && b != null) {
    const d = document.createElement('div');
    d.className = 'rango';
    const i = Math.min(a, b);
    const o = Math.max(a, b);
    d.style.left = (i / dur * 100) + '%';
    d.style.width = ((o - i) / dur * 100) + '%';
    ed.marcas.appendChild(d);
  } else if (a != null || b != null) {
    const d = document.createElement('div');
    d.className = 'marca-corte';
    d.style.left = ((a != null ? a : b) / dur * 100) + '%';
    d.textContent = a != null ? 'E' : 'S';
    ed.marcas.appendChild(d);
  }
}

function marcarEntrada() {
  if (!S.proy) return;
  S.marcaIn = tiempoDe(S.cuadro);
  if (S.marcaOut != null && S.marcaOut <= S.marcaIn) S.marcaOut = null;
  pintarMarcas();
  actualizarHerramientas();
}

function marcarSalida() {
  if (!S.proy) return;
  S.marcaOut = tiempoDe(S.cuadro);
  if (S.marcaIn != null && S.marcaIn >= S.marcaOut) S.marcaIn = null;
  pintarMarcas();
  actualizarHerramientas();
}

function limpiarMarcas() {
  S.marcaIn = S.marcaOut = null;
  pintarMarcas();
  actualizarHerramientas();
}

/* ============================================================
   operaciones
   ============================================================ */
// Las operaciones salen de a una y en orden: dos pedidos en vuelo podrian responder al reves y dejar en pantalla
// un proyecto viejo (pasa al mantener apretada una tecla).
let colaOperar = Promise.resolve();
function operar(nombre, args) {
  const hecho = colaOperar.then(() => operarYa(nombre, args));
  colaOperar = hecho.catch(() => {});
  return hecho;
}

async function operarYa(nombre, args) {
  let r;
  try {
    r = await llamar('editar_' + nombre, args || []);
  } catch (e) {
    avisar('No pude hacer ese cambio: ' + mensajeDe(e), 'ojo');
    return null;
  }
  if (r.proyecto) aplicarProyecto(r.proyecto);
  if (r.error) {
    avisar(r.error, 'ojo');
    return null;
  }
  return r;
}

async function accionDividir() {
  if (!S.proy) return;
  await operar('dividir', [tiempoDe(S.cuadro)]);
}

async function accionBorrar() {
  if (!S.proy) return;
  if (S.marcaIn != null && S.marcaOut != null) {
    const r = await operar('borrar_rango', [Math.min(S.marcaIn, S.marcaOut), Math.max(S.marcaIn, S.marcaOut)]);
    if (r) limpiarMarcas();
    return;
  }
  const clips = elegidos();
  if (!clips.length) {
    avisar('Elegí un clip con un clic en la línea de tiempo, o marcá una entrada (I) y una salida (O).', 'ojo');
    return;
  }
  const soloExtra = clips.length === 1 && clips[0].pista.id !== 'V1' && clips[0].pista.id !== 'A1';
  const r = soloExtra ? await operar('eliminar_clip', [clips[0].clip.id]) : await operar('borrar_grupo', [S.sel.grupo]);
  if (r) S.sel = null;
  actualizarSeleccion();
}

async function accionRecortar() {
  if (S.marcaIn == null || S.marcaOut == null) {
    avisar('Marcá una entrada (I) y una salida (O) para quedarte solo con ese tramo.', 'ojo');
    return;
  }
  const r = await operar('recortar_a', [Math.min(S.marcaIn, S.marcaOut), Math.max(S.marcaIn, S.marcaOut)]);
  if (r) limpiarMarcas();
}

async function accionAgregarAudio() {
  if (!S.proy) return;
  let r;
  try {
    r = await llamar('elegir_archivo');
  } catch (e) {
    avisar('No pude abrir el selector de archivos.');
    return;
  }
  if (!r || r.cancelado) return;
  if (r.error) { avisar(r.error); return; }
  try {
    r = await llamar('agregar_audio', [r.ruta, tiempoDe(S.cuadro)]);
  } catch (e) {
    avisar('No pude agregar ese audio: ' + mensajeDe(e));
    return;
  }
  if (r.proyecto) aplicarProyecto(r.proyecto);
  if (r.error) { avisar(r.error, 'ojo'); return; }
  const f = S.proy.fuentes[r.fuente];
  if (f && !f.web_compatible) {
    avisar('Ese audio (' + (f.codec || 'formato desconocido') + ') no se puede escuchar desde esta ventana, pero va a sonar en lo que exportes.', 'ojo');
  }
  S.sel = { grupo: r.proyecto.pistas.flatMap((p) => p.clips).find((c) => c.id === r.clip).grupo, clip: r.clip };
  actualizarSeleccion();
}

/* ============================================================
   herramientas
   ============================================================ */
function actualizarHerramientas() {
  const p = S.proy;
  const hay = !!p;
  const rango = S.marcaIn != null && S.marcaOut != null;
  ed.btnDividir.disabled = !hay;
  ed.btnBorrar.disabled = !hay || !(rango || S.sel);
  ed.btnRecortar.disabled = !hay || !rango;
  ed.btnEntrada.classList.toggle('herr--activa', S.marcaIn != null);
  ed.btnSalida.classList.toggle('herr--activa', S.marcaOut != null);
  ed.btnLimpiar.disabled = S.marcaIn == null && S.marcaOut == null;
  ed.btnDeshacer.disabled = !hay || !p.puede_deshacer;
  ed.btnRehacer.disabled = !hay || !p.puede_rehacer;
  ed.btnAudio.disabled = !hay;
  const txt = $('btn-borrar-txt');          // el boton lleva un icono: solo cambia la etiqueta
  if (txt) txt.textContent = rango ? 'Borrar tramo' : 'Borrar';
}

/* ============================================================
   inspector: fundidos y volumen del clip elegido
   ============================================================ */
function pintarInspector() {
  const cs = elegidos();
  if (!cs.length) { ed.inspector.hidden = true; return; }
  ed.inspector.hidden = false;
  const video = cs.find((x) => x.pista.tipo === 'video');
  const audio = cs.find((x) => x.pista.tipo === 'audio');
  const base = (video || audio).clip;
  const largo = largoClip(base);
  const tope = Math.max(0.1, Math.min(10, largo));
  ed.titulo.textContent = video ? 'Clip de video y su audio' : ('Audio ' + audio.pista.id);
  [[ed.fadeIn, ed.fadeInVal, base.fade_in], [ed.fadeOut, ed.fadeOutVal, base.fade_out]].forEach((x) => {
    x[0].max = String(tope);
    x[0].value = String(x[2]);
    x[1].textContent = x[2].toFixed(1).replace('.', ',') + ' s';
  });
  ed.curva.value = base.curva_in;
  ed.campoColor.hidden = !video;
  ed.color.value = base.color_fundido || 'negro';
  ed.campoVol.hidden = !audio;
  if (audio) {
    const v = Math.round(audio.clip.volumen * 100);
    ed.volumen.value = String(v);
    ed.volumenVal.textContent = v + ' %';
    ed.btnSilenciar.hidden = audio.pista.id !== 'A1';
    ed.btnSilenciar.textContent = audio.pista.silenciada ? 'Activar el audio' : 'Silenciar el audio';
  } else {
    ed.btnSilenciar.hidden = true;
  }
  ed.btnSeparar.hidden = !(video && audio);
  // orden: un clip de V1 se puede pasar antes o despues de su vecino (cambia el orden de los videos)
  const v1 = pistaDe('V1');
  const ix = video && v1 ? v1.clips.findIndex((c) => c.grupo === video.clip.grupo) : -1;
  $('sec-orden').hidden = !(video && v1 && v1.clips.length > 1 && ix >= 0 && video.pista.id === 'V1');
  ed.btnMoverAntes.disabled = ix <= 0;
  ed.btnMoverDespues.disabled = ix < 0 || ix >= (v1 ? v1.clips.length : 0) - 1;
  // las secciones del panel se muestran solo si tienen algo que mostrar para este clip
  $('sec-audio').hidden = !audio;
  $('sec-enlace').hidden = !(video && audio);
}

async function aplicarFundido(lado) {
  const cs = elegidos();
  if (!cs.length) return;
  const campo = lado === 'in' ? ed.fadeIn : ed.fadeOut;
  const seg = parseFloat(campo.value) || 0;
  const g = S.sel.grupo;
  const hayVideo = cs.some((x) => x.pista.tipo === 'video');
  const color = hayVideo ? ed.color.value : null;
  if (hayVideo) await operar('fade_grupo', [g, lado, seg, ed.curva.value, color]);
  else await operar('fade', [cs[0].clip.id, lado, seg, ed.curva.value]);
  pintarInspector();
}

ed.fadeIn.addEventListener('input', () => { ed.fadeInVal.textContent = parseFloat(ed.fadeIn.value).toFixed(1).replace('.', ',') + ' s'; });
ed.fadeOut.addEventListener('input', () => { ed.fadeOutVal.textContent = parseFloat(ed.fadeOut.value).toFixed(1).replace('.', ',') + ' s'; });
// un cambio por vez que se suelta el control (no uno por cada pixel que se arrastra: llenaria el historial)
ed.fadeIn.addEventListener('change', () => { aplicarFundido('in'); });
ed.fadeOut.addEventListener('change', () => { aplicarFundido('out'); });
[ed.curva, ed.color].forEach((c) => c.addEventListener('change', async () => {
  const cs = elegidos();
  if (!cs.length) return;
  const base = cs[0].clip;
  if (base.fade_in > 0) await aplicarFundido('in');
  if (base.fade_out > 0) await aplicarFundido('out');
}));
ed.volumen.addEventListener('input', () => { ed.volumenVal.textContent = ed.volumen.value + ' %'; });
ed.volumen.addEventListener('change', async () => {
  const a = elegidos().find((x) => x.pista.tipo === 'audio');
  if (a) { await operar('volumen', [a.clip.id, parseInt(ed.volumen.value, 10) / 100]); pintarInspector(); }
});
ed.btnSilenciar.addEventListener('click', async () => {
  const a = elegidos().find((x) => x.pista.id === 'A1');
  if (a) { await operar('silenciar', ['A1', !a.pista.silenciada]); pintarInspector(); }
  ed.btnSilenciar.blur();
});
async function moverClip(direccion) {
  const v = elegidos().find((x) => x.pista.id === 'V1');
  const v1 = pistaDe('V1');
  if (!v || !v1) return;
  const ix = v1.clips.findIndex((c) => c.grupo === v.clip.grupo);
  const vecino = v1.clips[ix + direccion];
  if (!vecino) return;
  // el destino es el borde de clip del otro lado del vecino: antes de el (su inicio) o despues de el (su final)
  const destino = direccion < 0 ? vecino.inicio : finClip(vecino);
  const r = await operar('mover_grupo', [v.clip.grupo, destino + (direccion < 0 ? 0.0005 : -0.0005)]);
  if (r) {
    S.sel = { grupo: v.clip.grupo, clip: v.clip.id };
    if (typeof irA === 'function' && typeof r.resultado === 'number') irA(cuadroDe(r.resultado + 0.001), ANCHO_NITIDO);
    pintarInspector();
  }
}
ed.btnMoverAntes.addEventListener('click', () => { moverClip(-1); ed.btnMoverAntes.blur(); });
ed.btnMoverDespues.addEventListener('click', () => { moverClip(1); ed.btnMoverDespues.blur(); });
ed.btnSeparar.addEventListener('click', async () => {
  if (S.sel) { await operar('desenlazar', [S.sel.grupo]); pintarInspector(); }
  ed.btnSeparar.blur();
});

/* ============================================================
   botones y atajos
   ============================================================ */
[
  [ed.btnEntrada, marcarEntrada], [ed.btnSalida, marcarSalida], [ed.btnLimpiar, limpiarMarcas],
  [ed.btnDividir, accionDividir], [ed.btnBorrar, accionBorrar], [ed.btnRecortar, accionRecortar],
  [ed.btnDeshacer, () => operar('deshacer')], [ed.btnRehacer, () => operar('rehacer')],
  [ed.btnAudio, accionAgregarAudio]
].forEach(([boton, accion]) => boton.addEventListener('click', () => { accion(); boton.blur(); }));

window.addEventListener('keydown', (e) => {
  const foco = e.target;
  if (foco && (foco.tagName === 'INPUT' || foco.tagName === 'TEXTAREA' || foco.tagName === 'SELECT' || foco.isContentEditable)) return;
  if (!S.info || !S.proy) return;
  if (e.ctrlKey || e.metaKey) {
    if (e.code === 'KeyZ' && !e.shiftKey) operar('deshacer');
    else if (e.code === 'KeyY' || (e.code === 'KeyZ' && e.shiftKey)) operar('rehacer');
    else return;
    e.preventDefault();
    return;
  }
  if (e.altKey) return;
  // mantener apretada S o Supr no tiene que repetir la operacion
  if (e.repeat && ['KeyI', 'KeyO', 'KeyS', 'Delete', 'Backspace'].includes(e.code)) { e.preventDefault(); return; }
  switch (e.code) {
    case 'KeyI': marcarEntrada(); break;
    case 'KeyO': marcarSalida(); break;
    case 'KeyS': accionDividir(); break;
    case 'Delete':
    case 'Backspace': accionBorrar(); break;
    case 'Escape':
      if (S.marcaIn == null && S.marcaOut == null && !S.sel) return;
      S.sel = null;
      limpiarMarcas();
      actualizarSeleccion();
      break;
    default: return;
  }
  e.preventDefault();
});

/* ============================================================
   al cambiar el proyecto o el cursor
   ============================================================ */
function alActualizarProyecto() {
  const p = S.proy;
  ed.barra.hidden = !p;
  $('props').hidden = !p;
  if (!p) return;
  // la seleccion puede haber desaparecido (se borro, se deshizo)
  if (S.sel && !(clipsDelGrupo(S.sel.grupo).length || buscarClip(S.sel.clip))) S.sel = null;
  // las marcas tienen que caer dentro de lo que queda
  const dur = S.duracion;
  if (S.marcaIn != null && S.marcaIn > dur) S.marcaIn = null;
  if (S.marcaOut != null && S.marcaOut > dur) S.marcaOut = null;
  pintarMarcas();
  pintarInspector();
  actualizarHerramientas();
  // los audios que ya no estan dejan de sonar
  previa.extras.forEach((a, id) => { if (!buscarClip(id)) { a.pause(); previa.extras.delete(id); } });
}

function alMoverCursor() {
  if (!S.reproduciendo) previaEstatica(tiempoDe(S.cuadro));
}

/* ============================================================
   vista previa: fundido de video, volumen, fundido de audio y audios extra
   (el <video> reproduce el original; esto se le suma encima, aproximado)
   ============================================================ */
const previa = { extras: new Map() };

function aplicarFundidoVisor(tl) {
  const v1 = pistaDe('V1');
  const c = clipEn(v1, tl);
  const g = c ? gananciaFundido(c, tl) : 1;
  ed.fundido.style.opacity = String(1 - g);
  ed.fundido.style.background = (c && c.color_fundido === 'blanco') ? '#fff' : '#000';
  if (typeof aplicarEfectosVisor === 'function') aplicarEfectosVisor(c);
}

function previaEstatica(tl) {
  if (!S.proy) return;
  aplicarFundidoVisor(tl);
}

function previaInicio(t) {
  // los audios extra se vuelven a sincronizar en el proximo tick
  previa.extras.forEach((a) => a.pause());
}

function audioExtra(c, f) {
  let a = previa.extras.get(c.id);
  if (!a && f && f.url && f.web_compatible) {
    a = new Audio(f.url);
    a.preload = 'auto';
    previa.extras.set(c.id, a);
  }
  return a || null;
}

function previaTick(tl) {
  if (!S.proy) return;
  aplicarFundidoVisor(tl);
  const video = el.capaVideo;
  // el audio del video (A1): volumen y fundidos
  const a1 = pistaDe('A1');
  const ca = clipEn(a1, tl);
  video.muted = !ca || !!(a1 && a1.silenciada);
  if (ca) video.volume = clamp01(ca.volumen * gananciaFundido(ca, tl));
  // los audios extra
  S.proy.pistas.forEach((p) => {
    if (p.tipo !== 'audio' || p.id === 'A1') return;
    p.clips.forEach((c) => {
      const a = audioExtra(c, S.proy.fuentes[c.fuente]);
      if (!a) return;
      const activo = !p.silenciada && tl >= c.inicio && tl < finClip(c);
      if (activo) {
        a.volume = clamp01(c.volumen * gananciaFundido(c, tl));
        if (a.paused) {
          try { a.currentTime = c.desde + (tl - c.inicio); } catch (e) { /* todavia no cargo */ }
          a.play().catch(() => {});
        }
      } else if (!a.paused) {
        a.pause();
      }
    });
  });
}

function previaFin() {
  previa.extras.forEach((a) => a.pause());
  const video = el.capaVideo;
  video.muted = false;
  video.volume = 1;
  if (S.proy) aplicarFundidoVisor(tiempoDe(S.cuadro));
}

/* ============================================================
   arranque
   ============================================================ */
ed.barra.hidden = true;
