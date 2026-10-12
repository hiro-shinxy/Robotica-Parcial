# Pregunta 1 - versión corregida de tu interprete_pkg

Conserva tus nombres (interprete_pkg, interprete_ordenes, /interpretar_orden, timeout_laya,
agarrar/cubo/rojo, prioridad 1 a 5, campo degradado). Todo lo de abajo se hace en la terminal del Jetson.

## Qué estaba mal y qué cambió

| Antes | Ahora |
|---|---|
| Se leían accion/objeto/color de claves de LAYA que no existen y, al faltar, se rellenaban en silencio con el clasificador local; prioridad siempre local | LAYA recibe 5 preguntas tipadas (3 choice, 1 score, 1 noul). Si responde algo inesperado, TODA la decisión pasa al respaldo y queda degradado=True con el motivo |
| state vacío en la petición | state = la frase |
| IP de LAYA escrita en el código | Parámetros laya_url, laya_endpoint, lang, laya_extra_json, umbral_permitido |
| Sin tiempos en la respuesta | Devuelve latencia_total/http/calculo/red (lee X-Inference-Time-Ms) |
| No se podía elegir método | Campo modo: "", "auto", "laya", "palabras_clave" (las llamadas viejas sin modo siguen funcionando) |
| Límite de tiempo solo por socket | Límite duro: el callback no espera más que timeout_laya |
| "ya" dentro de "ayuda" subía la prioridad a 5 | "ya" ahora solo cuenta como palabra completa |
| Solo atrapaba errores de conexión | 503, 401, JSON inválido y respuestas raras también van al respaldo |
| Sin motivo del rechazo | causa_rechazo, y lista de términos prohibidos |
| Medidor: 1 frase repetida, sin esperar respuesta | Lee las 50 frases del docente, espera cada respuesta, llama a LAYA y al respaldo, calcula mediana/P95 y exactitud |

