"""Genera docs/sql/sistema_experto_dj.sql (PostgreSQL 16) con el mismo modelo que esquema.sql
y los datos de reglas.json. Uso: python3 docs/sql/generar_postgresql.py"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
k = json.loads((RAIZ / "reglas.json").read_text(encoding="utf-8"))
q = lambda s: "'" + str(s).replace("'", "''") + "'"

DDL = r"""-- =====================================================================
-- Sistema experto para recomendación musical de DJ
-- SGBD: PostgreSQL 16 · Esquema: sistema_dj
-- Ejecución: psql -U postgres -f sistema_experto_dj.sql
--
-- Versión con las restricciones de integridad corregidas. Es el mismo modelo
-- que la aplicación ejecuta en SQLite (esquema.sql). Cambios frente a la
-- versión anterior del documento, marcados con [C1]..[C10]:
--  [C1] regla.accion: acción que ejecuta el motor (antes se deducía del texto).
--  [C2] Cada FK a valor_variable comprueba que el valor sea de SU variable
--       (evento.tipo_evento_id, las 4 columnas de contexto_evento y
--       genero_musical.valor_regla_id).
--  [C3] contexto_evento.cancion_actual_id: la canción que sonaba.
--  [C4] recomendacion: FK compuesta (contexto_id, evento_id); el contexto
--       pertenece al mismo evento.
--  [C5] recomendacion: se retira CHECK (cancion_id o tecnica_id). Las
--       recomendaciones generales (CU03) no llevan canción ni técnica.
--  [C6] recomendacion_transicion sustituye a recomendacion.tecnica_id: una
--       transición combina varias técnicas.
--  [C7] Canción sugerida, canción actual y canción final deben ser del
--       catálogo del DJ dueño del evento.
--  [C8] decision_dj: canción final si y solo si la acción es MODIFICADA, y
--       distinta de la sugerida.
--  [C9] Contextos, recomendaciones y decisiones son de solo inserción.
-- [C10] El estado del evento solo avanza y un evento finalizado no admite
--       contextos nuevos.
-- [C11] transicion_regla admite el caso BPM_TOLERABLE (diferencia de 5 a 10 BPM).
-- [C12] cancion.conocida y cancion.comercial, usadas por R23 y R21.
-- [C13] Conocimiento: valor se_retira con las reglas R26 y R27, y parámetro
--       energia_diferencia_mismo_nivel (R19).
-- =====================================================================

DROP SCHEMA IF EXISTS sistema_dj CASCADE;
CREATE SCHEMA sistema_dj;
SET search_path TO sistema_dj;

-- =====================================================================
-- 1. BASE DE CONOCIMIENTO
-- =====================================================================

CREATE TABLE variable (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo      VARCHAR(30)  NOT NULL UNIQUE,
    descripcion VARCHAR(200) NOT NULL
);

CREATE TABLE valor_variable (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variable_id INTEGER      NOT NULL REFERENCES variable(id),
    codigo      VARCHAR(40)  NOT NULL,
    etiqueta    VARCHAR(100) NOT NULL,
    UNIQUE (variable_id, codigo),
    UNIQUE (id, variable_id)            -- destino de la FK compuesta de condicion_regla
);

