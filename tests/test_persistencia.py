"""Pruebas de los procesos transaccionales (CU01 a CU05) y de las restricciones de integridad."""
import sqlite3
import unittest
from unittest import mock

from datos import ConexionBD, RecomendacionDAO
from negocio import ErrorConflicto, ErrorNoEncontrado, ServicioSesion
from tests.base import CasoConBase, cancion

CONTEXTO = {"momento": "momento_principal", "grupo_edad": "jovenes",
            "genero_actual": "salsa", "reaccion_publico": "baila_poco"}


class ProcesosTransaccionales(CasoConBase):
    # ---------------------------------------------------------------- usuario
    def test_PT01_registrar_dj_es_idempotente_por_correo(self):
        otra_vez = self.s.registrar_dj("Otro nombre", "  DJ@Ejemplo.com ")
        self.assertEqual(otra_vez["id"], self.dj["id"])
        self.assertEqual(self.contar("usuario"), 1)
        with self.assertRaises(ValueError):
            self.s.registrar_dj("X", "sin-arroba")

    # ---------------------------------------------------------------- CU01
    def test_PT02_cancion_se_guarda_y_se_consulta(self):
        (cid,) = self.cargar(cancion("Tema A", 124, "8a", 5, metadatos_id3={"TIT2": "Tema A"}))
        guardada = self.s.catalogo(self.dj["id"])[0]
        self.assertEqual(guardada["id"], cid)
        self.assertEqual(guardada["tonalidad_camelot"], "8A")
        self.assertEqual(guardada["genero"], "Salsa")
        self.assertEqual(guardada["metadatos_id3"], {"TIT2": "Tema A"})

    def test_PT03_cancion_invalida_o_duplicada_no_se_guarda(self):
        self.cargar(cancion("Tema A", 124, "8A", 5))
        with self.assertRaises(ValueError):
            self.s.registrar_cancion(self.dj["id"], cancion("Tema B", 300, "8A", 5))
        with self.assertRaises(ErrorConflicto):
            self.s.registrar_cancion(self.dj["id"], cancion("Tema A", 100, "1B", 2))
        self.assertEqual(self.contar("cancion"), 1)

    # ---------------------------------------------------------------- CU02
    def test_PT04_evento_valida_tipo_y_duracion(self):
        self.assertEqual(self.evento["estado"], "PLANEADO")
        self.assertEqual(self.evento["tipo_evento"], "discoteca")
        with self.assertRaises(ValueError):
            self.s.crear_evento(self.dj["id"], "Mal", "salsa", 60)       # valor de otra variable
        with self.assertRaises(ValueError):
            self.s.crear_evento(self.dj["id"], "Mal", "boda", 0)
        with self.assertRaises(ErrorNoEncontrado):
            self.s.crear_evento(999, "Mal", "boda", 60)
        self.assertEqual(self.contar("evento"), 1)

    def test_PT05_cada_actualizacion_de_contexto_es_una_fotografia_nueva(self):
        self.s.recomendar(self.evento["id"], CONTEXTO)
        self.s.recomendar(self.evento["id"], dict(CONTEXTO, momento="cierre"))
        contextos = self.s.contextos.listar(self.evento["id"])
        self.assertEqual([c["momento"] for c in contextos], ["momento_principal", "cierre"])
        self.assertEqual(self.s.eventos.obtener(self.evento["id"])["estado"], "EN_CURSO")

    # ---------------------------------------------------------------- CU03
    def test_PT06_recomendar_guarda_contexto_recomendaciones_reglas_y_tecnicas(self):
        a, b, _ = self.cargar(cancion("Actual", 124, "8A", 5), cancion("Sube", 120, "9A", 7),
                              cancion("Lejana", 124, "2B", 9))
        r = self.s.recomendar(self.evento["id"], CONTEXTO, a)
        self.assertEqual([x["codigo"] for x in r["reglas_disparadas"]], ["R05", "R10", "R14", "R20"])
        subir = next(x for x in r["recomendaciones"] if x["accion"] == "SUBIR_ENERGIA")
        guardada = self.s.recomendaciones.obtener(subir["id"])
        self.assertEqual(guardada["cancion_id"], b)
        self.assertEqual(guardada["contexto_id"], r["contexto_id"])
        self.assertEqual([g["codigo"] for g in guardada["reglas"]], ["R10", "R20"])
        self.assertEqual({t["codigo"] for t in guardada["transiciones"]},
                         {"SYNC_BPM", "ECHO_OUT", "CROSSFADE", "MEZCLA_SIMPLE"})
        self.assertGreaterEqual(guardada["tiempo_respuesta_ms"], 0)
        contexto = self.s.contextos.obtener(r["contexto_id"])
        self.assertEqual(contexto["cancion_actual_id"], a)
        self.assertEqual(contexto["reaccion_publico"], "baila_poco")

    def test_PT07_recomendacion_general_se_guarda_sin_cancion(self):
        r = self.s.recomendar(self.evento["id"], {"momento": "inicio"})
        self.assertEqual({x["accion"] for x in r["recomendaciones"]}, {"CRITERIO"})
        guardada = self.s.recomendaciones.obtener(r["recomendaciones"][0]["id"])
        self.assertIsNone(guardada["cancion_id"])
        self.assertEqual(guardada["transiciones"], [])
        self.assertEqual([g["codigo"] for g in guardada["reglas"]], ["R05", "R08"])

    def test_PT08_si_falla_a_mitad_no_queda_nada_guardado(self):
        self.cargar(cancion("Actual", 124, "8A", 5), cancion("Sube", 120, "9A", 7))
        original = RecomendacionDAO.crear
        llamadas = []

        def falla_en_la_segunda(dao, *args):
            llamadas.append(1)
            if len(llamadas) == 2:
                raise sqlite3.OperationalError("fallo simulado")
            return original(dao, *args)

        with mock.patch.object(RecomendacionDAO, "crear", falla_en_la_segunda):
            with self.assertRaises(sqlite3.OperationalError):
                self.s.recomendar(self.evento["id"], CONTEXTO)
        for tabla in ("contexto_evento", "recomendacion", "recomendacion_regla", "recomendacion_transicion"):
            self.assertEqual(self.contar(tabla), 0, tabla)
        self.assertEqual(self.s.eventos.obtener(self.evento["id"])["estado"], "PLANEADO")

    def test_PT09_cancion_actual_ajena_al_catalogo_se_rechaza_sin_guardar(self):
        otro = self.s.registrar_dj("Otro", "otro@ejemplo.com")
        ajena = self.s.registrar_cancion(otro["id"], cancion("Ajena", 120, "8A", 5))["id"]
        with self.assertRaises(ValueError):
            self.s.recomendar(self.evento["id"], CONTEXTO, ajena)
        self.assertEqual(self.contar("contexto_evento"), 0)

    def test_PT10_evento_finalizado_no_admite_recomendaciones(self):
        self.s.finalizar_evento(self.evento["id"])
        with self.assertRaises(ErrorConflicto):
            self.s.recomendar(self.evento["id"], CONTEXTO)

    # ---------------------------------------------------------------- CU04
    def test_PT11_explicacion_se_reconstruye_del_historial(self):
        a, _ = self.cargar(cancion("Actual", 124, "8A", 5), cancion("Sube", 120, "9A", 7))
        r = self.s.recomendar(self.evento["id"], CONTEXTO, a)
        subir = next(x for x in r["recomendaciones"] if x["accion"] == "SUBIR_ENERGIA")
        nueva_conexion = ConexionBD(self.ruta)          # otra sesión: solo existe lo guardado
        try:
            e = ServicioSesion(nueva_conexion).explicacion(subir["id"])
        finally:
            nueva_conexion.cerrar()
        self.assertEqual(e["hechos"], dict(CONTEXTO, tipo_evento="discoteca"))
        self.assertEqual([g["codigo"] for g in e["reglas"]], ["R10", "R20"])
        self.assertEqual(e["cancion_sugerida"]["titulo"], "Sube")
        for texto in ("R10", "R20", "«Sube»", "Cross-fade out", "energía mayor"):
            self.assertIn(texto, e["explicacion"])

    # ---------------------------------------------------------------- CU05
    def _recomendacion_con_cancion(self):
        a, b, c = self.cargar(cancion("Actual", 124, "8A", 5), cancion("Sube", 120, "9A", 7),
                              cancion("Otra", 126, "8A", 6))
        r = self.s.recomendar(self.evento["id"], CONTEXTO, a)
        return next(x for x in r["recomendaciones"] if x["accion"] == "SUBIR_ENERGIA")["id"], b, c

    def test_PT12_aceptar_rechazar_y_modificar_quedan_en_el_historial(self):
        rid, sugerida, otra = self._recomendacion_con_cancion()
        antes = self.s.recomendaciones.obtener(rid)
        self.s.decidir(rid, "MODIFICADA", otra, "El público pidió otra")
        despues = self.s.recomendaciones.obtener(rid)
        self.assertEqual(despues["cancion_id"], sugerida)               # el original no se borra
        self.assertEqual(despues["explicacion"], antes["explicacion"])
        fila = self.s.historial(self.evento["id"])[0]
        self.assertEqual((fila["accion"], fila["cancion_sugerida"], fila["cancion_final"], fila["reglas"]),
                         ("MODIFICADA", "Sube", "Otra", "R10, R20"))
        self.assertEqual(fila["motivo"], "El público pidió otra")
        self.assertTrue(fila["decidida_en"])

    def test_PT13_reglas_de_la_decision(self):
        rid, sugerida, otra = self._recomendacion_con_cancion()
        with self.assertRaises(ValueError):
            self.s.decidir(rid, "MODIFICADA")                 # falta la canción final
        with self.assertRaises(ValueError):
            self.s.decidir(rid, "ACEPTADA", otra)             # solo MODIFICADA lleva canción final
        with self.assertRaises(ValueError):
            self.s.decidir(rid, "MODIFICADA", sugerida)       # la misma sugerida no es modificar
        with self.assertRaises(ValueError):
            self.s.decidir(rid, "POSPUESTA")
        with self.assertRaises(ErrorNoEncontrado):
            self.s.decidir(9999, "ACEPTADA")
        self.assertEqual(self.contar("decision_dj"), 0)
        self.s.decidir(rid, "ACEPTADA")
        with self.assertRaises(ErrorConflicto):
            self.s.decidir(rid, "RECHAZADA", motivo="segunda decisión")
        self.assertEqual(self.contar("decision_dj"), 1)

    def test_PT14_cancion_con_historial_no_se_elimina(self):
        rid, sugerida, otra = self._recomendacion_con_cancion()
        with self.assertRaises(ErrorConflicto):
            self.s.eliminar_cancion(self.dj["id"], sugerida)
        self.s.eliminar_cancion(self.dj["id"], otra)          # sin historial: sí se elimina
        self.assertEqual(self.contar("cancion"), 2)

    def test_PT15_los_datos_sobreviven_al_cierre_de_la_conexion(self):
        rid, _, _ = self._recomendacion_con_cancion()
        self.s.decidir(rid, "ACEPTADA")
        self.cx.cerrar()
        self.cx = ConexionBD(self.ruta)
        self.s = ServicioSesion(self.cx)
        self.assertEqual(len(self.s.catalogo(self.dj["id"])), 3)
        self.assertEqual(len(self.s.historial(self.evento["id"])), 1)
        self.assertEqual(self.contar("regla"), 27)            # el conocimiento no se duplica


