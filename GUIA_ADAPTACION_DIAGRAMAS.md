# Adaptación al documento Entrega Final Sistema Experto

## Qué se mantiene
- Login individual por correo y contraseña con hash, sesiones y PostgreSQL.
- Catálogo, eventos, recomendaciones, historial y decisiones asociados al DJ.
- Tablas del modelo relacional del documento y extensión `resultado_consulta` para el historial íntegro.
- Reglas R01–R27 en PostgreSQL, cargadas desde `reglas.json` al crear el esquema.

## Correspondencia con el árbol
1. Tipo de evento → R01–R06.
2. Momento → R07–R11.
3. Grupo de edad → R12–R17.
4. Género y reacción → R18–R27, con Y entre variables y O entre valores de una variable.
5. Preguntas de confirmación cuando la conclusión es condicional: R10, R20, R21 y R25.
6. Canciones compatibles, transición BPM/Camelot y decisión del DJ.

Las preguntas de confirmación son aclaraciones de la sesión, no nuevas reglas R28 ni columnas de contexto_evento; se conservan en `resultado_consulta.resultado` y se pueden recuperar desde el historial. Las reglas R10, R20, R21 y R25 siguen activándose según los antecedentes originales; la acción se ejecuta solamente cuando la información adicional la justifica.

**Nota:** Las preguntas condicionales son una adaptación operacional para evitar inferir hechos que el documento exige consultar. La evaluación no reproduce gráficamente el árbol.

## Base de datos y despliegue
`esquema.sql` crea el esquema PostgreSQL automáticamente en una base vacía. En una base existente no se ejecuta `DROP SCHEMA`: se preservan cuentas y registros. No se requiere migración destructiva para estas modificaciones; las aclaraciones se guardan en el JSONB ya existente.

Si la base fue creada con una versión antigua de las reglas, el sistema no sobrescribe automáticamente su conocimiento. Se debe comparar el contenido de `regla` y `condicion_regla` con `reglas.json` antes de migrarlo.

## Diferencia documental
La página 9 y el apartado de roles del documento dicen identificación sin contraseña. La implementación conserva `usuario.clave_hash` porque el docente solicitó identificación persistente. Actualizar ese texto y el modelo relacional del informe para reflejar el campo.

## Prueba recomendada
- Boda / cierre / adultos / pop / negativa → R02, R11, R15, R24.
- Discoteca / desarrollo / jóvenes / pop / baila_y_canta → R05, R09, R14, R19.
- Salsa / baila_poco → R20, pero solo sube energía cuando se confirma baile y participación.
- Electrónica / sentado → R21, primero consulta si desea bailar.
- Salsa / sin_reaccion → R25, primero consulta la causa.
- Cierre / se_retira → R11 y R26; antes del cierre, R27.

Para desplegar, utilizar las instrucciones existentes en `README_GOOGLE_CLOUD.md`. Los cambios no despliegan automáticamente ninguna nueva versión.
