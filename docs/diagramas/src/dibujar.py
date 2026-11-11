"""Genera los diagramas dibujados a mano (SVG): caja negra, flujo de datos y clases DAO.

Uso: python3 docs/diagramas/src/dibujar.py   (escribe los .svg junto a los .png)
"""
from html import escape
from pathlib import Path

SALIDA = Path(__file__).resolve().parent.parent
AZUL, BORDE, TINTA, LINEA = "#eaf2fb", "#1f4e79", "#1c2b3a", "#33475b"


class Lienzo:
    def __init__(self, ancho, alto, titulo):
        self.w, self.h, self.p = ancho, alto, []
        self.p.append(f'<rect width="{ancho}" height="{alto}" fill="#ffffff"/>')
        self.texto(ancho / 2, 34, titulo, 21, negrita=True)

    def texto(self, x, y, t, tam=14, ancla="middle", negrita=False, color=TINTA, cursiva=False, fondo=False):
        lineas = t.split("\n")
        if fondo:
            ancho = max(len(l) for l in lineas) * tam * 0.56 + 10
            x0 = x - ancho / 2 if ancla == "middle" else (x - 5 if ancla == "start" else x - ancho + 5)
            self.p.append(f'<rect x="{x0:.0f}" y="{y - tam:.0f}" width="{ancho:.0f}" '
                          f'height="{len(lineas) * tam * 1.3 + 4:.0f}" fill="#ffffff" opacity="0.92"/>')
        estilo = f'font-size="{tam}" text-anchor="{ancla}" fill="{color}"'
        if negrita:
            estilo += ' font-weight="700"'
        if cursiva:
            estilo += ' font-style="italic"'
        for i, l in enumerate(lineas):
            sangria = len(l) - len(l.lstrip(" "))
            l = "\u00a0" * sangria + l.lstrip(" ")
            self.p.append(f'<text x="{x}" y="{y + i * tam * 1.3:.1f}" {estilo}>{escape(l)}</text>')

    def caja(self, x, y, w, h, lineas, relleno=AZUL, borde=BORDE, color=TINTA, radio=8, tam=14, grosor=1.4):
        """lineas: [(texto, negrita)]; centradas vertical y horizontalmente."""
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radio}" fill="{relleno}" '
                      f'stroke="{borde}" stroke-width="{grosor}"/>')
        alto = len(lineas) * tam * 1.35
        y0 = y + (h - alto) / 2 + tam
        for i, (t, negrita) in enumerate(lineas):
            self.texto(x + w / 2, y0 + i * tam * 1.35, t, tam, negrita=negrita, color=color)

    def flecha(self, puntos, etiqueta=None, pos=None, punta="fin", discontinua=False, ancla="middle", tam=12.5):
        d = "M" + " L".join(f"{x},{y}" for x, y in puntos)
        extra = ' stroke-dasharray="6 5"' if discontinua else ""
        marcas = {"fin": ' marker-end="url(#f)"', "abierta": ' marker-end="url(#a)"',
                  "herencia": ' marker-end="url(#h)"', "rombo": ' marker-start="url(#r)"',
                  "rombo_abierta": ' marker-start="url(#r)" marker-end="url(#a)"', "nada": ""}[punta]
        self.p.append(f'<path d="{d}" fill="none" stroke="{LINEA}" stroke-width="1.5"{extra}{marcas}/>')
        if etiqueta:
            x, y = pos
            self.texto(x, y, etiqueta, tam, ancla=ancla, color="#26394d", fondo=True)

    def svg(self):
        defs = ('<defs>'
                f'<marker id="f" markerWidth="11" markerHeight="9" refX="10" refY="4.5" orient="auto"><path d="M0,0 L11,4.5 L0,9 z" fill="{LINEA}"/></marker>'
                f'<marker id="a" markerWidth="12" markerHeight="10" refX="11" refY="5" orient="auto"><path d="M0,0 L11,5 L0,10" fill="none" stroke="{LINEA}" stroke-width="1.5"/></marker>'
                f'<marker id="h" markerWidth="16" markerHeight="14" refX="15" refY="7" orient="auto"><path d="M0,0 L15,7 L0,14 z" fill="#ffffff" stroke="{LINEA}" stroke-width="1.4"/></marker>'
                f'<marker id="r" markerWidth="20" markerHeight="12" refX="1" refY="6" orient="auto"><path d="M1,6 L10,1 L19,6 L10,11 z" fill="{LINEA}"/></marker>'
                '</defs>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" font-family="Arial, Helvetica, sans-serif">{defs}{"".join(self.p)}</svg>')

    def guardar(self, nombre):
        (SALIDA / nombre).write_text(self.svg(), encoding="utf-8")


