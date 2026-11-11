"""API Flask del sistema experto DJ.

Cada petición abre una conexión a la base (DJ_DB), ejecuta un proceso de ServicioSesion y
la cierra. La web y la consola usan el mismo MotorDJ.

    GET  /api/opciones                          variables, géneros, formatos y parámetros
    POST /api/usuarios                          registra o recupera al DJ por correo
    GET  /api/usuarios/<id>/canciones           catálogo (CU01)
    POST /api/usuarios/<id>/canciones           registrar canción (CU01)
    DEL  /api/usuarios/<id>/canciones/<id>      quitar canción sin historial
    GET  /api/usuarios/<id>/eventos             eventos del DJ
    POST /api/usuarios/<id>/eventos             registrar evento (CU02)
    POST /api/eventos/<id>/recomendar           contexto + recomendaciones (CU02, CU03)
    POST /api/eventos/<id>/finalizar            cerrar el evento
    GET  /api/eventos/<id>/historial            decisiones del evento (CU05)
    GET  /api/recomendaciones/<id>              explicación desde el historial (CU04)
    POST /api/recomendaciones/<id>/decision     aceptar, rechazar o modificar (CU05)
    POST /api/recomendar                        simulación sin guardar (catálogo en la petición)
    GET  /api/salud                             estado del servicio y de la base (RNF04)

Nota: no hay autenticación; el documento no la define. El DJ se identifica por su correo.
"""
import sqlite3
from contextlib import contextmanager

from flask import Flask, jsonify, render_template, request

from datos import ConexionBD, ConocimientoDAO, RepositorioConocimiento
from negocio import ErrorConflicto, ErrorNoEncontrado, MotorDJ, ServicioSesion

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024  # límite de seguridad para cualquier petición
FORMATOS = ["MP3", "WAV", "FLAC"]


@contextmanager
def servicio():
    """Abre la base, entrega el servicio de sesión y cierra la conexión al terminar."""
    conexion = ConexionBD(app.config.get("DJ_DB"))
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


@app.errorhandler(ValueError)
def error_validacion(error):
    return jsonify({"error": str(error)}), 400


@app.errorhandler(ErrorNoEncontrado)
def error_no_encontrado(error):
    return jsonify({"error": str(error)}), 404


@app.errorhandler(ErrorConflicto)
def error_conflicto(error):
    return jsonify({"error": str(error)}), 409


@app.errorhandler(sqlite3.IntegrityError)
def error_integridad(error):
    return jsonify({"error": f"La base de datos rechazó la operación: {error}."}), 409


@app.errorhandler(413)
def error_tamano(_error):
    return jsonify({"error": "La petición es demasiado grande."}), 413


@app.get("/")
def inicio():
    return render_template("index.html")


@app.get("/api/opciones")
def opciones():
    with servicio() as s:
        variables = s.conocimiento.variables()
        return jsonify({
            "variables": [{"id": v, "nombre": info["descripcion"], "valores": info["valores"]}
                          for v, info in variables.items()],
            "generos": list(s.conocimiento.generos().keys()),
            "formatos": FORMATOS,
            "parametros": s.conocimiento.parametros(),
        })


@app.post("/api/usuarios")
def registrar_usuario():
    datos = cuerpo()
    with servicio() as s:
        return jsonify(s.registrar_dj(datos.get("nombre"), datos.get("correo")))


@app.get("/api/usuarios/<int:usuario_id>/canciones")
def listar_canciones(usuario_id):
    with servicio() as s:
        return jsonify(s.catalogo(usuario_id))


@app.post("/api/usuarios/<int:usuario_id>/canciones")
def registrar_cancion(usuario_id):
    datos = cuerpo()
    with servicio() as s:
        return jsonify(s.registrar_cancion(usuario_id, datos)), 201


@app.delete("/api/usuarios/<int:usuario_id>/canciones/<int:cancion_id>")
def eliminar_cancion(usuario_id, cancion_id):
    with servicio() as s:
        s.eliminar_cancion(usuario_id, cancion_id)
        return jsonify({"eliminada": cancion_id})


@app.get("/api/usuarios/<int:usuario_id>/eventos")
def listar_eventos(usuario_id):
    with servicio() as s:
        return jsonify(s.eventos_de(usuario_id))


@app.post("/api/usuarios/<int:usuario_id>/eventos")
def crear_evento(usuario_id):
    d = cuerpo()
    with servicio() as s:
        return jsonify(s.crear_evento(usuario_id, d.get("nombre"), d.get("tipo_evento"), d.get("duracion_min"),
                                      d.get("inicio_previsto"), d.get("lugar"), d.get("aforo_estimado"))), 201


@app.post("/api/eventos/<int:evento_id>/recomendar")
def recomendar_evento(evento_id):
    d = cuerpo()
    with servicio() as s:
        return jsonify(s.recomendar(evento_id, d.get("contexto", {}), d.get("cancion_actual_id")))


@app.post("/api/eventos/<int:evento_id>/finalizar")
def finalizar_evento(evento_id):
    with servicio() as s:
        return jsonify(s.finalizar_evento(evento_id))


@app.get("/api/eventos/<int:evento_id>/historial")
def historial(evento_id):
    with servicio() as s:
        return jsonify(s.historial(evento_id))


@app.get("/api/recomendaciones/<int:recomendacion_id>")
def explicacion(recomendacion_id):
    with servicio() as s:
        return jsonify(s.explicacion(recomendacion_id))


@app.post("/api/recomendaciones/<int:recomendacion_id>/decision")
def decidir(recomendacion_id):
    d = cuerpo()
    with servicio() as s:
        return jsonify(s.decidir(recomendacion_id, d.get("accion"), d.get("cancion_final_id"),
                                 d.get("motivo"))), 201


@app.post("/api/recomendar")
def recomendar():
    """Simulación: ejecuta el motor con el catálogo enviado y no guarda nada."""
    datos = cuerpo()
    repo = RepositorioConocimiento()
    try:
        motor = MotorDJ(repo)
        return jsonify(motor.recomendar(datos.get("contexto", {}), datos.get("catalogo", []),
                                        datos.get("cancion_actual_id")))
    finally:
        repo.cerrar()


@app.get("/api/salud")
def salud():
    """Comprueba que la base responde y que el conocimiento está cargado."""
    try:
        conexion = ConexionBD(app.config.get("DJ_DB"))
        try:
            reglas = len(ConocimientoDAO(conexion).reglas())
        finally:
            conexion.cerrar()
    except Exception as error:  # el servicio informa la avería en vez de caerse
        return jsonify({"estado": "error", "detalle": str(error)}), 503
    return jsonify({"estado": "ok", "motor": "MotorDJ · reglas del documento", "reglas_activas": reglas})


if __name__ == "__main__":
    app.run(debug=True)
