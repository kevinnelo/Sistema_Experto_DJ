"""Motor de inferencia del documento 'Sistema experto DJ'.

Qué hace, y solo lo que define el documento:
1. Dispara las reglas R01-R27 (forward chaining): una regla se dispara si cada
   variable de su antecedente tiene un valor del contexto. Valores de la misma
   variable se combinan con O; variables distintas, con Y.
2. Detecta conflictos entre reglas que piden subir y bajar la energía (criterio
   del propio documento, sección 9). No los resuelve: el documento no define
   prioridades, así que la decisión queda en manos del DJ.
3. Propone canciones del catálogo del DJ (RF03): filtra por compatibilidad de
   tonalidad en Camelot (parámetro del documento) con la canción que suena y
   ordena según la acción de la regla.
4. Asigna técnicas de transición según el caso de BPM (transicion_regla).
5. Redacta la explicación de cada recomendación: hechos, reglas, filtro y técnicas (RF04).

ServicioSesion reúne los procesos transaccionales (catálogo, evento, contexto,
recomendación y decisión). Cada proceso se ejecuta en una sola transacción y guarda
su resultado en las tablas del modelo del documento a través de los DAO de datos.py.
"""
import json
import re
import sqlite3
import time
from datetime import datetime, timezone

from datos import (CancionDAO, ConocimientoDAO, ContextoDAO, DecisionDAO, EventoDAO,
                   RecomendacionDAO, UsuarioDAO, VARIABLES_CONTEXTO)

CAMPOS_CONTEXTO = ("tipo_evento", "momento", "grupo_edad", "genero_actual", "reaccion_publico")
FORMATOS = ("MP3", "WAV", "FLAC")
CAMELOT = re.compile(r"^(1[0-2]|[1-9])[AB]$")  # restricción CHECK de la tabla cancion

# Acciones de canción y su orden. Las demás acciones solo muestran texto.
ACCION_CONSULTA = "CONSULTAR"
ACCION_CAMBIO_GENERO = "CAMBIAR_GENERO"
ACCIONES_SIN_CANCION = {"CRITERIO", ACCION_CONSULTA, ACCION_CAMBIO_GENERO}
DECISIONES = ("ACEPTADA", "RECHAZADA", "MODIFICADA")
CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorNoEncontrado(LookupError):
    """El usuario, evento, canción o recomendación indicado no existe."""


class ErrorConflicto(Exception):
    """La operación choca con el estado guardado (duplicado, evento cerrado, ya decidida)."""
SUBE, BAJA = "SUBIR_ENERGIA", "BAJAR_ENERGIA"
BAJA_O_COMERCIAL = "BAJAR_O_COMERCIAL"
BAJAN = {BAJA, BAJA_O_COMERCIAL}  # acciones que piden menos energía (conflictos del documento)


