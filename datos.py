"""Capa de datos: PostgreSQL con la base de conocimiento y el sistema transaccional.

La conexión se toma de la variable de entorno DATABASE_URL (o del archivo .env), por ejemplo:

    DATABASE_URL=postgresql://dj_app:mi_clave@localhost:5432/sistema_dj

Cada clase DAO encapsula las consultas de una parte del modelo del documento:

    ConexionBD        abre la base, aplica esquema.sql y carga reglas.json la primera vez
    ConocimientoDAO   variables, valores, reglas, parámetros, géneros y técnicas (BC)
    UsuarioDAO        usuario (con el hash de la contraseña)
    CancionDAO        cancion (catálogo del DJ, RF01)
    EventoDAO         evento (RF02)
    ContextoDAO       contexto_evento y resultado_consulta (historial de consultas)
    RecomendacionDAO  recomendacion, recomendacion_regla y recomendacion_transicion (RF03, RF04)
    DecisionDAO       decision_dj y la vista v_historial_decisiones (RF05)

Los DAO no abren transacciones: las abre la capa de negocio con ConexionBD.transaccion(),
de modo que un proceso completo (por ejemplo contexto + recomendaciones) se confirma o se
deshace entero. Todas las consultas usan parámetros; nunca se concatena texto del usuario.

RepositorioConocimiento lee el conocimiento directamente de reglas.json, sin base de datos:
lo usan la consola (main.py) y las pruebas del motor.
"""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ARCHIVO_CONOCIMIENTO = "reglas.json"
ARCHIVO_ESQUEMA = "esquema.sql"
ESQUEMA_POR_DEFECTO = "sistema_dj"
VARIABLES_CONTEXTO = ("momento", "grupo_edad", "genero_actual", "reaccion_publico")
ErrorIntegridad = psycopg.errors.IntegrityError
_FECHA = "to_char({} AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"')"


def cargar_env(ruta=None):
    """Lee pares CLAVE=valor del archivo .env sin pisar variables ya definidas."""
    archivo = Path(ruta) if ruta else Path(__file__).with_name(".env")
    if not archivo.is_file():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def url_por_defecto():
    """URL de conexión configurada (DATABASE_URL)."""
    cargar_env()
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Falta DATABASE_URL. Cree el archivo .env a partir de .env.ejemplo, por ejemplo: "
                           "DATABASE_URL=postgresql://dj_app:mi_clave@localhost:5432/sistema_dj")
    return url


def leer_conocimiento():
    """Conocimiento del experto: reglas.json local o, si GCS_BUCKET está definido, Cloud Storage."""
    bucket = os.getenv("GCS_BUCKET", "").strip()
    if bucket:
        from google.cloud import storage  # identidad de servicio; sin claves en el código
        objeto = os.getenv("GCS_OBJECT", ARCHIVO_CONOCIMIENTO).strip()
        raw = storage.Client().bucket(bucket).blob(objeto).download_as_bytes(timeout=15)
        return json.loads(raw.decode("utf-8"))
    return json.loads(Path(__file__).with_name(ARCHIVO_CONOCIMIENTO).read_text(encoding="utf-8"))


