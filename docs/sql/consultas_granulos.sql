-- ===== atras =====
SET search_path TO sistema_dj;
WITH por_variable AS (
    SELECT c.regla_id, v.codigo AS var,
           string_agg(vv.codigo, ' O ' ORDER BY vv.codigo) AS valores
    FROM condicion_regla c
    JOIN variable v        ON v.id = c.variable_id
    JOIN valor_variable vv ON vv.id = c.valor_id
    GROUP BY c.regla_id, v.codigo)
SELECT r.codigo, r.conclusion,
       string_agg(p.var || ' = ' || p.valores, ' Y ' ORDER BY p.var) AS antecedentes
FROM regla r
JOIN por_variable p ON p.regla_id = r.id
GROUP BY r.id, r.codigo, r.conclusion
ORDER BY r.id;

-- ===== hipotesis =====
SET search_path TO sistema_dj;
WITH por_variable AS (
    SELECT c.regla_id, v.codigo AS var,
           string_agg(vv.codigo, ' O ' ORDER BY vv.codigo) AS valores
    FROM condicion_regla c
    JOIN variable v        ON v.id = c.variable_id
    JOIN valor_variable vv ON vv.id = c.valor_id
    GROUP BY c.regla_id, v.codigo)
SELECT r.codigo, r.nombre,
       string_agg(p.var || ' = ' || p.valores, ' Y ' ORDER BY p.var) AS antecedentes
FROM regla r
JOIN por_variable p ON p.regla_id = r.id
WHERE r.conclusion ILIKE '%mantener el nivel de energía%'   -- cambie el texto para otra hipótesis
GROUP BY r.codigo, r.nombre
ORDER BY r.codigo;

-- ===== adelante =====
SET search_path TO sistema_dj;
-- Cada escenario (id) es un conjunto de hechos. Agregue o cambie filas en VALUES.
WITH escenarios(id, var, val) AS (VALUES
    ('E1','tipo_evento','cumpleanos'),   ('E1','momento','inicio'),
    ('E1','grupo_edad','ninos'),         ('E1','genero_actual','infantil'),
    ('E1','reaccion_publico','rie_y_canta'),
    ('E2','tipo_evento','discoteca'),    ('E2','momento','desarrollo'),
    ('E2','grupo_edad','jovenes'),       ('E2','genero_actual','pop'),
    ('E2','reaccion_publico','baila_y_canta'),
    ('E3','tipo_evento','boda'),         ('E3','momento','cierre'),
    ('E3','grupo_edad','adultos'),       ('E3','genero_actual','salsa'),
    ('E3','reaccion_publico','baila_poco'),
    ('E4','tipo_evento','reunion_familiar'), ('E4','momento','llegada'),
    ('E4','grupo_edad','variadas'),      ('E4','genero_actual','popular'),
    ('E4','reaccion_publico','solicita_otro_genero'),
    ('E5','tipo_evento','empresarial'),  ('E5','momento','momento_principal'),
    ('E5','grupo_edad','adultos_mayores'), ('E5','genero_actual','electronica'),
    ('E5','reaccion_publico','sentado'),
    ('E6','tipo_evento','tematica'),     ('E6','momento','desarrollo'),
    ('E6','grupo_edad','adolescentes'),  ('E6','genero_actual','merengue'),
    ('E6','reaccion_publico','sin_reaccion'),
    ('E7','tipo_evento','boda'),         ('E7','momento','cierre'),
    ('E7','grupo_edad','variadas'),      ('E7','genero_actual','vallenato'),
    ('E7','reaccion_publico','se_retira'),
    ('E8','tipo_evento','discoteca'),    ('E8','momento','desarrollo'),
    ('E8','grupo_edad','jovenes'),       ('E8','genero_actual','electronica'),
    ('E8','reaccion_publico','se_retira')),
ant AS (
    SELECT r.id, r.codigo, v.codigo AS var, vv.codigo AS val
    FROM regla r
    JOIN condicion_regla c ON c.regla_id = r.id
    JOIN variable v        ON v.id = c.variable_id
    JOIN valor_variable vv ON vv.id = c.valor_id
    WHERE r.activa),
req AS (SELECT DISTINCT id, var FROM ant),
cub AS (
    SELECT DISTINCT e.id AS esc, a.id AS regla, a.var
    FROM ant a JOIN escenarios e ON e.var = a.var AND e.val = a.val),
