"""Pruebas de los requisitos no funcionales RNF01 a RNF06 y de las reglas alineadas (R18-R25)."""
import ast
import os
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app import app
from datos import ConexionBD, ConocimientoDAO
from negocio import MotorDJ, ServicioSesion
from tests.base import CasoConBase, cancion

RAIZ = Path(__file__).resolve().parent.parent
GENEROS = ["Infantil", "Pop", "Urbano", "Salsa", "Merengue", "Electrónica", "Rock", "Popular", "Vallenato"]


def catalogo_grande(n):
    return [cancion(f"Tema {i}", 80 + (i * 7) % 100, f"{i % 12 + 1}{'AB'[i % 2]}", i % 10 + 1,
                    genero=GENEROS[i % len(GENEROS)]) for i in range(n)]


class RNF01TiempoDeRespuesta(CasoConBase):
    """El sistema debe responder en menos de 2 segundos."""
    LIMITE_S = 2.0

    def test_RNF01_recomendar_con_500_canciones_tarda_menos_de_2_s(self):
        ids = self.cargar(*catalogo_grande(500))
        contexto = {"momento": "momento_principal", "grupo_edad": "jovenes",
                    "genero_actual": "salsa", "reaccion_publico": "baila_poco"}
        tiempos = []
        for _ in range(5):
            inicio = time.perf_counter()
            r = self.s.recomendar(self.evento["id"], contexto, ids[0])
            tiempos.append(time.perf_counter() - inicio)
            self.assertLess(r["tiempo_respuesta_ms"], self.LIMITE_S * 1000)
        self.assertLess(max(tiempos), self.LIMITE_S)
        guardado = self.cx.db.execute("SELECT MAX(tiempo_respuesta_ms) FROM recomendacion").fetchone()[0]
        self.assertLess(guardado, self.LIMITE_S * 1000)       # el tiempo queda registrado en la base
        print(f"\n  RNF01 · 500 canciones · peor de 5 ejecuciones: {max(tiempos) * 1000:.0f} ms", end="")

    def test_RNF01_peticion_web_completa_tarda_menos_de_2_s(self):
        app.config["DJ_DB"] = self.ruta
        try:
            cliente = app.test_client()
            ids = self.cargar(*catalogo_grande(500))
            inicio = time.perf_counter()
            r = cliente.post(f"/api/eventos/{self.evento['id']}/recomendar",
                             json={"contexto": {"momento": "cierre"}, "cancion_actual_id": ids[0]})
            transcurrido = time.perf_counter() - inicio
        finally:
            app.config.pop("DJ_DB", None)
        self.assertEqual(r.status_code, 200)
        self.assertLess(transcurrido, self.LIMITE_S)
        print(f"\n  RNF01 · petición HTTP con 500 canciones: {transcurrido * 1000:.0f} ms", end="")


