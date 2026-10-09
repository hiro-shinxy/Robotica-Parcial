#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
import csv
import time
from interprete_pkg.srv import InterpretarOrden 

class MedidorEvaluacion(Node):
    def __init__(self):
        super().__init__('medidor_evaluacion')
        
        # Crea el cliente para comunicarse con el servicio
        self.cliente = self.create_client(InterpretarOrden, '/interpretar_orden')
        
        while not self.cliente.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('Esperando a que el servicio /interpretar_orden esté disponible...')
            
        # El docente entregará 50 frases. Aquí pones las reales el día del examen.
        # Rellenamos una lista de prueba con 50 elementos para verificar el código.
        frase_ejemplo = "agarra el cubo rojo y ponlo en la caja"
        self.frases = [f"{frase_ejemplo} {i}" for i in range(1, 51)] 
        
        self.resultados = []
        self.latencias = []
        
    def ejecutar_medicion(self):
        self.get_logger().info('Iniciando medición de 50 frases...')
        
        for i, frase in enumerate(self.frases):
            req = InterpretarOrden.Request()
            req.frase = frase
            
            # Registrar tiempo antes de llamar al servicio
            inicio = time.time()
            
            # Llamada síncrona al servicio ROS 2
            futuro = self.cliente.call_async(req)
            rclpy.spin_until_future_complete(self, futuro)
            
            # Registrar tiempo al recibir respuesta
            fin = time.time()
            
            latencia_total = fin - inicio
            respuesta = futuro.result()
            
            self.latencias.append(latencia_total)
            
            # Almacenar fila para el CSV
            self.resultados.append({
                'ID': i + 1,
                'Frase': frase,
                'Accion': respuesta.accion,
                'Objeto': respuesta.objeto,
                'Color': respuesta.color,
                'Prioridad': respuesta.prioridad,
                'Permitido': respuesta.permitido,
                'Degradado': respuesta.degradado,
                'Latencia_Total_s': round(latencia_total, 4)
            })
            self.get_logger().info(f'Progreso: {i+1}/50')
            
        self.generar_reporte_csv()
        self.imprimir_estadisticas()
        
    def generar_reporte_csv(self):
        nombre_archivo = 'resultados_50_frases.csv'
        with open(nombre_archivo, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=self.resultados[0].keys())
            writer.writeheader()
            writer.writerows(self.resultados)
            
        self.get_logger().info(f'Archivo CSV generado exitosamente: {nombre_archivo}')
        
    def imprimir_estadisticas(self):
        # Calcular Mediana y Percentil 95 (Requisito del examen)
        self.latencias.sort()
        n = len(self.latencias)
        
        # Cálculo de mediana
        if n % 2 == 0:
            mediana = (self.latencias[n//2 - 1] + self.latencias[n//2]) / 2.0
        else:
            mediana = self.latencias[n//2]
            
        # Cálculo de percentil 95
        p95_index = int(0.95 * n) - 1
        p95 = self.latencias[max(0, p95_index)]
        
        print("\n" + "="*40)
        print("  RESULTADOS DE LATENCIA (PREGUNTA 1)  ")
        print("="*40)
        print(f"Total de frases medidas : {n}")
        print(f"Mediana                 : {mediana:.4f} segundos")
        print(f"Percentil 95            : {p95:.4f} segundos")
        print("="*40 + "\n")

def main(args=None):
    rclpy.init(args=args)
    medidor = MedidorEvaluacion()
    medidor.ejecutar_medicion()
    medidor.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
