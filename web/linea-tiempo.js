/* Moviola
 * Copyright (C) 2026 Diego Bertelli y Claude (Anthropic, Claude Sonnet 5.5)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Este programa se distribuye SIN NINGUNA GARANTIA. Ver el archivo LICENSE.
 */
/* ============================================================
   Moviola — la linea de tiempo con el mouse
   - Zoom y desplazamiento: el lienzo (#carriles) se hace mas ancho dentro de un contenedor que se desplaza; todo lo que ya se dibujaba
     «como fraccion del ancho» (miniaturas, espectro, cursor, marcas) sigue andando igual. Regla de tiempo arriba. Ctrl + rueda, + / - / 0.
   - Arrastrar un clip de video (con su audio) lo cambia de lugar entre los demas (mover_grupo); un audio suelto, la musica, se mueve a
     donde se suelte (mover_clip).
   - Tirar de los bordes de un clip lo recorta o lo estira (recortar_borde): el bloque principal corre lo que sigue; un audio suelto no.
   - Iman: los bordes se pegan al cursor, a las marcas de entrada y salida y a los bordes de los demas clips (Alt lo apaga mientras se arrastra).
   Todo cambio pasa por operar() y entra al historial. Se carga despues de texto.js y usa su estado (S, el, operar, avisar, irA...).
   ============================================================ */
'use strict';

const lt = {
  desp:      $('lt-desplazador'),
  barra:     $('lt-barra'),
  iman:      $('lt-iman'),
  menos:     $('lt-menos'),
  mas:       $('lt-mas'),
  ajustar:   $('lt-ajustar'),
  zoomTxt:   $('lt-zoom'),
  regla:     $('regla'),
  guia:      $('lt-guia'),
  fantasma:  $('lt-fantasma'),
  zoom:      1,               // 1 = todo el proyecto a lo ancho
  imanOn:    true,
  drag:      null,            // el arrastre en curso
  pendiente: null,            // un clic sobre un clip que todavia puede ser un arrastre
  rutaVista: null
};

const ANCHO_MAX_PX = 14000;       // ancho maximo del lienzo (los canvas del espectro tienen limite)
const PX_POR_SEG_MAX = 600;       // mas que esto ya no sirve para nada
const TACTIL = !!(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);        // con el dedo, los bordes y el umbral son mas grandes
const UMBRAL_IMAN_PX = TACTIL ? 14 : 8;
const UMBRAL_ARRASTRE_PX = TACTIL ? 9 : 5;
const BORDE_PX = TACTIL ? 18 : 8;
const LARGO_MIN = 0.1;

try { lt.imanOn = localStorage.getItem('moviola.iman') !== '0'; } catch (e) { /* sin almacenamiento: queda prendido */ }

function comaLt(n, dec) { return Number(n).toFixed(dec).replace('.', ','); }
function anchoLienzo() { return Math.max(1, el.carriles.clientWidth); }
function pxDe(t) { return t / Math.max(S.duracion, 1e-6) * anchoLienzo(); }
function tDeX(clientX) {
  const r = el.carriles.getBoundingClientRect();
  return Math.min(Math.max((clientX - r.left) / Math.max(r.width, 1), 0), 1) * S.duracion;
}
function pxPorSeg() { return anchoLienzo() / Math.max(S.duracion, 1e-6); }

/* ============================================================
   zoom y desplazamiento
   ============================================================ */
function zoomMaximo() {
  const w = Math.max(lt.desp.clientWidth, 1);
  return Math.max(1, Math.min(ANCHO_MAX_PX / w, Math.max(2, PX_POR_SEG_MAX * Math.max(S.duracion, 0.1) / w)));
}

function pintarZoom() {
  lt.zoomTxt.textContent = lt.zoom <= 1.001 ? 'Ajustado' : (lt.zoom < 10 ? comaLt(lt.zoom, 1) : String(Math.round(lt.zoom))) + '×';
  lt.menos.disabled = lt.zoom <= 1.001;
  lt.mas.disabled = lt.zoom >= zoomMaximo() - 0.001;
}

