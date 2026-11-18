"""API Flask del sistema experto DJ.

Cada petición abre una conexión a PostgreSQL (DATABASE_URL), ejecuta un proceso de
ServicioSesion y la cierra. El DJ inicia sesión con correo y contraseña; la sesión viaja en
una cookie firmada y todas las rutas de datos exigen sesión y trabajan solo con lo del DJ.

    POST /api/registro                          crear cuenta (y, si se pide, los casos de ejemplo)
    POST /api/login · POST /api/logout          iniciar y cerrar sesión
    GET  /api/sesion                            usuario de la sesión actual
    GET  /api/opciones                          variables, géneros, formatos, parámetros y flujo
    GET  /api/canciones · POST /api/canciones   catálogo (CU01)
    DEL  /api/canciones/<id>                    quitar canción sin historial
    GET  /api/eventos · POST /api/eventos       eventos del DJ (CU02)
    POST /api/eventos/<id>/consultas            contexto + recomendaciones (CU02, CU03)
    POST /api/eventos/<id>/finalizar            cerrar el evento
    GET  /api/eventos/<id>/historial            decisiones del evento (CU05)
    GET  /api/consultas                         historial de consultas del DJ
    GET  /api/consultas/<id>                    resultado completo de una consulta
    GET  /api/recomendaciones/<id>              explicación desde el historial (CU04)
    POST /api/recomendaciones/<id>/decision     aceptar, rechazar o modificar (CU05)
    POST /api/ejemplos                          cargar los cinco casos de ejemplo
    GET  /api/salud                             estado del servicio y de la base (RNF04)
"""
import os
import secrets
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

from datos import ConexionBD, ConocimientoDAO, ErrorIntegridad, cargar_env
from negocio import ErrorConflicto, ErrorCredenciales, ErrorNoEncontrado, ServicioSesion

cargar_env()


def clave_de_sesion():
    """Clave que firma la cookie de sesión: SECRET_KEY o, en local, un archivo generado una vez."""
    clave = os.getenv("SECRET_KEY", "").strip()
    if clave:
        return clave
    archivo = Path(__file__).with_name(".clave_sesion")
    try:
        if not archivo.is_file():
            archivo.write_text(secrets.token_hex(32), encoding="utf-8")
        return archivo.read_text(encoding="utf-8").strip()
    except OSError:
        return secrets.token_hex(32)   # disco de solo lectura: las sesiones duran lo que el proceso


app = Flask(__name__)
app.config.update(
    SECRET_KEY=clave_de_sesion(),
    MAX_CONTENT_LENGTH=512 * 1024,                 # límite de seguridad para cualquier petición
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SEGURA", "").strip() == "1",   # póngalo en 1 al servir por HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
FORMATOS = ["MP3", "WAV", "FLAC"]


@contextmanager
def servicio():
    """Abre la base, entrega el servicio de sesión y cierra la conexión al terminar."""
    conexion = ConexionBD(app.config.get("DATABASE_URL"), app.config.get("DJ_SCHEMA"))
    try:
        yield ServicioSesion(conexion)
    finally:
        conexion.cerrar()


def cuerpo():
    """Cuerpo JSON de la petición; debe ser un objeto."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ValueError("Envía un objeto JSON.")
    return datos


def con_sesion(vista):
    """Exige sesión iniciada y pasa el id del usuario como primer argumento."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario_id = session.get("usuario_id")
        if usuario_id is None:
            return jsonify({"error": "Inicia sesión para continuar."}), 401
        return vista(usuario_id, *args, **kwargs)
    return envoltura


def abrir_sesion(usuario):
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario["id"]


@app.errorhandler(ValueError)
def error_validacion(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(ErrorCredenciales)
def error_credenciales(error):
    return jsonify({"error": str(error)}), 401


@app.errorhandler(ErrorNoEncontrado)
def error_no_encontrado(error):
    return jsonify({"error": str(error)}), 404


@app.errorhandler(ErrorConflicto)
def error_conflicto(error):
    return jsonify({"error": str(error)}), 409


@app.errorhandler(ErrorIntegridad)
def error_integridad(_error):
    return jsonify({"error": "La base de datos rechazó la operación por una restricción de integridad."}), 409


@app.errorhandler(413)
def error_tamano(_error):
    return jsonify({"error": "La petición es demasiado grande."}), 413


@app.get("/")
def inicio():
    return render_template("index.html")


# ---------------------------------------------------------------- cuenta
@app.post("/api/registro")
def registro():
    d = cuerpo()
    with servicio() as s:
        with s.conexion.transaccion():          # la cuenta y sus ejemplos se crean juntos o no se crean
            usuario = s.registrar_usuario(d.get("nombre"), d.get("correo"), d.get("clave"))
            if d.get("ejemplos"):
                s.cargar_ejemplos(usuario["id"])
        abrir_sesion(usuario)
        return jsonify(usuario), 201


@app.post("/api/login")
def login():
    d = cuerpo()
    with servicio() as s:
        usuario = s.autenticar(d.get("correo"), d.get("clave"))
        abrir_sesion(usuario)
        return jsonify(usuario)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"sesion": False})


