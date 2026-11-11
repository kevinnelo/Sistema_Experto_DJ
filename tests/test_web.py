import os
import tempfile
import unittest
from app import app
from datos import RepositorioConocimiento
from negocio import MotorDJ

CATALOGO = [
    {"id": "a", "titulo": "A", "artista": "x", "genero": "Salsa", "bpm": 124, "tonalidad_camelot": "8A",
     "energia": 5, "duracion_seg": 200, "formato": "MP3"},
    {"id": "b", "titulo": "B", "artista": "x", "genero": "Salsa", "bpm": 120, "tonalidad_camelot": "9A",
     "energia": 7, "duracion_seg": 200, "formato": "MP3"},
]


class TestsWeb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        app.config["DJ_DB"] = os.path.join(self.tmp.name, "prueba.db")
        self.client = app.test_client()

    def tearDown(self):
        app.config.pop("DJ_DB", None)
        self.tmp.cleanup()

    def test_opciones_incluye_variables_generos_y_parametros(self):
        r = self.client.get("/api/opciones")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json["variables"]), 5)
        self.assertIn("Salsa", r.json["generos"])
        self.assertEqual(r.json["parametros"]["camelot_distancia_maxima"], 3)

    def test_recomendar_coincide_con_el_motor_python(self):
        contexto = {"momento": "momento_principal", "genero_actual": "salsa", "reaccion_publico": "baila_poco"}
        r = self.client.post("/api/recomendar", json={"contexto": contexto, "catalogo": CATALOGO,
                                                       "cancion_actual_id": "a"})
        self.assertEqual(r.status_code, 200)
        repo = RepositorioConocimiento()
        try:
            esperado = MotorDJ(repo).recomendar(contexto, CATALOGO, "a")
        finally:
            repo.cerrar()
        self.assertEqual(r.json["recomendaciones"], esperado["recomendaciones"])
        self.assertEqual(r.json["reglas_disparadas"], esperado["reglas_disparadas"])

    def test_rechaza_variable_desconocida_y_valor_invalido(self):
        r = self.client.post("/api/recomendar", json={"contexto": {"momento": "no_existe"}, "catalogo": []})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/recomendar", json={"contexto": {"inventada": "x"}, "catalogo": []})
        self.assertEqual(r.status_code, 400)

    def test_rechaza_catalogo_invalido(self):
        malo = [dict(CATALOGO[0], bpm=10)]
        r = self.client.post("/api/recomendar", json={"contexto": {"momento": "cierre"}, "catalogo": malo})
        self.assertEqual(r.status_code, 400)
        self.assertIn("BPM", r.json["error"])

    def test_rechaza_cuerpo_que_no_es_objeto(self):
        r = self.client.post("/api/recomendar", data="no json", content_type="text/plain")
        self.assertEqual(r.status_code, 400)

    def test_acepta_contexto_vacio_sin_reglas(self):
        r = self.client.post("/api/recomendar", json={"contexto": {}, "catalogo": []})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json["sin_reglas"])

    def test_pagina_principal_y_salud(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/salud").json["estado"], "ok")

    # --- flujo persistente completo por HTTP (CU01 a CU05)
    def test_flujo_completo_queda_guardado(self):
        c = self.client
        dj = c.post("/api/usuarios", json={"nombre": "DJ Web", "correo": "web@ejemplo.com"}).json
        ids = []
        for cancion in CATALOGO:
            r = c.post(f"/api/usuarios/{dj['id']}/canciones", json={k: v for k, v in cancion.items() if k != "id"})
            self.assertEqual(r.status_code, 201)
            ids.append(r.json["id"])
        self.assertEqual(c.post(f"/api/usuarios/{dj['id']}/canciones",
                                json={k: v for k, v in CATALOGO[0].items() if k != "id"}).status_code, 409)
        evento = c.post(f"/api/usuarios/{dj['id']}/eventos",
                        json={"nombre": "Fiesta", "tipo_evento": "discoteca", "duracion_min": 180})
        self.assertEqual((evento.status_code, evento.json["estado"]), (201, "PLANEADO"))
        eid = evento.json["id"]
        r = c.post(f"/api/eventos/{eid}/recomendar", json={
            "contexto": {"momento": "momento_principal", "genero_actual": "salsa", "reaccion_publico": "baila_poco"},
            "cancion_actual_id": ids[0]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["codigo"] for x in r.json["reglas_disparadas"]], ["R05", "R10", "R20"])
        subir = next(x for x in r.json["recomendaciones"] if x["accion"] == "SUBIR_ENERGIA")
        self.assertEqual(int(subir["cancion_sugerida"]["id"]), ids[1])
        d = c.post(f"/api/recomendaciones/{subir['id']}/decision", json={"accion": "ACEPTADA"})
        self.assertEqual((d.status_code, d.json["decision"]["accion"]), (201, "ACEPTADA"))
        self.assertEqual(c.post(f"/api/recomendaciones/{subir['id']}/decision",
                                json={"accion": "RECHAZADA"}).status_code, 409)
        historial = c.get(f"/api/eventos/{eid}/historial").json
        self.assertEqual([(h["accion"], h["cancion_sugerida"]) for h in historial], [("ACEPTADA", "B")])
        explicacion = c.get(f"/api/recomendaciones/{subir['id']}").json
        self.assertEqual(explicacion["hechos"]["tipo_evento"], "discoteca")
        self.assertIn("R20", explicacion["explicacion"])
        self.assertEqual(c.delete(f"/api/usuarios/{dj['id']}/canciones/{ids[1]}").status_code, 409)
        self.assertEqual(c.post(f"/api/eventos/{eid}/finalizar", json={}).json["estado"], "FINALIZADO")
        self.assertEqual(c.post(f"/api/eventos/{eid}/recomendar", json={"contexto": {}}).status_code, 409)
        self.assertEqual(c.get(f"/api/usuarios/{dj['id']}/eventos").json[0]["estado"], "FINALIZADO")

    def test_recursos_inexistentes_devuelven_404(self):
        self.assertEqual(self.client.get("/api/usuarios/99/canciones").status_code, 404)
        self.assertEqual(self.client.get("/api/recomendaciones/99").status_code, 404)
        self.assertEqual(self.client.get("/api/eventos/99/historial").status_code, 404)


if __name__ == "__main__":
    unittest.main()
