// Interfaz del sistema experto DJ. Todo el estado vive en el servidor (SQLite):
// aquí solo se recuerda quién es el DJ y qué evento está abierto.
const CLAVE = 'dj-sesion-v2';
const state = { opciones: null, dj: null, eventos: [], evento: null, catalogo: [], actual: null, historial: [] };
const $ = s => document.querySelector(s);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const etiqueta = (variable, valor) => (state.opciones.variables.find(v => v.id === variable)?.valores.find(x => x.codigo === valor)?.etiqueta) || valor;
const marcas = c => (c.conocida ? ' · conocida' : '') + (c.comercial ? ' · comercial' : '');
const cancion = id => state.catalogo.find(c => String(c.id) === String(id));

async function api(ruta, metodo = 'GET', cuerpo) {
  const r = await fetch(ruta, { method: metodo, headers: cuerpo ? { 'Content-Type': 'application/json' } : {}, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(d.error || 'Error del servidor');
  return d;
}
function avisar(mensaje) { const e = $('#error'); e.textContent = mensaje || ''; e.hidden = !mensaje; if (mensaje) e.scrollIntoView({ block: 'nearest' }); }
async function intentar(fn) { try { avisar(''); await fn(); } catch (err) { avisar(err.message); } }

async function init() {
  try {
    state.opciones = await api('/api/opciones');
    pintarContexto(); llenarSelects();
    const guardado = JSON.parse(localStorage.getItem(CLAVE) || 'null');
    if (guardado?.correo) { $('#djNombre').value = guardado.nombre; $('#djCorreo').value = guardado.correo; await entrar(guardado.nombre, guardado.correo, guardado.evento); }
  } catch (e) { $('#fields').textContent = 'No fue posible cargar el conocimiento: ' + e.message; }
}

function pintarContexto() {
  const fields = $('#fields'); fields.replaceChildren();
  for (const v of state.opciones.variables.filter(v => v.id !== 'tipo_evento')) {
    const holder = el('div', 'field'); const label = el('label', null, v.nombre); label.htmlFor = v.id;
    const select = el('select'); select.name = v.id; select.id = v.id;
    select.append(new Option('Sin responder', ''));
    for (const o of v.valores) select.append(new Option(o.etiqueta, o.codigo));
    holder.append(label, select); fields.append(holder);
  }
}

function llenarSelects() {
  const g = $('#genero'); g.replaceChildren(new Option('Selecciona…', ''));
  for (const n of state.opciones.generos) g.append(new Option(n, n));
  const f = $('#formato'); f.replaceChildren();
  for (const x of state.opciones.formatos) f.append(new Option(x, x));
  const t = $('#evTipo'); t.replaceChildren(new Option('Selecciona…', ''));
  for (const o of state.opciones.variables.find(v => v.id === 'tipo_evento').valores) t.append(new Option(o.etiqueta, o.codigo));
}

// ---------------------------------------------------------------- DJ y evento
async function entrar(nombre, correo, eventoPrevio) {
  state.dj = await api('/api/usuarios', 'POST', { nombre, correo });
  $('#zonaEvento').hidden = false; $('#agregar').disabled = false;
  $('#djActual').textContent = `Sesión de ${state.dj.nombre} · ${state.dj.correo}`;
  [state.catalogo, state.eventos] = await Promise.all([api(`/api/usuarios/${state.dj.id}/canciones`), api(`/api/usuarios/${state.dj.id}/eventos`)]);
  pintarCatalogo(); pintarEventos();
  await abrirEvento(state.eventos.some(e => e.id === eventoPrevio) ? eventoPrevio : null);
}

function recordar() { localStorage.setItem(CLAVE, JSON.stringify({ nombre: state.dj.nombre, correo: state.dj.correo, evento: state.evento?.id || null })); }

function pintarEventos() {
  const sel = $('#evento'); sel.replaceChildren(new Option('Selecciona o crea un evento…', ''));
  for (const e of state.eventos) sel.append(new Option(`${e.nombre} · ${etiqueta('tipo_evento', e.tipo_evento)} · ${e.estado.replace('_', ' ').toLowerCase()}`, e.id));
  sel.value = state.evento?.id || '';
}

async function abrirEvento(id) {
  state.evento = state.eventos.find(e => e.id === Number(id)) || null;
  $('#evento').value = state.evento?.id || '';
  const abierto = state.evento && state.evento.estado !== 'FINALIZADO';
  $('#run').disabled = !abierto; $('#finalizar').disabled = !abierto;
  $('#tipoEvento').textContent = state.evento
    ? `Evento: ${state.evento.nombre} · tipo ${etiqueta('tipo_evento', state.evento.tipo_evento)} · ${state.evento.estado.replace('_', ' ').toLowerCase()}`
    : 'El tipo de evento se toma del evento activo.';
  $('#results').hidden = true; $('#empty').hidden = false;
  state.historial = state.evento ? await api(`/api/eventos/${state.evento.id}/historial`) : [];
  pintarHistorial(); recordar();
}

$('#formDJ').addEventListener('submit', e => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.target)); intentar(() => entrar(d.nombre, d.correo)); });
$('#evento').addEventListener('change', e => intentar(() => abrirEvento(e.target.value)));
$('#formEvento').addEventListener('submit', e => {
  e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
  intentar(async () => {
    const nuevo = await api(`/api/usuarios/${state.dj.id}/eventos`, 'POST', { nombre: d.nombre, tipo_evento: d.tipo_evento, duracion_min: Number(d.duracion_min) });
    state.eventos.unshift(nuevo); pintarEventos(); await abrirEvento(nuevo.id); $('#evNombre').value = '';
  });
});
$('#finalizar').addEventListener('click', () => intentar(async () => {
  const cerrado = await api(`/api/eventos/${state.evento.id}/finalizar`, 'POST', {});
  state.eventos = state.eventos.map(e => e.id === cerrado.id ? cerrado : e); pintarEventos(); await abrirEvento(cerrado.id);
}));

