-- =====================================================================
-- Sistema experto DJ · esquema único (SQLite)
-- Equivale al esquema sistema_dj del documento (PostgreSQL 16), adaptado
-- a SQLite y con las restricciones de integridad corregidas (ver README).
--   1. Base de conocimiento (BC)   2. Sistema transaccional (ST)
--   3. Disparadores de integridad  4. Vistas
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- 1. BC
CREATE TABLE IF NOT EXISTS variable (
  id          INTEGER PRIMARY KEY,
  codigo      TEXT NOT NULL UNIQUE,
  descripcion TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS valor_variable (
  id          INTEGER PRIMARY KEY,
  variable_id INTEGER NOT NULL REFERENCES variable(id),
  codigo      TEXT NOT NULL,
  etiqueta    TEXT NOT NULL,
  UNIQUE (variable_id, codigo),
  UNIQUE (id, variable_id));            -- destino de la FK compuesta de condicion_regla

CREATE TABLE IF NOT EXISTS regla (
  id          INTEGER PRIMARY KEY,
  codigo      TEXT NOT NULL UNIQUE CHECK (codigo GLOB 'R[0-9][0-9]'),
  nombre      TEXT NOT NULL,
  conclusion  TEXT NOT NULL,
  descripcion TEXT NOT NULL,
  -- Qué hace el motor con la regla. El documento la deducía del texto de la conclusión.
  accion      TEXT NOT NULL CHECK (accion IN (
                'CRITERIO', 'MANTENER_GENERO', 'MISMO_GENERO', 'MANTENER_ENERGIA',
                'SUBIR_ENERGIA', 'BAJAR_ENERGIA', 'BAJAR_O_COMERCIAL', 'CAMBIAR_GENERO', 'CONSULTAR',
                'BUSCAR_OTRA')),
  activa      INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
  version     INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  creada_en   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));

-- Valores de la misma variable se combinan con O; variables distintas, con Y.
CREATE TABLE IF NOT EXISTS condicion_regla (
  regla_id    INTEGER NOT NULL REFERENCES regla(id) ON DELETE CASCADE,
  variable_id INTEGER NOT NULL REFERENCES variable(id),
  valor_id    INTEGER NOT NULL,
  PRIMARY KEY (regla_id, valor_id),
  FOREIGN KEY (valor_id, variable_id) REFERENCES valor_variable (id, variable_id));

