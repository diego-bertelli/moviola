/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — cortar silencios y medir el volumen
   "Cortar silencios…": el motor busca los tramos sin sonido (motor/silencios.py) y los devuelve en tiempos de la
   linea de tiempo ACTUAL; aca se muestran (resumen, mapa y lista) y, si la persona quiere, se borran todos juntos
   (editar_borrar_rangos: un solo paso de deshacer). Los resultados se descartan si se cambia cualquier valor.
   "Medir el volumen del proyecto": LUFS, pico y rango de todo el proyecto como queda al exportar.
   Se carga despues de efectos.js y usa su estado (S, llamar, operar, avisar, formatoTiempo...).
   ============================================================ */
'use strict';

const sil = {
  boton:     $('btn-silencios'),
  dlg:       $('dlg-silencios'),
  umbral:    $('sil-umbral'),
  umbralVal: $('sil-umbral-valor'),
  duracion:  $('sil-duracion'),
  duracionVal: $('sil-duracion-valor'),
  margen:    $('sil-margen'),
  margenVal: $('sil-margen-valor'),
  analizando: $('sil-analizando'),
  resultado: $('sil-resultado'),
  resumen:   $('sil-resumen'),
  mapa:      $('sil-mapa'),
  lista:     $('sil-lista'),
  error:     $('sil-error'),
  cerrar:    $('sil-cerrar'),
  analizar:  $('sil-analizar'),
  cortar:    $('sil-cortar'),
  medir:     $('btn-medir-volumen'),
  medida:    $('medida-volumen'),
  hallados:  null,          // lo que devolvio el motor para los valores de ahora
  rutaAlAbrir: null,        // el archivo del que se abrio el dialogo
  ocupado:   false
};

function coma(n, dec) { return Number(n).toFixed(dec).replace('.', ','); }

function pintarValores() {
  sil.umbralVal.textContent = '−' + Math.abs(Number(sil.umbral.value)) + ' dB';
  sil.duracionVal.textContent = coma(sil.duracion.value, 1) + ' s';
  sil.margenVal.textContent = coma(sil.margen.value, 2) + ' s';
}

function errorSil(texto) {
  sil.error.hidden = !texto;
  sil.error.textContent = texto || '';
}

function descartarResultado() {
  sil.hallados = null;
  sil.resultado.hidden = true;
  sil.cortar.hidden = true;
}

/* ---------- abrir y cerrar ---------- */
async function abrirSilencios() {
  if (!S.info || !S.proy || sil.dlg.open) return;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  errorSil('');
  descartarResultado();
  sil.analizando.hidden = true;
  sil.analizar.disabled = false;
  pintarValores();
  sil.rutaAlAbrir = S.ruta;
  sil.dlg.showModal();
  sil.analizar.focus();
}

function cerrarSilencios() {
  if (sil.dlg.open) sil.dlg.close();
}

/* ---------- analizar ---------- */
async function buscarSilencios() {
  if (sil.ocupado) return;
  sil.ocupado = true;
  errorSil('');
  descartarResultado();
  sil.analizar.disabled = true;
  sil.analizando.hidden = false;
  let r;
  try {
    r = await llamar('analizar_silencios', [Number(sil.umbral.value), Number(sil.duracion.value), Number(sil.margen.value)]);
  } catch (e) {
    r = { error: 'No pude analizar el audio: ' + mensajeDe(e) };
  }
  sil.ocupado = false;
  sil.analizando.hidden = true;
  sil.analizar.disabled = false;
  if (!sil.dlg.open) return;
  if (!r || r.error) { errorSil((r && r.error) || 'No pude analizar el audio.'); return; }
  mostrarSilencios(r);
}

function tiempoCorto(t) { return formatoTiempo(t).replace(/,\d+$/, (m) => m.slice(0, 3)); }

function mostrarSilencios(r) {
  sil.hallados = r;
  sil.resultado.hidden = false;
  const n = r.silencios.length;
  if (!n) {
    sil.resumen.textContent = 'No se encontraron silencios con estos valores. Probá subir el nivel (más cerca de 0 dB) o bajar la duración.';
    sil.cortar.hidden = true;
    sil.lista.textContent = '';
    dibujarMapa(r);
    sil.mapa.hidden = true;
    return;
  }
  sil.mapa.hidden = false;
  const quedaria = Math.max(0, r.duracion - r.total);
  sil.resumen.textContent = 'Se encontraron ' + n + (n === 1 ? ' silencio' : ' silencios') + ' que suman ' + coma(r.total, 1) +
    ' s de ' + coma(r.duracion, 1) + ' s. El proyecto quedaría de ' + coma(quedaria, 1) + ' s.';
  sil.lista.textContent = '';
  r.silencios.slice(0, 8).forEach((s) => {
    const li = document.createElement('li');
    const mono = document.createElement('span');
    mono.className = 'exp__mono';
    mono.textContent = tiempoCorto(s.inicio) + ' – ' + tiempoCorto(s.fin);
    li.appendChild(mono);
    li.appendChild(document.createTextNode('  (' + coma(s.fin - s.inicio, 1) + ' s)'));
    sil.lista.appendChild(li);
  });
  if (n > 8) {
    const li = document.createElement('li');
    li.textContent = 'y ' + (n - 8) + ' más';
    sil.lista.appendChild(li);
  }
  sil.cortar.textContent = 'Cortar ' + (n === 1 ? 'el silencio' : 'los ' + n + ' silencios');
  sil.cortar.hidden = false;
  dibujarMapa(r);
  sil.cortar.focus();
}

