/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — panel de medios: varios videos en el mismo proyecto
   La lista de archivos del proyecto (los videos y la musica), con sus miniaturas: "Agregar videos…" los suma al panel
   (todavia no a la linea de tiempo), y cada uno se pone al final o en el cursor (editar_insertar_fuente: con su audio, y
   corriendo lo que sigue). Un video que no esta en uso se saca con la ✕.
   Tambien pide al motor los datos de cada video que aparece en el proyecto (cuadros por segundo, tabla de cuadros, miniaturas,
   espectro, como reproducirlo) y, cuando llegan, vuelve a armar la linea de tiempo: asegurarMedios() lo llama aplicarProyecto().
   Se carga despues de proyectos.js y usa su estado (S, llamar, operar, avisar, aplicarProyecto...).
   ============================================================ */
'use strict';

const md = {
  seccion:  $('sec-medios'),
  cuenta:   $('medios-cuenta'),
  lista:    $('medios-lista'),
  vacio:    $('medios-vacio'),
  agregar:  $('btn-agregar-videos'),
  aviso:    $('medios-aviso'),
  cargando: new Set(),       // videos de los que se esta pidiendo la informacion
  vigilados: new Set()       // videos cuya copia de reproduccion se esta preparando
};

function duracionCorta(s) {
  s = Math.max(0, Math.round(s));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

/* ---------- los datos de cada video ---------- */
async function pedirMedio(fid) {
  if (md.cargando.has(fid)) return;
  md.cargando.add(fid);
  let r;
  try { r = await llamar('medio_info', [fid]); } catch (e) { r = { error: 'No pude leer ese video.' }; }
  md.cargando.delete(fid);
  if (!S.proy || !S.proy.fuentes[fid]) return;            // mientras tanto se saco o se abrio otro proyecto
  if (!r || r.error) { S.medios[fid] = { fid, error: (r && r.error) || 'No pude leer ese video.', nombre: S.proy.fuentes[fid].nombre }; pintarMedios(); return; }
  S.medios[fid] = r;
  vigilarMedio(fid);
  aplicarProyecto(S.proy);                                  // ahora que se sabe de este video, la linea de tiempo se arma bien
}

/** Pide lo que falte de los videos del proyecto (se llama despues de cada cambio del proyecto). */
function asegurarMedios() {
  if (!S.proy || S.soloAudio) return;
  Object.values(S.proy.fuentes).forEach((f) => {
    if (f.tipo === 'video' && f.id !== S.fidPrincipal && !S.medios[f.id]) pedirMedio(f.id);
  });
  pintarMedios();
}

/** Mientras la copia de reproduccion de un video se prepara, se consulta cada tanto. */
function vigilarMedio(fid) {
  const m = S.medios[fid];
  if (!m || m.proxy !== 'generando' || md.vigilados.has(fid)) return;
  md.vigilados.add(fid);
  const paso = async () => {
    const actual = S.medios[fid];
    if (!S.proy || !S.proy.fuentes[fid] || actual !== m) { md.vigilados.delete(fid); return; }
    let e = null;
    try { e = await llamar('medio_estado', [fid]); } catch (err) { e = null; }
    if (e && e.estado === 'listo') {
      m.proxy = 'listo';
      m.reproducible = true;
      m.url = e.url;
      md.vigilados.delete(fid);
      pintarMedios();
      return;
    }
    if (e && e.estado === 'error') {
      m.proxy = 'error';
      m.proxy_error = e.error;
      md.vigilados.delete(fid);
      pintarMedios();
      return;
    }
    if (e) { m.proxy_progreso = e.progreso; pintarMedios(); }
    setTimeout(paso, 900);
  };
  paso();
}

/* ---------- la lista ---------- */
function usosDe(fid) {
  // cuantos clips (video con su audio enlazado cuentan uno solo) usan este archivo
  const grupos = new Set();
  if (S.proy) S.proy.pistas.forEach((p) => p.clips.forEach((c) => { if (c.fuente === fid) grupos.add(c.grupo); }));
  return grupos.size;
}

function pintarMedios() {
  const p = S.proy;
  md.seccion.hidden = !p;
  if (!p) return;
  const fuentes = Object.values(p.fuentes);
  md.cuenta.textContent = fuentes.length ? '(' + fuentes.length + ')' : '';
  md.agregar.disabled = !!S.soloAudio;
  md.aviso.hidden = !S.soloAudio;
  md.aviso.textContent = S.soloAudio ? 'Para sumar videos, abrí un video primero (este proyecto empezó con un audio).' : '';
  md.vacio.hidden = fuentes.length > 0;
  md.lista.textContent = '';
  fuentes.forEach((f) => {
    const m = S.medios[f.id] || null;
    const item = document.createElement('div');
    item.className = 'medio';
    item.dataset.fid = f.id;
    item.setAttribute('role', 'listitem');
    const mini = document.createElement('div');
    mini.className = 'medio__mini' + (f.tipo === 'audio' ? ' medio__mini--audio' : '');
    if (f.tipo === 'video' && m && m.tira && m.tira_cantidad && m.tira_ancho_mini) {
      mini.style.backgroundImage = 'url("' + m.tira + '")';
      mini.style.backgroundSize = (m.tira_cantidad * 100) + '% 100%';          // la primera miniatura de la tira
      mini.style.backgroundPosition = '0 0';
    } else {
      mini.textContent = f.tipo === 'audio' ? '♪' : '▦';
    }
    const datos = document.createElement('div');
    datos.className = 'medio__datos';
    const nombre = document.createElement('span');
    nombre.className = 'medio__nombre';
    nombre.textContent = f.nombre || f.ruta;
    nombre.title = f.ruta;
    const meta = document.createElement('span');
    meta.className = 'medio__meta';
    const trozos = [];
    if (f.tipo === 'video') {
      if (f.ancho && f.alto) trozos.push(f.ancho + '×' + f.alto);
      if (f.fps) trozos.push(String(Math.round(f.fps * 100) / 100).replace('.', ',') + ' fps');
    } else {
      trozos.push('audio');
    }
    trozos.push(duracionCorta(f.duracion));
    const usos = usosDe(f.id);
    if (usos) trozos.push('en uso' + (usos > 1 ? ' ×' + usos : ''));
    meta.textContent = trozos.join(' · ');
    datos.appendChild(nombre);
    datos.appendChild(meta);
    if (f.id === S.fidPrincipal) {
      const b = document.createElement('span');
      b.className = 'medio__marca';
      b.textContent = 'Principal';
      datos.appendChild(b);
    }
    if (m && m.error) {
      const e = document.createElement('span');
      e.className = 'medio__error';
      e.textContent = m.error;
      datos.appendChild(e);
    } else if (m && m.proxy === 'generando') {
      const e = document.createElement('span');
      e.className = 'medio__preparando';
      e.textContent = 'Preparando la reproducción… ' + Math.round((m.proxy_progreso || 0) * 100) + ' %';
      datos.appendChild(e);
    } else if (m && m.proxy === 'error') {
      const e = document.createElement('span');
      e.className = 'medio__error';
      e.textContent = (m.proxy_error || 'No se pudo preparar la reproducción.') + ' Se ve bien al exportar.';
      datos.appendChild(e);
    }
    const acciones = document.createElement('div');
    acciones.className = 'medio__acciones';
    const boton = (txt, accion, titulo, deshabilitado) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'medio__btn' + (accion === 'quitar' ? ' medio__btn--quitar' : '');
      b.textContent = txt;
      b.title = titulo;
      b.dataset.accion = accion;
      b.disabled = !!deshabilitado;
      b.addEventListener('click', () => accionMedio(f, accion));
      acciones.appendChild(b);
    };
    if (f.tipo === 'video') {
      const listo = !!(m && !m.error);
      boton('Al final', 'final', 'Poner al final de la línea de tiempo (con su audio)', !listo);
      boton('En el cursor', 'cursor', 'Poner en el borde de clip más cercano al cursor; lo que sigue se corre', !listo);
    } else {
      boton('Al cursor', 'audio', 'Poner este audio en el cursor (en una pista de audio extra)');
    }
    boton('✕', 'quitar', f.id === S.fidPrincipal ? 'El video principal no se puede sacar' : (usos ? 'Se usa en la línea de tiempo: borrá sus clips antes' : 'Sacar del panel'),
          f.id === S.fidPrincipal || usos > 0);
    item.appendChild(mini);
    item.appendChild(datos);
    item.appendChild(acciones);
    md.lista.appendChild(item);
  });
}

