/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — subtitulos
   El dialogo "Subtitulos…": transcribir (el motor corre whisper en segundo plano; aca se muestra el avance y se
   cancela), la lista de frases editable (texto, inicio, final), el estilo (armado solo con el catalogo del motor)
   y el aviso de "el video cambio despues de transcribir". Ademas dibuja la frase actual sobre el visor.
   Las frases viven en el proyecto (S.proy.subtitulos): todo cambio pasa por operar() y entra al historial.
   Se carga despues de silencios.js y usa su estado (S, llamar, operar, avisar, formatoTiempo...).
   ============================================================ */
'use strict';

const sb = {
  boton:     $('btn-subtitulos'),
  dlg:       $('dlg-subtitulos'),
  idioma:    $('sub-idioma'),
  letras:    $('sub-letras'),
  letrasVal: $('sub-letras-valor'),
  motivo:    $('sub-motivo'),
  progTexto: $('sub-progreso-texto'),
  riel:      $('sub-riel'),
  barra:     $('sub-barra'),
  campos:    $('sub-campos-trans'),
  cancelarT: $('sub-cancelar-trans'),
  transcribir: $('sub-transcribir-ya'),
  desact:    $('sub-desactualizado'),
  alDia:     $('sub-al-dia'),
  cuenta:    $('sub-cuenta'),
  lista:     $('sub-lista'),
  vacio:     $('sub-vacio'),
  agregar:   $('sub-agregar'),
  borrarTodas: $('sub-borrar-todas'),
  estilo:    $('sub-estilo'),
  error:     $('sub-error'),
  cerrar:    $('sub-cerrar'),
  visor:     $('subtitulo-visor'),
  cat:       null,          // catalogo del motor (estilo, idiomas, letras)
  puede:     false,         // esta PC puede transcribir
  temporizador: 0,
  rutaAlAbrir: null
};

const FUENTES_CSS = {
  segoeui: ['"Segoe UI", sans-serif', 400], segoeuib: ['"Segoe UI", sans-serif', 700], arial: ['Arial, sans-serif', 400], arialbd: ['Arial, sans-serif', 700],
  georgia: ['Georgia, serif', 400], impact: ['Impact, sans-serif', 400], times: ['"Times New Roman", serif', 400], verdana: ['Verdana, sans-serif', 400]
};
const COLORES_CSS = { blanco: '#FFFFFF', amarillo: '#FFFF00', negro: '#000000', coral: '#FF6D5A', celeste: '#7FD8FF', verde: '#5FD6A6' };

function subs() { return (S.proy && S.proy.subtitulos) || { frases: [], estilo: {} }; }

function errorSub(texto) {
  sb.error.hidden = !texto;
  sb.error.textContent = texto || '';
}

function comaSub(n, dec) { return Number(n).toFixed(dec).replace('.', ','); }

/* ---------- la frase actual sobre el visor ---------- */
// Las palabras de una frase con el segundo en que empieza cada una: las medidas (si la frase no cambio) o repartidas segun las letras.
function piezasDeFrase(f) {
  const por = {};
  (subs().palabras || []).forEach((w) => { por[w.id] = w; });
  const medidas = (f.palabras || []).map((i) => por[i]);
  const norm = (x) => x.split(/\s+/).filter(Boolean).join(' ');
  if (medidas.length && medidas.every(Boolean) && norm(medidas.map((w) => w.texto).join(' ')) === norm(f.texto)) return medidas.map((w) => [w.texto, w.inicio]);
  const ps = f.texto.split(/\s+/).filter(Boolean);
  const total = ps.reduce((a, x) => a + Math.max(1, x.length), 0) || 1;
  let acum = 0;
  return ps.map((x) => { const pz = [x, f.inicio + (f.fin - f.inicio) * acum / total]; acum += Math.max(1, x.length); return pz; });
}