class ConexionBD:
    """Conexión a PostgreSQL con el esquema aplicado y la base de conocimiento cargada."""

    def __init__(self, url=None, esquema=None):
        self.url = url or url_por_defecto()
        self.esquema = esquema or os.getenv("DJ_SCHEMA", "").strip() or ESQUEMA_POR_DEFECTO
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", self.esquema):
            raise ValueError("Nombre de esquema inválido.")
        # autocommit: las transacciones se abren solo de forma explícita con transaccion().
        self.db = psycopg.connect(self.url, autocommit=True, row_factory=dict_row, connect_timeout=5)
        try:
            self._preparar()
        except BaseException:
            self.db.close()
            raise

    def _preparar(self):
        with self.transaccion():
            # El bloqueo evita que dos procesos creen el esquema a la vez.
            self.db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("dj:" + self.esquema,))
            self.db.execute(f"CREATE SCHEMA IF NOT EXISTS {self.esquema}")
            self.db.execute(f"SET search_path TO {self.esquema}")
            existe = self.db.execute("SELECT to_regclass(%s) AS t", (self.esquema + ".regla",)).fetchone()["t"]
            if not existe:
                ddl = Path(__file__).with_name(ARCHIVO_ESQUEMA).read_text(encoding="utf-8")
                self.db.execute(ddl.replace(ESQUEMA_POR_DEFECTO + ".", self.esquema + "."))
                self._cargar(leer_conocimiento())

    @contextmanager
    def transaccion(self):
        """Ejecuta el bloque como una unidad: COMMIT si termina bien, ROLLBACK si falla."""
        with self.db.transaction():
            yield self.db

    def cerrar(self):
        """Cierra la conexión."""
        self.db.close()

    def _cargar(self, k):
        """Inserta el conocimiento de reglas.json. Se llama dentro de una transacción."""
        db = self.db
        for var, info in k["variables"].items():
            vid = db.execute("INSERT INTO variable (codigo, descripcion) VALUES (%s,%s) RETURNING id",
                             (var, info["descripcion"])).fetchone()["id"]
            for val, etiqueta in info["valores"].items():
                db.execute("INSERT INTO valor_variable (variable_id, codigo, etiqueta) VALUES (%s,%s,%s)",
                           (vid, val, etiqueta))
        for nombre, valor in k["generos"].items():
            db.execute("INSERT INTO genero_musical (nombre, valor_regla_id) "
                       "SELECT %s, vv.id FROM valor_variable vv JOIN variable v ON v.id=vv.variable_id "
                       "WHERE v.codigo='genero_actual' AND vv.codigo=%s", (nombre, valor))
        for clave, p in k["parametros"].items():
            db.execute("INSERT INTO parametro_experto (clave, valor, unidad, descripcion) VALUES (%s,%s,%s,%s)",
                       (clave, p["valor"], p["unidad"], p["descripcion"]))
        for codigo, t in k["tecnicas"].items():
            db.execute("INSERT INTO tecnica_transicion (codigo, nombre, descripcion) VALUES (%s,%s,%s)",
                       (codigo, t["nombre"], t["descripcion"]))
        for tr in k["transicion_reglas"]:
            db.execute("INSERT INTO transicion_regla (caso, tecnica_id, prioridad) "
                       "SELECT %s, id, %s FROM tecnica_transicion WHERE codigo=%s",
                       (tr["caso"], tr["prioridad"], tr["tecnica"]))
        dao = ConocimientoDAO(self)
        for i, r in enumerate(k["reglas"], start=1):
            dao.crear_regla(i, r["codigo"], r["nombre"], r["conclusion"], r["descripcion"],
                            r["accion"], r["condiciones"])


class _DAO:
    """Base de los DAO: comparten la conexión para participar en la misma transacción."""

    def __init__(self, conexion):
        self.db = conexion.db

    def _uno(self, sql, parametros=()):
        return self.db.execute(sql, parametros).fetchone()

    def _todos(self, sql, parametros=()):
        return self.db.execute(sql, parametros).fetchall()


