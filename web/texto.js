/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — editar por texto
   Un panel al costado (el video y la linea de tiempo siguen a la vista) con lo que se dice, palabra por palabra. Elegir palabras y apretar
   Supr corta el montaje (editar_palabras_borrar: video, audio y todas las pistas, en un paso de deshacer). Tambien: marcar muletillas,
   acortar pausas largas, corregir una palabra con doble clic y escuchar siguiendo la palabra que suena.
   Las palabras viven en el proyecto (S.proy.subtitulos.palabras, con su tiempo): todo cambio pasa por operar() y entra al historial.
   Se carga despues de subtitulos.js y usa su estado (S, llamar, operar, avisar, tiempoDe, cuadroDe, irA...).
   ============================================================ */
'use strict';

const tx = {
  boton:     $('btn-texto'),
  panel:     $('panel-texto'),
  cerrar:    $('tx-cerrar'),
  vacio:     $('tx-vacio'),
  vacioTexto: $('tx-vacio-texto'),
  vacioCampos: $('tx-vacio-campos'),
  idioma:    $('tx-idioma'),
  transcribir: $('tx-transcribir'),
  prog:      $('tx-prog'),
  progTexto: $('tx-prog-texto'),
  progBarra: $('tx-prog-barra'),
  progCancelar: $('tx-prog-cancelar'),
  desact:    $('tx-desact'),
  alDia:     $('tx-al-dia'),
  herr:      $('tx-herr'),
  escuchar:  $('tx-escuchar'),
  borrar:    $('tx-borrar'),
  deshacer:  $('tx-deshacer'),
  rehacer:   $('tx-rehacer'),
  selTexto:  $('tx-sel'),
  muleMarcar: $('tx-mule-marcar'),
  muleN:     $('tx-mule-n'),
  pausaMin:  $('tx-pausa-min'),
  pausaMinV: $('tx-pausa-min-v'),
  pausaDejar: $('tx-pausa-dejar'),
  pausaDejarV: $('tx-pausa-dejar-v'),
  pausaAcortar: $('tx-pausa-acortar'),
  pausaN:    $('tx-pausa-n'),
  texto:     $('tx-texto'),
  error:     $('tx-error'),
  sel:       new Set(),       // indices (en la lista de palabras) de las elegidas
  ancla:     -1,              // donde empezo la seleccion
  arrastrando: false,
  ocupado:   false,
  rutaAlAbrir: null,
  ahora:     -1,              // la palabra que suena
  temporizador: 0,
  idiomas:   false
};

// Las muletillas que se pueden marcar. Se comparan sin tildes, sin signos y en minusculas.
const MULETILLAS = {
  ehm: { palabras: ['eh', 'ehh', 'ehhh', 'em', 'emm', 'mm', 'mmm', 'hm', 'hmm', 'ah', 'ahh', 'uh', 'uhm', 'um'] },
  osea: { secuencias: [['o', 'sea']] },
  bueno: { palabras: ['bueno'] },
  digamos: { palabras: ['digamos'] },
  tipo: { palabras: ['tipo'] }
};

