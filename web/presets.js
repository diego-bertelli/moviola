/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — presets y lotes («Reel en un clic»)
   Un dialogo para elegir una receta (cortar silencios, subtitular, nivelar el volumen, exportar) y aplicarla al proyecto abierto o a varios
   archivos de una vez. El motor (motor/lotes.py) trabaja en segundo plano sobre una COPIA: lo que esta abierto no cambia. Aca se muestra el
   avance, se puede cancelar y, al terminar, se lista cada archivo con lo que se hizo (o por que fallo).
   Se carga despues de youtube.js y usa su estado (S, llamar, avisar, mensajeDe...).
   ============================================================ */
'use strict';

const pst = {
  dlg:       $('dlg-presets'),
  abrirRiel: $('btn-presets'),
  abrirInicio: $('btn-lote'),
  armar:     $('pre-armar'),
  progreso:  $('pre-progreso'),
  resultado: $('pre-resultado'),
  archivos:  $('pre-archivos'),
  archivosN: $('pre-archivos-n'),
  archivosLista: $('pre-archivos-lista'),
  elegir:    $('pre-elegir'),
  lista:     $('pre-lista'),
  pasos:     $('pre-pasos'),
  silencios: $('pre-silencios'),
  subtitulos: $('pre-subtitulos'),
  karaoke:   $('pre-karaoke'),
  karaokeCampo: $('pre-karaoke-campo'),
  normalizar: $('pre-normalizar'),
  idioma:    $('pre-idioma'),
  idiomaCampo: $('pre-idioma-campo'),
  avisoWhisper: $('pre-aviso-whisper'),
  carpeta:   $('pre-carpeta'),
  cambiar:   $('pre-cambiar'),
  error:     $('pre-error'),
  cerrar:    $('pre-cerrar'),
  empezar:   $('pre-empezar'),
  progresoTexto: $('pre-progreso-texto'),
  barra:     $('pre-barra'),
  progresoPaso: $('pre-progreso-paso'),
  cancelar:  $('pre-cancelar'),
  resTitulo: $('pre-resultado-titulo'),
  resLista:  $('pre-resultado-lista'),
  mostrar:   $('pre-mostrar'),
  otra:      $('pre-otra'),
  listo:     $('pre-listo'),
  cat:       null,       // lo que devolvio presets_catalogo
  origen:    'proyecto', // 'proyecto' | 'archivos'
  preset:    'reel',
  rutas:     [],
  carpetaElegida: '',    // '' = la de siempre (al lado del original)
  temporizador: 0,
  ocupado:   false
};

function errorPre(texto) {
  pst.error.hidden = !texto;
  pst.error.textContent = texto || '';
}

function pasoPre(paso) {
  pst.armar.hidden = paso !== 'armar';
  pst.progreso.hidden = paso !== 'progreso';
  pst.resultado.hidden = paso !== 'resultado';
}

function presetActual() {
  return pst.cat ? pst.cat.presets.find((p) => p.clave === pst.preset) : null;
}

function nombreCorto(ruta) { return String(ruta).split(/[\\/]/).pop(); }

/* ---------- el formulario ---------- */
function pintarPresets() {
  pst.lista.textContent = '';
  pst.cat.presets.forEach((p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.setAttribute('role', 'radio');
    b.className = 'pre__tarjeta';
    b.dataset.clave = p.clave;
    const t = document.createElement('b');
    t.textContent = p.nombre;
    const n = document.createElement('small');
    n.textContent = p.nota;
    b.appendChild(t);
    b.appendChild(n);
    b.addEventListener('click', () => elegirPreset(p.clave));
    pst.lista.appendChild(b);
  });
}

