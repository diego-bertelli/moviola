/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — escenas, negros y congelados
   "Escenas…": el motor busca (motor/escenas.py) los cambios de escena, los tramos negros y los tramos donde la imagen
   no se mueve, en tiempos de la linea de tiempo ACTUAL. Aca se muestran (resumen, mapa y lista) y se puede cortar en
   cada cambio (editar_dividir_varios) o sacar los tramos (editar_borrar_rangos): un solo paso de deshacer cada uno.
   Los resultados se descartan si se cambia cualquier valor. Se carga despues de subtitulos.js.
   ============================================================ */
'use strict';

const esc = {
  boton:     $('btn-escenas'),
  dlg:       $('dlg-escenas'),
  umbral:    $('esc-umbral'),
  umbralVal: $('esc-umbral-valor'),
  negro:     $('esc-negro'),
  negroVal:  $('esc-negro-valor'),
  congelado: $('esc-congelado'),
  congeladoVal: $('esc-congelado-valor'),
  analizando: $('esc-analizando'),
  resultado: $('esc-resultado'),
  resumen:   $('esc-resumen'),
  mapa:      $('esc-mapa'),
  lista:     $('esc-lista'),
  error:     $('esc-error'),
  cerrar:    $('esc-cerrar'),
  analizar:  $('esc-analizar'),
  cortar:    $('esc-cortar'),
  sacarNegros: $('esc-sacar-negros'),
  sacarCongelados: $('esc-sacar-congelados'),
  hallados:  null,
  rutaAlAbrir: null,
  ocupado:   false
};

function comaEsc(n, dec) { return Number(n).toFixed(dec).replace('.', ','); }
function plural(n, uno, varios) { return n + ' ' + (n === 1 ? uno : varios); }

function pintarValoresEsc() {
  esc.umbralVal.textContent = String(esc.umbral.value);
  esc.negroVal.textContent = comaEsc(esc.negro.value, 1) + ' s';
  esc.congeladoVal.textContent = comaEsc(esc.congelado.value, 1) + ' s';
}

function errorEsc(texto) {
  esc.error.hidden = !texto;
  esc.error.textContent = texto || '';
}

function descartarEsc() {
  esc.hallados = null;
  esc.resultado.hidden = true;
  esc.cortar.hidden = esc.sacarNegros.hidden = esc.sacarCongelados.hidden = true;
}

async function abrirEscenas() {
  if (!S.info || !S.proy || esc.dlg.open) return;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  errorEsc('');
  descartarEsc();
  esc.analizando.hidden = true;
  esc.analizar.disabled = false;
  pintarValoresEsc();
  esc.rutaAlAbrir = S.ruta;
  esc.dlg.showModal();
  esc.analizar.focus();
}

function cerrarEscenas() {
  if (esc.dlg.open) esc.dlg.close();
}

async function buscarEscenas() {
  if (esc.ocupado) return;
  esc.ocupado = true;
  errorEsc('');
  descartarEsc();
  esc.analizar.disabled = true;
  esc.analizando.hidden = false;
  let r;
  try {
    r = await llamar('analizar_escenas', [null, Number(esc.umbral.value), Number(esc.negro.value), Number(esc.congelado.value)]);
  } catch (e) {
    r = { error: 'No pude analizar el video: ' + mensajeDe(e) };
  }
  esc.ocupado = false;
  esc.analizando.hidden = true;
  esc.analizar.disabled = false;
  if (!esc.dlg.open) return;
  if (!r || r.error) { errorEsc((r && r.error) || 'No pude analizar el video.'); return; }
  mostrarEscenas(r);
}

function filaEsc(texto) {
  const li = document.createElement('li');
  li.textContent = texto;
  esc.lista.appendChild(li);
}