function palabrasDe() { return (S.proy && S.proy.subtitulos && S.proy.subtitulos.palabras) || []; }
function frasesDeTx() { return (S.proy && S.proy.subtitulos && S.proy.subtitulos.frases) || []; }
function comaTx(n, dec) { return Number(n).toFixed(dec).replace('.', ','); }
function limpia(t) { return String(t).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9ñ]/g, ''); }
function tiempoCortoTx(t) { const s = Math.max(0, Math.round(t)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }

function errorTx(texto) {
  tx.error.hidden = !texto;
  tx.error.textContent = texto || '';
}

/* ---------- pintar el texto ---------- */
function pintarTexto() {
  const ws = palabrasDe();
  tx.texto.textContent = '';
  tx.ahora = -1;
  let parrafo = null;
  const nuevoParrafo = (t) => {
    parrafo = document.createElement('p');
    parrafo.className = 'tx__parrafo';
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tx__tiempo';
    b.textContent = tiempoCortoTx(t);
    b.title = 'Ir a este momento';
    b.addEventListener('click', () => irA(cuadroDe(t)));
    parrafo.appendChild(b);
    tx.texto.appendChild(parrafo);
  };
  ws.forEach((w, i) => {
    const pausa = i > 0 ? w.voz - ws[i - 1].habla : 0;
    if (i === 0 || pausa >= 1.2) nuevoParrafo(w.voz);
    else if (pausa >= 0.6) {
      const c = document.createElement('button');
      c.type = 'button';
      c.className = 'tx__pausa';
      c.dataset.id = ws[i - 1].id;
      c.dataset.largo = String(pausa);
      c.textContent = '⏸ ' + comaTx(pausa, 1) + ' s';
      c.title = 'Acortar esta pausa a ' + comaTx(Math.min(pausa, Number(tx.pausaDejar.value)), 2) + ' s';
      parrafo.appendChild(c);
      parrafo.appendChild(document.createTextNode(' '));
    }
    const s = document.createElement('span');
    s.className = 'tx__pal';
    s.dataset.i = String(i);
    s.textContent = w.texto;
    parrafo.appendChild(s);
    parrafo.appendChild(document.createTextNode(' '));
  });
  pintarSeleccion();
  pintarPausas();
  pintarMuletillasN();
  marcarAhora();
}

function pintarSeleccion() {
  const ws = palabrasDe();
  tx.sel.forEach((i) => { if (i >= ws.length) tx.sel.delete(i); });
  tx.texto.querySelectorAll('.tx__pal').forEach((s) => s.classList.toggle('tx__pal--sel', tx.sel.has(Number(s.dataset.i))));
  const n = tx.sel.size;
  const estancado = !!(S.proy && S.proy.subtitulos_desactualizados);
  tx.borrar.disabled = !n || estancado || tx.ocupado;
  tx.borrar.textContent = n > 1 ? 'Borrar ' + n : 'Borrar';
  let dur = 0;
  tx.sel.forEach((i) => { if (ws[i]) dur += ws[i].fin - ws[i].inicio; });
  tx.selTexto.textContent = n ? n + (n === 1 ? ' palabra' : ' palabras') + ' · ' + comaTx(dur, 1) + ' s' : '';
}

function marcarAhora() {
  const ws = palabrasDe();
  if (!tx.panel || tx.panel.hidden || !ws.length || !S.info) return;
  const t = tiempoDe(S.cuadro);
  let k = -1;
  for (let i = 0; i < ws.length; i++) { if (t >= ws[i].inicio - 1e-6 && t < ws[i].fin - 1e-6) { k = i; break; } }
  if (k === tx.ahora) return;
  const spans = tx.texto.querySelectorAll('.tx__pal');
  if (tx.ahora >= 0 && spans[tx.ahora]) spans[tx.ahora].classList.remove('tx__pal--ahora');
  tx.ahora = k;
  if (k >= 0 && spans[k]) {
    spans[k].classList.add('tx__pal--ahora');
    if (S.reproduciendo) spans[k].scrollIntoView({ block: 'nearest' });
  }
}

/* ---------- elegir palabras ---------- */
function elegirRango(a, b) {
  tx.sel.clear();
  for (let i = Math.min(a, b); i <= Math.max(a, b); i++) tx.sel.add(i);
}

function indiceDe(e) {
  const s = e.target.closest && e.target.closest('.tx__pal');
  return s ? Number(s.dataset.i) : -1;
}

tx.texto.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  const i = indiceDe(e);
  if (i < 0) return;
  if (e.shiftKey && tx.ancla >= 0) elegirRango(tx.ancla, i);
  else if (e.ctrlKey || e.metaKey) { if (tx.sel.has(i)) tx.sel.delete(i); else tx.sel.add(i); tx.ancla = i; }
  else { tx.sel.clear(); tx.sel.add(i); tx.ancla = i; tx.arrastrando = true; }
  e.preventDefault();
  tx.texto.focus();
  pintarSeleccion();
});
tx.texto.addEventListener('mouseover', (e) => {
  if (!tx.arrastrando || !(e.buttons & 1)) return;
  const i = indiceDe(e);
  if (i >= 0) { elegirRango(tx.ancla, i); pintarSeleccion(); }
});
window.addEventListener('mouseup', () => {
  if (!tx.arrastrando) return;
  tx.arrastrando = false;
  const ws = palabrasDe();
  if (tx.sel.size && ws.length) {
    const primera = Math.min(...tx.sel);
    if (ws[primera]) irA(cuadroDe(ws[primera].voz));      // el cursor va a la palabra (si es una sola, o al principio de la tanda)
  }
});
tx.texto.addEventListener('click', (e) => {
  const c = e.target.closest && e.target.closest('.tx__pausa');
  if (c) acortarUna(c.dataset.id, Number(c.dataset.largo));
});
tx.texto.addEventListener('dblclick', (e) => {
  const i = indiceDe(e);
  if (i >= 0) editarPalabra(i, e.target.closest('.tx__pal'));
});