CREATE TABLE regla (
    id          INTEGER      PRIMARY KEY,
    codigo      CHAR(3)      NOT NULL UNIQUE CHECK (codigo ~ '^R[0-9]{2}$'),       -- R01 ... R27
    nombre      VARCHAR(120) NOT NULL,
    conclusion  VARCHAR(255) NOT NULL,
    descripcion TEXT         NOT NULL,
    accion      VARCHAR(20)  NOT NULL CHECK (accion IN (                       -- [C1]
                    'CRITERIO', 'MANTENER_GENERO', 'MISMO_GENERO', 'MANTENER_ENERGIA',
                    'SUBIR_ENERGIA', 'BAJAR_ENERGIA', 'BAJAR_O_COMERCIAL', 'CAMBIAR_GENERO',
                    'CONSULTAR', 'BUSCAR_OTRA')),
    activa      BOOLEAN      NOT NULL DEFAULT TRUE,
    version     INTEGER      NOT NULL DEFAULT 1 CHECK (version > 0),
    creada_en   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Valores de una misma variable son alternativos (O); variables distintas se combinan (Y).
CREATE TABLE condicion_regla (
    regla_id    INTEGER NOT NULL REFERENCES regla(id) ON DELETE CASCADE,
    variable_id INTEGER NOT NULL REFERENCES variable(id),
    valor_id    INTEGER NOT NULL,
    PRIMARY KEY (regla_id, valor_id),
    FOREIGN KEY (valor_id, variable_id) REFERENCES valor_variable (id, variable_id)
);

CREATE TABLE parametro_experto (
    clave       VARCHAR(60)  PRIMARY KEY,
    valor       NUMERIC(8,2) NOT NULL CHECK (valor > 0),
    unidad      VARCHAR(20),
    descripcion VARCHAR(255) NOT NULL
);

CREATE TABLE tecnica_transicion (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo      VARCHAR(30) NOT NULL UNIQUE,
    nombre      VARCHAR(80) NOT NULL,
    descripcion TEXT        NOT NULL
);

CREATE TABLE transicion_regla (
    id         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    caso       VARCHAR(30) NOT NULL CHECK (caso IN (
                   'SIEMPRE', 'BPM_SIMILAR', 'BPM_TOLERABLE', 'BPM_DISTINTO', 'CAMBIO_CANCION',  -- [C11]
                   'EFECTO_IMPACTO', 'CAMBIO_GENERO', 'ANUNCIO_MICROFONO')),
    tecnica_id INTEGER     NOT NULL REFERENCES tecnica_transicion(id),
    prioridad  SMALLINT    NOT NULL DEFAULT 1 CHECK (prioridad > 0),
    UNIQUE (caso, tecnica_id)
);

-- =====================================================================
-- 2. SISTEMA TRANSACCIONAL
-- =====================================================================

CREATE TABLE usuario (
    id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre    VARCHAR(120) NOT NULL CHECK (btrim(nombre) <> ''),
    correo    VARCHAR(160) NOT NULL UNIQUE
              CHECK (correo LIKE '_%@_%._%' AND correo = lower(btrim(correo))),
    rol       VARCHAR(25)  NOT NULL CHECK (rol IN ('DJ', 'ADMIN_CONOCIMIENTO')),
    creado_en TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE genero_musical (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre         VARCHAR(60) NOT NULL UNIQUE,
    valor_regla_id INTEGER UNIQUE REFERENCES valor_variable(id)                -- [C2]
);

-- Catálogo musical del DJ (RF01)
CREATE TABLE cancion (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id        INTEGER      NOT NULL REFERENCES usuario(id),
    titulo            VARCHAR(200) NOT NULL CHECK (btrim(titulo) <> ''),
    artista           VARCHAR(200) NOT NULL CHECK (btrim(artista) <> ''),
    genero_id         INTEGER      NOT NULL REFERENCES genero_musical(id),
    bpm               NUMERIC(5,2) NOT NULL CHECK (bpm BETWEEN 40 AND 250),
    tonalidad_camelot VARCHAR(3)   NOT NULL CHECK (tonalidad_camelot ~ '^(1[0-2]|[1-9])[AB]$'),
    energia           SMALLINT     NOT NULL CHECK (energia BETWEEN 1 AND 10),
    duracion_seg      INTEGER      NOT NULL CHECK (duracion_seg > 0),
    formato           VARCHAR(5)   NOT NULL CHECK (formato IN ('MP3', 'WAV', 'FLAC')),
    conocida          BOOLEAN      NOT NULL DEFAULT FALSE,   -- [C12] el público la reconoce (R23)
    comercial         BOOLEAN      NOT NULL DEFAULT FALSE,   -- [C12] éxito de radio o de listas (R21)
    ruta_archivo      VARCHAR(500),
    metadatos_id3     JSONB,
    UNIQUE (usuario_id, titulo, artista)
);

-- Evento o fiesta (RF02)
CREATE TABLE evento (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      INTEGER      NOT NULL REFERENCES usuario(id),
    nombre          VARCHAR(200) NOT NULL CHECK (btrim(nombre) <> ''),
    tipo_evento_id  INTEGER      NOT NULL REFERENCES valor_variable(id),      -- [C2]
    lugar           VARCHAR(200),
    aforo_estimado  INTEGER      CHECK (aforo_estimado > 0),
    inicio_previsto TIMESTAMPTZ  NOT NULL,
    duracion_min    INTEGER      NOT NULL CHECK (duracion_min > 0),
    estado          VARCHAR(15)  NOT NULL DEFAULT 'PLANEADO'
                    CHECK (estado IN ('PLANEADO', 'EN_CURSO', 'FINALIZADO'))
);

-- Fotografías del contexto: cada actualización es un registro nuevo
CREATE TABLE contexto_evento (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evento_id           INTEGER     NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
    momento_id          INTEGER     REFERENCES valor_variable(id),            -- [C2]
    grupo_edad_id       INTEGER     REFERENCES valor_variable(id),            -- [C2]
    genero_actual_id    INTEGER     REFERENCES valor_variable(id),            -- [C2]
    reaccion_publico_id INTEGER     REFERENCES valor_variable(id),            -- [C2]
    cancion_actual_id   INTEGER     REFERENCES cancion(id),                   -- [C3]
    registrado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, evento_id)              -- destino de la FK compuesta de recomendacion
);
CREATE INDEX ix_contexto_evento_fecha ON contexto_evento (evento_id, registrado_en);

-- Recomendaciones del motor (RF03): una por cada acción inferida.
-- cancion_id queda vacío en las recomendaciones generales.                     [C5]
CREATE TABLE recomendacion (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evento_id           INTEGER     NOT NULL REFERENCES evento(id) ON DELETE CASCADE,
    contexto_id         INTEGER     NOT NULL,
    cancion_id          INTEGER     REFERENCES cancion(id),
    explicacion         TEXT        NOT NULL CHECK (btrim(explicacion) <> ''), -- RF04
    generada_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
    tiempo_respuesta_ms INTEGER     CHECK (tiempo_respuesta_ms >= 0),          -- RNF01
    FOREIGN KEY (contexto_id, evento_id) REFERENCES contexto_evento (id, evento_id)  -- [C4]
);
CREATE INDEX ix_recomendacion_evento ON recomendacion (evento_id);

-- Reglas que sustentan cada recomendación (trazabilidad de RF04)
CREATE TABLE recomendacion_regla (
    recomendacion_id INTEGER NOT NULL REFERENCES recomendacion(id) ON DELETE CASCADE,
    regla_id         INTEGER NOT NULL REFERENCES regla(id),
    PRIMARY KEY (recomendacion_id, regla_id)
);

-- Técnicas de transición de la canción sugerida                                [C6]
CREATE TABLE recomendacion_transicion (
    recomendacion_id    INTEGER NOT NULL REFERENCES recomendacion(id) ON DELETE CASCADE,
    transicion_regla_id INTEGER NOT NULL REFERENCES transicion_regla(id),
    PRIMARY KEY (recomendacion_id, transicion_regla_id)
);

-- Decisión del DJ (RF05): una por recomendación
CREATE TABLE decision_dj (
    id               INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recomendacion_id INTEGER     NOT NULL UNIQUE REFERENCES recomendacion(id) ON DELETE CASCADE,
    accion           VARCHAR(12) NOT NULL CHECK (accion IN ('ACEPTADA', 'RECHAZADA', 'MODIFICADA')),
    cancion_final_id INTEGER     REFERENCES cancion(id),
    motivo           TEXT,
    decidida_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((accion = 'MODIFICADA') = (cancion_final_id IS NOT NULL))           -- [C8]
);

-- =====================================================================
-- 3. DISPARADORES DE INTEGRIDAD
-- =====================================================================

-- [C2] ¿El valor pertenece a la variable indicada? (NULL se acepta: variable sin responder)
CREATE FUNCTION valor_es_de(p_valor_id INTEGER, p_variable VARCHAR) RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
    SELECT p_valor_id IS NULL OR EXISTS (
        SELECT 1 FROM sistema_dj.valor_variable vv
        JOIN sistema_dj.variable v ON v.id = vv.variable_id
        WHERE vv.id = p_valor_id AND v.codigo = p_variable);
$$;

-- [C7] ¿La canción es del catálogo del DJ dueño del evento?
CREATE FUNCTION cancion_es_del_evento(p_cancion_id INTEGER, p_evento_id INTEGER) RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
    SELECT p_cancion_id IS NULL OR EXISTS (
        SELECT 1 FROM sistema_dj.cancion c
        JOIN sistema_dj.evento e ON e.usuario_id = c.usuario_id
        WHERE c.id = p_cancion_id AND e.id = p_evento_id);
$$;

CREATE FUNCTION trg_genero() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT valor_es_de(NEW.valor_regla_id, 'genero_actual') THEN
        RAISE EXCEPTION 'valor_regla_id no pertenece a la variable genero_actual'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER genero_dominio BEFORE INSERT OR UPDATE OF valor_regla_id ON genero_musical
    FOR EACH ROW EXECUTE FUNCTION trg_genero();

CREATE FUNCTION trg_evento() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT valor_es_de(NEW.tipo_evento_id, 'tipo_evento') THEN
        RAISE EXCEPTION 'tipo_evento_id no pertenece a la variable tipo_evento'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF TG_OP = 'UPDATE' AND (                                                  -- [C10]
           (OLD.estado = 'FINALIZADO' AND NEW.estado <> 'FINALIZADO')
        OR (OLD.estado = 'EN_CURSO'   AND NEW.estado = 'PLANEADO')) THEN
        RAISE EXCEPTION 'el estado del evento no puede retroceder'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER evento_integridad BEFORE INSERT OR UPDATE ON evento
    FOR EACH ROW EXECUTE FUNCTION trg_evento();

CREATE FUNCTION trg_contexto() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT valor_es_de(NEW.momento_id, 'momento')
       OR NOT valor_es_de(NEW.grupo_edad_id, 'grupo_edad')
       OR NOT valor_es_de(NEW.genero_actual_id, 'genero_actual')
       OR NOT valor_es_de(NEW.reaccion_publico_id, 'reaccion_publico') THEN
        RAISE EXCEPTION 'un valor del contexto no pertenece a su variable'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF (SELECT estado FROM evento WHERE id = NEW.evento_id) = 'FINALIZADO' THEN  -- [C10]
        RAISE EXCEPTION 'el evento está finalizado'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT cancion_es_del_evento(NEW.cancion_actual_id, NEW.evento_id) THEN     -- [C7]
        RAISE EXCEPTION 'la canción actual no es del catálogo del DJ del evento'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER contexto_integridad BEFORE INSERT ON contexto_evento
    FOR EACH ROW EXECUTE FUNCTION trg_contexto();

CREATE FUNCTION trg_recomendacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT cancion_es_del_evento(NEW.cancion_id, NEW.evento_id) THEN            -- [C7]
        RAISE EXCEPTION 'la canción sugerida no es del catálogo del DJ del evento'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER recomendacion_integridad BEFORE INSERT ON recomendacion
    FOR EACH ROW EXECUTE FUNCTION trg_recomendacion();

CREATE FUNCTION trg_transicion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT cancion_id FROM recomendacion WHERE id = NEW.recomendacion_id) IS NULL THEN
        RAISE EXCEPTION 'solo una recomendación con canción puede llevar técnica de transición'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER transicion_integridad BEFORE INSERT ON recomendacion_transicion
    FOR EACH ROW EXECUTE FUNCTION trg_transicion();

