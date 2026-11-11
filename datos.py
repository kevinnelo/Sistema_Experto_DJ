"""Capa de datos: una sola base SQLite con la base de conocimiento y el sistema transaccional.

Cada clase DAO encapsula las consultas de una parte del modelo del documento:

    ConexionBD        abre la base, aplica esquema.sql y carga reglas.json la primera vez
    ConocimientoDAO   variables, valores, reglas, parámetros, géneros y técnicas (BC)
    UsuarioDAO        usuario
    CancionDAO        cancion (catálogo del DJ, RF01)
    EventoDAO         evento (RF02)
    ContextoDAO       contexto_evento (una fotografía por actualización)
    RecomendacionDAO  recomendacion, recomendacion_regla y recomendacion_transicion (RF03, RF04)
    DecisionDAO       decision_dj y la vista v_historial_decisiones (RF05)

Los DAO no abren transacciones: las abre la capa de negocio con ConexionBD.transaccion(),
de modo que un proceso completo (por ejemplo contexto + recomendaciones) se confirma o se
deshace entero. Todas las consultas usan parámetros; nunca se concatena texto del usuario.

La ruta de la base se toma de la variable de entorno DJ_DB (por defecto sistema_dj.db).
El conocimiento se lee de reglas.json, o de Cloud Storage si GCS_BUCKET está definido.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ARCHIVO_CONOCIMIENTO = "reglas.json"
ARCHIVO_ESQUEMA = "esquema.sql"
VARIABLES_CONTEXTO = ("momento", "grupo_edad", "genero_actual", "reaccion_publico")
VERSION_ESQUEMA = 2  # 2: canción conocida/comercial, R26-R27, BPM_TOLERABLE


def ruta_por_defecto():
    """Ruta de la base de datos configurada para la aplicación."""
    return os.getenv("DJ_DB", "").strip() or str(Path(__file__).with_name("sistema_dj.db"))


class ConexionBD:
    """Conexión SQLite con el esquema aplicado y la base de conocimiento cargada."""

    def __init__(self, ruta=None):
        self.ruta = ruta or ruta_por_defecto()
        # isolation_level=None: las transacciones se abren solo de forma explícita.
        self.db = sqlite3.connect(self.ruta, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        if self.ruta != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")  # lecturas y escrituras concurrentes
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        existe = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='regla'").fetchone()
        if existe and version != VERSION_ESQUEMA:
            self.db.close()
            raise RuntimeError(f"La base {self.ruta} es de una versión anterior del esquema. "
                               "Renómbrela o bórrela para que se cree de nuevo.")
        self.db.executescript(Path(__file__).with_name(ARCHIVO_ESQUEMA).read_text(encoding="utf-8"))
        self.db.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
        with self.transaccion():  # el bloqueo evita que dos procesos carguen a la vez
            if not self.db.execute("SELECT COUNT(*) FROM regla").fetchone()[0]:
                self._cargar(self._leer_conocimiento())

    @contextmanager
    def transaccion(self):
        """Ejecuta el bloque como una unidad: COMMIT si termina bien, ROLLBACK si falla."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def cerrar(self):
        """Cierra la conexión."""
        self.db.close()

    @staticmethod
    def _leer_conocimiento():
        bucket = os.getenv("GCS_BUCKET", "").strip()
        if bucket:
            from google.cloud import storage  # identidad de servicio; sin claves en el código
            objeto = os.getenv("GCS_OBJECT", ARCHIVO_CONOCIMIENTO).strip()
            raw = storage.Client().bucket(bucket).blob(objeto).download_as_bytes(timeout=15)
            return json.loads(raw.decode("utf-8"))
        return json.loads(Path(__file__).with_name(ARCHIVO_CONOCIMIENTO).read_text(encoding="utf-8"))

    def _cargar(self, k):
        """Inserta el conocimiento de reglas.json. Se llama dentro de una transacción."""
        db = self.db
        for i, (var, info) in enumerate(k["variables"].items(), start=1):
            db.execute("INSERT INTO variable (id, codigo, descripcion) VALUES (?,?,?)",
                       (i, var, info["descripcion"]))
            for val, etiqueta in info["valores"].items():
                db.execute("INSERT INTO valor_variable (variable_id, codigo, etiqueta) VALUES (?,?,?)",
                           (i, val, etiqueta))
        for nombre, valor in k["generos"].items():
            db.execute("INSERT INTO genero_musical (nombre, valor_regla_id) "
                       "SELECT ?, vv.id FROM valor_variable vv JOIN variable v ON v.id=vv.variable_id "
                       "WHERE v.codigo='genero_actual' AND vv.codigo=?", (nombre, valor))
        for clave, p in k["parametros"].items():
            db.execute("INSERT INTO parametro_experto (clave, valor, unidad, descripcion) VALUES (?,?,?,?)",
                       (clave, p["valor"], p["unidad"], p["descripcion"]))
        for codigo, t in k["tecnicas"].items():
            db.execute("INSERT INTO tecnica_transicion (codigo, nombre, descripcion) VALUES (?,?,?)",
                       (codigo, t["nombre"], t["descripcion"]))
        for tr in k["transicion_reglas"]:
            db.execute("INSERT INTO transicion_regla (caso, tecnica_id, prioridad) "
                       "SELECT ?, id, ? FROM tecnica_transicion WHERE codigo=?",
                       (tr["caso"], tr["prioridad"], tr["tecnica"]))
        dao = ConocimientoDAO(self)
        for i, r in enumerate(k["reglas"], start=1):
            dao.crear_regla(i, r["codigo"], r["nombre"], r["conclusion"], r["descripcion"],
                            r["accion"], r["condiciones"])