CREATE TABLE IF NOT EXISTS parametro_experto (
  clave       TEXT PRIMARY KEY,
  valor       REAL NOT NULL CHECK (valor > 0),
  unidad      TEXT,
  descripcion TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS tecnica_transicion (
  id          INTEGER PRIMARY KEY,
  codigo      TEXT NOT NULL UNIQUE,
  nombre      TEXT NOT NULL,
  descripcion TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS transicion_regla (
  id          INTEGER PRIMARY KEY,
  caso        TEXT NOT NULL CHECK (caso IN (
                'SIEMPRE', 'BPM_SIMILAR', 'BPM_TOLERABLE', 'BPM_DISTINTO', 'CAMBIO_CANCION',
                'EFECTO_IMPACTO', 'CAMBIO_GENERO', 'ANUNCIO_MICROFONO')),
  tecnica_id  INTEGER NOT NULL REFERENCES tecnica_transicion(id),
  prioridad   INTEGER NOT NULL DEFAULT 1 CHECK (prioridad > 0),
  UNIQUE (caso, tecnica_id));

-- ---------------------------------------------------------------- 2. ST
CREATE TABLE IF NOT EXISTS usuario (
  id        INTEGER PRIMARY KEY,
  nombre    TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
  correo    TEXT NOT NULL UNIQUE CHECK (correo LIKE '_%@_%._%' AND correo = lower(trim(correo))),
  rol       TEXT NOT NULL CHECK (rol IN ('DJ', 'ADMIN_CONOCIMIENTO')),
  creado_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')));

-- valor_regla_id enlaza el género con el dominio de la variable genero_actual.
CREATE TABLE IF NOT EXISTS genero_musical (
  id             INTEGER PRIMARY KEY,
  nombre         TEXT NOT NULL UNIQUE,
  valor_regla_id INTEGER UNIQUE REFERENCES valor_variable(id));

-- Catálogo musical del DJ (RF01)
CREATE TABLE IF NOT EXISTS cancion (
  id                INTEGER PRIMARY KEY,
  usuario_id        INTEGER NOT NULL REFERENCES usuario(id),
  titulo            TEXT NOT NULL CHECK (length(trim(titulo)) BETWEEN 1 AND 200),
  artista           TEXT NOT NULL CHECK (length(trim(artista)) BETWEEN 1 AND 200),
  genero_id         INTEGER NOT NULL REFERENCES genero_musical(id),
  bpm               REAL NOT NULL CHECK (bpm BETWEEN 40 AND 250),
  tonalidad_camelot TEXT NOT NULL
                    CHECK (tonalidad_camelot GLOB '[1-9][AB]' OR tonalidad_camelot GLOB '1[0-2][AB]'),
  energia           INTEGER NOT NULL CHECK (energia BETWEEN 1 AND 10),
  duracion_seg      INTEGER NOT NULL CHECK (duracion_seg > 0),
  formato           TEXT NOT NULL CHECK (formato IN ('MP3', 'WAV', 'FLAC')),
  conocida          INTEGER NOT NULL DEFAULT 0 CHECK (conocida IN (0, 1)),    -- muy reconocida por el público (R23)
  comercial         INTEGER NOT NULL DEFAULT 0 CHECK (comercial IN (0, 1)),   -- éxito comercial o de radio (R21)
  ruta_archivo      TEXT,
  metadatos_id3     TEXT CHECK (metadatos_id3 IS NULL OR json_valid(metadatos_id3)),
  UNIQUE (usuario_id, titulo, artista));

-- Evento o fiesta (RF02)
CREATE TABLE IF NOT EXISTS evento (
  id              INTEGER PRIMARY KEY,
  usuario_id      INTEGER NOT NULL REFERENCES usuario(id),
  nombre          TEXT NOT NULL CHECK (length(trim(nombre)) > 0),
  tipo_evento_id  INTEGER NOT NULL REFERENCES valor_variable(id),
  lugar           TEXT,
  aforo_estimado  INTEGER CHECK (aforo_estimado > 0),
  inicio_previsto TEXT NOT NULL,
  duracion_min    INTEGER NOT NULL CHECK (duracion_min > 0),
  estado          TEXT NOT NULL DEFAULT 'PLANEADO'
                  CHECK (estado IN ('PLANEADO', 'EN_CURSO', 'FINALIZADO')));

-- Fotografías del contexto: cada actualización es un registro nuevo (nunca se edita).
-- cancion_actual_id guarda la canción que sonaba: el motor la usa para la compatibilidad.
CREATE TABLE IF NOT EXISTS contexto_evento (
  id                  INTEGER PRIMARY KEY,
  evento_id           INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  momento_id          INTEGER REFERENCES valor_variable(id),
  grupo_edad_id       INTEGER REFERENCES valor_variable(id),
  genero_actual_id    INTEGER REFERENCES valor_variable(id),
  reaccion_publico_id INTEGER REFERENCES valor_variable(id),
  cancion_actual_id   INTEGER REFERENCES cancion(id),
  registrado_en       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE (id, evento_id));              -- destino de la FK compuesta de recomendacion
CREATE INDEX IF NOT EXISTS ix_contexto_evento_fecha ON contexto_evento (evento_id, registrado_en);

-- Recomendaciones del motor (RF03). Una por cada acción inferida.
-- cancion_id es la canción sugerida; queda vacío en las recomendaciones generales
-- (criterio, consultar, cambiar género) o cuando ninguna canción cumple la regla.
-- La FK compuesta garantiza que el contexto pertenece al mismo evento.
CREATE TABLE IF NOT EXISTS recomendacion (
  id                  INTEGER PRIMARY KEY,
  evento_id           INTEGER NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
  contexto_id         INTEGER NOT NULL,
  cancion_id          INTEGER REFERENCES cancion(id),
  explicacion         TEXT NOT NULL CHECK (length(trim(explicacion)) > 0),     -- RF04
  generada_en         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  tiempo_respuesta_ms INTEGER CHECK (tiempo_respuesta_ms >= 0),               -- RNF01
  FOREIGN KEY (contexto_id, evento_id) REFERENCES contexto_evento (id, evento_id));
CREATE INDEX IF NOT EXISTS ix_recomendacion_evento ON recomendacion (evento_id);

-- Reglas que sustentan cada recomendación (trazabilidad de RF04)
CREATE TABLE IF NOT EXISTS recomendacion_regla (
  recomendacion_id INTEGER NOT NULL REFERENCES recomendacion(id) ON DELETE CASCADE,
  regla_id         INTEGER NOT NULL REFERENCES regla(id),
  PRIMARY KEY (recomendacion_id, regla_id));

-- Técnicas de transición de la canción sugerida. Sustituye a recomendacion.tecnica_id:
-- una transición combina varias técnicas (p. ej. sincronización + cross-fade + echo out).
CREATE TABLE IF NOT EXISTS recomendacion_transicion (
  recomendacion_id    INTEGER NOT NULL REFERENCES recomendacion(id) ON DELETE CASCADE,
  transicion_regla_id INTEGER NOT NULL REFERENCES transicion_regla(id),
  PRIMARY KEY (recomendacion_id, transicion_regla_id));

-- Decisión del DJ (RF05): una por recomendación; solo MODIFICADA lleva canción final.
CREATE TABLE IF NOT EXISTS decision_dj (
  id               INTEGER PRIMARY KEY,
  recomendacion_id INTEGER NOT NULL UNIQUE REFERENCES recomendacion(id) ON DELETE CASCADE,
  accion           TEXT NOT NULL CHECK (accion IN ('ACEPTADA', 'RECHAZADA', 'MODIFICADA')),
  cancion_final_id INTEGER REFERENCES cancion(id),
  motivo           TEXT,
  decidida_en      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK ((accion = 'MODIFICADA') = (cancion_final_id IS NOT NULL)));

-- ---------------------------------------------------------------- 3. Disparadores
-- 3.1 Cada FK a valor_variable debe apuntar a un valor de SU variable.
CREATE TRIGGER IF NOT EXISTS trg_genero_dominio_ins BEFORE INSERT ON genero_musical
BEGIN
  SELECT RAISE(ABORT, 'valor_regla_id no pertenece a la variable genero_actual')
  WHERE NEW.valor_regla_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.valor_regla_id AND v.codigo = 'genero_actual');
END;
CREATE TRIGGER IF NOT EXISTS trg_genero_dominio_upd BEFORE UPDATE OF valor_regla_id ON genero_musical
BEGIN
  SELECT RAISE(ABORT, 'valor_regla_id no pertenece a la variable genero_actual')
  WHERE NEW.valor_regla_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.valor_regla_id AND v.codigo = 'genero_actual');
END;
CREATE TRIGGER IF NOT EXISTS trg_evento_dominio_ins BEFORE INSERT ON evento
BEGIN
  SELECT RAISE(ABORT, 'tipo_evento_id no pertenece a la variable tipo_evento')
  WHERE NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.tipo_evento_id AND v.codigo = 'tipo_evento');
