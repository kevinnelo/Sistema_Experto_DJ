"""Datos de demostración: un catálogo ficticio y cinco casos que recorren el árbol de decisión.

Los títulos y artistas son inventados. ServicioSesion.cargar_ejemplos ejecuta el motor real sobre
cada caso, de modo que el historial de ejemplo muestra resultados auténticos del sistema.
"""
PREFIJO_EJEMPLO = "Ejemplo · "


def _c(titulo, artista, genero, bpm, camelot, energia, duracion, conocida=False, comercial=False):
    return {"titulo": titulo, "artista": artista, "genero": genero, "bpm": bpm, "tonalidad_camelot": camelot,
            "energia": energia, "duracion_seg": duracion, "formato": "MP3", "conocida": conocida,
            "comercial": comercial}


CANCIONES_EJEMPLO = [
    _c("Noche de Barrio", "Orquesta La Séptima", "Salsa", 124, "8A", 5, 252),
    _c("Tumbao Lento", "Orquesta La Séptima", "Salsa", 118, "7A", 3, 268, conocida=True),
    _c("Rumba Arriba", "Son del Puente", "Salsa", 126, "9A", 7, 240),
    _c("Merengue del Puerto", "Los Marineros", "Merengue", 135, "10A", 8, 214, comercial=True),
    _c("Calle 80", "Kiro MC", "Urbano", 96, "6A", 7, 198),
    _c("Sin Freno", "Kiro MC", "Urbano", 98, "7A", 8, 205, comercial=True),
    _c("Luz Baja", "Naya", "Urbano", 94, "5A", 7, 221),
    _c("La Ronda del Sol", "Los Pequeños Gigantes", "Infantil", 110, "4B", 5, 150),
    _c("El Tren de Colores", "Los Pequeños Gigantes", "Infantil", 112, "5B", 6, 162, conocida=True),
    _c("Salta Salta", "Tía Lulú", "Infantil", 108, "4B", 5, 144),
    _c("Motor Encendido", "Vértigo", "Rock", 128, "9A", 7, 236),
    _c("Carretera Lenta", "Vértigo", "Rock", 120, "8A", 4, 258),
    _c("Trueno", "Los Cables", "Rock", 132, "10A", 9, 227),
    _c("Himno de Radio", "Clara Mar", "Pop", 126, "9B", 6, 209, conocida=True, comercial=True),
    _c("Camino del Valle", "Los Hermanos Daza", "Vallenato", 100, "3A", 5, 274, conocida=True),
    _c("Acordeón de Madrugada", "Los Hermanos Daza", "Vallenato", 96, "2A", 4, 290),
]

CASOS_EJEMPLO = [
    {"evento": "Boda Pérez–Gómez", "tipo_evento": "boda", "duracion_min": 300, "lugar": "Salón Los Arrayanes",
     "contexto": {"momento": "cierre", "grupo_edad": "adultos", "reaccion_publico": "baila_poco"},
     "suena": "Noche de Barrio", "finalizado": True,
     "decisiones": {"BAJAR_ENERGIA": {"accion": "ACEPTADA", "motivo": "Corresponde al cierre de la boda"},
                    "SUBIR_ENERGIA": {"accion": "RECHAZADA", "motivo": "Ya estamos despidiendo a los invitados"},
                    "CRITERIO": {"accion": "ACEPTADA"}}},
    {"evento": "Viernes en discoteca", "tipo_evento": "discoteca", "duracion_min": 360, "lugar": "Club Zona T",
     "contexto": {"momento": "desarrollo", "grupo_edad": "jovenes", "reaccion_publico": "baila_y_canta"},
     "suena": "Calle 80",
     "decisiones": {"MANTENER_ENERGIA": {"accion": "ACEPTADA", "motivo": "La pista está llena, sigo en la misma línea"}}},
    {"evento": "Cumpleaños de Sofía", "tipo_evento": "cumpleanos", "duracion_min": 180, "lugar": "Casa de la familia",
     "contexto": {"momento": "inicio", "grupo_edad": "ninos", "reaccion_publico": "rie_y_canta"},
     "suena": "La Ronda del Sol", "finalizado": True,
     "decisiones": {"MISMO_GENERO": {"accion": "MODIFICADA", "cancion_final": "Salta Salta",
                                     "motivo": "La pidió la cumpleañera"},
                    "CRITERIO": {"accion": "ACEPTADA"}}},
    {"evento": "Fiesta de fin de año de la empresa", "tipo_evento": "empresarial", "duracion_min": 240,
     "lugar": "Hotel del Parque",
     "contexto": {"momento": "momento_principal", "grupo_edad": "adultos", "reaccion_publico": "sentado"},
     "suena": "Motor Encendido",
     "decisiones": {"BAJAR_O_COMERCIAL": {"accion": "ACEPTADA", "motivo": "Están cenando; paso a algo comercial"},
                    "SUBIR_ENERGIA": {"accion": "RECHAZADA", "motivo": "Todavía no han terminado de comer"}}},
    {"evento": "Reunión familiar de domingo", "tipo_evento": "reunion_familiar", "duracion_min": 240,
     "lugar": "Finca El Recuerdo",
     "contexto": {"momento": "desarrollo", "grupo_edad": "variadas", "reaccion_publico": "se_retira"},
     "suena": "Camino del Valle",
     "decisiones": {"CONSULTAR": {"accion": "ACEPTADA",
                                  "motivo": "Pregunté: se iban a almorzar, no era por la música"}}},
]
