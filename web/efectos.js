/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — efectos por clip
   Las secciones "Efectos de video" y "Efectos de audio" del panel de Propiedades.
   El catalogo (que efectos hay y que ajustes tiene cada uno) lo manda el motor
   (motor/efectos.py): este archivo NO sabe nada de ningun efecto en particular, arma los
   controles con lo que el catalogo dice. Un efecto nuevo en el motor aparece solo.
   Se carga despues de edicion.js y usa su estado (S, ed, operar, elegidos...).
   ============================================================ */
'use strict';

const fx = {
  catalogo: null,                       // {tipo: {nombre, categoria, descripcion, params: [...]}}
  transiciones: null,                   // {id: {nombre}}
  cuerpoTrans: $('trans-cuerpo'),
  seccionTrans: $('sec-transicion'),
  video: $('fx-video'),
  audio: $('fx-audio'),
  seccionVideo: $('sec-fx-video'),
  seccionAudio: $('sec-fx-audio')
};

async function cargarCatalogoEfectos() {
  try {
    const r = await llamar('efectos_catalogo');
    fx.catalogo = r && r.efectos ? r.efectos : {};
    fx.transiciones = r && r.transiciones ? r.transiciones : {};
  } catch (e) {
    fx.catalogo = {};
    fx.transiciones = {};
  }
  if (S.proy) pintarEfectos();
}

function formatoNumero(valor, spec) {
  const pasos = String(spec.paso).split('.')[1];
  const dec = pasos ? pasos.length : 0;
  return Number(valor).toFixed(dec).replace('.', ',') + (spec.unidad ? ' ' + spec.unidad : '');
}

/* ---------- la vista previa en el visor (aproximada: lo exportado es el exacto) ---------- */
function filtroCssDe(clip, sobre) {
  // sobre: {eid, id, valor}: un ajuste que se esta moviendo y todavia no se guardo
  const filtros = [];
  let voltear = [1, 1];
  ((clip && clip.efectos) || []).forEach((e) => {
    if (!e.activo) return;
    const p = Object.assign({}, e.params);
    if (sobre && sobre.eid === e.id) p[sobre.id] = sobre.valor;
    if (e.tipo === 'color_basico') {
      // ffmpeg suma el brillo y multiplica el contraste; el navegador multiplica los dos: de ahi lo aproximado
      filtros.push('brightness(' + (1 + p.brillo * 1.2).toFixed(3) + ')', 'contrast(' + p.contraste.toFixed(3) + ')',
                   'saturate(' + p.saturacion.toFixed(3) + ')');
    } else if (e.tipo === 'voltear') {
      if (p.horizontal) voltear[0] *= -1;
      if (p.vertical) voltear[1] *= -1;
    }
  });
  return { filtro: filtros.length ? filtros.join(' ') : 'none', volteo: (voltear[0] === 1 && voltear[1] === 1) ? 'none' : 'scale(' + voltear[0] + ', ' + voltear[1] + ')' };
}

function aplicarEfectosVisor(clip, sobre) {
  const visor = $('visor');
  if (!visor) return;
  const f = filtroCssDe(clip, sobre);
  visor.style.setProperty('--filtro', f.filtro);
  visor.style.setProperty('--volteo', f.volteo);
}

/* ---------- el logo encima («superponer»), en el visor: se ve y se arrastra con el mouse ----------
   Se dibuja sobre la imagen con la misma cuenta que el exportador (motor/efectos.py, subgrafo): el tamaño es un % del
   ancho, el margen un % del ancho en los dos sentidos, y el lugar libre un % de lo que sobra (0 = contra un borde,
   100 = contra el otro). Aproximado como el resto de la vista previa: el visor muestra la fuente, no el encuadre final. */
const logos = {
  capa: $('logos-visor'),
  urls: new Map(),          // ruta de la imagen -> URL que la sirve ('' = no se pudo)
  pidiendo: new Set(),
  arrastre: null,           // {img, cid, eid, dx, dy, x0, y0, movio, params}
  soltado: null,            // {eid, params}: lo que se solto, hasta que vuelve el proyecto con el cambio
  sobre: null               // {eid, id, valor}: un deslizador que se esta moviendo
};

