"""Pruebas de la API por HTTP: cuenta y sesión, flujo completo, historial y aislamiento entre usuarios."""
import unittest

import psycopg

from app import app
from datos import ConexionBD
from tests.base import URL, borrar_esquema, esquema_nuevo

CLAVE = "clave-segura-1"
CATALOGO = [
    {"titulo": "A", "artista": "x", "genero": "Salsa", "bpm": 124, "tonalidad_camelot": "8A",
     "energia": 5, "duracion_seg": 200, "formato": "MP3"},
    {"titulo": "B", "artista": "x", "genero": "Salsa", "bpm": 120, "tonalidad_camelot": "9A",
     "energia": 7, "duracion_seg": 200, "formato": "MP3", "conocida": True},
]


class TestsWeb(unittest.TestCase):
    def setUp(self):
        if not URL:
            self.skipTest("Defina PRUEBAS_DATABASE_URL o DATABASE_URL para ejecutar las pruebas con base de datos.")
        self.esquema = esquema_nuevo()
        try:
            ConexionBD(URL, self.esquema).cerrar()
        except psycopg.OperationalError as error:
            self.skipTest(f"No hay conexión con PostgreSQL: {error}")
        self.addCleanup(borrar_esquema, self.esquema)
        app.config.update(DATABASE_URL=URL, DJ_SCHEMA=self.esquema)
        self.addCleanup(lambda: (app.config.pop("DATABASE_URL", None), app.config.pop("DJ_SCHEMA", None)))
        self.c = app.test_client()

    def registrar(self, cliente=None, correo="web@ejemplo.com", **extra):
        return (cliente or self.c).post("/api/registro", json={"nombre": "DJ Web", "correo": correo, "clave": CLAVE, **extra})

    # --- páginas públicas
    def test_pagina_principal_salud_y_opciones(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        salud = self.c.get("/api/salud").json
        self.assertEqual((salud["estado"], salud["base"], salud["reglas_activas"]), ("ok", "PostgreSQL", 27))
        o = self.c.get("/api/opciones").json
        self.assertEqual(len(o["variables"]), 5)
        self.assertEqual(o["generos"]["Salsa"], "salsa")
        self.assertEqual(o["parametros"]["camelot_distancia_maxima"], 3)
        # flujo guiado: qué reacciones tienen regla para cada género (sale de las reglas, no del código)
        self.assertEqual(o["reacciones_por_genero"]["salsa"], ["baila_poco", "sin_reaccion"])
        self.assertEqual(o["reacciones_por_genero"]["infantil"], ["positiva", "rie_y_canta"])
        self.assertEqual(o["reacciones_generales"], ["se_retira"])

    # --- cuenta y sesión
    def test_sin_sesion_las_rutas_de_datos_responden_401(self):
        for metodo, ruta in (("get", "/api/canciones"), ("post", "/api/canciones"), ("get", "/api/eventos"),
                             ("get", "/api/consultas"), ("get", "/api/consultas/1"), ("post", "/api/eventos/1/consultas"),
                             ("post", "/api/recomendaciones/1/decision"), ("get", "/api/recomendaciones/1"),
                             ("post", "/api/ejemplos"), ("delete", "/api/canciones/1")):
            self.assertEqual(getattr(self.c, metodo)(ruta, json={}).status_code, 401, ruta)
        self.assertIsNone(self.c.get("/api/sesion").json["usuario"])

    def test_registro_login_y_logout(self):
        r = self.registrar()
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("clave", " ".join(r.json))                       # ni la clave ni su hash salen por la API
        self.assertEqual(self.c.get("/api/sesion").json["usuario"]["correo"], "web@ejemplo.com")
        self.assertEqual(self.registrar().status_code, 409)               # correo repetido
        self.assertEqual(self.registrar(correo="otro@ejemplo.com", clave="corta").status_code, 400)
        self.c.post("/api/logout", json={})
        self.assertEqual(self.c.get("/api/canciones").status_code, 401)
        mala = self.c.post("/api/login", json={"correo": "web@ejemplo.com", "clave": "equivocada-1"})
        nadie = self.c.post("/api/login", json={"correo": "nadie@ejemplo.com", "clave": CLAVE})
        self.assertEqual((mala.status_code, nadie.status_code), (401, 401))
        self.assertEqual(mala.json, nadie.json)                           # no revela si el correo existe
        self.assertEqual(self.c.post("/api/login", json={"correo": "WEB@ejemplo.com", "clave": CLAVE}).status_code, 200)
        self.assertEqual(self.c.get("/api/canciones").status_code, 200)
        cookie = self.c.get_cookie("session")
        self.assertTrue(cookie.http_only)

    # --- flujo completo (CU01 a CU05) e historial
    def test_flujo_completo_queda_guardado_y_se_consulta_en_el_historial(self):
        c = self.c
        self.registrar()
        ids = []
        for cancion in CATALOGO:
            r = c.post("/api/canciones", json=cancion)
            self.assertEqual(r.status_code, 201)
            ids.append(r.json["id"])
        self.assertEqual(c.post("/api/canciones", json=CATALOGO[0]).status_code, 409)
        self.assertEqual(c.post("/api/canciones", json=dict(CATALOGO[0], titulo="Mala", bpm=10)).status_code, 400)
        evento = c.post("/api/eventos", json={"nombre": "Fiesta", "tipo_evento": "discoteca"})
        self.assertEqual((evento.status_code, evento.json["estado"]), (201, "PLANEADO"))
        eid = evento.json["id"]
        r = c.post(f"/api/eventos/{eid}/consultas", json={
            "contexto": {"momento": "momento_principal", "reaccion_publico": "baila_poco"}, "cancion_actual_id": ids[0]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual([x["codigo"] for x in r.json["reglas_disparadas"]], ["R05", "R10", "R20"])
        self.assertEqual(r.json["hechos"]["genero_actual"], "salsa")               # tomado de la canción
        subir = next(x for x in r.json["recomendaciones"] if x["accion"] == "SUBIR_ENERGIA")
        self.assertEqual(int(subir["cancion_sugerida"]["id"]), ids[1])
        d = c.post(f"/api/recomendaciones/{subir['id']}/decision", json={"accion": "ACEPTADA", "motivo": "ok"})
        self.assertEqual((d.status_code, d.json["decision"]["accion"]), (201, "ACEPTADA"))
        self.assertEqual(c.post(f"/api/recomendaciones/{subir['id']}/decision", json={"accion": "RECHAZADA"}).status_code, 409)
        # historial: lista y resultado completo
        lista = c.get("/api/consultas").json
        self.assertEqual([(x["evento"], x["reglas"], x["recomendaciones"], x["decisiones"]) for x in lista],
                         [("Fiesta", "R05, R10, R20", 2, 1)])
        completa = c.get(f"/api/consultas/{lista[0]['id']}").json
        self.assertEqual(completa["reglas_disparadas"], r.json["reglas_disparadas"])
        guardada = next(x for x in completa["recomendaciones"] if x["id"] == subir["id"])
        self.assertEqual((guardada["explicacion"], guardada["decision"]["motivo"]), (subir["explicacion"], "ok"))
        self.assertEqual(c.get(f"/api/eventos/{eid}/historial").json[0]["cancion_sugerida"], "B")
        self.assertIn("R20", c.get(f"/api/recomendaciones/{subir['id']}").json["explicacion"])
        self.assertEqual(c.delete(f"/api/canciones/{ids[1]}").status_code, 409)     # está en el historial
        self.assertEqual(c.post(f"/api/eventos/{eid}/finalizar", json={}).json["estado"], "FINALIZADO")
        self.assertEqual(c.post(f"/api/eventos/{eid}/consultas", json={"contexto": {}}).status_code, 409)

    def test_registro_con_casos_de_ejemplo(self):
        self.assertEqual(self.registrar(ejemplos=True).status_code, 201)
        consultas = self.c.get("/api/consultas").json
        self.assertEqual(len(consultas), 5)
        self.assertTrue(all(x["evento"].startswith("Ejemplo · ") for x in consultas))
        self.assertEqual(len(self.c.get("/api/canciones").json), 16)
        self.assertEqual(self.c.post("/api/ejemplos", json={}).status_code, 409)

    def test_un_usuario_no_ve_ni_cambia_lo_de_otro(self):
        self.registrar(ejemplos=True)
        consulta = self.c.get("/api/consultas").json[0]
        completa = self.c.get(f"/api/consultas/{consulta['id']}").json
        pendiente = next(x for x in completa["recomendaciones"] if x["decision"] is None)
        cancion = self.c.get("/api/canciones").json[0]["id"]
        intruso = app.test_client()
        self.registrar(intruso, correo="intruso@ejemplo.com")
        self.assertEqual(intruso.get("/api/consultas").json, [])
        self.assertEqual(intruso.get("/api/canciones").json, [])
        for respuesta in (intruso.get(f"/api/consultas/{consulta['id']}"),
                          intruso.get(f"/api/recomendaciones/{pendiente['id']}"),
                          intruso.post(f"/api/recomendaciones/{pendiente['id']}/decision", json={"accion": "ACEPTADA"}),
                          intruso.post(f"/api/eventos/{consulta['evento_id']}/consultas", json={"contexto": {}}),
                          intruso.get(f"/api/eventos/{consulta['evento_id']}/historial"),
                          intruso.delete(f"/api/canciones/{cancion}")):
            self.assertEqual(respuesta.status_code, 404)

    # --- validaciones
    def test_rechaza_entradas_invalidas(self):
        self.registrar()
        eid = self.c.post("/api/eventos", json={"nombre": "Fiesta", "tipo_evento": "boda"}).json["id"]
        self.assertEqual(self.c.post("/api/eventos", json={"nombre": "x", "tipo_evento": "salsa"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/eventos/{eid}/consultas", json={"contexto": {"momento": "no_existe"}}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/eventos/{eid}/consultas", json={"contexto": {"inventada": "x"}}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/eventos/{eid}/consultas", data="no json", content_type="text/plain").status_code, 400)
        sin_reglas = self.c.post(f"/api/eventos/{eid}/consultas", json={"contexto": {}})
        self.assertEqual(sin_reglas.status_code, 201)                              # boda dispara R02
        self.assertEqual(self.c.get("/api/consultas/999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