/** Cambia el zoom dejando quieto el instante `t` en la posicion `x` (pixeles desde el borde izquierdo del contenedor). */
function aplicarZoom(nuevo, t, x) {
  if (!S.info) return;
  nuevo = Math.min(Math.max(nuevo, 1), zoomMaximo());
  if (t === undefined) { t = tiempoDe(S.cuadro); x = lt.desp.clientWidth / 2; }
  lt.zoom = nuevo;
  el.carriles.style.width = nuevo <= 1.001 ? '' : (nuevo * 100) + '%';
  const w = el.carriles.clientWidth;           // fuerza el calculo con el ancho nuevo
  lt.desp.scrollLeft = Math.max(0, t / Math.max(S.duracion, 1e-6) * w - x);
  pintarZoom();
  dibujarRegla();
}

function zoomPasos(factor) { aplicarZoom(lt.zoom * factor); }

lt.menos.addEventListener('click', () => { zoomPasos(1 / 1.5); lt.menos.blur(); });
lt.mas.addEventListener('click', () => { zoomPasos(1.5); lt.mas.blur(); });
lt.ajustar.addEventListener('click', () => { aplicarZoom(1); lt.ajustar.blur(); });
lt.iman.addEventListener('click', () => {
  lt.imanOn = !lt.imanOn;
  pintarIman();
  try { localStorage.setItem('moviola.iman', lt.imanOn ? '1' : '0'); } catch (e) { /* no pasa nada */ }
  lt.iman.blur();
});
function pintarIman() { lt.iman.setAttribute('aria-pressed', lt.imanOn ? 'true' : 'false'); lt.iman.classList.toggle('lt__iman--on', lt.imanOn); }

lt.desp.addEventListener('wheel', (e) => {
  if (!S.info || !S.proy) return;
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    const r = lt.desp.getBoundingClientRect();
    const x = e.clientX - r.left;
    const t = tDeX(e.clientX);
    aplicarZoom(lt.zoom * (e.deltaY < 0 ? 1.25 : 0.8), t, x);
  } else if (lt.zoom > 1.001) {
    e.preventDefault();
    lt.desp.scrollLeft += (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY);
  }
}, { passive: false });

window.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.altKey || e.metaKey || !S.info || !S.proy) return;
  const foco = e.target;
  if (foco && /^(INPUT|TEXTAREA|SELECT)$/.test(foco.tagName || '')) return;
  if (foco && foco.isContentEditable) return;
  if (lt.drag && e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); cancelarArrastre(); return; }
  if (e.key === '+' || e.key === '=' || e.code === 'NumpadAdd') { zoomPasos(1.5); e.preventDefault(); }
  else if (e.key === '-' || e.code === 'NumpadSubtract') { zoomPasos(1 / 1.5); e.preventDefault(); }
  else if (e.key === '0' || e.code === 'Numpad0') { aplicarZoom(1); e.preventDefault(); }
}, true);

/** Con zoom, el cursor no se puede perder de vista: al reproducir se pasa de «pagina»; al moverlo con el teclado, se lo trae. */
function seguirCursor() {
  if (lt.zoom <= 1.001 || !S.info || S.arrastrando || lt.drag) return;
  const x = pxDe(tiempoDe(S.cuadro));
  const a = lt.desp.scrollLeft, w = lt.desp.clientWidth;
  if (S.reproduciendo) {
    if (x > a + w - 24 || x < a) lt.desp.scrollLeft = Math.max(0, x - w * 0.12);
  } else if (x < a + 8 || x > a + w - 8) {
    lt.desp.scrollLeft = Math.max(0, x - w / 2);
  }
}
const _pintarPosicionLt = pintarPosicion;
pintarPosicion = function () {
  _pintarPosicionLt();
  seguirCursor();
};

/* ============================================================
   regla de tiempo
   ============================================================ */
const PASOS_REGLA = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];

function etiquetaRegla(t, paso) {
  const total = Math.round(t * 100) / 100;
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  if (paso < 1) return m + ':' + comaLt(s, 1).padStart(4, '0');
  return m + ':' + String(Math.round(s)).padStart(2, '0');
}

