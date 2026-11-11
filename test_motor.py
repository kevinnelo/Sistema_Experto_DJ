import unittest
from datos import RepositorioConocimiento
from negocio import MotorDJ


def cancion(id_, bpm, camelot, energia, genero="Salsa", **extra):
    base = {"id": id_, "titulo": f"T{id_}", "artista": "A", "genero": genero, "bpm": bpm,
            "tonalidad_camelot": camelot, "energia": energia, "duracion_seg": 200, "formato": "MP3"}
    base.update(extra)
    return base


class PruebasMotor(unittest.TestCase):
    def setUp(self):
        self.repo = RepositorioConocimiento()
        self.motor = MotorDJ(self.repo)

    def tearDown(self):
        self.repo.cerrar()

    # --- base de conocimiento fiel al documento
    def test_base_tiene_27_reglas_y_parametros_del_documento(self):
        self.assertEqual(len(self.motor.reglas), 27)
        self.assertEqual(self.motor.parametros["energia_diferencia_mismo_nivel"], 1)
        self.assertEqual(self.motor.parametros["bpm_diferencia_tolerada"], 10)
        self.assertEqual(self.motor.parametros["bpm_diferencia_mezcla_similar"], 5)
        self.assertEqual(self.motor.parametros["camelot_distancia_maxima"], 3)

    # --- disparo de reglas (Y entre variables, O dentro de la variable)
    def test_regla_se_dispara_con_O_dentro_de_variable(self):
        disparadas = {r["codigo"] for r in self.motor.disparar({"genero_actual": "merengue", "reaccion_publico": "baila_poco"})}
        self.assertIn("R20", disparadas)
        disparadas = {r["codigo"] for r in self.motor.disparar({"genero_actual": "salsa", "reaccion_publico": "sentado"})}
        self.assertNotIn("R20", disparadas)

    def test_sin_respuesta_la_regla_no_se_dispara(self):
        codigos = {r["codigo"] for r in self.motor.disparar({"genero_actual": "salsa"})}
        self.assertNotIn("R20", codigos)
        self.assertNotIn("R25", codigos)

    # --- validaciones
    def test_rechaza_valor_de_contexto_invalido(self):
        with self.assertRaises(ValueError):
            self.motor.validar_contexto({"momento": "inventado"})
        with self.assertRaises(ValueError):
            self.motor.validar_contexto({"variable_extra": "x"})

    def test_rechaza_cancion_con_datos_fuera_de_restriccion(self):
        malas = [
            cancion("1", 30, "8A", 5),          # BPM < 40
            cancion("2", 120, "13A", 5),        # Camelot inválido
            cancion("3", 120, "8A", 11),        # energía > 10
            cancion("4", 120, "8A", 5, formato="OGG"),
            cancion("5", 120, "8A", 5, genero="Jazz"),
        ]
        for c in malas:
            with self.assertRaises(ValueError):
                self.motor.validar_catalogo([c])

    def test_rechaza_ids_repetidos(self):
        with self.assertRaises(ValueError):
            self.motor.validar_catalogo([cancion("1", 120, "8A", 5), cancion("1", 121, "8A", 5)])

    # --- conflictos: se reportan, no se resuelven
    def test_conflicto_subir_y_bajar_se_reporta(self):
        r = self.motor.recomendar({"momento": "momento_principal", "tipo_evento": "empresarial"}, [], None)
        self.assertEqual(r["conflictos"], [])  # R10 sube, sin regla que baje aquí
        r = self.motor.recomendar({"momento": "momento_principal", "genero_actual": "rock",
                                   "reaccion_publico": "sentado"}, [], None)
        self.assertTrue(any(c["reglas"] == ["R10", "R21"] for c in r["conflictos"]))
        self.assertIn("decide el DJ", r["conflictos"][0]["descripcion"])

    # --- recomendaciones con catálogo
    def test_no_recomienda_canciones_incompatibles_en_camelot(self):
        catalogo = [cancion("a", 124, "8A", 5), cancion("b", 120, "9A", 7), cancion("c", 131, "2B", 9)]
        r = self.motor.recomendar({"momento": "momento_principal"}, catalogo, "a")
        ids = [c["id"] for rec in r["recomendaciones"] for c in rec["canciones"]]
        self.assertIn("b", ids)
        self.assertNotIn("c", ids)   # 8A vs 2B: distancia 6 > 3
        self.assertNotIn("a", ids)   # la propia canción actual

    def test_subir_solo_muestra_canciones_con_mas_energia(self):
        catalogo = [cancion("a", 124, "8A", 5), cancion("b", 124, "8A", 7), cancion("c", 124, "8A", 3)]
        r = self.motor.recomendar({"momento": "momento_principal"}, catalogo, "a")
        subir = next(x for x in r["recomendaciones"] if x["accion"] == "SUBIR_ENERGIA")
        self.assertEqual([c["id"] for c in subir["canciones"]], ["b"])

    def test_bajar_ordena_de_menor_a_mayor_energia_desde_la_actual(self):
        catalogo = [cancion("a", 124, "8A", 8), cancion("b", 124, "8A", 2), cancion("c", 124, "8A", 5)]
        r = self.motor.recomendar({"momento": "cierre"}, catalogo, "a")
        bajar = next(x for x in r["recomendaciones"] if x["accion"] == "BAJAR_ENERGIA")
        self.assertEqual([c["id"] for c in bajar["canciones"]], ["b", "c"])

    # --- técnicas de transición según el caso de BPM (tabla del documento)
    def test_bpm_similar_usa_cross_fade_y_mezcla_sencilla(self):
        catalogo = [cancion("a", 124, "8A", 5), cancion("b", 120, "8A", 7)]
        r = self.motor.recomendar({"momento": "momento_principal"}, catalogo, "a")
        codigos = [t["codigo"] for t in r["recomendaciones"][0]["canciones"][0]["transiciones"]]
        self.assertIn("CROSSFADE", codigos)
        self.assertIn("MEZCLA_SIMPLE", codigos)
        self.assertIn("SYNC_BPM", codigos)

    def test_bpm_distinto_usa_ajuste_de_tempo(self):
        catalogo = [cancion("a", 100, "8A", 5), cancion("b", 130, "8A", 7)]
        r = self.motor.recomendar({"momento": "momento_principal"}, catalogo, "a")
        codigos = [t["codigo"] for t in r["recomendaciones"][0]["canciones"][0]["transiciones"]]
        self.assertIn("AJUSTE_TEMPO", codigos)

    def test_bpm_entre_5_y_10_usa_ajuste_de_tempo_y_cross_fade(self):
        catalogo = [cancion("a", 124, "8A", 5), cancion("b", 130, "8A", 7)]
        r = self.motor.recomendar({"momento": "momento_principal"}, catalogo, "a")
        cancion_b = r["recomendaciones"][0]["canciones"][0]
        tolerables = [t["codigo"] for t in cancion_b["transiciones"] if t["caso"] == "BPM_TOLERABLE"]
        self.assertEqual(tolerables, ["AJUSTE_TEMPO", "CROSSFADE"])       # en orden de prioridad
        self.assertNotIn("MEZCLA_SIMPLE", [t["codigo"] for t in cancion_b["transiciones"]])
        self.assertEqual(cancion_b["notas"], [])

    def test_limites_de_los_casos_de_bpm(self):
        self.assertEqual([self.motor._caso_bpm(d) for d in (0, 5, 5.01, 10, 10.01)],
                         ["BPM_SIMILAR", "BPM_SIMILAR", "BPM_TOLERABLE", "BPM_TOLERABLE", "BPM_DISTINTO"])

    def test_cambio_de_genero_agrega_corte_directo(self):
        catalogo = [cancion("a", 124, "8A", 5, genero="Salsa"), cancion("b", 124, "8A", 7, genero="Pop")]
        r = self.motor.recomendar({"momento": "momento_principal", "genero_actual": "salsa"}, catalogo, "a")
        codigos = [t["codigo"] for t in r["recomendaciones"][0]["canciones"][0]["transiciones"]]
        self.assertIn("CORTE_DIRECTO", codigos)

    # --- casos sin canción que cumplan
    def test_cambiar_genero_pide_confirmar_y_no_inventa_canciones(self):
        catalogo = [cancion("a", 124, "8A", 5, genero="Vallenato")]
        r = self.motor.recomendar({"genero_actual": "vallenato", "reaccion_publico": "solicita_otro_genero"},
                                  catalogo, "a")
        rec = next(x for x in r["recomendaciones"] if x["accion"] == "CAMBIAR_GENERO")
        self.assertEqual(rec["canciones"], [])
        self.assertTrue(rec["notas"])

    def test_sin_reglas_se_informa(self):
        r = self.motor.recomendar({"tipo_evento": "boda", "momento": "llegada"}, [], None)
        self.assertFalse(r["sin_reglas"])  # R02 y R07 sí aplican
        r = self.motor.recomendar({"grupo_edad": "ninos", "genero_actual": "pop"}, [], None)
        self.assertFalse(r["sin_reglas"])  # R12 aplica
        r = self.motor.recomendar({}, [], None)
        self.assertTrue(r["sin_reglas"])

    def test_cancion_actual_debe_existir(self):
        with self.assertRaises(ValueError):
            self.motor.recomendar({"momento": "cierre"}, [cancion("a", 124, "8A", 5)], "zz")

    def test_traza_registra_reglas_y_filtros(self):
        r = self.motor.recomendar({"momento": "cierre"}, [cancion("a", 124, "8A", 5)], None)
        self.assertEqual(r["traza"][0]["paso"], "reglas_disparadas")
        self.assertIn("R11", r["traza"][0]["reglas"])


if __name__ == "__main__":
    unittest.main()