END;
CREATE TRIGGER IF NOT EXISTS trg_evento_dominio_upd BEFORE UPDATE OF tipo_evento_id ON evento
BEGIN
  SELECT RAISE(ABORT, 'tipo_evento_id no pertenece a la variable tipo_evento')
  WHERE NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.tipo_evento_id AND v.codigo = 'tipo_evento');
END;
CREATE TRIGGER IF NOT EXISTS trg_contexto_ins BEFORE INSERT ON contexto_evento
BEGIN
  SELECT RAISE(ABORT, 'momento_id no pertenece a la variable momento')
  WHERE NEW.momento_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.momento_id AND v.codigo = 'momento');
  SELECT RAISE(ABORT, 'grupo_edad_id no pertenece a la variable grupo_edad')
  WHERE NEW.grupo_edad_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.grupo_edad_id AND v.codigo = 'grupo_edad');
  SELECT RAISE(ABORT, 'genero_actual_id no pertenece a la variable genero_actual')
  WHERE NEW.genero_actual_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.genero_actual_id AND v.codigo = 'genero_actual');
  SELECT RAISE(ABORT, 'reaccion_publico_id no pertenece a la variable reaccion_publico')
  WHERE NEW.reaccion_publico_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM valor_variable vv JOIN variable v ON v.id = vv.variable_id
    WHERE vv.id = NEW.reaccion_publico_id AND v.codigo = 'reaccion_publico');
  -- 3.2 Un evento finalizado no admite más contextos.
  SELECT RAISE(ABORT, 'el evento está finalizado')
  WHERE (SELECT estado FROM evento WHERE id = NEW.evento_id) = 'FINALIZADO';
  -- 3.3 La canción que suena debe ser del catálogo del DJ del evento.
  SELECT RAISE(ABORT, 'la canción actual no es del catálogo del DJ del evento')
  WHERE NEW.cancion_actual_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM cancion c JOIN evento e ON e.usuario_id = c.usuario_id
    WHERE c.id = NEW.cancion_actual_id AND e.id = NEW.evento_id);