class ConocimientoDAO(_DAO):
    """Base de conocimiento: lo que consulta el motor de inferencia."""

    def variables(self):
        resultado = {}
        for v in self._todos("SELECT id, codigo, descripcion FROM variable ORDER BY id"):
            valores = self._todos("SELECT codigo, etiqueta FROM valor_variable WHERE variable_id=%s ORDER BY id",
                                  (v["id"],))
            resultado[v["codigo"]] = {"descripcion": v["descripcion"], "valores": valores}
        return resultado

    def valores(self, variable):
        return [r["codigo"] for r in self._todos(
            "SELECT vv.codigo FROM valor_variable vv JOIN variable v ON v.id=vv.variable_id "
            "WHERE v.codigo=%s ORDER BY vv.id", (variable,))]

    def id_valor(self, variable, codigo):
        """Id del valor de una variable, o None si no se respondió."""
        if codigo in (None, ""):
            return None
        fila = self._uno("SELECT vv.id FROM valor_variable vv JOIN variable v ON v.id=vv.variable_id "
                         "WHERE v.codigo=%s AND vv.codigo=%s", (variable, codigo))
        if fila is None:
            raise ValueError(f"Valor inválido para {variable}.")
        return fila["id"]

    def reglas(self):
        """Reglas activas con sus condiciones agrupadas por variable."""
        condiciones = {}
        for c in self._todos("SELECT c.regla_id, v.codigo AS var, vv.codigo AS val FROM condicion_regla c "
                             "JOIN variable v ON v.id=c.variable_id JOIN valor_variable vv ON vv.id=c.valor_id "
                             "ORDER BY c.regla_id, vv.id"):
            condiciones.setdefault(c["regla_id"], {}).setdefault(c["var"], []).append(c["val"])
        return [{"codigo": r["codigo"], "nombre": r["nombre"], "conclusion": r["conclusion"],
                 "descripcion": r["descripcion"], "accion": r["accion"], "condiciones": condiciones.get(r["id"], {})}
                for r in self._todos("SELECT id, codigo, nombre, conclusion, descripcion, accion FROM regla "
                                     "WHERE activa ORDER BY id")]

    def crear_regla(self, id_, codigo, nombre, conclusion, descripcion, accion, condiciones):
        """Registra una regla y sus antecedentes ({variable: [valores]}) (CU06)."""
        self.db.execute("INSERT INTO regla (id, codigo, nombre, conclusion, descripcion, accion) "
                        "VALUES (%s,%s,%s,%s,%s,%s)", (id_, codigo, nombre, conclusion, descripcion, accion))
        for var, valores in condiciones.items():
            for val in valores:
                cur = self.db.execute(
                    "INSERT INTO condicion_regla (regla_id, variable_id, valor_id) "
                    "SELECT %s, v.id, vv.id FROM variable v JOIN valor_variable vv "
                    "ON vv.variable_id=v.id WHERE v.codigo=%s AND vv.codigo=%s", (id_, var, val))
                if cur.rowcount != 1:
                    raise ValueError(f"Regla {codigo}: el valor {val} no existe en la variable {var}.")

    def cambiar_estado_regla(self, codigo, activa):
        """Activa o desactiva una regla (CU06). Devuelve True si la regla existe."""
        return self.db.execute("UPDATE regla SET activa=%s WHERE codigo=%s", (bool(activa), codigo)).rowcount == 1

    def crear_genero(self, nombre, codigo, etiqueta=None):
        """Agrega un género al dominio de genero_actual y al catálogo de géneros (RNF03)."""
        valor_id = self._uno("INSERT INTO valor_variable (variable_id, codigo, etiqueta) "
                             "SELECT id, %s, %s FROM variable WHERE codigo='genero_actual' RETURNING id",
                             (codigo, etiqueta or nombre))["id"]
        self.db.execute("INSERT INTO genero_musical (nombre, valor_regla_id) VALUES (%s,%s)", (nombre, valor_id))

    def parametros(self):
        return {r["clave"]: r["valor"] for r in self._todos("SELECT clave, valor::float8 AS valor FROM parametro_experto")}

    def generos(self):
        """nombre del género -> código del valor de genero_actual."""
        return {r["nombre"]: r["codigo"] for r in self._todos(
            "SELECT g.nombre, vv.codigo FROM genero_musical g "
            "JOIN valor_variable vv ON vv.id=g.valor_regla_id ORDER BY g.id")}

    def transiciones(self, caso):
        """Técnicas del caso de transición, por prioridad. 'id' es el de transicion_regla."""
        return self._todos(
            "SELECT tr.id, t.codigo, t.nombre, tr.prioridad::int AS prioridad FROM transicion_regla tr "
            "JOIN tecnica_transicion t ON t.id=tr.tecnica_id WHERE tr.caso=%s ORDER BY tr.prioridad, t.codigo",
            (caso,))


class UsuarioDAO(_DAO):
    """Usuarios del sistema (DJ o administrador del conocimiento)."""

    _SELECT = f"SELECT id, nombre, correo, rol, {_FECHA.format('creado_en')} AS creado_en FROM usuario "

    def crear(self, nombre, correo, clave_hash, rol="DJ"):
        return self._uno("INSERT INTO usuario (nombre, correo, clave_hash, rol) VALUES (%s,%s,%s,%s) RETURNING id",
                         (nombre, correo, clave_hash, rol))["id"]

    def obtener(self, usuario_id):
        """Usuario sin el hash de la contraseña."""
        return self._uno(self._SELECT + "WHERE id=%s", (usuario_id,))

    def por_correo(self, correo):
        return self._uno(self._SELECT + "WHERE correo=%s", (correo,))

    def clave_hash(self, correo):
        """(id, hash) del usuario con ese correo, o None."""
        return self._uno("SELECT id, clave_hash FROM usuario WHERE correo=%s", (correo,))