/* ---------- acciones ---------- */
async function accionMedio(f, accion) {
  if (accion === 'quitar') {
    let r;
    try { r = await llamar('quitar_medio', [f.id]); } catch (e) { r = { error: 'No pude sacarlo.' }; }
    if (r && r.error) { avisar(r.error, 'ojo'); if (r.proyecto) aplicarProyecto(r.proyecto); return; }
    delete S.medios[f.id];
    aplicarProyecto(r.proyecto);
    return;
  }
  if (accion === 'audio') {
    let r;
    try { r = await llamar('agregar_audio', [f.ruta, tiempoDe(S.cuadro)]); } catch (e) { r = { error: 'No pude poner el audio.' }; }
    if (r && r.proyecto) aplicarProyecto(r.proyecto);
    if (!r || r.error) avisar((r && r.error) || 'No pude poner el audio.', 'ojo');
    return;
  }
  const t = accion === 'final' ? null : tiempoDe(S.cuadro);
  const r = await operar('insertar_fuente', t === null ? [f.id] : [f.id, Math.round(t * 1000) / 1000]);
  if (!r) return;
  const res = r.resultado || {};
  avisar('Se puso «' + (f.nombre || 'el video') + '» desde los ' + formatoTiempo(res.inicio).replace(/,\d+$/, '') + '. «Deshacer» (Ctrl+Z) lo saca.', 'info');
  if (typeof res.inicio === 'number') irA(cuadroDe(res.inicio + 0.001), ANCHO_NITIDO);
}