## Paso 1 - Respaldo y copia de archivos

    cp -r ~/Robotica-Parcial/interprete_pkg ~/interprete_pkg_respaldo
    cd ~ && unzip -o interprete_pkg_v2.zip
    cp ~/interprete_pkg_v2/interprete_pkg/srv/InterpretarOrden.srv ~/Robotica-Parcial/interprete_pkg/srv/
    cp ~/interprete_pkg_v2/interprete_pkg/scripts/*.py ~/Robotica-Parcial/interprete_pkg/scripts/
    chmod +x ~/Robotica-Parcial/interprete_pkg/scripts/*.py

(El CMakeLists.txt y package.xml se quedan como están: ya instalan los dos scripts.)

## Paso 2 - Recompilar (cambió el .srv, así que es obligatorio)

    source /opt/ros/humble/setup.bash
    cd ~/p2_ws
    colcon build --symlink-install
    source install/setup.bash
    export ROS_DOMAIN_ID=52        # el que muestre tu cuadro System Information
    ros2 interface show interprete_pkg/srv/InterpretarOrden

Debe mostrar los campos nuevos (modo en la petición; causa_rechazo, fuente, motivo, exito, latencias...).
Apaga el nodo viejo (Ctrl+C) antes de lanzar el nuevo.

## Paso 3 - Verificar LAYA real ANTES de medir (lo más importante)

No pude ver el servidor del laboratorio. Esta prueba confirma que habla el formato que usa el nodo:

    export LAYA=http://IP:PUERTO      # tu código tenía 172.51.1.14:8000; usa la que dé el docente
    curl -s $LAYA/health
    curl -s -i $LAYA/v1/systemone -H 'content-type: application/json' -d '{"state":"recoge el cubo rojo","lang":"es","questions":{"color":{"type":"choice","instructions":"De que color es el objeto?","criteria":{"rojo":"color rojo","verde":"color verde","desconocido":"sin color"}},"permitido":{"type":"noul","instructions":"Es una orden segura?"}}}'

Debes ver una cabecera X-Inference-Time-Ms y un JSON con "answers" que contenga "choice" y "noul".
Si sale otra cosa (error 400/422 o un JSON distinto), el nodo no se rompe: caerá al respaldo con
motivo=respuesta_invalida o error_http y escribirá en el log el inicio de la respuesta del servidor.
Pega ese texto y se ajusta el formato.

## Paso 4 - Parámetros y nodo (terminal 1)

    cat > ~/p2_ws/mis_parametros.yaml <<'EOF'
    interprete_ordenes:
      ros__parameters:
        laya_url: "http://IP:PUERTO"
        timeout_laya: 5.0
        lang: "es"
        laya_extra_json: '{"preset": "multilingual"}'
    EOF
    ros2 run interprete_pkg interprete_ordenes.py --ros-args --params-file ~/p2_ws/mis_parametros.yaml

Cambia el preset por el que entregue el docente. timeout_laya 5.0 es SOLO para medir; después se baja
(regla: unas 3 veces el P95 en calma, sin pasar de ~2 s).

## Paso 5 - Pruebas manuales (terminal 2, con el bloque de 3 líneas source/export)

    ros2 service call /interpretar_orden interprete_pkg/srv/InterpretarOrden "{frase: 'toma el cubo rojo ya', modo: 'auto'}"
    ros2 service call /interpretar_orden interprete_pkg/srv/InterpretarOrden "{frase: 'lanza la caja azul', modo: 'auto'}"

La segunda debe volver con permitido=False y causa_rechazo. Para ver el respaldo: apaga la red de LAYA
o usa  -p laya_url:=http://127.0.0.1:9 -p timeout_laya:=1.0  y comprueba degradado=True, motivo=sin_conexion.

## Paso 6 - Las 50 frases

Guarda las frases del docente como ~/frases.csv: primera línea "frase" y luego una por línea.
Para la exactitud añade columnas con lo esperado, con estos nombres exactos:
accion_esperada, objeto_esperado, color_esperado, prioridad_esperada, permitido_esperado
(tus nombres de acción/objeto/color deben coincidir con los del docente: edita ACCIONES/OBJETOS/COLORES
al inicio de interprete_ordenes.py). Modelo: datos/frases_ejemplo.csv.

Antes de medir, escribe y haz commit de docs/PREDICCIONES.md.

    # CALMA (nadie más usa el servidor)
    ros2 run interprete_pkg medidor_evaluacion.py --frases ~/frases.csv --escenario calma \
      --salida ~/resultados_calma.csv --laya-url http://IP:PUERTO \
      --prediccion-mediana-ms 80 --prediccion-p95-ms 150

    # CARGA (todos a la vez, con la señal del docente)
    ros2 run interprete_pkg medidor_evaluacion.py --frases ~/frases.csv --escenario carga --rondas 5 \
      --esperar-enter --salida ~/resultados_carga.csv --laya-url http://IP:PUERTO

Cada corrida deja un CSV y un archivo *_tablas.md con mediana y P95 (HTTP, cálculo, red+cola, red pura)
y la tabla de exactitud LAYA contra palabras clave.

## Paso 7 - Ensayo en casa sin el servidor del laboratorio (opcional)

    python3 ~/interprete_pkg_v2/herramientas/laya_simulado.py --port 8000

y usa laya_url http://127.0.0.1:8000. Es un simulador: sus números NO se reportan.

## Paso 8 - Subir a GitHub (sin --force)

    cd ~/Robotica-Parcial
    mkdir -p evidencia docs && cp ~/resultados_*.csv ~/resultados_*_tablas.md evidencia/
    cp ~/interprete_pkg_v2/docs/*.md docs/
    git add . && git commit -m "Pregunta 1: nodo corregido, medidor y evidencia" && git push origin main

## Lo que sigue pendiente (no se puede hacer antes del examen)

Las 50 frases, la IP, el puerto y el preset los da el docente. Quedan por hacer ese día: las dos mediciones,
la explicación calma vs carga con tus números, la media página de qué frases falla cada método y el
informe (plantilla en docs/INFORME_plantilla.md, con la justificación de la salida tipada ya redactada).
