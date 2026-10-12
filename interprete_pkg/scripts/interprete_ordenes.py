#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
import requests
from interprete_pkg.srv import InterpretarOrden

class InterpreteOrdenes(Node):
    def __init__(self):
        super().__init__('interprete_ordenes')
        self.declare_parameter('timeout_laya', 2.0)
        self.laya_url = "http://172.51.1.14:8000/v1/systemone" 
        self.srv = self.create_service(InterpretarOrden, '/interpretar_orden', self.interpretar_callback)
        self.get_logger().info('Servicio /interpretar_orden listo (Prioridad 1 a 5).')

    def clasificador_palabras_clave(self, frase):
        frase_low = frase.lower()
        
        accion = "agarrar" if any(w in frase_low for w in ["coge", "agarra", "toma", "mueve"]) else "desconocida"
        objeto = "cubo" if "cubo" in frase_low else "desconocido"
        
        color = "desconocido"
        for c in ["rojo", "azul", "verde", "amarillo"]:
            if c in frase_low: color = c
                
        # Prioridad del 1 al 5
        prioridad = 1
        if any(p in frase_low for p in ["emergencia", "inmediatamente", "ya"]):
            prioridad = 5
        elif any(p in frase_low for p in ["urgente", "urgentemente", "rapido", "rápido"]):
            prioridad = 4
        elif any(p in frase_low for p in ["prioritario", "cuanto antes"]):
            prioridad = 3
        elif "pronto" in frase_low:
            prioridad = 2

        permitido = True if accion != "desconocida" and color != "desconocido" else False
        return accion, objeto, color, prioridad, permitido

    def interpretar_callback(self, request, response):
        self.get_logger().info(f'Procesando: "{request.frase}"')
        timeout_val = self.get_parameter('timeout_laya').get_parameter_value().double_value
        
        payload = {
            "preset": "multilingual",
            "questions": {
                "q1": {
                    "text": request.frase,
                    "type": "noul",
                    "instructions": "Clasifica la intencion de accion"
                }
            },
            "state": {} 
        }
        
        accion_loc, objeto_loc, color_loc, prioridad_loc, permitido_loc = self.clasificador_palabras_clave(request.frase)
        
        try:
            res = requests.post(self.laya_url, json=payload, timeout=timeout_val)
            res.raise_for_status()
            
            datos = res.json()
            respuesta_q1 = datos.get("answers", {}).get("q1", {})
            probabilidad_accion = respuesta_q1.get("action", {}).get("act_probability", 0.0)
            
            response.accion = respuesta_q1.get('accion', accion_loc)
            response.objeto = respuesta_q1.get('objeto', objeto_loc)
            response.color = respuesta_q1.get('color', color_loc)
            response.prioridad = prioridad_loc
            response.permitido = True if probabilidad_accion > 0.6 else False
            response.degradado = False 
            
        except requests.exceptions.RequestException:
            self.get_logger().warn(f'Fallo conexion con LAYA, usando modo degradado.')
            response.accion = accion_loc
            response.objeto = objeto_loc
            response.color = color_loc
            response.prioridad = prioridad_loc
            response.permitido = permitido_loc
            response.degradado = True 
            
        return response

def main(args=None):
    rclpy.init(args=args)
    nodo = InterpreteOrdenes()
    try:
        rclpy.spin(nodo)
    except KeyboardInterrupt:
        pass
    finally:
        nodo.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