CREATE FUNCTION trg_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r recomendacion%ROWTYPE;
BEGIN
    SELECT * INTO r FROM recomendacion WHERE id = NEW.recomendacion_id;
    IF NOT cancion_es_del_evento(NEW.cancion_final_id, r.evento_id) THEN        -- [C7]
        RAISE EXCEPTION 'la canción final no es del catálogo del DJ del evento'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.cancion_final_id IS NOT NULL AND NEW.cancion_final_id = r.cancion_id THEN  -- [C8]
        RAISE EXCEPTION 'la canción final debe ser distinta de la sugerida'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER decision_integridad BEFORE INSERT ON decision_dj
    FOR EACH ROW EXECUTE FUNCTION trg_decision();

-- [C9] El historial es de solo inserción
CREATE FUNCTION trg_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'los registros de % no se modifican', TG_TABLE_NAME
          USING ERRCODE = 'integrity_constraint_violation';
END $$;
CREATE TRIGGER contexto_inmutable      BEFORE UPDATE ON contexto_evento FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER recomendacion_inmutable BEFORE UPDATE ON recomendacion   FOR EACH ROW EXECUTE FUNCTION trg_inmutable();
CREATE TRIGGER decision_inmutable      BEFORE UPDATE ON decision_dj     FOR EACH ROW EXECUTE FUNCTION trg_inmutable();