class CancionDAO(_DAO):
    """Catálogo musical del DJ (RF01)."""

    _SELECT = ("SELECT c.id, c.usuario_id, c.titulo, c.artista, g.nombre AS genero, c.bpm::float8 AS bpm, "
               "c.tonalidad_camelot, c.energia::int AS energia, c.duracion_seg, c.formato, c.conocida, c.comercial, "
               "c.ruta_archivo, c.metadatos_id3 "
               "FROM cancion c JOIN genero_musical g ON g.id=c.genero_id ")

    def crear(self, usuario_id, c):
        """Inserta una canción ya validada por la capa de negocio."""
        meta = c.get("metadatos_id3")
        return self._uno(
            "INSERT INTO cancion (usuario_id, titulo, artista, genero_id, bpm, tonalidad_camelot, energia, "
            "duracion_seg, formato, conocida, comercial, ruta_archivo, metadatos_id3) "
            "SELECT %s,%s,%s, g.id, %s,%s,%s,%s,%s,%s,%s,%s,%s FROM genero_musical g WHERE g.nombre=%s RETURNING id",
            (usuario_id, c["titulo"], c["artista"], c["bpm"], c["tonalidad_camelot"], c["energia"],
             c["duracion_seg"], c["formato"], bool(c.get("conocida", False)), bool(c.get("comercial", False)),
             c.get("ruta_archivo"), Jsonb(meta) if meta is not None else None, c["genero"]))["id"]

    def listar(self, usuario_id):
        return self._todos(self._SELECT + "WHERE c.usuario_id=%s ORDER BY c.id", (usuario_id,))

    def obtener(self, cancion_id):
        return self._uno(self._SELECT + "WHERE c.id=%s", (cancion_id,))

    def eliminar(self, cancion_id, usuario_id):
        """Borra la canción. Falla (ErrorIntegridad) si aparece en el historial."""
        return self.db.execute("DELETE FROM cancion WHERE id=%s AND usuario_id=%s",
                               (cancion_id, usuario_id)).rowcount == 1