async function agregarVideos() {
  if (!S.proy || S.soloAudio) return;
  let r;
  try { r = await llamar('elegir_videos'); } catch (e) { r = { error: 'No pude abrir el selector de archivos.' }; }
  if (!r || r.cancelado) return;
  if (r.error) { avisar(r.error); return; }
  await sumarRutas(r.rutas || []);
}

async function sumarRutas(rutas) {
  let nuevos = 0;
  for (const ruta of rutas) {
    let r;
    try { r = await llamar('agregar_medio', [ruta]); } catch (e) { r = { error: 'No pude agregar ese archivo.' }; }
    if (r && r.proyecto) aplicarProyecto(r.proyecto);
    if (!r || r.error) { avisar((r && r.error) || 'No pude agregar ese archivo.', 'ojo'); continue; }
    if (!r.repetido) nuevos++;
    else avisar('«' + nombreDe(ruta) + '» ya estaba en el panel.', 'info');
  }
  if (nuevos) avisar(nuevos === 1 ? 'Se agregó un video al panel. Ponelo en la línea de tiempo con «Al final» o «En el cursor».'
                                  : 'Se agregaron ' + nuevos + ' videos al panel. Ponelos en la línea de tiempo con «Al final» o «En el cursor».', 'info');
}

/* ---------- conexiones ---------- */
md.agregar.addEventListener('click', () => { agregarVideos(); md.agregar.blur(); });

// Soltar archivos SOBRE el panel los suma al proyecto (soltarlos en otro lado abre un proyecto nuevo)
['dragenter', 'dragover'].forEach((nombre) => {
  md.seccion.addEventListener(nombre, (e) => {
    if (!S.proy || S.soloAudio) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    md.seccion.classList.add('sec--suelta');
  });
});
md.seccion.addEventListener('dragleave', () => md.seccion.classList.remove('sec--suelta'));
md.seccion.addEventListener('drop', (e) => {
  md.seccion.classList.remove('sec--suelta');
  if (!S.proy || S.soloAudio) return;
  e.preventDefault();
  e.stopPropagation();
  el.zonaSuelta.hidden = true;
  const archivos = e.dataTransfer && e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
  const rutas = archivos.map((a) => a.path).filter(Boolean);
  if (rutas.length) { sumarRutas(rutas); return; }
  avisar('Desde acá no puedo leer la ruta de los archivos soltados. Usá «Agregar videos…».', 'ojo');
});

const _alActualizarProyectoMd = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoMd) _alActualizarProyectoMd();
  pintarMedios();
};
pintarMedios();
