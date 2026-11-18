// Interfaz del sistema experto DJ. Todo el estado se guarda en el servidor (PostgreSQL);
// aquí solo se dibujan las vistas: acceso, historial, asistente por preguntas, resultado y catálogo.
const S = { op: null, usuario: null, catalogo: [], eventos: [], w: null, evento: null };
const $ = s => document.querySelector(s);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
const VISTAS = ['Acceso', 'Inicio', 'Asistente', 'Resultado', 'Catalogo'];
const ICONOS = {
  cumpleanos: '🎂', boda: '💍', empresarial: '🏢', tematica: '🎭', discoteca: '🪩', reunion_familiar: '🏡',
  llegada: '🚪', inicio: '▶️', desarrollo: '🎶', momento_principal: '⭐', cierre: '🌙',
  ninos: '🧒', adolescentes: '🎧', jovenes: '🕺', adultos: '🧑', adultos_mayores: '👵', variadas: '👥',
  infantil: '🎈', pop: '🎤', urbano: '🔥', salsa: '💃', merengue: '🥁', electronica: '🎛️', rock: '🎸', popular: '🪕', vallenato: '🪗',
  positiva: '👍', negativa: '👎', baila_y_canta: '🙌', baila_poco: '🚶', sentado: '🪑', rie_y_canta: '😄',
  solicita_otro_genero: '🔁', sin_reaccion: '😐', se_retira: '👋' };
const PREGUNTAS = {
  evento: ['¿Para qué evento es la consulta?', 'Elige un evento abierto o crea uno nuevo.'],
  tipo: ['¿Qué tipo de evento es?', 'El tipo de evento activa las reglas R01 a R06.'],
  nombre: ['¿Cómo se llama el evento?', 'Sirve para encontrarlo después en el historial.'],
  momento: ['¿En qué momento está la fiesta?', 'El momento activa las reglas R07 a R11.'],
  grupo_edad: ['¿Qué edad predomina en el público?', 'La edad activa las reglas R12 a R17.'],
  cancion: ['¿Qué canción suena ahora?', 'Con ella se comprueba la compatibilidad de tonalidad, el BPM y la energía. El género se toma de la canción.'],
  genero_actual: ['¿Qué género suena o se solicita?', 'Sin canción elegida, indica el género para evaluar la reacción del público.'],
  reaccion_publico: ['¿Cómo reacciona el público?', 'Primero aparecen las reacciones que tienen regla para el género que suena.'],
  actividad_principal: ['¿La actividad principal requiere música más animada?', 'R10: solo se aumenta la energía si corresponde a la actividad prevista.'],
  actividad_baile: ['¿La actividad está orientada al baile y el público desea participar?', 'R20: no se debe subir la energía sin comprobar estas condiciones.'],
  publico_desea_bailar: ['¿El público sentado desea bailar?', 'R21: puede estar conversando, comiendo o descansando.'],
  causa_sin_reaccion: ['¿Qué ocurre con el público?', 'R25: primero se consulta la causa y después se decide si cambiar o bajar la energía.'],
  resumen: ['Revisa antes de consultar', 'Si algo no está bien, vuelve atrás y corrígelo.'] };
const NOMBRE_PASO = { evento: 'Evento', tipo: 'Evento', nombre: 'Evento', momento: 'Momento', grupo_edad: 'Público', cancion: 'Canción',
  genero_actual: 'Género', reaccion_publico: 'Reacción', actividad_principal: 'Actividad', actividad_baile: 'Actividad', publico_desea_bailar: 'Actividad', causa_sin_reaccion: 'Actividad', resumen: 'Resumen' };

const variable = id => S.op.variables.find(v => v.id === id);
const etq = (id, codigo) => variable(id)?.valores.find(x => x.codigo === codigo)?.etiqueta || codigo || '—';
const cancion = id => S.catalogo.find(c => String(c.id) === String(id));
const marcas = c => (c.conocida ? ' · conocida' : '') + (c.comercial ? ' · comercial' : '');
const fecha = iso => iso ? new Date(iso).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' }) : '';
const boton = (texto, fn, cls = 'mini') => { const b = el('button', cls, texto); b.type = 'button'; b.addEventListener('click', fn); return b; };