# ------------------------------------------------------------------ 1. caja negra
def caja_negra():
    L = Lienzo(1400, 700, "Diagrama de caja negra · Sistema experto DJ")
    entradas = [("Evento", "tipo de evento"),
                ("Contexto", "momento · edad predominante\ngénero actual · reacción del público"),
                ("Catálogo del DJ", "género · BPM · tonalidad Camelot · energía\nconocida · comercial · formato"),
                ("Canción que suena", "elegida del catálogo"),
                ("Decisión del DJ", "aceptar · rechazar · modificar")]
    salidas = [("Reglas activadas", "con los hechos que las cumplen"),
               ("Conflictos", "subir frente a bajar la energía\n(los resuelve el DJ)"),
               ("Recomendaciones", "canción sugerida y otras candidatas"),
               ("Técnicas de transición", "según la diferencia de BPM\ny el cambio de género"),
               ("Explicación e historial", "por qué se recomendó\ny qué decidió el DJ")]
    L.texto(230, 78, "ENTRADAS", 14, negrita=True, color=BORDE)
    L.texto(1170, 78, "SALIDAS", 14, negrita=True, color=BORDE)
    for i, (titulo, detalle) in enumerate(entradas):
        y = 95 + i * 116
        L.caja(40, y, 380, 96, [(titulo, True)] + [(d, False) for d in detalle.split("\n")])
        L.flecha([(420, y + 48), (548, y + 48)])
    for i, (titulo, detalle) in enumerate(salidas):
        y = 95 + i * 116
        L.caja(980, y, 380, 96, [(titulo, True)] + [(d, False) for d in detalle.split("\n")])
        L.flecha([(850, y + 48), (978, y + 48)])
    L.caja(550, 95, 300, 560, [("SISTEMA EXPERTO DJ", True), ("", False), ("MotorDJ", True),
                               ("Reglas SI–ENTONCES", False), ("R01–R27", False), ("", False),
                               ("Encadenamiento", False), ("hacia adelante", False), ("", False),
                               ("Sin probabilidades", False), ("ni hipótesis", False)],
           relleno=BORDE, color="#ffffff", tam=16)
    L.texto(700, 685, "El DJ solo ve entradas y salidas; el interior se detalla en el diagrama de flujo de datos.", 12.5,
            color="#4a5b6c", cursiva=True)
    L.guardar("01_caja_negra.svg")