function pintarEleccion() {
  pst.lista.querySelectorAll('.pre__tarjeta').forEach((b) => {
    const activo = b.dataset.clave === pst.preset;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('pre__tarjeta--activa', activo);
  });
  pst.dlg.querySelectorAll('[data-origen]').forEach((b) => {
    const activo = b.dataset.origen === pst.origen;
    b.setAttribute('aria-checked', activo ? 'true' : 'false');
    b.classList.toggle('exp__op--activo', activo);
  });
  pst.archivos.hidden = pst.origen !== 'archivos';
  const p = presetActual();
  pst.pasos.textContent = p ? 'Hace: ' + p.pasos.join(' → ') + '.' : '';
  const puedeTranscribir = !!(pst.cat && pst.cat.transcripcion && pst.cat.transcripcion.disponible);
  pst.subtitulos.disabled = !puedeTranscribir;
  if (!puedeTranscribir) pst.subtitulos.checked = false;
  pst.avisoWhisper.hidden = puedeTranscribir || !(p && p.ajustes.subtitulos);
  pst.avisoWhisper.textContent = puedeTranscribir ? '' : 'Este preset subtitula, pero ' + (pst.cat.transcripcion.motivo || 'falta whisper.') + ' Se hace todo lo demás.';
  pst.karaokeCampo.hidden = !pst.subtitulos.checked;
  pst.idiomaCampo.hidden = !pst.subtitulos.checked;
  pst.carpeta.textContent = carpetaMostrada();
  pst.carpeta.title = pst.carpeta.textContent;
  const hayQue = pst.origen === 'proyecto' ? !!S.proy : pst.rutas.length > 0;
  pst.empezar.disabled = !hayQue || pst.ocupado;
  pst.empezar.textContent = pst.origen === 'archivos' && pst.rutas.length > 1 ? 'Procesar ' + pst.rutas.length + ' archivos' : 'Empezar';
}

function carpetaMostrada() {
  if (pst.carpetaElegida) return pst.carpetaElegida;
  if (pst.origen === 'proyecto') return (pst.cat && pst.cat.carpeta) || '';
  return 'Una carpeta «moviola-salida» al lado de cada archivo';
}

function elegirPreset(clave) {
  pst.preset = clave;
  const p = presetActual();
  if (p) {
    pst.silencios.checked = p.ajustes.silencios;
    pst.subtitulos.checked = p.ajustes.subtitulos && !pst.subtitulos.disabled;
    pst.karaoke.checked = p.ajustes.karaoke;
    pst.normalizar.checked = p.ajustes.normalizar;
    pst.idioma.value = p.ajustes.idioma;
  }
  pintarEleccion();
}

function pintarArchivos() {
  pst.archivosLista.textContent = '';
  const n = pst.rutas.length;
  pst.archivosN.textContent = n ? n + (n === 1 ? ' archivo elegido' : ' archivos elegidos') : 'Ningún archivo elegido';
  pst.rutas.slice(0, 6).forEach((r) => {
    const li = document.createElement('li');
    li.textContent = nombreCorto(r);
    li.title = r;
    pst.archivosLista.appendChild(li);
  });
  if (n > 6) {
    const li = document.createElement('li');
    li.textContent = 'y ' + (n - 6) + ' más';
    pst.archivosLista.appendChild(li);
  }
}

/* ---------- abrir y cerrar ---------- */
async function abrirPresets(origen) {
  if (pst.dlg.open) return;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  let c;
  try { c = await llamar('presets_catalogo'); } catch (e) { c = { error: 'No pude preparar los presets: ' + mensajeDe(e) }; }
  if (!c || c.error) { avisar((c && c.error) || 'No pude preparar los presets.', 'ojo'); return; }
  const e = await llamar('lote_estado').catch(() => ({ estado: 'ninguno' }));
  pst.cat = c;
  pst.origen = (origen === 'archivos' || !S.proy) ? 'archivos' : 'proyecto';
  if (!pst.idioma.options.length) {
    c.idiomas.forEach((i) => {
      const o = document.createElement('option');
      o.value = i.valor;
      o.textContent = i.nombre;
      pst.idioma.appendChild(o);
    });
  }
  pintarPresets();
  if (!c.presets.some((p) => p.clave === pst.preset)) pst.preset = c.presets[0].clave;
  pst.carpetaElegida = '';
  errorPre('');
  pintarArchivos();
  elegirPreset(pst.preset);
  pst.dlg.querySelector('[data-origen="proyecto"]').disabled = !S.proy;
  pst.dlg.showModal();
  if (e && e.estado === 'procesando') { pasoPre('progreso'); sondearPre(); return; }
  pasoPre('armar');
  pst.empezar.focus();
}