function urlLogo(cid, e) {
  const ruta = e.params.archivo;
  if (logos.urls.has(ruta)) return logos.urls.get(ruta);
  if (!logos.pidiendo.has(ruta)) {
    logos.pidiendo.add(ruta);
    llamar('imagen_efecto', [cid, e.id])
      .then((r) => logos.urls.set(ruta, r && r.url ? r.url : ''))
      .catch(() => logos.urls.set(ruta, ''))
      .finally(() => { logos.pidiendo.delete(ruta); pintarLogosVisor(); });
  }
  return null;
}

function medioVisor() { return $('capa-video').hidden ? $('capa-cuadro') : $('capa-video'); }

function paramsLogo(e) {
  let p = Object.assign({ x: 50, y: 50, desde: 0, hasta: 0, margen: 0, opacidad: 1, tamano: 20 }, e.params);
  if (logos.soltado && logos.soltado.eid === e.id) p = Object.assign(p, logos.soltado.params);
  if (logos.arrastre && logos.arrastre.eid === e.id && logos.arrastre.params) p = Object.assign(p, logos.arrastre.params);
  if (logos.sobre && logos.sobre.eid === e.id) p[logos.sobre.id] = logos.sobre.valor;
  return p;
}

function colocarLogo(img, p, rm, rv) {
  const prop = img.naturalWidth ? img.naturalHeight / img.naturalWidth : 0;
  if (!prop) { img.style.visibility = 'hidden'; return; }      // todavia no cargo: se pinta en su onload
  img.style.visibility = '';
  const w = rm.width * p.tamano / 100, h = w * prop;
  const m = rm.width * (p.margen || 0) / 100;
  let x, y;
  if (p.posicion === 'libre') {
    x = (rm.width - w) * p.x / 100;
    y = (rm.height - h) * p.y / 100;
  } else {
    const [vert, horiz] = p.posicion === 'centro' ? ['centro', 'centro'] : p.posicion.split('_');
    x = horiz === 'izquierda' ? m : (horiz === 'derecha' ? rm.width - w - m : (rm.width - w) / 2);
    y = vert === 'arriba' ? m : (vert === 'abajo' ? rm.height - h - m : (rm.height - h) / 2);
  }
  img.style.left = (rm.left - rv.left + x) + 'px';
  img.style.top = (rm.top - rv.top + y) + 'px';
  img.style.width = w + 'px';
  img.style.height = h + 'px';
  img.style.opacity = String(p.opacidad);
}

function pintarLogosVisor() {
  const capa = logos.capa;
  if (!capa) return;
  const vivos = new Set();
  if (logos.arrastre) vivos.add(logos.arrastre.img);      // lo que se esta arrastrando no desaparece aunque corra el video
  const v1 = S.proy ? pistaDe('V1') : null;
  const tl = S.proy && S.info ? tiempoDe(S.cuadro) : 0;
  const c = v1 ? clipEn(v1, tl) : null;
  const medio = medioVisor();
  const rm = medio.getBoundingClientRect(), rv = $('visor').getBoundingClientRect();
  if (c && rm.height >= 20) {
    const local = tl - c.inicio;
    (c.efectos || []).forEach((e) => {
      if (!e.activo || e.tipo !== 'superponer' || !e.params.archivo) return;
      const p = paramsLogo(e);
      const arrastrado = logos.arrastre && logos.arrastre.eid === e.id;
      if (!arrastrado && (local < p.desde - 1e-6 || (p.hasta > 0 && local >= Math.max(p.hasta, p.desde + 0.1) - 1e-6))) return;
      const url = urlLogo(c.id, e);
      if (!url) return;
      let img = capa.querySelector('img[data-eid="' + e.id + '"]');
      if (!img) img = crearLogo(e.id);
      img.dataset.cid = c.id;
      if (img.getAttribute('src') !== url) img.src = url;
      vivos.add(img);
      colocarLogo(img, p, rm, rv);
    });
  }
  capa.querySelectorAll('img').forEach((img) => { if (!vivos.has(img)) img.remove(); });
}

