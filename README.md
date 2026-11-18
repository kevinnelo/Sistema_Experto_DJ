# Sistema experto DJ — Python + Flask + PostgreSQL

Implementación del documento «Sistema experto DJ». El motor aplica las reglas SI-ENTONCES R01–R27, detecta conflictos entre ellas y propone canciones del catálogo del DJ con la técnica de transición que indica el documento. El DJ inicia sesión, responde una pregunta a la vez y todo queda guardado en PostgreSQL: catálogo, eventos, consultas, recomendaciones y decisiones.

## Puesta en marcha

### 1. Crear la base de datos y sus credenciales

Con PostgreSQL 14 o superior instalado, abra `psql` como administrador (en Windows: «SQL Shell (psql)») y ejecute, cambiando la clave:

```sql
CREATE ROLE dj_app LOGIN PASSWORD 'cambie_esta_clave';
CREATE DATABASE sistema_dj OWNER dj_app;
```

### 2. Configurar la conexión

Copie `.env.ejemplo` como `.env` y ponga sus credenciales:

```
DATABASE_URL=postgresql://dj_app:cambie_esta_clave@localhost:5432/sistema_dj
```

El archivo `.env` no se sube al repositorio. La URL sirve igual para un PostgreSQL en la nube (Cloud SQL, Neon, Supabase, Render…): solo cambia el servidor.

