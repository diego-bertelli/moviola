/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — exportar
   El dialogo "Exportar…": formato (original / 9:16 / 16:9 / 1:1 / solo audio), encuadre, normalizar el
   volumen, carpeta y nombre; el progreso con cancelar; y el resultado.
   Se carga despues de edicion.js y usa su estado (S, llamar, avisar, formatoTiempo...).
   El motor exporta en segundo plano sobre una COPIA del proyecto tomada al apretar "Exportar".
   ============================================================ */
'use strict';

const ex = {
  boton:     $('btn-exportar'),
  dlg:       $('dlg-exportar'),
  armar:     $('exp-armar'),
  progreso:  $('exp-progreso'),
  resultado: $('exp-resultado'),
  campoVideo: $('exp-campo-video'),
  perfilCampo: $('exp-perfil-campo'),
  perfil:    $('exp-perfil'),
  perfilNota: $('exp-perfil-nota'),
  calidadCampo: $('exp-calidad-campo'),
  gifCampo:  $('exp-gif-campo'),
  gifAncho:  $('exp-gif-ancho'),
  gifAnchoVal: $('exp-gif-ancho-valor'),
  gifFps:    $('exp-gif-fps'),
  rotuloAudio: $('exp-rotulo-audio'),
  encuadre:  $('exp-encuadre'),
  foco:      $('exp-foco'),
  focoX:     $('exp-foco-x'),
  focoXVal:  $('exp-foco-x-valor'),
  focoY:     $('exp-foco-y'),
  focoYVal:  $('exp-foco-y-valor'),
  campoSubs: $('exp-campo-subs'),
  subsQuemarCampo: $('exp-subs-quemar-campo'),
  subsQuemar: $('exp-subs-quemar'),
  subsSrt:   $('exp-subs-srt'),
  subsVtt:   $('exp-subs-vtt'),
  campoNorm: $('exp-campo-norm'),
  norm:      $('exp-normalizar'),
  carpeta:   $('exp-carpeta'),
  cambiar:   $('exp-cambiar'),
  nombre:    $('exp-nombre'),
  archivo:   $('exp-archivo'),
  gpu:       $('exp-gpu'),
  error:     $('exp-error'),
  cancelarArmar: $('exp-cancelar-armar'),
  iniciar:   $('exp-iniciar'),
  progresoTexto: $('exp-progreso-texto'),
  barra:     $('exp-barra'),
  cancelarExport: $('exp-cancelar-export'),
  resTitulo: $('exp-resultado-titulo'),
  resLineas: $('exp-resultado-lineas'),
  resAviso:  $('exp-resultado-aviso'),
  mostrar:   $('exp-mostrar'),
  otra:      $('exp-otra'),
  cerrar:    $('exp-cerrar')
};

const FORMATOS_DE_AUDIO = ['wav', 'mp3', 'flac', 'm4a', 'opus', 'ogg'];
const EXT_AUDIO = { wav: '.wav', mp3: '.mp3', flac: '.flac', m4a: '.m4a', opus: '.opus', ogg: '.ogg' };

// Lo que la persona eligio (se recuerda mientras la app esta abierta)
const X = {
  op: null,                 // exportar_opciones
  formato: null,
  perfil: 'mp4_h264',
  calidad: 'alta',
  encuadre: 'recortar',
  carpeta: '',
  ocupado: false,           // hay un pedido al motor en vuelo
  temporizador: 0,          // sondeo del progreso
  pedidoNombre: 0,          // para ignorar respuestas viejas del nombre propuesto
  rutaAlAbrir: null         // el archivo del que se abrio el dialogo
};

function esAudio(f) { return FORMATOS_DE_AUDIO.indexOf(f) >= 0; }
function esVideoConProporcion(f) { return f === 'vertical' || f === 'horizontal' || f === 'cuadrado'; }

function mostrarPaso(paso) {
  ex.armar.hidden = paso !== 'armar';
  ex.progreso.hidden = paso !== 'progreso';
  ex.resultado.hidden = paso !== 'resultado';
}

function mostrarError(texto) {
  ex.error.hidden = !texto;
  ex.error.textContent = texto || '';
}