# ------------------------------------------------------------------ 2. flujo de datos
def flujo_datos():
    L = Lienzo(1640, 1290, "Diagrama de flujo de datos (nivel 1) · Sistema experto DJ")
    PX, PW, PH = 560, 330, 96                 # columna de procesos
    filas = [70, 225, 395, 565, 735, 905, 1075]
    nombres = ["Gestionar el catálogo\n(validar canción)", "Registrar evento y contexto\n(validar valores)",
               "Disparar reglas y\ndetectar conflictos", "Seleccionar canciones\n(género, energía, Camelot)",
               "Asignar técnicas de transición\n(caso de BPM y cambio de género)",
               "Explicar y guardar\nla recomendación", "Registrar la decisión\ndel DJ"]

    def proceso(i):
        y = filas[i]
        L.caja(PX, y, PW, PH, [(f"{i + 1}", True)] + [(t, False) for t in nombres[i].split("\n")], radio=22)

    def almacen(x, y, w, cod, nombre, tablas, h=58):
        L.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff8e6" stroke="none"/>')
        L.p.append(f'<path d="M{x + w},{y} L{x},{y} L{x},{y + h} L{x + w},{y + h}" fill="none" stroke="#8a6d1f" stroke-width="1.5"/>')
        L.p.append(f'<line x1="{x + 46}" y1="{y}" x2="{x + 46}" y2="{y + h}" stroke="#8a6d1f" stroke-width="1.5"/>')
        L.texto(x + 23, y + h / 2 + 5, cod, 14, negrita=True)
        L.texto(x + 56, y + 23, nombre, 14, ancla="start", negrita=True)
        L.texto(x + 56, y + 23 + 19, tablas, 11.5, ancla="start", color="#4a5b6c")

    # entidad externa (el mismo DJ a lo largo de todo el flujo)
    L.caja(40, 70, 150, 1101, [("DJ", True), ("(entidad", False), ("externa)", False)], relleno="#eef0f3",
           borde="#4a5b6c", radio=0, tam=16)
    for i in range(7):
        proceso(i)
    X0, X1 = 190, PX                           # tramo DJ <-> procesos
    cx = (X0 + X1) / 2

    def dj_a(i, dy, etiqueta):
        y = filas[i] + dy
        L.flecha([(X0, y), (X1 - 2, y)], etiqueta, (cx, y - 9 - 16 * etiqueta.count("\n")))

    def a_dj(i, dy, etiqueta):
        y = filas[i] + dy
        L.flecha([(X1, y), (X0 + 2, y)], etiqueta, (cx, y - 9 - 16 * etiqueta.count("\n")))

    dj_a(0, 30, "datos de la canción")
    a_dj(0, 72, "catálogo o motivo del rechazo")
    dj_a(1, 48, "evento, contexto y\ncanción que suena")
    a_dj(5, 48, "reglas activadas, conflictos,\ncanción sugerida, técnicas y explicación")
    dj_a(6, 30, "aceptar, rechazar o modificar")
    a_dj(6, 72, "historial de decisiones")

    # cadena de procesos
    xc = PX + PW / 2
    for i, etiqueta in ((1, "hechos del contexto"), (2, "acciones de las reglas disparadas"),
                        (3, "canciones candidatas"), (4, "candidatas con sus técnicas")):
        L.flecha([(xc, filas[i] + PH), (xc, filas[i + 1] - 2)], etiqueta,
                 (xc + 12, (filas[i] + PH + filas[i + 1]) / 2 + 4), ancla="start")
    # reglas y conflictos van directo a la explicación (carril izquierdo)
    xl = PX - 46
    L.flecha([(PX, filas[2] + 70), (xl, filas[2] + 70), (xl, filas[5] + 20), (PX - 2, filas[5] + 20)],
             "reglas disparadas\ny conflictos", (xl - 8, filas[3] + 40), ancla="end")

    # almacenes
    AX, AW = 1070, 300                          # almacenes transaccionales
    BX, BW = 1420, 190                          # base de conocimiento (única, a lo alto)
    R = PX + PW
    ca = (R + AX) / 2
    almacen(AX, filas[0] + 19, AW, "D2", "Catálogo musical", "cancion · genero_musical")
    L.flecha([(R, filas[0] + 34), (AX - 2, filas[0] + 34)], "canción validada", (ca, filas[0] + 25))
    L.flecha([(AX, filas[0] + 64), (R + 2, filas[0] + 64)], "catálogo", (ca, filas[0] + 83))

    almacen(AX, filas[1] - 2, AW, "D3", "Eventos y contextos", "evento · contexto_evento")
    L.flecha([(R, filas[1] + 26), (AX - 2, filas[1] + 26)], "evento y fotografía\ndel contexto", (ca, filas[1] - 1))

    almacen(AX, filas[3] - 2, AW, "D2", "Catálogo musical", "cancion · genero_musical")
    L.flecha([(AX, filas[3] + 26), (R + 2, filas[3] + 26)], "catálogo y\ncanción actual", (ca, filas[3] - 1))

    almacen(AX, filas[5] + 19, AW, "D4", "Recomendaciones",
            "recomendacion · recomendacion_regla\nrecomendacion_transicion", h=66)
    L.flecha([(R, filas[5] + 48), (AX - 2, filas[5] + 48)], "recomendación,\nreglas y técnicas", (ca, filas[5] + 22))
    # D4 -> 7 : baja desde el almacén
    L.flecha([(AX + 150, filas[5] + 85), (AX + 150, filas[6] + 26), (R + 2, filas[6] + 26)],
             "recomendación\npendiente", (ca, filas[6] - 1))
    almacen(AX, filas[6] + 50, AW, "D5", "Decisiones", "decision_dj")
    L.flecha([(R, filas[6] + 78), (AX - 2, filas[6] + 78)], "decisión", (ca, filas[6] + 97))

    # base de conocimiento: un solo almacén para los procesos 2 a 5
    yb0, yb1 = filas[1] - 2, filas[4] + PH + 2
    L.p.append(f'<rect x="{BX}" y="{yb0}" width="{BW}" height="{yb1 - yb0}" fill="#fff8e6" stroke="none"/>')
    L.p.append(f'<path d="M{BX + BW},{yb0} L{BX},{yb0} L{BX},{yb1} L{BX + BW},{yb1}" fill="none" stroke="#8a6d1f" stroke-width="1.5"/>')
    L.p.append(f'<line x1="{BX}" y1="{yb0 + 40}" x2="{BX + BW}" y2="{yb0 + 40}" stroke="#8a6d1f" stroke-width="1.5"/>')
    L.texto(BX + BW / 2, yb0 + 26, "D1", 14, negrita=True)
    ym = (yb0 + yb1) / 2
    L.texto(BX + BW / 2, ym - 86, "Base de\nconocimiento", 15, negrita=True)
    L.texto(BX + BW / 2, ym - 26, "variable\nvalor_variable\nregla\ncondicion_regla\nparametro_experto\n"
            "tecnica_transicion\ntransicion_regla", 12, color="#4a5b6c")
    cb = (R + BX) / 2 + 150
    for i, dy, etiqueta in ((1, 78, "valores permitidos de cada variable"), (2, 48, "reglas activas y sus condiciones"),
                            (3, 78, "distancia máxima en la rueda de Camelot"),
                            (4, 48, "umbrales de BPM y técnicas por caso")):
        y = filas[i] + dy
        L.flecha([(BX, y), (R + 2, y)], etiqueta, (R + 30, y - 8), ancla="start")

    # leyenda
    yl = 1215
    L.caja(40, yl, 150, 40, [("Entidad externa", False)], relleno="#eef0f3", borde="#4a5b6c", radio=0, tam=12.5)
    L.caja(220, yl, 150, 40, [("Proceso", False)], radio=18, tam=12.5)
    almacen(400, yl - 8, 210, "Dn", "Almacén de datos", "tablas de SQLite", h=56)
    L.flecha([(650, yl + 20), (730, yl + 20)])
    L.texto(742, yl + 25, "Flujo de datos", 12.5, ancla="start")
    L.texto(880, yl + 25, "D2 aparece dos veces para no cruzar flujos; es el mismo almacén. "
            "Los procesos 2 a 7 corren en transacciones.", 12.5, ancla="start", color="#4a5b6c", cursiva=True)
    L.guardar("02_flujo_de_datos.svg")