### 3. Instalar y ejecutar

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux o macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py                     # http://127.0.0.1:5000/
```

La primera vez, la aplicación crea sola el esquema `sistema_dj` con sus tablas y carga `reglas.json`. No hay que ejecutar ningún script SQL.

## Cómo se usa

1. **Crear cuenta o iniciar sesión.** Al registrarse se pueden cargar cinco casos de ejemplo.
2. **Historial.** Cada tarjeta es una consulta guardada; al abrirla se ve el resultado completo: hechos, reglas disparadas, conflictos, canciones, explicación y decisiones.
3. **Nueva consulta, pregunta por pregunta.** Evento → momento → público → canción que suena → reacción → resumen. Cada pregunta muestra sus opciones como tarjetas y se puede volver atrás.
4. **Resultado.** El DJ acepta, rechaza o modifica cada recomendación.
5. **Catálogo.** Canciones una por una o importadas desde un JSON (`docs/ejemplos/catalogo_ejemplo.json`).

El flujo de preguntas sigue el árbol de decisión y evita combinaciones que llevan a error:

- El **género se toma de la canción que suena**; solo se pregunta si no se eligió canción. El servidor rechaza un género que contradiga a la canción.
- En la pregunta de la reacción aparecen **primero las reacciones que tienen regla para ese género** (por ejemplo, con salsa: «baila poco», «sin reacción» y «se está retirando»). Esa lista sale de las reglas, no está escrita en la interfaz.
- El evento nuevo se crea al confirmar el resumen, no antes.

## Capas y archivos

| Archivo | Capa | Contenido |
|---|---|---|
| `reglas.json` | Conocimiento | Variables, valores, reglas R01–R27, parámetros (BPM 10 y 5, Camelot 3, energía 1), técnicas y casos de transición. |
| `esquema.sql` | Datos | Las 17 tablas, los disparadores de integridad y las 2 vistas (PostgreSQL). |
| `datos.py` | Datos | `ConexionBD` y las clases DAO: `ConocimientoDAO`, `UsuarioDAO`, `CancionDAO`, `EventoDAO`, `ContextoDAO`, `RecomendacionDAO`, `DecisionDAO`. |
| `negocio.py` | Negocio | `MotorDJ` (inferencia) y `ServicioSesion` (cuenta, CU01–CU05, historial). |
| `ejemplos.py` | Negocio | Catálogo ficticio y los cinco casos de ejemplo. |
| `app.py` | Presentación | API Flask con sesión e interfaz web. |
| `main.py` | Presentación | Consola con el mismo motor; lee `reglas.json` y no usa la base. |
| `docs/` | Documentación | Diagramas, capturas y scripts SQL. |

## Qué hace el motor

1. **Dispara reglas** (encadenamiento hacia adelante): una regla se dispara si cada variable de su antecedente tiene un valor del contexto. Valores de la misma variable se combinan con O; variables distintas, con Y.
2. **Detecta conflictos**: si una regla pide subir la energía (R10, R20) y otra bajarla (R11, R21, R26), las muestra y no elige. El documento no define prioridades.
3. **Selecciona canciones** del catálogo según la acción de la regla, entre las compatibles con la canción que suena (distancia circular de los números Camelot ≤ 3; la letra A/B no se considera, como en el documento).
4. **Asigna técnicas**: diferencia de BPM ≤ 5 → cross-fade y mezcla sencilla; entre 5 y 10 → ajuste de tempo y luego cross-fade; > 10 → ajuste de tempo; cambio de género → corte directo; siempre sincronización de BPM y echo out al cambiar de canción.
5. **Explica** cada recomendación: hechos, reglas, filtro, canción y técnicas (RF04).

No calcula probabilidades: el documento no define pesos.

| Reglas | Acción | Selección en el catálogo |
|---|---|---|
| R01–R09, R12–R17 | `CRITERIO` | Ninguna: muestran su conclusión. |
| R10, R20 | `SUBIR_ENERGIA` | Energía mayor que la actual. |
| R11, R26 | `BAJAR_ENERGIA` | Energía menor que la actual. |
| R21 | `BAJAR_O_COMERCIAL` | Energía menor o canción comercial; primero las comerciales. |
| R18 | `MANTENER_GENERO` | Mismo género, por energía más cercana. |
| R19 | `MANTENER_ENERGIA` | Mismo género y energía a 1 punto o menos de la actual. |
| R22 | `CAMBIAR_GENERO` | Ninguna: hay que confirmar qué género pide el público. |
| R23 | `MISMO_GENERO` | Mismo género; primero las canciones conocidas. |
| R24, R27 | `CONSULTAR` | Ninguna: se consulta al público antes de cambiar. |
| R25 | `BUSCAR_OTRA` | Otra canción compatible; antes hay que consultar la causa. |

## Cuentas y seguridad

- La contraseña se guarda solo como hash (`werkzeug.security`, scrypt con sal); nunca en claro ni en las respuestas de la API.
- La sesión viaja en una cookie firmada, `HttpOnly` y `SameSite=Lax`, y dura 12 horas. Con HTTPS, defina `COOKIE_SEGURA=1`.
- Todas las rutas de datos exigen sesión y cada DJ solo ve y cambia lo suyo: pedir un evento, una consulta o una canción ajena responde 404.
- El inicio de sesión responde lo mismo si el correo no existe o si la contraseña es incorrecta.
- No incluye recuperación de contraseña, verificación del correo ni límite de intentos de inicio de sesión.

## Persistencia

Cada proceso de `ServicioSesion` es una transacción. Al consultar se guardan juntos la fotografía del contexto, las recomendaciones, sus reglas, sus técnicas y el resultado completo (tabla `resultado_consulta`); si algo falla, no queda nada a medias. Contextos, recomendaciones, decisiones y resultados son de solo inserción.

`docs/sql/sistema_experto_dj.sql` es el mismo esquema con los datos del conocimiento, por si se quiere crear la base a mano con `psql`.

## Pruebas

```bash
python -m unittest -v
```

Las pruebas con base de datos usan `PRUEBAS_DATABASE_URL` o, si falta, `DATABASE_URL`. Cada prueba crea un esquema temporal `prueba_…` y lo borra al terminar, así que no tocan los datos de la aplicación. Sin conexión a PostgreSQL esas pruebas se omiten y solo corren las del motor.

| Archivo | Qué comprueba |
|---|---|
| `test_motor.py` | Disparo de reglas, conflictos, selección y técnicas. No usa base de datos. |
| `tests/test_web.py` | API: cuenta y sesión, flujo completo, historial y aislamiento entre usuarios. |
| `tests/test_persistencia.py` | Procesos transaccionales PT01–PT19 y restricciones de integridad RI01–RI16. |
| `tests/test_no_funcionales.py` | RNF01–RNF06, reglas R18–R27 y escenarios E1–E6 del documento. |
| `docs/sql/pruebas_integridad.sql` | Las restricciones directamente en PostgreSQL (35 casos). |

## Límites conocidos

- Los criterios de la versión 2 (R26–R27, energía ±1, técnica para 5–10 BPM, canción conocida y comercial) los adoptó el equipo y están pendientes de validar con DJs.
- CU06 (administrar reglas) se hace editando `reglas.json` antes de crear la base, o con `ConocimientoDAO`; no tiene pantalla.
- El conocimiento se carga cuando se crea el esquema. Para recargar `reglas.json` en una base existente hay que hacerlo con `ConocimientoDAO` o crear un esquema nuevo (`DJ_SCHEMA`).
- El documento Word y los diagramas de `docs/` describen la versión anterior (SQLite, sin inicio de sesión, formulario único).

## Despliegue

Ver `README_GOOGLE_CLOUD.md`.

## Adaptación de las decisiones al árbol del documento (noviembre de 2026)

Las reglas R01–R27 siguen el documento y se ejecutan desde PostgreSQL. Se añadieron
preguntas de confirmación para las conclusiones condicionales R10, R20, R21 y R25:
no se modifica la energía o el género por suposiciones sobre el público. Las
aclaraciones se guardan en el historial JSONB de cada consulta. Se conserva el
inicio de sesión con contraseña y la separación persistente por DJ.

Ver `GUIA_ADAPTACION_DIAGRAMAS.md` y ejecutar `python -m unittest test_diagramas.py`.
