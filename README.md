# Sistema experto DJ — Python + Flask + PostgreSQL


## Puesta en marcha Local

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

### 3. Instalar y ejecutar

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux o macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py                     # http://127.0.0.1:5000/
```

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


