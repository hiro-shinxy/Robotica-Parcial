# Pregunta 1 — Servicio de interpretación de órdenes

## 1. Decisión tipada y seguridad
El nodo `interprete_ordenes` expone `/interpretar_orden` y devuelve acción, objeto, color, prioridad entera, autorización y estado degradado. La salida es tipada y no texto libre porque un sistema robótico necesita valores acotados que se puedan validar antes de ejecutar acciones; una respuesta redactada puede ser ambigua o contener instrucciones no válidas. El nodo de interpretación decide, pero no publica comandos directamente al brazo.

## 2. Timeout y modo degradado
- Timeout configurado: **[indicar valor medido/configurado] s**.
- Clasificador local: **[describir reglas usadas]**.
- Prueba de caída/timeout: **[describir procedimiento y evidencia]**.
- Evidencia adjunta: **[ros2 bag, log o video]**.

## 3. Latencia
Completar con resultados reales de `resultados_50_frases.csv`.

| Condición | n | Mediana servicio (ms) | P95 servicio (ms) | Cálculo LAYA (ms) | Red/HTTP estimada (ms) |
|---|---:|---:|---:|---:|---:|
| Laboratorio en calma | 50 | [ ] | [ ] | [ ] | [ ] |
| Bajo carga simultánea | 50 por equipo | [ ] | [ ] | [ ] | [ ] |

La latencia del servicio medida desde el cliente ROS 2 incluye comunicación ROS 2, llamada HTTP, inferencia y retorno. El tiempo de inferencia del servidor se toma del encabezado `X-Inference-Time-Ms` o `Server-Timing`; la diferencia entre la duración HTTP total y la inferencia es una estimación de red/HTTP y overhead del servidor, no una medición física pura de la red.

## 4. Exactitud
Las etiquetas de referencia deben corresponder a las respuestas correctas aprobadas por el docente. Una frase se considera correcta si coinciden **todos** los campos evaluados.

| Método | Correctas | Evaluadas | Exactitud |
|---|---:|---:|---:|
| LAYA | [ ] | [ ] | [ ] % |
| Clasificador por palabras clave | [ ] | [ ] | [ ] % |

## 5. Comentario sobre errores (media página)
[Completar después de analizar las 50 frases reales. Comparar frases con sinónimos, órdenes ambiguas, objetos/colores ausentes, negaciones, prioridades implícitas y órdenes no permitidas. No afirmar tendencias que no aparezcan en los resultados.] 

## 6. Evidencias
- Repositorio GitHub: [enlace]
- CSV de 50 frases y decisiones: [archivo]
- CSV/tabla en calma: [archivo]
- CSV/tabla bajo carga: [archivo]
- `ros2 bag` o video del timeout y modo degradado: [archivo]