async function api(ruta, metodo = 'GET', cuerpo) {
  const r = await fetch(ruta, { method: metodo, headers: cuerpo ? { 'Content-Type': 'application/json' } : {}, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
  const d = await r.json().catch(() => ({}));
  if (r.status === 401 && S.usuario) { S.usuario = null; mostrarAcceso(); }
  if (!r.ok) throw Error(d.error || 'Error del servidor');
  return d;
}
function avisar(mensaje) { const e = $('#error'); e.textContent = mensaje || ''; e.hidden = !mensaje; if (mensaje) e.scrollIntoView({ block: 'nearest' }); }
async function intentar(fn) { try { avisar(''); await fn(); } catch (err) { avisar(err.message); } }
function ver(vista) { for (const v of VISTAS) $('#v' + v).hidden = v !== vista; window.scrollTo(0, 0); }

// ---------------------------------------------------------------- acceso
function mostrarAcceso() { $('#menu').hidden = true; ver('Acceso'); }
async function entrar(usuario) {
  S.usuario = usuario; $('#menu').hidden = false; $('#quien').textContent = usuario.nombre;
  [S.catalogo, S.eventos] = await Promise.all([api('/api/canciones'), api('/api/eventos')]);
  llenarSelects(); await irInicio();
}
$('#formLogin').addEventListener('submit', e => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
  intentar(async () => { await entrar(await api('/api/login', 'POST', d)); e.target.reset(); }); });
$('#formRegistro').addEventListener('submit', e => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
  intentar(async () => { await entrar(await api('/api/registro', 'POST', { ...d, ejemplos: d.ejemplos === 'on' })); e.target.reset(); }); });
$('#salir').addEventListener('click', () => intentar(async () => { await api('/api/logout', 'POST', {}); S.usuario = null; mostrarAcceso(); }));
document.querySelectorAll('[data-ir]').forEach(b => b.addEventListener('click', () => intentar(() =>
  ({ inicio: irInicio, catalogo: irCatalogo, asistente: () => nuevaConsulta(null) })[b.dataset.ir]())));

// ---------------------------------------------------------------- historial
async function irInicio() {
  const consultas = await api('/api/consultas');
  $('#saludo').textContent = `Hola, ${S.usuario.nombre}`;
  const box = $('#historial'); box.replaceChildren();
  $('#sinHistorial').hidden = consultas.length > 0;
  for (const c of consultas) {
    const t = boton('', () => intentar(() => abrirConsulta(c.id)), 'carta-opcion');
    const pendientes = c.recomendaciones - c.decisiones;
    const estado = !c.recomendaciones ? ['Sin reglas', ''] : pendientes ? [`${pendientes} por decidir`, 'pend'] : ['Decidida', 'ok'];
    t.append(el('span', 'etiqueta ' + estado[1], estado[0]), el('span', 'icono', ICONOS[c.tipo_evento] || '♫'), el('b', null, c.evento),
      el('small', null, `${etq('tipo_evento', c.tipo_evento)} · ${fecha(c.registrado_en)}`),
      el('small', null, ['momento', 'grupo_edad', 'genero_actual', 'reaccion_publico'].filter(v => c[v]).map(v => etq(v, c[v])).join(' · ') || 'Sin contexto'),
      el('small', null, c.cancion_actual ? `Sonaba: ${c.cancion_actual}` : 'Sin canción actual'),
      el('small', null, c.reglas ? `Reglas: ${c.reglas}` : 'Ninguna regla aplicó'));
    t.setAttribute('aria-label', `Abrir consulta de ${c.evento}`);
    box.append(t);
  }
  ver('Inicio');
}
$('#cargarEjemplos').addEventListener('click', () => intentar(async () => {
  await api('/api/ejemplos', 'POST', {});
  [S.catalogo, S.eventos] = await Promise.all([api('/api/canciones'), api('/api/eventos')]); await irInicio();
}));
async function abrirConsulta(id) { const d = await api(`/api/consultas/${id}`); mostrarResultado(d, d.evento, d.registrado_en, true); }