class RestriccionesDeIntegridad(CasoConBase):
    """Cada restricción se prueba directamente contra la base, sin pasar por la validación de Python."""

    def setUp(self):
        super().setUp()
        self.a, self.b = self.cargar(cancion("Actual", 124, "8A", 5), cancion("Sube", 120, "9A", 7))
        r = self.s.recomendar(self.evento["id"], {"momento": "momento_principal"}, self.a)
        self.contexto_id = r["contexto_id"]
        self.rec_id = r["recomendaciones"][-1]["id"]
        self.db = self.cx.db

    def id_valor(self, variable, codigo):
        return self.s.conocimiento.id_valor(variable, codigo)

    def rechaza(self, sql, parametros=(), mensaje=None):
        with self.assertRaises(sqlite3.IntegrityError) as error:
            self.db.execute(sql, parametros)
        if mensaje:
            self.assertIn(mensaje, str(error.exception))

    def test_RI01_condicion_exige_valor_de_su_variable(self):
        variable_momento = self.db.execute("SELECT id FROM variable WHERE codigo='momento'").fetchone()[0]
        self.rechaza("INSERT INTO condicion_regla (regla_id, variable_id, valor_id) VALUES (1, ?, ?)",
                     (variable_momento, self.id_valor("genero_actual", "salsa")))

    def test_RI02_cancion_respeta_rangos_y_formato(self):
        base = "INSERT INTO cancion (usuario_id, titulo, artista, genero_id, bpm, tonalidad_camelot, " \
               "energia, duracion_seg, formato) VALUES (?, ?, 'Artista', 1, ?, ?, ?, ?, ?)"
        u = self.dj["id"]
        self.rechaza(base, (u, "bpm", 39, "8A", 5, 200, "MP3"))
        self.rechaza(base, (u, "camelot", 120, "13A", 5, 200, "MP3"))
        self.rechaza(base, (u, "camelot2", 120, "8C", 5, 200, "MP3"))
        self.rechaza(base, (u, "energia", 120, "8A", 11, 200, "MP3"))
        self.rechaza(base, (u, "duracion", 120, "8A", 5, 0, "MP3"))
        self.rechaza(base, (u, "formato", 120, "8A", 5, 200, "OGG"))
        self.rechaza(base, (u, "Actual", 120, "8A", 5, 200, "MP3"))          # título + artista repetidos
        self.rechaza(base.replace("formato)", "formato, conocida)").replace("?)", "?, 2)"),
                     (u, "conocida", 120, "8A", 5, 200, "MP3"))
        self.rechaza(base.replace("formato)", "formato, metadatos_id3)").replace("?)", "?, '{mal')"),
                     (u, "json", 120, "8A", 5, 200, "MP3"))

    def test_RI03_evento_exige_valor_de_tipo_evento(self):
        self.rechaza("INSERT INTO evento (usuario_id, nombre, tipo_evento_id, inicio_previsto, duracion_min) "
                     "VALUES (?, 'x', ?, '2026-01-01', 60)",
                     (self.dj["id"], self.id_valor("momento", "cierre")), "tipo_evento")

    def test_RI04_contexto_exige_valores_de_cada_variable(self):
        for columna in ("momento_id", "grupo_edad_id", "genero_actual_id", "reaccion_publico_id"):
            self.rechaza(f"INSERT INTO contexto_evento (evento_id, {columna}) VALUES (?, ?)",
                         (self.evento["id"], self.id_valor("tipo_evento", "boda")), columna)

    def test_RI05_genero_exige_valor_de_genero_actual(self):
        self.rechaza("INSERT INTO genero_musical (nombre, valor_regla_id) VALUES ('Raro', ?)",
                     (self.id_valor("momento", "cierre"),), "genero_actual")

    def test_RI06_recomendacion_exige_contexto_del_mismo_evento(self):
        otro = self.s.crear_evento(self.dj["id"], "Otro evento", "boda", 60)
        self.rechaza("INSERT INTO recomendacion (evento_id, contexto_id, explicacion) VALUES (?, ?, 'x')",
                     (otro["id"], self.contexto_id))

    def test_RI07_canciones_de_otro_dj_no_entran_al_evento(self):
        otro = self.s.registrar_dj("Otro", "otro@ejemplo.com")
        ajena = self.s.registrar_cancion(otro["id"], cancion("Ajena", 120, "8A", 5))["id"]
        self.rechaza("INSERT INTO recomendacion (evento_id, contexto_id, cancion_id, explicacion) "
                     "VALUES (?, ?, ?, 'x')", (self.evento["id"], self.contexto_id, ajena), "catálogo")
        self.rechaza("INSERT INTO contexto_evento (evento_id, cancion_actual_id) VALUES (?, ?)",
                     (self.evento["id"], ajena), "catálogo")
        self.rechaza("INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id) "
                     "VALUES (?, 'MODIFICADA', ?)", (self.rec_id, ajena), "catálogo")

    def test_RI08_explicacion_obligatoria(self):
        self.rechaza("INSERT INTO recomendacion (evento_id, contexto_id, explicacion) VALUES (?, ?, '  ')",
                     (self.evento["id"], self.contexto_id))

    def test_RI09_tecnica_solo_con_cancion(self):
        general = self.db.execute("SELECT id FROM recomendacion WHERE cancion_id IS NULL").fetchone()[0]
        self.rechaza("INSERT INTO recomendacion_transicion VALUES (?, 1)", (general,), "técnica")

    def test_RI10_decision_coherente_y_unica(self):
        self.rechaza("INSERT INTO decision_dj (recomendacion_id, accion) VALUES (?, 'MODIFICADA')", (self.rec_id,))
        self.rechaza("INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id) "
                     "VALUES (?, 'ACEPTADA', ?)", (self.rec_id, self.a))
        self.rechaza("INSERT INTO decision_dj (recomendacion_id, accion, cancion_final_id) "
                     "VALUES (?, 'MODIFICADA', ?)", (self.rec_id, self.b), "distinta")
        self.rechaza("INSERT INTO decision_dj (recomendacion_id, accion) VALUES (?, 'OTRA')", (self.rec_id,))
        self.db.execute("INSERT INTO decision_dj (recomendacion_id, accion) VALUES (?, 'ACEPTADA')", (self.rec_id,))
        self.rechaza("INSERT INTO decision_dj (recomendacion_id, accion) VALUES (?, 'RECHAZADA')", (self.rec_id,))

    def test_RI11_el_historial_es_de_solo_insercion(self):
        self.db.execute("INSERT INTO decision_dj (recomendacion_id, accion) VALUES (?, 'ACEPTADA')", (self.rec_id,))
        self.rechaza("UPDATE contexto_evento SET momento_id = NULL", mensaje="no se modifica")
        self.rechaza("UPDATE recomendacion SET explicacion = 'otra'", mensaje="no se modifica")
        self.rechaza("UPDATE decision_dj SET accion = 'RECHAZADA'", mensaje="no se modifica")

    def test_RI12_estado_del_evento_solo_avanza(self):
        self.rechaza("UPDATE evento SET estado = 'PLANEADO' WHERE id = ?", (self.evento["id"],), "retroceder")
        self.db.execute("UPDATE evento SET estado = 'FINALIZADO' WHERE id = ?", (self.evento["id"],))
        self.rechaza("UPDATE evento SET estado = 'EN_CURSO' WHERE id = ?", (self.evento["id"],), "retroceder")
        self.rechaza("INSERT INTO contexto_evento (evento_id) VALUES (?)", (self.evento["id"],), "finalizado")
        self.rechaza("UPDATE evento SET estado = 'CANCELADO' WHERE id = ?", (self.evento["id"],))

    def test_RI13_usuario_correo_unico_y_rol_valido(self):
        self.rechaza("INSERT INTO usuario (nombre, correo, rol) VALUES ('x', 'dj@ejemplo.com', 'DJ')")
        self.rechaza("INSERT INTO usuario (nombre, correo, rol) VALUES ('x', 'nuevo@ejemplo.com', 'INVITADO')")
        self.rechaza("INSERT INTO usuario (nombre, correo, rol) VALUES ('x', 'sin-arroba', 'DJ')")

    def test_RI14_base_de_conocimiento_protegida(self):
        self.rechaza("INSERT INTO regla (id, codigo, nombre, conclusion, descripcion, accion) "
                     "VALUES (99, 'R99', 'x', 'x', 'x', 'BAILAR')")
        self.rechaza("INSERT INTO transicion_regla (caso, tecnica_id) VALUES ('INVENTADO', 1)")
        self.rechaza("UPDATE parametro_experto SET valor = 0")
        self.rechaza("DELETE FROM regla WHERE codigo = 'R10'")          # la cita una recomendación

    def test_RI15_referencias_inexistentes_se_rechazan(self):
        self.rechaza("INSERT INTO evento (usuario_id, nombre, tipo_evento_id, inicio_previsto, duracion_min) "
                     "VALUES (999, 'x', ?, '2026-01-01', 60)", (self.id_valor("tipo_evento", "boda"),))
        self.rechaza("INSERT INTO recomendacion_regla VALUES (?, 999)", (self.rec_id,))


if __name__ == "__main__":
    unittest.main()