function crearLogo(eid) {
  const img = document.createElement('img');
  img.className = 'logo-visor';
  img.alt = '';
  img.draggable = false;
  img.dataset.eid = eid;
  img.title = 'Arrastralo para ponerlo donde quieras';
  img.addEventListener('load', pintarLogosVisor);
  img.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const r = img.getBoundingClientRect();
    logos.arrastre = { img, cid: img.dataset.cid, eid, dx: ev.clientX - r.left, dy: ev.clientY - r.top, x0: ev.clientX, y0: ev.clientY, movio: false, params: null };
    try { img.setPointerCapture(ev.pointerId); } catch (err) { /* sin captura igual anda dentro del visor */ }
    img.classList.add('logo-visor--arrastrando');
  });
  img.addEventListener('pointermove', (ev) => {
    const a = logos.arrastre;
    if (!a || a.img !== img) return;
    if (!a.movio && Math.hypot(ev.clientX - a.x0, ev.clientY - a.y0) < 3) return;
    a.movio = true;
    const rm = medioVisor().getBoundingClientRect(), r = img.getBoundingClientRect();
    const sobraX = rm.width - r.width, sobraY = rm.height - r.height;
    const pct = (pos, sobra) => (sobra > 0.5 ? Math.round(Math.min(100, Math.max(0, pos / sobra * 100)) * 2) / 2 : 50);
    a.params = { posicion: 'libre', x: pct(ev.clientX - a.dx - rm.left, sobraX), y: pct(ev.clientY - a.dy - rm.top, sobraY) };
    pintarLogosVisor();
  });
  const soltar = () => {
    const a = logos.arrastre;
    if (!a || a.img !== img) return;
    logos.arrastre = null;
    img.classList.remove('logo-visor--arrastrando');
    if (a.movio && a.params) {
      // hasta que el motor confirma, se queda donde se solto (si no, saltaria un instante al lugar viejo)
      logos.soltado = { eid: a.eid, params: a.params };
      operar('cambiar_efecto', [a.cid, a.eid, a.params]).finally(() => {
        if (logos.soltado && logos.soltado.params === a.params) logos.soltado = null;
        pintarLogosVisor();
      });
    }
    pintarLogosVisor();
  };
  img.addEventListener('pointerup', soltar);
  img.addEventListener('pointercancel', soltar);
  logos.capa.appendChild(img);
  return img;
}

// la imagen cambia con cada cuadro (el tramo en que aparece): se engancha donde se pinta, como los subtitulos
const _pintarPosicionLogo = pintarPosicion;
pintarPosicion = function () {
  _pintarPosicionLogo();
  pintarLogosVisor();
};
window.addEventListener('resize', pintarLogosVisor);

/* ---------- el panel ---------- */
function claveFoco() {
  const a = document.activeElement;
  return a && a.dataset && a.dataset.fxk ? a.dataset.fxk : null;
}