class _DAO:
    """Base de los DAO: comparten la conexión para participar en la misma transacción."""

    def __init__(self, conexion):
        self.db = conexion.db


class ConocimientoDAO(_DAO):
    """Base de conocimiento: lo que consulta el motor de inferencia."""

    def variables(self):
        resultado = {}
        for v in self.db.execute("SELECT id, codigo, descripcion FROM variable ORDER BY id"):
            valores = [dict(r) for r in self.db.execute(
                "SELECT codigo, etiqueta FROM valor_variable WHERE variable_id=? ORDER BY id", (v["id"],))]
            resultado[v["codigo"]] = {"descripcion": v["descripcion"], "valores": valores}
        return resultado

    def valores(self, variable):
        return [r[0] for r in self.db.execute(
            "SELECT vv.codigo FROM valor_variable vv JOIN variable v ON v.id=vv.variable_id "
            "WHERE v.codigo=? ORDER BY vv.id", (variable,))]

    def id_valor(self, variable, codigo):
        """Id del valor de una variable, o None si no se respondió."""
        if codigo in (None, ""):
            return None
        fila = self.db.execute(
            "SELECT vv.id FROM valor_variable vv JOIN variable v ON v.id=vv.variable_id "
            "WHERE v.codigo=? AND vv.codigo=?", (variable, codigo)).fetchone()
        if fila is None:
            raise ValueError(f"Valor inválido para {variable}.")
        return fila[0]

    def reglas(self):
        """Reglas activas con sus condiciones agrupadas por variable."""
        reglas = []
        for r in self.db.execute("SELECT * FROM regla WHERE activa=1 ORDER BY id"):
            condiciones = {}
            for c in self.db.execute(
                    "SELECT v.codigo AS var, vv.codigo AS val FROM condicion_regla c "
                    "JOIN variable v ON v.id=c.variable_id JOIN valor_variable vv ON vv.id=c.valor_id "
                    "WHERE c.regla_id=? ORDER BY vv.id", (r["id"],)):
                condiciones.setdefault(c["var"], []).append(c["val"])
            reglas.append({"codigo": r["codigo"], "nombre": r["nombre"], "conclusion": r["conclusion"],
                           "descripcion": r["descripcion"], "accion": r["accion"], "condiciones": condiciones})
        return reglas

    def crear_regla(self, id_, codigo, nombre, conclusion, descripcion, accion, condiciones):
        """Registra una regla y sus antecedentes ({variable: [valores]}) (CU06)."""
        self.db.execute("INSERT INTO regla (id, codigo, nombre, conclusion, descripcion, accion) "
                        "VALUES (?,?,?,?,?,?)", (id_, codigo, nombre, conclusion, descripcion, accion))
        for var, valores in condiciones.items():
            for val in valores:
                cur = self.db.execute(
                    "INSERT INTO condicion_regla (regla_id, variable_id, valor_id) "
                    "SELECT ?, v.id, vv.id FROM variable v JOIN valor_variable vv "
                    "ON vv.variable_id=v.id WHERE v.codigo=? AND vv.codigo=?", (id_, var, val))
                if cur.rowcount != 1:
                    raise ValueError(f"Regla {codigo}: el valor {val} no existe en la variable {var}.")

    def cambiar_estado_regla(self, codigo, activa):
        """Activa o desactiva una regla (CU06). Devuelve True si la regla existe."""
        cur = self.db.execute("UPDATE regla SET activa=? WHERE codigo=?", (1 if activa else 0, codigo))
        return cur.rowcount == 1

    def crear_genero(self, nombre, codigo, etiqueta=None):
        """Agrega un género al dominio de genero_actual y al catálogo de géneros (RNF03)."""
        self.db.execute("INSERT INTO valor_variable (variable_id, codigo, etiqueta) "
                        "SELECT id, ?, ? FROM variable WHERE codigo='genero_actual'",
                        (codigo, etiqueta or nombre))
        self.db.execute("INSERT INTO genero_musical (nombre, valor_regla_id) VALUES (?, last_insert_rowid())",
                        (nombre,))

    def parametros(self):
        return {r["clave"]: r["valor"] for r in self.db.execute("SELECT clave, valor FROM parametro_experto")}

    def generos(self):
        """nombre del género -> código del valor de genero_actual."""
        return {r["nombre"]: r["codigo"] for r in self.db.execute(
            "SELECT g.nombre, vv.codigo FROM genero_musical g "
            "JOIN valor_variable vv ON vv.id=g.valor_regla_id ORDER BY g.id")}

    def transiciones(self, caso):
        """Técnicas del caso de transición, por prioridad. 'id' es el de transicion_regla."""
        return [dict(r) for r in self.db.execute(
            "SELECT tr.id, t.codigo, t.nombre, tr.prioridad FROM transicion_regla tr "
            "JOIN tecnica_transicion t ON t.id=tr.tecnica_id WHERE tr.caso=? ORDER BY tr.prioridad, t.codigo",
            (caso,))]