function cerrarPresets() {
  clearTimeout(pst.temporizador);
  pst.temporizador = 0;
  if (pst.dlg.open) pst.dlg.close();
}

/* ---------- elegir archivos y carpeta ---------- */
async function elegirArchivosPre() {
  let r;
  try { r = await llamar('elegir_videos'); } catch (e) { r = { error: 'No pude abrir el selector de archivos.' }; }
  if (r && r.error) { errorPre(r.error); return; }
  if (!r || !r.rutas) return;
  const max = (pst.cat && pst.cat.maximo) || 500;
  pst.rutas = r.rutas.slice(0, max);
  errorPre(r.rutas.length > max ? 'Son demasiados: se toman los primeros ' + max + '.' : '');
  pintarArchivos();
  pintarEleccion();
}

async function cambiarCarpetaPre() {
  let r;
  try { r = await llamar('elegir_carpeta'); } catch (e) { r = { error: 'No pude abrir el selector de carpetas.' }; }
  if (r && r.error) { errorPre(r.error); return; }
  if (!r || !r.ruta) return;
  pst.carpetaElegida = r.ruta;
  errorPre('');
  pintarEleccion();
}

/* ---------- procesar ---------- */
function cambiosDeLaPantalla() {
  const c = { silencios: pst.silencios.checked, normalizar: pst.normalizar.checked };
  if (!pst.subtitulos.disabled) {
    c.subtitulos = pst.subtitulos.checked;
    if (pst.subtitulos.checked) { c.idioma = pst.idioma.value; c.karaoke = pst.karaoke.checked; }
  }
  return c;
}

async function empezarPre() {
  if (pst.ocupado) return;
  errorPre('');
  pst.ocupado = true;
  pst.empezar.disabled = true;
  let r;
  try {
    r = await llamar('lote_iniciar', [{ preset: pst.preset, cambios: cambiosDeLaPantalla(), carpeta: pst.carpetaElegida,
                                          origenes: pst.origen === 'archivos' ? pst.rutas : null }]);
  } catch (e) { r = { error: 'No pude empezar: ' + mensajeDe(e) }; }
  pst.ocupado = false;
  pst.empezar.disabled = false;
  if (!r || r.error) { errorPre((r && r.error) || 'No pude empezar.'); return; }
  pst.barra.style.width = '0%';
  pst.progresoTexto.textContent = 'Empezando…';
  pst.progresoPaso.textContent = '';
  pst.cancelar.disabled = false;
  pasoPre('progreso');
  pst.cancelar.focus();
  sondearPre();
}

async function sondearPre() {
  clearTimeout(pst.temporizador);
  let e;
  try { e = await llamar('lote_estado'); } catch (err) { pst.temporizador = setTimeout(sondearPre, 900); return; }
  if (!pst.dlg.open) return;
  if (e.estado === 'procesando') {
    const pct = Math.max(0, Math.min(100, Math.round((e.progreso || 0) * 100)));
    pst.barra.style.width = pct + '%';
    pst.progresoTexto.textContent = (e.n > 1 ? 'Archivo ' + (e.i + 1) + ' de ' + e.n + ' · ' : '') + pct + ' %';
    pst.progresoPaso.textContent = [e.nombre, e.paso].filter(Boolean).join(' — ');
    pst.temporizador = setTimeout(sondearPre, 500);
    return;
  }
  if (e.estado === 'listo') { mostrarResultadoPre(e); return; }
  if (e.estado === 'cancelado') {
    pasoPre('armar');
    errorPre('Cancelado. No quedó ningún archivo a medias.');
    return;
  }
  pasoPre('armar');
  errorPre(e.error || 'No pude procesar.');
}

