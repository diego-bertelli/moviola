/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — bajar un video de YouTube
   Un dialogo: la direccion, la calidad, y la confirmacion de que se tiene derecho a usar ese video. El motor corre el yt-dlp que ya este
   instalado (motor/descargas.py): aca se muestra el avance, se puede cancelar y, al terminar, se elige si editarlo, sumarlo al proyecto o
   verlo en su carpeta. Moviola no esquiva ninguna proteccion: si YouTube no deja bajarlo, el motivo se muestra y listo.
   Se carga despues de medios.js y usa su estado (S, llamar, avisar, pedirAbrir, sumarRutas...).
   ============================================================ */
'use strict';

const yt = {
  dlg:       $('dlg-youtube'),
  abrirInicio: $('btn-youtube'),
  abrirMedios: $('btn-youtube-medios'),
  herramienta: $('yt-herramienta'),
  derecho:   $('yt-derecho'),
  url:       $('yt-url'),
  calidad:   $('yt-calidad'),
  calidadCampo: $('yt-calidad-campo'),
  tipo:      'video',            // 'video' (MP4, con la calidad elegida) o 'audio' (solo el sonido, en MP3)
  carpeta:   $('yt-carpeta'),
  error:     $('yt-error'),
  progreso:  $('yt-progreso'),
  progresoTexto: $('yt-progreso-texto'),
  barra:     $('yt-barra'),
  resultado: $('yt-resultado'),
  resultadoTexto: $('yt-resultado-texto'),
  editar:    $('yt-editar'),
  sumar:     $('yt-sumar'),
  mostrar:   $('yt-mostrar'),
  cerrar:    $('yt-cerrar'),
  cancelar:  $('yt-cancelar'),
  bajar:     $('yt-bajar'),
  formulario: $('yt-formulario'),
  puede:     false,
  temporizador: 0,
  ultimo:    null
};

function errorYt(texto) {
  yt.error.hidden = !texto;
  yt.error.textContent = texto || '';
}

function pintarTipo() {
  document.querySelectorAll('[data-yt-tipo]').forEach((b) => {
    const activo = b.dataset.ytTipo === yt.tipo;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('exp__op--activo', activo);
  });
  yt.calidadCampo.hidden = yt.tipo === 'audio';
  yt.bajar.textContent = yt.tipo === 'audio' ? 'Bajar el audio' : 'Bajar el video';
}

function pintarBajar() {
  yt.bajar.disabled = !(yt.puede && yt.derecho.checked && yt.url.value.trim().length > 5);
}

function pintarPaso(paso) {
  yt.formulario.hidden = paso !== 'formulario';
  yt.progreso.hidden = paso !== 'progreso';
  yt.resultado.hidden = paso !== 'resultado';
  yt.bajar.hidden = paso !== 'formulario';
  yt.cancelar.hidden = paso !== 'progreso';
}

async function abrirYoutube() {
  if (yt.dlg.open) return;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  let h;
  try { h = await llamar('descarga_herramienta'); } catch (e) { h = { error: 'No pude preparar la descarga.' }; }
  if (!h || h.error) { avisar((h && h.error) || 'No pude preparar la descarga.'); return; }
  yt.puede = !!h.disponible;
  yt.herramienta.hidden = yt.puede;
  yt.herramienta.textContent = yt.puede ? '' : h.motivo;
  if (!yt.calidad.options.length) {
    h.calidades.filter((c) => c.valor !== 'audio').forEach((c) => {            // «solo el audio» tiene su propio selector
      const o = document.createElement('option');
      o.value = c.valor;
      o.textContent = c.nombre;
      yt.calidad.appendChild(o);
    });
    yt.calidad.value = '1080';
  }
  yt.carpeta.textContent = h.carpeta;
  yt.carpeta.title = h.carpeta;
  yt.derecho.checked = false;
  yt.url.value = '';
  yt.tipo = 'video';
  pintarTipo();
  errorYt('');
  pintarPaso('formulario');
  pintarBajar();
  yt.dlg.showModal();
  yt.url.focus();
}

function cerrarYoutube() {
  clearTimeout(yt.temporizador);
  yt.temporizador = 0;
  if (yt.dlg.open) yt.dlg.close();
}