function crearTarjeta(cid, e, def) {
  const tarjeta = document.createElement('div');
  tarjeta.className = 'fx' + (e.activo ? '' : ' fx--apagado');
  tarjeta.dataset.eid = e.id;

  const cab = document.createElement('div');
  cab.className = 'fx__cab';
  const interruptor = document.createElement('input');
  interruptor.type = 'checkbox';
  interruptor.checked = e.activo;
  interruptor.className = 'fx__activo';
  interruptor.dataset.fxk = e.id + ':activo';
  interruptor.title = e.activo ? 'Apagar este efecto (conserva sus valores)' : 'Prender este efecto';
  interruptor.setAttribute('aria-label', (e.activo ? 'Apagar ' : 'Prender ') + def.nombre);
  interruptor.addEventListener('change', () => operar('activar_efecto', [cid, e.id, interruptor.checked]));
  const nombre = document.createElement('span');
  nombre.className = 'fx__nombre';
  nombre.textContent = def.nombre;
  nombre.title = def.descripcion || '';
  cab.appendChild(interruptor);
  cab.appendChild(nombre);
  [['↑', -1, 'Subir (se aplica antes)'], ['↓', 1, 'Bajar (se aplica después)']].forEach(([txt, dir, ayuda]) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'fx__btn';
    b.textContent = txt;
    b.title = ayuda;
    b.setAttribute('aria-label', ayuda + ': ' + def.nombre);
    b.dataset.fxk = e.id + ':mover' + dir;
    b.addEventListener('click', () => operar('mover_efecto', [cid, e.id, dir]));
    cab.appendChild(b);
  });
  const quitar = document.createElement('button');
  quitar.type = 'button';
  quitar.className = 'fx__btn fx__btn--quitar';
  quitar.textContent = '✕';
  quitar.title = 'Quitar este efecto';
  quitar.setAttribute('aria-label', 'Quitar ' + def.nombre);
  quitar.dataset.fxk = e.id + ':quitar';
  quitar.addEventListener('click', () => operar('quitar_efecto', [cid, e.id]));
  cab.appendChild(quitar);
  tarjeta.appendChild(cab);

  const cuerpo = document.createElement('div');
  cuerpo.className = 'fx__cuerpo';
  def.params.forEach((spec) => {
    const campo = document.createElement('label');
    campo.className = 'campo' + (spec.tipo === 'bool' ? ' campo--casilla' : '');
    campo.appendChild(document.createTextNode(spec.nombre));
    // un proyecto viejo puede no tener un ajuste nuevo (el «desde» del logo, de la 1.2): vale el de por defecto
    const valor = e.params[spec.id] !== undefined ? e.params[spec.id] : spec.defecto;
    if (spec.tipo === 'opcion') {
      campo.classList.add('campo--lista');
      const lista = document.createElement('select');
      lista.dataset.fxk = e.id + ':' + spec.id;
      spec.opciones.forEach((o) => {
        const op = document.createElement('option');
        op.value = o.valor;
        op.textContent = o.nombre;
        lista.appendChild(op);
      });
      lista.value = valor;
      lista.addEventListener('change', () => operar('cambiar_efecto', [cid, e.id, { [spec.id]: lista.value }]));
      campo.appendChild(lista);
    } else if (spec.tipo === 'archivo') {
      campo.classList.add('campo--archivo');
      const nombre = document.createElement('span');
      nombre.className = 'fx__archivo';
      nombre.textContent = valor ? nombreDe(valor) : 'Ningún archivo';
      nombre.title = valor || '';
      const elegir = document.createElement('button');
      elegir.type = 'button';
      elegir.className = 'boton boton--chico';
      elegir.textContent = valor ? 'Cambiar…' : 'Elegir…';
      elegir.dataset.fxk = e.id + ':' + spec.id;
      elegir.addEventListener('click', async (ev) => {
        ev.preventDefault();
        let r;
        try { r = await llamar('elegir_lut', [spec.extensiones || null]); } catch (err) { r = { error: 'No pude abrir el selector de archivos.' }; }
        if (r && r.error) { avisar(r.error); return; }
        if (r && r.ruta) operar('cambiar_efecto', [cid, e.id, { [spec.id]: r.ruta }]);
      });
      campo.appendChild(nombre);
      campo.appendChild(elegir);
    } else if (spec.tipo === 'texto') {
      campo.classList.add('campo--texto');
      const caja = document.createElement('textarea');
      caja.rows = 2;
      caja.maxLength = spec.max;
      caja.value = valor || '';
      caja.placeholder = 'Escribí el texto';
      caja.dataset.fxk = e.id + ':' + spec.id;
      // se guarda al salir del cuadro (un solo cambio en el historial, no uno por letra)
      caja.addEventListener('change', () => operar('cambiar_efecto', [cid, e.id, { [spec.id]: caja.value }]));
      campo.appendChild(caja);
    } else if (spec.tipo === 'bool') {
      const caja = document.createElement('input');
      caja.type = 'checkbox';
      caja.checked = !!valor;
      caja.dataset.fxk = e.id + ':' + spec.id;
      caja.addEventListener('change', () => operar('cambiar_efecto', [cid, e.id, { [spec.id]: caja.checked }]));
      campo.insertBefore(caja, campo.firstChild);
    } else {
      const rango = document.createElement('input');
      rango.type = 'range';
      rango.min = String(spec.min);
      rango.max = String(spec.max);
      rango.step = String(spec.paso);
      rango.value = String(valor);
      rango.dataset.fxk = e.id + ':' + spec.id;
      const salida = document.createElement('output');
      salida.textContent = formatoNumero(valor, spec);
      // mientras se arrastra: solo el numero y la vista previa; se guarda UN cambio al soltar (no llenar el historial)
      rango.addEventListener('input', () => {
        salida.textContent = formatoNumero(rango.value, spec);
        const hallado = buscarClip(cid);
        const sobre = { eid: e.id, id: spec.id, valor: Number(rango.value) };
        if (hallado) aplicarEfectosVisor(hallado.clip, sobre);
        logos.sobre = sobre;
        pintarLogosVisor();
      });
      rango.addEventListener('change', () => {
        logos.sobre = null;
        operar('cambiar_efecto', [cid, e.id, { [spec.id]: Number(rango.value) }]);
      });
      campo.appendChild(salida);
      campo.appendChild(rango);
      if (spec.unidad === 's') {
        // «Aparece a los» / «Desaparece a los»: se puede tomar el tiempo de donde esta parada la linea roja
        const aca = document.createElement('button');
        aca.type = 'button';
        aca.className = 'boton boton--chico fx__aca';
        aca.textContent = 'Usar donde está la línea roja';
        campo.classList.add('campo--aca');
        aca.title = 'Poner este tiempo donde está parada la línea roja (contado desde el principio del clip)';
        aca.dataset.fxk = e.id + ':' + spec.id + ':aca';
        aca.addEventListener('click', (ev) => {
          ev.preventDefault();
          const hallado = buscarClip(cid);
          if (!hallado) return;
          const c = hallado.clip;
          const local = tiempoDe(S.cuadro) - c.inicio;
          if (local < -1e-6 || local > largoClip(c) + 1e-6) {
            avisar('La línea roja no está sobre este clip: llevala adonde querés que ' + (spec.id === 'hasta' ? 'desaparezca' : 'aparezca') + '.', 'ojo');
            return;
          }
          const v = Math.min(spec.max, Math.max(spec.min, Math.round(local * 10) / 10));
          operar('cambiar_efecto', [cid, e.id, { [spec.id]: v }]);
        });
        campo.appendChild(aca);
      }
    }
    // un ajuste que solo cuenta con cierta opcion (el lugar libre del logo, por ejemplo) se esconde con las otras
    if (spec.solo_si && Object.keys(spec.solo_si).some((k) => (e.params[k] !== undefined ? e.params[k] : null) !== spec.solo_si[k])) campo.hidden = true;
    cuerpo.appendChild(campo);
  });
  tarjeta.appendChild(cuerpo);
  const notas = [];
  if (def.aviso) notas.push(def.aviso);
  if (def.categoria === 'video' && !def.vista_previa) notas.push('Se ve al exportar: la vista previa todavía no lo muestra.');
  notas.forEach((txt) => {
    const nota = document.createElement('p');
    nota.className = 'fx__nota';
    nota.textContent = txt;
    tarjeta.appendChild(nota);
  });
  return tarjeta;
}