class UsuarioDAO(_DAO):
    """Usuarios del sistema (DJ o administrador del conocimiento)."""

    def crear(self, nombre, correo, rol="DJ"):
        return self.db.execute("INSERT INTO usuario (nombre, correo, rol) VALUES (?,?,?)",
                               (nombre, correo, rol)).lastrowid

    def obtener(self, usuario_id):
        fila = self.db.execute("SELECT * FROM usuario WHERE id=?", (usuario_id,)).fetchone()
        return dict(fila) if fila else None

    def por_correo(self, correo):
        fila = self.db.execute("SELECT * FROM usuario WHERE correo=?", (correo,)).fetchone()
        return dict(fila) if fila else None


class CancionDAO(_DAO):
    """Catálogo musical del DJ (RF01)."""

    _SELECT = ("SELECT c.id, c.usuario_id, c.titulo, c.artista, g.nombre AS genero, c.bpm, "
               "c.tonalidad_camelot, c.energia, c.duracion_seg, c.formato, c.conocida, c.comercial, "
               "c.ruta_archivo, c.metadatos_id3 "
               "FROM cancion c JOIN genero_musical g ON g.id=c.genero_id ")

    @staticmethod
    def _fila(fila):
        c = dict(fila)
        c["metadatos_id3"] = json.loads(c["metadatos_id3"]) if c["metadatos_id3"] else None
        c["conocida"], c["comercial"] = bool(c["conocida"]), bool(c["comercial"])
        return c

    def crear(self, usuario_id, c):
        """Inserta una canción ya validada por la capa de negocio."""
        meta = c.get("metadatos_id3")
        return self.db.execute(
            "INSERT INTO cancion (usuario_id, titulo, artista, genero_id, bpm, tonalidad_camelot, energia, "
            "duracion_seg, formato, conocida, comercial, ruta_archivo, metadatos_id3) "
            "SELECT ?,?,?, g.id, ?,?,?,?,?,?,?,?,? FROM genero_musical g WHERE g.nombre=?",
            (usuario_id, c["titulo"], c["artista"], c["bpm"], c["tonalidad_camelot"], c["energia"],
             c["duracion_seg"], c["formato"], int(c.get("conocida", False)), int(c.get("comercial", False)),
             c.get("ruta_archivo"),
             json.dumps(meta, ensure_ascii=False) if meta is not None else None, c["genero"])).lastrowid

    def listar(self, usuario_id):
        return [self._fila(f) for f in self.db.execute(
            self._SELECT + "WHERE c.usuario_id=? ORDER BY c.id", (usuario_id,))]

    def obtener(self, cancion_id):
        fila = self.db.execute(self._SELECT + "WHERE c.id=?", (cancion_id,)).fetchone()
        return self._fila(fila) if fila else None

    def eliminar(self, cancion_id, usuario_id):
        """Borra la canción. Falla (IntegrityError) si aparece en el historial."""
        cur = self.db.execute("DELETE FROM cancion WHERE id=? AND usuario_id=?", (cancion_id, usuario_id))
        return cur.rowcount == 1