function dibujarRegla() {
  const c = lt.regla;
  if (!c || !S.info) return;
  const w = Math.max(1, c.clientWidth), h = 18;
  const dpr = window.devicePixelRatio || 1;
  c.width = Math.round(w * dpr);
  c.height = Math.round(h * dpr);
  const ctx = c.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const dur = Math.max(S.duracion, 1e-6);
  const px = w / dur;
  const paso = PASOS_REGLA.find((p) => p * px >= 70) || PASOS_REGLA[PASOS_REGLA.length - 1];
  const sub = paso >= 5 ? 5 : (paso >= 1 ? 4 : 5);
  ctx.fillStyle = colorCss('--texto-3', '#7A7599');
  ctx.strokeStyle = colorCss('--borde-fuerte', '#4A4470');
  ctx.font = '10px "Cascadia Mono", "Consolas", monospace';
  ctx.textBaseline = 'top';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let t = 0; t <= dur + 1e-6; t += paso / sub) {
    const x = Math.round(t * px) + 0.5;
    const mayor = Math.abs(t / paso - Math.round(t / paso)) < 1e-6;
    ctx.moveTo(x, h);
    ctx.lineTo(x, mayor ? h - 9 : h - 4);
  }
  ctx.stroke();
  for (let t = 0; t <= dur + 1e-6; t += paso) {
    const x = Math.round(t * px);
    ctx.fillText(etiquetaRegla(t, paso), Math.min(x + 3, w - 40), 0);
  }
}

if (typeof ResizeObserver === 'function') new ResizeObserver(() => { dibujarRegla(); pintarZoom(); }).observe(lt.desp);

/* ============================================================
   iman
   ============================================================ */
/** Los instantes a los que se pegan los bordes: el cursor, las marcas, el principio y el final, y los bordes de los clips que no son del grupo dado. */
function puntosIman(grupo) {
  const out = [0, S.duracion, tiempoDe(S.cuadro)];
  if (S.marcaIn != null) out.push(S.marcaIn);
  if (S.marcaOut != null) out.push(S.marcaOut);
  if (S.proy) S.proy.pistas.forEach((p) => p.clips.forEach((c) => { if (c.grupo !== grupo) { out.push(c.inicio); out.push(finClip(c)); } }));
  return out;
}

/** El instante `t` pegado al punto mas cercano si esta a menos de UMBRAL_IMAN_PX. Devuelve {t, pegado}. */
function pegar(t, puntos, alt) {
  if (!lt.imanOn || alt) return { t, pegado: null };
  const umbral = UMBRAL_IMAN_PX / Math.max(pxPorSeg(), 1e-6);
  let mejor = null;
  puntos.forEach((p) => { const d = Math.abs(p - t); if (d <= umbral && (mejor === null || d < Math.abs(mejor - t))) mejor = p; });
  return mejor === null ? { t, pegado: null } : { t: mejor, pegado: mejor };
}

function mostrarGuia(t) {
  if (t == null) { lt.guia.hidden = true; return; }
  lt.guia.hidden = false;
  lt.guia.style.left = Math.round(pxDe(t)) + 'px';
}

/* ============================================================
   a quien se le pega
   ============================================================ */
function filaDe(pistaId) {
  const nodo = pistaId === 'V1' ? el.tira.closest('.pelicula') : (el.carriles.querySelector('[data-carril="' + pistaId + '"]'));
  if (!nodo) return null;
  const r = nodo.getBoundingClientRect(), rc = el.carriles.getBoundingClientRect();
  return { top: r.top - rc.top, alto: r.height };
}

/** Que hay bajo el puntero: {pista, clip, lado} donde lado es 'inicio' / 'fin' si esta sobre un borde, o null si esta sobre el cuerpo del clip. */
function golpe(e) {
  if (!S.proy || !e.target || !e.target.closest) return null;
  const carril = e.target.closest('[data-carril]');
  if (!carril) return null;
  const pista = pistaDe(carril.dataset.carril);
  if (!pista) return null;
  const rc = el.carriles.getBoundingClientRect();
  const x = e.clientX - rc.left;
  const c = clipEn(pista, tDeX(e.clientX));
  if (!c) return null;
  const x0 = pxDe(c.inicio), x1 = pxDe(finClip(c));
  const tol = Math.max(3, Math.min(BORDE_PX, (x1 - x0) / 3));
  let lado = null;
  if (x - x0 <= tol) lado = 'inicio';
  else if (x1 - x <= tol) lado = 'fin';
  return { pista, clip: c, lado };
}