class MotorDJ:
    """Motor de inferencia con encadenamiento hacia adelante sobre la base de conocimiento."""

    def __init__(self, repositorio):
        self.repo = repositorio
        self.reglas = repositorio.reglas()
        self.parametros = repositorio.parametros()
        self.generos = repositorio.generos()                     # nombre -> valor de genero_actual
        self.generos_por_valor = {v: n for n, v in self.generos.items()}
        self.valores = {v: set(repositorio.valores(v)) for v in CAMPOS_CONTEXTO}

    # ------------------------------------------------------------------ validación
    def validar_contexto(self, contexto):
        """Comprueba variables y valores contra sus dominios; omite las variables sin responder."""
        if not isinstance(contexto, dict):
            raise ValueError("El contexto debe ser un objeto.")
        desconocidas = set(contexto) - set(CAMPOS_CONTEXTO)
        if desconocidas:
            raise ValueError(f"Variable desconocida: {sorted(desconocidas)[0]}.")
        limpio = {}
        for var, val in contexto.items():
            if val in (None, ""):
                continue  # las variables sin responder se omiten
            if not isinstance(val, str) or val not in self.valores[var]:
                raise ValueError(f"Valor inválido para {var}.")
            limpio[var] = val
        return limpio

    def validar_cancion(self, c, etiqueta="La canción"):
        """Valida una canción con las restricciones de la tabla cancion y la devuelve normalizada."""
        if not isinstance(c, dict):
            raise ValueError(f"{etiqueta}: formato inválido.")
        try:
            cid = str(c["id"]).strip()
            titulo, artista = str(c["titulo"]).strip(), str(c["artista"]).strip()
            genero = c["genero"]
            bpm = float(c["bpm"])
            camelot = str(c["tonalidad_camelot"]).strip().upper()
            energia = int(c["energia"])
            duracion = int(c["duracion_seg"])
            formato = str(c["formato"]).upper()
            conocida, comercial = c.get("conocida", False), c.get("comercial", False)
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{etiqueta}: faltan datos o tienen tipo incorrecto.")
        if not cid:
            raise ValueError(f"{etiqueta}: id vacío.")
        if not titulo or not artista or len(titulo) > 200 or len(artista) > 200:
            raise ValueError(f"{etiqueta}: título o artista inválido.")
        if genero not in self.generos:
            raise ValueError(f"{etiqueta}: género no existe en el catálogo musical.")
        if not 40 <= bpm <= 250:
            raise ValueError(f"{etiqueta}: BPM fuera de 40-250.")
        if not CAMELOT.match(camelot):
            raise ValueError(f"{etiqueta}: tonalidad Camelot inválida (1A-12B).")
        if not 1 <= energia <= 10:
            raise ValueError(f"{etiqueta}: energía fuera de 1-10.")
        if duracion <= 0:
            raise ValueError(f"{etiqueta}: duración inválida.")
        if formato not in FORMATOS:
            raise ValueError(f"{etiqueta}: formato debe ser MP3, WAV o FLAC.")
        if conocida not in (True, False, 0, 1) or comercial not in (True, False, 0, 1):
            raise ValueError(f"{etiqueta}: 'conocida' y 'comercial' deben ser verdadero o falso.")
        return {"id": cid, "titulo": titulo, "artista": artista, "genero": genero,
                "bpm": bpm, "tonalidad_camelot": camelot, "energia": energia,
                "duracion_seg": duracion, "formato": formato,
                "conocida": bool(conocida), "comercial": bool(comercial)}

    def validar_catalogo(self, catalogo):
        """Valida la lista de canciones y exige ids únicos."""
        if not isinstance(catalogo, list):
            raise ValueError("El catálogo debe ser una lista.")
        ids, canciones = set(), []
        for i, c in enumerate(catalogo):
            cancion = self.validar_cancion(c, f"Canción {i + 1}")
            if cancion["id"] in ids:
                raise ValueError(f"Canción {i + 1}: id vacío o repetido.")
            ids.add(cancion["id"])
            canciones.append(cancion)
        return canciones

    # ------------------------------------------------------------------ reglas
    def disparar(self, contexto):
        """Devuelve las reglas cuyo antecedente se cumple con el contexto (Y entre variables, O dentro)."""
        disparadas = []
        for r in self.reglas:
            cumplidas = {}
            for var, valores in r["condiciones"].items():
                if var in contexto and contexto[var] in valores:
                    cumplidas[var] = contexto[var]
            if len(cumplidas) == len(r["condiciones"]):
                disparadas.append({"codigo": r["codigo"], "nombre": r["nombre"],
                                   "conclusion": r["conclusion"], "accion": r["accion"],
                                   "descripcion": r["descripcion"], "cumplidas": cumplidas})
        return disparadas

    @staticmethod
    def conflictos(disparadas):
        """Pares de reglas que piden subir y bajar la energía a la vez. No se resuelven."""
        subidas = [r for r in disparadas if r["accion"] == SUBE]
        bajadas = [r for r in disparadas if r["accion"] in BAJAN]
        return [{"reglas": [s["codigo"], b["codigo"]],
                 "descripcion": f"{s['codigo']} pide subir la energía y {b['codigo']} pide bajarla. "
                                "El documento no define prioridad entre ellas; decide el DJ."}
                for s in subidas for b in bajadas]

    # ------------------------------------------------------------------ canciones
    def _compatible(self, a, b):
        """Compatibilidad en la rueda de Camelot: distancia circular sobre el número (parámetro del documento)."""
        na, nb = int(a["tonalidad_camelot"][:-1]), int(b["tonalidad_camelot"][:-1])
        dist = abs(na - nb)
        return min(dist, 12 - dist) <= self.parametros["camelot_distancia_maxima"]

    def _caso_bpm(self, dif):
        if dif <= self.parametros["bpm_diferencia_mezcla_similar"]:
            return "BPM_SIMILAR"
        if dif <= self.parametros["bpm_diferencia_tolerada"]:
            return "BPM_TOLERABLE"  # entre 5 y 10 BPM: ajuste de tempo y cross-fade (decisión del experto)
        return "BPM_DISTINTO"

    def _transiciones(self, cancion, actual, genero_referencia):
        casos = ["SIEMPRE", "CAMBIO_CANCION"]
        notas = []
        if actual is not None:
            caso = self._caso_bpm(abs(cancion["bpm"] - actual["bpm"]))
            casos.append(caso)
        if genero_referencia is not None and cancion["genero"] != genero_referencia:
            casos.append("CAMBIO_GENERO")
        tecnicas = []
        vistos = set()
        for caso in casos:
            for t in self.repo.transiciones(caso):
                if t["codigo"] not in vistos:
                    vistos.add(t["codigo"])
                    tecnicas.append({"caso": caso, "codigo": t["codigo"], "nombre": t["nombre"],
                                     "prioridad": t["prioridad"], "transicion_regla_id": t["id"]})
        return tecnicas, notas

    def _seleccionar(self, accion, catalogo, actual, genero_referencia):
        """Filtra y ordena canciones según la acción de la regla. Devuelve (lista, filtro aplicado)."""
        if actual is not None:
            base = [c for c in catalogo if c["id"] != actual["id"] and self._compatible(c, actual)]
            delta = lambda c: c["energia"] - actual["energia"]
        else:
            base = list(catalogo)
            delta = None
        if accion == "MANTENER_GENERO":
            base = [c for c in base if c["genero"] == genero_referencia]
            filtro = f"género = {genero_referencia}"
            orden = (lambda c: (abs(delta(c)), c["id"])) if delta else (lambda c: c["id"])
        elif accion == "MISMO_GENERO":
            # Canción más conocida del mismo género: primero las marcadas como conocidas.
            base = [c for c in base if c["genero"] == genero_referencia]
            filtro = f"género = {genero_referencia}, primero las canciones conocidas"
            orden = (lambda c: (not c["conocida"], abs(delta(c)), c["id"])) if delta \
                else (lambda c: (not c["conocida"], c["id"]))
        elif accion == "MANTENER_ENERGIA":
            # Mantener el género y el nivel de energía (canción de continuidad).
            margen = int(self.parametros["energia_diferencia_mismo_nivel"])
            base = [c for c in base if c["genero"] == genero_referencia]
            filtro = f"género = {genero_referencia}"
            if delta:
                base = [c for c in base if abs(delta(c)) <= margen]
                filtro += f" y energía a {margen} punto o menos de la actual"
            orden = (lambda c: (abs(delta(c)), c["id"])) if delta else (lambda c: c["id"])
        elif accion == "SUBIR_ENERGIA":
            if delta:
                base = [c for c in base if delta(c) > 0]
                orden = lambda c: (-delta(c), c["id"])
            else:
                orden = lambda c: (-c["energia"], c["id"])
            filtro = "energía mayor"
        elif accion == BAJA:
            if delta:
                base = [c for c in base if delta(c) < 0]
                orden = lambda c: (delta(c), c["id"])
            else:
                orden = lambda c: (c["energia"], c["id"])
            filtro = "energía menor"
        elif accion == BAJA_O_COMERCIAL:
            # Disminuir la energía o pasar a una canción comercial: primero las comerciales.
            if delta:
                base = [c for c in base if delta(c) < 0 or c["comercial"]]
                orden = lambda c: (not c["comercial"], delta(c), c["id"])
            else:
                orden = lambda c: (not c["comercial"], c["energia"], c["id"])
            filtro = "energía menor o canción comercial, primero las comerciales"
        elif accion == "BUSCAR_OTRA":
            filtro = "compatible con la canción actual, distinta de ella"
            orden = (lambda c: (abs(delta(c)), c["id"])) if delta else (lambda c: c["id"])
        else:
            return [], None
        return sorted(base, key=orden), filtro

    # ------------------------------------------------------------------ explicación (RF04)
    def _explicar(self, reglas, filtro, sugerida, actual, notas):
        """Texto que justifica la recomendación: hechos, reglas, filtro, canción y técnicas."""
        partes = []
        for r in reglas:
            hechos = " Y ".join(f"{var} = {val}" for var, val in r["cumplidas"].items())
            partes.append(f"{r['codigo']} ({r['nombre']}): SI {hechos} ENTONCES {r['conclusion']}.")
        if filtro:
            base = "Selección en el catálogo: "
            if actual is not None:
                base += (f"tonalidad a {int(self.parametros['camelot_distancia_maxima'])} posiciones o menos "
                         f"de {actual['tonalidad_camelot']} en la rueda de Camelot; ")
            partes.append(base + filtro + ".")
        if sugerida is not None:
            detalle = (f"Canción sugerida: «{sugerida['titulo']}» de {sugerida['artista']} "
                       f"({sugerida['genero']}, {sugerida['bpm']:g} BPM, {sugerida['tonalidad_camelot']}, "
                       f"energía {sugerida['energia']}"
                       + (", conocida" if sugerida["conocida"] else "")
                       + (", comercial" if sugerida["comercial"] else ""))
            if actual is not None:
                detalle += (f"; frente a «{actual['titulo']}»: energía {sugerida['delta_energia']:+d}, "
                            f"diferencia de {sugerida['diferencia_bpm']:g} BPM")
            partes.append(detalle + ").")
            if sugerida["transiciones"]:
                partes.append("Transición: " + ", ".join(
                    f"{t['nombre']} [{t['caso']}]" for t in sugerida["transiciones"]) + ".")
            notas = list(notas) + sugerida["notas"]
        partes.extend(notas)
        return " ".join(partes)

    # ------------------------------------------------------------------ recomendación
    def recomendar(self, contexto, catalogo, cancion_actual_id=None):
        """Aplica las reglas al contexto y propone canciones del catálogo.

        Devuelve reglas disparadas, conflictos, una recomendación por acción (con su canción
        sugerida, las demás candidatas, las técnicas y la explicación) y la traza.
        """
        contexto = self.validar_contexto(contexto)
        catalogo = self.validar_catalogo(catalogo)
        actual = None
        if cancion_actual_id not in (None, ""):
            actual = next((c for c in catalogo if c["id"] == str(cancion_actual_id)), None)
            if actual is None:
                raise ValueError("La canción actual no está en el catálogo.")

        disparadas = self.disparar(contexto)
        if not disparadas:
            return {"reglas_disparadas": [], "conflictos": [], "recomendaciones": [],
                    "sin_reglas": True, "cancion_actual": actual, "traza": [],
                    "aviso": "Ninguna regla aplica al contexto indicado."}

        genero_referencia = self.generos_por_valor.get(contexto.get("genero_actual"))
        if genero_referencia is None and actual is not None:
            genero_referencia = actual["genero"]

        traza = [{"paso": "reglas_disparadas", "reglas": [r["codigo"] for r in disparadas]}]
        grupos = {}
        for r in disparadas:
            grupos.setdefault(r["accion"], []).append(r)

        notas_generales = {
            ACCION_CONSULTA: ["No se cambia la selección hasta consultar al público."],
            ACCION_CAMBIO_GENERO: ["Confirmar qué género desea escuchar el público; "
                                   "el sistema no conoce el género solicitado."]}
        recomendaciones = []
        for accion, reglas in grupos.items():
            codigos = [r["codigo"] for r in reglas]
            mensaje = " · ".join(r["conclusion"] for r in reglas)
            if accion in ACCIONES_SIN_CANCION:
                notas = notas_generales.get(accion, [])
                recomendaciones.append({
                    "accion": accion, "reglas": codigos, "mensaje": mensaje, "filtro": None,
                    "cancion_sugerida": None, "canciones": [], "notas": notas,
                    "explicacion": self._explicar(reglas, None, None, actual, notas)})
                continue

            candidatas, filtro = self._seleccionar(accion, catalogo, actual, genero_referencia)
            canciones = []
            for c in candidatas:
                tecnicas, notas = self._transiciones(c, actual, genero_referencia)
                canciones.append({**c,
                                  "delta_energia": (c["energia"] - actual["energia"]) if actual else None,
                                  "diferencia_bpm": round(abs(c["bpm"] - actual["bpm"]), 2) if actual else None,
                                  "transiciones": tecnicas, "notas": notas})
            notas = []
            if accion == "MISMO_GENERO" and canciones and not any(c["conocida"] for c in canciones):
                notas.append("Ninguna canción de ese género está marcada como conocida; se ordena por energía.")
            if accion == BAJA_O_COMERCIAL and canciones and not any(c["comercial"] for c in canciones):
                notas.append("Ninguna candidata está marcada como comercial; se propone solo bajar la energía.")
            if accion == "BUSCAR_OTRA":
                notas.append("Consultar la causa de la falta de reacción antes de cambiar la selección.")
            if not canciones:
                notas.append("Ninguna canción del catálogo cumple esta regla con la canción actual.")
            sugerida = canciones[0] if canciones else None
            recomendaciones.append({"accion": accion, "reglas": codigos, "mensaje": mensaje,
                                    "filtro": filtro, "cancion_sugerida": sugerida,
                                    "canciones": canciones, "notas": notas,
                                    "explicacion": self._explicar(reglas, filtro, sugerida, actual, notas)})
            traza.append({"paso": "seleccion", "accion": accion, "filtro": filtro,
                          "candidatas": [c["id"] for c in candidatas]})

        return {"reglas_disparadas": disparadas,
                "conflictos": self.conflictos(disparadas),
                "recomendaciones": recomendaciones,
                "sin_reglas": False,
                "cancion_actual": actual,
                "traza": traza,
                "aviso": "Las reglas y los parámetros provienen del documento; requieren validación con DJs."}