disp AS (
    SELECT r.id AS regla, r.codigo, e.esc
    FROM regla r
    CROSS JOIN (SELECT DISTINCT id AS esc FROM escenarios) e
    WHERE r.activa AND NOT EXISTS (
        SELECT 1 FROM req q
        WHERE q.id = r.id
          AND NOT EXISTS (SELECT 1 FROM cub c
                          WHERE c.regla = q.id AND c.var = q.var AND c.esc = e.esc)))
SELECT e.esc AS escenario,
       string_agg(d.codigo, ', ' ORDER BY d.codigo) AS reglas_disparadas
FROM (SELECT DISTINCT id AS esc FROM escenarios) e
LEFT JOIN disp d ON d.esc = e.esc
GROUP BY e.esc
ORDER BY e.esc;

-- ===== conflictos =====
SET search_path TO sistema_dj;
-- Mismos escenarios y disparo que la consulta anterior, más el sentido de energía de cada regla.
WITH escenarios(id, var, val) AS (VALUES
    ('E1','tipo_evento','cumpleanos'),   ('E1','momento','inicio'),
    ('E1','grupo_edad','ninos'),         ('E1','genero_actual','infantil'),
    ('E1','reaccion_publico','rie_y_canta'),
    ('E2','tipo_evento','discoteca'),    ('E2','momento','desarrollo'),
    ('E2','grupo_edad','jovenes'),       ('E2','genero_actual','pop'),
    ('E2','reaccion_publico','baila_y_canta'),
    ('E3','tipo_evento','boda'),         ('E3','momento','cierre'),
    ('E3','grupo_edad','adultos'),       ('E3','genero_actual','salsa'),
    ('E3','reaccion_publico','baila_poco'),
    ('E4','tipo_evento','reunion_familiar'), ('E4','momento','llegada'),
    ('E4','grupo_edad','variadas'),      ('E4','genero_actual','popular'),
    ('E4','reaccion_publico','solicita_otro_genero'),
    ('E5','tipo_evento','empresarial'),  ('E5','momento','momento_principal'),
    ('E5','grupo_edad','adultos_mayores'), ('E5','genero_actual','electronica'),
    ('E5','reaccion_publico','sentado'),
    ('E6','tipo_evento','tematica'),     ('E6','momento','desarrollo'),
    ('E6','grupo_edad','adolescentes'),  ('E6','genero_actual','merengue'),
    ('E6','reaccion_publico','sin_reaccion'),
    ('E7','tipo_evento','boda'),         ('E7','momento','cierre'),
    ('E7','grupo_edad','variadas'),      ('E7','genero_actual','vallenato'),
    ('E7','reaccion_publico','se_retira'),
    ('E8','tipo_evento','discoteca'),    ('E8','momento','desarrollo'),
    ('E8','grupo_edad','jovenes'),       ('E8','genero_actual','electronica'),
    ('E8','reaccion_publico','se_retira')),
ant AS (
    SELECT r.id, r.codigo, v.codigo AS var, vv.codigo AS val
    FROM regla r
    JOIN condicion_regla c ON c.regla_id = r.id
    JOIN variable v        ON v.id = c.variable_id
    JOIN valor_variable vv ON vv.id = c.valor_id
    WHERE r.activa),
req AS (SELECT DISTINCT id, var FROM ant),
cub AS (
    SELECT DISTINCT e.id AS esc, a.id AS regla, a.var
    FROM ant a JOIN escenarios e ON e.var = a.var AND e.val = a.val),
disp AS (
    SELECT r.id AS regla, r.codigo, e.esc
    FROM regla r
    CROSS JOIN (SELECT DISTINCT id AS esc FROM escenarios) e
    WHERE r.activa AND NOT EXISTS (
        SELECT 1 FROM req q
        WHERE q.id = r.id
          AND NOT EXISTS (SELECT 1 FROM cub c
                          WHERE c.regla = q.id AND c.var = q.var AND c.esc = e.esc))),
dir AS (
    SELECT d.esc, r.codigo, r.conclusion,
           CASE WHEN r.accion = 'SUBIR_ENERGIA'                         THEN 'SUBE'
                WHEN r.accion IN ('BAJAR_ENERGIA', 'BAJAR_O_COMERCIAL') THEN 'BAJA' END AS sentido
    FROM disp d JOIN regla r ON r.id = d.regla)
