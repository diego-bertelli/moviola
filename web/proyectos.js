/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — proyectos
   Guardar (Ctrl+S) y "Guardar como…", abrir un proyecto .moviola, la lista de abiertos hace poco y la recuperacion del
   trabajo que quedo sin guardar, en la pantalla de inicio; y el aviso "hay cambios sin guardar" antes de abrir otra cosa
   desde un boton o arrastrando un archivo. El motor lleva la cuenta de los cambios (S.proy.sin_guardar).
   Se carga despues de subtitulos.js y usa su estado (S, llamar, avisar, abrir, nombreDe...).
   ============================================================ */
'use strict';

const pr = {
  guardar:    $('btn-guardar'),
  guardarComo: $('btn-guardar-como'),
  marca:      $('marca-proyecto'),
  abrirVideo: $('btn-abrir'),
  abrirBarra: $('btn-abrir-barra'),
  abrirProyecto: $('btn-abrir-proyecto'),
  crearProyecto: $('btn-crear-proyecto'),
  recientes:  $('recientes'),
  lista:      $('recientes-lista'),
  recuperar:  $('recuperar'),
  recuperarTexto: $('recuperar-texto'),
  btnRecuperar: $('btn-recuperar'),
  btnDescartarRecup: $('btn-descartar-recup'),
  dlg:        $('dlg-confirmar'),
  confTexto:  $('conf-texto'),
  confCancelar: $('conf-cancelar'),
  confDescartar: $('conf-descartar'),
  confGuardar: $('conf-guardar'),
  ocupado:    false,
  sinConfirmar: false        // para repetir un clic que ya se confirmo
};

/* ---------- la marca del encabezado ---------- */
function pintarMarcaProyecto() {
  const p = S.proy;
  pr.guardar.hidden = !p;
  pr.guardarComo.hidden = !p;
  if (!p) { pr.marca.hidden = true; return; }
  pr.marca.hidden = false;
  const nombre = p.archivo_proyecto || 'Proyecto sin guardar';
  pr.marca.textContent = nombre + (p.sin_guardar && p.archivo_proyecto ? '  •' : '');
  pr.marca.title = p.ruta_proyecto || 'Todavía no se guardó: Guardar (Ctrl+S) te pregunta dónde.';
  pr.marca.classList.toggle('marca-proyecto--sin', !!p.sin_guardar);
  pr.guardar.textContent = p.sin_guardar ? 'Guardar •' : 'Guardar';
}

/* ---------- guardar ---------- */
async function guardarProyecto(como) {
  if (!S.proy || pr.ocupado) return false;
  pr.ocupado = true;
  let r;
  try { r = await llamar(como ? 'guardar_proyecto_como' : 'guardar_proyecto'); }
  catch (e) { r = { error: 'No pude guardar: ' + mensajeDe(e) }; }
  pr.ocupado = false;
  if (!r || r.cancelado) return false;
  if (r.error) { avisar(r.error); return false; }
  if (r.proyecto && S.proy) {
    S.proy.archivo_proyecto = r.proyecto.archivo_proyecto;
    S.proy.ruta_proyecto = r.proyecto.ruta_proyecto;
    S.proy.sin_guardar = false;
  }
  pintarMarcaProyecto();
  avisar('Proyecto guardado: ' + r.nombre, 'info');
  return true;
}

/* ---------- cambios sin guardar ---------- */
function preguntarCambios(texto) {
  return new Promise((resolver) => {
    pr.confTexto.textContent = texto || 'Si seguís, se pierden las ediciones que hiciste en este proyecto.';
    let listo = false;
    const fin = (v) => {
      if (listo) return;
      listo = true;
      pr.confCancelar.removeEventListener('click', alCancelar);
      pr.confDescartar.removeEventListener('click', alDescartar);
      pr.confGuardar.removeEventListener('click', alGuardar);
      pr.dlg.removeEventListener('cancel', alCancelar);
      if (pr.dlg.open) pr.dlg.close();
      resolver(v);
    };
    const alCancelar = (e) => { if (e && e.preventDefault) e.preventDefault(); fin('cancelar'); };
    const alDescartar = () => fin('descartar');
    const alGuardar = async () => {
      pr.confGuardar.disabled = true;
      const bien = await guardarProyecto(false);
      pr.confGuardar.disabled = false;
      if (bien) fin('guardar');
    };
    pr.confCancelar.addEventListener('click', alCancelar);
    pr.confDescartar.addEventListener('click', alDescartar);
    pr.confGuardar.addEventListener('click', alGuardar);
    pr.dlg.addEventListener('cancel', alCancelar);
    pr.dlg.showModal();
    pr.confGuardar.focus();
  });
}

/** Si hay cambios sin guardar, pregunta antes de seguir. true = se puede seguir. */
async function puedeSeguir() {
  if (!S.proy || !S.proy.sin_guardar) return true;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  const r = await preguntarCambios();
  return r !== 'cancelar';
}

/** Abrir algo desde la interfaz (botones, recientes, arrastrar): pregunta por los cambios y despues abre. */
async function pedirAbrir(ruta) {
  if (!(await puedeSeguir())) return;
  await abrir(ruta);
}

async function elegirProyectoYAbrir() {
  if (!(await puedeSeguir())) return;
  let r;
  try { r = await llamar('elegir_proyecto'); } catch (e) { r = { error: 'No pude abrir el selector de archivos.' }; }
  if (!r || r.cancelado) return;
  if (r.error) { avisar(r.error); return; }
  await abrir(r.ruta);
}

