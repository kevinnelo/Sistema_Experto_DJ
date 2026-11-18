-- Pruebas de las restricciones de integridad en PostgreSQL 16.
-- Ejecución (después de sistema_experto_dj.sql):  psql -U postgres -f pruebas_integridad.sql
-- Cada caso intenta una operación inválida y espera que la base la rechace.
-- Todo corre en una transacción que se deshace al final: no deja datos.
SET search_path TO sistema_dj;
BEGIN;

CREATE TEMP TABLE resultado (caso TEXT, descripcion TEXT, estado TEXT) ON COMMIT DROP;

CREATE FUNCTION pg_temp.debe_fallar(p_caso TEXT, p_descripcion TEXT, p_sql TEXT) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
        INSERT INTO resultado VALUES (p_caso, p_descripcion, 'FALLA: la base aceptó la operación');
    EXCEPTION WHEN integrity_constraint_violation OR check_violation OR foreign_key_violation
                OR unique_violation OR not_null_violation THEN
        INSERT INTO resultado VALUES (p_caso, p_descripcion, 'OK (rechazada)');
    END;
END $$;

CREATE FUNCTION pg_temp.v(p_var TEXT, p_cod TEXT) RETURNS INTEGER LANGUAGE sql AS $$
    SELECT vv.id FROM sistema_dj.valor_variable vv JOIN sistema_dj.variable v ON v.id = vv.variable_id
    WHERE v.codigo = p_var AND vv.codigo = p_cod $$;

-- Datos válidos de partida: dos DJ, canciones, un evento, un contexto y dos recomendaciones
INSERT INTO usuario (nombre, correo, clave_hash, rol) VALUES ('DJ Uno', 'uno@ejemplo.com', 'hash-de-prueba', 'DJ'), ('DJ Dos', 'dos@ejemplo.com', 'hash-de-prueba', 'DJ');
INSERT INTO cancion (usuario_id, titulo, artista, genero_id, bpm, tonalidad_camelot, energia, duracion_seg, formato)
SELECT u.id, x.titulo, 'Artista', (SELECT id FROM genero_musical WHERE nombre = 'Salsa'), 124, '8A', 5, 200, 'MP3'
FROM (VALUES ('uno@ejemplo.com', 'Actual'), ('uno@ejemplo.com', 'Sugerida'), ('uno@ejemplo.com', 'Otra'),
             ('dos@ejemplo.com', 'Ajena')) AS x(correo, titulo) JOIN usuario u ON u.correo = x.correo;
INSERT INTO evento (usuario_id, nombre, tipo_evento_id, inicio_previsto, duracion_min)
SELECT id, 'Evento A', pg_temp.v('tipo_evento', 'boda'), now(), 120 FROM usuario WHERE correo = 'uno@ejemplo.com';
INSERT INTO evento (usuario_id, nombre, tipo_evento_id, inicio_previsto, duracion_min)
SELECT id, 'Evento B', pg_temp.v('tipo_evento', 'discoteca'), now(), 120 FROM usuario WHERE correo = 'uno@ejemplo.com';
INSERT INTO contexto_evento (evento_id, momento_id, cancion_actual_id)
SELECT e.id, pg_temp.v('momento', 'cierre'), c.id FROM evento e, cancion c WHERE e.nombre = 'Evento A' AND c.titulo = 'Actual';
INSERT INTO recomendacion (evento_id, contexto_id, cancion_id, explicacion)
SELECT x.evento_id, x.id, c.id, 'R11: energía menor' FROM contexto_evento x, cancion c WHERE c.titulo = 'Sugerida';
INSERT INTO recomendacion (evento_id, contexto_id, explicacion)            -- [C5] general: sin canción ni técnica
SELECT evento_id, id, 'R02: criterio general' FROM contexto_evento;
INSERT INTO recomendacion_regla SELECT r.id, 11 FROM recomendacion r WHERE r.cancion_id IS NOT NULL;
INSERT INTO recomendacion_transicion SELECT r.id, 1 FROM recomendacion r WHERE r.cancion_id IS NOT NULL;

SELECT pg_temp.debe_fallar('RI01', 'condicion_regla con valor de otra variable',
  $q$INSERT INTO condicion_regla VALUES (1, (SELECT id FROM variable WHERE codigo='momento'), pg_temp.v('genero_actual','salsa'))$q$);
SELECT pg_temp.debe_fallar('RI02a', 'canción con BPM 39',
  $q$INSERT INTO cancion (usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato) VALUES (1,'x','x',1,39,'8A',5,200,'MP3')$q$);