function pintarSubtituloVisor() {
  const v = sb.visor;
  if (!v) return;
  const s = subs();
  if (!S.proy || !S.info || !s.frases.length) { v.hidden = true; return; }
  const t = tiempoDe(S.cuadro);
  const f = s.frases.find((x) => t >= x.inicio - 1e-6 && t < x.fin - 1e-6);
  if (!f) { v.hidden = true; return; }
  const e = s.estilo || {};
  // se dibuja sobre la IMAGEN (no sobre todo el visor): el visor deja bordes cuando la proporcion no es la del panel
  const medio = $('capa-video').hidden ? $('capa-cuadro') : $('capa-video');
  const rm = medio.getBoundingClientRect(), rv = $('visor').getBoundingClientRect();
  if (rm.height < 20) { v.hidden = true; return; }
  const alto = rm.height;
  const [fam, peso] = FUENTES_CSS[e.fuente] || FUENTES_CSS.segoeuib;
  v.hidden = false;
  if (e.karaoke) {
    // «karaoke»: la palabra que se dice va del color de resalte (lo mismo que se quema al exportar)
    v.textContent = '';
    const piezas = piezasDeFrase(f);
    let actual = 0;
    piezas.forEach((pz, i) => { if (t >= pz[1] - 1e-6) actual = i; });
    piezas.forEach((pz, i) => {
      const sp = document.createElement('span');
      sp.textContent = e.mayusculas ? pz[0].toUpperCase() : pz[0];
      if (i === actual) sp.style.color = COLORES_CSS[e.resaltado] || '#FFFF00';
      v.appendChild(sp);
      if (i < piezas.length - 1) v.appendChild(document.createTextNode(' '));
    });
  } else {
    v.textContent = e.mayusculas ? f.texto.toUpperCase() : f.texto;
  }
  v.style.fontFamily = fam;
  v.style.fontWeight = String(peso);
  v.style.fontSize = Math.max(8, Math.round(alto * (e.tamano || 6) / 100)) + 'px';
  v.style.color = COLORES_CSS[e.color] || '#FFFFFF';
  v.style.textShadow = e.contorno && !e.caja ? '0 0 3px #000, 0 0 3px #000, 1px 1px 2px #000, -1px -1px 2px #000' : 'none';
  v.style.background = e.caja ? 'rgba(0,0,0,0.55)' : 'transparent';
  v.style.left = Math.round(rm.left - rv.left + rm.width * 0.05) + 'px';
  v.style.width = Math.round(rm.width * 0.9) + 'px';
  const margen = alto * (e.margen || 0) / 100;
  v.style.top = v.style.bottom = '';
  v.style.transform = '';
  if (e.posicion === 'arriba') v.style.top = Math.round(rm.top - rv.top + margen) + 'px';
  else if (e.posicion === 'centro') { v.style.top = Math.round(rm.top - rv.top + alto / 2) + 'px'; v.style.transform = 'translateY(-50%)'; }
  else v.style.bottom = Math.round(rv.bottom - rm.bottom + margen) + 'px';
}

// la posicion cambia con cada cuadro: se engancha donde se pinta
const _pintarPosicionSub = pintarPosicion;
pintarPosicion = function () {
  _pintarPosicionSub();
  pintarSubtituloVisor();
};

/* ---------- estilo ---------- */
function construirEstilo() {
  sb.estilo.textContent = '';
  const e = subs().estilo || {};
  (sb.cat ? sb.cat.estilo : []).forEach((spec) => {
    const campo = document.createElement('label');
    campo.className = 'campo' + (spec.tipo === 'bool' ? ' campo--casilla' : '') + (spec.tipo === 'opcion' ? ' campo--lista' : '');
    campo.appendChild(document.createTextNode(spec.nombre));
    const valor = e[spec.id] !== undefined ? e[spec.id] : spec.defecto;
    if (spec.tipo === 'opcion') {
      const lista = document.createElement('select');
      lista.dataset.sbk = spec.id;
      spec.opciones.forEach((o) => {
        const op = document.createElement('option');
        op.value = o.valor;
        op.textContent = o.nombre;
        lista.appendChild(op);
      });
      lista.value = valor;
      lista.addEventListener('change', () => operar('subtitulos_estilo', [{ [spec.id]: lista.value }]));
      campo.appendChild(lista);
    } else if (spec.tipo === 'bool') {
      const caja = document.createElement('input');
      caja.type = 'checkbox';
      caja.checked = !!valor;
      caja.dataset.sbk = spec.id;
      caja.addEventListener('change', () => operar('subtitulos_estilo', [{ [spec.id]: caja.checked }]));
      campo.insertBefore(caja, campo.firstChild);
    } else {
      const rango = document.createElement('input');
      rango.type = 'range';
      rango.min = String(spec.min);
      rango.max = String(spec.max);
      rango.step = String(spec.paso);
      rango.value = String(valor);
      rango.dataset.sbk = spec.id;
      const salida = document.createElement('output');
      salida.textContent = comaSub(valor, spec.paso < 1 ? 1 : 0) + ' ' + (spec.unidad || '');
      rango.addEventListener('input', () => { salida.textContent = comaSub(rango.value, spec.paso < 1 ? 1 : 0) + ' ' + (spec.unidad || ''); });
      rango.addEventListener('change', () => operar('subtitulos_estilo', [{ [spec.id]: Number(rango.value) }]));
      campo.appendChild(salida);
      campo.appendChild(rango);
    }
    sb.estilo.appendChild(campo);
  });
}