class EventoDAO(_DAO):
    """Eventos o fiestas del DJ (RF02)."""

    _SELECT = ("SELECT e.id, e.usuario_id, e.nombre, vv.codigo AS tipo_evento, e.lugar, e.aforo_estimado, "
               f"{_FECHA.format('e.inicio_previsto')} AS inicio_previsto, e.duracion_min, e.estado "
               "FROM evento e JOIN valor_variable vv ON vv.id=e.tipo_evento_id ")

    def crear(self, usuario_id, nombre, tipo_evento_id, inicio_previsto, duracion_min, lugar=None, aforo=None):
        return self._uno(
            "INSERT INTO evento (usuario_id, nombre, tipo_evento_id, lugar, aforo_estimado, inicio_previsto, "
            "duracion_min) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (usuario_id, nombre, tipo_evento_id, lugar, aforo, inicio_previsto, duracion_min))["id"]

    def obtener(self, evento_id):
        return self._uno(self._SELECT + "WHERE e.id=%s", (evento_id,))

    def listar(self, usuario_id):
        return self._todos(self._SELECT + "WHERE e.usuario_id=%s ORDER BY e.id DESC", (usuario_id,))

    def cambiar_estado(self, evento_id, estado):
        self.db.execute("UPDATE evento SET estado=%s WHERE id=%s", (estado, evento_id))


class ContextoDAO(_DAO):
    """Fotografías del contexto de un evento (RF02) y resultado de cada consulta (historial)."""

    _SELECT = (
        f"SELECT x.id, x.evento_id, {_FECHA.format('x.registrado_en')} AS registrado_en, x.cancion_actual_id, "
        "m.codigo AS momento, g.codigo AS grupo_edad, a.codigo AS genero_actual, r.codigo AS reaccion_publico "
        "FROM contexto_evento x "
        "LEFT JOIN valor_variable m ON m.id=x.momento_id "
        "LEFT JOIN valor_variable g ON g.id=x.grupo_edad_id "
        "LEFT JOIN valor_variable a ON a.id=x.genero_actual_id "
        "LEFT JOIN valor_variable r ON r.id=x.reaccion_publico_id ")

    def registrar(self, evento_id, ids_valores, cancion_actual_id=None):
        """Inserta una fotografía del contexto. ids_valores: {variable: id de valor_variable o None}."""
        return self._uno(
            "INSERT INTO contexto_evento (evento_id, momento_id, grupo_edad_id, genero_actual_id, "
            "reaccion_publico_id, cancion_actual_id) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (evento_id, *(ids_valores.get(v) for v in VARIABLES_CONTEXTO), cancion_actual_id))["id"]

    def obtener(self, contexto_id):
        """Contexto con los códigos de sus valores (los hechos que evaluó el motor)."""
        return self._uno(self._SELECT + "WHERE x.id=%s", (contexto_id,))

    def listar(self, evento_id):
        return self._todos(self._SELECT + "WHERE x.evento_id=%s ORDER BY x.id", (evento_id,))

    def guardar_resultado(self, contexto_id, resultado):
        """Guarda el resultado completo de la consulta, tal como lo vio el DJ."""
        self.db.execute("INSERT INTO resultado_consulta (contexto_id, resultado) VALUES (%s,%s)",
                        (contexto_id, Jsonb(resultado)))

    def resultado(self, contexto_id):
        fila = self._uno("SELECT resultado FROM resultado_consulta WHERE contexto_id=%s", (contexto_id,))
        return fila["resultado"] if fila else None

    def historial(self, usuario_id):
        """Consultas del DJ, de la más reciente a la más antigua, con un resumen de cada una."""
        return self._todos(
            f"SELECT x.id, x.evento_id, e.nombre AS evento, te.codigo AS tipo_evento, e.estado, "
            f"{_FECHA.format('x.registrado_en')} AS registrado_en, "
            "m.codigo AS momento, g.codigo AS grupo_edad, a.codigo AS genero_actual, r.codigo AS reaccion_publico, "
            "c.titulo AS cancion_actual, "
            "(SELECT string_agg(DISTINCT q.codigo, ', ' ORDER BY q.codigo) FROM recomendacion rec "
            "   JOIN recomendacion_regla rr ON rr.recomendacion_id=rec.id JOIN regla q ON q.id=rr.regla_id "
            "  WHERE rec.contexto_id=x.id) AS reglas, "
            "(SELECT count(*)::int FROM recomendacion rec WHERE rec.contexto_id=x.id) AS recomendaciones, "
            "(SELECT count(*)::int FROM recomendacion rec JOIN decision_dj d ON d.recomendacion_id=rec.id "
            "  WHERE rec.contexto_id=x.id) AS decisiones "
            "FROM contexto_evento x JOIN evento e ON e.id=x.evento_id "
            "JOIN valor_variable te ON te.id=e.tipo_evento_id "
            "LEFT JOIN valor_variable m ON m.id=x.momento_id "
            "LEFT JOIN valor_variable g ON g.id=x.grupo_edad_id "
            "LEFT JOIN valor_variable a ON a.id=x.genero_actual_id "
            "LEFT JOIN valor_variable r ON r.id=x.reaccion_publico_id "
            "LEFT JOIN cancion c ON c.id=x.cancion_actual_id "
            "WHERE e.usuario_id=%s ORDER BY x.id DESC", (usuario_id,))


class RecomendacionDAO(_DAO):
    """Recomendaciones generadas, con sus reglas y técnicas (RF03, RF04)."""

    def crear(self, evento_id, contexto_id, cancion_id, explicacion, tiempo_ms, codigos_regla, ids_transicion):
        """Inserta la recomendación con sus reglas y técnicas de transición."""
        rid = self._uno(
            "INSERT INTO recomendacion (evento_id, contexto_id, cancion_id, explicacion, tiempo_respuesta_ms) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id", (evento_id, contexto_id, cancion_id, explicacion, tiempo_ms))["id"]
        for codigo in codigos_regla:
            self.db.execute("INSERT INTO recomendacion_regla (recomendacion_id, regla_id) "
                            "SELECT %s, id FROM regla WHERE codigo=%s", (rid, codigo))
        for tid in ids_transicion:
            self.db.execute("INSERT INTO recomendacion_transicion (recomendacion_id, transicion_regla_id) "
                            "VALUES (%s,%s)", (rid, tid))
        return rid

    def obtener(self, recomendacion_id):
        """Recomendación con reglas, técnicas y decisión, leída del registro histórico (CU04)."""
        rec = self._uno(
            "SELECT r.id, r.evento_id, r.contexto_id, r.cancion_id, r.explicacion, r.tiempo_respuesta_ms, "
            f"{_FECHA.format('r.generada_en')} AS generada_en, "
            "c.titulo AS cancion_titulo, c.artista AS cancion_artista, e.usuario_id "
            "FROM recomendacion r JOIN evento e ON e.id=r.evento_id "
            "LEFT JOIN cancion c ON c.id=r.cancion_id WHERE r.id=%s", (recomendacion_id,))
        if rec is None:
            return None
        rec["reglas"] = self._todos(
            "SELECT g.codigo, g.nombre, g.conclusion, g.descripcion, g.accion FROM recomendacion_regla rr "
            "JOIN regla g ON g.id=rr.regla_id WHERE rr.recomendacion_id=%s ORDER BY g.codigo", (recomendacion_id,))
        rec["transiciones"] = self._todos(
            "SELECT tr.caso, t.codigo, t.nombre, tr.prioridad::int AS prioridad FROM recomendacion_transicion rt "
            "JOIN transicion_regla tr ON tr.id=rt.transicion_regla_id "
            "JOIN tecnica_transicion t ON t.id=tr.tecnica_id WHERE rt.recomendacion_id=%s "
            "ORDER BY tr.id", (recomendacion_id,))
        rec["decision"] = DecisionDAO.de(self, recomendacion_id)
        return rec

    def listar(self, evento_id):
        return [self.obtener(f["id"]) for f in self._todos(
            "SELECT id FROM recomendacion WHERE evento_id=%s ORDER BY id", (evento_id,))]


class DecisionDAO(_DAO):
    """Decisiones del DJ sobre las recomendaciones (RF05)."""

    @staticmethod
    def de(dao, recomendacion_id):
        """Decisión de una recomendación, o None si está pendiente."""
        return dao._uno(
            "SELECT d.accion, d.cancion_final_id, c.titulo AS cancion_final, d.motivo, "
            f"{_FECHA.format('d.decidida_en')} AS decidida_en FROM decision_dj d "
            "LEFT JOIN cancion c ON c.id=d.cancion_final_id WHERE d.recomendacion_id=%s", (recomendacion_id,))

    def registrar(self, recomendacion_id, accion, cancion_final_id=None, motivo=None):
        return self._uno(
            "INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id, motivo) VALUES (%s,%s,%s,%s) "
            "RETURNING id", (recomendacion_id, accion, cancion_final_id, motivo or None))["id"]

    def historial(self, evento_id):
        """Decisiones del evento en orden cronológico (vista v_historial_decisiones)."""
        return self._todos(
            "SELECT evento_id, evento, recomendacion_id, reglas, cancion_sugerida, accion, cancion_final, motivo, "
            f"{_FECHA.format('generada_en')} AS generada_en, {_FECHA.format('decidida_en')} AS decidida_en "
            "FROM v_historial_decisiones WHERE evento_id=%s ORDER BY decidida_en, recomendacion_id", (evento_id,))


class RepositorioConocimiento:
    """Base de conocimiento leída de reglas.json, sin base de datos (consola y pruebas del motor)."""

    def __init__(self, conocimiento=None):
        self.k = conocimiento or leer_conocimiento()

    def valores(self, variable):
        return list(self.k["variables"][variable]["valores"])

    def reglas(self):
        return [dict(r) for r in self.k["reglas"]]

    def parametros(self):
        return {clave: float(p["valor"]) for clave, p in self.k["parametros"].items()}

    def generos(self):
        return dict(self.k["generos"])

    def transiciones(self, caso):
        filas = [{"id": None, "codigo": t["tecnica"], "nombre": self.k["tecnicas"][t["tecnica"]]["nombre"],
                  "prioridad": t["prioridad"]} for t in self.k["transicion_reglas"] if t["caso"] == caso]
        return sorted(filas, key=lambda t: (t["prioridad"], t["codigo"]))

    def cerrar(self):
        """No hay conexión que cerrar; se conserva por compatibilidad."""