// Los botones de abrir un video preguntan antes: se engancha ANTES que los de app.js (fase de captura)
function antesDeAbrir(e) {
  if (pr.sinConfirmar) return;
  if (!S.proy || !S.proy.sin_guardar) return;
  e.stopImmediatePropagation();
  e.preventDefault();
  const boton = e.currentTarget;
  puedeSeguir().then((si) => {
    if (!si) return;
    pr.sinConfirmar = true;
    try { boton.click(); } finally { pr.sinConfirmar = false; }
  });
}
[pr.abrirVideo, pr.abrirBarra].forEach((b) => b.addEventListener('click', antesDeAbrir, true));

/** «Crear un proyecto»: se eligen varios videos, el primero se abre, los demas se suman al panel de medios y se ponen en la linea de tiempo
 *  uno detras de otro, y al final se ofrece guardar el proyecto (.moviola). */
async function crearProyecto() {
  if (!(await puedeSeguir())) return;
  let r;
  try { r = await llamar('elegir_videos'); } catch (e) { r = { error: 'No pude abrir el selector de archivos.' }; }
  if (!r || r.cancelado) return;
  if (r.error) { avisar(r.error); return; }
  const rutas = r.rutas || [];
  if (!rutas.length) return;
  await abrir(rutas[0]);
  if (!S.proy) return;
  let puestos = 1;
  if (!S.soloAudio) {
    for (const ruta of rutas.slice(1)) {
      let m;
      try { m = await llamar('agregar_medio', [ruta]); } catch (e) { m = { error: 'No pude agregar ese archivo.' }; }
      if (m && m.proyecto) aplicarProyecto(m.proyecto);
      if (!m || m.error) { avisar((m && m.error) || 'No pude agregar ese archivo.', 'ojo'); continue; }
      if (m.repetido) continue;
      const ins = await operar('insertar_fuente', [m.fuente]);
      if (ins) puestos++;
    }
  }
  avisar('Proyecto creado con ' + puestos + (puestos === 1 ? ' video.' : ' videos, uno detrás de otro.') + ' Guardalo para no perder el trabajo.', 'info');
  await guardarProyecto(true);
}

/* ---------- pantalla de inicio: recientes y recuperacion ---------- */
async function cargarRecientes() {
  let r;
  try { r = await llamar('recientes'); } catch (e) { return; }
  if (!r) return;
  const lista = r.recientes || [];
  pr.lista.textContent = '';
  pr.recientes.hidden = !lista.length;
  lista.forEach((x) => {
    const li = document.createElement('li');
    li.className = 'reciente';
    const abrirBtn = document.createElement('button');
    abrirBtn.type = 'button';
    abrirBtn.className = 'reciente__abrir';
    abrirBtn.dataset.ruta = x.ruta;
    const nombre = document.createElement('span');
    nombre.className = 'reciente__nombre';
    const tipo = document.createElement('span');
    tipo.className = 'reciente__tipo';
    tipo.textContent = x.tipo === 'proyecto' ? 'Proyecto' : 'Video';
    nombre.appendChild(tipo);
    nombre.appendChild(document.createTextNode(x.nombre));
    const carpeta = document.createElement('span');
    carpeta.className = 'reciente__carpeta';
    carpeta.textContent = x.carpeta;
    carpeta.title = x.ruta;
    abrirBtn.appendChild(nombre);
    abrirBtn.appendChild(carpeta);
    abrirBtn.addEventListener('click', () => pedirAbrir(x.ruta));
    const olvidar = document.createElement('button');
    olvidar.type = 'button';
    olvidar.className = 'reciente__olvidar';
    olvidar.textContent = '✕';
    olvidar.title = 'Sacar de la lista (no borra el archivo)';
    olvidar.setAttribute('aria-label', 'Sacar ' + x.nombre + ' de la lista');
    olvidar.addEventListener('click', async () => { await llamar('olvidar_reciente', [x.ruta]); cargarRecientes(); });
    li.appendChild(abrirBtn);
    li.appendChild(olvidar);
    pr.lista.appendChild(li);
  });
  const rec = r.recuperacion;
  pr.recuperar.hidden = !rec;
  if (rec) pr.recuperarTexto.textContent = 'Quedó trabajo sin guardar de «' + rec.nombre + '» (' + rec.fecha + ').';
}

async function recuperarTrabajo() {
  limpiarAvisos();
  mostrarCargando('Recuperando el trabajo…');
  let d;
  try { d = await llamar('abrir_recuperacion'); }
  catch (e) { d = { error: 'No pude recuperar el trabajo: ' + mensajeDe(e) }; }
  finally { ocultarCargando(); }
  if (!d || d.error) { avisar((d && d.error) || 'No pude recuperar el trabajo.'); return; }
  if (d.solo_audio) aplicarAudio(d.ruta, d); else aplicarVideo(d.ruta, d);
}

/* ---------- conexiones ---------- */
pr.guardar.addEventListener('click', () => { guardarProyecto(false); pr.guardar.blur(); });
pr.guardarComo.addEventListener('click', () => { guardarProyecto(true); pr.guardarComo.blur(); });
pr.abrirProyecto.addEventListener('click', () => { elegirProyectoYAbrir(); pr.abrirProyecto.blur(); });
pr.crearProyecto.addEventListener('click', () => { crearProyecto(); pr.crearProyecto.blur(); });
pr.btnRecuperar.addEventListener('click', recuperarTrabajo);
pr.btnDescartarRecup.addEventListener('click', async () => { await llamar('descartar_recuperacion'); pr.recuperar.hidden = true; });

window.addEventListener('keydown', (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey || e.code !== 'KeyS') return;
  e.preventDefault();
  if (document.querySelector('dialog[open]')) return;
  if (S.proy) guardarProyecto(e.shiftKey);
});

const _alActualizarProyectoPr = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoPr) _alActualizarProyectoPr();
  pintarMarcaProyecto();
};
pintarMarcaProyecto();
cargarRecientes();
