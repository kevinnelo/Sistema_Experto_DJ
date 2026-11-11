"""Apoyo común de las pruebas: base temporal y datos de ejemplo."""
import os
import tempfile
import unittest

from datos import ConexionBD
from negocio import ServicioSesion


def cancion(titulo, bpm, camelot, energia, genero="Salsa", **extra):
    base = {"titulo": titulo, "artista": "Artista", "genero": genero, "bpm": bpm,
            "tonalidad_camelot": camelot, "energia": energia, "duracion_seg": 200, "formato": "MP3"}
    base.update(extra)
    return base


class CasoConBase(unittest.TestCase):
    """Crea una base SQLite en un archivo temporal y un DJ con un evento."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = os.path.join(self.tmp.name, "prueba.db")
        self.cx = ConexionBD(self.ruta)
        self.s = ServicioSesion(self.cx)
        self.dj = self.s.registrar_dj("DJ Prueba", "dj@ejemplo.com")
        self.evento = self.s.crear_evento(self.dj["id"], "Fiesta de prueba", "discoteca", 240)

    def tearDown(self):
        self.cx.cerrar()
        self.tmp.cleanup()

    def cargar(self, *canciones):
        """Registra canciones y devuelve sus ids en el mismo orden."""
        return [self.s.registrar_cancion(self.dj["id"], c)["id"] for c in canciones]

    def contar(self, tabla):
        return self.cx.db.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