/* ---------- lista de frases ---------- */
function pintarFrases() {
  const s = subs();
  sb.lista.textContent = '';
  sb.vacio.hidden = s.frases.length > 0;
  sb.cuenta.textContent = s.frases.length ? '(' + s.frases.length + ')' : '';
  sb.borrarTodas.disabled = !s.frases.length;
  sb.desact.hidden = !(S.proy && S.proy.subtitulos_desactualizados);
  s.frases.forEach((f) => {
    const li = document.createElement('li');
    li.className = 'sub__frase';
    li.dataset.sid = f.id;
    const tiempos = document.createElement('span');
    tiempos.className = 'sub__tiempos';
    ['inicio', 'fin'].forEach((campo, i) => {
      if (i) tiempos.appendChild(document.createTextNode(' – '));
      const n = document.createElement('input');
      n.type = 'number';
      n.className = 'sub__t';
      n.min = '0';
      n.step = '0.1';
      n.value = String(f[campo]);
      n.setAttribute('aria-label', campo === 'inicio' ? 'Empieza (segundos)' : 'Termina (segundos)');
      n.dataset.sbf = campo;
      n.addEventListener('change', () => operar('subtitulo_cambiar', [f.id, { [campo]: Number(n.value) }]));
      tiempos.appendChild(n);
    });
    const texto = document.createElement('input');
    texto.type = 'text';
    texto.className = 'sub__texto';
    texto.value = f.texto;
    texto.maxLength = 400;
    texto.setAttribute('aria-label', 'Texto de la frase');
    texto.dataset.sbf = 'texto';
    texto.addEventListener('change', () => operar('subtitulo_cambiar', [f.id, { texto: texto.value }]));
    const ir = document.createElement('button');
    ir.type = 'button';
    ir.className = 'sub__btn';
    ir.textContent = '▸';
    ir.title = 'Ir a esta frase en el visor';
    ir.setAttribute('aria-label', 'Ir a esta frase');
    ir.addEventListener('click', () => irA(cuadroDe(f.inicio)));
    const quitar = document.createElement('button');
    quitar.type = 'button';
    quitar.className = 'sub__btn sub__btn--quitar';
    quitar.textContent = '✕';
    quitar.title = 'Quitar esta frase';
    quitar.setAttribute('aria-label', 'Quitar esta frase');
    quitar.dataset.sbf = 'quitar';
    quitar.addEventListener('click', () => operar('subtitulo_quitar', [f.id]));
    li.appendChild(tiempos);
    li.appendChild(texto);
    li.appendChild(ir);
    li.appendChild(quitar);
    sb.lista.appendChild(li);
  });
}

/* ---------- transcribir ---------- */
function mostrarTranscripcion(estado) {
  const activa = estado && estado.estado === 'transcribiendo';
  sb.progTexto.hidden = !activa;
  sb.riel.hidden = !activa;
  sb.cancelarT.hidden = !activa;
  sb.transcribir.hidden = activa;
  sb.campos.hidden = activa;
  if (activa) {
    const pct = Math.round((estado.progreso || 0) * 100);
    sb.progTexto.textContent = 'Transcribiendo… ' + pct + ' %. La primera vez tarda un poco más (carga el modelo).';
    sb.barra.style.width = pct + '%';
  }
}

async function sondearTranscripcion() {
  clearTimeout(sb.temporizador);
  sb.temporizador = 0;
  let e;
  try { e = await llamar('transcribir_estado'); } catch (err) { e = { estado: 'error', error: 'Perdí la conexión con el motor.' }; }
  if (e.estado === 'transcribiendo') {
    mostrarTranscripcion(e);
    sb.temporizador = setTimeout(sondearTranscripcion, 700);
    return;
  }
  mostrarTranscripcion(null);
  if (e.estado === 'listo') {
    if (e.montaje_cambio) {
      errorSub('El video cambió mientras se transcribía: las frases no coinciden. Volvé a transcribir.');
      llamar('transcribir_cancelar');
      return;
    }
    const r = await operar('subtitulos_poner', [e.frases, e.palabras || []]);
    if (r) {
      const n = (r.resultado !== undefined && r.resultado !== null) ? r.resultado : e.frases.length;
      avisar(n ? 'Listo: ' + n + (n === 1 ? ' frase.' : ' frases.') + ' Si algo no está bien, corregilo en la lista. «Deshacer» (Ctrl+Z) vuelve a las de antes.'
               : 'No se entendió ninguna frase. Probá con otro idioma o revisá que la pista de voz tenga sonido.', 'info');
    }
  } else if (e.estado === 'error') {
    errorSub(e.error || 'No pude transcribir.');
  }
}