function esBloquePrincipal(grupo) {
  const g = clipsDelGrupo(grupo);
  return g.length > 1 || g.some((x) => x.pista.id === 'V1');
}

/** Hasta donde se puede tirar de un borde: [minimo, maximo] en segundos de la linea de tiempo. */
function limitesBorde(c, lado) {
  const g = clipsDelGrupo(c.grupo);
  const base = (g.find((x) => x.pista.tipo === 'video') || g[0]).clip;
  const f = S.proy.fuentes[base.fuente];
  const v = base.velocidad || 1;
  const a = base.inicio, b = finClip(base);
  const rev = !!base.reversa;
  const principal = esBloquePrincipal(c.grupo);
  // cuanto material sobra de cada lado de lo que se usa
  const sobraAntes = base.desde / v, sobraDespues = (f.duracion - base.hasta) / v;
  if (lado === 'fin') {
    const mas = rev ? sobraAntes : sobraDespues;
    return [a + LARGO_MIN, b + mas];
  }
  const mas = rev ? sobraDespues : sobraAntes;
  if (principal) return [a - mas, b - LARGO_MIN];
  return [Math.max(0, a - mas), b - LARGO_MIN];
}

/* ============================================================
   arrastrar: empezar
   ============================================================ */
function limpiarFantasma() { lt.fantasma.textContent = ''; mostrarGuia(null); }

function crearCaja(clase, left, top, ancho, alto, texto) {
  const d = document.createElement('div');
  d.className = clase;
  d.style.left = Math.round(left) + 'px';
  d.style.top = Math.round(top) + 'px';
  d.style.width = Math.max(2, Math.round(ancho)) + 'px';
  d.style.height = Math.round(alto) + 'px';
  if (texto) d.textContent = texto;
  lt.fantasma.appendChild(d);
  return d;
}

function filasDelGrupo(grupo) {
  const filas = clipsDelGrupo(grupo).map((x) => filaDe(x.pista.id)).filter(Boolean);
  const top = Math.min(...filas.map((f) => f.top));
  const bajo = Math.max(...filas.map((f) => f.top + f.alto));
  return { top, alto: bajo - top };
}

lt.desp.addEventListener('pointerdown', (e) => {
  if (e.button !== 0 || !S.proy || !S.info || lt.drag) return;
  if (e.target.closest && e.target.closest('#regla')) return;                    // la regla mueve el cursor, como siempre
  const g = golpe(e);
  if (!g) return;
  const c = g.clip;
  const bloque = esBloquePrincipal(c.grupo);
  if (g.lado) {
    e.stopPropagation();
    e.preventDefault();
    S.sel = { grupo: c.grupo, clip: c.id };
    actualizarSeleccion();
    lt.drag = { tipo: 'borde', grupo: c.grupo, lado: g.lado, bloque, clip: c, id: e.pointerId, x0: e.clientX, nuevo: null, pegado: null };
    try { lt.desp.setPointerCapture(e.pointerId); } catch (err) { /* sigue sin captura */ }
    document.body.classList.add('lt-arrastrando');
    lt.drag.limites = limitesBorde(c, g.lado);
    return;
  }
  // el cuerpo de un clip: es un clic (elegir y llevar el cursor, lo hace app.js) hasta que se mueve unos pixeles
  lt.pendiente = { grupo: c.grupo, clip: c, bloque, pista: g.pista, x0: e.clientX, y0: e.clientY, id: e.pointerId };
}, true);

lt.desp.addEventListener('pointermove', (e) => {
  if (lt.pendiente && !lt.drag && (e.buttons & 1)) {
    if (Math.abs(e.clientX - lt.pendiente.x0) >= UMBRAL_ARRASTRE_PX) {
      const p = lt.pendiente;
      lt.pendiente = null;
      S.arrastrando = false;                                    // ya no es arrastrar el cursor
      el.carriles.classList.remove('arrastrando');
      lt.drag = { tipo: p.bloque ? 'mover-bloque' : 'mover-audio', grupo: p.grupo, clip: p.clip, id: e.pointerId, x0: p.x0, nuevo: null, pegado: null };
      document.body.classList.add('lt-arrastrando');
    }
  }
  if (lt.drag) {
    e.stopPropagation();
    e.preventDefault();
    moverArrastre(e);
    return;
  }
  // sin arrastrar: el puntero cambia segun lo que hay debajo
  if (!(e.buttons & 1) && S.proy && S.info) {
    const g = golpe(e);
    lt.desp.dataset.lt = g ? (g.lado ? 'borde' : 'cuerpo') : '';
  }
}, true);