class RNF02InterfazConPocaLuz(unittest.TestCase):
    """Tema oscuro con contraste suficiente (WCAG AA: 4,5:1 en texto normal)."""

    @staticmethod
    def _luminancia(hex_):
        canales = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lineal = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
        return 0.2126 * lineal[0] + 0.7152 * lineal[1] + 0.0722 * lineal[2]

    def contraste(self, a, b):
        la, lb = sorted((self._luminancia(a), self._luminancia(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)

    def test_RNF02_contraste_del_tema_oscuro(self):
        css = (RAIZ / "static" / "styles.css").read_text(encoding="utf-8")
        for color in ("#0b0d17", "#141827", "#1c2233", "#edf0fa", "#a9b1c7"):
            self.assertIn(color, css)                     # los colores medidos son los que usa la hoja
        pares = {"texto sobre fondo": ("#edf0fa", "#0b0d17"),
                 "texto sobre panel": ("#edf0fa", "#141827"),
                 "texto sobre tarjeta": ("#ecedfa", "#1c2233"),
                 "texto secundario sobre panel": ("#a9b1c7", "#141827"),
                 "texto secundario sobre tarjeta": ("#a9b1c7", "#1c2233"),
                 "aviso de conflicto": ("#ffb8a6", "#3a2420")}
        for nombre, (texto, fondo) in pares.items():
            self.assertGreaterEqual(self.contraste(texto, fondo), 4.5, nombre)

    def test_RNF02_formularios_con_etiquetas_y_validacion(self):
        html = (RAIZ / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="es"', html)
        self.assertIn('name="viewport"', html)
        campos = re.findall(r"<(?:input|select)\b[^>]*>", html)
        self.assertTrue(campos)
        etiquetas = set(re.findall(r'<label for="([^"]+)"', html))
        for campo in campos:
            identificador = re.search(r'\bid="([^"]+)"', campo)
            self.assertTrue(identificador and identificador.group(1) in etiquetas, campo)


class RNF03Escalabilidad(CasoConBase):
    """Nuevas reglas y géneros se incorporan como datos, sin tocar el motor."""

    def test_RNF03_regla_nueva_se_dispara_sin_cambiar_el_motor(self):
        bc = ConocimientoDAO(self.cx)
        with self.cx.transaccion():
            bc.crear_regla(28, "R28", "Rock con baile y canto", "Mantener el nivel de energía",
                           "SI el género actual es rock y el público baila y canta, ENTONCES mantener.",
                           "MANTENER_ENERGIA", {"genero_actual": ["rock"], "reaccion_publico": ["baila_y_canta"]})
        motor = MotorDJ(bc)
        codigos = [r["codigo"] for r in motor.disparar({"genero_actual": "rock", "reaccion_publico": "baila_y_canta"})]
        self.assertEqual(codigos, ["R28"])

    def test_RNF03_genero_nuevo_queda_disponible_para_canciones_y_reglas(self):
        bc = ConocimientoDAO(self.cx)
        with self.cx.transaccion():
            bc.crear_genero("Bachata", "bachata")
        servicio = ServicioSesion(self.cx)                   # el motor relee el conocimiento
        guardada = servicio.registrar_cancion(self.dj["id"], cancion("Nueva", 120, "8A", 5, genero="Bachata"))
        self.assertEqual(guardada["genero"], "Bachata")
        self.assertIn("bachata", servicio.motor.valores["genero_actual"])

    def test_RNF03_regla_desactivada_deja_de_dispararse(self):
        bc = ConocimientoDAO(self.cx)
        with self.cx.transaccion():
            self.assertTrue(bc.cambiar_estado_regla("R10", False))
        codigos = [r["codigo"] for r in MotorDJ(bc).disparar({"momento": "momento_principal"})]
        self.assertNotIn("R10", codigos)

    def test_RNF03_el_motor_no_nombra_reglas_en_la_inferencia(self):
        # Disparo, conflictos y selección dependen de los datos, no de códigos de regla.
        fuente = (RAIZ / "negocio.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        clase = next(n for n in arbol.body if isinstance(n, ast.ClassDef) and n.name == "MotorDJ")
        for metodo in clase.body:
            if isinstance(metodo, ast.FunctionDef) and metodo.name in ("disparar", "conflictos", "_seleccionar",
                                                                        "_transiciones", "_compatible", "_caso_bpm"):
                texto = ast.get_source_segment(fuente, metodo)
                sin_comentarios = re.sub(r"#.*", "", texto)
                self.assertIsNone(re.search(r"R\d\d", sin_comentarios), metodo.name)


class RNF04Disponibilidad(CasoConBase):
    """El servicio sigue respondiendo ante errores y peticiones simultáneas."""

    def setUp(self):
        super().setUp()
        app.config["DJ_DB"] = self.ruta
        self.cliente = app.test_client()

    def tearDown(self):
        app.config.pop("DJ_DB", None)
        super().tearDown()

    def test_RNF04_salud_comprueba_base_y_conocimiento(self):
        r = self.cliente.get("/api/salud")
        self.assertEqual((r.status_code, r.json["estado"], r.json["reglas_activas"]), (200, "ok", 27))

    def test_RNF04_salud_informa_503_si_la_base_no_abre(self):
        app.config["DJ_DB"] = os.path.join(self.tmp.name, "no", "existe", "x.db")
        r = self.cliente.get("/api/salud")
        self.assertEqual((r.status_code, r.json["estado"]), (503, "error"))

    def test_RNF04_un_error_no_tumba_el_servicio(self):
        self.assertEqual(self.cliente.post("/api/eventos/999/recomendar", json={}).status_code, 404)
        self.assertEqual(self.cliente.post(f"/api/eventos/{self.evento['id']}/recomendar",
                                           json={"contexto": {"momento": "inventado"}}).status_code, 400)
        self.assertEqual(self.cliente.post("/api/usuarios", data="x", content_type="text/plain").status_code, 400)
        self.assertEqual(self.cliente.post("/api/usuarios", data=b"x" * 600_000,
                                           content_type="application/json").status_code, 413)
        self.assertEqual(self.cliente.get("/api/salud").status_code, 200)

    def test_RNF04_peticiones_simultaneas_no_pierden_datos(self):
        resultados = []

        def trabajo(i):
            cliente = app.test_client()
            r = cliente.post(f"/api/eventos/{self.evento['id']}/recomendar",
                             json={"contexto": {"momento": "desarrollo"}})
            resultados.append(r.status_code)

        hilos = [threading.Thread(target=trabajo, args=(i,)) for i in range(12)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(resultados, [200] * 12)
        self.assertEqual(self.contar("contexto_evento"), 12)
        self.assertEqual(self.contar("recomendacion"), 12)

    def test_RNF04_base_nueva_se_inicializa_sola(self):
        with tempfile.TemporaryDirectory() as carpeta:
            app.config["DJ_DB"] = os.path.join(carpeta, "nueva.db")
            self.assertEqual(self.cliente.get("/api/salud").json["reglas_activas"], 27)


class RNF05FormatosYMetadatos(CasoConBase):
    """Formatos MP3, WAV y FLAC, y metadatos ID3."""

    def test_RNF05_acepta_los_tres_formatos_y_rechaza_otros(self):
        for i, formato in enumerate(("MP3", "WAV", "FLAC", "flac")):
            guardada = self.s.registrar_cancion(self.dj["id"], cancion(f"T{i}", 120, "8A", 5, formato=formato))
            self.assertEqual(guardada["formato"], formato.upper())
        for formato in ("OGG", "AAC", ""):
            with self.assertRaises(ValueError):
                self.s.registrar_cancion(self.dj["id"], cancion("Otro", 120, "8A", 5, formato=formato))

    def test_RNF05_conserva_metadatos_id3_y_ruta(self):
        id3 = {"TIT2": "Título", "TPE1": "Artista", "TBPM": "124", "TKEY": "8A", "TCON": "Salsa"}
        guardada = self.s.registrar_cancion(self.dj["id"], cancion("Con ID3", 124, "8A", 5, metadatos_id3=id3,
                                                                    ruta_archivo="musica/con_id3.mp3"))
        self.assertEqual(guardada["metadatos_id3"], id3)
        self.assertEqual(guardada["ruta_archivo"], "musica/con_id3.mp3")
        with self.assertRaises(ValueError):
            self.s.registrar_cancion(self.dj["id"], cancion("Mal ID3", 124, "8A", 5, metadatos_id3="texto"))


class RNF06Documentacion(unittest.TestCase):
    """El código está documentado: módulos, clases y funciones públicas."""

    def test_RNF06_modulos_clases_y_funciones_publicas_tienen_docstring(self):
        faltan = []
        for archivo in ("datos.py", "negocio.py", "app.py", "main.py"):
            arbol = ast.parse((RAIZ / archivo).read_text(encoding="utf-8"))
            if not ast.get_docstring(arbol):
                faltan.append(archivo)
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.ClassDef) and not ast.get_docstring(nodo):
                    faltan.append(f"{archivo}:{nodo.name}")
            if archivo == "negocio.py":
                for clase in (n for n in arbol.body if isinstance(n, ast.ClassDef)):
                    for m in clase.body:
                        if isinstance(m, ast.FunctionDef) and not m.name.startswith("_") \
                                and not ast.get_docstring(m):
                            faltan.append(f"{archivo}:{clase.name}.{m.name}")
        self.assertEqual(faltan, [])

    def test_RNF06_readme_describe_capas_y_ejecucion(self):
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        for texto in ("datos.py", "negocio.py", "app.py", "esquema.sql", "reglas.json", "unittest"):
            self.assertIn(texto, readme)


class ReglasAlineadas(CasoConBase):
    """R18 a R25: cada regla hace lo que dice su fila en la base de conocimiento."""

    def recomendar(self, genero, reaccion, actual=None):
        return self.s.recomendar(self.evento["id"], {"genero_actual": genero, "reaccion_publico": reaccion}, actual)

    def accion(self, resultado, nombre):
        return next(x for x in resultado["recomendaciones"] if x["accion"] == nombre)

    def test_R19_mantiene_genero_y_energia(self):
        actual, igual, cerca, _, _, _ = self.cargar(
            cancion("Actual", 100, "8A", 6, genero="Pop"), cancion("Pop igual", 100, "8A", 6, genero="Pop"),
            cancion("Pop cerca", 100, "8A", 7, genero="Pop"), cancion("Salsa igual", 100, "8A", 6, genero="Salsa"),
            cancion("Urbano igual", 100, "8A", 6, genero="Urbano"),
            cancion("Pop lejos", 100, "8A", 8, genero="Pop"))          # +2: ya no es el mismo nivel
        rec = self.accion(self.recomendar("pop", "baila_y_canta", actual), "MANTENER_ENERGIA")
        self.assertEqual(rec["reglas"], ["R19"])
        self.assertEqual([int(c["id"]) for c in rec["canciones"]], [igual, cerca])   # solo Pop, por cercanía
        self.assertEqual(int(rec["cancion_sugerida"]["id"]), igual)
        self.assertIn("género = Pop y energía a 1 punto o menos", rec["filtro"])

    def test_R18_y_R23_proponen_el_mismo_genero_infantil(self):
        actual, infantil, _ = self.cargar(cancion("Actual", 100, "8A", 5, genero="Infantil"),
                                          cancion("Infantil 2", 100, "8A", 6, genero="Infantil"),
                                          cancion("Pop", 100, "8A", 5, genero="Pop"))
        r18 = self.accion(self.recomendar("infantil", "positiva", actual), "MANTENER_GENERO")
        self.assertEqual((r18["reglas"], [int(c["id"]) for c in r18["canciones"]]), (["R18"], [infantil]))
        r23 = self.accion(self.recomendar("infantil", "rie_y_canta", actual), "MISMO_GENERO")
        self.assertEqual((r23["reglas"], [int(c["id"]) for c in r23["canciones"]]), (["R23"], [infantil]))
        self.assertTrue(any("marcada como conocida" in n for n in r23["notas"]))

    def test_R23_prefiere_las_canciones_conocidas(self):
        actual, normal, conocida = self.cargar(
            cancion("Actual", 100, "8A", 5, genero="Infantil"), cancion("Normal", 100, "8A", 5, genero="Infantil"),
            cancion("Clásico", 100, "8A", 8, genero="Infantil", conocida=True))
        rec = self.accion(self.recomendar("infantil", "rie_y_canta", actual), "MISMO_GENERO")
        self.assertEqual([int(c["id"]) for c in rec["canciones"]], [conocida, normal])
        self.assertEqual(rec["notas"], [])
        self.assertIn("conocida", rec["explicacion"])

    def test_R21_baja_la_energia_o_propone_comerciales(self):
        actual, baja, comercial, alta = self.cargar(
            cancion("Actual", 128, "8A", 7, genero="Rock"), cancion("Suave", 126, "8A", 4, genero="Rock"),
            cancion("Éxito", 128, "9A", 8, genero="Pop", comercial=True), cancion("Fuerte", 128, "8A", 9, genero="Rock"))
        r = self.recomendar("rock", "sentado", actual)
        rec = self.accion(r, "BAJAR_O_COMERCIAL")
        self.assertEqual(rec["reglas"], ["R21"])
        self.assertEqual([int(c["id"]) for c in rec["canciones"]], [comercial, baja])   # comercial primero
        self.assertNotIn(alta, [int(c["id"]) for c in rec["canciones"]])

    def test_R21_sigue_en_conflicto_con_subir_la_energia(self):
        disparadas = self.s.motor.disparar({"momento": "momento_principal", "genero_actual": "rock",
                                            "reaccion_publico": "sentado"})
        self.assertEqual([c["reglas"] for c in self.s.motor.conflictos(disparadas)], [["R10", "R21"]])

    def test_R26_y_R27_publico_que_se_retira(self):
        motor = self.s.motor
        cierre = motor.disparar({"momento": "cierre", "reaccion_publico": "se_retira"})
        self.assertEqual([(r["codigo"], r["accion"]) for r in cierre],
                         [("R11", "BAJAR_ENERGIA"), ("R26", "BAJAR_ENERGIA")])
        self.assertEqual(motor.conflictos(cierre), [])
        for momento in ("llegada", "inicio", "desarrollo", "momento_principal"):
            codigos = [r["codigo"] for r in motor.disparar({"momento": momento, "reaccion_publico": "se_retira"})]
            self.assertIn("R27", codigos)
            self.assertNotIn("R26", codigos)
        self.assertEqual(motor.disparar({"reaccion_publico": "se_retira"}), [])    # sin momento no se dispara
        r = self.s.recomendar(self.evento["id"], {"momento": "desarrollo", "reaccion_publico": "se_retira"})
        consulta = self.accion(r, "CONSULTAR")
        self.assertEqual((consulta["reglas"], consulta["canciones"]), (["R27"], []))

    def test_todos_los_valores_tienen_al_menos_una_regla(self):
        usados = {(v, x) for r in self.s.motor.reglas for v, xs in r["condiciones"].items() for x in xs}
        todos = {(v, x) for v, xs in self.s.motor.valores.items() for x in xs}
        self.assertEqual(len(todos), 35)
        self.assertEqual(todos - usados, set())

    def test_R24_consulta_y_no_propone_cancion(self):
        self.cargar(cancion("Actual", 100, "8A", 5, genero="Urbano"), cancion("Otra", 100, "8A", 5, genero="Urbano"))
        rec = self.accion(self.recomendar("urbano", "negativa"), "CONSULTAR")
        self.assertEqual((rec["reglas"], rec["canciones"], rec["cancion_sugerida"]), (["R24"], [], None))

    def test_R25_busca_otra_cancion_compatible_y_pide_consultar_la_causa(self):
        actual, otra, lejos = self.cargar(cancion("Actual", 100, "8A", 5), cancion("Otra", 104, "9A", 5),
                                          cancion("Lejos", 100, "2B", 5))
        rec = self.accion(self.recomendar("merengue", "sin_reaccion", actual), "BUSCAR_OTRA")
        self.assertEqual((rec["reglas"], [int(c["id"]) for c in rec["canciones"]]), (["R25"], [otra]))
        self.assertTrue(any("Consultar la causa" in n for n in rec["notas"]))

    def test_R18_a_R25_exigen_genero_y_reaccion_como_en_la_base(self):
        pares = {"R18": ("infantil", "positiva"), "R19": ("urbano", "baila_y_canta"), "R20": ("salsa", "baila_poco"),
                 "R21": ("rock", "sentado"), "R22": ("vallenato", "solicita_otro_genero"),
                 "R23": ("infantil", "rie_y_canta"), "R24": ("pop", "negativa"), "R25": ("merengue", "sin_reaccion")}
        motor = self.s.motor
        for codigo, (genero, reaccion) in pares.items():
            disparadas = [r["codigo"] for r in motor.disparar({"genero_actual": genero, "reaccion_publico": reaccion})]
            self.assertEqual(disparadas, [codigo])
            self.assertEqual(motor.disparar({"reaccion_publico": reaccion}), [])      # sin género no se dispara
        self.assertEqual(motor.disparar({"genero_actual": "rock", "reaccion_publico": "positiva"}), [])

    def test_escenarios_E1_a_E6_del_documento(self):
        escenarios = {
            "E1": (("cumpleanos", "inicio", "ninos", "infantil", "rie_y_canta"), ["R01", "R08", "R12", "R23"]),
            "E2": (("discoteca", "desarrollo", "jovenes", "pop", "baila_y_canta"), ["R05", "R09", "R14", "R19"]),
            "E3": (("boda", "cierre", "adultos", "salsa", "baila_poco"), ["R02", "R11", "R15", "R20"]),
            "E4": (("reunion_familiar", "llegada", "variadas", "popular", "solicita_otro_genero"),
                   ["R06", "R07", "R17", "R22"]),
            "E5": (("empresarial", "momento_principal", "adultos_mayores", "electronica", "sentado"),
                   ["R03", "R10", "R16", "R21"]),
            "E6": (("tematica", "desarrollo", "adolescentes", "merengue", "sin_reaccion"),
                   ["R04", "R09", "R13", "R25"])}
        variables = ("tipo_evento", "momento", "grupo_edad", "genero_actual", "reaccion_publico")
        conflictos = {}
        for nombre, (valores, esperadas) in escenarios.items():
            disparadas = self.s.motor.disparar(dict(zip(variables, valores)))
            self.assertEqual([r["codigo"] for r in disparadas], esperadas, nombre)
            conflictos[nombre] = [c["reglas"] for c in self.s.motor.conflictos(disparadas)]
        self.assertEqual(conflictos["E3"], [["R20", "R11"]])
        self.assertEqual(conflictos["E5"], [["R10", "R21"]])
        self.assertEqual([n for n, c in conflictos.items() if c], ["E3", "E5"])


if __name__ == "__main__":
    unittest.main()