async function iniciarTranscripcion() {
  errorSub('');
  let r;
  try { r = await llamar('transcribir_iniciar', [sb.idioma.value, Number(sb.letras.value)]); }
  catch (e) { r = { error: 'No pude empezar: ' + mensajeDe(e) }; }
  if (!r || r.error) { errorSub((r && r.error) || 'No pude empezar a transcribir.'); return; }
  mostrarTranscripcion({ estado: 'transcribiendo', progreso: 0 });
  sondearTranscripcion();
}

async function cancelarTranscripcion() {
  try { await llamar('transcribir_cancelar'); } catch (e) { /* sigue */ }
}

/* ---------- abrir y cerrar ---------- */
async function abrirSubtitulos() {
  if (!S.info || !S.proy || sb.dlg.open) return;
  if (S.reproduciendo) { try { await pausar(); } catch (e) { /* sigue */ } }
  errorSub('');
  let r;
  try { r = await llamar('subtitulos_catalogo'); } catch (e) { r = { error: 'No pude preparar los subtítulos.' }; }
  if (!r || r.error) { avisar((r && r.error) || 'No pude preparar los subtítulos.'); return; }
  sb.cat = r.catalogo;
  sb.puede = !!r.transcripcion.disponible;
  if (!sb.idioma.options.length) {
    r.catalogo.idiomas.forEach((i) => {
      const op = document.createElement('option');
      op.value = i.valor;
      op.textContent = i.nombre;
      sb.idioma.appendChild(op);
    });
    sb.idioma.value = 'es';
    sb.letras.min = String(r.catalogo.letras.min);
    sb.letras.max = String(r.catalogo.letras.max);
    sb.letras.value = String(r.catalogo.letras.defecto);
    sb.letrasVal.textContent = sb.letras.value;
  }
  sb.motivo.hidden = sb.puede;
  sb.motivo.textContent = sb.puede ? '' : r.transcripcion.motivo;
  sb.transcribir.disabled = !sb.puede;
  sb.rutaAlAbrir = S.ruta;
  construirEstilo();
  pintarFrases();
  const estado = await llamar('transcribir_estado').catch(() => null);
  mostrarTranscripcion(estado && estado.estado === 'transcribiendo' ? estado : null);
  if (estado && estado.estado === 'transcribiendo') sondearTranscripcion();
  sb.dlg.showModal();
  (sb.puede ? sb.transcribir : sb.agregar).focus();
}

function cerrarSubtitulos() {
  if (sb.dlg.open) sb.dlg.close();
}

/* ---------- conexiones ---------- */
sb.boton.addEventListener('click', () => { abrirSubtitulos(); sb.boton.blur(); });
sb.cerrar.addEventListener('click', cerrarSubtitulos);
sb.transcribir.addEventListener('click', iniciarTranscripcion);
sb.cancelarT.addEventListener('click', cancelarTranscripcion);
sb.letras.addEventListener('input', () => { sb.letrasVal.textContent = sb.letras.value; });
sb.alDia.addEventListener('click', () => operar('subtitulos_al_dia', []));
sb.borrarTodas.addEventListener('click', () => operar('subtitulos_borrar', []));
sb.agregar.addEventListener('click', () => {
  const t = tiempoDe(S.cuadro);
  const fin = Math.min(S.proy.duracion, t + 2);
  if (fin - t < 0.2) { errorSub('El cursor está al final del video: movelo antes de agregar una frase.'); return; }
  errorSub('');
  operar('subtitulo_agregar', [Math.round(t * 1000) / 1000, Math.round(fin * 1000) / 1000, 'Escribí acá']);
});

// Con el dialogo abierto, ninguna tecla llega a los atajos del visor y la edicion.
window.addEventListener('keydown', (e) => {
  if (sb.dlg.open) e.stopImmediatePropagation();
}, true);

// El boton y la lista dependen del proyecto: se actualizan con el.
const _alActualizarProyectoSub = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoSub) _alActualizarProyectoSub();
  sb.boton.disabled = !S.proy;
  if (sb.dlg.open) {
    if (S.ruta !== sb.rutaAlAbrir) { cerrarSubtitulos(); return; }
    pintarFrases();
    construirEstilo();
  }
  pintarSubtituloVisor();
};
sb.boton.disabled = true;
