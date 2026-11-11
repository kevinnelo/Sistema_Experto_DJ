-- =====================================================================
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

INSERT INTO variable (codigo, descripcion) VALUES
    ('tipo_evento', 'Tipo de evento o fiesta contratada'),
    ('momento', 'Momento de la fiesta'),
    ('grupo_edad', 'Edad predominante del público'),
    ('genero_actual', 'Género musical que suena o se solicita'),
    ('reaccion_publico', 'Reacción observada en el público');

INSERT INTO valor_variable (variable_id, codigo, etiqueta)
SELECT v.id, x.codigo, x.etiqueta
FROM (VALUES
    ('tipo_evento', 'cumpleanos', 'Cumpleaños'),
    ('tipo_evento', 'boda', 'Boda'),
    ('tipo_evento', 'empresarial', 'Fiesta empresarial'),
    ('tipo_evento', 'tematica', 'Fiesta temática'),
    ('tipo_evento', 'discoteca', 'Discoteca'),
    ('tipo_evento', 'reunion_familiar', 'Reunión familiar'),
    ('momento', 'llegada', 'Llegada de los invitados'),
    ('momento', 'inicio', 'Inicio de la fiesta'),
    ('momento', 'desarrollo', 'Desarrollo de la fiesta'),
    ('momento', 'momento_principal', 'Momento principal'),
    ('momento', 'cierre', 'Cierre de la fiesta'),
    ('grupo_edad', 'ninos', 'Niños'),
    ('grupo_edad', 'adolescentes', 'Adolescentes'),
    ('grupo_edad', 'jovenes', 'Jóvenes'),
    ('grupo_edad', 'adultos', 'Adultos'),
    ('grupo_edad', 'adultos_mayores', 'Adultos mayores'),
    ('grupo_edad', 'variadas', 'Edades variadas'),
    ('genero_actual', 'infantil', 'Infantil'),
    ('genero_actual', 'pop', 'Pop'),
    ('genero_actual', 'urbano', 'Música urbana'),
    ('genero_actual', 'salsa', 'Salsa'),
    ('genero_actual', 'merengue', 'Merengue'),
    ('genero_actual', 'electronica', 'Electrónica'),
    ('genero_actual', 'rock', 'Rock'),
    ('genero_actual', 'popular', 'Música popular'),
    ('genero_actual', 'vallenato', 'Vallenato'),
    ('reaccion_publico', 'positiva', 'Reacción positiva'),
    ('reaccion_publico', 'negativa', 'Reacción negativa'),
    ('reaccion_publico', 'baila_y_canta', 'Baila y canta'),
    ('reaccion_publico', 'baila_poco', 'Baila poco'),
    ('reaccion_publico', 'sentado', 'Permanece sentado'),
    ('reaccion_publico', 'rie_y_canta', 'Ríe y canta'),
    ('reaccion_publico', 'solicita_otro_genero', 'Solicita otro género'),
    ('reaccion_publico', 'sin_reaccion', 'Sin reacción'),
    ('reaccion_publico', 'se_retira', 'Se está retirando')
) AS x(var, codigo, etiqueta)
JOIN variable v ON v.codigo = x.var;