// ---------------------------------------------------------------- catálogo
function pintarCatalogo() {
  const box = $('#catalogo'); box.replaceChildren();
  if (!state.catalogo.length) box.append(el('p', 'muted', 'Sin canciones. Agrega tu catálogo para recibir recomendaciones de canciones.'));
  for (const c of state.catalogo) {
    const row = el('div', 'song');
    row.append(el('span', null, `${c.titulo} · ${c.artista}`), el('small', null, `${c.genero} · ${c.bpm} BPM · ${c.tonalidad_camelot} · energía ${c.energia} · ${c.formato}${marcas(c)}`));
    const quitar = el('button', 'mini', '✕ Quitar'); quitar.type = 'button'; quitar.setAttribute('aria-label', `Quitar ${c.titulo}`);
    quitar.addEventListener('click', () => intentar(async () => {
      await api(`/api/usuarios/${state.dj.id}/canciones/${c.id}`, 'DELETE');
      state.catalogo = state.catalogo.filter(x => x.id !== c.id); if (String(state.actual) === String(c.id)) state.actual = null; pintarCatalogo();
    }));
    row.append(quitar); box.append(row);
  }
  const sel = $('#actual'); const previo = state.actual;
  sel.replaceChildren(new Option('Ninguna (sin compatibilidad ni transición)', ''));
  for (const c of state.catalogo) sel.append(new Option(`${c.titulo} · ${c.artista}`, c.id));
  sel.value = cancion(previo) ? previo : ''; state.actual = sel.value || null;
}
$('#actual').addEventListener('change', e => { state.actual = e.target.value || null; });
$('#formCancion').addEventListener('submit', e => {
  e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
  intentar(async () => {
    const nueva = await api(`/api/usuarios/${state.dj.id}/canciones`, 'POST', { titulo: d.titulo, artista: d.artista, genero: d.genero,
      bpm: Number(d.bpm), tonalidad_camelot: d.tonalidad_camelot, energia: Number(d.energia), duracion_seg: Number(d.duracion_seg), formato: d.formato,
      conocida: d.conocida === 'on', comercial: d.comercial === 'on' });
    state.catalogo.push(nueva); pintarCatalogo(); e.target.reset();
  });
});

// ---------------------------------------------------------------- recomendación
$('#form').addEventListener('submit', e => {
  e.preventDefault();
  const contexto = Object.fromEntries([...new FormData(e.target)].filter(([, v]) => v));
  const button = $('#run'); button.disabled = true; button.textContent = 'Analizando…';
  intentar(async () => {
    try {
      const d = await api(`/api/eventos/${state.evento.id}/recomendar`, 'POST', { contexto, cancion_actual_id: state.actual ? Number(state.actual) : null });
      if (state.evento.estado === 'PLANEADO') { state.evento.estado = 'EN_CURSO'; pintarEventos(); }
      mostrar(d);
    } finally { button.disabled = false; button.textContent = '✦   Recomendar'; }
  });
});

function mostrar(d) {
  $('#empty').hidden = true; $('#results').hidden = false;
  const reglas = $('#reglas'); reglas.replaceChildren();
  if (d.sin_reglas) reglas.append(el('p', 'muted', d.aviso));
  for (const r of d.reglas_disparadas) {
    const item = el('div', 'rule'); item.append(el('b', null, `${r.codigo} · ${r.nombre}`), el('span', null, r.conclusion), el('small', 'muted', r.descripcion));
    reglas.append(item);
  }
  const conf = $('#conflictos'); conf.replaceChildren();
  for (const c of d.conflictos) conf.append(el('div', 'conflict', 'Conflicto: ' + c.descripcion));
  const recs = $('#recs'); recs.replaceChildren();
  for (const rec of d.recomendaciones) recs.append(bloque(rec));
  $('#aviso').textContent = `${d.aviso} · Contexto n.º ${d.contexto_id} guardado · respuesta en ${d.tiempo_respuesta_ms} ms`;
}