# ------------------------------------------------------------------ 3. clases DAO
def clases():
    L = Lienzo(1580, 1300, "Diagrama de clases · capa de datos (DAO) y su uso desde la capa de negocio")
    T = 12.5

    def clase(x, y, w, nombre, atributos, metodos, estereotipo=None, relleno=AZUL):
        cab = 46 if estereotipo else 32
        alto = cab + (len(atributos) * 17 + 12 if atributos else 10) + len(metodos) * 17 + 12
        L.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{alto}" fill="{relleno}" stroke="{BORDE}" stroke-width="1.4"/>')
        if estereotipo:
            L.texto(x + w / 2, y + 17, f"«{estereotipo}»", 11.5)
            L.texto(x + w / 2, y + 35, nombre, 14.5, negrita=True, cursiva=True)
        else:
            L.texto(x + w / 2, y + 21, nombre, 14.5, negrita=True)
        yy = y + cab
        L.p.append(f'<line x1="{x}" y1="{yy}" x2="{x + w}" y2="{yy}" stroke="{BORDE}" stroke-width="1.2"/>')
        for i, a in enumerate(atributos):
            L.texto(x + 9, yy + 17 + i * 17, a, T, ancla="start")
        yy += len(atributos) * 17 + 12 if atributos else 10
        L.p.append(f'<line x1="{x}" y1="{yy}" x2="{x + w}" y2="{yy}" stroke="{BORDE}" stroke-width="1.2"/>')
        for i, m in enumerate(metodos):
            L.texto(x + 9, yy + 17 + i * 17, m, T, ancla="start")
        return alto

    # ---- capa de negocio (negocio.py) y conexión
    L.texto(60, 70, "datos.py", 12.5, ancla="start", color="#4a5b6c", cursiva=True)
    L.texto(540, 70, "negocio.py", 12.5, ancla="start", color="#4a5b6c", cursiva=True)
    hc = clase(60, 80, 350, "ConexionBD", ["+ ruta: str", "+ db: sqlite3.Connection"],
               ["+ __init__(ruta = None)", "+ transaccion(): ContextManager", "+ cerrar()",
                "– _leer_conocimiento(): dict", "– _cargar(conocimiento: dict)"])
    hs = clase(540, 80, 470, "ServicioSesion", ["+ conexion: ConexionBD", "+ motor: MotorDJ"],
               ["+ registrar_dj(nombre, correo): dict", "+ registrar_cancion(usuario_id, datos): dict",
                "+ catalogo(usuario_id): list", "+ eliminar_cancion(usuario_id, cancion_id)",
                "+ crear_evento(usuario_id, nombre, tipo_evento, duracion_min,",
                "      inicio_previsto, lugar, aforo_estimado): dict",
                "+ eventos_de(usuario_id): list", "+ finalizar_evento(evento_id): dict",
                "+ recomendar(evento_id, contexto, cancion_actual_id): dict",
                "+ explicacion(recomendacion_id): dict",
                "+ decidir(recomendacion_id, accion, cancion_final_id, motivo): dict",
                "+ historial(evento_id): list"])
    hm = clase(1140, 80, 400, "MotorDJ", ["+ reglas: list", "+ parametros: dict", "+ generos: dict", "+ valores: dict"],
               ["+ validar_contexto(contexto): dict", "+ validar_cancion(cancion, etiqueta): dict",
                "+ validar_catalogo(catalogo): list", "+ disparar(contexto): list",
                "+ conflictos(disparadas): list",
                "+ recomendar(contexto, catalogo, cancion_actual_id): dict"])
    L.flecha([(540, 150), (412, 150)], "abre\ntransacciones", (476, 122), punta="abierta")
    L.flecha([(1010, 150), (1138, 150)], "1", (1120, 140), punta="rombo_abierta")
    L.texto(1075, 172, "ejecuta", 12.5, color="#26394d")

    # ---- familia DAO
    FY = 475
    FH = 715
    L.p.append(f'<rect x="30" y="{FY}" width="1520" height="{FH}" rx="12" fill="#f7f9fc" stroke="#9fb3c8" '
               f'stroke-width="1.3" stroke-dasharray="7 5"/>')
    L.texto(1535, FY + 24, "Clases DAO (datos.py)", 13, ancla="end", color="#4a5b6c", cursiva=True)
    cols, W = [60, 432, 804, 1176], 344
    hd = clase(cols[0], FY + 40, W, "_DAO", ["# db: sqlite3.Connection"], ["+ __init__(conexion: ConexionBD)"],
               estereotipo="abstracta", relleno="#ffffff")
    YA = FY + 215
    ha = [clase(cols[0], YA, W, "UsuarioDAO", [], ["+ crear(nombre, correo, rol = 'DJ'): int",
                                                 "+ obtener(usuario_id): dict", "+ por_correo(correo): dict"]),
          clase(cols[1], YA, W, "CancionDAO", [], ["+ crear(usuario_id, cancion: dict): int", "+ listar(usuario_id): list",
                                                 "+ obtener(cancion_id): dict",
                                                 "+ eliminar(cancion_id, usuario_id): bool"]),
          clase(cols[2], YA, W, "EventoDAO", [], ["+ crear(usuario_id, nombre, tipo_evento_id,",
                                                "      inicio_previsto, duracion_min, lugar, aforo): int",
                                                "+ obtener(evento_id): dict", "+ listar(usuario_id): list",
                                                "+ cambiar_estado(evento_id, estado)"]),
          clase(cols[3], YA, W, "ConocimientoDAO", [], ["+ variables(): dict", "+ valores(variable): list",
                                                      "+ id_valor(variable, codigo): int", "+ reglas(): list",
                                                      "+ crear_regla(id, codigo, nombre, conclusion,",
                                                      "      descripcion, accion, condiciones)",
                                                      "+ cambiar_estado_regla(codigo, activa): bool",
                                                      "+ crear_genero(nombre, codigo, etiqueta)",
                                                      "+ parametros(): dict", "+ generos(): dict",
                                                      "+ transiciones(caso): list"])]
    YB = YA + 300
    hb = [clase(cols[0], YB, W, "ContextoDAO", [], ["+ registrar(evento_id, ids_valores,",
                                                  "      cancion_actual_id): int",
                                                  "+ obtener(contexto_id): dict", "+ listar(evento_id): list"]),
          clase(cols[1], YB, W, "RecomendacionDAO", [], ["+ crear(evento_id, contexto_id, cancion_id,",
                                                       "      explicacion, tiempo_ms, codigos_regla,",
                                                       "      ids_transicion): int",
                                                       "+ obtener(recomendacion_id): dict",
                                                       "+ listar(evento_id): list"]),
          clase(cols[2], YB, W, "DecisionDAO", [], ["+ registrar(recomendacion_id, accion,",
                                                  "      cancion_final_id, motivo): int",
                                                  "+ historial(evento_id): list"]),
          clase(cols[3], YB, W, "RepositorioConocimiento", ["+ conexion: ConexionBD"],
                ["+ __init__(ruta = ':memory:')", "+ cerrar()"])]

    # herencia: bus horizontal bajo _DAO
    xd = cols[0] + W / 2
    yd = FY + 40 + hd
    bus = YA - 28
    # fila A
    L.flecha([(xd, bus), (xd, yd + 1)], punta="herencia")
    L.p.append(f'<path d="M{cols[0] + 60},{bus} L{cols[3] + 60},{bus}" fill="none" stroke="{LINEA}" stroke-width="1.5"/>')
    for i in (0, 1, 2):
        x = cols[i] + W / 2 if i else cols[0] + 60
        L.p.append(f'<path d="M{x},{bus} L{x},{YA}" fill="none" stroke="{LINEA}" stroke-width="1.5"/>')
    L.p.append(f'<path d="M{cols[3] + 60},{bus} L{cols[3] + 60},{YA}" fill="none" stroke="{LINEA}" stroke-width="1.5"/>')
    # fila B: bajan por los pasillos entre columnas
    for i in (0, 1, 2):
        xp = cols[i] + W + 14
        L.p.append(f'<path d="M{xp},{bus} L{xp},{YB + 20} L{cols[i] + W},{YB + 20}" fill="none" stroke="{LINEA}" stroke-width="1.5"/>')
    L.texto(xd + 14, yd + 22, "herencia", 12, ancla="start", color="#26394d")
    # RepositorioConocimiento hereda de ConocimientoDAO
    xr = cols[3] + W / 2
    L.flecha([(xr, YB), (xr, YA + ha[3] + 1)], punta="herencia")

    # _DAO usa la conexión
    L.flecha([(cols[0] + 120, FY + 40), (cols[0] + 120, 80 + hc + 2)], "comparte la conexión\n(misma transacción)",
             (cols[0] + 134, 80 + hc + 44), punta="abierta", ancla="start")
    # ServicioSesion compone un DAO de cada tipo
    xs = 775
    L.flecha([(xs, 80 + hs), (xs, FY - 2)], "compone 1 instancia de cada DAO:\nConocimiento, Usuario, Cancion, Evento,\n"
             "Contexto, Recomendacion y Decision", (xs + 16, 80 + hs + 30), punta="rombo_abierta", ancla="start")
    # MotorDJ lee el conocimiento
    xm = cols[3] + W - 70
    L.flecha([(xm, 80 + hm), (xm, YA - 2)], "lee reglas, parámetros,\ngéneros y técnicas",
             (xm - 12, 80 + hm + 50), punta="abierta", ancla="end")
    # RepositorioConocimiento crea su conexión (ruta exterior)
    yr = YB + hb[3]
    L.flecha([(cols[3] + 60, yr), (cols[3] + 60, FY + FH + 26), (14, FY + FH + 26), (14, 150), (58, 150)],
             "crea su propia conexión en memoria (consola y simulación)", (cols[1] + 100, FY + FH + 46),
             punta="rombo_abierta")
    # leyenda
    yl = FY + FH + 80
    L.flecha([(60, yl), (130, yl)], punta="herencia"); L.texto(140, yl + 4, "hereda de", 12.5, ancla="start")
    L.flecha([(260, yl), (330, yl)], punta="rombo"); L.texto(340, yl + 4, "compone (el rombo está en el dueño)", 12.5, ancla="start")
    L.flecha([(600, yl), (670, yl)], punta="abierta"); L.texto(680, yl + 4, "usa", 12.5, ancla="start")
    L.texto(760, yl + 4, "ConexionBD._cargar usa ConocimientoDAO.crear_regla en la carga inicial de reglas.json.",
            12.5, ancla="start", color="#4a5b6c", cursiva=True)
    L.guardar("03_clases_dao.svg")