// ---------------------------------------------------------------- asistente por preguntas
function nuevaConsulta(evento, previas) {
  const abierto = evento && evento.estado !== 'FINALIZADO' ? evento : null;
  S.w = { i: 0, evento: abierto, nuevo: false, tipo: null, nombre: '', r: { ...(previas || {}) }, aclaraciones: {}, actual: previas?.actual ?? null };
  delete S.w.r.actual; if (abierto) S.w.i = 1;
  pintarPaso(); ver('Asistente');
}
function pasos() {
  const w = S.w, p = ['evento'];
  if (w.nuevo) p.push('tipo', 'nombre');
  p.push('momento', 'grupo_edad', 'cancion');
  if (!cancion(w.actual)) p.push('genero_actual');
  p.push('reaccion_publico');
  const g = cancion(w.actual) ? S.op.generos[cancion(w.actual).genero] : w.r.genero_actual;
  const reaccion = w.r.reaccion_publico;
  if (w.r.momento === 'momento_principal') p.push('actividad_principal');
  if (['salsa', 'merengue'].includes(g) && reaccion === 'baila_poco' && !['llegada', 'cierre'].includes(w.r.momento)) p.push('actividad_baile');
  if (['electronica', 'rock'].includes(g) && reaccion === 'sentado') p.push('publico_desea_bailar');
  if (['salsa', 'merengue'].includes(g) && reaccion === 'sin_reaccion') p.push('causa_sin_reaccion');
  p.push('resumen');
  return p;
}
const generoActual = () => { const c = cancion(S.w.actual); return c ? S.op.generos[c.genero] : S.w.r.genero_actual || null; };
function avanzar() { S.w.i = Math.min(S.w.i + 1, pasos().length - 1); pintarPaso(); }