function pintarSeccionEfectos(contenedor, seccion, categoria, entrada) {
  contenedor.textContent = '';
  seccion.hidden = !entrada;
  if (!entrada) return;
  const cid = entrada.clip.id;
  const lista = entrada.clip.efectos || [];
  if (!lista.length) {
    const vacio = document.createElement('p');
    vacio.className = 'fx__vacio';
    vacio.textContent = 'Todavía no hay efectos en este clip.';
    contenedor.appendChild(vacio);
  }
  lista.forEach((e) => {
    const def = fx.catalogo[e.tipo];
    if (def) contenedor.appendChild(crearTarjeta(cid, e, def));
  });

  const fila = document.createElement('div');
  fila.className = 'fx__agregar';
  const lista_tipos = document.createElement('select');
  lista_tipos.setAttribute('aria-label', 'Efecto a agregar');
  Object.keys(fx.catalogo).filter((k) => fx.catalogo[k].categoria === categoria).forEach((k) => {
    const o = document.createElement('option');
    o.value = k;
    o.textContent = fx.catalogo[k].nombre;
    lista_tipos.appendChild(o);
  });
  const boton = document.createElement('button');
  boton.type = 'button';
  boton.className = 'boton boton--chico';
  boton.textContent = 'Agregar';
  boton.dataset.fxk = categoria + ':agregar';
  boton.addEventListener('click', () => { if (lista_tipos.value) operar('agregar_efecto', [cid, lista_tipos.value]); });
  fila.appendChild(lista_tipos);
  fila.appendChild(boton);
  contenedor.appendChild(fila);
  if (categoria === 'audio') {
    const nota = document.createElement('p');
    nota.className = 'fx__nota';
    nota.textContent = 'Los efectos de audio se oyen al exportar: la vista previa todavía no los reproduce.';
    contenedor.appendChild(nota);
  }
}