class EventoDAO(_DAO):
    """Eventos o fiestas del DJ (RF02)."""

    _SELECT = ("SELECT e.id, e.usuario_id, e.nombre, vv.codigo AS tipo_evento, e.lugar, e.aforo_estimado, "
               "e.inicio_previsto, e.duracion_min, e.estado "
               "FROM evento e JOIN valor_variable vv ON vv.id=e.tipo_evento_id ")

    def crear(self, usuario_id, nombre, tipo_evento_id, inicio_previsto, duracion_min, lugar=None, aforo=None):
        return self.db.execute(
            "INSERT INTO evento (usuario_id, nombre, tipo_evento_id, lugar, aforo_estimado, inicio_previsto, "
            "duracion_min) VALUES (?,?,?,?,?,?,?)",
            (usuario_id, nombre, tipo_evento_id, lugar, aforo, inicio_previsto, duracion_min)).lastrowid

    def obtener(self, evento_id):
        fila = self.db.execute(self._SELECT + "WHERE e.id=?", (evento_id,)).fetchone()
        return dict(fila) if fila else None

    def listar(self, usuario_id):
        return [dict(f) for f in self.db.execute(
            self._SELECT + "WHERE e.usuario_id=? ORDER BY e.id DESC", (usuario_id,))]

    def cambiar_estado(self, evento_id, estado):
        self.db.execute("UPDATE evento SET estado=? WHERE id=?", (estado, evento_id))


class ContextoDAO(_DAO):
    """Fotografías del contexto de un evento (RF02)."""

    def registrar(self, evento_id, ids_valores, cancion_actual_id=None):
        """Inserta una fotografía del contexto. ids_valores: {variable: id de valor_variable o None}."""
        return self.db.execute(
            "INSERT INTO contexto_evento (evento_id, momento_id, grupo_edad_id, genero_actual_id, "
            "reaccion_publico_id, cancion_actual_id) VALUES (?,?,?,?,?,?)",
            (evento_id, *(ids_valores.get(v) for v in VARIABLES_CONTEXTO), cancion_actual_id)).lastrowid

    def obtener(self, contexto_id):
        """Contexto con los códigos de sus valores (los hechos que evaluó el motor)."""
        fila = self.db.execute(
            "SELECT x.id, x.evento_id, x.registrado_en, x.cancion_actual_id, "
            "m.codigo AS momento, g.codigo AS grupo_edad, a.codigo AS genero_actual, r.codigo AS reaccion_publico "
            "FROM contexto_evento x "
            "LEFT JOIN valor_variable m ON m.id=x.momento_id "
            "LEFT JOIN valor_variable g ON g.id=x.grupo_edad_id "
            "LEFT JOIN valor_variable a ON a.id=x.genero_actual_id "
            "LEFT JOIN valor_variable r ON r.id=x.reaccion_publico_id WHERE x.id=?", (contexto_id,)).fetchone()
        return dict(fila) if fila else None

    def listar(self, evento_id):
        return [self.obtener(f[0]) for f in self.db.execute(
            "SELECT id FROM contexto_evento WHERE evento_id=? ORDER BY id", (evento_id,)).fetchall()]


