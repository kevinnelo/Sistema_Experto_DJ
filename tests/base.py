"""Apoyo común de las pruebas: esquema temporal de PostgreSQL y datos de ejemplo.

Las pruebas con base de datos necesitan un servidor PostgreSQL. La URL se toma de
PRUEBAS_DATABASE_URL o, si no existe, de DATABASE_URL (variables de entorno o archivo .env).
Cada prueba crea su propio esquema y lo borra al terminar: no toca los datos de la aplicación.
"""
import os
import unittest
import uuid

import psycopg

from datos import ConexionBD, cargar_env
from negocio import ServicioSesion

cargar_env()
URL = os.getenv("PRUEBAS_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
CLAVE = "clave-segura-1"


def cancion(titulo, bpm, camelot, energia, genero="Salsa", **extra):
    base = {"titulo": titulo, "artista": "Artista", "genero": genero, "bpm": bpm,
            "tonalidad_camelot": camelot, "energia": energia, "duracion_seg": 200, "formato": "MP3"}
    base.update(extra)
    return base


def esquema_nuevo():
    return "prueba_" + uuid.uuid4().hex[:16]


def borrar_esquema(esquema):
    with psycopg.connect(URL, autocommit=True) as db:
        db.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")


class CasoConBase(unittest.TestCase):
    """Crea un esquema temporal y un DJ con un evento."""

    def setUp(self):
        if not URL:
            self.skipTest("Defina PRUEBAS_DATABASE_URL o DATABASE_URL para ejecutar las pruebas con base de datos.")
        self.esquema = esquema_nuevo()
        try:
            self.cx = ConexionBD(URL, self.esquema)
        except psycopg.OperationalError as error:
            self.skipTest(f"No hay conexión con PostgreSQL: {error}")
        self.addCleanup(borrar_esquema, self.esquema)
        self.addCleanup(lambda: self.cx.cerrar())
        self.s = ServicioSesion(self.cx)
        self.dj = self.s.registrar_usuario("DJ Prueba", "dj@ejemplo.com", CLAVE)
        self.u = self.dj["id"]
        self.evento = self.s.crear_evento(self.u, "Fiesta de prueba", "discoteca", 240)

    def cargar(self, *canciones):
        """Registra canciones y devuelve sus ids en el mismo orden."""
        return [self.s.registrar_cancion(self.u, c)["id"] for c in canciones]

    def contar(self, tabla):
        return self.cx.db.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]

    def recomendar(self, contexto, actual=None, evento=None):
        return self.s.recomendar(self.u, evento or self.evento["id"], contexto, actual)