function editarPalabra(i, span) {
  const w = palabrasDe()[i];
  if (!w || !span) return;
  const campo = document.createElement('input');
  campo.type = 'text';
  campo.className = 'tx__editar';
  campo.value = w.texto;
  campo.maxLength = 60;
  campo.size = Math.max(3, w.texto.length + 1);
  campo.setAttribute('aria-label', 'Corregir la palabra');
  let listo = false;
  const terminar = async (guardar) => {
    if (listo) return;
    listo = true;
    const nuevo = campo.value.trim();
    if (guardar && nuevo && nuevo !== w.texto) {
      const r = await operar('palabra_cambiar', [w.id, nuevo]);
      if (!r) pintarTexto();
    } else {
      pintarTexto();
    }
  };
  campo.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); terminar(true); }
    else if (e.key === 'Escape') { e.preventDefault(); terminar(false); }
  });
  campo.addEventListener('blur', () => terminar(true));
  span.textContent = '';
  span.appendChild(campo);
  campo.focus();
  campo.select();
}

/* ---------- borrar ---------- */
async function borrarSeleccion() {
  const ws = palabrasDe();
  const ids = [...tx.sel].map((i) => ws[i] && ws[i].id).filter(Boolean);
  if (!ids.length || tx.ocupado) return;
  errorTx('');
  tx.ocupado = true;
  tx.borrar.disabled = true;
  const primera = Math.min(...tx.sel);
  const r = await operar('palabras_borrar', [ids]);
  tx.ocupado = false;
  if (!r) { pintarSeleccion(); return; }
  tx.sel.clear();
  tx.ancla = -1;
  const res = r.resultado || {};
  avisar('Se sacaron ' + ids.length + (ids.length === 1 ? ' palabra' : ' palabras') + ' (' + comaTx(res.duracion || 0, 1) + ' s). «Deshacer» (Ctrl+Z) las devuelve.', 'info');
  pintarTexto();
  const nueva = palabrasDe()[Math.min(primera, palabrasDe().length - 1)];
  if (nueva) irA(cuadroDe(nueva.voz));
}

/* ---------- muletillas ---------- */
function indicesMuletillas() {
  const ws = palabrasDe();
  const activas = [...tx.panel.querySelectorAll('[data-mule]')].filter((c) => c.checked).map((c) => c.dataset.mule);
  const hallados = new Set();
  const norm = ws.map((w) => limpia(w.texto));
  activas.forEach((clave) => {
    const m = MULETILLAS[clave];
    (m.palabras || []).forEach((p) => { norm.forEach((n, i) => { if (n === p) hallados.add(i); }); });
    (m.secuencias || []).forEach((sec) => {
      for (let i = 0; i + sec.length <= ws.length; i++) {
        if (sec.every((p, k) => norm[i + k] === p)) sec.forEach((_, k) => hallados.add(i + k));
      }
    });
  });
  return [...hallados].sort((a, b) => a - b);
}