INSERT INTO regla (id, codigo, nombre, conclusion, accion, descripcion) VALUES
    (1, 'R01', 'Cumpleaños',
     'Recomendar canciones festivas y alegres apropiadas para cumpleaños', 'CRITERIO',
     'SI el tipo de fiesta es un cumpleaños, ENTONCES recomendar música festiva y reconocida, considerando los gustos de la persona homenajeada.'),
    (2, 'R02', 'Boda',
     'Recomendar música romántica, alegre y elegante para bodas', 'CRITERIO',
     'SI el tipo de fiesta es una boda, ENTONCES recomendar música apropiada para cada momento de la celebración, respetando las preferencias de la pareja.'),
    (3, 'R03', 'Fiesta empresarial',
     'Recomendar música moderna y moderada para empresas', 'CRITERIO',
     'SI el tipo de fiesta es empresarial, ENTONCES recomendar música adecuada para el ambiente laboral y social, considerando las indicaciones del evento.'),
    (4, 'R04', 'Fiesta temática',
     'Recomendar música acorde con la temática elegida', 'CRITERIO',
     'SI el tipo de fiesta es temática, ENTONCES recomendar música relacionada con la temática acordada.'),
    (5, 'R05', 'Discoteca',
     'Recomendar música bailable y de alta energía', 'CRITERIO',
     'SI el evento se realiza en una discoteca, ENTONCES recomendar repertorio orientado al baile, considerando el estilo del lugar y los gustos del público.'),
    (6, 'R06', 'Reunión familiar',
     'Recomendar música familiar y canciones para todas las edades', 'CRITERIO',
     'SI el tipo de evento es una reunión familiar, ENTONCES recomendar música variada y compartida entre los asistentes, favoreciendo la participación de diferentes grupos.'),
    (7, 'R07', 'Llegada de invitados',
     'Recomendar música suave de fondo y de bienvenida', 'CRITERIO',
     'SI los invitados están llegando, ENTONCES recomendar música agradable y de energía moderada que facilite la bienvenida y la conversación.'),
    (8, 'R08', 'Inicio de la fiesta',
     'Recomendar música animada para romper el hielo', 'CRITERIO',
     'SI la fiesta está comenzando, ENTONCES recomendar música animada con un aumento gradual de energía, invitando a participar sin forzar el baile.'),
    (9, 'R09', 'Desarrollo de la fiesta',
     'Recomendar música bailable manteniendo un ritmo constante', 'CRITERIO',
     'SI la fiesta está en desarrollo, ENTONCES recomendar música con una energía acorde con la actividad y la participación del público, manteniendo continuidad y permitiendo pausas.'),
    (10, 'R10', 'Momento principal',
     'Recomendar música de máxima energía y canciones reconocidas o en tendencia', 'SUBIR_ENERGIA',
     'SI la fiesta está en su momento principal, ENTONCES recomendar música más animada cuando corresponda a la actividad prevista, destacando el momento de celebración.'),
    (11, 'R11', 'Cierre de la fiesta',
     'Recomendar música relajante o canciones de despedida', 'BAJAR_ENERGIA',
     'SI la fiesta está llegando a su cierre, ENTONCES recomendar canciones de despedida con una disminución gradual de energía.'),
    (12, 'R12', 'Público infantil',
     'Recomendar música infantil y canciones muy alegres', 'CRITERIO',
     'SI predominan niños, ENTONCES recomendar canciones apropiadas para su edad, gustos y actividad, comprobando el contenido y las preferencias.'),
    (13, 'R13', 'Público adolescente',
     'Recomendar música juvenil actual o en tendencia', 'CRITERIO',
     'SI predominan adolescentes, ENTONCES recomendar canciones reconocidas por ese público y apropiadas para el evento, considerando sus solicitudes y gustos.'),
    (14, 'R14', 'Público joven',
     'Recomendar música urbana, electrónica comercial o canciones populares', 'CRITERIO',
     'SI predominan jóvenes, ENTONCES recomendar repertorio familiar para el grupo, actual o de otras épocas, confirmando sus preferencias sin presuponer un género.'),
    (15, 'R15', 'Público adulto',
     'Recomendar música de los ochenta y noventa y pop', 'CRITERIO',
     'SI predominan adultos, ENTONCES recomendar canciones reconocidas según sus gustos reales, combinando épocas si el público lo desea.'),
    (16, 'R16', 'Público adulto mayor',
     'Recomendar música tradicional y baladas clásicas', 'CRITERIO',
     'SI predominan adultos mayores, ENTONCES recomendar repertorio clásico o actual según sus preferencias, considerando sus gustos y comodidad.'),
    (17, 'R17', 'Edades variadas',
     'Recomendar música variada y éxitos generacionales', 'CRITERIO',
     'SI el público está compuesto por personas de edades variadas, ENTONCES recomendar repertorio diverso y canciones compartidas, alternando opciones para distintos grupos.'),
    (18, 'R18', 'Infantil con reacción positiva',
     'Mantener el género musical', 'MANTENER_GENERO',
     'SI el género actual es infantil y la reacción del público es positiva, ENTONCES recomendar una canción candidata de ese género, considerando el tipo de evento, el momento y las características del público, sin reproducirla todavía.'),
    (19, 'R19', 'Pop/urbano con baile y canto',
     'Mantener el nivel de energía', 'MANTENER_ENERGIA',
     'SI el género actual es pop o urbano y el público baila y canta, ENTONCES recomendar mantener el género y el nivel de energía mientras el contexto continúe igual, seleccionando una canción de continuidad.'),
    (20, 'R20', 'Salsa/merengue con poco baile',
     'Aumentar la energía musical', 'SUBIR_ENERGIA',
     'SI el género actual es salsa o merengue y el público baila poco, ENTONCES recomendar aumentar gradualmente la energía solo cuando la actividad esté orientada al baile y el público desee participar; en una etapa tranquila, mantener la energía apropiada.'),
    (21, 'R21', 'Electrónica/rock con público sentado',
     'Disminuir la energía o seleccionar canciones más comerciales', 'BAJAR_O_COMERCIAL',
     'SI el género actual es electrónica o rock y el público permanece sentado, ENTONCES considerar si conversa, come o descansa antes de cambiar; si desea bailar, recomendar una canción más conocida y consultar sus preferencias si hay dudas.'),
    (22, 'R22', 'Solicitud de otro género',
     'Cambiar el género musical', 'CAMBIAR_GENERO',
     'SI el género actual es popular o vallenato y el público solicita otro género, ENTONCES confirmar cuál desea escuchar y recomendar una canción de ese género si resulta apropiada; de lo contrario, acordar una alternativa.'),
    (23, 'R23', 'Infantil con risas y canto',
     'Recomendar una canción más conocida del mismo género', 'MISMO_GENERO',
     'SI el género actual es infantil y el público ríe y canta, ENTONCES recomendar una canción más conocida del mismo género.'),
    (24, 'R24', 'Pop/urbano con reacción negativa',
     'Consultar las preferencias musicales del público', 'CONSULTAR',
     'SI el género actual es pop o urbano y la reacción del público es negativa, ENTONCES consultar las preferencias musicales antes de modificar la selección.'),
    (25, 'R25', 'Salsa/merengue sin reacción',
     'Buscar y recomendar otra canción', 'BUSCAR_OTRA',
     'SI el género actual es salsa o merengue y el público no reacciona, ENTONCES consultar la causa antes de modificar la selección; si rechaza la canción, buscar otra, y si pide menos intensidad, disminuir la energía.'),
    (26, 'R26', 'Público se retira en el cierre',
     'Disminuir la energía con canciones de despedida', 'BAJAR_ENERGIA',
     'SI la fiesta está en su cierre y el público se está retirando, ENTONCES recomendar disminuir la energía y utilizar canciones de despedida.'),
    (27, 'R27', 'Público se retira antes del cierre',
     'Consultar el motivo de la salida antes de cambiar la música', 'CONSULTAR',
     'SI el evento continúa (llegada, inicio, desarrollo o momento principal) y el público se está retirando, ENTONCES consultar el motivo sin atribuir la salida automáticamente a la música.');