/* ---------- el formulario ---------- */
function pintarFormato() {
  ex.dlg.querySelectorAll('[data-formato]').forEach((b) => {
    const activo = b.dataset.formato === X.formato;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('exp__op--activo', activo);
  });
  ex.dlg.querySelectorAll('[data-calidad]').forEach((b) => {
    const activo = b.dataset.calidad === X.calidad;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('exp__op--activo', activo);
  });
  const pf = perfilActual();
  const video = !esAudio(X.formato);
  ex.perfilCampo.hidden = !video || !(X.op && X.op.perfiles && X.op.perfiles.length);
  ex.perfilNota.textContent = pf ? pf.nota : '';
  ex.calidadCampo.hidden = !(pf && pf.calidad);
  ex.gifCampo.hidden = !(pf && pf.gif);
  ex.dlg.querySelectorAll('[data-encuadre]').forEach((b) => {
    const activo = b.dataset.encuadre === X.encuadre;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('exp__op--activo', activo);
  });
  const proporcion = esVideoConProporcion(X.formato);
  ex.encuadre.hidden = !proporcion;
  ex.foco.hidden = X.encuadre !== 'recortar';
  ex.gpu.hidden = !(X.op && X.op.gpu && !esAudio(X.formato) && pf && pf.gpu);
}

function perfilActual() {
  return (X.op && X.op.perfiles || []).find((p) => p.clave === X.perfil) || null;
}

function pintarSliders() {
  ex.focoXVal.textContent = ex.focoX.value + ' %';
  ex.focoYVal.textContent = ex.focoY.value + ' %';
  ex.gifAnchoVal.textContent = ex.gifAncho.value + ' px';
}

async function proponerNombre() {
  const pedido = ++X.pedidoNombre;
  if (!X.carpeta || !X.formato) { ex.archivo.textContent = ''; return; }
  let r;
  try { r = await llamar('exportar_destino', [X.carpeta, ex.nombre.value || 'exportado', X.formato, X.perfil]); }
  catch (e) { return; }
  if (pedido !== X.pedidoNombre) return;
  ex.archivo.textContent = r && r.archivo ? 'Se guardará como: ' + nombreDe(r.archivo) : '';
}

function elegirFormato(f) {
  X.formato = f;
  ex.subsQuemarCampo.hidden = esAudio(f);          // un audio no tiene imagen donde quemar nada
  pintarFormato();
  proponerNombre();
}

function prepararFormulario(op) {
  X.op = op;
  // la lista de tipos de archivo sale del motor; se recuerda el que se eligio si todavia existe
  ex.perfil.textContent = '';
  (op.perfiles || []).forEach((p) => {
    const o = document.createElement('option');
    o.value = p.clave;
    o.textContent = p.nombre;
    ex.perfil.appendChild(o);
  });
  if (!(op.perfiles || []).some((p) => p.clave === X.perfil)) X.perfil = 'mp4_h264';
  ex.perfil.value = X.perfil;
  const conVideo = !!op.tiene_video;
  const conAudio = !!op.tiene_audio;
  ex.campoVideo.hidden = !conVideo;
  ex.rotuloAudio.textContent = conVideo ? 'Solo el audio' : 'Formato del audio';
  ex.rotuloAudio.closest('fieldset').hidden = !conAudio;
  ex.campoNorm.hidden = !conAudio;
  if (!conAudio) ex.norm.checked = false;
  // los subtitulos solo se ofrecen si hay frases; quemarlos, solo si se exporta video
  const hayFrases = !!(S.proy && S.proy.subtitulos && S.proy.subtitulos.frases.length);
  ex.campoSubs.hidden = !hayFrases;
  if (!hayFrases) { ex.subsQuemar.checked = false; ex.subsSrt.checked = false; ex.subsVtt.checked = false; }

  // Un formato que recordamos de antes solo vale si el proyecto actual lo puede dar.
  const sirve = (f) => !!f && (esAudio(f) ? conAudio : conVideo);
  if (!sirve(X.formato)) X.formato = conVideo ? 'original' : 'wav';

  if (!X.carpeta) X.carpeta = op.carpeta;
  ex.carpeta.textContent = X.carpeta;
  ex.carpeta.title = X.carpeta;
  ex.nombre.value = op.nombre;
  mostrarError('');
  pintarSliders();
  pintarFormato();
  ex.subsQuemarCampo.hidden = esAudio(X.formato);
  proponerNombre();
}

/* ---------- abrir y cerrar ---------- */
async function abrirExportar() {
  if (!S.info || !S.proy || ex.dlg.open) return;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  let estado, op;
  try {
    [estado, op] = await Promise.all([llamar('exportar_estado'), llamar('exportar_opciones')]);
  } catch (e) {
    avisar('No pude preparar la exportación: ' + mensajeDe(e));
    return;
  }
  if (op && op.error) { avisar(op.error); return; }
  if (!op.disponible) { avisar('El exportador no está disponible en esta instalación.'); return; }
  X.rutaAlAbrir = S.ruta;
  ex.dlg.showModal();
  if (estado && estado.estado === 'exportando') {       // la pagina se recargo con una exportacion en curso
    mostrarPaso('progreso');
    sondear();
    return;
  }
  mostrarPaso('armar');
  prepararFormulario(op);
  ex.iniciar.focus();
}

