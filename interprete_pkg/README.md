# interprete_pkg — Pregunta 1 JetCobot

Paquete ROS 2 para el servicio `/interpretar_orden`. La API HTTP de LAYA es externa al grafo ROS 2.

## Archivos
- `srv/InterpretarOrden.srv`: frase de entrada y decisión tipada de salida.
- `scripts/interprete_ordenes.py`: consulta LAYA y usa un clasificador local si hay timeout, error HTTP o respuesta inválida.
- `scripts/medidor_evaluacion.py`: evalúa exactamente 50 frases, genera CSV, mediana/P95 y exactitud si las etiquetas están completas.
- `datos/frases_50.csv`: plantilla que debes completar con las 50 frases oficiales y etiquetas correctas.
- `informes/plantilla_informe.md`: plantilla de informe.

## 1. Requisitos
ROS 2 Humble (o la versión usada en el laboratorio), Python 3 y `requests`.

```bash
sudo apt install python3-requests
```

## 2. Configurar dirección de LAYA
Usa la IP y el puerto entregados por el docente. El valor predeterminado de este paquete conserva la dirección que estaba en el proyecto original, pero debes confirmarla en el examen:

```bash
ros2 run interprete_pkg interprete_ordenes.py --ros-args \
  -p laya_url:=http://IP_DEL_DOCENTE:8000/v1/systemone \
  -p timeout_laya:=2.0 -p modelo_laya:=multilingual
```

Si el servidor requiere clave, exporta la variable de entorno indicada por el docente; no la escribas en el código ni la subas a Git:

```bash
export LAYA_API_KEY='TU_CLAVE_SOLO_EN_EL_ENTORNO'
```

Si no se requiere autenticación, no necesitas definirla. El nodo admite configurar el nombre de la variable con `-p api_key_env:=LAYA_API_KEY`.

## 3. Compilar
Desde la raíz del workspace ROS 2, donde está `src/interprete_pkg`:

```bash
cd ~/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select interprete_pkg
source install/setup.bash
```

Comprueba que el servicio aparece:

```bash
ros2 service list | grep interpretar_orden
ros2 interface show interprete_pkg/srv/InterpretarOrden
```

## 4. Probar manualmente
En una terminal, inicia el nodo. En otra, llama al servicio (los campos nuevos de respuesta se muestran también):

```bash
ros2 service call /interpretar_orden interprete_pkg/srv/InterpretarOrden \
  "{frase: 'agarra el cubo rojo con prioridad urgente'}"
```

Prueba una frase no reconocida y prueba el timeout con una URL inaccesible. La respuesta debe indicar `degradado: true` y `metodo: clasificador_local` si LAYA falla.

## 5. Completar las 50 frases oficiales
Edita `datos/frases_50.csv`. Debe tener exactamente 50 filas de datos y estas columnas:

`id,frase,esperado_accion,esperado_objeto,esperado_color,esperado_prioridad,esperado_permitido`

Las columnas `esperado_*` deben ser etiquetas correctas verificadas, no predicciones del modelo. Para `esperado_permitido`, usa `true` o `false`. Si no hay etiquetas de referencia, el medidor puede registrar latencias y decisiones, pero no puede calcular exactitud.

## 6. Medición en calma
Ejecuta el nodo de interpretación y luego el medidor desde el directorio del paquete (o indica rutas absolutas):

```bash
ros2 run interprete_pkg medidor_evaluacion.py --ros-args \
  -p archivo_entrada:=/ruta/al/interprete_pkg/datos/frases_50.csv \
  -p archivo_salida:=resultados_calma.csv -p modo:=calma
```

## 7. Medición bajo carga
Durante la ventana de carga acordada, todos los equipos deben enviar solicitudes simultáneamente. Cada integrante ejecuta su medidor con su propio CSV y nombre de salida, por ejemplo `resultados_carga_equipo1.csv`. No basta con etiquetar una ejecución como carga si los otros equipos no están consultando al servidor a la vez. Conserva los CSV y anota cuántos equipos hicieron solicitudes y el horario.

## 8. Cómo se calcula
- Mediana: mediana de las 50 latencias de servicio medidas por el cliente ROS 2.
- P95: percentil 95 por método nearest-rank, posición `ceil(0.95*n)`.
- Tiempo de cálculo LAYA: encabezado `X-Inference-Time-Ms` o `Server-Timing: inference;dur=...` enviado por el servidor.
- Red/HTTP estimada: duración total de la petición HTTP menos el tiempo de inferencia del servidor. Incluye overhead HTTP/servidor y no es una medida física aislada de la red.
- Exactitud: una fila es correcta si acción, objeto, color, prioridad y permitido coinciden todos con las etiquetas esperadas.

## Advertencias importantes
1. La documentación actual de LAYA usa `state` y `questions`; las respuestas `choice` vienen en `answers.<id>.choice` y una respuesta `noul` en `answers.<id>.noul`. El código se ha preparado para ese formato. Confirma que el servidor del laboratorio usa la misma versión/API.
2. La política local de autorización es una regla demostrativa y conservadora; debes alinearla con la política de seguridad definida por el docente. No conectes este servicio a movimiento real sin validar las reglas y las órdenes permitidas.
3. El tiempo `latencia_red_ms` es una estimación (HTTP total menos inferencia reportada), no una medida de red independiente.
4. El paquete no contiene las 50 frases oficiales, los resultados de laboratorio ni evidencia de ejecución; debes incorporarlos tú.