if __name__ == "__main__":
    caja_negra()
    flujo_datos()
    clases()


# ------------------------------------------------------------------ 4. modelo relacional
def relacional():
    L = Lienzo(1700, 1290, "Modelo relacional · base de conocimiento y sistema transaccional")
    BC, ST, FILA = "#1f4e79", "#7a4a12", 19
    cajas = {}

    def tabla(nombre, x, y, w, columnas, color):
        h = 30 + len(columnas) * FILA + 8
        L.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" stroke="{color}" stroke-width="1.5"/>')
        L.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="30" fill="{color}"/>')
        L.texto(x + w / 2, y + 20, nombre, 14, negrita=True, color="#ffffff")
        for i, (col, marca, nuevo) in enumerate(columnas):
            yy = y + 30 + 16 + i * FILA
            L.texto(x + 9, yy, col, 12.5, ancla="start", negrita="PK" in marca)
            L.texto(x + w - 9, yy, marca + ("  ● nuevo" if nuevo else ""), 11.5, ancla="end",
                    color="#1b7a3d" if nuevo else "#4a5b6c", negrita=nuevo)
        cajas[nombre] = (x, y, w, h)

    A, B, C, D = 40, 440, 880, 1320
    WA, WB = 300, 340
    VV = "FK → valor_variable"
    tabla("variable", A, 70, WA, [("id", "PK", 0), ("codigo", "UK", 0), ("descripcion", "", 0)], BC)
    tabla("valor_variable", A, 215, WA, [("id", "PK", 0), ("variable_id", "FK", 0), ("codigo", "", 0), ("etiqueta", "", 0)], BC)
    tabla("condicion_regla", A, 520, WA, [("regla_id", "PK, FK", 0), ("valor_id", "PK, FK", 0), ("variable_id", "FK", 0)], BC)
    tabla("regla", A, 740, WA, [("id", "PK", 0), ("codigo", "UK", 0), ("nombre", "", 0), ("conclusion", "", 0),
                                ("descripcion", "", 0), ("accion", "", 1), ("activa", "", 0), ("version", "", 0),
                                ("creada_en", "", 0)], BC)
    tabla("recomendacion_regla", A, 1060, WA, [("recomendacion_id", "PK, FK", 0), ("regla_id", "PK, FK", 0)], ST)

    tabla("usuario", B, 70, WB, [("id", "PK", 0), ("nombre", "", 0), ("correo", "UK", 0), ("rol", "", 0), ("creado_en", "", 0)], ST)
    tabla("evento", B, 250, WB, [("id", "PK", 0), ("usuario_id", "FK", 0), ("nombre", "", 0), ("tipo_evento_id", VV, 0),
                                 ("lugar", "", 0), ("aforo_estimado", "", 0), ("inicio_previsto", "", 0),
                                 ("duracion_min", "", 0), ("estado", "", 0)], ST)
    tabla("contexto_evento", B, 520, WB, [("id", "PK", 0), ("evento_id", "FK", 0), ("momento_id", VV, 0),
                                          ("grupo_edad_id", VV, 0), ("genero_actual_id", VV, 0),
                                          ("reaccion_publico_id", VV, 0), ("cancion_actual_id", "FK", 1),
                                          ("registrado_en", "", 0)], ST)
    tabla("recomendacion", B, 770, WB, [("id", "PK", 0), ("evento_id", "FK", 0), ("contexto_id", "FK", 0),
                                        ("cancion_id", "FK", 0), ("explicacion", "", 0), ("generada_en", "", 0),
                                        ("tiempo_respuesta_ms", "", 0)], ST)

    tabla("genero_musical", C, 70, WB, [("id", "PK", 0), ("nombre", "UK", 0), ("valor_regla_id", "UK, " + VV, 0)], ST)
    tabla("cancion", C, 250, WB, [("id", "PK", 0), ("usuario_id", "FK", 0), ("titulo", "", 0), ("artista", "", 0),
                                  ("genero_id", "FK", 0), ("bpm", "", 0), ("tonalidad_camelot", "", 0), ("energia", "", 0),
                                  ("duracion_seg", "", 0), ("formato", "", 0), ("conocida", "", 1), ("comercial", "", 1),
                                  ("ruta_archivo", "", 0),
                                  ("metadatos_id3", "", 0)], ST)
    tabla("decision_dj", C, 770, WB, [("id", "PK", 0), ("recomendacion_id", "UK, FK", 0), ("accion", "", 0),
                                      ("cancion_final_id", "FK", 0), ("motivo", "", 0), ("decidida_en", "", 0)], ST)

    tabla("parametro_experto", D, 70, WB, [("clave", "PK", 0), ("valor", "", 0), ("unidad", "", 0), ("descripcion", "", 0)], BC)
    tabla("tecnica_transicion", D, 250, WB, [("id", "PK", 0), ("codigo", "UK", 0), ("nombre", "", 0), ("descripcion", "", 0)], BC)
    tabla("transicion_regla", D, 520, WB, [("id", "PK", 0), ("caso", "", 0), ("tecnica_id", "FK", 0), ("prioridad", "", 0)], BC)
    tabla("recomendacion_transicion", D, 1060, WB, [("recomendacion_id", "PK, FK", 1), ("transicion_regla_id", "PK, FK", 1)], ST)

    def linea(puntos, uno, muchos, card="N"):
        """Relación 1 a N: 'uno' y 'muchos' son las posiciones de las etiquetas de cardinalidad."""
        d = "M" + " L".join(f"{x},{y}" for x, y in puntos)
        L.p.append(f'<path d="{d}" fill="none" stroke="{LINEA}" stroke-width="1.5"/>')
        L.texto(*uno, "1", 12.5, negrita=True, color="#26394d", fondo=True)
        L.texto(*muchos, card, 12.5, negrita=True, color="#26394d", fondo=True)

    def abajo(n):
        x, y, w, h = cajas[n]
        return y + h

    def vertical(arriba, debajo, dx=150, card="N", invertida=False):
        x = cajas[arriba][0] + dx
        y0, y1 = abajo(arriba), cajas[debajo][1]
        if invertida:      # el lado 1 es la tabla de abajo
            linea([(x, y0), (x, y1)], (x + 12, y1 - 8), (x + 12, y0 + 18), card)
        else:
            linea([(x, y0), (x, y1)], (x + 12, y0 + 18), (x + 12, y1 - 8), card)

    vertical("variable", "valor_variable")
    vertical("valor_variable", "condicion_regla")
    vertical("condicion_regla", "regla", invertida=True)
    vertical("regla", "recomendacion_regla")
    vertical("usuario", "evento", dx=170)
    vertical("evento", "contexto_evento", dx=170)
    vertical("contexto_evento", "recomendacion", dx=170)
    L.texto(B + 20, 752, "(contexto_id, evento_id)", 11.5, ancla="start", color="#4a5b6c", cursiva=True)
    vertical("genero_musical", "cancion", dx=170)
    vertical("cancion", "decision_dj", dx=250, card="0..N")
    L.texto(C + 262, 640, "cancion_final_id", 11.5, ancla="start", color="#4a5b6c", cursiva=True)
    vertical("tecnica_transicion", "transicion_regla", dx=170)
    vertical("transicion_regla", "recomendacion_transicion", dx=170)

    BD, CI = B + WB, C                     # borde derecho de B, izquierdo de C
    # usuario -> cancion
    linea([(BD, 120), (BD + 70, 120), (BD + 70, 290), (CI, 290)], (BD + 14, 112), (CI - 14, 282))
    # cancion -> contexto_evento.cancion_actual_id
    linea([(CI, 420), (BD + 35, 420), (BD + 35, 672), (BD, 672)], (CI - 12, 412), (BD + 18, 696), "0..N")
    # cancion -> recomendacion.cancion_id
    linea([(CI, 470), (BD + 70, 470), (BD + 70, 800), (BD, 800)], (CI - 12, 462), (BD + 24, 824), "0..N")
    # recomendacion -> decision_dj (0..1)
    linea([(BD, 880), (CI, 880)], (BD + 14, 872), (CI - 20, 872), "0..1")
    # evento -> recomendacion.evento_id
    linea([(B, 400), (B - 25, 400), (B - 25, 820), (B, 820)], (B - 12, 392), (B - 12, 842))
    # recomendacion -> recomendacion_regla
    linea([(B, 900), (B - 50, 900), (B - 50, 1100), (A + WA, 1100)], (B - 12, 922), (A + WA + 14, 1092))
    # recomendacion -> recomendacion_transicion
    xr = B + 250
    linea([(xr, abajo("recomendacion")), (xr, 1100), (D, 1100)], (xr + 12, abajo("recomendacion") + 18),
          (D - 22, 1092), "0..N")

    # leyenda y notas
    y = 1180
    L.p.append(f'<rect x="40" y="{y}" width="22" height="16" fill="{BC}"/>')
    L.texto(70, y + 13, "Base de conocimiento", 12.5, ancla="start")
    L.p.append(f'<rect x="230" y="{y}" width="22" height="16" fill="{ST}"/>')
    L.texto(260, y + 13, "Sistema transaccional", 12.5, ancla="start")
    L.texto(430, y + 13, "● nuevo", 12.5, ancla="start", color="#1b7a3d", negrita=True)
    L.texto(495, y + 13, "= columna o tabla añadida al modelo del documento.   1 — N: una fila de la tabla «1» "
            "se relaciona con varias de la tabla «N».", 12.5, ancla="start")
    L.texto(40, y + 42, "«FK → valor_variable»: la columna apunta a valor_variable(id) y un disparador comprueba que el "
            "valor sea de su variable. Esas seis líneas no se dibujan para no cruzar el diagrama.", 12.5,
            ancla="start", color="#4a5b6c", cursiva=True)
    L.texto(40, y + 64, "recomendacion.tecnica_id se sustituye por recomendacion_transicion (una transición combina varias "
            "técnicas). parametro_experto no tiene claves foráneas.", 12.5, ancla="start", color="#4a5b6c", cursiva=True)
    L.guardar("04_modelo_relacional.svg")


if __name__ == "__main__":
    relacional()