class RecomendacionDAO(_DAO):
    """Recomendaciones generadas, con sus reglas y técnicas (RF03, RF04)."""

    def crear(self, evento_id, contexto_id, cancion_id, explicacion, tiempo_ms, codigos_regla, ids_transicion):
        """Inserta la recomendación con sus reglas y técnicas de transición."""
        rid = self.db.execute(
            "INSERT INTO recomendacion (evento_id, contexto_id, cancion_id, explicacion, tiempo_respuesta_ms) "
            "VALUES (?,?,?,?,?)", (evento_id, contexto_id, cancion_id, explicacion, tiempo_ms)).lastrowid
        for codigo in codigos_regla:
            self.db.execute("INSERT INTO recomendacion_regla (recomendacion_id, regla_id) "
                            "SELECT ?, id FROM regla WHERE codigo=?", (rid, codigo))
        for tid in ids_transicion:
            self.db.execute("INSERT INTO recomendacion_transicion (recomendacion_id, transicion_regla_id) "
                            "VALUES (?,?)", (rid, tid))
        return rid

    def obtener(self, recomendacion_id):
        """Recomendación con reglas, técnicas y decisión, leída del registro histórico (CU04)."""
        fila = self.db.execute(
            "SELECT r.*, c.titulo AS cancion_titulo, c.artista AS cancion_artista, e.usuario_id "
            "FROM recomendacion r JOIN evento e ON e.id=r.evento_id "
            "LEFT JOIN cancion c ON c.id=r.cancion_id WHERE r.id=?", (recomendacion_id,)).fetchone()
        if fila is None:
            return None
        rec = dict(fila)
        rec["reglas"] = [dict(f) for f in self.db.execute(
            "SELECT g.codigo, g.nombre, g.conclusion, g.descripcion, g.accion FROM recomendacion_regla rr "
            "JOIN regla g ON g.id=rr.regla_id WHERE rr.recomendacion_id=? ORDER BY g.codigo", (recomendacion_id,))]
        rec["transiciones"] = [dict(f) for f in self.db.execute(
            "SELECT tr.caso, t.codigo, t.nombre, tr.prioridad FROM recomendacion_transicion rt "
            "JOIN transicion_regla tr ON tr.id=rt.transicion_regla_id "
            "JOIN tecnica_transicion t ON t.id=tr.tecnica_id WHERE rt.recomendacion_id=? "
            "ORDER BY tr.id", (recomendacion_id,))]
        decision = self.db.execute("SELECT accion, cancion_final_id, motivo, decidida_en FROM decision_dj "
                                   "WHERE recomendacion_id=?", (recomendacion_id,)).fetchone()
        rec["decision"] = dict(decision) if decision else None
        return rec

    def listar(self, evento_id):
        return [self.obtener(f[0]) for f in self.db.execute(
            "SELECT id FROM recomendacion WHERE evento_id=? ORDER BY id", (evento_id,)).fetchall()]


class DecisionDAO(_DAO):
    """Decisiones del DJ sobre las recomendaciones (RF05)."""

    def registrar(self, recomendacion_id, accion, cancion_final_id=None, motivo=None):
        return self.db.execute(
            "INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id, motivo) VALUES (?,?,?,?)",
            (recomendacion_id, accion, cancion_final_id, motivo or None)).lastrowid

    def historial(self, evento_id):
        """Decisiones del evento en orden cronológico (vista v_historial_decisiones)."""
        return [dict(f) for f in self.db.execute(
            "SELECT * FROM v_historial_decisiones WHERE evento_id=? ORDER BY decidida_en, recomendacion_id",
            (evento_id,))]


class RepositorioConocimiento(ConocimientoDAO):
    """Base de conocimiento en memoria, sin datos transaccionales (consola y simulaciones)."""

    def __init__(self, ruta=":memory:"):
        self.conexion = ConexionBD(ruta)
        super().__init__(self.conexion)

    def cerrar(self):
        self.conexion.cerrar()