function terminarPuntero(e, cancelado) {
  if (lt.pendiente) lt.pendiente = null;
  if (!lt.drag) return;
  e.stopPropagation();
  const d = lt.drag;
  lt.drag = null;
  document.body.classList.remove('lt-arrastrando');
  try { lt.desp.releasePointerCapture(d.id); } catch (err) { /* ya estaba suelto */ }
  S.arrastrando = false;
  el.carriles.classList.remove('arrastrando');
  const hecho = !cancelado && d.nuevo != null;
  limpiarFantasma();
  if (hecho) confirmarArrastre(d);
}
lt.desp.addEventListener('pointerup', (e) => terminarPuntero(e, false), true);
lt.desp.addEventListener('pointercancel', (e) => terminarPuntero(e, true), true);

function cancelarArrastre() {
  const d = lt.drag;
  lt.drag = null;
  lt.pendiente = null;
  document.body.classList.remove('lt-arrastrando');
  if (d) { try { lt.desp.releasePointerCapture(d.id); } catch (err) { /* nada */ } }
  limpiarFantasma();
}

/* ============================================================
   arrastrar: mover
   ============================================================ */
function desplazarBordes(e) {
  const r = lt.desp.getBoundingClientRect();
  if (e.clientX < r.left + 28) lt.desp.scrollLeft -= 18;
  else if (e.clientX > r.right - 28) lt.desp.scrollLeft += 18;
}

function moverArrastre(e) {
  desplazarBordes(e);
  const d = lt.drag;
  limpiarFantasma();
  if (d.tipo === 'borde') return moverBorde(e, d);
  if (d.tipo === 'mover-bloque') return moverBloque(e, d);
  return moverAudio(e, d);
}

function moverBorde(e, d) {
  const c = buscarClip(d.clip.id);
  if (!c) { cancelarArrastre(); return; }
  const clip = c.clip;
  const [lo, hi] = d.limites;
  const actual = d.lado === 'fin' ? finClip(clip) : clip.inicio;
  const p = pegar(tDeX(e.clientX), puntosIman(d.grupo), e.altKey);
  let t = Math.min(Math.max(p.t, lo), hi);
  const filas = filasDelGrupo(d.grupo);
  const xa = pxDe(actual), xn = pxDe(t);
  const cambio = t - actual;
  d.nuevo = Math.abs(cambio) < 1e-4 ? null : t;
  const caja = crearCaja('lt__recorte ' + (cambio < 0 ? 'lt__recorte--saca' : 'lt__recorte--suma'), Math.min(xa, xn), filas.top, Math.abs(xn - xa), filas.alto, '');
  caja.setAttribute('data-texto', (cambio >= 0 ? '+' : '−') + comaLt(Math.abs(cambio), 2) + ' s');
  crearCaja('lt__borde-nuevo', xn - 1, filas.top - 2, 2, filas.alto + 4, '');
  mostrarGuia(p.pegado != null && Math.abs(p.pegado - t) < 1e-6 ? t : null);
  const estiraTope = (t <= lo + 1e-6 && cambio < 0) || (t >= hi - 1e-6 && cambio > 0);
  caja.setAttribute('data-tope', estiraTope ? 'sí' : 'no');
}

/** Los bordes entre clips de V1 a los que puede ir un clip: el principio, el final y el inicio de cada clip. Devuelve {todos, propios}: `propios`
 *  son los dos bordes del clip que se arrastra (soltarlo ahi es dejarlo donde esta). */
function bordesDestino(grupo) {
  const v1 = pistaDe('V1');
  const mio = v1.clips.find((x) => x.grupo === grupo);
  const out = new Set([0, v1.clips.length ? Math.max(...v1.clips.map(finClip)) : 0]);
  v1.clips.forEach((x) => out.add(x.inicio));
  return { todos: [...out].sort((a, b) => a - b), propios: [mio.inicio, finClip(mio)] };
}