-- Una canción no cambia de dueño (protege los historiales que la citan)
CREATE FUNCTION trg_cancion_dueno() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.usuario_id <> OLD.usuario_id THEN
        RAISE EXCEPTION 'una canción no puede cambiar de usuario'
              USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER cancion_dueno BEFORE UPDATE OF usuario_id ON cancion
    FOR EACH ROW EXECUTE FUNCTION trg_cancion_dueno();

-- =====================================================================
-- 4. VISTAS
-- =====================================================================

CREATE VIEW v_reglas AS
SELECT r.codigo, r.nombre, v.codigo AS variable, vv.codigo AS valor, r.conclusion, r.accion
FROM regla r
JOIN condicion_regla c ON c.regla_id = r.id
JOIN variable v        ON v.id = c.variable_id
JOIN valor_variable vv ON vv.id = c.valor_id
WHERE r.activa;

CREATE VIEW v_historial_decisiones AS
SELECT e.id      AS evento_id,
       e.nombre  AS evento,
       r.id      AS recomendacion_id,
       r.generada_en,
       (SELECT string_agg(g.codigo, ', ' ORDER BY g.codigo)
          FROM recomendacion_regla rr JOIN regla g ON g.id = rr.regla_id
         WHERE rr.recomendacion_id = r.id) AS reglas,
       c.titulo  AS cancion_sugerida,
       d.accion,
       cf.titulo AS cancion_final,
       d.motivo,
       d.decidida_en