class ServicioSesion:
    """Procesos transaccionales del DJ sobre la base de datos (CU01 a CU05).

    Cada método público es una transacción: si algo falla, no queda nada guardado a medias.
    """

    def __init__(self, conexion):
        self.conexion = conexion
        self.conocimiento = ConocimientoDAO(conexion)
        self.usuarios = UsuarioDAO(conexion)
        self.canciones = CancionDAO(conexion)
        self.eventos = EventoDAO(conexion)
        self.contextos = ContextoDAO(conexion)
        self.recomendaciones = RecomendacionDAO(conexion)
        self.decisiones = DecisionDAO(conexion)
        self.motor = MotorDJ(self.conocimiento)

    # ------------------------------------------------------------------ apoyo
    def _usuario(self, usuario_id):
        usuario = self.usuarios.obtener(usuario_id)
        if usuario is None:
            raise ErrorNoEncontrado("El usuario no existe.")
        return usuario

    def _evento(self, evento_id):
        evento = self.eventos.obtener(evento_id)
        if evento is None:
            raise ErrorNoEncontrado("El evento no existe.")
        return evento

    @staticmethod
    def _entero(valor, nombre, obligatorio=True):
        if valor in (None, "") and not obligatorio:
            return None
        try:
            if isinstance(valor, bool):
                raise ValueError
            return int(valor)
        except (TypeError, ValueError):
            raise ValueError(f"{nombre} debe ser un número entero.")

    # ------------------------------------------------------------------ usuario
    def registrar_dj(self, nombre, correo):
        """Devuelve el DJ con ese correo; si no existe, lo crea."""
        nombre, correo = str(nombre or "").strip(), str(correo or "").strip().lower()
        if not nombre or len(nombre) > 120:
            raise ValueError("El nombre es obligatorio (máximo 120 caracteres).")
        if not CORREO.match(correo) or len(correo) > 160:
            raise ValueError("El correo no es válido.")
        with self.conexion.transaccion():
            existente = self.usuarios.por_correo(correo)
            if existente:
                return existente
            return self.usuarios.obtener(self.usuarios.crear(nombre, correo, "DJ"))

    # ------------------------------------------------------------------ CU01 catálogo
    def registrar_cancion(self, usuario_id, datos):
        """Valida la canción y la agrega al catálogo del DJ."""
        if not isinstance(datos, dict):
            raise ValueError("La canción: formato inválido.")
        cancion = self.motor.validar_cancion({**datos, "id": "nueva"})
        ruta = datos.get("ruta_archivo")
        if ruta is not None and (not isinstance(ruta, str) or len(ruta) > 500):
            raise ValueError("La canción: ruta de archivo inválida.")
        meta = datos.get("metadatos_id3")
        if meta is not None and (not isinstance(meta, dict) or len(json.dumps(meta)) > 10000):
            raise ValueError("La canción: los metadatos ID3 deben ser un objeto.")
        cancion.update(ruta_archivo=ruta, metadatos_id3=meta)
        with self.conexion.transaccion():
            self._usuario(usuario_id)
            try:
                nuevo_id = self.canciones.crear(usuario_id, cancion)
            except sqlite3.IntegrityError:
                raise ErrorConflicto("Ya existe una canción con ese título y artista en el catálogo.")
            return self.canciones.obtener(nuevo_id)

    def catalogo(self, usuario_id):
        """Canciones del DJ."""
        self._usuario(usuario_id)
        return self.canciones.listar(usuario_id)

    def eliminar_cancion(self, usuario_id, cancion_id):
        """Quita una canción que todavía no aparece en ningún historial."""
        with self.conexion.transaccion():
            try:
                if not self.canciones.eliminar(cancion_id, usuario_id):
                    raise ErrorNoEncontrado("La canción no existe en el catálogo.")
            except sqlite3.IntegrityError:
                raise ErrorConflicto("La canción aparece en el historial de un evento y no se puede eliminar.")

    # ------------------------------------------------------------------ CU02 evento
    def crear_evento(self, usuario_id, nombre, tipo_evento, duracion_min, inicio_previsto=None,
                     lugar=None, aforo_estimado=None):
        """Registra un evento del DJ en estado PLANEADO."""
        nombre = str(nombre or "").strip()
        if not nombre or len(nombre) > 200:
            raise ValueError("El nombre del evento es obligatorio (máximo 200 caracteres).")
        duracion = self._entero(duracion_min, "La duración")
        aforo = self._entero(aforo_estimado, "El aforo", obligatorio=False)
        if duracion <= 0 or (aforo is not None and aforo <= 0):
            raise ValueError("La duración y el aforo deben ser mayores que cero.")
        if inicio_previsto in (None, ""):
            inicio = datetime.now(timezone.utc).isoformat(timespec="seconds")
        else:
            try:
                inicio = datetime.fromisoformat(str(inicio_previsto)).isoformat(timespec="seconds")
            except ValueError:
                raise ValueError("La fecha de inicio no es válida (formato ISO 8601).")
        lugar = str(lugar).strip()[:200] if lugar else None
        if tipo_evento in (None, ""):
            raise ValueError("El tipo de evento es obligatorio.")
        with self.conexion.transaccion():
            self._usuario(usuario_id)
            tipo_id = self.conocimiento.id_valor("tipo_evento", tipo_evento)
            return self.eventos.obtener(
                self.eventos.crear(usuario_id, nombre, tipo_id, inicio, duracion, lugar, aforo))

    def eventos_de(self, usuario_id):
        """Eventos del DJ, del más reciente al más antiguo."""
        self._usuario(usuario_id)
        return self.eventos.listar(usuario_id)

    def finalizar_evento(self, evento_id):
        """Cierra el evento: ya no admite contextos ni recomendaciones nuevas."""
        with self.conexion.transaccion():
            self._evento(evento_id)
            self.eventos.cambiar_estado(evento_id, "FINALIZADO")
            return self.eventos.obtener(evento_id)

    # ------------------------------------------------------------------ CU02 + CU03
    def recomendar(self, evento_id, contexto, cancion_actual_id=None):
        """Registra el contexto, ejecuta el motor y guarda las recomendaciones.

        El tipo de evento se toma del evento; el catálogo, de las canciones del DJ.
        Todo ocurre en una transacción: contexto, recomendaciones, reglas y técnicas.
        """
        inicio = time.perf_counter()
        if contexto is None:
            contexto = {}
        if not isinstance(contexto, dict):
            raise ValueError("El contexto debe ser un objeto.")
        with self.conexion.transaccion():
            evento = self._evento(evento_id)
            if evento["estado"] == "FINALIZADO":
                raise ErrorConflicto("El evento está finalizado.")
            hechos = {k: v for k, v in contexto.items() if k != "tipo_evento"}
            hechos["tipo_evento"] = evento["tipo_evento"]
            catalogo = [{k: c[k] for k in ("id", "titulo", "artista", "genero", "bpm", "tonalidad_camelot",
                                           "energia", "duracion_seg", "formato", "conocida", "comercial")}
                        for c in self.canciones.listar(evento["usuario_id"])]
            actual_id = self._entero(cancion_actual_id, "La canción actual", obligatorio=False)
            resultado = self.motor.recomendar(hechos, catalogo, actual_id)

            ids_valores = {v: self.conocimiento.id_valor(v, hechos.get(v)) for v in VARIABLES_CONTEXTO}
            contexto_id = self.contextos.registrar(evento_id, ids_valores, actual_id)
            if evento["estado"] == "PLANEADO":
                self.eventos.cambiar_estado(evento_id, "EN_CURSO")
            tiempo_ms = int((time.perf_counter() - inicio) * 1000)
            for rec in resultado["recomendaciones"]:
                sugerida = rec["cancion_sugerida"]
                rec["id"] = self.recomendaciones.crear(
                    evento_id, contexto_id, int(sugerida["id"]) if sugerida else None, rec["explicacion"],
                    tiempo_ms, rec["reglas"],
                    [t["transicion_regla_id"] for t in sugerida["transiciones"]] if sugerida else [])
                rec["decision"] = None
        resultado.update(evento_id=evento_id, contexto_id=contexto_id, tiempo_respuesta_ms=tiempo_ms)
        return resultado

    # ------------------------------------------------------------------ CU04 explicación
    def explicacion(self, recomendacion_id):
        """Hechos, reglas, técnicas y decisión de una recomendación, leídos del historial."""
        rec = self.recomendaciones.obtener(recomendacion_id)
        if rec is None:
            raise ErrorNoEncontrado("La recomendación no existe.")
        contexto = self.contextos.obtener(rec["contexto_id"])
        evento = self.eventos.obtener(rec["evento_id"])
        hechos = {"tipo_evento": evento["tipo_evento"]}
        hechos.update({v: contexto[v] for v in VARIABLES_CONTEXTO if contexto[v]})
        return {"recomendacion_id": rec["id"], "evento": evento["nombre"], "generada_en": rec["generada_en"],
                "tiempo_respuesta_ms": rec["tiempo_respuesta_ms"], "hechos": hechos,
                "cancion_actual_id": contexto["cancion_actual_id"],
                "cancion_sugerida": ({"id": rec["cancion_id"], "titulo": rec["cancion_titulo"],
                                      "artista": rec["cancion_artista"]} if rec["cancion_id"] else None),
                "reglas": rec["reglas"], "transiciones": rec["transiciones"],
                "explicacion": rec["explicacion"], "decision": rec["decision"]}

    # ------------------------------------------------------------------ CU05 decisiones
    def decidir(self, recomendacion_id, accion, cancion_final_id=None, motivo=None):
        """Registra la decisión del DJ. La recomendación original no se altera."""
        if accion not in DECISIONES:
            raise ValueError("La acción debe ser ACEPTADA, RECHAZADA o MODIFICADA.")
        final_id = self._entero(cancion_final_id, "La canción final", obligatorio=False)
        if accion == "MODIFICADA" and final_id is None:
            raise ValueError("Una decisión MODIFICADA debe indicar la canción final.")
        if accion != "MODIFICADA" and final_id is not None:
            raise ValueError("Solo una decisión MODIFICADA lleva canción final.")
        motivo = str(motivo).strip()[:1000] if motivo else None
        with self.conexion.transaccion():
            rec = self.recomendaciones.obtener(recomendacion_id)
            if rec is None:
                raise ErrorNoEncontrado("La recomendación no existe.")
            if rec["decision"] is not None:
                raise ErrorConflicto("La recomendación ya tiene una decisión registrada.")
            if final_id is not None:
                final = self.canciones.obtener(final_id)
                if final is None or final["usuario_id"] != rec["usuario_id"]:
                    raise ValueError("La canción final no está en el catálogo del DJ.")
                if final_id == rec["cancion_id"]:
                    raise ValueError("La canción final es la misma sugerida: use ACEPTADA.")
            self.decisiones.registrar(recomendacion_id, accion, final_id, motivo)
            return self.recomendaciones.obtener(recomendacion_id)

    def historial(self, evento_id):
        """Decisiones tomadas durante el evento."""
        self._evento(evento_id)
        return self.decisiones.historial(evento_id)