function bloque(rec) {
  const block = el('div', 'rec');
  block.append(el('span', 'eyebrow', `${rec.accion.replaceAll('_', ' ')} · ${rec.reglas.join(', ')} · recomendación n.º ${rec.id}`), el('p', null, rec.mensaje));
  for (const n of rec.notas) block.append(el('p', 'muted', '• ' + n));
  const [sugerida, ...otras] = rec.canciones;
  if (sugerida) block.append(tarjeta(sugerida, 'Canción sugerida'));
  const porque = el('details', 'why'); porque.append(el('summary', null, '¿Por qué? (RF04)'), el('p', null, rec.explicacion)); block.append(porque);
  const pie = el('div', 'decide');
  const motivo = el('input'); motivo.placeholder = 'Motivo (opcional)'; motivo.maxLength = 1000; motivo.setAttribute('aria-label', 'Motivo de la decisión');
  const decidir = (accion, finalId) => intentar(async () => {
    await api(`/api/recomendaciones/${rec.id}/decision`, 'POST', { accion, cancion_final_id: finalId || null, motivo: motivo.value });
    if (accion === 'ACEPTADA' && sugerida) state.actual = sugerida.id;
    if (accion === 'MODIFICADA') state.actual = finalId;
    $('#actual').value = state.actual || '';
    block.classList.add('decided'); block.querySelectorAll('button, input').forEach(b => { b.disabled = true; });
    block.append(el('p', 'done', `Decisión registrada: ${accion}`));
    state.historial = await api(`/api/eventos/${state.evento.id}/historial`); pintarHistorial();
  });
  pie.append(motivo, boton('Aceptar', () => decidir('ACEPTADA')), boton('Rechazar', () => decidir('RECHAZADA')));
  block.append(pie);
  if (otras.length) {
    const mas = el('details', 'why'); mas.append(el('summary', null, `Otras ${otras.length} candidatas (elegir una registra la decisión como MODIFICADA)`));
    for (const c of otras) { const t = tarjeta(c); t.append(boton('Usar esta', () => decidir('MODIFICADA', Number(c.id)))); mas.append(t); }
    block.append(mas);
  }
  return block;
}

function tarjeta(c, titulo) {
  const card = el('div', 'song');
  if (titulo) card.append(el('small', 'eyebrow', titulo.toUpperCase()));
  const delta = c.delta_energia == null ? '' : ` (${c.delta_energia > 0 ? '+' : ''}${c.delta_energia})`;
  const bpm = c.diferencia_bpm == null ? '' : ` (diferencia ${c.diferencia_bpm})`;
  card.append(el('span', null, `${c.titulo} · ${c.artista}`), el('small', null, `${c.genero} · ${c.bpm} BPM${bpm} · ${c.tonalidad_camelot} · energía ${c.energia}${delta}${marcas(c)}`));
  const transiciones = c.transiciones.map(t => `${t.nombre} (${t.caso.replaceAll('_', ' ').toLowerCase()})`).join(' · ');
  card.append(el('small', null, 'Transición: ' + (transiciones || 'sin técnica definida')));
  for (const n of c.notas) card.append(el('small', 'muted', '• ' + n));
  return card;
}
const boton = (texto, fn) => { const b = el('button', 'mini', texto); b.type = 'button'; b.addEventListener('click', fn); return b; };

// ---------------------------------------------------------------- historial
function pintarHistorial() {
  const box = $('#historial'); box.replaceChildren();
  if (!state.historial.length) { box.textContent = 'Aún no hay decisiones en este evento.'; return; }
  for (const h of state.historial) {
    const fila = el('div', 'decision');
    const final = h.cancion_final ? ` → ${h.cancion_final}` : '';
    fila.append(el('span', null, `${new Date(h.decidida_en).toLocaleTimeString()} · ${h.accion} · ${h.reglas || ''} · ${h.cancion_sugerida || 'recomendación general'}${final}${h.motivo ? ' · ' + h.motivo : ''}`));
    const detalle = el('p', 'muted'); detalle.hidden = true;
    fila.append(boton('Explicación', () => intentar(async () => {
      if (!detalle.textContent) { const x = await api(`/api/recomendaciones/${h.recomendacion_id}`); detalle.textContent = `Hechos: ${Object.entries(x.hechos).map(([k, v]) => `${k} = ${v}`).join(', ')}. ${x.explicacion}`; }
      detalle.hidden = !detalle.hidden;
    })), detalle);
    box.append(fila);
  }
}
$('#download').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify({ evento: state.evento, historial: state.historial }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob); const a = el('a'); a.href = url; a.download = 'historial_decisiones.json'; a.click(); URL.revokeObjectURL(url);
});
$('#resetCtx').addEventListener('click', () => setTimeout(() => { $('#results').hidden = true; $('#empty').hidden = false; }, 0));
init();
