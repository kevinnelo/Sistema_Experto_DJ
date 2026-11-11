# Sistema experto DJ — Python + Flask 

Implementación del documento «Sistema experto DJ». El motor aplica las reglas SI-ENTONCES R01–R27, detecta conflictos entre ellas y propone canciones del catálogo del DJ con la técnica de transición que indica el documento. El catálogo, los eventos, los contextos, las recomendaciones y las decisiones se guardan en la base de datos con el modelo del documento.

## Capas y archivos

| Archivo | Capa | Contenido |
|---|---|---|
| `reglas.json` | Conocimiento | Variables, valores, reglas R01–R27, parámetros (BPM 10 y 5, Camelot 3, energía 1), técnicas y casos de transición. |
| `esquema.sql` | Datos | Las 16 tablas, los disparadores de integridad y las 2 vistas (SQLite). |
| `datos.py` | Datos | `ConexionBD` y las clases DAO: `ConocimientoDAO`, `UsuarioDAO`, `CancionDAO`, `EventoDAO`, `ContextoDAO`, `RecomendacionDAO`, `DecisionDAO`. |
| `negocio.py` | Negocio | `MotorDJ` (inferencia) y `ServicioSesion` (procesos transaccionales CU01–CU05). |
| `app.py` | Presentación | API Flask e interfaz web. |
| `main.py` | Presentación | Consola con el mismo motor; no guarda nada. |
| `docs/` | Documentación | Diagramas, capturas y el script equivalente para PostgreSQL 16. |

## Qué hace el motor

1. **Dispara reglas** (encadenamiento hacia adelante): una regla se dispara si cada variable de su antecedente tiene un valor del contexto. Valores de la misma variable se combinan con O; variables distintas, con Y.
2. **Detecta conflictos**: si una regla pide subir la energía (R10, R20) y otra bajarla (R11, R21, R26), las muestra y no elige. El documento no define prioridades.
3. **Selecciona canciones** del catálogo según la acción de la regla, entre las compatibles con la canción que suena (distancia circular de los números Camelot ≤ 3; la letra A/B no se considera, como en el documento).
4. **Asigna técnicas**: diferencia de BPM ≤ 5 → cross-fade y mezcla sencilla; entre 5 y 10 → ajuste de tempo y luego cross-fade; > 10 → ajuste de tempo; cambio de género → corte directo; siempre sincronización de BPM y echo out al cambiar de canción.
5. **Explica** cada recomendación: hechos, reglas, filtro, canción y técnicas (RF04).

No calcula probabilidades: el documento no define pesos.

### Acción de cada regla

| Reglas | Acción | Selección en el catálogo |
|---|---|---|
| R01–R09, R12–R17 | `CRITERIO` | Ninguna: el catálogo no tiene atributos de tipo de fiesta ni de edad. Muestran su conclusión. |
| R10, R20 | `SUBIR_ENERGIA` | Energía mayor que la actual, de mayor a menor salto. |
| R11, R26 | `BAJAR_ENERGIA` | Energía menor que la actual. |
| R21 | `BAJAR_O_COMERCIAL` | Energía menor o canción marcada como comercial; primero las comerciales. |
| R18 | `MANTENER_GENERO` | Mismo género, por energía más cercana. |
| R19 | `MANTENER_ENERGIA` | **Mismo género** y energía a 1 punto o menos de la actual (parámetro `energia_diferencia_mismo_nivel`). |
| R22 | `CAMBIAR_GENERO` | Ninguna: hay que confirmar qué género pide el público. |
| R23 | `MISMO_GENERO` | Mismo género; primero las canciones marcadas como conocidas. |
| R24, R27 | `CONSULTAR` | Ninguna: se consulta al público antes de cambiar la selección. |
| R25 | `BUSCAR_OTRA` | Otra canción compatible; antes hay que consultar la causa. |

## Ejecutar en local

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m unittest -v      # 86 pruebas
python3 app.py              # http://127.0.0.1:5000/
```

Consola: `python3 main.py` (contexto interactivo) o `python3 main.py --catalogo docs/ejemplos/catalogo_ejemplo.json --actual a`.

## Pruebas

| Archivo | Qué comprueba |
|---|---|
| `test_motor.py` | Disparo de reglas, conflictos, selección y técnicas (19). |
| `tests/test_web.py` | API: flujo completo por HTTP, validaciones y códigos de error (9). |
| `tests/test_persistencia.py` | Procesos transaccionales PT01–PT15 y restricciones de integridad RI01–RI15 (30). |
| `tests/test_no_funcionales.py` | RNF01–RNF06, reglas R18–R27 y escenarios E1–E6 del documento (28). |
| `docs/sql/pruebas_integridad.sql` | Las mismas restricciones en PostgreSQL 16 (33 casos). |
