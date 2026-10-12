#!/usr/bin/env python3
"""Servicio ROS 2 que convierte una frase en una decisión tipada con LAYA.

El servidor LAYA es externo al grafo ROS 2 y se consulta por HTTP.
Si LAYA supera el timeout o devuelve una respuesta inválida, se usa el
clasificador local y la respuesta queda marcada como degradada.
"""
import json
import time

import requests
import rclpy
from rclpy.node import Node
from interprete_pkg.srv import InterpretarOrden

ACCIONES = {"agarrar", "soltar", "mover", "detener", "desconocida"}
OBJETOS = {"cubo", "caja", "esfera", "cilindro", "desconocido"}
COLORES = {"rojo", "azul", "verde", "amarillo", "desconocido"}


def normalizar(texto):
    return " ".join(str(texto or "").strip().lower().split())


def a_bool(valor):
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor >= 0.5
    if isinstance(valor, str):
        return normalizar(valor) in {"true", "si", "sí", "permitido", "yes", "1"}
    return False


class InterpreteOrdenes(Node):
    def __init__(self):
        super().__init__("interprete_ordenes")
        self.declare_parameter("laya_url", "http://172.51.1.2:8000/v1/systemone")
        self.declare_parameter("timeout_laya", 2.0)
        self.declare_parameter("modelo_laya", "multilingual")
        self.declare_parameter("umbral_permitido", 0.5)
        self.declare_parameter("api_key_env", "LAYA_API_KEY")
        self.srv = self.create_service(
            InterpretarOrden, "/interpretar_orden", self.interpretar_callback
        )
        self.session = requests.Session()
        self.get_logger().info("Servicio /interpretar_orden listo")

    def clasificador_palabras_clave(self, frase):
        """Clasificador determinista de respaldo. No sustituye la evaluación real."""
        t = normalizar(frase)
        palabras = set(t.replace(",", " ").replace(".", " ").split())

        if any(x in palabras for x in ("detente", "detener", "para", "alto", "stop")):
            accion = "detener"
        elif any(x in palabras for x in ("suelta", "soltar", "deja")):
            accion = "soltar"
        elif any(x in palabras for x in ("mueve", "mover", "lleva", "traslada")):
            accion = "mover"
        elif any(x in palabras for x in ("agarra", "agarrar", "coge", "toma", "recoge")):
            accion = "agarrar"
        else:
            accion = "desconocida"

        objeto = next((o for o in ("cubo", "caja", "esfera", "cilindro") if o in palabras), "desconocido")
        color = next((c for c in ("rojo", "azul", "verde", "amarillo") if c in palabras), "desconocido")

        if any(x in t for x in ("emergencia", "inmediatamente", "ahora mismo")):
            prioridad = 5
        elif any(x in t for x in ("urgente", "urgentemente", "rápido", "rapido")):
            prioridad = 4
        elif any(x in t for x in ("prioridad alta", "cuanto antes", "cuanto antes")):
            prioridad = 3
        elif "pronto" in palabras:
            prioridad = 2
        else:
            prioridad = 1

        # Regla conservadora de ejemplo. Ajustar a la política de seguridad acordada
        # con el docente; las órdenes desconocidas no se autorizan.
        permitido = accion != "desconocida" and objeto != "desconocido" and color != "desconocido"
        if accion == "detener":
            permitido = True
        return accion, objeto, color, prioridad, permitido

    @staticmethod
    def choice_value(answer, default="desconocido"):
        if not isinstance(answer, dict):
            return default
        value = answer.get("choice", default)
        return str(value) if value is not None else default

    def consultar_laya(self, frase):
        """Devuelve decisión y tiempos. LAYA trabaja con decisiones tipadas choice/score/noul."""
        url = self.get_parameter("laya_url").value
        timeout = float(self.get_parameter("timeout_laya").value)
        modelo = str(self.get_parameter("modelo_laya").value)
        umbral = float(self.get_parameter("umbral_permitido").value)

        payload = {
            "model": modelo,
            "state": frase,
            "questions": {
                "accion": {
                    "type": "choice",
                    "instructions": "Elige la acción solicitada en la orden robótica.",
                    "criteria": {
                        "agarrar": "recoger o tomar un objeto con el brazo robotico",
                        "soltar": "liberar o dejar un objeto",
                        "mover": "mover o trasladar un objeto o el brazo",
                        "detener": "parar inmediatamente el movimiento",
                        "desconocida": "no se identifica una acción de la lista"
                    }
                },
                "objeto": {
                    "type": "choice",
                    "instructions": "Identifica el objeto mencionado; si no aparece, elige desconocido.",
                    "criteria": {
                        "cubo": "un cubo",
                        "caja": "una caja",
                        "esfera": "una esfera",
                        "cilindro": "un cilindro",
                        "desconocido": "ninguno de los objetos disponibles o no se identifica"
                    }
                },
                "color": {
                    "type": "choice",
                    "instructions": "Identifica el color mencionado; si no aparece, elige desconocido.",
                    "criteria": {
                        "rojo": "color rojo",
                        "azul": "color azul",
                        "verde": "color verde",
                        "amarillo": "color amarillo",
                        "desconocido": "no se identifica un color de la lista"
                    }
                },
                "prioridad": {
                    "type": "choice",
                    "instructions": "Asigna prioridad entera de 1 a 5 según la urgencia expresada. 1 es normal y 5 es máxima.",
                    "criteria": {
                        "1": "normal, sin urgencia expresa",
                        "2": "algo pronto",
                        "3": "prioritario o cuanto antes",
                        "4": "urgente o rápido",
                        "5": "emergencia o inmediatamente"
                    }
                },
                "permitido": {
                    "type": "noul",
                    "instructions": "¿La orden es segura y permitida según esta política? Solo se permiten acciones conocidas sobre un objeto y color identificados. Una orden desconocida o que pide detenerse no es peligrosa; detener es permitido.",
                    "criteria": {
                        "false": "la orden no está permitida o no se puede identificar con suficiente claridad",
                        "true": "la orden está permitida y es suficientemente clara"
                    }
                }
            }
        }

        api_key_env = str(self.get_parameter("api_key_env").value)
        import os
        api_key = os.environ.get(api_key_env, "").strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        inicio = time.perf_counter()
        response = self.session.post(url, json=payload, headers=headers, timeout=timeout)
        total_ms = (time.perf_counter() - inicio) * 1000.0
        response.raise_for_status()
        data = response.json()
        answers = data.get("answers")
        if not isinstance(answers, dict):
            raise ValueError("Respuesta LAYA sin objeto 'answers'")

        accion = self.choice_value(answers.get("accion"))
        objeto = self.choice_value(answers.get("objeto"))
        color = self.choice_value(answers.get("color"))
        prioridad_txt = self.choice_value(answers.get("prioridad"), "1")
        try:
            prioridad = int(prioridad_txt)
        except (TypeError, ValueError):
            raise ValueError(f"Prioridad no entera recibida: {prioridad_txt!r}")
        prioridad = max(1, min(5, prioridad))

        permit_answer = answers.get("permitido", {})
        p_true = permit_answer.get("noul") if isinstance(permit_answer, dict) else None
        if not isinstance(p_true, (int, float)):
            raise ValueError("Respuesta LAYA 'permitido' no contiene un valor noul numérico")
        permitido = float(p_true) >= umbral

        # La API de LAYA publica el tiempo de inferencia en X-Inference-Time-Ms
        # o Server-Timing: inference;dur=...; se conserva como cálculo del servidor.
        calc_ms = None
        header_calc = response.headers.get("X-Inference-Time-Ms")
        if header_calc is not None:
            try:
                calc_ms = float(header_calc)
            except ValueError:
                calc_ms = None
        if calc_ms is None:
            server_timing = response.headers.get("Server-Timing", "")
            for item in server_timing.split(","):
                item = item.strip()
                if item.startswith("inference;") and "dur=" in item:
                    try:
                        calc_ms = float(item.split("dur=", 1)[1].split(";", 1)[0])
                    except ValueError:
                        pass
        red_ms = max(0.0, total_ms - calc_ms) if calc_ms is not None else total_ms

        if accion not in ACCIONES or objeto not in OBJETOS or color not in COLORES:
            raise ValueError("La respuesta contiene una etiqueta fuera del esquema permitido")
        return accion, objeto, color, prioridad, permitido, total_ms, red_ms

    def interpretar_callback(self, request, response):
        frase = str(request.frase or "").strip()
        (response.accion_local, response.objeto_local, response.color_local,
         response.prioridad_local, response.permitido_local) = self.clasificador_palabras_clave(frase)
        response.latencia_laya_ms = 0.0
        response.latencia_red_ms = 0.0
        response.detalle_error = ""
        response.degradado = False
        response.metodo = "laya"

        try:
            (response.accion, response.objeto, response.color, response.prioridad,
             response.permitido, response.latencia_laya_ms,
             response.latencia_red_ms) = self.consultar_laya(frase)
        except (requests.RequestException, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            response.accion = response.accion_local
            response.objeto = response.objeto_local
            response.color = response.color_local
            response.prioridad = response.prioridad_local
            response.permitido = response.permitido_local
            response.degradado = True
            response.metodo = "clasificador_local"
            response.detalle_error = f"{type(exc).__name__}: {exc}"[:500]
            self.get_logger().warning(
                f"LAYA no disponible/respuesta inválida; se usa clasificador local: {response.detalle_error}"
            )
        return response


def main(args=None):
    rclpy.init(args=args)
    node = InterpreteOrdenes()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