function mostrarResultadoPre(e) {
  pasoPre('resultado');
  const bien = e.ok || 0;
  const mal = (e.fallaron || 0) + (e.canceladas || 0);
  pst.resTitulo.textContent = mal ? bien + ' listos, ' + mal + ' con problemas.' : (bien === 1 ? 'Listo: ya está guardado.' : 'Listo: ' + bien + ' archivos guardados.');
  pst.resLista.textContent = '';
  e.resultados.forEach((r) => {
    const li = document.createElement('li');
    li.className = r.ok ? 'pre__res pre__res--bien' : 'pre__res pre__res--mal';
    const t = document.createElement('b');
    t.textContent = r.ok ? r.nombre : nombreCorto(r.origen);
    li.appendChild(t);
    const d = document.createElement('span');
    if (r.ok) {
      const partes = [formatoTiempo(r.duracion), tamanoLegible(r.tamano_bytes)];
      if (r.silencios_quitados) partes.push('−' + String(Math.round(r.silencios_quitados * 10) / 10).replace('.', ',') + ' s de silencios');
      if (r.frases) partes.push(r.frases + ' frases');
      d.textContent = ' — ' + partes.join(' · ');
    } else {
      d.textContent = ' — ' + (r.error || 'No se pudo.');
    }
    li.appendChild(d);
    (r.avisos || []).forEach((a) => {
      const p = document.createElement('small');
      p.textContent = a;
      li.appendChild(p);
    });
    pst.resLista.appendChild(li);
  });
  pst.mostrar.hidden = !e.resultados.some((r) => r.ok);
  pst.listo.focus();
}

async function cancelarPre() {
  pst.cancelar.disabled = true;
  pst.progresoTexto.textContent = 'Cancelando…';
  try { await llamar('lote_cancelar'); } catch (e) { /* el sondeo cuenta lo que paso */ }
}

/* ---------- conexiones ---------- */
pst.abrirRiel.addEventListener('click', () => { abrirPresets('proyecto'); pst.abrirRiel.blur(); });
pst.abrirInicio.addEventListener('click', () => { abrirPresets('archivos'); pst.abrirInicio.blur(); });
pst.dlg.querySelectorAll('[data-origen]').forEach((b) => b.addEventListener('click', () => { pst.origen = b.dataset.origen; errorPre(''); pintarEleccion(); }));
pst.elegir.addEventListener('click', elegirArchivosPre);
pst.cambiar.addEventListener('click', cambiarCarpetaPre);
pst.subtitulos.addEventListener('change', pintarEleccion);
pst.empezar.addEventListener('click', empezarPre);
pst.cancelar.addEventListener('click', cancelarPre);
pst.cerrar.addEventListener('click', cerrarPresets);
pst.listo.addEventListener('click', cerrarPresets);
pst.otra.addEventListener('click', () => { pasoPre('armar'); errorPre(''); pintarEleccion(); pst.empezar.focus(); });
pst.mostrar.addEventListener('click', () => { llamar('mostrar_en_carpeta').then((r) => { if (r && r.error) avisar(r.error, 'ojo'); }); });
pst.dlg.addEventListener('cancel', (e) => { if (!pst.progreso.hidden) e.preventDefault(); });
pst.dlg.addEventListener('close', () => { clearTimeout(pst.temporizador); pst.temporizador = 0; });

window.addEventListener('keydown', (e) => {
  if (pst.dlg.open) e.stopImmediatePropagation();
}, true);

// el boton del riel solo con un proyecto abierto
const _alActualizarProyectoPre = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoPre) _alActualizarProyectoPre();
  pst.abrirRiel.disabled = !S.proy;
};
pst.abrirRiel.disabled = true;