function dibujarMapa(r) {
  const lienzo = sil.mapa;
  const w = Math.max(1, Math.floor(lienzo.getBoundingClientRect().width)) || 480;
  const h = 34;
  const dpr = window.devicePixelRatio || 1;
  lienzo.width = Math.round(w * dpr);
  lienzo.height = Math.round(h * dpr);
  const ctx = lienzo.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const dur = Math.max(r.duracion, 1e-6);
  ctx.fillStyle = colorCss('--onda-baja', '#6F5FE0');
  ctx.globalAlpha = 0.55;
  ctx.fillRect(0, 12, w, 10);
  ctx.globalAlpha = 1;
  ctx.fillStyle = colorCss('--coral', '#FF6D5A');
  r.silencios.forEach((s) => {
    ctx.fillRect(Math.floor(s.inicio / dur * w), 4, Math.max(2, Math.ceil((s.fin - s.inicio) / dur * w)), h - 8);
  });
}

/* ---------- cortar ---------- */
async function cortarSilencios() {
  if (sil.ocupado || !sil.hallados || !sil.hallados.silencios.length) return;
  sil.ocupado = true;
  sil.cortar.disabled = true;
  const rangos = sil.hallados.silencios.map((s) => [s.inicio, s.fin]);
  const r = await operar('borrar_rangos', [rangos]);
  sil.ocupado = false;
  sil.cortar.disabled = false;
  if (!r) {                                  // operar ya mostro el aviso con el motivo
    errorSil('No se pudieron cortar. Volvé a buscar los silencios (el proyecto cambió).');
    descartarResultado();
    return;
  }
  cerrarSilencios();
  const res = r.resultado || {};
  avisar('Se cortaron ' + res.tramos + (res.tramos === 1 ? ' silencio' : ' silencios') + ' (' + coma(res.duracion, 1) +
         ' s). «Deshacer» (Ctrl+Z) los devuelve todos de una vez.', 'info');
}

/* ---------- medir el volumen ---------- */
async function medirVolumen() {
  sil.medir.disabled = true;
  sil.medida.hidden = false;
  sil.medida.textContent = 'Midiendo…';
  let r;
  try { r = await llamar('medir_volumen'); } catch (e) { r = { error: 'No pude medir el volumen.' }; }
  sil.medir.disabled = false;
  if (!r || r.error) { sil.medida.textContent = (r && r.error) || 'No pude medir el volumen.'; return; }
  const nota = r.lufs > -13 ? ' Está más fuerte que lo habitual en redes (−14).' : (r.lufs < -20 ? ' Está bajo: podés normalizar al exportar.' : '');
  sil.medida.textContent = 'Todo el proyecto: ' + coma(r.lufs, 1).replace('-', '−') + ' LUFS · pico ' + coma(r.pico, 1).replace('-', '−') +
    ' dB · rango ' + coma(r.rango, 1) + ' LU.' + nota;
}

/* ---------- conexiones ---------- */
sil.boton.addEventListener('click', () => { abrirSilencios(); sil.boton.blur(); });
sil.cerrar.addEventListener('click', cerrarSilencios);
sil.analizar.addEventListener('click', buscarSilencios);
sil.cortar.addEventListener('click', cortarSilencios);
sil.medir.addEventListener('click', () => { medirVolumen(); sil.medir.blur(); });
[sil.umbral, sil.duracion, sil.margen].forEach((r) => {
  r.addEventListener('input', () => { pintarValores(); descartarResultado(); errorSil(''); });
});

// Con el dialogo abierto, ninguna tecla llega a los atajos del visor y la edicion.
window.addEventListener('keydown', (e) => {
  if (sil.dlg.open) e.stopImmediatePropagation();
}, true);

// El boton y la medicion dependen del proyecto: se actualizan con el, y una medicion vieja se borra.
const _alActualizarProyectoSil = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoSil) _alActualizarProyectoSil();
  sil.boton.disabled = !(S.proy && S.proy.pistas.some((p) => p.id === 'A1' && p.clips.length));
  sil.medida.hidden = true;
  sil.medida.textContent = '';
  if (sil.dlg.open && !sil.ocupado && S.ruta !== sil.rutaAlAbrir) cerrarSilencios();
};
sil.boton.disabled = true;
