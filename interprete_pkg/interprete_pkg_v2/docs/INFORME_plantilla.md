# Informe — Pregunta 1: El servicio de interpretación de órdenes
Equipo N.º __ · Integrantes: ______ · ROS_DOMAIN_ID: __ · Repo: ______

## 1. Diseño
- Nodo `interprete_ordenes`, servicio `/interpretar_orden` (`interprete_pkg/srv/InterpretarOrden`).
- Campos de la decisión: acción, objeto, color, prioridad (int 1–3), permitido (bool) + trazabilidad (fuente, degradado, motivo, latencias).
- Preguntas tipadas a LAYA: 3 × `choice` (acción, objeto, color), 1 × `score` (prioridad), 1 × `noul` (permitido). Una sola petición HTTP, un solo paso hacia adelante.
- Parámetros declarados: `timeout_laya = ___` (justificar con la tabla de calma: ___ × P95), `laya_url`, `lang`, `umbral_permitido`, `usar_disyuntor`.
- Respaldo: clasificador por palabras clave (`clasificar_palabras()`), respuesta marcada `degradado=true`, `fuente="palabras_clave"`, y `motivo` (timeout, sin_conexion, servidor_ocupado, disyuntor_abierto).

## 2. Por qué la salida debe ser tipada y no texto (justificación exigida)
(Adapte con sus palabras; estos son los argumentos que sostienen la decisión.)
1. **Espacio de acciones cerrado.** Un brazo solo puede ejecutar un conjunto finito de acciones. Con `choice` es imposible que el modelo "invente" una acción fuera de ese conjunto; con texto libre habría que interpretar la redacción y cualquier error de interpretación termina en movimiento físico.
2. **Sin análisis de texto (parsing).** No hay expresiones regulares ni formatos que se rompan; la salida ya es un valor del tipo que el resto del sistema espera.
3. **Alucinación acotada.** Un modelo generativo puede producir una orden plausible pero inexistente ("gira la muñeca 400°"). Un clasificador solo puede equivocarse *dentro* del vocabulario validado, y ese error es medible (exactitud).
4. **Tiempo acotado y predecible.** Un paso hacia adelante (decenas de ms) frente a generar token por token (cientos de ms a segundos y de duración variable). En un sistema con plazo duro (timeout) la latencia predecible es un requisito de seguridad.
5. **Confianza calibrada y auditable.** Las probabilidades permiten rechazar o escalar a un humano cuando la confianza es baja, y quedan registradas para revisar qué decidió el sistema y por qué.
6. **Seguridad como filtro previo.** La pregunta `permitido` produce un booleano verificable antes de encolar; una negativa no depende de que el modelo "redacte" bien un rechazo.

## 3. Latencia (pegar tablas generadas por `medidor_evaluacion.py`)
### 3.1 Laboratorio en calma
### 3.2 Laboratorio bajo carga
### 3.3 Separación red vs cálculo
- Cálculo: cabecera `X-Inference-Time-Ms` del servidor.
- Red + cola = tiempo HTTP total − cálculo. Incluye serialización, la red y **la espera en la cola del servidor** (procesa una petición a la vez).
- Red pura de referencia: `GET /health` (no usa el modelo).
### 3.4 Explicación de la diferencia calma vs carga
(Con SUS números: ¿creció el cálculo o creció red+cola? ¿Qué muestra `/health`? Conclusión esperada: el cálculo casi no cambia, lo que crece es la espera en cola.)
### 3.5 Predicho vs medido (de `docs/PREDICCIONES.md`)

## 4. Exactitud (tabla comparativa LAYA vs palabras clave)

## 5. Comentario: qué tipo de frases falla cada método (media página)
Abra el CSV y filtre las filas donde la decisión no coincide con la esperada. Categorías para clasificar sus fallos:
- Palabras clave: negaciones ("no recojas…"), sinónimos y regionalismos fuera de la lista, frases sin objeto explícito ("suelta eso"), palabras ambiguas ("para" preposición vs verbo), órdenes prohibidas con redacción amable o sin palabras de la lista, orden de varias acciones.
- LAYA: vocabulario cercano entre opciones (cubo vs caja), descripciones de opciones poco discriminativas, frases cortas sin contexto, uso fuera de lo que el modelo fue ajustado (su README admite que el modelo base rinde cerca del azar sin ajuste fino), preguntas `score` (ordinales) son su primitiva más débil.
Cierre: qué método usarían para cada tipo de frase y por qué el respaldo existe aunque sea menos exacto.

## 6. Evidencia entregada
`evidencia/resultados_calma.csv`, `evidencia/resultados_carga.csv`, `resultados_calma_tablas.md`, `resultados_carga_tablas.md`, `parametros_usados.yaml`, video corto del respaldo (servidor desconectado).