async function bajarYoutube() {
  errorYt('');
  let r;
  try { r = await llamar('descargar_iniciar', [yt.url.value.trim(), yt.tipo === 'audio' ? 'audio' : yt.calidad.value, yt.derecho.checked === true]); }
  catch (e) { r = { error: 'No pude empezar: ' + mensajeDe(e) }; }
  if (!r || r.error) { errorYt((r && r.error) || 'No pude empezar la descarga.'); return; }
  yt.barra.style.width = '0%';
  yt.progresoTexto.textContent = 'Bajando…';
  pintarPaso('progreso');
  sondearYoutube();
}

async function sondearYoutube() {
  clearTimeout(yt.temporizador);
  let e;
  try { e = await llamar('descargar_estado'); } catch (err) { e = { estado: 'error', error: 'Perdí la conexión con el motor.' }; }
  if (e.estado === 'bajando') {
    const pct = Math.round((e.progreso || 0) * 100);
    yt.barra.style.width = pct + '%';
    yt.progresoTexto.textContent = 'Bajando… ' + pct + ' %';
    yt.temporizador = setTimeout(sondearYoutube, 600);
    return;
  }
  if (e.estado === 'listo') {
    yt.ultimo = e;
    yt.resultadoTexto.textContent = 'Listo: ' + e.nombre;
    yt.sumar.hidden = !(S.proy && (e.es_audio || !S.soloAudio));
    yt.sumar.textContent = e.es_audio ? 'Ponerlo como audio en el cursor' : 'Agregarlo al proyecto';
    pintarPaso('resultado');
    return;
  }
  if (e.estado === 'cancelado') { pintarPaso('formulario'); errorYt('Descarga cancelada.'); return; }
  pintarPaso('formulario');
  errorYt(e.error || 'No pude bajar el video.');
}

async function cancelarYoutube() {
  try { await llamar('descargar_cancelar'); } catch (e) { /* sigue */ }
}

async function editarBajado() {
  if (!yt.ultimo) return;
  const ruta = yt.ultimo.archivo;
  cerrarYoutube();
  await pedirAbrir(ruta);
}

async function sumarBajado() {
  if (!yt.ultimo || !S.proy) return;
  const e = yt.ultimo;
  cerrarYoutube();
  if (e.es_audio) {
    let r;
    try { r = await llamar('agregar_audio', [e.archivo, tiempoDe(S.cuadro)]); } catch (err) { r = { error: 'No pude poner el audio.' }; }
    if (r && r.proyecto) aplicarProyecto(r.proyecto);
    if (!r || r.error) avisar((r && r.error) || 'No pude poner el audio.', 'ojo');
    return;
  }
  await sumarRutas([e.archivo]);
}

/* ---------- conexiones ---------- */
[yt.abrirInicio, yt.abrirMedios].forEach((b) => b.addEventListener('click', () => { abrirYoutube(); b.blur(); }));
yt.derecho.addEventListener('change', pintarBajar);
document.querySelectorAll('[data-yt-tipo]').forEach((b) => b.addEventListener('click', () => { yt.tipo = b.dataset.ytTipo; pintarTipo(); }));
yt.url.addEventListener('input', () => { errorYt(''); pintarBajar(); });
yt.url.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); if (!yt.bajar.disabled) bajarYoutube(); } });
yt.bajar.addEventListener('click', bajarYoutube);
yt.cancelar.addEventListener('click', cancelarYoutube);
yt.cerrar.addEventListener('click', cerrarYoutube);
yt.editar.addEventListener('click', editarBajado);
yt.sumar.addEventListener('click', sumarBajado);
yt.mostrar.addEventListener('click', () => { llamar('descarga_mostrar').then((r) => { if (r && r.error) avisar(r.error, 'ojo'); }); });
yt.dlg.addEventListener('cancel', (e) => { if (!yt.progreso.hidden) e.preventDefault(); });
yt.dlg.addEventListener('close', () => { clearTimeout(yt.temporizador); yt.temporizador = 0; });

window.addEventListener('keydown', (e) => {
  if (yt.dlg.open) e.stopImmediatePropagation();
}, true);

// el boton del panel de medios solo con un proyecto abierto
const _alActualizarProyectoYt = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoYt) _alActualizarProyectoYt();
  yt.abrirMedios.hidden = !S.proy;
};
yt.abrirMedios.hidden = true;