function cerrarExportar() {
  clearTimeout(X.temporizador);
  X.temporizador = 0;
  if (ex.dlg.open) ex.dlg.close();
}

/* ---------- exportar ---------- */
async function iniciar() {
  if (X.ocupado) return;
  mostrarError('');
  const opciones = {
    formato: X.formato,
    encuadre: X.encuadre,
    foco: [Number(ex.focoX.value) / 100, Number(ex.focoY.value) / 100],
    normalizar: !ex.campoNorm.hidden && ex.norm.checked,
    perfil: esAudio(X.formato) ? undefined : X.perfil,
    calidad: X.calidad,
    gif: (!esAudio(X.formato) && X.perfil === 'gif') ? { ancho: Number(ex.gifAncho.value), fps: Number(ex.gifFps.value) } : undefined,
    subtitulos: ex.campoSubs.hidden ? {} : { quemar: ex.subsQuemar.checked && !esAudio(X.formato), srt: ex.subsSrt.checked, vtt: ex.subsVtt.checked },
    carpeta: X.carpeta,
    nombre: ex.nombre.value.trim()
  };
  X.ocupado = true;
  ex.iniciar.disabled = true;
  let r;
  try { r = await llamar('exportar_iniciar', [opciones]); }
  catch (e) { r = { error: 'No pude arrancar la exportación: ' + mensajeDe(e) }; }
  X.ocupado = false;
  ex.iniciar.disabled = false;
  if (!r || r.error) { mostrarError((r && r.error) || 'No pude arrancar la exportación.'); return; }
  ex.barra.style.width = '0%';
  ex.progresoTexto.textContent = 'Preparando…';
  mostrarPaso('progreso');
  ex.cancelarExport.disabled = false;
  ex.cancelarExport.focus();
  sondear();
}

async function sondear() {
  clearTimeout(X.temporizador);
  let e;
  try { e = await llamar('exportar_estado'); }
  catch (err) { X.temporizador = setTimeout(sondear, 800); return; }
  if (!ex.dlg.open) return;
  if (e.estado === 'exportando') {
    const pct = Math.max(0, Math.min(100, Math.round((e.progreso || 0) * 100)));
    ex.barra.style.width = pct + '%';
    ex.progresoTexto.textContent = (e.progreso || 0) < 0.005 ? 'Preparando…' : 'Exportando… ' + pct + ' %';
    X.temporizador = setTimeout(sondear, 300);
    return;
  }
  if (e.estado === 'listo') { mostrarResultado(e); return; }
  if (e.estado === 'cancelado') {
    mostrarPaso('armar');
    mostrarError('Exportación cancelada. No quedó ningún archivo a medias.');
    ex.iniciar.focus();
    return;
  }
  if (e.estado === 'error') {
    mostrarPaso('armar');
    mostrarError(e.error || 'No pude exportar.');
    ex.iniciar.focus();
    return;
  }
  // 'ninguna': la exportacion desaparecio (no deberia pasar); se vuelve al formulario
  mostrarPaso('armar');
}

function tamanoLegible(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1).replace('.', ',') + ' MB';
  return Math.max(1, Math.round(bytes / 1024)) + ' KB';
}

function mostrarResultado(e) {
  mostrarPaso('resultado');
  ex.resTitulo.textContent = 'Listo: ya está guardado.';
  ex.resLineas.textContent = '';
  const linea = (rotulo, valor, mono) => {
    const li = document.createElement('li');
    const b = document.createElement('b');
    b.textContent = rotulo + ': ';
    const s = document.createElement('span');
    s.textContent = valor;
    if (mono) s.className = 'exp__mono';
    li.appendChild(b);
    li.appendChild(s);
    ex.resLineas.appendChild(li);
  };
  linea('Archivo', e.nombre, true);
  linea('Carpeta', e.carpeta, true);
  linea('Duración', formatoTiempo(e.duracion));
  linea('Tamaño', tamanoLegible(e.tamano_bytes));
  if (e.dimensiones) {
    linea('Imagen', e.dimensiones[0] + ' × ' + e.dimensiones[1] + (e.fps ? ' a ' + String(Math.round(e.fps * 100) / 100).replace('.', ',') + ' cuadros por segundo' : ''));
  }
  if (e.perfil) linea('Tipo', e.perfil + (e.perfil.indexOf('ProRes') < 0 && e.perfil.indexOf('GIF') < 0 ? ' · calidad ' + e.calidad : ''));
  if (e.normalizado) linea('Volumen', 'normalizado a −14 LUFS');
  if (e.subtitulos && e.subtitulos.length) linea('Subtítulos', e.subtitulos.join(', '), true);

  const avisos = [];
  if (e.respaldo) avisos.push((e.motivo_respaldo || 'La GPU no funcionó.') + ' Se exportó con el procesador, con el mismo resultado.');
  if (e.pidio_normalizar && !e.normalizado) avisos.push('El volumen no se normalizó: no se encontró sonido que medir.');
  ex.resAviso.hidden = !avisos.length;
  ex.resAviso.textContent = avisos.join(' ');
  ex.cerrar.focus();
}