SELECT pg_temp.debe_fallar('RI02b', 'canción con tonalidad 13A',
  $q$INSERT INTO cancion (usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato) VALUES (1,'x','x',1,120,'13A',5,200,'MP3')$q$);
SELECT pg_temp.debe_fallar('RI02c', 'canción con energía 11',
  $q$INSERT INTO cancion (usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato) VALUES (1,'x','x',1,120,'8A',11,200,'MP3')$q$);
SELECT pg_temp.debe_fallar('RI02d', 'canción con formato OGG',
  $q$INSERT INTO cancion (usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato) VALUES (1,'x','x',1,120,'8A',5,200,'OGG')$q$);
SELECT pg_temp.debe_fallar('RI02e', 'canción repetida (título y artista) en el mismo catálogo',
  $q$INSERT INTO cancion (usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato) SELECT usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato FROM cancion WHERE titulo='Actual'$q$);
SELECT pg_temp.debe_fallar('RI02f', 'canción sin indicar si es conocida (NULL)',
  $q$INSERT INTO cancion (usuario_id,titulo,artista,genero_id,bpm,tonalidad_camelot,energia,duracion_seg,formato,conocida) VALUES (1,'x','x',1,120,'8A',5,200,'MP3',NULL)$q$);
SELECT pg_temp.debe_fallar('RI03', 'evento cuyo tipo es un valor de momento',
  $q$INSERT INTO evento (usuario_id,nombre,tipo_evento_id,inicio_previsto,duracion_min) SELECT id,'x',pg_temp.v('momento','cierre'),now(),60 FROM usuario LIMIT 1$q$);
SELECT pg_temp.debe_fallar('RI04a', 'contexto con momento_id de otra variable',
  $q$INSERT INTO contexto_evento (evento_id, momento_id) SELECT id, pg_temp.v('tipo_evento','boda') FROM evento WHERE nombre='Evento A'$q$);
SELECT pg_temp.debe_fallar('RI04b', 'contexto con reaccion_publico_id de otra variable',
  $q$INSERT INTO contexto_evento (evento_id, reaccion_publico_id) SELECT id, pg_temp.v('genero_actual','salsa') FROM evento WHERE nombre='Evento A'$q$);
SELECT pg_temp.debe_fallar('RI05', 'género enlazado a un valor que no es de genero_actual',
  $q$INSERT INTO genero_musical (nombre, valor_regla_id) VALUES ('Raro', pg_temp.v('momento','cierre'))$q$);
SELECT pg_temp.debe_fallar('RI06', 'recomendación con contexto de otro evento',
  $q$INSERT INTO recomendacion (evento_id, contexto_id, explicacion) SELECT e.id, x.id, 'x' FROM evento e, contexto_evento x WHERE e.nombre='Evento B'$q$);
SELECT pg_temp.debe_fallar('RI07a', 'canción sugerida de otro DJ',
  $q$INSERT INTO recomendacion (evento_id, contexto_id, cancion_id, explicacion) SELECT x.evento_id, x.id, c.id, 'x' FROM contexto_evento x, cancion c WHERE c.titulo='Ajena'$q$);
SELECT pg_temp.debe_fallar('RI07b', 'canción actual de otro DJ',
  $q$INSERT INTO contexto_evento (evento_id, cancion_actual_id) SELECT e.id, c.id FROM evento e, cancion c WHERE e.nombre='Evento A' AND c.titulo='Ajena'$q$);
SELECT pg_temp.debe_fallar('RI07c', 'canción final de otro DJ',
  $q$INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id) SELECT r.id, 'MODIFICADA', c.id FROM recomendacion r, cancion c WHERE r.cancion_id IS NOT NULL AND c.titulo='Ajena'$q$);
SELECT pg_temp.debe_fallar('RI08', 'recomendación sin explicación',
  $q$INSERT INTO recomendacion (evento_id, contexto_id, explicacion) SELECT evento_id, id, '  ' FROM contexto_evento$q$);
SELECT pg_temp.debe_fallar('RI09', 'técnica en una recomendación sin canción',
  $q$INSERT INTO recomendacion_transicion SELECT id, 1 FROM recomendacion WHERE cancion_id IS NULL$q$);
SELECT pg_temp.debe_fallar('RI10a', 'MODIFICADA sin canción final',
  $q$INSERT INTO decision_dj (recomendacion_id, accion) SELECT id, 'MODIFICADA' FROM recomendacion WHERE cancion_id IS NOT NULL$q$);
