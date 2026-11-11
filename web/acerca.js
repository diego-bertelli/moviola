/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — «Acerca de»
   Version, quien lo hizo, la licencia y que herramientas hay en esta computadora (FFmpeg, whisper, yt-dlp). Se abre con el boton «i» del
   encabezado, con el enlace de la pantalla de inicio o con F1. Se carga antes de texto.js y usa su estado (llamar, avisar...).
   ============================================================ */
'use strict';

const ac = {
  dlg:        $('dlg-acerca'),
  abrirBarra: $('btn-acerca'),
  abrirInicio: $('btn-acerca-inicio'),
  version:    $('ac-version'),
  descripcion: $('ac-descripcion'),
  autores:    $('ac-autores'),
  licencia:   $('ac-licencia'),
  garantia:   $('ac-garantia'),
  herramientas: $('ac-herramientas'),
  componentes: $('ac-componentes'),
  error:      $('ac-error'),
  ver:        $('ac-licencia-ver'),
  cerrar:     $('ac-cerrar')
};

function errorAc(texto) {
  ac.error.hidden = !texto;
  ac.error.textContent = texto || '';
}

async function abrirAcerca() {
  if (ac.dlg.open) return;
  let d;
  try { d = await llamar('acerca_de'); } catch (e) { d = { error: 'No pude leer los datos del programa.' }; }
  if (!d || d.error) { avisar((d && d.error) || 'No pude leer los datos del programa.', 'ojo'); return; }
  ac.version.textContent = 'Versión ' + d.version + ' · ' + d.anio;
  ac.descripcion.textContent = d.descripcion;
  ac.autores.textContent = d.autores;
  ac.licencia.textContent = d.licencia;
  ac.garantia.textContent = d.garantia;
  ac.herramientas.textContent = '';
  d.herramientas.forEach((h) => {
    const li = document.createElement('li');
    li.className = 'ac__item ac__item--' + (h.hay ? 'si' : 'no');
    const marca = document.createElement('span');
    marca.className = 'ac__marca';
    marca.textContent = h.hay ? '✓' : '–';
    marca.setAttribute('aria-label', h.hay ? 'Está instalado' : 'No está instalado');
    const nombre = document.createElement('b');
    nombre.textContent = h.nombre;
    const detalle = document.createElement('small');
    detalle.textContent = h.detalle;
    li.appendChild(marca);
    li.appendChild(nombre);
    li.appendChild(detalle);
    ac.herramientas.appendChild(li);
  });
  ac.componentes.textContent = d.componentes.map((c) => c.nombre + ' (' + c.licencia + ')').join(' · ');
  errorAc('');
  ac.dlg.showModal();
  ac.cerrar.focus();
}

function cerrarAcerca() { if (ac.dlg.open) ac.dlg.close(); }

async function verLicencia() {
  errorAc('');
  let r;
  try { r = await llamar('acerca_licencia'); } catch (e) { r = { error: 'No pude abrir la licencia.' }; }
  if (r && r.error) errorAc(r.error);
}

[ac.abrirBarra, ac.abrirInicio].forEach((b) => b.addEventListener('click', () => { abrirAcerca(); b.blur(); }));
ac.cerrar.addEventListener('click', cerrarAcerca);
ac.ver.addEventListener('click', verLicencia);

// F1 abre y cierra; con el dialogo abierto no llega ninguna otra tecla a los atajos.
window.addEventListener('keydown', (e) => {
  if (e.key === 'F1') {
    e.preventDefault();
    e.stopImmediatePropagation();
    if (ac.dlg.open) cerrarAcerca(); else abrirAcerca();
    return;
  }
  if (ac.dlg.open) e.stopImmediatePropagation();
}, true);