function moverBloque(e, d) {
  const c = buscarClip(d.clip.id);
  if (!c) { cancelarArrastre(); return; }
  const clip = c.clip;
  const filas = filasDelGrupo(d.grupo);
  const dx = e.clientX - d.x0;
  const x0 = pxDe(clip.inicio) + dx, ancho = pxDe(finClip(clip)) - pxDe(clip.inicio);
  crearCaja('lt__fantasma', x0, filas.top, ancho, filas.alto, '');
  const { todos, propios } = bordesDestino(d.grupo);
  const tm = tDeX(e.clientX);
  const b = todos.reduce((m, x) => (Math.abs(x - tm) < Math.abs(m - tm) ? x : m), todos[0]);
  if (propios.some((x) => Math.abs(x - b) < 1e-4)) { d.nuevo = null; return; }        // lo mas cerca esta donde ya esta: no se mueve
  d.nuevo = b;
  const xb = pxDe(b);
  crearCaja('lt__destino', xb - 1.5, filas.top - 6, 3, filas.alto + 12, '');
}

function moverAudio(e, d) {
  const c = buscarClip(d.clip.id);
  if (!c) { cancelarArrastre(); return; }
  const clip = c.clip;
  const largo = largoClip(clip);
  const bruto = Math.max(0, clip.inicio + (e.clientX - d.x0) / Math.max(pxPorSeg(), 1e-6));
  const puntos = puntosIman(d.grupo);
  const pa = pegar(bruto, puntos, e.altKey), pb = pegar(bruto + largo, puntos, e.altKey);
  let t = bruto, guia = null;
  if (pa.pegado != null && (pb.pegado == null || Math.abs(pa.t - bruto) <= Math.abs(pb.t - (bruto + largo)))) { t = pa.t; guia = pa.pegado; }
  else if (pb.pegado != null) { t = pb.t - largo; guia = pb.pegado; }
  t = Math.max(0, t);
  d.nuevo = Math.abs(t - clip.inicio) < 1e-4 ? null : t;
  const fila = filaDe(c.pista.id);
  if (fila) crearCaja('lt__fantasma', pxDe(t), fila.top, pxDe(t + largo) - pxDe(t), fila.alto, '');
  mostrarGuia(guia);
}

/* ============================================================
   arrastrar: soltar
   ============================================================ */
async function confirmarArrastre(d) {
  let r = null;
  if (d.tipo === 'borde') r = await operar('recortar_borde', [d.grupo, d.lado, Math.round(d.nuevo * 1000) / 1000]);
  else if (d.tipo === 'mover-bloque') r = await operar('mover_grupo', [d.grupo, Math.round(d.nuevo * 1000) / 1000]);
  else r = await operar('mover_clip', [d.clip.id, Math.round(d.nuevo * 1000) / 1000]);
  if (r && d.tipo === 'borde') {
    const res = r.resultado || {};
    if (res.cambio) avisar((res.cambio < 0 ? 'Se sacaron ' : 'Se agregaron ') + comaLt(Math.abs(res.cambio), 2) + ' s. «Deshacer» (Ctrl+Z) lo devuelve.', 'info');
  }
}

/* ============================================================
   enganches con el resto de la interfaz
   ============================================================ */
// el cursor del puntero cuando el mouse esta sobre un borde o un clip
lt.desp.addEventListener('pointerleave', () => { lt.desp.dataset.lt = ''; });

// un archivo nuevo: el zoom vuelve a «todo»; al cambiar el proyecto se redibuja la regla
const _alActualizarProyectoLt = typeof window.alActualizarProyecto === 'function' ? window.alActualizarProyecto : null;
window.alActualizarProyecto = function () {
  if (_alActualizarProyectoLt) _alActualizarProyectoLt();
  if (S.ruta !== lt.rutaVista) { lt.rutaVista = S.ruta; if (lt.zoom !== 1) aplicarZoom(1); }
  else if (lt.zoom > zoomMaximo()) aplicarZoom(zoomMaximo());
  dibujarRegla();
  pintarZoom();
};
pintarIman();
pintarZoom();