function opcion(icono, titulo, detalle, fn, clases = '') {
  const b = boton('', fn, 'carta-opcion ' + clases);
  b.append(el('span', 'icono', icono), el('b', null, titulo)); if (detalle) b.append(el('small', null, detalle));
  return b;
}
function pintarPaso() {
  const w = S.w, lista = pasos(), paso = lista[w.i];
  // barra de progreso: una etiqueta por pregunta, sin repetir las del evento
  const nombres = [...new Set(lista.map(p => NOMBRE_PASO[p]))], actual = NOMBRE_PASO[paso];
  $('#pasos').replaceChildren(...nombres.map((n, k) => { const li = el('li', k < nombres.indexOf(actual) ? 'hecho' : n === actual ? 'actual' : '', `${k + 1}. ${n}`);
    if (n === actual) li.setAttribute('aria-current', 'step'); return li; }));
  $('#numPregunta').textContent = `PREGUNTA ${nombres.indexOf(actual) + 1} DE ${nombres.length}`;
  [$('#textoPregunta').textContent, $('#ayudaPregunta').textContent] = PREGUNTAS[paso];
  const box = $('#opciones'); box.replaceChildren(); box.hidden = false;
  $('#formEvento').hidden = true; $('#resumen').hidden = true;
  $('#atras').disabled = w.i === 0;
  $('#omitir').hidden = !['momento', 'grupo_edad', 'genero_actual', 'reaccion_publico'].includes(paso);

  if (paso === 'evento') {
    for (const e of S.eventos.filter(e => e.estado !== 'FINALIZADO'))
      box.append(opcion(ICONOS[e.tipo_evento] || '♫', e.nombre, `${etq('tipo_evento', e.tipo_evento)} · ${e.estado.replace('_', ' ').toLowerCase()}`,
        () => { w.evento = e; w.nuevo = false; avanzar(); }, w.evento?.id === e.id ? 'elegida' : ''));
    box.append(opcion('＋', 'Nuevo evento', 'Registrar otra fiesta', () => { w.evento = null; w.nuevo = true; avanzar(); }, 'nueva'));
  } else if (paso === 'tipo') {
    for (const o of variable('tipo_evento').valores)
      box.append(opcion(ICONOS[o.codigo] || '♫', o.etiqueta, null, () => { w.tipo = o.codigo; avanzar(); }, w.tipo === o.codigo ? 'elegida' : ''));
  } else if (paso === 'nombre') {
    box.hidden = true; $('#formEvento').hidden = false; $('#evNombre').value = w.nombre; $('#evNombre').focus();
  } else if (paso === 'momento' || paso === 'grupo_edad' || paso === 'genero_actual') {
    for (const o of variable(paso).valores)
      box.append(opcion(ICONOS[o.codigo] || '♫', o.etiqueta, null, () => { w.r[paso] = o.codigo; avanzar(); }, w.r[paso] === o.codigo ? 'elegida' : ''));
  } else if (paso === 'cancion') {
    for (const c of S.catalogo)
      box.append(opcion(ICONOS[S.op.generos[c.genero]] || '♫', c.titulo, `${c.artista} · ${c.genero} · ${c.bpm} BPM · ${c.tonalidad_camelot} · energía ${c.energia}${marcas(c)}`,
        () => { w.actual = c.id; delete w.r.genero_actual; avanzar(); }, String(w.actual) === String(c.id) ? 'elegida' : ''));
    box.append(opcion('∅', S.catalogo.length ? 'Ninguna del catálogo' : 'Tu catálogo está vacío',
      S.catalogo.length ? 'Sin canción no se evalúan compatibilidad ni transición.' : 'Puedes continuar; el sistema mostrará las reglas pero no canciones.',
      () => { w.actual = null; avanzar(); }, 'nueva' + (w.actual == null ? '' : '')));
  } else if (paso === 'reaccion_publico') {
    const g = generoActual(), todas = variable('reaccion_publico').valores;
    const propias = g ? [...(S.op.reacciones_por_genero[g] || []), ...S.op.reacciones_generales] : todas.map(o => o.codigo);
    const dibujar = (o, cls) => box.append(opcion(ICONOS[o.codigo] || '♫', o.etiqueta, null, () => { w.r.reaccion_publico = o.codigo; avanzar(); },
      cls + (w.r.reaccion_publico === o.codigo ? ' elegida' : '')));
    if (g) box.append(el('p', 'subtitulo-rejilla', `Con ${etq('genero_actual', g)} hay regla para:`));
    todas.filter(o => propias.includes(o.codigo)).forEach(o => dibujar(o, 'sugerida'));
    const otras = todas.filter(o => !propias.includes(o.codigo));
    if (otras.length) { box.append(el('p', 'subtitulo-rejilla', 'Otras reacciones (no hay regla para este género; solo aplicarán las reglas generales):')); otras.forEach(o => dibujar(o, '')); }
  } else if (['actividad_principal', 'actividad_baile', 'publico_desea_bailar', 'causa_sin_reaccion'].includes(paso)) {
    const respuestas = paso === 'causa_sin_reaccion'
      ? [['rechaza_cancion', 'Rechaza la canción'], ['menos_intensidad', 'Pide menos intensidad'], ['otra_causa', 'Está descansando o existe otra causa'], ['no_se', 'Todavía no se sabe']]
      : [['si', 'Sí, está confirmado'], ['no', 'No'], ['no_se', 'No se sabe todavía']];
    for (const [valor, titulo] of respuestas) box.append(opcion('◉', titulo, null,
      () => { w.aclaraciones[paso] = valor; avanzar(); }, w.aclaraciones[paso] === valor ? 'elegida' : ''));
  } else if (paso === 'resumen') {
    box.hidden = true; const res = $('#resumen'); res.hidden = false; res.replaceChildren();
    const dl = el('dl'), c = cancion(w.actual), g = generoActual();
    const fila = (k, v) => dl.append(el('dt', null, k), el('dd', null, v));
    fila('Evento', w.evento ? w.evento.nombre : w.nombre);
    fila('Tipo de evento', etq('tipo_evento', w.evento ? w.evento.tipo_evento : w.tipo));
    fila('Momento', w.r.momento ? etq('momento', w.r.momento) : 'Sin responder');
    fila('Público', w.r.grupo_edad ? etq('grupo_edad', w.r.grupo_edad) : 'Sin responder');
    fila('Canción que suena', c ? `${c.titulo} · ${c.artista}` : 'Ninguna');
    fila('Género', g ? etq('genero_actual', g) : 'Sin responder');
    fila('Reacción', w.r.reaccion_publico ? etq('reaccion_publico', w.r.reaccion_publico) : 'Sin responder');
    const respuestas = { si: 'Sí', no: 'No', no_se: 'No se sabe', rechaza_cancion: 'Rechaza la canción', menos_intensidad: 'Pide menos intensidad', otra_causa: 'Otra causa' };
    for (const k of ['actividad_principal', 'actividad_baile', 'publico_desea_bailar', 'causa_sin_reaccion'])
      if (pasos().includes(k)) fila(PREGUNTAS[k][0], respuestas[w.aclaraciones[k]] || 'No se sabe');
    res.append(dl, boton('✦  Recomendar', () => intentar(consultar), 'primario'));
  }
}
$('#atras').addEventListener('click', () => { if (S.w.i > 0) { S.w.i--; pintarPaso(); } });
$('#omitir').addEventListener('click', () => { delete S.w.r[pasos()[S.w.i]]; avanzar(); });
$('#formEvento').addEventListener('submit', e => { e.preventDefault(); S.w.nombre = $('#evNombre').value.trim(); if (S.w.nombre) avanzar(); });