function pintarMuletillasN() {
  const n = indicesMuletillas().length;
  tx.muleN.textContent = n ? n + (n === 1 ? ' palabra' : ' palabras') + ' en el texto' : 'No hay ninguna';
  tx.muleMarcar.disabled = !n;
}

function marcarMuletillas() {
  const idx = indicesMuletillas();
  tx.sel = new Set(idx);
  tx.ancla = idx.length ? idx[0] : -1;
  pintarSeleccion();
  const primera = tx.texto.querySelectorAll('.tx__pal')[idx[0]];
  if (primera) primera.scrollIntoView({ block: 'center' });
}

/* ---------- pausas ---------- */
function pausasLargas(minimo) {
  const ws = palabrasDe();
  const out = [];
  for (let i = 0; i + 1 < ws.length; i++) {
    const p = ws[i + 1].voz - ws[i].habla;
    if (p >= minimo - 1e-9) out.push({ id: ws[i].id, largo: p });
  }
  return out;
}

function pintarPausas() {
  tx.pausaMinV.textContent = comaTx(tx.pausaMin.value, 1) + ' s';
  tx.pausaDejarV.textContent = comaTx(tx.pausaDejar.value, 2) + ' s';
  const minimo = Number(tx.pausaMin.value), dejar = Number(tx.pausaDejar.value);
  const ps = dejar < minimo ? pausasLargas(minimo) : [];
  const ahorro = ps.reduce((a, p) => a + (p.largo - dejar), 0);
  tx.pausaN.textContent = ps.length ? ps.length + (ps.length === 1 ? ' pausa' : ' pausas') + ' · se ahorran ' + comaTx(ahorro, 1) + ' s' : (dejar >= minimo ? 'La pausa que queda tiene que ser más corta' : 'No hay pausas así de largas');
  tx.pausaAcortar.disabled = !ps.length || !!(S.proy && S.proy.subtitulos_desactualizados);
}

async function acortarPausas() {
  if (tx.ocupado) return;
  errorTx('');
  tx.ocupado = true;
  const r = await operar('palabras_acortar_pausas', [Number(tx.pausaMin.value), Number(tx.pausaDejar.value), null]);
  tx.ocupado = false;
  if (r) {
    const res = r.resultado || {};
    avisar('Se acortaron ' + res.pausas + (res.pausas === 1 ? ' pausa' : ' pausas') + ' (' + comaTx(res.duracion || 0, 1) + ' s menos). «Deshacer» (Ctrl+Z) las devuelve.', 'info');
  }
}

async function acortarUna(id, largo) {
  if (tx.ocupado || (S.proy && S.proy.subtitulos_desactualizados)) return;
  const dejar = Math.min(Number(tx.pausaDejar.value), largo - 0.05);
  tx.ocupado = true;
  const r = await operar('palabras_acortar_pausas', [Math.max(0.2, largo - 0.001), dejar, [id]]);
  tx.ocupado = false;
  if (r) pintarTexto();
}

/* ---------- transcribir desde aca (cuando todavia no hay palabras) ---------- */
function pintarVacio() {
  const ws = palabrasDe();
  const hayFrases = frasesDeTx().length > 0;
  const estancado = !!(S.proy && S.proy.subtitulos_desactualizados);
  tx.vacio.hidden = ws.length > 0 && !tx.transcribiendo;
  tx.herr.hidden = !ws.length;
  tx.texto.hidden = !ws.length;
  tx.desact.hidden = !(ws.length && estancado);
  if (!ws.length) {
    tx.vacioTexto.textContent = hayFrases
      ? 'Los subtítulos que hay no tienen el tiempo de cada palabra (se escribieron a mano o son de una versión anterior). Volvé a transcribir para editar por texto: las frases actuales se reemplazan (Ctrl+Z las devuelve).'
      : 'Todavía no hay texto. Transcribí el audio y vas a poder editar el video borrando palabras.';
    if (!tx.puedeTranscribir) tx.vacioTexto.textContent = tx.motivoTranscribir || 'No se puede transcribir en esta computadora.';
  }
  tx.vacioCampos.hidden = !!tx.transcribiendo || !tx.puedeTranscribir;
  tx.prog.hidden = !tx.transcribiendo;
}