function mostrarEscenas(r) {
  esc.hallados = r;
  esc.resultado.hidden = false;
  const ne = r.escenas.length, nn = r.negros.length, nc = r.congelados.length;
  if (!ne && !nn && !nc) {
    esc.resumen.textContent = 'No se encontró nada con estos valores. Probá bajar la sensibilidad o la duración mínima.';
    esc.mapa.hidden = true;
    esc.lista.textContent = '';
    return;
  }
  esc.mapa.hidden = false;
  const totalNegro = r.negros.reduce((a, x) => a + (x.fin - x.inicio), 0);
  const totalCong = r.congelados.reduce((a, x) => a + (x.fin - x.inicio), 0);
  esc.resumen.textContent = 'Se encontraron ' + plural(ne, 'cambio de escena', 'cambios de escena') + ', ' + plural(nn, 'tramo negro', 'tramos negros') +
    ' (' + comaEsc(totalNegro, 1) + ' s) y ' + plural(nc, 'tramo congelado', 'tramos congelados') + ' (' + comaEsc(totalCong, 1) + ' s).';
  esc.lista.textContent = '';
  r.escenas.slice(0, 5).forEach((t) => filaEsc('Cambio de escena en ' + tiempoCorto(t)));
  if (ne > 5) filaEsc('… y ' + (ne - 5) + ' cambios más');
  r.negros.slice(0, 4).forEach((x) => filaEsc('Negro: ' + tiempoCorto(x.inicio) + ' – ' + tiempoCorto(x.fin)));
  r.congelados.slice(0, 4).forEach((x) => filaEsc('Congelado: ' + tiempoCorto(x.inicio) + ' – ' + tiempoCorto(x.fin)));
  esc.cortar.hidden = !ne;
  esc.cortar.textContent = 'Cortar en ' + (ne === 1 ? 'el cambio' : 'los ' + ne + ' cambios');
  esc.sacarNegros.hidden = !nn;
  esc.sacarNegros.textContent = 'Sacar ' + (nn === 1 ? 'el negro' : 'los ' + nn + ' negros');
  esc.sacarCongelados.hidden = !nc;
  esc.sacarCongelados.textContent = 'Sacar ' + (nc === 1 ? 'el congelado' : 'los ' + nc + ' congelados');
  dibujarMapaEsc(r);
}

function dibujarMapaEsc(r) {
  const lienzo = esc.mapa;
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
  ctx.fillStyle = colorCss('--rosa', '#FF5C80');
  r.negros.forEach((x) => ctx.fillRect(Math.floor(x.inicio / dur * w), 8, Math.max(2, Math.ceil((x.fin - x.inicio) / dur * w)), 18));
  ctx.fillStyle = colorCss('--menta', '#5FD6A6');
  r.congelados.forEach((x) => ctx.fillRect(Math.floor(x.inicio / dur * w), 4, Math.max(2, Math.ceil((x.fin - x.inicio) / dur * w)), 6));
  ctx.fillStyle = colorCss('--coral', '#FF6D5A');
  r.escenas.forEach((t) => ctx.fillRect(Math.floor(t / dur * w) - 1, 0, 2, h));
}

async function aplicarEsc(nombre, args, mensaje) {
  if (esc.ocupado || !esc.hallados) return;
  esc.ocupado = true;
  const r = await operar(nombre, args);
  esc.ocupado = false;
  if (!r) {                                  // operar ya mostro el aviso con el motivo
    errorEsc('No se pudo. Volvé a buscar (el proyecto cambió).');
    descartarEsc();
    return;
  }
  cerrarEscenas();
  avisar(mensaje(r.resultado) + ' «Deshacer» (Ctrl+Z) lo devuelve de una vez.', 'info');
}

function cortarEnCambios() {
  aplicarEsc('dividir_varios', [esc.hallados.escenas], (n) => 'Se cortó en ' + plural(n, 'lugar', 'lugares') + '.');
}
function sacarNegros() {
  aplicarEsc('borrar_rangos', [esc.hallados.negros.map((x) => [x.inicio, x.fin])], (res) => 'Se sacaron ' + plural((res || {}).tramos || 0, 'tramo negro', 'tramos negros') + '.');
}
function sacarCongelados() {
  aplicarEsc('borrar_rangos', [esc.hallados.congelados.map((x) => [x.inicio, x.fin])], (res) => 'Se sacaron ' + plural((res || {}).tramos || 0, 'tramo congelado', 'tramos congelados') + '.');
}

esc.boton.addEventListener('click', () => { abrirEscenas(); esc.boton.blur(); });
esc.cerrar.addEventListener('click', cerrarEscenas);
esc.analizar.addEventListener('click', buscarEscenas);
esc.cortar.addEventListener('click', cortarEnCambios);
esc.sacarNegros.addEventListener('click', sacarNegros);
esc.sacarCongelados.addEventListener('click', sacarCongelados);
[esc.umbral, esc.negro, esc.congelado].forEach((r) => {
  r.addEventListener('input', () => { pintarValoresEsc(); descartarEsc(); errorEsc(''); });
});

window.addEventListener('keydown', (e) => {
  if (esc.dlg.open) e.stopImmediatePropagation();
}, true);

const _alActualizarProyectoEsc = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoEsc) _alActualizarProyectoEsc();
  esc.boton.disabled = !(S.proy && S.proy.pistas.some((p) => p.id === 'V1' && p.clips.length));
  if (esc.dlg.open && !esc.ocupado && S.ruta !== esc.rutaAlAbrir) cerrarEscenas();
};
esc.boton.disabled = true;