/* ---------- transicion de entrada del clip elegido ---------- */
function pintarTransicion(cs) {
  const cuerpo = fx.cuerpoTrans;
  cuerpo.textContent = '';
  const base = cs.length ? (cs.find((x) => x.pista.tipo === 'video') || cs[0]) : null;
  const t = base ? base.clip.transicion : null;
  const maximo = base ? (base.clip.transicion_max || 0) : 0;
  // sin otro clip pegado antes (o sin material a los lados): no hay nada que ofrecer
  fx.seccionTrans.hidden = !base || (!t && maximo < 0.1);
  if (fx.seccionTrans.hidden) return;
  const grupo = base.clip.grupo;
  const tope = Math.max(0.1, Math.min(3, Math.floor(maximo * 10) / 10));

  const campoTipo = document.createElement('label');
  campoTipo.className = 'campo campo--lista';
  campoTipo.appendChild(document.createTextNode('Tipo'));
  const lista = document.createElement('select');
  lista.dataset.fxk = 'trans:tipo';
  Object.keys(fx.transiciones || {}).forEach((k) => {
    const o = document.createElement('option');
    o.value = k;
    o.textContent = fx.transiciones[k].nombre;
    lista.appendChild(o);
  });
  lista.value = t ? t.tipo : 'disolver';
  campoTipo.appendChild(lista);
  cuerpo.appendChild(campoTipo);

  const campoDur = document.createElement('label');
  campoDur.className = 'campo';
  campoDur.appendChild(document.createTextNode('Duración'));
  const rango = document.createElement('input');
  rango.type = 'range';
  rango.min = '0.1';
  rango.max = String(tope);
  rango.step = '0.1';
  rango.value = String(Math.min(tope, t ? t.duracion : 1.0));
  rango.dataset.fxk = 'trans:duracion';
  const salida = document.createElement('output');
  const pintarSalida = () => { salida.textContent = Number(rango.value).toFixed(1).replace('.', ',') + ' s'; };
  pintarSalida();
  rango.addEventListener('input', pintarSalida);
  campoDur.appendChild(salida);
  campoDur.appendChild(rango);
  cuerpo.appendChild(campoDur);

  const aplicar = () => operar('poner_transicion', [grupo, lista.value, Number(rango.value)]);
  const boton = document.createElement('button');
  boton.type = 'button';
  boton.className = 'herr herr--ancho';
  boton.dataset.fxk = 'trans:accion';
  if (t) {
    lista.addEventListener('change', aplicar);
    rango.addEventListener('change', aplicar);
    boton.textContent = 'Quitar la transición';
    boton.addEventListener('click', () => operar('quitar_transicion', [grupo]));
  } else {
    boton.textContent = 'Agregar la transición';
    boton.addEventListener('click', aplicar);
  }
  cuerpo.appendChild(boton);
  const nota = document.createElement('p');
  nota.className = 'fx__nota';
  nota.textContent = 'Está centrada en el corte, con la imagen y el sonido que sobran a cada lado: no cambia lo que dura el proyecto. Se ve al exportar.';
  cuerpo.appendChild(nota);
}