async function iniciarTranscripcionTx() {
  errorTx('');
  let r;
  try { r = await llamar('transcribir_iniciar', [tx.idioma.value, 32]); } catch (e) { r = { error: 'No pude empezar: ' + mensajeDe(e) }; }
  if (!r || r.error) { errorTx((r && r.error) || 'No pude empezar a transcribir.'); return; }
  tx.transcribiendo = true;
  tx.progBarra.style.width = '0%';
  pintarVacio();
  sondearTx();
}

async function sondearTx() {
  clearTimeout(tx.temporizador);
  let e;
  try { e = await llamar('transcribir_estado'); } catch (err) { e = { estado: 'error', error: 'Perdí la conexión con el motor.' }; }
  if (e.estado === 'transcribiendo') {
    const pct = Math.round((e.progreso || 0) * 100);
    tx.progTexto.textContent = 'Transcribiendo… ' + pct + ' %. La primera vez tarda más (carga el modelo).';
    tx.progBarra.style.width = pct + '%';
    tx.temporizador = setTimeout(sondearTx, 700);
    return;
  }
  tx.transcribiendo = false;
  if (e.estado === 'listo') {
    if (e.montaje_cambio) { errorTx('El video cambió mientras se transcribía. Volvé a transcribir.'); llamar('transcribir_cancelar'); pintarVacio(); return; }
    const r = await operar('subtitulos_poner', [e.frases, e.palabras || []]);
    if (r) avisar(e.frases.length ? 'Listo: ' + (e.palabras || []).length + ' palabras. Elegí las que sobran y apretá Supr.' : 'No se entendió nada. Probá con otro idioma.', 'info');
  } else if (e.estado === 'error') {
    errorTx(e.error || 'No pude transcribir.');
  }
  pintarVacio();
  pintarTexto();
}

/* ---------- abrir y cerrar ---------- */
async function abrirTexto() {
  if (!S.info || !S.proy) return;
  if (!tx.panel.hidden) { tx.texto.focus(); return; }
  let c;
  try { c = await llamar('subtitulos_catalogo'); } catch (e) { c = { error: 'No pude preparar el editor de texto.' }; }
  if (!c || c.error) { avisar((c && c.error) || 'No pude preparar el editor de texto.', 'ojo'); return; }
  tx.puedeTranscribir = !!c.transcripcion.disponible;
  tx.motivoTranscribir = c.transcripcion.motivo || '';
  if (!tx.idiomas) {
    c.catalogo.idiomas.forEach((i) => {
      const o = document.createElement('option');
      o.value = i.valor;
      o.textContent = i.nombre;
      tx.idioma.appendChild(o);
    });
    tx.idioma.value = 'es';
    tx.idiomas = true;
  }
  const e = await llamar('transcribir_estado').catch(() => null);
  tx.transcribiendo = !!(e && e.estado === 'transcribiendo');
  tx.rutaAlAbrir = S.ruta;
  tx.sel.clear();
  tx.ancla = -1;
  errorTx('');
  tx.panel.hidden = false;
  document.body.classList.add('con-texto');
  pintarVacio();
  pintarTexto();
  if (tx.transcribiendo) sondearTx();
  tx.boton.classList.add('herr--marcada');
  (palabrasDe().length ? tx.texto : tx.transcribir).focus();
}

function cerrarTexto() {
  if (tx.panel.hidden) return;
  clearTimeout(tx.temporizador);
  tx.panel.hidden = true;
  document.body.classList.remove('con-texto');
  tx.boton.classList.remove('herr--marcada');
  tx.sel.clear();
}