FROM decision_dj d
JOIN recomendacion r ON r.id = d.recomendacion_id
JOIN evento e        ON e.id = r.evento_id
LEFT JOIN cancion c  ON c.id = r.cancion_id
LEFT JOIN cancion cf ON cf.id = d.cancion_final_id;

-- =====================================================================
-- 5. CARGA DE LA BASE DE CONOCIMIENTO
-- =====================================================================
"""

sal = [DDL]
sal.append("INSERT INTO variable (codigo, descripcion) VALUES\n" + ",\n".join(
    f"    ({q(v)}, {q(i['descripcion'])})" for v, i in k["variables"].items()) + ";\n")
filas = [f"    ({q(v)}, {q(c)}, {q(e)})" for v, i in k["variables"].items() for c, e in i["valores"].items()]
sal.append("INSERT INTO valor_variable (variable_id, codigo, etiqueta)\nSELECT v.id, x.codigo, x.etiqueta\n"
           "FROM (VALUES\n" + ",\n".join(filas) + "\n) AS x(var, codigo, etiqueta)\nJOIN variable v ON v.codigo = x.var;\n")
sal.append("INSERT INTO regla (id, codigo, nombre, conclusion, accion, descripcion) VALUES\n" + ",\n".join(
    f"    ({n}, {q(r['codigo'])}, {q(r['nombre'])},\n     {q(r['conclusion'])}, {q(r['accion'])},\n     {q(r['descripcion'])})"
    for n, r in enumerate(k["reglas"], 1)) + ";\n")
cond = [f"    ({n}, {q(var)}, {q(val)})" for n, r in enumerate(k["reglas"], 1)
        for var, vals in r["condiciones"].items() for val in vals]
sal.append("-- Antecedentes: valores de una misma variable con O; variables distintas con Y.\n"
           "INSERT INTO condicion_regla (regla_id, variable_id, valor_id)\nSELECT c.regla_id, v.id, vv.id\nFROM (VALUES\n"
           + ",\n".join(cond) + "\n) AS c(regla_id, var, val)\nJOIN variable v        ON v.codigo = c.var\n"
           "JOIN valor_variable vv ON vv.variable_id = v.id AND vv.codigo = c.val;\n")
sal.append("INSERT INTO parametro_experto (clave, valor, unidad, descripcion) VALUES\n" + ",\n".join(
    f"    ({q(c)}, {p['valor']}, {q(p['unidad'])}, {q(p['descripcion'])})" for c, p in k["parametros"].items()) + ";\n")
sal.append("INSERT INTO tecnica_transicion (codigo, nombre, descripcion) VALUES\n" + ",\n".join(
    f"    ({q(c)}, {q(t['nombre'])}, {q(t['descripcion'])})" for c, t in k["tecnicas"].items()) + ";\n")
sal.append("INSERT INTO transicion_regla (caso, tecnica_id, prioridad)\nSELECT c.caso, t.id, c.prioridad\nFROM (VALUES\n"
           + ",\n".join(f"    ({q(t['caso'])}, {q(t['tecnica'])}, {t['prioridad']})" for t in k["transicion_reglas"])
           + "\n) AS c(caso, tecnica, prioridad)\nJOIN tecnica_transicion t ON t.codigo = c.tecnica;\n")
sal.append("-- Catálogo inicial de géneros, enlazado al dominio de genero_actual\n"
           "INSERT INTO genero_musical (nombre, valor_regla_id)\nSELECT x.nombre, vv.id\nFROM (VALUES\n"
           + ",\n".join(f"    ({q(n)}, {q(c)})" for n, c in k["generos"].items())
           + "\n) AS x(nombre, codigo)\nJOIN variable v        ON v.codigo = 'genero_actual'\n"
           "JOIN valor_variable vv ON vv.variable_id = v.id AND vv.codigo = x.codigo;\n")
sal.append("""-- =====================================================================
-- 6. PERMISOS SUGERIDOS (opcional)
-- =====================================================================
-- CREATE ROLE dj_app LOGIN PASSWORD 'cambiar_esta_clave';
-- GRANT USAGE ON SCHEMA sistema_dj TO dj_app;
-- GRANT SELECT ON ALL TABLES IN SCHEMA sistema_dj TO dj_app;
-- GRANT INSERT ON usuario, contexto_evento, recomendacion, recomendacion_regla,
--       recomendacion_transicion, decision_dj TO dj_app;
-- GRANT INSERT, UPDATE, DELETE ON cancion TO dj_app;
-- GRANT INSERT, UPDATE ON evento TO dj_app;
""")
(Path(__file__).with_name("sistema_experto_dj.sql")).write_text("\n".join(sal), encoding="utf-8")