async function cancelarExportacion() {
  ex.cancelarExport.disabled = true;
  ex.progresoTexto.textContent = 'Cancelando…';
  try { await llamar('exportar_cancelar'); } catch (e) { /* el sondeo cuenta lo que pasó */ }
}

async function cambiarCarpeta() {
  let r;
  try { r = await llamar('elegir_carpeta'); } catch (e) { r = { error: 'No pude abrir el selector de carpetas.' }; }
  if (r && r.error) { mostrarError(r.error); return; }
  if (!r || !r.ruta) return;
  X.carpeta = r.ruta;
  ex.carpeta.textContent = r.ruta;
  ex.carpeta.title = r.ruta;
  mostrarError('');
  proponerNombre();
}

async function mostrarEnCarpeta() {
  let r;
  try { r = await llamar('mostrar_en_carpeta'); } catch (e) { r = { error: 'No pude abrir la carpeta.' }; }
  if (r && r.error) avisar(r.error);
}

/* ---------- conexiones ---------- */
ex.boton.addEventListener('click', () => { abrirExportar(); ex.boton.blur(); });
ex.dlg.querySelectorAll('[data-formato]').forEach((b) => b.addEventListener('click', () => elegirFormato(b.dataset.formato)));
ex.dlg.querySelectorAll('[data-encuadre]').forEach((b) => b.addEventListener('click', () => { X.encuadre = b.dataset.encuadre; pintarFormato(); }));
ex.dlg.querySelectorAll('[data-calidad]').forEach((b) => b.addEventListener('click', () => { X.calidad = b.dataset.calidad; pintarFormato(); }));
ex.perfil.addEventListener('change', () => { X.perfil = ex.perfil.value; pintarFormato(); proponerNombre(); });
ex.gifAncho.addEventListener('input', pintarSliders);
ex.focoX.addEventListener('input', pintarSliders);
ex.focoY.addEventListener('input', pintarSliders);
let esperaNombre = 0;
ex.nombre.addEventListener('input', () => { clearTimeout(esperaNombre); esperaNombre = setTimeout(proponerNombre, 180); });
ex.nombre.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); iniciar(); } });
ex.cambiar.addEventListener('click', cambiarCarpeta);
ex.iniciar.addEventListener('click', iniciar);
ex.cancelarArmar.addEventListener('click', cerrarExportar);
ex.cancelarExport.addEventListener('click', cancelarExportacion);
ex.mostrar.addEventListener('click', mostrarEnCarpeta);
ex.otra.addEventListener('click', () => { mostrarPaso('armar'); if (X.op) prepararFormulario(X.op); ex.iniciar.focus(); });
ex.cerrar.addEventListener('click', cerrarExportar);

// Esc no cierra el dialogo mientras se exporta (para cancelar esta el boton).
ex.dlg.addEventListener('cancel', (e) => { if (!ex.progreso.hidden) e.preventDefault(); });
ex.dlg.addEventListener('close', () => { clearTimeout(X.temporizador); X.temporizador = 0; });

// Con el dialogo abierto, ninguna tecla llega a los atajos del visor y la edicion (Espacio, flechas, S...).
window.addEventListener('keydown', (e) => {
  if (ex.dlg.open) e.stopImmediatePropagation();
}, true);

// Ctrl+E abre el dialogo
window.addEventListener('keydown', (e) => {
  if (e.code === 'KeyE' && e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey && !ex.dlg.open) {
    e.preventDefault();
    if (!ex.boton.disabled) abrirExportar();
  }
});

// El boton esta disponible cuando hay un proyecto
const _alActualizarProyecto = typeof alActualizarProyecto === 'function' ? alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyecto) _alActualizarProyecto();
  ex.boton.disabled = !S.proy;
  // Si se abrio otro archivo (por ejemplo, al soltarlo sobre la ventana) y no se esta exportando, el
  // dialogo ya habla de otra cosa: se cierra. Una exportacion en curso sigue, es sobre su propia copia.
  if (ex.dlg.open && ex.progreso.hidden && S.ruta !== X.rutaAlAbrir) cerrarExportar();
};