-- Antecedentes: valores de una misma variable con O; variables distintas con Y.
INSERT INTO condicion_regla (regla_id, variable_id, valor_id)
SELECT c.regla_id, v.id, vv.id
FROM (VALUES
    (1, 'tipo_evento', 'cumpleanos'),
    (2, 'tipo_evento', 'boda'),
    (3, 'tipo_evento', 'empresarial'),
    (4, 'tipo_evento', 'tematica'),
    (5, 'tipo_evento', 'discoteca'),
    (6, 'tipo_evento', 'reunion_familiar'),
    (7, 'momento', 'llegada'),
    (8, 'momento', 'inicio'),
    (9, 'momento', 'desarrollo'),
    (10, 'momento', 'momento_principal'),
    (11, 'momento', 'cierre'),
    (12, 'grupo_edad', 'ninos'),
    (13, 'grupo_edad', 'adolescentes'),
    (14, 'grupo_edad', 'jovenes'),
    (15, 'grupo_edad', 'adultos'),
    (16, 'grupo_edad', 'adultos_mayores'),
    (17, 'grupo_edad', 'variadas'),
    (18, 'genero_actual', 'infantil'),
    (18, 'reaccion_publico', 'positiva'),
    (19, 'genero_actual', 'pop'),
    (19, 'genero_actual', 'urbano'),
    (19, 'reaccion_publico', 'baila_y_canta'),
    (20, 'genero_actual', 'salsa'),
    (20, 'genero_actual', 'merengue'),
    (20, 'reaccion_publico', 'baila_poco'),
    (21, 'genero_actual', 'electronica'),
    (21, 'genero_actual', 'rock'),
    (21, 'reaccion_publico', 'sentado'),
    (22, 'genero_actual', 'popular'),
    (22, 'genero_actual', 'vallenato'),
    (22, 'reaccion_publico', 'solicita_otro_genero'),
    (23, 'genero_actual', 'infantil'),
    (23, 'reaccion_publico', 'rie_y_canta'),
    (24, 'genero_actual', 'pop'),
    (24, 'genero_actual', 'urbano'),
    (24, 'reaccion_publico', 'negativa'),
    (25, 'genero_actual', 'salsa'),
    (25, 'genero_actual', 'merengue'),
    (25, 'reaccion_publico', 'sin_reaccion'),
    (26, 'momento', 'cierre'),
    (26, 'reaccion_publico', 'se_retira'),
    (27, 'momento', 'llegada'),
    (27, 'momento', 'inicio'),
    (27, 'momento', 'desarrollo'),
    (27, 'momento', 'momento_principal'),
    (27, 'reaccion_publico', 'se_retira')
) AS c(regla_id, var, val)
JOIN variable v        ON v.codigo = c.var
JOIN valor_variable vv ON vv.variable_id = v.id AND vv.codigo = c.val;