END;
CREATE TRIGGER IF NOT EXISTS trg_recomendacion_ins BEFORE INSERT ON recomendacion
BEGIN
  SELECT RAISE(ABORT, 'la canción sugerida no es del catálogo del DJ del evento')
  WHERE NEW.cancion_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM cancion c JOIN evento e ON e.usuario_id = c.usuario_id
    WHERE c.id = NEW.cancion_id AND e.id = NEW.evento_id);
END;
CREATE TRIGGER IF NOT EXISTS trg_transicion_ins BEFORE INSERT ON recomendacion_transicion
BEGIN
  SELECT RAISE(ABORT, 'solo una recomendación con canción puede llevar técnica de transición')
  WHERE (SELECT cancion_id FROM recomendacion WHERE id = NEW.recomendacion_id) IS NULL;
END;
CREATE TRIGGER IF NOT EXISTS trg_decision_ins BEFORE INSERT ON decision_dj
BEGIN
  SELECT RAISE(ABORT, 'la canción final no es del catálogo del DJ del evento')
  WHERE NEW.cancion_final_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM cancion c
    JOIN recomendacion r ON r.id = NEW.recomendacion_id
    JOIN evento e ON e.id = r.evento_id AND e.usuario_id = c.usuario_id
    WHERE c.id = NEW.cancion_final_id);
  SELECT RAISE(ABORT, 'la canción final debe ser distinta de la sugerida')
  WHERE NEW.cancion_final_id IS NOT NULL
    AND NEW.cancion_final_id = (SELECT cancion_id FROM recomendacion WHERE id = NEW.recomendacion_id);
END;
-- 3.4 El historial no se reescribe (CU02 y CU05): contextos, recomendaciones y decisiones
--     son de solo inserción.
CREATE TRIGGER IF NOT EXISTS trg_contexto_inmutable BEFORE UPDATE ON contexto_evento
BEGIN SELECT RAISE(ABORT, 'un contexto registrado no se modifica: registre uno nuevo'); END;
CREATE TRIGGER IF NOT EXISTS trg_recomendacion_inmutable BEFORE UPDATE ON recomendacion
BEGIN SELECT RAISE(ABORT, 'una recomendación registrada no se modifica'); END;
CREATE TRIGGER IF NOT EXISTS trg_decision_inmutable BEFORE UPDATE ON decision_dj
BEGIN SELECT RAISE(ABORT, 'una decisión registrada no se modifica'); END;
-- 3.5 El estado del evento solo avanza: PLANEADO -> EN_CURSO -> FINALIZADO.
CREATE TRIGGER IF NOT EXISTS trg_evento_estado BEFORE UPDATE OF estado ON evento
WHEN (OLD.estado = 'FINALIZADO' AND NEW.estado <> 'FINALIZADO')
  OR (OLD.estado = 'EN_CURSO' AND NEW.estado = 'PLANEADO')
BEGIN SELECT RAISE(ABORT, 'el estado del evento no puede retroceder'); END;
-- 3.6 Una canción no cambia de dueño (protege los historiales que la citan).
CREATE TRIGGER IF NOT EXISTS trg_cancion_dueno BEFORE UPDATE OF usuario_id ON cancion
WHEN NEW.usuario_id <> OLD.usuario_id
BEGIN SELECT RAISE(ABORT, 'una canción no puede cambiar de usuario'); END;

-- ---------------------------------------------------------------- 4. Vistas
CREATE VIEW IF NOT EXISTS v_reglas AS
SELECT r.codigo, r.nombre, v.codigo AS variable, vv.codigo AS valor, r.conclusion, r.accion
FROM regla r
JOIN condicion_regla c ON c.regla_id = r.id
JOIN variable v        ON v.id = c.variable_id
JOIN valor_variable vv ON vv.id = c.valor_id
WHERE r.activa = 1;

CREATE VIEW IF NOT EXISTS v_historial_decisiones AS
SELECT e.id            AS evento_id,
       e.nombre        AS evento,
       r.id            AS recomendacion_id,
       r.generada_en,
       (SELECT group_concat(codigo, ', ') FROM (
          SELECT g.codigo FROM recomendacion_regla rr JOIN regla g ON g.id = rr.regla_id
          WHERE rr.recomendacion_id = r.id ORDER BY g.codigo)) AS reglas,
       c.titulo        AS cancion_sugerida,
       d.accion,
       cf.titulo       AS cancion_final,
       d.motivo,
       d.decidida_en
FROM decision_dj d
JOIN recomendacion r ON r.id = d.recomendacion_id
JOIN evento e        ON e.id = r.evento_id
LEFT JOIN cancion c  ON c.id = r.cancion_id
LEFT JOIN cancion cf ON cf.id = d.cancion_final_id;