SELECT a.esc AS escenario,
       a.codigo AS regla_a, a.conclusion AS conclusion_a,
       b.codigo AS regla_b, b.conclusion AS conclusion_b
FROM dir a
JOIN dir b ON a.esc = b.esc AND a.codigo < b.codigo
WHERE a.sentido IS NOT NULL AND b.sentido IS NOT NULL AND a.sentido <> b.sentido
ORDER BY 1, 2;

-- ===== sinregla =====
SET search_path TO sistema_dj;
-- Valores de cualquier variable que ninguna regla usa (vacío = sin huecos)
SELECT v.codigo AS variable, vv.codigo AS valor_sin_regla
FROM valor_variable vv
JOIN variable v ON v.id = vv.variable_id
WHERE NOT EXISTS (SELECT 1 FROM condicion_regla c WHERE c.valor_id = vv.id)
ORDER BY 1, 2;

-- ===== bpm =====
SET search_path TO sistema_dj;
-- Clasifica la transición entre pares de canciones usando los parámetros de la entrevista.
-- Reemplace los VALUES por canciones de su catálogo cuando lo tenga cargado.
WITH catalogo(titulo, bpm, camelot) AS (VALUES
    ('Tema A', 124.0, '8A'),
    ('Tema B', 120.0, '9A'),
    ('Tema C', 131.0, '2B'))
SELECT a.titulo AS cancion_actual,
       b.titulo AS cancion_siguiente,
       abs(a.bpm - b.bpm) AS dif_bpm,
       CASE
         WHEN abs(a.bpm - b.bpm) <= (SELECT valor FROM parametro_experto
                                     WHERE clave = 'bpm_diferencia_mezcla_similar') THEN 'BPM_SIMILAR'
         WHEN abs(a.bpm - b.bpm) <= (SELECT valor FROM parametro_experto
                                     WHERE clave = 'bpm_diferencia_tolerada')       THEN 'BPM_TOLERABLE'
         ELSE 'BPM_DISTINTO'
       END AS caso
FROM catalogo a
CROSS JOIN catalogo b
WHERE a.titulo < b.titulo
ORDER BY 1, 2;

-- ===== tecnicas =====
SET search_path TO sistema_dj;
-- Técnicas de transición aplicables a cada caso, en orden de prioridad
SELECT tr.caso, t.nombre AS tecnica, tr.prioridad
FROM transicion_regla tr
JOIN tecnica_transicion t ON t.id = tr.tecnica_id
ORDER BY tr.caso, tr.prioridad;

-- ===== camelot =====
SET search_path TO sistema_dj;
-- Distancia circular en la rueda de Camelot (solo número) frente al parámetro del experto
WITH tonos(camelot, n) AS (VALUES ('8A',8), ('9A',9), ('2B',2), ('11A',11))
SELECT a.camelot AS desde, b.camelot AS hacia,
       LEAST(abs(a.n - b.n), 12 - abs(a.n - b.n)) AS distancia,
       LEAST(abs(a.n - b.n), 12 - abs(a.n - b.n)) <=
         (SELECT valor FROM parametro_experto WHERE clave = 'camelot_distancia_maxima') AS compatible
FROM tonos a
CROSS JOIN tonos b
WHERE a.camelot <> b.camelot
ORDER BY 1, 2;

-- ===== energia =====
SET search_path TO sistema_dj;
-- R19: ¿qué canciones mantienen el nivel de energía de la que suena? (parámetro del experto)
WITH actual(titulo, energia) AS (VALUES ('Suena ahora', 6)),
     candidatas(titulo, energia) AS (VALUES ('Tema 1', 4), ('Tema 2', 5), ('Tema 3', 6), ('Tema 4', 7), ('Tema 5', 8))
SELECT c.titulo, c.energia, c.energia - a.energia AS diferencia,
       abs(c.energia - a.energia) <=
         (SELECT valor FROM parametro_experto WHERE clave = 'energia_diferencia_mismo_nivel') AS mismo_nivel
FROM candidatas c CROSS JOIN actual a
ORDER BY c.energia;

-- ===== param =====
SET search_path TO sistema_dj;
SELECT clave, valor, unidad, descripcion FROM parametro_experto ORDER BY clave;

-- ===== conocimiento =====
SET search_path TO sistema_dj;
SELECT r.codigo, r.nombre, r.conclusion, r.accion FROM regla r ORDER BY r.id;