INSERT INTO parametro_experto (clave, valor, unidad, descripcion) VALUES
    ('bpm_diferencia_tolerada', 10, 'BPM', 'Diferencia de BPM considerada aceptable entre canciones'),
    ('bpm_diferencia_mezcla_similar', 5, 'BPM', 'Diferencia máxima para tratar dos canciones como de BPM similares'),
    ('camelot_distancia_maxima', 3, 'posiciones', 'Distancia máxima en la rueda de Camelot para considerar tonalidades compatibles'),
    ('energia_diferencia_mismo_nivel', 1, 'puntos', 'Diferencia máxima de energía (escala 1-10) para considerar que dos canciones mantienen el mismo nivel');

INSERT INTO tecnica_transicion (codigo, nombre, descripcion) VALUES
    ('SYNC_BPM', 'Sincronización de BPM', 'Se aplica siempre para que la fiesta no se sienta detenida.'),
    ('CROSSFADE', 'Cross-fade out', 'Transición suave cuando las canciones tienen BPM similares.'),
    ('MEZCLA_SIMPLE', 'Mezcla sencilla', 'Mezcla tradicional cuando las canciones tienen BPM similares.'),
    ('ECHO_OUT', 'Echo out', 'Al cambiar de canción o para dar un efecto de impacto dentro de la misma canción.'),
    ('AJUSTE_TEMPO', 'Igualar BPM con ajuste de tempo', 'Cuando los BPM son muy diferentes, se iguala el tempo procurando que la mezcla no suene forzada.'),
    ('CORTE_DIRECTO', 'Corte directo', 'Al cambiar de género o para anunciar algo por micrófono.');

INSERT INTO transicion_regla (caso, tecnica_id, prioridad)
SELECT c.caso, t.id, c.prioridad
FROM (VALUES
    ('SIEMPRE', 'SYNC_BPM', 1),
    ('BPM_SIMILAR', 'CROSSFADE', 1),
    ('BPM_SIMILAR', 'MEZCLA_SIMPLE', 2),
    ('CAMBIO_CANCION', 'ECHO_OUT', 1),
    ('EFECTO_IMPACTO', 'ECHO_OUT', 1),
    ('BPM_TOLERABLE', 'AJUSTE_TEMPO', 1),
    ('BPM_TOLERABLE', 'CROSSFADE', 2),
    ('BPM_DISTINTO', 'AJUSTE_TEMPO', 1),
    ('CAMBIO_GENERO', 'CORTE_DIRECTO', 1),
    ('ANUNCIO_MICROFONO', 'CORTE_DIRECTO', 1)
) AS c(caso, tecnica, prioridad)
JOIN tecnica_transicion t ON t.codigo = c.tecnica;

-- Catálogo inicial de géneros, enlazado al dominio de genero_actual
INSERT INTO genero_musical (nombre, valor_regla_id)
SELECT x.nombre, vv.id
FROM (VALUES
    ('Infantil', 'infantil'),
    ('Pop', 'pop'),
    ('Urbano', 'urbano'),
    ('Salsa', 'salsa'),
    ('Merengue', 'merengue'),
    ('Electrónica', 'electronica'),
    ('Rock', 'rock'),
    ('Popular', 'popular'),
    ('Vallenato', 'vallenato')
) AS x(nombre, codigo)
JOIN variable v        ON v.codigo = 'genero_actual'
JOIN valor_variable vv ON vv.variable_id = v.id AND vv.codigo = x.codigo;

-- =====================================================================
-- 6. PERMISOS SUGERIDOS (opcional)
-- =====================================================================
-- CREATE ROLE dj_app LOGIN PASSWORD 'cambiar_esta_clave';
-- GRANT USAGE ON SCHEMA sistema_dj TO dj_app;
-- GRANT SELECT ON ALL TABLES IN SCHEMA sistema_dj TO dj_app;
-- GRANT INSERT ON usuario, contexto_evento, recomendacion, recomendacion_regla,
--       recomendacion_transicion, decision_dj TO dj_app;
-- GRANT INSERT, UPDATE, DELETE ON cancion TO dj_app;
-- GRANT INSERT, UPDATE ON evento TO dj_app;
