"""Genera docs/sql/sistema_experto_dj.sql (PostgreSQL 16): esquema.sql más los datos de reglas.json. Uso: python3 docs/sql/generar_postgresql.py"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
k = json.loads((RAIZ / "reglas.json").read_text(encoding="utf-8"))
q = lambda s: "'" + str(s).replace("'", "''") + "'"

CABECERA = r"""-- =====================================================================
-- Sistema experto para recomendación musical de DJ
-- SGBD: PostgreSQL 16 · Esquema: sistema_dj
-- Ejecución: psql -U postgres -f sistema_experto_dj.sql
--
-- Es el modelo que ejecuta la aplicación (esquema.sql). Cambios frente a la
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
-- [C14] usuario.clave_hash: inicio de sesión con contraseña (se guarda solo el hash).
-- [C15] resultado_consulta: resultado completo de cada consulta para el historial.
-- =====================================================================

"""

ESQUEMA = (RAIZ / "esquema.sql").read_text(encoding="utf-8")
ESQUEMA = ESQUEMA[ESQUEMA.index("-- =====================================================================\n-- 1. BASE"):]
DDL = (CABECERA + "DROP SCHEMA IF EXISTS sistema_dj CASCADE;\nCREATE SCHEMA sistema_dj;\nSET search_path TO sistema_dj;\n\n" + ESQUEMA
       + "\n-- =====================================================================\n-- 5. CARGA DE LA BASE DE CONOCIMIENTO\n-- =====================================================================\n")

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