async function consultar() {
  const w = S.w;
  if (!w.evento) {   // el evento nuevo se crea al final, cuando el DJ ya confirmó todas las respuestas
    w.evento = await api('/api/eventos', 'POST', { nombre: w.nombre, tipo_evento: w.tipo });
    S.eventos.unshift(w.evento); w.nuevo = false;
  }
  const contexto = { ...w.r }; if (cancion(w.actual)) delete contexto.genero_actual;   // el género lo da la canción
  const d = await api(`/api/eventos/${w.evento.id}/consultas`, 'POST', { contexto, aclaraciones: Object.fromEntries(Object.entries(w.aclaraciones).filter(([k]) => pasos().includes(k))), cancion_actual_id: w.actual ? Number(w.actual) : null });
  if (w.evento.estado === 'PLANEADO') w.evento.estado = 'EN_CURSO';
  mostrarResultado(d, w.evento, new Date().toISOString(), false);
}

// ---------------------------------------------------------------- resultado (consulta nueva o del historial)
function mostrarResultado(d, evento, cuando, delHistorial) {
  S.evento = evento;
  const h = d.hechos || {};
  S.previas = { momento: h.momento, grupo_edad: h.grupo_edad, actual: d.cancion_actual ? Number(d.cancion_actual.id) : null };
  $('#resSobre').textContent = delHistorial ? 'CONSULTA DEL HISTORIAL' : 'RESULTADO DE LA CONSULTA';
  $('#resTitulo').textContent = evento.nombre;
  $('#resFecha').textContent = `${fecha(cuando)} · consulta n.º ${d.contexto_id} · respuesta en ${d.tiempo_respuesta_ms} ms`;
  $('#otraConsulta').hidden = evento.estado === 'FINALIZADO';
  const fichas = $('#resHechos'); fichas.replaceChildren();
  for (const v of ['tipo_evento', 'momento', 'grupo_edad', 'genero_actual', 'reaccion_publico']) if (h[v]) {
    const f = el('span', 'ficha'); f.append(el('i', null, variable(v).nombre + ': '), document.createTextNode(etq(v, h[v]))); fichas.append(f); }
  if (d.cancion_actual) { const f = el('span', 'ficha'); f.append(el('i', null, 'Suena: '), document.createTextNode(`${d.cancion_actual.titulo} · ${d.cancion_actual.artista}`)); fichas.append(f); }
  const reglas = $('#reglas'); reglas.replaceChildren();
  if (d.sin_reglas) reglas.append(el('p', 'tenue', d.aviso));
  for (const r of d.reglas_disparadas) { const item = el('div', 'regla'); item.append(el('b', null, `${r.codigo} · ${r.nombre}`), el('span', null, r.conclusion), el('small', null, r.descripcion)); reglas.append(item); }
  const conf = $('#conflictos'); conf.replaceChildren();
  for (const c of d.conflictos) conf.append(el('div', 'conflicto', 'Conflicto: ' + c.descripcion));
  const recs = $('#recs'); recs.replaceChildren();
  if (!d.recomendaciones.length) recs.append(el('p', 'tenue', 'No hay recomendaciones para este contexto.'));
  for (const rec of d.recomendaciones) recs.append(bloque(rec));
  $('#aviso').textContent = d.aviso;
  if (d.aclaraciones && Object.keys(d.aclaraciones).length) {
    const a = el('p', 'tenue', 'Aclaraciones consultadas: ' + Object.entries(d.aclaraciones).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${v.replaceAll('_', ' ')}`).join(' · '));
    reglas.prepend(a);
  }
  ver('Resultado');
}
$('#otraConsulta').addEventListener('click', () => nuevaConsulta(S.evento, S.previas));

function bloque(rec) {
  const block = el('div', 'rec');
  block.append(el('span', 'sobre', `${rec.accion.replaceAll('_', ' ')} · ${rec.reglas.join(', ')} · recomendación n.º ${rec.id}`), el('p', null, rec.mensaje));
  for (const n of rec.notas) block.append(el('p', 'tenue', '• ' + n));
  const [sugerida, ...otras] = rec.canciones;
  if (sugerida) block.append(tarjeta(sugerida, 'Canción sugerida'));
  const porque = el('details', 'porque'); porque.open = true; porque.append(el('summary', null, '¿Por qué? (explicación)'), el('p', null, rec.explicacion)); block.append(porque);
  const pie = el('div', 'decide'); block.append(pie);
  const cerrar = d => { pie.replaceChildren(el('p', 'hecho-decision',
    `Decisión: ${d.accion}${d.cancion_final ? ' → ' + d.cancion_final : ''}${d.motivo ? ' · ' + d.motivo : ''} · ${fecha(d.decidida_en)}`)); block.querySelectorAll('.usar').forEach(b => b.remove()); };
  const motivo = el('input'); motivo.placeholder = 'Motivo (opcional)'; motivo.maxLength = 1000; motivo.setAttribute('aria-label', 'Motivo de la decisión');
  const decidir = (accion, finalId) => intentar(async () => {
    const r = await api(`/api/recomendaciones/${rec.id}/decision`, 'POST', { accion, cancion_final_id: finalId || null, motivo: motivo.value });
    rec.decision = r.decision; cerrar(r.decision);
    if (accion === 'ACEPTADA' && sugerida) S.previas.actual = Number(sugerida.id);
    if (accion === 'MODIFICADA') S.previas.actual = finalId;
  });
  if (otras.length) {
    const mas = el('details', 'porque'); mas.append(el('summary', null, `Otras ${otras.length} candidatas`));
    for (const c of otras) { const t = tarjeta(c); if (!rec.decision) t.append(boton('Usar esta (registra la decisión como MODIFICADA)', () => decidir('MODIFICADA', Number(c.id)), 'mini usar')); mas.append(t); }
    block.append(mas);
  }
  if (rec.decision) cerrar(rec.decision);
  else pie.append(motivo, boton('Aceptar', () => decidir('ACEPTADA')), boton('Rechazar', () => decidir('RECHAZADA')));
  return block;
}
function tarjeta(c, titulo) {
  const card = el('div', 'cancion');
  if (titulo) card.append(el('small', 'sobre', titulo.toUpperCase()));
  const delta = c.delta_energia == null ? '' : ` (${c.delta_energia > 0 ? '+' : ''}${c.delta_energia})`;
  const bpm = c.diferencia_bpm == null ? '' : ` (diferencia ${c.diferencia_bpm})`;
  card.append(el('b', null, `${c.titulo} · ${c.artista}`), el('small', null, `${c.genero} · ${c.bpm} BPM${bpm} · ${c.tonalidad_camelot} · energía ${c.energia}${delta}${marcas(c)}`));
  const transiciones = c.transiciones.map(t => `${t.nombre} (${t.caso.replaceAll('_', ' ').toLowerCase()})`).join(' · ');
  card.append(el('small', null, 'Transición: ' + (transiciones || 'sin técnica definida')));
  for (const n of c.notas) card.append(el('small', null, '• ' + n));
  return card;
}

// ---------------------------------------------------------------- catálogo
function llenarSelects() {
  const g = $('#genero'); g.replaceChildren(new Option('Selecciona…', ''));
  for (const n of Object.keys(S.op.generos)) g.append(new Option(n, n));
  const f = $('#formato'); f.replaceChildren();
  for (const x of S.op.formatos) f.append(new Option(x, x));
}
function irCatalogo() { pintarCatalogo(); ver('Catalogo'); }
function pintarCatalogo() {
  const box = $('#catalogo'); box.replaceChildren();
  if (!S.catalogo.length) box.append(el('p', 'tenue', 'Sin canciones. Agrega o importa tu catálogo para recibir recomendaciones de canciones.'));
  for (const c of S.catalogo) {
    const t = el('div', 'carta-opcion');
    t.append(el('span', 'icono', ICONOS[S.op.generos[c.genero]] || '♫'), el('b', null, c.titulo), el('small', null, c.artista),
      el('small', null, `${c.genero} · ${c.bpm} BPM · ${c.tonalidad_camelot} · energía ${c.energia} · ${c.formato}${marcas(c)}`));
    const quitar = boton('✕ Quitar', () => intentar(async () => { await api(`/api/canciones/${c.id}`, 'DELETE'); S.catalogo = S.catalogo.filter(x => x.id !== c.id); pintarCatalogo(); }));
    quitar.setAttribute('aria-label', `Quitar ${c.titulo}`); t.append(quitar); box.append(t);
  }
}
$('#formCancion').addEventListener('submit', e => {
  e.preventDefault(); const d = Object.fromEntries(new FormData(e.target));
  intentar(async () => {
    S.catalogo.push(await api('/api/canciones', 'POST', { titulo: d.titulo, artista: d.artista, genero: d.genero, bpm: Number(d.bpm),
      tonalidad_camelot: d.tonalidad_camelot, energia: Number(d.energia), duracion_seg: Number(d.duracion_seg), formato: d.formato,
      conocida: d.conocida === 'on', comercial: d.comercial === 'on' }));
    pintarCatalogo(); e.target.reset();
  });
});
// Importa una lista de canciones (mismo formato que docs/ejemplos/catalogo_ejemplo.json).
$('#archivoCatalogo').addEventListener('change', e => intentar(async () => {
  const archivo = e.target.files[0]; if (!archivo) return;
  let lista;
  try { lista = JSON.parse(await archivo.text()); } catch { throw Error('El archivo no es un JSON válido.'); }
  if (!Array.isArray(lista)) throw Error('El archivo debe contener una lista de canciones.');
  let guardadas = 0; const errores = [];
  for (const c of lista) {
    const { id, ...datos } = c || {};      // el id lo asigna la base
    try { S.catalogo.push(await api('/api/canciones', 'POST', datos)); guardadas++; }
    catch (err) { errores.push(`${datos.titulo || 'sin título'}: ${err.message}`); }
  }
  pintarCatalogo(); e.target.value = '';
  $('#importado').textContent = `${guardadas} de ${lista.length} canciones importadas.` + (errores.length ? ' No se guardaron: ' + errores.join(' · ') : '');
}));

// ---------------------------------------------------------------- arranque
(async function init() {
  try {
    S.op = await api('/api/opciones');
    const { usuario } = await api('/api/sesion');
    if (usuario) await entrar(usuario); else mostrarAcceso();
  } catch (e) { mostrarAcceso(); avisar('No fue posible conectar con el servidor: ' + e.message); }
})();
