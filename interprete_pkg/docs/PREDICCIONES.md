# Predicciones (se llenan ANTES de medir — el docente puede pedir ver la hora del commit)

Regla del examen: escribir lo que se espera obtener antes de ejecutar cada medición.
Haga `git commit` de este archivo ANTES de correr el benchmark: el commit es la prueba.

| # | Medición | Predicción | Razonamiento (1 línea) | Hora | Medido | Diferencia |
|---|---|---|---|---|---|---|
| 1 | Mediana HTTP LAYA, laboratorio en calma (ms) | | | | | |
| 2 | P95 HTTP LAYA, en calma (ms) | | | | | |
| 3 | Cálculo del servidor, mediana (ms) | | | | | |
| 4 | Red+cola (HTTP − cálculo), mediana en calma (ms) | | | | | |
| 5 | Mediana HTTP bajo carga (ms) | | | | | |
| 6 | P95 HTTP bajo carga (ms) | | | | | |
| 7 | ¿Cuántos timeouts (de 50) con el límite elegido, bajo carga? | | | | | |
| 8 | Exactitud decisión completa LAYA (%) | | | | | |
| 9 | Exactitud decisión completa palabras clave (%) | | | | | |

Pistas para predecir con criterio (no al azar):
- El README de LAYA reporta ~33–40 ms por pregunta en GPU T4, y ~337 ms por 50 preguntas en lote; usted manda 5 preguntas por frase.
- El servidor procesa UNA petición a la vez: bajo carga la espera en cola se suma al cálculo.
- LAYA base, sin ajuste fino, rinde cerca del azar en tareas que no entrenó (lo dice su propio README).