/* ---------- velocidad, reversa y repetir ---------- */
const PASOS_VELOCIDAD = [0.25, 0.5, 1, 2, 4];

function nombreVelocidad(v) { return String(Number(v.toFixed(2))).replace('.', ',') + '×'; }

function pintarVelocidad(cs) {
  const cuerpo = $('vel-cuerpo');
  cuerpo.textContent = '';
  const base = cs.length ? (cs.find((x) => x.pista.tipo === 'video') || cs[0]) : null;
  $('sec-velocidad').hidden = !base;
  if (!base) return;
  const c = base.clip;
  const grupo = c.grupo;
  const v = c.velocidad || 1;
  const hayAudio = cs.some((x) => x.pista.tipo === 'audio');
  const hayVideo = cs.some((x) => x.pista.tipo === 'video');

  const aplicar = (nueva) => operar('velocidad', [grupo, nueva, mantener.checked, interpolar.checked]);

  // la velocidad se mueve en escala logaritmica: de ¼× a 4× con el 1× en el medio
  const campo = document.createElement('label');
  campo.className = 'campo';
  campo.appendChild(document.createTextNode('Velocidad'));
  const salida = document.createElement('output');
  salida.textContent = nombreVelocidad(v);
  const rango = document.createElement('input');
  rango.type = 'range';
  rango.min = '-2';
  rango.max = '2';
  rango.step = '0.05';
  rango.value = String(Math.log2(v));
  rango.dataset.fxk = 'vel:rango';
  rango.addEventListener('input', () => { salida.textContent = nombreVelocidad(Math.pow(2, Number(rango.value))); });
  rango.addEventListener('change', () => aplicar(Math.round(Math.pow(2, Number(rango.value)) * 100) / 100));
  campo.appendChild(salida);
  campo.appendChild(rango);
  cuerpo.appendChild(campo);

  const fila = document.createElement('div');
  fila.className = 'vel__pasos';
  PASOS_VELOCIDAD.forEach((p) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'boton boton--chico' + (Math.abs(v - p) < 0.005 ? ' boton--marcado' : '');
    b.textContent = nombreVelocidad(p);
    b.dataset.fxk = 'vel:' + p;
    b.addEventListener('click', () => aplicar(p));
    fila.appendChild(b);
  });
  cuerpo.appendChild(fila);

  const caja = (texto, marcado, visible, alCambiar, clave) => {
    const l = document.createElement('label');
    l.className = 'campo campo--casilla';
    const i = document.createElement('input');
    i.type = 'checkbox';
    i.checked = marcado;
    i.dataset.fxk = clave;
    i.addEventListener('change', () => alCambiar(i.checked));
    l.appendChild(i);
    l.appendChild(document.createTextNode(texto));
    l.hidden = !visible;
    cuerpo.appendChild(l);
    return i;
  };
  const mantener = caja('Mantener el tono del audio', c.mantener_tono !== false, hayAudio && v !== 1, () => aplicar(v), 'vel:tono');
  const interpolar = caja('Cámara lenta suave (más lento al exportar)', !!c.interpolar, hayVideo && v < 1, () => aplicar(v), 'vel:suave');
  caja('Al revés', !!c.reversa, true, (si) => operar('reversa', [grupo, si]), 'vel:reves');

  const repetir = document.createElement('div');
  repetir.className = 'fx__agregar';
  const veces = document.createElement('input');
  veces.type = 'number';
  veces.min = '2';
  veces.max = '20';
  veces.value = '2';
  veces.className = 'vel__veces';
  veces.setAttribute('aria-label', 'Cuántas veces repetir');
  const botonRep = document.createElement('button');
  botonRep.type = 'button';
  botonRep.className = 'boton boton--chico';
  botonRep.textContent = 'Repetir este clip';
  botonRep.dataset.fxk = 'vel:repetir';
  botonRep.addEventListener('click', () => operar('repetir_grupo', [grupo, Math.max(2, Math.min(20, parseInt(veces.value, 10) || 2))]));
  repetir.appendChild(veces);
  repetir.appendChild(botonRep);
  cuerpo.appendChild(repetir);

  const nota = document.createElement('p');
  nota.className = 'fx__nota';
  nota.textContent = 'La velocidad cambia lo que dura el clip y corre todo lo que sigue. La vista previa la reproduce; el «al revés» y la cámara lenta suave se ven al exportar.';
  cuerpo.appendChild(nota);
}