SELECT pg_temp.debe_fallar('RI10b', 'ACEPTADA con canción final',
  $q$INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id) SELECT r.id, 'ACEPTADA', c.id FROM recomendacion r, cancion c WHERE r.cancion_id IS NOT NULL AND c.titulo='Otra'$q$);
SELECT pg_temp.debe_fallar('RI10c', 'MODIFICADA con la misma canción sugerida',
  $q$INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id) SELECT id, 'MODIFICADA', cancion_id FROM recomendacion WHERE cancion_id IS NOT NULL$q$);

-- Decisión válida, y luego la segunda decisión sobre la misma recomendación
INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id, motivo)
SELECT r.id, 'MODIFICADA', c.id, 'prefiero otra' FROM recomendacion r, cancion c WHERE r.cancion_id IS NOT NULL AND c.titulo = 'Otra';
SELECT pg_temp.debe_fallar('RI10d', 'segunda decisión sobre la misma recomendación',
  $q$INSERT INTO decision_dj (recomendacion_id, accion) SELECT id, 'RECHAZADA' FROM recomendacion WHERE cancion_id IS NOT NULL$q$);
SELECT pg_temp.debe_fallar('RI11a', 'modificar un contexto registrado', $q$UPDATE contexto_evento SET momento_id = NULL$q$);
SELECT pg_temp.debe_fallar('RI11b', 'modificar una recomendación registrada', $q$UPDATE recomendacion SET explicacion = 'otra'$q$);
SELECT pg_temp.debe_fallar('RI11c', 'modificar una decisión registrada', $q$UPDATE decision_dj SET accion = 'RECHAZADA'$q$);
UPDATE evento SET estado = 'EN_CURSO' WHERE nombre = 'Evento A';
SELECT pg_temp.debe_fallar('RI12a', 'evento EN_CURSO vuelve a PLANEADO', $q$UPDATE evento SET estado='PLANEADO' WHERE nombre='Evento A'$q$);
UPDATE evento SET estado = 'FINALIZADO' WHERE nombre = 'Evento A';
SELECT pg_temp.debe_fallar('RI12b', 'evento FINALIZADO vuelve a EN_CURSO', $q$UPDATE evento SET estado='EN_CURSO' WHERE nombre='Evento A'$q$);
SELECT pg_temp.debe_fallar('RI12c', 'contexto nuevo en un evento finalizado',
  $q$INSERT INTO contexto_evento (evento_id) SELECT id FROM evento WHERE nombre='Evento A'$q$);
SELECT pg_temp.debe_fallar('RI13a', 'correo repetido', $q$INSERT INTO usuario (nombre,correo,clave_hash,rol) VALUES ('x','uno@ejemplo.com','h','DJ')$q$);
SELECT pg_temp.debe_fallar('RI13b', 'rol inexistente', $q$INSERT INTO usuario (nombre,correo,clave_hash,rol) VALUES ('x','x@ejemplo.com','h','INVITADO')$q$);
SELECT pg_temp.debe_fallar('RI13c', 'usuario sin hash de contraseña', $q$INSERT INTO usuario (nombre,correo,rol) VALUES ('x','y@ejemplo.com','DJ')$q$);
SELECT pg_temp.debe_fallar('RI14a', 'regla con acción desconocida',
  $q$INSERT INTO regla (id,codigo,nombre,conclusion,descripcion,accion) VALUES (99,'R99','x','x','x','BAILAR')$q$);
SELECT pg_temp.debe_fallar('RI14b', 'caso de transición desconocido', $q$INSERT INTO transicion_regla (caso,tecnica_id) VALUES ('INVENTADO',1)$q$);
SELECT pg_temp.debe_fallar('RI14c', 'borrar una regla citada por una recomendación', $q$DELETE FROM regla WHERE codigo='R11'$q$);
SELECT pg_temp.debe_fallar('RI15', 'borrar una canción citada en el historial', $q$DELETE FROM cancion WHERE titulo='Sugerida'$q$);

SELECT pg_temp.debe_fallar('RI16', 'resultado de consulta que no es un objeto JSON',
  $q$INSERT INTO resultado_consulta SELECT id, '[1]'::jsonb FROM contexto_evento$q$);

SELECT caso, descripcion, estado FROM resultado ORDER BY caso;
SELECT count(*) FILTER (WHERE estado LIKE 'OK%') AS correctas, count(*) AS total FROM resultado;
SELECT evento, reglas, cancion_sugerida, accion, cancion_final, motivo FROM v_historial_decisiones;
ROLLBACK;