@app.get("/api/sesion")
def sesion_actual():
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return jsonify({"usuario": None})
    with servicio() as s:
        usuario = s.usuario(usuario_id)
        if usuario is None:
            session.clear()
        return jsonify({"usuario": usuario})


# ---------------------------------------------------------------- conocimiento
@app.get("/api/opciones")
def opciones():
    """Opciones de cada pregunta y, para el flujo guiado, las reacciones que tienen regla por género."""
    with servicio() as s:
        bc = s.conocimiento
        por_genero, generales = {}, set()
        for regla in bc.reglas():
            reacciones = regla["condiciones"].get("reaccion_publico", [])
            generos = regla["condiciones"].get("genero_actual")
            if generos:
                for g in generos:
                    por_genero.setdefault(g, [])
                    por_genero[g] += [r for r in reacciones if r not in por_genero[g]]
            else:
                generales.update(reacciones)
        return jsonify({
            "variables": [{"id": v, "nombre": info["descripcion"], "valores": info["valores"]}
                          for v, info in bc.variables().items()],
            "generos": bc.generos(),
            "formatos": FORMATOS,
            "parametros": bc.parametros(),
            "reacciones_por_genero": por_genero,
            "reacciones_generales": sorted(generales),
        })


# ---------------------------------------------------------------- catálogo
@app.get("/api/canciones")
@con_sesion
def listar_canciones(usuario_id):
    with servicio() as s:
        return jsonify(s.catalogo(usuario_id))


@app.post("/api/canciones")
@con_sesion
def registrar_cancion(usuario_id):
    datos = cuerpo()
    with servicio() as s:
        return jsonify(s.registrar_cancion(usuario_id, datos)), 201


@app.delete("/api/canciones/<int:cancion_id>")
@con_sesion
def eliminar_cancion(usuario_id, cancion_id):
    with servicio() as s:
        s.eliminar_cancion(usuario_id, cancion_id)
        return jsonify({"eliminada": cancion_id})


# ---------------------------------------------------------------- eventos y consultas
@app.get("/api/eventos")
@con_sesion
def listar_eventos(usuario_id):
    with servicio() as s:
        return jsonify(s.eventos_de(usuario_id))


@app.post("/api/eventos")
@con_sesion
def crear_evento(usuario_id):
    d = cuerpo()
    with servicio() as s:
        return jsonify(s.crear_evento(usuario_id, d.get("nombre"), d.get("tipo_evento"), d.get("duracion_min", 240),
                                      d.get("inicio_previsto"), d.get("lugar"), d.get("aforo_estimado"))), 201


@app.post("/api/eventos/<int:evento_id>/consultas")
@con_sesion
def consultar(usuario_id, evento_id):
    d = cuerpo()
    with servicio() as s:
        return jsonify(s.recomendar(usuario_id, evento_id, d.get("contexto", {}), d.get("cancion_actual_id"), d.get("aclaraciones", {}))), 201


@app.post("/api/eventos/<int:evento_id>/finalizar")
@con_sesion
def finalizar_evento(usuario_id, evento_id):
    with servicio() as s:
        return jsonify(s.finalizar_evento(usuario_id, evento_id))


@app.get("/api/eventos/<int:evento_id>/historial")
@con_sesion
def historial(usuario_id, evento_id):
    with servicio() as s:
        return jsonify(s.historial(usuario_id, evento_id))


@app.get("/api/consultas")
@con_sesion
def listar_consultas(usuario_id):
    with servicio() as s:
        return jsonify(s.consultas(usuario_id))


@app.get("/api/consultas/<int:contexto_id>")
@con_sesion
def ver_consulta(usuario_id, contexto_id):
    with servicio() as s:
        return jsonify(s.consulta(usuario_id, contexto_id))


@app.get("/api/recomendaciones/<int:recomendacion_id>")
@con_sesion
def explicacion(usuario_id, recomendacion_id):
    with servicio() as s:
        return jsonify(s.explicacion(usuario_id, recomendacion_id))


@app.post("/api/recomendaciones/<int:recomendacion_id>/decision")
@con_sesion
def decidir(usuario_id, recomendacion_id):
    d = cuerpo()
    with servicio() as s:
        return jsonify(s.decidir(usuario_id, recomendacion_id, d.get("accion"), d.get("cancion_final_id"),
                                 d.get("motivo"))), 201


@app.post("/api/ejemplos")
@con_sesion
def cargar_ejemplos(usuario_id):
    with servicio() as s:
        return jsonify(s.cargar_ejemplos(usuario_id)), 201


@app.get("/api/salud")
def salud():
    """Comprueba que la base responde y que el conocimiento está cargado."""
    try:
        conexion = ConexionBD(app.config.get("DATABASE_URL"), app.config.get("DJ_SCHEMA"))
        try:
            reglas = len(ConocimientoDAO(conexion).reglas())
        finally:
            conexion.cerrar()
    except Exception:  # el servicio informa la avería en vez de caerse (sin exponer la URL ni la clave)
        return jsonify({"estado": "error", "detalle": "No se pudo conectar con la base de datos."}), 503
    return jsonify({"estado": "ok", "motor": "MotorDJ · reglas del documento", "base": "PostgreSQL",
                    "reglas_activas": reglas})


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "").strip() == "1")