/* ---------- ducking: la musica baja cuando habla el audio del video ---------- */
function pintarDucking(cs) {
  const cuerpo = $('duck-cuerpo');
  cuerpo.textContent = '';
  const base = cs.find((x) => x.pista.tipo === 'audio' && x.pista.id !== 'A1');
  $('sec-ducking').hidden = !base;
  if (!base) return;
  const pista = base.pista;
  const d = pista.ducking || { activo: false, reduccion: 12 };
  const aplicar = () => operar('ducking', [pista.id, caja.checked, Number(rango.value)]);

  const l = document.createElement('label');
  l.className = 'campo campo--casilla';
  const caja = document.createElement('input');
  caja.type = 'checkbox';
  caja.checked = !!d.activo;
  caja.dataset.fxk = 'duck:activo';
  caja.addEventListener('change', aplicar);
  l.appendChild(caja);
  l.appendChild(document.createTextNode('Bajar cuando habla el audio del video'));
  cuerpo.appendChild(l);

  const campo = document.createElement('label');
  campo.className = 'campo';
  campo.appendChild(document.createTextNode('Cuánto baja'));
  const salida = document.createElement('output');
  salida.textContent = d.reduccion + ' dB';
  const rango = document.createElement('input');
  rango.type = 'range';
  rango.min = '3';
  rango.max = '24';
  rango.step = '1';
  rango.value = String(d.reduccion);
  rango.dataset.fxk = 'duck:rango';
  rango.addEventListener('input', () => { salida.textContent = rango.value + ' dB'; });
  rango.addEventListener('change', aplicar);
  campo.appendChild(salida);
  campo.appendChild(rango);
  cuerpo.appendChild(campo);

  const nota = document.createElement('p');
  nota.className = 'fx__nota';
  nota.textContent = 'Se aplica a toda la pista ' + pista.id + ': mientras suena el audio del video, esta música baja, y cuando calla vuelve. Se oye al exportar.';
  cuerpo.appendChild(nota);
}

function pintarEfectos() {
  if (!fx.catalogo) return;
  const cs = elegidos();
  pintarVelocidad(cs);
  pintarDucking(cs);
  pintarTransicion(cs);
  const foco = claveFoco();
  const video = cs.find((x) => x.pista.tipo === 'video') || null;
  const audio = cs.find((x) => x.pista.tipo === 'audio') || null;
  pintarSeccionEfectos(fx.video, fx.seccionVideo, 'video', video);
  pintarSeccionEfectos(fx.audio, fx.seccionAudio, 'audio', audio);
  pintarLogosVisor();
  if (foco) {
    const otra = document.querySelector('[data-fxk="' + foco.replace(/"/g, '') + '"]');
    if (otra) otra.focus();
  }
}

// Se engancha al panel: cada vez que edicion.js repinta el inspector, se repintan tambien los efectos.
const _pintarInspector = pintarInspector;
window.pintarInspector = function () {
  _pintarInspector();
  pintarEfectos();
};

cargarCatalogoEfectos();