/* ---------- conexiones ---------- */
tx.boton.addEventListener('click', () => { if (tx.panel.hidden) abrirTexto(); else cerrarTexto(); tx.boton.blur(); });
tx.cerrar.addEventListener('click', cerrarTexto);
tx.transcribir.addEventListener('click', iniciarTranscripcionTx);
tx.progCancelar.addEventListener('click', () => { llamar('transcribir_cancelar'); });
tx.alDia.addEventListener('click', () => operar('subtitulos_al_dia', []));
tx.borrar.addEventListener('click', borrarSeleccion);
tx.deshacer.addEventListener('click', () => operar('deshacer', []));
tx.rehacer.addEventListener('click', () => operar('rehacer', []));
tx.escuchar.addEventListener('click', () => { alternarReproduccion(); tx.escuchar.blur(); });
tx.muleMarcar.addEventListener('click', marcarMuletillas);
tx.panel.querySelectorAll('[data-mule]').forEach((c) => c.addEventListener('change', pintarMuletillasN));
[tx.pausaMin, tx.pausaDejar].forEach((r) => r.addEventListener('input', pintarPausas));
tx.pausaAcortar.addEventListener('click', acortarPausas);

// Teclado: con el panel abierto, Supr borra las palabras elegidas (no el clip), el espacio escucha y las flechas recorren el texto.
window.addEventListener('keydown', (e) => {
  if (tx.panel.hidden) return;
  const enCampo = e.target && /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
  if (enCampo) return;
  const k = e.key;
  if (k === 'Delete' || k === 'Backspace') {
    e.preventDefault();
    e.stopImmediatePropagation();
    if (tx.sel.size) borrarSeleccion();
    else avisar('Elegí primero las palabras que querés sacar.', 'info');
  } else if (k === ' ' && (tx.panel.contains(e.target) || e.target === document.body)) {
    e.preventDefault();
    e.stopImmediatePropagation();
    alternarReproduccion();
  } else if (k === 'Escape') {
    e.stopImmediatePropagation();
    if (tx.sel.size) { tx.sel.clear(); pintarSeleccion(); } else cerrarTexto();
  } else if ((k === 'ArrowLeft' || k === 'ArrowRight') && tx.panel.contains(e.target)) {
    const n = palabrasDe().length;
    if (!n) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const actual = tx.sel.size ? (k === 'ArrowRight' ? Math.max(...tx.sel) : Math.min(...tx.sel)) : (tx.ahora >= 0 ? tx.ahora : 0);
    const nuevo = Math.max(0, Math.min(n - 1, actual + (k === 'ArrowRight' ? 1 : -1)));
    if (e.shiftKey && tx.ancla >= 0) elegirRango(tx.ancla, nuevo);
    else { tx.sel = new Set([nuevo]); tx.ancla = nuevo; }
    pintarSeleccion();
    const s = tx.texto.querySelectorAll('.tx__pal')[nuevo];
    if (s) s.scrollIntoView({ block: 'nearest' });
    const w = palabrasDe()[nuevo];
    if (w && !e.shiftKey) irA(cuadroDe(w.voz));
  }
}, true);

// La palabra que suena sigue al cursor.
const _pintarPosicionTx = pintarPosicion;
pintarPosicion = function () {
  _pintarPosicionTx();
  marcarAhora();
};

// Todo lo que dependa del proyecto se actualiza con el.
const _alActualizarProyectoTx = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoTx) _alActualizarProyectoTx();
  tx.boton.disabled = !S.proy;
  if (!tx.panel.hidden) {
    if (!S.proy || S.ruta !== tx.rutaAlAbrir) { cerrarTexto(); return; }
    pintarVacio();
    pintarTexto();
    tx.deshacer.disabled = !(S.proy && S.proy.puede_deshacer);
    tx.rehacer.disabled = !(S.proy && S.proy.puede_rehacer);
  }
};
tx.boton.disabled = true;
